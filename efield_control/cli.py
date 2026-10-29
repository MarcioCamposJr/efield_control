"""Experiment entry point: python -m efield_control.cli <command>.

main reads arguments and files; run_center/run_planar/run_circular assemble
the drivers, execute the experiment, and save results. run_pulse_test operates
only the selected pulse source without acquisition or motion. The algorithms can
also be used from custom scripts without going through this CLI.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Iterable
from contextlib import ExitStack
from dataclasses import asdict
from typing import Any

from .acquisition import AcquisitionService, AcquisitionSettings
from .calibration import CalibratedAngularPositioner, calibrated_center_guess
from .centering import CenteringSettings, SensorCentering
from .configuration import ProjectConfig, load_project_config
from .domain import Measurement
from .drivers.red_pitaya import (
    RedPitayaAcquisition,
    RedPitayaDigitalPulse,
    RedPitayaSettings,
)
from .drivers.red_pitaya.scpi import scpi
from .drivers.robots.dobot import DobotRobotAdapter
from .drivers.robots.elfin import ElfinRobotAdapter
from .drivers.serial_controller import SerialMotorController
from .drivers.stimulators.mtms import (
    MtmsApiPulse,
    MtmsSingleChannelClient,
    MtmsSingleChannelSettings,
)
from .mapping import CircularMapping, PlanarMapping, circular_serpentine, planar_serpentine
from .ports import CartesianRobot
from .storage import CsvRunStore, MeasurementLocation
from .workflows import CenterSensorWorkflow


HARDWARE_CONFIRMATION = "MOVE_AND_FIRE"


def inclusive_range(start: float, stop: float, step: float) -> tuple[float, ...]:
    if step == 0 or (stop - start) * step < 0:
        raise ValueError("Invalid range: check start, stop, and step values.")
    values: list[float] = []
    current = start
    compare = (lambda value: value <= stop + 1e-9) if step > 0 else (
        lambda value: value >= stop - 1e-9
    )
    while compare(current):
        values.append(round(current, 10))
        if len(values) > 100_000:
            raise ValueError("The range exceeds 100,000 points.")
        current += step
    return tuple(values)


def _require_confirmation(args: argparse.Namespace) -> None:
    """Require MOVE_AND_FIRE to authorize the entire operation with real hardware.

    This option does not test equipment or validate physical limits. It blocks
    motion and firing when explicit authorization is missing.
    """
    if args.confirm_hardware != HARDWARE_CONFIRMATION:
        raise SystemExit(
            "Operation blocked. Review all limits and use "
            f"--confirm-hardware {HARDWARE_CONFIRMATION} to authorize "
            "real motion and pulse generation."
        )


def _require_value(args: argparse.Namespace, attribute: str, source: str) -> Any:
    value = getattr(args, attribute, None)
    if value in (None, ""):
        raise SystemExit(f"Missing {source}. Set it in the hardware .env file.")
    return value


def _acquisition(args: argparse.Namespace) -> RedPitayaAcquisition:
    """Create the CH1/CH2 acquisition device and open its Red Pitaya SCPI connection."""
    host = _require_value(args, "rp_ip", "Red Pitaya host")
    return RedPitayaAcquisition(
        RedPitayaSettings(
            host=host,
            port=args.rp_port,
            decimation=args.decimation,
            trigger_source=args.trigger_source,
            trigger_delay=args.trigger_delay,
            high_voltage=args.high_voltage,
        )
    )


def _service(
    args: argparse.Namespace,
    acquisition: RedPitayaAcquisition,
    serial_controller: SerialMotorController | None,
    mtms_pulse: MtmsApiPulse | None = None,
) -> AcquisitionService:
    """Combine Red Pitaya acquisition with the selected pulse source."""
    if args.pulse_source == "serial":
        if serial_controller is None:
            raise ValueError("The serial pulse source requires a serial port.")
        pulse = serial_controller
    elif args.pulse_source == "redpitaya":
        # Acquisition and digital pulses share the same Red Pitaya SCPI connection.
        pulse = RedPitayaDigitalPulse(
            acquisition.client,
            pin=args.pulse_pin,
            pulse_s=args.pulse_duration,
        )
    else:
        if mtms_pulse is None:
            raise RuntimeError("The mTMS API pulse source is not connected.")
        pulse = mtms_pulse
    return AcquisitionService(
        acquisition,
        pulse,
        AcquisitionSettings(
            repetitions=args.repetitions,
            interval_s=args.repetition_interval,
            trigger_timeout_s=args.trigger_timeout,
            buffer_timeout_s=args.buffer_timeout,
        ),
    )


def _serial_if_requested(args: argparse.Namespace) -> SerialMotorController | None:
    """Open serial communication for Arduino firing in center/planar if selected."""
    if args.pulse_source != "serial":
        return None
    port = _require_value(args, "serial_port", "stage serial port")
    controller = SerialMotorController(
        port=port,
        baudrate=args.serial_baud,
        timeout_s=args.serial_timeout,
        movement_settling_s=args.settling_time,
    )
    controller.ping()
    return controller


def _mtms_if_requested(args: argparse.Namespace) -> MtmsApiPulse | None:
    """Create the mTMS client and start its session only when mtms_api is selected."""
    if args.pulse_source != "mtms_api":
        return None
    client = MtmsSingleChannelClient(
        MtmsSingleChannelSettings(
            channel=args.mtms_channel,
            allowed_channels=tuple(args.mtms_allowed_channels),
            target_voltage_v=args.mtms_target_voltage,
            maximum_target_voltage_v=args.mtms_maximum_target_voltage,
            reverse_polarity=args.mtms_reverse_polarity,
            trigger_out_port=args.mtms_trigger_out_port,
            trigger_out_duration_us=args.mtms_trigger_out_duration,
            schedule_lead_s=args.mtms_schedule_lead,
            minimum_inter_pulse_interval_s=args.mtms_minimum_interval,
            discharge_after_pulse=args.mtms_discharge_after_pulse,
            service_discovery_timeout_s=args.mtms_service_discovery_timeout,
            device_startup_timeout_s=args.mtms_device_startup_timeout,
            session_startup_timeout_s=args.mtms_session_startup_timeout,
            operation_timeout_s=args.mtms_operation_timeout,
            shutdown_timeout_s=args.mtms_shutdown_timeout,
        )
    )
    pulse = MtmsApiPulse(client)
    pulse.connect()
    return pulse


def _new_store(args: argparse.Namespace, run_name: str) -> CsvRunStore:
    """Create the results directory and record the parameters for this run."""
    store = CsvRunStore(
        args.output,
        run_name,
        save_waveforms=args.save_waveforms,
    )
    config: ProjectConfig = args.project_config
    effective = {
        key: value
        for key, value in vars(args).items()
        if key not in {"handler", "project_config"} and not callable(value)
    }
    store.write_json(
        "resolved_config.json",
        {"loaded_config": config.to_dict(), "effective_settings": effective},
    )
    return store


def _robot(args: argparse.Namespace) -> CartesianRobot:
    """Select a robot adapter without opening its connection or changing host settings."""
    host = _require_value(args, "robot_ip", "robot host")
    config = args.project_config.robot
    hardware = args.project_config.hardware
    common = dict(
        movement_timeout_s=args.movement_timeout,
        settling_time_s=args.settling_time,
        speed_percent=args.robot_speed_percent,
        socket_timeout_s=config.socket_timeout_s,
        position_tolerance_mm=config.position_tolerance_mm,
        orientation_tolerance_deg=config.orientation_tolerance_deg,
    )
    if hardware.robot_type == "dobot":
        return DobotRobotAdapter(host, **common)
    if hardware.robot_type == "elfin":
        return ElfinRobotAdapter(host, **common, use_new_api=hardware.elfin_use_new_api)
    raise ValueError("Robot type must be 'elfin' or 'dobot'.")


def _print_measurement(point: str, measurement: Measurement) -> None:
    print(
        f"[{point}] CH1 p-p={measurement.p2p_ch1_v:.6g} V | "
        f"CH2 p-p={measurement.p2p_ch2_v:.6g} V | "
        f"M={measurement.magnitude_v:.6g} V | repetitions={measurement.repetitions}",
        flush=True,
    )


def run_center(args: argparse.Namespace) -> int:
    """Center the sensor with the selected robot, measuring suggested positions."""
    _require_confirmation(args)
    algorithm = SensorCentering(
        CenteringSettings(
            initial_step_mm=args.initial_step,
            minimum_step_mm=args.minimum_step,
            step_reduction=args.step_reduction,
            relative_improvement=args.relative_improvement,
            max_iterations=args.max_iterations,
            max_radius_mm=args.max_radius,
        )
    )
    _validate_runtime_settings(args)
    robot = _robot(args)
    acquisition = _acquisition(args)
    serial_controller = None
    mtms_pulse = None
    robot_connected = False
    store = _new_store(args, "centering")
    try:
        # Connect the actuators and assemble acquisition before starting the search.
        robot.connect()
        robot_connected = True
        serial_controller = _serial_if_requested(args)
        mtms_pulse = _mtms_if_requested(args)
        service = _service(args, acquisition, serial_controller, mtms_pulse)
        def save_sample(sample) -> None:
            # The algorithm reports each sample; the CLI handles writing it to disk.
            store.append(
                MeasurementLocation(
                    mode="centering",
                    label=f"{sample.iteration}:{sample.label}",
                    x_mm=sample.x_mm,
                    y_mm=sample.y_mm,
                ),
                sample.measurement,
            )
            _print_measurement(
                f"center {sample.iteration}:{sample.label} "
                f"X={sample.x_mm:.3f} Y={sample.y_mm:.3f} mm",
                sample.measurement,
            )

        origin = calibrated_center_guess(
            robot.current_pose(), args.project_config.sensor_calibration
        )
        result = CenterSensorWorkflow(robot, service, algorithm).run(
            origin=origin,
            observer=save_sample,
        )
        print(
            f"Center found: X={result.x_mm:.3f} mm, "
            f"Y={result.y_mm:.3f} mm, M={result.measurement.magnitude_v:.6f} V"
        )
        print(f"Results: {store.run_directory}")
        return 0
    except BaseException:
        if robot_connected:
            try:
                robot.stop()
            except Exception:
                pass
        raise
    finally:
        # Close connections even when the experiment fails or is interrupted.
        if robot_connected:
            robot.disconnect()
        try:
            if mtms_pulse is not None:
                mtms_pulse.close()
        finally:
            try:
                acquisition.close()
            finally:
                if serial_controller is not None:
                    serial_controller.close()


def run_pulse_test(args: argparse.Namespace) -> int:
    """Send a finite pulse sequence without connecting a robot or arming acquisition."""
    _require_confirmation(args)
    config: ProjectConfig = args.project_config
    test = config.pulse_test
    source = config.pulse.source
    if source == "mtms_api":
        if test.count > 1 and test.interval_s < config.mtms.minimum_inter_pulse_interval_s:
            raise ValueError(
                "pulse_test.interval_s must be at least "
                "mtms.minimum_inter_pulse_interval_s for multiple pulses."
            )
        MtmsSingleChannelClient.validate_environment()
    print(f"Pulse test: source={source}, count={test.count}, interval={test.interval_s:g} s")
    if source == "mtms_api":
        print(f"mTMS channel={config.mtms.channel}, target={config.mtms.target_voltage_v:g} V")

    with ExitStack() as cleanup:
        if source == "serial":
            pulse = SerialMotorController(
                port=_require_value(args, "serial_port", "stage serial port"),
                baudrate=config.hardware.stage_serial_baud,
                timeout_s=config.hardware.stage_serial_timeout_s,
            )
            cleanup.callback(pulse.close)
            try:
                pulse.ping()
            except TimeoutError:
                # Opening USB serial can reboot the board and lose the first PING.
                pulse.ping()
        elif source == "redpitaya":
            client = scpi(
                _require_value(args, "rp_ip", "Red Pitaya host"),
                timeout=config.robot.socket_timeout_s,
                port=config.hardware.red_pitaya_port,
            )
            cleanup.callback(client.close)
            pulse = RedPitayaDigitalPulse(
                client, pin=config.pulse.pin, pulse_s=config.pulse.duration_s,
            )
        else:
            client = MtmsSingleChannelClient(MtmsSingleChannelSettings(**asdict(config.mtms)))
            # Register before startup so cleanup is attempted even on partial failure.
            cleanup.callback(client.close)
            pulse = MtmsApiPulse(client)
            pulse.connect()

        for index in range(test.count):
            if index:
                time.sleep(test.interval_s)
            pulse.fire()
            print(f"Pulse command {index + 1}/{test.count} completed.", flush=True)
    print("Pulse test completed; connection closed.")
    return 0


def run_planar(args: argparse.Namespace) -> int:
    """Traverse X/Y offsets with the selected robot and save each measurement."""
    _require_confirmation(args)
    _validate_runtime_settings(args)
    points = tuple(
        planar_serpentine(
            inclusive_range(args.x_start, args.x_stop, args.x_step),
            inclusive_range(args.y_start, args.y_stop, args.y_step),
        )
    )
    robot = _robot(args)
    acquisition = _acquisition(args)
    serial_controller = None
    mtms_pulse = None
    robot_connected = False
    store = _new_store(args, "planar")
    try:
        robot.connect()
        robot_connected = True
        serial_controller = _serial_if_requested(args)
        mtms_pulse = _mtms_if_requested(args)
        service = _service(args, acquisition, serial_controller, mtms_pulse)
        origin = robot.current_pose()
        # The map yields one point at a time; this loop saves each result.
        for point, pose, measurement in PlanarMapping(robot, service).run(origin, points):
            store.append(
                MeasurementLocation(
                    mode="planar",
                    label=f"{point.row},{point.column}",
                    x_mm=pose.x_mm,
                    y_mm=pose.y_mm,
                    z_mm=pose.z_mm,
                ),
                measurement,
            )
            _print_measurement(
                f"planar {point.row},{point.column} "
                f"X={pose.x_mm:.3f} Y={pose.y_mm:.3f} Z={pose.z_mm:.3f} mm",
                measurement,
            )
        print(f"Planar map completed: {store.run_directory}")
        return 0
    except BaseException:
        if robot_connected:
            try:
                robot.stop()
            except Exception:
                pass
        raise
    finally:
        if robot_connected:
            robot.disconnect()
        try:
            if mtms_pulse is not None:
                mtms_pulse.close()
        finally:
            try:
                acquisition.close()
            finally:
                if serial_controller is not None:
                    serial_controller.close()


def run_circular(args: argparse.Namespace) -> int:
    """Traverse Arduino stage angles and save the measurement at each point."""
    _require_confirmation(args)
    _validate_runtime_settings(args)
    config: ProjectConfig = args.project_config
    points = tuple(
        circular_serpentine(
            inclusive_range(args.base_start, args.base_stop, args.base_step),
            inclusive_range(
                args.inclination_start,
                args.inclination_stop,
                args.inclination_step,
            ),
        )
    )
    for point in points:
        # Validate the full calibrated path before opening connections or moving servos.
        config.angular_calibration.commands_for(
            point.base_deg, point.inclination_deg
        )

    acquisition = _acquisition(args)
    controller = None
    mtms_pulse = None
    store = _new_store(args, "circular")
    try:
        # Serial is needed for the servos even when mTMS generates the pulse.
        controller = SerialMotorController(
            port=_require_value(args, "serial_port", "stage serial port"),
            baudrate=args.serial_baud,
            timeout_s=args.serial_timeout,
            movement_settling_s=args.settling_time,
        )
        controller.ping()
        positioner = CalibratedAngularPositioner(
            controller, config.angular_calibration
        )
        if args.center_first:
            positioner.center()
        mtms_pulse = _mtms_if_requested(args)
        service = _service(args, acquisition, controller, mtms_pulse)
        for point, measurement in CircularMapping(positioner, service).run(points):
            store.append(
                MeasurementLocation(
                    mode="circular",
                    label=f"{point.row},{point.column}",
                    base_deg=point.base_deg,
                    inclination_deg=point.inclination_deg,
                ),
                measurement,
            )
            _print_measurement(
                f"circular {point.row},{point.column} "
                f"base={point.base_deg:.3f} inclination={point.inclination_deg:.3f} deg",
                measurement,
            )
        print(f"Circular map completed: {store.run_directory}")
        return 0
    finally:
        try:
            if mtms_pulse is not None:
                mtms_pulse.close()
        finally:
            try:
                acquisition.close()
            finally:
                if controller is not None:
                    controller.close()


def show_config(args: argparse.Namespace) -> int:
    """Display the resolved configuration as JSON without connecting to equipment."""
    print(json.dumps(args.project_config.to_dict(), indent=2, sort_keys=True))
    return 0


def _validate_runtime_settings(args: argparse.Namespace) -> None:
    """Validate parameters and required imports without preparing the host environment."""
    if args.pulse_source == "mtms_api":
        MtmsSingleChannelSettings(
            channel=args.mtms_channel,
            allowed_channels=tuple(args.mtms_allowed_channels),
            target_voltage_v=args.mtms_target_voltage,
            maximum_target_voltage_v=args.mtms_maximum_target_voltage,
            reverse_polarity=args.mtms_reverse_polarity,
            trigger_out_port=args.mtms_trigger_out_port,
            trigger_out_duration_us=args.mtms_trigger_out_duration,
            schedule_lead_s=args.mtms_schedule_lead,
            minimum_inter_pulse_interval_s=args.mtms_minimum_interval,
            discharge_after_pulse=args.mtms_discharge_after_pulse,
            service_discovery_timeout_s=args.mtms_service_discovery_timeout,
            device_startup_timeout_s=args.mtms_device_startup_timeout,
            session_startup_timeout_s=args.mtms_session_startup_timeout,
            operation_timeout_s=args.mtms_operation_timeout,
            shutdown_timeout_s=args.mtms_shutdown_timeout,
        )
        MtmsSingleChannelClient.validate_environment()
    AcquisitionSettings(
        repetitions=args.repetitions,
        interval_s=args.repetition_interval,
        trigger_timeout_s=args.trigger_timeout,
        buffer_timeout_s=args.buffer_timeout,
    )
    if args.decimation <= 0:
        raise ValueError("Decimation must be positive.")
    if not 1 <= args.rp_port <= 65535:
        raise ValueError("Red Pitaya port must be between 1 and 65535.")
    if args.pulse_duration <= 0:
        raise ValueError("Pulse duration must be positive.")
    if args.serial_baud <= 0 or args.serial_timeout < 0:
        raise ValueError("Serial baud rate and timeout are invalid.")


def build_parser() -> argparse.ArgumentParser:
    """Choose an operation and input files; experiment parameters come from TOML."""
    parser = argparse.ArgumentParser(prog="efield-control")
    parser.add_argument("--config", default="config/default.toml",
                        help="Experiment TOML file")
    parser.add_argument("--env-file", default=".env",
                        help="Hardware identity and endpoints file")
    parser.add_argument("--angular-calibration", default="config/calibration/angular_stage.toml")
    parser.add_argument("--sensor-calibration", default="config/calibration/sensor_pose.toml")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("show-config", help="Print the resolved configuration").set_defaults(
        handler=show_config
    )
    for name, description, handler in (
        ("center", "Center the sensor with the configured robot", run_center),
        ("planar", "Run the configured planar map", run_planar),
        ("circular", "Run the configured angular stage map", run_circular),
        ("pulse-test", "Test the configured stimulator without motion or acquisition", run_pulse_test),
    ):
        command = commands.add_parser(name, help=description)
        command.add_argument(
            "--confirm-hardware", metavar="MOVE_AND_FIRE",
            help="Authorize real motion and stimulation for the whole experiment",
        )
        command.set_defaults(handler=handler)
    return parser


def apply_project_config(args: argparse.Namespace, config: ProjectConfig) -> None:
    """Populate runtime settings from resolved files, without CLI parameter overrides."""
    values = {
        "rp_ip": config.hardware.red_pitaya_host,
        "rp_port": config.hardware.red_pitaya_port,
        "robot_ip": config.hardware.robot_host,
        "robot_speed_percent": config.robot.speed_percent,
        "serial_port": config.hardware.stage_serial_port,
        "serial_baud": config.hardware.stage_serial_baud,
        "serial_timeout": config.hardware.stage_serial_timeout_s,
        "decimation": config.acquisition.decimation,
        "trigger_source": config.acquisition.trigger_source,
        "trigger_delay": config.acquisition.trigger_delay,
        "trigger_timeout": config.acquisition.trigger_timeout_s,
        "buffer_timeout": config.acquisition.buffer_timeout_s,
        "repetitions": config.acquisition.repetitions,
        "repetition_interval": config.acquisition.repetition_interval_s,
        "high_voltage": config.acquisition.high_voltage,
        "pulse_source": config.pulse.source,
        "pulse_pin": config.pulse.pin,
        "pulse_duration": config.pulse.duration_s,
        "mtms_channel": config.mtms.channel,
        "mtms_allowed_channels": config.mtms.allowed_channels,
        "mtms_target_voltage": config.mtms.target_voltage_v,
        "mtms_maximum_target_voltage": config.mtms.maximum_target_voltage_v,
        "mtms_reverse_polarity": config.mtms.reverse_polarity,
        "mtms_trigger_out_port": config.mtms.trigger_out_port,
        "mtms_trigger_out_duration": config.mtms.trigger_out_duration_us,
        "mtms_schedule_lead": config.mtms.schedule_lead_s,
        "mtms_minimum_interval": config.mtms.minimum_inter_pulse_interval_s,
        "mtms_discharge_after_pulse": config.mtms.discharge_after_pulse,
        "mtms_service_discovery_timeout": config.mtms.service_discovery_timeout_s,
        "mtms_device_startup_timeout": config.mtms.device_startup_timeout_s,
        "mtms_session_startup_timeout": config.mtms.session_startup_timeout_s,
        "mtms_operation_timeout": config.mtms.operation_timeout_s,
        "mtms_shutdown_timeout": config.mtms.shutdown_timeout_s,
        "movement_timeout": config.robot.movement_timeout_s,
        "settling_time": config.robot.settling_time_s,
        "initial_step": config.centering.initial_step_mm,
        "minimum_step": config.centering.minimum_step_mm,
        "step_reduction": config.centering.step_reduction,
        "relative_improvement": config.centering.relative_improvement,
        "max_iterations": config.centering.max_iterations,
        "max_radius": config.centering.max_radius_mm,
        "x_start": config.planar_mapping.x_start_mm,
        "x_stop": config.planar_mapping.x_stop_mm,
        "x_step": config.planar_mapping.x_step_mm,
        "y_start": config.planar_mapping.y_start_mm,
        "y_stop": config.planar_mapping.y_stop_mm,
        "y_step": config.planar_mapping.y_step_mm,
        "base_start": config.circular_mapping.base_start_deg,
        "base_stop": config.circular_mapping.base_stop_deg,
        "base_step": config.circular_mapping.base_step_deg,
        "inclination_start": config.circular_mapping.inclination_start_deg,
        "inclination_stop": config.circular_mapping.inclination_stop_deg,
        "inclination_step": config.circular_mapping.inclination_step_deg,
        "center_first": config.circular_mapping.center_before_mapping,
        "output": config.storage.output_directory,
        "save_waveforms": config.storage.save_waveforms,
    }
    for attribute, value in values.items():
        setattr(args, attribute, value)


def main(argv: Iterable[str] | None = None) -> int:
    """Shared entry point for the Python module and the efield-control executable.

    argv allows calling main(["show-config"]) from a script. When omitted,
    argparse uses terminal arguments; a subcommand is required.
    """
    args = build_parser().parse_args(argv)
    try:
        config = load_project_config(
            config_path=args.config,
            env_path=args.env_file,
            angular_calibration_path=args.angular_calibration,
            sensor_calibration_path=args.sensor_calibration,
        )
        args.project_config = config
        apply_project_config(args, config)
        # The selected handler owns device setup and operation.
        return int(args.handler(args))
    except KeyboardInterrupt:
        print("Operation interrupted by the user.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
