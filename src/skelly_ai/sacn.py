"""Guarded sACN/E1.31 output for the external head and jaw DAC."""

from __future__ import annotations

import asyncio
import socket
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Callable


E131_PORT = 5568
DMX_SLOT_COUNT = 512
ACN_PACKET_IDENTIFIER = b"ASC-E1.17\x00\x00\x00"


class DacUnavailable(RuntimeError):
    """Raised when a guarded DAC command cannot be sent."""


def _flags_and_length(length: int) -> bytes:
    if not 0 <= length <= 0x0FFF:
        raise ValueError("E1.31 PDU length is outside the 12-bit range")
    return (0x7000 | length).to_bytes(2, "big")


def build_e131_packet(
    *,
    cid: bytes,
    source_name: str,
    universe: int,
    priority: int,
    sequence: int,
    slots: bytes,
    terminated: bool = False,
) -> bytes:
    """Build one standards-compatible E1.31 data packet."""

    if len(cid) != 16:
        raise ValueError("E1.31 CID must contain exactly 16 bytes")
    if not 1 <= universe <= 63999:
        raise ValueError("E1.31 universe must be between 1 and 63999")
    if not 0 <= priority <= 200:
        raise ValueError("E1.31 priority must be between 0 and 200")
    if not 0 <= sequence <= 255:
        raise ValueError("E1.31 sequence must be between 0 and 255")
    if not 1 <= len(slots) <= DMX_SLOT_COUNT:
        raise ValueError("E1.31 must contain between 1 and 512 DMX slots")

    source = source_name.encode("utf-8")[:63]
    source = source + (b"\x00" * (64 - len(source)))
    property_count = len(slots) + 1  # DMX start code plus channel slots.
    packet_size = 126 + len(slots)

    packet = bytearray()
    packet.extend((0x0010).to_bytes(2, "big"))
    packet.extend((0x0000).to_bytes(2, "big"))
    packet.extend(ACN_PACKET_IDENTIFIER)

    packet.extend(_flags_and_length(packet_size - 16))
    packet.extend((0x00000004).to_bytes(4, "big"))
    packet.extend(cid)

    packet.extend(_flags_and_length(packet_size - 38))
    packet.extend((0x00000002).to_bytes(4, "big"))
    packet.extend(source)
    packet.append(priority)
    packet.extend((0).to_bytes(2, "big"))  # Synchronization address.
    packet.append(sequence)
    packet.append(0x40 if terminated else 0x00)
    packet.extend(universe.to_bytes(2, "big"))

    packet.extend(_flags_and_length(packet_size - 115))
    packet.append(0x02)
    packet.append(0xA1)
    packet.extend((0).to_bytes(2, "big"))
    packet.extend((1).to_bytes(2, "big"))
    packet.extend(property_count.to_bytes(2, "big"))
    packet.append(0x00)  # DMX start code.
    packet.extend(slots)
    return bytes(packet)


@dataclass(frozen=True, slots=True)
class DacSnapshot:
    driver: str
    target: str
    port: int
    universe: int
    priority: int
    fps: float
    armed: bool
    transmitting: bool
    channels: dict[str, int]
    values: dict[str, int]
    packet_count: int
    last_error: str | None
    changed_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class SacnDacController:
    """Safety-interlocked unicast E1.31 source for four DAC channels.

    Arming alone never creates a socket or transmits a packet. The first
    explicit position command starts the stream. Releasing sends stream-
    terminated packets and leaves the last requested servo position intact.
    """

    def __init__(
        self,
        *,
        target: str,
        universe: int = 1,
        priority: int = 90,
        fps: float = 20.0,
        source_name: str = "Skelly AI",
        port: int = E131_PORT,
        jaw_channel: int = 1,
        tilt_channel: int = 5,
        yaw_channel: int = 7,
        pitch_channel: int = 12,
        jaw_closed: int = 0,
        tilt_center: int = 127,
        yaw_center: int = 127,
        pitch_center: int = 127,
        cid: bytes | None = None,
        socket_factory: Callable[..., socket.socket] = socket.socket,
    ) -> None:
        if not target.strip():
            raise ValueError("DAC target address cannot be empty")
        if not 1 <= universe <= 63999:
            raise ValueError("DAC universe must be between 1 and 63999")
        if not 0 <= priority <= 200:
            raise ValueError("DAC priority must be between 0 and 200")
        if not 1 <= fps <= 44:
            raise ValueError("DAC frame rate must be between 1 and 44 FPS")
        if not 1 <= port <= 65535:
            raise ValueError("DAC UDP port must be between 1 and 65535")

        channels = {
            "jaw": jaw_channel,
            "tilt": tilt_channel,
            "yaw": yaw_channel,
            "pitch": pitch_channel,
        }
        if len(set(channels.values())) != len(channels):
            raise ValueError("DAC channels must be unique")
        if any(not 1 <= channel <= DMX_SLOT_COUNT for channel in channels.values()):
            raise ValueError("DAC channels must be between 1 and 512")

        values = {
            "jaw": jaw_closed,
            "tilt": tilt_center,
            "yaw": yaw_center,
            "pitch": pitch_center,
        }
        if not 0 <= values["jaw"] <= 255:
            raise ValueError("DAC jaw value must be between 0 and 255")
        if any(not 1 <= values[name] <= 255 for name in ("tilt", "yaw", "pitch")):
            raise ValueError("DAC head-axis values must be between 1 and 255")

        self._target = target.strip()
        self._port = port
        self._universe = universe
        self._priority = priority
        self._fps = float(fps)
        self._source_name = source_name
        self._channels = channels
        self._values = values
        self._centers = values.copy()
        self._cid = cid or uuid.uuid5(
            uuid.NAMESPACE_DNS,
            f"skelly-ai:{uuid.getnode():012x}",
        ).bytes
        self._socket_factory = socket_factory
        self._socket: socket.socket | None = None
        self._lock = asyncio.Lock()
        self._stream_task: asyncio.Task[None] | None = None
        self._armed = False
        self._transmitting = False
        self._sequence = 0
        self._packet_count = 0
        self._last_error: str | None = None
        self._changed_at = self._now()

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def snapshot(self) -> DacSnapshot:
        return DacSnapshot(
            driver="sacn_unicast",
            target=self._target,
            port=self._port,
            universe=self._universe,
            priority=self._priority,
            fps=self._fps,
            armed=self._armed,
            transmitting=self._transmitting,
            channels=self._channels.copy(),
            values=self._values.copy(),
            packet_count=self._packet_count,
            last_error=self._last_error,
            changed_at=self._changed_at,
        )

    def _slots(self) -> bytes:
        slots = bytearray(DMX_SLOT_COUNT)
        for name, channel in self._channels.items():
            slots[channel - 1] = self._values[name]
        return bytes(slots)

    def _ensure_socket(self) -> socket.socket:
        if self._socket is None:
            self._socket = self._socket_factory(socket.AF_INET, socket.SOCK_DGRAM)
        return self._socket

    def _send(self, *, terminated: bool = False) -> None:
        packet = build_e131_packet(
            cid=self._cid,
            source_name=self._source_name,
            universe=self._universe,
            priority=self._priority,
            sequence=self._sequence,
            slots=self._slots(),
            terminated=terminated,
        )
        try:
            self._ensure_socket().sendto(packet, (self._target, self._port))
        except OSError as exc:
            self._last_error = str(exc)
            self._transmitting = False
            self._changed_at = self._now()
            raise DacUnavailable(f"DAC E1.31 send failed: {exc}") from exc
        self._sequence = (self._sequence + 1) % 256
        self._packet_count += 1
        self._last_error = None
        self._changed_at = self._now()

    async def arm(self) -> DacSnapshot:
        async with self._lock:
            # Never carry an open-jaw value into a newly armed session. Arming
            # remains motionless; the safe value is sent with the first command.
            self._values["jaw"] = self._centers["jaw"]
            self._armed = True
            self._last_error = None
            self._changed_at = self._now()
            return self.snapshot()

    async def set_position(
        self,
        *,
        jaw: int | None = None,
        tilt: int | None = None,
        yaw: int | None = None,
        pitch: int | None = None,
    ) -> DacSnapshot:
        requested = {
            "jaw": jaw,
            "tilt": tilt,
            "yaw": yaw,
            "pitch": pitch,
        }
        supplied = {name: value for name, value in requested.items() if value is not None}
        if not supplied:
            raise ValueError("At least one DAC position must be supplied")
        if "jaw" in supplied and not 0 <= supplied["jaw"] <= 255:
            raise ValueError("DAC jaw value must be between 0 and 255")
        if any(
            name != "jaw" and not 1 <= value <= 255
            for name, value in supplied.items()
        ):
            raise ValueError("DAC head-axis values must be between 1 and 255")
        if "jaw" in supplied:
            # The jaw output is a binary gate: zero closes it and any
            # non-zero channel value opens it.
            supplied["jaw"] = 0 if supplied["jaw"] == 0 else 255

        async with self._lock:
            if not self._armed:
                raise DacUnavailable("DAC output is disarmed")
            self._values.update(supplied)
            self._transmitting = True
            self._send()
            if self._stream_task is None or self._stream_task.done():
                self._stream_task = asyncio.create_task(self._stream())
            return self.snapshot()

    async def center(self) -> DacSnapshot:
        return await self.set_position(**self._centers)

    async def _stream(self) -> None:
        try:
            while True:
                await asyncio.sleep(1.0 / self._fps)
                async with self._lock:
                    if not self._armed or not self._transmitting:
                        return
                    self._send()
        except asyncio.CancelledError:
            return
        except DacUnavailable:
            return

    async def release(self) -> DacSnapshot:
        task: asyncio.Task[None] | None
        async with self._lock:
            was_transmitting = self._transmitting
            self._armed = False
            self._transmitting = False
            task = self._stream_task
            self._stream_task = None
            if was_transmitting:
                if self._values["jaw"] != self._centers["jaw"]:
                    # Close before terminating the stream so the servo is not
                    # left holding the jaw open under load.
                    self._values["jaw"] = self._centers["jaw"]
                    try:
                        self._send()
                    except DacUnavailable:
                        pass
                for _ in range(3):
                    try:
                        self._send(terminated=True)
                    except DacUnavailable:
                        break
            self._changed_at = self._now()
            snapshot = self.snapshot()
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        return snapshot

    async def close(self) -> None:
        await self.release()
        if self._socket is not None:
            self._socket.close()
            self._socket = None
