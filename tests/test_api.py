import json
import os
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from skelly_ai.api import create_app
from skelly_ai.brain import BrainReply
from skelly_ai.config import Settings
from skelly_ai.credentials import CredentialValidationError
from skelly_ai.hardware import Movement, SimulatedSkelly


class FakeBrain:
    def __init__(self) -> None:
        self.histories: list[list[dict[str, str]]] = []

    async def status(self) -> dict[str, object]:
        return {"available": True, "model": "test", "local_only": True}

    async def respond(self, visitor_text: str, history=()) -> BrainReply:
        assert visitor_text
        self.histories.append(list(history))
        lowered = visitor_text.lower()
        if "knock knock" in lowered:
            spoken_response = "Who's there?"
        elif lowered == "boo" and history:
            spoken_response = "Aw, you got me!"
        else:
            spoken_response = "Welcome, brave visitor!"
        return BrainReply(
            spoken_response=spoken_response,
            eye_icon="angry",
            movement="head_only",
        )


def test_health_and_show_lock_flow(tmp_path) -> None:
    app = create_app(
        Settings(data_dir=tmp_path, fpp_token=SecretStr("test-token"))
    )

    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        assert client.post("/api/mode/interactive").status_code == 200
        client.post(
            "/api/operation/settings",
            json={
                "hardware_profile": "dac",
                "default_mode": "ai",
                "allow_fpp_override": True,
            },
        )
        client.post("/api/hardware/connect", json={})

        unauthorized = client.post("/api/show/start", json={"name": "Test"})
        assert unauthorized.status_code == 401

        headers = {"X-Skelly-Token": "test-token"}
        started = client.post(
            "/api/show/start", json={"name": "Test"}, headers=headers
        )
        assert started.json()["state"]["mode"] == "show_locked"

        blocked = client.post("/api/mode/interactive")
        assert blocked.status_code == 409

        ended = client.post("/api/show/end", headers=headers)
        assert ended.json()["state"]["mode"] == "interactive"


def test_captive_portal_detection_routes_open_setup_dashboard(tmp_path) -> None:
    app = create_app(Settings(data_dir=tmp_path))

    with TestClient(app, follow_redirects=False) as client:
        for path in (
            "/generate_204",
            "/gen_204",
            "/hotspot-detect.html",
            "/library/test/success.html",
            "/connecttest.txt",
            "/ncsi.txt",
            "/canonical.html",
            "/success.txt",
            "/redirect",
        ):
            response = client.get(path)
            assert response.status_code == 302
            assert response.headers["location"] == "http://192.168.4.1/"


def test_simulated_hardware_commands_respect_show_lock(tmp_path) -> None:
    app = create_app(Settings(data_dir=tmp_path))

    with TestClient(app) as client:
        client.post(
            "/api/operation/settings",
            json={
                "hardware_profile": "dac",
                "default_mode": "ai",
                "allow_fpp_override": True,
            },
        )
        client.post("/api/hardware/connect", json={})
        eye = client.post("/api/hardware/eye", json={"icon": "angry"})
        assert eye.status_code == 200
        assert eye.json()["eye_icon"] == "angry"

        movement = client.post(
            "/api/hardware/movement", json={"movement": "head_only"}
        )
        assert movement.status_code == 200
        assert movement.json()["movement"] == "head_only"

        assert client.post("/api/show/start", json={"name": "Test"}).status_code == 200

        blocked = client.post("/api/hardware/eye", json={"icon": "hearts"})
        assert blocked.status_code == 409
        assert "blocked during a show" in blocked.json()["detail"]

        stopped = client.post("/api/hardware/stop")
        assert stopped.status_code == 200
        assert stopped.json()["movement"] == "none"


def test_guided_classic_mode_and_media_library(tmp_path) -> None:
    app = create_app(Settings(data_dir=tmp_path))

    with TestClient(app) as client:
        saved = client.post(
            "/api/operation/settings",
            json={
                "hardware_profile": "stock",
                "default_mode": "classic",
                "allow_fpp_override": False,
            },
        )
        started = client.post("/api/operation/start", json={"mode": "classic"})
        media = client.post("/api/media/refresh")
        played = client.post(
            "/api/media/play", json={"serial": 1, "enabled": True}
        )
        volume = client.post("/api/media/volume", json={"volume": 96})
        lighting = client.post(
            "/api/hardware/lighting",
            json={
                "channel": 0,
                "brightness": 180,
                "r": 20,
                "g": 80,
                "b": 255,
                "effect_mode": 1,
                "cycle": False,
            },
        )
        edited = client.post(
            "/api/media/edit",
            json={
                "serial": 1,
                "action": 2,
                "eye": 15,
                "head_light": {
                    "brightness": 200,
                    "r": 255,
                    "g": 20,
                    "b": 40,
                    "effect_mode": 2,
                    "cycle": False,
                },
                "torso_light": {
                    "brightness": 160,
                    "r": 20,
                    "g": 40,
                    "b": 255,
                    "effect_mode": 1,
                    "cycle": True,
                },
            },
        )
        disabled = client.post(
            "/api/media/enabled", json={"serial": 1, "enabled": False}
        )
        uploaded = client.post(
            "/api/media/upload?filename=Test%20Greeting.mp3",
            content=b"simulated mp3 data",
        )
        stopped = client.post("/api/operation/stop")

    assert saved.status_code == 200
    assert saved.json()["default_mode"] == "classic"
    assert started.status_code == 200
    assert started.json()["operation"]["active_mode"] == "classic"
    assert started.json()["operation"]["ready"] is True
    assert "Prop BLE connected" in started.json()["operation"]["steps"]
    assert media.status_code == 200
    assert media.json()["file_count"] > 0
    assert played.json()["playing_serial"] == 1
    assert volume.json()["volume"] == 96
    assert lighting.status_code == 200
    assert lighting.json()["lights"]["torso"]["brightness"] == 180
    assert edited.status_code == 200
    assert edited.json()["files"][0]["eye"] == 15
    assert disabled.status_code == 200
    assert disabled.json()["files"][0]["enabled"] is False
    assert uploaded.status_code == 200
    assert uploaded.json()["files"][-1]["name"] == "Test Greeting.mp3"
    assert stopped.json()["operation"]["active_mode"] == "standby"


def test_saved_startup_choices_and_forget_release_both_connections(tmp_path) -> None:
    app = create_app(Settings(data_dir=tmp_path))

    with TestClient(app) as client:
        saved = client.post(
            "/api/operation/settings",
            json={
                "hardware_profile": "dac",
                "default_mode": "ai",
                "auto_start": True,
                "device_configured": True,
                "allow_fpp_override": False,
            },
        )
        connected = client.post("/api/hardware/connect", json={})
        speaker = client.post("/api/audio/prepare-connect")
        forgotten = client.post("/api/setup/forget-skelly")

    assert saved.status_code == 200
    assert saved.json()["auto_start"] is True
    assert connected.status_code == 200
    assert speaker.status_code == 200
    assert speaker.json()["connected"] is True
    assert forgotten.status_code == 200
    assert forgotten.json()["forgotten"] is True
    assert forgotten.json()["hardware"]["connected"] is False
    assert forgotten.json()["audio"]["connected"] is False
    assert forgotten.json()["audio"]["paired"] is False
    assert forgotten.json()["operation"]["settings"]["device_configured"] is False
    assert forgotten.json()["operation"]["settings"]["auto_start"] is False
    assert "Prop control disconnected and forgotten" in forgotten.json()["operation"]["steps"]


def test_fpp_override_is_disabled_until_enabled(tmp_path) -> None:
    app = create_app(Settings(data_dir=tmp_path))

    with TestClient(app) as client:
        blocked = client.post("/api/show/start", json={"name": "Test"})
        stock_settings = client.post(
            "/api/operation/settings",
            json={
                "hardware_profile": "stock",
                "default_mode": "ai",
                "allow_fpp_override": True,
            },
        )
        still_blocked = client.post("/api/show/start", json={"name": "Test"})
        client.post(
            "/api/operation/settings",
            json={
                "hardware_profile": "dac",
                "default_mode": "ai",
                "allow_fpp_override": True,
            },
        )
        client.post("/api/hardware/connect", json={})
        allowed = client.post("/api/show/start", json={"name": "Test"})

    assert blocked.status_code == 409
    assert "disabled" in blocked.json()["detail"]
    assert stock_settings.json()["allow_fpp_override"] is False
    assert still_blocked.status_code == 409
    assert allowed.status_code == 200


def test_legacy_manual_brain_routes_are_not_public() -> None:
    app = create_app(Settings())

    with TestClient(app) as client:
        assert client.post("/api/brain/respond", json={"visitor_text": "Hi"}).status_code == 404
        assert client.post("/api/brain/voice-turn", json={"duration_seconds": 5}).status_code == 404
        assert client.post("/api/brain/conversation/reset").status_code == 404


def test_update_status_is_safe_without_a_release_channel() -> None:
    app = create_app(Settings(update_manifest_url=None))

    with TestClient(app) as client:
        status_response = client.get("/api/update/status")
        check_response = client.post("/api/update/check")

    assert status_response.status_code == 200
    assert status_response.json()["channel_configured"] is False
    assert status_response.json()["update_available"] is False
    assert check_response.json()["current_version"] == status_response.json()["current_version"]


def test_beta_update_channel_requires_explicit_acknowledgement(tmp_path) -> None:
    app = create_app(Settings(data_dir=tmp_path))

    with TestClient(app) as client:
        rejected = client.post(
            "/api/update/channel",
            json={"channel": "beta", "acknowledged": False},
        )
        enabled = client.post(
            "/api/update/channel",
            json={"channel": "beta", "acknowledged": True},
        )
        persisted = client.get("/api/update/status")
        stable = client.post(
            "/api/update/channel",
            json={"channel": "stable", "acknowledged": True},
        )

    assert rejected.status_code == 422
    assert enabled.status_code == 200
    assert enabled.json()["channel"] == "beta"
    assert enabled.json()["beta_enabled"] is True
    assert persisted.json()["channel"] == "beta"
    assert stable.json()["channel"] == "stable"


def test_update_version_comparison_handles_beta_versions(tmp_path, monkeypatch) -> None:
    class Response:
        def __init__(self, version: str) -> None:
            self._version = version

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {
                "version": self._version,
                "package_url": "https://example.test/update.zip",
                "sha256": "0" * 64,
            }

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, _url):
            return Response("0.28.2-beta1")

    monkeypatch.setattr("skelly_ai.api.httpx.AsyncClient", lambda **_kwargs: Client())
    app = create_app(Settings(data_dir=tmp_path))

    with TestClient(app) as client:
        client.post(
            "/api/update/channel",
            json={"channel": "beta", "acknowledged": True},
        )
        checked = client.post("/api/update/check")

    assert checked.status_code == 200
    assert checked.json()["channel"] == "beta"
    assert checked.json()["latest_version"] == "0.28.2-beta1"
    assert checked.json()["update_available"] is True


def test_raw_ble_probe_is_hidden_unless_developer_mode_is_enabled() -> None:
    public_app = create_app(Settings())

    with TestClient(public_app) as client:
        hidden = client.post(
            "/api/diagnostics/ble-movement-probe",
            json={"action": 8, "duration_ms": 100, "acknowledged": True},
        )
    assert hidden.status_code == 404


def test_operator_mode_speaks_exact_text_and_adapts_gestures_to_dac(tmp_path) -> None:
    class FakeOperatorSpeech:
        def __init__(self) -> None:
            self.spoken: list[str] = []

        def status(self) -> dict[str, object]:
            return {"available": True, "local_only": True}

        async def speak(self, text: str, jaw) -> dict[str, object]:
            self.spoken.append(text)
            return {
                "spoken": True,
                "engine": "test",
                "jaw_animated": jaw.snapshot().armed,
                "elevenlabs_used": False,
            }

    brain = FakeBrain()
    speech = FakeOperatorSpeech()
    app = create_app(
        Settings(data_dir=tmp_path),
        brain_client=brain,
        local_speech_client=speech,
    )

    with TestClient(app) as client:
        client.post(
            "/api/operation/settings",
            json={
                "hardware_profile": "stock",
                "default_mode": "manual",
                "allow_fpp_override": False,
            },
        )
        started = client.post("/api/operation/start", json={"mode": "manual"})
        spoken = client.post(
            "/api/operator/speak", json={"text": "Welcome, brave visitor!"}
        )
        blocked = client.post(
            "/api/operator/gesture", json={"gesture": "look_left"}
        )
        laughed = client.post(
            "/api/operator/gesture", json={"gesture": "laugh"}
        )

    assert started.status_code == 200
    assert spoken.status_code == 200
    assert spoken.json()["spoken_text"] == "Welcome, brave visitor!"
    assert speech.spoken == ["Welcome, brave visitor!", "Ha! Ha! Ha! Ha!"]
    assert brain.histories == []
    assert blocked.status_code == 409
    assert "Advanced DAC profile" in blocked.json()["detail"]
    assert laughed.status_code == 200
    assert laughed.json()["audio"]["source"] == "offline_local"


def test_advanced_operator_direction_gesture_uses_full_safe_dac_position(tmp_path) -> None:
    app = create_app(Settings(data_dir=tmp_path))

    with TestClient(app) as client:
        client.post(
            "/api/operation/settings",
            json={
                "hardware_profile": "dac",
                "default_mode": "manual",
                "allow_fpp_override": False,
            },
        )
        client.post("/api/operation/start", json={"mode": "manual"})
        looked_up = client.post(
            "/api/operator/gesture", json={"gesture": "look_up"}
        )

    assert looked_up.status_code == 200
    assert looked_up.json()["dac"]["values"]["pitch"] == 255


def test_elevenlabs_key_is_validated_and_never_returned(tmp_path) -> None:
    observed_key: str | None = None

    async def accept_key(api_key: SecretStr) -> None:
        nonlocal observed_key
        observed_key = api_key.get_secret_value()

    app = create_app(Settings(data_dir=tmp_path), credential_validator=accept_key)
    secret = "elevenlabs_test_secret_value_1234"

    with TestClient(app) as client:
        response = client.post(
            "/api/setup/elevenlabs",
            json={"api_key": secret},
        )
        assert response.status_code == 200
        assert response.json() == {
            "key_configured": True,
            "key_hint": "…1234",
        }
        assert secret not in response.text

        status_response = client.get("/api/status")
        assert secret not in status_response.text
        assert status_response.json()["device"]["elevenlabs_key_configured"] is True

    assert observed_key == secret
    credential_path = tmp_path / "credentials.json"
    stored = json.loads(credential_path.read_text(encoding="utf-8"))
    assert stored["elevenlabs_api_key"] == secret
    if os.name == "posix":
        assert credential_path.stat().st_mode & 0o777 == 0o600


def test_rejected_elevenlabs_key_is_not_saved(tmp_path) -> None:
    async def reject_key(_: SecretStr) -> None:
        raise CredentialValidationError("Rejected for testing")

    app = create_app(Settings(data_dir=tmp_path), credential_validator=reject_key)

    with TestClient(app) as client:
        response = client.post(
            "/api/setup/elevenlabs",
            json={"api_key": "invalid"},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Rejected for testing"
    assert not (tmp_path / "credentials.json").exists()


def test_groq_key_and_provider_choices_are_saved_without_exposing_secret(tmp_path) -> None:
    observed_key: str | None = None

    async def accept_groq_key(api_key: SecretStr) -> None:
        nonlocal observed_key
        observed_key = api_key.get_secret_value()

    app = create_app(
        Settings(data_dir=tmp_path),
        groq_credential_validator=accept_groq_key,
    )
    secret = "groq_test_secret_4321"

    with TestClient(app) as client:
        saved_key = client.post("/api/setup/groq", json={"api_key": secret})
        saved_settings = client.post(
            "/api/providers/settings",
            json={
                "brain_provider": "groq",
                "voice_provider": "groq",
                "local_voice": "en-us+m3",
                "local_speed": 155,
                "local_pitch": 35,
                "local_word_gap": 3,
                "groq_voice": "troy",
                "elevenlabs_voice_id": "",
                "speaker_preroll_ms": 725,
                "jaw_activity_percent": 25,
            },
        )
        status_response = client.get("/api/providers/status")

    assert saved_key.status_code == 200
    assert secret not in saved_key.text
    assert observed_key == secret
    assert saved_settings.status_code == 200
    assert saved_settings.json()["speaker_preroll_ms"] == 725
    assert saved_settings.json()["jaw_activity_percent"] == 25
    assert status_response.json()["settings"]["brain_provider"] == "groq"
    assert status_response.json()["groq"]["key_configured"] is True
    assert secret not in status_response.text


def test_cloud_voice_preview_does_not_silently_fallback_to_local(tmp_path) -> None:
    app = create_app(Settings(data_dir=tmp_path))

    with TestClient(app) as client:
        saved = client.post(
            "/api/providers/settings",
            json={
                "brain_provider": "local",
                "voice_provider": "groq",
                "local_voice": "en-us+m3",
                "local_speed": 145,
                "local_pitch": 30,
                "local_word_gap": 5,
                "groq_voice": "troy",
                "elevenlabs_voice_id": "",
                "speaker_preroll_ms": 650,
            },
        )
        preview = client.post("/api/voice/preview", json={"text": "Test"})

    assert saved.status_code == 200
    assert preview.status_code == 503
    assert "Save a Groq API key" in preview.json()["detail"]


@pytest.mark.asyncio
async def test_private_lan_client_can_complete_nontechnical_setup(tmp_path) -> None:
    async def accept_key(_: SecretStr) -> None:
        return None

    app = create_app(Settings(data_dir=tmp_path), credential_validator=accept_key)
    transport = httpx.ASGITransport(app=app, client=("10.0.10.50", 53000))

    async with httpx.AsyncClient(transport=transport, base_url="http://skelly") as client:
        response = await client.post(
            "/api/setup/elevenlabs",
            json={"api_key": "must-not-save"},
        )

    assert response.status_code == 200
    assert (tmp_path / "credentials.json").exists()


def test_elevenlabs_agent_creation_route_is_not_public(tmp_path) -> None:
    app = create_app(Settings(data_dir=tmp_path))

    with TestClient(app) as client:
        response = client.post(
            "/api/setup/elevenlabs/create-agent",
            json={"name": "Skelly AI"},
        )

    assert response.status_code == 404


def test_local_sensor_lab_endpoints_return_camera_and_microphone_results() -> None:
    sensor_status = {
        "local_only": True,
        "camera": {
            "available": True,
            "device": "/dev/video-test",
            "analyzed": True,
            "presence_detected": True,
            "person_count": 1,
            "face_count": 1,
            "motion_percent": 4.2,
            "width": 640,
            "height": 480,
            "captured_at": "2026-08-02T12:00:00+00:00",
        },
        "microphone": {
            "available": True,
            "device": "plughw:3,0",
            "voice_threshold_dbfs": -38.0,
            "offline_transcription_available": True,
            "speech_model": "vosk-model-small-en-us-0.15",
            "sampled": True,
            "voice_active": True,
            "level_dbfs": -22.5,
            "peak_percent": 37.0,
            "duration_seconds": 1.0,
            "sampled_at": "2026-08-02T12:00:00+00:00",
            "transcript": "welcome to the graveyard",
            "transcription_seconds": 0.42,
            "transcribed_at": "2026-08-02T12:00:01+00:00",
        },
    }

    class FakeSensorLab:
        def status(self) -> dict[str, object]:
            return sensor_status

        async def analyze_camera(self) -> bytes:
            return b"\xff\xd8fake-jpeg\xff\xd9"

        async def sample_microphone(self) -> dict[str, object]:
            return sensor_status

        async def transcribe_microphone(self, duration_seconds: int) -> dict[str, object]:
            assert duration_seconds == 5
            return sensor_status

        def last_audio_wav(self) -> bytes:
            return b"RIFFfake-wave"

    app = create_app(Settings(), sensor_lab=FakeSensorLab())
    with TestClient(app) as client:
        status_response = client.get("/api/sensors/status")
        camera_response = client.get("/api/sensors/camera/frame.jpg")
        microphone_response = client.post("/api/sensors/microphone/sample")
        transcript_response = client.post(
            "/api/sensors/microphone/transcribe",
            json={"duration_seconds": 5},
        )
        audio_response = client.get("/api/sensors/microphone/last.wav")

    assert status_response.json()["local_only"] is True
    assert camera_response.status_code == 200
    assert camera_response.headers["content-type"] == "image/jpeg"
    assert microphone_response.json()["microphone"]["voice_active"] is True
    assert transcript_response.json()["microphone"]["transcript"] == (
        "welcome to the graveyard"
    )
    assert audio_response.status_code == 200
    assert audio_response.headers["content-type"] == "audio/wav"


def test_listening_sensitivity_persists_and_updates_microphone_threshold(tmp_path) -> None:
    from skelly_ai.sensors import SensorLab
    from skelly_ai.operation_settings import OperationSettingsStore

    sensors = SensorLab(
        voice_threshold_dbfs=-38.0,
        speech_model_path=tmp_path / "models" / "vosk-model-small-en-us-0.15",
    )
    app = create_app(Settings(data_dir=tmp_path), sensor_lab=sensors)

    with TestClient(app) as client:
        initial = client.get("/api/operation/status")
        settings = initial.json()["settings"]
        settings["listening_sensitivity"] = 80
        saved = client.post("/api/operation/settings", json=settings)
        sensor_status = client.get("/api/sensors/status")

    assert saved.status_code == 200
    assert saved.json()["listening_sensitivity"] == 80
    assert sensor_status.json()["microphone"]["voice_threshold_dbfs"] < -45.0
    assert OperationSettingsStore(tmp_path).load().listening_sensitivity == 80


def test_ai_response_movement_weighting_boundaries() -> None:
    from skelly_ai.api import choose_ai_response_movement
    from skelly_ai.hardware import Movement

    assert choose_ai_response_movement(0.00) == Movement.HEAD_ONLY
    assert choose_ai_response_movement(0.49) == Movement.HEAD_ONLY
    assert choose_ai_response_movement(0.50) == Movement.HEAD_AND_TORSO
    assert choose_ai_response_movement(0.69) == Movement.HEAD_AND_TORSO
    assert choose_ai_response_movement(0.70) == Movement.TORSO_AND_ARMS
    assert choose_ai_response_movement(0.79) == Movement.TORSO_AND_ARMS
    assert choose_ai_response_movement(0.80) == Movement.ALL
    assert choose_ai_response_movement(0.99) == Movement.ALL


def test_ai_primes_stock_movement_before_speech_playback(tmp_path) -> None:
    order: list[str] = []

    class RecordingHardware(SimulatedSkelly):
        async def set_movement(self, movement: Movement):
            order.append(f"movement:{movement.value}")
            return await super().set_movement(movement)

        async def stop(self):
            order.append("stop")
            return await super().stop()

    class ImmediateSensors:
        def status(self) -> dict[str, object]:
            return {
                "camera": {
                    "available": True,
                    "face_count": 1,
                    "person_count": 1,
                    "motion_percent": 0.0,
                },
                "microphone": {
                    "available": True,
                    "offline_transcription_available": True,
                    "voice_active": True,
                    "level_dbfs": -25.0,
                },
            }

        async def analyze_camera(self) -> bytes:
            return b"jpeg"

        async def sample_microphone(self, duration_seconds: int = 1) -> dict[str, object]:
            return self.status()

        async def transcribe_microphone_until_silence(
            self, max_duration_seconds: int, silence_seconds: float
        ) -> dict[str, object]:
            return {
                "microphone": {
                    "voice_active": True,
                    "transcript": "hello skelly",
                    "level_dbfs": -25.0,
                    "duration_seconds": 1.0,
                    "transcription_seconds": 0.01,
                }
            }

    class RecordingSpeech:
        def status(self) -> dict[str, object]:
            return {"available": True, "local_only": True}

        async def speak(self, text: str, jaw) -> dict[str, object]:
            order.append("speech")
            return {"spoken": True, "engine": "test", "elapsed_seconds": 0.1}

    app = create_app(
        Settings(data_dir=tmp_path),
        sensor_lab=ImmediateSensors(),
        brain_client=FakeBrain(),
        hardware_client=RecordingHardware(),
        local_speech_client=RecordingSpeech(),
    )

    with TestClient(app) as client:
        client.post(
            "/api/operation/settings",
            json={
                "hardware_profile": "stock",
                "default_mode": "ai",
                "allow_fpp_override": False,
            },
        )
        assert client.post("/api/operation/start", json={"mode": "ai"}).status_code == 200
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if client.get("/api/perception/status").json()["event_count"]:
                break
            time.sleep(0.01)
        client.post("/api/operation/stop")

    first_movement = next(index for index, item in enumerate(order) if item.startswith("movement:"))
    assert first_movement < order.index("speech") < order.index("stop", first_movement)


def test_visitor_nag_settings_persist(tmp_path) -> None:
    from skelly_ai.operation_settings import OperationSettingsStore

    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        settings = client.get("/api/operation/status").json()["settings"]
        settings.update(
            {
                "nag_mode": "media",
                "nag_delay_seconds": 7,
                "nag_cooldown_seconds": 45,
                "nag_max_per_visitor": 4,
                "nag_require_presence": True,
                "nag_unattended_enabled": True,
                "nag_unattended_interval_seconds": 180,
            }
        )
        saved = client.post("/api/operation/settings", json=settings)

    assert saved.status_code == 200
    body = saved.json()
    assert body["nag_mode"] == "media"
    assert body["nag_delay_seconds"] == 7
    assert body["nag_cooldown_seconds"] == 45
    assert body["nag_max_per_visitor"] == 4
    assert body["nag_unattended_enabled"] is True
    assert body["nag_unattended_interval_seconds"] == 180
    persisted = OperationSettingsStore(tmp_path).load()
    assert persisted.nag_mode == "media"
    assert persisted.nag_max_per_visitor == 4
    assert persisted.nag_unattended_enabled is True
    assert persisted.nag_unattended_interval_seconds == 180


def test_factory_media_delete_is_blocked_by_api(tmp_path) -> None:
    app = create_app(Settings(data_dir=tmp_path), hardware_client=SimulatedSkelly())

    with TestClient(app) as client:
        response = client.post("/api/media/delete", json={"serial": 1})

    assert response.status_code == 409
    assert response.json()["detail"] == "Factory media files cannot be deleted"


def test_hardware_events_endpoint_returns_recent_events(tmp_path) -> None:
    hardware = SimulatedSkelly()
    hardware._record("diagnostic", "one")
    hardware._record("diagnostic", "two")
    app = create_app(Settings(data_dir=tmp_path), hardware_client=hardware)

    with TestClient(app) as client:
        response = client.get("/api/hardware/events?limit=1")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["events"][0]["action"] == "diagnostic"
    assert body["events"][0]["value"] == "two"


def test_character_prompt_prioritizes_answer_over_personality() -> None:
    from skelly_ai.brain import build_system_prompt
    prompt = build_system_prompt("Skelly", "sarcastic")
    assert "Answer the visitor's actual question directly and accurately" in prompt
    assert "For factual questions, the response must contain the factual answer." in prompt
    assert "Never replace the answer with a joke" in prompt


def test_welcome_message_settings_persist(tmp_path) -> None:
    from skelly_ai.operation_settings import OperationSettingsStore
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        settings = client.get("/api/operation/status").json()["settings"]
        settings["welcome_enabled"] = True
        settings["welcome_message"] = "Greetings, brave visitor."
        saved = client.post("/api/operation/settings", json=settings)
    assert saved.status_code == 200
    assert saved.json()["welcome_enabled"] is True
    assert saved.json()["welcome_message"] == "Greetings, brave visitor."
    persisted = OperationSettingsStore(tmp_path).load()
    assert persisted.welcome_enabled is True
    assert persisted.welcome_message == "Greetings, brave visitor."


def test_pi_media_upload_api_success_duplicate_and_invalid(tmp_path, monkeypatch):
    from skelly_ai.pi_media import PiMediaLibrary

    # Keep the existing 10 GB disk reserve from blocking our
    # small simulated upload tests.
    monkeypatch.setattr(
        PiMediaLibrary,
        "_disk_free",
        lambda self: 20 * 1024 ** 3,
    )

    app = create_app(Settings(data_dir=tmp_path, simulation=True))

    with TestClient(app) as client:
        response = client.post(
            "/api/pi-media/upload?filename=greeting.mp3",
            content=b"ID3" + b"x" * 1024,
            headers={"Content-Type": "audio/mpeg"},
        )

        assert response.status_code == 200, response.text
        assert any(
            item["name"] == "greeting.mp3"
            for item in response.json()["files"]
        )

        saved = tmp_path / "media" / "greeting.mp3"
        assert saved.read_bytes() == b"ID3" + b"x" * 1024

        duplicate = client.post(
            "/api/pi-media/upload?filename=greeting.mp3",
            content=b"ID3duplicate",
        )
        assert duplicate.status_code == 409

        # A duplicate must not overwrite the original file.
        assert saved.read_bytes() == b"ID3" + b"x" * 1024

        invalid = client.post(
            "/api/pi-media/upload?filename=malware.exe",
            content=b"not audio",
        )
        assert invalid.status_code == 422

        status = client.get("/api/pi-media/status")
        assert status.status_code == 200
        assert status.json()["file_count"] == 1


def test_pi_media_upload_api_rejects_oversized(tmp_path, monkeypatch):
    from skelly_ai.pi_media import PiMediaLibrary

    monkeypatch.setattr(
        PiMediaLibrary, "_disk_free",
        lambda self: 20 * 1024 ** 3,
    )
    monkeypatch.setattr(PiMediaLibrary, "MAX_FILE_BYTES", 100)

    app = create_app(Settings(data_dir=tmp_path, simulation=True))

    with TestClient(app) as client:
        response = client.post(
            "/api/pi-media/upload?filename=oversized.mp3",
            content=b"x" * 150,
            headers={"Content-Type": "audio/mpeg"},
        )

        assert response.status_code == 413, response.text
        assert not (tmp_path / "media" / "oversized.mp3").exists()
        assert not list((tmp_path / "media").glob(".*.upload"))
        assert client.get("/api/pi-media/status").json()["file_count"] == 0


def test_pi_media_display_name_api(tmp_path, monkeypatch):
    from skelly_ai.pi_media import PiMediaLibrary, GIB

    monkeypatch.setattr(
        PiMediaLibrary, "_disk_free", lambda self: 20 * GIB
    )

    app = create_app(Settings(data_dir=tmp_path, simulation=True))

    with TestClient(app) as client:
        upload = client.post(
            "/api/pi-media/upload?filename=welcome.mp3",
            content=b"ID3test",
        )
        assert upload.status_code == 200, upload.text

        original = upload.json()["files"][0]
        clip_id = original["id"]

        edited = client.post(
            "/api/pi-media/edit",
            json={
                "name": "welcome.mp3",
                "display_name": "Welcome Visitors",
                "action": 5,
                "eye": 7,
                "jaw_sync": False,
                "nag_response": True,
            },
        )

        assert edited.status_code == 200, edited.text
        clip = edited.json()["files"][0]

        assert clip["display_name"] == "Welcome Visitors"
        assert clip["name"] == "welcome.mp3"
        assert clip["id"] == clip_id
        assert clip["action"] == 5
        assert clip["eye"] == 7
        assert clip["jaw_sync"] is False
        assert clip["nag_response"] is True

        assert (tmp_path / "media" / "welcome.mp3").exists()

        reloaded = client.get("/api/pi-media/status").json()["files"][0]
        assert reloaded["id"] == clip_id
        assert reloaded["display_name"] == "Welcome Visitors"
        assert reloaded["eye"] == 7
        assert reloaded["nag_response"] is True

    # Recreate the app to verify disk persistence, not just in-process state.
    restarted = create_app(Settings(data_dir=tmp_path, simulation=True))
    with TestClient(restarted) as client:
        persisted = client.get("/api/pi-media/status").json()["files"][0]
        assert persisted["id"] == clip_id
        assert persisted["eye"] == 7
        assert persisted["nag_response"] is True
        response = client.post("/api/pi-media/edit", json={**persisted, "eye": 18, "nag_response": False})
        assert response.status_code == 200
    restarted_again = create_app(Settings(data_dir=tmp_path, simulation=True))
    with TestClient(restarted_again) as client:
        persisted = client.get("/api/pi-media/status").json()["files"][0]
        assert persisted["eye"] == 18
        assert persisted["nag_response"] is False


def test_pi_media_local_tts_generate_without_playback(tmp_path, monkeypatch):
    import io
    import wave
    from pathlib import Path

    from skelly_ai.speech import LocalSpeech

    app = create_app(Settings(data_dir=tmp_path, simulation=True))
    calls = []

    async def fake_generate(self, text, destination):
        calls.append(text)

        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(22050)
            wav.writeframes(b"\x00\x00" * 1000)

        Path(destination).write_bytes(output.getvalue())
        return Path(destination)

    async def forbidden_play(*args, **kwargs):
        raise AssertionError("Generating TTS must not trigger playback")

    monkeypatch.setattr(LocalSpeech, "generate_wav", fake_generate)
    monkeypatch.setattr(LocalSpeech, "_play", forbidden_play)

    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        response = client.post(
            "/api/pi-media/tts/generate",
            json={"text": "Welcome, brave visitor!"},
        )

        assert response.status_code == 200, response.text

        payload = response.json()

        assert payload["provider"] == "local"
        assert payload["format"] == "wav"
        assert len(payload["preview_id"]) == 32
        assert payload["size_bytes"] > 44

        assert calls == ["Welcome, brave visitor!"]

        preview = (
            tmp_path
            / "tts-previews"
            / f"{payload['preview_id']}.wav"
        )

        assert preview.is_file()

        # Generation must not automatically add anything to Pi Media.
        status = client.get("/api/pi-media/status")
        assert status.status_code == 200
        assert status.json()["file_count"] == 0


def test_pi_media_tts_browser_preview(tmp_path):
    import io
    import wave
    from skelly_ai.tts_previews import TTSPreviewManager

    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(22050)
        wav.writeframes(b"\x00\x00" * 1000)

    app = create_app(Settings(data_dir=tmp_path, simulation=True))
    manager = TTSPreviewManager(tmp_path)
    preview_id = manager.create(output.getvalue())

    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        response = client.get(
            f"/api/pi-media/tts/preview/{preview_id}"
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("audio/wav")
        assert response.headers["cache-control"] == "no-store"
        assert response.content == output.getvalue()

        missing = client.get(
            "/api/pi-media/tts/preview/" + "0" * 32
        )
        assert missing.status_code == 404

        invalid = client.get(
            "/api/pi-media/tts/preview/not-a-valid-id"
        )
        assert invalid.status_code == 404


def test_pi_media_tts_save_endpoint(tmp_path, monkeypatch):
    import io
    import wave

    from skelly_ai.pi_media import GIB, PiMediaLibrary
    from skelly_ai.tts_previews import TTSPreviewManager

    monkeypatch.setattr(
        PiMediaLibrary,
        "_disk_free",
        lambda self: 20 * GIB,
    )

    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(22050)
        wav.writeframes(b"\x00\x00" * 1000)

    app = create_app(Settings(data_dir=tmp_path, simulation=True))
    manager = TTSPreviewManager(tmp_path)
    preview_id = manager.create(output.getvalue())

    payload = {
        "preview_id": preview_id,
        "filename": "welcome.wav",
        "display_name": "Welcome Visitors",
    }

    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        saved = client.post(
            "/api/pi-media/tts/save",
            json=payload,
        )
        assert saved.status_code == 200, saved.text

        files = saved.json()["files"]
        assert len(files) == 1
        assert files[0]["name"] == "welcome.wav"
        assert files[0]["display_name"] == "Welcome Visitors"
        assert len(files[0]["id"]) == 32

        assert (
            PiMediaLibrary(tmp_path).media_dir / "welcome.wav"
        ).read_bytes() == output.getvalue()

        duplicate = client.post(
            "/api/pi-media/tts/save",
            json={**payload, "filename": "second.wav"},
        )
        assert duplicate.status_code == 404
        assert len(
            client.get("/api/pi-media/status").json()["files"]
        ) == 1


@pytest.mark.asyncio
async def test_tts_generation_rejects_concurrent_requests(tmp_path, monkeypatch):
    import asyncio
    import io
    import wave

    from skelly_ai.speech import LocalSpeech

    app = create_app(Settings(data_dir=tmp_path, simulation=True))
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_generate(self, text, destination):
        started.set()
        await release.wait()

        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(22050)
            wav.writeframes(b"\x00\x00" * 1000)

        destination.write_bytes(output.getvalue())
        return destination

    monkeypatch.setattr(LocalSpeech, "generate_wav", slow_generate)

    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        first_task = asyncio.create_task(
            client.post(
                "/api/pi-media/tts/generate",
                json={"text": "First request"},
            )
        )

        await asyncio.wait_for(started.wait(), timeout=5)

        try:
            second = await asyncio.wait_for(
                client.post(
                    "/api/pi-media/tts/generate",
                    json={"text": "Second request"},
                ),
                timeout=5,
            )

            assert second.status_code == 429, second.text
            assert "already in progress" in second.json()["detail"]
        finally:
            release.set()

        first = await asyncio.wait_for(first_task, timeout=5)
        assert first.status_code == 200, first.text


@pytest.mark.parametrize(
    "provider, key_name, voice_class",
    [
        ("groq", "groq_api_key", "GroqVoice"),
        ("elevenlabs", "api_key", "ElevenLabsVoice"),
    ],
)
def test_pi_media_cloud_tts_generation(
    tmp_path, monkeypatch, provider, key_name, voice_class
):
    import io
    import wave

    from skelly_ai import api as api_module
    from skelly_ai.provider_settings import ProviderSettingsStore

    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(22050)
        wav.writeframes(b"\x00\x00" * 1000)
    fake_audio = output.getvalue()

    generated = []

    async def fake_generate(self, *args, **kwargs):
        generated.append((args, kwargs))
        return fake_audio

    voice_type = getattr(api_module, voice_class)
    monkeypatch.setattr(voice_type, "generate", fake_generate)

    app = create_app(Settings(data_dir=tmp_path, simulation=True))

    credentials = app.state.credential_store
    monkeypatch.setattr(
        credentials,
        "load",
        lambda: type(
            "FakeCredentials",
            (),
            {
                "api_key": SecretStr("elevenlabs-test"),
                "groq_api_key": SecretStr("groq-test"),
            },
        )(),
    )

    store = app.state.provider_store
    settings = store.load()
    settings.voice_provider = provider
    if provider == "elevenlabs":
        settings.elevenlabs_voice_id = "test-voice"
    store.save(settings)

    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        response = client.post(
            "/api/pi-media/tts/generate",
            json={"text": "Welcome visitors"},
        )

        assert response.status_code == 200, response.text
        payload = response.json()

        assert payload["provider"] == provider
        assert payload["format"] == "wav"
        assert payload["size_bytes"] == len(fake_audio)
        assert len(payload["preview_id"]) == 32

        assert len(generated) == 1
        assert generated[0][0][1] == "Welcome visitors"

        preview = client.get(
            f"/api/pi-media/tts/preview/{payload['preview_id']}"
        )
        assert preview.status_code == 200
        assert preview.content == fake_audio


def test_pi_media_tts_discard_endpoint(tmp_path):
    import io
    import wave
    from skelly_ai.tts_previews import TTSPreviewManager
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(22050)
        wav.writeframes(b"\x00\x00" * 1000)
    app = create_app(Settings(data_dir=tmp_path, simulation=True))
    preview_id = TTSPreviewManager(tmp_path).create(output.getvalue())
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        response = client.delete(f"/api/pi-media/tts/preview/{preview_id}")
        assert response.status_code == 200, response.text
        assert response.json() == {"discarded": True}
        assert client.get(f"/api/pi-media/tts/preview/{preview_id}").status_code == 404
        assert client.get("/api/pi-media/status").json()["file_count"] == 0


@pytest.mark.parametrize("method,path,body", [
    ("POST", "/api/pi-media/tts/generate", {"text": "Hello"}),
    ("POST", "/api/pi-media/tts/save", {"preview_id": "0" * 32, "filename": "hello.wav", "display_name": "Hello"}),
    ("GET", "/api/pi-media/tts/preview/" + "0" * 32, None),
    ("DELETE", "/api/pi-media/tts/preview/" + "0" * 32, None),
])
def test_tts_lan_access_without_operator_password(tmp_path, method, path, body):
    app = create_app(Settings(data_dir=tmp_path, tts_password=SecretStr("legacy-unused-password")))
    with TestClient(app, client=("192.168.1.25", 50000)) as client:
        response = client.request(method, path, json=body)
        assert response.status_code not in (401, 403)
        assert "www-authenticate" not in response.headers


def test_tts_proxy_allowed_and_public_or_cross_origin_denied(tmp_path):
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app, client=("8.8.8.8", 50000)) as client:
        assert client.get("/api/pi-media/tts/preview/" + "0" * 32, headers={"X-Forwarded-For":"192.168.1.25"}).status_code == 403
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        for header in ("X-Forwarded-For", "Forwarded", "X-Real-IP"):
            assert client.get("/api/pi-media/tts/preview/" + "0" * 32, headers={header: "192.168.1.25"}).status_code == 404
        for headers in ({"Origin": "https://evil.example"}, {"Sec-Fetch-Site": "cross-site"}):
            assert client.post("/api/pi-media/tts/generate", json={"text": "Hello"}, headers=headers).status_code == 403


def test_tts_quota_checked_before_provider_call(tmp_path, monkeypatch):
    from skelly_ai.tts_previews import TTSPreviewManager
    from skelly_ai.speech import LocalSpeech
    monkeypatch.setattr(TTSPreviewManager, "MAX_PREVIEWS", 0)
    async def forbidden(*args, **kwargs):
        raise AssertionError("Quota rejection must precede synthesis")
    monkeypatch.setattr(LocalSpeech, "generate_wav", forbidden)
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        response = client.post("/api/pi-media/tts/generate", json={"text": "Hello"})
        assert response.status_code == 429
