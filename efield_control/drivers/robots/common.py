"""Motion parameters shared by Cartesian robot drivers."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RobotMotionSettings:
    movement_timeout_s: float = 30.0
    settling_time_s: float = 1.0
    speed_percent: int = 10
    socket_timeout_s: float = 3.0
    position_tolerance_mm: float = 0.1
    orientation_tolerance_deg: float = 0.1

    def __post_init__(self) -> None:
        positive = (
            self.movement_timeout_s, self.socket_timeout_s,
            self.position_tolerance_mm, self.orientation_tolerance_deg,
        )
        if any(not math.isfinite(value) or value <= 0 for value in positive):
            raise ValueError("Robot timeouts and tolerances must be finite and positive.")
        if not math.isfinite(self.settling_time_s) or self.settling_time_s < 0:
            raise ValueError("Robot settling time must be finite and non-negative.")
        if (isinstance(self.speed_percent, bool) or not isinstance(self.speed_percent, int)
                or not 1 <= self.speed_percent <= 100):
            raise ValueError("Robot speed percentage must be an integer from 1 to 100.")


def pose_matches(
    actual: tuple[float, ...] | list[float],
    target: tuple[float, ...] | list[float],
    position_tolerance_mm: float,
    orientation_tolerance_deg: float,
) -> bool:
    """Compare XYZ distance and wrapped Euler angles in mm and degrees."""
    if len(actual) != 6 or len(target) != 6:
        return False
    if not all(math.isfinite(value) for value in (*actual, *target)):
        return False
    angle_error = max(abs((a - b + 180) % 360 - 180) for a, b in zip(actual[3:], target[3:]))
    return (math.dist(actual[:3], target[:3]) <= position_tolerance_mm
            and angle_error <= orientation_tolerance_deg)
