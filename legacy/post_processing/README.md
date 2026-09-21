# Legacy post-processing

Scripts retained to reproduce plots from previous experiments:

- `processamento_ch2_45a100.py` and `processamento_teste.py`: Vpp versus
  intensity fitting;
- `processamentoMAP.py`: planar vector map;
- `processamento_volumetrico.py`: static 3D map reports;
- `plot3d.py`: interactive 3D visualization;
- `3d_bloco.py`: scalar 3D interpolation;
- `3d_comseta.py`: 3D vector field;
- `pmapeamentohemisferico.py`: angular-map processing.

These scripts define their input paths directly in the source. Run them from
the project root and update `FILE`, `PASTA`, or `ARQUIVO_RESUMO` first. Install
their dependencies with:

```powershell
uv sync --extra analysis
```

