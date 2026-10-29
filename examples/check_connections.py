"""Check all configured devices: python examples/check_connections.py.

Reads the existing TOML, .env, and calibration files. No motion, acquisition
arming, capacitor charging, or pulse commands are sent. mTMS is checked by
starting and closing an API device/session. No environment setup is performed.
The Dobot check explicitly enables a disabled, fault-free robot through TCP/IP
and leaves it enabled after closing the sockets. It does not change control mode.
"""

from __future__ import annotations

import socket
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

PROJECT_DIRECTORY = Path(__file__).resolve().parents[1]
if not __package__:
    # Direct file execution normally searches examples/ before site-packages.
    # Prefer this checkout for this process only; no environment or files change.
    sys.path.insert(0, str(PROJECT_DIRECTORY))

from efield_control.configuration import ProjectConfig, load_project_config
from efield_control.drivers.robots.dobot import DobotRobotAdapter, DobotStateError
from efield_control.drivers.robots.elfin import ElfinRobotAdapter
from efield_control.drivers.serial_controller import SerialMotorController
from efield_control.drivers.stimulators.mtms import (
    MtmsSingleChannelClient, MtmsSingleChannelSettings,
)


@dataclass(frozen=True, slots=True)
class ConnectionResult:
    """The check includes closing the connection; detail explains any failure."""

    device: str
    success: bool
    detail: str


def _require_endpoint(value: str, variable: str) -> str:
    if not value.strip():
        raise ValueError(f"{variable} is not configured in .env.")
    return value


def _with_cleanup(check: Callable[[], str], close: Callable[[], None]) -> str:
    """Attempt cleanup even when connection or validation fails."""
    failure: Exception | None = None
    detail = ""
    try:
        detail = check()
    except Exception as error:
        failure = error
    finally:
        try:
            close()
        except Exception as error:
            if failure is None:
                raise RuntimeError(f"Check succeeded, but cleanup failed: {error}") from error
            raise RuntimeError(f"{failure}; cleanup also failed: {error}") from failure
    if failure is not None:
        raise failure
    return detail


def check_robot(config: ProjectConfig) -> str:
    """Open the selected robot connection and request its actual TCP pose."""
    hardware = config.hardware
    host = _require_endpoint(hardware.robot_host, "EFIELD_ROBOT_HOST")
    settings = asdict(config.robot)
    if hardware.robot_type == "dobot":
        robot = DobotRobotAdapter(host, **settings)
    else:
        robot = ElfinRobotAdapter(host, **settings, use_new_api=hardware.elfin_use_new_api)

    def check() -> str:
        if hardware.robot_type == "dobot":
            # Keep communication open long enough to read alarms when not ready.
            robot.connect(require_ready=False)
        else:
            robot.connect()
        try:
            enabled_now = hardware.robot_type == "dobot" and robot.enable()
            pose = robot.current_pose()
        except DobotStateError as error:
            try:
                alarms = robot.get_error_id()
                detail = f"GetErrorID={alarms}"
            except Exception as alarm_error:
                detail = f"Alarm query failed: {alarm_error}"
            raise RuntimeError(
                f"TCP connections and feedback OK; controller not ready: {error} {detail}"
            ) from error
        activation = "enabled via TCP/IP; " if enabled_now else ""
        return (f"{hardware.robot_type}: {activation}TCP pose received "
                f"(X={pose.x_mm:g}, Y={pose.y_mm:g}, Z={pose.z_mm:g} mm)")

    return _with_cleanup(check, robot.disconnect)


def check_microcontroller(config: ProjectConfig) -> str:
    """Require PONG from the Arduino stage; never send CENTER, MOVEABS, or FIRE."""
    hardware = config.hardware
    port = _require_endpoint(hardware.stage_serial_port, "EFIELD_STAGE_SERIAL_PORT")
    controller = SerialMotorController(
        port=port,
        baudrate=hardware.stage_serial_baud,
        timeout_s=hardware.stage_serial_timeout_s,
        movement_settling_s=config.robot.settling_time_s,
    )

    def check() -> str:
        controller.ping()
        return "PING answered with PONG"

    return _with_cleanup(check, controller.close)


def check_red_pitaya(config: ProjectConfig) -> str:
    """Request SCPI identification without changing acquisition or digital outputs."""
    hardware = config.hardware
    host = _require_endpoint(hardware.red_pitaya_host, "EFIELD_RED_PITAYA_HOST")
    timeout_s = config.robot.socket_timeout_s
    # A direct transport check avoids arming acquisition and detects EOF explicitly.
    with socket.create_connection((host, hardware.red_pitaya_port), timeout=timeout_s) as client:
        deadline = time.monotonic() + timeout_s
        client.sendall(b"*IDN?\r\n")
        response = bytearray()
        while not response.endswith(b"\r\n"):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Timed out waiting for Red Pitaya SCPI identification.")
            client.settimeout(remaining)
            chunk = client.recv(4096)
            if not chunk:
                raise ConnectionError("Red Pitaya closed the connection before responding.")
            response.extend(chunk)
            if len(response) > 65536:
                raise RuntimeError("SCPI identification response is too long.")
        identity = response.decode("utf-8").strip()
        if not identity or "error" in identity.lower() or "unknown command" in identity.lower():
            raise RuntimeError(f"Invalid SCPI identification response: {identity!r}")
        return f"SCPI identification: {identity}"


def check_mtms(config: ProjectConfig) -> str:
    """Test API initialization and session startup, without charging or firing."""
    client = MtmsSingleChannelClient(MtmsSingleChannelSettings(**asdict(config.mtms)))

    def check() -> str:
        client.connect()
        return "Device Operational and session Started confirmed; shutdown confirmed"

    return _with_cleanup(check, client.close)


def check_connections(
    config: ProjectConfig,
    on_result: Callable[[ConnectionResult], None] | None = None,
) -> list[ConnectionResult]:
    """Always try all four devices, regardless of the configured pulse source."""
    results = []
    for name, check in (
        ("Robot", check_robot),
        ("Microcontroller", check_microcontroller),
        ("Red Pitaya", check_red_pitaya),
        ("mTMS", check_mtms),
    ):
        try:
            results.append(ConnectionResult(name, True, check(config)))
        except Exception as error:
            results.append(ConnectionResult(name, False, f"{type(error).__name__}: {error}"))
        if on_result is not None:
            on_result(results[-1])
    return results


def main() -> int:
    try:
        # Resolve files from this checkout even when the IDE uses another cwd.
        config = load_project_config(
            config_path=PROJECT_DIRECTORY / "config/default.toml",
            env_path=PROJECT_DIRECTORY / ".env",
            angular_calibration_path=PROJECT_DIRECTORY / "config/calibration/angular_stage.toml",
            sensor_calibration_path=PROJECT_DIRECTORY / "config/calibration/sensor_pose.toml",
        )
    except (OSError, ValueError) as error:
        print(f"Configuration error: {error}")
        return 2
    def report(result: ConnectionResult) -> None:
        status = "OK" if result.success else "FAIL"
        print(f"[{status:4}] {result.device}: {result.detail}")
    results = check_connections(config, on_result=report)
    successful = [result.device for result in results if result.success]
    print(f"\nDevices that passed: {', '.join(successful) or 'none'}")
    return 0 if all(result.success for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
