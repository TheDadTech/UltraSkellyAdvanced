import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ProviderSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    brain_provider: Literal["local", "groq"] = "local"
    voice_provider: Literal["local", "groq", "elevenlabs"] = "local"
    local_voice: str = Field(default="en-us+m3", min_length=1, max_length=60)
    local_speed: int = Field(default=145, ge=80, le=300)
    local_pitch: int = Field(default=30, ge=0, le=99)
    local_word_gap: int = Field(default=5, ge=0, le=50)
    groq_voice: str = Field(default="troy", min_length=1, max_length=40)
    groq_voice_style: Literal[
        "natural",
        "cartoon_skeleton_villain",
        "gravelly_whisper",
        "deadpan",
    ] = "cartoon_skeleton_villain"
    elevenlabs_voice_id: str = Field(default="", max_length=100)
    elevenlabs_model: Literal[
        "eleven_v3",
        "eleven_flash_v2_5",
        "eleven_multilingual_v2",
    ] = "eleven_v3"
    elevenlabs_speed: float = Field(default=0.85, ge=0.7, le=1.2)
    elevenlabs_volume_percent: int = Field(default=85, ge=10, le=100)
    speaker_preroll_ms: int = Field(default=650, ge=0, le=1500)
    jaw_activity_percent: int = Field(default=35, ge=0, le=100)


class ProviderSettingsStore:
    """Persists non-secret provider choices on the Pi."""

    def __init__(self, data_dir: Path, defaults: ProviderSettings) -> None:
        self._data_dir = data_dir
        self._path = data_dir / "provider-settings.json"
        self._defaults = defaults

    def load(self) -> ProviderSettings:
        if not self._path.exists():
            return self._defaults.model_copy(deep=True)
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            merged = self._defaults.model_dump()
            merged.update(payload)
            return ProviderSettings.model_validate(merged)
        except (OSError, json.JSONDecodeError, ValueError):
            return self._defaults.model_copy(deep=True)

    def save(self, settings: ProviderSettings) -> ProviderSettings:
        self._data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self._data_dir, 0o700)
        temporary_path = self._data_dir / ".provider-settings.json.tmp"
        temporary_path.write_text(
            json.dumps(settings.model_dump(), separators=(",", ":")),
            encoding="utf-8",
        )
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, self._path)
        os.chmod(self._path, 0o600)
        return settings
