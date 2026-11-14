"""Setup AP policy with synthetic NetworkManager state; no radios are touched."""
import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def helper(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("hotspot_helper", ROOT / "deploy/usa-system-helper.py")
    h = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(h)
    h.STATE = tmp_path / "onboarding.json"
    h.DATA_DIR = tmp_path
    h.RECOVERY_STATE = tmp_path / "network-recovery.json"
    h.network_identity = lambda: {"interfaces": [{"type": "wifi", "connected": True, "hotspot": False}]}
    calls = []
    def run(*args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")
    h.run = run
    h.time = SimpleNamespace(sleep=lambda _: None)
    return h, calls


@pytest.mark.parametrize("ethernet", ["eth0", "enx1234", ""])
def test_missing_setup_ap_restored_independently_of_ethernet(helper, monkeypatch, ethernet):
    h, calls = helper
    monkeypatch.setattr(h, "hotspot_active", lambda: False)
    monkeypatch.setattr(h, "prepare_wifi", lambda: "wlan1")
    restored = []
    monkeypatch.setattr(h, "start_hotspot", restored.append)
    # Ethernet is deliberately absent from the decision, including its routes.
    h.run = lambda *a, **k: subprocess.CompletedProcess(a, 0, f"{ethernet}:ethernet\n", "")
    h.maintain_setup_hotspot()
    assert restored == ["wlan1"]


def test_healthy_ap_is_not_recreated_or_disconnected(helper, monkeypatch):
    h, calls = helper
    monkeypatch.setattr(h, "hotspot_active", lambda: True)
    h.maintain_setup_hotspot()
    h.start_hotspot("wlan0")
    h.network_boot()
    assert calls == []


@pytest.mark.parametrize("state", [{"network_mode": "home"}, [], None])
def test_timer_preserves_home_wifi_choice_and_unknown_state(helper, state):
    h, calls = helper
    h.STATE.write_text(json.dumps(state))
    h.maintain_setup_hotspot()
    assert not any(any(token in a for token in ("up", "down", "add", "delete", "modify")) for a in calls)


def test_invalid_state_does_not_take_over_radio(helper):
    h, calls = helper
    h.STATE.write_text("{partial")
    h.maintain_setup_hotspot()
    assert calls == []


def test_existing_profile_preserves_password_and_disables_wps(helper):
    h, calls = helper
    h.ensure_hotspot("wlan0")
    assert not any("delete" in a or "add" in a for a in calls)
    command = calls[-1]
    assert command[command.index("wifi-sec.wps-method") + 1] == "disabled"
    assert "wifi-sec.psk" not in command
    assert "shared" in command and "192.168.4.1/24" in command


def test_new_profile_requires_password_and_disables_wps(helper):
    h, calls = helper
    def run(*args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 10 if "connection.uuid" in args else 0, "", "")
    h.run = run
    h.ensure_hotspot("wlan1")
    add = next(a for a in calls if "add" in a)
    assert add[add.index("ifname") + 1] == "wlan1"
    assert add[add.index("wifi-sec.psk") + 1] == "dadtech1"
    assert calls[-1][calls[-1].index("wifi-sec.wps-method") + 1] == "disabled"


def test_hotspot_timeout_retries_and_observes_actual_state(helper, monkeypatch):
    h, calls = helper
    monkeypatch.setattr(h, "ensure_hotspot", lambda device: None)
    monkeypatch.setattr(h, "hotspot_active", lambda: False)
    attempts = []
    def run(*args, **kwargs):
        attempts.append(args)
        assert kwargs["timeout"] > int(args[args.index("--wait") + 1])
        if len(attempts) < 3:
            raise subprocess.TimeoutExpired(args, 25)
        return subprocess.CompletedProcess(args, 0, "", "")
    h.run = run
    h.start_hotspot("wlan0")
    assert len(attempts) == 3


def test_timer_installed_for_images_and_updates():
    for path in ["deploy/bootstrap-pi.sh", "image/pi-gen-stage/00-install-skelly-ai/files/install-chroot.sh"]:
        text = (ROOT / path).read_text()
        assert "usa-setup-hotspot.service usa-setup-hotspot.timer" in text
        assert "systemctl enable" in text
    timer = (ROOT / "deploy/usa-setup-hotspot.timer").read_text()
    assert "OnUnitInactiveSec=30s" in timer
    assert "RemainAfterExit" not in (ROOT / "deploy/usa-setup-hotspot.service").read_text()


def test_rollback_removes_units_absent_in_previous_release(helper, tmp_path, monkeypatch):
    h, calls = helper
    h.pathlib = SimpleNamespace(Path=lambda p: tmp_path / str(p).lstrip("/"))
    unit_dir = tmp_path / "etc/systemd/system"
    unit_dir.mkdir(parents=True)
    for name in ("usa-setup-hotspot.service", "usa-setup-hotspot.timer"):
        (unit_dir / name).write_text("new unit")
    backup = tmp_path / "backup"
    backup.mkdir()
    h.restore_hotspot_timer(backup)
    assert not list(unit_dir.iterdir())
    assert ("systemctl", "disable", "usa-setup-hotspot.timer") in calls


def test_rollback_keeps_previously_disabled_timer_disabled(helper, tmp_path):
    h, calls = helper
    h.pathlib = SimpleNamespace(Path=lambda p: tmp_path / str(p).lstrip("/"))
    backup = tmp_path / "backup"
    for name in ("usa-setup-hotspot.service", "usa-setup-hotspot.timer"):
        p = backup / "etc/systemd/system" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("previous unit")
    h.restore_hotspot_timer(backup)
    assert ("systemctl", "disable", "--now", "usa-setup-hotspot.timer") in calls
    assert not any("enable" in a for a in calls)
