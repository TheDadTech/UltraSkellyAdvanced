"""Receive FPP 10.x MultiSync media timing without modifying FPP.

Wire layout verified against FalconChristmas/fpp tag 10.3, MultiSync.h/.cpp.
UDP is unauthenticated: an explicit master IPv4 allowlist is required. Receipt
of packets is not proof that an HTTP player or the audio hardware is healthy.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import ipaddress
import math
from pathlib import Path
import socket
import struct
import time
from typing import Callable

GROUP = "239.70.80.80"
PORT = 32320
_HEADER = struct.Struct("<4sBH")
_SYNC = struct.Struct("<BBIf")
_EVENTS = {0: "start", 1: "stop", 2: "sync", 3: "open"}


from pydantic import BaseModel, ConfigDict, model_validator
from .settings_store import ValidatedSettingsStore


class FppSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    master_ip: ipaddress.IPv4Address | None = None
    interface_ip: ipaddress.IPv4Address = ipaddress.IPv4Address("0.0.0.0")
    play_audio: bool = False
    override_ai: bool = False

    @model_validator(mode="after")
    def require_master(self):
        if self.enabled and self.master_ip is None:
            raise ValueError("Enter the Main FPP player IPv4 address")
        if self.master_ip is not None and (self.master_ip.is_multicast or self.master_ip.is_unspecified):
            raise ValueError("Enter a single Main FPP player address")
        return self


class FppSettingsStore(ValidatedSettingsStore):
    def __init__(self, data_dir: Path, defaults=None):
        super().__init__(Path(data_dir)/'fpp-settings.json', FppSettings, defaults)


class InvalidSyncPacket(ValueError):
    pass


@dataclass(frozen=True)
class MediaSync:
    event: str
    filename: str
    position: float


def decode_media_sync(data: bytes) -> MediaSync | None:
    """Only media sync is actionable; never execute command/plugin packets."""
    if len(data) < _HEADER.size or len(data) > 2048:
        raise InvalidSyncPacket("Invalid datagram length")
    magic, kind, length = _HEADER.unpack_from(data)
    if magic != b"FPPD" or length != len(data) - _HEADER.size:
        raise InvalidSyncPacket("Invalid FPP header")
    if kind != 1:
        return None
    if length < _SYNC.size + 2:
        raise InvalidSyncPacket("Truncated sync payload")
    event, file_type, _, seconds = _SYNC.unpack_from(data, _HEADER.size)
    if event not in _EVENTS or file_type not in (0, 1):
        raise InvalidSyncPacket("Unknown sync event or file type")
    if file_type != 1:
        return None
    raw = data[_HEADER.size + _SYNC.size:]
    if not raw.endswith(b"\0") or b"\0" in raw[:-1]:
        raise InvalidSyncPacket("Filename must be terminated exactly once")
    try:
        name = raw[:-1].decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise InvalidSyncPacket("Invalid filename encoding") from exc
    # USA intentionally accepts exact local basenames only. No path resolution,
    # extension guessing, shell commands, downloads, or remote filenames as paths.
    if (not name or len(raw) > 161 or name in {".", ".."}
            or any(c in name for c in "/\\")
            or any(ord(c) < 32 or ord(c) == 127 for c in name)):
        raise InvalidSyncPacket("Unsafe local filename")
    if not math.isfinite(seconds) or not 0 <= seconds <= 86400:
        raise InvalidSyncPacket("Invalid media position")
    return MediaSync(_EVENTS[event], name, seconds)


class MediaTimeline:
    """Background timing survives foreground ownership; no hardware side effects."""
    def __init__(self, media_dir: Path, master_ip: str, *,
                 clock: Callable[[], float] = time.monotonic,
                 stale_after: float = 5.0) -> None:
        self.media_dir = Path(media_dir)
        self.master_ip = str(ipaddress.IPv4Address(master_ip))
        self.clock = clock
        self.stale_after = stale_after
        self.filename: str | None = None
        self.playing = False
        self.revision = 0
        self._position = 0.0
        self._anchor = clock()
        self._seen: float | None = None
        self.accepted = self.invalid = self.ignored = 0
        self.listener_error: str | None = None

    def receive(self, data: bytes, sender: str) -> bool:
        if sender != self.master_ip:
            self.ignored += 1
            return False
        try:
            packet = decode_media_sync(data)
        except InvalidSyncPacket:
            self.invalid += 1
            return False
        if packet is None:
            self.ignored += 1
            return False
        now = self.clock()
        self.accepted += 1
        # Delayed stop/open for a different file must not disrupt active media.
        if packet.event == "stop":
            if packet.filename == self.filename:
                self._seen = now
                self._position = self.position()
                self.playing = False
            return True
        if packet.event == "open":
            if not self.playing:
                self._seen = now
                self.filename = packet.filename
                self._position = 0
                self._anchor = now
            return True
        if packet.event == 'start' or not self.playing or packet.filename != self.filename:
            self.revision += 1
        self._seen = now
        self.filename = packet.filename
        self._position = packet.position
        self._anchor = now
        self.playing = True
        return True

    def position(self) -> float:
        return self._position + (max(0, self.clock() - self._anchor) if self.playing else 0)

    def local_file(self) -> Path | None:
        if not self.filename:
            return None
        import json
        name = self.filename
        mapping = self.media_dir.parent / "fpp-sequence-map.json"
        try:
            entry = json.loads(mapping.read_text()).get(name)
            if entry:
                name = entry["file"]
                if not isinstance(name, str) or Path(name).name != name or "/" in name or "\\" in name:
                    return None
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            return None
        path = self.media_dir / name
        if path.suffix.casefold() not in {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac"}:
            return None
        # Symlinks are excluded so a hostile packet cannot expose another file.
        if path.is_symlink() or not path.is_file():
            return None
        if path.resolve().parent != self.media_dir.resolve():
            return None
        return path

    def snapshot(self) -> dict[str, object]:
        age = None if self._seen is None else max(0, self.clock() - self._seen)
        fresh = age is not None and age <= self.stale_after
        matched = self.local_file() is not None
        return {"master_ip": self.master_ip, "sync_recent": fresh,
                "seconds_since_media_sync": age, "filename": self.filename,
                "playing": bool(self.playing and fresh),
                "position_seconds": round(self.position(), 3),
                "local_match": matched,
                "eligible": bool(self.playing and fresh and matched),
                "accepted_packets": self.accepted, "invalid_packets": self.invalid,
                "ignored_packets": self.ignored, "listener_error": self.listener_error,
                "playback_implemented": False}


def decode_discovery(data: bytes, sender: str) -> dict | None:
    """Read only bounded FPP native ping replies; never act on commands."""
    if len(data) < 7 + 169 or len(data) > 1024:
        return None
    magic, kind, length = _HEADER.unpack_from(data)
    if magic != b"FPPD" or kind != 4 or length != len(data) - 7:
        return None
    payload = data[7:]
    if payload[0] not in (1, 2, 3, 4) or payload[1] != 0 or not 1 <= payload[2] < 128:
        return None
    try:
        address = ipaddress.IPv4Address(sender)
        if not address.is_private or address.is_loopback or address.is_multicast or address.is_unspecified:
            return None
        def text(start, size):
            return ''.join(c for c in payload[start:start+size].split(b"\0", 1)[0].decode("utf-8", "replace") if c.isprintable())
        return {"address": str(address), "hostname": text(12, 64) or str(address),
                "version": text(77, 40), "sending_sync": bool(payload[7] & 4)}
    except ValueError:
        return None


class MultiSyncListener(asyncio.DatagramProtocol):
    def __init__(self, timeline: MediaTimeline) -> None:
        self.timeline = timeline
        self.transport: asyncio.DatagramTransport | None = None
        self.discovered: dict[str, dict] = {}

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        found = decode_discovery(data, addr[0])
        if found is not None:
            if len(self.discovered) < 128 or addr[0] in self.discovered:
                self.discovered[addr[0]] = found
            return
        self.timeline.receive(data, addr[0])

    def error_received(self, exc: Exception) -> None:
        self.timeline.listener_error = str(exc)

    async def start(self, interface_ip: str = "0.0.0.0") -> None:
        if self.transport is not None:
            return
        interface_ip = str(ipaddress.IPv4Address(interface_ip))
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", PORT))
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                            socket.inet_aton(GROUP) + socket.inet_aton(interface_ip))
            sock.setblocking(False)
            self.transport, _ = await asyncio.get_running_loop().create_datagram_endpoint(
                lambda: self, sock=sock)
            self.timeline.listener_error = None
        except Exception:
            sock.close()
            raise

    async def discover(self) -> list[dict]:
        if self.transport is None:
            raise RuntimeError("FPP discovery listener is unavailable")
        self.discovered.clear()
        payload = bytearray(294)
        payload[0:3] = bytes((3, 1, 0xC0))
        # Zero advertised address marks a discovery-only client, not a new remote.
        self.transport.sendto(_HEADER.pack(b"FPPD", 4, len(payload)) + payload, (GROUP, PORT))
        await asyncio.sleep(3)
        return sorted(self.discovered.values(), key=lambda item: item["hostname"].casefold())

    def close(self) -> None:
        if self.transport is not None:
            self.transport.close()
            self.transport = None


class FppPlayback:
    """Consume a synchronized local file at the lowest audio priority.

    The timeline, not a suspended player process, preserves position during
    foreground interaction. Re-entry trims decoded PCM to the current position.
    """
    def __init__(self, timeline: MediaTimeline, speech, jaw, *, silent: bool = True,
                 prepare=None, ready=lambda: True, stock_before=None, stock_after=None, stock_target=None, offset_seconds=0.0, priority_update=None, preset_before=None, preset_after=None, file_settings=None) -> None:
        self.timeline, self.speech, self.jaw = timeline, speech, jaw
        self.silent, self.prepare, self.ready = silent, prepare, ready
        self.stock_before, self.stock_after, self.stock_target = stock_before, stock_after, stock_target
        self.offset_seconds = offset_seconds
        self.priority_update = priority_update
        self.preset_before, self.preset_after = preset_before, preset_after
        self.file_settings = file_settings or (lambda path: {})
        self._worker: asyncio.Task | None = None
        self._audio: asyncio.Task | None = None
        self._file: str | None = None
        self._exhausted: str | None = None
        self._last_position = 0.0
        self._revision = -1
        self._audio_anchor = 0.0
        self._audio_start = 0.0
        self.last_error: str | None = None

    def status(self) -> dict[str, object]:
        return {'playback_implemented': True,
                'audio_active': bool(self._audio and not self._audio.done()),
                'audio_filename': self._file if self._audio and not self._audio.done() else None,
                'silent': self.silent, 'playback_error': self.last_error,
                'foreground_active': self.speech._lock.foreground_busy}

    async def start(self) -> None:
        if self._worker is None:
            self._worker = asyncio.create_task(self._run())

    async def _stop_audio(self) -> None:
        audio = self._audio
        if audio is None:
            return
        if not audio.done() and not audio.cancelling():
            audio.cancel()
        caller_cancelled = False
        while not audio.done():
            try:
                await asyncio.shield(audio)
            except asyncio.CancelledError:
                # Child cancellation is expected. Cancellation of the supervisor
                # must survive cleanup or close() can wait forever on its loop.
                if asyncio.current_task().cancelling():
                    caller_cancelled = True
            except Exception as exc:
                self.last_error = str(exc)
        if not audio.cancelled():
            error = audio.exception()
            if error is not None:
                self.last_error = str(error)
        if self._audio is audio:
            self._audio = None
        if caller_cancelled:
            raise asyncio.CancelledError

    async def close(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
            self._worker = None
        await self._stop_audio()

    def playback_position(self) -> float:
        offset = float(self.offset_seconds() if callable(self.offset_seconds) else self.offset_seconds)
        if not math.isfinite(offset) or abs(offset) > 5:
            raise ValueError("Invalid FPP jaw timing offset")
        return max(0.0, self.timeline.position() + offset)

    async def _play(self, path: Path) -> None:
        if self.prepare is not None:
            await self.prepare()
        def current_position():
            position = self.playback_position()
            self._audio_anchor = self.timeline.clock()
            self._audio_start = position
            return position
        stock_silent = self.silent and not self.jaw.snapshot().armed
        async def before():
            if stock_silent and self.stock_before:
                await self.stock_before()
            if self.preset_before:
                await self.preset_before(path)
        async def after():
            try:
                if self.preset_after:
                    await self.preset_after()
            finally:
                if stock_silent and self.stock_after:
                    await self.stock_after()
        await self.speech.play_audio_file(path, self.jaw, engine='fpp-local',
                                          background=True, start_seconds=current_position,
                                          silent=self.silent and not stock_silent,
                                          target_override=self.stock_target if (stock_silent or not self.silent) else None,
                                          before_play=before if self.preset_before or stock_silent else None,
                                          after_play=after if self.preset_after or stock_silent else None,
                                          jaw_follow=bool(self.file_settings(path).get('jaw_sync', True)))

    async def _run(self) -> None:
        from .audio_priority import BackgroundDeferred
        try:
            while True:
                snapshot = self.timeline.snapshot()
                if self.priority_update:
                    if not snapshot['eligible']:
                        await self._stop_audio()
                    await self.priority_update(bool(snapshot['eligible']))
                position = self.timeline.position()
                name = self.timeline.filename
                if name != self._file or self.timeline.revision != self._revision or position < self._last_position - 1:
                    await self._stop_audio()
                    self._file = name
                    self._revision = self.timeline.revision
                    self._exhausted = None
                    self.last_error = None
                self._last_position = position
                allowed = snapshot['eligible'] and self.ready()
                if self.silent and not self.jaw.snapshot().armed:
                    allowed = False
                    self.last_error = 'Silent stock FPP singing failed hardware validation; allow audible playback or use independent DAC jaw control'
                if self._audio is not None and self._audio.done():
                    try:
                        self._audio.result()
                    except (asyncio.CancelledError, BackgroundDeferred):
                        pass
                    except Exception as exc:
                        self.last_error = str(exc)
                        self._exhausted = name  # do not retry broken audio at 5Hz
                    else:
                        self._exhausted = name
                    self._audio = None
                # Stop packets, stale timing, missing files, and foreground use
                # must all terminate background output before another owner plays.
                if not allowed or self.speech._lock.foreground_busy:
                    await self._stop_audio()
                elif self._audio and self._audio_anchor:
                    expected = self._audio_start + self.timeline.clock() - self._audio_anchor
                    if abs(self.playback_position() - expected) > 1.0:
                        await self._stop_audio()
                if allowed and not self.speech._lock.foreground_busy and self._audio is None and self._exhausted != name:
                    path = self.timeline.local_file()
                    if path is not None:
                        self._audio_anchor = 0
                        self._audio = asyncio.create_task(self._play(path))
                await asyncio.sleep(.2)
        finally:
            try:
                await self._stop_audio()
            finally:
                if self.priority_update:
                    await self.priority_update(False)
