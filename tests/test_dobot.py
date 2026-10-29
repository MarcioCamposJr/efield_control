"""Hardware-free regression tests: python -m unittest discover -s tests -p test_dobot.py -v."""

import math
import queue
import socket
import struct
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import call, patch

from efield_control.cli import _robot, apply_project_config, build_parser, main
from efield_control.configuration import HardwareConfig, RobotConfig, load_project_config
from efield_control.domain import Pose
from efield_control.drivers.robots.dobot import (
    Dobot, DobotCommandError, DobotConnection, DobotFeedback, DobotRobotAdapter, DobotStateError,
)
from efield_control.drivers.robots.elfin import ElfinRobotAdapter


def frame(pose=(0, 0, 0, 0, 0, 0), mode=5, running=False, enabled=True, error=False):
    data = bytearray(1440)
    struct.pack_into("<Q", data, 0, 1440)
    struct.pack_into("<Q", data, 24, mode)
    struct.pack_into("<Q", data, 48, 0x123456789ABCDEF)
    struct.pack_into("<6d", data, 624, *pose)
    data[1026], data[1028], data[1029] = enabled, running, error
    return bytes(data)


def state(pose=(0, 0, 0, 0, 0, 0), **kwargs):
    return DobotFeedback.from_bytes(frame(pose, **kwargs))


class FakeSocket:
    def __init__(self, chunks=()):
        self.chunks, self.sent = list(chunks), []
        self.closed = self.shutdown_called = False

    def settimeout(self, value):
        self.timeout = value

    def sendall(self, command):
        self.sent.append(command)

    def recv(self, count):
        if not self.chunks:
            return b""
        chunk = self.chunks.pop(0)
        if isinstance(chunk, Exception):
            raise chunk
        if len(chunk) > count:
            self.chunks.insert(0, chunk[count:])
        return chunk[:count]

    def shutdown(self, how):
        self.shutdown_called = True

    def close(self):
        self.closed = True


class ScriptedClient:
    def __init__(self, states):
        self.states, self.moves = list(states), []
        self.stops, self.connected = 0, False
        self.enable_requests = 0
        self.connection = self

    def connect(self):
        self.connected = True

    def disconnect(self):
        self.connected = False

    def feedback(self, **kwargs):
        if not self.states:
            raise TimeoutError("No fresh feedback")
        result = self.states.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    def move_linear(self, target, speed):
        self.moves.append((target, speed))

    def stop_robot(self):
        self.stops += 1

    def enable_robot(self):
        self.enable_requests += 1


class QueueConnection:
    """Closing wakes a blocked feedback reader, just like socket shutdown."""

    def __init__(self):
        self.frames, self.closed = queue.Queue(), False

    def connect(self):
        self.closed = False

    def get_feedback(self):
        item = self.frames.get(timeout=1)
        if isinstance(item, Exception):
            raise item
        return item

    def close(self):
        self.closed = True
        self.frames.put(ConnectionError("closed"))


class DobotProtocolTests(unittest.TestCase):
    def connection(self, dashboard=(), movement=(), feedback=()):
        sockets = [FakeSocket(dashboard), FakeSocket(movement), FakeSocket(feedback)]
        factory = iter(sockets)
        connection = DobotConnection("unused", socket_factory=lambda *a, **kw: next(factory))
        connection.connect()
        self.addCleanup(connection.close)
        return connection, sockets

    def test_fragmented_feedback_decodes_position_and_motion(self):
        data = frame((1, 2, 3, 4, 5, 6), mode=7, running=True)
        connection, _ = self.connection(feedback=[data[:80], data[80:999], data[999:]])
        feedback = connection.get_feedback()
        self.assertEqual(feedback.pose, (1, 2, 3, 4, 5, 6))
        self.assertTrue(feedback.running)
        self.assertEqual(feedback.robot_mode, 7)

    def test_invalid_length_marker_and_nonfinite_pose(self):
        invalid = bytearray(frame())
        invalid[48] = 0
        for data in (b"short", bytes(invalid), frame((math.nan, 0, 0, 0, 0, 0))):
            with self.subTest(size=len(data)), self.assertRaises(RuntimeError):
                DobotFeedback.from_bytes(data)

    def test_feedback_eof_and_timeout_raise(self):
        for chunks in ([frame()[:30]], [socket.timeout("timeout")]):
            connection, _ = self.connection(feedback=chunks)
            with self.assertRaises((ConnectionError, TimeoutError)):
                connection.get_feedback()

    def test_command_reads_fragmented_reply_and_sets_global_speed_before_moving(self):
        command = "MovL(1,2,3,4,5,6)"
        connection, sockets = self.connection(
            dashboard=[b"0,{},SpeedFactor(10);"],
            movement=[b"0,{},", command.encode(), b";"],
        )
        with patch.object(connection, "_command", wraps=connection._command) as send:
            connection.move_linear([1, 2, 3, 4, 5, 6], 10)
        self.assertEqual(send.call_args_list, [
            call("dashboard", "SpeedFactor(10)"), call("movement", command),
        ])
        self.assertEqual(sockets[1].sent, [command.encode()])
        self.assertEqual(sockets[0].sent, [b"SpeedFactor(10)"])

    def test_speed_failure_prevents_movement(self):
        for chunks in ([b"-1,{},SpeedFactor(10);"], [b"bad;"], [], [socket.timeout("timeout")]):
            with self.subTest(chunks=chunks):
                connection, sockets = self.connection(dashboard=chunks)
                with self.assertRaises((DobotCommandError, ConnectionError, TimeoutError)):
                    connection.move_linear([1, 2, 3, 4, 5, 6], 10)
                self.assertEqual(sockets[1].sent, [])

    def test_error_malformed_and_mismatched_replies_raise(self):
        for reply in (b"-1,{},ResetRobot();", b"bad;", b"0,{},Other();"):
            connection, _ = self.connection(dashboard=[reply])
            with self.assertRaises(DobotCommandError):
                connection.stop_robot()

    def test_command_eof_and_timeout_raise(self):
        for chunks in ([], [socket.timeout("timeout")]):
            connection, _ = self.connection(dashboard=chunks)
            with self.assertRaises((ConnectionError, TimeoutError)):
                connection.stop_robot()

    def test_alarm_query_accepts_nested_payload_without_state_changes(self):
        connection, sockets = self.connection(dashboard=[b"0,{{123},{}},", b"GetErrorID();"])
        self.assertEqual(connection.get_error_id(), "{{123},{}}")
        self.assertEqual(sockets[0].sent, [b"GetErrorID()"])
        self.assertEqual(sockets[1].sent, [])

    def test_enable_uses_only_dashboard_and_requires_success(self):
        connection, sockets = self.connection(dashboard=[b"0,{},EnableRobot();"])
        connection.enable_robot()
        self.assertEqual(sockets[0].sent, [b"EnableRobot()"])
        self.assertEqual(sockets[1].sent, [])
        connection, _ = self.connection(dashboard=[b"-1,{},EnableRobot();"])
        with self.assertRaises(DobotCommandError):
            connection.enable_robot()

    def test_partial_connect_failure_closes_previous_sockets(self):
        opened = FakeSocket()
        attempts = iter([opened, ConnectionError("failed")])
        def factory(*args, **kwargs):
            result = next(attempts)
            if isinstance(result, Exception):
                raise result
            return result
        connection = DobotConnection("unused", socket_factory=factory)
        with self.assertRaises(ConnectionError):
            connection.connect()
        self.assertTrue(opened.closed and opened.shutdown_called)
        self.assertEqual(connection._sockets, {})

    def test_close_releases_all_sockets_and_is_idempotent(self):
        connection, sockets = self.connection()
        connection.close()
        connection.close()
        self.assertTrue(all(s.closed and s.shutdown_called for s in sockets))


class DobotAdapterTests(unittest.TestCase):
    def adapter(self, states):
        client = ScriptedClient(states)
        return DobotRobotAdapter("unused", client=client, settling_time_s=0), client

    def test_waits_for_idle_at_target_and_rechecks_settling(self):
        target = (1, 2, 3, 4, 5, 6)
        adapter, client = self.adapter([
            state(), state(), state(target, mode=7, running=True),
            state(), state(target), state(target),
        ])
        adapter.connect()
        adapter.move_to(Pose(*target))
        self.assertEqual(client.moves, [(list(target), 10)])
        self.assertEqual(client.stops, 0)

    def test_disabled_or_faulted_connect_closes_without_enabling_or_clearing(self):
        for feedback in (state(mode=4, enabled=False), state(mode=9, error=True)):
            adapter, client = self.adapter([feedback])
            with self.assertRaises(RuntimeError):
                adapter.connect()
            self.assertFalse(client.connected)
            self.assertEqual(client.moves, [])
            self.assertEqual(client.stops, 0)

    def test_diagnostic_connect_allows_inspection_but_still_blocks_motion(self):
        fault = state(mode=9, error=True)
        adapter, client = self.adapter([fault, fault])
        adapter.connect(require_ready=False)
        self.assertTrue(client.connected)
        with self.assertRaisesRegex(RuntimeError, "robot_mode=9, error_status=1"):
            adapter.current_pose()
        with self.assertRaisesRegex(RuntimeError, "error_status=1"):
            adapter.move_to(Pose(10, 0, 0))
        self.assertEqual(client.moves, [])
        adapter.disconnect()

    def test_enable_waits_for_new_enabled_idle_feedback_without_moving(self):
        disabled = state(mode=4, enabled=False)
        adapter, client = self.adapter([disabled, disabled, state()])
        with patch.object(client, "feedback", wraps=client.feedback) as feedback:
            self.assertTrue(adapter.enable())
        self.assertEqual(client.enable_requests, 1)
        self.assertEqual(client.moves, [])
        self.assertEqual(client.stops, 0)
        self.assertGreater(feedback.call_args_list[1].kwargs["after"], 0)

    def test_enable_is_noop_when_already_ready(self):
        adapter, client = self.adapter([state()])
        self.assertFalse(adapter.enable())
        self.assertEqual(client.enable_requests, 0)

    def test_enable_rejects_fault_poweroff_drag_and_running_states(self):
        for feedback in (
            state(mode=9, error=True), state(mode=4, enabled=False, error=True),
            state(mode=3, enabled=False), state(mode=6), state(mode=7, running=True),
        ):
            adapter, client = self.adapter([feedback])
            with self.assertRaises(DobotStateError):
                adapter.enable()
            self.assertEqual(client.enable_requests, 0)
            self.assertEqual(client.moves, [])

    def test_enable_failure_and_feedback_loss_propagate_without_reset(self):
        disabled = state(mode=4, enabled=False)
        for failure in (TimeoutError("no feedback"), state(mode=9, error=True)):
            adapter, client = self.adapter([disabled, failure])
            with self.assertRaises((TimeoutError, DobotStateError)):
                adapter.enable()
            self.assertEqual(client.enable_requests, 1)
            self.assertEqual(client.stops, 0)

    def test_enable_rejection_does_not_wait_or_retry(self):
        adapter, client = self.adapter([state(mode=4, enabled=False)])
        with patch.object(client, "enable_robot", side_effect=DobotCommandError("rejected")) as enable:
            with self.assertRaises(DobotCommandError):
                adapter.enable()
        enable.assert_called_once()
        self.assertEqual(client.stops, 0)

    def test_enable_deadline_bounds_wait_even_with_live_disabled_feedback(self):
        adapter, client = self.adapter([])
        adapter.movement_timeout_s = 0.005
        client.feedback = lambda **kwargs: state(mode=4, enabled=False)
        with self.assertRaisesRegex(TimeoutError, "enable confirmation"):
            adapter.enable()
        self.assertEqual(client.enable_requests, 1)
        self.assertEqual(client.moves, [])

    def test_fault_timeout_and_interrupt_attempt_stop(self):
        for failure in (state(mode=9, error=True), TimeoutError("lost"), KeyboardInterrupt()):
            adapter, client = self.adapter([state(), failure])
            with self.assertRaises((RuntimeError, TimeoutError, KeyboardInterrupt)):
                adapter.move_to(Pose(10, 0, 0))
            self.assertEqual(client.stops, 1)

    def test_idle_at_wrong_position_or_running_at_target_does_not_complete(self):
        for feedback in (state(), state((10, 0, 0, 0, 0, 0), mode=7, running=True)):
            adapter, client = self.adapter([state(), feedback])
            with self.assertRaises(TimeoutError):
                adapter.move_to(Pose(10, 0, 0))
            self.assertEqual(client.stops, 1)

    def test_departure_after_settling_blocks_completion(self):
        adapter, client = self.adapter([state(), state((10, 0, 0, 0, 0, 0)), state()])
        with self.assertRaisesRegex(RuntimeError, "moved away"):
            adapter.move_to(Pose(10, 0, 0))
        self.assertEqual(client.stops, 1)

    def test_pose_and_noop_use_current_position(self):
        adapter, client = self.adapter([state(), state()])
        self.assertEqual(adapter.current_pose(), Pose(0, 0, 0))
        adapter.move_to(Pose(0, 0, 0))
        self.assertEqual(client.moves, [])

    def test_tolerances_and_wrapped_angles(self):
        adapter, _ = self.adapter([])
        self.assertTrue(adapter._at_target((0, 0, 0, 359.99, 0, 0), [0] * 6))
        self.assertFalse(adapter._at_target((1, 0, 0, 0, 0, 0), [0] * 6))
        self.assertFalse(adapter._at_target((0, 0, 0, 1, 0, 0), [0] * 6))

    def test_nonfinite_target_is_rejected_before_feedback_or_motion(self):
        adapter, client = self.adapter([])
        with self.assertRaises(ValueError):
            adapter.move_to(Pose(math.nan, 0, 0))
        self.assertEqual(client.moves, [])

    def test_motion_deadline_expires_even_with_live_idle_feedback(self):
        adapter, client = self.adapter([])
        adapter.movement_timeout_s = 0.005
        client.feedback = lambda **kwargs: state()
        with self.assertRaisesRegex(TimeoutError, "motion completion"):
            adapter.move_to(Pose(10, 0, 0))
        self.assertEqual(client.stops, 1)

    def test_rejected_movement_attempts_stop_and_preserves_error(self):
        adapter, client = self.adapter([state()])
        with patch.object(client, "move_linear", side_effect=DobotCommandError("rejected")):
            with self.assertRaisesRegex(DobotCommandError, "rejected"):
                adapter.move_to(Pose(10, 0, 0))
        self.assertEqual(client.stops, 1)

    def test_planar_mapping_measures_only_after_target_and_settling_checks(self):
        from efield_control.mapping import PlanarMapping, PlanarPoint
        from unittest.mock import Mock
        target = (10, 0, 0, 0, 0, 0)
        adapter, client = self.adapter([
            state(), state(target, mode=7, running=True), state(target), state(target),
        ])
        service = Mock()
        def measure():
            self.assertEqual(client.states, [])
            return "measurement"
        service.measure.side_effect = measure
        result = list(PlanarMapping(adapter, service).run(
            Pose(0, 0, 0), [PlanarPoint(0, 0, 10, 0)]
        ))
        self.assertEqual(result[0][1:], (Pose(*target), "measurement"))
        service.measure.assert_called_once()


class DobotClientTests(unittest.TestCase):
    def client(self, max_age=0.05):
        connection = QueueConnection()
        connection.frames.put(state())
        client = Dobot("unused", connection=connection, feedback_max_age_s=max_age)
        self.addCleanup(client.disconnect)
        client.connect()
        return client, connection

    def test_new_feedback_and_clean_disconnect(self):
        client, connection = self.client()
        after = time.monotonic()
        connection.frames.put(state((10, 0, 0, 0, 0, 0)))
        self.assertEqual(client.feedback(after=after).pose[0], 10)
        client.disconnect()
        self.assertTrue(connection.closed)
        self.assertIsNone(client._thread)
        with self.assertRaises(ConnectionError):
            client.feedback()

    def test_stale_feedback_cannot_return_cached_position(self):
        client, _ = self.client(0.01)
        time.sleep(0.02)
        with self.assertRaises(TimeoutError):
            client.feedback(timeout_s=0.01)

    def test_reader_failure_propagates(self):
        client, connection = self.client()
        after = time.monotonic()
        connection.frames.put(ConnectionError("dropped"))
        with self.assertRaisesRegex(ConnectionError, "reader failed"):
            client.feedback(after=after)

    def test_connect_without_feedback_times_out_and_closes_reader(self):
        connection = QueueConnection()
        client = Dobot("unused", connection=connection, feedback_max_age_s=0.01)
        with self.assertRaises(TimeoutError):
            client.connect()
        self.assertTrue(connection.closed)
        self.assertIsNone(client._thread)


class DobotSelectionTests(unittest.TestCase):
    def test_cli_selects_both_robots_without_connecting(self):
        config = load_project_config(environ={})
        for command in ("center", "planar"):
            for kind, expected in (("elfin", ElfinRobotAdapter), ("dobot", DobotRobotAdapter)):
                selected = replace(config, hardware=replace(config.hardware, robot_type=kind))
                selected = replace(selected, robot=replace(selected.robot, speed_percent=20))
                args = build_parser().parse_args([command])
                apply_project_config(args, selected)
                args.project_config = selected
                with patch("socket.socket", side_effect=AssertionError("Unexpected connection")):
                    robot = _robot(args)
                self.assertIsInstance(robot, expected)
                self.assertEqual(robot.speed_percent, 20)

    def test_environment_selection_and_toml_motion_parameters(self):
        config = load_project_config(environ={"EFIELD_ROBOT_TYPE": "dobot"})
        args = build_parser().parse_args(["center"])
        apply_project_config(args, config)
        args.project_config = config
        self.assertIsInstance(_robot(args), DobotRobotAdapter)
        config = replace(config, robot=replace(config.robot, speed_percent=25))
        args = build_parser().parse_args(["center"])
        apply_project_config(args, config)
        self.assertEqual(args.robot_speed_percent, 25)

    def test_invalid_settings(self):
        for kwargs in ({"speed_percent": 0}, {"speed_percent": 1.5},
                       {"socket_timeout_s": math.nan}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                RobotConfig(**kwargs)
        with self.assertRaises(ValueError):
            HardwareConfig(robot_type="unknown")

    def test_actual_toml_loads_dobot_settings(self):
        from efield_control.configuration import _read_toml, tomllib
        content = Path("config/default.toml").read_text(encoding="utf-8")
        experiment = tomllib.loads(content)
        def read_config(path):
            return experiment if str(path) == "experiment.toml" else _read_toml(path)
        with patch("efield_control.configuration._read_toml", side_effect=read_config):
            config = load_project_config(config_path="experiment.toml", environ={"EFIELD_ROBOT_TYPE": "dobot"})
        self.assertEqual(config.hardware.robot_type, "dobot")
        self.assertEqual(config.robot.speed_percent, 10)
        self.assertEqual(config.robot.position_tolerance_mm, 0.1)
        self.assertNotIn("type", experiment["robot"])

    def test_dobot_hardware_still_requires_confirmation_before_connecting(self):
        with patch("socket.socket", side_effect=AssertionError("Unexpected connection")):
            with self.assertRaisesRegex(SystemExit, "Operation blocked"):
                with patch.dict("os.environ", {"EFIELD_ROBOT_TYPE": "dobot"}):
                    main(["center"])

    def test_robot_identity_cannot_be_overridden_on_cli_or_toml(self):
        import contextlib
        import io
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            build_parser().parse_args(["center", "--robot-type", "dobot"])
        from efield_control.configuration import _read_toml
        def read_config(path):
            return {"robot": {"type": "dobot"}} if str(path) == "invalid.toml" else _read_toml(path)
        with patch("efield_control.configuration._read_toml", side_effect=read_config):
            with self.assertRaisesRegex(ValueError, "Unknown configuration"):
                load_project_config(config_path="invalid.toml", environ={})


if __name__ == "__main__":
    unittest.main()
