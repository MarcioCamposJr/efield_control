import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import plotly.graph_objects as go
from pathlib import Path


# ================= FILE =================

FILE = Path(
    r"data\data\mapeamento_3D_TMS_60percent_20260822_154949"
    r"\resumo_mapeamento_3D.csv"
)

OUTPUT_FOLDER = FILE.parent / "processing_3D"
OUTPUT_FOLDER.mkdir(exist_ok=True)


# ================= READ SUMMARY =================

df = pd.read_csv(FILE)

vx = []
vy = []
magnitude = []


print(f"\nTotal points: {len(df)}")


# ================= PROCESS WAVEFORMS =================

for n, (_, row) in enumerate(df.iterrows(), 1):

    waveform_file = Path(row["arquivo_waveform"])

    if not waveform_file.exists():
        waveform_file = Path.cwd() / waveform_file

    data = pd.read_csv(waveform_file)

    ch1 = data["ch1_V"].to_numpy()
    ch2 = data["ch2_V"].to_numpy()

    # Remove DC offset
    ch1 = ch1 - np.mean(ch1)
    ch2 = ch2 - np.mean(ch2)

    # Instantaneous vector magnitude
    mag = np.sqrt(ch1**2 + ch2**2)

    # Instant of maximum magnitude
    k = np.argmax(mag)

    # Signed components at the same instant
    vx.append(ch1[k])
    vy.append(ch2[k])
    magnitude.append(mag[k])

    if n % 50 == 0:
        print(f"Processed: {n}/{len(df)}")


# ================= PROCESSED DATA =================

df["Vx"] = vx
df["Vy"] = vy
df["magnitude"] = magnitude

df["Vx_mV"] = df["Vx"] * 1000
df["Vy_mV"] = df["Vy"] * 1000
df["magnitude_mV"] = df["magnitude"] * 1000


df.to_csv(
    OUTPUT_FOLDER / "processed_3D_data.csv",
    index=False
)


# ================= DISTANCES =================

distances = sorted(
    df["distancia_bobina_mm"].unique()
)

print("\nDistances found:")
print(distances)


# ================= COMMON COLOR SCALE =================

COLOR_MIN = df["magnitude_mV"].min()
COLOR_MAX = df["magnitude_mV"].max()


# ============================================================
# 2D VECTOR MAP FOR EACH SLICE
# ============================================================

for distance in distances:

    print(f"Generating vector map: {distance:.1f} mm")

    slice_df = df[
        df["distancia_bobina_mm"] == distance
    ].copy()


    # Magnitude map
    map_data = slice_df.pivot(
        index="y_offset_mm",
        columns="x_offset_mm",
        values="magnitude_mV"
    )

    map_data = map_data.sort_index()
    map_data = map_data.sort_index(axis=1)


    # Normalize vectors -> direction only
    norm = np.sqrt(
        slice_df["Vx_mV"]**2 +
        slice_df["Vy_mV"]**2
    )

    norm = norm.replace(0, np.nan)

    Ux = slice_df["Vx_mV"] / norm
    Uy = slice_df["Vy_mV"] / norm


    # ================= FIGURE =================

    fig, ax = plt.subplots(figsize=(11, 7))

    image = ax.imshow(
        map_data.values,
        origin="lower",

        extent=[
            map_data.columns.min(),
            map_data.columns.max(),
            map_data.index.min(),
            map_data.index.max()
        ],

        aspect="equal",
        interpolation="bilinear",

        vmin=COLOR_MIN,
        vmax=COLOR_MAX
    )

    fig.colorbar(
        image,
        ax=ax,
        label=r"Magnitude $\sqrt{CH1^2+CH2^2}$ (mV)"
    )


    # ================= WHITE DIRECTION ARROWS =================

    ax.quiver(
        slice_df["x_offset_mm"],
        slice_df["y_offset_mm"],

        Ux,
        Uy,

        color="white",

        angles="xy",
        scale_units="xy",

        # Larger value = shorter arrows
        scale=0.20,

        width=0.002,

        headwidth=3,
        headlength=4,
        headaxislength=3.5,

        pivot="mid"
    )


    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")

    ax.set_title(
        f"Vector Map - Distance {distance:.1f} mm\n"
        "Color = Magnitude | Arrows = Direction"
    )

    fig.tight_layout()

    fig.savefig(
        OUTPUT_FOLDER /
        f"vector_map_{distance:.1f}mm.png",
        dpi=300
    )

    plt.close(fig)


# ============================================================
# INTERACTIVE 3D VECTOR MAP
# ============================================================

print("\nGenerating interactive 3D vector map...")


fig3d = go.Figure()


# ---------------- POINTS BY SLICE ----------------

for i, distance in enumerate(distances):

    slice_df = df[
        df["distancia_bobina_mm"] == distance
    ].copy()

    fig3d.add_trace(
        go.Scatter3d(
            x=slice_df["x_offset_mm"],
            y=slice_df["y_offset_mm"],
            z=slice_df["distancia_bobina_mm"],

            mode="markers",

            name=f"{distance:.1f} mm",

            marker=dict(
                size=5,

                color=slice_df["magnitude_mV"],

                colorscale="Viridis",

                cmin=COLOR_MIN,
                cmax=COLOR_MAX,

                showscale=(i == 0),

                colorbar=dict(
                    title="Magnitude (mV)"
                ),

                opacity=0.8
            ),

            customdata=slice_df[
                [
                    "Vx_mV",
                    "Vy_mV",
                    "magnitude_mV"
                ]
            ],

            hovertemplate=(
                "<b>X:</b> %{x:.1f} mm"
                "<br><b>Y:</b> %{y:.1f} mm"
                "<br><b>Distance:</b> %{z:.1f} mm"
                "<br><b>Vx:</b> %{customdata[0]:.2f} mV"
                "<br><b>Vy:</b> %{customdata[1]:.2f} mV"
                "<br><b>Magnitude:</b> %{customdata[2]:.2f} mV"
                "<extra></extra>"
            )
        )
    )


# ============================================================
# DIRECTION SEGMENTS
# ============================================================

# Normalize vectors
norm = np.sqrt(
    df["Vx_mV"]**2 +
    df["Vy_mV"]**2
)

norm = norm.replace(0, np.nan)

Ux = df["Vx_mV"] / norm
Uy = df["Vy_mV"] / norm


# Length of each direction indicator in mm
ARROW_LENGTH = 5


x_lines = []
y_lines = []
z_lines = []


for x, y, z, ux, uy in zip(
    df["x_offset_mm"],
    df["y_offset_mm"],
    df["distancia_bobina_mm"],
    Ux,
    Uy
):

    if np.isnan(ux) or np.isnan(uy):
        continue

    x1 = x - ux * ARROW_LENGTH / 2
    x2 = x + ux * ARROW_LENGTH / 2

    y1 = y - uy * ARROW_LENGTH / 2
    y2 = y + uy * ARROW_LENGTH / 2


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
        z,
        z,
        None
    ]


fig3d.add_trace(
    go.Scatter3d(
        x=x_lines,
        y=y_lines,
        z=z_lines,

        mode="lines",

        line=dict(
            color="white",
            width=3
        ),

        name="Direction",

        hoverinfo="skip",

        showlegend=True
    )
)


# ================= 3D LAYOUT =================

fig3d.update_layout(

    title=(
        "Interactive 3D Vector Field Map"
        "<br><sup>Color = Magnitude | White segments = Direction</sup>"
    ),

    scene=dict(

        xaxis_title="X (mm)",
        yaxis_title="Y (mm)",
        zaxis_title="Sensor-coil distance (mm)",

        aspectmode="manual",

        aspectratio=dict(
            x=1.8,
            y=1.1,
            z=0.7
        )
    ),

    legend=dict(
        title="Distance"
    ),

    width=1100,
    height=800,

    margin=dict(
        l=0,
        r=0,
        b=0,
        t=70
    )
)


# ================= SAVE INTERACTIVE HTML =================

HTML_FILE = (
    OUTPUT_FOLDER /
    "interactive_3D_vector_map.html"
)

fig3d.write_html(
    HTML_FILE
)


# Opens interactive figure
fig3d.show()


# ================= RESULT =================

print("\nProcessing completed.")

print(
    f"Distances processed: {distances}"
)

print(
    f"\nInteractive 3D map saved in:\n{HTML_FILE}"
)

print(
    f"\nAll files saved in:\n{OUTPUT_FOLDER}"
)