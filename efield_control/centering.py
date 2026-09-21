from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from typing import Callable

from .domain import Measurement


@dataclass(frozen=True, slots=True)
class CenteringSettings:
    initial_step_mm: float = 1.0
    minimum_step_mm: float = 0.5
    step_reduction: float = 0.5
    relative_improvement: float = 0.005
    max_iterations: int = 20
    max_radius_mm: float = 20.0

    def __post_init__(self) -> None:
        if self.initial_step_mm <= 0 or self.minimum_step_mm <= 0:
            raise ValueError("Step sizes must be positive.")
        if self.minimum_step_mm > self.initial_step_mm:
            raise ValueError("The minimum step cannot exceed the initial step.")
        if not 0 < self.step_reduction < 1:
            raise ValueError("step_reduction must be between 0 and 1.")
        if self.relative_improvement < 0 or self.max_iterations < 1:
            raise ValueError("Invalid stopping configuration.")
        if self.max_radius_mm <= 0:
            raise ValueError("max_radius_mm must be positive.")


@dataclass(frozen=True, slots=True)
class CenteringSample:
    iteration: int
    label: str
    step_mm: float
    x_mm: float
    y_mm: float
    measurement: Measurement
    accepted: bool = False


@dataclass(frozen=True, slots=True)
class CenteringResult:
    x_mm: float
    y_mm: float
    measurement: Measurement
    iterations: int
    samples: tuple[CenteringSample, ...]


PointEvaluator = Callable[[float, float], Measurement]
SampleObserver = Callable[[CenteringSample], None]


class SensorCentering:
    """Cross-pattern local search that maximizes combined channel magnitude."""

    def __init__(self, settings: CenteringSettings | None = None) -> None:
        self.settings = settings or CenteringSettings()

    def run(
        self,
        start_x_mm: float,
        start_y_mm: float,
        evaluate: PointEvaluator,
        observer: SampleObserver | None = None,
    ) -> CenteringResult:
        cfg = self.settings
        x_current = start_x_mm
        y_current = start_y_mm
        step = cfg.initial_step_mm
        samples: list[CenteringSample] = []

        current = evaluate(x_current, y_current)
        initial = CenteringSample(
            iteration=0,
            label="initial",
            step_mm=step,
            x_mm=x_current,
            y_mm=y_current,
            measurement=current,
            accepted=True,
        )
        self._record(initial, samples, observer)

        completed_iterations = 0
        for iteration in range(1, cfg.max_iterations + 1):
            completed_iterations = iteration
            candidates: list[tuple[str, float, float, Measurement]] = [
                ("center", x_current, y_current, current)
            ]
            neighbours = (
                ("+x", x_current + step, y_current),
                ("-x", x_current - step, y_current),
                ("+y", x_current, y_current + step),
                ("-y", x_current, y_current - step),
            )

            for label, x_mm, y_mm in neighbours:
                if not self._inside_radius(
                    start_x_mm, start_y_mm, x_mm, y_mm, cfg.max_radius_mm
                ):
                    continue
                measurement = evaluate(x_mm, y_mm)
                candidates.append((label, x_mm, y_mm, measurement))
                self._record(
                    CenteringSample(
                        iteration=iteration,
                        label=label,
                        step_mm=step,
                        x_mm=x_mm,
                        y_mm=y_mm,
                        measurement=measurement,
                    ),
                    samples,
                    observer,
                )

            best = max(candidates, key=lambda item: item[3].magnitude_v)
            improvement = self._relative_improvement(
                current.magnitude_v, best[3].magnitude_v
            )

            if best[0] != "center" and improvement > cfg.relative_improvement:
                _, x_current, y_current, current = best
                accepted = CenteringSample(
                    iteration=iteration,
                    label="accepted",
                    step_mm=step,
                    x_mm=x_current,
                    y_mm=y_current,
                    measurement=current,
                    accepted=True,
                )
                self._record(accepted, samples, observer)
                continue

            if step <= cfg.minimum_step_mm:
                break
            step = max(cfg.minimum_step_mm, step * cfg.step_reduction)

        return CenteringResult(
            x_mm=x_current,
            y_mm=y_current,
            measurement=current,
            iterations=completed_iterations,
            samples=tuple(samples),
        )

    @staticmethod
    def _inside_radius(
        origin_x: float,
        origin_y: float,
        x_mm: float,
        y_mm: float,
        radius_mm: float,
    ) -> bool:
        return hypot(x_mm - origin_x, y_mm - origin_y) <= radius_mm

    @staticmethod
    def _relative_improvement(current: float, candidate: float) -> float:
        if current <= 0:
            return float("inf") if candidate > current else 0.0
        return (candidate - current) / current

    @staticmethod
    def _record(
        sample: CenteringSample,
        samples: list[CenteringSample],
        observer: SampleObserver | None,
    ) -> None:
        samples.append(sample)
        if observer is not None:
            observer(sample)
