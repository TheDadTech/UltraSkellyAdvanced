import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class OperationSettings(BaseModel):
    """Non-secret choices that shape the simplified operator workflow."""

    model_config = ConfigDict(extra="ignore")

    skelly_name: str = Field(default="Skelly", min_length=1, max_length=30)
    personality: Literal["classic", "sarcastic", "sinister", "goofy", "grumpy", "friendly", "unhinged", "deadpan", "custom"] = "classic"
    personality_pool: list[Literal["classic", "sarcastic", "sinister", "goofy", "grumpy", "friendly", "unhinged", "deadpan", "custom"]] = Field(default_factory=lambda: ["classic"], min_length=1, max_length=9)
    custom_personality: str = Field(default="", max_length=500)
    hardware_profile: Literal["stock", "dac"] = "stock"
    default_mode: Literal["classic", "ai", "manual", "idle"] = "ai"
    auto_start: bool = False
    # A clean installation must stay inert until its owner completes Setup.
    device_configured: bool = False
    control_address: str | None = None
    speaker_address: str | None = None
    audio_output: Literal["skelly", "external_bluetooth", "system"] = "skelly"
    external_bluetooth_address: str | None = None
    external_bluetooth_name: str | None = None
    jaw_follow_speech: bool = True
    jaw_sync_offset_ms: int = Field(default=-750, ge=-1000, le=1000)
    jaw_mirror_level_percent: int = Field(default=100, ge=70, le=100)
    mute_skelly_speaker_on_external: bool = True
    skelly_speaker_restore_volume: int = Field(default=128, ge=0, le=255)
    allow_fpp_override: bool = False
    manual_microphone_enabled: bool = True
    manual_camera_enabled: bool = True
    listening_sensitivity: int = Field(default=45, ge=1, le=100)
    trigger_on_audio: bool = True
    trigger_on_face: bool = True
    trigger_on_motion: bool = True
    nag_mode: Literal["disabled", "media", "ai"] = "disabled"
    nag_delay_seconds: int = Field(default=5, ge=2, le=30)
    nag_cooldown_seconds: int = Field(default=30, ge=10, le=120)
    nag_max_per_visitor: int = Field(default=2, ge=1, le=5)
    nag_require_presence: bool = True

    @field_validator("skelly_name", mode="before")
    @classmethod
    def normalize_skelly_name(cls, value: object) -> str:
        name = str(value or "").strip()
        return name or "Skelly"

    @field_validator("custom_personality", mode="before")
    @classmethod
    def normalize_custom_personality(cls, value: object) -> str:
        return str(value or "").strip()[:500]

    @field_validator("personality_pool", mode="before")
    @classmethod
    def normalize_personality_pool(cls, value: object) -> list[str]:
        allowed = {"classic", "sarcastic", "sinister", "goofy", "grumpy", "friendly", "unhinged", "deadpan", "custom"}
        raw = value if isinstance(value, (list, tuple, set)) else [value]
        normalized: list[str] = []
        for item in raw:
            personality = str(item or "").strip().lower()
            if personality in allowed and personality not in normalized:
                normalized.append(personality)
        return normalized or ["classic"]

    @model_validator(mode="after")
    def synchronize_legacy_personality(self) -> "OperationSettings":
        # Keep the legacy single-value field populated for old clients and rollback compatibility.
        self.personality = self.personality_pool[0] if self.personality_pool else "classic"
        return self

    @model_validator(mode="after")
    def disable_fpp_override_without_dac(self) -> "OperationSettings":
        if self.hardware_profile != "dac" and self.allow_fpp_override:
            self.allow_fpp_override = False
        return self


class OperationSettingsStore:
    """Persist operator choices separately from provider credentials."""

    def __init__(self, data_dir: Path, defaults: OperationSettings | None = None) -> None:
        self._data_dir = data_dir
        self._path = data_dir / "operation-settings.json"
        self._defaults = defaults or OperationSettings()

    def load(self) -> OperationSettings:
        if not self._path.exists():
            return self._defaults.model_copy(deep=True)
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            merged = self._defaults.model_dump()
            merged.update(payload)
            if "personality_pool" not in payload and payload.get("personality"):
                merged["personality_pool"] = [payload["personality"]]
            return OperationSettings.model_validate(merged)
        except (OSError, json.JSONDecodeError, ValueError):
            return self._defaults.model_copy(deep=True)

    def save(self, settings: OperationSettings) -> OperationSettings:
        self._data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self._data_dir, 0o700)
        temporary_path = self._data_dir / ".operation-settings.json.tmp"
        temporary_path.write_text(
            json.dumps(settings.model_dump(), separators=(",", ":")),
            encoding="utf-8",
        )
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, self._path)
        os.chmod(self._path, 0o600)
        return settings


def listening_sensitivity_to_dbfs(value: int) -> float:
    """Map a friendly 1-100 sensitivity control to a practical speech threshold.

    1 is intentionally conservative (-25 dBFS); 100 is very sensitive (-55 dBFS).
    The default 45 maps to approximately the historical -38 dBFS threshold.
    """
    sensitivity = max(1, min(100, int(value)))
    return round(-25.0 - ((sensitivity - 1) * (30.0 / 99.0)), 1)


def dbfs_to_listening_sensitivity(value: float) -> int:
    """Inverse mapping used to preserve an environment-configured legacy threshold."""
    dbfs = max(-55.0, min(-25.0, float(value)))
    sensitivity = 1 + ((-25.0 - dbfs) * (99.0 / 30.0))
    return max(1, min(100, round(sensitivity)))
