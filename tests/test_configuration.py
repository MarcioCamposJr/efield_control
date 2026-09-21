from pathlib import Path

from efield_control.calibration import CalibratedAngularPositioner
from efield_control.configuration import PulseConfig, load_project_config


class FakePositioner:
    def __init__(self) -> None:
        self.moves: list[tuple[float, float]] = []

    def center(self) -> None:
        raise AssertionError("The raw CENTER command must not bypass calibration.")

    def move_to(self, base_deg: float, inclination_deg: float) -> None:
        self.moves.append((base_deg, inclination_deg))


def test_environment_overrides_toml_and_env_file() -> None:
    config = load_project_config(
        environ={
            "EFIELD_RED_PITAYA_HOST": "10.0.0.10",
            "EFIELD_ROBOT_HOST": "10.0.0.20",
            "EFIELD_STAGE_SERIAL_BAUD": "57600",
        }
    )

    assert config.hardware.red_pitaya_host == "10.0.0.10"
    assert config.hardware.robot_host == "10.0.0.20"
    assert config.hardware.stage_serial_baud == 57600
    assert config.acquisition.decimation == 8


def test_experiment_toml_does_not_contain_hardware_section() -> None:
    content = Path("config/default.toml").read_text(encoding="utf-8")

    assert "[hardware]" not in content


def test_mtms_api_is_a_supported_pulse_source() -> None:
    assert PulseConfig(source="mtms_api").source == "mtms_api"


def test_angular_calibration_transforms_logical_angles() -> None:
    config = load_project_config(environ={})
    raw = FakePositioner()
    positioner = CalibratedAngularPositioner(raw, config.angular_calibration)

    positioner.center()
    positioner.move_to(10, -5)

    assert raw.moves == [(90.0, 92.0), (100.0, 87.0)]


def test_angular_calibration_rejects_out_of_range_command() -> None:
    config = load_project_config(environ={})

    try:
        config.angular_calibration.commands_for(91, 0)
    except ValueError as error:
        assert "outside the calibrated range" in str(error)
    else:
        raise AssertionError("Out-of-range motor command was accepted.")
