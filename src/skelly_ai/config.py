from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables or an env file."""

    model_config = SettingsConfigDict(
        env_prefix="SKELLY_",
        env_file="/etc/skelly-ai/skelly-ai.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8787
    name: str = "USA"
    prop_model: Literal["ultra_skelly", "lethal_lily"] = "ultra_skelly"
    simulation: bool = True
    developer_mode: bool = False
    onboarding_required: bool = False
    system_helper: Path = Path("/usr/local/libexec/usa-system-helper")
    update_manifest_url: str | None = (
        "https://raw.githubusercontent.com/TheDadTech/UltraSkellyAdvanced/"
        "main/releases/stable/latest.json"
    )
    ble_address: str | None = None
    ble_name: str = "Animated Skelly"
    ble_connect_timeout_seconds: float = 15.0
    classic_audio_address: str | None = None
    # Matches both known factory names: ServoSkelly(Live) and Animated Skelly(Live).
    classic_audio_name: str = "Skelly(Live)"
    classic_audio_pin: str = Field(default="1234", min_length=4, max_length=16)
    classic_audio_connect_timeout_seconds: float = 20.0
    # Never target a LAN controller until an advanced user configures one.
    dac_target_ip: str = "127.0.0.1"
    dac_target_port: int = Field(default=5568, ge=1, le=65535)
    dac_universe: int = Field(default=1, ge=1, le=63999)
    dac_priority: int = Field(default=90, ge=0, le=200)
    dac_fps: float = Field(default=20.0, ge=1.0, le=44.0)
    dac_jaw_channel: int = Field(default=1, ge=1, le=512)
    dac_tilt_channel: int = Field(default=5, ge=1, le=512)
    dac_yaw_channel: int = Field(default=7, ge=1, le=512)
    dac_pitch_channel: int = Field(default=12, ge=1, le=512)
    dac_jaw_closed: int = Field(default=0, ge=0, le=255)
    dac_tilt_center: int = Field(default=127, ge=1, le=255)
    dac_yaw_center: int = Field(default=127, ge=1, le=255)
    dac_pitch_center: int = Field(default=127, ge=1, le=255)
    data_dir: Path = Path("/var/lib/skelly-ai")
    camera_device: str = "/dev/video0"
    microphone_device: str = "auto"
    voice_threshold_dbfs: float = -38.0
    speech_model_path: Path = Path(
        "/var/lib/skelly-ai/models/vosk-model-small-en-us-0.15"
    )
    perception_camera_interval_seconds: float = 2.5
    perception_presence_confirmations: int = 2
    perception_clear_confirmations: int = 4
    perception_record_seconds: int = Field(default=10, ge=3, le=15)
    perception_silence_seconds: float = Field(default=1.4, ge=0.8, le=3.0)
    perception_departure_motion_threshold: float = 1.0
    tracking_yaw_range: int = Field(default=38, ge=0, le=80)
    tracking_yaw_inverted: bool = False
    tracking_dead_zone_percent: float = Field(default=8.0, ge=0.0, le=25.0)
    tracking_listening_tilt_offset: int = Field(default=18, ge=-50, le=50)
    brain_url: str = "http://127.0.0.1:8790"
    brain_model: str = "skelly-local"
    brain_timeout_seconds: float = 90.0
    local_speech_voice: str = "en-us+m3"
    local_speech_speed: int = Field(default=145, ge=80, le=450)
    local_speech_pitch: int = Field(default=30, ge=0, le=99)
    local_speech_word_gap: int = Field(default=5, ge=0, le=100)
    local_speech_bluetooth_delay_seconds: float = Field(default=0.2, ge=0, le=2)
    local_speech_speaker_preroll_seconds: float = Field(default=0.65, ge=0, le=1.5)

    elevenlabs_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    fpp_token: SecretStr | None = Field(default=None)

    def public_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "prop_model": self.prop_model,
            "simulation": self.simulation,
            "ble_address": self.ble_address,
            "classic_audio_address": self.classic_audio_address,
            "dac_target": self.dac_target_ip,
            "dac_universe": self.dac_universe,
            "elevenlabs_configured": bool(self.elevenlabs_api_key),
            "fpp_token_configured": bool(self.fpp_token),
            "local_brain_model": self.brain_model,
        }
