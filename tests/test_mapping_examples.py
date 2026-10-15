"""Run acquisition examples through real workflows with equipment replaced in tests."""

import csv
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest

from efield_control import cli
from efield_control.configuration import PoseOffset, load_project_config
from efield_control.domain import Pose, Waveform
from efield_control.drivers.simulated import SimulatedRobot
from examples.acquire_planar import main as acquire_planar
from examples.acquire_circular import main as acquire_circular


PROJECT_DIRECTORY = Path(__file__).resolve().parents[1]


@pytest.fixture
def mapping_config(tmp_path, monkeypatch):
    config = load_project_config(
        config_path=PROJECT_DIRECTORY / "config/default.toml",
        env_path=tmp_path / ".env",
        angular_calibration_path=PROJECT_DIRECTORY / "config/calibration/angular_stage.toml",
        sensor_calibration_path=PROJECT_DIRECTORY / "config/calibration/sensor_pose.toml",
        environ={},
    )
    config = replace(
        config,
        hardware=replace(config.hardware, robot_type="elfin", robot_host="robot.test",
                         red_pitaya_host="rp.test", stage_serial_port="test-port"),
        pulse=replace(config.pulse, source="serial"),
        storage=replace(config.storage, output_directory=str(tmp_path / "results")),
        sensor_calibration=replace(config.sensor_calibration,
                                   coil_center_guess=PoseOffset(x_mm=1000, y_mm=1000)),
        planar_mapping=replace(config.planar_mapping, x_start_mm=-1, x_stop_mm=1,
                               x_step_mm=1, y_start_mm=-2, y_stop_mm=2, y_step_mm=4),
    )
    monkeypatch.setattr(cli, "load_project_config", Mock(return_value=config))
    for name in ("SensorCentering", "CenterSensorWorkflow", "calibrated_center_guess"):
        monkeypatch.setattr(cli, name, Mock(side_effect=AssertionError("Unexpected centering")))
    monkeypatch.setattr("socket.socket", Mock(side_effect=AssertionError("Hardware connection")))
    monkeypatch.setattr("serial.Serial", Mock(side_effect=AssertionError("Serial connection")))
    return config


def read_summary(config):
    run_directory, = Path(config.storage.output_directory).iterdir()
    assert (run_directory / "resolved_config.json").is_file()
    with (run_directory / "summary.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert len(list((run_directory / "waveforms").glob("*.csv"))) == len(rows)
    return rows


@pytest.mark.parametrize("interrupted", [False, True])
def test_planar_acquires_grid_from_current_pose_without_centering(
    mapping_config, monkeypatch, interrupted,
):
    robot = Mock(wraps=SimulatedRobot(Pose(10, 20, 30, 1, 2, 3)))
    device = Mock()
    waveform = Waveform.from_iterables((-0.5, 0.5), (-0.25, 0.25), 15_625_000)
    device.read_waveform.return_value = waveform
    if interrupted:
        device.read_waveform.side_effect = [waveform, KeyboardInterrupt]
    controller = Mock()
    monkeypatch.setattr(cli, "ElfinRobotAdapter", Mock(return_value=robot))
    monkeypatch.setattr(cli, "RedPitayaAcquisition", Mock(return_value=device))
    monkeypatch.setattr(cli, "SerialMotorController", Mock(return_value=controller))

    assert acquire_planar(["--confirm-hardware", "MOVE_AND_FIRE"]) == (130 if interrupted else 0)

    expected_xy = [(9, 18), (10, 18), (11, 18), (11, 22), (10, 22), (9, 22)]
    expected_moves = expected_xy[:2] if interrupted else expected_xy
    assert [call.args[0] for call in robot.move_to.call_args_list] == [
        Pose(x, y, 30, 1, 2, 3) for x, y in expected_moves
    ]
    assert device.arm.call_count == controller.fire.call_count == len(expected_moves)
    rows = read_summary(mapping_config)
    assert [(float(row["x_mm"]), float(row["y_mm"])) for row in rows] == (
        expected_xy[:1] if interrupted else expected_xy
    )
    assert all(row["mode"] == "planar" and float(row["z_mm"]) == 30 for row in rows)
    if interrupted:
        robot.stop.assert_called_once()
    else:
        robot.stop.assert_not_called()
    robot.disconnect.assert_called_once()
    device.close.assert_called_once()
    controller.close.assert_called_once()


@pytest.mark.parametrize("center_first", [False, True])
@pytest.mark.parametrize("interrupted", [False, True])
def test_circular_acquires_calibrated_angles_without_robot_or_sensor_centering(
    mapping_config, monkeypatch, center_first, interrupted,
):
    config = replace(
        mapping_config,
        circular_mapping=replace(
            mapping_config.circular_mapping,
            base_start_deg=-10, base_stop_deg=10, base_step_deg=20,
            inclination_start_deg=-5, inclination_stop_deg=5, inclination_step_deg=10,
            center_before_mapping=center_first,
        ),
    )
    monkeypatch.setattr(cli, "load_project_config", Mock(return_value=config))
    monkeypatch.setattr(cli, "_robot", Mock(side_effect=AssertionError("Unexpected robot")))
    device = Mock()
    waveform = Waveform.from_iterables((-0.5, 0.5), (-0.25, 0.25), 15_625_000)
    device.read_waveform.return_value = waveform
    if interrupted:
        device.read_waveform.side_effect = [waveform, KeyboardInterrupt]
    controller = Mock()
    monkeypatch.setattr(cli, "RedPitayaAcquisition", Mock(return_value=device))
    monkeypatch.setattr(cli, "SerialMotorController", Mock(return_value=controller))

    assert acquire_circular(["--confirm-hardware", "MOVE_AND_FIRE"]) == (130 if interrupted else 0)

    expected_logical = [(-10, -5), (10, -5), (10, 5), (-10, 5)]
    expected_physical = [(80, 87), (100, 87), (100, 97), (80, 97)]
    expected_moves = expected_physical[:2] if interrupted else expected_physical
    if center_first:
        expected_moves = [(90, 92), *expected_moves]
    assert [call.args for call in controller.move_to.call_args_list] == expected_moves
    controller.center.assert_not_called()
    controller.ping.assert_called_once()
    assert device.arm.call_count == controller.fire.call_count == (2 if interrupted else 4)
    rows = read_summary(config)
    assert [(float(row["base_deg"]), float(row["inclination_deg"])) for row in rows] == (
        expected_logical[:1] if interrupted else expected_logical
    )
    assert all(row["mode"] == "circular" for row in rows)
    device.close.assert_called_once()
    controller.close.assert_called_once()


def test_circular_rejects_out_of_range_angles_before_connecting(mapping_config, monkeypatch):
    config = replace(
        mapping_config,
        circular_mapping=replace(mapping_config.circular_mapping, base_start_deg=-100),
    )
    monkeypatch.setattr(cli, "load_project_config", Mock(return_value=config))
    acquisition_factory = Mock(side_effect=AssertionError("Unexpected acquisition connection"))
    controller_factory = Mock(side_effect=AssertionError("Unexpected serial connection"))
    monkeypatch.setattr(cli, "RedPitayaAcquisition", acquisition_factory)
    monkeypatch.setattr(cli, "SerialMotorController", controller_factory)
    with pytest.raises(ValueError):
        acquire_circular(["--confirm-hardware", "MOVE_AND_FIRE"])
    acquisition_factory.assert_not_called()
    controller_factory.assert_not_called()
