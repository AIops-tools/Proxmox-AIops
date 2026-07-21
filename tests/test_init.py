"""Tests for the ``proxmox-aiops init`` onboarding wizard.

Driven end-to-end through Typer's CliRunner against an isolated
``PROXMOX_AIOPS_HOME`` — nothing touches the real ``~/.proxmox-aiops`` and no
network connection is ever attempted (the closing doctor prompt is declined).
"""

from __future__ import annotations

import pytest
import yaml
from typer.testing import CliRunner

import proxmox_aiops.cli.init as init_mod
import proxmox_aiops.config as config_mod
import proxmox_aiops.secretstore as ss
from proxmox_aiops.cli._root import app

pytestmark = pytest.mark.unit

MASTER_PW = "wizard-master-pw"
runner = CliRunner()


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    """Point every path constant the wizard touches at a throwaway home."""
    config_file = tmp_path / "config.yaml"
    monkeypatch.setenv("PROXMOX_AIOPS_HOME", str(tmp_path))
    monkeypatch.setenv(ss.MASTER_PASSWORD_ENV, MASTER_PW)

    monkeypatch.setattr(config_mod, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_mod, "CONFIG_FILE", config_file)
    monkeypatch.setattr(config_mod, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(init_mod, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(init_mod, "CONFIG_FILE", config_file)
    monkeypatch.setattr(ss, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(ss, "SECRETS_FILE", tmp_path / "secrets.enc")
    monkeypatch.setattr(ss, "LEGACY_ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(ss, "_cached", None)
    return tmp_path


@pytest.fixture
def fake_getpass(monkeypatch):
    """The wizard reads the target secret via getpass (bypasses stdin)."""
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "api-token-uuid")


def _run_init(answers: list[str]):
    return runner.invoke(app, ["init"], input="".join(a + "\n" for a in answers))


# name, host, auth kind, user, node(skip), port, verify TLS, add another?, run doctor?
HAPPY_ANSWERS = ["pve-lab", "192.0.2.10", "token", "root@pam!aiops", "", "8006", "y", "n", "n"]


def test_wizard_writes_config_to_isolated_home(isolated_home, fake_getpass):
    result = _run_init(HAPPY_ANSWERS)
    assert result.exit_code == 0, result.output

    raw = yaml.safe_load((isolated_home / "config.yaml").read_text("utf-8"))
    assert raw["targets"] == [
        {
            "name": "pve-lab",
            "host": "192.0.2.10",
            "user": "root@pam!aiops",
            "auth_kind": "token",
            "port": 8006,
            "verify_ssl": True,
        }
    ]


def test_secret_lands_encrypted_not_in_config(isolated_home, fake_getpass):
    _run_init(HAPPY_ANSWERS)

    config_text = (isolated_home / "config.yaml").read_text("utf-8")
    assert "api-token-uuid" not in config_text
    secrets_blob = (isolated_home / "secrets.enc").read_text("utf-8")
    assert "api-token-uuid" not in secrets_blob
    assert ss.SecretStore.unlock(MASTER_PW).get("pve-lab") == "api-token-uuid"


def test_init_writes_no_policy_rules(isolated_home, fake_getpass):
    """The skill no longer authorizes, so init seeds no rules.yaml — a fresh
    install delivers full functionality and leaves permission to the account."""
    result = _run_init(HAPPY_ANSWERS)
    assert result.exit_code == 0, result.output
    assert not (isolated_home / "rules.yaml").exists()


def test_verify_ssl_defaults_true_on_enter(isolated_home, fake_getpass):
    # Accept the TLS prompt with a bare Enter — secure default must be True.
    answers = ["pve-lab", "192.0.2.10", "token", "root@pam!aiops", "", "8006", "", "n", "n"]
    _run_init(answers)
    raw = yaml.safe_load((isolated_home / "config.yaml").read_text("utf-8"))
    assert raw["targets"][0]["verify_ssl"] is True


def test_verify_ssl_can_be_declined(isolated_home, fake_getpass):
    answers = ["pve-lab", "192.0.2.10", "token", "root@pam!aiops", "", "8006", "n", "n", "n"]
    _run_init(answers)
    raw = yaml.safe_load((isolated_home / "config.yaml").read_text("utf-8"))
    assert raw["targets"][0]["verify_ssl"] is False


def test_unknown_auth_kind_falls_back_to_token(isolated_home, fake_getpass):
    answers = ["pve-lab", "192.0.2.10", "kerberos", "root@pam!aiops", "", "8006", "y", "n", "n"]
    result = _run_init(answers)
    assert "defaulting to 'token'" in result.output
    raw = yaml.safe_load((isolated_home / "config.yaml").read_text("utf-8"))
    assert raw["targets"][0]["auth_kind"] == "token"


def test_optional_node_is_recorded(isolated_home, fake_getpass):
    answers = ["pve-lab", "192.0.2.10", "token", "root@pam!aiops", "pve1", "8006", "y", "n", "n"]
    _run_init(answers)
    raw = yaml.safe_load((isolated_home / "config.yaml").read_text("utf-8"))
    assert raw["targets"][0]["node"] == "pve1"


def test_existing_target_kept_when_overwrite_declined(isolated_home, fake_getpass):
    _run_init(HAPPY_ANSWERS)
    # Re-add the same name, decline overwrite, then add a fresh target.
    answers = [
        "pve-lab",  # duplicate name
        "n",  # overwrite? -> no, loop restarts
        "pve-new",
        "192.0.2.30",
        "token",
        "root@pam!aiops",
        "",
        "8006",
        "y",
        "n",  # add another?
        "n",  # doctor?
    ]
    result = _run_init(answers)
    assert result.exit_code == 0, result.output
    raw = yaml.safe_load((isolated_home / "config.yaml").read_text("utf-8"))
    names = [t["name"] for t in raw["targets"]]
    assert names == ["pve-lab", "pve-new"]
    # Original target untouched.
    assert raw["targets"][0]["host"] == "192.0.2.10"


def test_declining_doctor_prompt_skips_connectivity(isolated_home, fake_getpass, monkeypatch):
    def _boom(*a, **k):  # pragma: no cover — must not be reached
        raise AssertionError("run_doctor must not run when declined")

    monkeypatch.setattr("proxmox_aiops.doctor.run_doctor", _boom)
    result = _run_init(HAPPY_ANSWERS)
    assert result.exit_code == 0, result.output
