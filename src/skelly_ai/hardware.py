import asyncio
from collections import deque
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol


class EyeIcon(StrEnum):
    NORMAL = "normal"
    HAZEL = "hazel"
    GREEN = "green"
    BROWN = "brown"
    ANGRY = "angry"
    GRAY = "gray"
    SQUINT = "squint"
    ORANGE_CAT = "orange_cat"
    SPIRAL = "spiral"
    FIRE = "fire"
    STAR = "star"
    SKULL = "skull"
    FIREWORKS = "fireworks"
    AMERICAN_FLAG = "american_flag"
    HEARTS = "hearts"
    CLOVER = "clover"
    SNOWFLAKE = "snowflake"
    CONFETTI = "confetti"


EYE_INDEX = {
    EyeIcon.NORMAL: 1,
    EyeIcon.HAZEL: 2,
    EyeIcon.GREEN: 3,
    EyeIcon.BROWN: 4,
    EyeIcon.ANGRY: 5,
    EyeIcon.GRAY: 6,
    EyeIcon.SQUINT: 7,
    EyeIcon.ORANGE_CAT: 8,
    EyeIcon.SPIRAL: 9,
    EyeIcon.FIRE: 10,
    EyeIcon.STAR: 11,
    EyeIcon.SKULL: 12,
    EyeIcon.FIREWORKS: 13,
    EyeIcon.AMERICAN_FLAG: 14,
    EyeIcon.HEARTS: 15,
    EyeIcon.CLOVER: 16,
    EyeIcon.SNOWFLAKE: 17,
    EyeIcon.CONFETTI: 18,
}


class Movement(StrEnum):
    NONE = "none"
    HEAD_ONLY = "head_only"
    ARMS_ONLY = "arms_only"
    TORSO_ONLY = "torso_only"
    HEAD_AND_TORSO = "head_and_torso"
    TORSO_AND_ARMS = "torso_and_arms"
    ALL = "all"


MOVEMENT_ACTION = {
    Movement.NONE: 0,
    Movement.HEAD_ONLY: 1,
    Movement.ARMS_ONLY: 2,
    Movement.TORSO_ONLY: 4,
    Movement.HEAD_AND_TORSO: 5,
    Movement.TORSO_AND_ARMS: 6,
    Movement.ALL: 255,
}


class HardwareUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class HardwareSnapshot:
    driver: str
    connected: bool
    live_mode: bool
    eye_icon: EyeIcon
    eye_index: int
    movement: Movement
    movement_armed: bool
    address: str | None
    device_name: str | None
    last_error: str | None
    last_notification: str | None
    changed_at: str
    event_count: int
    firmware_version: str | None = None

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["eye_icon"] = self.eye_icon.value
        result["movement"] = self.movement.value
        return result


class SkellyHardware(Protocol):
    async def connect(self, address: str | None = None) -> HardwareSnapshot: ...
    async def disconnect(self) -> HardwareSnapshot: ...
    async def forget(self) -> HardwareSnapshot: ...
    def clear_saved_target(self) -> None: ...
    def set_saved_target(self, address: str | None) -> None: ...
    async def set_eye(self, icon: EyeIcon) -> HardwareSnapshot: ...
    async def set_eye_index(self, index: int) -> HardwareSnapshot: ...
    async def set_movement(self, movement: Movement) -> HardwareSnapshot: ...
    async def set_live_mode(self, enabled: bool) -> HardwareSnapshot: ...
    async def arm_movement(self, enabled: bool) -> HardwareSnapshot: ...
    async def stop(self) -> HardwareSnapshot: ...
    async def probe_movement_bit(self, action: int, duration_ms: int) -> HardwareSnapshot: ...
    async def refresh_media_files(self, timeout: float = 6.0) -> dict[str, object]: ...
    async def play_media(self, serial: int, enabled: bool = True) -> dict[str, object]: ...
    async def set_volume(self, volume: int) -> dict[str, object]: ...
    async def set_lighting(self, channel: int, brightness: int, red: int, green: int, blue: int, mode: int, cycle: bool = False) -> dict[str, object]: ...
    async def edit_media(self, serial: int, action: int, eye: int, head_light: dict[str, object], torso_light: dict[str, object]) -> dict[str, object]: ...
    async def set_media_enabled(self, serial: int, enabled: bool) -> dict[str, object]: ...
    async def upload_media(self, name: str, data: bytes) -> dict[str, object]: ...
    def media_status(self) -> dict[str, object]: ...
    def snapshot(self) -> HardwareSnapshot: ...


class SimulatedSkelly:
    """Stateful test double matching the future BLE hardware interface."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._connected = False
        self._live_mode = False
        self._eye_icon = EyeIcon.NORMAL
        self._eye_index = EYE_INDEX[EyeIcon.NORMAL]
        self._movement = Movement.NONE
        self._movement_armed = True
        self._changed_at = self._now()
        self._events: deque[dict[str, str]] = deque(maxlen=50)
        self._volume = 128
        self._firmware_version = "vSIM"
        self._playing_serial: int | None = None
        self._live_lights = {
            "torso": {"effect_mode": 1, "brightness": 200, "r": 51, "g": 0, "b": 255, "cycle": False},
            "head": {"effect_mode": 1, "brightness": 200, "r": 0, "g": 255, "b": 98, "cycle": False},
        }
        self._media_files = [
            {
                "serial": 1,
                "cluster": 1,
                "length": 12,
                "action": 255,
                "eye": 1,
                "lights": [{"effect_mode": 1, "brightness": 180, "r": 255, "g": 0, "b": 0, "cycle": False}, {"effect_mode": 1, "brightness": 220, "r": 0, "g": 255, "b": 80, "cycle": False}],
                "enabled": True,
                "name": "Simulated Sound 1.mp3",
            },
            {
                "serial": 2,
                "cluster": 2,
                "length": 9,
                "action": 1,
                "eye": 12,
                "lights": [{"effect_mode": 2, "brightness": 200, "r": 30, "g": 80, "b": 255, "cycle": False}, {"effect_mode": 1, "brightness": 200, "r": 255, "g": 255, "b": 255, "cycle": False}],
                "enabled": False,
                "name": "Simulated Sound 2.mp3",
            },
        ]

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def _record(self, action: str, value: str) -> None:
        self._changed_at = self._now()
        self._events.append(
            {"at": self._changed_at, "action": action, "value": value}
        )

    def _require_connected(self) -> None:
        if not self._connected:
            raise HardwareUnavailable("The simulated Skelly is disconnected")

    def snapshot(self) -> HardwareSnapshot:
        return HardwareSnapshot(
            driver="simulated",
            connected=self._connected,
            live_mode=self._live_mode,
            eye_icon=self._eye_icon,
            eye_index=self._eye_index,
            movement=self._movement,
            movement_armed=self._movement_armed,
            address=None,
            device_name="Simulated Skelly",
            last_error=None,
            last_notification=None,
            changed_at=self._changed_at,
            event_count=len(self._events),
            firmware_version=self._firmware_version,
        )

    async def connect(self, address: str | None = None) -> HardwareSnapshot:
        async with self._lock:
            self._connected = True
            self._record("connection", "connected")
            return self.snapshot()

    async def disconnect(self) -> HardwareSnapshot:
        async with self._lock:
            self._connected = False
            self._live_mode = False
            self._movement = Movement.NONE
            self._record("connection", "disconnected")
            return self.snapshot()

    async def forget(self) -> HardwareSnapshot:
        snapshot = await self.disconnect()
        self._record("connection", "forgotten")
        return snapshot

    def clear_saved_target(self) -> None:
        return None

    def set_saved_target(self, address: str | None) -> None:
        del address

    async def set_eye(self, icon: EyeIcon) -> HardwareSnapshot:
        async with self._lock:
            self._require_connected()
            self._eye_icon = icon
            self._eye_index = EYE_INDEX[icon]
            self._record("eye", icon.value)
            return self.snapshot()

    async def set_eye_index(self, index: int) -> HardwareSnapshot:
        if not 1 <= index <= 18:
            raise ValueError("Eye index must be between 1 and 18")
        async with self._lock:
            self._require_connected()
            self._eye_index = index
            self._record("eye", str(index))
            return self.snapshot()

    async def set_movement(self, movement: Movement) -> HardwareSnapshot:
        async with self._lock:
            self._require_connected()
            self._movement = movement
            self._record("movement", movement.value)
            return self.snapshot()

    async def set_live_mode(self, enabled: bool) -> HardwareSnapshot:
        async with self._lock:
            self._require_connected()
            self._live_mode = enabled
            self._record("live_mode", str(enabled).lower())
            return self.snapshot()

    async def arm_movement(self, enabled: bool) -> HardwareSnapshot:
        async with self._lock:
            self._require_connected()
            self._movement_armed = enabled
            if not enabled:
                self._movement = Movement.NONE
            self._record("movement_armed", str(enabled).lower())
            return self.snapshot()

    async def stop(self) -> HardwareSnapshot:
        async with self._lock:
            self._require_connected()
            self._movement = Movement.NONE
            self._record("movement", Movement.NONE.value)
            return self.snapshot()

    async def probe_movement_bit(
        self, action: int, duration_ms: int
    ) -> HardwareSnapshot:
        del action, duration_ms
        raise HardwareUnavailable(
            "The movement probe requires the real BLE hardware driver"
        )

    def media_status(self) -> dict[str, object]:
        return {
            "available": self._connected,
            "files": list(self._media_files),
            "file_count": len(self._media_files),
            "playing_serial": self._playing_serial,
            "volume": self._volume,
            "lights": self._live_lights,
            "refreshing": False,
            "last_error": None,
        }

    async def refresh_media_files(self, timeout: float = 6.0) -> dict[str, object]:
        del timeout
        self._require_connected()
        return self.media_status()

    async def play_media(self, serial: int, enabled: bool = True) -> dict[str, object]:
        self._require_connected()
        if serial not in {int(item["serial"]) for item in self._media_files}:
            raise HardwareUnavailable(f"Media file #{serial} is not available")
        self._playing_serial = serial if enabled else None
        self._record("media", f"{serial}:{'play' if enabled else 'stop'}")
        return self.media_status()

    async def set_volume(self, volume: int) -> dict[str, object]:
        self._require_connected()
        if not 0 <= volume <= 255:
            raise ValueError("Skelly volume must be between 0 and 255")
        self._volume = volume
        self._record("volume", str(volume))
        return self.media_status()

    async def set_lighting(self, channel: int, brightness: int, red: int, green: int, blue: int, mode: int, cycle: bool = False) -> dict[str, object]:
        self._require_connected()
        target = "head" if channel == 1 else "torso"
        self._live_lights[target] = {
            "effect_mode": mode,
            "brightness": brightness,
            "r": red,
            "g": green,
            "b": blue,
            "cycle": cycle,
        }
        self._record("lighting", f"{channel}:{brightness}:{red},{green},{blue}:{mode}:{cycle}")
        return self.media_status()

    async def edit_media(self, serial: int, action: int, eye: int, head_light: dict[str, object], torso_light: dict[str, object]) -> dict[str, object]:
        self._require_connected()
        item = next((entry for entry in self._media_files if int(entry["serial"]) == serial), None)
        if item is None:
            raise HardwareUnavailable(f"Media file #{serial} is not available")
        item.update(action=action, eye=eye, lights=[dict(torso_light), dict(head_light)])
        return self.media_status()

    async def set_media_enabled(self, serial: int, enabled: bool) -> dict[str, object]:
        self._require_connected()
        item = next((entry for entry in self._media_files if int(entry["serial"]) == serial), None)
        if item is None:
            raise HardwareUnavailable(f"Media file #{serial} is not available")
        item["enabled"] = enabled
        return self.media_status()

    async def upload_media(self, name: str, data: bytes) -> dict[str, object]:
        self._require_connected()
        serial = max((int(item["serial"]) for item in self._media_files), default=0) + 1
        self._media_files.append({"serial": serial, "cluster": serial, "length": len(data), "action": 1, "eye": 1, "name": name, "enabled": True, "lights": [{"effect_mode": 1, "brightness": 200, "r": 255, "g": 0, "b": 0, "cycle": False}, {"effect_mode": 1, "brightness": 200, "r": 0, "g": 255, "b": 0, "cycle": False}]})
        return self.media_status()
