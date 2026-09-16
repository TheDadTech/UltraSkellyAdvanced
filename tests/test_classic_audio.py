import pytest
from fastapi.testclient import TestClient

from skelly_ai.api import create_app
from skelly_ai.classic_audio import (
    BluetoothClassicAudio,
    ClassicAudioSnapshot,
    _CommandResult,
)
from skelly_ai.config import Settings


def test_pipewire_skelly_sink_is_identified_as_default(monkeypatch) -> None:
    monkeypatch.setattr("skelly_ai.classic_audio.shutil.which", lambda _: "/usr/bin/tool")
    audio = BluetoothClassicAudio()
    output = """
Audio
 ├─ Sinks:
 │      53. Built-in Audio Stereo               [vol: 0.40]
 │  *   91. ServoSkelly(Live)                   [vol: 0.40]
 ├─ Sources:
"""

    assert audio._find_sink(output) == ("91", True)


def test_broad_skelly_live_filter_matches_animated_factory_name(monkeypatch) -> None:
    monkeypatch.setattr("skelly_ai.classic_audio.shutil.which", lambda _: "/usr/bin/tool")
    audio = BluetoothClassicAudio(name_filter="Skelly(Live)")
    output = """
Audio
 ├─ Sinks:
 │  *   91. Animated Skelly(Live)                [vol: 1.00]
 ├─ Sources:
"""

    assert audio._find_sink(output) == ("91", True)


@pytest.mark.asyncio
async def test_routing_waits_for_sink_and_initializes_unity_gain(monkeypatch) -> None:
    monkeypatch.setattr("skelly_ai.classic_audio.shutil.which", lambda _: "/usr/bin/wpctl")
    monkeypatch.setattr("skelly_ai.classic_audio.asyncio.sleep", lambda _: _completed_sleep())
    audio = BluetoothClassicAudio(name_filter="Skelly(Live)")
    status_reads = 0
    calls: list[tuple[str, ...]] = []

    async def fake_run_program(executable: str, *arguments: str, input_text=None) -> _CommandResult:
        nonlocal status_reads
        del input_text
        calls.append((executable, *arguments))
        if arguments == ("status",):
            status_reads += 1
            if status_reads < 12:
                return _CommandResult(0, "Audio\n ├─ Sinks:\n │  *   77. Built-in Audio Stereo")
            return _CommandResult(
                0,
                "Audio\n ├─ Sinks:\n │  *   92. Animated Skelly(Live) [vol: 0.40]\n ├─ Sources:",
            )
        return _CommandResult(0, "")

    async def _completed_sleep() -> None:
        return None

    audio._run_program = fake_run_program  # type: ignore[method-assign]
    snapshot = await audio._route_pipewire_sink()

    assert status_reads == 12
    assert snapshot.sink_ready is True
    assert snapshot.sink_id == "92"
    assert ("/usr/bin/wpctl", "set-default", "92") in calls
    assert ("/usr/bin/wpctl", "set-volume", "92", "1.0") in calls


@pytest.mark.asyncio
async def test_routing_allows_full_first_connection_publication_window(monkeypatch) -> None:
    monkeypatch.setattr("skelly_ai.classic_audio.shutil.which", lambda _: "/usr/bin/wpctl")

    async def completed_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("skelly_ai.classic_audio.asyncio.sleep", completed_sleep)
    audio = BluetoothClassicAudio(name_filter="Skelly(Live)")
    status_reads = 0

    async def fake_run_program(executable: str, *arguments: str, input_text=None) -> _CommandResult:
        nonlocal status_reads
        del executable, input_text
        if arguments == ("status",):
            status_reads += 1
        return _CommandResult(0, "Audio\n ├─ Sinks:\n │  *   77. Built-in Audio Stereo")

    audio._run_program = fake_run_program  # type: ignore[method-assign]
    snapshot = await audio._route_pipewire_sink()

    assert status_reads == 120
    assert snapshot.sink_ready is False
    assert snapshot.last_error == (
        "Bluetooth connected, but the Skelly PipeWire audio output did not appear"
    )


@pytest.mark.asyncio
async def test_prepare_discovers_pairs_trusts_and_connects_first_use_speaker(monkeypatch) -> None:
    monkeypatch.setattr("skelly_ai.classic_audio.shutil.which", lambda _: "/usr/bin/bluetoothctl")
    audio = BluetoothClassicAudio(name_filter="Skelly(Live)")
    paired = False
    trusted = False
    connected = False
    calls: list[tuple[tuple[str, ...], str | None]] = []

    async def fake_run(*arguments: str, input_text: str | None = None) -> _CommandResult:
        nonlocal paired, trusted, connected
        calls.append((arguments, input_text))
        if arguments in (("devices", "Paired"), ("devices",)):
            name = "Animated Skelly(Live)" if arguments == ("devices",) else ""
            return _CommandResult(0, f"Device AA:BB:CC:DD:EE:02 {name}".rstrip() if name else "")
        if arguments[:3] == ("--timeout", "12", "scan"):
            return _CommandResult(0, "[NEW] Device AA:BB:CC:DD:EE:02 Animated Skelly(Live)")
        if arguments[0] == "pair":
            raise AssertionError("Pair must use the configured agent")
        if arguments[:3] == ("--agent", "KeyboardOnly", "pair"):
            paired = True
            return _CommandResult(0, "Pairing successful")
        if arguments[0] == "trust":
            trusted = True
            return _CommandResult(0, "trust succeeded")
        if arguments[0] == "connect":
            connected = True
            return _CommandResult(0, "Connection successful")
        if arguments[0] == "info":
            return _CommandResult(
                0,
                "\n".join(
                    (
                        "Device AA:BB:CC:DD:EE:02 (public)",
                        "Name: Animated Skelly(Live)",
                        f"Paired: {'yes' if paired else 'no'}",
                        f"Trusted: {'yes' if trusted else 'no'}",
                        f"Connected: {'yes' if connected else 'no'}",
                    )
                ),
            )
        raise AssertionError(arguments)

    audio._run = fake_run  # type: ignore[method-assign]

    async def fake_route() -> ClassicAudioSnapshot:
        return audio._update(sink_ready=True, sink_id="91", last_error=None)

    audio._route_pipewire_sink = fake_route  # type: ignore[method-assign]
    snapshot = await audio.prepare("1234")

    assert snapshot.device_name == "Animated Skelly(Live)"
    assert snapshot.paired is True
    assert snapshot.trusted is True
    assert snapshot.connected is True
    assert snapshot.sink_ready is True
    assert (("--agent", "KeyboardOnly", "pair", "AA:BB:CC:DD:EE:02"), "1234\n") in calls


@pytest.mark.asyncio
async def test_prepare_recovers_from_stale_factory_reset_pairing(monkeypatch) -> None:
    monkeypatch.setattr("skelly_ai.classic_audio.shutil.which", lambda _: "/usr/bin/bluetoothctl")

    async def completed_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("skelly_ai.classic_audio.asyncio.sleep", completed_sleep)
    audio = BluetoothClassicAudio(address="AA:BB:CC:DD:EE:02")
    pair_attempts = 0
    paired = False
    connected = False
    calls: list[tuple[str, ...]] = []

    async def fake_run(*arguments: str, input_text: str | None = None) -> _CommandResult:
        nonlocal pair_attempts, paired, connected
        del input_text
        calls.append(arguments)
        if arguments[0] == "info":
            return _CommandResult(
                0,
                "\n".join(
                    (
                        "Device AA:BB:CC:DD:EE:02 (public)",
                        "Name: Animated Skelly(Live)",
                        f"Paired: {'yes' if paired else 'no'}",
                        "Trusted: no",
                        f"Connected: {'yes' if connected else 'no'}",
                    )
                ),
            )
        if arguments[:3] == ("--agent", "KeyboardOnly", "pair"):
            pair_attempts += 1
            if pair_attempts == 1:
                return _CommandResult(1, "Failed to pair: org.bluez.Error.AuthenticationCanceled")
            paired = True
            return _CommandResult(0, "Pairing successful")
        if arguments[0] == "remove":
            return _CommandResult(0, "Device has been removed")
        if arguments[:3] == ("--timeout", "12", "scan"):
            return _CommandResult(0, "[NEW] Device AA:BB:CC:DD:EE:02 Animated Skelly(Live)")
        if arguments[0] == "trust":
            return _CommandResult(0, "trust succeeded")
        if arguments[0] == "connect":
            connected = True
            return _CommandResult(0, "Connection successful")
        raise AssertionError(arguments)

    audio._run = fake_run  # type: ignore[method-assign]

    async def fake_route() -> ClassicAudioSnapshot:
        return audio._update(sink_ready=True, sink_id="91", last_error=None)

    audio._route_pipewire_sink = fake_route  # type: ignore[method-assign]
    snapshot = await audio.prepare("1234")

    assert pair_attempts == 2
    assert ("remove", "AA:BB:CC:DD:EE:02") in calls
    assert ("--timeout", "12", "scan", "bredr") in calls
    assert snapshot.paired is True
    assert snapshot.connected is True
    assert snapshot.sink_ready is True


@pytest.mark.asyncio
async def test_paired_skelly_speaker_is_discovered_and_connected(monkeypatch) -> None:
    monkeypatch.setattr("skelly_ai.classic_audio.shutil.which", lambda _: "/usr/bin/bluetoothctl")
    audio = BluetoothClassicAudio()
    connected = False

    async def fake_run(*arguments: str) -> _CommandResult:
        nonlocal connected
        if arguments == ("devices", "Paired"):
            return _CommandResult(0, "Device AA:BB:CC:DD:EE:02 ServoSkelly(Live)")
        if arguments[0] == "connect":
            connected = True
            return _CommandResult(0, "Connection successful")
        if arguments[0] == "info":
            return _CommandResult(
                0,
                "\n".join(
                    (
                        "Device AA:BB:CC:DD:EE:02 (public)",
                        "Name: ServoSkelly(Live)",
                        "Paired: yes",
                        "Trusted: yes",
                        f"Connected: {'yes' if connected else 'no'}",
                    )
                ),
            )
        raise AssertionError(arguments)

    audio._run = fake_run  # type: ignore[method-assign]
    async def fake_route() -> ClassicAudioSnapshot:
        return audio._update(sink_ready=True, sink_id="91", last_error=None)

    audio._route_pipewire_sink = fake_route  # type: ignore[method-assign]

    before = await audio.refresh()
    after = await audio.connect()

    assert before.address == "AA:BB:CC:DD:EE:02"
    assert before.paired is True
    assert before.connected is False
    assert after.connected is True
    assert after.sink_ready is True
    assert after.device_name == "ServoSkelly(Live)"


def test_audio_connect_endpoint_reports_state() -> None:
    class FakeAudio:
        def __init__(self) -> None:
            self.connected = False

        def snapshot(self) -> ClassicAudioSnapshot:
            return ClassicAudioSnapshot(
                available=True,
                connected=self.connected,
                paired=True,
                trusted=True,
                sink_ready=self.connected,
                sink_id="91" if self.connected else None,
                address="AA:BB:CC:DD:EE:02",
                device_name="ServoSkelly(Live)",
                last_error=None,
                changed_at="2026-08-10T00:00:00+00:00",
            )

        async def refresh(self) -> ClassicAudioSnapshot:
            return self.snapshot()

        async def connect(self) -> ClassicAudioSnapshot:
            self.connected = True
            return self.snapshot()

        async def disconnect(self) -> ClassicAudioSnapshot:
            self.connected = False
            return self.snapshot()

    audio = FakeAudio()
    app = create_app(Settings(), classic_audio_client=audio)
    with TestClient(app) as client:
        connected = client.post("/api/audio/connect")
        status = client.get("/api/status")
        disconnected = client.post("/api/audio/disconnect")

    assert connected.status_code == 200
    assert connected.json()["connected"] is True
    assert status.json()["audio"]["connected"] is True
    assert disconnected.json()["connected"] is False


def test_prepare_connect_enables_live_mode_before_connecting_speaker() -> None:
    class FakeAudio:
        def __init__(self) -> None:
            self.connected = False

        def snapshot(self) -> ClassicAudioSnapshot:
            return ClassicAudioSnapshot(
                available=True,
                connected=self.connected,
                paired=True,
                trusted=True,
                sink_ready=self.connected,
                sink_id="91" if self.connected else None,
                address="AA:BB:CC:DD:EE:02",
                device_name="ServoSkelly(Live)",
                last_error=None,
                changed_at="2026-08-10T00:00:00+00:00",
            )

        async def refresh(self) -> ClassicAudioSnapshot:
            return self.snapshot()

        async def connect(self) -> ClassicAudioSnapshot:
            self.connected = True
            return self.snapshot()

        async def disconnect(self) -> ClassicAudioSnapshot:
            self.connected = False
            return self.snapshot()

    app = create_app(Settings(), classic_audio_client=FakeAudio())
    with TestClient(app) as client:
        client.post("/api/hardware/connect", json={})
        connected = client.post("/api/audio/prepare-connect")
        status = client.get("/api/status")

    assert connected.status_code == 200
    assert connected.json()["sink_ready"] is True
    assert status.json()["hardware"]["live_mode"] is True


def test_prepare_connect_automatically_performs_second_pipewire_routing_pass() -> None:
    class DelayedSinkAudio:
        def __init__(self) -> None:
            self.connected = False
            self.routed = False
            self.connect_calls = 0
            self.refresh_calls = 0

        def snapshot(self) -> ClassicAudioSnapshot:
            return ClassicAudioSnapshot(
                available=True,
                connected=self.connected,
                paired=True,
                trusted=True,
                sink_ready=self.routed,
                sink_id="91" if self.routed else None,
                address="AA:BB:CC:DD:EE:02",
                device_name="Animated Skelly(Live)",
                last_error=None if self.routed else "PipeWire output did not appear",
                changed_at="2026-08-10T00:00:00+00:00",
            )

        async def prepare(self, pin: str) -> ClassicAudioSnapshot:
            assert pin == "1234"
            self.connected = True
            return self.snapshot()

        async def refresh(self) -> ClassicAudioSnapshot:
            self.refresh_calls += 1
            return self.snapshot()

        async def connect(self) -> ClassicAudioSnapshot:
            self.connect_calls += 1
            self.routed = True
            return self.snapshot()

        async def disconnect(self) -> ClassicAudioSnapshot:
            self.connected = False
            self.routed = False
            return self.snapshot()

    audio = DelayedSinkAudio()
    app = create_app(Settings(), classic_audio_client=audio)
    with TestClient(app) as client:
        client.post("/api/hardware/connect", json={})
        connected = client.post("/api/audio/prepare-connect")

    assert connected.status_code == 200
    assert connected.json()["sink_ready"] is True
    assert audio.refresh_calls == 2
    assert audio.connect_calls == 1

@pytest.mark.asyncio
async def test_connect_reclaims_skelly_for_dadtech_when_bluez_connected_without_sink(monkeypatch) -> None:
    monkeypatch.setattr("skelly_ai.classic_audio.shutil.which", lambda _: "/usr/bin/bluetoothctl")
    audio = BluetoothClassicAudio(address="AA:BB:CC:DD:EE:02")
    connected = True
    calls: list[tuple[str, ...]] = []
    claim_events: list[str] = []

    async def pause() -> bool:
        claim_events.append("pause")
        return True

    async def resume() -> None:
        claim_events.append("resume")

    async def fake_run(*arguments: str, input_text=None) -> _CommandResult:
        nonlocal connected
        del input_text
        calls.append(arguments)
        if arguments[0] == "info":
            return _CommandResult(0, "\n".join((
                "Device AA:BB:CC:DD:EE:02 (public)",
                "Name: Animated Skelly(Live)",
                "Paired: yes",
                "Trusted: yes",
                f"Connected: {'yes' if connected else 'no'}",
            )))
        if arguments[0] == "disconnect":
            connected = False
            return _CommandResult(0, "Successful disconnected")
        if arguments[0] == "connect":
            connected = True
            return _CommandResult(0, "Connection successful")
        raise AssertionError(arguments)

    async def no_sink() -> ClassicAudioSnapshot:
        return audio._update(sink_ready=False, sink_id=None, sink_name=None)

    async def routed() -> ClassicAudioSnapshot:
        return audio._update(sink_ready=True, sink_id="92", sink_name="bluez_output.AA_BB_CC_DD_EE_02.1")

    monkeypatch.setattr(audio, "_pause_competing_audio_session", pause)
    monkeypatch.setattr(audio, "_resume_competing_audio_session", resume)
    monkeypatch.setattr(audio, "_run", fake_run)
    monkeypatch.setattr(audio, "_read_pipewire_status", no_sink)
    monkeypatch.setattr(audio, "_route_pipewire_sink", routed)

    result = await audio.connect(route=True)

    assert result.sink_ready is True
    assert ("disconnect", "AA:BB:CC:DD:EE:02") in calls
    assert ("connect", "AA:BB:CC:DD:EE:02") in calls
    assert claim_events == ["pause", "resume"]


@pytest.mark.asyncio
async def test_connect_does_not_bounce_skelly_when_dadtech_already_owns_sink(monkeypatch) -> None:
    monkeypatch.setattr("skelly_ai.classic_audio.shutil.which", lambda _: "/usr/bin/bluetoothctl")
    audio = BluetoothClassicAudio(address="AA:BB:CC:DD:EE:02")
    calls: list[tuple[str, ...]] = []

    async def pause() -> bool:
        return True

    async def resume() -> None:
        return None

    async def fake_run(*arguments: str, input_text=None) -> _CommandResult:
        del input_text
        calls.append(arguments)
        if arguments[0] == "info":
            return _CommandResult(0, "\n".join((
                "Device AA:BB:CC:DD:EE:02 (public)",
                "Name: Animated Skelly(Live)",
                "Paired: yes",
                "Trusted: yes",
                "Connected: yes",
            )))
        raise AssertionError(arguments)

    async def has_sink() -> ClassicAudioSnapshot:
        return audio._update(sink_ready=True, sink_id="92", sink_name="bluez_output.AA_BB_CC_DD_EE_02.1")

    monkeypatch.setattr(audio, "_pause_competing_audio_session", pause)
    monkeypatch.setattr(audio, "_resume_competing_audio_session", resume)
    monkeypatch.setattr(audio, "_run", fake_run)
    monkeypatch.setattr(audio, "_read_pipewire_status", has_sink)
    monkeypatch.setattr(audio, "_route_pipewire_sink", has_sink)

    result = await audio.connect(route=True)

    assert result.sink_ready is True
    assert not any(call[0] in {"disconnect", "connect"} for call in calls)
