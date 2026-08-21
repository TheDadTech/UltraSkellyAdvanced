import asyncio
import io
import json
import math
import re
import shutil
import subprocess
import sys
import threading
import time
import wave
from array import array
from datetime import datetime, timezone
from pathlib import Path


class SensorUnavailable(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tracking_target(
    faces: object,
    people: object,
    width: int,
    height: int,
) -> dict[str, object]:
    """Choose the largest face, or largest person when no face is visible."""

    face_boxes = list(faces)  # type: ignore[arg-type]
    person_boxes = list(people)  # type: ignore[arg-type]
    candidates = face_boxes if face_boxes else person_boxes
    if not candidates or width <= 0 or height <= 0:
        return {
            "target_visible": False,
            "target_source": None,
            "target_x_percent": None,
            "target_y_percent": None,
        }
    x, y, box_width, box_height = max(
        candidates,
        key=lambda box: float(box[2]) * float(box[3]),
    )
    return {
        "target_visible": True,
        "target_source": "face" if face_boxes else "person",
        "target_x_percent": round(100.0 * (float(x) + float(box_width) / 2) / width, 1),
        "target_y_percent": round(100.0 * (float(y) + float(box_height) / 2) / height, 1),
    }


class SensorLab:
    """On-device camera and microphone analysis with no cloud connections."""

    def __init__(
        self,
        camera_device: str = "/dev/video0",
        microphone_device: str = "auto",
        voice_threshold_dbfs: float = -38.0,
        speech_model_path: Path = Path(
            "/var/lib/skelly-ai/models/vosk-model-small-en-us-0.15"
        ),
    ) -> None:
        self.camera_device = camera_device
        self.microphone_device = microphone_device
        self.voice_threshold_dbfs = voice_threshold_dbfs
        self.speech_model_path = speech_model_path
        self._camera_lock = asyncio.Lock()
        self._microphone_lock = asyncio.Lock()
        self._state_lock = threading.Lock()
        self._previous_gray = None
        self._hog = None
        self._face_detector = None
        self._vosk_model = None
        self._vosk_model_lock = threading.Lock()
        self._last_camera: dict[str, object] = {
            "analyzed": False,
            "presence_detected": False,
            "person_count": 0,
            "face_count": 0,
            "motion_percent": 0.0,
            "width": None,
            "height": None,
            "captured_at": None,
        }
        self._last_microphone: dict[str, object] = {
            "sampled": False,
            "voice_active": False,
            "level_dbfs": None,
            "peak_percent": 0.0,
            "duration_seconds": 0.0,
            "sampled_at": None,
            "transcript": None,
            "transcription_seconds": None,
            "transcribed_at": None,
        }
        self._last_audio_wav: bytes | None = None
        self._last_audio_pcm: bytes | None = None

    def status(self) -> dict[str, object]:
        with self._state_lock:
            camera = dict(self._last_camera)
            microphone = dict(self._last_microphone)
        return {
            "local_only": True,
            "camera": {
                "available": Path(self.camera_device).exists(),
                "device": self.camera_device,
                **camera,
            },
            "microphone": {
                "available": shutil.which("arecord") is not None,
                "device": self.microphone_device,
                "voice_threshold_dbfs": self.voice_threshold_dbfs,
                "offline_transcription_available": self.speech_model_path.is_dir(),
                "speech_model": self.speech_model_path.name,
                **microphone,
            },
        }

    async def analyze_camera(self) -> bytes:
        async with self._camera_lock:
            return await asyncio.to_thread(self._analyze_camera_sync)

    def _analyze_camera_sync(self) -> bytes:
        try:
            import cv2
        except ImportError as exc:
            raise SensorUnavailable("OpenCV is not installed on this Pi") from exc

        capture = cv2.VideoCapture(self.camera_device, cv2.CAP_V4L2)
        if not capture.isOpened():
            capture.release()
            raise SensorUnavailable(f"Unable to open camera {self.camera_device}")

        try:
            capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            frame = None
            for _ in range(3):
                ok, candidate = capture.read()
                if ok:
                    frame = candidate
            if frame is None:
                raise SensorUnavailable("The camera opened but returned no image")
        finally:
            capture.release()

        height, width = frame.shape[:2]
        if width > 720:
            scale = 720 / width
            frame = cv2.resize(frame, (720, max(1, int(height * scale))))
            height, width = frame.shape[:2]

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)

        if self._face_detector is None:
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            self._face_detector = cv2.CascadeClassifier(cascade_path)
        faces = self._face_detector.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(50, 50)
        )

        if self._hog is None:
            self._hog = cv2.HOGDescriptor()
            self._hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        people, _ = self._hog.detectMultiScale(
            frame, winStride=(8, 8), padding=(8, 8), scale=1.05
        )

        motion_percent = 0.0
        if self._previous_gray is not None and self._previous_gray.shape == gray.shape:
            difference = cv2.absdiff(self._previous_gray, gray)
            _, changed = cv2.threshold(difference, 25, 255, cv2.THRESH_BINARY)
            motion_percent = round(
                100.0 * float(cv2.countNonZero(changed)) / float(changed.size), 2
            )
        self._previous_gray = gray

        for x, y, box_width, box_height in people:
            cv2.rectangle(
                frame,
                (int(x), int(y)),
                (int(x + box_width), int(y + box_height)),
                (0, 140, 255),
                2,
            )
            cv2.putText(
                frame,
                "person",
                (int(x), max(18, int(y) - 7)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 140, 255),
                2,
            )
        for x, y, box_width, box_height in faces:
            cv2.rectangle(
                frame,
                (int(x), int(y)),
                (int(x + box_width), int(y + box_height)),
                (75, 210, 120),
                2,
            )
            cv2.putText(
                frame,
                "face presence",
                (int(x), max(18, int(y) - 7)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (75, 210, 120),
                2,
            )

        presence_detected = bool(len(people) or len(faces))
        tracking_target = _tracking_target(faces, people, width, height)
        label = (
            f"presence: {'yes' if presence_detected else 'no'}  "
            f"motion: {motion_percent:.1f}%"
        )
        cv2.rectangle(frame, (0, 0), (width, 34), (10, 10, 12), -1)
        cv2.putText(
            frame,
            label,
            (10, 23),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (240, 240, 240),
            1,
        )

        encoded, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
        if not encoded:
            raise SensorUnavailable("Unable to encode the camera image")

        with self._state_lock:
            self._last_camera = {
                "analyzed": True,
                "presence_detected": presence_detected,
                "person_count": int(len(people)),
                "face_count": int(len(faces)),
                **tracking_target,
                "motion_percent": motion_percent,
                "width": int(width),
                "height": int(height),
                "captured_at": _utc_now(),
            }
        return jpeg.tobytes()

    async def sample_microphone(self, duration_seconds: int = 1) -> dict[str, object]:
        async with self._microphone_lock:
            return await asyncio.to_thread(
                self._sample_microphone_sync, duration_seconds
            )

    def _resolve_microphone_device(self) -> str:
        if self.microphone_device != "auto":
            return self.microphone_device
        arecord = shutil.which("arecord")
        if arecord is None:
            raise SensorUnavailable("arecord is not installed")
        listing = subprocess.run(
            [arecord, "-l"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=5,
            text=True,
        )
        match = re.search(r"card\s+(\d+):.*device\s+(\d+):", listing.stdout)
        return f"plughw:{match.group(1)},{match.group(2)}" if match else "default"

    def _sample_microphone_sync(self, duration_seconds: int = 1) -> dict[str, object]:
        arecord = shutil.which("arecord")
        if arecord is None:
            raise SensorUnavailable("arecord is not installed")
        device = self._resolve_microphone_device()
        try:
            recording = subprocess.run(
                [
                    arecord,
                    "-q",
                    "-D",
                    device,
                    "-f",
                    "S16_LE",
                    "-c",
                    "1",
                    "-r",
                    "16000",
                    "-d",
                    str(duration_seconds),
                    "-t",
                    "raw",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=duration_seconds + 3,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SensorUnavailable("Microphone sampling failed") from exc

        if recording.returncode != 0 or not recording.stdout:
            detail = recording.stderr.decode(errors="replace").strip()[-500:]
            raise SensorUnavailable(detail or "The microphone returned no audio")

        return self._store_microphone_pcm(recording.stdout, device)

    def _store_microphone_pcm(self, pcm: bytes, device: str) -> dict[str, object]:
        samples = array("h")
        samples.frombytes(pcm)
        if sys.byteorder != "little":
            samples.byteswap()
        if not samples:
            raise SensorUnavailable("The microphone returned an empty audio sample")

        mean_square = sum(float(sample) * float(sample) for sample in samples) / len(samples)
        rms = math.sqrt(mean_square)
        level_dbfs = round(20.0 * math.log10(max(rms / 32768.0, 1e-9)), 1)
        peak_percent = round(100.0 * max(abs(sample) for sample in samples) / 32768.0, 1)
        voice_active = level_dbfs >= self.voice_threshold_dbfs

        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(16000)
            wav_file.writeframes(pcm)

        microphone_status = {
            "sampled": True,
            "voice_active": voice_active,
            "level_dbfs": level_dbfs,
            "peak_percent": peak_percent,
            "duration_seconds": round(len(samples) / 16000.0, 2),
            "sampled_at": _utc_now(),
            "resolved_device": device,
            "transcript": None,
            "transcription_seconds": None,
            "transcribed_at": None,
        }
        with self._state_lock:
            self._last_microphone = microphone_status
            self._last_audio_wav = wav_buffer.getvalue()
            self._last_audio_pcm = pcm
        return self.status()

    async def transcribe_microphone_until_silence(
        self,
        max_duration_seconds: int = 5,
        silence_seconds: float = 0.7,
    ) -> dict[str, object]:
        async with self._microphone_lock:
            return await asyncio.to_thread(
                self._record_until_silence_and_transcribe_sync,
                max_duration_seconds,
                silence_seconds,
            )

    async def prepare_transcription(self) -> None:
        """Load the offline recognizer before a visitor is invited to speak."""

        await asyncio.to_thread(self._new_vosk_recognizer)

    def _new_vosk_recognizer(self):
        if not self.speech_model_path.is_dir():
            raise SensorUnavailable(
                "The offline speech model is not installed; run deploy/install-speech-model.sh"
            )
        try:
            from vosk import KaldiRecognizer, Model, SetLogLevel
        except ImportError as exc:
            raise SensorUnavailable("The Vosk speech engine is not installed") from exc

        SetLogLevel(-1)
        if self._vosk_model is None:
            with self._vosk_model_lock:
                if self._vosk_model is None:
                    self._vosk_model = Model(str(self.speech_model_path))
        return KaldiRecognizer(self._vosk_model, 16000)

    def _record_until_silence_and_transcribe_sync(
        self,
        max_duration_seconds: int,
        silence_seconds: float,
    ) -> dict[str, object]:
        arecord = shutil.which("arecord")
        if arecord is None:
            raise SensorUnavailable("arecord is not installed")
        device = self._resolve_microphone_device()
        chunk_seconds = 0.1
        chunk_bytes = round(16000 * 2 * chunk_seconds)
        maximum_chunks = max(1, round(max_duration_seconds / chunk_seconds))
        silence_chunks_required = max(1, round(silence_seconds / chunk_seconds))
        recognizer = self._new_vosk_recognizer()
        chunks: list[bytes] = []
        speech_started = False
        silent_chunks = 0
        process = subprocess.Popen(
            [
                arecord,
                "-q",
                "-D",
                device,
                "-f",
                "S16_LE",
                "-c",
                "1",
                "-r",
                "16000",
                "-t",
                "raw",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            if process.stdout is None:
                raise SensorUnavailable("The microphone stream could not be opened")
            for _ in range(maximum_chunks):
                chunk = process.stdout.read(chunk_bytes)
                if not chunk:
                    break
                chunks.append(chunk)
                recognizer.AcceptWaveform(chunk)
                samples = array("h")
                samples.frombytes(chunk)
                if sys.byteorder != "little":
                    samples.byteswap()
                mean_square = (
                    sum(float(sample) * float(sample) for sample in samples)
                    / max(1, len(samples))
                )
                level_dbfs = 20.0 * math.log10(
                    max(math.sqrt(mean_square) / 32768.0, 1e-9)
                )
                if level_dbfs >= self.voice_threshold_dbfs:
                    speech_started = True
                    silent_chunks = 0
                elif speech_started:
                    silent_chunks += 1
                    if silent_chunks >= silence_chunks_required:
                        break
        except OSError as exc:
            raise SensorUnavailable("Adaptive microphone recording failed") from exc
        finally:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

        pcm = b"".join(chunks)
        if not pcm:
            raise SensorUnavailable("The microphone returned no audio")
        self._store_microphone_pcm(pcm, device)
        if speech_started:
            with self._state_lock:
                self._last_microphone = {
                    **self._last_microphone,
                    "voice_active": True,
                }
        finalized = time.monotonic()
        try:
            transcript = str(json.loads(recognizer.FinalResult()).get("text", "")).strip()
        except (json.JSONDecodeError, TypeError, AttributeError) as exc:
            raise SensorUnavailable("The offline speech engine returned invalid text") from exc
        with self._state_lock:
            self._last_microphone = {
                **self._last_microphone,
                "transcript": transcript,
                # Recognition ran alongside capture. This is only the extra wait
                # after the microphone closed, which is the latency visitors feel.
                "transcription_seconds": round(time.monotonic() - finalized, 2),
                "transcription_mode": "streaming",
                "transcribed_at": _utc_now(),
            }
        return self.status()

    async def transcribe_microphone(self, duration_seconds: int = 5) -> dict[str, object]:
        async with self._microphone_lock:
            return await asyncio.to_thread(
                self._record_and_transcribe_sync, duration_seconds
            )

    def _record_and_transcribe_sync(self, duration_seconds: int) -> dict[str, object]:
        self._sample_microphone_sync(duration_seconds)
        return self._transcribe_last_pcm_sync()

    def _transcribe_last_pcm_sync(self) -> dict[str, object]:
        with self._state_lock:
            pcm = self._last_audio_pcm
        if not pcm:
            raise SensorUnavailable("No microphone audio is available to transcribe")

        started = time.monotonic()
        recognizer = self._new_vosk_recognizer()
        for offset in range(0, len(pcm), 8000):
            recognizer.AcceptWaveform(pcm[offset : offset + 8000])
        try:
            transcript = str(json.loads(recognizer.FinalResult()).get("text", "")).strip()
        except (json.JSONDecodeError, TypeError, AttributeError) as exc:
            raise SensorUnavailable("The offline speech engine returned invalid text") from exc

        elapsed = round(time.monotonic() - started, 2)
        with self._state_lock:
            self._last_microphone = {
                **self._last_microphone,
                "transcript": transcript,
                "transcription_seconds": elapsed,
                "transcribed_at": _utc_now(),
            }
        return self.status()

    def last_audio_wav(self) -> bytes | None:
        with self._state_lock:
            return self._last_audio_wav
