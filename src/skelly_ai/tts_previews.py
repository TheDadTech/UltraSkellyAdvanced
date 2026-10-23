"""Temporary generated speech previews for Pi Media."""

from __future__ import annotations

import asyncio
import io
import secrets
import shutil
import time
import wave
from pathlib import Path

from .pi_media import PiMediaLibrary


class TTSPreviewError(RuntimeError):
    pass


class TTSPreviewManager:
    TTL_SECONDS = 900
    MAX_AUDIO_BYTES = 20 * 1024 * 1024
    MAX_PREVIEWS = 20
    MAX_TOTAL_BYTES = 100 * 1024 * 1024
    MIN_FREE_BYTES = 256 * 1024 * 1024

    def __init__(self, data_dir: Path):
        self.directory = Path(data_dir) / "tts-previews"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.directory.chmod(0o700)
        self._save_lock = asyncio.Lock()

    def _path(self, preview_id: str) -> Path:
        if len(preview_id) != 32 or any(
            c not in "0123456789abcdef" for c in preview_id
        ):
            raise TTSPreviewError("Invalid preview ID")
        return self.directory / f"{preview_id}.wav"

    def cleanup(self):
        now = time.time()
        for path in self.directory.glob("*.wav"):
            try:
                if now - path.stat().st_mtime > self.TTL_SECONDS:
                    path.unlink()
            except FileNotFoundError:
                pass

    def check_capacity(self, incoming_bytes: int):
        self.cleanup()
        paths = list(self.directory.glob("*.wav"))
        sizes = []
        for path in paths:
            try:
                sizes.append(path.stat().st_size)
            except FileNotFoundError:
                pass
        if len(sizes) >= self.MAX_PREVIEWS:
            raise TTSPreviewError("Preview count limit reached; discard or save a preview")
        if sum(sizes) + incoming_bytes > self.MAX_TOTAL_BYTES:
            raise TTSPreviewError("Preview storage quota exceeded; discard or save a preview")
        if shutil.disk_usage(self.directory).free - incoming_bytes < self.MIN_FREE_BYTES:
            raise TTSPreviewError("Preview generation would exceed the free disk reserve")

    def create(self, audio: bytes) -> str:
        self.cleanup()

        if not audio or len(audio) > self.MAX_AUDIO_BYTES:
            raise TTSPreviewError("Generated audio exceeds the 20 MB limit")

        try:
            with wave.open(io.BytesIO(audio), "rb") as wav:
                if (
                    wav.getnchannels() not in (1, 2)
                    or wav.getsampwidth() != 2
                    or wav.getframerate() <= 0
                    or wav.getnframes() <= 0
                ):
                    raise TTSPreviewError("Unsupported generated WAV format")
        except (wave.Error, EOFError) as exc:
            raise TTSPreviewError("Generated audio is not a valid WAV file") from exc

        self.check_capacity(len(audio))
        preview_id = secrets.token_hex(16)
        path = self._path(preview_id)
        with path.open("xb") as output:
            output.write(audio)
        path.chmod(0o600)
        return preview_id

    def get(self, preview_id: str) -> Path:
        self.cleanup()
        path = self._path(preview_id)
        if not path.is_file():
            raise TTSPreviewError("Preview expired or not found")
        return path

    def discard(self, preview_id: str):
        path = self._path(preview_id)
        path.unlink(missing_ok=True)

    async def save(
        self,
        preview_id: str,
        filename: str,
        display_name: str,
        library: PiMediaLibrary,
    ) -> dict[str, object]:
        """Save generated audio without overwriting existing Pi Media."""

        async with self._save_lock:
            path = self.get(preview_id)

            if (
                not isinstance(display_name, str)
                or not display_name.strip()
                or len(display_name.strip()) > 120
            ):
                raise TTSPreviewError("Media Name must contain 1 to 120 characters")

            async def audio_chunks():
                with path.open("rb") as source:
                    while chunk := source.read(64 * 1024):
                        yield chunk

            result = await library.add_stream(
                filename,
                audio_chunks(),
                display_name=display_name,
            )

            self.discard(preview_id)
            return result
