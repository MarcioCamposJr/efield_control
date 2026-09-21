import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path


# ================= FILE =================

FILE = Path(
    r"data\data\mapeamento_3D_TMS_60percent_20260822_154949\resumo_mapeamento_3D.csv"
)

OUTPUT_FOLDER = FILE.parent / "processing_3D"
OUTPUT_FOLDER.mkdir(exist_ok=True)


# ================= READ SUMMARY =================

df = pd.read_csv(FILE)

vx = []
vy = []
magnitude = []


print(f"\nTotal points: {len(df)}")


# ================= PROCESS EACH WAVEFORM =================

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

    # Vector magnitude at each instant
    mag = np.sqrt(ch1**2 + ch2**2)

    # Instant of maximum magnitude
    k = np.argmax(mag)

    # Signed components at the same instant
    vx.append(ch1[k])
    vy.append(ch2[k])
    magnitude.append(mag[k])

    if n % 50 == 0:
        print(f"Processed waveforms: {n}/{len(df)}")


# ================= ADD PROCESSED DATA =================

df["Vx"] = vx
df["Vy"] = vy
df["magnitude"] = magnitude

# Convert V -> mV
df["Vx_mV"] = df["Vx"] * 1000
df["Vy_mV"] = df["Vy"] * 1000
df["magnitude_mV"] = df["magnitude"] * 1000


# ================= SAVE PROCESSED CSV =================

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


# ============================================================
# VECTOR MAP FOR EACH Z SLICE
# ============================================================

maximum_data = []
center_data = []


# Same color scale for all slices
COLOR_MIN = df["magnitude_mV"].min()
COLOR_MAX = df["magnitude_mV"].max()


for distance in distances:

    print(f"\nGenerating vector map: {distance:.1f} mm")

    slice_df = df[
        df["distancia_bobina_mm"] == distance
    ].copy()


    # ================= MAGNITUDE MAP =================

    map_data = slice_df.pivot(
        index="y_offset_mm",
        columns="x_offset_mm",
        values="magnitude_mV"
    )

    map_data = map_data.sort_index()
    map_data = map_data.sort_index(axis=1)


    # ================= NORMALIZED ARROWS =================

    norm = np.sqrt(
        slice_df["Vx_mV"]**2 +
        slice_df["Vy_mV"]**2
    )

    norm = norm.replace(0, np.nan)

    Ux = slice_df["Vx_mV"] / norm
    Uy = slice_df["Vy_mV"] / norm


    # ================= MAXIMUM =================

    idx_max = slice_df["magnitude_mV"].idxmax()
    maximum = slice_df.loc[idx_max]

    maximum_data.append([
        distance,
        maximum["x_offset_mm"],
        maximum["y_offset_mm"],
        maximum["magnitude_mV"]
    ])


    # ================= CENTER =================

    slice_df["distance_from_center"] = np.sqrt(
        slice_df["x_offset_mm"]**2 +
        slice_df["y_offset_mm"]**2
    )

    center = slice_df.loc[
        slice_df["distance_from_center"].idxmin()
    ]

    center_data.append([
        distance,
        center["x_offset_mm"],
        center["y_offset_mm"],
        center["magnitude_mV"]
    ])


    # ================= PLOT =================

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
        label=r"Magnitude $\sqrt{CH1^2 + CH2^2}$ (mV)"
    )


    # ================= ARROWS =================

    ax.quiver(
        slice_df["x_offset_mm"],
        slice_df["y_offset_mm"],

        Ux,
        Uy,

        color="white",

        angles="xy",
        scale_units="xy",

        # Smaller arrows
        scale=0.18,
        width=0.002,

        headwidth=3,
        headlength=4,
        headaxislength=3.5,

        pivot="mid"
    )


    # ================= FORMAT =================

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
# MAXIMUM MAGNITUDE VS DISTANCE
# ============================================================

print("\nGenerating maximum magnitude vs distance...")


df_max = pd.DataFrame(
    maximum_data,
    columns=[
        "distance_mm",
        "x_max_mm",
        "y_max_mm",
        "maximum_magnitude_mV"
    ]
)

df_max.to_csv(
    OUTPUT_FOLDER / "maximum_vs_distance.csv",
    index=False
)


fig, ax = plt.subplots(figsize=(7, 5))

ax.plot(
    df_max["distance_mm"],
    df_max["maximum_magnitude_mV"],
    "o-"
)

ax.set_xlabel("Sensor-coil distance (mm)")
ax.set_ylabel("Maximum magnitude (mV)")
ax.set_title("Maximum Magnitude vs Distance")

ax.grid()

fig.tight_layout()

fig.savefig(
    OUTPUT_FOLDER /
    "maximum_magnitude_vs_distance.png",
    dpi=300
)

plt.close(fig)


# ============================================================
# CENTER MAGNITUDE VS DISTANCE
# ============================================================

print("Generating center magnitude vs distance...")


df_center = pd.DataFrame(
    center_data,
    columns=[
        "distance_mm",
        "x_mm",
        "y_mm",
        "center_magnitude_mV"
    ]
)

df_center.to_csv(
    OUTPUT_FOLDER / "center_vs_distance.csv",
    index=False
)


fig, ax = plt.subplots(figsize=(7, 5))

ax.plot(
    df_center["distance_mm"],
    df_center["center_magnitude_mV"],
    "o-"
)

ax.set_xlabel("Sensor-coil distance (mm)")
ax.set_ylabel("Magnitude at center (mV)")
ax.set_title("Magnitude at Coil Center vs Distance")

ax.grid()

fig.tight_layout()

fig.savefig(
    OUTPUT_FOLDER /
    "center_magnitude_vs_distance.png",
    dpi=300
)

plt.close(fig)


# ============================================================
# 3D MAGNITUDE MAP
# ============================================================

print("Generating 3D magnitude map...")


fig = plt.figure(figsize=(11, 8))

ax = fig.add_subplot(
    111,
    projection="3d"
)

scatter = ax.scatter(
    df["x_offset_mm"],
    df["y_offset_mm"],
    df["distancia_bobina_mm"],

    c=df["magnitude_mV"],

    s=35
)

fig.colorbar(
    scatter,
    ax=ax,
    label="Magnitude (mV)",
    pad=0.1
)

ax.set_xlabel("X (mm)")
ax.set_ylabel("Y (mm)")
ax.set_zlabel("Sensor-coil distance (mm)")

ax.set_title(
    "3D Magnitude Map"
)

fig.tight_layout()

fig.savefig(
    OUTPUT_FOLDER /
    "3D_magnitude_map.png",
    dpi=300
)

plt.close(fig)


# ============================================================
# 3D VECTOR MAP
# ============================================================

print("Generating 3D vector map...")


norm = np.sqrt(
    df["Vx_mV"]**2 +
    df["Vy_mV"]**2
)

norm = norm.replace(0, np.nan)

Ux = df["Vx_mV"] / norm
Uy = df["Vy_mV"] / norm


fig = plt.figure(figsize=(12, 8))

ax = fig.add_subplot(
    111,
    projection="3d"
)


# Magnitude points
scatter = ax.scatter(
    df["x_offset_mm"],
    df["y_offset_mm"],
    df["distancia_bobina_mm"],

    c=df["magnitude_mV"],

    s=20,
    alpha=0.8
)


# Vector directions
ax.quiver(
    df["x_offset_mm"],
    df["y_offset_mm"],
    df["distancia_bobina_mm"],

    Ux,
    Uy,
    np.zeros(len(df)),

    length=5,
    normalize=True
)


fig.colorbar(
    scatter,
    ax=ax,
    label="Magnitude (mV)",
    pad=0.1
)

ax.set_xlabel("X (mm)")
ax.set_ylabel("Y (mm)")
ax.set_zlabel("Sensor-coil distance (mm)")

ax.set_title(
    "3D Vector Map"
)

fig.tight_layout()

fig.savefig(
    OUTPUT_FOLDER /
    "3D_vector_map.png",
    dpi=300
)

plt.close(fig)


# ============================================================
# MAXIMUM POSITION VS DISTANCE
# ============================================================

print("Generating maximum position plot...")


fig, ax = plt.subplots(figsize=(8, 6))

scatter = ax.scatter(
    df_max["x_max_mm"],
    df_max["y_max_mm"],

    c=df_max["distance_mm"],

    s=100
)

for _, row in df_max.iterrows():

    ax.text(
        row["x_max_mm"],
        row["y_max_mm"],
        f' {row["distance_mm"]:.1f} mm'
    )


fig.colorbar(
    scatter,
    ax=ax,
    label="Sensor-coil distance (mm)"
)

ax.set_xlabel("X position of maximum (mm)")
ax.set_ylabel("Y position of maximum (mm)")

ax.set_title(
    "Maximum Magnitude Position vs Distance"
)

ax.grid()

fig.tight_layout()

fig.savefig(
    OUTPUT_FOLDER /
    "maximum_position_vs_distance.png",
    dpi=300
)

plt.close(fig)


# ============================================================
# SUMMARY
# ============================================================

print("\n======================================")
print("PROCESSING COMPLETED")
print("======================================")

print(f"\nTotal points: {len(df)}")

print(
    "\nDistances processed:",
    distances
)

print(
    "\nFiles saved in:"
)

print(OUTPUT_FOLDER)