from __future__ import annotations

import time
from dataclasses import dataclass

from .domain import Measurement, Waveform
from .ports import AcquisitionDevice, PulseSource


@dataclass(frozen=True, slots=True)
class AcquisitionSettings:
    repetitions: int = 1
    interval_s: float = 0.0
    trigger_timeout_s: float = 10.0
    buffer_timeout_s: float = 10.0

    def __post_init__(self) -> None:
        if self.repetitions < 1:
            raise ValueError("repetitions must be at least 1.")
        if min(self.interval_s, self.trigger_timeout_s, self.buffer_timeout_s) < 0:
            raise ValueError("Time values cannot be negative.")


class AcquisitionService:
    """Coordinates the safe order: arm, fire, wait, and read."""

    def __init__(
        self,
        device: AcquisitionDevice,
        pulse_source: PulseSource,
        settings: AcquisitionSettings | None = None,
    ) -> None:
        self._device = device
        self._pulse_source = pulse_source
        self.settings = settings or AcquisitionSettings()

    def acquire_once(self) -> Waveform:
        self._device.arm()
        self._pulse_source.fire()
        self._device.wait_for_trigger(self.settings.trigger_timeout_s)
        self._device.wait_until_ready(self.settings.buffer_timeout_s)
        return self._device.read_waveform()

    def measure(self) -> Measurement:
        waveforms: list[Waveform] = []
        for index in range(self.settings.repetitions):
            waveforms.append(self.acquire_once())
            if index + 1 < self.settings.repetitions and self.settings.interval_s:
                time.sleep(self.settings.interval_s)
        return Measurement.aggregate(waveforms)
