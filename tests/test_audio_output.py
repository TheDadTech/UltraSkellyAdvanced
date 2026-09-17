from fastapi.testclient import TestClient

from skelly_ai.api import create_app
from skelly_ai.config import Settings
from skelly_ai.operation_settings import OperationSettings
from skelly_ai.speech import LocalSpeech


def test_operation_settings_audio_output_defaults_preserve_skelly_path() -> None:
    settings = OperationSettings()
    assert settings.audio_output == "skelly"
    assert settings.external_bluetooth_address is None
    assert settings.jaw_follow_speech is True
    assert settings.jaw_sync_offset_ms == -750
    assert settings.jaw_mirror_level_percent == 100
    assert settings.mute_skelly_speaker_on_external is True
    assert settings.skelly_speaker_restore_volume == 100




def test_legacy_skelly_volume_is_clamped_to_native_range() -> None:
    assert OperationSettings(skelly_speaker_restore_volume=128).skelly_speaker_restore_volume == 100
    assert OperationSettings(skelly_speaker_restore_volume=255).skelly_speaker_restore_volume == 100

def test_simulated_external_bluetooth_can_be_selected_and_saved(tmp_path) -> None:
    app = create_app(Settings(simulation=True, data_dir=tmp_path))
    with TestClient(app) as client:
        # A configured prop is required for manual hardware actions.
        current = client.get("/api/operation/status").json()["settings"]
        current["device_configured"] = True
        client.post("/api/operation/settings", json=current)
        devices = client.post("/api/audio/external/scan")
        assert devices.status_code == 200
        address = devices.json()["devices"][0]["address"]
        selected = client.post("/api/audio/external/select", json={"address": address})
        assert selected.status_code == 200
        body = selected.json()
        assert body["settings"]["audio_output"] == "external_bluetooth"
        assert body["external_bluetooth"]["connected"] is True
        saved = client.get("/api/operation/status").json()["settings"]
        assert saved["external_bluetooth_address"] == address


def test_external_reconnect_recovers_single_paired_speaker_when_saved_target_missing(tmp_path) -> None:
    app = create_app(Settings(simulation=True, data_dir=tmp_path))
    with TestClient(app) as client:
        current = client.get("/api/operation/status").json()["settings"]
        current["device_configured"] = True
        current["external_bluetooth_address"] = None
        current["external_bluetooth_name"] = None
        client.post("/api/operation/settings", json=current)

        reconnect = client.post("/api/audio/external/connect")
        assert reconnect.status_code == 200
        assert reconnect.json()["connected"] is True
        saved = client.get("/api/operation/status").json()["settings"]
        assert saved["external_bluetooth_address"] == "11:22:33:44:55:66"
        assert saved["external_bluetooth_name"] == "External Speaker (simulated)"


def test_local_speech_output_configuration_separates_playback_and_jaw_mirror() -> None:
    speech = LocalSpeech()
    speech.configure_output(
        playback_target="external-42",
        jaw_mirror_target="skelly-17",
        jaw_mirror_volume_target="17",
        jaw_follow_speech=True,
        jaw_sync_offset_ms=-200,
    )
    status = speech.status()
    assert status["playback_target"] == "external-42"
    assert status["jaw_mirror_target"] == "skelly-17"
    assert status["jaw_follow_speech"] is True
    assert status["jaw_sync_offset_seconds"] == -0.2


def test_static_ui_contains_external_audio_controls() -> None:
    from pathlib import Path
    html = (Path(__file__).parents[1] / "src/skelly_ai/static/index.html").read_text()
    assert 'id="audio-output-select"' in html
    assert '>External Bluetooth<' in html
    assert 'id="jaw-follow-speech"' in html
    assert 'id="jaw-sync-offset"' in html
    assert 'min="-1000" max="1000" step="25" value="-750"' in html
    assert 'id="mute-skelly-speaker-on-external"' in html
    assert 'id="speaker-mute-button"' in html
    assert 'Jaw sooner' in html
    assert 'Audio sooner' in html
    assert '>Together<' not in html
    assert 'id="speaker-volume" type="range" min="0" max="100" value="100"' in html


def test_external_bluetooth_failure_does_not_block_manual_operation(tmp_path, monkeypatch) -> None:
    from skelly_ai.audio_output import AudioOutputUnavailable, ExternalBluetoothAudio

    async def fail_connect(self, *, route=True):
        raise AudioOutputUnavailable("org.bluez.Error.Failed br-connection-page-timeout")

    monkeypatch.setattr(ExternalBluetoothAudio, "connect", fail_connect)
    app = create_app(Settings(simulation=True, data_dir=tmp_path))
    with TestClient(app) as client:
        current = client.get("/api/operation/status").json()["settings"]
        current.update({
            "device_configured": True,
            "audio_output": "external_bluetooth",
            "external_bluetooth_address": "F4:2B:7D:30:BB:94",
            "external_bluetooth_name": "soundcore Boom V2",
        })
        saved = client.post("/api/operation/settings", json=current)
        assert saved.status_code == 200
        started = client.post("/api/operation/start", json={"mode": "manual"})
        assert started.status_code == 200
        body = started.json()["operation"]
        assert body["active_mode"] == "manual"
        assert body["ready"] is True


def test_local_speech_can_route_primary_and_jaw_to_different_sessions(tmp_path) -> None:
    helper = tmp_path / "helper"
    helper.write_text("#!/bin/sh\n")
    speech = LocalSpeech(system_helper=helper)
    speech.configure_output(
        playback_target="bluez_output.soundcore",
        jaw_mirror_target="bluez_output.skelly",
        jaw_mirror_volume_target="17",
        jaw_follow_speech=True,
        jaw_sync_offset_ms=-200,
        playback_session="skelly-ai",
        jaw_mirror_session="dadtech",
        playback_target_required=True,
    )
    status = speech.status()
    assert status["playback_session"] == "skelly-ai"
    assert status["jaw_mirror_session"] == "dadtech"
    assert speech._player_exec("--target", "bluez_output.soundcore", session="skelly-ai") == [
        "sudo", str(helper), "audio-pw-play", "--session", "skelly-ai",
        "--target", "bluez_output.soundcore",
    ]
    assert speech._player_exec("--target", "bluez_output.skelly", session="dadtech") == [
        "sudo", str(helper), "audio-pw-play", "--session", "dadtech",
        "--target", "bluez_output.skelly",
    ]


def test_external_audio_auto_mutes_skelly_and_restores_volume(tmp_path) -> None:
    app = create_app(Settings(simulation=True, data_dir=tmp_path))
    with TestClient(app) as client:
        settings = client.get("/api/operation/status").json()["settings"]
        settings["device_configured"] = True
        client.post("/api/operation/settings", json=settings)
        client.post("/api/hardware/connect", json={"address": None})
        before = client.post("/api/media/volume", json={"volume": 80})
        assert before.status_code == 200
        assert before.json()["volume"] == 80

        settings = client.get("/api/operation/status").json()["settings"]
        settings["audio_output"] = "external_bluetooth"
        settings["external_bluetooth_address"] = "F4:2B:7D:30:BB:94"
        settings["external_bluetooth_name"] = "soundcore Boom V2"
        saved = client.post("/api/operation/settings", json=settings)
        assert saved.status_code == 200
        assert saved.json()["skelly_speaker_restore_volume"] == 80
        # Merely preferring External must not mute Skelly until the external
        # route is actually ready; fallback remains audible.
        assert client.get("/api/media/status").json()["volume"] == 80
        connected = client.post("/api/audio/external/connect")
        assert connected.status_code == 200
        assert client.get("/api/media/status").json()["volume"] == 0

        settings = saved.json()
        settings["audio_output"] = "skelly"
        restored = client.post("/api/operation/settings", json=settings)
        assert restored.status_code == 200
        assert client.get("/api/media/status").json()["volume"] == 80


def test_provider_switch_preserves_external_dual_session_routing(tmp_path) -> None:
    app = create_app(Settings(simulation=True, data_dir=tmp_path))
    with TestClient(app) as client:
        settings = client.get("/api/operation/status").json()["settings"]
        settings.update({
            "audio_output": "external_bluetooth",
            "external_bluetooth_address": "F4:2B:7D:30:BB:94",
            "external_bluetooth_name": "soundcore Boom V2",
        })
        client.post("/api/operation/settings", json=settings)
        speech = app.state.local_speech
        before = speech.status()

        providers = client.get("/api/providers/status").json()["settings"]
        providers["brain_provider"] = "groq"
        providers["voice_provider"] = "elevenlabs"
        saved = client.post("/api/providers/settings", json=providers)
        assert saved.status_code == 200
        after = speech.status()

        assert after["playback_session"] == before["playback_session"]
        assert after["jaw_mirror_session"] == before["jaw_mirror_session"]
        assert after["playback_target"] == before["playback_target"]
        assert after["jaw_mirror_target"] == before["jaw_mirror_target"]


def test_external_bluetooth_waits_up_to_sixty_seconds_for_pipewire_sink(monkeypatch, tmp_path) -> None:
    import asyncio
    from types import SimpleNamespace
    from skelly_ai.audio_output import ExternalBluetoothAudio

    helper = tmp_path / "helper"
    helper.write_text("#!/bin/sh\n")
    audio = ExternalBluetoothAudio(
        address="F4:2B:7D:30:BB:94",
        system_helper=helper,
        pipewire_session="skelly-ai",
    )
    attempts = 0

    async def noop_headless():
        return None

    async def read_info(address):
        return SimpleNamespace(
            connected=True,
            paired=True,
            trusted=True,
            device_name="soundcore Boom V2",
        )

    async def find_sink(name):
        nonlocal attempts
        attempts += 1
        if attempts == 120:
            return ("77", "bluez_output.F4_2B_7D_30_BB_94.1")
        return None

    async def fast_sleep(_seconds):
        return None

    async def run_program(*args):
        return SimpleNamespace(returncode=0, output="")

    async def run_bluetooth(*args, **kwargs):
        return SimpleNamespace(returncode=0, output="Connection successful")

    monkeypatch.setattr(audio, "_require_tools", lambda: None)
    monkeypatch.setattr(audio, "_ensure_headless_pipewire", noop_headless)
    monkeypatch.setattr(audio, "_read_info", read_info)
    monkeypatch.setattr(audio, "_find_pipewire_sink", find_sink)
    monkeypatch.setattr(audio, "_run_program", run_program)
    monkeypatch.setattr(audio, "_run", run_bluetooth)
    monkeypatch.setattr(asyncio, "sleep", fast_sleep)

    result = asyncio.run(audio.connect(route=True))
    assert attempts == 120
    assert result.sink_id == "77"
    assert result.sink_name == "bluez_output.F4_2B_7D_30_BB_94.1"


def test_skelly_output_reasserts_saved_ble_volume_when_hardware_cache_is_zero(tmp_path) -> None:
    app = create_app(Settings(simulation=True, data_dir=tmp_path))
    with TestClient(app) as client:
        settings = client.get("/api/operation/status").json()["settings"]
        settings["device_configured"] = True
        client.post("/api/operation/settings", json=settings)
        client.post("/api/hardware/connect", json={"address": None})
        client.post("/api/media/volume", json={"volume": 75})

        # Simulate the exact field failure: the prop's internal BLE volume was
        # left at zero while saved/UI state still expects an audible level.
        app.state.hardware._volume = 0
        settings = client.get("/api/operation/status").json()["settings"]
        settings["audio_output"] = "skelly"
        saved = client.post("/api/operation/settings", json=settings)

        assert saved.status_code == 200
        assert client.get("/api/media/status").json()["volume"] == 75


def test_turning_external_auto_mute_off_restores_skelly_ble_volume_immediately(tmp_path) -> None:
    app = create_app(Settings(simulation=True, data_dir=tmp_path))
    with TestClient(app) as client:
        settings = client.get("/api/operation/status").json()["settings"]
        settings["device_configured"] = True
        client.post("/api/operation/settings", json=settings)
        client.post("/api/hardware/connect", json={"address": None})
        client.post("/api/media/volume", json={"volume": 90})

        settings = client.get("/api/operation/status").json()["settings"]
        settings["audio_output"] = "external_bluetooth"
        settings["mute_skelly_speaker_on_external"] = True
        settings["external_bluetooth_address"] = "F4:2B:7D:30:BB:94"
        settings["external_bluetooth_name"] = "soundcore Boom V2"
        muted = client.post("/api/operation/settings", json=settings)
        assert muted.status_code == 200
        assert client.get("/api/media/status").json()["volume"] == 90
        connected = client.post("/api/audio/external/connect")
        assert connected.status_code == 200
        assert client.get("/api/media/status").json()["volume"] == 0

        settings = muted.json()
        settings["mute_skelly_speaker_on_external"] = False
        unmuted = client.post("/api/operation/settings", json=settings)
        assert unmuted.status_code == 200
        assert client.get("/api/media/status").json()["volume"] == 90


def test_status_reports_preferred_and_active_audio_route(tmp_path) -> None:
    app = create_app(Settings(simulation=True, data_dir=tmp_path))
    with TestClient(app) as client:
        settings = client.get("/api/operation/status").json()["settings"]
        settings.update({
            "device_configured": True,
            "audio_output": "external_bluetooth",
            "external_bluetooth_address": "11:22:33:44:55:66",
            "external_bluetooth_name": "External Speaker (simulated)",
        })
        client.post("/api/operation/settings", json=settings)
        client.post("/api/hardware/connect", json={"address": None})
        client.post("/api/audio/prepare-connect")
        status = client.get("/api/status").json()
        assert status["audio_route"]["preferred"] == "external_bluetooth"
        assert status["audio_route"]["active"] in {"external_bluetooth", "skelly"}


def test_runtime_version_matches_dev9() -> None:
    from skelly_ai import __version__
    assert __version__ == "0.27.0"
