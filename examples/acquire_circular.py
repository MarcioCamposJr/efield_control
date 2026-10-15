"""Acquire a real circular map without running sensor centering.

Run: python examples/acquire_circular.py --confirm-hardware MOVE_AND_FIRE

Position the sensor before starting. [circular_mapping] defines the logical
base/inclination grid; angular_stage.toml converts it to servo commands.
center_before_mapping optionally moves the stage to calibrated angular zero;
it does not search for the sensor's signal maximum. This example uses the
checkout's configuration files and the shared circular acquisition command.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path

PROJECT_DIRECTORY = Path(__file__).resolve().parents[1]
if not __package__:
    sys.path.insert(0, str(PROJECT_DIRECTORY))

from efield_control.cli import main as run_experiment


def main(argv: Iterable[str] | None = None) -> int:
    """Measure the configured angular grid with the calibrated serial stage."""
    return run_experiment([
        "--config", str(PROJECT_DIRECTORY / "config/default.toml"),
        "--env-file", str(PROJECT_DIRECTORY / ".env"),
        "--angular-calibration", str(PROJECT_DIRECTORY / "config/calibration/angular_stage.toml"),
        "--sensor-calibration", str(PROJECT_DIRECTORY / "config/calibration/sensor_pose.toml"),
        "circular",
        *(sys.argv[1:] if argv is None else argv),
    ])


if __name__ == "__main__":
    raise SystemExit(main())
