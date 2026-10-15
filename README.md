# E-field control

Modular system for centering a sensor relative to a coil and mapping the field
measured by a Red Pitaya.

## System workflows

1. **Centering**: the robot moves the sensor along `+X`, `-X`, `+Y`, and `-Y`.
   The Red Pitaya measures both channels while the algorithm maximizes
   `sqrt(Vpp(CH1)^2 + Vpp(CH2)^2)`. The step size is reduced when no meaningful
   improvement is found.
2. **Planar mapping**: the robot follows a serpentine X/Y path while preserving
   the Z coordinate and orientation of the origin pose.
3. **Circular mapping**: the angular stage follows a serpentine
   base/inclination path. The current serial protocol uses the `PING`, `CENTER`,
   `MOVEABS`, and `FIRE` commands.

The algorithms do not depend on a robot brand. `CartesianRobot` is the
contract implemented by both the Elfin and Dobot drivers. Likewise,
`AngularPositioner` allows the serial controller to be
replaced by Red Pitaya digital signals without changing the mapping logic.

## Project structure

- `efield_control/domain.py`: poses, waveforms, and measurements.
- `efield_control/ports.py`: robot, acquisition, pulse, and stage contracts.
- `efield_control/acquisition.py`: safe acquisition sequence.
- `efield_control/centering.py`: feedback-based sensor centering.
- `efield_control/mapping.py`: serpentine planar and circular maps.
- `efield_control/workflows.py`: high-level workflow composition.
- `efield_control/storage.py`: summary CSV and waveform persistence.
- `efield_control/configuration.py`: typed TOML and environment configuration.
- `efield_control/calibration.py`: angular and pose calibration transforms.
- `efield_control/drivers/robots/elfin/`: self-contained Elfin implementation.
- `efield_control/drivers/robots/dobot/`: self-contained six-axis Dobot V3
  implementation, using the same robot contract as Elfin.
- `efield_control/drivers/red_pitaya/`: self-contained SCPI implementation and
  project-level Red Pitaya adapters.
- `efield_control/drivers/stimulators/mtms/`: isolated mTMS API integration.
- `efield_control/drivers/`: serial controller and simulation adapters.
- `legacy/post_processing/`: preserved plotting and processing scripts.
- `legacy/hardware_reference/`: one reference for each previous hardware
  workflow, retained only for parameters and protocol details.
- `firmware/arduino_hemispherical_stage/`: uploadable Arduino firmware for the
  two-servo hemispherical mapping stage.

Legacy files are not part of the active application. Hardware reference
scripts must not be imported because they execute connections at module level.

## Validation without hardware

```powershell
uv sync --extra dev
uv run pytest
```

To run legacy plotting and processing scripts, install the analysis dependency
group with `uv sync --extra dev --extra analysis`. Input paths are still
configured inside each legacy script.

The centering tests use a Gaussian field with a known center to validate the
search without moving real hardware. `examples/center_sensor.py` runs real
hardware centering.

## Configuration and calibration

Experiment parameters come from the selected TOML file, with built-in defaults
for omitted fields. Hardware identity and endpoints come from `.env`, with
existing process environment variables taking priority:

```text
Experiment parameters: TOML > built-in safety defaults
Hardware: process environment > .env > built-in defaults
```

Local device endpoints belong in `.env`, which is ignored by Git. Copy
`.env.example` when setting up another machine. Experiment parameters live in
`config/default.toml`, while hardware-specific calibration lives in:

- `config/calibration/angular_stage.toml`;
- `config/calibration/sensor_pose.toml`.

Each supplied configuration file documents every section and parameter inline,
including units, accepted choices, ignored fields, and hardware-safety notes.
Start by copying `.env.example`, then review `config/default.toml` and both
calibration files before the first hardware run.

Experiment TOML files intentionally do not accept a `[hardware]` section. IP
addresses, network ports, serial ports, baud rates, and serial timeouts must be
defined through `.env` or process environment variables. Protocol defaults
remain typed in Python, but there is only one user-editable source for device
endpoints.

Inspect the fully resolved configuration without connecting to hardware:

```powershell
uv run efield-control show-config
```

The angular stage uses logical angles centered at zero. Each motor command is
calculated as:

```text
command = center_command + direction * scale * logical_angle
```

Every command is checked against its calibrated minimum and maximum before a
hardware connection is opened. The initial angular calibration uses the legacy
physical centers of 90 degrees for the base and 92 degrees for inclination.

`coil_center_guess` is added to the robot's current pose before feedback
centering starts. `sensor_to_tcp` is recorded in run metadata but is not yet
applied as a rigid transform because the final mounting geometry is still
required.

Every experiment writes `resolved_config.json` beside `summary.csv`, recording
the loaded configuration, calibration, environment-resolved endpoints, and
effective settings used for that run.

## Operational commands

Check all four configured device connections without running an experiment:

```powershell
python examples/check_connections.py
```

The example reads the existing `.env`, experiment TOML, and calibration files.
The examples also support `python -m examples.<name>`. When launched by file
path (including the IDE Run button), they prefer this checkout over an installed
copy for that Python process only. The examples resolve configuration
files relative to the checkout, so they can be launched from another directory.
No installation, persistent environment change, or working-directory change is needed.
It reports `OK` or `FAIL` and a reason for each device, then lists those that
passed. One failure does not skip the other checks. All connections are closed.
The exit code is 0 when every device passes, 1 if a device check fails, or 2 if
configuration cannot be loaded.

The robot check connects and reads its TCP pose. For a disabled, fault-free
Dobot, it sends `EnableRobot()` through TCP/IP and waits for feedback confirming
enabled and idle. It keeps the existing control mode and leaves the robot
enabled after disconnecting; it does not send movement or disable commands.
If Dobot feedback reports an
invalid operating state, it shows that TCP/feedback connected, prints the state
flags, and reads `GetErrorID()` before closing. This remains `FAIL` because the
robot is not ready to operate; alarms are never cleared automatically.
The microcontroller check sends only `PING` and requires `PONG`;
opening USB serial may reset the board, so a timed-out first PING is retried once.
The Red Pitaya check reads `*IDN?` over SCPI. The mTMS check starts and closes
the API device/session without charging or firing. It requires an Operational
device and a Started session and applies best-effort deadlines to public API
calls using the `[mtms]` timeout settings in TOML. Native SDK waits may delay
these deadlines; all communication goes through MTMSApi's public methods.
The real API check runs on the ROS Linux host's main Python thread; see the
[mTMS integration notes](efield_control/drivers/stimulators/mtms/README.md).
These checks do not prove acquisition quality
or movement accuracy and send no motion, servo, acquisition-arm, or pulse commands.

The executable refuses any real operation without the literal confirmation
`--confirm-hardware MOVE_AND_FIRE`. Review every parameter before using it:

The CLI selects the operation and file paths only. Acquisition settings, pulse
source, repetitions, robot speed, map ranges, and output settings are edited in
TOML, not passed as command-line overrides. For example, edit `[pulse].source`
to choose `mtms_api`, and `[planar_mapping]` to change the planar grid.

```powershell
uv run efield-control center --help
uv run efield-control planar --help
uv run efield-control circular --help
```

Run an experiment using the parameters already saved in the files:

```powershell
python -m efield_control.cli center --confirm-hardware MOVE_AND_FIRE
python -m efield_control.cli planar --confirm-hardware MOVE_AND_FIRE
python -m efield_control.cli circular --confirm-hardware MOVE_AND_FIRE
```

Run sensor centering directly from the example:

```powershell
python examples/center_sensor.py --confirm-hardware MOVE_AND_FIRE
```

This uses the configured Elfin or Dobot, Red Pitaya CH1/CH2, and `[pulse].source`.
It starts at the current TCP pose plus `coil_center_guess`, searches X/Y for the
largest `sqrt(Vpp(CH1)^2 + Vpp(CH2)^2)`, reduces the step when no meaningful
improvement is found, and finishes at the best measured position. Z and
orientation remain fixed at the calibrated starting pose during the search.
Search limits come from `[centering]`; measurements and resolved settings are
saved under `[storage].output_directory`, relative to the working directory.
For the IDE Run button, add `--confirm-hardware MOVE_AND_FIRE` to the script
arguments. Without it the operation is blocked before connecting to hardware.

Acquire a planar map without running sensor centering:

```powershell
python examples/acquire_planar.py --confirm-hardware MOVE_AND_FIRE
```

Position the sensor before starting. The current robot TCP pose is the map
origin; `[planar_mapping]` defines X/Y offsets and steps. Acquisition follows a
serpentine path with fixed Z and orientation, using the configured pulse source
and saving the summary, waveforms, and resolved configuration. The example does
not apply `coil_center_guess` or search for a signal maximum.

Alternative files can be selected before the subcommand:

```powershell
uv run efield-control `
  --config config/default.toml `
  --env-file .env `
  --angular-calibration config/calibration/angular_stage.toml `
  --sensor-calibration config/calibration/sensor_pose.toml `
  show-config
```

Planar map limits are offsets relative to the robot's current pose. Circular
map values are absolute angles sent to the stage controller. Every run creates
a new directory containing `summary.csv` and one waveform per point.

## Hardware composition

Hardware adapters never connect merely because the package was imported. The
application explicitly creates:

- `ElfinRobotAdapter` or `DobotRobotAdapter`, selected by `EFIELD_ROBOT_TYPE`;
- `RedPitayaAcquisition`;
- a pulse source such as `RedPitayaDigitalPulse` or `SerialMotorController`;
- `CenterSensorWorkflow`, `PlanarMapping`, or `CircularMapping`.

When the Red Pitaya generates the pulse, share its SCPI client with the digital
output adapter: `RedPitayaDigitalPulse(acquisition.client)`. For the current
circular setup, one `SerialMotorController` instance can serve as both the
angular positioner and pulse source.

The pulse source also accepts `mtms_api`. Its single-channel client charges the
selected channel, schedules stimulation and trigger out for the same device
timestamp, waits for completion, and optionally discharges the channel. This
keeps electrical and API-based stimulation interchangeable without coupling
acquisition or mapping code to the vendor library.

The mTMS API and its dependencies must already be importable in the Python
environment used to run the project. Run project commands directly:

```bash
python -m efield_control.cli show-config
```

The integration imports `MTMSApi` and `ExecutionCondition` from the existing
environment. It does not install packages, run setup scripts, or modify the
Python import path or environment variables. If imports fail, the operation
stops with an error. See `efield_control/drivers/stimulators/mtms/README.md`
for integration details.

The low-level SCPI client remains available for direct use through:

```python
from efield_control.drivers.red_pitaya import scpi
```

For Dobot CR/Nova V3, set `EFIELD_ROBOT_TYPE=dobot` in `.env`.
Both manufacturers use `EFIELD_ROBOT_HOST`. Dobot uses
the existing controller frames and requires the robot to be enabled and idle;
ordinary experiment connections do not enable it or clear alarms automatically.
The connection example explicitly enables a fault-free, disabled Dobot. See
[Dobot driver details](efield_control/drivers/robots/dobot/README.md) for protocol
scope and movement checks. Elfin remains the default. Robot selection is not
accepted in TOML or CLI arguments. `EFIELD_ELFIN_USE_NEW_API` also belongs in
`.env` and selects the Elfin protocol variant.

The `[robot]` TOML section contains shared speed, movement and socket timeouts,
settling time, and target tolerances. Both drivers apply these parameters before
allowing a measurement; Elfin uses its speed ratio and Dobot uses per-move SpeedL.

To command the circular stage through the Red Pitaya, define the DIO pins and
the electrical motion-complete handshake.
