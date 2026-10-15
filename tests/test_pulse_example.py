"""Pulse-only tests replace all equipment and never send physical pulses."""

from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, call

import pytest

from efield_control import cli
from efield_control.configuration import PulseTestConfig, load_project_config
from efield_control.drivers.red_pitaya.adapter import RedPitayaDigitalPulse
from examples.pulse_stimulator import main


PROJECT_DIRECTORY = Path(__file__).resolve().parents[1]


@pytest.fixture
def pulse_config(tmp_path, monkeypatch):
    config = load_project_config(
        config_path=PROJECT_DIRECTORY / "config/default.toml",
        env_path=tmp_path / ".env",
        angular_calibration_path=PROJECT_DIRECTORY / "config/calibration/angular_stage.toml",
        sensor_calibration_path=PROJECT_DIRECTORY / "config/calibration/sensor_pose.toml",
        environ={},
    )
    config = replace(
        config,
        hardware=replace(config.hardware, stage_serial_port="test-port", red_pitaya_host="rp.test"),
        pulse_test=PulseTestConfig(count=3, interval_s=2.5),
    )
    for name in ("_robot", "RedPitayaAcquisition", "SensorCentering", "CenterSensorWorkflow"):
        monkeypatch.setattr(cli, name, Mock(side_effect=AssertionError("Unexpected equipment")))
    for name in ("SerialMotorController", "scpi", "MtmsSingleChannelClient"):
        monkeypatch.setattr(cli, name, Mock(side_effect=AssertionError("Wrong pulse source")))
    monkeypatch.setattr("socket.socket", Mock(side_effect=AssertionError("Hardware connection")))
    monkeypatch.setattr("serial.Serial", Mock(side_effect=AssertionError("Serial connection")))
    return config


@pytest.mark.parametrize("source", ["serial", "redpitaya", "mtms_api"])
@pytest.mark.parametrize("outcome", ["success", "failure", "interrupt", "startup_failure"])
def test_pulse_sequence_limits_count_and_cleans_up(pulse_config, monkeypatch, capsys, source, outcome):
    config = replace(pulse_config, pulse=replace(pulse_config.pulse, source=source))
    monkeypatch.setattr(cli, "load_project_config", Mock(return_value=config))
    events = Mock()
    monkeypatch.setattr(cli.time, "sleep", events.sleep)
    device = Mock()
    factory = Mock(return_value=device)
    if source == "serial":
        monkeypatch.setattr(cli, "SerialMotorController", factory)
        fire = device.fire
        startup = device.ping
    elif source == "redpitaya":
        monkeypatch.setattr(cli, "scpi", factory)
        digital = Mock()
        startup = Mock(return_value=digital)
        monkeypatch.setattr(cli, "RedPitayaDigitalPulse", startup)
        fire = digital.fire
    else:
        monkeypatch.setattr(cli, "MtmsSingleChannelClient", factory)
        fire = device.trigger
        startup = device.connect
    events.attach_mock(fire, "fire")
    events.attach_mock(device.close, "close")
    if outcome == "startup_failure":
        startup.side_effect = RuntimeError("Startup failed")
    elif outcome == "failure":
        fire.side_effect = [None, TimeoutError("Pulse completion unknown")]
    elif outcome == "interrupt":
        fire.side_effect = [None, KeyboardInterrupt]

    if outcome in {"failure", "startup_failure"}:
        with pytest.raises((TimeoutError, RuntimeError)):
            main(["--confirm-hardware", "MOVE_AND_FIRE"])
    else:
        assert main(["--confirm-hardware", "MOVE_AND_FIRE"]) == (130 if outcome == "interrupt" else 0)

    expected = [call.fire(), call.sleep(2.5), call.fire(), call.sleep(2.5), call.fire(), call.close()]
    if outcome == "startup_failure":
        expected = [call.close()]
    elif outcome in {"failure", "interrupt"}:
        expected = expected[:3] + [call.close()]
    assert events.mock_calls == expected
    output = capsys.readouterr()
    assert ("Pulse command 3/3 completed" in output.out) == (outcome == "success")
    if source == "mtms_api":
        factory.validate_environment.assert_called_once()
        assert factory.call_args.args[0].target_voltage_v == config.mtms.target_voltage_v


def test_mtms_interval_is_checked_before_imports_or_connections(pulse_config, monkeypatch):
    config = replace(
        pulse_config, pulse=replace(pulse_config.pulse, source="mtms_api"),
        pulse_test=PulseTestConfig(count=3, interval_s=1),
    )
    monkeypatch.setattr(cli, "load_project_config", Mock(return_value=config))
    with pytest.raises(ValueError, match="minimum_inter_pulse_interval_s"):
        main(["--confirm-hardware", "MOVE_AND_FIRE"])
    cli.MtmsSingleChannelClient.assert_not_called()
    cli.MtmsSingleChannelClient.validate_environment.assert_not_called()


def test_serial_ping_retries_once_without_repeating_pulses(pulse_config, monkeypatch):
    config = replace(pulse_config, pulse=replace(pulse_config.pulse, source="serial"),
                     pulse_test=PulseTestConfig(count=1))
    monkeypatch.setattr(cli, "load_project_config", Mock(return_value=config))
    controller = Mock()
    controller.ping.side_effect = [TimeoutError, None]
    monkeypatch.setattr(cli, "SerialMotorController", Mock(return_value=controller))
    sleep = Mock()
    monkeypatch.setattr(cli.time, "sleep", sleep)
    assert main(["--confirm-hardware", "MOVE_AND_FIRE"]) == 0
    assert controller.ping.call_count == 2
    controller.fire.assert_called_once()
    controller.close.assert_called_once()
    sleep.assert_not_called()


@pytest.mark.parametrize("values", [
    {"count": 0}, {"count": -1}, {"count": 1.5}, {"count": True},
    {"interval_s": 0}, {"interval_s": -1}, {"interval_s": float("nan")},
    {"interval_s": float("inf")},
])
def test_invalid_pulse_test_settings_are_rejected(values):
    with pytest.raises(ValueError):
        PulseTestConfig(**values)


def test_pulse_test_parameters_load_from_toml(tmp_path):
    path = tmp_path / "experiment.toml"
    path.write_text("[pulse_test]\ncount = 5\ninterval_s = 4.0\n", encoding="utf-8")
    config = load_project_config(config_path=path, env_path=tmp_path / ".env", environ={})
    assert config.pulse_test == PulseTestConfig(count=5, interval_s=4.0)


def test_red_pitaya_trigger_returns_to_idle_on_interrupt(monkeypatch):
    client = Mock()
    pulse = RedPitayaDigitalPulse(client)
    client.reset_mock()
    monkeypatch.setattr("efield_control.drivers.red_pitaya.adapter.time.sleep",
                        Mock(side_effect=[None, KeyboardInterrupt]))
    with pytest.raises(KeyboardInterrupt):
        pulse.fire()
    assert client.tx_txt.call_args_list == [
        call("DIG:PIN DIO1_P,0"), call("DIG:PIN DIO1_P,1"), call("DIG:PIN DIO1_P,0"),
    ]
