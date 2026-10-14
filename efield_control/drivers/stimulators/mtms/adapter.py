"""Expose the mTMS client as a pulse source for AcquisitionService."""

from __future__ import annotations

from typing import Protocol


class MtmsApiClient(Protocol):
    """Contract implemented by MtmsSingleChannelClient: connect, trigger, and close."""

    def connect(self) -> None: ...

    def trigger(self) -> None: ...

    def close(self) -> None: ...


class MtmsApiPulse:
    """Expose an mTMS API client through the application's PulseSource port."""

    def __init__(self, client: MtmsApiClient) -> None:
        self._client = client
        self._connected = False

    def connect(self) -> None:
        """Delegate mTMS device and session initialization to the client."""
        if not self._connected:
            self._client.connect()
            self._connected = True

    def fire(self) -> None:
        """Translate the acquisition service fire call into the mTMS client trigger call."""
        if not self._connected:
            raise RuntimeError("The mTMS API client is not connected.")
        self._client.trigger()

    def close(self) -> None:
        """Delegate discharge and session shutdown to the mTMS client."""
        if self._connected:
            self._client.close()
            self._connected = False

    def __enter__(self) -> "MtmsApiPulse":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

