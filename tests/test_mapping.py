from efield_control.mapping import circular_serpentine, planar_serpentine


def test_planar_path_is_serpentine() -> None:
    points = list(planar_serpentine([-1, 0, 1], [10, 20]))
    assert [(point.dx_mm, point.dy_mm) for point in points] == [
        (-1, 10),
        (0, 10),
        (1, 10),
        (1, 20),
        (0, 20),
        (-1, 20),
    ]


def test_circular_path_is_serpentine() -> None:
    points = list(circular_serpentine([0, 90, 180], [30, 60]))
    assert [(point.base_deg, point.inclination_deg) for point in points] == [
        (0, 30),
        (90, 30),
        (180, 30),
        (180, 60),
        (90, 60),
        (0, 60),
    ]

