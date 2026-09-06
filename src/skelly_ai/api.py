import asyncio
import ipaddress
import re
import random
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import FileResponse, RedirectResponse, Response
import httpx
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, SecretStr

from . import __version__
from .brain import BrainResponseError, BrainUnavailable, LocalBrain
from .audio_output import (
    AudioOutputUnavailable,
    ExternalBluetoothAudio,
    SimulatedExternalBluetoothAudio,
)
from .cloud_providers import (
    CloudSpeechUnavailable,
    ElevenLabsVoice,
    GroqBrain,
    GroqVoice,
)
from .ble_hardware import BleSkelly, discover_skelly_devices
from .classic_audio import (
    BluetoothClassicAudio,
    ClassicAudio,
    ClassicAudioUnavailable,
    SimulatedClassicAudio,
)
from .config import Settings
from .credentials import (
    CredentialStore,
    CredentialStoreError,
    CredentialValidationError,
    ElevenLabsCredentials,
    validate_groq_key,
    validate_elevenlabs_key,
    fetch_elevenlabs_account,
    fetch_groq_quota,
)
from .diagnostics import collect_diagnostics
from .hardware import (
    EyeIcon,
    HardwareUnavailable,
    Movement,
    SkellyHardware,
    SimulatedSkelly,
)
from .perception import PerceptionEngine
from .operation_settings import (
    OperationSettings,
    OperationSettingsStore,
    dbfs_to_listening_sensitivity,
    listening_sensitivity_to_dbfs,
)
from .onboarding import OnboardingStore
from .provider_settings import ProviderSettings, ProviderSettingsStore
from .sacn import DacUnavailable, SacnDacController
from .sensors import SensorLab, SensorUnavailable
from .speech import LocalSpeech, SpeechUnavailable
from .state import InvalidTransition, Mode, StateController
from .updates import UpdateError, UpdateManager


class ShowRequest(BaseModel):
    name: str | None = Field(default=None, max_length=200)


class EyeRequest(BaseModel):
    icon: EyeIcon


class MovementRequest(BaseModel):
    movement: Movement


class LiveModeRequest(BaseModel):
    enabled: bool


class EyeIndexRequest(BaseModel):
    index: int = Field(ge=1, le=18)


class MovementArmRequest(BaseModel):
    enabled: bool


class ExternalBluetoothSelectRequest(BaseModel):
    address: str = Field(min_length=17, max_length=17)


class MovementProbeRequest(BaseModel):
    action: int = Field(ge=8, le=248, multiple_of=8)
    duration_ms: int = Field(default=350, ge=100, le=2000)
    acknowledged: bool


class DacArmRequest(BaseModel):
    enabled: bool


class DacPositionRequest(BaseModel):
    jaw: int | None = Field(default=None, ge=0, le=255)
    tilt: int | None = Field(default=None, ge=1, le=255)
    yaw: int | None = Field(default=None, ge=1, le=255)
    pitch: int | None = Field(default=None, ge=1, le=255)


class HardwareConnectRequest(BaseModel):
    address: str | None = Field(default=None, max_length=100)


class ElevenLabsSetupRequest(BaseModel):
    api_key: SecretStr


class GroqSetupRequest(BaseModel):
    api_key: SecretStr


class WifiConnectRequest(BaseModel):
    ssid: str = Field(min_length=1, max_length=64)
    password: SecretStr = Field(min_length=8, max_length=128)


class DisclaimerRequest(BaseModel):
    accepted: bool


class SshEnableRequest(BaseModel):
    password: SecretStr = Field(min_length=10, max_length=128)
    persistent: bool = False


class VoicePreviewRequest(BaseModel):
    text: str = Field(
        default="Welcome, brave visitor. Skelly is awake!",
        min_length=1,
        max_length=180,
    )


class MicrophoneTranscriptionRequest(BaseModel):
    duration_seconds: int = Field(default=5, ge=2, le=10)


class OperatorSpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=600)


class OperatorGestureRequest(BaseModel):
    gesture: Literal[
        "look_up",
        "look_down",
        "look_left",
        "look_right",
        "center",
        "tilt_left",
        "tilt_right",
        "listen",
        "confused",
        "yes",
        "no",
        "laugh",
    ]


class OperationStartRequest(BaseModel):
    mode: Literal["classic", "ai", "manual"]


class MediaPlayRequest(BaseModel):
    serial: int = Field(ge=0, le=65535)
    enabled: bool = True


class MediaVolumeRequest(BaseModel):
    volume: int = Field(ge=0, le=255)


class LightSettings(BaseModel):
    brightness: int = Field(default=200, ge=0, le=255)
    r: int = Field(default=255, ge=0, le=255)
    g: int = Field(default=255, ge=0, le=255)
    b: int = Field(default=255, ge=0, le=255)
    effect_mode: int = Field(default=1, ge=1, le=3)
    cycle: bool = False


class LightingRequest(LightSettings):
    channel: int = Field(ge=0, le=1)


class MediaEditRequest(BaseModel):
    serial: int = Field(ge=0, le=65535)
    action: int = Field(default=0)
    eye: int = Field(default=1, ge=1, le=18)
    head_light: LightSettings = Field(default_factory=LightSettings)
    torso_light: LightSettings = Field(default_factory=LightSettings)
    nag_response: bool = False


class MediaEnabledRequest(BaseModel):
    serial: int = Field(ge=0, le=65535)
    enabled: bool


def _listening_head_pose(
    camera: dict[str, object],
    *,
    yaw_center: int,
    tilt_center: int,
    yaw_range: int,
    dead_zone_percent: float,
    tilt_offset: int,
    yaw_inverted: bool,
) -> dict[str, int]:
    """Map a camera target into a conservative listening pose."""

    raw_x = camera.get("target_x_percent")
    x_percent = float(raw_x) if raw_x is not None else 50.0
    distance = x_percent - 50.0
    if abs(distance) <= dead_zone_percent:
        yaw_offset = 0
    else:
        usable = max(1.0, 50.0 - dead_zone_percent)
        magnitude = min(1.0, (abs(distance) - dead_zone_percent) / usable)
        yaw_offset = round(yaw_range * magnitude) * (1 if distance > 0 else -1)
    if yaw_inverted:
        yaw_offset *= -1
    return {
        "yaw": max(1, min(255, yaw_center + yaw_offset)),
        "tilt": max(1, min(255, tilt_center + tilt_offset)),
    }


def choose_ai_response_movement(roll: float | None = None) -> Movement:
    """Choose response motion with 90% head, 50% torso, and 30% arm usage.

    The supported stock movement groups are weighted so those marginal rates
    hold over time while keeping the loud arms comparatively rare.
    """

    value = random.random() if roll is None else max(0.0, min(0.999999, roll))
    if value < 0.50:
        return Movement.HEAD_ONLY
    if value < 0.70:
        return Movement.HEAD_AND_TORSO
    if value < 0.80:
        return Movement.TORSO_AND_ARMS
    return Movement.ALL


def create_app(
    settings: Settings | None = None,
    credential_validator=validate_elevenlabs_key,
    groq_credential_validator=validate_groq_key,
    sensor_lab: SensorLab | None = None,
    brain_client: LocalBrain | None = None,
    hardware_client: SkellyHardware | None = None,
    dac_client: SacnDacController | None = None,
    local_speech_client: LocalSpeech | None = None,
    classic_audio_client: ClassicAudio | None = None,
) -> FastAPI:
    app_settings = settings or Settings()
    controller = StateController()
    hardware = hardware_client or (
        SimulatedSkelly()
        if app_settings.simulation
        else BleSkelly(
            address=app_settings.ble_address,
            name_filter=app_settings.ble_name,
            timeout=app_settings.ble_connect_timeout_seconds,
        )
    )
    sensors = sensor_lab or SensorLab(
        camera_device=app_settings.camera_device,
        microphone_device=app_settings.microphone_device,
        voice_threshold_dbfs=app_settings.voice_threshold_dbfs,
        speech_model_path=app_settings.speech_model_path,
    )
    brain = brain_client or LocalBrain(
        app_settings.brain_url,
        app_settings.brain_model,
        timeout_seconds=app_settings.brain_timeout_seconds,
    )
    dac = dac_client or SacnDacController(
        target=app_settings.dac_target_ip,
        port=app_settings.dac_target_port,
        universe=app_settings.dac_universe,
        priority=app_settings.dac_priority,
        fps=app_settings.dac_fps,
        source_name=f"{app_settings.name} AI",
        jaw_channel=app_settings.dac_jaw_channel,
        tilt_channel=app_settings.dac_tilt_channel,
        yaw_channel=app_settings.dac_yaw_channel,
        pitch_channel=app_settings.dac_pitch_channel,
        jaw_closed=app_settings.dac_jaw_closed,
        tilt_center=app_settings.dac_tilt_center,
        yaw_center=app_settings.dac_yaw_center,
        pitch_center=app_settings.dac_pitch_center,
    )
    local_speech = local_speech_client or LocalSpeech(
        voice=app_settings.local_speech_voice,
        speed=app_settings.local_speech_speed,
        pitch=app_settings.local_speech_pitch,
        word_gap=app_settings.local_speech_word_gap,
        bluetooth_delay_seconds=app_settings.local_speech_bluetooth_delay_seconds,
        speaker_preroll_seconds=app_settings.local_speech_speaker_preroll_seconds,
        system_helper=app_settings.system_helper,
    )
    classic_audio = classic_audio_client or (
        SimulatedClassicAudio()
        if app_settings.simulation
        else BluetoothClassicAudio(
            address=app_settings.classic_audio_address,
            name_filter=app_settings.classic_audio_name,
            timeout_seconds=app_settings.classic_audio_connect_timeout_seconds,
            system_helper=app_settings.system_helper,
        )
    )
    external_audio = (
        SimulatedExternalBluetoothAudio()
        if app_settings.simulation
        else ExternalBluetoothAudio(
            timeout_seconds=app_settings.classic_audio_connect_timeout_seconds,
            system_helper=app_settings.system_helper,
            pipewire_session="skelly-ai",
        )
    )
    groq_brain = GroqBrain()
    groq_voice = GroqVoice()
    elevenlabs_voice = ElevenLabsVoice()

    provider_store = ProviderSettingsStore(
        app_settings.data_dir,
        ProviderSettings(
            local_voice=app_settings.local_speech_voice,
            local_speed=app_settings.local_speech_speed,
            local_pitch=app_settings.local_speech_pitch,
            local_word_gap=app_settings.local_speech_word_gap,
            speaker_preroll_ms=round(
                app_settings.local_speech_speaker_preroll_seconds * 1000
            ),
        ),
    )
    elevenlabs_cache_path = app_settings.data_dir / "elevenlabs-voices-cache.json"

    def load_elevenlabs_cache() -> dict[str, object]:
        if not elevenlabs_cache_path.exists():
            return {"voices": [], "remaining": None, "limit": None, "remaining_percent": None}
        try:
            import json
            payload = json.loads(elevenlabs_cache_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {"voices": []}
        except (OSError, ValueError):
            return {"voices": [], "remaining": None, "limit": None, "remaining_percent": None}

    def save_elevenlabs_cache(payload: dict[str, object]) -> None:
        import json
        app_settings.data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = app_settings.data_dir / ".elevenlabs-voices-cache.json.tmp"
        temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(elevenlabs_cache_path)
        elevenlabs_cache_path.chmod(0o600)

    operation_store = OperationSettingsStore(
        app_settings.data_dir,
        defaults=OperationSettings(
            listening_sensitivity=dbfs_to_listening_sensitivity(
                app_settings.voice_threshold_dbfs
            )
        ),
    )
    nag_media_path = app_settings.data_dir / "nag-media.json"

    def load_nag_media_serials() -> set[int]:
        if not nag_media_path.exists():
            return set()
        try:
            import json
            payload = json.loads(nag_media_path.read_text(encoding="utf-8"))
            values = payload.get("serials", []) if isinstance(payload, dict) else []
            return {int(value) for value in values}
        except (OSError, ValueError, TypeError):
            return set()

    def save_nag_media_serials(serials: set[int]) -> None:
        import json
        app_settings.data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = app_settings.data_dir / ".nag-media.json.tmp"
        temporary.write_text(
            json.dumps({"serials": sorted(serials)}, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary.chmod(0o600)
        temporary.replace(nag_media_path)
        nag_media_path.chmod(0o600)

    def enrich_media_status(status: dict[str, object]) -> dict[str, object]:
        serials = load_nag_media_serials()
        result = dict(status)
        files = []
        for item in status.get("files", []):
            if isinstance(item, dict):
                entry = dict(item)
                entry["nag_response"] = int(entry.get("serial", -1)) in serials
                files.append(entry)
        result["files"] = files
        return result
    onboarding = OnboardingStore(
        app_settings.data_dir,
        app_settings.system_helper,
        enabled=app_settings.onboarding_required,
    )
    updates = UpdateManager(app_settings.data_dir, app_settings.system_helper)
    saved_operation_settings = operation_store.load()
    external_audio.set_saved_target(
        saved_operation_settings.external_bluetooth_address,
        saved_operation_settings.external_bluetooth_name,
    )
    sensors.voice_threshold_dbfs = listening_sensitivity_to_dbfs(
        saved_operation_settings.listening_sensitivity
    )
    if not saved_operation_settings.device_configured:
        clear_hardware_target = getattr(hardware, "clear_saved_target", None)
        if clear_hardware_target is not None:
            clear_hardware_target()
        clear_audio_target = getattr(classic_audio, "clear_saved_target", None)
        if clear_audio_target is not None:
            clear_audio_target()
    else:
        set_hardware_target = getattr(hardware, "set_saved_target", None)
        if set_hardware_target is not None and saved_operation_settings.control_address:
            set_hardware_target(saved_operation_settings.control_address)
        set_audio_target = getattr(classic_audio, "set_saved_target", None)
        if set_audio_target is not None and saved_operation_settings.speaker_address:
            set_audio_target(saved_operation_settings.speaker_address)
    operation_lock = asyncio.Lock()
    operation_state: dict[str, object] = {
        "active_mode": "standby",
        "ready": False,
        "steps": [],
        "last_error": None,
    }

    def apply_local_voice_settings(settings: ProviderSettings) -> None:
        configure = getattr(local_speech, "configure", None)
        if configure is not None:
            configure(
                voice=settings.local_voice,
                speed=settings.local_speed,
                pitch=settings.local_pitch,
                word_gap=settings.local_word_gap,
                speaker_preroll_seconds=settings.speaker_preroll_ms / 1000,
                jaw_activity_percent=settings.jaw_activity_percent,
            )

    apply_local_voice_settings(provider_store.load())

    def apply_audio_output_settings() -> None:
        settings = operation_store.load()
        playback_target: str | None = None
        jaw_mirror_target: str | None = None
        playback_session = "dadtech"
        jaw_mirror_session = "dadtech"
        playback_target_required = False
        skelly_snapshot = classic_audio.snapshot()
        external_snapshot = external_audio.snapshot()
        if settings.audio_output == "skelly":
            playback_target = skelly_snapshot.sink_name or skelly_snapshot.sink_id
        elif settings.audio_output == "external_bluetooth":
            # Proven 3-Bluetooth topology: Soundcore belongs to skelly-ai's
            # PipeWire session while Animated Skelly(Live) belongs to dadtech.
            playback_session = "skelly-ai"
            playback_target_required = True
            playback_target = external_snapshot.sink_name or external_snapshot.sink_id
            if settings.jaw_follow_speech:
                jaw_mirror_target = skelly_snapshot.sink_name or skelly_snapshot.sink_id
        elif settings.jaw_follow_speech:
            jaw_mirror_target = skelly_snapshot.sink_name or skelly_snapshot.sink_id
        configure_output = getattr(local_speech, "configure_output", None)
        if configure_output is not None:
            configure_output(
                playback_target=playback_target,
                jaw_mirror_target=jaw_mirror_target,
                jaw_follow_speech=settings.jaw_follow_speech,
                jaw_sync_offset_ms=settings.jaw_sync_offset_ms,
                jaw_mirror_level_percent=settings.jaw_mirror_level_percent,
                playback_session=playback_session,
                jaw_mirror_session=jaw_mirror_session,
                playback_target_required=playback_target_required,
            )

    apply_audio_output_settings()

    async def apply_skelly_speaker_policy(
        settings: OperationSettings,
        *,
        previous: OperationSettings | None = None,
    ) -> OperationSettings:
        """Mute only Skelly's onboard speaker while external audio is selected.

        This uses the prop's BLE speaker-volume command, not PipeWire gain, so the
        full-strength A2DP jaw-mirror stream remains untouched. The user's last
        audible Skelly volume is persisted and restored when external audio is
        disabled.
        """
        status = hardware.media_status()
        current_volume = int(status.get("volume", settings.skelly_speaker_restore_volume) or 0)
        external_muted = (
            settings.audio_output == "external_bluetooth"
            and settings.mute_skelly_speaker_on_external
        )
        previous_external_muted = bool(
            previous
            and previous.audio_output == "external_bluetooth"
            and previous.mute_skelly_speaker_on_external
        )

        if external_muted:
            restore_volume = settings.skelly_speaker_restore_volume
            if not previous_external_muted and current_volume > 0:
                restore_volume = current_volume
            if current_volume != 0:
                try:
                    await hardware.set_volume(0)
                except HardwareUnavailable:
                    return settings
            if restore_volume != settings.skelly_speaker_restore_volume:
                settings = operation_store.save(
                    settings.model_copy(update={"skelly_speaker_restore_volume": restore_volume})
                )
            return settings

        if previous_external_muted and current_volume == 0:
            try:
                await hardware.set_volume(settings.skelly_speaker_restore_volume)
            except HardwareUnavailable:
                pass
        return settings

    async def respond_locally(
        transcript: str, history: list[dict[str, str]]
    ) -> dict[str, object]:
        settings = provider_store.load()
        operation_settings = operation_store.load()
        skelly_name = operation_settings.skelly_name
        configure_local_character = getattr(brain, "set_skelly_name", None)
        if configure_local_character is not None:
            configure_local_character(skelly_name)
        configure_groq_character = getattr(groq_brain, "set_skelly_name", None)
        if configure_groq_character is not None:
            configure_groq_character(skelly_name)
        personality_pool = list(operation_settings.personality_pool or ["classic"])
        effective_personality = random.choice(personality_pool)
        configure_local_personality = getattr(brain, "set_personality", None)
        if configure_local_personality is not None:
            configure_local_personality(
                effective_personality, operation_settings.custom_personality
            )
        configure_groq_personality = getattr(groq_brain, "set_personality", None)
        if configure_groq_personality is not None:
            configure_groq_personality(
                effective_personality, operation_settings.custom_personality
            )
        started = asyncio.get_running_loop().time()
        provider_used = settings.brain_provider
        fallback_reason: str | None = None
        if settings.brain_provider == "groq":
            try:
                credentials = credential_store.load()
                if credentials.groq_api_key is None:
                    raise BrainUnavailable(
                        "Save a Groq API key in Setup or choose Local Brain"
                    )
                reply = await groq_brain.respond(
                    credentials.groq_api_key, transcript, history
                )
            except (BrainUnavailable, BrainResponseError) as exc:
                reply = await brain.respond(transcript, history)
                provider_used = "local"
                fallback_reason = str(exc)
        else:
            reply = await brain.respond(transcript, history)
        generation_seconds = round(
            asyncio.get_running_loop().time() - started, 2
        )
        await hardware.set_eye(reply.eye_icon)
        selected_movement = choose_ai_response_movement()
        if hardware.snapshot().movement_armed:
            await hardware.set_movement(selected_movement)
        result = reply.to_dict()
        result["movement"] = selected_movement.value
        result["generation_seconds"] = generation_seconds
        result["brain_provider"] = provider_used
        result["brain_provider_selected"] = settings.brain_provider
        result["personality"] = effective_personality
        result["personality_pool"] = personality_pool
        if fallback_reason:
            result["brain_fallback_reason"] = fallback_reason
        return result

    async def speak_selected(
        text: str,
        *,
        allow_fallback: bool = True,
    ) -> dict[str, object]:
        settings = provider_store.load()
        apply_local_voice_settings(settings)
        # Audio sinks can appear/reconnect after application startup. Always
        # re-apply the latest snapshots before playback so every voice provider
        # (including streamed ElevenLabs speech) uses the same external/main
        # output and Skelly jaw-mirror targets.
        apply_audio_output_settings()
        voice_started = asyncio.get_running_loop().time()
        provider_used = settings.voice_provider
        fallback_reason: str | None = None
        if settings.voice_provider == "local":
            result = await local_speech.speak(text, dac)
        else:
            credentials = credential_store.load()
            try:
                if settings.voice_provider == "groq":
                    if credentials.groq_api_key is None:
                        raise CloudSpeechUnavailable(
                            "Save a Groq API key in Setup or choose Local Voice"
                        )
                    audio = await groq_voice.generate(
                        credentials.groq_api_key,
                        text,
                        settings.groq_voice,
                        settings.groq_voice_style,
                    )
                    engine = f"groq-orpheus:{settings.groq_voice}"
                else:
                    if credentials.api_key is None:
                        raise CloudSpeechUnavailable(
                            "Save an ElevenLabs API key in Setup or choose Local Voice"
                        )
                    # Buffer ElevenLabs PCM into a proper WAV before playback.
                    # The raw streaming path proved fragile on the dual-session
                    # Bluetooth topology (beep/static on some Pi runs), while the
                    # WAV path is already proven for both PipeWire sessions.
                    audio = await elevenlabs_voice.generate(
                        credentials.api_key,
                        text,
                        settings.elevenlabs_voice_id,
                        model=settings.elevenlabs_model,
                        speed=settings.elevenlabs_speed,
                        volume_percent=settings.elevenlabs_volume_percent,
                    )
                    engine = f"elevenlabs:{settings.elevenlabs_model}"
                    result = await local_speech.play_wav_bytes(
                        audio,
                        dac,
                        engine=engine,
                        cloud_used=True,
                    )
            except CloudSpeechUnavailable as exc:
                if not allow_fallback:
                    raise SpeechUnavailable(str(exc)) from exc
                fallback_reason = str(exc)
                provider_used = "local"
                result = await local_speech.speak(text, dac)
            else:
                if settings.voice_provider == "groq":
                    voice_generation_seconds = round(
                        asyncio.get_running_loop().time() - voice_started, 2
                    )
                    result = await local_speech.play_wav_bytes(
                        audio,
                        dac,
                        engine=engine,
                        cloud_used=True,
                    )
                else:
                    voice_generation_seconds = round(
                        asyncio.get_running_loop().time() - voice_started, 2
                    )
                result["voice_generation_seconds"] = voice_generation_seconds
                if settings.voice_provider == "elevenlabs":
                    result["voice_model"] = settings.elevenlabs_model
                    result["voice_speed"] = settings.elevenlabs_speed
                    result["voice_volume_percent"] = settings.elevenlabs_volume_percent
        result["voice_provider"] = provider_used
        result["voice_provider_selected"] = settings.voice_provider
        if fallback_reason:
            result["voice_fallback_reason"] = fallback_reason
        result["total_speech_seconds"] = round(
            asyncio.get_running_loop().time() - voice_started, 2
        )
        return result

    async def respond_automatically(
        transcript: str, history: list[dict[str, str]]
    ) -> dict[str, object]:
        result = await respond_locally(transcript, history)
        try:
            result["speech"] = await speak_selected(str(result["spoken_response"]))
        except SpeechUnavailable as exc:
            result["speech"] = {
                "spoken": False,
                "error": str(exc),
                "elevenlabs_used": False,
            }
        finally:
            try:
                await hardware.stop()
            except HardwareUnavailable:
                pass
        return result

    async def end_local_session() -> None:
        try:
            await hardware.stop()
            await hardware.set_eye(EyeIcon.NORMAL)
        finally:
            if dac.snapshot().armed:
                try:
                    await dac.center()
                except DacUnavailable:
                    pass

    async def show_local_phase_cue(phase: str) -> None:
        cue_eye = {
            "listening": EyeIcon.GREEN,
            "thinking": EyeIcon.SPIRAL,
            "no_speech": EyeIcon.NORMAL,
        }.get(phase)
        if cue_eye is None or controller.snapshot().mode == Mode.SHOW_LOCKED:
            return
        try:
            await hardware.set_eye(cue_eye)
        except HardwareUnavailable:
            # The dashboard cue still works while the prop is disconnected.
            pass
        if not dac.snapshot().armed:
            return
        try:
            if phase == "listening":
                camera = sensors.status().get("camera", {})
                camera_status = camera if isinstance(camera, dict) else {}
                pose = _listening_head_pose(
                    camera_status,
                    yaw_center=app_settings.dac_yaw_center,
                    tilt_center=app_settings.dac_tilt_center,
                    yaw_range=app_settings.tracking_yaw_range,
                    dead_zone_percent=app_settings.tracking_dead_zone_percent,
                    tilt_offset=app_settings.tracking_listening_tilt_offset,
                    yaw_inverted=app_settings.tracking_yaw_inverted,
                )
                await dac.set_position(jaw=0, **pose)
            elif phase == "no_speech":
                await dac.center()
        except DacUnavailable:
            pass

    interaction_snapshot_dir = app_settings.data_dir / "interaction-snapshots"
    interaction_snapshot_limit = 100

    async def save_interaction_snapshot(
        event_id: int, session_id: int, turn_number: int
    ) -> str | None:
        try:
            jpeg = await sensors.analyze_camera()
        except SensorUnavailable:
            return None
        interaction_snapshot_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        filename = f"event-{event_id:06d}-session-{session_id:04d}-turn-{turn_number:03d}.jpg"
        path = interaction_snapshot_dir / filename
        path.write_bytes(jpeg)
        path.chmod(0o600)
        snapshots = sorted(
            interaction_snapshot_dir.glob("event-*.jpg"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for stale in snapshots[interaction_snapshot_limit:]:
            try:
                stale.unlink()
            except OSError:
                pass
        return f"/api/perception/snapshots/{filename}"

    async def perform_visitor_nag(
        nag_count: int, session_elapsed: float, since_last_nag: float | None
    ) -> dict[str, object] | None:
        settings = operation_store.load()
        if settings.nag_mode == "disabled":
            return None
        if nag_count >= settings.nag_max_per_visitor:
            return None
        if nag_count == 0 and session_elapsed < settings.nag_delay_seconds:
            return None
        if nag_count > 0 and (
            since_last_nag is None or since_last_nag < settings.nag_cooldown_seconds
        ):
            return None
        if settings.nag_require_presence:
            camera = sensors.status().get("camera", {})
            if not isinstance(camera, dict) or not bool(camera.get("presence_detected")):
                return None

        if settings.nag_mode == "media":
            media_status = hardware.media_status()
            if not media_status.get("files"):
                try:
                    media_status = await hardware.refresh_media_files()
                except HardwareUnavailable:
                    return None
            eligible = [
                item
                for item in enrich_media_status(media_status).get("files", [])
                if isinstance(item, dict)
                and item.get("nag_response") is True
                and item.get("enabled", True) is not False
            ]
            if not eligible:
                return None
            previous = getattr(perform_visitor_nag, "_last_media_serial", None)
            alternatives = [item for item in eligible if int(item.get("serial", -1)) != previous]
            selected = random.choice(alternatives or eligible)
            serial = int(selected["serial"])
            await hardware.play_media(serial, True)
            setattr(perform_visitor_nag, "_last_media_serial", serial)
            return {"performed": True, "mode": "media", "serial": serial}

        prompt = (
            "A visitor is standing nearby but has not spoken to you. "
            "Get their attention with one playful Halloween line of at most 8 words. "
            "Do not introduce yourself or say your name."
        )
        result = await respond_automatically(prompt, [])
        return {"performed": True, "mode": "ai", "response": result.get("spoken_response")}

    def perception_trigger_settings() -> dict[str, bool]:
        settings = operation_store.load()
        return {
            "audio": settings.trigger_on_audio,
            "face": settings.trigger_on_face,
            "motion": settings.trigger_on_motion,
        }

    perception = PerceptionEngine(
        sensors,
        show_locked=lambda: controller.snapshot().mode == Mode.SHOW_LOCKED,
        responder=respond_automatically,
        session_ended=end_local_session,
        phase_cue=show_local_phase_cue,
        nagger=perform_visitor_nag,
        snapshotter=save_interaction_snapshot,
        trigger_settings=perception_trigger_settings,
        camera_interval_seconds=app_settings.perception_camera_interval_seconds,
        presence_confirmations=app_settings.perception_presence_confirmations,
        clear_confirmations=app_settings.perception_clear_confirmations,
        record_seconds=app_settings.perception_record_seconds,
        silence_seconds=app_settings.perception_silence_seconds,
        departure_motion_threshold=app_settings.perception_departure_motion_threshold,
    )
    credential_store = CredentialStore(
        app_settings.data_dir,
        defaults=ElevenLabsCredentials(
            api_key=app_settings.elevenlabs_api_key,
            groq_api_key=app_settings.groq_api_key,
        ),
    )
    static_dir = Path(__file__).parent / "static"
    operator_gesture_lock = asyncio.Lock()
    operator_gesture_task: asyncio.Task[dict[str, object]] | None = None
    auto_start_task: asyncio.Task[None] | None = None
    external_audio_reconnect_task: asyncio.Task[None] | None = None

    async def auto_start_saved_mode() -> None:
        await asyncio.sleep(0.25)
        settings = operation_store.load()
        if not settings.device_configured or not settings.auto_start:
            return
        if settings.default_mode == "idle":
            return
        try:
            await start_operation_mode(settings.default_mode)
        except HTTPException:
            # The dashboard reports the ordered startup steps and the exact failure.
            return

    async def maintain_external_audio_connection() -> None:
        while True:
            await asyncio.sleep(15)
            settings = operation_store.load()
            if settings.audio_output != "external_bluetooth" or not settings.external_bluetooth_address:
                continue
            try:
                snapshot = await external_audio.refresh()
                if not snapshot.connected or not snapshot.sink_id:
                    await external_audio.connect(route=True)
                if settings.jaw_follow_speech and settings.hardware_profile != "dac":
                    skelly = await classic_audio.refresh()
                    if not skelly.connected or not skelly.sink_id:
                        try:
                            await classic_audio.connect(route=False)
                            remember_speaker_connection()
                        except ClassicAudioUnavailable:
                            pass
                apply_audio_output_settings()
            except AudioOutputUnavailable:
                # The Setup card reports the last error; retry when the speaker returns.
                continue

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        nonlocal auto_start_task, external_audio_reconnect_task
        await controller.ready()
        if operation_store.load().device_configured:
            try:
                await hardware.connect()
                await apply_skelly_speaker_policy(operation_store.load())
            except HardwareUnavailable:
                # Keep the setup dashboard available when the prop is off or out of range.
                pass
            await classic_audio.refresh()
            try:
                await external_audio.refresh()
            except AudioOutputUnavailable:
                pass
        external_audio_reconnect_task = asyncio.create_task(maintain_external_audio_connection())
        if operation_store.load().auto_start:
            auto_start_task = asyncio.create_task(auto_start_saved_mode())
        yield
        if auto_start_task is not None and not auto_start_task.done():
            auto_start_task.cancel()
            try:
                await auto_start_task
            except asyncio.CancelledError:
                pass
        if external_audio_reconnect_task is not None and not external_audio_reconnect_task.done():
            external_audio_reconnect_task.cancel()
            try:
                await external_audio_reconnect_task
            except asyncio.CancelledError:
                pass
        await perception.stop()
        await dac.close()
        await hardware.disconnect()

    app = FastAPI(title="UltraSkellyAdvanced", version=__version__, lifespan=lifespan)
    app.state.settings = app_settings
    app.state.controller = controller
    app.state.hardware = hardware
    app.state.sensors = sensors
    app.state.perception = perception
    app.state.brain = brain
    app.state.dac = dac
    app.state.local_speech = local_speech
    app.state.classic_audio = classic_audio
    app.state.external_audio = external_audio
    app.state.credential_store = credential_store
    app.state.provider_store = provider_store
    app.state.operation_store = operation_store
    app.state.onboarding = onboarding
    app.state.updates = updates

    def require_fpp_token(x_skelly_token: str | None) -> None:
        if not operation_store.load().allow_fpp_override:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="FPP override is disabled in Setup",
            )
        configured = app_settings.fpp_token
        if configured is None:
            return
        if x_skelly_token != configured.get_secret_value():
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    def state_response() -> dict[str, object]:
        credential_status = credential_store.status()
        groq_status = credential_store.groq_status()
        providers = provider_store.load()
        public_device = app_settings.public_dict()
        public_device["elevenlabs_configured"] = credential_status.key_configured
        public_device["elevenlabs_key_configured"] = credential_status.key_configured
        public_device["groq_key_configured"] = groq_status.key_configured
        public_device["brain_provider"] = providers.brain_provider
        public_device["voice_provider"] = providers.voice_provider
        return {
            "version": __version__,
            "device": public_device,
            "state": controller.snapshot().to_dict(),
            "hardware": hardware.snapshot().to_dict(),
            "audio": classic_audio.snapshot().to_dict(),
            "external_audio": external_audio.snapshot().to_dict(),
            "dac": dac.snapshot().to_dict(),
            "operation": {
                **operation_state,
                "settings": operation_store.load().model_dump(),
            },
        }

    def remember_control_connection() -> None:
        snapshot = hardware.snapshot()
        settings = operation_store.load()
        changes: dict[str, object] = {"device_configured": True}
        if snapshot.address:
            changes["control_address"] = snapshot.address
        try:
            operation_store.save(settings.model_copy(update=changes))
        except OSError:
            # A live connection should still work if its optional binding cannot persist.
            pass

    def remember_speaker_connection() -> None:
        snapshot = classic_audio.snapshot()
        if not snapshot.address:
            return
        settings = operation_store.load()
        try:
            operation_store.save(
                settings.model_copy(
                    update={
                        "device_configured": True,
                        "speaker_address": snapshot.address,
                    }
                )
            )
        except OSError:
            # Audio remains usable even if the binding cannot be persisted.
            pass

    def require_local_setup(request: Request) -> None:
        client_host = request.client.host if request.client else ""
        try:
            local_network = ipaddress.ip_address(client_host).is_private
        except ValueError:
            local_network = client_host == "testclient"
        if not local_network:
            raise HTTPException(
                status_code=403,
                detail="Setup changes are accepted only from this Pi's local network",
            )

    def require_manual_hardware_access() -> None:
        mode = controller.snapshot().mode
        if mode == Mode.SHOW_LOCKED:
            raise HTTPException(
                status_code=409,
                detail="Operator and AI hardware commands are blocked during a show",
            )
        if mode == Mode.FAULT:
            raise HTTPException(
                status_code=409,
                detail="Hardware commands are blocked while the controller is faulted",
            )

    def require_manual_conversation_access() -> None:
        require_manual_hardware_access()
        if perception.status()["enabled"]:
            raise HTTPException(
                status_code=409,
                detail="Stop AI Mode before using the Operator microphone",
            )

    def require_developer_mode() -> None:
        if not app_settings.developer_mode:
            raise HTTPException(status_code=404, detail="Not found")

    def require_operator_mode() -> None:
        require_manual_hardware_access()
        if operation_state["active_mode"] != "manual":
            raise HTTPException(
                status_code=409,
                detail="Start Operator Mode before using live operator controls",
            )

    @staticmethod
    def _axis_value(value: int) -> int:
        return max(1, min(255, value))

    async def _run_dac_gesture(gesture: str) -> dict[str, object]:
        before = dac.snapshot()
        if not before.armed:
            raise DacUnavailable(
                "Advanced head gestures require the DAC to be armed"
            )
        original = dict(before.values)
        yaw_left, yaw_right = (255, 1) if app_settings.tracking_yaw_inverted else (1, 255)
        direct_positions: dict[str, dict[str, int]] = {
            "look_up": {"pitch": 255},
            "look_down": {"pitch": 1},
            "look_left": {"yaw": yaw_left},
            "look_right": {"yaw": yaw_right},
            "center": {
                "jaw": 0,
                "tilt": app_settings.dac_tilt_center,
                "yaw": app_settings.dac_yaw_center,
                "pitch": app_settings.dac_pitch_center,
            },
            "tilt_left": {"tilt": 1},
            "tilt_right": {"tilt": 255},
            "listen": {
                "jaw": 0,
                "tilt": _axis_value(app_settings.dac_tilt_center + 45),
                "pitch": _axis_value(app_settings.dac_pitch_center + 22),
            },
        }
        if gesture in direct_positions:
            snapshot = await dac.set_position(**direct_positions[gesture])
            return {"gesture": gesture, "complete": True, "dac": snapshot.to_dict()}

        async def move(axis: str, value: int, delay: float) -> None:
            await dac.set_position(**{axis: _axis_value(value)})
            await asyncio.sleep(delay)

        try:
            if gesture == "yes":
                for _ in range(3):
                    await move("pitch", 225, 0.22)
                    await move("pitch", 35, 0.22)
            elif gesture == "no":
                for _ in range(3):
                    await move("yaw", yaw_left, 0.22)
                    await move("yaw", yaw_right, 0.22)
            elif gesture == "confused":
                await move("tilt", 210, 0.45)
                await move("tilt", 55, 0.45)
                await move("tilt", 195, 0.45)
            elif gesture == "laugh":
                for index in range(7):
                    await dac.set_position(
                        jaw=255 if index % 2 == 0 else 0,
                        tilt=165 if index % 2 == 0 else 105,
                    )
                    await asyncio.sleep(0.22)
            else:
                raise DacUnavailable(f"Unknown DAC gesture: {gesture}")
        finally:
            await dac.set_position(
                jaw=0,
                tilt=int(original["tilt"]),
                yaw=int(original["yaw"]),
                pitch=int(original["pitch"]),
            )
        return {"gesture": gesture, "complete": True, "dac": dac.snapshot().to_dict()}

    async def _perform_operator_gesture(gesture: str) -> dict[str, object]:
        if gesture != "laugh":
            return await _run_dac_gesture(gesture)

        settings = provider_store.load()
        media = hardware.media_status()
        files = media.get("files", [])
        laugh_file = next(
            (
                item
                for item in files
                if isinstance(item, dict)
                and any(word in str(item.get("name", "")).lower() for word in ("laugh", "cackle"))
            ),
            None,
        )
        dac_task = asyncio.create_task(_run_dac_gesture("laugh")) if dac.snapshot().armed else None
        audio_result: dict[str, object]
        try:
            if settings.voice_provider != "local":
                try:
                    audio_result = await speak_selected("Ha! Ha! Ha! Ha!", allow_fallback=False)
                    audio_result["source"] = f"cloud_{settings.voice_provider}"
                except SpeechUnavailable:
                    if laugh_file is not None:
                        await hardware.play_media(int(laugh_file["serial"]), True)
                        audio_result = {"source": "skelly_media", "name": str(laugh_file.get("name") or "Laugh")}
                    else:
                        apply_local_voice_settings(settings)
                        audio_result = await local_speech.speak("Ha! Ha! Ha! Ha!", dac)
                        audio_result["source"] = "offline_local"
            elif laugh_file is not None:
                await hardware.play_media(int(laugh_file["serial"]), True)
                audio_result = {
                    "source": "skelly_media",
                    "name": str(laugh_file.get("name") or "Laugh"),
                }
            else:
                apply_local_voice_settings(settings)
                audio_result = await local_speech.speak("Ha! Ha! Ha! Ha!", dac)
                audio_result["source"] = "offline_local"
            if dac_task is not None:
                await dac_task
        except BaseException:
            if dac_task is not None and not dac_task.done():
                dac_task.cancel()
                try:
                    await dac_task
                except asyncio.CancelledError:
                    pass
            raise
        return {
            "gesture": "laugh",
            "complete": True,
            "audio": audio_result,
            "dac_used": dac.snapshot().armed,
        }

    async def _cancel_operator_gesture() -> bool:
        nonlocal operator_gesture_task
        task = operator_gesture_task
        operator_gesture_task = None
        if task is None or task.done():
            return False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        if dac.snapshot().armed:
            try:
                await dac.set_position(jaw=0)
            except DacUnavailable:
                pass
        return True

    async def recover_audio_for_mode(settings: OperationSettings) -> None:
        """Recover optional audio routes without delaying AI/Operator control startup."""
        try:
            if settings.audio_output == "skelly":
                await classic_audio.connect(route=True)
                remember_speaker_connection()
            elif settings.audio_output == "external_bluetooth":
                if settings.jaw_follow_speech and settings.hardware_profile != "dac":
                    try:
                        await classic_audio.connect(route=False)
                        remember_speaker_connection()
                    except ClassicAudioUnavailable:
                        pass
                try:
                    await external_audio.connect(route=True)
                except AudioOutputUnavailable:
                    pass
            elif settings.jaw_follow_speech and settings.hardware_profile != "dac":
                try:
                    await classic_audio.connect(route=False)
                    remember_speaker_connection()
                except ClassicAudioUnavailable:
                    pass
        finally:
            apply_audio_output_settings()

    async def start_operation_mode(selected_mode: str) -> dict[str, object]:
        """Prepare the selected operating mode in one ordered, explicit action."""

        async with operation_lock:
            settings = operation_store.load()
            steps: list[str] = []
            operation_state.update(
                active_mode="starting",
                ready=False,
                steps=steps,
                last_error=None,
            )
            try:
                await perception.stop()
                steps.append("Visitor listening reset")
                if not hardware.snapshot().connected:
                    await hardware.connect()
                remember_control_connection()
                settings = await apply_skelly_speaker_policy(settings)
                if settings.audio_output == "external_bluetooth" and settings.mute_skelly_speaker_on_external:
                    steps.append("Skelly speaker muted; jaw mirror remains active")
                steps.append("Prop BLE connected")
                await controller.set_interactive()
                steps.append("Local control enabled")
                await hardware.arm_movement(True)
                steps.append("Built-in motors armed")

                if settings.hardware_profile == "dac":
                    await dac.arm()
                    await dac.center()
                    steps.append("DAC armed; head centered; jaw closed")

                if selected_mode in {"ai", "manual"}:
                    await hardware.set_live_mode(True)
                    steps.append("Live Mode enabled")
                    await asyncio.sleep(0.8)
                    if settings.audio_output == "skelly":
                        steps.append("Skelly speaker recovery started in background")
                    elif settings.audio_output == "external_bluetooth":
                        steps.append("External audio and jaw mirror recovery started in background")
                    else:
                        steps.append("Pi / USB audio selected; jaw mirror recovery started in background")
                    asyncio.create_task(recover_audio_for_mode(settings))
                    apply_audio_output_settings()

                if selected_mode == "ai":
                    await perception.start()
                    steps.append("Camera and microphone visitor monitor started")

                operation_state.update(
                    active_mode=selected_mode,
                    ready=True,
                    steps=steps,
                    last_error=None,
                )
            except (
                HardwareUnavailable,
                ClassicAudioUnavailable,
                AudioOutputUnavailable,
                DacUnavailable,
                SensorUnavailable,
                InvalidTransition,
            ) as exc:
                operation_state.update(
                    active_mode="needs_attention",
                    ready=False,
                    steps=steps,
                    last_error=str(exc),
                )
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            return state_response()

    async def stop_operation_mode() -> dict[str, object]:
        async with operation_lock:
            await _cancel_operator_gesture()
            await perception.stop()
            try:
                if hardware.snapshot().connected:
                    await hardware.arm_movement(False)
            except HardwareUnavailable:
                pass
            await dac.release()
            try:
                await controller.set_idle()
            except InvalidTransition as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            operation_state.update(
                active_mode="standby",
                ready=False,
                steps=["Interaction stopped", "Motor outputs released"],
                last_error=None,
            )
            return state_response()

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/onboarding/status")
    async def onboarding_status() -> dict[str, object]:
        return onboarding.public_status(
            prop_configured=operation_store.load().device_configured
        )

    @app.get("/api/onboarding/wifi")
    async def onboarding_wifi_scan(request: Request) -> dict[str, object]:
        require_local_setup(request)
        try:
            return {"networks": onboarding.scan_wifi()}
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/system/wifi")
    async def wifi_status(request: Request) -> dict[str, object]:
        require_local_setup(request)
        return onboarding.wifi_status()

    @app.post("/api/system/wifi/refresh")
    async def wifi_refresh(request: Request) -> dict[str, object]:
        require_local_setup(request)
        try:
            onboarding.refresh_wifi()
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {
            "accepted": True,
            "message": "WiFi rescan scheduled; the setup hotspot will briefly restart",
        }

    @app.post("/api/system/wifi/hotspot")
    async def wifi_hotspot(request: Request) -> dict[str, object]:
        require_local_setup(request)
        try:
            state = onboarding.use_hotspot()
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {
            "accepted": True,
            "network_mode": state.network_mode,
            "message": "USA setup hotspot is active",
        }

    @app.post("/api/onboarding/offline")
    async def onboarding_offline(request: Request) -> dict[str, object]:
        require_local_setup(request)
        onboarding.choose_offline()
        return onboarding.public_status(prop_configured=False)

    @app.post("/api/onboarding/wifi")
    async def onboarding_wifi(
        setup: WifiConnectRequest, request: Request
    ) -> dict[str, object]:
        require_local_setup(request)
        try:
            onboarding.connect_wifi(setup.ssid, setup.password.get_secret_value())
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return onboarding.public_status(prop_configured=False)

    @app.post("/api/onboarding/disclaimer")
    async def onboarding_disclaimer(
        setup: DisclaimerRequest, request: Request
    ) -> dict[str, object]:
        require_local_setup(request)
        if not setup.accepted:
            raise HTTPException(status_code=400, detail="Acceptance is required")
        onboarding.accept_disclaimer()
        return onboarding.public_status(
            prop_configured=operation_store.load().device_configured
        )

    @app.get("/api/system/ssh")
    async def ssh_status(request: Request) -> dict[str, object]:
        require_local_setup(request)
        return onboarding.ssh_status()

    @app.post("/api/system/ssh/enable")
    async def ssh_enable(
        setup: SshEnableRequest, request: Request
    ) -> dict[str, object]:
        require_local_setup(request)
        try:
            return onboarding.enable_ssh(
                setup.password.get_secret_value(), persistent=setup.persistent
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/system/ssh/disable")
    async def ssh_disable(request: Request) -> dict[str, object]:
        require_local_setup(request)
        try:
            return onboarding.disable_ssh()
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/system/service/restart")
    async def restart_service(request: Request) -> dict[str, object]:
        require_local_setup(request)
        try:
            onboarding.system_action("service-restart")
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {"accepted": True, "message": "USA service restart scheduled"}

    @app.post("/api/system/reboot")
    async def reboot_controller(request: Request) -> dict[str, object]:
        require_local_setup(request)
        try:
            onboarding.system_action("reboot")
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {"accepted": True, "message": "Raspberry Pi reboot scheduled"}

    @app.post("/api/system/shutdown")
    async def shutdown_controller(request: Request) -> dict[str, object]:
        require_local_setup(request)
        try:
            onboarding.system_action("shutdown")
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {"accepted": True, "message": "Raspberry Pi shutdown scheduled"}

    def update_status_payload(
        *,
        latest_version: str | None = None,
        download_url: str | None = None,
        release_notes_url: str | None = None,
        installable: bool = False,
        message: str | None = None,
    ) -> dict[str, object]:
        def version_parts(value: str) -> tuple[int, ...]:
            numbers = re.findall(r"\d+", value)
            return tuple(int(number) for number in numbers[:4])

        available = bool(
            latest_version
            and version_parts(latest_version) > version_parts(__version__)
        )
        return {
            "current_version": __version__,
            "channel_configured": bool(app_settings.update_manifest_url),
            "update_available": available,
            "latest_version": latest_version,
            "download_url": download_url if available else None,
            "release_notes_url": release_notes_url,
            "installable": bool(available and installable),
            "installation": updates.status(),
            "rollback": updates.rollback_status(current_version=__version__),
            "message": message
            or (
                "USA release channel ready. Check for updates when this Pi is online."
                if app_settings.update_manifest_url
                else "No release channel is configured yet; install signed release packages manually."
            ),
        }

    @app.get("/api/update/status")
    async def update_status() -> dict[str, object]:
        return update_status_payload()

    async def read_update_manifest() -> dict[str, object]:
        manifest_url = app_settings.update_manifest_url
        if not manifest_url:
            raise HTTPException(status_code=409, detail="No USA release channel is configured")
        try:
            async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
                response = await client.get(manifest_url)
                response.raise_for_status()
                manifest = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(
                status_code=503,
                detail="The Pi could not read the configured USA release channel",
            ) from exc
        if not isinstance(manifest, dict):
            raise HTTPException(status_code=502, detail="The update manifest is invalid")
        return manifest

    @app.post("/api/update/check")
    async def check_for_update() -> dict[str, object]:
        if not app_settings.update_manifest_url:
            return update_status_payload()
        manifest = await read_update_manifest()
        latest = str(manifest.get("version", "")).strip()
        if not latest:
            raise HTTPException(status_code=502, detail="The update manifest has no version")
        payload = update_status_payload(
            latest_version=latest,
            download_url=str(manifest.get("download_url") or "").strip() or None,
            release_notes_url=(
                str(manifest.get("release_notes_url") or "").strip() or None
            ),
            installable=bool(manifest.get("package_url") and manifest.get("sha256")),
        )
        if payload["update_available"]:
            payload["message"] = f"USA {latest} is available."
        else:
            payload["message"] = "This Pi is running the latest published version."
        return payload

    @app.get("/api/update/install-status")
    async def update_install_status() -> dict[str, object]:
        return updates.status()

    @app.post("/api/update/install")
    async def install_update(request: Request) -> dict[str, object]:
        require_local_setup(request)
        manifest = await read_update_manifest()
        latest = str(manifest.get("version") or "").strip()
        availability = update_status_payload(latest_version=latest)
        if not availability["update_available"]:
            raise HTTPException(status_code=409, detail="This Pi is already up to date")
        try:
            return await updates.stage_and_start(manifest, current_version=__version__)
        except UpdateError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/update/rollback")
    async def rollback_update(request: Request) -> dict[str, object]:
        require_local_setup(request)
        try:
            return updates.start_rollback(current_version=__version__)
        except UpdateError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/status")
    async def get_status() -> dict[str, object]:
        return state_response()

    @app.get("/api/config/public")
    async def public_config() -> dict[str, object]:
        result = app_settings.public_dict()
        credential_status = credential_store.status()
        result["elevenlabs_configured"] = credential_status.key_configured
        result["elevenlabs_key_configured"] = credential_status.key_configured
        result["groq_key_configured"] = credential_store.groq_status().key_configured
        result["providers"] = provider_store.load().model_dump()
        return result

    @app.get("/api/providers/status")
    async def provider_status() -> dict[str, object]:
        settings = provider_store.load()
        return {
            "settings": settings.model_dump(),
            "groq": credential_store.groq_status().to_dict(),
            "elevenlabs": credential_store.status().to_dict(),
            "local_voice": local_speech.status(),
            "local_voices": [
                "en-us+m1",
                "en-us+m2",
                "en-us+m3",
                "en-us+m4",
                "en-us+m5",
                "en-us+m6",
                "en-us+m7",
                "en-us+croak",
                "en-us+whisper",
                "en-gb+m3",
            ],
            "groq_voices": ["troy", "daniel", "austin", "hannah", "diana", "autumn"],
            "cloud_usage_warning": (
                "Cloud voice previews and spoken responses may consume provider quota."
            ),
        }

    @app.post("/api/providers/settings")
    async def save_provider_settings(
        setup: ProviderSettings,
    ) -> dict[str, object]:
        saved = provider_store.save(setup)
        apply_local_voice_settings(saved)
        # Provider changes are hot-applied and must never change physical audio
        # routing or Skelly speaker policy. Re-assert the current output/jaw
        # mirror configuration without reconnecting or restarting either audio session.
        apply_audio_output_settings()
        return saved.model_dump()

    @app.get("/api/operation/status")
    async def operation_status() -> dict[str, object]:
        return {
            **operation_state,
            "settings": operation_store.load().model_dump(),
        }

    @app.post("/api/operation/settings")
    async def save_operation_settings(
        setup: OperationSettings,
    ) -> dict[str, object]:
        previous = operation_store.load()
        # The restore volume is internal state; older/newer UIs may omit it.
        # Preserve the server-side value unless this request explicitly carries
        # a different value.
        if setup.skelly_speaker_restore_volume == OperationSettings().skelly_speaker_restore_volume:
            setup = setup.model_copy(
                update={"skelly_speaker_restore_volume": previous.skelly_speaker_restore_volume}
            )
        saved = operation_store.save(setup)
        external_audio.set_saved_target(
            saved.external_bluetooth_address,
            saved.external_bluetooth_name,
        )
        sensors.voice_threshold_dbfs = listening_sensitivity_to_dbfs(
            saved.listening_sensitivity
        )
        saved = await apply_skelly_speaker_policy(saved, previous=previous)
        apply_audio_output_settings()
        return saved.model_dump()

    @app.post("/api/operation/start")
    async def start_operation(request: OperationStartRequest) -> dict[str, object]:
        require_manual_hardware_access()
        return await start_operation_mode(request.mode)

    @app.post("/api/operation/stop")
    async def stop_operation() -> dict[str, object]:
        return await stop_operation_mode()

    @app.post("/api/setup/forget-skelly")
    async def forget_skelly() -> dict[str, object]:
        """Release this prop and remove its saved control and speaker bindings."""

        async with operation_lock:
            warnings: list[str] = []
            steps = ["Visitor interaction stopped"]
            await _cancel_operator_gesture()
            await perception.stop()
            try:
                if hardware.snapshot().connected:
                    await hardware.arm_movement(False)
            except HardwareUnavailable:
                pass
            await dac.release()
            steps.append("Motor outputs released")

            forget_audio = getattr(classic_audio, "forget", None)
            try:
                if forget_audio is not None:
                    await forget_audio()
                else:
                    await classic_audio.disconnect()
                steps.append("Speaker disconnected and pairing removed")
            except ClassicAudioUnavailable as exc:
                clear_audio_target = getattr(classic_audio, "clear_saved_target", None)
                if clear_audio_target is not None:
                    clear_audio_target()
                warnings.append(str(exc))
                steps.append("Saved speaker target cleared")

            forget_hardware = getattr(hardware, "forget", None)
            if forget_hardware is not None:
                await forget_hardware()
            else:
                await hardware.disconnect()
            steps.append("Prop control disconnected and forgotten")

            settings = operation_store.load()
            operation_store.save(
                settings.model_copy(
                    update={
                        "auto_start": False,
                        "device_configured": False,
                        "control_address": None,
                        "speaker_address": None,
                    }
                )
            )
            try:
                await controller.set_idle()
            except InvalidTransition:
                pass
            operation_state.update(
                active_mode="standby",
                ready=False,
                steps=steps,
                last_error="; ".join(warnings) if warnings else None,
            )
            response = state_response()
            response["forgotten"] = True
            response["warnings"] = warnings
            return response

    @app.get("/api/setup/groq/status")
    async def groq_status() -> dict[str, object]:
        return credential_store.groq_status().to_dict()

    @app.post("/api/setup/groq")
    async def configure_groq(
        setup: GroqSetupRequest,
        request: Request,
    ) -> dict[str, object]:
        require_local_setup(request)
        try:
            await groq_credential_validator(setup.api_key)
            return credential_store.save_groq(setup.api_key).to_dict()
        except CredentialValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except CredentialStoreError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/api/voice/preview")
    async def preview_voice(setup: VoicePreviewRequest) -> dict[str, object]:
        require_manual_conversation_access()
        try:
            return await speak_selected(setup.text, allow_fallback=False)
        except SpeechUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/setup/elevenlabs/status")
    async def elevenlabs_status() -> dict[str, object]:
        return credential_store.status().to_dict()

    @app.get("/api/providers/elevenlabs/account")
    async def elevenlabs_account() -> dict[str, object]:
        credentials = credential_store.load()
        cached = load_elevenlabs_cache()
        if credentials.api_key is None:
            return {**cached, "available": False, "cached": bool(cached.get("voices")), "error": "ElevenLabs key not saved"}
        try:
            payload = await fetch_elevenlabs_account(credentials.api_key)
            save_elevenlabs_cache(payload)
            return {**payload, "available": True, "cached": False}
        except CredentialValidationError as exc:
            return {**cached, "available": False, "cached": bool(cached.get("voices")), "error": str(exc)}

    @app.get("/api/providers/groq/quota")
    async def groq_quota() -> dict[str, object]:
        credentials = credential_store.load()
        if credentials.groq_api_key is None:
            return {"limit": None, "remaining": None, "remaining_percent": None, "available": False, "error": "Groq key not saved"}
        try:
            payload = await fetch_groq_quota(credentials.groq_api_key)
            return {**payload, "available": True}
        except CredentialValidationError as exc:
            return {"limit": None, "remaining": None, "remaining_percent": None, "available": False, "error": str(exc)}

    @app.post("/api/setup/elevenlabs")
    async def configure_elevenlabs(
        setup: ElevenLabsSetupRequest,
        request: Request,
    ) -> dict[str, object]:
        require_local_setup(request)
        try:
            await credential_validator(setup.api_key)
            saved = credential_store.save_elevenlabs(setup.api_key)
        except CredentialValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except CredentialStoreError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return saved.to_dict()

    @app.post("/api/mode/idle")
    async def set_idle() -> dict[str, object]:
        try:
            await dac.release()
            await controller.set_idle()
            await hardware.stop()
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return state_response()

    @app.post("/api/mode/interactive")
    async def set_interactive() -> dict[str, object]:
        try:
            await controller.set_interactive()
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return state_response()

    @app.post("/api/show/start")
    async def begin_show(
        request: ShowRequest,
        x_skelly_token: str | None = Header(default=None),
    ) -> dict[str, object]:
        require_fpp_token(x_skelly_token)
        try:
            await dac.release()
            await hardware.stop()
            await controller.begin_show(request.name)
            operation_state.update(
                active_mode="show",
                ready=True,
                steps=["Local output released", "FPP/xLights has control"],
                last_error=None,
            )
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return state_response()

    @app.post("/api/show/end")
    async def end_show(
        x_skelly_token: str | None = Header(default=None),
    ) -> dict[str, object]:
        require_fpp_token(x_skelly_token)
        await controller.end_show()
        operation_state.update(
            active_mode="standby",
            ready=False,
            steps=["Show ended", "Select an operating mode to resume"],
            last_error=None,
        )
        return state_response()

    @app.get("/api/diagnostics")
    async def diagnostics() -> dict[str, object]:
        return await collect_diagnostics()

    @app.get("/api/sensors/status")
    async def sensor_status() -> dict[str, object]:
        return sensors.status()

    @app.get("/api/perception/status")
    async def perception_status() -> dict[str, object]:
        return perception.status()

    @app.get("/api/brain/status")
    async def brain_status() -> dict[str, object]:
        settings = provider_store.load()
        if settings.brain_provider == "groq":
            result = groq_brain.status(credential_store.load().groq_api_key)
        else:
            result = await brain.status()
            result["provider"] = "local"
        result["local_speech"] = local_speech.status()
        result["voice_provider"] = settings.voice_provider
        return result

    @app.get("/api/audio/output/status")
    async def audio_output_status() -> dict[str, object]:
        settings = operation_store.load()
        external = await external_audio.refresh()
        skelly = await classic_audio.refresh()
        apply_audio_output_settings()
        return {
            "selected": settings.audio_output,
            "jaw_follow_speech": settings.jaw_follow_speech,
            "jaw_sync_offset_ms": settings.jaw_sync_offset_ms,
            "skelly": skelly.to_dict(),
            "external_bluetooth": external.to_dict(),
        }

    @app.post("/api/audio/external/scan")
    async def external_audio_scan() -> dict[str, object]:
        require_manual_hardware_access()
        try:
            devices = await external_audio.scan()
        except AudioOutputUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        # Skelly's own Classic endpoint has dedicated pairing controls; omit it here.
        skelly_name_filter = app_settings.classic_audio_name.casefold()
        devices = [
            device for device in devices
            if skelly_name_filter not in str(device.get("name", "")).casefold()
        ]
        return {"devices": devices}

    @app.post("/api/audio/external/select")
    async def external_audio_select(setup: ExternalBluetoothSelectRequest) -> dict[str, object]:
        require_manual_hardware_access()
        try:
            snapshot = await external_audio.prepare(setup.address)
        except AudioOutputUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        settings = operation_store.load()
        saved = operation_store.save(
            settings.model_copy(
                update={
                    "audio_output": "external_bluetooth",
                    "external_bluetooth_address": snapshot.address,
                    "external_bluetooth_name": snapshot.device_name,
                }
            )
        )
        external_audio.set_saved_target(snapshot.address, snapshot.device_name)
        if saved.jaw_follow_speech and saved.hardware_profile != "dac":
            try:
                await classic_audio.connect(route=False)
                remember_speaker_connection()
            except ClassicAudioUnavailable:
                pass
        saved = await apply_skelly_speaker_policy(saved, previous=settings)
        apply_audio_output_settings()
        return {
            "settings": saved.model_dump(),
            "external_bluetooth": snapshot.to_dict(),
        }

    @app.post("/api/audio/external/connect")
    async def external_audio_connect() -> dict[str, object]:
        require_manual_hardware_access()
        try:
            snapshot = await external_audio.connect(route=True)
        except AudioOutputUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        apply_audio_output_settings()
        return snapshot.to_dict()

    @app.post("/api/audio/external/disconnect")
    async def external_audio_disconnect() -> dict[str, object]:
        require_manual_hardware_access()
        try:
            snapshot = await external_audio.disconnect()
        except AudioOutputUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        apply_audio_output_settings()
        return snapshot.to_dict()

    @app.post("/api/audio/external/forget")
    async def external_audio_forget() -> dict[str, object]:
        require_manual_hardware_access()
        try:
            snapshot = await external_audio.forget()
        except AudioOutputUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        settings = operation_store.load()
        saved = operation_store.save(
            settings.model_copy(
                update={
                    "audio_output": "skelly",
                    "external_bluetooth_address": None,
                    "external_bluetooth_name": None,
                }
            )
        )
        saved = await apply_skelly_speaker_policy(saved, previous=settings)
        apply_audio_output_settings()
        return {"settings": saved.model_dump(), "external_bluetooth": snapshot.to_dict()}

    @app.get("/api/audio/status")
    async def classic_audio_status() -> dict[str, object]:
        return (await classic_audio.refresh()).to_dict()

    @app.post("/api/audio/connect")
    async def classic_audio_connect() -> dict[str, object]:
        require_manual_hardware_access()
        try:
            snapshot = await classic_audio.connect()
            remember_speaker_connection()
            return snapshot.to_dict()
        except ClassicAudioUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/audio/prepare-connect")
    async def prepare_and_connect_classic_audio() -> dict[str, object]:
        """Enable Live Mode, pair when needed, then route the Classic speaker."""

        require_manual_hardware_access()
        try:
            await hardware.set_live_mode(True)
            await asyncio.sleep(0.8)
            prepare = getattr(classic_audio, "prepare", None)
            snapshot = (
                await prepare(app_settings.classic_audio_pin)
                if prepare is not None
                else await classic_audio.connect()
            )
            if snapshot.connected and not snapshot.sink_ready:
                # On a fresh Classic connection BlueZ can report connected
                # before WirePlumber publishes the A2DP sink.  Releasing the
                # prepare lock and beginning a second routing pass is the same
                # transition owners previously achieved with a second button
                # click, so keep it inside this one request.
                snapshot = await classic_audio.refresh()
                if not snapshot.sink_ready:
                    snapshot = await classic_audio.connect()
            remember_speaker_connection()
            return snapshot.to_dict()
        except (HardwareUnavailable, ClassicAudioUnavailable) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/audio/disconnect")
    async def classic_audio_disconnect() -> dict[str, object]:
        require_manual_hardware_access()
        try:
            return (await classic_audio.disconnect()).to_dict()
        except ClassicAudioUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/operator/speak")
    async def operator_speak(request: OperatorSpeakRequest) -> dict[str, object]:
        require_operator_mode()
        try:
            speech = await speak_selected(request.text)
        except SpeechUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {
            "spoken_text": request.text,
            "spoken_response": request.text,
            "speech": speech,
        }

    @app.post("/api/operator/gesture")
    async def operator_gesture(
        request: OperatorGestureRequest,
    ) -> dict[str, object]:
        nonlocal operator_gesture_task
        require_operator_mode()
        settings = operation_store.load()
        if request.gesture != "laugh" and settings.hardware_profile != "dac":
            raise HTTPException(
                status_code=409,
                detail="This precise head gesture requires the Advanced DAC profile",
            )
        async with operator_gesture_lock:
            await _cancel_operator_gesture()
            task = asyncio.create_task(_perform_operator_gesture(request.gesture))
            operator_gesture_task = task
        try:
            return await task
        except (DacUnavailable, HardwareUnavailable, SpeechUnavailable) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        finally:
            async with operator_gesture_lock:
                if operator_gesture_task is task:
                    operator_gesture_task = None

    @app.post("/api/operator/gesture/stop")
    async def stop_operator_gesture() -> dict[str, object]:
        require_operator_mode()
        async with operator_gesture_lock:
            cancelled = await _cancel_operator_gesture()
        try:
            await hardware.stop()
        except HardwareUnavailable:
            pass
        return {"stopped": True, "gesture_cancelled": cancelled}

    @app.post("/api/perception/start")
    async def perception_start() -> dict[str, object]:
        try:
            return await perception.start()
        except SensorUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/perception/stop")
    async def perception_stop() -> dict[str, object]:
        return await perception.stop()

    @app.post("/api/perception/events/clear")
    async def perception_clear_events() -> dict[str, object]:
        return perception.clear_events()

    @app.get("/api/perception/snapshots/{filename}")
    async def perception_snapshot(filename: str) -> FileResponse:
        if not re.fullmatch(r"event-\d{6}-session-\d{4}-turn-\d{3}\.jpg", filename):
            raise HTTPException(status_code=404, detail="Snapshot not found")
        path = interaction_snapshot_dir / filename
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Snapshot not found")
        return FileResponse(
            path,
            media_type="image/jpeg",
            headers={"Cache-Control": "private, max-age=86400"},
        )

    @app.get("/api/sensors/camera/frame.jpg")
    async def camera_frame() -> Response:
        try:
            jpeg = await sensors.analyze_camera()
        except SensorUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return Response(
            content=jpeg,
            media_type="image/jpeg",
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/api/sensors/microphone/sample")
    async def microphone_sample() -> dict[str, object]:
        try:
            return await sensors.sample_microphone()
        except SensorUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/sensors/microphone/transcribe")
    async def microphone_transcribe(
        request: MicrophoneTranscriptionRequest,
    ) -> dict[str, object]:
        try:
            return await sensors.transcribe_microphone(request.duration_seconds)
        except SensorUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/sensors/microphone/last.wav")
    async def microphone_last_sample() -> Response:
        audio = sensors.last_audio_wav()
        if audio is None:
            raise HTTPException(status_code=404, detail="No microphone sample exists yet")
        return Response(
            content=audio,
            media_type="audio/wav",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/hardware/status")
    async def hardware_status() -> dict[str, object]:
        return hardware.snapshot().to_dict()

    @app.get("/api/media/status")
    async def media_status() -> dict[str, object]:
        return enrich_media_status(hardware.media_status())

    @app.post("/api/media/refresh")
    async def media_refresh() -> dict[str, object]:
        require_manual_hardware_access()
        try:
            return enrich_media_status(await hardware.refresh_media_files())
        except HardwareUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/media/play")
    async def media_play(request: MediaPlayRequest) -> dict[str, object]:
        require_manual_hardware_access()
        try:
            return enrich_media_status(await hardware.play_media(request.serial, request.enabled))
        except HardwareUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/media/volume")
    async def media_volume(request: MediaVolumeRequest) -> dict[str, object]:
        require_manual_hardware_access()
        settings = operation_store.load()
        try:
            if settings.audio_output == "external_bluetooth" and settings.mute_skelly_speaker_on_external:
                operation_store.save(
                    settings.model_copy(update={"skelly_speaker_restore_volume": request.volume})
                )
                status = hardware.media_status()
                if int(status.get("volume", 0) or 0) != 0:
                    status = await hardware.set_volume(0)
                result = enrich_media_status(status)
                result["external_auto_muted"] = True
                result["restore_volume"] = request.volume
                return result
            status = await hardware.set_volume(request.volume)
            operation_store.save(
                settings.model_copy(update={"skelly_speaker_restore_volume": request.volume})
            )
            return enrich_media_status(status)
        except HardwareUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/hardware/lighting")
    async def hardware_lighting(request: LightingRequest) -> dict[str, object]:
        require_manual_hardware_access()
        try:
            return await hardware.set_lighting(
                request.channel,
                request.brightness,
                request.r,
                request.g,
                request.b,
                request.effect_mode,
                request.cycle,
            )
        except (HardwareUnavailable, ValueError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/media/edit")
    async def media_edit(request: MediaEditRequest) -> dict[str, object]:
        require_manual_hardware_access()
        try:
            status = await hardware.edit_media(
                request.serial,
                request.action,
                request.eye,
                request.head_light.model_dump(),
                request.torso_light.model_dump(),
            )
            serials = load_nag_media_serials()
            if request.nag_response:
                serials.add(request.serial)
            else:
                serials.discard(request.serial)
            save_nag_media_serials(serials)
            return enrich_media_status(status)
        except (HardwareUnavailable, ValueError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/media/enabled")
    async def media_enabled(request: MediaEnabledRequest) -> dict[str, object]:
        require_manual_hardware_access()
        try:
            return enrich_media_status(await hardware.set_media_enabled(request.serial, request.enabled))
        except HardwareUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/media/upload")
    async def media_upload(request: Request, filename: str) -> dict[str, object]:
        require_manual_hardware_access()
        clean_name = Path(filename).name.strip()
        if not clean_name or len(clean_name) > 120:
            raise HTTPException(status_code=422, detail="Choose a valid audio filename")
        data = await request.body()
        if len(data) > 8 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Audio files must be 8 MB or smaller")
        try:
            return await hardware.upload_media(clean_name, data)
        except HardwareUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/dac/status")
    async def dac_status() -> dict[str, object]:
        return dac.snapshot().to_dict()

    @app.post("/api/dac/arm")
    async def arm_dac(request: DacArmRequest) -> dict[str, object]:
        if not request.enabled:
            return (await dac.release()).to_dict()
        require_manual_hardware_access()
        return (await dac.arm()).to_dict()

    @app.post("/api/dac/position")
    async def set_dac_position(request: DacPositionRequest) -> dict[str, object]:
        require_manual_hardware_access()
        if all(
            value is None
            for value in (request.jaw, request.tilt, request.yaw, request.pitch)
        ):
            raise HTTPException(
                status_code=422,
                detail="Supply at least one jaw or head position",
            )
        try:
            snapshot = await dac.set_position(**request.model_dump())
        except (DacUnavailable, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return snapshot.to_dict()

    @app.post("/api/dac/center")
    async def center_dac() -> dict[str, object]:
        require_manual_hardware_access()
        try:
            snapshot = await dac.center()
        except DacUnavailable as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return snapshot.to_dict()

    @app.post("/api/dac/release")
    async def release_dac() -> dict[str, object]:
        return (await dac.release()).to_dict()

    @app.post("/api/hardware/discover")
    async def discover_hardware() -> dict[str, object]:
        if app_settings.onboarding_required and not onboarding.load().disclaimer_accepted:
            raise HTTPException(status_code=409, detail="Complete the safety disclosure first")
        try:
            if app_settings.onboarding_required:
                onboarding.prepare_bluetooth()
            devices = await discover_skelly_devices(timeout=8.0)
        except Exception as exc:
            raise HTTPException(
                status_code=503, detail=f"BLE discovery failed: {exc}"
            ) from exc
        return {"devices": devices}

    @app.post("/api/hardware/connect")
    async def connect_hardware(
        request: HardwareConnectRequest,
    ) -> dict[str, object]:
        if app_settings.onboarding_required and not onboarding.load().disclaimer_accepted:
            raise HTTPException(status_code=409, detail="Complete the safety disclosure first")
        try:
            snapshot = await hardware.connect(request.address)
            remember_control_connection()
            await apply_skelly_speaker_policy(operation_store.load())
        except HardwareUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return snapshot.to_dict()

    @app.post("/api/hardware/disconnect")
    async def disconnect_hardware() -> dict[str, object]:
        return (await hardware.disconnect()).to_dict()

    @app.post("/api/hardware/eye")
    async def set_eye(request: EyeRequest) -> dict[str, object]:
        require_manual_hardware_access()
        try:
            snapshot = await hardware.set_eye(request.icon)
        except HardwareUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return snapshot.to_dict()

    @app.post("/api/hardware/eye-index")
    async def set_eye_index(request: EyeIndexRequest) -> dict[str, object]:
        require_manual_hardware_access()
        try:
            snapshot = await hardware.set_eye_index(request.index)
        except HardwareUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return snapshot.to_dict()

    @app.post("/api/hardware/movement")
    async def set_movement(request: MovementRequest) -> dict[str, object]:
        require_manual_hardware_access()
        try:
            snapshot = await hardware.set_movement(request.movement)
        except HardwareUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return snapshot.to_dict()

    @app.post("/api/hardware/movement-arm")
    async def arm_movement(request: MovementArmRequest) -> dict[str, object]:
        require_manual_hardware_access()
        try:
            snapshot = await hardware.arm_movement(request.enabled)
        except HardwareUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return snapshot.to_dict()

    @app.post("/api/diagnostics/ble-movement-probe")
    async def probe_ble_movement(
        request: MovementProbeRequest,
    ) -> dict[str, object]:
        require_developer_mode()
        require_manual_hardware_access()
        if not request.acknowledged:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Confirm the prop is clear and the power switch is within reach"
                ),
            )
        try:
            snapshot = await hardware.probe_movement_bit(
                request.action, request.duration_ms
            )
        except (HardwareUnavailable, ValueError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {
            "probe": f"0x{request.action:02X}",
            "duration_ms": request.duration_ms,
            "stopped": True,
            "hardware": snapshot.to_dict(),
        }

    @app.post("/api/hardware/live-mode")
    async def set_live_mode(request: LiveModeRequest) -> dict[str, object]:
        require_manual_hardware_access()
        try:
            snapshot = await hardware.set_live_mode(request.enabled)
        except HardwareUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return snapshot.to_dict()

    @app.post("/api/hardware/stop")
    async def stop_hardware() -> dict[str, object]:
        try:
            snapshot = await hardware.stop()
        except HardwareUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return snapshot.to_dict()

    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/generate_204", include_in_schema=False)
    @app.get("/gen_204", include_in_schema=False)
    @app.get("/hotspot-detect.html", include_in_schema=False)
    @app.get("/library/test/success.html", include_in_schema=False)
    @app.get("/ncsi.txt", include_in_schema=False)
    @app.get("/connecttest.txt", include_in_schema=False)
    @app.get("/canonical.html", include_in_schema=False)
    @app.get("/success.txt", include_in_schema=False)
    @app.get("/redirect", include_in_schema=False)
    async def captive_portal_probe() -> RedirectResponse:
        return RedirectResponse(url="http://192.168.4.1/", status_code=302)

    return app


app = create_app()
