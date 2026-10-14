"""Link centering decisions to robot movement and sensor acquisition."""

from __future__ import annotations

from dataclasses import dataclass

from .acquisition import AcquisitionService
from .centering import CenteringResult, SampleObserver, SensorCentering
from .domain import Measurement, Pose
from .ports import CartesianRobot


@dataclass(slots=True)
class CenterSensorWorkflow:
    """Supply the algorithm with a function that moves the robot and measures each position."""
    robot: CartesianRobot
    acquisition: AcquisitionService
    algorithm: SensorCentering

    def run(
        self,
        origin: Pose | None = None,
        observer: SampleObserver | None = None,
    ) -> CenteringResult:
        reference = origin or self.robot.current_pose()

        def evaluate(x_mm: float, y_mm: float) -> Measurement:
            # The reference preserves Z and orientation; the algorithm varies only X/Y.
            self.robot.move_to(reference.with_xy(x_mm, y_mm))
            return self.acquisition.measure()

        result = self.algorithm.run(
            start_x_mm=reference.x_mm,
            start_y_mm=reference.y_mm,
            evaluate=evaluate,
            observer=observer,
        )
        # The last tested position may not be the best; finish at the resulting center.
        self.robot.move_to(reference.with_xy(result.x_mm, result.y_mm))
        return result
