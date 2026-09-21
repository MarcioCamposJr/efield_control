import csv
from pathlib import Path
import matplotlib.pyplot as plt

# ============================================================
# CONFIGURAÇÕES
# ============================================================

ARQUIVO_RESUMO = Path("data/data") / "tms_pico_a_pico_teste_45a63" / "resumo_pico_a_pico.csv"

PASTA_PROCESSADA = Path("data/data") / "tms_pico_a_pico_teste_45a63" / "processado_ch2"
PASTA_PROCESSADA.mkdir(parents=True, exist_ok=True)

ARQUIVO_PROCESSADO = PASTA_PROCESSADA / "resumo_processado_ch2.csv"
GRAFICO_CH2 = PASTA_PROCESSADA / "grafico_ch2_vpp_vs_intensidade.png"
GRAFICO_RESIDUOS = PASTA_PROCESSADA / "grafico_residuos_ch2.png"


# ============================================================
# FUNÇÕES
# ============================================================

def ajuste_linear(x, y):
    """
    Ajuste linear manual: y = a*x + b
    Retorna a, b, y_fit e R².
    """

    n = len(x)

    soma_x = sum(x)
    soma_y = sum(y)
    soma_x2 = sum(xi**2 for xi in x)
    soma_xy = sum(xi * yi for xi, yi in zip(x, y))

    denominador = n * soma_x2 - soma_x**2

    if denominador == 0:
        raise ValueError("Não foi possível ajustar reta: denominador zero.")

    a = (n * soma_xy - soma_x * soma_y) / denominador
    b = (soma_y - a * soma_x) / n

    y_fit = [a * xi + b for xi in x]

    media_y = sum(y) / n
    ss_res = sum((yi - yfi)**2 for yi, yfi in zip(y, y_fit))
    ss_tot = sum((yi - media_y)**2 for yi in y)

    if ss_tot == 0:
        r2 = float("nan")
    else:
        r2 = 1 - ss_res / ss_tot

    return a, b, y_fit, r2


# ============================================================
# LEITURA DO CSV
# ============================================================

dados = []

with open(ARQUIVO_RESUMO, "r", newline="") as arquivo:
    leitor = csv.DictReader(arquivo)

    for linha in leitor:
        intensidade = float(linha["intensidade_TMS_percent"])
        ch2_vpp = float(linha["ch2_vpp_V"])
        ch2_vmax = float(linha["ch2_vmax_V"])
        ch2_vmin = float(linha["ch2_vmin_V"])

        dados.append({
            "medida": int(linha["medida"]),
            "intensidade": intensidade,
            "ch2_vmax_V": ch2_vmax,
            "ch2_vmin_V": ch2_vmin,
            "ch2_vpp_V": ch2_vpp,
            "ch2_vpp_mV": ch2_vpp * 1000,
            "arquivo_waveform": linha["arquivo_waveform"],
            "timestamp": linha["timestamp"]
        })

# Ordena por intensidade
dados = sorted(dados, key=lambda d: d["intensidade"])

x = [d["intensidade"] for d in dados]
y = [d["ch2_vpp_V"] for d in dados]


# ============================================================
# AJUSTE LINEAR
# ============================================================

a, b, y_fit, r2 = ajuste_linear(x, y)

for d, yf in zip(dados, y_fit):
    d["ch2_vpp_fit_V"] = yf
    d["residuo_ch2_V"] = d["ch2_vpp_V"] - yf


# ============================================================
# SALVAR CSV PROCESSADO
# ============================================================

with open(ARQUIVO_PROCESSADO, "w", newline="") as arquivo:
    campos = [
        "medida",
        "intensidade",
        "ch2_vmax_V",
        "ch2_vmin_V",
        "ch2_vpp_V",
        "ch2_vpp_mV",
        "ch2_vpp_fit_V",
        "residuo_ch2_V",
        "arquivo_waveform",
        "timestamp"
    ]

    escritor = csv.DictWriter(arquivo, fieldnames=campos)
    escritor.writeheader()

    for d in dados:
        escritor.writerow(d)


# ============================================================
# RESULTADOS NO TERMINAL
# ============================================================

print("\nArquivo lido:")
print(ARQUIVO_RESUMO)

print("\nCSV processado salvo em:")
print(ARQUIVO_PROCESSADO)

print("\n==============================")
print("AJUSTE LINEAR — CANAL 2")
print("==============================")
print(f"Vpp_CH2 = {a:.6e} * intensidade + {b:.6e}")
print(f"R² = {r2:.6f}")

print("\nTabela resumida:")
print("Intensidade (%) | CH2 Vpp (V) | CH2 Vpp (mV)")
print("---------------------------------------------")

for d in dados:
    print(f"{d['intensidade']:>15.1f} | {d['ch2_vpp_V']:>10.6f} | {d['ch2_vpp_mV']:>11.3f}")


# ============================================================
# GRÁFICO 1 — CH2 VPP VS INTENSIDADE
# ============================================================

plt.figure(figsize=(9, 5))

plt.scatter(x, y, label="CH2 medido")
plt.plot(x, y_fit, label=f"Ajuste linear — R² = {r2:.4f}")

plt.xlabel("Intensidade do TMS (%)")
plt.ylabel("CH2 Vpp (V)")
plt.title("Canal 2 — Pico a pico em função da intensidade do TMS")
plt.grid(True)
plt.legend()
plt.tight_layout()
plt.savefig(GRAFICO_CH2, dpi=300)
plt.show()

print("\nGráfico CH2 salvo em:")
print(GRAFICO_CH2)


# ============================================================
# GRÁFICO 2 — RESÍDUOS DO CH2
# ============================================================

residuos = [d["residuo_ch2_V"] for d in dados]

plt.figure(figsize=(9, 5))

plt.axhline(0, linestyle="--", linewidth=1)
plt.scatter(x, residuos, label="Resíduo CH2")

plt.xlabel("Intensidade do TMS (%)")
plt.ylabel("Resíduo do ajuste linear (V)")
plt.title("Canal 2 — Resíduos do ajuste linear")
plt.grid(True)
plt.legend()
plt.tight_layout()
plt.savefig(GRAFICO_RESIDUOS, dpi=300)
plt.show()

print("\nGráfico de resíduos salvo em:")
print(GRAFICO_RESIDUOS)


# ============================================================
# FINAL
# ============================================================

print("\nProcessamento finalizado.")
