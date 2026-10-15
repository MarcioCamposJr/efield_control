"""Exercise the real example workflow with hardware replaced at the driver boundary."""

import csv
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest

from efield_control import cli
from efield_control.configuration import PoseOffset, load_project_config
from efield_control.domain import Pose
from efield_control.drivers.simulated import GaussianAcquisition, SimulatedRobot
from examples.center_sensor import main


PROJECT_DIRECTORY = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("robot_type", ["elfin", "dobot"])
@pytest.mark.parametrize("interrupted", [False, True])
def test_example_centers_and_saves_or_stops_on_interrupt(
    tmp_path, monkeypatch, capsys, robot_type, interrupted,
):
    config = load_project_config(
        config_path=PROJECT_DIRECTORY / "config/default.toml",
        env_path=tmp_path / ".env",
        angular_calibration_path=PROJECT_DIRECTORY / "config/calibration/angular_stage.toml",
        sensor_calibration_path=PROJECT_DIRECTORY / "config/calibration/sensor_pose.toml",
        environ={},
    )
    config = replace(
        config,
        hardware=replace(config.hardware, robot_type=robot_type, robot_host="robot.test",
                         red_pitaya_host="rp.test", stage_serial_port="test-port"),
        pulse=replace(config.pulse, source="serial"),
        storage=replace(config.storage, output_directory=str(tmp_path / "results")),
        sensor_calibration=replace(config.sensor_calibration,
                                   coil_center_guess=PoseOffset(x_mm=1, y_mm=-1, z_mm=2)),
    )
    loader = Mock(return_value=config)
    monkeypatch.setattr(cli, "load_project_config", loader)
    simulated_robot = SimulatedRobot(Pose(10, 20, 30, 1, 2, 3))
    robot = Mock(wraps=simulated_robot)
    device = Mock(wraps=GaussianAcquisition(simulated_robot, center_x_mm=14, center_y_mm=17))
    pulse = Mock()
    robot_factory = Mock(return_value=robot)
    unused_robot_factory = Mock(side_effect=AssertionError("Wrong robot selected"))
    monkeypatch.setattr(cli, "ElfinRobotAdapter",
                        robot_factory if robot_type == "elfin" else unused_robot_factory)
    monkeypatch.setattr(cli, "DobotRobotAdapter",
                        robot_factory if robot_type == "dobot" else unused_robot_factory)
    monkeypatch.setattr(cli, "RedPitayaAcquisition", Mock(return_value=device))
    monkeypatch.setattr(cli, "SerialMotorController", Mock(return_value=pulse))
    # Fail any accidental attempt to open real network or serial connections.
    monkeypatch.setattr("socket.socket", Mock(side_effect=AssertionError("Hardware connection")))
    monkeypatch.setattr("serial.Serial", Mock(side_effect=AssertionError("Serial connection")))
    if interrupted:
        device.read_waveform.side_effect = KeyboardInterrupt

    assert main(["--confirm-hardware", "MOVE_AND_FIRE"]) == (130 if interrupted else 0)

    loader.assert_called_once_with(
        config_path=str(PROJECT_DIRECTORY / "config/default.toml"),
        env_path=str(PROJECT_DIRECTORY / ".env"),
        angular_calibration_path=str(PROJECT_DIRECTORY / "config/calibration/angular_stage.toml"),
        sensor_calibration_path=str(PROJECT_DIRECTORY / "config/calibration/sensor_pose.toml"),
    )
    assert robot_factory.call_args.args == ("robot.test",)
    assert robot_factory.call_args.kwargs["speed_percent"] == config.robot.speed_percent
    robot.disconnect.assert_called_once()
    device.close.assert_called_once()
    pulse.close.assert_called_once()
    pulse.ping.assert_called_once()
    assert pulse.fire.call_count == device.arm.call_count > 0
    for call in robot.move_to.call_args_list:
        pose = call.args[0]
        assert (pose.z_mm, pose.rx_deg, pose.ry_deg, pose.rz_deg) == (32, 1, 2, 3)

    if interrupted:
        robot.stop.assert_called_once()
        assert "Operation interrupted" in capsys.readouterr().err
    else:
        robot.stop.assert_not_called()
        assert simulated_robot.current_pose() == Pose(14, 17, 32, 1, 2, 3)
        run_directory, = (tmp_path / "results").iterdir()
        assert (run_directory / "resolved_config.json").is_file()
        with (run_directory / "summary.csv").open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        assert (float(rows[0]["x_mm"]), float(rows[0]["y_mm"])) == (11, 19)
        assert any(float(row["x_mm"]) == 14 and float(row["y_mm"]) == 17 for row in rows)
        assert list((run_directory / "waveforms").glob("*.csv"))
        assert "Center found" in capsys.readouterr().out
