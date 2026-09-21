# Dobot driver

This directory is reserved for the future Dobot implementation.

The adapter should implement the `CartesianRobot` protocol from
`efield_control.ports` and keep vendor SDK details inside this directory. A
recommended layout is:

- `adapter.py`: implementation of the project-level robot contract;
- `client.py`: thin wrapper around the official Dobot SDK;
- `models.py`: vendor-specific poses, states, and error codes;
- `__init__.py`: public exports only.

Before implementation, define the exact Dobot model, SDK transport, coordinate
units, orientation convention, workspace limits, and emergency-stop behavior.

