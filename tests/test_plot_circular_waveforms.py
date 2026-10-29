import csv
from unittest.mock import Mock

import numpy as np
import pytest

from efield_control.domain import Measurement, Waveform
from efield_control.storage import CsvRunStore, MeasurementLocation
from examples.plot_circular_waveforms import load_records, load_waveform, main


@pytest.mark.parametrize("include_center", [False, True])
def test_waveform_overlay_uses_real_times_colors_and_instantaneous_magnitude(
    tmp_path, monkeypatch, include_center,
):
    pytest.importorskip("matplotlib")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    monkeypatch.setattr("socket.create_connection", Mock(side_effect=AssertionError("Hardware")))
    store = CsvRunStore(tmp_path, "circular")
    coordinates = [(10, 0), (-10, 0), (0, 20)]
    if include_center:
        coordinates.append((0, 0))
    measurement = Measurement.aggregate([Waveform((3, -3), (4, -4), 2000)])
    for base, inclination in coordinates:
        store.append(MeasurementLocation("circular", "point", base_deg=base,
                                         inclination_deg=inclination), measurement)
    # Exercise copied runs with Windows paths in otherwise portable CSV metadata.
    with store.summary_file.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    with store.summary_file.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CsvRunStore.SUMMARY_FIELDS)
        writer.writeheader()
        for index, row in enumerate(rows, start=1):
            row["waveform_file"] = f"C:\\old_run\\waveforms\\waveform_{index:05d}.csv"
            writer.writerow(row)
    assert len(load_records(store.summary_file)) == len(coordinates)

    savefig = plt.Figure.savefig
    observed = []

    def inspect_plot(fig, *args, **kwargs):
        ch1, ch2, magnitude, key = fig.axes
        assert len(ch1.lines) == len(ch2.lines) == len(magnitude.lines) == len(coordinates)
        assert len(key.collections) == len(coordinates)
        for first, second, combined in zip(ch1.lines, ch2.lines, magnitude.lines):
            np.testing.assert_array_equal(first.get_xdata(), [0, 500])
            np.testing.assert_array_equal(first.get_ydata(), [3, -3])
            np.testing.assert_array_equal(second.get_ydata(), [4, -4])
            np.testing.assert_array_equal(combined.get_ydata(), [5, 5])
            assert first.get_color() == second.get_color() == combined.get_color()
        assert len({str(line.get_color()) for line in ch1.lines}) == len(coordinates)
        assert any(line.get_label() == "(0, 0) deg" for line in ch1.lines) == include_center
        if include_center:
            assert ch1.lines[-1].get_color() == "black"
            assert ch1.lines[-1].get_linewidth() > ch1.lines[0].get_linewidth()
        observed.append(True)
        return savefig(fig, *args, **kwargs)

    monkeypatch.setattr(plt.Figure, "savefig", inspect_plot)
    assert main([str(store.run_directory)]) == 0
    assert observed == [True]
    assert (store.run_directory / "circular_waveforms.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.parametrize("rows", [
    [], [(0, "nan", 1)], [(0, 1, 2), (0, 3, 4)], [(1, 1, 2), (0, 3, 4)],
])
def test_invalid_waveform_samples_are_rejected(tmp_path, rows):
    path = tmp_path / "waveform.csv"
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("time_us", "ch1_v", "ch2_v"))
        writer.writerows(rows)
    with pytest.raises(ValueError):
        load_waveform(path)


def test_missing_or_unsaved_waveforms_are_reported(tmp_path):
    store = CsvRunStore(tmp_path, "circular", save_waveforms=False)
    store.append(MeasurementLocation("circular", "center", base_deg=0, inclination_deg=0),
                 Measurement.aggregate([Waveform((1, 2), (3, 4), 1000)]))
    with pytest.raises(ValueError, match="Waveforms were not saved"):
        load_records(store.summary_file)
    with store.summary_file.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    rows[0]["waveform_file"] = "waveform_00001.csv"
    with store.summary_file.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CsvRunStore.SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="Missing waveform"):
        load_records(store.summary_file)
