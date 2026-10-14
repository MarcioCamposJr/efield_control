"""Guard public MTMSApi calls without accessing its ROS implementation."""

from __future__ import annotations

import signal
import threading
import time
from contextlib import contextmanager


@contextmanager
def alarm_deadline(timeout_s: float, description: str):
    """Interrupt service discovery on the ROS Linux host's main Python thread.

    This is a best-effort deadline: native waits inside the vendor library may
    delay Python signal handling until they return. No ROS methods are replaced.
    Existing alarm handlers/timers are restored after each operation.
    """
    if not hasattr(signal, "setitimer") or threading.current_thread() is not threading.main_thread():
        raise RuntimeError("Bounded mTMS API calls require a POSIX main thread (ROS Linux host).")
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    started = time.monotonic()

    def expired(signum, frame):
        raise TimeoutError(f"mTMS timeout during {description} ({timeout_s:g} s).")

    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, timeout_s)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        delay, interval = previous_timer
        if delay:
            delay = max(0.000001, delay - (time.monotonic() - started))
        signal.setitimer(signal.ITIMER_REAL, delay, interval)


