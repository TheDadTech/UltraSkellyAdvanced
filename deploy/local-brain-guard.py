#!/usr/bin/env python3
"""Keep Qwen opt-in on Raspberry Pi 3 Model B, independently of the app."""
import json
from pathlib import Path
import sys


MODEL_PATHS = (
    Path("/proc/device-tree/model"),
    Path("/sys/firmware/devicetree/base/model"),
)
ACTIVATION = Path("/etc/skelly-ai/pi3b-qwen-enabled")


def status():
    model = ""
    for path in MODEL_PATHS:
        try:
            model = path.read_text().rstrip("\x00\n")
            break
        except OSError:
            continue
    # Pi 3B and 3B+ both have 1 GB RAM; neither preloads Qwen in this beta.
    pi3b = model.startswith(("Raspberry Pi 3 Model B Rev ", "Raspberry Pi 3 Model B Plus Rev "))
    return {"model": model, "pi3b": pi3b,
            "enabled": not pi3b or ACTIVATION.is_file()}


def main():
    state = status()
    if sys.argv[1:] == ["status"]:
        print(json.dumps(state))
        return 0
    if sys.argv[1:]:
        return 2
    if not state["enabled"]:
        print("Experimental Pi 3B/3B+: local Qwen is not loaded automatically.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
