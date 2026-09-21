"""Launch a project command with ROS 2 and the external mTMS API available.

This bootstrap intentionally uses only the Python standard library. It runs
before ROS 2 and MTMSApi can be imported into the project environment.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


EXIT_CONFIGURATION_ERROR = 2
EXIT_ENVIRONMENT_ERROR = 3
PROJECT_DIRECTORY = Path(__file__).resolve().parent


class MtmsBootstrapError(RuntimeError):
    """Configuration error found before starting the target process."""


def read_env_file(path: Path) -> dict[str, str]:
    """Read the small KEY=VALUE subset used by this project's .env file."""
    if not path.is_file():
        return {}

    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise MtmsBootstrapError(
                f"Invalid .env entry at {path}:{line_number}; expected KEY=VALUE."
            )
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def resolve_api_directory(configured_value: str) -> Path:
    if not configured_value.strip():
        raise MtmsBootstrapError(
            "EFIELD_MTMS_API_PATH is empty. Set it to MTMSApi.py or its directory."
        )

    configured_path = Path(configured_value).expanduser().resolve()
    if configured_path.is_file():
        if configured_path.name != "MTMSApi.py":
            raise MtmsBootstrapError(
                f"The configured file is not MTMSApi.py: {configured_path}"
            )
        api_directory = configured_path.parent
    else:
        api_directory = configured_path

    api_file = api_directory / "MTMSApi.py"
    if not api_file.is_file():
        raise MtmsBootstrapError(f"MTMSApi.py was not found in {api_directory}")
    return api_directory


def find_mtms_workspace(api_directory: Path) -> Path:
    """Find the workspace containing install/local_setup.bash."""
    for candidate in (api_directory, *api_directory.parents):
        if (candidate / "install" / "local_setup.bash").is_file():
            return candidate
    raise MtmsBootstrapError(
        "Could not find install/local_setup.bash above "
        f"{api_directory}. Build the mTMS workspace first."
    )


def build_command(
    ros_setup: Path,
    workspace_setup: Path,
    api_directory: Path,
    target_arguments: list[str],
) -> list[str]:
    shell_script = r'''
set -e

source "$1"
source "$2"
export PYTHONPATH="$3${PYTHONPATH:+:$PYTHONPATH}"

python_bin="$4"
shift 4

if ! "$python_bin" -c \
    "import rclpy; import MTMSApi; from mtms_event_interfaces.msg import ExecutionCondition"; then
    echo "" >&2
    echo "[mTMS] ERROR: failed to import the API or its ROS 2 dependencies." >&2
    echo "Check the Python/ROS version, compiled workspace, and API path." >&2
    exit 3
fi

exec "$python_bin" "$@"
'''
    return [
        "bash",
        "-c",
        shell_script,
        "mtms-bootstrap",
        str(ros_setup),
        str(workspace_setup),
        str(api_directory),
        sys.executable,
        *target_arguments,
    ]


def fail(message: str, exit_code: int) -> None:
    print(f"[mTMS] ERROR: {message}", file=sys.stderr)
    raise SystemExit(exit_code)


def main() -> None:
    if not sys.platform.startswith("linux"):
        fail(
            "the mTMS bootstrap must run on the Linux host containing ROS 2.",
            EXIT_ENVIRONMENT_ERROR,
        )
    if len(sys.argv) < 2:
        fail(
            "missing target command. Example: run_with_mtms.py -m "
            "efield_control.cli show-config",
            EXIT_CONFIGURATION_ERROR,
        )

    try:
        file_environment = read_env_file(PROJECT_DIRECTORY / ".env")
        api_value = os.environ.get(
            "EFIELD_MTMS_API_PATH", file_environment.get("EFIELD_MTMS_API_PATH", "")
        )
        ros_value = os.environ.get(
            "EFIELD_MTMS_ROS_SETUP",
            file_environment.get("EFIELD_MTMS_ROS_SETUP", "/opt/ros/jazzy/setup.bash"),
        )

        api_directory = resolve_api_directory(api_value)
        workspace = find_mtms_workspace(api_directory)
        ros_setup = Path(ros_value).expanduser().resolve()
        workspace_setup = workspace / "install" / "local_setup.bash"
        if not ros_setup.is_file():
            raise MtmsBootstrapError(
                f"ROS 2 setup was not found at {ros_setup}. Set "
                "EFIELD_MTMS_ROS_SETUP to the correct setup.bash file."
            )
    except MtmsBootstrapError as error:
        fail(str(error), EXIT_CONFIGURATION_ERROR)

    print(f"[mTMS] API: {api_directory}")
    print(f"[mTMS] Workspace: {workspace_setup}")
    print(f"[mTMS] Python: {sys.executable}")

    try:
        result = subprocess.run(
            build_command(
                ros_setup,
                workspace_setup,
                api_directory,
                sys.argv[1:],
            ),
            check=False,
        )
    except FileNotFoundError:
        fail("the 'bash' command was not found.", EXIT_ENVIRONMENT_ERROR)
    except OSError as error:
        fail(f"failed to start the environment: {error}", EXIT_ENVIRONMENT_ERROR)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()

