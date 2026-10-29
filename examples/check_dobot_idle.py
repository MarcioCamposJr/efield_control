"""Compare Dobot movement after connecting with movement after an idle wait.

Run separately with --wait-s 0 and --wait-s 20. Moves by --dx-mm in the active
Cartesian X axis, then returns only if the outbound movement succeeds. Requires
an already enabled robot and clear space for both movements. No pulses or
acquisition; reads this checkout's existing configuration and calibration files.
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from dataclasses import asdict
from pathlib import Path

PROJECT_DIRECTORY = Path(__file__).resolve().parents[1]
if not __package__:
    sys.path.insert(0, str(PROJECT_DIRECTORY))

from efield_control.configuration import load_project_config
from efield_control.drivers.robots.dobot import DobotRobotAdapter


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wait-s", type=float, default=0.0)
    parser.add_argument("--dx-mm", type=float, required=True)
    parser.add_argument("--confirm-hardware", choices=["MOVE_ONLY"], required=True)
    args = parser.parse_args(argv)
    if not math.isfinite(args.wait_s) or args.wait_s < 0:
        parser.error("--wait-s must be finite and non-negative.")
    if not math.isfinite(args.dx_mm):
        parser.error("--dx-mm must be finite.")
    config = load_project_config(
        config_path=PROJECT_DIRECTORY / "config/default.toml",
        env_path=PROJECT_DIRECTORY / ".env",
        angular_calibration_path=PROJECT_DIRECTORY / "config/calibration/angular_stage.toml",
        sensor_calibration_path=PROJECT_DIRECTORY / "config/calibration/sensor_pose.toml",
    )
    if config.hardware.robot_type != "dobot" or not config.hardware.robot_host.strip():
        parser.error("Configure a Dobot and its host in .env first.")
    if abs(args.dx_mm) <= config.robot.position_tolerance_mm:
        parser.error("--dx-mm must exceed the position tolerance to send a movement.")

    robot = DobotRobotAdapter(config.hardware.robot_host, **asdict(config.robot))
    print(f"Python: {sys.executable}; venv={sys.prefix != sys.base_prefix}", flush=True)
    started = time.monotonic()
    stage = "connect"
    try:
        robot.connect()
        origin = robot.current_pose()
        target = origin.translated(dx_mm=args.dx_mm)
        print(f"Connected: origin={origin.as_list()}; target={target.as_list()}", flush=True)
        stage = "idle wait"
        print(f"Waiting {args.wait_s:g} s without movement commands...", flush=True)
        time.sleep(args.wait_s)
        stage = "outbound movement"
        print(f"[{time.monotonic() - started:.3f} s] Sending outbound movement", flush=True)
        robot.move_to(target)
        print(f"[{time.monotonic() - started:.3f} s] Outbound confirmed", flush=True)
        stage = "return movement"
        robot.move_to(origin)
        print(f"[{time.monotonic() - started:.3f} s] Return confirmed; test passed", flush=True)
        return 0
    except BaseException as error:
        print(
            f"[{time.monotonic() - started:.3f} s] Failed during {stage}: "
            f"{type(error).__name__}: {error}",
            flush=True,
        )
        raise
    finally:
        robot.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
