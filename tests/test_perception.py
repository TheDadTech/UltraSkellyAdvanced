import asyncio

import pytest

from skelly_ai.perception import PerceptionEngine


class FakeSensors:
    def __init__(self, presence: list[bool], motion_percent: float = 3.5) -> None:
        self._presence = presence
        self._motion_percent = motion_percent
        self._current_presence = False
        self.camera_calls = 0
        self.transcription_calls = 0
        self.last_silence_seconds: float | None = None

    def status(self) -> dict[str, object]:
        return {
            "local_only": True,
            "camera": {
                "available": True,
                "presence_detected": self._current_presence,
                "person_count": 1 if self._current_presence else 0,
                "face_count": 1 if self._current_presence else 0,
                "motion_percent": self._motion_percent,
            },
            "microphone": {
                "available": True,
                "offline_transcription_available": True,
                "voice_active": True,
                "level_dbfs": -21.0,
                "transcript": "welcome to the graveyard",
                "transcription_seconds": 0.3,
            },
        }

    async def analyze_camera(self) -> bytes:
        self.camera_calls += 1
        if self._presence:
            self._current_presence = self._presence.pop(0)
        return b"jpeg"

    async def transcribe_microphone(self, duration_seconds: int) -> dict[str, object]:
        assert duration_seconds == 5
        self.transcription_calls += 1
        return self.status()

    async def transcribe_microphone_until_silence(
        self, max_duration_seconds: int, silence_seconds: float
    ) -> dict[str, object]:
        self.last_silence_seconds = silence_seconds
        return await self.transcribe_microphone(max_duration_seconds)


async def wait_until(predicate, timeout: float = 1.0) -> None:
    async def poll() -> None:
        while not predicate():
            await asyncio.sleep(0.005)

    await asyncio.wait_for(poll(), timeout=timeout)


@pytest.mark.asyncio
async def test_monitor_confirms_presence_captures_turn_and_rearms_after_clear() -> None:
    sensors = FakeSensors([True, True, False, False, False])
    engine = PerceptionEngine(
        sensors,
        show_locked=lambda: False,
        camera_interval_seconds=0.01,
        presence_confirmations=2,
        clear_confirmations=2,
        record_seconds=5,
        listen_retry_seconds=0.01,
    )

    await engine.start()
    await wait_until(
        lambda: engine.status()["event_count"] == 1 and engine.status()["armed"]
    )
    stopped = await engine.stop()

    assert sensors.transcription_calls == 1
    assert sensors.last_silence_seconds == 1.4
    assert stopped["running"] is False
    assert stopped["events"][0]["transcript"] == "welcome to the graveyard"
    assert stopped["events"][0]["face_count"] == 1


@pytest.mark.asyncio
async def test_monitor_does_not_use_sensors_while_show_is_locked() -> None:
    sensors = FakeSensors([True, True, True])
    show_state = {"locked": True}
    engine = PerceptionEngine(
        sensors,
        show_locked=lambda: show_state["locked"],
        camera_interval_seconds=0.01,
        presence_confirmations=2,
        record_seconds=5,
    )

    await engine.start()
    await asyncio.sleep(0.04)
    assert sensors.camera_calls == 0
    assert engine.status()["phase"] == "paused_for_show"

    show_state["locked"] = False
    await wait_until(lambda: engine.status()["event_count"] == 1)
    await engine.stop()

    assert sensors.transcription_calls == 1


@pytest.mark.asyncio
async def test_consecutive_clear_frames_end_session_without_motion_requirement() -> None:
    sensors = FakeSensors([True, True] + [False] * 20, motion_percent=0.0)
    engine = PerceptionEngine(
        sensors,
        show_locked=lambda: False,
        camera_interval_seconds=0.01,
        presence_confirmations=2,
        clear_confirmations=2,
        record_seconds=5,
    )

    await engine.start()
    await wait_until(lambda: engine.status()["event_count"] == 1)
    await wait_until(lambda: engine.status()["armed"] is True)

    assert engine.status()["session_active"] is False
    assert sensors.transcription_calls == 1

    stopped = await engine.stop()
    assert stopped["armed"] is True
    assert stopped["phase"] == "stopped"


@pytest.mark.asyncio
async def test_monitor_supports_multiple_turns_while_visitor_remains() -> None:
    sensors = FakeSensors([True, True, True, False, False])
    observed_history: list[list[dict[str, str]]] = []

    async def respond(
        transcript: str, history: list[dict[str, str]]
    ) -> dict[str, object]:
        assert transcript == "welcome to the graveyard"
        observed_history.append(history)
        return {
            "spoken_response": "Welcome, brave visitor!",
            "eye_icon": "normal",
            "movement": "head_only",
        }

    engine = PerceptionEngine(
        sensors,
        show_locked=lambda: False,
        responder=respond,
        camera_interval_seconds=0.01,
        presence_confirmations=2,
        clear_confirmations=2,
        record_seconds=5,
        listen_retry_seconds=0.01,
        conversation_turn_delay_seconds=0.0,
    )

    await engine.start()
    await wait_until(lambda: engine.status()["event_count"] >= 2)
    stopped = await engine.stop()

    assert sensors.transcription_calls >= 2
    assert stopped["events"][0]["ai_response"] == "Welcome, brave visitor!"
    assert stopped["events"][0]["turn_number"] >= 2
    assert observed_history[0] == []
    assert observed_history[1][-1] == {
        "role": "assistant",
        "content": "Welcome, brave visitor!",
    }


@pytest.mark.asyncio
async def test_monitor_reports_that_automatic_response_was_spoken() -> None:
    sensors = FakeSensors([True, True, False, False])
    phases: list[str] = []

    async def respond(
        transcript: str, history: list[dict[str, str]]
    ) -> dict[str, object]:
        return {
            "spoken_response": "I see you, brave visitor!",
            "eye_icon": "normal",
            "movement": "head_only",
            "generation_seconds": 0.4,
            "speech": {
                "spoken": True,
                "engine": "espeak-ng",
                "elevenlabs_used": False,
            },
        }

    async def phase_cue(phase: str) -> None:
        phases.append(phase)

    engine = PerceptionEngine(
        sensors,
        show_locked=lambda: False,
        responder=respond,
        phase_cue=phase_cue,
        camera_interval_seconds=0.01,
        presence_confirmations=2,
        clear_confirmations=2,
        record_seconds=5,
    )

    await engine.start()
    await wait_until(lambda: engine.status()["event_count"] == 1)
    stopped = await engine.stop()

    assert stopped["events"][0]["speech_spoken"] is True
    assert stopped["events"][0]["speech_error"] is None
    assert "listening" in phases
    assert "thinking" in phases
