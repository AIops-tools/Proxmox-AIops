"""Resolve what a Proxmox async task actually did.

Proxmox VE's mutating endpoints are **asynchronous**: ``POST
.../status/start`` answers ``200`` with a task UPID *before* the operation
runs. A 200 therefore means "queued", not "done" — the real outcome lives in
the task's ``exitstatus``.

Treating the UPID as success made this tool report green for operations that
failed on the node. Live-verified against Proxmox VE 8.4.19 (2026-08-02): a
start that died with ``QEMU exited with code 1``, a shutdown that ended in
``VM quit/powerdown failed - got timeout``, and a backup that ended in ``job
errors`` were **all** recorded ``status=ok`` with ``effect_verified=1``. The
audit — this tool's central promise — was recording state changes that never
happened, and ``undo_list`` advertised them as verified.

The three verdicts map exactly onto the harness's existing outcome model, so
nothing new has to be invented downstream:

``OK``
    The node confirmed the change. The caller returns normally, the audit row
    says ``ok``, and the undo token is ``effect_verified=True``.
``FAILED``
    The node reported a definite failure. Raising here means ``@tool_errors``
    records ``status=error`` and :func:`_record_undo` writes **no** inverse —
    correct, because nothing changed.
``UNDETERMINED``
    The task had not finished within the wait budget, or its status could not
    be read. The change may or may not land, so the result is passed through
    :func:`~proxmox_aiops.governance.mark_unknown`: the audit says so and any
    undo token is flagged ``effect_verified=False``.

**Never guess.** An unreadable or unparseable task status is ``UNDETERMINED``,
never ``OK``. Assuming success on a probe failure is exactly the defect this
module exists to remove — the same "a failure that looks like health" shape as
a bare ``except: return []``.

Waiting is bounded by ``PROXMOX_TASK_WAIT_SECONDS`` (default
:data:`DEFAULT_WAIT_SECONDS`). Set it to ``0`` to never wait: every task that
has not already finished is then reported ``UNDETERMINED``, which is honest and
still leaves the UPID for ``cluster task-status`` to poll. Long operations
(clone, migrate, backup, move-disk) routinely outlast any sane budget — for
them ``UNDETERMINED`` is the truthful answer, not a degraded one.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from proxmox_aiops.governance import mark_unknown, sanitize

_log = logging.getLogger("proxmox-aiops.task")

#: How long to wait for a task to finish before reporting it undetermined.
DEFAULT_WAIT_SECONDS = 20.0
#: Env override; ``0`` disables waiting entirely.
WAIT_ENV = "PROXMOX_TASK_WAIT_SECONDS"
_POLL_INTERVAL_SECONDS = 0.5

#: Proxmox spells a successful task exactly this way.
_EXIT_OK = "OK"

OK = "ok"
FAILED = "failed"
UNDETERMINED = "undetermined"


class TaskFailed(RuntimeError):  # noqa: N818 — teaching error, reads as a statement
    """A Proxmox async task finished with a non-OK ``exitstatus``.

    Raised so the failure travels the ordinary error path: ``@tool_errors``
    flattens it into an ``{"error": ...}`` payload, the audit row says
    ``error``, and no undo token is recorded. A dedicated class (rather than a
    bare ``RuntimeError``) keeps "the node refused/failed the job" separable
    from "we could not talk to the node" — those need different operator
    responses, and collapsing them is bug class #5.
    """


def node_from_upid(upid: str) -> str | None:
    """Extract the node name from a UPID (``UPID:<node>:...``)."""
    parts = str(upid).split(":")
    return parts[1] if len(parts) > 2 and parts[0] == "UPID" else None


def _wait_budget() -> float:
    """Seconds to wait for a task, from the environment (never negative)."""
    raw = os.environ.get(WAIT_ENV)
    if raw is None:
        return DEFAULT_WAIT_SECONDS
    try:
        return max(0.0, float(raw))
    except ValueError:
        _log.warning("%s=%r is not a number; using the %ss default",
                     WAIT_ENV, raw, DEFAULT_WAIT_SECONDS)
        return DEFAULT_WAIT_SECONDS


def _read_status(conn: Any, node: str, upid: str) -> dict[str, Any] | None:
    """Read one task's status, or ``None`` when it cannot be determined.

    ``None`` means *unknown*, deliberately distinct from "still running" and
    from "finished". A transport error while polling says nothing about the
    task, so it must not be allowed to look like either outcome.
    """
    try:
        status = conn.nodes(node).tasks(upid).status.get()
    except Exception:  # noqa: BLE001 — a failed probe is a finding, not a crash
        _log.warning("could not read status of task %s on %s", upid, node,
                     exc_info=True)
        return None
    return status if isinstance(status, dict) else None


def wait_for_task(
    conn: Any, upid: str, node: str | None = None, timeout: float | None = None
) -> tuple[str, str]:
    """Poll a task until it finishes or the budget runs out.

    Returns ``(verdict, detail)`` where verdict is :data:`OK`, :data:`FAILED`
    or :data:`UNDETERMINED` and detail is a human-readable reason (empty for
    ``OK``). Never raises: the caller decides what a verdict means.
    """
    host_node = node or node_from_upid(upid)
    if not host_node:
        return UNDETERMINED, (
            f"could not determine the node from UPID {upid!r}, so the task "
            f"outcome could not be checked"
        )

    budget = _wait_budget() if timeout is None else max(0.0, timeout)
    deadline = time.monotonic() + budget
    last = "the task status could not be read"
    while True:
        status = _read_status(conn, host_node, upid)
        if status is not None:
            # 'stopped' is Proxmox's word for finished; exitstatus carries the
            # verdict. Absent exitstatus on a finished task is UNDETERMINED,
            # not OK — the node did not actually say it succeeded.
            if status.get("status") == "stopped":
                exit_status = status.get("exitstatus")
                if exit_status == _EXIT_OK:
                    return OK, ""
                if exit_status:
                    # Node-controlled text — clean it before it travels
                    # into an error message an agent will read.
                    return FAILED, sanitize(str(exit_status), 300)
                return UNDETERMINED, (
                    "the task finished but reported no exitstatus, so whether "
                    "it succeeded is unknown"
                )
            last = f"the task was still running after {budget:g}s"
        if time.monotonic() >= deadline:
            return UNDETERMINED, last
        time.sleep(min(_POLL_INTERVAL_SECONDS, max(0.0, deadline - time.monotonic())))


def settle(
    conn: Any,
    result: dict[str, Any],
    *,
    upid: str,
    node: str | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Attach a task's real outcome to a write result, or raise if it failed.

    Returns a NEW dict (the input is never mutated) carrying ``taskStatus``.
    On :data:`FAILED` it raises :class:`TaskFailed` so the failure is audited
    as an error with no undo token; on :data:`UNDETERMINED` the result is
    marked unknown so the audit and any undo token say so.

    A falsy ``upid`` means Proxmox applied the change **synchronously** and
    returned no task (an offline config edit does this). There is nothing to
    poll and nothing to doubt: the 2xx *is* the confirmation, so the result
    passes through as ``OK``. This is the one case where "no task" legitimately
    means success — everywhere else an unreadable task is UNDETERMINED.
    """
    if not upid or str(upid).lower() in ("none", "null"):
        return {**result, "taskStatus": OK}
    verdict, detail = wait_for_task(conn, upid, node=node, timeout=timeout)
    if verdict == FAILED:
        raise TaskFailed(
            f"Proxmox reported that task {upid} failed: {detail}. Nothing was "
            f"changed by this call — inspect the task log with "
            f"'cluster task-log {upid}' before retrying."
        )
    settled = {**result, "taskStatus": verdict}
    if verdict == UNDETERMINED:
        settled["taskDetail"] = detail
        return mark_unknown(settled)
    return settled
