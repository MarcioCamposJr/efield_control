from pathlib import Path

import pytest

from efield_control.drivers.stimulators.mtms import (
    MtmsApiPulse,
    MtmsSingleChannelClient,
    MtmsSingleChannelSettings,
)
from run_with_mtms import (
    MtmsBootstrapError,
    find_mtms_workspace,
    read_env_file,
    resolve_api_directory,
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


def test_bootstrap_finds_api_and_compiled_workspace(tmp_path: Path) -> None:
    api_directory = tmp_path / "api" / "python"
    api_directory.mkdir(parents=True)
    api_file = api_directory / "MTMSApi.py"
    api_file.touch()
    setup = tmp_path / "install" / "local_setup.bash"
    setup.parent.mkdir()
    setup.touch()

    assert resolve_api_directory(str(api_file)) == api_directory
    assert resolve_api_directory(str(api_directory)) == api_directory
    assert find_mtms_workspace(api_directory) == tmp_path


def test_bootstrap_rejects_missing_api(tmp_path: Path) -> None:
    with pytest.raises(MtmsBootstrapError, match="MTMSApi.py was not found"):
        resolve_api_directory(str(tmp_path))


def test_bootstrap_reads_quoted_env_values(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        '# comment\nEFIELD_MTMS_API_PATH="/opt/mtms api/MTMSApi.py"\n',
        encoding="utf-8",
    )

    assert read_env_file(env_file)["EFIELD_MTMS_API_PATH"] == (
        "/opt/mtms api/MTMSApi.py"
    )
