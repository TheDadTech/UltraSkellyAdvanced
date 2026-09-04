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
        system_helper: Path | None = None,
    ) -> None:
        self._voice = voice
        self._speed = speed
        self._pitch = pitch
        self._word_gap = word_gap
        self._bluetooth_delay_seconds = bluetooth_delay_seconds
        self._jaw_sync_offset_seconds = -0.2
        self._playback_target: str | None = None
        self._playback_session = "dadtech"
        self._playback_target_required = False
        self._jaw_mirror_target: str | None = None
        self._jaw_mirror_session = "dadtech"
        self._jaw_follow_speech = True
        self._jaw_mirror_level_percent = 100
        self._speaker_preroll_seconds = speaker_preroll_seconds
        self._jaw_activity_percent = max(0, min(100, jaw_activity_percent))
        self._frame_seconds = frame_seconds
        self._espeak_command = espeak_command
        self._player_command = player_command
        self._system_helper = system_helper
        self._lock = asyncio.Lock()

    def status(self) -> dict[str, object]:
        generator_available = shutil.which(self._espeak_command) is not None
        player_available = shutil.which(self._player_command) is not None or bool(self._system_helper and self._system_helper.exists())
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
            "jaw_sync_offset_seconds": self._jaw_sync_offset_seconds,
            "playback_target": self._playback_target,
            "playback_session": self._playback_session,
            "jaw_mirror_target": self._jaw_mirror_target,
            "jaw_mirror_session": self._jaw_mirror_session,
            "jaw_follow_speech": self._jaw_follow_speech,
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

    def _player_exec(self, *arguments: str, session: str | None = None) -> list[str]:
        if self._system_helper is not None and self._system_helper.exists():
            command = ["sudo", str(self._system_helper), "audio-pw-play"]
            if session:
                command.extend(["--session", session])
            return [*command, *arguments]
        return [self._player_command, *arguments]

    def configure_output(
        self,
        *,
        playback_target: str | None,
        jaw_mirror_target: str | None,
        jaw_follow_speech: bool,
        jaw_sync_offset_ms: int,
        jaw_mirror_level_percent: int = 100,
        playback_session: str = "dadtech",
        jaw_mirror_session: str = "dadtech",
        playback_target_required: bool = False,
    ) -> None:
        self._playback_target = playback_target
        self._playback_session = playback_session
        self._playback_target_required = bool(playback_target_required)
        self._jaw_mirror_session = jaw_mirror_session
        self._jaw_mirror_target = (
            jaw_mirror_target
            if jaw_mirror_target and jaw_mirror_target != playback_target
            else None
        )
        self._jaw_follow_speech = bool(jaw_follow_speech)
        self._jaw_sync_offset_seconds = max(-1.0, min(1.0, jaw_sync_offset_ms / 1000.0))
        self._jaw_mirror_level_percent = max(70, min(100, int(jaw_mirror_level_percent)))

    def _player_arguments(
        self,
        *,
        target: str | None = None,
        raw: bool = False,
        sample_rate: int | None = None,
    ) -> list[str]:
        arguments: list[str] = []
        if target:
            arguments.extend(["--target", str(target)])
        if raw:
            arguments.extend([
                "--raw",
                "--rate",
                str(sample_rate or 22050),
                "--channels",
                "1",
                "--format",
                "s16",
            ])
        return arguments

    async def _set_jaw_mirror_level(self) -> None:
        if not self._jaw_mirror_target:
            return
        if self._system_helper is None or not self._system_helper.exists():
            return
        process = await asyncio.create_subprocess_exec(
            "sudo", str(self._system_helper), "audio-wpctl", "--session", self._jaw_mirror_session,
            "set-volume", self._jaw_mirror_target, f"{self._jaw_mirror_level_percent / 100:.2f}",
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            await asyncio.wait_for(process.wait(), timeout=3.0)
        except TimeoutError:
            process.kill()
            await process.wait()

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
                wav_path.chmod(0o644)
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
                wav_path.chmod(0o644)
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
        if self._playback_target_required and not self._playback_target:
            raise SpeechUnavailable("External Bluetooth is connected, but its PipeWire audio output is not ready")

        async with self._lock:
            try:
                process = await asyncio.create_subprocess_exec(
                    *self._player_exec(*self._player_arguments(
                        target=self._playback_target, raw=True, sample_rate=sample_rate
                    ), session=self._playback_session),
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

            mirror_process = None
            mirror_stock_jaw = bool(
                self._jaw_follow_speech
                and self._jaw_mirror_target
                and not jaw.snapshot().armed
            )
            if mirror_stock_jaw:
                await self._set_jaw_mirror_level()
                try:
                    mirror_process = await asyncio.create_subprocess_exec(
                        *self._player_exec(*self._player_arguments(
                            target=self._jaw_mirror_target, raw=True, sample_rate=sample_rate
                        ), session=self._jaw_mirror_session),
                        "-",
                        stdin=asyncio.subprocess.PIPE,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.PIPE,
                    )
                except OSError as exc:
                    process.terminate()
                    await process.wait()
                    raise SpeechUnavailable("pw-play could not start Skelly jaw mirror") from exc
                if mirror_process.stdin is None:
                    mirror_process.terminate()
                    await mirror_process.wait()
                    process.terminate()
                    await process.wait()
                    raise SpeechUnavailable("pw-play did not open the Skelly jaw mirror input")
                delay_bytes = round(sample_rate * 2 * abs(self._jaw_sync_offset_seconds))
                if delay_bytes > 0 and self._jaw_sync_offset_seconds > 0:
                    mirror_process.stdin.write(b"\x00" * delay_bytes)
                    await mirror_process.stdin.drain()

            loop = asyncio.get_running_loop()
            started = loop.time()
            frame_samples = max(1, round(sample_rate * self._frame_seconds))
            frame_bytes = frame_samples * 2
            preroll = self._speaker_wake_pcm(sample_rate, 2, 1)
            pending = bytearray()
            audio_bytes = 0
            first_audio_seconds: float | None = None
            jaw_animated = bool(
                jaw.snapshot().armed
                and self._jaw_follow_speech
                and self._jaw_activity_percent > 0
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
                await asyncio.sleep(max(0.0, self._jaw_sync_offset_seconds))
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
                if mirror_stock_jaw and self._jaw_sync_offset_seconds < 0:
                    delay_bytes = round(sample_rate * 2 * abs(self._jaw_sync_offset_seconds))
                    if delay_bytes > 0:
                        process.stdin.write(b"\x00" * delay_bytes)
                        await process.stdin.drain()
                if preroll:
                    process.stdin.write(preroll)
                    await process.stdin.drain()
                    if mirror_process is not None and mirror_process.stdin is not None:
                        mirror_process.stdin.write(preroll)
                        await mirror_process.stdin.drain()
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
                    if mirror_process is not None and mirror_process.stdin is not None:
                        mirror_process.stdin.write(pcm)
                        await mirror_process.stdin.drain()
                    await queue_envelope(pcm)
                if carry:
                    raise SpeechUnavailable("ElevenLabs returned invalid PCM audio")
                if audio_bytes == 0:
                    raise SpeechUnavailable("The voice provider returned empty audio")
                if pending:
                    await queue_envelope(b"\x00" * (frame_bytes - len(pending)))
                process.stdin.close()
                if mirror_process is not None and mirror_process.stdin is not None:
                    mirror_process.stdin.close()
                await envelope_queue.put(None)
                await jaw_task
                await process.wait()
                if mirror_process is not None:
                    await mirror_process.wait()
                    mirror_stderr = await mirror_process.stderr.read() if mirror_process.stderr else b""
                    if mirror_process.returncode != 0:
                        detail = mirror_stderr.decode(errors="replace").strip()
                        raise SpeechUnavailable(detail or "pw-play could not mirror streamed speech to Skelly jaw")
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
                if mirror_process is not None and mirror_process.returncode is None:
                    mirror_process.terminate()
                    await mirror_process.wait()
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
                "jaw_mirrored_to_skelly": mirror_stock_jaw,
                "jaw_follow_speech": self._jaw_follow_speech,
                "jaw_sync_offset_ms": round(self._jaw_sync_offset_seconds * 1000),
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
        if self._playback_target_required and not self._playback_target:
            raise SpeechUnavailable("External Bluetooth is connected, but its PipeWire audio output is not ready")
        mirror_process = None
        mirror_stock_jaw = bool(
            self._jaw_follow_speech
            and self._jaw_mirror_target
            and not jaw.snapshot().armed
        )

        async def start_primary():
            return await asyncio.create_subprocess_exec(
                *self._player_exec(*self._player_arguments(target=self._playback_target), session=self._playback_session),
                str(wav_path),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )

        async def start_mirror():
            await self._set_jaw_mirror_level()
            return await asyncio.create_subprocess_exec(
                *self._player_exec(*self._player_arguments(target=self._jaw_mirror_target), session=self._jaw_mirror_session),
                str(wav_path),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )

        # Signed sync semantics:
        #   negative => Skelly jaw mirror starts first; delay external/main audio
        #   zero     => both start together
        #   positive => external/main starts first; delay Skelly jaw mirror
        if mirror_stock_jaw and self._jaw_sync_offset_seconds < 0:
            mirror_process = await start_mirror()
            await asyncio.sleep(abs(self._jaw_sync_offset_seconds))
            process = await start_primary()
        else:
            process = await start_primary()
            if mirror_stock_jaw:
                if self._jaw_sync_offset_seconds > 0:
                    await asyncio.sleep(self._jaw_sync_offset_seconds)
                mirror_process = await start_mirror()

        jaw_animated = bool(jaw.snapshot().armed)
        jaw_animated = jaw_animated and self._jaw_follow_speech and self._jaw_activity_percent > 0
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
                # For a negative offset, the main audio was delayed above, so jaw
                # animation begins immediately. Positive values delay the jaw.
                await asyncio.sleep(max(0.0, self._jaw_sync_offset_seconds))
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
            if mirror_process is not None:
                _, mirror_stderr = await mirror_process.communicate()
                if mirror_process.returncode != 0:
                    detail = mirror_stderr.decode(errors="replace").strip()
                    raise SpeechUnavailable(detail or "pw-play could not mirror speech to Skelly jaw")
            if process.returncode != 0:
                detail = stderr.decode(errors="replace").strip()
                raise SpeechUnavailable(detail or "pw-play could not play local speech")
        finally:
            if process.returncode is None:
                process.terminate()
                await process.wait()
            if mirror_process is not None and mirror_process.returncode is None:
                mirror_process.terminate()
                await mirror_process.wait()
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
            "jaw_mirrored_to_skelly": mirror_stock_jaw,
            "jaw_follow_speech": self._jaw_follow_speech,
            "jaw_sync_offset_ms": round(self._jaw_sync_offset_seconds * 1000),
            "jaw_error": jaw_error,
            "cloud_used": cloud_used,
            "elevenlabs_used": engine.startswith("elevenlabs"),
        }
