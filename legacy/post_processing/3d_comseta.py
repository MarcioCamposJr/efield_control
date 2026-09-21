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

OUTPUT = FILE.parent / "interactive_3D_vector_interpolated_lines.html"


# ================= READ DATA =================

df = pd.read_csv(FILE)

x = df["x_offset_mm"].to_numpy()
y = df["y_offset_mm"].to_numpy()
z = df["distancia_bobina_mm"].to_numpy()

vx = df["Vx_mV"].to_numpy()
vy = df["Vy_mV"].to_numpy()


# ================= MEASURED POINTS =================

points = np.column_stack((x, y, z))


# ================= 3D GRID =================

xi = np.linspace(x.min(), x.max(), 45)
yi = np.linspace(y.min(), y.max(), 35)
zi = np.linspace(z.min(), z.max(), 25)

X, Y, Z = np.meshgrid(
    xi,
    yi,
    zi,
    indexing="ij"
)


# ================= INTERPOLATE COMPONENTS =================

print("Interpolating Vx...")

VX = griddata(
    points,
    vx,
    (X, Y, Z),
    method="linear"
)

print("Interpolating Vy...")

VY = griddata(
    points,
    vy,
    (X, Y, Z),
    method="linear"
)


# ================= MAGNITUDE =================

MAG = np.sqrt(
    VX**2 +
    VY**2
)


# ================= VALID REGION =================

valid = (
    np.isfinite(VX) &
    np.isfinite(VY) &
    np.isfinite(MAG)
)

valid_values = MAG[valid]

if len(valid_values) == 0:
    raise RuntimeError("Interpolation returned no valid points.")


# ================= COLOR SCALE =================

vmin = np.nanpercentile(valid_values, 15)
vmax = np.nanpercentile(valid_values, 99)


# ================= FIGURE =================

fig = go.Figure()


# ============================================================
# INTERPOLATED MAGNITUDE VOLUME
# ============================================================

fig.add_trace(
    go.Isosurface(
        x=X[valid].flatten(),
        y=Y[valid].flatten(),
        z=Z[valid].flatten(),

        value=MAG[valid].flatten(),

        isomin=vmin,
        isomax=vmax,

        surface_count=7,

        colorscale="Viridis",

        opacity=0.20,

        caps=dict(
            x_show=False,
            y_show=False,
            z_show=False
        ),

        colorbar=dict(
            title="Magnitude (mV)"
        ),

        name="Interpolated magnitude",

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

measured_mag = np.sqrt(
    vx**2 +
    vy**2
)

fig.add_trace(
    go.Scatter3d(
        x=x,
        y=y,
        z=z,

        mode="markers",

        marker=dict(
            size=3,
            color=measured_mag,
            colorscale="Viridis",
            showscale=False,
            opacity=0.65
        ),

        name="Measured points",

        customdata=np.column_stack(
            (
                vx,
                vy,
                measured_mag
            )
        ),

        hovertemplate=(
            "<b>Measured point</b>"
            "<br>X = %{x:.1f} mm"
            "<br>Y = %{y:.1f} mm"
            "<br>Distance = %{z:.1f} mm"
            "<br>Vx = %{customdata[0]:.2f} mV"
            "<br>Vy = %{customdata[1]:.2f} mV"
            "<br>Magnitude = %{customdata[2]:.2f} mV"
            "<extra></extra>"
        )
    )
)


# ============================================================
# INTERPOLATED DIRECTION VECTORS
# ============================================================

# Larger values = fewer direction indicators
STEP_X = 8
STEP_Y = 7
STEP_Z = 5

Xs = X[
    ::STEP_X,
    ::STEP_Y,
    ::STEP_Z
]

Ys = Y[
    ::STEP_X,
    ::STEP_Y,
    ::STEP_Z
]

Zs = Z[
    ::STEP_X,
    ::STEP_Y,
    ::STEP_Z
]

VXs = VX[
    ::STEP_X,
    ::STEP_Y,
    ::STEP_Z
]

VYs = VY[
    ::STEP_X,
    ::STEP_Y,
    ::STEP_Z
]


# ================= VALID DIRECTIONS =================

arrow_valid = (
    np.isfinite(VXs) &
    np.isfinite(VYs)
)

Xs = Xs[arrow_valid]
Ys = Ys[arrow_valid]
Zs = Zs[arrow_valid]

VXs = VXs[arrow_valid]
VYs = VYs[arrow_valid]


# ================= NORMALIZE DIRECTIONS =================

arrow_norm = np.sqrt(
    VXs**2 +
    VYs**2
)

nonzero = arrow_norm > 0

Xs = Xs[nonzero]
Ys = Ys[nonzero]
Zs = Zs[nonzero]

VXs = VXs[nonzero]
VYs = VYs[nonzero]

arrow_norm = arrow_norm[nonzero]

Ux = VXs / arrow_norm
Uy = VYs / arrow_norm


# ============================================================
# WHITE DIRECTION SEGMENTS
# ============================================================

# Length of each segment in mm
ARROW_LENGTH = 5

x_lines = []
y_lines = []
z_lines = []

for x0, y0, z0, ux, uy in zip(
    Xs,
    Ys,
    Zs,
    Ux,
    Uy
):

    x1 = x0 - ux * ARROW_LENGTH / 2
    x2 = x0 + ux * ARROW_LENGTH / 2

    y1 = y0 - uy * ARROW_LENGTH / 2
    y2 = y0 + uy * ARROW_LENGTH / 2

    x_lines += [
        x1,
        x2,
        None
    ]

    y_lines += [
        y1,
        y2,
        None
    ]

    z_lines += [
        z0,
        z0,
        None
    ]


fig.add_trace(
    go.Scatter3d(
        x=x_lines,
        y=y_lines,
        z=z_lines,

        mode="lines",

        line=dict(
            color="black",
            width=4
        ),

        name="Direction",

        hoverinfo="skip"
    )
)


# ================= LAYOUT =================

fig.update_layout(

    title=(
        "Interpolated 3D Vector Field"
        "<br><sup>Color = Magnitude | White segments = Direction</sup>"
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
            z=0.7
        ),

        camera=dict(
            eye=dict(
                x=1.5,
                y=1.5,
                z=1.0
            )
        )
    ),

    width=1150,
    height=850,

    margin=dict(
        l=0,
        r=0,
        b=0,
        t=70
    )
)


# ================= SAVE =================

fig.write_html(
    OUTPUT
)

fig.show()


# ================= RESULT =================

print("\n3D interpolated vector field created.")

print(
    f"\nSaved in:\n{OUTPUT}"
)