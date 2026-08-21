import math
import tempfile
from io import BytesIO
import wave
from array import array
from pathlib import Path

import pytest

from skelly_ai.speech import LocalSpeech, SpeechUnavailable


class FakeJaw:
    def __init__(self, *, armed: bool) -> None:
        self.armed = armed
        self.positions: list[int] = []

    def snapshot(self):
        return self

    async def set_position(self, *, jaw=None, **kwargs):
        assert jaw is not None
        self.positions.append(jaw)
        return self


def make_test_wav(levels: list[float], rate: int = 1000) -> BytesIO:
    samples = array("h")
    for level in levels:
        for index in range(80):
            samples.append(round(level * 12000 * math.sin(index / 5)))
    output = BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(samples.tobytes())
    output.seek(0)
    return output


def test_jaw_envelope_uses_hysteresis_and_reports_duration() -> None:
    wav = make_test_wav([0, 1.0, 0.12, 0, 0.8])
    speech = LocalSpeech(frame_seconds=0.08, jaw_activity_percent=100)

    envelope, duration = speech._jaw_envelope(wav)

    assert envelope == [False, True, True, False, True]
    assert duration == pytest.approx(0.4)


def test_calm_jaw_activity_suppresses_quick_reopening() -> None:
    wav = make_test_wav([0, 1.0, 0.12, 0, 0.8])
    speech = LocalSpeech(frame_seconds=0.08, jaw_activity_percent=35)

    envelope, _ = speech._jaw_envelope(wav)

    assert envelope == [False, True, True, False, False]


def test_speaker_wake_signal_adds_quiet_audio_before_the_first_word() -> None:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temporary:
        wav_path = Path(temporary.name)
    try:
        wav_path.write_bytes(make_test_wav([1.0], rate=1000).getvalue())
        speech = LocalSpeech(speaker_preroll_seconds=0.65)

        speech._prepend_wake_signal(wav_path)

        with wave.open(str(wav_path), "rb") as wav:
            assert wav.getnframes() == 730
            wake_signal = wav.readframes(650)
            first_audio = wav.readframes(80)
        wake_samples = array("h")
        wake_samples.frombytes(wake_signal)
        speech_samples = array("h")
        speech_samples.frombytes(first_audio)
        assert any(wake_samples)
        assert max(map(abs, wake_samples)) < max(map(abs, speech_samples))
        assert any(first_audio)
    finally:
        wav_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_play_skips_jaw_when_dac_is_disarmed(monkeypatch) -> None:
    class FakeProcess:
        returncode = 0

        async def communicate(self):
            return b"", b""

    async def fake_subprocess(*args, **kwargs):
        return FakeProcess()

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_subprocess)
    speech = LocalSpeech(bluetooth_delay_seconds=0, frame_seconds=0.001)
    jaw = FakeJaw(armed=False)

    result = await speech._play(Path("unused.wav"), [True, False], 0.2, jaw)

    assert result["spoken"] is True
    assert result["jaw_animated"] is False
    assert jaw.positions == []


@pytest.mark.asyncio
async def test_play_always_closes_an_armed_jaw(monkeypatch) -> None:
    class FakeProcess:
        returncode = 0

        async def communicate(self):
            return b"", b""

    async def fake_subprocess(*args, **kwargs):
        return FakeProcess()

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_subprocess)
    speech = LocalSpeech(bluetooth_delay_seconds=0, frame_seconds=0.001)
    jaw = FakeJaw(armed=True)

    result = await speech._play(Path("unused.wav"), [True], 0.1, jaw)

    assert result["jaw_animated"] is True
    assert jaw.positions == [255, 0]


@pytest.mark.asyncio
async def test_zero_jaw_activity_keeps_an_armed_jaw_closed(monkeypatch) -> None:
    class FakeProcess:
        returncode = 0

        async def communicate(self):
            return b"", b""

    async def fake_subprocess(*args, **kwargs):
        return FakeProcess()

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_subprocess)
    speech = LocalSpeech(
        bluetooth_delay_seconds=0,
        frame_seconds=0.001,
        jaw_activity_percent=0,
    )
    jaw = FakeJaw(armed=True)

    result = await speech._play(Path("unused.wav"), [True, True], 0.1, jaw)

    assert result["jaw_animated"] is False
    assert jaw.positions == [0]


@pytest.mark.asyncio
async def test_speak_reports_missing_local_tools(monkeypatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _: None)
    speech = LocalSpeech()

    with pytest.raises(SpeechUnavailable, match="espeak-ng is not installed"):
        await speech.speak("Hello", FakeJaw(armed=False))


@pytest.mark.asyncio
async def test_streamed_pcm_starts_player_before_audio_finishes_and_closes_jaw(
    monkeypatch,
) -> None:
    class FakeStdin:
        def __init__(self) -> None:
            self.writes: list[bytes] = []
            self.closed = False

        def write(self, data: bytes) -> None:
            self.writes.append(data)

        async def drain(self) -> None:
            return None

        def close(self) -> None:
            self.closed = True

    class FakeStderr:
        async def read(self) -> bytes:
            return b""

    class FakeProcess:
        def __init__(self) -> None:
            self.returncode = None
            self.stdin = FakeStdin()
            self.stderr = FakeStderr()

        async def wait(self) -> int:
            self.returncode = 0
            return 0

        def terminate(self) -> None:
            self.returncode = 0

    process = FakeProcess()

    async def fake_subprocess(*args, **kwargs):
        assert "--raw" in args
        assert args[-1] == "-"
        return process

    async def audio_chunks():
        yield array("h", [0] * 8 + [9000] * 8).tobytes()
        yield array("h", [0] * 16).tobytes()

    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/pw-play")
    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_subprocess)
    speech = LocalSpeech(
        bluetooth_delay_seconds=0,
        speaker_preroll_seconds=0,
        frame_seconds=0.001,
        jaw_activity_percent=100,
    )
    jaw = FakeJaw(armed=True)

    result = await speech.play_pcm_stream(
        audio_chunks(), jaw, engine="elevenlabs:eleven_v3", sample_rate=1000
    )

    assert process.stdin.closed is True
    assert b"".join(process.stdin.writes)
    assert result["streamed"] is True
    assert result["first_audio_seconds"] is not None
    assert jaw.positions.count(255) >= 2
    assert jaw.positions.count(0) >= 2
    assert jaw.positions[-1] == 0
