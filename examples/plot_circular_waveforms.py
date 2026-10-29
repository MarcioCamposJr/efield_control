"""Overlay circular waveforms: python examples/plot_circular_waveforms.py RUN_DIRECTORY.

Saves circular_waveforms.png with CH1, CH2, and instantaneous magnitude versus
buffer time, plus a coordinate color key referenced to logical (0 deg, 0 deg).
Uses the stored waveform at every measured point; no hardware is connected.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from colorsys import hls_to_rgb
from pathlib import Path, PureWindowsPath

import numpy as np

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from examples.plot_circular import load_points


def load_records(summary: Path) -> list[tuple[float, float, Path]]:
    points = load_points(summary)
    with summary.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    records = []
    for point, row in zip(points, rows):
        filename = row.get("waveform_file")
        if not filename:
            raise ValueError("Waveforms were not saved. Collection requires storage.save_waveforms=true.")
        # Resolve beside the summary so runs copied from another computer still work.
        waveform = summary.parent / "waveforms" / PureWindowsPath(filename).name
        if not waveform.is_file():
            raise ValueError(f"Missing waveform: {waveform}")
        records.append((point[0], point[1], waveform))
    return records


def load_waveform(path: Path) -> np.ndarray:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        header = next(csv.reader(stream), [])
        columns = ("time_us", "ch1_v", "ch2_v")
        if not set(columns).issubset(header):
            raise ValueError(f"{path.name}: expected time_us, ch1_v, and ch2_v columns.")
        data = np.loadtxt(stream, delimiter=",", usecols=[header.index(c) for c in columns], ndmin=2)
    if not data.size or not np.isfinite(data).all():
        raise ValueError(f"{path.name}: waveform must contain finite samples.")
    if np.any(np.diff(data[:, 0]) <= 0):
        raise ValueError(f"{path.name}: sample times must be strictly increasing.")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, help="Circular run directory or its summary.csv")
    args = parser.parse_args(argv)
    summary = args.run / "summary.csv" if args.run.is_dir() else args.run
    try:
        records = load_records(summary)
    except (OSError, ValueError, csv.Error) as error:
        parser.error(str(error))
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        parser.error('Plotting requires matplotlib: python -m pip install -e ".[analysis]"')

    records.sort(key=lambda point: math.hypot(point[0], point[1]), reverse=True)
    radius = math.hypot(records[0][0], records[0][1]) or 1.0
    fig = plt.figure(figsize=(15, 10), layout="constrained")
    grid = fig.add_gridspec(3, 2, width_ratios=(3, 1))
    axes = [fig.add_subplot(grid[0, 0])]
    axes.extend(fig.add_subplot(grid[row, 0], sharex=axes[0]) for row in (1, 2))
    key = fig.add_subplot(grid[:, 1])
    try:
        # shortcut: all traces stay in memory; reduce display samples if large scans exhaust RAM.
        for base, inclination, waveform in records:
            try:
                data = load_waveform(waveform)
            except (OSError, ValueError, csv.Error) as error:
                parser.error(str(error))
            time_us, ch1, ch2 = data.T
            distance = math.hypot(base, inclination)
            hue = (math.atan2(inclination, base) / (2 * math.pi)) % 1
            color = hls_to_rgb(hue, 0.3 + 0.4 * distance / radius, 0.85) if distance else "black"
            for axis, values in zip(axes, (ch1, ch2, np.hypot(ch1, ch2))):
                axis.plot(time_us, values, color=color, linewidth=0.7 if distance else 2,
                          label=f"({base:g}, {inclination:g}) deg")
            key.scatter(base, inclination, color=color, marker="s", s=45)
        for axis, title in zip(axes, ("CH1", "CH2", "Instantaneous magnitude: sqrt(CH1(t)^2 + CH2(t)^2)")):
            axis.set(title=title, ylabel="V")
            axis.grid(alpha=0.2)
        axes[-1].set_xlabel("Time from buffer start (us)")
        key.set(title="Coordinate colors\nReference: (0, 0) deg", xlabel="Base (deg)",
                ylabel="Inclination (deg)")
        key.set_aspect("equal", adjustable="box")
        key.grid(alpha=0.2)
        fig.suptitle(f"{summary.parent.name} | {len(records)} stored waveforms | darker = nearer center")
        output = summary.parent / "circular_waveforms.png"
        fig.savefig(output, dpi=180)
    finally:
        plt.close(fig)
    print(f"Plot saved: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
