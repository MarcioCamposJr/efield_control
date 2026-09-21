from __future__ import annotations

from dataclasses import dataclass

from .configuration import AngularStageCalibration, SensorPoseCalibration
from .domain import Pose
from .ports import AngularPositioner


@dataclass(slots=True)
class CalibratedAngularPositioner:
    positioner: AngularPositioner
    calibration: AngularStageCalibration

    def center(self) -> None:
        self.move_to(0.0, 0.0)

    def move_to(self, base_deg: float, inclination_deg: float) -> None:
        base_command, inclination_command = self.calibration.commands_for(
            base_deg, inclination_deg
        )
        self.positioner.move_to(base_command, inclination_command)


def calibrated_center_guess(current_pose: Pose, calibration: SensorPoseCalibration) -> Pose:
    offset = calibration.coil_center_guess
    return Pose(
        x_mm=current_pose.x_mm + offset.x_mm,
        y_mm=current_pose.y_mm + offset.y_mm,
        z_mm=current_pose.z_mm + offset.z_mm,
        rx_deg=current_pose.rx_deg + offset.rx_deg,
        ry_deg=current_pose.ry_deg + offset.ry_deg,
        rz_deg=current_pose.rz_deg + offset.rz_deg,
    )

