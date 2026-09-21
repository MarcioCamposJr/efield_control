from __future__ import annotations

from dataclasses import dataclass
from math import exp

from efield_control.domain import Pose, Waveform


class SimulatedRobot:
    def __init__(self, initial_pose: Pose) -> None:
        self.pose = initial_pose
        self.connected = False

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def current_pose(self) -> Pose:
        return self.pose

    def move_to(self, pose: Pose) -> None:
        if not self.connected:
            raise RuntimeError("The simulated robot is disconnected.")
        self.pose = pose

    def stop(self) -> None:
        return None


class SimulatedPulse:
    def fire(self) -> None:
        return None


@dataclass(slots=True)
class GaussianAcquisition:
    """Synthetic field with a known maximum for centering tests."""

    robot: SimulatedRobot
    center_x_mm: float
    center_y_mm: float
    sigma_mm: float = 5.0
    sample_rate_hz: float = 15_625_000.0

    def arm(self) -> None:
        return None

    def wait_for_trigger(self, timeout_s: float) -> None:
        return None

    def wait_until_ready(self, timeout_s: float) -> None:
        return None

    def read_waveform(self) -> Waveform:
        dx = self.robot.pose.x_mm - self.center_x_mm
        dy = self.robot.pose.y_mm - self.center_y_mm
        amplitude = exp(-(dx * dx + dy * dy) / (2 * self.sigma_mm**2))
        return Waveform.from_iterables(
            (-amplitude / 2, amplitude / 2),
            (-amplitude / 4, amplitude / 4),
            self.sample_rate_hz,
        )

    def close(self) -> None:
        return None
