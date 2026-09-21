from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable


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

    def __post_init__(self) -> None:
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
    ) -> None:
        self.settings = settings
        self._api_factory = api_factory
        self._execution_condition = execution_condition
        self._monotonic = monotonic
        self._api: Any | None = None
        self._device_started = False
        self._session_started = False
        self._charged = False
        self._last_pulse_at: float | None = None

    @staticmethod
    def validate_environment() -> None:
        try:
            import rclpy  # noqa: F401
            import MTMSApi  # noqa: F401
            from mtms_event_interfaces.msg import ExecutionCondition  # noqa: F401
        except ImportError as error:
            raise RuntimeError(
                "The mTMS API environment is unavailable. Start the command "
                "through run_with_mtms.py on the ROS 2 Linux host."
            ) from error

    def _load_vendor_api(self) -> tuple[Callable[[], Any], Any]:
        if self._api_factory is not None and self._execution_condition is not None:
            return self._api_factory, self._execution_condition

        self.validate_environment()
        from MTMSApi import MTMSApi
        from mtms_event_interfaces.msg import ExecutionCondition

        return MTMSApi, ExecutionCondition

    def connect(self) -> None:
        if self._api is not None:
            return

        api_factory, execution_condition = self._load_vendor_api()
        self._execution_condition = execution_condition
        self._api = api_factory()
        try:
            self._api.start_device()
            self._device_started = True
            self._api.start_session()
            self._session_started = True
        except BaseException:
            self._shutdown()
            raise

    def trigger(self) -> None:
        api = self._require_api()
        self._check_rate_limit()
        condition = self._execution_condition

        api.send_charge(
            channel=self.settings.channel,
            target_voltage=self.settings.target_voltage_v,
            execution_condition=condition.IMMEDIATE,
        )
        # Mark the channel conservatively as soon as charging is requested so
        # shutdown still attempts a discharge if completion reporting fails.
        self._charged = True
        api.wait_for_completion()

        waveform = api.get_default_waveform(self.settings.channel)
        scheduled_time = api.get_time() + self.settings.schedule_lead_s
        api.send_pulse(
            channel=self.settings.channel,
            waveform=waveform,
            execution_condition=condition.TIMED,
            time=scheduled_time,
            reverse_polarity=self.settings.reverse_polarity,
        )
        api.send_trigger_out(
            port=self.settings.trigger_out_port,
            duration_us=self.settings.trigger_out_duration_us,
            execution_condition=condition.TIMED,
            time=scheduled_time,
        )
        api.wait_for_completion()
        self._last_pulse_at = self._monotonic()

        if self.settings.discharge_after_pulse:
            self._discharge()

    def _check_rate_limit(self) -> None:
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
        if self._api is None or not self._charged:
            return
        self._api.send_discharge(
            channel=self.settings.channel,
            target_voltage=0,
            execution_condition=self._execution_condition.IMMEDIATE,
        )
        self._api.wait_for_completion()
        self._charged = False

    def _require_api(self) -> Any:
        if self._api is None or not self._session_started:
            raise RuntimeError("The mTMS API client is not connected.")
        return self._api

    def close(self) -> None:
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
            return

        first_error: BaseException | None = None
        if self._session_started:
            try:
                self._api.stop_session()
            except BaseException as error:
                first_error = error
            finally:
                self._session_started = False
        if self._device_started:
            try:
                self._api.stop_device()
            except BaseException as error:
                if first_error is None:
                    first_error = error
            finally:
                self._device_started = False
        end = getattr(self._api, "end", None)
        if callable(end):
            try:
                end()
            except BaseException as error:
                if first_error is None:
                    first_error = error
        self._api = None
        if first_error is not None:
            raise first_error
