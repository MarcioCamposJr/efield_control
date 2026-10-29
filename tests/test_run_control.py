"""Pause and stop requests must preserve completed points and close equipment."""

import csv
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest

from efield_control import cli
from efield_control.configuration import load_project_config
from efield_control.domain import Pose, Waveform
from efield_control.keyboard_control import KeyboardControl


def test_stop_takes_priority_over_pause(monkeypatch):
    control = KeyboardControl()
    monkeypatch.setattr(control, "_read_keys", lambda: "pRs")
    sleep = Mock(side_effect=AssertionError("STOP must not wait for resume"))
    monkeypatch.setattr(cli.time, "sleep", sleep)
    with pytest.raises(KeyboardInterrupt):
        control.checkpoint()
    sleep.assert_not_called()


@pytest.mark.parametrize("command", ["center", "planar", "circular"])
@pytest.mark.parametrize("action", ["resume", "stop", "interrupt"])
def test_pause_preserves_point_and_resume_or_stop_cleans_up(
    tmp_path, monkeypatch, capsys, command, action,
):
    config = load_project_config(environ={}, env_path=tmp_path / ".env")
    config = replace(
        config,
        hardware=replace(config.hardware, robot_host="robot.test", red_pitaya_host="rp.test",
                         stage_serial_port="unused"),
        pulse=replace(config.pulse, source="mtms_api"),
        acquisition=replace(config.acquisition, repetitions=2, repetition_interval_s=0),
        centering=replace(config.centering, max_iterations=1),
        storage=replace(config.storage, output_directory=str(tmp_path / "results")),
        planar_mapping=replace(config.planar_mapping, x_start_mm=0, x_stop_mm=1,
                               x_step_mm=1, y_start_mm=0, y_stop_mm=0, y_step_mm=1),
        circular_mapping=replace(config.circular_mapping, base_start_deg=0, base_stop_deg=5,
                                 base_step_deg=5, inclination_start_deg=0,
                                 inclination_stop_deg=0, inclination_step_deg=5,
                                 center_before_mapping=True),
    )
    monkeypatch.setattr(cli, "load_project_config", Mock(return_value=config))
    monkeypatch.setattr(cli.MtmsSingleChannelClient, "validate_environment", Mock())
    robot = Mock()
    robot.current_pose.return_value = Pose(0, 0, 0)
    acquisition = Mock()
    acquisition.read_waveform.return_value = Waveform((-1, 1), (-2, 2), 1000)
    controller, pulse = Mock(), Mock()
    monkeypatch.setattr(cli, "_robot", Mock(return_value=robot))
    monkeypatch.setattr(cli, "_acquisition", Mock(return_value=acquisition))
    monkeypatch.setattr(cli, "_mtms_if_requested", Mock(return_value=pulse))
    monkeypatch.setattr(cli, "SerialMotorController", Mock(return_value=controller))
    monkeypatch.setattr("socket.socket", Mock(side_effect=AssertionError("Real hardware")))
    keys = []
    monkeypatch.setattr(KeyboardControl, "__enter__", lambda self: self)
    monkeypatch.setattr(KeyboardControl, "_read_keys", lambda self: keys.pop(0) if keys else "")

    def directory():
        run_directory, = Path(config.storage.output_directory).iterdir()
        return run_directory

    def request_pause_during_point():
        if acquisition.read_waveform.call_count == 1:
            keys.append("p")
        return Waveform((-1, 1), (-2, 2), 1000)

    acquisition.read_waveform.side_effect = request_pause_during_point
    checks = []

    def while_paused(seconds):
        assert seconds == 0.2
        assert pulse.fire.call_count == acquisition.read_waveform.call_count == 2
        with (directory() / "summary.csv").open(newline="") as stream:
            saved, = list(csv.DictReader(stream))
        assert saved["repetitions"] == "2"
        assert len(list((directory() / "waveforms").glob("*.csv"))) == 1
        if command == "circular":
            assert controller.move_to.call_count == 2  # Center, then first map point.
        else:
            robot.move_to.assert_called_once()
        checks.append(True)
        if len(checks) == 1:
            return
        if action == "resume":
            keys.append("r")
        elif action == "stop":
            keys.append("S")
        else:
            raise KeyboardInterrupt

    monkeypatch.setattr(cli.time, "sleep", while_paused)
    result = cli.main([command, "--confirm-hardware", "MOVE_AND_FIRE"])
    assert result == (0 if action == "resume" else 130)
    assert len(checks) == 2
    pulse.close.assert_called_once()
    acquisition.close.assert_called_once()
    if command == "circular":
        controller.close.assert_called_once()
    else:
        robot.disconnect.assert_called_once()
        assert robot.stop.call_count == (0 if action == "resume" else 1)
    with (directory() / "summary.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    if action == "resume":
        assert len(rows) > 1
    else:
        assert len(rows) == 1
    output = capsys.readouterr()
    assert "Acquisition paused" in output.out
    if action == "resume":
        assert "Resuming acquisition" in output.out
    else:
        assert "Operation interrupted" in output.err
