"""Send test pulses without robot movement, centering, or sensor acquisition.

Run: python examples/pulse_stimulator.py --confirm-hardware MOVE_AND_FIRE

[pulse].source selects serial, redpitaya, or mtms_api. [pulse_test] sets the
count and pause after each completed command. Only mtms_api controls charging
and voltage through [mtms]; electrical trigger sources require the stimulator
to be prepared separately. No waveform is acquired to verify physical pulses.
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
    """Run only the configured pulse source and close it on completion or failure."""
    return run_experiment([
        "--config", str(PROJECT_DIRECTORY / "config/default.toml"),
        "--env-file", str(PROJECT_DIRECTORY / ".env"),
        "--angular-calibration", str(PROJECT_DIRECTORY / "config/calibration/angular_stage.toml"),
        "--sensor-calibration", str(PROJECT_DIRECTORY / "config/calibration/sensor_pose.toml"),
        "pulse-test",
        *(sys.argv[1:] if argv is None else argv),
    ])


if __name__ == "__main__":
    raise SystemExit(main())
