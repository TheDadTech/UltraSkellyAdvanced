import pytest

from skelly_ai.hardware import EyeIcon, Movement, SimulatedSkelly


@pytest.mark.asyncio
async def test_simulated_skelly_tracks_commands() -> None:
    hardware = SimulatedSkelly()
    await hardware.connect()

    await hardware.set_eye(EyeIcon.HEARTS)
    await hardware.set_movement(Movement.TORSO_AND_ARMS)
    await hardware.set_live_mode(True)

    snapshot = hardware.snapshot()
    assert snapshot.connected is True
    assert snapshot.eye_icon == EyeIcon.HEARTS
    assert snapshot.movement == Movement.TORSO_AND_ARMS
    assert snapshot.live_mode is True
    assert snapshot.event_count == 4

    snapshot = await hardware.stop()
    assert snapshot.movement == Movement.NONE
