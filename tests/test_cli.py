"""CLI only chooses operations/files; experiment parameters come from TOML."""

import contextlib
import io
import json
import unittest
from dataclasses import replace
from unittest.mock import patch

from efield_control.cli import (
    HARDWARE_CONFIRMATION, _require_confirmation, _validate_runtime_settings,
    apply_project_config, build_parser, inclusive_range, main,
)
from efield_control.configuration import load_project_config


class CliTests(unittest.TestCase):
    def test_inclusive_range_supports_both_directions(self):
        self.assertEqual(inclusive_range(-1, 1, 1), (-1, 0, 1))
        self.assertEqual(inclusive_range(1, -1, -1), (1, 0, -1))

    def test_hardware_command_requires_exact_confirmation(self):
        for command in ("center", "planar", "circular", "pulse-test"):
            args = build_parser().parse_args([command])
            with self.assertRaisesRegex(SystemExit, "Operation blocked"):
                _require_confirmation(args)
            args.confirm_hardware = "yes"
            with self.assertRaises(SystemExit):
                _require_confirmation(args)
            args.confirm_hardware = HARDWARE_CONFIRMATION
            _require_confirmation(args)

    def test_all_runtime_parameters_come_from_resolved_files(self):
        config = load_project_config(environ={})
        config = replace(config, centering=replace(config.centering, initial_step_mm=2.5),
                         robot=replace(config.robot, speed_percent=25))
        args = build_parser().parse_args(["center"])
        args.initial_step = 100
        apply_project_config(args, config)
        self.assertEqual(args.initial_step, 2.5)
        self.assertEqual(args.robot_speed_percent, 25)
        self.assertEqual(args.decimation, config.acquisition.decimation)
        self.assertEqual(args.rp_ip, config.hardware.red_pitaya_host)
        self.assertEqual(args.pulse_source, config.pulse.source)

    def test_removed_parameter_arguments_are_rejected(self):
        for command, option, value in (
            ("center", "--initial-step", "2.5"),
            ("center", "--robot-speed-percent", "20"),
            ("center", "--rp-ip", "127.0.0.1"),
            ("center", "--pulse-source", "mtms_api"),
            ("center", "--mtms-target-voltage", "10"),
            ("center", "--output", "data"),
            ("planar", "--x-start", "0"),
            ("circular", "--base-start", "0"),
            ("circular", "--serial-port", "COM3"),
        ):
            with self.subTest(option=option), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    build_parser().parse_args([command, option, value])

    def test_cli_accepts_file_selection_and_confirmation(self):
        args = build_parser().parse_args([
            "--config", "experiment.toml", "--env-file", "hardware.env",
            "--angular-calibration", "stage.toml", "--sensor-calibration", "sensor.toml",
            "planar", "--confirm-hardware", HARDWARE_CONFIRMATION,
        ])
        self.assertEqual(args.config, "experiment.toml")
        self.assertEqual(args.env_file, "hardware.env")
        self.assertEqual(args.angular_calibration, "stage.toml")
        self.assertEqual(args.sensor_calibration, "sensor.toml")
        _require_confirmation(args)

    def test_mtms_import_preflight_uses_configured_pulse_source(self):
        config = load_project_config(environ={})
        config = replace(config, pulse=replace(config.pulse, source="mtms_api"))
        args = build_parser().parse_args(["center"])
        apply_project_config(args, config)
        with patch("efield_control.cli.MtmsSingleChannelClient.validate_environment",
                   side_effect=RuntimeError("mTMS environment unavailable")):
            with self.assertRaisesRegex(RuntimeError, "environment unavailable"):
                _validate_runtime_settings(args)

    def test_show_config_uses_selected_files_without_connecting(self):
        config = load_project_config(environ={})
        output = io.StringIO()
        with patch("efield_control.cli.load_project_config", return_value=config) as loader:
            with patch("socket.socket", side_effect=AssertionError("Unexpected connection")):
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(["--config", "experiment.toml", "show-config"]), 0)
        loader.assert_called_once_with(
            config_path="experiment.toml", env_path=".env",
            angular_calibration_path="config/calibration/angular_stage.toml",
            sensor_calibration_path="config/calibration/sensor_pose.toml",
        )
        self.assertEqual(json.loads(output.getvalue()), json.loads(json.dumps(config.to_dict())))

    def test_main_dispatches_the_selected_toml_parameters(self):
        config = load_project_config(environ={})
        config = replace(config, planar_mapping=replace(config.planar_mapping, x_start_mm=-20))
        with patch("efield_control.cli.load_project_config", return_value=config):
            with patch("efield_control.cli.run_planar", return_value=0) as handler:
                self.assertEqual(main(["planar", "--confirm-hardware", HARDWARE_CONFIRMATION]), 0)
        args = handler.call_args.args[0]
        self.assertEqual(args.x_start, -20)
        self.assertEqual(args.x_stop, config.planar_mapping.x_stop_mm)
        self.assertIs(args.project_config, config)


if __name__ == "__main__":
    unittest.main()
