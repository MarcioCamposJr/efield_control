"""Single-key acquisition control, polled only between completed points."""

from __future__ import annotations

import os
import select
import sys
import time


class KeyboardControl:
    def __init__(self) -> None:
        self._enabled = False
        self._settings = None
        self._fd = None
        self._paused = False

    def __enter__(self) -> KeyboardControl:
        self._enabled = sys.stdin.isatty()
        if not self._enabled:
            print("Single-key control requires an interactive terminal; use Ctrl+C to interrupt.", flush=True)
            return self
        if os.name != "nt":
            import termios
            import tty

            self._fd = sys.stdin.fileno()
            self._settings = termios.tcgetattr(self._fd)
            try:
                tty.setcbreak(self._fd, termios.TCSANOW)
            except BaseException:
                termios.tcsetattr(self._fd, termios.TCSANOW, self._settings)
                self._settings = None
                raise
        print("Keys (no Enter): P = pause, R = resume, S = stop after saving the current point. "
              "Ctrl+C interrupts.", flush=True)
        return self

    def __exit__(self, *exc_info) -> None:
        if self._settings is not None:
            import termios

            termios.tcsetattr(self._fd, termios.TCSANOW, self._settings)

    def _read_keys(self) -> str:
        if not self._enabled:
            return ""
        if os.name == "nt":
            import msvcrt

            keys = []
            while msvcrt.kbhit():
                key = msvcrt.getwch()
                if key in ("\x00", "\xe0"):
                    msvcrt.getwch()  # Consume the scan code for a special key.
                else:
                    keys.append(key)
            return "".join(keys)
        if select.select([self._fd], [], [], 0)[0]:
            data = os.read(self._fd, 1024)
            if not data:
                raise KeyboardInterrupt
            return data.decode("ascii", errors="ignore")
        return ""

    def checkpoint(self) -> None:
        while True:
            keys = self._read_keys().lower()
            if "s" in keys or "\x03" in keys:
                print("S pressed; closing the run.", flush=True)
                raise KeyboardInterrupt
            for key in keys:
                if key == "p" and not self._paused:
                    self._paused = True
                    print("Acquisition paused. Press R to resume or S to stop (no Enter).", flush=True)
                elif key == "r" and self._paused:
                    self._paused = False
                    print("Resuming acquisition.", flush=True)
            if not self._paused:
                return
            time.sleep(0.2)
