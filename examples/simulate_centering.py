from efield_control.acquisition import AcquisitionService
from efield_control.centering import CenteringSettings, SensorCentering
from efield_control.domain import Pose
from efield_control.drivers.simulated import (
    GaussianAcquisition,
    SimulatedPulse,
    SimulatedRobot,
)
from efield_control.workflows import CenterSensorWorkflow


def main() -> None:
    robot = SimulatedRobot(Pose(0, 0, 10))
    robot.connect()
    device = GaussianAcquisition(robot, center_x_mm=3.0, center_y_mm=-2.0)
    acquisition = AcquisitionService(device, SimulatedPulse())
    algorithm = SensorCentering(
        CenteringSettings(initial_step_mm=2.0, minimum_step_mm=0.5)
    )

    result = CenterSensorWorkflow(robot, acquisition, algorithm).run()
    print(
        f"Center: X={result.x_mm:.2f} mm, Y={result.y_mm:.2f} mm, "
        f"magnitude={result.measurement.magnitude_v:.6f} V"
    )


if __name__ == "__main__":
    main()
