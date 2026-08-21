import asyncio
import glob
import platform
import shutil
import sys
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Probe:
    name: str
    command: tuple[str, ...]


PROBES = (
    Probe("bluetooth", ("bluetoothctl", "show")),
    Probe("audio", ("wpctl", "status")),
    Probe("microphones", ("arecord", "-l")),
    Probe("camera", ("v4l2-ctl", "--list-devices")),
    Probe("network", ("ip", "-brief", "address")),
)


async def _run_probe(probe: Probe) -> dict[str, object]:
    executable = shutil.which(probe.command[0])
    if executable is None:
        return {
            "available": False,
            "ok": False,
            "detail": f"{probe.command[0]} is not installed",
        }

    try:
        process = await asyncio.create_subprocess_exec(
            executable,
            *probe.command[1:],
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=8)
    except TimeoutError:
        return {"available": True, "ok": False, "detail": "Probe timed out"}
    except OSError as exc:
        return {"available": True, "ok": False, "detail": str(exc)}

    output = (stdout or stderr).decode(errors="replace").strip()
    return {
        "available": True,
        "ok": process.returncode == 0,
        "detail": output[-8000:],
    }


async def collect_diagnostics() -> dict[str, object]:
    results = await asyncio.gather(*(_run_probe(probe) for probe in PROBES))
    return {
        "system": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
            "video_devices": sorted(glob.glob("/dev/video*")),
            "sound_devices": sorted(glob.glob("/dev/snd/*")),
        },
        "probes": {probe.name: result for probe, result in zip(PROBES, results)},
    }

