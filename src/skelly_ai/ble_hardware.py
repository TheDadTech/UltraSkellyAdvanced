import asyncio
from collections import deque
from datetime import UTC, datetime
from typing import Any

try:
    from bleak import BleakClient, BleakScanner
except ImportError:  # Allows simulator-only development before BLE extras install.
    BleakClient = None  # type: ignore[assignment,misc]
    BleakScanner = None  # type: ignore[assignment,misc]

from . import ble_protocol
from .hardware import (
    EYE_INDEX,
    MOVEMENT_ACTION,
    EyeIcon,
    HardwareSnapshot,
    HardwareUnavailable,
    Movement,
)


async def discover_skelly_devices(timeout: float = 8.0) -> list[dict[str, object]]:
    """Scan without connecting and return likely Ultra Skelly/Lethal Lily devices."""
    if BleakScanner is None:
        raise RuntimeError("The Bleak Bluetooth package is not installed")
    found = await BleakScanner.discover(timeout=timeout, return_adv=True)
    devices: list[dict[str, object]] = []
    for device, advertisement in found.values():
        name = device.name or advertisement.local_name or "Unknown"
        service_uuids = [value.lower() for value in advertisement.service_uuids]
        likely_prop = (
            "skelly" in name.lower()
            or "lily" in name.lower()
            or ble_protocol.SERVICE_UUID in service_uuids
        )
        if likely_prop:
            devices.append(
                {
                    "name": name,
                    "address": device.address,
                    "rssi": advertisement.rssi,
                    "service_uuids": service_uuids,
                }
            )
    return sorted(devices, key=lambda item: int(item["rssi"]), reverse=True)


class BleSkelly:
    """Persistent BLE adapter with an explicit motor safety interlock."""

    def __init__(
        self,
        address: str | None = None,
        name_filter: str = "Animated Skelly",
        timeout: float = 15.0,
        *,
        scanner: Any = BleakScanner,
        client_factory: Any = BleakClient,
    ) -> None:
        self.address = address
        self.name_filter = name_filter
        self.timeout = timeout
        self._scanner = scanner
        self._client_factory = client_factory
        if self._scanner is None or self._client_factory is None:
            raise HardwareUnavailable("The Bleak Bluetooth package is not installed")
        self._client: Any = None
        self._device_name = name_filter
        self._connected = False
        self._live_mode = False
        self._eye_icon = EyeIcon.NORMAL
        self._eye_index = EYE_INDEX[EyeIcon.NORMAL]
        self._movement = Movement.NONE
        self._movement_armed = False
        self._last_error: str | None = None
        self._last_notification: str | None = None
        self._media_files: dict[int, dict[str, object]] = {}
        self._media_expected = 0
        self._media_refreshing = False
        self._media_event = asyncio.Event()
        self._response_events: dict[str, asyncio.Event] = {}
        self._responses: dict[str, str] = {}
        self._chunk_resume_from: int | None = None
        self._media_order: list[int] = []
        self._playing_serial: int | None = None
        self._volume = 128
        self._firmware_version: str | None = None
        self._changed_at = self._now()
        self._events: deque[dict[str, str]] = deque(maxlen=100)
        self._lock = asyncio.Lock()

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def _record(self, action: str, value: str) -> None:
        self._changed_at = self._now()
        self._events.append({"at": self._changed_at, "action": action, "value": value})

    def _on_disconnect(self, _: Any) -> None:
        self._connected = False
        self._movement_armed = False
        self._movement = Movement.NONE
        self._record("connection", "disconnected")

    def _on_notification(self, _: Any, data: bytearray) -> None:
        self._last_notification = bytes(data).hex().upper()
        self._record("notification", self._last_notification)
        self._parse_notification(self._last_notification)

    def _parse_notification(self, packet: str) -> None:
        prefix = packet[:4]
        self._responses[prefix] = packet
        self._response_events.setdefault(prefix, asyncio.Event()).set()
        if packet.startswith("BBC1") and len(packet) >= 10:
            if int(packet[4:6], 16):
                self._chunk_resume_from = int(packet[6:10], 16)
            return
        if packet.startswith("BBE5") and len(packet) >= 6:
            self._volume = int(packet[4:6], 16)
            return
        if packet.startswith("BBEE") and len(packet) >= 6:
            self._firmware_version = f"v{int(packet[4:6], 16)}"
            self._record("firmware_version", self._firmware_version)
            return
        if packet.startswith("BBD1") and len(packet) >= 6:
            count = int(packet[4:6], 16)
            self._media_order = [
                int(packet[6 + offset : 10 + offset], 16)
                for offset in range(0, min(len(packet) - 6, count * 4), 4)
                if len(packet[6 + offset : 10 + offset]) == 4
            ]
            for serial, item in self._media_files.items():
                item["enabled"] = serial in self._media_order
                item["order"] = self._media_order.index(serial) + 1 if serial in self._media_order else None
            self._media_event.set()
            return
        if not packet.startswith("BBD0") or len(packet) < 116:
            return
        try:
            serial = int(packet[4:8], 16)
            cluster = int(packet[8:16], 16)
            total = int(packet[16:20], 16)
            length = int(packet[20:24], 16)
            action = int(packet[24:26], 16)
            lights = []
            light_data = packet[26:110]
            for offset in range(0, 84, 14):
                channel = light_data[offset : offset + 14]
                if len(channel) < 14:
                    continue
                lights.append(
                    {
                        "effect_mode": int(channel[0:2], 16),
                        "brightness": int(channel[2:4], 16),
                        "r": int(channel[4:6], 16),
                        "g": int(channel[6:8], 16),
                        "b": int(channel[8:10], 16),
                        "cycle": bool(int(channel[10:12], 16)),
                        "effect_speed": int(channel[12:14], 16),
                    }
                )
            eye = int(packet[110:112], 16)
            marker = packet.find("5C55", 114)
            name = ""
            if marker >= 0:
                name_bytes = bytes.fromhex(packet[marker + 4 : -2])
                name = name_bytes.decode("utf-16-le", errors="ignore").strip("\x00 ")
            self._media_expected = max(self._media_expected, total)
            self._media_files[serial] = {
                "serial": serial,
                "cluster": cluster,
                "length": length,
                "action": action,
                "eye": eye,
                "lights": lights,
                "enabled": serial in self._media_order if self._media_order else True,
                "order": self._media_order.index(serial) + 1 if serial in self._media_order else None,
                "name": name or f"Sound {serial}",
            }
            self._media_event.set()
        except (ValueError, UnicodeError):
            return

    def snapshot(self) -> HardwareSnapshot:
        return HardwareSnapshot(
            driver="ble",
            connected=self._connected,
            live_mode=self._live_mode,
            eye_icon=self._eye_icon,
            eye_index=self._eye_index,
            movement=self._movement,
            movement_armed=self._movement_armed,
            address=self.address,
            device_name=self._device_name,
            last_error=self._last_error,
            last_notification=self._last_notification,
            changed_at=self._changed_at,
            event_count=len(self._events),
            firmware_version=self._firmware_version,
        )

    async def _resolve_device(self) -> Any:
        if self.address:
            return await self._scanner.find_device_by_address(
                self.address, timeout=self.timeout
            )
        return await self._scanner.find_device_by_filter(
            lambda device, advertisement: (
                self.name_filter.lower()
                in (device.name or advertisement.local_name or "").lower()
            ),
            timeout=self.timeout,
        )

    async def connect(self, address: str | None = None) -> HardwareSnapshot:
        async with self._lock:
            if address:
                self.address = address
            if self._connected and self._client and self._client.is_connected:
                return self.snapshot()
            try:
                device = await self._resolve_device()
                if device is None:
                    target = self.address or self.name_filter
                    raise HardwareUnavailable(f"Skelly BLE device was not found: {target}")
                self.address = device.address
                self._device_name = device.name or self.name_filter
                client = self._client_factory(
                    device,
                    timeout=self.timeout,
                    disconnected_callback=self._on_disconnect,
                )
                await client.connect()
                services = {service.uuid.lower() for service in client.services}
                if ble_protocol.SERVICE_UUID not in services:
                    await client.disconnect()
                    raise HardwareUnavailable(
                        "Connected device does not expose the Ultra Skelly AE00 service"
                    )
                await client.start_notify(
                    ble_protocol.NOTIFY_UUID, self._on_notification
                )
                self._client = client
                self._connected = True
                self._movement_armed = False
                self._last_error = None
                self._record("connection", f"connected:{self.address}")
                version_event = self._prepare_response("BBEE")
                await self._write_locked(ble_protocol.query_version())
                try:
                    await self._wait_response("BBEE", version_event, 2.0)
                except HardwareUnavailable:
                    # Firmware reporting is helpful metadata, not a connection requirement.
                    self._firmware_version = None
                return self.snapshot()
            except HardwareUnavailable as exc:
                self._last_error = str(exc)
                self._connected = False
                self._record("connection_error", self._last_error)
                raise
            except Exception as exc:
                self._last_error = f"Unable to connect to Skelly over BLE: {exc}"
                self._connected = False
                self._record("connection_error", self._last_error)
                raise HardwareUnavailable(self._last_error) from exc

    async def disconnect(self) -> HardwareSnapshot:
        async with self._lock:
            client = self._client
            self._client = None
            if client:
                try:
                    if client.is_connected:
                        await client.stop_notify(ble_protocol.NOTIFY_UUID)
                        await client.disconnect()
                except Exception as exc:
                    self._last_error = f"BLE disconnect warning: {exc}"
            self._connected = False
            self._movement_armed = False
            self._live_mode = False
            self._firmware_version = None
            self._movement = Movement.NONE
            self._record("connection", "disconnected")
            return self.snapshot()

    async def forget(self) -> HardwareSnapshot:
        await self.disconnect()
        async with self._lock:
            self.address = None
            self._device_name = self.name_filter
            self._last_error = None
            self._record("connection", "forgotten")
            return self.snapshot()

    def clear_saved_target(self) -> None:
        if self._connected:
            raise HardwareUnavailable("Disconnect Skelly before clearing its saved target")
        self.address = None
        self._device_name = self.name_filter

    def set_saved_target(self, address: str | None) -> None:
        if self._connected:
            raise HardwareUnavailable("Disconnect Skelly before changing its saved target")
        self.address = address.upper() if address else None

    def _require_connected(self) -> None:
        if not self._connected or not self._client or not self._client.is_connected:
            raise HardwareUnavailable("Skelly is not connected over BLE")

    async def _write_locked(self, command: bytes) -> None:
        self._require_connected()
        try:
            await self._client.write_gatt_char(
                ble_protocol.WRITE_UUID, command, response=False
            )
        except Exception as exc:
            self._last_error = f"BLE command failed: {exc}"
            raise HardwareUnavailable(self._last_error) from exc

    def _prepare_response(self, prefix: str) -> asyncio.Event:
        event = self._response_events.setdefault(prefix, asyncio.Event())
        event.clear()
        self._responses.pop(prefix, None)
        return event

    async def _wait_response(self, prefix: str, event: asyncio.Event, timeout: float) -> str:
        try:
            await asyncio.wait_for(event.wait(), timeout)
        except TimeoutError as exc:
            raise HardwareUnavailable(f"Skelly did not acknowledge {prefix} in time") from exc
        return self._responses.get(prefix, "")

    async def set_eye(self, icon: EyeIcon) -> HardwareSnapshot:
        return await self.set_eye_index(EYE_INDEX[icon], icon=icon)

    async def set_eye_index(
        self, index: int, *, icon: EyeIcon | None = None
    ) -> HardwareSnapshot:
        async with self._lock:
            await self._write_locked(ble_protocol.set_eye_icon(index))
            self._eye_index = index
            if icon is not None:
                self._eye_icon = icon
            self._last_error = None
            self._record("eye", str(index))
            return self.snapshot()

    async def set_movement(self, movement: Movement) -> HardwareSnapshot:
        async with self._lock:
            if movement != Movement.NONE and not self._movement_armed:
                raise HardwareUnavailable(
                    "Movement is disarmed. Check the prop clearance and arm motors first."
                )
            await self._write_locked(
                ble_protocol.set_movement(MOVEMENT_ACTION[movement])
            )
            self._movement = movement
            self._last_error = None
            self._record("movement", movement.value)
            return self.snapshot()

    async def arm_movement(self, enabled: bool) -> HardwareSnapshot:
        async with self._lock:
            self._require_connected()
            if not enabled:
                await self._write_locked(ble_protocol.set_movement(0))
                self._movement = Movement.NONE
            self._movement_armed = enabled
            self._record("movement_armed", str(enabled).lower())
            return self.snapshot()

    async def set_live_mode(self, enabled: bool) -> HardwareSnapshot:
        async with self._lock:
            await self._write_locked(ble_protocol.set_classic_audio(enabled))
            self._live_mode = enabled
            self._record("live_mode", str(enabled).lower())
            return self.snapshot()

    async def stop(self) -> HardwareSnapshot:
        async with self._lock:
            await self._write_locked(ble_protocol.set_movement(0))
            self._movement = Movement.NONE
            self._record("movement", Movement.NONE.value)
            return self.snapshot()

    async def probe_movement_bit(
        self, action: int, duration_ms: int
    ) -> HardwareSnapshot:
        """Pulse one unused AACA action bit, then unconditionally send Stop."""
        if not 8 <= action <= 248 or action % 8:
            raise ValueError(
                "Diagnostic movement value must be 0x08-0xF8 in steps of 0x08"
            )
        if not 100 <= duration_ms <= 2000:
            raise ValueError("Diagnostic movement pulse must be 100-2000 ms")
        async with self._lock:
            self._require_connected()
            if not self._movement_armed:
                raise HardwareUnavailable(
                    "Movement is disarmed. Check prop clearance and arm motors first."
                )
            try:
                await self._write_locked(ble_protocol.probe_movement_value(action))
                self._record("movement_probe", f"0x{action:02X}:{duration_ms}ms")
                await asyncio.sleep(duration_ms / 1000)
            finally:
                await self._write_locked(ble_protocol.set_movement(0))
                self._movement = Movement.NONE
                self._record("movement", Movement.NONE.value)
            return self.snapshot()

    def media_status(self) -> dict[str, object]:
        files = sorted(self._media_files.values(), key=lambda item: int(item["serial"]))
        return {
            "available": self._connected,
            "files": files,
            "file_count": len(files),
            "expected_count": self._media_expected,
            "playing_serial": self._playing_serial,
            "volume": self._volume,
            "refreshing": self._media_refreshing,
            "last_error": self._last_error,
        }

    async def refresh_media_files(self, timeout: float = 6.0) -> dict[str, object]:
        async with self._lock:
            self._require_connected()
            self._media_files.clear()
            self._media_expected = 0
            self._media_refreshing = True
            self._media_event.clear()
            await self._write_locked(ble_protocol.query_media_files())

        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        try:
            while loop.time() < deadline:
                if self._media_expected and len(self._media_files) >= self._media_expected:
                    break
                remaining = deadline - loop.time()
                try:
                    await asyncio.wait_for(self._media_event.wait(), min(0.8, remaining))
                    self._media_event.clear()
                except TimeoutError:
                    if self._media_files:
                        break
        finally:
            self._media_refreshing = False
        async with self._lock:
            order_event = self._prepare_response("BBD1")
            await self._write_locked(ble_protocol.query_media_order())
        try:
            await self._wait_response("BBD1", order_event, 2.0)
        except HardwareUnavailable:
            pass
        return self.media_status()

    async def play_media(self, serial: int, enabled: bool = True) -> dict[str, object]:
        async with self._lock:
            await self._write_locked(ble_protocol.play_media_file(serial, enabled))
            self._playing_serial = serial if enabled else None
            self._record("media", f"{serial}:{'play' if enabled else 'stop'}")
            return self.media_status()

    async def set_volume(self, volume: int) -> dict[str, object]:
        async with self._lock:
            await self._write_locked(ble_protocol.set_volume(volume))
            self._volume = volume
            self._record("volume", str(volume))
            return self.media_status()

    async def set_lighting(self, channel: int, brightness: int, red: int, green: int, blue: int, mode: int, cycle: bool = False) -> dict[str, object]:
        async with self._lock:
            await self._write_locked(ble_protocol.set_light_brightness(channel, brightness))
            await self._write_locked(ble_protocol.set_light_mode(channel, mode))
            await self._write_locked(ble_protocol.set_light_rgb(channel, red, green, blue, cycle))
            self._record("lighting", f"{channel}:{brightness}:{red},{green},{blue}:{mode}:{cycle}")
            return self.media_status()

    async def edit_media(self, serial: int, action: int, eye: int, head_light: dict[str, object], torso_light: dict[str, object]) -> dict[str, object]:
        async with self._lock:
            item = self._media_files.get(serial)
            if item is None:
                raise HardwareUnavailable(f"Media file #{serial} is not available")
            cluster = int(item["cluster"])
            name = str(item["name"])
            await self._write_locked(ble_protocol.set_media_movement(action, cluster, name))
            await self._write_locked(ble_protocol.set_media_eye(eye, cluster, name))
            for channel, light in ((0, torso_light), (1, head_light)):
                await self._write_locked(ble_protocol.set_light_brightness(channel, int(light["brightness"]), cluster=cluster, name=name))
                await self._write_locked(ble_protocol.set_light_mode(channel, int(light["effect_mode"]), cluster=cluster, name=name))
                await self._write_locked(ble_protocol.set_light_rgb(channel, int(light["r"]), int(light["g"]), int(light["b"]), bool(light.get("cycle", False)), cluster=cluster, name=name))
            item.update(action=action, eye=eye, lights=[dict(torso_light), dict(head_light)])
            self._record("media_edit", str(serial))
            return self.media_status()

    async def set_media_enabled(self, serial: int, enabled: bool) -> dict[str, object]:
        async with self._lock:
            if serial not in self._media_files:
                raise HardwareUnavailable(f"Media file #{serial} is not available")
            order = [value for value in self._media_order if value in self._media_files]
            if not order:
                order = [int(item["serial"]) for item in self._media_files.values() if bool(item.get("enabled", True))]
            if enabled and serial not in order:
                order.append(serial)
            if not enabled:
                order = [value for value in order if value != serial]
            if not order:
                raise HardwareUnavailable("At least one Classic media file must remain enabled")
            for position, value in enumerate(order, start=1):
                item = self._media_files[value]
                await self._write_locked(ble_protocol.set_media_order(len(order), position, value, str(item["name"])))
                await asyncio.sleep(0.05)
            self._media_order = order
            for value, item in self._media_files.items():
                item["enabled"] = value in order
                item["order"] = order.index(value) + 1 if value in order else None
            return self.media_status()

    async def upload_media(self, name: str, data: bytes) -> dict[str, object]:
        if not data:
            raise HardwareUnavailable("The selected audio file is empty")
        chunk_size = 250
        packet_count = (len(data) + chunk_size - 1) // chunk_size
        async with self._lock:
            self._chunk_resume_from = None
            start_event = self._prepare_response("BBC0")
            await self._write_locked(ble_protocol.start_media_transfer(len(data), packet_count, name))
            start = await self._wait_response("BBC0", start_event, 8.0)
            if len(start) >= 6 and int(start[4:6], 16):
                raise HardwareUnavailable("Skelly rejected the file transfer")
            written = int(start[6:14], 16) if len(start) >= 14 else 0
            index = min(packet_count, written // chunk_size)
            retries = 0
            while index < packet_count:
                chunk = data[index * chunk_size : (index + 1) * chunk_size]
                await self._write_locked(ble_protocol.media_transfer_chunk(index, chunk))
                await asyncio.sleep(0.05)
                if self._chunk_resume_from is not None:
                    resume_from = self._chunk_resume_from
                    self._chunk_resume_from = None
                    if not 0 <= resume_from < packet_count:
                        raise HardwareUnavailable("Skelly requested an invalid audio transfer position")
                    retries += 1
                    if retries > 8:
                        raise HardwareUnavailable("Skelly repeatedly rejected audio chunks; please retry")
                    index = resume_from
                    continue
                index += 1
            end_event = self._prepare_response("BBC2")
            await self._write_locked(ble_protocol.end_media_transfer())
            end = await self._wait_response("BBC2", end_event, 180.0)
            if len(end) >= 6 and int(end[4:6], 16):
                resume_from = int(end[6:10], 16) if len(end) >= 10 else 0
                if not 0 <= resume_from < packet_count:
                    raise HardwareUnavailable("Skelly reported an incomplete file transfer; please retry")
                for index in range(resume_from, packet_count):
                    chunk = data[index * chunk_size : (index + 1) * chunk_size]
                    await self._write_locked(ble_protocol.media_transfer_chunk(index, chunk))
                    await asyncio.sleep(0.012)
            confirm_event = self._prepare_response("BBC3")
            await self._write_locked(ble_protocol.confirm_media_transfer(name))
            confirm = await self._wait_response("BBC3", confirm_event, 8.0)
            if len(confirm) >= 6 and int(confirm[4:6], 16):
                raise HardwareUnavailable("Skelly could not save the uploaded file")
            self._record("media_upload", f"{name}:{len(data)}")
        return await self.refresh_media_files(timeout=8.0)
