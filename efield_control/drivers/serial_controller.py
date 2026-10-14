"""Arduino stage serial protocol for servo movements and TMS firing."""

from __future__ import annotations

import time


class ControllerCommandError(RuntimeError):
    """The stage controller explicitly rejected a command."""


class SerialMotorController:
    """Provide move_to for the stage and fire for the serial pulse source.

    The constructor opens the port unless serial_port is already supplied.
    Commands follow the firmware in firmware/arduino_hemispherical_stage/.
    """

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
        """Wait for the controller response and propagate rejections or timeouts."""
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
        """Send PING and require PONG to verify communication with the stage."""
        self._send("PING")
        self._wait_prefix("PONG")

    def center(self) -> None:
        """Send CENTER to use the physical center defined in the firmware.

        The CLI uses CalibratedAngularPositioner.center(), which sends MOVEABS
        with centers from the calibration file instead of this fallback command.
        """
        self._serial.reset_input_buffer()
        self._send("CENTER")
        self._wait_prefix("SERVOS_OK")

    def move_to(self, base_deg: float, inclination_deg: float) -> None:
        """Send MOVEABS with physical servo angles in degrees and wait for MOVED."""
        self._serial.reset_input_buffer()
        self._send(f"MOVEABS,{base_deg:g},{inclination_deg:g}")
        self._wait_prefix("MOVED")
        time.sleep(self.movement_settling_s)

    def fire(self) -> None:
        """Send FIRE to Arduino and wait for FIRE_DONE after the output pulse."""
        self._serial.reset_input_buffer()
        self._send("FIRE")
        self._wait_prefix("FIRE_DONE")

    def close(self) -> None:
        self._serial.close()
