#!/usr/bin/env python3
"""Bounded, read-only beta probes with a sanitized report on bootfs."""
import json
import os
from pathlib import Path
import re
import subprocess
import time

SECRET = re.compile(r"(?i)(password|passphrase|psk|api[_ -]?key|token|secret)\s*[:=]")
COMMANDS = [
    ("interfaces", ["ip", "-brief", "address"]),
    ("routes", ["ip", "-4", "route"]),
    ("wifi_devices", ["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"]),
    ("active_connections", ["nmcli", "-t", "-f", "NAME,TYPE,DEVICE", "connection", "show", "--active"]),
    ("radio_blocks", ["rfkill", "list"]),
    ("services", ["systemctl", "show", "usa-network.service", "usa-setup-hotspot.service",
                  "skelly-ai.service", "skelly-brain.service", "NetworkManager.service",
                  "--property=Id,ActiveState,SubState,Result"]),
    ("network_log", ["journalctl", "-b", "--no-pager", "-n", "120", "-u", "usa-network.service",
                     "-u", "usa-setup-hotspot.service", "-u", "NetworkManager.service"]),
    ("kernel_log", ["journalctl", "-k", "-b", "--no-pager", "-n", "250"]),
]


def sanitize(text):
    return "\n".join("[credential-bearing line redacted]" if SECRET.search(line) else line
                     for line in text.splitlines())[-24000:]


def collect():
    result = {"image": "UltraSkellyAdvanced 0.30.1-beta1 (experimental Pi 3B)",
              "uptime_seconds": round(time.monotonic()), "captured_unix": int(time.time())}
    for key, path in [("hardware", "/proc/device-tree/model"), ("boot_id", "/proc/sys/kernel/random/boot_id")]:
        try:
            result[key] = Path(path).read_text().strip("\x00\n")
        except OSError:
            result[key] = "unavailable"
    try:
        result["memory"] = "\n".join(x for x in Path("/proc/meminfo").read_text().splitlines()
                                     if x.startswith(("MemTotal:", "MemAvailable:", "SwapTotal:", "SwapFree:")))
    except OSError:
        result["memory"] = "unavailable"
    for key, command in COMMANDS:
        try:
            p = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False)
            output = (p.stdout + p.stderr)[-48000:]
            if key == "kernel_log":
                output = "\n".join(x for x in output.splitlines()
                                   if re.search(r"brcm|wlan|wifi|sdio|oom|memory|voltage|rfkill|mmc", x, re.I))
            result[key] = {"exit": p.returncode, "output": sanitize(output)}
        except (OSError, subprocess.SubprocessError) as exc:
            result[key] = {"error": type(exc).__name__}
    return result


def atomic_write(path, text, mode=0o600):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    try:
        temporary.chmod(mode)
    except PermissionError:
        pass  # FAT mount permissions are authoritative.
    temporary.replace(path)


def main():
    result = collect()
    text = json.dumps(result, indent=2) + "\n"
    directory = Path("/var/log/usa-beta")
    directory.mkdir(mode=0o700, exist_ok=True)
    atomic_write(directory / f"snapshot-{int(time.time())}.json", text)
    for old in sorted(directory.glob("snapshot-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[10:]:
        old.unlink()
    # Windows/macOS can read this without Linux account access or SSH.
    boot = Path("/boot/firmware")
    if os.path.ismount(boot):
        atomic_write(boot / "USA-BETA-DIAGNOSTICS.txt",
                     "Experimental beta diagnostics. Network names/addresses may identify your network.\n"
                     "Review before sharing. No passwords or credential files are collected.\n\n" + text,
                     mode=0o644)
    print("Beta diagnostic snapshot saved; no network settings changed")


if __name__ == "__main__":
    main()
