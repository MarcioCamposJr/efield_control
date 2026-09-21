import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path


# ================= FILE =================

FILE = Path(
    r"data\data\mapa_bobina_18x11_TMS_60percent_20260822_143519\resumo_mapeamento.csv"
)

OUTPUT_FOLDER = FILE.parent / "vector_processing"
OUTPUT_FOLDER.mkdir(exist_ok=True)


# ================= READ SUMMARY =================

df = pd.read_csv(FILE)

vx = []
vy = []
magnitude = []


# ================= PROCESS EACH WAVEFORM =================

for _, row in df.iterrows():

    waveform_file = Path(row["arquivo_waveform"])

    # If the saved path is relative to the project
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


# ================= SAVE COMPONENTS =================

df["Vx"] = vx
df["Vy"] = vy
df["magnitude"] = magnitude

# Convert to mV
df["Vx_mV"] = df["Vx"] * 1000
df["Vy_mV"] = df["Vy"] * 1000
df["magnitude_mV"] = df["magnitude"] * 1000


# ================= MAGNITUDE MAP =================

map_data = df.pivot(
    index="y_offset_mm",
    columns="x_offset_mm",
    values="magnitude_mV"
)

map_data = map_data.sort_index()
map_data = map_data.sort_index(axis=1)


# ================= NORMALIZE ARROWS =================

norm = np.sqrt(
    df["Vx_mV"]**2 +
    df["Vy_mV"]**2
)

# Avoid division by zero
norm = norm.replace(0, np.nan)

# Unit vectors: arrows indicate direction only
Ux = df["Vx_mV"] / norm
Uy = df["Vy_mV"] / norm


# ================= PLOT =================

plt.figure(figsize=(11, 7))


# ================= BACKGROUND =================

plt.imshow(
    map_data.values,
    origin="lower",
    extent=[
        map_data.columns.min(),
        map_data.columns.max(),
        map_data.index.min(),
        map_data.index.max()
    ],
    aspect="equal",
    interpolation="bilinear"
)

plt.colorbar(
    label=r"Magnitude $\sqrt{CH1^2 + CH2^2}$ (mV)"
)


# ================= ARROWS =================

plt.quiver(
    df["x_offset_mm"],
    df["y_offset_mm"],
    Ux,
    Uy,

    color="white",

    angles="xy",
    scale_units="xy",

    # Larger scale -> shorter arrows
    scale=0.18,

    # Thinner arrows
    width=0.002,

    headwidth=3,
    headlength=4,
    headaxislength=3.5,

    pivot="mid"
)


# ================= FORMATTING =================

plt.xlabel("X (mm)")
plt.ylabel("Y (mm)")

plt.title(
    "Vector Map - Distance 18.7 mm\n"
    "Color = Magnitude | Arrows = Direction"
)

plt.tight_layout()


# ================= SAVE FIGURE =================

plt.savefig(
    OUTPUT_FOLDER / "vector_map_18.7mm.png",
    dpi=300
)

plt.show()


# ================= SAVE PROCESSED DATA =================

df.to_csv(
    OUTPUT_FOLDER / "vector_data_18.7mm.csv",
    index=False
)


# ================= RESULT =================

print("\nProcessing completed.")
print(f"Results saved in:\n{OUTPUT_FOLDER}")