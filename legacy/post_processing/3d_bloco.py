import pandas as pd
import numpy as np
import plotly.graph_objects as go
from pathlib import Path
from scipy.interpolate import griddata


# ================= FILE =================

FILE = Path(
    r"data\data\mapeamento_3D_TMS_60percent_20260822_154949"
    r"\processing_3D\processed_3D_data.csv"
)

OUTPUT = FILE.parent / "interactive_3D_interpolated.html"


# ================= READ DATA =================

df = pd.read_csv(FILE)

x = df["x_offset_mm"].to_numpy()
y = df["y_offset_mm"].to_numpy()
z = df["distancia_bobina_mm"].to_numpy()

magnitude = df["magnitude_mV"].to_numpy()


# ================= 3D GRID =================

# Resolution of interpolated volume
xi = np.linspace(x.min(), x.max(), 45)
yi = np.linspace(y.min(), y.max(), 35)
zi = np.linspace(z.min(), z.max(), 25)

X, Y, Z = np.meshgrid(
    xi,
    yi,
    zi,
    indexing="ij"
)


# ================= INTERPOLATION =================

print("Interpolating 3D volume...")

points = np.column_stack((x, y, z))

MAG = griddata(
    points,
    magnitude,
    (X, Y, Z),
    method="linear"
)


# Fill regions where linear interpolation returned NaN
MAG_nearest = griddata(
    points,
    magnitude,
    (X, Y, Z),
    method="nearest"
)

MAG = np.where(
    np.isnan(MAG),
    MAG_nearest,
    MAG
)


# ================= COLOR RANGE =================

vmin = np.nanpercentile(MAG, 10)
vmax = np.nanpercentile(MAG, 99)


# ================= FIGURE =================

fig = go.Figure()


# ============================================================
# INTERPOLATED 3D VOLUME - ISOSURFACES
# ============================================================

fig.add_trace(
    go.Isosurface(
        x=X.flatten(),
        y=Y.flatten(),
        z=Z.flatten(),

        value=MAG.flatten(),

        isomin=vmin,
        isomax=vmax,

        surface_count=8,

        colorscale="Viridis",

        opacity=0.35,

        caps=dict(
            x_show=False,
            y_show=False,
            z_show=False
        ),

        colorbar=dict(
            title="Magnitude (mV)"
        ),

        name="Interpolated field",

        hovertemplate=(
            "<b>X:</b> %{x:.1f} mm"
            "<br><b>Y:</b> %{y:.1f} mm"
            "<br><b>Distance:</b> %{z:.1f} mm"
            "<br><b>Magnitude:</b> %{value:.2f} mV"
            "<extra></extra>"
        )
    )
)


# ============================================================
# ORIGINAL MEASURED POINTS
# ============================================================

fig.add_trace(
    go.Scatter3d(
        x=x,
        y=y,
        z=z,

        mode="markers",

        name="Measured points",

        marker=dict(
            size=3,
            color=magnitude,
            colorscale="Viridis",

            cmin=magnitude.min(),
            cmax=magnitude.max(),

            showscale=False,

            line=dict(
                width=0.5
            )
        ),

        customdata=magnitude,

        hovertemplate=(
            "<b>Measured point</b>"
            "<br>X = %{x:.1f} mm"
            "<br>Y = %{y:.1f} mm"
            "<br>Distance = %{z:.1f} mm"
            "<br>Magnitude = %{customdata:.2f} mV"
            "<extra></extra>"
        )
    )
)


# ================= LAYOUT =================

fig.update_layout(

    title=(
        "Interpolated 3D Field Magnitude"
        "<br><sup>Isosurfaces + measured points</sup>"
    ),

    scene=dict(

        xaxis=dict(
            title="X (mm)"
        ),

        yaxis=dict(
            title="Y (mm)"
        ),

        zaxis=dict(
            title="Sensor-coil distance (mm)"
        ),

        aspectmode="manual",

        aspectratio=dict(
            x=1.8,
            y=1.1,
            z=0.8
        ),

        camera=dict(
            eye=dict(
                x=1.5,
                y=1.5,
                z=1.0
            )
        )
    ),

    width=1100,
    height=850,

    margin=dict(
        l=0,
        r=0,
        b=0,
        t=70
    )
)


# ================= SAVE =================

fig.write_html(OUTPUT)

fig.show()

print("\nInteractive interpolated 3D plot created.")
print(f"Saved in:\n{OUTPUT}")