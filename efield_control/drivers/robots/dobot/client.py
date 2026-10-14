"""Maintain the latest Dobot feedback without accumulating old position frames."""

from __future__ import annotations

import math
import time
from threading import Condition, Event, Thread

from .connection import DobotConnection, DobotFeedback


class Dobot:
    """Device client used by DobotRobotAdapter; no automatic enable or error reset."""

    def __init__(
        self,
        host: str,
        *,
        socket_timeout_s: float = 3.0,
        feedback_max_age_s: float = 1.0,
        connection: DobotConnection | None = None,
    ) -> None:
        if not math.isfinite(feedback_max_age_s) or feedback_max_age_s <= 0:
            raise ValueError("Dobot feedback maximum age must be finite and positive.")
        self.connection = connection if connection is not None else DobotConnection(
            host, socket_timeout_s
        )
        self.feedback_max_age_s = feedback_max_age_s
        self._condition = Condition()
        self._closing = Event()
        self._thread: Thread | None = None
        self._feedback: DobotFeedback | None = None
        self._received_at = 0.0
        self._feedback_error: Exception | None = None

    def connect(self) -> None:
        if self._thread is not None:
            return
        self._closing.clear()
        self._feedback = None
        self._feedback_error = None
        try:
            self.connection.connect()
            self._thread = Thread(target=self._read_feedback, name="dobot-feedback", daemon=True)
            self._thread.start()
            self.feedback(timeout_s=self.feedback_max_age_s)
        except BaseException:
            self.disconnect()
            raise

    def _read_feedback(self) -> None:
        try:
            while not self._closing.is_set():
                feedback = self.connection.get_feedback()
                with self._condition:
                    self._feedback = feedback
                    self._received_at = time.monotonic()
                    self._condition.notify_all()
        except Exception as error:
            if not self._closing.is_set():
                with self._condition:
                    self._feedback_error = error
                    self._condition.notify_all()

    def feedback(self, *, after: float = 0.0, timeout_s: float | None = None) -> DobotFeedback:
        """Require recent feedback, optionally received after a command was accepted."""
        if timeout_s is not None and (not math.isfinite(timeout_s) or timeout_s <= 0):
            raise ValueError("Dobot feedback wait timeout must be finite and positive.")
        deadline = time.monotonic() + (
            self.feedback_max_age_s if timeout_s is None else timeout_s
        )
        with self._condition:
            while True:
                if self._closing.is_set() or self._thread is None:
                    raise ConnectionError("The Dobot feedback client is disconnected.")
                if self._feedback_error is not None:
                    raise ConnectionError("Dobot feedback reader failed.") from self._feedback_error
                now = time.monotonic()
                if (
                    self._feedback is not None
                    and self._received_at > after
                    and now - self._received_at <= self.feedback_max_age_s
                ):
                    return self._feedback
                remaining = deadline - now
                if remaining <= 0:
                    raise TimeoutError("No fresh Dobot feedback was received.")
                self._condition.wait(remaining)

    def disconnect(self) -> None:
        """Close all TCP channels and finish the reader before allowing reconnection."""
        self._closing.set()
        try:
            self.connection.close()
        finally:
            with self._condition:
                self._condition.notify_all()
            if self._thread is not None:
                self._thread.join()
                self._thread = None
            self._feedback = None
