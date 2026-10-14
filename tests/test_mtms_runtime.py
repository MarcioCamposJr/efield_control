"""Test public API deadline restoration without ROS hardware."""

import signal
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from efield_control.drivers.stimulators.mtms import runtime


class RuntimeTests(unittest.TestCase):
    def test_alarm_restores_previous_handler_and_timer_on_error(self):
        previous = object()
        backend = SimpleNamespace(
            SIGALRM=14, ITIMER_REAL=0,
            getsignal=Mock(return_value=previous), getitimer=Mock(return_value=(5.0, 0.0)),
            signal=Mock(), setitimer=Mock(),
        )
        with patch.object(runtime, "signal", backend):
            with self.assertRaisesRegex(TimeoutError, "service discovery"):
                with runtime.alarm_deadline(0.1, "service discovery"):
                    backend.signal.call_args.args[1](14, None)
        self.assertEqual(backend.signal.call_args.args, (14, previous))
        timer = backend.setitimer.call_args.args
        self.assertGreater(timer[1], 0)
        self.assertLessEqual(timer[1], 5)

    def test_non_main_thread_is_rejected_instead_of_running_unbounded(self):
        with patch.object(runtime.threading, "current_thread", return_value=object()):
            with self.assertRaisesRegex(RuntimeError, "POSIX main thread"):
                with runtime.alarm_deadline(1, "discovery"):
                    self.fail("Unsupported execution must not start the API")

    @unittest.skipUnless(hasattr(signal, "setitimer"), "Actual POSIX alarm tested on Linux")
    def test_actual_posix_alarm_interrupts_blocking_wait(self):
        previous = signal.getsignal(signal.SIGALRM)
        with self.assertRaises(TimeoutError):
            with runtime.alarm_deadline(0.01, "blocking call"):
                time.sleep(0.1)
        self.assertEqual(signal.getsignal(signal.SIGALRM), previous)


if __name__ == "__main__":
    unittest.main()
