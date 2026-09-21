from __future__ import annotations

from typing import Protocol

from .domain import Pose, Waveform


class CartesianRobot(Protocol):
    """Contract implemented by Elfin and, in the future, Dobot."""

    def connect(self) -> None: ...

    def disconnect(self) -> None: ...

    def current_pose(self) -> Pose: ...

    def move_to(self, pose: Pose) -> None: ...

    def stop(self) -> None: ...


class AngularPositioner(Protocol):
    """Circular-stage controller independent of its electrical protocol."""

    def center(self) -> None: ...

    def move_to(self, base_deg: float, inclination_deg: float) -> None: ...


class PulseSource(Protocol):
    """Device that requests the pulse used to produce a measurement."""

    def fire(self) -> None: ...


class AcquisitionDevice(Protocol):
    """Two-channel acquisition device synchronized by a trigger."""

    def arm(self) -> None: ...

    def wait_for_trigger(self, timeout_s: float) -> None: ...

    def wait_until_ready(self, timeout_s: float) -> None: ...

    def read_waveform(self) -> Waveform: ...

    def close(self) -> None: ...
