import csv
from unittest.mock import Mock

import pytest

from efield_control.domain import Measurement, Waveform
from efield_control.storage import CsvRunStore, MeasurementLocation
from examples.plot_circular import COLUMNS, load_points, main


def test_plot_reads_current_store_and_creates_png(tmp_path, monkeypatch):
    pytest.importorskip("matplotlib")
    monkeypatch.setattr("socket.socket", Mock(side_effect=AssertionError("Hardware connection")))
    store = CsvRunStore(tmp_path, "circular", save_waveforms=False)
    measurement = Measurement.aggregate([Waveform((-1, 1), (-2, 2), 1000)])
    # Include a serpentine row and a missing grid point from an interrupted run.
    for base, inclination in ((-10, -5), (10, -5), (10, 5)):
        store.append(MeasurementLocation("circular", "point", base_deg=base,
                                         inclination_deg=inclination), measurement)
    points = load_points(store.summary_file)
    assert [point[:2] for point in points] == [(-10, -5), (10, -5), (10, 5)]
    assert points[0][2:] == (2, 4, measurement.magnitude_v)
    original_csv = store.summary_file.read_bytes()
    for source in (store.run_directory, store.summary_file):
        assert main([str(source)]) == 0
        assert (store.run_directory / "circular_map.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert store.summary_file.read_bytes() == original_csv


@pytest.mark.parametrize("rows", [
    [],
    [("planar", 0, 0, 1, 2, 3)],
    [("circular", "", 0, 1, 2, 3)],
    [("circular", 0, 0, "nan", 2, 3)],
    [("circular", 0, 0, -1, 2, 3)],
    [("circular", 0, 0, 1, 2, 3)] * 2,
])
def test_invalid_summaries_are_rejected(tmp_path, rows):
    summary = tmp_path / "summary.csv"
    with summary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("mode", *COLUMNS))
        writer.writerows(rows)
    with pytest.raises(ValueError):
        load_points(summary)


def test_missing_columns_are_rejected(tmp_path):
    summary = tmp_path / "summary.csv"
    summary.write_text("old_header\n1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="CSV must contain"):
        load_points(summary)
