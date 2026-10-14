"""Red Pitaya SCPI commands for acquisition and digital trigger output."""

from __future__ import annotations

import time
from dataclasses import dataclass

from efield_control.domain import Waveform


@dataclass(frozen=True, slots=True)
class RedPitayaSettings:
    host: str
    port: int = 5000
    decimation: int = 8
    trigger_source: str = "EXT_PE"
    trigger_delay: int = 0
    high_voltage: bool = True

    @property
    def sample_rate_hz(self) -> float:
        return 125e6 / self.decimation


class RedPitayaAcquisition:
    """Legacy SCPI client adapter that does not connect during module import."""

    def __init__(self, settings: RedPitayaSettings, client=None) -> None:
        """Open the SCPI connection on construction unless a client is supplied."""
        self.settings = settings
        if client is None:
            from .scpi import scpi

            client = scpi(settings.host, timeout=30, port=settings.port)
        self._client = client

    @property
    def client(self):
        """Client that can be shared with a digital output on the same device."""
        return self._client

    def _send(self, command: str) -> None:
        self._client.tx_txt(command)

    def _query(self, command: str) -> str:
        self._send(command)
        return self._client.rx_txt().strip()

    def arm(self) -> None:
        """Prepare Red Pitaya to capture CH1/CH2 on the configured trigger."""
        # Reset the previous acquisition before configuring the next capture.
        self._send("ACQ:RST")
        time.sleep(0.05)
        if self.settings.high_voltage:
            # HV selects the channel input range; it does not energize mTMS.
            self._send("ACQ:SOUR1:GAIN HV")
            self._send("ACQ:SOUR2:GAIN HV")
        self._send("ACQ:DATA:FORMAT ASCII")
        self._send("ACQ:DATA:UNITS VOLTS")
        # Decimation sets the sampling rate; delay positions the trigger in the buffer.
        self._send(f"ACQ:DEC {self.settings.decimation}")
        self._send(f"ACQ:TRIG:DLY {self.settings.trigger_delay}")
        self._send("ACQ:START")
        time.sleep(0.05)
        # The default EXT_PE selects the rising edge of the external trigger.
        self._send(f"ACQ:TRIG {self.settings.trigger_source}")

    def wait_for_trigger(self, timeout_s: float) -> None:
        """Poll Red Pitaya until TD indicates that the trigger was detected."""
        self._wait_for("ACQ:TRIG:STAT?", "TD", timeout_s, "trigger")

    def wait_until_ready(self, timeout_s: float) -> None:
        """Wait until the Red Pitaya buffer is filled before reading the waveform."""
        self._wait_for("ACQ:TRIG:FILL?", "1", timeout_s, "buffer")

    def _wait_for(
        self, command: str, expected: str, timeout_s: float, description: str
    ) -> None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() <= deadline:
            if self._query(command) == expected:
                return
            time.sleep(0.001)
        raise TimeoutError(f"Timed out while waiting for Red Pitaya {description}.")

    def read_waveform(self) -> Waveform:
        """Read CH1 and CH2 buffers over SCPI and convert text responses into samples."""
        ch1 = self._parse(self._query("ACQ:SOUR1:DATA?"))
        ch2 = self._parse(self._query("ACQ:SOUR2:DATA?"))
        return Waveform.from_iterables(ch1, ch2, self.settings.sample_rate_hz)

    @staticmethod
    def _parse(response: str) -> tuple[float, ...]:
        content = response.strip().strip("{}")
        try:
            values = tuple(float(value) for value in content.split(",") if value.strip())
        except ValueError as exc:
            raise RuntimeError("The SCPI response contains an invalid sample.") from exc
        if not values:
            raise RuntimeError("The Red Pitaya returned an empty channel.")
        return values

    def close(self) -> None:
        """Close the SCPI connection, which may also be shared with the digital output."""
        self._client.close()


class RedPitayaDigitalPulse:
    """Digital pulse for setups in which the Red Pitaya fires the TMS."""

    def __init__(
        self,
        client,
        pin: str = "DIO1_P",
        pulse_s: float = 0.010,
        active_high: bool = True,
    ) -> None:
        self._client = client
        self.pin = pin
        self.pulse_s = pulse_s
        self.active_high = active_high
        self._client.tx_txt(f"DIG:PIN:DIR OUT,{pin}")
        self._write(False)

    def _write(self, active: bool) -> None:
        level = int(active == self.active_high)
        self._client.tx_txt(f"DIG:PIN {self.pin},{level}")

    def fire(self) -> None:
        """Generate a pulse on the Red Pitaya digital pin connected to the stimulator."""
        self._write(False)
        time.sleep(0.01)
        self._write(True)
        time.sleep(self.pulse_s)
        self._write(False)
