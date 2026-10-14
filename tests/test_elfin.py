"""Regression tests for shared motion settings in the Elfin driver."""

import math
import unittest
from unittest.mock import Mock, patch

from efield_control.domain import Pose
from efield_control.drivers.robots.elfin import ElfinRobotAdapter, ElfinConnection, MotionState


class ElfinMotionTests(unittest.TestCase):
    def adapter(self, states, poses, **kwargs):
        client = Mock()
        client.connection.get_motion_state.side_effect = states
        client.get_pose.side_effect = [(True, pose) for pose in poses]
        client.move_linear.return_value = True
        adapter = ElfinRobotAdapter(
            "unused", client=client, settling_time_s=0, **kwargs
        )
        return adapter, client

    def test_shared_speed_ratio_and_target_check(self):
        target = [10, 0, 0, 0, 0, 0]
        adapter, client = self.adapter(
            [MotionState.FREE_TO_MOVE] * 2, [target, target], speed_percent=25
        )
        adapter.move_to(Pose(*target))
        client.move_linear.assert_called_once_with(target, 0.25)
        client.stop_robot.assert_not_called()

    def test_idle_before_target_is_not_completion(self):
        target = [10, 0, 0, 0, 0, 0]
        adapter, client = self.adapter(
            [MotionState.FREE_TO_MOVE] * 3, [[0] * 6, target, target]
        )
        with patch("efield_control.drivers.robots.elfin.adapter.time.sleep"):
            adapter.move_to(Pose(*target))
        self.assertEqual(client.get_pose.call_count, 3)

    def test_waiting_and_moving_are_not_completion(self):
        target = [10, 0, 0, 0, 0, 0]
        adapter, client = self.adapter(
            [MotionState.WAITING_FOR_EXECUTION, MotionState.IN_MOTION,
             MotionState.FREE_TO_MOVE, MotionState.FREE_TO_MOVE], [target, target]
        )
        with patch("efield_control.drivers.robots.elfin.adapter.time.sleep"):
            adapter.move_to(Pose(*target))
        self.assertEqual(client.connection.get_motion_state.call_count, 4)

    def test_error_or_unknown_state_blocks_measurement_and_attempts_stop(self):
        for state in (MotionState.ERROR, MotionState.UNKNOWN):
            adapter, client = self.adapter([state], [])
            with self.assertRaises(RuntimeError):
                adapter.move_to(Pose(10, 0, 0))
            client.stop_robot.assert_called_once()

    def test_rejected_move_attempts_stop(self):
        adapter, client = self.adapter([], [])
        client.move_linear.return_value = False
        with self.assertRaisesRegex(RuntimeError, "rejected"):
            adapter.move_to(Pose(10, 0, 0))
        client.stop_robot.assert_called_once()

    def test_timeout_attempts_stop(self):
        adapter, client = self.adapter([MotionState.IN_MOTION], [])
        with patch("efield_control.drivers.robots.elfin.adapter.time.monotonic", side_effect=[0, 31]):
            with self.assertRaises(TimeoutError):
                adapter.move_to(Pose(10, 0, 0))
        client.stop_robot.assert_called_once()

    def test_target_tolerances_apply_after_settling(self):
        adapter, client = self.adapter(
            [MotionState.FREE_TO_MOVE] * 2, [[10, 0, 0, 0, 0, 0], [11, 0, 0, 0, 0, 0]]
        )
        with self.assertRaisesRegex(RuntimeError, "after settling"):
            adapter.move_to(Pose(10, 0, 0))
        client.stop_robot.assert_called_once()

    def test_invalid_speed_or_target_is_rejected(self):
        with self.assertRaises(ValueError):
            ElfinRobotAdapter("unused", speed_percent=101)
        adapter, client = self.adapter([], [])
        with self.assertRaises(ValueError):
            adapter.move_to(Pose(math.nan, 0, 0))
        client.move_linear.assert_not_called()

    def test_tcp_timeout_is_shared_and_failed_connect_closes_socket(self):
        client = Mock()
        with patch("efield_control.drivers.robots.elfin.connection.socket", return_value=client):
            connection = ElfinConnection("unused", False, timeout_s=2.5)
            self.assertTrue(connection.connect())
        client.settimeout.assert_called_once_with(2.5)
        connection.disconnect()
        client = Mock()
        client.connect.side_effect = OSError("unreachable")
        with patch("efield_control.drivers.robots.elfin.connection.socket", return_value=client):
            connection = ElfinConnection("unused", False, timeout_s=2.5)
            self.assertFalse(connection.connect())
        client.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
