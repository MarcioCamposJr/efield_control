"""Exercise terminal handling without changing the test runner's real terminal."""

import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from efield_control import keyboard_control as module


@pytest.mark.parametrize("failure", [None, RuntimeError("device failed"), KeyboardInterrupt()])
def test_posix_terminal_is_restored_after_run(monkeypatch, failure):
    stream = Mock()
    stream.isatty.return_value = True
    stream.fileno.return_value = 7
    settings = ["original terminal settings"]
    termios = SimpleNamespace(tcgetattr=Mock(return_value=settings), tcsetattr=Mock(), TCSANOW=0)
    tty = SimpleNamespace(setcbreak=Mock())
    monkeypatch.setattr(module, "os", SimpleNamespace(name="posix"))
    monkeypatch.setattr(module, "sys", SimpleNamespace(stdin=stream))
    monkeypatch.setitem(sys.modules, "termios", termios)
    monkeypatch.setitem(sys.modules, "tty", tty)

    def run():
        with module.KeyboardControl():
            tty.setcbreak.assert_called_once_with(7, 0)
            if failure is not None:
                raise failure

    if failure is None:
        run()
    else:
        with pytest.raises(type(failure)):
            run()
    termios.tcsetattr.assert_called_once_with(7, 0, settings)


def test_posix_reads_keys_without_newline_and_stops_on_terminal_eof(monkeypatch):
    control = module.KeyboardControl()
    control._enabled, control._fd = True, 7
    read = Mock(side_effect=[b"S", b""])
    monkeypatch.setattr(module, "os", SimpleNamespace(name="posix", read=read))
    monkeypatch.setattr(module.select, "select", Mock(return_value=([7], [], [])))
    assert control._read_keys() == "S"
    with pytest.raises(KeyboardInterrupt):
        control._read_keys()


def test_windows_reads_single_keys_and_ignores_special_key_scan_codes(monkeypatch):
    control = module.KeyboardControl()
    control._enabled = True
    console = SimpleNamespace(
        kbhit=Mock(side_effect=[True, True, False]),
        getwch=Mock(side_effect=["\xe0", "P", "s"]),
    )
    monkeypatch.setattr(module, "os", SimpleNamespace(name="nt"))
    monkeypatch.setitem(sys.modules, "msvcrt", console)
    assert control._read_keys() == "s"


def test_redirected_input_is_not_read_or_reconfigured(monkeypatch, capsys):
    stream = Mock()
    stream.isatty.return_value = False
    monkeypatch.setattr(module, "sys", SimpleNamespace(stdin=stream))
    with module.KeyboardControl() as control:
        control.checkpoint()
    stream.fileno.assert_not_called()
    assert "interactive terminal" in capsys.readouterr().out
