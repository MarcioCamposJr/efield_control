import pytest

from efield_control.cli import (
    HARDWARE_CONFIRMATION,
    _require_confirmation,
    _validate_runtime_settings,
    apply_project_config,
    build_parser,
    inclusive_range,
)
from efield_control.configuration import load_project_config


def test_inclusive_range_supports_both_directions() -> None:
    assert inclusive_range(-1, 1, 1) == (-1, 0, 1)
    assert inclusive_range(1, -1, -1) == (1, 0, -1)


def test_hardware_command_is_blocked_without_exact_confirmation() -> None:
    args = build_parser().parse_args(
        [
            "center",
            "--rp-ip",
            "127.0.0.1",
            "--robot-ip",
            "127.0.0.1",
            "--pulse-source",
            "redpitaya",
        ]
    )
    with pytest.raises(SystemExit, match="Operation blocked"):
        _require_confirmation(args)

    args.confirm_hardware = HARDWARE_CONFIRMATION
    _require_confirmation(args)


def test_cli_value_has_precedence_over_loaded_configuration() -> None:
    args = build_parser().parse_args(
        ["center", "--initial-step", "2.5", "--pulse-source", "redpitaya"]
    )
    config = load_project_config(environ={})

    apply_project_config(args, config)

    assert args.initial_step == 2.5
    assert args.decimation == config.acquisition.decimation
    assert args.rp_ip == "169.254.197.73"


def test_mtms_api_preflight_requires_bootstrapped_environment(monkeypatch) -> None:
    args = build_parser().parse_args(["center", "--pulse-source", "mtms_api"])
    apply_project_config(args, load_project_config(environ={}))

    def unavailable() -> None:
        raise RuntimeError("mTMS environment unavailable")

    monkeypatch.setattr(
        "efield_control.cli.MtmsSingleChannelClient.validate_environment",
        unavailable,
    )

    with pytest.raises(RuntimeError, match="environment unavailable"):
        _validate_runtime_settings(args)
