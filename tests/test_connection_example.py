"""Hardware-free tests for the device connection example."""

import contextlib
import io
import socket
import unittest
from dataclasses import replace
from unittest.mock import Mock, patch

from efield_control.configuration import load_project_config
from efield_control.domain import Pose
from efield_control.drivers.stimulators.mtms import MtmsSingleChannelClient
from examples import check_connections as example


class FakeScpiSocket:
    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.sent = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def sendall(self, data):
        self.sent.append(data)

    def settimeout(self, timeout):
        self.timeout = timeout

    def recv(self, count):
        chunk = self.chunks.pop(0) if self.chunks else b""
        if isinstance(chunk, Exception):
            raise chunk
        return chunk


class ConnectionExampleTests(unittest.TestCase):
    def setUp(self):
        config = load_project_config(environ={})
        self.config = replace(config, hardware=replace(
            config.hardware, robot_host="unused", stage_serial_port="unused",
            red_pitaya_host="unused",
        ))

    def test_all_devices_are_checked_independently_and_results_reported(self):
        results_seen = []
        with patch.object(example, "check_robot", return_value="pose") as robot:
            with patch.object(example, "check_microcontroller", side_effect=TimeoutError("no PONG")) as serial:
                with patch.object(example, "check_red_pitaya", return_value="identity") as red:
                    with patch.object(example, "check_mtms", side_effect=ImportError("no API")) as mtms:
                        results = example.check_connections(self.config, on_result=results_seen.append)
        self.assertEqual([r.device for r in results], ["Robot", "Microcontroller", "Red Pitaya", "mTMS"])
        self.assertEqual([r.success for r in results], [True, False, True, False])
        self.assertEqual(results_seen, results)
        self.assertIn("TimeoutError", results[1].detail)
        for check in (robot, serial, red, mtms):
            check.assert_called_once_with(self.config)

    def test_selected_robot_reads_pose_and_closes_without_moving(self):
        for kind, factory_name in (("elfin", "ElfinRobotAdapter"), ("dobot", "DobotRobotAdapter")):
            config = replace(self.config, hardware=replace(self.config.hardware, robot_type=kind))
            robot = Mock()
            robot.current_pose.return_value = Pose(1, 2, 3)
            with patch.object(example, factory_name, return_value=robot):
                self.assertIn(kind, example.check_robot(config))
            robot.connect.assert_called_once()
            robot.current_pose.assert_called_once()
            robot.disconnect.assert_called_once()
            robot.move_to.assert_not_called()
            robot.stop.assert_not_called()

    def test_robot_failure_still_disconnects(self):
        robot = Mock()
        robot.connect.side_effect = ConnectionError("offline")
        config = replace(self.config, hardware=replace(self.config.hardware, robot_type="elfin"))
        with patch.object(example, "ElfinRobotAdapter", return_value=robot):
            with self.assertRaises(ConnectionError):
                example.check_robot(config)
        robot.disconnect.assert_called_once()

    def test_serial_only_sends_ping_and_closes(self):
        controller = Mock()
        with patch.object(example, "SerialMotorController", return_value=controller):
            self.assertIn("PONG", example.check_microcontroller(self.config))
        controller.ping.assert_called_once()
        controller.close.assert_called_once()
        controller.center.assert_not_called()
        controller.move_to.assert_not_called()
        controller.fire.assert_not_called()

    def test_serial_retries_once_if_board_boot_discards_first_ping(self):
        controller = Mock()
        controller.ping.side_effect = [TimeoutError("booting"), None]
        with patch.object(example, "SerialMotorController", return_value=controller):
            example.check_microcontroller(self.config)
        self.assertEqual(controller.ping.call_count, 2)
        controller.close.assert_called_once()

    def test_serial_failure_still_closes(self):
        controller = Mock()
        controller.ping.side_effect = TimeoutError("offline")
        with patch.object(example, "SerialMotorController", return_value=controller):
            with self.assertRaises(TimeoutError):
                example.check_microcontroller(self.config)
        controller.close.assert_called_once()

    def test_red_pitaya_only_requests_readonly_identification(self):
        client = FakeScpiSocket([b"RedPitaya,", b"STEMlab\r", b"\n"])
        with patch.object(example.socket, "create_connection", return_value=client):
            self.assertIn("RedPitaya,STEMlab", example.check_red_pitaya(self.config))
        self.assertEqual(client.sent, [b"*IDN?\r\n"])
        self.assertTrue(client.closed)

    def test_red_pitaya_eof_timeout_and_invalid_response_close_socket(self):
        for chunks in ([], [socket.timeout("offline")], [b"Unknown command\r\n"], [b"\r\n"]):
            client = FakeScpiSocket(chunks)
            with patch.object(example.socket, "create_connection", return_value=client):
                with self.assertRaises((ConnectionError, TimeoutError, RuntimeError)):
                    example.check_red_pitaya(self.config)
            self.assertTrue(client.closed)

    def test_mtms_opens_and_closes_session_without_charge_or_pulse(self):
        api = Mock()
        def factory(settings):
            return MtmsSingleChannelClient(settings, api_factory=lambda: api, execution_condition=object())
        with patch.object(example, "MtmsSingleChannelClient", side_effect=factory):
            self.assertIn("session", example.check_mtms(self.config))
        self.assertEqual([call[0] for call in api.mock_calls], [
            "start_device", "start_session", "stop_session", "stop_device", "end",
        ])
        api.send_charge.assert_not_called()
        api.send_pulse.assert_not_called()
        api.send_trigger_out.assert_not_called()
        api.send_discharge.assert_not_called()

    def test_mtms_failed_session_start_still_shuts_down_device(self):
        api = Mock()
        api.start_session.side_effect = RuntimeError("session unavailable")
        def factory(settings):
            return MtmsSingleChannelClient(settings, api_factory=lambda: api, execution_condition=object())
        with patch.object(example, "MtmsSingleChannelClient", side_effect=factory):
            with self.assertRaisesRegex(RuntimeError, "session unavailable"):
                example.check_mtms(self.config)
        api.stop_device.assert_called_once()
        api.end.assert_called_once()
        api.send_charge.assert_not_called()

    def test_missing_endpoints_do_not_attempt_connections(self):
        config = replace(self.config, hardware=replace(
            self.config.hardware, robot_host="", stage_serial_port="", red_pitaya_host="",
        ))
        with patch.object(example, "ElfinRobotAdapter", side_effect=AssertionError("Unexpected connection")):
            with patch.object(example, "SerialMotorController", side_effect=AssertionError("Unexpected connection")):
                with patch.object(example.socket, "create_connection", side_effect=AssertionError("Unexpected connection")):
                    for check in (example.check_robot, example.check_microcontroller, example.check_red_pitaya):
                        with self.assertRaisesRegex(ValueError, "not configured"):
                            check(config)

    def test_cleanup_failure_is_reported(self):
        with self.assertRaisesRegex(RuntimeError, "cleanup failed"):
            example._with_cleanup(lambda: "connected", Mock(side_effect=OSError("cannot close")))

    def test_main_prints_results_and_returns_failure_if_one_device_failed(self):
        results = [example.ConnectionResult("Robot", True, "pose"),
                   example.ConnectionResult("mTMS", False, "API unavailable")]
        def check(config, on_result):
            for result in results:
                on_result(result)
            return results
        output = io.StringIO()
        with patch.object(example, "load_project_config", return_value=self.config):
            with patch.object(example, "check_connections", side_effect=check):
                with contextlib.redirect_stdout(output):
                    self.assertEqual(example.main(), 1)
        self.assertIn("[OK  ] Robot", output.getvalue())
        self.assertIn("[FAIL] mTMS", output.getvalue())
        self.assertIn("Devices that passed: Robot", output.getvalue())

    def test_main_returns_success_when_all_checks_pass(self):
        results = [example.ConnectionResult("Robot", True, "pose")]
        with patch.object(example, "load_project_config", return_value=self.config):
            with patch.object(example, "check_connections", return_value=results):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(example.main(), 0)

    def test_configuration_failure_does_not_attempt_device_checks(self):
        with patch.object(example, "load_project_config", side_effect=ValueError("invalid TOML")):
            with patch.object(example, "check_connections") as check:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(example.main(), 2)
        check.assert_not_called()


if __name__ == "__main__":
    unittest.main()
