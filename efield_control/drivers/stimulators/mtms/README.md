# mTMS API integration

The mTMS API is a ROS 2-backed Python module stored outside this repository.
Use the root-level `run_with_mtms.py` bootstrap on the Linux mTMS host. It
sources ROS 2 and the compiled mTMS workspace, adds the directory containing
`MTMSApi.py` to `PYTHONPATH`, validates all required imports, and only then
starts the requested project command.

Configure the external installation in `.env`:

```dotenv
EFIELD_MTMS_API_PATH=/home/user/mtms/api/python/MTMSApi.py
EFIELD_MTMS_ROS_SETUP=/opt/ros/jazzy/setup.bash
```

The API setting may point either to `MTMSApi.py` or its containing directory.
The bootstrap searches its parent directories for
`install/local_setup.bash`.

Example:

```bash
source .venv/bin/activate
python run_with_mtms.py -m efield_control.cli show-config
```

The Python virtual environment must use the same Python major/minor version as
the ROS 2 installation. ROS 2 Jazzy on Ubuntu 24.04 normally uses Python 3.12.

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
