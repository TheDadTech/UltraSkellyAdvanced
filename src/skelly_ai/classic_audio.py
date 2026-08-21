import asyncio
import re
import shutil
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Protocol


class ClassicAudioUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ClassicAudioSnapshot:
    available: bool
    connected: bool
    paired: bool
    trusted: bool
    sink_ready: bool
    sink_id: str | None
    address: str | None
    device_name: str | None
    last_error: str | None
    changed_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ClassicAudio(Protocol):
    async def refresh(self) -> ClassicAudioSnapshot: ...
    async def prepare(self, pin: str) -> ClassicAudioSnapshot: ...
    async def connect(self) -> ClassicAudioSnapshot: ...
    async def disconnect(self) -> ClassicAudioSnapshot: ...
    async def forget(self) -> ClassicAudioSnapshot: ...
    def clear_saved_target(self) -> None: ...
    def set_saved_target(self, address: str | None) -> None: ...
    def snapshot(self) -> ClassicAudioSnapshot: ...


class SimulatedClassicAudio:
    """In-memory speaker connection used by development and UI simulation."""

    def __init__(self) -> None:
        self._snapshot = ClassicAudioSnapshot(
            available=True,
            connected=False,
            paired=True,
            trusted=True,
            sink_ready=False,
            sink_id=None,
            address="00:00:00:00:00:00",
            device_name="ServoSkelly(Live) (simulated)",
            last_error=None,
            changed_at=self._now(),
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def snapshot(self) -> ClassicAudioSnapshot:
        return self._snapshot

    async def refresh(self) -> ClassicAudioSnapshot:
        return self._snapshot

    async def connect(self) -> ClassicAudioSnapshot:
        return self._update(connected=True, sink_ready=True, sink_id="simulated")

    async def prepare(self, pin: str) -> ClassicAudioSnapshot:
        del pin
        return self._update(
            connected=True, paired=True, trusted=True,
            sink_ready=True, sink_id="simulated",
        )

    async def disconnect(self) -> ClassicAudioSnapshot:
        return self._update(connected=False, sink_ready=False, sink_id=None)

    async def forget(self) -> ClassicAudioSnapshot:
        return self._update(
            connected=False,
            paired=False,
            trusted=False,
            sink_ready=False,
            sink_id=None,
            address=None,
            device_name=None,
            last_error=None,
        )

    def clear_saved_target(self) -> None:
        self._update(address=None, device_name=None)

    def set_saved_target(self, address: str | None) -> None:
        self._update(address=address, device_name="ServoSkelly(Live) (simulated)")

    def _update(self, **changes: object) -> ClassicAudioSnapshot:
        current = self._snapshot.to_dict()
        current.update(changes)
        current["changed_at"] = self._now()
        self._snapshot = ClassicAudioSnapshot(**current)
        return self._snapshot


@dataclass(frozen=True, slots=True)
class _CommandResult:
    returncode: int
    output: str


class BluetoothClassicAudio:
    """Discover, pair, connect, and route the Skelly Classic audio endpoint."""

    _DEVICE_PATTERN = re.compile(
        r"^Device\s+([0-9A-F]{2}(?::[0-9A-F]{2}){5})\s+(.+)$",
        re.IGNORECASE,
    )

    def __init__(
        self,
        *,
        address: str | None = None,
        name_filter: str = "Skelly(Live)",
        timeout_seconds: float = 20.0,
    ) -> None:
        self._configured_address = address.upper() if address else None
        self._address = self._configured_address
        self._name_filter = name_filter
        self._timeout_seconds = timeout_seconds
        self._lock = asyncio.Lock()
        self._snapshot = ClassicAudioSnapshot(
            available=shutil.which("bluetoothctl") is not None,
            connected=False,
            paired=False,
            trusted=False,
            sink_ready=False,
            sink_id=None,
            address=self._address,
            device_name=None,
            last_error=None,
            changed_at=self._now(),
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def snapshot(self) -> ClassicAudioSnapshot:
        return self._snapshot

    async def refresh(self) -> ClassicAudioSnapshot:
        async with self._lock:
            if shutil.which("bluetoothctl") is None:
                return self._update(
                    available=False,
                    connected=False,
                    paired=False,
                    trusted=False,
                    last_error="bluetoothctl is not installed",
                )
            try:
                address = await self._resolve_address()
                snapshot = await self._read_info(address)
                if snapshot.connected:
                    return await self._read_pipewire_status()
                return self._update(sink_ready=False, sink_id=None)
            except ClassicAudioUnavailable as exc:
                return self._update(
                    available=True,
                    connected=False,
                    paired=False,
                    trusted=False,
                    sink_ready=False,
                    sink_id=None,
                    last_error=str(exc),
                )

    async def connect(self) -> ClassicAudioSnapshot:
        async with self._lock:
            self._require_tool()
            address = await self._resolve_address()
            snapshot = await self._read_info(address)
            if not snapshot.connected:
                result = await self._run("connect", address)
                snapshot = await self._read_info(address)
                if result.returncode != 0 or not snapshot.connected:
                    detail = self._useful_output(result.output)
                    message = detail or "The Skelly speaker did not accept the connection"
                    self._update(last_error=message)
                    raise ClassicAudioUnavailable(message)
            return await self._route_pipewire_sink()

    async def prepare(self, pin: str) -> ClassicAudioSnapshot:
        """Discover and pair a first-use speaker, then connect and route it."""
        async with self._lock:
            self._require_tool()
            address = await self._resolve_address(discover=True)
            snapshot = await self._read_info(address)
            if not snapshot.paired:
                paired = await self._run(
                    "--agent", "KeyboardOnly", "pair", address,
                    input_text=f"{pin}\n",
                )
                pair_detail = paired.output.casefold()
                if paired.returncode != 0 and "alreadyexists" not in pair_detail:
                    message = self._useful_output(paired.output) or "The Skelly speaker could not be paired"
                    self._update(last_error=message)
                    raise ClassicAudioUnavailable(message)
                trusted = await self._run("trust", address)
                if trusted.returncode != 0:
                    message = self._useful_output(trusted.output) or "The Skelly speaker could not be trusted"
                    self._update(last_error=message)
                    raise ClassicAudioUnavailable(message)
                snapshot = await self._read_info(address)
                if not snapshot.paired:
                    message = "The Skelly speaker pairing did not complete"
                    self._update(last_error=message)
                    raise ClassicAudioUnavailable(message)
            if not snapshot.connected:
                connected = await self._run("connect", address)
                snapshot = await self._read_info(address)
                if connected.returncode != 0 or not snapshot.connected:
                    message = self._useful_output(connected.output) or "The Skelly speaker did not accept the connection"
                    self._update(last_error=message)
                    raise ClassicAudioUnavailable(message)
            return await self._route_pipewire_sink()

    async def disconnect(self) -> ClassicAudioSnapshot:
        async with self._lock:
            self._require_tool()
            address = await self._resolve_address()
            result = await self._run("disconnect", address)
            snapshot = await self._read_info(address)
            if result.returncode != 0 or snapshot.connected:
                detail = self._useful_output(result.output)
                message = detail or "The Skelly speaker did not disconnect"
                self._update(last_error=message)
                raise ClassicAudioUnavailable(message)
            return self._update(last_error=None, sink_ready=False, sink_id=None)

    async def forget(self) -> ClassicAudioSnapshot:
        async with self._lock:
            self._require_tool()
            address = self._address
            if address is None:
                try:
                    address = await self._resolve_address()
                except ClassicAudioUnavailable:
                    return self._clear_target_snapshot()
            try:
                snapshot = await self._read_info(address)
            except ClassicAudioUnavailable:
                snapshot = self._snapshot
            if snapshot.connected:
                disconnected = await self._run("disconnect", address)
                if disconnected.returncode != 0:
                    message = self._useful_output(disconnected.output) or "The Skelly speaker did not disconnect"
                    raise ClassicAudioUnavailable(message)
            removed = await self._run("remove", address)
            already_absent = "not available" in removed.output.casefold()
            if removed.returncode != 0 and not already_absent:
                message = self._useful_output(removed.output) or "The Skelly speaker pairing could not be removed"
                raise ClassicAudioUnavailable(message)
            return self._clear_target_snapshot()

    def clear_saved_target(self) -> None:
        self._clear_target_snapshot()

    def set_saved_target(self, address: str | None) -> None:
        normalized = address.upper() if address else None
        self._configured_address = normalized
        self._address = normalized
        self._update(address=normalized, device_name=None, last_error=None)

    def _clear_target_snapshot(self) -> ClassicAudioSnapshot:
        self._configured_address = None
        self._address = None
        return self._update(
            connected=False,
            paired=False,
            trusted=False,
            sink_ready=False,
            sink_id=None,
            address=None,
            device_name=None,
            last_error=None,
        )

    def _require_tool(self) -> None:
        if shutil.which("bluetoothctl") is None:
            raise ClassicAudioUnavailable("bluetoothctl is not installed")

    async def _resolve_address(self, *, discover: bool = False) -> str:
        if self._address:
            return self._address

        target = self._name_filter.casefold()
        commands = [("devices", "Paired"), ("devices",)]
        if discover:
            # Live Mode exposes the Classic endpoint only after BLE control asks
            # for it. A bounded BR/EDR scan makes first-use setup deterministic.
            await self._run("--timeout", "12", "scan", "bredr")
            commands.append(("devices",))
        for command in commands:
            result = await self._run(*command)
            for raw_line in result.output.splitlines():
                match = self._DEVICE_PATTERN.match(raw_line.strip())
                if match and target in match.group(2).casefold():
                    self._address = match.group(1).upper()
                    return self._address
        raise ClassicAudioUnavailable(
            f'No paired Bluetooth speaker matching "{self._name_filter}" was found'
        )

    async def _read_info(self, address: str) -> ClassicAudioSnapshot:
        result = await self._run("info", address)
        if result.returncode != 0 or "Device " not in result.output:
            raise ClassicAudioUnavailable(
                self._useful_output(result.output) or "Bluetooth speaker information is unavailable"
            )
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

    async def _run(
        self, *arguments: str, input_text: str | None = None
    ) -> _CommandResult:
        executable = shutil.which("bluetoothctl")
        if executable is None:
            raise ClassicAudioUnavailable("bluetoothctl is not installed")
        return await self._run_program(executable, *arguments, input_text=input_text)

    async def _run_program(
        self, executable: str, *arguments: str, input_text: str | None = None
    ) -> _CommandResult:
        try:
            process = await asyncio.create_subprocess_exec(
                executable,
                *arguments,
                stdin=asyncio.subprocess.PIPE if input_text is not None else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(
                process.communicate(
                    input_text.encode() if input_text is not None else None
                ),
                timeout=max(self._timeout_seconds, 18.0) if "scan" in arguments else self._timeout_seconds,
            )
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise ClassicAudioUnavailable("Bluetooth speaker command timed out") from exc
        except OSError as exc:
            raise ClassicAudioUnavailable(f"Bluetooth speaker command failed: {exc}") from exc
        return _CommandResult(
            returncode=process.returncode or 0,
            output=stdout.decode(errors="replace").strip(),
        )

    async def _read_pipewire_status(self) -> ClassicAudioSnapshot:
        executable = shutil.which("wpctl")
        if executable is None:
            return self._update(
                sink_ready=False,
                sink_id=None,
                last_error="wpctl is not installed; Bluetooth connected but audio routing is unavailable",
            )
        result = await self._run_program(executable, "status")
        sink = self._find_sink(result.output)
        if sink is None:
            return self._update(sink_ready=False, sink_id=None)
        sink_id, is_default = sink
        return self._update(sink_ready=is_default, sink_id=sink_id)

    async def _route_pipewire_sink(self) -> ClassicAudioSnapshot:
        executable = shutil.which("wpctl")
        if executable is None:
            return self._update(
                sink_ready=False,
                sink_id=None,
                last_error="Bluetooth connected, but wpctl is not installed",
            )
        # The Bluetooth connection can complete several seconds before
        # WirePlumber publishes the A2DP sink on a fresh boot.  Keep this
        # first button press alive long enough for that initial publication.
        for _ in range(24):
            result = await self._run_program(executable, "status")
            sink = self._find_sink(result.output)
            if sink is not None:
                sink_id, _ = sink
                routed = await self._run_program(executable, "set-default", sink_id)
                if routed.returncode != 0:
                    return self._update(
                        sink_ready=False,
                        sink_id=sink_id,
                        last_error=self._useful_output(routed.output)
                        or "Unable to select the Skelly speaker as the default output",
                    )

                # PipeWire creates a new Bluetooth sink at 40% on the image.
                # That is audible, but too quiet to drive Skelly's onboard
                # audio-reactive jaw.  Initialize the transport at unity gain;
                # the separate Skelly speaker-volume control remains available
                # for the user's preferred listening level.
                volume = await self._run_program(
                    executable, "set-volume", sink_id, "1.0"
                )
                if volume.returncode != 0:
                    return self._update(
                        sink_ready=False,
                        sink_id=sink_id,
                        last_error=self._useful_output(volume.output)
                        or "Skelly connected, but its Pi audio level could not be initialized",
                    )
                return self._update(
                    sink_ready=True,
                    sink_id=sink_id,
                    last_error=None,
                )
            await asyncio.sleep(0.5)
        return self._update(
            sink_ready=False,
            sink_id=None,
            last_error="Bluetooth connected, but the Skelly PipeWire audio output did not appear",
        )

    def _find_sink(self, output: str) -> tuple[str, bool] | None:
        in_audio_sinks = False
        target = self._name_filter.casefold()
        for line in output.splitlines():
            stripped = line.strip()
            if stripped.endswith("Sinks:"):
                in_audio_sinks = True
                continue
            if in_audio_sinks and stripped.endswith(("Sources:", "Filters:", "Streams:")):
                break
            if not in_audio_sinks or target not in stripped.casefold():
                continue
            match = re.search(r"(?:\*\s*)?(\d+)\.\s+", stripped)
            if match:
                return match.group(1), "*" in stripped[: match.start(1)]
        return None

    @staticmethod
    def _useful_output(output: str) -> str:
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        return lines[-1][-300:] if lines else ""

    def _update(self, **changes: object) -> ClassicAudioSnapshot:
        current = self._snapshot.to_dict()
        current.update(changes)
        current["changed_at"] = self._now()
        self._snapshot = ClassicAudioSnapshot(**current)
        return self._snapshot
