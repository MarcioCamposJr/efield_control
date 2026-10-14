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
imports before creating the API instance and calling `start_device()` and
`start_session()`.

`MtmsApiPulse` is the application-facing lifecycle adapter. Its
`MtmsSingleChannelClient` implementation uses the API sequence supplied with
this project:

1. charge the selected zero-indexed channel;
2. obtain that channel's default waveform;
3. schedule `send_pulse(...)` and `send_trigger_out(...)` for the same mTMS
   timestamp;
4. wait for both operations to complete;
5. optionally discharge the selected channel to 0 V.

`send_pulse(...)` performs stimulation. `send_trigger_out(...)` is only the
synchronization marker received by the Red Pitaya. Single-channel intensity is
configured as capacitor target voltage, not percentage or electric-field V/m.
The `[mtms]` section of `config/default.toml` contains the channel allowlist,
independent voltage ceiling, trigger-out settings, rate limit, and discharge
behavior. These defaults must be reviewed against the installation's approved
hardware and protocol limits before use.
