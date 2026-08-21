import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


class OperationSettings(BaseModel):
    """Non-secret choices that shape the simplified operator workflow."""

    model_config = ConfigDict(extra="ignore")

    hardware_profile: Literal["stock", "dac"] = "stock"
    default_mode: Literal["classic", "ai", "manual", "idle"] = "ai"
    auto_start: bool = False
    # A clean installation must stay inert until its owner completes Setup.
    device_configured: bool = False
    control_address: str | None = None
    speaker_address: str | None = None
    allow_fpp_override: bool = False
    manual_microphone_enabled: bool = True
    manual_camera_enabled: bool = True

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
