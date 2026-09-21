import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from pathlib import Path


# ============================================================
# PASTA DO EXPERIMENTO
# ============================================================

PASTA = Path(
    r"C:\Repositorios\redpitaya_control\data\mapeamento_angular_20260910_145915"
)

ARQUIVO = (
    PASTA
    / "resumo_mapeamento.csv"
)


# ============================================================
# PASTA DE SAIDA
# ============================================================

PASTA_SAIDA = (
    PASTA
    / "processamento_campo_eletrico_corrigido"
)

PASTA_SAIDA.mkdir(
    exist_ok=True
)


# ============================================================
# COMPRIMENTO EFETIVO DO SENSOR
# ============================================================

L_EFETIVO_MM = 5.74

L_EFETIVO_M = (
    L_EFETIVO_MM
    /
    1000.0
)


# ============================================================
# LER CSV
# ============================================================

print()
print("=" * 70)
print("PROCESSAMENTO DO CAMPO ELETRICO")
print("=" * 70)

df = pd.read_csv(
    ARQUIVO
)

print()
print(
    f"{len(df)} pontos encontrados."
)

print(
    f"Comprimento efetivo = "
    f"{L_EFETIVO_MM:.2f} mm"
)

print(
    f"Fator de conversao = "
    f"{1/L_EFETIVO_M:.2f} V/m por V"
)


# ============================================================
# VERIFICAR COLUNAS
# ============================================================

colunas_necessarias = [
    "base_relativa_deg",
    "inclinacao_relativa_deg",
    "servo_base_real_deg",
    "servo_inclinacao_real_deg",
    "p2p_ch1_V",
    "p2p_ch2_V",
    "magnitude_V",
    "arquivo_waveform"
]

for coluna in colunas_necessarias:

    if coluna not in df.columns:

        raise ValueError(
            f"Coluna ausente: {coluna}"
        )


# ============================================================
# ORDENAR
# ============================================================

df = df.sort_values(
    [
        "inclinacao_relativa_deg",
        "base_relativa_deg"
    ]
).reset_index(
    drop=True
)


# ============================================================
# CAMPO ELETRICO A PARTIR DO P2P
#
# E = V / L
#
# ============================================================

df["E1_pp_V_m"] = (
    df["p2p_ch1_V"]
    /
    L_EFETIVO_M
)

df["E2_pp_V_m"] = (
    df["p2p_ch2_V"]
    /
    L_EFETIVO_M
)

df["E_magnitude_V_m"] = np.sqrt(
    df["E1_pp_V_m"] ** 2
    +
    df["E2_pp_V_m"] ** 2
)


# ============================================================
# NORMALIZACAO
# ============================================================

df["E1_percent"] = (
    df["E1_pp_V_m"]
    /
    df["E1_pp_V_m"].max()
    *
    100
)

df["E2_percent"] = (
    df["E2_pp_V_m"]
    /
    df["E2_pp_V_m"].max()
    *
    100
)

df["E_magnitude_percent"] = (
    df["E_magnitude_V_m"]
    /
    df["E_magnitude_V_m"].max()
    *
    100
)


# ============================================================
# MAXIMOS
# ============================================================

linha_E1 = df.loc[
    df["E1_pp_V_m"].idxmax()
]

linha_E2 = df.loc[
    df["E2_pp_V_m"].idxmax()
]

linha_E = df.loc[
    df["E_magnitude_V_m"].idxmax()
]


print()
print("=" * 70)
print("MAXIMOS")
print("=" * 70)

print(
    f"CH1 max = "
    f"{linha_E1['E1_pp_V_m']:.2f} V/m"
)

print(
    f"Base = "
    f"{linha_E1['base_relativa_deg']:.1f} deg | "
    f"Inclinacao = "
    f"{linha_E1['inclinacao_relativa_deg']:.1f} deg"
)

print()

print(
    f"CH2 max = "
    f"{linha_E2['E2_pp_V_m']:.2f} V/m"
)

print(
    f"Base = "
    f"{linha_E2['base_relativa_deg']:.1f} deg | "
    f"Inclinacao = "
    f"{linha_E2['inclinacao_relativa_deg']:.1f} deg"
)

print()

print(
    f"|E| max = "
    f"{linha_E['E_magnitude_V_m']:.2f} V/m"
)

print(
    f"Base = "
    f"{linha_E['base_relativa_deg']:.1f} deg | "
    f"Inclinacao = "
    f"{linha_E['inclinacao_relativa_deg']:.1f} deg"
)


# ============================================================
# FUNCAO PARA ENCONTRAR WAVEFORM
# ============================================================

def resolver_waveform(caminho_salvo):

    caminho = Path(
        caminho_salvo
    )

    if caminho.exists():
        return caminho

    caminho2 = (
        Path.cwd()
        /
        caminho
    )

    if caminho2.exists():
        return caminho2

    caminho3 = (
        PASTA
        /
        caminho.name
    )

    if caminho3.exists():
        return caminho3

    raise FileNotFoundError(
        f"Nao encontrei waveform:\n{caminho_salvo}"
    )


# ============================================================
# REFERENCIA TEMPORAL
#
# Usa o ponto (0,0)
# ============================================================

referencia = df[
    (
        df["base_relativa_deg"] == 0
    )
    &
    (
        df["inclinacao_relativa_deg"] == 0
    )
]

if len(referencia) == 0:

    raise RuntimeError(
        "Ponto (0,0) nao encontrado."
    )


arquivo_ref = resolver_waveform(
    referencia.iloc[0]["arquivo_waveform"]
)

dados_ref = pd.read_csv(
    arquivo_ref
)

ch1_ref = (
    dados_ref["ch1_V"]
    .to_numpy(dtype=float)
)

ch2_ref = (
    dados_ref["ch2_V"]
    .to_numpy(dtype=float)
)

tempo_ref = (
    dados_ref["time_s"]
    .to_numpy(dtype=float)
)


# ============================================================
# REMOVER DC
# ============================================================

ch1_ref = (
    ch1_ref
    -
    np.mean(ch1_ref)
)

ch2_ref = (
    ch2_ref
    -
    np.mean(ch2_ref)
)


# ============================================================
# PICO DE REFERENCIA
# ============================================================

mag_ref = np.sqrt(
    ch1_ref ** 2
    +
    ch2_ref ** 2
)

indice_pico = int(
    np.argmax(
        mag_ref
    )
)

tempo_pico = tempo_ref[
    indice_pico
]


print()
print(
    f"Instante de referencia = "
    f"{tempo_pico*1e6:.3f} us"
)


# ============================================================
# EXTRAIR COMPONENTES ASSINADAS
#
# Essas sao usadas SOMENTE no mapa vetorial
# ============================================================

E1_assinado = []
E2_assinado = []


for _, row in df.iterrows():

    arquivo_waveform = resolver_waveform(
        row["arquivo_waveform"]
    )

    dados = pd.read_csv(
        arquivo_waveform
    )

    ch1 = (
        dados["ch1_V"]
        .to_numpy(dtype=float)
    )

    ch2 = (
        dados["ch2_V"]
        .to_numpy(dtype=float)
    )


    # --------------------------------------------------------
    # remover DC
    # --------------------------------------------------------

    ch1 = (
        ch1
        -
        np.mean(ch1)
    )

    ch2 = (
        ch2
        -
        np.mean(ch2)
    )


    if (
        indice_pico >= len(ch1)
        or
        indice_pico >= len(ch2)
    ):

        raise RuntimeError(
            f"Waveform curta demais:\n"
            f"{arquivo_waveform}"
        )


    # --------------------------------------------------------
    # componentes instantaneas
    # --------------------------------------------------------

    v1 = float(
        ch1[indice_pico]
    )

    v2 = float(
        ch2[indice_pico]
    )


    e1 = (
        v1
        /
        L_EFETIVO_M
    )

    e2 = (
        v2
        /
        L_EFETIVO_M
    )


    E1_assinado.append(
        e1
    )

    E2_assinado.append(
        e2
    )


df["E1_assinado_V_m"] = (
    E1_assinado
)

df["E2_assinado_V_m"] = (
    E2_assinado
)

df["E_vetor_V_m"] = np.sqrt(
    df["E1_assinado_V_m"] ** 2
    +
    df["E2_assinado_V_m"] ** 2
)


# ============================================================
# MATRIZES PARA HEATMAP
# ============================================================

def criar_matriz(
    coluna
):

    matriz = df.pivot(
        index="inclinacao_relativa_deg",
        columns="base_relativa_deg",
        values=coluna
    )

    matriz = matriz.sort_index(
        ascending=True
    )

    matriz = matriz.sort_index(
        axis=1,
        ascending=True
    )

    return matriz


matriz_E1 = criar_matriz(
    "E1_pp_V_m"
)

matriz_E2 = criar_matriz(
    "E2_pp_V_m"
)

matriz_E = criar_matriz(
    "E_magnitude_V_m"
)

matriz_E_percent = criar_matriz(
    "E_magnitude_percent"
)


# ============================================================
# FUNCAO HEATMAP ESCALAR
#
# SEM SETAS
# ============================================================

def plotar_heatmap(
    matriz,
    titulo,
    label,
    nome_arquivo,
    marcar_maximo=None
):

    x = matriz.columns.to_numpy(
        dtype=float
    )

    y = matriz.index.to_numpy(
        dtype=float
    )

    z = matriz.to_numpy(
        dtype=float
    )


    fig, ax = plt.subplots(
        figsize=(8, 7)
    )


    imagem = ax.imshow(
        z,

        origin="lower",

        aspect="equal",

        extent=[
            x.min() - 5,
            x.max() + 5,
            y.min() - 5,
            y.max() + 5
        ]
    )


    cbar = plt.colorbar(
        imagem,
        ax=ax
    )

    cbar.set_label(
        label
    )


    if marcar_maximo is not None:

        ax.scatter(
            marcar_maximo[
                "base_relativa_deg"
            ],

            marcar_maximo[
                "inclinacao_relativa_deg"
            ],

            marker="x",

            s=150,

            linewidths=2.5
        )


    ax.set_xlabel(
        "Base relative angle (°)"
    )

    ax.set_ylabel(
        "Inclination relative angle (°)"
    )

    ax.set_title(
        titulo
    )

    ax.set_xticks(
        x
    )

    ax.set_yticks(
        y
    )


    plt.tight_layout()


    plt.savefig(
        PASTA_SAIDA
        /
        nome_arquivo,

        dpi=300,

        bbox_inches="tight"
    )


    plt.show()


# ============================================================
# CH1
#
# SOMENTE COMPONENTE ESCALAR
# ============================================================

plotar_heatmap(
    matriz_E1,

    "Electric field component - CH1",

    "E1 peak-to-peak (V/m)",

    "campo_eletrico_CH1.png",

    marcar_maximo=linha_E1
)


# ============================================================
# CH2
#
# SOMENTE COMPONENTE ESCALAR
# ============================================================

plotar_heatmap(
    matriz_E2,

    "Electric field component - CH2",

    "E2 peak-to-peak (V/m)",

    "campo_eletrico_CH2.png",

    marcar_maximo=linha_E2
)


# ============================================================
# MAGNITUDE
#
# SEM SETAS
# ============================================================

plotar_heatmap(
    matriz_E,

    "Electric field magnitude",

    "|E| (V/m)",

    "campo_eletrico_magnitude.png",

    marcar_maximo=linha_E
)


# ============================================================
# MAGNITUDE NORMALIZADA
# ============================================================

plotar_heatmap(
    matriz_E_percent,

    "Normalized electric field magnitude",

    "Normalized |E| (%)",

    "campo_eletrico_magnitude_normalizada.png",

    marcar_maximo=linha_E
)


# ============================================================
# MAPA VETORIAL
#
# AQUI SIM CH1 + CH2 FORMAM A SETA
# ============================================================

X = (
    df["base_relativa_deg"]
    .to_numpy(dtype=float)
)

Y = (
    df["inclinacao_relativa_deg"]
    .to_numpy(dtype=float)
)

U_bruto = (
    df["E1_assinado_V_m"]
    .to_numpy(dtype=float)
)

V_bruto = (
    df["E2_assinado_V_m"]
    .to_numpy(dtype=float)
)

M_vetor = np.sqrt(
    U_bruto ** 2
    +
    V_bruto ** 2
)


# ============================================================
# NORMALIZAR APENAS O TAMANHO DAS SETAS
#
# Assim a seta mostra direcao/sentido.
# A cor mostra intensidade.
# ============================================================

M_seguro = np.where(
    M_vetor > 0,
    M_vetor,
    1.0
)

U = (
    U_bruto
    /
    M_seguro
)

V = (
    V_bruto
    /
    M_seguro
)


fig, ax = plt.subplots(
    figsize=(8, 8)
)


q = ax.quiver(
    X,
    Y,

    U,
    V,

    M_vetor,

    angles="xy",

    scale_units="xy",

    scale=0.13,

    width=0.004,

    headwidth=4.5,

    headlength=5.5,

    headaxislength=4.5,

    pivot="middle"
)


cbar = plt.colorbar(
    q,
    ax=ax
)

cbar.set_label(
    "Instantaneous |E| (V/m)"
)


ax.axhline(
    0,
    linewidth=0.8,
    alpha=0.3
)

ax.axvline(
    0,
    linewidth=0.8,
    alpha=0.3
)


ax.set_xlabel(
    "Base relative angle (°)"
)

ax.set_ylabel(
    "Inclination relative angle (°)"
)

ax.set_title(
    "Electric field vector map"
)


ax.set_xticks(
    sorted(
        df[
            "base_relativa_deg"
        ].unique()
    )
)

ax.set_yticks(
    sorted(
        df[
            "inclinacao_relativa_deg"
        ].unique()
    )
)


ax.set_aspect(
    "equal"
)

ax.grid(
    True,
    alpha=0.2
)


plt.tight_layout()


plt.savefig(
    PASTA_SAIDA
    /
    "campo_eletrico_vetorial.png",

    dpi=300,

    bbox_inches="tight"
)


plt.show()


# ============================================================
# SUPERFICIE 3D DA MAGNITUDE
# ============================================================

x = matriz_E.columns.to_numpy(
    dtype=float
)

y = matriz_E.index.to_numpy(
    dtype=float
)

XX, YY = np.meshgrid(
    x,
    y
)

ZZ = matriz_E.to_numpy(
    dtype=float
)


fig = plt.figure(
    figsize=(9, 7)
)

ax = fig.add_subplot(
    111,
    projection="3d"
)


ax.plot_surface(
    XX,
    YY,
    ZZ,

    edgecolor="none",

    alpha=0.9
)


ax.set_xlabel(
    "Base relative angle (°)"
)

ax.set_ylabel(
    "Inclination relative angle (°)"
)

ax.set_zlabel(
    "|E| (V/m)"
)

ax.set_title(
    "Angular electric field surface"
)


plt.tight_layout()


plt.savefig(
    PASTA_SAIDA
    /
    "superficie_3D_campo_eletrico.png",

    dpi=300,

    bbox_inches="tight"
)


plt.show()


# ============================================================
# PERFIL BASE
#
# inclinacao = 0
# ============================================================

perfil_base = df[
    df[
        "inclinacao_relativa_deg"
    ] == 0
].sort_values(
    "base_relativa_deg"
)


fig, ax = plt.subplots(
    figsize=(8, 5)
)

ax.plot(
    perfil_base[
        "base_relativa_deg"
    ],

    perfil_base[
        "E_magnitude_V_m"
    ],

    marker="o"
)


ax.set_xlabel(
    "Base relative angle (°)"
)

ax.set_ylabel(
    "|E| (V/m)"
)

ax.set_title(
    "Electric field profile - Base"
)

ax.grid(
    True,
    alpha=0.3
)


plt.tight_layout()


plt.savefig(
    PASTA_SAIDA
    /
    "perfil_base.png",

    dpi=300,

    bbox_inches="tight"
)


plt.show()


# ============================================================
# PERFIL INCLINACAO
#
# base = 0
# ============================================================

perfil_inc = df[
    df[
        "base_relativa_deg"
    ] == 0
].sort_values(
    "inclinacao_relativa_deg"
)


fig, ax = plt.subplots(
    figsize=(8, 5)
)

ax.plot(
    perfil_inc[
        "inclinacao_relativa_deg"
    ],

    perfil_inc[
        "E_magnitude_V_m"
    ],

    marker="o"
)


ax.set_xlabel(
    "Inclination relative angle (°)"
)

ax.set_ylabel(
    "|E| (V/m)"
)

ax.set_title(
    "Electric field profile - Inclination"
)

ax.grid(
    True,
    alpha=0.3
)


plt.tight_layout()


plt.savefig(
    PASTA_SAIDA
    /
    "perfil_inclinacao.png",

    dpi=300,

    bbox_inches="tight"
)


plt.show()


# ============================================================
# SALVAR CSV PROCESSADO
# ============================================================

ARQUIVO_PROCESSADO = (
    PASTA_SAIDA
    /
    "resumo_campo_eletrico_processado.csv"
)

df.to_csv(
    ARQUIVO_PROCESSADO,
    index=False
)


# ============================================================
# FINAL
# ============================================================

print()
print("=" * 70)
print("PROCESSAMENTO FINALIZADO")
print("=" * 70)

print()

print(
    f"|E| max = "
    f"{linha_E['E_magnitude_V_m']:.2f} V/m"
)

print(
    f"Base relativa = "
    f"{linha_E['base_relativa_deg']:.1f} graus"
)

print(
    f"Inclinacao relativa = "
    f"{linha_E['inclinacao_relativa_deg']:.1f} graus"
)

print()

print(
    f"Instante usado para as setas = "
    f"{tempo_pico*1e6:.3f} us"
)

print()

print(
    "Mapas CH1 e CH2 = componentes escalares."
)

print(
    "Mapa vetorial = CH1 + CH2 juntos."
)

print()

print(
    "Resultados salvos em:"
)

print(
    PASTA_SAIDA.resolve()
)

print("=" * 70)