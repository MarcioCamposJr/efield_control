"""Plot a circular run: python examples/plot_circular.py data/circular_TIMESTAMP.

Reads summary.csv and saves circular_map.png beside it. No hardware is opened.
Only measured angular positions are plotted; missing points are not interpolated.
Requires matplotlib from the project's optional analysis dependencies.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path


COLUMNS = ("base_deg", "inclination_deg", "p2p_ch1_v", "p2p_ch2_v", "magnitude_v")


def load_points(summary: Path) -> list[tuple[float, ...]]:
    points = []
    positions = set()
    with summary.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not {"mode", *COLUMNS}.issubset(reader.fieldnames or []):
            raise ValueError("The CSV must contain mode, angles, CH1/CH2 p-p, and magnitude.")
        for line_number, row in enumerate(reader, start=2):
            if row["mode"] != "circular":
                raise ValueError(f"Line {line_number}: expected a circular measurement.")
            try:
                point = tuple(float(row[name]) for name in COLUMNS)
            except (TypeError, ValueError) as error:
                raise ValueError(f"Line {line_number}: invalid or missing numeric value.") from error
            if not all(math.isfinite(value) for value in point) or min(point[2:]) < 0:
                raise ValueError(f"Line {line_number}: angles must be finite and signals non-negative.")
            if point[:2] in positions:
                raise ValueError(f"Line {line_number}: duplicate angular position {point[:2]}.")
            positions.add(point[:2])
            points.append(point)
    if not points:
        raise ValueError("No completed circular measurements were found.")
    return points


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, help="Run directory or its summary.csv file")
    args = parser.parse_args(argv)
    summary = args.run / "summary.csv" if args.run.is_dir() else args.run
    try:
        points = load_points(summary)
    except (OSError, ValueError, csv.Error) as error:
        parser.error(str(error))
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        parser.error('Plotting requires matplotlib: python -m pip install -e ".[analysis]"')

    base, inclination, ch1, ch2, magnitude = zip(*points)
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), sharex=True, sharey=True,
                             layout="constrained")
    try:
        for axis, values, title in zip(axes, (ch1, ch2, magnitude),
                                       ("CH1 peak-to-peak", "CH2 peak-to-peak", "Combined magnitude")):
            plot = axis.scatter(base, inclination, c=values, marker="s", s=70,
                                cmap="viridis", vmin=0)
            axis.set(title=title, xlabel="Base (deg)")
            fig.colorbar(plot, ax=axis, label="V")
        axes[0].set_ylabel("Inclination (deg)")
        fig.suptitle(f"{summary.parent.name} | {len(points)} measured points")
        output = summary.parent / "circular_map.png"
        fig.savefig(output, dpi=180)
    finally:
        plt.close(fig)
    print(f"Plot saved: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
