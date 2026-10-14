# Dobot driver

Self-contained driver for six-axis Dobot CR/Nova controllers using the V3 TCP/IP
protocol represented by the reference project. It does not support V4/CRA/E6 or
four-axis MG400/M1 controllers. No external SDK or new dependency is required.

The implementation follows [Dobot's V3 protocol and SDK](https://github.com/Dobot-Arm/TCP-IP-Python-V3),
including its 1440-byte feedback layout. The reference repository is not imported.

## Layers

- `connection.py`: ports 29999 (dashboard), 30003 (motion), and 30004 (feedback);
  complete replies, controller error codes, socket timeouts, and frame validation.
- `client.py`: background feedback reader, recent-state checks, and cleanup.
- `adapter.py`: the same `CartesianRobot` methods as Elfin: `connect`,
  `disconnect`, `current_pose`, `move_to`, and `stop`.
- `__init__.py`: public exports.

Construction does not connect. `connect()` requires valid feedback from an
already enabled, idle controller. It does not call `EnableRobot`, `ClearError`,
`PowerOn`, `User`, `Tool`, or `SpeedFactor`. No host network configuration,
environment setup, or installation is performed.

## Selection

Select the robot and host only in `.env` (or existing process environment):

```dotenv
EFIELD_ROBOT_TYPE=dobot
EFIELD_ROBOT_HOST=192.168.5.1
```

The `[robot]` parameters in `config/default.toml` are shared with Elfin:
`speed_percent`, `socket_timeout_s`, `movement_timeout_s`, `settling_time_s`,
`position_tolerance_mm`, and `orientation_tolerance_deg`. Edit the TOML to change
motion parameters; command-line parameter overrides are not accepted.
Robot identity has no TOML or CLI override.
`EFIELD_ELFIN_USE_NEW_API` applies only to Elfin. Dobot's streaming feedback
freshness limit remains internal to the driver (one second by default).

```powershell
python -m efield_control.cli center --confirm-hardware MOVE_AND_FIRE
python -m efield_control.cli planar --confirm-hardware MOVE_AND_FIRE
```

The operator must prepare the controller in TCP/IP mode and enable it before
running. Poses use the controller's active tool/user frame: XYZ in mm and
RX/RY/RZ in degrees. The driver leaves those frames unchanged; review them so
the sensor pose and map origin refer to the intended frame.

## Motion and failure behavior

`MovL(...,SpeedL=N)` limits speed for this command. A zero error code confirms
acceptance, not completion. `move_to()` requires new feedback showing an idle
controller at the target, within both tolerances, then waits for settling and
rechecks the pose before returning. A target already reached is a no-op.

Faults, dropped connections, stale feedback, rejected commands, invalid frames,
and motion timeouts propagate as errors. On movement failure or interruption,
the adapter attempts `ResetRobot()` on the dashboard channel, the V3 motion stop
command. This is a software stop, not a physical emergency stop. `disconnect()`
shuts down all sockets and joins the feedback reader.

Tests use simulated sockets and feedback. Controller compatibility, coordinate
frames, motion accuracy, and stop behavior still require hardware validation.

