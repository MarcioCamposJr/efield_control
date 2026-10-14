import builtins
import os
import sys
from types import ModuleType

import pytest

from efield_control.drivers.stimulators.mtms import (
    MtmsApiPulse,
    MtmsSingleChannelClient,
    MtmsSingleChannelSettings,
)


class FakeMtmsApiClient:
    def __init__(self) -> None:
        self.events: list[str] = []

    def connect(self) -> None:
        self.events.append("connect")

    def trigger(self) -> None:
        self.events.append("trigger")

    def close(self) -> None:
        self.events.append("close")


class FakeExecutionCondition:
    IMMEDIATE = "immediate"
    TIMED = "timed"


class FakeVendorApi:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def _record(self, name: str, **values) -> None:
        self.events.append((name, values))

    def start_device(self) -> None:
        self._record("start_device")

    def start_session(self) -> None:
        self._record("start_session")

    def send_charge(self, **values) -> None:
        self._record("send_charge", **values)

    def wait_for_completion(self) -> None:
        self._record("wait_for_completion")

    def get_default_waveform(self, channel: int):
        self._record("get_default_waveform", channel=channel)
        return "default-waveform"

    def get_time(self) -> float:
        self._record("get_time")
        return 100.0

    def send_pulse(self, **values) -> None:
        self._record("send_pulse", **values)

    def send_trigger_out(self, **values) -> None:
        self._record("send_trigger_out", **values)

    def send_discharge(self, **values) -> None:
        self._record("send_discharge", **values)

    def stop_session(self) -> None:
        self._record("stop_session")

    def stop_device(self) -> None:
        self._record("stop_device")

    def end(self) -> None:
        self._record("end")


def test_mtms_api_pulse_delegates_lifecycle_and_trigger() -> None:
    client = FakeMtmsApiClient()

    with MtmsApiPulse(client) as pulse:
        pulse.fire()

    assert client.events == ["connect", "trigger", "close"]


def test_mtms_api_pulse_requires_connection() -> None:
    pulse = MtmsApiPulse(FakeMtmsApiClient())

    with pytest.raises(RuntimeError, match="not connected"):
        pulse.fire()


def test_single_channel_client_charges_pulses_marks_and_discharges() -> None:
    api = FakeVendorApi()
    settings = MtmsSingleChannelSettings(
        channel=1,
        allowed_channels=(0, 1),
        target_voltage_v=15.0,
        maximum_target_voltage_v=20.0,
        reverse_polarity=True,
        trigger_out_port=2,
        trigger_out_duration_us=750,
        schedule_lead_s=1.5,
        minimum_inter_pulse_interval_s=0,
    )
    client = MtmsSingleChannelClient(
        settings,
        api_factory=lambda: api,
        execution_condition=FakeExecutionCondition,
    )

    client.connect()
    client.trigger()
    client.close()

    event_names = [name for name, _ in api.events]
    assert event_names == [
        "start_device",
        "start_session",
        "send_charge",
        "wait_for_completion",
        "get_default_waveform",
        "get_time",
        "send_pulse",
        "send_trigger_out",
        "wait_for_completion",
        "send_discharge",
        "wait_for_completion",
        "stop_session",
        "stop_device",
        "end",
    ]
    pulse_values = dict(api.events[6][1])
    marker_values = dict(api.events[7][1])
    assert pulse_values["channel"] == 1
    assert pulse_values["time"] == 101.5
    assert pulse_values["reverse_polarity"] is True
    assert marker_values["port"] == 2
    assert marker_values["duration_us"] == 750
    assert marker_values["time"] == pulse_values["time"]


def test_single_channel_voltage_cannot_exceed_safety_ceiling() -> None:
    with pytest.raises(ValueError, match="cannot exceed"):
        MtmsSingleChannelSettings(
            target_voltage_v=21.0,
            maximum_target_voltage_v=20.0,
        )


def test_client_imports_existing_api_without_preparing_environment(monkeypatch) -> None:
    vendor_module = ModuleType("MTMSApi")
    vendor_module.MTMSApi = FakeVendorApi
    interfaces_module = ModuleType("mtms_event_interfaces")
    interfaces_module.__path__ = []
    messages_module = ModuleType("mtms_event_interfaces.msg")
    messages_module.ExecutionCondition = FakeExecutionCondition
    monkeypatch.setitem(sys.modules, "MTMSApi", vendor_module)
    monkeypatch.setitem(sys.modules, "mtms_event_interfaces", interfaces_module)
    monkeypatch.setitem(sys.modules, "mtms_event_interfaces.msg", messages_module)
    monkeypatch.setitem(sys.modules, "rclpy", None)
    environment_before = dict(os.environ)
    import_path_before = list(sys.path)
    client = MtmsSingleChannelClient(MtmsSingleChannelSettings())

    client.validate_environment()
    factory, condition = client._load_vendor_api()

    assert factory is FakeVendorApi
    assert condition is FakeExecutionCondition
    assert dict(os.environ) == environment_before
    assert sys.path == import_path_before


@pytest.mark.parametrize("missing_module", ["MTMSApi", "mtms_event_interfaces.msg"])
def test_missing_api_import_stops_without_preparing_environment(
    monkeypatch, missing_module: str
) -> None:
    original_import = builtins.__import__

    def import_with_missing_api(name, *args, **kwargs):
        if name == missing_module:
            raise ModuleNotFoundError(f"No module named '{name}'", name=name)
        if name == "MTMSApi":
            module = ModuleType(name)
            module.MTMSApi = FakeVendorApi
            return module
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_with_missing_api)
    environment_before = dict(os.environ)
    import_path_before = list(sys.path)
    client = MtmsSingleChannelClient(MtmsSingleChannelSettings())

    with pytest.raises(RuntimeError, match="No environment setup is performed") as error:
        client.connect()

    assert isinstance(error.value.__cause__, ModuleNotFoundError)
    assert error.value.__cause__.name == missing_module
    assert client._api is None
    assert dict(os.environ) == environment_before
    assert sys.path == import_path_before
