# Arduino hemispherical-stage firmware

This sketch controls the two servos used only by circular/hemispherical
mapping. Planar mapping and robot-based centering do not use these servos.

## Supported setup

The sketch uses Arduino's standard `Servo` library and is suitable for common
Uno, Nano, and Mega boards. The default pin assignment is:

| Signal | Arduino pin |
| --- | ---: |
| Base servo | D9 |
| Inclination servo | D10 |
| TMS trigger output | D7 |

Change the constants at the top of the `.ino` file if the board or wiring is
different. Do not power either servo from the Arduino 5 V pin; use a suitable
external servo supply. Grounds may only be connected when permitted by the
TMS interface and isolation design.

## Critical trigger warning

ESP32 GPIO uses 3.3 V logic, while many Arduino boards output 5 V. Do not
connect the Arduino trigger pin directly to the TMS input until its accepted
voltage, polarity, required pulse, and isolation have been verified. Use a
level shifter, optocoupler, or other approved interface when required.

For this reason, the firmware ships with:

```cpp
constexpr bool ENABLE_TMS_TRIGGER = false;
```

With the trigger disabled, `FIRE` returns `FIRE_ERROR,DISABLED` and the Python
application aborts that acquisition. Change the constant to `true` only after
the electrical interface has been validated.

## Upload with Arduino IDE

1. Open `arduino_hemispherical_stage.ino` in Arduino IDE.
2. Select the exact Arduino board and serial port.
3. Review pin assignments, pulse widths, servo limits, and trigger settings.
4. Compile and upload the sketch.
5. Open Serial Monitor at 115200 baud with newline termination.
6. Send `PING`; the board must reply with `PONG`.
7. Test `MOVEABS` with the mechanism unloaded and emergency stop available.

## Serial protocol

| Command | Successful response | Purpose |
| --- | --- | --- |
| `PING` | `PONG` | Communication test |
| `CENTER` | `MOVED,...`, `CENTERED,...`, `SERVOS_OK` | Legacy fallback center |
| `MOVEABS,90,92` | `MOVED,90.000,92.000` | Physical servo commands |
| `FIRE` | `FIRE_DONE` | TMS pulse, when explicitly enabled |

The active Python workflow normally does not send `CENTER`. It reads logical
centers and offsets from `config/calibration/angular_stage.toml`, converts them
to physical angles, and sends `MOVEABS`. This keeps calibration in one place.

## Differences from the previous ESP32 sketch

- Replaces `ESP32Servo.h` with the standard `Servo.h` library.
- Uses configurable Arduino pins instead of ESP32 GPIO numbers.
- Accepts decimal calibrated angles instead of truncating with `toInt()`.
- Uses a fixed 64-byte command buffer instead of dynamic `String` allocation.
- Does not move servos automatically at startup.
- Rejects malformed commands and out-of-range motor angles.
- Keeps TMS output disabled until electrical compatibility is confirmed.

