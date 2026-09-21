from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator

from .acquisition import AcquisitionService
from .domain import Measurement, Pose
from .ports import AngularPositioner, CartesianRobot


@dataclass(frozen=True, slots=True)
class PlanarPoint:
    row: int
    column: int
    dx_mm: float
    dy_mm: float


@dataclass(frozen=True, slots=True)
class AngularPoint:
    row: int
    column: int
    base_deg: float
    inclination_deg: float


def planar_serpentine(
    x_offsets_mm: Iterable[float], y_offsets_mm: Iterable[float]
) -> Iterator[PlanarPoint]:
    xs = tuple(float(value) for value in x_offsets_mm)
    ys = tuple(float(value) for value in y_offsets_mm)
    if not xs or not ys:
        raise ValueError("A planar map requires both X and Y values.")

    for row, y_mm in enumerate(ys):
        columns = range(len(xs)) if row % 2 == 0 else range(len(xs) - 1, -1, -1)
        for column in columns:
            yield PlanarPoint(row, column, xs[column], y_mm)


def circular_serpentine(
    base_angles_deg: Iterable[float], inclination_angles_deg: Iterable[float]
) -> Iterator[AngularPoint]:
    bases = tuple(float(value) for value in base_angles_deg)
    inclinations = tuple(float(value) for value in inclination_angles_deg)
    if not bases or not inclinations:
        raise ValueError("A circular map requires both angle sets.")

    for row, inclination in enumerate(inclinations):
        columns = (
            range(len(bases)) if row % 2 == 0 else range(len(bases) - 1, -1, -1)
        )
        for column in columns:
            yield AngularPoint(row, column, bases[column], inclination)


class PlanarMapping:
    def __init__(self, robot: CartesianRobot, acquisition: AcquisitionService) -> None:
        self.robot = robot
        self.acquisition = acquisition

    def run(
        self,
        origin: Pose,
        points: Iterable[PlanarPoint],
    ) -> Iterator[tuple[PlanarPoint, Pose, Measurement]]:
        for point in points:
            target = origin.translated(point.dx_mm, point.dy_mm)
            self.robot.move_to(target)
            yield point, target, self.acquisition.measure()


class CircularMapping:
    def __init__(
        self,
        positioner: AngularPositioner,
        acquisition: AcquisitionService,
    ) -> None:
        self.positioner = positioner
        self.acquisition = acquisition

    def run(
        self, points: Iterable[AngularPoint]
    ) -> Iterator[tuple[AngularPoint, Measurement]]:
        for point in points:
            self.positioner.move_to(point.base_deg, point.inclination_deg)
            yield point, self.acquisition.measure()
