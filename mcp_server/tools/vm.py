"""QEMU VM lifecycle MCP tools: list/get, start/stop, snapshot CRUD.

Every tool is wrapped with ``@governed_tool`` (the proxmox-aiops harness):
policy pre-check, budget/runaway guard, graduated-autonomy risk-tier gate,
audit logging to ~/.proxmox-aiops/audit.db, and undo-token recording. Write tools
that have a clean inverse pass an ``undo=`` lambda so the harness records a
reversal descriptor to the undo store.
"""


from typing import Optional

from mcp_server._shared import _get_connection, mcp, tool_errors
from proxmox_aiops.governance import governed_tool
from proxmox_aiops.ops import vm_lifecycle as vl


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def vm_list(target: Optional[str] = None, node: Optional[str] = None) -> list:
    """[READ] List QEMU VMs with name, vmid, status, cpu, mem.

    Scans the given node, the configured default node, or all cluster nodes.
    Use vm_get for full status of a single VM.

    Args:
        target: Proxmox target name from config; omit to use the default.
        node: Node name; omit to use the target's configured node / all nodes.
    """
    return vl.list_vms(_get_connection(target), node=node)


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("dict")
def vm_get(vmid: int, target: Optional[str] = None, node: Optional[str] = None) -> dict:
    """[READ] Return current status detail for a single VM by vmid.

    Args:
        vmid: Numeric Proxmox VM id (see vm_list).
        target: Proxmox target name from config.
        node: Node name; omit to auto-locate the VM across nodes.
    """
    return vl.get_vm(_get_connection(target), vmid, node=node)


@mcp.tool()
@governed_tool(
    risk_level="medium",
    undo=lambda params, result: {
        "tool": "vm_stop",
        "params": {"vmid": params.get("vmid"), "node": params.get("node")},
        "skill": "proxmox-aiops",
        "note": "Inverse of vm_start: power the VM back off.",
    },
)
@tool_errors("dict")
def vm_start(vmid: int, target: Optional[str] = None, node: Optional[str] = None) -> dict:
    """[WRITE] Start a VM. Returns the Proxmox task UPID. Inverse: vm_stop.

    Args:
        vmid: Numeric Proxmox VM id.
        target: Proxmox target name from config.
        node: Node name; omit to auto-locate the VM.
    """
    return vl.start_vm(_get_connection(target), vmid, node=node)


@mcp.tool()
@governed_tool(
    risk_level="medium",
    undo=lambda params, result: {
        "tool": "vm_start",
        "params": {"vmid": params.get("vmid"), "node": params.get("node")},
        "skill": "proxmox-aiops",
        "note": "Inverse of vm_stop: start the VM again.",
    },
)
@tool_errors("dict")
def vm_stop(vmid: int, target: Optional[str] = None, node: Optional[str] = None) -> dict:
    """[WRITE] Hard-stop (power off) a VM. Returns the task UPID. Inverse: vm_start.

    This is an immediate power-off (not a graceful guest shutdown); the guest
    filesystem may be left dirty. Audited to ~/.proxmox-aiops/audit.db.

    Args:
        vmid: Numeric Proxmox VM id.
        target: Proxmox target name from config.
        node: Node name; omit to auto-locate the VM.
    """
    return vl.stop_vm(_get_connection(target), vmid, node=node)


@mcp.tool()
@governed_tool(
    risk_level="medium",
    undo=lambda params, result: {
        "tool": "vm_snapshot_delete",
        "params": {
            "vmid": params.get("vmid"),
            "name": params.get("name"),
            "node": params.get("node"),
        },
        "skill": "proxmox-aiops",
        "note": "Inverse of vm_snapshot_create: delete the snapshot just made.",
    },
)
@tool_errors("dict")
def vm_snapshot_create(
    vmid: int, name: str, target: Optional[str] = None, node: Optional[str] = None
) -> dict:
    """[WRITE] Create a named snapshot of a VM. Inverse: vm_snapshot_delete.

    Args:
        vmid: Numeric Proxmox VM id.
        name: Snapshot name (must be unique for the VM).
        target: Proxmox target name from config.
        node: Node name; omit to auto-locate the VM.
    """
    return vl.snapshot_create(_get_connection(target), vmid, name, node=node)


@mcp.tool()
@governed_tool(risk_level="medium")
@tool_errors("dict")
def vm_snapshot_delete(
    vmid: int, name: str, target: Optional[str] = None, node: Optional[str] = None
) -> dict:
    """[WRITE] Delete a named snapshot from a VM.

    Args:
        vmid: Numeric Proxmox VM id.
        name: Snapshot name to delete (see vm_snapshot_list).
        target: Proxmox target name from config.
        node: Node name; omit to auto-locate the VM.
    """
    return vl.snapshot_delete(_get_connection(target), vmid, name, node=node)


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def vm_list_snapshots(
    vmid: int, target: Optional[str] = None, node: Optional[str] = None
) -> list:
    """[READ] List snapshots for a VM (name + description).

    Args:
        vmid: Numeric Proxmox VM id.
        target: Proxmox target name from config.
        node: Node name; omit to auto-locate the VM.
    """
    return vl.list_snapshots(_get_connection(target), vmid, node=node)


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("dict")
def vm_config(vmid: int, target: Optional[str] = None, node: Optional[str] = None) -> dict:
    """[READ] Return a VM's config (cores, memory, ostype, boot order).

    Args:
        vmid: Numeric Proxmox VM id.
        target: Proxmox target name from config.
        node: Node name; omit to auto-locate the VM.
    """
    return vl.get_vm_config(_get_connection(target), vmid, node=node)


@mcp.tool()
@governed_tool(
    risk_level="medium",
    undo=lambda params, result: {
        "tool": "vm_start",
        "params": {"vmid": params.get("vmid"), "node": params.get("node")},
        "skill": "proxmox-aiops",
        "note": "Inverse of vm_shutdown: start the VM again.",
    },
)
@tool_errors("dict")
def vm_shutdown(vmid: int, target: Optional[str] = None, node: Optional[str] = None) -> dict:
    """[WRITE] Graceful ACPI shutdown of a VM (vs the hard vm_stop). Inverse: vm_start.

    Args:
        vmid: Numeric Proxmox VM id.
        target: Proxmox target name from config.
        node: Node name; omit to auto-locate the VM.
    """
    return vl.shutdown_vm(_get_connection(target), vmid, node=node)


@mcp.tool()
@governed_tool(risk_level="medium")
@tool_errors("dict")
def vm_reboot(vmid: int, target: Optional[str] = None, node: Optional[str] = None) -> dict:
    """[WRITE] Reboot a VM (graceful). No undo token — reboot has no inverse.

    Args:
        vmid: Numeric Proxmox VM id.
        target: Proxmox target name from config.
        node: Node name; omit to auto-locate the VM.
    """
    return vl.reboot_vm(_get_connection(target), vmid, node=node)


@mcp.tool()
@governed_tool(
    risk_level="medium",
    undo=lambda params, result: (
        {
            "tool": "vm_reconfigure",
            "params": {
                "vmid": params.get("vmid"),
                "cores": (result or {}).get("previous", {}).get("cores"),
                "memory": (result or {}).get("previous", {}).get("memory"),
                "node": params.get("node"),
            },
            "skill": "proxmox-aiops",
            "note": "Inverse of vm_reconfigure: restore the previous cores/memory.",
        }
        if isinstance(result, dict) and result.get("previous")
        else None
    ),
)
@tool_errors("dict")
def vm_reconfigure(
    vmid: int,
    cores: Optional[int] = None,
    memory: Optional[int] = None,
    target: Optional[str] = None,
    node: Optional[str] = None,
) -> dict:
    """[WRITE] Change a VM's cores and/or memory (MiB). Inverse: restore prior values.

    Provide at least one of cores / memory. The previous values are captured so
    the harness records a reverse reconfigure as the undo token.

    Args:
        vmid: Numeric Proxmox VM id.
        cores: New vCPU core count (omit to leave unchanged).
        memory: New memory in MiB (omit to leave unchanged).
        target: Proxmox target name from config.
        node: Node name; omit to auto-locate the VM.
    """
    return vl.reconfigure_vm(
        _get_connection(target), vmid, cores=cores, memory=memory, node=node
    )


@mcp.tool()
@governed_tool(
    risk_level="medium",
    undo=lambda params, result: {
        "tool": "vm_delete",
        "params": {"vmid": (result or {}).get("newid"), "node": params.get("node")},
        "skill": "proxmox-aiops",
        "note": "Inverse of vm_clone: destroy the freshly-cloned VM.",
    },
)
@tool_errors("dict")
def vm_clone(
    vmid: int,
    newid: int,
    name: Optional[str] = None,
    target: Optional[str] = None,
    node: Optional[str] = None,
) -> dict:
    """[WRITE] Clone a VM to a new vmid. Returns the task UPID. Inverse: vm_delete(newid).

    Cloning is asynchronous — poll completion with task_status, do not re-issue.

    Args:
        vmid: Source VM id to clone from.
        newid: New (unused) VM id for the clone.
        name: Optional name for the clone.
        target: Proxmox target name from config.
        node: Node name; omit to auto-locate the source VM.
    """
    return vl.clone_vm(_get_connection(target), vmid, newid, name=name, node=node)


@mcp.tool()
@governed_tool(risk_level="high")
@tool_errors("dict")
def vm_delete(vmid: int, target: Optional[str] = None, node: Optional[str] = None) -> dict:
    """[WRITE] Permanently destroy a VM. IRREVERSIBLE — no undo token.

    Confirm with the user before calling. Audited to ~/.proxmox-aiops/audit.db.

    Args:
        vmid: Numeric Proxmox VM id to destroy.
        target: Proxmox target name from config.
        node: Node name; omit to auto-locate the VM.
    """
    return vl.delete_vm(_get_connection(target), vmid, node=node)


@mcp.tool()
@governed_tool(
    risk_level="high",
    undo=lambda params, result: {
        "tool": "vm_migrate",
        "params": {
            "vmid": params.get("vmid"),
            "target_node": (result or {}).get("from_node"),
            "node": (result or {}).get("to_node"),
        },
        "skill": "proxmox-aiops",
        "note": "Inverse of vm_migrate: migrate the VM back to its source node.",
    },
)
@tool_errors("dict")
def vm_migrate(
    vmid: int,
    target_node: str,
    online: bool = True,
    target: Optional[str] = None,
    node: Optional[str] = None,
) -> dict:
    """[WRITE] Migrate a VM to another node. Returns task UPID. Inverse: migrate back.

    Asynchronous — poll completion with task_status.

    Args:
        vmid: Numeric Proxmox VM id.
        target_node: Destination node name.
        online: True (default) for live migration; False to migrate while stopped.
        target: Proxmox target name from config.
        node: Source node name; omit to auto-locate the VM.
    """
    return vl.migrate_vm(
        _get_connection(target), vmid, target_node, node=node, online=online
    )


@mcp.tool()
@governed_tool(risk_level="high")
@tool_errors("dict")
def vm_snapshot_rollback(
    vmid: int, name: str, target: Optional[str] = None, node: Optional[str] = None
) -> dict:
    """[WRITE] Roll a VM back to a snapshot. IRREVERSIBLE — discards changes since then.

    No undo token (the discarded state cannot be recovered). Confirm with the user.

    Args:
        vmid: Numeric Proxmox VM id.
        name: Snapshot name to roll back to (see vm_list_snapshots).
        target: Proxmox target name from config.
        node: Node name; omit to auto-locate the VM.
    """
    return vl.rollback_snapshot(_get_connection(target), vmid, name, node=node)
