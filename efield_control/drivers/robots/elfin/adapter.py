"""Adapt Elfin communication to the robot contract used by the experiments."""

from __future__ import annotations

import time
import math

from efield_control.domain import Pose
from .client import Elfin
from .connection import MotionState
from ..common import RobotMotionSettings, pose_matches


class ElfinRobotAdapter:
    """Expose poses in millimeters/degrees and movements that wait for completion."""
    def __init__(
        self,
        host: str,
        *,
        use_new_api: bool = False,
        movement_timeout_s: float = 30.0,
        settling_time_s: float = 1.0,
        speed_percent: int = 10,
        socket_timeout_s: float = 3.0,
        position_tolerance_mm: float = 0.1,
        orientation_tolerance_deg: float = 0.1,
        client: Elfin | None = None,
    ) -> None:
        RobotMotionSettings(
            movement_timeout_s=movement_timeout_s, settling_time_s=settling_time_s,
            speed_percent=speed_percent, socket_timeout_s=socket_timeout_s,
            position_tolerance_mm=position_tolerance_mm,
            orientation_tolerance_deg=orientation_tolerance_deg,
        )
        self._robot = client if client is not None else Elfin(
            ip=host, use_new_api=use_new_api, socket_timeout_s=socket_timeout_s
        )
        self.movement_timeout_s = movement_timeout_s
        self.settling_time_s = settling_time_s
        self.speed_percent = speed_percent
        self.position_tolerance_mm = position_tolerance_mm
        self.orientation_tolerance_deg = orientation_tolerance_deg

    def connect(self) -> None:
        """Open TCP communication with the Elfin controller."""
        if not self._robot.connect():
            raise ConnectionError("Could not connect to the Elfin robot.")

    def disconnect(self) -> None:
        self._robot.disconnect()

    def current_pose(self) -> Pose:
        """Read the tool center point pose: X, Y, Z in mm and RX, RY, RZ in degrees."""
        success, values = self._robot.get_pose()
        if not success or values is None or len(values) < 6:
            raise RuntimeError("The Elfin robot returned an invalid pose.")
        pose = Pose(*map(float, values[:6]))
        if not all(math.isfinite(value) for value in pose.as_list()):
            raise RuntimeError("The Elfin robot returned a non-finite pose.")
        return pose

    def _at_target(self, pose: Pose, target: list[float]) -> bool:
        return pose_matches(
            pose.as_list(), target,
            self.position_tolerance_mm, self.orientation_tolerance_deg,
        )

    def move_to(self, pose: Pose) -> None:
        """Request an Elfin linear movement and wait for completion and settling."""
        target = pose.as_list()
        if not all(math.isfinite(value) for value in target):
            raise ValueError("Elfin target coordinates must be finite.")
        try:
            deadline = time.monotonic() + self.movement_timeout_s
            # The Elfin client applies the shared percentage as a 0-1 speed ratio.
            if not self._robot.move_linear(target, self.speed_percent / 100):
                raise RuntimeError("The Elfin robot rejected the motion command.")
            while True:
                state = self._robot.connection.get_motion_state()
                if state in {MotionState.ERROR, MotionState.UNKNOWN}:
                    raise RuntimeError("The Elfin robot reports an invalid motion state.")
                if time.monotonic() > deadline:
                    raise TimeoutError("Timed out while waiting for Elfin motion.")
                # Idle alone does not prove a queued movement reached its target.
                if state == MotionState.FREE_TO_MOVE and self._at_target(self.current_pose(), target):
                    break
                time.sleep(0.05)
            time.sleep(self.settling_time_s)
            if (self._robot.connection.get_motion_state() != MotionState.FREE_TO_MOVE
                    or not self._at_target(self.current_pose(), target)):
                raise RuntimeError("Elfin is not idle at the target after settling.")
        except BaseException:
            try:
                self.stop()
            except Exception:
                pass
            raise

    def stop(self) -> None:
        """Send the motion stop command to the Elfin controller."""
        self._robot.stop_robot()
