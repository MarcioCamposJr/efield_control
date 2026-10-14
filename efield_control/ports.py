"""Equipment contracts used by the algorithms.

Protocol describes expected methods without connecting or commanding hardware.
A class satisfies a contract by providing its methods; inheritance is optional.
Concrete implementations live in drivers/.
"""

from __future__ import annotations

from typing import Protocol

from .domain import Pose, Waveform


class CartesianRobot(Protocol):
    """Robot that moves the sensor to a Cartesian pose in mm and degrees."""

    def connect(self) -> None: ...

    def disconnect(self) -> None: ...

    def current_pose(self) -> Pose: ...

    def move_to(self, pose: Pose) -> None: ...

    def stop(self) -> None: ...


class AngularPositioner(Protocol):
    """Stage that positions the base and inclination using angles in degrees."""

    def center(self) -> None: ...

    def move_to(self, base_deg: float, inclination_deg: float) -> None: ...


class PulseSource(Protocol):
    """Source that requests a pulse: mTMS, Arduino, Red Pitaya, or a simulator."""

    def fire(self) -> None: ...


class AcquisitionDevice(Protocol):
    """Two-channel acquisition device that arms, waits for a trigger, and reads a waveform.

    arm prepares capture without firing the stimulator. wait_for_trigger waits
    for trigger detection; wait_until_ready waits for the buffer to fill.
    read_waveform returns channel samples in volts and the sampling rate in Hz.
    """

    def arm(self) -> None: ...

    def wait_for_trigger(self, timeout_s: float) -> None: ...

    def wait_until_ready(self, timeout_s: float) -> None: ...

    def read_waveform(self) -> Waveform: ...

    def close(self) -> None: ...
