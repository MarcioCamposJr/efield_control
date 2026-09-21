from __future__ import annotations

import time


class ControllerCommandError(RuntimeError):
    """The stage controller explicitly rejected a command."""


class SerialMotorController:
    """Controls the circular stage and pulse through the existing ESP protocol."""

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        timeout_s: float = 3.0,
        movement_settling_s: float = 1.0,
        serial_port=None,
    ) -> None:
        if serial_port is None:
            import serial

            serial_port = serial.Serial(port, baudrate, timeout=timeout_s)
        self._serial = serial_port
        self.timeout_s = timeout_s
        self.movement_settling_s = movement_settling_s

    def _send(self, command: str) -> None:
        self._serial.write(f"{command}\n".encode("ascii"))
        self._serial.flush()

    def _wait_prefix(self, prefix: str, timeout_s: float | None = None) -> str:
        deadline = time.monotonic() + (timeout_s or self.timeout_s)
        while time.monotonic() <= deadline:
            line = self._serial.readline().decode(errors="replace").strip()
            if line.startswith(prefix):
                return line
            if "_ERROR" in line or line.startswith("ERROR"):
                raise ControllerCommandError(
                    f"The controller rejected the command: {line}"
                )
        raise TimeoutError(f"The controller did not respond with {prefix!r}.")

    def ping(self) -> None:
        self._send("PING")
        self._wait_prefix("PONG")

    def center(self) -> None:
        self._serial.reset_input_buffer()
        self._send("CENTER")
        self._wait_prefix("SERVOS_OK")

    def move_to(self, base_deg: float, inclination_deg: float) -> None:
        self._serial.reset_input_buffer()
        self._send(f"MOVEABS,{base_deg:g},{inclination_deg:g}")
        self._wait_prefix("MOVED")
        time.sleep(self.movement_settling_s)

    def fire(self) -> None:
        self._serial.reset_input_buffer()
        self._send("FIRE")
        self._wait_prefix("FIRE_DONE")

    def close(self) -> None:
        self._serial.close()
