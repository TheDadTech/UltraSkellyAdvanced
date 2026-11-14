import importlib.util
import io
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "deploy" / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def iface(name, address, state="UP"):
    return {"ifname": name, "operstate": state,
            "addr_info": [{"local": address, "scope": "global"}]}


@pytest.mark.parametrize("address", ["127.0.0.1", "127.0.1.1", "169.254.3.4", "0.0.0.0", "224.0.0.1"])
def test_loopback_and_link_local_never_become_dashboard_addresses(address):
    backend = load("usa_network.py")
    result = backend.summarize([iface("eth0", address)],
        {"eth0": {"type": "ethernet", "state": "connected", "connection": "USA-Ethernet"}})
    assert not result["connected"]
    assert result["dashboard_url"] is None


def test_ethernet_dhcp_and_hotspot_coexist():
    backend = load("usa_network.py")
    result = backend.summarize([iface("eth0", "192.168.1.84"), iface("wlan0", "192.168.4.1")],
        {"eth0": {"type": "ethernet", "state": "connected", "connection": "USA-Ethernet"},
         "wlan0": {"type": "wifi", "state": "connected", "connection": "USA-Setup"}})
    assert result["dashboard_url"] == "http://192.168.1.84"
    assert result["hotspot_active"]


def test_hotspot_is_not_claimed_as_home_network():
    backend = load("usa_network.py")
    result = backend.summarize([iface("wlan0", "192.168.4.1")],
        {"wlan0": {"type": "wifi", "state": "connected", "connection": "USA-Setup"}})
    assert result["hotspot_active"] and not result["connected"]


def test_real_ipv6_address_is_bracketed():
    backend = load("usa_network.py")
    result = backend.summarize([iface("eth0", "fd12::84")],
        {"eth0": {"type": "ethernet", "state": "connected", "connection": "Owner LAN"}})
    assert result["dashboard_url"] == "http://[fd12::84]"


def test_console_screen_reports_failure_without_inventing_hotspot():
    console = load("usa-network-console.py")
    text = "\n".join(console.screen_lines({"connected": False, "hotspot_active": False}))
    assert "unavailable / retrying" in text
    assert "Password: dadtech1" not in text
    assert "127.0." not in text
    assert console.clean("SSID\x1b[2J\n") == "SSID?[2J?"


def test_console_credentials_travel_only_in_stdin(monkeypatch):
    console = load("usa-network-console.py")
    calls = []
    def run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, '{"scheduled":true}', "")
    monkeypatch.setattr(console.subprocess, "run", run)
    payload = {"ssid": "Example home", "password": "fixture-password"}
    assert console.request("console-wifi-connect", payload)["scheduled"]
    args, kwargs = calls[0]
    assert payload["password"] not in " ".join(args)
    assert json.loads(kwargs["input"]) == payload


def test_ui_keyboard_connect_flow_is_responsive_and_masks_password(monkeypatch):
    console = load("usa-network-console.py")
    requests, frames = [], []
    class Done:
        def __init__(self, result): self.value = result
        def done(self): return True
        def result(self): return self.value
    class Pool:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def submit(self, function, action, *args):
            requests.append((action, args))
            if action == "console-wifi-scan": return Done({"networks": [{"ssid": "Example home"}]})
            if action == "console-wifi-connect": return Done({"scheduled": True})
            return Done({"connected": False})
    class Finished(BaseException): pass
    keys = iter(["w", -1, "\n", *"abcdefgh", "\n", -1])
    class Screen:
        def keypad(self, value): pass
        def timeout(self, value): pass
        def get_wch(self):
            try: return next(keys)
            except StopIteration: raise Finished
    monkeypatch.setattr(console.concurrent.futures, "ThreadPoolExecutor", Pool)
    monkeypatch.setattr(console.curses, "curs_set", lambda _: None)
    monkeypatch.setattr(console, "draw", lambda screen, lines: frames.append("\n".join(lines)))
    with pytest.raises(Finished): console.run_ui(Screen())
    connect = [args for action, args in requests if action == "console-wifi-connect"]
    assert connect and connect[0][0] == {"ssid": "Example home", "password": "abcdefgh"}
    assert any("********" in text for text in frames)
    assert all("abcdefgh" not in text for text in frames)


@pytest.mark.parametrize("failure", ["activation-timeout", "ap-down-timeout", "bad-password"])
def test_home_failure_persists_fallback_before_ap_retry(tmp_path, monkeypatch, failure):
    helper = load("usa-system-helper.py")
    helper.STATE = tmp_path / "onboarding.json"
    helper.WIFI_RESULT = tmp_path / "wifi-result.json"
    helper.DATA_DIR = tmp_path
    helper.STATE.write_text('{"network_mode":"home","disclaimer_accepted":true}')
    helper.prepare_wifi = lambda: "wlan0"
    def run(*args, **kwargs):
        if (failure == "activation-timeout" and "up" in args) or (failure == "ap-down-timeout" and helper.HOTSPOT in args):
            raise subprocess.TimeoutExpired(args, 25)
        return subprocess.CompletedProcess(args, 10 if "up" in args else 0, "", "Activation failed")
    helper.run = run
    def restore(device):
        state = json.loads(helper.STATE.read_text())
        assert state["network_mode"] == "hotspot" and state["disclaimer_accepted"]
    helper.start_hotspot = restore
    helper.wifi_switch_worker()
    assert "restored" in json.loads(helper.WIFI_RESULT.read_text())["message"]


@pytest.mark.parametrize("model,blocked", [("Raspberry Pi 3 Model B Rev 1.2", True),
    ("Raspberry Pi 3 Model B Plus Rev 1.3", True), ("Raspberry Pi 4 Model B Rev 1.1", False),
    ("Raspberry Pi 5 Model B Rev 1.0", False)])
def test_board_detection_before_qwen_start(tmp_path, model, blocked):
    guard = load("local-brain-guard.py")
    path = tmp_path / "model";path.write_text(model + "\0")
    guard.MODEL_PATHS = (path,)
    guard.ACTIVATION = tmp_path / "absent"
    assert guard.status()["enabled"] is not blocked


def test_diagnostics_redacts_secrets_and_never_requests_them():
    collector = load("beta-diagnostics.py")
    assert "hunter22" not in collector.sanitize("psk=hunter22\nready")
    assert "ready" in collector.sanitize("password: hunter22\nready")
    assert all("--show-secrets" not in args for _, args in collector.COMMANDS)
    assert all("shadow" not in " ".join(args) for _, args in collector.COMMANDS)


def test_console_sudo_boundary_is_limited():
    rules = (ROOT / "deploy/usa-console.sudoers").read_text()
    assert "*" not in rules and "ALL=(ALL)" not in rules
    assert "console-network-status" in rules and "console-wifi-connect" in rules
    assert "ssh-enable" not in rules and "update-install" not in rules


def test_ethernet_profile_uses_dhcp_without_preempting_owner_profiles():
    config = (ROOT / "deploy/USA-Ethernet.nmconnection").read_text()
    assert "autoconnect-priority=-50" in config
    assert "[ipv4]\nmethod=auto" in config
    assert "addresses=" not in config


def test_lost_home_wifi_recovers_after_grace_without_resetting_owner_state(tmp_path):
    helper = load("usa-system-helper.py")
    helper.DATA_DIR = tmp_path
    helper.STATE = tmp_path / "onboarding.json"
    helper.RECOVERY_STATE = tmp_path / "network-recovery.json"
    helper.WIFI_RESULT = tmp_path / "wifi-result.json"
    helper.STATE.write_text('{"network_mode":"home","disclaimer_accepted":true}')
    helper.hotspot_active = lambda: False
    helper.network_identity = lambda: {"interfaces": []}
    helper.prepare_wifi = lambda: "wlan0"
    restored = []
    helper.start_hotspot = restored.append
    clock = [100]
    helper.time = SimpleNamespace(monotonic=lambda: clock[0])
    helper.maintain_setup_hotspot()
    assert not restored and json.loads(helper.STATE.read_text())["network_mode"] == "home"
    clock[0] = 161
    helper.maintain_setup_hotspot()
    assert restored == ["wlan0"]
    assert json.loads(helper.STATE.read_text())["disclaimer_accepted"]
    assert json.loads(helper.STATE.read_text())["network_mode"] == "hotspot"


def test_working_home_wifi_without_internet_is_not_disconnected(tmp_path):
    helper = load("usa-system-helper.py")
    helper.STATE = tmp_path / "onboarding.json"
    helper.RECOVERY_STATE = tmp_path / "recovery.json"
    helper.STATE.write_text('{"network_mode":"home"}')
    helper.hotspot_active = lambda: False
    helper.network_identity = lambda: {"interfaces": [{"type": "wifi", "connected": True, "hotspot": False}]}
    helper.start_hotspot = lambda device: pytest.fail("Healthy home Wi-Fi must be preserved")
    helper.maintain_setup_hotspot()
