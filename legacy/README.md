# Legacy code

This directory contains references that predate the modular architecture.
Nothing here is imported by `efield_control`.

- `post_processing/`: previous processing and visualization scripts.
- `hardware_reference/`: one reference each for the previous planar, circular,
  and centering workflows.

New functionality belongs in the `efield_control` package. Do not duplicate
acquisition, motion, or persistence logic in these scripts.

