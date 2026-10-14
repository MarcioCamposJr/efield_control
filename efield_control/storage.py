"""Save experiment measurements and metadata without commanding equipment."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .domain import Measurement


@dataclass(frozen=True, slots=True)
class MeasurementLocation:
    """Identify the measured point using Cartesian coordinates or logical angles."""
    mode: str
    label: str
    x_mm: float | None = None
    y_mm: float | None = None
    z_mm: float | None = None
    base_deg: float | None = None
    inclination_deg: float | None = None


class CsvRunStore:
    """Writes a summary and waveforms to a unique directory for each run."""

    SUMMARY_FIELDS = (
        "index",
        "timestamp",
        "mode",
        "label",
        "x_mm",
        "y_mm",
        "z_mm",
        "base_deg",
        "inclination_deg",
        "p2p_ch1_v",
        "p2p_ch2_v",
        "magnitude_v",
        "repetitions",
        "waveform_file",
    )

    def __init__(
        self,
        root: str | Path = "data",
        run_name: str = "measurement",
        save_waveforms: bool = True,
    ) -> None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_directory = Path(root) / f"{run_name}_{timestamp}"
        self.waveform_directory = self.run_directory / "waveforms"
        self.waveform_directory.mkdir(parents=True, exist_ok=False)
        self.summary_file = self.run_directory / "summary.csv"
        self.save_waveforms = save_waveforms
        self._next_index = 1
        with self.summary_file.open("w", newline="", encoding="utf-8") as stream:
            csv.DictWriter(stream, fieldnames=self.SUMMARY_FIELDS).writeheader()

    def append(self, location: MeasurementLocation, measurement: Measurement) -> Path:
        """Write a summary.csv row and, if enabled, the waveform in a separate CSV."""
        index = self._next_index
        self._next_index += 1
        waveform_file: Path | None = None
        if self.save_waveforms:
            waveform_file = self.waveform_directory / f"waveform_{index:05d}.csv"
            self._write_waveform(waveform_file, measurement)

        row = {
            "index": index,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "mode": location.mode,
            "label": location.label,
            "x_mm": location.x_mm,
            "y_mm": location.y_mm,
            "z_mm": location.z_mm,
            "base_deg": location.base_deg,
            "inclination_deg": location.inclination_deg,
            "p2p_ch1_v": measurement.p2p_ch1_v,
            "p2p_ch2_v": measurement.p2p_ch2_v,
            "magnitude_v": measurement.magnitude_v,
            "repetitions": measurement.repetitions,
            "waveform_file": str(waveform_file) if waveform_file else "",
        }
        with self.summary_file.open("a", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=self.SUMMARY_FIELDS)
            writer.writerow(row)
        return waveform_file or self.summary_file

    def write_json(self, filename: str, data: object) -> Path:
        """Record metadata, such as resolved_config.json, in this run directory."""
        path = self.run_directory / filename
        with path.open("w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, sort_keys=True)
            stream.write("\n")
        return path

    @staticmethod
    def _write_waveform(path: Path, measurement: Measurement) -> None:
        # Export time in microseconds relative to the start of the sample array.
        waveform = measurement.waveform
        count = min(len(waveform.channel_1_v), len(waveform.channel_2_v))
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(("index", "time_us", "ch1_v", "ch2_v"))
            for index in range(count):
                writer.writerow(
                    (
                        index,
                        index / waveform.sample_rate_hz * 1e6,
                        waveform.channel_1_v[index],
                        waveform.channel_2_v[index],
                    )
                )
