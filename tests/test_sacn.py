import asyncio

import pytest

from skelly_ai.sacn import DacUnavailable, SacnDacController, build_e131_packet


class FakeSocket:
    def __init__(self) -> None:
        self.sent: list[tuple[bytes, tuple[str, int]]] = []
        self.closed = False

    def sendto(self, packet: bytes, target: tuple[str, int]) -> int:
        self.sent.append((packet, target))
        return len(packet)

    def close(self) -> None:
        self.closed = True


def test_e131_packet_layout_and_channel_slots() -> None:
    slots = bytearray(512)
    slots[0] = 19
    slots[4] = 55
    slots[6] = 77
    slots[11] = 121

    packet = build_e131_packet(
        cid=bytes(range(16)),
        source_name="Skelly AI test",
        universe=1,
        priority=90,
        sequence=23,
        slots=bytes(slots),
    )

    assert len(packet) == 638
    assert packet[4:16] == b"ASC-E1.17\x00\x00\x00"
    assert int.from_bytes(packet[16:18], "big") & 0x0FFF == 622
    assert int.from_bytes(packet[38:40], "big") & 0x0FFF == 600
    assert packet[108] == 90
    assert packet[111] == 23
    assert int.from_bytes(packet[113:115], "big") == 1
    assert int.from_bytes(packet[123:125], "big") == 513
    assert packet[125] == 0
    assert packet[126] == 19
    assert packet[130] == 55
    assert packet[132] == 77
    assert packet[137] == 121


@pytest.mark.asyncio
async def test_dac_arm_is_motionless_then_streams_tested_mapping() -> None:
    fake = FakeSocket()
    dac = SacnDacController(
        target="192.168.1.50",
        fps=1,
        cid=b"\x11" * 16,
        socket_factory=lambda *_: fake,
    )

    armed = await dac.arm()
    assert armed.armed is True
    assert armed.transmitting is False
    assert fake.sent == []

    active = await dac.set_position(jaw=20, tilt=50, yaw=70, pitch=120)
    assert active.transmitting is True
    packet, target = fake.sent[0]
    assert target == ("192.168.1.50", 5568)
    assert packet[126] == 255  # Controller slot 1: non-zero becomes jaw open.
    assert packet[130] == 50  # Controller slot 5: tilt / roll.
    assert packet[132] == 70  # Controller slot 7: no / yaw.
    assert packet[137] == 120  # Controller slot 12: yes / pitch.

    released = await dac.release()
    assert released.armed is False
    assert released.transmitting is False
    assert len(fake.sent) == 5
    assert fake.sent[-4][0][126] == 0  # Release closes the jaw first.
    assert all(packet[112] == 0x40 for packet, _ in fake.sent[-3:])
    await dac.close()
    assert fake.closed is True


@pytest.mark.asyncio
async def test_dac_rejects_position_while_disarmed() -> None:
    dac = SacnDacController(
        target="192.168.1.50",
        socket_factory=lambda *_: FakeSocket(),
    )
    with pytest.raises(DacUnavailable, match="disarmed"):
        await dac.set_position(yaw=127)
    await dac.close()


@pytest.mark.asyncio
async def test_jaw_is_normalized_to_binary_closed_or_open() -> None:
    fake = FakeSocket()
    dac = SacnDacController(
        target="192.168.1.50",
        socket_factory=lambda *_: fake,
    )
    await dac.arm()
    opened = await dac.set_position(jaw=1)
    assert opened.values["jaw"] == 255
    assert fake.sent[-1][0][126] == 255
    closed = await dac.set_position(jaw=0)
    assert closed.values["jaw"] == 0
    assert fake.sent[-1][0][126] == 0
    await dac.close()


@pytest.mark.asyncio
async def test_head_axes_reject_zero_while_jaw_still_accepts_zero() -> None:
    dac = SacnDacController(
        target="192.168.1.50",
        socket_factory=lambda *_: FakeSocket(),
    )
    await dac.arm()
    try:
        await dac.set_position(jaw=0)
        with pytest.raises(ValueError, match="between 1 and 255"):
            await dac.set_position(yaw=0)
    finally:
        await dac.close()


@pytest.mark.asyncio
async def test_rearming_never_carries_forward_an_open_jaw() -> None:
    fake = FakeSocket()
    dac = SacnDacController(
        target="192.168.1.50",
        socket_factory=lambda *_: fake,
    )
    await dac.arm()
    await dac.set_position(jaw=255)
    released = await dac.release()
    assert released.values["jaw"] == 0

    armed = await dac.arm()
    assert armed.values["jaw"] == 0
    await dac.set_position(yaw=140)
    assert fake.sent[-1][0][126] == 0
    await dac.close()


@pytest.mark.asyncio
async def test_dac_continues_streaming_after_first_command() -> None:
    fake = FakeSocket()
    dac = SacnDacController(
        target="192.168.1.50",
        fps=44,
        socket_factory=lambda *_: fake,
    )
    await dac.arm()
    await dac.set_position(jaw=10)
    await asyncio.sleep(0.03)
    assert len(fake.sent) >= 2
    await dac.release()
