# Legacy hardware references

These scripts are retained only because they document parameters and details
from previous experiments:

- `posicao_robo.py`: local-search centering;
- `Mapeamento_planar.py`: Cartesian trajectory with Elfin;
- `mapeamento_hemisférico.py`: serial protocol for the angular stage.

They execute code at module level and may move equipment or fire the TMS. Do
not run or import them during normal operation. Active workflows live in the
`efield_control` package and the `efield-control` command.

