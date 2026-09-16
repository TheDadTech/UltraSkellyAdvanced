import pytest

from skelly_ai import ble_protocol
from skelly_ai.ble_hardware import BleSkelly
from skelly_ai.hardware import EyeIcon, HardwareUnavailable, Movement


class FakeDevice:
    address = "AA:BB:CC:DD:EE:01"
    name = "Animated Skelly"


class FakeScanner:
    @staticmethod
    async def find_device_by_address(address: str, timeout: float):
        assert address == FakeDevice.address
        assert timeout > 0
        return FakeDevice()

    @staticmethod
    async def find_device_by_filter(filter_fn, timeout: float):
        raise AssertionError("Address lookup should be used in this test")


class FakeService:
    uuid = ble_protocol.SERVICE_UUID


class FakeClient:
    instances = []

    def __init__(self, device, timeout, disconnected_callback):
        self.device = device
        self.timeout = timeout
        self.disconnected_callback = disconnected_callback
        self.is_connected = False
        self.services = [FakeService()]
        self.writes: list[tuple[str, bytes, bool]] = []
        self.notify_uuid = None
        FakeClient.instances.append(self)

    async def connect(self):
        self.is_connected = True

    async def disconnect(self):
        self.is_connected = False

    async def start_notify(self, uuid, callback):
        self.notify_uuid = uuid
        self.notification_callback = callback

    async def stop_notify(self, uuid):
        assert uuid == self.notify_uuid

    async def write_gatt_char(self, uuid, command, response):
        self.writes.append((uuid, command, response))


def test_protocol_commands_match_verified_controller_frames() -> None:
    assert ble_protocol.set_eye_icon(1).hex().upper() == (
        "AAF9010000000000000073"
    )
    assert ble_protocol.set_movement(0).hex().upper() == (
        "AACA000000000000000012"
    )
    assert ble_protocol.set_movement(1).hex().upper() == (
        "AACA010000000000000051"
    )
    assert ble_protocol.set_classic_audio(True).hex().upper() == (
        "AAFD0100000000000000D1"
    )
    assert ble_protocol.query_version().hex().upper() == (
        "AAEE0000000000000000DD"
    )
    assert ble_protocol.query_media_files().hex().upper() == (
        "AAD00000000000000000A4"
    )
    assert ble_protocol.query_media_order().hex().upper() == (
        "AAD1000000000000000000"
    )
    assert ble_protocol.play_media_file(1).hex().upper() == (
        "AAC60001010000000000E7"
    )
    assert ble_protocol.set_volume(100).hex().upper() == (
        "AAFA640000000000000031"
    )
    with pytest.raises(ValueError, match="between 0 and 100"):
        ble_protocol.set_volume(101)
    assert ble_protocol.set_light_brightness(1, 200).hex().upper() == (
        "AAF301C8000000000000DE"
    )
    assert ble_protocol.set_light_mode(0, 2).hex().upper() == (
        "AAF20002000000000000E2"
    )
    assert ble_protocol.set_light_rgb(1, 10, 20, 30).hex().upper() == (
        "AAF4010A141E0000000000007E"
    )
    assert ble_protocol.end_media_transfer().hex().upper() == (
        "AAC200000000000000004F"
    )
    assert ble_protocol.probe_movement_value(8).hex().upper().startswith("AACA08")
    assert ble_protocol.probe_movement_value(248).hex().upper().startswith("AACAF8")
    with pytest.raises(ValueError, match="steps of 0x08"):
        ble_protocol.probe_movement_bit(3)


def test_ble_file_transfer_tracks_device_resume_request() -> None:
    hardware = BleSkelly(
        address=FakeDevice.address,
        scanner=FakeScanner,
        client_factory=FakeClient,
    )

    hardware._parse_notification("BBC1010007")

    assert hardware._chunk_resume_from == 7


@pytest.mark.asyncio
async def test_ble_connect_is_motionless_and_movement_requires_arming() -> None:
    FakeClient.instances.clear()
    hardware = BleSkelly(
        address=FakeDevice.address,
        scanner=FakeScanner,
        client_factory=FakeClient,
    )

    connected = await hardware.connect()
    client = FakeClient.instances[-1]

    assert connected.connected is True
    assert connected.movement_armed is False
    assert [write[1] for write in client.writes] == [ble_protocol.query_version()]
    assert client.notify_uuid == ble_protocol.NOTIFY_UUID

    await hardware.set_eye(EyeIcon.NORMAL)
    assert client.writes[-1][1] == ble_protocol.set_eye_icon(1)

    with pytest.raises(HardwareUnavailable, match="disarmed"):
        await hardware.set_movement(Movement.HEAD_ONLY)

    await hardware.arm_movement(True)
    await hardware.set_movement(Movement.HEAD_ONLY)
    assert client.writes[-1][1] == ble_protocol.set_movement(1)

    disarmed = await hardware.arm_movement(False)
    assert disarmed.movement_armed is False
    assert disarmed.movement == Movement.NONE
    assert client.writes[-1][1] == ble_protocol.set_movement(0)


@pytest.mark.asyncio
async def test_ble_movement_probe_is_restricted_armed_and_always_stops() -> None:
    FakeClient.instances.clear()
    hardware = BleSkelly(
        address=FakeDevice.address,
        scanner=FakeScanner,
        client_factory=FakeClient,
    )
    await hardware.connect()
    client = FakeClient.instances[-1]

    with pytest.raises(HardwareUnavailable, match="disarmed"):
        await hardware.probe_movement_bit(8, 100)

    await hardware.arm_movement(True)
    result = await hardware.probe_movement_bit(8, 100)

    assert result.movement == Movement.NONE
    assert client.writes[-2][1] == ble_protocol.probe_movement_value(8)
    assert client.writes[-1][1] == ble_protocol.set_movement(0)


def test_head_and_torso_combination_uses_verified_bitfield_layout() -> None:
    assert ble_protocol.set_movement(5).hex().upper().startswith("AACA05")
