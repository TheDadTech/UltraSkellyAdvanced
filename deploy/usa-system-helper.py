#!/usr/bin/env python3
"""Root-only allowlisted system actions for a USA Raspberry Pi image."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time


HOTSPOT = "USA-Setup"
HOME = "USA-Home"
HOTSPOT_SSID = "UltraSkellyAdvanced-Setup"
SUPPORT_USER = "dadtech"
DATA_DIR = pathlib.Path("/var/lib/skelly-ai")
ENV_FILE = pathlib.Path("/etc/skelly-ai/skelly-ai.env")
STATE = DATA_DIR / "onboarding.json"
WIFI_CACHE = DATA_DIR / "wifi-scan.json"
WIFI_RESULT = DATA_DIR / "wifi-result.json"
SELF = pathlib.Path(__file__).resolve()


def run(
    *args: str,
    input_text: str | None = None,
    check: bool = True,
    timeout: float = 45,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, input=input_text, text=True, capture_output=True,
        check=check, timeout=timeout,
    )


def error_text(result: subprocess.CompletedProcess[str]) -> str:
    return (result.stderr or result.stdout or "The system request failed").strip()


def write_json(path: pathlib.Path, payload: object) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    os.chmod(temporary, 0o600)
    try:
        owner = DATA_DIR.stat()
        os.chown(temporary, owner.st_uid, owner.st_gid)
    except OSError:
        pass
    temporary.replace(path)
    os.chmod(path, 0o600)


def ensure_hotspot(device: str = "wlan0") -> None:
    run("nmcli", "con", "delete", HOTSPOT, check=False)
    run(
        "nmcli", "con", "add", "type", "wifi", "ifname", device,
        "con-name", HOTSPOT, "ssid", HOTSPOT_SSID,
    )
    run(
        "nmcli", "con", "modify", HOTSPOT,
        "802-11-wireless.mode", "ap", "802-11-wireless.band", "bg",
        "802-11-wireless.powersave", "2", "ipv4.method", "shared",
        "ipv4.addresses", "192.168.4.1/24", "ipv6.method", "disabled",
        "wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", "dadtech1",
        "connection.autoconnect", "yes", "connection.autoconnect-priority", "-20",
    )


def prepare_wifi() -> str:
    run("rfkill", "unblock", "wifi", check=False)
    run("nmcli", "radio", "wifi", "on", check=False)
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        status = run("nmcli", "-t", "-f", "DEVICE,TYPE", "device", "status", check=False)
        for line in status.stdout.splitlines():
            device, _, device_type = line.partition(":")
            if device and device_type == "wifi":
                run("nmcli", "device", "set", device, "managed", "yes", check=False)
                return device
        time.sleep(1)
    raise SystemExit("No onboard WiFi interface appeared within 45 seconds")


def prepare_bluetooth() -> None:
    run("rfkill", "unblock", "bluetooth", check=False)
    run("systemctl", "start", "hciuart.service", check=False)
    run("systemctl", "start", "bluetooth.service", check=False)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if pathlib.Path("/sys/class/bluetooth/hci0").exists():
            powered = run("bluetoothctl", "power", "on", check=False, timeout=10)
            if powered.returncode == 0:
                print("ready")
                return
        time.sleep(1)
    details = run("rfkill", "list", "bluetooth", check=False).stdout.strip()
    raise SystemExit(
        "The onboard Bluetooth adapter did not become ready"
        + (f": {details}" if details else "")
    )


def parse_wifi_scan(output: str) -> list[dict[str, object]]:
    networks: dict[str, int] = {}
    for raw in output.splitlines():
        if ":" not in raw:
            continue
        ssid, signal = raw.rsplit(":", 1)
        ssid = ssid.replace(r"\:", ":").replace(r"\\", "\\").strip()
        if not ssid or ssid == HOTSPOT_SSID:
            continue
        try:
            strength = int(signal)
        except ValueError:
            strength = 0
        networks[ssid] = max(networks.get(ssid, 0), strength)
    return [
        {"ssid": ssid, "signal": signal}
        for ssid, signal in sorted(networks.items(), key=lambda item: item[1], reverse=True)
    ]


def scan_and_cache(device: str, attempts: int = 5) -> list[dict[str, object]]:
    """Scan with retries while the single WiFi radio settles after boot/AP use."""
    networks: list[dict[str, object]] = []
    for _ in range(attempts):
        run("nmcli", "device", "wifi", "rescan", "ifname", device, check=False)
        time.sleep(2)
        result = run(
            "nmcli", "-t", "--escape", "yes", "-f", "SSID,SIGNAL",
            "device", "wifi", "list", "ifname", device, "--rescan", "no",
            check=False,
        )
        networks = parse_wifi_scan(result.stdout)
        if networks:
            break
    write_json(WIFI_CACHE, networks)
    return networks


def cached_networks() -> list[dict[str, object]]:
    try:
        payload = json.loads(WIFI_CACHE.read_text("utf-8"))
        return payload if isinstance(payload, list) else []
    except (OSError, ValueError):
        return []


def hotspot_active() -> bool:
    result = run("nmcli", "-t", "-f", "NAME", "con", "show", "--active", check=False)
    return HOTSPOT in result.stdout.splitlines()


def start_hotspot(device: str) -> None:
    ensure_hotspot(device)
    last_error = "unknown NetworkManager error"
    for _ in range(5):
        result = run("nmcli", "con", "up", HOTSPOT, check=False)
        if result.returncode == 0:
            return
        last_error = error_text(result)
        time.sleep(2)
    raise SystemExit(f"USA hotspot could not start: {last_error}")


def network_boot() -> None:
    device = prepare_wifi()
    try:
        prepare_bluetooth()
    except SystemExit as exc:
        # A Bluetooth fault must not prevent WiFi onboarding and diagnostics.
        print(f"Bluetooth startup warning: {exc}", file=sys.stderr)
    mode = "hotspot"
    if STATE.exists():
        try:
            mode = json.loads(STATE.read_text("utf-8")).get("network_mode", "hotspot")
        except (OSError, ValueError):
            pass
    if mode == "home" and run("nmcli", "con", "up", HOME, check=False).returncode == 0:
        scan_and_cache(device)
        return
    # Scan before starting the single-radio access point. The Pi radio cannot
    # reliably rescan while it is serving the setup hotspot.
    scan_and_cache(device)
    start_hotspot(device)


def wifi_list() -> None:
    device = prepare_wifi()
    networks = cached_networks() if hotspot_active() else scan_and_cache(device)
    for network in networks:
        print(json.dumps(network, separators=(",", ":")))


def schedule_helper(unit: str, action: str, delay: str = "3s") -> None:
    run(
        "systemd-run", f"--unit={unit}", f"--on-active={delay}",
        str(SELF), action,
    )


def wifi_refresh() -> None:
    schedule_helper(f"usa-wifi-rescan-{os.getpid()}", "wifi-rescan-worker", "2s")


def wifi_rescan_worker() -> None:
    device = prepare_wifi()
    was_hotspot = hotspot_active()
    if was_hotspot:
        run("nmcli", "con", "down", HOTSPOT, check=False)
    try:
        networks = scan_and_cache(device)
        write_json(WIFI_RESULT, {"ok": True, "message": f"Found {len(networks)} networks"})
    finally:
        if was_hotspot:
            start_hotspot(device)


def wifi_connect(ssid: str, password: str) -> None:
    if not ssid or len(ssid) > 64 or len(password) < 8:
        raise SystemExit("Enter a WiFi network name and a password of at least 8 characters")
    if any(character in ssid + password for character in "\r\n\0"):
        raise SystemExit("WiFi details contain unsupported characters")
    run("nmcli", "con", "delete", HOME, check=False)
    run("nmcli", "con", "add", "type", "wifi", "ifname", "wlan0", "con-name", HOME, "ssid", ssid)
    run(
        "nmcli", "con", "modify", HOME,
        "wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", password,
        "connection.autoconnect", "yes", "connection.autoconnect-priority", "20",
    )
    write_json(WIFI_RESULT, {"ok": None, "message": "Home WiFi connection scheduled"})
    schedule_helper(f"usa-wifi-switch-{os.getpid()}", "wifi-switch-worker")


def wifi_switch_worker() -> None:
    device = prepare_wifi()
    run("nmcli", "con", "down", HOTSPOT, check=False)
    result = run("nmcli", "con", "up", HOME, check=False, timeout=60)
    if result.returncode == 0:
        write_json(WIFI_RESULT, {"ok": True, "message": "Connected to home WiFi"})
        return
    start_hotspot(device)
    try:
        state = json.loads(STATE.read_text("utf-8"))
    except (OSError, ValueError):
        state = {}
    state.update({"network_choice_made": False, "network_mode": "hotspot"})
    write_json(STATE, state)
    write_json(
        WIFI_RESULT,
        {"ok": False, "message": f"Home WiFi failed; setup hotspot restored. {error_text(result)}"},
    )


def wifi_status() -> None:
    payload: dict[str, object] = {
        "mode": "hotspot" if hotspot_active() else "home",
        "hotspot_ssid": HOTSPOT_SSID,
    }
    try:
        payload["last_result"] = json.loads(WIFI_RESULT.read_text("utf-8"))
    except (OSError, ValueError):
        payload["last_result"] = None
    print(json.dumps(payload, separators=(",", ":")))


def wifi_hotspot() -> None:
    schedule_helper(f"usa-wifi-hotspot-{os.getpid()}", "wifi-hotspot-worker", "3s")


def wifi_hotspot_worker() -> None:
    device = prepare_wifi()
    run("nmcli", "con", "down", HOME, check=False)
    start_hotspot(device)
    try:
        state = json.loads(STATE.read_text("utf-8"))
    except (OSError, ValueError):
        state = {}
    state.update({"network_choice_made": True, "network_mode": "hotspot"})
    write_json(STATE, state)
    write_json(WIFI_RESULT, {"ok": True, "message": "USA setup hotspot active"})


def ensure_support_user() -> None:
    if run("id", SUPPORT_USER, check=False).returncode != 0:
        run("useradd", "--create-home", "--shell", "/bin/bash", SUPPORT_USER)
    run("usermod", "--shell", "/bin/bash", SUPPORT_USER)


def ssh_enable(mode: str, password: str) -> None:
    if len(password) < 10 or password.lower() in {"dadtech", "dadtech1"}:
        raise SystemExit("Use a unique support password of at least 10 characters")
    if any(character in password for character in ":\r\n\0"):
        raise SystemExit("The support password contains unsupported characters")
    ensure_support_user()
    run("chpasswd", input_text=f"{SUPPORT_USER}:{password}\n")
    run("usermod", "--unlock", SUPPORT_USER, check=False)
    run("systemctl", "enable", "--now", "ssh.service")
    run("systemctl", "stop", "usa-ssh-timeout.timer", check=False)
    run("systemctl", "reset-failed", "usa-ssh-timeout.timer", check=False)
    if mode != "persistent":
        schedule_helper("usa-ssh-timeout", "ssh-disable", "30m")


def ssh_disable() -> None:
    run("systemctl", "disable", "--now", "ssh.service", check=False)
    if run("id", SUPPORT_USER, check=False).returncode == 0:
        run("usermod", "--lock", SUPPORT_USER, check=False)


def first_boot_reset() -> None:
    schedule_helper(f"usa-first-boot-reset-{os.getpid()}", "first-boot-reset-worker", "3s")


def first_boot_reset_worker() -> None:
    run("systemctl", "stop", "skelly-ai.service", check=False)
    if ENV_FILE.exists():
        lines = ENV_FILE.read_text("utf-8").splitlines()
        replacements = {
            "SKELLY_ONBOARDING_REQUIRED": "true",
            "SKELLY_SIMULATION": "false",
        }
        output: list[str] = []
        found: set[str] = set()
        for line in lines:
            key, separator, _ = line.partition("=")
            if separator and key in replacements:
                output.append(f"{key}={replacements[key]}")
                found.add(key)
            else:
                output.append(line)
        output.extend(f"{key}={value}" for key, value in replacements.items() if key not in found)
        ENV_FILE.write_text("\n".join(output) + "\n", encoding="utf-8")
    run("hostnamectl", "set-hostname", "usa-controller", check=False)
    for path in DATA_DIR.glob("*.json"):
        path.unlink(missing_ok=True)
    for path in DATA_DIR.glob(".*.tmp"):
        path.unlink(missing_ok=True)
    run("nmcli", "con", "delete", HOME, check=False)
    paired = run("bluetoothctl", "devices", "Paired", check=False)
    for line in paired.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[0] == "Device":
            run("bluetoothctl", "remove", fields[1], check=False)
    ssh_disable()
    device = prepare_wifi()
    run("nmcli", "con", "down", HOTSPOT, check=False)
    scan_and_cache(device)
    start_hotspot(device)
    run("systemctl", "reboot")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Missing action")
    action = sys.argv[1]
    if action == "network-boot": network_boot()
    elif action == "bluetooth-prepare": prepare_bluetooth()
    elif action == "wifi-list": wifi_list()
    elif action == "wifi-refresh": wifi_refresh()
    elif action == "wifi-rescan-worker": wifi_rescan_worker()
    elif action == "wifi-connect" and len(sys.argv) == 3: wifi_connect(sys.argv[2], sys.stdin.readline().rstrip("\n"))
    elif action == "wifi-switch-worker": wifi_switch_worker()
    elif action == "wifi-status": wifi_status()
    elif action == "wifi-hotspot": wifi_hotspot()
    elif action == "wifi-hotspot-worker": wifi_hotspot_worker()
    elif action == "ssh-status":
        active = run("systemctl", "is-active", "--quiet", "ssh.service", check=False).returncode == 0
        print("enabled" if active else "disabled")
    elif action == "ssh-enable" and len(sys.argv) == 3 and sys.argv[2] in {"temporary", "persistent"}:
        ssh_enable(sys.argv[2], sys.stdin.readline().rstrip("\n"))
    elif action == "ssh-disable": ssh_disable()
    elif action == "first-boot-reset": first_boot_reset()
    elif action == "first-boot-reset-worker": first_boot_reset_worker()
    elif action in {"service-restart", "reboot", "shutdown"}:
        command = {
            "service-restart": ["systemctl", "restart", "skelly-ai.service"],
            "reboot": ["systemctl", "reboot"],
            "shutdown": ["systemctl", "poweroff"],
        }[action]
        run("systemd-run", f"--unit=usa-dashboard-{action}-{os.getpid()}", "--on-active=2s", *command)
    else:
        raise SystemExit("Unsupported action")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        raise SystemExit(error_text(exc)) from None
    except subprocess.TimeoutExpired as exc:
        raise SystemExit(f"System command timed out: {' '.join(exc.cmd)}") from None
