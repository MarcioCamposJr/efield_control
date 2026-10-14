"""Shared data: poses in millimeters/degrees and electrical signals in volts."""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from statistics import median
from typing import Iterable


@dataclass(frozen=True, slots=True)
class Pose:
    """Cartesian pose expressed in millimeters and degrees."""

    x_mm: float
    y_mm: float
    z_mm: float
    rx_deg: float = 0.0
    ry_deg: float = 0.0
    rz_deg: float = 0.0

    def with_xy(self, x_mm: float, y_mm: float) -> "Pose":
        """Create a pose with absolute X/Y coordinates, preserving Z and orientation."""
        return Pose(
            x_mm=x_mm,
            y_mm=y_mm,
            z_mm=self.z_mm,
            rx_deg=self.rx_deg,
            ry_deg=self.ry_deg,
            rz_deg=self.rz_deg,
        )

    def translated(self, dx_mm: float = 0.0, dy_mm: float = 0.0) -> "Pose":
        """Apply X/Y offsets relative to the pose without sending robot commands."""
        return self.with_xy(self.x_mm + dx_mm, self.y_mm + dy_mm)

    def as_list(self) -> list[float]:
        return [
            self.x_mm,
            self.y_mm,
            self.z_mm,
            self.rx_deg,
            self.ry_deg,
            self.rz_deg,
        ]


@dataclass(frozen=True, slots=True)
class Waveform:
    """Samples from both channels in volts, with the sampling rate in Hz."""
    channel_1_v: tuple[float, ...]
    channel_2_v: tuple[float, ...]
    sample_rate_hz: float

    @classmethod
    def from_iterables(
        cls,
        channel_1_v: Iterable[float],
        channel_2_v: Iterable[float],
        sample_rate_hz: float,
    ) -> "Waveform":
        return cls(tuple(channel_1_v), tuple(channel_2_v), sample_rate_hz)

    def __post_init__(self) -> None:
        if not self.channel_1_v or not self.channel_2_v:
            raise ValueError("Both channels must contain samples.")
        if self.sample_rate_hz <= 0:
            raise ValueError("The sample rate must be positive.")

    @staticmethod
    def _peak_to_peak(values: tuple[float, ...]) -> float:
        return max(values) - min(values)

    @property
    def p2p_ch1_v(self) -> float:
        return self._peak_to_peak(self.channel_1_v)

    @property
    def p2p_ch2_v(self) -> float:
        return self._peak_to_peak(self.channel_2_v)

    @property
    def magnitude_v(self) -> float:
        """Combine peak-to-peak values without converting them to electric field in V/m."""
        return hypot(self.p2p_ch1_v, self.p2p_ch2_v)


@dataclass(frozen=True, slots=True)
class Measurement:
    """Aggregated result from one or more acquisitions at the same point."""

    p2p_ch1_v: float
    p2p_ch2_v: float
    magnitude_v: float
    waveform: Waveform
    repetitions: int = 1

    @classmethod
    def aggregate(cls, waveforms: Iterable[Waveform]) -> "Measurement":
        """Use measurement medians and keep the waveform from the last repetition."""
        collected = tuple(waveforms)
        if not collected:
            raise ValueError("At least one acquisition is required.")

        p2p_ch1 = median(item.p2p_ch1_v for item in collected)
        p2p_ch2 = median(item.p2p_ch2_v for item in collected)
        magnitude = median(item.magnitude_v for item in collected)
        return cls(
            p2p_ch1_v=float(p2p_ch1),
            p2p_ch2_v=float(p2p_ch2),
            magnitude_v=float(magnitude),
            waveform=collected[-1],
            repetitions=len(collected),
        )
