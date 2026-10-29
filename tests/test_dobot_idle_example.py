"""Idle diagnostics use fake equipment and never send physical movements."""

from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

from efield_control.domain import Pose
from efield_control.drivers.robots.common import RobotMotionSettings
from examples import check_dobot_idle as example


@pytest.fixture
def equipment(monkeypatch):
    config = SimpleNamespace(
        hardware=SimpleNamespace(robot_type="dobot", robot_host="robot.test"),
        robot=RobotMotionSettings(),
    )
    monkeypatch.setattr(example, "load_project_config", Mock(return_value=config))
    robot = Mock()
    robot.current_pose.return_value = Pose(10, 20, 30, 1, 2, 3)
    factory = Mock(return_value=robot)
    monkeypatch.setattr(example, "DobotRobotAdapter", factory)
    sleep = Mock()
    monkeypatch.setattr(example.time, "sleep", sleep)
    monkeypatch.setattr("socket.socket", Mock(side_effect=AssertionError("Real connection")))
    return robot, factory, sleep


@pytest.mark.parametrize("wait_s", [0, 20])
def test_wait_precedes_movement_and_success_returns_to_origin(equipment, capsys, wait_s):
    robot, factory, sleep = equipment
    events = Mock()
    events.attach_mock(sleep, "sleep")
    events.attach_mock(robot.move_to, "move")
    assert example.main([
        "--dx-mm", "-1", "--wait-s", str(wait_s), "--confirm-hardware", "MOVE_ONLY",
    ]) == 0
    assert events.mock_calls == [
        call.sleep(wait_s), call.move(Pose(9, 20, 30, 1, 2, 3)),
        call.move(Pose(10, 20, 30, 1, 2, 3)),
    ]
    factory.assert_called_once()
    robot.disconnect.assert_called_once()
    assert "test passed" in capsys.readouterr().out


@pytest.mark.parametrize("failure", [ConnectionError("closed"), KeyboardInterrupt()])
def test_failed_movement_is_not_retried_or_followed_by_return(equipment, capsys, failure):
    robot, _, _ = equipment
    robot.move_to.side_effect = failure
    with pytest.raises(type(failure)):
        example.main(["--dx-mm", "1", "--confirm-hardware", "MOVE_ONLY"])
    robot.move_to.assert_called_once()
    robot.disconnect.assert_called_once()
    assert "Failed during outbound movement" in capsys.readouterr().out


@pytest.mark.parametrize("arguments", [
    ["--dx-mm", "1"],
    ["--dx-mm", "nan", "--confirm-hardware", "MOVE_ONLY"],
    ["--dx-mm", "0.01", "--confirm-hardware", "MOVE_ONLY"],
    ["--dx-mm", "1", "--wait-s", "-1", "--confirm-hardware", "MOVE_ONLY"],
    ["--dx-mm", "1", "--wait-s", "inf", "--confirm-hardware", "MOVE_ONLY"],
])
def test_invalid_parameters_never_construct_robot(equipment, arguments):
    _, factory, _ = equipment
    with pytest.raises(SystemExit):
        example.main(arguments)
    factory.assert_not_called()
