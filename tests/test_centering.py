from efield_control.acquisition import AcquisitionService
from efield_control.centering import CenteringSettings, SensorCentering
from efield_control.domain import Pose
from efield_control.drivers.simulated import (
    GaussianAcquisition,
    SimulatedPulse,
    SimulatedRobot,
)
from efield_control.workflows import CenterSensorWorkflow


def test_centering_converges_to_field_maximum() -> None:
    robot = SimulatedRobot(Pose(0, 0, 10))
    robot.connect()
    device = GaussianAcquisition(robot, center_x_mm=3.0, center_y_mm=-2.0)
    acquisition = AcquisitionService(device, SimulatedPulse())
    algorithm = SensorCentering(
        CenteringSettings(
            initial_step_mm=2.0,
            minimum_step_mm=0.5,
            relative_improvement=0.0,
            max_iterations=20,
        )
    )

    result = CenterSensorWorkflow(robot, acquisition, algorithm).run()

    assert abs(result.x_mm - 3.0) <= 0.5
    assert abs(result.y_mm + 2.0) <= 0.5
    assert robot.current_pose().x_mm == result.x_mm
    assert robot.current_pose().y_mm == result.y_mm

