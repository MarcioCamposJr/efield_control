# mTMS API integration

The mTMS API is an external Python module. The integration uses the current
Python environment, where these imports must already work:

```python
from MTMSApi import MTMSApi
from mtms_event_interfaces.msg import ExecutionCondition
```

The project does not install packages, run shell or ROS setup scripts, search
for an API installation, or modify environment variables or the Python import
path. Missing imports stop the operation with an error; no environment repair
is attempted.

Run commands directly using the Python environment that already has the API:

```bash
python -m efield_control.cli show-config
```

`show-config` only displays configuration; it does not connect to the device.
Selecting `pulse.source = "mtms_api"` for a hardware operation validates the
imports before creating the API instance. The client requests device startup,
waits for `Operational`, then requests a session and waits for `Started`.
It never starts a session after failed device startup. A successful service response alone
does not establish that the equipment is ready.

Public API calls have best-effort deadlines configured in the `[mtms]` TOML section:

| Setting | Default | Applies to |
| --- | --- | --- |
| `service_discovery_timeout_s` | 30 s | API construction and ROS service discovery |
| `device_startup_timeout_s` | 30 s | Device reaching Operational |
| `session_startup_timeout_s` | 10 s | Session reaching Started |
| `operation_timeout_s` | 10 s | Complete charge, pulse, marker and optional discharge sequence |
| `shutdown_timeout_s` | 10 s | Each discharge, session stop, device stop and API cleanup step |

The real API integration runs on the ROS Linux host's main Python thread.
It uses a temporary POSIX alarm around public API calls. Native waits inside
the SDK may delay Python signal handling, so these are not guaranteed hard
timeouts. The integration does not import `rclpy`, access the internal ROS
node, replace SDK methods, or send ROS service requests itself. ROS remains
an internal dependency of MTMSApi. Existing signal handlers are restored;
vendor source files and machine configuration are untouched. Windows and background
threads are rejected because they cannot provide this deadline guard.
Detailed startup alarms are left to the SDK/controller diagnostics because
this SDK has no public getter for the startup error code. If construction
fails before returning an API instance, this client cannot call `end()`;
partial initialization remains the SDK's responsibility.

On failure, cleanup attempts to stop any requested session/device and close
the API, even if an earlier cleanup step fails. A timeout does not prove that
the hardware accepted or completed a stop command. The connection example
requires confirmed startup and shutdown before reporting success; it does
not charge or stimulate any channel.

`MtmsApiPulse` is the application-facing lifecycle adapter. Its
`MtmsSingleChannelClient` implementation uses the API sequence supplied with
this project:

1. charge the selected zero-indexed channel;
2. obtain that channel's default waveform;
3. schedule `send_pulse(...)` and `send_trigger_out(...)` for the same mTMS
   timestamp;
4. wait for both operations and verify their event feedback;
5. optionally request discharge to the API's minimum target voltage.

Charge and discharge feedback are also checked. The referenced SDK clamps
a discharge request of 0 V to 3 V, so this integration does not claim that
the capacitor reaches zero voltage.

`send_pulse(...)` performs stimulation. `send_trigger_out(...)` is only the
synchronization marker received by the Red Pitaya. Single-channel intensity is
configured as capacitor target voltage, not percentage or electric-field V/m.
The `[mtms]` section of `config/default.toml` contains the channel allowlist,
independent voltage ceiling, trigger-out settings, rate limit, and discharge
behavior. These defaults must be reviewed against the installation's approved
hardware and protocol limits before use.
