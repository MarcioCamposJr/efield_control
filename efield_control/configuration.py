"""Read project parameters and calibrations without reconfiguring the host environment."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from .drivers.robots.common import RobotMotionSettings

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib


def _validate_sweep(start: float, stop: float, step: float, name: str) -> None:
    if step == 0 or (stop - start) * step < 0:
        raise ValueError(f"Invalid {name} sweep.")


@dataclass(frozen=True, slots=True)
class HardwareConfig:
    red_pitaya_host: str = ""
    red_pitaya_port: int = 5000
    robot_host: str = ""
    robot_type: str = "elfin"
    elfin_use_new_api: bool = False
    stage_serial_port: str = ""
    stage_serial_baud: int = 115200
    stage_serial_timeout_s: float = 3.0

    def __post_init__(self) -> None:
        if self.robot_type not in {"elfin", "dobot"}:
            raise ValueError("EFIELD_ROBOT_TYPE must be 'elfin' or 'dobot'.")
        if not 1 <= self.red_pitaya_port <= 65535:
            raise ValueError("Red Pitaya port must be between 1 and 65535.")
        if self.stage_serial_baud <= 0 or self.stage_serial_timeout_s < 0:
            raise ValueError("Serial baud rate and timeout are invalid.")


@dataclass(frozen=True, slots=True)
class AcquisitionConfig:
    decimation: int = 8
    trigger_source: str = "EXT_PE"
    trigger_delay: int = 0
    trigger_timeout_s: float = 10.0
    buffer_timeout_s: float = 10.0
    repetitions: int = 1
    repetition_interval_s: float = 2.0
    high_voltage: bool = True

    def __post_init__(self) -> None:
        if self.decimation <= 0 or self.repetitions < 1:
            raise ValueError("Decimation and repetitions must be positive.")
        if min(
            self.trigger_timeout_s,
            self.buffer_timeout_s,
            self.repetition_interval_s,
        ) < 0:
            raise ValueError("Acquisition time values cannot be negative.")


@dataclass(frozen=True, slots=True)
class PulseConfig:
    source: str = "serial"
    pin: str = "DIO1_P"
    duration_s: float = 0.010

    def __post_init__(self) -> None:
        if self.source not in {"serial", "redpitaya", "mtms_api"}:
            raise ValueError(
                "Pulse source must be 'serial', 'redpitaya', or 'mtms_api'."
            )
        if self.duration_s <= 0:
            raise ValueError("Pulse duration must be positive.")


@dataclass(frozen=True, slots=True)
class MtmsConfig:
    channel: int = 0
    allowed_channels: tuple[int, ...] = (0, 1)
    target_voltage_v: float = 20.0
    maximum_target_voltage_v: float = 20.0
    reverse_polarity: bool = False
    trigger_out_port: int = 1
    trigger_out_duration_us: int = 1000
    schedule_lead_s: float = 1.0
    minimum_inter_pulse_interval_s: float = 2.0
    discharge_after_pulse: bool = True
    service_discovery_timeout_s: float = 30.0
    device_startup_timeout_s: float = 30.0
    session_startup_timeout_s: float = 10.0
    operation_timeout_s: float = 10.0
    shutdown_timeout_s: float = 10.0

    def __post_init__(self) -> None:
        from .drivers.stimulators.mtms import MtmsSingleChannelSettings

        validated = MtmsSingleChannelSettings(**asdict(self))
        object.__setattr__(self, "allowed_channels", validated.allowed_channels)


@dataclass(frozen=True, slots=True)
class RobotConfig(RobotMotionSettings):
    """Experiment motion parameters; robot identity belongs to HardwareConfig."""


@dataclass(frozen=True, slots=True)
class CenteringConfig:
    initial_step_mm: float = 1.0
    minimum_step_mm: float = 0.5
    step_reduction: float = 0.5
    relative_improvement: float = 0.005
    max_iterations: int = 20
    max_radius_mm: float = 20.0

    def __post_init__(self) -> None:
        if self.initial_step_mm <= 0 or self.minimum_step_mm <= 0:
            raise ValueError("Centering step sizes must be positive.")
        if self.minimum_step_mm > self.initial_step_mm:
            raise ValueError("Minimum centering step cannot exceed the initial step.")
        if not 0 < self.step_reduction < 1:
            raise ValueError("Centering step reduction must be between 0 and 1.")
        if self.relative_improvement < 0 or self.max_iterations < 1:
            raise ValueError("Centering stopping parameters are invalid.")
        if self.max_radius_mm <= 0:
            raise ValueError("Centering radius must be positive.")


@dataclass(frozen=True, slots=True)
class PlanarMappingConfig:
    x_start_mm: float = -90.0
    x_stop_mm: float = 90.0
    x_step_mm: float = 10.0
    y_start_mm: float = -55.0
    y_stop_mm: float = 55.0
    y_step_mm: float = 11.0

    def __post_init__(self) -> None:
        _validate_sweep(self.x_start_mm, self.x_stop_mm, self.x_step_mm, "planar X")
        _validate_sweep(self.y_start_mm, self.y_stop_mm, self.y_step_mm, "planar Y")


@dataclass(frozen=True, slots=True)
class CircularMappingConfig:
    base_start_deg: float = -90.0
    base_stop_deg: float = 90.0
    base_step_deg: float = 5.0
    inclination_start_deg: float = -90.0
    inclination_stop_deg: float = 90.0
    inclination_step_deg: float = 5.0
    center_before_mapping: bool = True

    def __post_init__(self) -> None:
        _validate_sweep(
            self.base_start_deg, self.base_stop_deg, self.base_step_deg, "base angle"
        )
        _validate_sweep(
            self.inclination_start_deg,
            self.inclination_stop_deg,
            self.inclination_step_deg,
            "inclination angle",
        )


@dataclass(frozen=True, slots=True)
class StorageConfig:
    output_directory: str = "data"
    save_waveforms: bool = True

    def __post_init__(self) -> None:
        if not self.output_directory.strip():
            raise ValueError("Storage output directory cannot be empty.")


@dataclass(frozen=True, slots=True)
class ProjectConfig:
    hardware: HardwareConfig
    acquisition: AcquisitionConfig
    pulse: PulseConfig
    mtms: MtmsConfig
    robot: RobotConfig
    centering: CenteringConfig
    planar_mapping: PlanarMappingConfig
    circular_mapping: CircularMappingConfig
    storage: StorageConfig
    angular_calibration: "AngularStageCalibration"
    sensor_calibration: "SensorPoseCalibration"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AxisCalibration:
    center_command_deg: float
    direction: int = 1
    scale: float = 1.0
    minimum_command_deg: float = 0.0
    maximum_command_deg: float = 180.0

    def __post_init__(self) -> None:
        if self.direction not in (-1, 1):
            raise ValueError("Axis direction must be either -1 or 1.")
        if self.scale <= 0:
            raise ValueError("Axis scale must be positive.")
        if self.minimum_command_deg >= self.maximum_command_deg:
            raise ValueError("Axis command limits are invalid.")
        self.validate_command(self.center_command_deg)

    def command_for(self, relative_angle_deg: float) -> float:
        """Convert a logical angle to physical degrees and check the servo limits."""
        command = (
            self.center_command_deg
            + self.direction * self.scale * float(relative_angle_deg)
        )
        self.validate_command(command)
        return command

    def validate_command(self, command_deg: float) -> None:
        if not self.minimum_command_deg <= command_deg <= self.maximum_command_deg:
            raise ValueError(
                f"Motor command {command_deg:.3f} deg is outside the calibrated "
                f"range [{self.minimum_command_deg:.3f}, "
                f"{self.maximum_command_deg:.3f}] deg."
            )


@dataclass(frozen=True, slots=True)
class AngularStageCalibration:
    calibration_id: str
    calibrated_at: str
    description: str
    base: AxisCalibration
    inclination: AxisCalibration

    def commands_for(
        self, base_relative_deg: float, inclination_relative_deg: float
    ) -> tuple[float, float]:
        return (
            self.base.command_for(base_relative_deg),
            self.inclination.command_for(inclination_relative_deg),
        )


@dataclass(frozen=True, slots=True)
class PoseOffset:
    x_mm: float = 0.0
    y_mm: float = 0.0
    z_mm: float = 0.0
    rx_deg: float = 0.0
    ry_deg: float = 0.0
    rz_deg: float = 0.0


@dataclass(frozen=True, slots=True)
class SensorPoseCalibration:
    calibration_id: str
    calibrated_at: str
    sensor_to_tcp: PoseOffset
    coil_center_guess: PoseOffset


DEFAULTS: dict[str, Any] = {
    "hardware": asdict(HardwareConfig()),
    "acquisition": asdict(AcquisitionConfig()),
    "pulse": asdict(PulseConfig()),
    "mtms": asdict(MtmsConfig()),
    "robot": asdict(RobotConfig()),
    "centering": asdict(CenteringConfig()),
    "planar_mapping": asdict(PlanarMappingConfig()),
    "circular_mapping": asdict(CircularMappingConfig()),
    "storage": asdict(StorageConfig()),
}

ENVIRONMENT_FIELDS: dict[str, tuple[str, str]] = {
    "EFIELD_RED_PITAYA_HOST": ("hardware", "red_pitaya_host"),
    "EFIELD_RED_PITAYA_PORT": ("hardware", "red_pitaya_port"),
    "EFIELD_ROBOT_HOST": ("hardware", "robot_host"),
    "EFIELD_ROBOT_TYPE": ("hardware", "robot_type"),
    "EFIELD_ELFIN_USE_NEW_API": ("hardware", "elfin_use_new_api"),
    "EFIELD_STAGE_SERIAL_PORT": ("hardware", "stage_serial_port"),
    "EFIELD_STAGE_SERIAL_BAUD": ("hardware", "stage_serial_baud"),
    "EFIELD_STAGE_SERIAL_TIMEOUT_S": ("hardware", "stage_serial_timeout_s"),
}


def load_project_config(
    config_path: str | Path = "config/default.toml",
    env_path: str | Path = ".env",
    angular_calibration_path: str | Path = "config/calibration/angular_stage.toml",
    sensor_calibration_path: str | Path = "config/calibration/sensor_pose.toml",
    environ: Mapping[str, str] | None = None,
) -> ProjectConfig:
    """Merge defaults, TOML, .env, and the existing environment in increasing priority.

    Values are copied into project objects without writing process environment
    variables. cli.py only selects the operation and input file paths.
    """
    values = _deep_copy(DEFAULTS)
    toml_values = _read_toml(config_path)
    if "hardware" in toml_values:
        raise ValueError(
            "The [hardware] section is not allowed in experiment TOML files. "
            "Set device endpoints in .env or process environment variables."
        )
    _deep_merge(values, toml_values)

    file_environment = _read_env_file(env_path)
    # Use a copy to prioritize the environment without modifying os.environ.
    process_environment = dict(os.environ if environ is None else environ)
    file_environment.update(process_environment)
    _apply_environment(values, file_environment)

    angular_data = _read_toml(angular_calibration_path)
    sensor_data = _read_toml(sensor_calibration_path)
    return _build_project_config(values, angular_data, sensor_data)


def _build_project_config(
    values: Mapping[str, Any],
    angular_data: Mapping[str, Any],
    sensor_data: Mapping[str, Any],
) -> ProjectConfig:
    metadata = angular_data.get("metadata", {})
    angular_calibration = AngularStageCalibration(
        calibration_id=str(metadata.get("calibration_id", "unidentified")),
        calibrated_at=str(metadata.get("calibrated_at", "unknown")),
        description=str(metadata.get("description", "")),
        base=AxisCalibration(**angular_data.get("base", {})),
        inclination=AxisCalibration(**angular_data.get("inclination", {})),
    )

    sensor_metadata = sensor_data.get("metadata", {})
    sensor_calibration = SensorPoseCalibration(
        calibration_id=str(sensor_metadata.get("calibration_id", "unidentified")),
        calibrated_at=str(sensor_metadata.get("calibrated_at", "unknown")),
        sensor_to_tcp=PoseOffset(**sensor_data.get("sensor_to_tcp", {})),
        coil_center_guess=PoseOffset(**sensor_data.get("coil_center_guess", {})),
    )

    return ProjectConfig(
        hardware=HardwareConfig(**values["hardware"]),
        acquisition=AcquisitionConfig(**values["acquisition"]),
        pulse=PulseConfig(**values["pulse"]),
        mtms=MtmsConfig(**values["mtms"]),
        robot=RobotConfig(**values["robot"]),
        centering=CenteringConfig(**values["centering"]),
        planar_mapping=PlanarMappingConfig(**values["planar_mapping"]),
        circular_mapping=CircularMappingConfig(**values["circular_mapping"]),
        storage=StorageConfig(**values["storage"]),
        angular_calibration=angular_calibration,
        sensor_calibration=sensor_calibration,
    )


def _read_toml(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {file_path}")
    with file_path.open("rb") as stream:
        return tomllib.load(stream)


def _read_env_file(path: str | Path) -> dict[str, str]:
    """Read KEY=VALUE as text without running a shell or setting process variables."""
    file_path = Path(path)
    if not file_path.exists():
        return {}
    result: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        file_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ValueError(f"Invalid .env entry at {file_path}:{line_number}.")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        result[key] = value
    return result


def _apply_environment(values: dict[str, Any], environment: Mapping[str, str]) -> None:
    for variable, (section, field) in ENVIRONMENT_FIELDS.items():
        if variable not in environment:
            continue
        current = values[section][field]
        values[section][field] = _convert_value(environment[variable], current)


def _convert_value(raw_value: str, current: Any) -> Any:
    if isinstance(current, bool):
        normalized = raw_value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        raise ValueError(f"Invalid boolean environment value: {raw_value!r}")
    if isinstance(current, int):
        return int(raw_value)
    if isinstance(current, float):
        return float(raw_value)
    return raw_value


def _deep_merge(target: dict[str, Any], source: Mapping[str, Any]) -> None:
    for key, value in source.items():
        if key not in target:
            raise ValueError(f"Unknown configuration section or field: {key}")
        if isinstance(value, Mapping) and isinstance(target[key], dict):
            _deep_merge(target[key], value)
        else:
            target[key] = value


def _deep_copy(source: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in source.items():
        result[key] = _deep_copy(value) if isinstance(value, Mapping) else value
    return result
