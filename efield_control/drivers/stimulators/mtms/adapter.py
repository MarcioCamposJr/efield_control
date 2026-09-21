from __future__ import annotations

from typing import Protocol


class MtmsApiClient(Protocol):
    """Internal contract implemented by the future MTMSApi wrapper.

    The concrete implementation will translate the vendor's ROS-backed API
    into these methods after its firing and shutdown semantics are confirmed.
    """

    def connect(self) -> None: ...

    def trigger(self) -> None: ...

    def close(self) -> None: ...


class MtmsApiPulse:
    """Expose an mTMS API client through the application's PulseSource port."""

    def __init__(self, client: MtmsApiClient) -> None:
        self._client = client
        self._connected = False

    def connect(self) -> None:
        if not self._connected:
            self._client.connect()
            self._connected = True

    def fire(self) -> None:
        if not self._connected:
            raise RuntimeError("The mTMS API client is not connected.")
        self._client.trigger()

    def close(self) -> None:
        if self._connected:
            self._client.close()
            self._connected = False

    def __enter__(self) -> "MtmsApiPulse":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

