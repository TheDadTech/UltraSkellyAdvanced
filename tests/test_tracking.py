from skelly_ai.api import _listening_head_pose
from skelly_ai.config import Settings
from skelly_ai.sensors import _tracking_target


def test_tracking_prefers_largest_face_and_reports_screen_position() -> None:
    target = _tracking_target(
        faces=[(20, 30, 40, 40), (400, 100, 120, 100)],
        people=[(50, 40, 300, 400)],
        width=640,
        height=480,
    )

    assert target["target_visible"] is True
    assert target["target_source"] == "face"
    assert target["target_x_percent"] == 71.9
    assert target["target_y_percent"] == 31.2


def test_listening_pose_has_dead_zone_limits_tilt_and_supports_inversion() -> None:
    centered = _listening_head_pose(
        {"target_x_percent": 56.0},
        yaw_center=127,
        tilt_center=127,
        yaw_range=38,
        dead_zone_percent=8.0,
        tilt_offset=18,
        yaw_inverted=False,
    )
    right = _listening_head_pose(
        {"target_x_percent": 100.0},
        yaw_center=127,
        tilt_center=250,
        yaw_range=38,
        dead_zone_percent=8.0,
        tilt_offset=18,
        yaw_inverted=False,
    )
    inverted = _listening_head_pose(
        {"target_x_percent": 100.0},
        yaw_center=127,
        tilt_center=127,
        yaw_range=38,
        dead_zone_percent=8.0,
        tilt_offset=18,
        yaw_inverted=True,
    )

    assert centered == {"yaw": 127, "tilt": 145}
    assert right == {"yaw": 165, "tilt": 255}
    assert inverted == {"yaw": 89, "tilt": 145}


def test_interactive_listening_defaults_allow_normal_sentence_pauses() -> None:
    settings = Settings()

    assert settings.perception_record_seconds == 10
    assert settings.perception_silence_seconds == 1.4
