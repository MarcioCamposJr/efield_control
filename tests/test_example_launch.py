"""Check file-based example launching without connecting to real equipment."""

import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_DIRECTORY = Path(__file__).resolve().parents[1]


class ExampleLaunchTests(unittest.TestCase):
    def test_simulation_runs_by_file_from_another_working_directory(self):
        result = subprocess.run(
            [sys.executable, "-B", str(PROJECT_DIRECTORY / "examples/simulate_centering.py")],
            cwd=PROJECT_DIRECTORY / "examples",
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Center: X=3.00 mm, Y=-2.00 mm", result.stdout)

    def test_connection_example_imports_checkout_and_loads_files_from_other_cwd(self):
        script = PROJECT_DIRECTORY / "examples/check_connections.py"
        # run_path uses the same empty package context as file execution. Replace
        # all device checks before calling main so no sockets or ports are opened.
        code = f'''
import pathlib
import runpy
import socket
import sys
namespace = runpy.run_path({str(script)!r})
import efield_control
root = pathlib.Path({str(PROJECT_DIRECTORY)!r})
assert pathlib.Path(efield_control.__file__).resolve() == root / "efield_control/__init__.py"
original_cwd = pathlib.Path.cwd()
def forbidden_connection(*args, **kwargs):
    raise AssertionError("Unexpected hardware connection")
socket.socket = forbidden_connection
socket.create_connection = forbidden_connection
def simulated_checks(config, on_result):
    assert config.robot.speed_percent > 0
    assert config.hardware.robot_type in ("elfin", "dobot")
    results = [namespace["ConnectionResult"]("Robot", True, "simulated")]
    for result in results:
        on_result(result)
    return results
namespace["main"].__globals__["check_connections"] = simulated_checks
assert namespace["main"]() == 0
assert pathlib.Path.cwd() == original_cwd
print("Checkout imports and configuration paths verified without hardware")
'''
        result = subprocess.run(
            [sys.executable, "-B", "-c", code],
            cwd=PROJECT_DIRECTORY / "examples",
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("configuration paths verified without hardware", result.stdout)


if __name__ == "__main__":
    unittest.main()
