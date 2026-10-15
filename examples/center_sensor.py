"""Center the real sensor using the configured robot, Red Pitaya, and pulse source.

Run: python examples/center_sensor.py --confirm-hardware MOVE_AND_FIRE

This example moves real hardware and generates pulses. It reads the checkout's TOML,
.env, and calibration files and saves measurements through the shared center
command. Without the confirmation option, no hardware connections are opened.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path

PROJECT_DIRECTORY = Path(__file__).resolve().parents[1]
if not __package__:
    # Use this checkout when running the file directly, without installing it.
    sys.path.insert(0, str(PROJECT_DIRECTORY))

from efield_control.cli import main as run_experiment


def main(argv: Iterable[str] | None = None) -> int:
    """Run the real centering workflow with files resolved relative to this checkout."""
    # Reuse driver selection, calibration, acquisition, search, result storage,
    # and connection cleanup from the real experiment entry point.
    return run_experiment([
        "--config", str(PROJECT_DIRECTORY / "config/default.toml"),
        "--env-file", str(PROJECT_DIRECTORY / ".env"),
        "--angular-calibration", str(PROJECT_DIRECTORY / "config/calibration/angular_stage.toml"),
        "--sensor-calibration", str(PROJECT_DIRECTORY / "config/calibration/sensor_pose.toml"),
        "center",
        *(sys.argv[1:] if argv is None else argv),
    ])


if __name__ == "__main__":
    raise SystemExit(main())
