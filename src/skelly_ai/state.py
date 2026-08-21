import asyncio
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum


class Mode(StrEnum):
    STARTING = "starting"
    IDLE = "idle"
    INTERACTIVE = "interactive"
    SHOW_LOCKED = "show_locked"
    OFFLINE = "offline"
    FAULT = "fault"


class InvalidTransition(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class StateSnapshot:
    mode: Mode
    changed_at: str
    show_name: str | None
    fault: str | None

    def to_dict(self) -> dict[str, str | None]:
        result = asdict(self)
        result["mode"] = self.mode.value
        return result


class StateController:
    """Owns the local safety mode and serializes all mode changes."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._mode = Mode.STARTING
        self._changed_at = self._now()
        self._show_name: str | None = None
        self._fault: str | None = None
        self._mode_before_show = Mode.IDLE

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def snapshot(self) -> StateSnapshot:
        return StateSnapshot(
            mode=self._mode,
            changed_at=self._changed_at,
            show_name=self._show_name,
            fault=self._fault,
        )

    def _set_mode(self, mode: Mode) -> None:
        self._mode = mode
        self._changed_at = self._now()

    async def ready(self) -> StateSnapshot:
        async with self._lock:
            if self._mode == Mode.STARTING:
                self._set_mode(Mode.IDLE)
            return self.snapshot()

    async def set_idle(self) -> StateSnapshot:
        async with self._lock:
            if self._mode == Mode.SHOW_LOCKED:
                raise InvalidTransition("A running show must be ended before entering idle mode")
            self._fault = None
            self._set_mode(Mode.IDLE)
            return self.snapshot()

    async def set_interactive(self) -> StateSnapshot:
        async with self._lock:
            if self._mode == Mode.SHOW_LOCKED:
                raise InvalidTransition(
                    "Interactive mode is unavailable while an FPP show is active"
                )
            if self._mode == Mode.FAULT:
                raise InvalidTransition("Clear the fault before entering interactive mode")
            self._set_mode(Mode.INTERACTIVE)
            return self.snapshot()

    async def begin_show(self, show_name: str | None = None) -> StateSnapshot:
        async with self._lock:
            if self._mode == Mode.SHOW_LOCKED:
                if show_name and show_name != self._show_name:
                    raise InvalidTransition("Another show is already active")
                return self.snapshot()
            self._mode_before_show = (
                self._mode if self._mode in {Mode.IDLE, Mode.INTERACTIVE} else Mode.IDLE
            )
            self._show_name = show_name
            self._fault = None
            self._set_mode(Mode.SHOW_LOCKED)
            return self.snapshot()

    async def end_show(self) -> StateSnapshot:
        async with self._lock:
            if self._mode != Mode.SHOW_LOCKED:
                return self.snapshot()
            self._show_name = None
            self._set_mode(self._mode_before_show)
            return self.snapshot()

    async def set_fault(self, message: str) -> StateSnapshot:
        async with self._lock:
            self._show_name = None
            self._fault = message
            self._set_mode(Mode.FAULT)
            return self.snapshot()

