import json
import os

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from skelly_ai.api import create_app
from skelly_ai.brain import BrainReply
from skelly_ai.config import Settings
from skelly_ai.credentials import CredentialValidationError


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
