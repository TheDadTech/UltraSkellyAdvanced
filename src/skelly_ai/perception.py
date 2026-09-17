import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from .sensors import SensorLab, SensorUnavailable


def _now() -> str:
    return datetime.now(UTC).isoformat()


Responder = Callable[[str, list[dict[str, str]]], Awaitable[dict[str, object]]]
SessionEnded = Callable[[], Awaitable[None]]
PhaseCue = Callable[[str], Awaitable[None]]
Nagger = Callable[[int, float, float | None], Awaitable[dict[str, object] | None]]
Snapshotter = Callable[[int, int, int], Awaitable[str | None]]
TriggerSettings = Callable[[], dict[str, bool]]


@dataclass(frozen=True, slots=True)
class PerceptionEvent:
    event_id: int
    session_id: int
    turn_number: int
    occurred_at: str
    transcript: str
    voice_level_dbfs: float | None
    person_count: int
    face_count: int
    motion_percent: float
    listening_seconds: float | None
    transcription_seconds: float | None
    transcription_mode: str | None = None
    ai_response: str | None = None
    eye_icon: str | None = None
    movement: str | None = None
    ai_generation_seconds: float | None = None
    brain_provider: str | None = None
    personality: str | None = None
    voice_provider: str | None = None
    brain_fallback_reason: str | None = None
    voice_fallback_reason: str | None = None
    speech_seconds: float | None = None
    voice_generation_seconds: float | None = None
    playback_seconds: float | None = None
    total_response_seconds: float | None = None
    speech_spoken: bool = False
    speech_error: str | None = None
    ai_error: str | None = None
    snapshot_url: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class PerceptionEngine:
    """Opt-in, local visitor conversation loop with camera-based session ending."""

    def __init__(
        self,
        sensors: SensorLab,
        show_locked: Callable[[], bool],
        *,
        responder: Responder | None = None,
        session_ended: SessionEnded | None = None,
        phase_cue: PhaseCue | None = None,
        nagger: Nagger | None = None,
        snapshotter: Snapshotter | None = None,
        trigger_settings: TriggerSettings | None = None,
        camera_interval_seconds: float = 2.5,
        presence_confirmations: int = 2,
        clear_confirmations: int = 4,
        record_seconds: int = 5,
        silence_seconds: float = 1.4,
        listen_retry_seconds: float = 1.0,
        conversation_turn_delay_seconds: float = 1.0,
        departure_motion_threshold: float = 1.0,
        max_events: int = 50,
    ) -> None:
        self._sensors = sensors
        self._show_locked = show_locked
        self._responder = responder
        self._session_ended = session_ended
        self._phase_cue = phase_cue
        self._nagger = nagger
        self._snapshotter = snapshotter
        self._trigger_settings = trigger_settings
        self._camera_interval_seconds = camera_interval_seconds
        self._presence_confirmations = presence_confirmations
        self._clear_confirmations = clear_confirmations
        self._record_seconds = record_seconds
        self._silence_seconds = silence_seconds
        self._listen_retry_seconds = listen_retry_seconds
        self._conversation_turn_delay_seconds = conversation_turn_delay_seconds
        # Retained in status/config for compatibility; consecutive clear frames
        # are now the reliable departure signal and do not require motion.
        self._departure_motion_threshold = departure_motion_threshold
        self._events: deque[PerceptionEvent] = deque(maxlen=max_events)
        self._control_lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._enabled = False
        self._phase = "stopped"
        self._armed = True
        self._session_active = False
        self._session_id = 0
        self._turn_count = 0
        self._history: list[dict[str, str]] = []
        self._presence_streak = 0
        self._clear_streak = 0
        self._last_error: str | None = None
        self._started_at: str | None = None
        self._next_event_id = 1
        self._next_listen_at = 0.0
        self._session_started_at = 0.0
        self._last_nag_at = 0.0
        self._nag_count = 0
        self._trigger_states = {"audio": False, "face": False, "motion": False}

    def status(self) -> dict[str, object]:
        events = [event.to_dict() for event in reversed(self._events)]
        return {
            "enabled": self._enabled,
            "running": bool(self._task and not self._task.done()),
            "phase": self._phase,
            "armed": self._armed,
            "session_active": self._session_active,
            "session_id": self._session_id if self._session_active else None,
            "turn_count": self._turn_count,
            "presence_streak": self._presence_streak,
            "presence_confirmations_required": self._presence_confirmations,
            "clear_streak": self._clear_streak,
            "clear_confirmations_required": self._clear_confirmations,
            "record_seconds": self._record_seconds,
            "event_count": len(self._events),
            "events": events[:10],
            "last_error": self._last_error,
            "started_at": self._started_at,
            "local_only": True,
            "ai_enabled": self._responder is not None,
            "nag_count": self._nag_count,
            "trigger_states": dict(self._trigger_states),
        }

    async def start(self) -> dict[str, object]:
        async with self._control_lock:
            if self._task and not self._task.done():
                return self.status()
            sensor_status = self._sensors.status()
            if not sensor_status["camera"]["available"]:
                raise SensorUnavailable("The camera is unavailable")
            if not sensor_status["microphone"]["available"]:
                raise SensorUnavailable("The microphone is unavailable")
            if not sensor_status["microphone"]["offline_transcription_available"]:
                raise SensorUnavailable("The offline speech model is not installed")

            prepare_transcription = getattr(
                self._sensors, "prepare_transcription", None
            )
            if callable(prepare_transcription):
                self._phase = "preparing_speech"
                await prepare_transcription()

            self._enabled = True
            self._phase = "starting"
            self._reset_session()
            self._last_error = None
            self._started_at = _now()
            self._next_listen_at = 0.0
            self._task = asyncio.create_task(
                self._run(), name="skelly-perception-monitor"
            )
            return self.status()

    async def stop(self) -> dict[str, object]:
        async with self._control_lock:
            self._enabled = False
            task = self._task
            self._task = None
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            if self._session_active:
                await self._notify_session_ended()
            self._reset_session()
            self._phase = "stopped"
            return self.status()

    def clear_events(self) -> dict[str, object]:
        self._events.clear()
        return self.status()

    def _reset_session(self) -> None:
        self._armed = True
        self._session_active = False
        self._turn_count = 0
        self._history.clear()
        self._presence_streak = 0
        self._clear_streak = 0
        self._session_started_at = 0.0
        self._last_nag_at = 0.0
        self._nag_count = 0

    def _begin_session(self) -> None:
        self._session_id += 1
        self._session_active = True
        self._armed = False
        self._turn_count = 0
        self._history.clear()
        self._clear_streak = 0
        self._session_started_at = time.monotonic()
        self._last_nag_at = 0.0
        self._nag_count = 0

    async def _notify_session_ended(self) -> None:
        if self._session_ended is None:
            return
        try:
            await self._session_ended()
        except RuntimeError as exc:
            self._last_error = str(exc)

    async def _notify_phase_cue(self, phase: str) -> None:
        if self._phase_cue is None:
            return
        try:
            await self._phase_cue(phase)
        except RuntimeError as exc:
            self._last_error = str(exc)


    async def _maybe_nag(self) -> None:
        if self._nagger is None or not self._session_active:
            return
        now = time.monotonic()
        try:
            result = await self._nagger(
                self._nag_count,
                max(0.0, now - self._session_started_at),
                (None if self._last_nag_at <= 0 else max(0.0, now - self._last_nag_at)),
            )
        except RuntimeError as exc:
            self._last_error = str(exc)
            return
        if not result or not bool(result.get("performed")):
            return
        self._nag_count += 1
        self._last_nag_at = now
        self._phase = "nagging"

    async def _run(self) -> None:
        try:
            while self._enabled:
                if self._show_locked():
                    if self._session_active:
                        await self._notify_session_ended()
                        self._reset_session()
                    self._phase = "paused_for_show"
                    await asyncio.sleep(self._camera_interval_seconds)
                    continue

                try:
                    self._phase = "scanning"
                    await self._sensors.analyze_camera()
                    sensor_status = self._sensors.status()
                    camera = sensor_status["camera"]
                    trigger_settings = (
                        self._trigger_settings()
                        if self._trigger_settings is not None
                        else {"audio": False, "face": True, "motion": False}
                    )
                    face_active = bool(camera.get("face_count"))
                    motion_active = float(camera.get("motion_percent") or 0.0) >= self._departure_motion_threshold
                    audio_active = False
                    if trigger_settings.get("audio", False):
                        if self._session_active:
                            # Do not add an extra one-second microphone sample before every
                            # conversation turn. Accepted speech below resets departure
                            # confirmation, so Audio can keep an active session alive without
                            # making the green-listening cue feel sluggish.
                            microphone = sensor_status.get("microphone", {})
                            audio_active = bool(
                                isinstance(microphone, dict) and microphone.get("voice_active")
                            )
                        else:
                            try:
                                microphone_sample = await self._sensors.sample_microphone(1)
                                microphone = microphone_sample.get("microphone", {})
                                audio_active = bool(
                                    isinstance(microphone, dict) and microphone.get("voice_active")
                                )
                            except SensorUnavailable:
                                audio_active = False
                    self._trigger_states = {
                        "audio": audio_active,
                        "face": face_active,
                        "motion": motion_active,
                    }
                    presence = bool(
                        (trigger_settings.get("audio", False) and audio_active)
                        or (trigger_settings.get("face", False) and face_active)
                        or (trigger_settings.get("motion", False) and motion_active)
                    )

                    if not presence:
                        self._presence_streak = 0
                        if self._session_active:
                            self._clear_streak += 1
                            self._phase = "confirming_departure"
                            if self._clear_streak >= self._clear_confirmations:
                                await self._notify_session_ended()
                                self._reset_session()
                                self._phase = "rearmed"
                                await asyncio.sleep(self._camera_interval_seconds)
                                continue
                            # Do not stop listening merely because one camera frame
                            # missed a stationary visitor. The active conversation
                            # remains present until departure is fully confirmed.
                        else:
                            self._clear_streak = 0
                            await asyncio.sleep(self._camera_interval_seconds)
                            continue
                    else:
                        self._clear_streak = 0
                    if not self._session_active:
                        if trigger_settings.get("audio", False) and audio_active:
                            self._presence_streak = self._presence_confirmations
                        else:
                            self._presence_streak = min(
                                self._presence_streak + 1,
                                self._presence_confirmations,
                            )
                        if self._presence_streak < self._presence_confirmations:
                            self._phase = "confirming_presence"
                            await asyncio.sleep(self._camera_interval_seconds)
                            continue
                        self._begin_session()
                        self._phase = "visitor_confirmed"

                    if time.monotonic() < self._next_listen_at:
                        self._phase = "waiting_to_listen"
                        await asyncio.sleep(
                            min(
                                self._camera_interval_seconds,
                                max(0.05, self._next_listen_at - time.monotonic()),
                            )
                        )
                        continue

                    self._phase = "listening"
                    await self._notify_phase_cue("listening")
                    adaptive_transcription = getattr(
                        self._sensors,
                        "transcribe_microphone_until_silence",
                        None,
                    )
                    if callable(adaptive_transcription):
                        transcription = await adaptive_transcription(
                            self._record_seconds,
                            self._silence_seconds,
                        )
                    else:
                        transcription = await self._sensors.transcribe_microphone(
                            self._record_seconds
                        )
                    if self._show_locked():
                        self._phase = "paused_for_show"
                        continue

                    microphone = transcription["microphone"]
                    transcript = str(microphone.get("transcript") or "").strip()
                    if not microphone.get("voice_active") or not transcript:
                        self._phase = "no_speech"
                        await self._notify_phase_cue("no_speech")
                        await self._maybe_nag()
                        self._next_listen_at = (
                            time.monotonic() + self._listen_retry_seconds
                        )
                        # A confirmed visitor should get another listening
                        # window promptly.  The slower camera cadence remains
                        # in effect while no session is active.
                        await asyncio.sleep(
                            min(
                                self._camera_interval_seconds,
                                self._listen_retry_seconds,
                            )
                        )
                        continue

                    self._clear_streak = 0
                    snapshot_url: str | None = None
                    if self._snapshotter is not None:
                        try:
                            snapshot_url = await self._snapshotter(
                                self._next_event_id, self._session_id, self._turn_count + 1
                            )
                        except RuntimeError:
                            snapshot_url = None
                    ai_result: dict[str, object] = {}
                    ai_error: str | None = None
                    response_started = time.monotonic()
                    if self._responder is not None:
                        self._phase = "thinking"
                        await self._notify_phase_cue("thinking")
                        started = time.monotonic()
                        try:
                            ai_result = await self._responder(
                                transcript, list(self._history)
                            )
                            ai_result.setdefault(
                                "generation_seconds",
                                round(time.monotonic() - started, 2),
                            )
                        except RuntimeError as exc:
                            ai_error = str(exc)
                            self._last_error = ai_error

                    self._turn_count += 1
                    spoken_response = str(ai_result.get("spoken_response") or "")
                    speech = ai_result.get("speech")
                    speech_result = speech if isinstance(speech, dict) else {}
                    event = PerceptionEvent(
                        event_id=self._next_event_id,
                        session_id=self._session_id,
                        turn_number=self._turn_count,
                        occurred_at=_now(),
                        transcript=transcript,
                        voice_level_dbfs=microphone.get("level_dbfs"),
                        person_count=int(camera.get("person_count") or 0),
                        face_count=int(camera.get("face_count") or 0),
                        motion_percent=float(camera.get("motion_percent") or 0.0),
                        listening_seconds=(
                            float(microphone.get("duration_seconds"))
                            if microphone.get("duration_seconds") is not None
                            else None
                        ),
                        transcription_seconds=microphone.get("transcription_seconds"),
                        transcription_mode=(
                            str(microphone.get("transcription_mode"))
                            if microphone.get("transcription_mode")
                            else None
                        ),
                        ai_response=spoken_response or None,
                        eye_icon=(str(ai_result.get("eye_icon")) if ai_result.get("eye_icon") else None),
                        movement=(str(ai_result.get("movement")) if ai_result.get("movement") else None),
                        ai_generation_seconds=ai_result.get("generation_seconds"),
                        brain_provider=(
                            str(ai_result.get("brain_provider"))
                            if ai_result.get("brain_provider")
                            else None
                        ),
                        personality=(
                            str(ai_result.get("personality"))
                            if ai_result.get("personality")
                            else None
                        ),
                        voice_provider=(
                            str(speech_result.get("voice_provider"))
                            if speech_result.get("voice_provider")
                            else None
                        ),
                        brain_fallback_reason=(
                            str(ai_result.get("brain_fallback_reason"))
                            if ai_result.get("brain_fallback_reason")
                            else None
                        ),
                        voice_fallback_reason=(
                            str(speech_result.get("voice_fallback_reason"))
                            if speech_result.get("voice_fallback_reason")
                            else None
                        ),
                        speech_seconds=(
                            float(speech_result.get("total_speech_seconds"))
                            if speech_result.get("total_speech_seconds") is not None
                            else None
                        ),
                        voice_generation_seconds=(
                            float(speech_result.get("voice_generation_seconds"))
                            if speech_result.get("voice_generation_seconds") is not None
                            else None
                        ),
                        playback_seconds=(
                            float(speech_result.get("elapsed_seconds"))
                            if speech_result.get("elapsed_seconds") is not None
                            else None
                        ),
                        total_response_seconds=round(
                            time.monotonic() - response_started, 2
                        ),
                        speech_spoken=bool(speech_result.get("spoken")),
                        speech_error=(
                            str(speech_result.get("error"))
                            if speech_result.get("error")
                            else None
                        ),
                        ai_error=ai_error,
                        snapshot_url=snapshot_url,
                    )
                    self._next_event_id += 1
                    self._events.append(event)
                    self._history.append({"role": "user", "content": transcript})
                    if spoken_response:
                        self._history.append(
                            {"role": "assistant", "content": spoken_response}
                        )
                    self._history = self._history[-4:]
                    self._phase = "response_ready" if spoken_response else "transcript_captured"
                    if ai_error is None:
                        self._last_error = None
                    self._next_listen_at = (
                        time.monotonic() + self._conversation_turn_delay_seconds
                    )
                    await asyncio.sleep(self._camera_interval_seconds)
                except SensorUnavailable as exc:
                    self._last_error = str(exc)
                    self._phase = "sensor_error"
                    await asyncio.sleep(max(2.0, self._camera_interval_seconds))
        except asyncio.CancelledError:
            raise
        finally:
            if not self._enabled:
                self._phase = "stopped"
