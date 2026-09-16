import asyncio
import re
import shutil
from pathlib import Path
from dataclasses import asdict, dataclass
from datetime import UTC, datetime


class AudioOutputUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ExternalBluetoothSnapshot:
    available: bool
    connected: bool
    paired: bool
    trusted: bool
    sink_id: str | None
    address: str | None
    device_name: str | None
    last_error: str | None
    changed_at: str
    sink_name: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ExternalBluetoothAudio:
    """Pair, reconnect, and route one user-selected external Bluetooth speaker."""

    _DEVICE_PATTERN = re.compile(
        r"^Device\s+([0-9A-F]{2}(?::[0-9A-F]{2}){5})\s+(.+)$",
        re.IGNORECASE,
    )

    def __init__(self, *, address: str | None = None, timeout_seconds: float = 20.0, system_helper: Path | None = None, pipewire_session: str = "dadtech") -> None:
        self._address = address.upper() if address else None
        self._timeout_seconds = timeout_seconds
        self._system_helper = system_helper
        self._pipewire_session = pipewire_session
        self._lock = asyncio.Lock()
        self._snapshot = ExternalBluetoothSnapshot(
            available=shutil.which("bluetoothctl") is not None,
            connected=False,
            paired=False,
            trusted=False,
            sink_id=None,
            sink_name=None,
            address=self._address,
            device_name=None,
            last_error=None,
            changed_at=self._now(),
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def snapshot(self) -> ExternalBluetoothSnapshot:
        return self._snapshot

    def set_saved_target(self, address: str | None, name: str | None = None) -> None:
        self._address = address.upper() if address else None
        self._update(address=self._address, device_name=name, last_error=None)

    def clear_saved_target(self) -> None:
        self._address = None
        self._update(
            connected=False,
            paired=False,
            trusted=False,
            sink_id=None,
            sink_name=None,
            address=None,
            device_name=None,
            last_error=None,
        )

    async def scan(self) -> list[dict[str, object]]:
        async with self._lock:
            self._require_tools()
            # Keep the scan bounded; discovered devices remain in BlueZ's cache.
            await self._run("--timeout", "8", "scan", "on", timeout=12.0)
            paired = await self._run("devices", "Paired")
            paired_addresses = {
                match.group(1).upper()
                for line in paired.output.splitlines()
                if (match := self._DEVICE_PATTERN.match(line.strip()))
            }
            devices = await self._run("devices")
            result: list[dict[str, object]] = []
            seen: set[str] = set()
            for raw_line in devices.output.splitlines():
                match = self._DEVICE_PATTERN.match(raw_line.strip())
                if not match:
                    continue
                address = match.group(1).upper()
                if address in seen:
                    continue
                seen.add(address)
                name = match.group(2).strip()
                result.append(
                    {
                        "address": address,
                        "name": name,
                        "paired": address in paired_addresses,
                    }
                )
            result.sort(key=lambda item: (not bool(item["paired"]), str(item["name"]).casefold()))
            return result

    async def paired_devices(self) -> list[dict[str, object]]:
        async with self._lock:
            self._require_tools()
            paired = await self._run("devices", "Paired")
            result: list[dict[str, object]] = []
            seen: set[str] = set()
            for raw_line in paired.output.splitlines():
                match = self._DEVICE_PATTERN.match(raw_line.strip())
                if not match:
                    continue
                address = match.group(1).upper()
                if address in seen:
                    continue
                seen.add(address)
                result.append({
                    "address": address,
                    "name": match.group(2).strip(),
                    "paired": True,
                })
            result.sort(key=lambda item: str(item["name"]).casefold())
            return result

    async def refresh(self) -> ExternalBluetoothSnapshot:
        async with self._lock:
            if not self._address:
                return self._update(
                    connected=False,
                    paired=False,
                    trusted=False,
                    sink_id=None,
                    sink_name=None,
                    last_error=None,
                )
            try:
                info = await self._read_info(self._address)
                sink = await self._find_pipewire_sink(info.device_name) if info.connected else None
                return self._update(
                    sink_id=sink[0] if sink else None,
                    sink_name=sink[1] if sink else None,
                    last_error=None,
                )
            except AudioOutputUnavailable as exc:
                return self._update(
                    connected=False, sink_id=None, sink_name=None, last_error=str(exc)
                )

    async def prepare(self, address: str) -> ExternalBluetoothSnapshot:
        async with self._lock:
            self._require_tools()
            await self._ensure_headless_pipewire()
            self._address = address.upper()
            info = await self._read_info(self._address)
            if not info.paired:
                paired = await self._run(
                    "--agent", "NoInputNoOutput", "pair", self._address,
                    timeout=max(self._timeout_seconds, 25.0),
                )
                if paired.returncode != 0 and "alreadyexists" not in paired.output.casefold():
                    raise AudioOutputUnavailable(self._useful_output(paired.output) or "External Bluetooth pairing failed")
            trusted = await self._run("trust", self._address)
            if trusted.returncode != 0:
                raise AudioOutputUnavailable(self._useful_output(trusted.output) or "External Bluetooth speaker could not be trusted")
            return await self._connect_locked(route=True)

    async def connect(self, *, route: bool = True) -> ExternalBluetoothSnapshot:
        async with self._lock:
            return await self._connect_locked(route=route)

    async def _connect_locked(self, *, route: bool) -> ExternalBluetoothSnapshot:
        self._require_tools()
        await self._ensure_headless_pipewire()
        if not self._address:
            raise AudioOutputUnavailable("Choose an External Bluetooth speaker in Setup first")

        info = await self._read_info(self._address)
        existing_sink = await self._find_pipewire_sink(info.device_name) if info.connected else None
        ownership_reserved = False
        try:
            # BlueZ can report the speaker connected while the *other* user
            # WirePlumber session owns its A2DP transport.  That produces the
            # confusing state where the speaker chimes but USA has no usable
            # external sink.  Reserve the requested PipeWire session and force
            # one controlled reconnect whenever the target session has no sink.
            if existing_sink is None:
                # First prove the external speaker is actually reachable WITHOUT
                # pausing dadtech. Failed background reconnect attempts must not
                # bounce the Skelly A2DP path and make the prop chime repeatedly.
                if not info.connected:
                    connected = await self._run("connect", self._address)
                    info = await self._read_info(self._address)
                    if connected.returncode != 0 or not info.connected:
                        raise AudioOutputUnavailable(self._useful_output(connected.output) or "External Bluetooth speaker did not accept the connection")
                    await asyncio.sleep(0.75)
                    existing_sink = await self._find_pipewire_sink(info.device_name)

                # If BlueZ connected but this session still has no sink, the other
                # WirePlumber session claimed the transport. Only now reserve the
                # external session and perform one controlled ownership transfer.
                if existing_sink is None:
                    await self._pause_competing_session()
                    ownership_reserved = True
                    info = await self._read_info(self._address)
                    if info.connected:
                        await self._run("disconnect", self._address)
                        await asyncio.sleep(0.75)
                    connected = await self._run("connect", self._address)
                    info = await self._read_info(self._address)
                    if connected.returncode != 0 or not info.connected:
                        raise AudioOutputUnavailable(self._useful_output(connected.output) or "External Bluetooth speaker did not accept the connection")

            sink_id = None
            sink_name = None
            for _ in range(120):
                sink = await self._find_pipewire_sink(info.device_name)
                if sink:
                    sink_id, sink_name = sink
                    break
                await asyncio.sleep(0.5)
            if sink_id is None:
                raise AudioOutputUnavailable("External Bluetooth connected, but its PipeWire audio output did not appear in the external-audio session within 60 seconds")
            if route:
                routed = await self._run_program("wpctl", "set-default", sink_id)
                if routed.returncode != 0:
                    raise AudioOutputUnavailable(self._useful_output(routed.output) or "Unable to select the external Bluetooth speaker as audio output")
            return self._update(sink_id=sink_id, sink_name=sink_name, last_error=None)
        finally:
            if ownership_reserved:
                await self._resume_competing_session()

    async def disconnect(self) -> ExternalBluetoothSnapshot:
        async with self._lock:
            if not self._address:
                return self._snapshot
            result = await self._run("disconnect", self._address)
            info = await self._read_info(self._address)
            if result.returncode != 0 or info.connected:
                raise AudioOutputUnavailable(self._useful_output(result.output) or "External Bluetooth speaker did not disconnect")
            return self._update(connected=False, sink_id=None, last_error=None)

    async def forget(self) -> ExternalBluetoothSnapshot:
        async with self._lock:
            if not self._address:
                self.clear_saved_target()
                return self._snapshot
            await self._run("disconnect", self._address)
            removed = await self._run("remove", self._address)
            if removed.returncode != 0 and "not available" not in removed.output.casefold():
                raise AudioOutputUnavailable(self._useful_output(removed.output) or "External Bluetooth pairing could not be removed")
            self.clear_saved_target()
            return self._snapshot

    async def _read_info(self, address: str) -> ExternalBluetoothSnapshot:
        result = await self._run("info", address)
        if result.returncode != 0 or "Device " not in result.output:
            raise AudioOutputUnavailable(self._useful_output(result.output) or "External Bluetooth device information is unavailable")
        values: dict[str, str] = {}
        for raw_line in result.output.splitlines():
            if ":" not in raw_line:
                continue
            key, value = raw_line.strip().split(":", 1)
            values[key] = value.strip()
        return self._update(
            available=True,
            connected=values.get("Connected", "no").casefold() == "yes",
            paired=values.get("Paired", "no").casefold() == "yes",
            trusted=values.get("Trusted", "no").casefold() == "yes",
            address=address,
            device_name=values.get("Name") or values.get("Alias"),
            last_error=None,
        )

    async def _find_pipewire_sink(self, device_name: str | None) -> tuple[str, str | None] | None:
        if not device_name or shutil.which("wpctl") is None:
            return None
        result = await self._run_program("wpctl", "status")
        target = device_name.casefold()
        in_sinks = False
        for line in result.output.splitlines():
            stripped = line.strip()
            if stripped.endswith("Sinks:"):
                in_sinks = True
                continue
            if in_sinks and stripped.endswith(("Sources:", "Filters:", "Streams:")):
                break
            if not in_sinks or target not in stripped.casefold():
                continue
            match = re.search(r"(?:\*\s*)?(\d+)\.\s+", stripped)
            if match:
                sink_id = match.group(1)
                inspect = await self._run_program("wpctl", "inspect", sink_id)
                sink_name = None
                for inspect_line in inspect.output.splitlines():
                    node_match = re.search(r'node\.name\s*=\s*"([^"]+)"', inspect_line)
                    if node_match:
                        sink_name = node_match.group(1)
                        break
                return sink_id, sink_name
        return None


    async def _pause_competing_session(self) -> None:
        if self._system_helper is None or not self._system_helper.exists():
            return
        result = await self._run_program(
            "sudo", str(self._system_helper),
            "audio-session-pause-competitor", "--session", self._pipewire_session,
        )
        if result.returncode != 0:
            raise AudioOutputUnavailable(
                self._useful_output(result.output)
                or "Unable to reserve the external Bluetooth audio session"
            )

    async def _resume_competing_session(self) -> None:
        if self._system_helper is None or not self._system_helper.exists():
            return
        result = await self._run_program(
            "sudo", str(self._system_helper),
            "audio-session-resume-competitor", "--session", self._pipewire_session,
        )
        if result.returncode != 0:
            # The external sink is already established.  Do not discard it only
            # because the other session had trouble restarting; surface that
            # through later Skelly refresh/recovery instead.
            return

    async def _ensure_headless_pipewire(self) -> None:
        # Production images keep Bluetooth audio in the persistent dadtech
        # PipeWire session. The root-owned helper prepares that session,
        # enables linger, installs the headless WirePlumber policy, and starts
        # PipeWire/WirePlumber before USA tries to discover a sink.
        if self._system_helper is not None and self._system_helper.exists():
            result = await self._run_program(
                "sudo", str(self._system_helper), "audio-session-prepare", "--session", self._pipewire_session, timeout=20.0,
            )
            if result.returncode != 0:
                raise AudioOutputUnavailable(
                    self._useful_output(result.output)
                    or "The headless audio session could not be prepared"
                )
            return

        # Development fallback when the privileged helper is not installed.
        config_dir = Path.home() / ".config" / "wireplumber" / "wireplumber.conf.d"
        config_path = config_dir / "80-usa-bluetooth-headless.conf"
        desired = (
            "wireplumber.profiles = {\n"
            "  main = {\n"
            "    monitor.bluez.seat-monitoring = disabled\n"
            "  }\n"
            "}\n"
        )
        try:
            if config_path.exists() and config_path.read_text(encoding="utf-8") == desired:
                return
            config_dir.mkdir(parents=True, exist_ok=True)
            config_path.write_text(desired, encoding="utf-8")
        except OSError as exc:
            raise AudioOutputUnavailable(f"Unable to configure headless Bluetooth audio: {exc}") from exc

    def _require_tools(self) -> None:
        if shutil.which("bluetoothctl") is None:
            raise AudioOutputUnavailable("bluetoothctl is not installed")
        if shutil.which("wpctl") is None and not (self._system_helper and self._system_helper.exists()):
            raise AudioOutputUnavailable("wpctl is not installed")

    async def _run(self, *args: str, timeout: float | None = None) -> "_CommandResult":
        return await self._run_program("bluetoothctl", *args, timeout=timeout)

    async def _run_program(self, executable: str, *args: str, timeout: float | None = None) -> "_CommandResult":
        resolved = shutil.which(executable)
        command: list[str]
        if executable == "wpctl" and self._system_helper is not None and self._system_helper.exists():
            command = ["sudo", str(self._system_helper), "audio-wpctl", "--session", self._pipewire_session, *args]
        else:
            if resolved is None:
                raise AudioOutputUnavailable(f"{executable} is not installed")
            command = [resolved, *args]
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout or (3.0 if executable == "wpctl" else self._timeout_seconds),
            )
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise AudioOutputUnavailable(f"{executable} command timed out") from exc
        except OSError as exc:
            raise AudioOutputUnavailable(f"{executable} command failed: {exc}") from exc
        return _CommandResult(process.returncode or 0, stdout.decode(errors="replace").strip())

    @staticmethod
    def _useful_output(output: str) -> str:
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        return lines[-1][-300:] if lines else ""

    def _update(self, **changes: object) -> ExternalBluetoothSnapshot:
        current = self._snapshot.to_dict()
        current.update(changes)
        current["changed_at"] = self._now()
        self._snapshot = ExternalBluetoothSnapshot(**current)
        return self._snapshot


@dataclass(frozen=True, slots=True)
class _CommandResult:
    returncode: int
    output: str

class SimulatedExternalBluetoothAudio:
    def __init__(self) -> None:
        self._snapshot = ExternalBluetoothSnapshot(
            available=True,
            connected=False,
            paired=False,
            trusted=False,
            sink_id=None,
            sink_name=None,
            address=None,
            device_name=None,
            last_error=None,
            changed_at=datetime.now(UTC).isoformat(),
        )

    def snapshot(self) -> ExternalBluetoothSnapshot:
        return self._snapshot

    def _set(self, **changes: object) -> ExternalBluetoothSnapshot:
        current = self._snapshot.to_dict()
        current.update(changes)
        current["changed_at"] = datetime.now(UTC).isoformat()
        self._snapshot = ExternalBluetoothSnapshot(**current)
        return self._snapshot

    def set_saved_target(self, address: str | None, name: str | None = None) -> None:
        self._set(address=address, device_name=name)

    def clear_saved_target(self) -> None:
        self._set(address=None, device_name=None, connected=False, paired=False, trusted=False, sink_id=None)

    async def scan(self) -> list[dict[str, object]]:
        return [
            {"address": "11:22:33:44:55:66", "name": "External Speaker (simulated)", "paired": False}
        ]

    async def paired_devices(self) -> list[dict[str, object]]:
        if self._snapshot.address:
            return [{
                "address": self._snapshot.address,
                "name": self._snapshot.device_name or "External Speaker (simulated)",
                "paired": True,
            }]
        return [{"address": "11:22:33:44:55:66", "name": "External Speaker (simulated)", "paired": True}]

    async def refresh(self) -> ExternalBluetoothSnapshot:
        return self._snapshot

    async def prepare(self, address: str) -> ExternalBluetoothSnapshot:
        return self._set(
            address=address.upper(), device_name="External Speaker (simulated)",
            connected=True, paired=True, trusted=True, sink_id="external-simulated",
            last_error=None,
        )

    async def connect(self, *, route: bool = True) -> ExternalBluetoothSnapshot:
        del route
        if not self._snapshot.address:
            raise AudioOutputUnavailable("Choose an External Bluetooth speaker in Setup first")
        return self._set(connected=True, paired=True, trusted=True, sink_id="external-simulated", last_error=None)

    async def disconnect(self) -> ExternalBluetoothSnapshot:
        return self._set(connected=False, sink_id=None)

    async def forget(self) -> ExternalBluetoothSnapshot:
        self.clear_saved_target()
        return self._snapshot
