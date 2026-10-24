import pytest
from skelly_ai.hardware import SimulatedSkelly, Movement


@pytest.mark.asyncio
async def test_commanded_camera_movement_includes_settling_after_stop(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr('skelly_ai.hardware.time.monotonic', lambda: clock[0])
    hardware = SimulatedSkelly()
    assert not hardware.camera_motion_active()
    await hardware.connect()
    await hardware.arm_movement(True)
    await hardware.set_movement(Movement.HEAD_AND_TORSO)
    clock[0] += 10
    assert hardware.camera_motion_active()
    await hardware.stop()
    assert hardware.camera_motion_active()
    clock[0] += 1.6
    assert not hardware.camera_motion_active()
