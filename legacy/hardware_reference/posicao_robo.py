import time
import csv
from pathlib import Path
from datetime import datetime

import numpy as np
import serial

from efield_control.drivers.red_pitaya import scpi
from efield_control.drivers.robots.elfin import Elfin


# ============================================================
# OTIMIZACAO AUTOMATICA DO CENTRO DA BOBINA
#
# ROBÔ:
#   procura o máximo em X/Y
#
# ESP32:
#   mantém servos centralizados
#   dispara TMS
#
# RED PITAYA:
#   trigger externo DIO0_P
#   IN1 + IN2 em HV
#
# CRITERIO:
#
# M = sqrt(P2P_CH1^2 + P2P_CH2^2)
#
# ============================================================


# ============================================================
# RED PITAYA
# ============================================================

RP_IP = "169.254.197.73"
RP_PORT = 5000


# ============================================================
# ROBO
# ============================================================

ROBOT_IP = "169.254.153.251"


# ============================================================
# ESP32
# ============================================================

# TROQUE PARA A PORTA DO SEU ESP32
ESP_PORT = "COM7"

ESP_BAUD = 115200

ESP_TIMEOUT = 3


# ============================================================
# AQUISICAO
# ============================================================

DEC = 8

# Trigger OUT do TMS -> DIO0_P
TRIGGER_SOURCE = "EXT_PE"

TRIGGER_DELAY = 0

TIMEOUT_TRIGGER = 10
TIMEOUT_BUFFER = 10


# ============================================================
# OTIMIZACAO
# ============================================================

PASSO_INICIAL = 1.0      # mm
PASSO_MINIMO = 0.5       # mm

MAX_ITERACOES = 20

# 0.5 %
TOLERANCIA_RELATIVA = 0.005


# ============================================================
# TEMPOS
# ============================================================

TEMPO_ESTABILIZACAO_ROBO = 1.0

TEMPO_ENTRE_DISPAROS = 2.0

TIMEOUT_MOVIMENTO = 30


# ============================================================
# REPETICOES
# ============================================================

# Para o primeiro teste:
N_REPETICOES = 1

# Depois recomendo:
# N_REPETICOES = 3


# ============================================================
# PASTA
# ============================================================

timestamp = datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

PASTA = Path(
    f"data/otimizacao_centro_{timestamp}"
)

PASTA.mkdir(
    parents=True,
    exist_ok=True
)

CSV_RESULTADOS = (
    PASTA
    / "otimizacao_centro.csv"
)


# ============================================================
# CONECTAR RED PITAYA
# ============================================================

print()
print("=" * 70)
print("OTIMIZACAO AUTOMATICA DO CENTRO")
print("=" * 70)

print()
print("Conectando a Red Pitaya...")


rp = scpi(
    RP_IP,
    RP_PORT
)


print(
    "Red Pitaya conectada."
)


# ============================================================
# CONECTAR ESP32
# ============================================================

print()
print(
    f"Conectando ao ESP32 em {ESP_PORT}..."
)


esp = serial.Serial(
    ESP_PORT,
    ESP_BAUD,
    timeout=ESP_TIMEOUT
)


# ESP normalmente reinicia quando abre a Serial
time.sleep(
    3
)


# limpar buffer
esp.reset_input_buffer()


print(
    "ESP32 conectado."
)


# ============================================================
# TESTAR ESP32
# ============================================================

def enviar_esp(
    comando
):

    esp.write(
        (
            comando
            +
            "\n"
        ).encode()
    )

    esp.flush()


def esperar_resposta_esp(
    resposta_esperada,
    timeout=5
):

    inicio = time.time()


    while (
        time.time() - inicio
        <
        timeout
    ):

        linha = (
            esp.readline()
            .decode(
                errors="ignore"
            )
            .strip()
        )


        if linha:

            print(
                f"ESP32: {linha}"
            )


        if (
            linha
            ==
            resposta_esperada
        ):

            return True


    return False


print()
print(
    "Testando comunicacao com ESP32..."
)


enviar_esp(
    "PING"
)


if not esperar_resposta_esp(
    "PONG"
):

    raise RuntimeError(
        "ESP32 nao respondeu PONG."
    )


print(
    "Comunicacao ESP32 OK."
)


# ============================================================
# CENTRALIZAR SERVOS
# ============================================================

print()
print(
    "Centralizando servos..."
)


enviar_esp(
    "CENTER"
)


if not esperar_resposta_esp(
    "SERVOS_OK"
):

    raise RuntimeError(
        "ESP32 nao confirmou posicao central."
    )


print(
    "Servos centralizados."
)


# ============================================================
# CONECTAR ROBO
# ============================================================

print()
print(
    "Conectando ao robo Elfin..."
)


robo = Elfin(
    ROBOT_IP
)


robo.connect()


print(
    "Robo conectado."
)


# ============================================================
# LER POSE
# ============================================================

ok, pose_inicial = robo.get_pose()


if not ok:

    raise RuntimeError(
        "Nao foi possivel ler a pose do robo."
    )


if (
    pose_inicial is None
    or
    len(pose_inicial) < 6
):

    raise RuntimeError(
        f"Pose invalida: {pose_inicial}"
    )


X0 = float(
    pose_inicial[0]
)

Y0 = float(
    pose_inicial[1]
)

Z0 = float(
    pose_inicial[2]
)

RX0 = float(
    pose_inicial[3]
)

RY0 = float(
    pose_inicial[4]
)

RZ0 = float(
    pose_inicial[5]
)


print()
print("=" * 70)
print("POSE INICIAL")
print("=" * 70)

print(
    f"X  = {X0:.3f} mm"
)

print(
    f"Y  = {Y0:.3f} mm"
)

print(
    f"Z  = {Z0:.3f} mm"
)

print(
    f"RX = {RX0:.3f}"
)

print(
    f"RY = {RY0:.3f}"
)

print(
    f"RZ = {RZ0:.3f}"
)


# ============================================================
# CSV
# ============================================================

with open(
    CSV_RESULTADOS,
    "w",
    newline="",
    encoding="utf-8"
) as arquivo:

    writer = csv.writer(
        arquivo
    )

    writer.writerow(
        [
            "iteracao",
            "ponto",

            "passo_mm",

            "x_mm",
            "y_mm",
            "z_mm",

            "p2p_ch1_V",
            "p2p_ch2_V",

            "magnitude_V",

            "melhor"
        ]
    )


# ============================================================
# MOVER ROBO
# ============================================================

def mover_robo(
    x,
    y
):

    pose_alvo = [
        float(x),
        float(y),

        Z0,

        RX0,
        RY0,
        RZ0
    ]


    print()
    print(
        f"ROBO -> "
        f"X={x:.3f} mm | "
        f"Y={y:.3f} mm"
    )


    robo.connection.move_linear(
        pose_alvo
    )


    inicio = time.time()


    while (
        robo.is_moving()
    ):

        if (
            robo.is_error_state()
        ):

            raise RuntimeError(
                "Robo entrou em erro."
            )


        if (
            time.time()
            -
            inicio
            >
            TIMEOUT_MOVIMENTO
        ):

            raise TimeoutError(
                "Timeout no movimento do robo."
            )


        time.sleep(
            0.05
        )


    time.sleep(
        TEMPO_ESTABILIZACAO_ROBO
    )


# ============================================================
# ARMAR RED PITAYA
# ============================================================

def armar_aquisicao():

    rp.tx_txt(
        "ACQ:RST"
    )

    time.sleep(
        0.05
    )


    # ========================================================
    # HV
    # ========================================================

    rp.tx_txt(
        "ACQ:SOUR1:GAIN HV"
    )

    rp.tx_txt(
        "ACQ:SOUR2:GAIN HV"
    )


    # ========================================================
    # FORMATO
    # ========================================================

    rp.tx_txt(
        "ACQ:DATA:FORMAT ASCII"
    )

    rp.tx_txt(
        "ACQ:DATA:UNITS VOLTS"
    )


    # ========================================================
    # DEC
    # ========================================================

    rp.tx_txt(
        f"ACQ:DEC {DEC}"
    )


    rp.tx_txt(
        f"ACQ:TRIG:DLY {TRIGGER_DELAY}"
    )


    # ========================================================
    # START
    # ========================================================

    rp.tx_txt(
        "ACQ:START"
    )


    time.sleep(
        0.05
    )


    # ========================================================
    # EXT TRIGGER
    #
    # TMS Trigger OUT -> DIO0_P
    # ========================================================

    rp.tx_txt(
        f"ACQ:TRIG {TRIGGER_SOURCE}"
    )


# ============================================================
# DISPARAR TMS PELO ESP32
# ============================================================

def disparar_tms():

    print(
        "ESP32 -> disparando TMS..."
    )


    # limpar mensagens anteriores
    esp.reset_input_buffer()


    enviar_esp(
        "FIRE"
    )


    if not esperar_resposta_esp(
        "FIRE_DONE",
        timeout=3
    ):

        raise RuntimeError(
            "ESP32 nao confirmou disparo do TMS."
        )


# ============================================================
# ESPERAR TRIGGER OUT
# ============================================================

def esperar_trigger():

    inicio = time.time()


    while True:

        rp.tx_txt(
            "ACQ:TRIG:STAT?"
        )


        estado = (
            rp.rx_txt()
            .strip()
        )


        if (
            estado
            ==
            "TD"
        ):

            return True


        if (
            time.time()
            -
            inicio
            >
            TIMEOUT_TRIGGER
        ):

            return False


        time.sleep(
            0.001
        )


# ============================================================
# ESPERAR BUFFER
# ============================================================

def esperar_buffer():

    inicio = time.time()


    while True:

        rp.tx_txt(
            "ACQ:TRIG:FILL?"
        )


        estado = (
            rp.rx_txt()
            .strip()
        )


        if (
            estado
            ==
            "1"
        ):

            return True


        if (
            time.time()
            -
            inicio
            >
            TIMEOUT_BUFFER
        ):

            return False


        time.sleep(
            0.001
        )


# ============================================================
# LER CANAL
# ============================================================

def ler_canal(
    canal
):

    rp.tx_txt(
        f"ACQ:SOUR{canal}:DATA?"
    )


    resposta = (
        rp.rx_txt()
        .strip()
        .strip("{}")
    )


    dados = np.fromstring(
        resposta,
        dtype=float,
        sep=","
    )


    return dados


# ============================================================
# MEDIR
# ============================================================

def medir_uma_vez():

    # ========================================================
    # RP ARMADA PRIMEIRO
    # ========================================================

    armar_aquisicao()


    # ========================================================
    # ESP32 DISPARA O TMS
    # ========================================================

    disparar_tms()


    # ========================================================
    # TRIGGER OUT REAL
    # ========================================================

    print(
        "Esperando Trigger OUT..."
    )


    if not esperar_trigger():

        raise TimeoutError(
            "Trigger OUT do TMS nao detectado."
        )


    print(
        "Trigger OUT detectado."
    )


    # ========================================================
    # BUFFER
    # ========================================================

    if not esperar_buffer():

        raise TimeoutError(
            "Buffer nao completou."
        )


    # ========================================================
    # CH1 E CH2
    # ========================================================

    ch1 = ler_canal(
        1
    )

    ch2 = ler_canal(
        2
    )


    if (
        len(ch1) == 0
        or
        len(ch2) == 0
    ):

        raise RuntimeError(
            "CH1 ou CH2 vazio."
        )


    # ========================================================
    # P2P
    # ========================================================

    p2p_ch1 = float(
        np.max(ch1)
        -
        np.min(ch1)
    )


    p2p_ch2 = float(
        np.max(ch2)
        -
        np.min(ch2)
    )


    # ========================================================
    # MAGNITUDE
    # ========================================================

    magnitude = float(
        np.sqrt(
            p2p_ch1 ** 2
            +
            p2p_ch2 ** 2
        )
    )


    return (
        p2p_ch1,
        p2p_ch2,
        magnitude
    )


# ============================================================
# MEDIR PONTO COM REPETICOES
# ============================================================

def medir_ponto():

    lista_ch1 = []
    lista_ch2 = []
    lista_mag = []


    for repeticao in range(
        1,
        N_REPETICOES + 1
    ):

        (
            ch1,
            ch2,
            mag
        ) = medir_uma_vez()


        lista_ch1.append(
            ch1
        )

        lista_ch2.append(
            ch2
        )

        lista_mag.append(
            mag
        )


        print(
            f"CH1={ch1:.6f} V | "
            f"CH2={ch2:.6f} V | "
            f"M={mag:.6f} V"
        )


        if (
            repeticao
            <
            N_REPETICOES
        ):

            time.sleep(
                TEMPO_ENTRE_DISPAROS
            )


    return (
        float(
            np.median(
                lista_ch1
            )
        ),
        float(
            np.median(
                lista_ch2
            )
        ),
        float(
            np.median(
                lista_mag
            )
        )
    )


# ============================================================
# AVALIAR POSICAO
# ============================================================

def avaliar_posicao(
    x,
    y
):

    mover_robo(
        x,
        y
    )


    return medir_ponto()


# ============================================================
# SALVAR
# ============================================================

def salvar(
    iteracao,
    nome,
    passo,
    x,
    y,
    ch1,
    ch2,
    mag,
    melhor
):

    with open(
        CSV_RESULTADOS,
        "a",
        newline="",
        encoding="utf-8"
    ) as arquivo:

        writer = csv.writer(
            arquivo
        )


        writer.writerow(
            [
                iteracao,
                nome,

                passo,

                x,
                y,
                Z0,

                ch1,
                ch2,

                mag,

                int(melhor)
            ]
        )


# ============================================================
# OTIMIZACAO
# ============================================================

x_atual = X0
y_atual = Y0

passo = PASSO_INICIAL


try:

    print()
    print("=" * 70)
    print("INICIANDO BUSCA LOCAL")
    print("=" * 70)


    # ========================================================
    # MEDIDA INICIAL
    # ========================================================

    print()
    print(
        "Medindo centro inicial..."
    )


    (
        ch1_atual,
        ch2_atual,
        mag_atual
    ) = avaliar_posicao(
        x_atual,
        y_atual
    )


    salvar(
        0,
        "centro_inicial",

        passo,

        x_atual,
        y_atual,

        ch1_atual,
        ch2_atual,
        mag_atual,

        True
    )


    print()
    print(
        f"M inicial = {mag_atual:.6f} V"
    )


    # ========================================================
    # ITERACOES
    # ========================================================

    for iteracao in range(
        1,
        MAX_ITERACOES + 1
    ):

        print()
        print("=" * 70)

        print(
            f"ITERACAO {iteracao}"
        )

        print(
            f"PASSO = {passo:.2f} mm"
        )

        print(
            f"X = {x_atual:.3f}"
        )

        print(
            f"Y = {y_atual:.3f}"
        )

        print(
            f"M = {mag_atual:.6f} V"
        )

        print("=" * 70)


        resultados = [
            (
                "centro",
                x_atual,
                y_atual,
                ch1_atual,
                ch2_atual,
                mag_atual
            )
        ]


        vizinhos = [

            (
                "+X",
                x_atual + passo,
                y_atual
            ),

            (
                "-X",
                x_atual - passo,
                y_atual
            ),

            (
                "+Y",
                x_atual,
                y_atual + passo
            ),

            (
                "-Y",
                x_atual,
                y_atual - passo
            )

        ]


        # ====================================================
        # MEDIR VIZINHOS
        # ====================================================

        for (
            nome,
            x,
            y
        ) in vizinhos:

            print()
            print(
                f"Testando {nome}"
            )


            (
                ch1,
                ch2,
                mag
            ) = avaliar_posicao(
                x,
                y
            )


            resultados.append(
                (
                    nome,
                    x,
                    y,
                    ch1,
                    ch2,
                    mag
                )
            )


            salvar(
                iteracao,
                nome,

                passo,

                x,
                y,

                ch1,
                ch2,
                mag,

                False
            )


        # ====================================================
        # MELHOR
        # ====================================================

        melhor = max(
            resultados,
            key=lambda v: v[5]
        )


        (
            nome_melhor,
            x_melhor,
            y_melhor,
            ch1_melhor,
            ch2_melhor,
            mag_melhor
        ) = melhor


        if mag_atual > 0:

            melhora = (
                mag_melhor
                -
                mag_atual
            ) / mag_atual

        else:

            melhora = np.inf


        print()
        print(
            f"Melhor: {nome_melhor}"
        )

        print(
            f"M = {mag_melhor:.6f} V"
        )

        print(
            f"Melhora = {100 * melhora:.3f}%"
        )


        # ====================================================
        # MELHOROU
        # ====================================================

        if (
            nome_melhor
            !=
            "centro"

            and

            melhora
            >
            TOLERANCIA_RELATIVA
        ):

            x_atual = x_melhor
            y_atual = y_melhor

            ch1_atual = ch1_melhor
            ch2_atual = ch2_melhor

            mag_atual = mag_melhor


            print()
            print(
                ">>> NOVO CENTRO <<<"
            )


            salvar(
                iteracao,
                "novo_centro",

                passo,

                x_atual,
                y_atual,

                ch1_atual,
                ch2_atual,
                mag_atual,

                True
            )


            mover_robo(
                x_atual,
                y_atual
            )


            continue


        # ====================================================
        # NAO MELHOROU
        # ====================================================

        print()
        print(
            "Nenhuma melhora significativa."
        )


        if (
            passo
            >
            PASSO_MINIMO
        ):

            passo = PASSO_MINIMO


            print(
                f"Reduzindo passo para {passo:.2f} mm."
            )


            mover_robo(
                x_atual,
                y_atual
            )


            continue


        # ====================================================
        # FINAL
        # ====================================================

        print(
            "Maximo local encontrado."
        )

        break


    # ========================================================
    # IR AO MELHOR PONTO
    # ========================================================

    mover_robo(
        x_atual,
        y_atual
    )


    print()
    print("=" * 70)
    print("OTIMIZACAO FINALIZADA")
    print("=" * 70)

    print(
        f"X = {x_atual:.3f} mm"
    )

    print(
        f"Y = {y_atual:.3f} mm"
    )

    print(
        f"Z = {Z0:.3f} mm"
    )

    print()

    print(
        f"CH1 = {ch1_atual:.6f} V"
    )

    print(
        f"CH2 = {ch2_atual:.6f} V"
    )

    print(
        f"M = {mag_atual:.6f} V"
    )


# ============================================================
# CTRL+C
# ============================================================

except KeyboardInterrupt:

    print()
    print(
        "Interrompido pelo usuario."
    )


    try:

        mover_robo(
            x_atual,
            y_atual
        )

    except Exception:

        pass


# ============================================================
# ERRO
# ============================================================

except Exception as erro:

    print()
    print("=" * 70)
    print("ERRO")
    print("=" * 70)

    print(
        erro
    )


    try:

        mover_robo(
            x_atual,
            y_atual
        )

    except Exception:

        pass


# ============================================================
# FINALIZACAO
# ============================================================

finally:

    try:

        esp.close()

    except Exception:

        pass


    print()
    print(
        "Resultados:"
    )

    print(
        CSV_RESULTADOS.resolve()
    )
