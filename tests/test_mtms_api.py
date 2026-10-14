"""Hardware-free mTMS lifecycle tests, runnable with unittest or pytest."""

import builtins
import math
import os
import signal
import sys
import unittest
from contextlib import nullcontext
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from efield_control.drivers.stimulators.mtms import (
    MtmsApiPulse, MtmsSingleChannelClient, MtmsSingleChannelSettings,
)


class FakeExecutionCondition:
    IMMEDIATE = "immediate"
    TIMED = "timed"


class FakeVendorApi:
    def __init__(self, verbose=True):
        self.events = []
        self.node = SimpleNamespace(system_state=SimpleNamespace(
            device_state=SimpleNamespace(value=0), startup_error=SimpleNamespace(value=0)))
        self.session_state = 0
        self.device_states = []
        self.session_states = []
        self.feedback_errors = {}
        self.event_id = 0
        self.fail_stop = False

    def record(self, name, **values):
        self.events.append((name, values))

    def start_device_without_waiting(self):
        self.record("start_device")
        self.node.system_state.device_state.value = 2

    def get_device_state(self):
        if self.device_states:
            value = self.device_states[0]
            if len(self.device_states) > 1:
                self.device_states.pop(0)
            self.node.system_state.device_state.value = value
        return self.node.system_state.device_state.value

    def start_session_without_waiting(self):
        self.record("start_session")
        self.session_state = 2

    def get_session_state(self):
        if self.session_states:
            value = self.session_states[0]
            if len(self.session_states) > 1:
                self.session_states.pop(0)
            self.session_state = value
        return self.session_state

    def stop_session_without_waiting(self):
        self.record("stop_session")
        self.session_states = []
        self.session_state = 0

    def stop_device_without_waiting(self):
        self.record("stop_device")
        if not self.fail_stop:
            self.device_states = []
            self.node.system_state.device_state.value = 0

    def request(self, name, values):
        self.record(name, **values)
        self.event_id += 1
        return self.event_id

    def send_charge(self, **values):
        return self.request("send_charge", values)

    def send_pulse(self, **values):
        return self.request("send_pulse", values)

    def send_trigger_out(self, **values):
        return self.request("send_trigger_out", values)

    def send_discharge(self, **values):
        return self.request("send_discharge", values)

    def wait_for_completion(self):
        self.record("wait_for_completion")

    def get_event_feedback(self, event_id):
        value = self.feedback_errors.get(event_id, 0)
        return None if value is None else SimpleNamespace(value=value)

    def get_default_waveform(self, channel):
        self.record("get_default_waveform", channel=channel)
        return "default-waveform"

    def get_time(self):
        self.record("get_time")
        return 100.0

    def end(self):
        self.record("end")


def fake_guard(timeout, description):
    # Synchronous fakes do not need a POSIX timer; state loops still enforce deadlines.
    return nullcontext()


class MtmsTests(unittest.TestCase):
    def client(self, api=None, **settings):
        api = api if api is not None else FakeVendorApi()
        client = MtmsSingleChannelClient(
            MtmsSingleChannelSettings(**settings), api_factory=lambda: api,
            execution_condition=FakeExecutionCondition, deadline_guard=fake_guard,
        )
        return client, api

    def names(self, api):
        return [name for name, _ in api.events]

    def test_adapter_delegates_lifecycle(self):
        client = Mock()
        with MtmsApiPulse(client) as pulse:
            pulse.fire()
        self.assertEqual([call[0] for call in client.mock_calls], ["connect", "trigger", "close"])

    def test_adapter_requires_connection(self):
        with self.assertRaisesRegex(RuntimeError, "not connected"):
            MtmsApiPulse(Mock()).fire()

    def test_operational_device_and_started_session_are_required(self):
        client, api = self.client()
        api.device_states = [0, 1, 2]
        api.session_states = [0, 1, 2]
        client.connect()
        self.assertTrue(client._session_started)
        client.close()
        self.assertEqual(self.names(api), ["start_device", "start_session", "stop_session", "stop_device", "end"])

    def test_failed_device_startup_never_starts_session(self):
        client, api = self.client()
        api.node.system_state.startup_error.value = 6
        api.device_states = [1, 3, 0]
        with self.assertRaisesRegex(RuntimeError, "Not operational"):
            client.connect()
        self.assertNotIn("start_session", self.names(api))
        self.assertEqual(self.names(api), ["start_device", "stop_device", "end"])
        self.assertIsNone(client._api)

    def test_failed_startup_without_alarm_never_starts_session(self):
        client, api = self.client()
        api.device_states = [1, 3, 0]
        with self.assertRaisesRegex(RuntimeError, "Not operational"):
            client.connect()
        self.assertNotIn("start_session", self.names(api))

    def test_device_startup_has_wall_clock_deadline(self):
        client, api = self.client(device_startup_timeout_s=0.01)
        api.device_states = [0]
        with self.assertRaises(TimeoutError):
            client.connect()
        self.assertNotIn("start_session", self.names(api))
        self.assertIn("end", self.names(api))

    def test_session_startup_timeout_still_attempts_session_stop(self):
        client, api = self.client(session_startup_timeout_s=0.01)
        api.session_states = [0]
        with self.assertRaises(TimeoutError):
            client.connect()
        self.assertIn("stop_session", self.names(api))
        self.assertIn("stop_device", self.names(api))
        self.assertIn("end", self.names(api))

    def test_shutdown_timeout_preserves_startup_failure_and_still_ends_api(self):
        client, api = self.client(shutdown_timeout_s=0.01)
        api.node.system_state.startup_error.value = 6
        api.fail_stop = True
        api.device_states = [1, 0]
        api.stop_device_without_waiting = Mock(side_effect=TimeoutError("stop timed out"))
        with self.assertRaisesRegex(RuntimeError, "Not operational.*cleanup also failed"):
            client.connect()
        self.assertIn("end", self.names(api))
        self.assertIsNone(client._api)

    def test_false_service_response_blocks_session(self):
        client, api = self.client()
        api.start_device_without_waiting = Mock(side_effect=RuntimeError("service rejected"))
        with self.assertRaisesRegex(RuntimeError, "service rejected"):
            client.connect()
        self.assertNotIn("start_session", self.names(api))

    def test_pulse_sequence_and_synchronized_timestamps(self):
        client, api = self.client(channel=1, target_voltage_v=15, reverse_polarity=True,
                                  schedule_lead_s=1.5, minimum_inter_pulse_interval_s=0)
        client.connect()
        client.trigger()
        client.close()
        self.assertEqual(self.names(api), [
            "start_device", "start_session", "send_charge", "wait_for_completion",
            "get_default_waveform", "get_time", "send_pulse", "send_trigger_out",
            "wait_for_completion", "send_discharge", "wait_for_completion",
            "stop_session", "stop_device", "end",
        ])
        pulse, marker = api.events[6][1], api.events[7][1]
        self.assertEqual(pulse["time"], 101.5)
        self.assertEqual(marker["time"], pulse["time"])
        self.assertTrue(pulse["reverse_polarity"])
        self.assertEqual(api.events[9][1]["target_voltage"], 0)  # Vendor may clamp this to 3 V.

    def test_charge_error_or_missing_feedback_prevents_pulse(self):
        for error in (4, None):
            client, api = self.client()
            api.feedback_errors[1] = error
            client.connect()
            with self.assertRaises(RuntimeError):
                client.trigger()
            self.assertNotIn("send_pulse", self.names(api))
            client.close()

    def test_readiness_is_rechecked_before_charging(self):
        client, api = self.client()
        client.connect()
        api.node.system_state.device_state.value = 0
        with self.assertRaisesRegex(RuntimeError, "pulse blocked"):
            client.trigger()
        self.assertNotIn("send_charge", self.names(api))
        client.close()

    def test_pulse_and_marker_errors_are_not_reported_as_success(self):
        for event_id, description in ((2, "pulse"), (3, "trigger out")):
            with self.subTest(event_id=event_id):
                client, api = self.client()
                api.feedback_errors[event_id] = 4
                client.connect()
                with self.assertRaisesRegex(RuntimeError, description + " failed"):
                    client.trigger()
                client.close()
                self.assertIn("send_discharge", self.names(api))

    def test_uncertain_charge_request_still_attempts_discharge_on_close(self):
        client, api = self.client()
        client.connect()
        api.send_charge = Mock(side_effect=TimeoutError("response missing"))
        with self.assertRaises(TimeoutError):
            client.trigger()
        client.close()
        self.assertIn("send_discharge", self.names(api))

    def test_uncertain_pulse_request_blocks_immediate_retry(self):
        client, api = self.client()
        client.connect()
        api.send_pulse = Mock(side_effect=TimeoutError("response missing"))
        with self.assertRaises(TimeoutError):
            client.trigger()
        with self.assertRaisesRegex(RuntimeError, "configured minimum"):
            client.trigger()
        api.send_pulse.assert_called_once()
        client.close()

    def test_session_stop_failure_does_not_skip_device_stop_or_api_cleanup(self):
        client, api = self.client()
        client.connect()
        api.stop_session_without_waiting = Mock(side_effect=TimeoutError("session stop"))
        with self.assertRaisesRegex(TimeoutError, "session stop"):
            client.close()
        self.assertIn("stop_device", self.names(api))
        self.assertIn("end", self.names(api))

    def test_vendor_lifecycle_does_not_access_ros_or_node_internals(self):
        api = FakeVendorApi()
        # Public methods remain usable without exposing the vendor's node.
        class PublicApi:
            def __getattr__(self, name):
                if name == "node":
                    raise AssertionError("The integration must use public MTMSApi methods")
                return getattr(api, name)
        client, _ = self.client(PublicApi())
        with patch.dict(sys.modules, {"rclpy": None}):
            client.connect()
            client.trigger()
            client.close()
        self.assertIn("end", self.names(api))

    def test_invalid_timeouts_and_voltage_are_rejected(self):
        for values in ({"operation_timeout_s": 0}, {"device_startup_timeout_s": math.nan},
                       {"shutdown_timeout_s": -1}, {"target_voltage_v": 21}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                MtmsSingleChannelSettings(**values)

    def test_constructor_timeout_restores_interrupt_handler(self):
        original = signal.getsignal(signal.SIGINT)
        def factory():
            signal.signal(signal.SIGINT, lambda *args: None)
            raise TimeoutError("API discovery timed out")
        client = MtmsSingleChannelClient(MtmsSingleChannelSettings(), api_factory=factory,
                                        execution_condition=FakeExecutionCondition, deadline_guard=fake_guard)
        with self.assertRaises(TimeoutError):
            client.connect()
        self.assertEqual(signal.getsignal(signal.SIGINT), original)

    def test_close_restores_vendor_sigint_override(self):
        original = signal.getsignal(signal.SIGINT)
        api = FakeVendorApi()
        def factory():
            signal.signal(signal.SIGINT, lambda *args: None)
            return api
        client = MtmsSingleChannelClient(MtmsSingleChannelSettings(), api_factory=factory,
                                        execution_condition=FakeExecutionCondition, deadline_guard=fake_guard)
        client.connect()
        client.close()
        self.assertEqual(signal.getsignal(signal.SIGINT), original)

    def test_imports_do_not_prepare_or_modify_environment(self):
        vendor = ModuleType("MTMSApi")
        vendor.MTMSApi = FakeVendorApi
        messages = ModuleType("mtms_event_interfaces.msg")
        messages.ExecutionCondition = FakeExecutionCondition
        with patch.dict(sys.modules, {"MTMSApi": vendor, "mtms_event_interfaces.msg": messages, "rclpy": None}):
            before, paths = dict(os.environ), list(sys.path)
            MtmsSingleChannelClient.validate_environment()
            self.assertEqual(dict(os.environ), before)
            self.assertEqual(sys.path, paths)

    def test_missing_imports_fail_without_preparing_environment(self):
        original_import = builtins.__import__
        for missing in ("MTMSApi", "mtms_event_interfaces.msg"):
            def controlled_import(name, *args, **kwargs):
                if name == missing:
                    raise ModuleNotFoundError(name, name=name)
                if name == "MTMSApi":
                    return SimpleNamespace(MTMSApi=FakeVendorApi)
                return original_import(name, *args, **kwargs)
            with patch("builtins.__import__", controlled_import):
                with self.assertRaisesRegex(RuntimeError, "No environment setup"):
                    MtmsSingleChannelClient(MtmsSingleChannelSettings()).connect()


if __name__ == "__main__":
    unittest.main()
