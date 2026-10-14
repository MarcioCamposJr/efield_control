"""TCP transport for the six-axis Dobot V3 protocol (CR/Nova).

Protocol layout and commands: https://github.com/Dobot-Arm/TCP-IP-Python-V3
Only the feedback fields needed for position and motion state are decoded.
"""

from __future__ import annotations

import math
import re
import socket
import struct
import time
from dataclasses import dataclass
from enum import IntEnum
from typing import Callable


class RobotStatus(IntEnum):
    DISABLED = 4
    IDLE = 5
    RUNNING = 7
    ERROR = 9


class DobotCommandError(RuntimeError):
    """The controller rejected a command or returned an invalid reply."""


@dataclass(frozen=True, slots=True)
class DobotFeedback:
    """One validated frame: TCP pose in mm/degrees and controller motion state."""

    pose: tuple[float, ...]
    robot_mode: int
    running: bool
    enabled: bool
    error: bool

    @classmethod
    def from_bytes(cls, frame: bytes) -> DobotFeedback:
        if len(frame) != 1440 or struct.unpack_from("<Q", frame, 0)[0] != 1440:
            raise RuntimeError("Invalid Dobot V3 feedback frame length.")
        if struct.unpack_from("<Q", frame, 48)[0] != 0x123456789ABCDEF:
            raise RuntimeError("Invalid Dobot V3 feedback marker or byte order.")
        pose = struct.unpack_from("<6d", frame, 624)
        if not all(math.isfinite(value) for value in pose):
            raise RuntimeError("Dobot feedback contains a non-finite TCP pose.")
        return cls(
            pose=pose,
            robot_mode=struct.unpack_from("<Q", frame, 24)[0],
            running=bool(frame[1028]),
            enabled=bool(frame[1026]),
            error=bool(frame[1029]),
        )


class DobotConnection:
    """Open TCP channels explicitly; importing or constructing does not connect."""

    DASHBOARD_PORT = 29999
    MOVEMENT_PORT = 30003
    FEEDBACK_PORT = 30004

    def __init__(
        self,
        host: str,
        timeout_s: float = 3.0,
        *,
        socket_factory: Callable = socket.create_connection,
    ) -> None:
        if not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("Dobot socket timeout must be finite and positive.")
        self.host = host
        self.timeout_s = timeout_s
        self._socket_factory = socket_factory
        self._sockets: dict[str, socket.socket] = {}

    def connect(self) -> None:
        if self._sockets:
            return
        try:
            for name, port in (
                ("dashboard", self.DASHBOARD_PORT),
                ("movement", self.MOVEMENT_PORT),
                ("feedback", self.FEEDBACK_PORT),
            ):
                self._sockets[name] = self._socket_factory(
                    (self.host, port), timeout=self.timeout_s
                )
        except BaseException:
            self.close()
            raise

    def _socket(self, channel: str) -> socket.socket:
        try:
            return self._sockets[channel]
        except KeyError as error:
            raise ConnectionError("The Dobot controller is not connected.") from error

    def _command(self, channel: str, command: str) -> str:
        """Read a complete semicolon-terminated reply and require error code zero."""
        sock = self._socket(channel)
        deadline = time.monotonic() + self.timeout_s
        response = bytearray()
        try:
            sock.settimeout(self.timeout_s)
            sock.sendall(command.encode("ascii"))
            while b";" not in response:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"Timed out waiting for Dobot {command}.")
                sock.settimeout(remaining)
                chunk = sock.recv(4096)
                if not chunk:
                    raise ConnectionError("Dobot closed the command connection.")
                response.extend(chunk)
                if len(response) > 65536:
                    raise DobotCommandError("Dobot command reply is too long.")
        finally:
            sock.settimeout(self.timeout_s)
        reply = response.decode("ascii").strip()
        match = re.fullmatch(r"(-?\d+)\s*,\s*(\{.*\})\s*,\s*(.*?)\s*;", reply)
        if match is None or match.group(3) != command:
            raise DobotCommandError(f"Invalid Dobot reply to {command}: {reply}")
        if int(match.group(1)) != 0:
            raise DobotCommandError(f"Dobot rejected {command}: {reply}")
        return match.group(2)

    def get_error_id(self) -> str:
        """Read controller/joint alarm IDs without clearing or resetting them."""
        return self._command("dashboard", "GetErrorID()")

    def enable_robot(self) -> None:
        """Enable the robot via TCP dashboard without changing its control mode."""
        self._command("dashboard", "EnableRobot()")

    def move_linear(self, target: list[float], speed_percent: int) -> None:
        """Send MovL on the motion channel, with a speed limit for this command."""
        if len(target) != 6 or not all(math.isfinite(value) for value in target):
            raise ValueError("Dobot target must contain six finite coordinates.")
        if not 1 <= speed_percent <= 100:
            raise ValueError("Dobot speed percentage must be between 1 and 100.")
        coordinates = ",".join(format(value, ".12g") for value in target)
        self._command("movement", f"MovL({coordinates},SpeedL={speed_percent})")

    def stop_robot(self) -> None:
        """ResetRobot is the motion stop command in the supported V3 protocol."""
        self._command("dashboard", "ResetRobot()")

    def get_feedback(self) -> DobotFeedback:
        """Read exactly one frame, detecting EOF and bounding the total read time."""
        sock = self._socket("feedback")
        deadline = time.monotonic() + self.timeout_s
        frame = bytearray()
        while len(frame) < 1440:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Timed out reading Dobot feedback.")
            sock.settimeout(remaining)
            chunk = sock.recv(1440 - len(frame))
            if not chunk:
                raise ConnectionError("Dobot closed the feedback connection.")
            frame.extend(chunk)
        return DobotFeedback.from_bytes(bytes(frame))

    def close(self) -> None:
        """Shutdown wakes a blocked feedback reader before sockets are closed."""
        sockets, self._sockets = self._sockets, {}
        first_error: OSError | None = None
        for sock in sockets.values():
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            finally:
                try:
                    sock.close()
                except OSError as error:
                    if first_error is None:
                        first_error = error
        if first_error is not None:
            raise first_error
