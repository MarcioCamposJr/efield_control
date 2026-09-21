from __future__ import annotations

from dataclasses import dataclass

from .acquisition import AcquisitionService
from .centering import CenteringResult, SampleObserver, SensorCentering
from .domain import Measurement, Pose
from .ports import CartesianRobot


@dataclass(slots=True)
class CenterSensorWorkflow:
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
            self.robot.move_to(reference.with_xy(x_mm, y_mm))
            return self.acquisition.measure()

        result = self.algorithm.run(
            start_x_mm=reference.x_mm,
            start_y_mm=reference.y_mm,
            evaluate=evaluate,
            observer=observer,
        )
        self.robot.move_to(reference.with_xy(result.x_mm, result.y_mm))
        return result
