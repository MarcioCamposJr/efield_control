"""Use the existing MTMSApi to operate one channel and its synchronization marker."""

from __future__ import annotations

import time
import math
import signal
import threading
from dataclasses import dataclass
from typing import Any, Callable

from .runtime import alarm_deadline


@dataclass(frozen=True, slots=True)
class MtmsSingleChannelSettings:
    """Validated settings for one mTMS channel and its synchronization marker."""

    channel: int = 0
    allowed_channels: tuple[int, ...] = (0, 1)
    target_voltage_v: float = 20.0
    maximum_target_voltage_v: float = 20.0
    reverse_polarity: bool = False
    trigger_out_port: int = 1
    trigger_out_duration_us: int = 1000
    schedule_lead_s: float = 1.0
    minimum_inter_pulse_interval_s: float = 2.0
    discharge_after_pulse: bool = True
    service_discovery_timeout_s: float = 30.0
    device_startup_timeout_s: float = 30.0
    session_startup_timeout_s: float = 10.0
    operation_timeout_s: float = 10.0
    shutdown_timeout_s: float = 10.0

    def __post_init__(self) -> None:
        if any(not math.isfinite(value) or value <= 0 for value in (
            self.service_discovery_timeout_s, self.device_startup_timeout_s,
            self.session_startup_timeout_s, self.operation_timeout_s, self.shutdown_timeout_s,
        )):
            raise ValueError("mTMS timeouts must be finite and positive.")
        allowed = tuple(int(value) for value in self.allowed_channels)
        object.__setattr__(self, "allowed_channels", allowed)
        if not allowed or any(value < 0 for value in allowed):
            raise ValueError("mTMS allowed channels must be non-negative.")
        if len(set(allowed)) != len(allowed):
            raise ValueError("mTMS allowed channels cannot contain duplicates.")
        if self.channel not in allowed:
            raise ValueError(
                f"mTMS channel {self.channel} is not in allowed_channels {allowed}."
            )
        if self.maximum_target_voltage_v <= 0:
            raise ValueError("mTMS maximum target voltage must be positive.")
        if not 0 < self.target_voltage_v <= self.maximum_target_voltage_v:
            raise ValueError(
                "mTMS target voltage must be positive and cannot exceed the "
                "configured maximum target voltage."
            )
        if self.trigger_out_port < 0:
            raise ValueError("mTMS trigger-out port must be non-negative.")
        if self.trigger_out_duration_us <= 0:
            raise ValueError("mTMS trigger-out duration must be positive.")
        if self.schedule_lead_s <= 0:
            raise ValueError("mTMS schedule lead time must be positive.")
        if self.minimum_inter_pulse_interval_s < 0:
            raise ValueError("mTMS minimum inter-pulse interval cannot be negative.")


class MtmsSingleChannelClient:
    """Concrete MTMSApi wrapper for synchronized single-channel pulses.

    The trigger-out marker and stimulation pulse are scheduled using the same
    device timestamp so the Red Pitaya can use that marker as its external
    acquisition trigger.
    """

    def __init__(
        self,
        settings: MtmsSingleChannelSettings,
        *,
        api_factory: Callable[[], Any] | None = None,
        execution_condition: Any | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        deadline_guard: Callable = alarm_deadline,
    ) -> None:
        self.settings = settings
        self._api_factory = api_factory
        self._execution_condition = execution_condition
        self._monotonic = monotonic
        self._deadline_guard = deadline_guard
        self._deadline: float | None = None
        self._original_sigint = None
        self._api: Any | None = None
        self._device_started = False
        self._session_started = False
        self._charged = False
        self._last_pulse_at: float | None = None

    @staticmethod
    def validate_environment() -> None:
        """Check imports in the current environment without preparing it."""
        MtmsSingleChannelClient._import_vendor_api()

    @staticmethod
    def _import_vendor_api() -> tuple[Callable[[], Any], Any]:
        try:
            from MTMSApi import MTMSApi
            from mtms_event_interfaces.msg import ExecutionCondition
        except ImportError as error:
            raise RuntimeError(
                "The mTMS API is unavailable in the current Python environment. "
                "MTMSApi and mtms_event_interfaces.msg.ExecutionCondition "
                "must already be importable. No environment setup is performed."
            ) from error
        return MTMSApi, ExecutionCondition

    def _load_vendor_api(self) -> tuple[Callable[[], Any], Any]:
        if self._api_factory is not None and self._execution_condition is not None:
            return self._api_factory, self._execution_condition

        return self._import_vendor_api()

    def connect(self) -> None:
        """Instantiate the API, start the device, and open the operating session.

        The external library handles communication; this client does not prepare
        ROS, import paths, or Python environment settings.
        """
        if self._api is not None:
            return

        api_factory, execution_condition = self._load_vendor_api()
        self._execution_condition = execution_condition
        if threading.current_thread() is threading.main_thread():
            self._original_sigint = signal.getsignal(signal.SIGINT)
        try:
            self._api = self._call(
                lambda: api_factory() if self._api_factory is not None else api_factory(verbose=False),
                self.settings.service_discovery_timeout_s, "API creation/service discovery",
            )
            # Mark requests conservatively before sending: a timeout may follow acceptance.
            self._device_started = True
            self._call(self._start_device, self.settings.device_startup_timeout_s, "device startup")
            self._session_started = True
            self._call(self._start_session, self.settings.session_startup_timeout_s, "session startup")
        except BaseException as error:
            try:
                self._shutdown()
            except Exception as cleanup_error:
                if isinstance(error, Exception):
                    raise RuntimeError(f"{error}; cleanup also failed: {cleanup_error}") from error
            raise

    def _call(self, function: Callable, timeout_s: float, description: str):
        previous = self._deadline
        self._deadline = self._monotonic() + timeout_s
        try:
            with self._deadline_guard(timeout_s, description):
                return function()
        finally:
            self._deadline = previous

    def _remaining(self) -> float:
        remaining = (self._deadline - self._monotonic()) if self._deadline is not None else 0
        if remaining <= 0:
            raise TimeoutError("mTMS operation deadline expired.")
        return remaining

    def _start_device(self) -> None:
        self._api.start_device_without_waiting()
        saw_startup = False
        while True:
            self._remaining()
            state = self._api.get_device_state()
            if state == 2:  # DeviceState.OPERATIONAL
                return
            saw_startup = saw_startup or state == 1
            if saw_startup and state == 0:
                raise RuntimeError("mTMS device returned to Not operational during startup.")

    def _start_session(self) -> None:
        self._api.start_session_without_waiting()
        while True:
            self._remaining()
            if self._api.get_device_state() != 2:
                raise RuntimeError("mTMS device is not operational; session startup aborted.")
            if self._api.get_session_state() == 2:  # Session.STARTED
                return

    def trigger(self) -> None:
        """Charge the channel, schedule stimulation and its marker, and wait for completion."""
        self._require_api()
        self._check_rate_limit()
        self._call(self._trigger, self.settings.operation_timeout_s, "charge/pulse/trigger")

    def _trigger(self) -> None:
        api = self._require_api()
        if api.get_device_state() != 2 or api.get_session_state() != 2:
            raise RuntimeError("mTMS is not operational with a started session; pulse blocked.")
        condition = self._execution_condition

        # target_voltage is the capacitor voltage in V, rather than intensity in percent.
        self._charged = True
        charge_id = api.send_charge(
            channel=self.settings.channel,
            target_voltage=self.settings.target_voltage_v,
            execution_condition=condition.IMMEDIATE,
        )
        # Mark the channel conservatively as soon as charging is requested so
        # shutdown still attempts a discharge if completion reporting fails.
        api.wait_for_completion()
        self._check_event(charge_id, "charge")

        waveform = api.get_default_waveform(self.settings.channel)
        scheduled_time = api.get_time() + self.settings.schedule_lead_s
        # Stimulate the coil at the scheduled time on the mTMS device clock.
        # Reserve the rate limit before sending: timeout does not prove rejection.
        self._last_pulse_at = self._monotonic() + self.settings.schedule_lead_s
        pulse_id = api.send_pulse(
            channel=self.settings.channel,
            waveform=waveform,
            execution_condition=condition.TIMED,
            time=scheduled_time,
            reverse_polarity=self.settings.reverse_polarity,
        )
        # Mark the same scheduled time on the Red Pitaya trigger input.
        marker_id = api.send_trigger_out(
            port=self.settings.trigger_out_port,
            duration_us=self.settings.trigger_out_duration_us,
            execution_condition=condition.TIMED,
            time=scheduled_time,
        )
        api.wait_for_completion()
        self._check_event(pulse_id, "pulse")
        self._check_event(marker_id, "trigger out")
        self._last_pulse_at = self._monotonic()

        if self.settings.discharge_after_pulse:
            self._discharge_request()

    def _check_event(self, event_id: int, description: str) -> None:
        feedback = self._api.get_event_feedback(event_id)
        if feedback is None:
            raise RuntimeError(f"mTMS {description} has no completion feedback (event={event_id}).")
        if feedback.value != 0:
            raise RuntimeError(f"mTMS {description} failed (event={event_id}, error={feedback.value}).")

    def _check_rate_limit(self) -> None:
        """Reject a pulse requested too soon without automatically waiting out the interval."""
        if self._last_pulse_at is None:
            return
        elapsed = self._monotonic() - self._last_pulse_at
        minimum = self.settings.minimum_inter_pulse_interval_s
        if elapsed < minimum:
            raise RuntimeError(
                f"mTMS pulse blocked: {elapsed:.3f} s since the previous pulse; "
                f"the configured minimum is {minimum:.3f} s."
            )

    def _discharge(self) -> None:
        """Request minimum discharge; the vendor currently clamps 0 V requests to 3 V."""
        if self._api is None or not self._charged:
            return
        self._call(self._discharge_request, self.settings.shutdown_timeout_s, "channel discharge")

    def _discharge_request(self) -> None:
        discharge_id = self._api.send_discharge(
            channel=self.settings.channel,
            target_voltage=0,
            execution_condition=self._execution_condition.IMMEDIATE,
        )
        self._api.wait_for_completion()
        self._check_event(discharge_id, "discharge")
        self._charged = False

    def _require_api(self) -> Any:
        if self._api is None or not self._session_started:
            raise RuntimeError("The mTMS API client is not connected.")
        return self._api

    def close(self) -> None:
        """Attempt discharge and session/device shutdown, propagating the first error."""
        first_error: BaseException | None = None
        try:
            self._discharge()
        except BaseException as error:
            first_error = error
        try:
            self._shutdown()
        except BaseException as error:
            if first_error is None:
                first_error = error
        if first_error is not None:
            raise first_error

    def _shutdown(self) -> None:
        if self._api is None:
            self._restore_sigint()
            return

        first_error: BaseException | None = None
        if self._session_started:
            try:
                self._call(self._stop_session, self.settings.shutdown_timeout_s, "session shutdown")
            except BaseException as error:
                first_error = error
            finally:
                self._session_started = False
        if self._device_started:
            try:
                self._call(self._stop_device, self.settings.shutdown_timeout_s, "device shutdown")
            except BaseException as error:
                if first_error is None:
                    first_error = error
            finally:
                self._device_started = False
        end = getattr(self._api, "end", None)
        if callable(end):
            try:
                self._call(end, self.settings.shutdown_timeout_s, "API shutdown")
            except BaseException as error:
                if first_error is None:
                    first_error = error
        self._api = None
        self._restore_sigint()
        if first_error is not None:
            raise first_error

    def _stop_session(self) -> None:
        self._api.stop_session_without_waiting()
        while True:
            self._remaining()
            if self._api.get_session_state() == 0:
                return

    def _stop_device(self) -> None:
        self._api.stop_device_without_waiting()
        while True:
            self._remaining()
            if self._api.get_device_state() == 0:
                return

    def _restore_sigint(self) -> None:
        if self._original_sigint is not None:
            signal.signal(signal.SIGINT, self._original_sigint)
            self._original_sigint = None
