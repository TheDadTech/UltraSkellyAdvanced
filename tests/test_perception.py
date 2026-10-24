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

@pytest.mark.asyncio
async def test_active_session_keeps_listening_during_brief_missed_presence_frames() -> None:
    sensors = FakeSensors([True, True, False, True, False, False, False])
    engine = PerceptionEngine(
        sensors,
        show_locked=lambda: False,
        camera_interval_seconds=0.01,
        presence_confirmations=2,
        clear_confirmations=3,
        record_seconds=5,
        listen_retry_seconds=0.0,
        conversation_turn_delay_seconds=0.0,
    )

    await engine.start()
    await wait_until(lambda: sensors.transcription_calls >= 2)
    stopped = await engine.stop()

    # A single missed camera frame must not suspend an active conversation.
    assert sensors.transcription_calls >= 2
    assert stopped["event_count"] >= 2


@pytest.mark.asyncio
async def test_nagger_runs_after_no_speech_without_ending_session() -> None:
    class QuietSensors(FakeSensors):
        async def transcribe_microphone(self, duration_seconds: int) -> dict[str, object]:
            self.transcription_calls += 1
            status = self.status()
            status["microphone"] = dict(status["microphone"])
            status["microphone"]["voice_active"] = False
            status["microphone"]["transcript"] = ""
            return status

    sensors = QuietSensors([True] * 20)
    nags: list[tuple[int, float, float | None]] = []

    async def nagger(count: int, elapsed: float, since_last: float | None) -> dict[str, object]:
        nags.append((count, elapsed, since_last))
        return {"performed": count == 0}

    engine = PerceptionEngine(
        sensors,
        show_locked=lambda: False,
        nagger=nagger,
        camera_interval_seconds=0.01,
        presence_confirmations=1,
        clear_confirmations=3,
        record_seconds=5,
        listen_retry_seconds=0.01,
    )

    await engine.start()
    await wait_until(lambda: engine.status()["nag_count"] == 1)
    status = engine.status()
    await engine.stop()

    assert status["session_active"] is True
    assert nags
    assert nags[0][0] == 0

@pytest.mark.asyncio
async def test_interaction_snapshot_url_is_attached_to_event() -> None:
    sensors = FakeSensors([True, True, True, True, False, False])
    calls: list[tuple[int, int, int]] = []

    async def snapshotter(event_id: int, session_id: int, turn_number: int) -> str:
        calls.append((event_id, session_id, turn_number))
        return f"/api/perception/snapshots/event-{event_id:06d}-session-{session_id:04d}-turn-{turn_number:03d}.jpg"

    engine = PerceptionEngine(
        sensors,
        show_locked=lambda: False,
        snapshotter=snapshotter,
        camera_interval_seconds=0.01,
        presence_confirmations=2,
        clear_confirmations=2,
        record_seconds=5,
        listen_retry_seconds=0.01,
    )

    await engine.start()
    await wait_until(lambda: engine.status()["event_count"] == 1)
    stopped = await engine.stop()

    assert calls == [(1, 1, 1)]
    assert stopped["events"][0]["snapshot_url"].endswith(
        "event-000001-session-0001-turn-001.jpg"
    )


def test_phantom_this_is_always_junk() -> None:
    from skelly_ai.perception import _is_junk_transcript

    assert _is_junk_transcript("this") is True
    assert _is_junk_transcript("THIS!") is True
    assert _is_junk_transcript("hello") is False


@pytest.mark.asyncio
async def test_monitor_ignores_common_junk_transcript() -> None:
    class JunkSensors(FakeSensors):
        async def transcribe_microphone(self, duration_seconds: int) -> dict[str, object]:
            assert duration_seconds == 5
            self.transcription_calls += 1
            status = self.status()
            status["microphone"] = dict(status["microphone"])
            status["microphone"]["transcript"] = "huh"
            return status

    sensors = JunkSensors([True, True, False, False, False])
    responses: list[str] = []

    async def respond(
        transcript: str, history: list[dict[str, str]]
    ) -> dict[str, object]:
        responses.append(transcript)
        return {"spoken_response": "This should not be spoken."}

    engine = PerceptionEngine(
        sensors,
        show_locked=lambda: False,
        responder=respond,
        camera_interval_seconds=0.01,
        presence_confirmations=2,
        clear_confirmations=2,
        record_seconds=5,
        listen_retry_seconds=0.01,
    )

    await engine.start()
    await wait_until(lambda: sensors.transcription_calls >= 1)
    await asyncio.sleep(0.04)
    stopped = await engine.stop()

    assert responses == []
    assert stopped["event_count"] == 0


@pytest.mark.asyncio
async def test_monitor_ignores_single_word_without_visual_confirmation() -> None:
    class SingleWordSensors(FakeSensors):
        async def transcribe_microphone(self, duration_seconds: int) -> dict[str, object]:
            assert duration_seconds == 5
            self.transcription_calls += 1
            status = self.status()
            status["camera"] = dict(status["camera"])
            status["camera"]["person_count"] = 0
            status["camera"]["face_count"] = 0
            status["microphone"] = dict(status["microphone"])
            status["microphone"]["transcript"] = "this"
            return status

    sensors = SingleWordSensors([False, False, False, False, False], motion_percent=3.5)
    responses: list[str] = []

    async def respond(
        transcript: str, history: list[dict[str, str]]
    ) -> dict[str, object]:
        responses.append(transcript)
        return {"spoken_response": "This should not be spoken."}

    engine = PerceptionEngine(
        sensors,
        show_locked=lambda: False,
        responder=respond,
        trigger_settings=lambda: {"audio": False, "face": False, "motion": True},
        camera_interval_seconds=0.01,
        presence_confirmations=2,
        clear_confirmations=2,
        record_seconds=5,
        listen_retry_seconds=0.01,
    )

    await engine.start()
    await wait_until(lambda: sensors.transcription_calls >= 1)
    await asyncio.sleep(0.04)
    stopped = await engine.stop()

    assert responses == []
    assert stopped["event_count"] == 0


@pytest.mark.asyncio
async def test_monitor_accepts_single_word_with_visual_confirmation() -> None:
    class SingleWordSensors(FakeSensors):
        async def transcribe_microphone(self, duration_seconds: int) -> dict[str, object]:
            assert duration_seconds == 5
            self.transcription_calls += 1
            status = self.status()
            status["microphone"] = dict(status["microphone"])
            status["microphone"]["transcript"] = "hello"
            return status

    sensors = SingleWordSensors([True, True, False, False, False])
    responses: list[str] = []

    async def respond(
        transcript: str, history: list[dict[str, str]]
    ) -> dict[str, object]:
        responses.append(transcript)
        return {"spoken_response": "Hello."}

    engine = PerceptionEngine(
        sensors,
        show_locked=lambda: False,
        responder=respond,
        camera_interval_seconds=0.01,
        presence_confirmations=2,
        clear_confirmations=2,
        record_seconds=5,
        listen_retry_seconds=0.01,
    )

    await engine.start()
    await wait_until(lambda: engine.status()["event_count"] >= 1)
    stopped = await engine.stop()

    assert responses[0] == "hello"
    assert stopped["events"][0]["transcript"] == "hello"


@pytest.mark.asyncio
async def test_visual_session_uses_welcome_once_before_first_listen() -> None:
    sensors = FakeSensors([True, True, True, True, False, False, False, False])
    welcomes = 0

    async def welcome():
        nonlocal welcomes
        welcomes += 1
        return {"performed": True}

    engine = PerceptionEngine(
        sensors,
        show_locked=lambda: False,
        welcomer=welcome,
        camera_interval_seconds=0.01,
        conversation_turn_delay_seconds=0.005,
        presence_confirmations=2,
        clear_confirmations=2,
        record_seconds=5,
        listen_retry_seconds=0.01,
    )
    await engine.start()
    await wait_until(lambda: sensors.transcription_calls >= 1)
    await engine.stop()
    assert welcomes == 1


def test_active_conversation_turn_delay_defaults_under_half_second() -> None:
    import inspect
    signature = inspect.signature(PerceptionEngine)
    assert signature.parameters["conversation_turn_delay_seconds"].default <= 0.5


class BackgroundAudioSensors(FakeSensors):
    def __init__(self, transcript=''):
        super().__init__([],motion_percent=0.0)
        self.present=True
        self.noisy=True
        self.transcript=transcript
    async def analyze_camera(self):
        self.camera_calls+=1
        self._current_presence=self.present
        return b'jpeg'
    async def sample_microphone(self,duration_seconds):
        return self.status()
    def status(self):
        data=super().status()
        data['microphone']['voice_active']=self.noisy
        data['microphone']['transcript']=self.transcript
        return data


@pytest.mark.asyncio
@pytest.mark.parametrize('background_transcript',['','television is talking in the room'])
async def test_background_audio_does_not_hold_departed_session_or_reuse_lure_count(background_transcript):
    sensors=BackgroundAudioSensors()
    lures=[];ended=[]
    async def nag(count,elapsed,since):
        if sensors.present and count<2:
            lures.append(count)
            return {'performed':True}
        return None
    async def session_ended():ended.append(True)
    engine=PerceptionEngine(sensors,show_locked=lambda:False,nagger=nag,session_ended=session_ended,
        trigger_settings=lambda:{'audio':True,'face':True,'motion':True},
        camera_interval_seconds=0.005,presence_confirmations=2,clear_confirmations=4,
        listen_retry_seconds=0.005,conversation_turn_delay_seconds=0.005)
    try:
        await engine.start()
        await wait_until(lambda:engine.status()['nag_count']==2)
        first_id=engine.status()['session_id']
        sensors.transcript=background_transcript
        sensors.present=False
        await wait_until(lambda:not engine.status()['session_active'])
        assert engine.status()['nag_count']==0 and ended==[True]
        assert engine.status()['audio_rearm_pending'] is True
        # Continuous noise must not immediately manufacture another visitor.
        calls=sensors.camera_calls
        await wait_until(lambda:sensors.camera_calls>=calls+5)
        assert not engine.status()['session_active']
        lures.clear();sensors.transcript="";sensors.present=True
        await wait_until(lambda:engine.status()['session_active'] and bool(lures))
        assert engine.status()['session_id']==first_id+1
        assert lures[0]==0
    finally:await engine.stop()


@pytest.mark.asyncio
async def test_visual_confirmation_still_tolerates_a_brief_missed_frame():
    sensors=BackgroundAudioSensors('hello visitor')
    engine=PerceptionEngine(sensors,show_locked=lambda:False,
        trigger_settings=lambda:{'audio':True,'face':True,'motion':False},
        camera_interval_seconds=0.005,presence_confirmations=2,clear_confirmations=4,
        listen_retry_seconds=0.005,conversation_turn_delay_seconds=0.005)
    try:
        await engine.start();await wait_until(lambda:engine.status()['session_active'])
        session=engine.status()['session_id'];sensors.present=False
        await wait_until(lambda:engine.status()['clear_streak']>=1)
        sensors.present=True
        await wait_until(lambda:engine.status()['clear_streak']==0)
        assert engine.status()['session_id']==session
    finally:await engine.stop()


@pytest.mark.asyncio
async def test_audio_only_noise_rearms_after_quiet_and_fresh_audio_can_start_next_visit():
    sensors=BackgroundAudioSensors();sensors.present=False
    engine=PerceptionEngine(sensors,show_locked=lambda:False,
        trigger_settings=lambda:{'audio':True,'face':False,'motion':False},
        camera_interval_seconds=0.005,presence_confirmations=2,clear_confirmations=4,
        listen_retry_seconds=0.005)
    try:
        await engine.start();await wait_until(lambda:engine.status()['session_active'])
        first=engine.status()['session_id']
        await wait_until(lambda:engine.status()['audio_rearm_pending'])
        assert not engine.status()['session_active']
        sensors.noisy=False
        await wait_until(lambda:not engine.status()['audio_rearm_pending'])
        sensors.noisy=True
        await wait_until(lambda:engine.status()['session_active'])
        assert engine.status()['session_id']==first+1
    finally:await engine.stop()


@pytest.mark.asyncio
async def test_audio_only_conversation_continues_on_accepted_speech_not_sound_level():
    sensors=BackgroundAudioSensors('a visitor is speaking');sensors.present=False
    engine=PerceptionEngine(sensors,show_locked=lambda:False,
        trigger_settings=lambda:{'audio':True,'face':False,'motion':False},
        camera_interval_seconds=0.005,presence_confirmations=2,clear_confirmations=4,
        listen_retry_seconds=0.005,conversation_turn_delay_seconds=0.005)
    try:
        await engine.start();await wait_until(lambda:engine.status()['session_active'])
        session=engine.status()['session_id'];calls=sensors.camera_calls
        await wait_until(lambda:sensors.camera_calls>=calls+8)
        assert engine.status()['session_active'] and engine.status()['session_id']==session
        sensors.transcript=''
        await wait_until(lambda:not engine.status()['session_active'])
        assert engine.status()['nag_count']==0
    finally:await engine.stop()
