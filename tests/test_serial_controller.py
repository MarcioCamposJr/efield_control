import pytest

from efield_control.drivers.serial_controller import (
    ControllerCommandError,
    SerialMotorController,
)


class FakeSerial:
    def __init__(self, responses: list[str]) -> None:
        self.responses = [f"{value}\n".encode() for value in responses]
        self.writes: list[bytes] = []
        self.closed = False

    def write(self, value: bytes) -> None:
        self.writes.append(value)

    def flush(self) -> None:
        return None

    def readline(self) -> bytes:
        return self.responses.pop(0) if self.responses else b""

    def reset_input_buffer(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


def test_decimal_motor_commands_are_sent_to_arduino() -> None:
    serial = FakeSerial(["MOVED,92.400,87.800"])
    controller = SerialMotorController(
        port="unused",
        movement_settling_s=0,
        serial_port=serial,
    )

    controller.move_to(92.4, 87.8)

    assert serial.writes == [b"MOVEABS,92.4,87.8\n"]


def test_firmware_error_is_reported_without_waiting_for_timeout() -> None:
    serial = FakeSerial(["FIRE_ERROR,DISABLED"])
    controller = SerialMotorController(port="unused", serial_port=serial)

    with pytest.raises(ControllerCommandError, match="FIRE_ERROR,DISABLED"):
        controller.fire()
