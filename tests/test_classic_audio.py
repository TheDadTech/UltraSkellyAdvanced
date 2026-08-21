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
    snapshot = await audio.prepare("0727")

    assert snapshot.device_name == "Animated Skelly(Live)"
    assert snapshot.paired is True
    assert snapshot.trusted is True
    assert snapshot.connected is True
    assert snapshot.sink_ready is True
    assert (("--agent", "KeyboardOnly", "pair", "AA:BB:CC:DD:EE:02"), "0727\n") in calls


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
