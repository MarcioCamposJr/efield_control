"""Adapt Elfin communication to the robot contract used by the experiments."""

from __future__ import annotations

import time

from efield_control.domain import Pose
from .client import Elfin


class ElfinRobotAdapter:
    """Expose poses in millimeters/degrees and movements that wait for completion."""
    def __init__(
        self,
        host: str,
        *,
        use_new_api: bool = False,
        movement_timeout_s: float = 30.0,
        settling_time_s: float = 1.0,
    ) -> None:
        self._robot = Elfin(ip=host, use_new_api=use_new_api)
        self.movement_timeout_s = movement_timeout_s
        self.settling_time_s = settling_time_s

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
        return Pose(*map(float, values[:6]))

    def move_to(self, pose: Pose) -> None:
        """Request an Elfin linear movement and wait for completion and settling."""
        if not self._robot.connection.move_linear(pose.as_list()):
            raise RuntimeError("The Elfin robot rejected the motion command.")

        deadline = time.monotonic() + self.movement_timeout_s
        time.sleep(0.2)
        while self._robot.is_moving():
            if self._robot.is_error_state():
                raise RuntimeError("The Elfin robot entered an error state.")
            if time.monotonic() > deadline:
                self.stop()
                raise TimeoutError("Timed out while waiting for Elfin motion.")
            time.sleep(0.05)
        time.sleep(self.settling_time_s)

    def stop(self) -> None:
        """Send the motion stop command to the Elfin controller."""
        self._robot.stop_robot()
