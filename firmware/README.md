# Firmware

Firmware in this directory runs on external microcontrollers and is not part of
the Python package.

- `arduino_hemispherical_stage/`: Arduino firmware for the two-servo angular
  stage used only by hemispherical mapping.

The computer communicates with the firmware through the protocol implemented
by `efield_control.drivers.serial_controller.SerialMotorController`.

