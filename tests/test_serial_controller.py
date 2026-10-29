import pytest

from efield_control.drivers import serial_controller
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


@pytest.mark.parametrize("respond_to_retry", [False, True])
def test_ping_retries_once_after_startup_timeout(monkeypatch, respond_to_retry):
    serial = FakeSerial([])
    clock = [0.0]

    def read():
        clock[0] += 4
        if respond_to_retry and len(serial.writes) == 2:
            return b"PONG\n"
        return b"ARDUINO_READY\n"

    serial.readline = read
    monkeypatch.setattr(serial_controller.time, "monotonic", lambda: clock[0])
    controller = SerialMotorController(port="unused", serial_port=serial)
    if respond_to_retry:
        controller.ping()
    else:
        with pytest.raises(TimeoutError, match="ARDUINO_READY"):
            controller.ping()
    assert serial.writes == [b"PING\n", b"PING\n"]


@pytest.mark.parametrize("command,arguments", [
    ("move_to", (90, 92)), ("center", ()), ("fire", ()),
])
def test_actuation_timeout_reports_last_line_without_retry(monkeypatch, command, arguments):
    serial = FakeSerial([])
    clock = [0.0]

    def read():
        clock[0] += 2
        return b"ARDUINO_READY\n" if clock[0] == 2 else b""

    serial.readline = read
    monkeypatch.setattr(serial_controller.time, "monotonic", lambda: clock[0])
    controller = SerialMotorController(port="unused", serial_port=serial)
    with pytest.raises(TimeoutError, match="Last non-empty response: 'ARDUINO_READY'"):
        getattr(controller, command)(*arguments)
    assert len(serial.writes) == 1


def test_ping_rejection_is_not_retried():
    serial = FakeSerial(["COMMAND_ERROR,UNKNOWN"])
    controller = SerialMotorController(port="unused", serial_port=serial)
    with pytest.raises(ControllerCommandError):
        controller.ping()
    assert serial.writes == [b"PING\n"]
