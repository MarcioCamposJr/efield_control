from efield_control.acquisition import AcquisitionService, AcquisitionSettings
from efield_control.domain import Waveform


class FakeDevice:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def arm(self) -> None:
        self.events.append("arm")

    def wait_for_trigger(self, timeout_s: float) -> None:
        self.events.append("trigger")

    def wait_until_ready(self, timeout_s: float) -> None:
        self.events.append("ready")

    def read_waveform(self) -> Waveform:
        self.events.append("read")
        return Waveform.from_iterables([-1, 1], [-2, 2], 1_000)

    def close(self) -> None:
        return None


class FakePulse:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def fire(self) -> None:
        self.events.append("fire")


def test_acquisition_uses_safe_order() -> None:
    events: list[str] = []
    service = AcquisitionService(
        FakeDevice(events),
        FakePulse(events),
        AcquisitionSettings(trigger_timeout_s=1, buffer_timeout_s=1),
    )

    result = service.measure()

    assert events == ["arm", "fire", "trigger", "ready", "read"]
    assert result.p2p_ch1_v == 2
    assert result.p2p_ch2_v == 4

