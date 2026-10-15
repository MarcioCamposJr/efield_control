"""Acquire a real planar map without running sensor centering.

Run: python examples/acquire_planar.py --confirm-hardware MOVE_AND_FIRE

Position the sensor before starting: the current robot TCP pose is the map
origin. [planar_mapping] defines X/Y offsets; Z and orientation stay fixed.
The checkout's .env, TOML, and calibration files configure the shared planar
command, including the pulse source and result storage.
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
    """Measure the configured serpentine grid from the current robot pose."""
    return run_experiment([
        "--config", str(PROJECT_DIRECTORY / "config/default.toml"),
        "--env-file", str(PROJECT_DIRECTORY / ".env"),
        "--angular-calibration", str(PROJECT_DIRECTORY / "config/calibration/angular_stage.toml"),
        "--sensor-calibration", str(PROJECT_DIRECTORY / "config/calibration/sensor_pose.toml"),
        "planar",
        *(sys.argv[1:] if argv is None else argv),
    ])


if __name__ == "__main__":
    raise SystemExit(main())
