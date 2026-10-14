"""Adapt six-axis Dobot V3 motion to the same CartesianRobot contract as Elfin."""

from __future__ import annotations

import math
import time

from efield_control.domain import Pose
from ..common import RobotMotionSettings, pose_matches
from .client import Dobot
from .connection import DobotFeedback, RobotStatus


class DobotRobotAdapter:
    """Expose poses and blocking linear moves; the controller must already be enabled."""

    def __init__(
        self,
        host: str,
        *,
        movement_timeout_s: float = 30.0,
        settling_time_s: float = 1.0,
        speed_percent: int = 10,
        socket_timeout_s: float = 3.0,
        feedback_max_age_s: float = 1.0,
        position_tolerance_mm: float = 0.1,
        orientation_tolerance_deg: float = 0.1,
        client: Dobot | None = None,
    ) -> None:
        RobotMotionSettings(
            movement_timeout_s=movement_timeout_s, settling_time_s=settling_time_s,
            speed_percent=speed_percent, socket_timeout_s=socket_timeout_s,
            position_tolerance_mm=position_tolerance_mm,
            orientation_tolerance_deg=orientation_tolerance_deg,
        )
        self._robot = client if client is not None else Dobot(
            host, socket_timeout_s=socket_timeout_s, feedback_max_age_s=feedback_max_age_s
        )
        self.movement_timeout_s = movement_timeout_s
        self.settling_time_s = settling_time_s
        self.speed_percent = speed_percent
        self.position_tolerance_mm = position_tolerance_mm
        self.orientation_tolerance_deg = orientation_tolerance_deg

    @staticmethod
    def _check_state(feedback: DobotFeedback, *, allow_running: bool = False) -> None:
        if feedback.error or feedback.robot_mode == RobotStatus.ERROR:
            raise RuntimeError("The Dobot controller reports an error.")
        allowed = {RobotStatus.IDLE, RobotStatus.RUNNING} if allow_running else {RobotStatus.IDLE}
        if not feedback.enabled or feedback.robot_mode not in allowed:
            raise RuntimeError("Dobot must be enabled and ready in TCP/IP mode.")
        if not allow_running and feedback.running:
            raise RuntimeError("Dobot is already executing a movement.")

    def connect(self) -> None:
        """Connect and verify readiness without enabling the robot or clearing alarms."""
        try:
            self._robot.connect()
            self._check_state(self._robot.feedback())
        except BaseException:
            self._robot.disconnect()
            raise

    def disconnect(self) -> None:
        self._robot.disconnect()

    def current_pose(self) -> Pose:
        """Read the latest TCP pose in mm and degrees, in the controller's active frame."""
        feedback = self._robot.feedback()
        self._check_state(feedback, allow_running=True)
        return Pose(*feedback.pose)

    def _at_target(self, actual: tuple[float, ...], target: list[float]) -> bool:
        return pose_matches(
            actual, target, self.position_tolerance_mm, self.orientation_tolerance_deg
        )

    def move_to(self, pose: Pose) -> None:
        """Wait for an idle controller at the target before allowing sensor acquisition."""
        target = pose.as_list()
        if not all(math.isfinite(value) for value in target):
            raise ValueError("Dobot target coordinates must be finite.")
        feedback = self._robot.feedback()
        self._check_state(feedback)
        if self._at_target(feedback.pose, target):
            return
        try:
            deadline = time.monotonic() + self.movement_timeout_s
            self._robot.connection.move_linear(target, self.speed_percent)
            # A successful reply means accepted, not completed: require new feedback.
            after = time.monotonic()
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Timed out waiting for Dobot motion completion.")
                feedback = self._robot.feedback(after=after, timeout_s=remaining)
                self._check_state(feedback, allow_running=True)
                if (
                    feedback.robot_mode == RobotStatus.IDLE
                    and not feedback.running
                    and self._at_target(feedback.pose, target)
                ):
                    break
                after = time.monotonic()
            time.sleep(self.settling_time_s)
            # Recheck after settling so a lost connection/alarm cannot silently allow firing.
            feedback = self._robot.feedback(after=after)
            self._check_state(feedback)
            if not self._at_target(feedback.pose, target):
                raise RuntimeError("Dobot moved away from the requested target while settling.")
        except BaseException:
            try:
                self.stop()
            except Exception:
                pass
            raise

    def stop(self) -> None:
        """Send the V3 ResetRobot stop command through the dashboard channel."""
        self._robot.connection.stop_robot()
