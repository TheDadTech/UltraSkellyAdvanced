import asyncio
import math
import os
import shutil
import sys
import tempfile
import wave
from array import array
from pathlib import Path
from collections.abc import AsyncIterable
from typing import BinaryIO, Protocol

from .sacn import DacUnavailable, SacnDacController


class SpeechUnavailable(RuntimeError):
    """Raised when local speech cannot be generated or played."""


class JawController(Protocol):
    def snapshot(self): ...

    async def set_position(self, *, jaw: int | None = None, **kwargs): ...


class LocalSpeech:
    """Generate local eSpeak audio and optionally animate the DAC jaw."""

    def __init__(
        self,
        *,
        voice: str = "en-us+m3",
        speed: int = 145,
        pitch: int = 30,
        word_gap: int = 5,
        bluetooth_delay_seconds: float = 0.2,
        speaker_preroll_seconds: float = 0.65,
        jaw_activity_percent: int = 35,
        frame_seconds: float = 0.08,
        espeak_command: str = "espeak-ng",
        player_command: str = "pw-play",
    ) -> None:
        self._voice = voice
        self._speed = speed
        self._pitch = pitch
        self._word_gap = word_gap
        self._bluetooth_delay_seconds = bluetooth_delay_seconds
        self._speaker_preroll_seconds = speaker_preroll_seconds
        self._jaw_activity_percent = max(0, min(100, jaw_activity_percent))
        self._frame_seconds = frame_seconds
        self._espeak_command = espeak_command
        self._player_command = player_command
        self._lock = asyncio.Lock()

    def status(self) -> dict[str, object]:
        generator_available = shutil.which(self._espeak_command) is not None
        player_available = shutil.which(self._player_command) is not None
        return {
            "available": generator_available and player_available,
            "generator": self._espeak_command,
            "generator_available": generator_available,
            "player": self._player_command,
            "player_available": player_available,
            "voice": self._voice,
            "speed": self._speed,
            "pitch": self._pitch,
            "word_gap": self._word_gap,
            "bluetooth_delay_seconds": self._bluetooth_delay_seconds,
            "speaker_preroll_seconds": self._speaker_preroll_seconds,
            "jaw_activity_percent": self._jaw_activity_percent,
            "local_only": True,
        }

    def configure(
        self,
        *,
        voice: str,
        speed: int,
        pitch: int,
        word_gap: int,
        speaker_preroll_seconds: float,
        jaw_activity_percent: int,
    ) -> None:
        self._voice = voice
        self._speed = speed
        self._pitch = pitch
        self._word_gap = word_gap
        self._speaker_preroll_seconds = max(0.0, speaker_preroll_seconds)
        self._jaw_activity_percent = max(0, min(100, jaw_activity_percent))

    async def speak(
        self,
        text: str,
        jaw: JawController,
    ) -> dict[str, object]:
        clean_text = " ".join(text.split())
        if not clean_text:
            raise SpeechUnavailable("The local speech response is empty")

        status = self.status()
        if not status["generator_available"]:
            raise SpeechUnavailable("espeak-ng is not installed on this Pi")
        if not status["player_available"]:
            raise SpeechUnavailable("pw-play is not installed on this Pi")

        async with self._lock:
            descriptor, filename = tempfile.mkstemp(
                prefix="skelly-speech-", suffix=".wav"
            )
            os.close(descriptor)
            wav_path = Path(filename)
            try:
                await self._generate(clean_text, wav_path)
                self._prepend_wake_signal(wav_path)
                envelope, duration = self._jaw_envelope(wav_path)
                return await self._play(
                    wav_path,
                    envelope,
                    duration,
                    jaw,
                    engine="espeak-ng",
                    cloud_used=False,
                )
            finally:
                wav_path.unlink(missing_ok=True)

    async def play_wav_bytes(
        self,
        audio: bytes,
        jaw: JawController,
        *,
        engine: str,
        cloud_used: bool,
    ) -> dict[str, object]:
        if not audio:
            raise SpeechUnavailable("The voice provider returned empty audio")
        async with self._lock:
            descriptor, filename = tempfile.mkstemp(
                prefix="skelly-cloud-speech-", suffix=".wav"
            )
            os.close(descriptor)
            wav_path = Path(filename)
            try:
                wav_path.write_bytes(audio)
                self._prepend_wake_signal(wav_path)
                envelope, duration = self._jaw_envelope(wav_path)
                return await self._play(
                    wav_path,
                    envelope,
                    duration,
                    jaw,
                    engine=engine,
                    cloud_used=cloud_used,
                )
            except (OSError, wave.Error) as exc:
                raise SpeechUnavailable("The voice provider returned invalid WAV audio") from exc
            finally:
                wav_path.unlink(missing_ok=True)

    async def play_pcm_stream(
        self,
        audio_stream: AsyncIterable[bytes],
        jaw: JawController,
        *,
        engine: str,
        sample_rate: int = 22050,
        volume_percent: int = 85,
    ) -> dict[str, object]:
        """Play raw mono PCM while it is still arriving from a voice provider."""

        if shutil.which(self._player_command) is None:
            raise SpeechUnavailable("pw-play is not installed on this Pi")
        if sample_rate <= 0:
            raise SpeechUnavailable("The streamed voice sample rate is invalid")

        async with self._lock:
            try:
                process = await asyncio.create_subprocess_exec(
                    self._player_command,
                    "--raw",
                    "--rate",
                    str(sample_rate),
                    "--channels",
                    "1",
                    "--format",
                    "s16",
                    "-",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
            except OSError as exc:
                raise SpeechUnavailable("pw-play could not start streamed speech") from exc
            if process.stdin is None:
                process.terminate()
                await process.wait()
                raise SpeechUnavailable("pw-play did not open its audio input")

            loop = asyncio.get_running_loop()
            started = loop.time()
            frame_samples = max(1, round(sample_rate * self._frame_seconds))
            frame_bytes = frame_samples * 2
            preroll = self._speaker_wake_pcm(sample_rate, 2, 1)
            pending = bytearray()
            audio_bytes = 0
            first_audio_seconds: float | None = None
            jaw_animated = bool(
                jaw.snapshot().armed and self._jaw_activity_percent > 0
            )
            jaw_state: dict[str, object] = {
                "last": False,
                "error": None,
                "peak": 0.0,
                "analysis_opened": False,
                "open_frames": 0,
                "closed_frames": 1,
            }
            if jaw.snapshot().armed and self._jaw_activity_percent == 0:
                try:
                    await jaw.set_position(jaw=0)
                except DacUnavailable as exc:
                    jaw_state["error"] = str(exc)
            envelope_queue: asyncio.Queue[bool | None] = asyncio.Queue()

            async def animate_jaw() -> None:
                if not jaw_animated:
                    return
                await asyncio.sleep(self._bluetooth_delay_seconds)
                timeline_start = loop.time()
                index = 0
                while True:
                    opened = await envelope_queue.get()
                    if opened is None:
                        return
                    target_time = timeline_start + index * self._frame_seconds
                    index += 1
                    await asyncio.sleep(max(0.0, target_time - loop.time()))
                    if opened == jaw_state["last"]:
                        continue
                    try:
                        await jaw.set_position(jaw=255 if opened else 0)
                        jaw_state["last"] = opened
                    except DacUnavailable as exc:
                        jaw_state["error"] = str(exc)
                        return

            def scale_pcm(chunk: bytes) -> bytes:
                volume = max(0.1, min(1.0, volume_percent / 100))
                if volume >= 1.0:
                    return chunk
                samples = array("h")
                samples.frombytes(chunk)
                if sys.byteorder == "big":
                    samples.byteswap()
                for index, sample in enumerate(samples):
                    samples[index] = round(sample * volume)
                if sys.byteorder == "big":
                    samples.byteswap()
                return samples.tobytes()

            async def queue_envelope(chunk: bytes) -> None:
                pending.extend(chunk)
                while len(pending) >= frame_bytes:
                    frame = bytes(pending[:frame_bytes])
                    del pending[:frame_bytes]
                    samples = array("h")
                    samples.frombytes(frame)
                    if sys.byteorder == "big":
                        samples.byteswap()
                    rms = math.sqrt(
                        sum(sample * sample for sample in samples) / len(samples)
                    )
                    peak = max(float(jaw_state["peak"]) * 0.94, rms)
                    jaw_state["peak"] = peak
                    opened = bool(jaw_state["analysis_opened"])
                    minimum_closed_frames = max(
                        1,
                        round(8 - 7 * self._jaw_activity_percent / 100),
                    )
                    open_ratio = 0.34 - 0.0012 * self._jaw_activity_percent
                    if opened:
                        jaw_state["open_frames"] = int(jaw_state["open_frames"]) + 1
                        jaw_state["closed_frames"] = 0
                        # Speech audio is often continuously loud. Close on a
                        # meaningful valley, or after 240 ms, so the jaw cannot
                        # remain pinned open through an entire phrase.
                        if (
                            rms <= max(500.0, peak * 0.18)
                            or int(jaw_state["open_frames"]) >= 3
                        ):
                            opened = False
                            jaw_state["open_frames"] = 0
                            jaw_state["closed_frames"] = 1
                    else:
                        jaw_state["closed_frames"] = int(jaw_state["closed_frames"]) + 1
                        jaw_state["open_frames"] = 0
                        if (
                            int(jaw_state["closed_frames"]) >= minimum_closed_frames
                            and rms >= max(700.0, peak * open_ratio)
                        ):
                            opened = True
                            jaw_state["open_frames"] = 1
                            jaw_state["closed_frames"] = 0
                    jaw_state["analysis_opened"] = opened
                    await envelope_queue.put(opened)

            jaw_task = asyncio.create_task(animate_jaw())
            carry = b""
            try:
                if preroll:
                    process.stdin.write(preroll)
                    await process.stdin.drain()
                    await queue_envelope(preroll)
                async for incoming in audio_stream:
                    if first_audio_seconds is None:
                        first_audio_seconds = round(loop.time() - started, 2)
                    combined = carry + incoming
                    even_length = len(combined) - (len(combined) % 2)
                    carry = combined[even_length:]
                    if not even_length:
                        continue
                    pcm = scale_pcm(combined[:even_length])
                    audio_bytes += len(pcm)
                    process.stdin.write(pcm)
                    await process.stdin.drain()
                    await queue_envelope(pcm)
                if carry:
                    raise SpeechUnavailable("ElevenLabs returned invalid PCM audio")
                if audio_bytes == 0:
                    raise SpeechUnavailable("The voice provider returned empty audio")
                if pending:
                    await queue_envelope(b"\x00" * (frame_bytes - len(pending)))
                process.stdin.close()
                await envelope_queue.put(None)
                await jaw_task
                await process.wait()
                stderr = await process.stderr.read() if process.stderr else b""
                if process.returncode != 0:
                    detail = stderr.decode(errors="replace").strip()
                    raise SpeechUnavailable(
                        detail or "pw-play could not play streamed speech"
                    )
            finally:
                if not jaw_task.done():
                    await envelope_queue.put(None)
                    await jaw_task
                if process.returncode is None:
                    process.terminate()
                    await process.wait()
                if jaw_state["last"]:
                    try:
                        await jaw.set_position(jaw=0)
                    except DacUnavailable as exc:
                        jaw_state["error"] = jaw_state["error"] or str(exc)

            duration = (
                audio_bytes + len(preroll)
            ) / float(sample_rate * 2)
            return {
                "spoken": True,
                "engine": engine,
                "duration_seconds": round(duration, 2),
                "elapsed_seconds": round(loop.time() - started, 2),
                "first_audio_seconds": first_audio_seconds,
                "streamed": True,
                "speaker_preroll_ms": round(self._speaker_preroll_seconds * 1000),
                "jaw_animated": jaw_animated,
                "jaw_activity_percent": self._jaw_activity_percent,
                "jaw_error": jaw_state["error"],
                "cloud_used": True,
                "elevenlabs_used": engine.startswith("elevenlabs"),
            }

    def _prepend_wake_signal(self, wav_path: Path) -> None:
        if self._speaker_preroll_seconds <= 0:
            return
        try:
            with wave.open(str(wav_path), "rb") as source:
                channels = source.getnchannels()
                sample_width = source.getsampwidth()
                frame_rate = source.getframerate()
                compression_type = source.getcomptype()
                compression_name = source.getcompname()
                frames = source.readframes(source.getnframes())
        except wave.Error as exc:
            raise SpeechUnavailable("Speech audio is not a playable PCM WAV") from exc
        if compression_type != "NONE" or frame_rate <= 0:
            raise SpeechUnavailable("Speech audio must be uncompressed PCM WAV")
        wake_signal = self._speaker_wake_pcm(
            frame_rate, sample_width, channels
        )
        temporary = wav_path.with_suffix(".preroll.wav")
        try:
            with wave.open(str(temporary), "wb") as output:
                output.setnchannels(channels)
                output.setsampwidth(sample_width)
                output.setframerate(frame_rate)
                output.setcomptype(compression_type, compression_name)
                output.writeframes(wake_signal + frames)
            temporary.replace(wav_path)
        finally:
            temporary.unlink(missing_ok=True)

    def _speaker_wake_pcm(
        self,
        frame_rate: int,
        sample_width: int,
        channels: int,
    ) -> bytes:
        """Return a very quiet tone so Bluetooth does not discard the warm-up audio."""

        frame_count = round(frame_rate * self._speaker_preroll_seconds)
        if frame_count <= 0:
            return b""
        if sample_width not in {1, 2, 3, 4} or channels <= 0:
            raise SpeechUnavailable("Speech audio has an unsupported PCM format")

        # Roughly -45 dBFS: strong enough to keep the audio transport active,
        # but normally inaudible through the prop speaker.
        maximum = (1 << (sample_width * 8 - 1)) - 1
        amplitude = max(1, round(maximum * 0.0055))
        tone_hz = 92.0
        result = bytearray()
        for index in range(frame_count):
            value = round(
                amplitude * math.sin(2.0 * math.pi * tone_hz * index / frame_rate)
            )
            if sample_width == 1:
                encoded = bytes((max(0, min(255, value + 128)),))
            else:
                encoded = value.to_bytes(sample_width, "little", signed=True)
            result.extend(encoded * channels)
        return bytes(result)

    async def _generate(self, text: str, wav_path: Path) -> None:
        process = await asyncio.create_subprocess_exec(
            self._espeak_command,
            "-v",
            self._voice,
            "-s",
            str(self._speed),
            "-p",
            str(self._pitch),
            "-g",
            str(self._word_gap),
            "-w",
            str(wav_path),
            text,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise SpeechUnavailable("Local speech generation timed out") from exc
        if process.returncode != 0:
            detail = stderr.decode(errors="replace").strip()
            raise SpeechUnavailable(detail or "espeak-ng could not generate speech")

    def _jaw_envelope(
        self, wav_source: Path | BinaryIO
    ) -> tuple[list[bool], float]:
        source = str(wav_source) if isinstance(wav_source, Path) else wav_source
        with wave.open(source, "rb") as wav:
            sample_width = wav.getsampwidth()
            channels = wav.getnchannels()
            rate = wav.getframerate()
            frame_count = wav.getnframes()
            audio = wav.readframes(frame_count)

        if sample_width != 2 or rate <= 0:
            raise SpeechUnavailable("Local speech WAV format is not 16-bit PCM")
        samples = array("h")
        samples.frombytes(audio)
        if sys.byteorder == "big":
            samples.byteswap()
        if channels > 1:
            samples = array("h", samples[::channels])

        chunk_size = max(1, round(rate * self._frame_seconds))
        levels: list[float] = []
        for start in range(0, len(samples), chunk_size):
            chunk = samples[start : start + chunk_size]
            if not chunk:
                continue
            mean_square = sum(sample * sample for sample in chunk) / len(chunk)
            levels.append(math.sqrt(mean_square))

        peak = max(levels, default=0.0)
        if peak <= 0:
            return [False] * len(levels), frame_count / rate

        open_threshold = peak * 0.16
        close_threshold = peak * 0.08
        opened = False
        envelope: list[bool] = []
        for level in levels:
            if opened and level <= close_threshold:
                opened = False
            elif not opened and level >= open_threshold:
                opened = True
            envelope.append(opened)
        return self._limit_jaw_activity(envelope), frame_count / rate

    def _limit_jaw_activity(self, envelope: list[bool]) -> list[bool]:
        if self._jaw_activity_percent <= 0:
            return [False] * len(envelope)
        minimum_closed_frames = max(
            0,
            round(5 - 5 * self._jaw_activity_percent / 100),
        )
        limited: list[bool] = []
        closed_frames = minimum_closed_frames
        opened = False
        for requested_open in envelope:
            if opened:
                opened = requested_open
                if not opened:
                    closed_frames = 1
            elif requested_open and closed_frames >= minimum_closed_frames:
                opened = True
                closed_frames = 0
            else:
                closed_frames += 1
            limited.append(opened)
        return limited

    async def _play(
        self,
        wav_path: Path,
        envelope: list[bool],
        duration: float,
        jaw: JawController,
        *,
        engine: str = "espeak-ng",
        cloud_used: bool = False,
    ) -> dict[str, object]:
        process = await asyncio.create_subprocess_exec(
            self._player_command,
            str(wav_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        jaw_animated = bool(jaw.snapshot().armed)
        jaw_animated = jaw_animated and self._jaw_activity_percent > 0
        jaw_error: str | None = None
        last_state = False
        started = asyncio.get_running_loop().time()
        try:
            if jaw.snapshot().armed and self._jaw_activity_percent == 0:
                try:
                    await jaw.set_position(jaw=0)
                except DacUnavailable as exc:
                    jaw_error = str(exc)
            if jaw_animated:
                await asyncio.sleep(self._bluetooth_delay_seconds)
                timeline_start = asyncio.get_running_loop().time()
                for index, opened in enumerate(envelope):
                    target_time = timeline_start + index * self._frame_seconds
                    await asyncio.sleep(
                        max(0.0, target_time - asyncio.get_running_loop().time())
                    )
                    if opened == last_state:
                        continue
                    try:
                        await jaw.set_position(jaw=255 if opened else 0)
                        last_state = opened
                    except DacUnavailable as exc:
                        jaw_animated = False
                        jaw_error = str(exc)
                        break
            _, stderr = await process.communicate()
            if process.returncode != 0:
                detail = stderr.decode(errors="replace").strip()
                raise SpeechUnavailable(detail or "pw-play could not play local speech")
        finally:
            if process.returncode is None:
                process.terminate()
                await process.wait()
            if last_state:
                try:
                    await jaw.set_position(jaw=0)
                except DacUnavailable as exc:
                    jaw_error = jaw_error or str(exc)

        return {
            "spoken": True,
            "engine": engine,
            "duration_seconds": round(duration, 2),
            "elapsed_seconds": round(asyncio.get_running_loop().time() - started, 2),
            "speaker_preroll_ms": round(self._speaker_preroll_seconds * 1000),
            "jaw_animated": jaw_animated,
            "jaw_error": jaw_error,
            "cloud_used": cloud_used,
            "elevenlabs_used": engine.startswith("elevenlabs"),
        }
