import time
import csv
from pathlib import Path
from datetime import datetime

import numpy as np
import serial

from efield_control.drivers.red_pitaya import scpi


# ============================================================
# MAPEAMENTO HEMISFERICO COMPLETO
#
# 0 -> 180 graus
# passo = 5 graus
#
# 37 x 37 = 1369 pontos
#
# ============================================================


# ============================================================
# RED PITAYA
# ============================================================

RP_IP = "169.254.197.73"
RP_PORT = 5000


# ============================================================
# ESP32
# ============================================================

ESP_PORT = "COM3"

ESP_BAUD = 115200

ESP_TIMEOUT = 3


# ============================================================
# AQUISICAO
# ============================================================

DEC = 8

FS = 125e6 / DEC

TRIGGER_SOURCE = "EXT_PE"

TRIGGER_DELAY = 0

TIMEOUT_TRIGGER = 10

TIMEOUT_BUFFER = 10


# ============================================================
# CENTROS MECANICOS
# ============================================================

CENTRO_BASE = 90

CENTRO_INCLINACAO = 92


# ============================================================
# ANGULOS
#
# 0, 5, 10, ..., 180
# ============================================================

ANGULOS_BASE = list(
    range(
        0,
        181,
        5
    )
)


ANGULOS_INCLINACAO = list(
    range(
        0,
        181,
        5
    )
)


TOTAL_PONTOS = (
    len(ANGULOS_BASE)
    *
    len(ANGULOS_INCLINACAO)
)


# ============================================================
# TEMPOS
# ============================================================

# Tempo extra depois da confirmacao do movimento
TEMPO_APOS_MOVIMENTO = 0.5

# Intervalo entre aquisicoes
TEMPO_ENTRE_DISPAROS = 2.0


# ============================================================
# PASTA DO EXPERIMENTO
# ============================================================

timestamp = datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)


PASTA = Path(
    f"data/mapeamento_hemisferico_37x37_{timestamp}"
)


PASTA.mkdir(
    parents=True,
    exist_ok=True
)


CSV_RESUMO = (
    PASTA
    /
    "resumo_mapeamento.csv"
)


# ============================================================
# FORMATAR TEMPO
# ============================================================

def formatar_tempo(segundos):

    segundos = max(
        0,
        int(segundos)
    )


    horas = (
        segundos
        //
        3600
    )


    minutos = (
        segundos
        %
        3600
    ) // 60


    segundos_restantes = (
        segundos
        %
        60
    )


    return (
        f"{horas:02d}:"
        f"{minutos:02d}:"
        f"{segundos_restantes:02d}"
    )


# ============================================================
# CONECTAR RED PITAYA
# ============================================================

print()
print("=" * 75)
print("MAPEAMENTO HEMISFERICO 37 x 37")
print("=" * 75)

print()
print(
    "Conectando Red Pitaya..."
)


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
    f"Conectando ESP32 em {ESP_PORT}..."
)


esp = serial.Serial(
    ESP_PORT,
    ESP_BAUD,
    timeout=ESP_TIMEOUT
)


# ESP pode reiniciar ao abrir a porta
time.sleep(
    5
)


esp.reset_input_buffer()


print(
    "ESP32 conectado."
)


# ============================================================
# SERIAL ESP32
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


def esperar_linha_esp(
    prefixo,
    timeout=5
):

    inicio = time.time()


    while (
        time.time()
        -
        inicio
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


        if linha.startswith(
            prefixo
        ):

            return linha


    return None


# ============================================================
# TESTAR ESP32
# ============================================================

print()
print(
    "Testando comunicacao com ESP32..."
)


enviar_esp(
    "PING"
)


resposta = esperar_linha_esp(
    "PONG",
    timeout=5
)


if resposta is None:

    raise RuntimeError(
        "ESP32 nao respondeu PONG."
    )


print(
    "ESP32 OK."
)


# ============================================================
# CENTRALIZAR
# ============================================================

print()
print(
    "Centralizando servos..."
)


enviar_esp(
    "CENTER"
)


resposta = esperar_linha_esp(
    "SERVOS_OK",
    timeout=5
)


if resposta is None:

    raise RuntimeError(
        "ESP32 nao confirmou CENTER."
    )


print()
print(
    f"Base centralizada em "
    f"{CENTRO_BASE} graus."
)

print(
    f"Inclinacao centralizada em "
    f"{CENTRO_INCLINACAO} graus."
)


# ============================================================
# CRIAR CSV
# ============================================================

with open(
    CSV_RESUMO,
    "w",
    newline="",
    encoding="utf-8"
) as arquivo:

    writer = csv.writer(
        arquivo
    )


    writer.writerow(
        [
            "indice",

            "servo_base_deg",
            "servo_inclinacao_deg",

            "base_relativa_centro_deg",
            "inclinacao_relativa_centro_deg",

            "max_ch1_V",
            "min_ch1_V",
            "p2p_ch1_V",

            "max_ch2_V",
            "min_ch2_V",
            "p2p_ch2_V",

            "magnitude_V",

            "arquivo_waveform",

            "tempo_ponto_s",
            "tempo_decorrido_s",
            "tempo_medio_ponto_s",
            "tempo_restante_estimado_s"
        ]
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


    # --------------------------------------------------------
    # GANHO HV
    # --------------------------------------------------------

    rp.tx_txt(
        "ACQ:SOUR1:GAIN HV"
    )

    rp.tx_txt(
        "ACQ:SOUR2:GAIN HV"
    )


    # --------------------------------------------------------
    # FORMATO
    # --------------------------------------------------------

    rp.tx_txt(
        "ACQ:DATA:FORMAT ASCII"
    )

    rp.tx_txt(
        "ACQ:DATA:UNITS VOLTS"
    )


    # --------------------------------------------------------
    # DECIMACAO
    # --------------------------------------------------------

    rp.tx_txt(
        f"ACQ:DEC {DEC}"
    )


    # --------------------------------------------------------
    # TRIGGER DELAY
    # --------------------------------------------------------

    rp.tx_txt(
        f"ACQ:TRIG:DLY {TRIGGER_DELAY}"
    )


    # --------------------------------------------------------
    # START
    # --------------------------------------------------------

    rp.tx_txt(
        "ACQ:START"
    )


    time.sleep(
        0.05
    )


    # --------------------------------------------------------
    # TMS Trigger OUT -> DIO0_P
    # --------------------------------------------------------

    rp.tx_txt(
        f"ACQ:TRIG {TRIGGER_SOURCE}"
    )


# ============================================================
# MOVER SERVOS
# ============================================================

def mover_servos(
    base_deg,
    inclinacao_deg
):

    comando = (
        f"MOVEABS,"
        f"{base_deg},"
        f"{inclinacao_deg}"
    )


    print()
    print(
        f"Servo BASE       = "
        f"{base_deg:3d} graus"
    )

    print(
        f"Servo INCLINACAO = "
        f"{inclinacao_deg:3d} graus"
    )


    esp.reset_input_buffer()


    enviar_esp(
        comando
    )


    resposta = esperar_linha_esp(
        "MOVED",
        timeout=5
    )


    if resposta is None:

        raise RuntimeError(
            "ESP32 nao confirmou movimento."
        )


    time.sleep(
        TEMPO_APOS_MOVIMENTO
    )


# ============================================================
# DISPARAR TMS
# ============================================================

def disparar_tms():

    print(
        "Disparando TMS..."
    )


    esp.reset_input_buffer()


    enviar_esp(
        "FIRE"
    )


    resposta = esperar_linha_esp(
        "FIRE_DONE",
        timeout=3
    )


    if resposta is None:

        raise RuntimeError(
            "ESP32 nao confirmou FIRE."
        )


# ============================================================
# ESPERAR TRIGGER
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


        if estado == "TD":

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


        if estado == "1":

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


    if len(dados) == 0:

        raise RuntimeError(
            f"Canal {canal} vazio."
        )


    return dados


# ============================================================
# MEDIR UM PONTO
# ============================================================

def medir_ponto():

    # ========================================================
    # 1. ARMAR RP
    # ========================================================

    armar_aquisicao()


    # ========================================================
    # 2. DISPARAR TMS
    # ========================================================

    disparar_tms()


    # ========================================================
    # 3. ESPERAR TRIGGER OUT
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
    # 4. ESPERAR BUFFER
    # ========================================================

    if not esperar_buffer():

        raise TimeoutError(
            "Buffer nao completou."
        )


    # ========================================================
    # 5. LER CH1 + CH2
    # ========================================================

    ch1 = ler_canal(
        1
    )

    ch2 = ler_canal(
        2
    )


    # ========================================================
    # CH1
    # ========================================================

    max_ch1 = float(
        np.max(ch1)
    )


    min_ch1 = float(
        np.min(ch1)
    )


    p2p_ch1 = (
        max_ch1
        -
        min_ch1
    )


    # ========================================================
    # CH2
    # ========================================================

    max_ch2 = float(
        np.max(ch2)
    )


    min_ch2 = float(
        np.min(ch2)
    )


    p2p_ch2 = (
        max_ch2
        -
        min_ch2
    )


    # ========================================================
    # MAGNITUDE COMBINADA
    # ========================================================

    magnitude = float(
        np.sqrt(
            p2p_ch1 ** 2
            +
            p2p_ch2 ** 2
        )
    )


    return (
        ch1,
        ch2,

        max_ch1,
        min_ch1,
        p2p_ch1,

        max_ch2,
        min_ch2,
        p2p_ch2,

        magnitude
    )


# ============================================================
# TRAJETORIA SERPENTINA
# ============================================================

trajetoria = []


for i, base_deg in enumerate(
    ANGULOS_BASE
):


    if i % 2 == 0:

        inclinacoes = (
            ANGULOS_INCLINACAO
        )


    else:

        inclinacoes = list(
            reversed(
                ANGULOS_INCLINACAO
            )
        )


    for inclinacao_deg in inclinacoes:

        trajetoria.append(
            (
                base_deg,
                inclinacao_deg
            )
        )


# ============================================================
# MOSTRAR CONFIGURACAO
# ============================================================

print()
print("=" * 75)
print("CONFIGURACAO DO EXPERIMENTO")
print("=" * 75)

print(
    "Base:         0 -> 180 graus"
)

print(
    "Inclinacao:   0 -> 180 graus"
)

print(
    "Passo:        5 graus"
)

print(
    f"Pontos/eixo:  "
    f"{len(ANGULOS_BASE)}"
)

print(
    f"Total:        "
    f"{TOTAL_PONTOS}"
)

print(
    f"Centro base:  "
    f"{CENTRO_BASE} graus"
)

print(
    f"Centro inc.:  "
    f"{CENTRO_INCLINACAO} graus"
)

print(
    f"FS:           "
    f"{FS/1e6:.6f} MS/s"
)

print("=" * 75)


# ============================================================
# TIMER GLOBAL
# ============================================================

tempo_inicio_experimento = (
    time.time()
)


# ============================================================
# MAPEAMENTO
# ============================================================

try:

    print()
    print("=" * 75)
    print("INICIANDO MAPEAMENTO 37 x 37")
    print("=" * 75)


    for indice, (
        base_deg,
        inclinacao_deg
    ) in enumerate(
        trajetoria,
        start=1
    ):


        tempo_inicio_ponto = (
            time.time()
        )


        print()
        print("=" * 75)

        print(
            f"PONTO "
            f"{indice}/{TOTAL_PONTOS}"
        )

        print("=" * 75)


        # ====================================================
        # ANGULOS RELATIVOS AO CENTRO
        # ====================================================

        base_rel = (
            base_deg
            -
            CENTRO_BASE
        )


        inclinacao_rel = (
            inclinacao_deg
            -
            CENTRO_INCLINACAO
        )


        print(
            f"Base relativa = "
            f"{base_rel:+d} graus"
        )

        print(
            f"Inclinacao relativa = "
            f"{inclinacao_rel:+d} graus"
        )


        # ====================================================
        # MOVER
        # ====================================================

        mover_servos(
            base_deg,
            inclinacao_deg
        )


        # ====================================================
        # MEDIR
        # ====================================================

        (
            ch1,
            ch2,

            max_ch1,
            min_ch1,
            p2p_ch1,

            max_ch2,
            min_ch2,
            p2p_ch2,

            magnitude

        ) = medir_ponto()


        # ====================================================
        # WAVEFORM
        # ====================================================

        nome_waveform = (

            f"waveform_"
            f"{indice:04d}_"
            f"base{base_deg:03d}_"
            f"inc{inclinacao_deg:03d}.csv"

        )


        arquivo_waveform = (
            PASTA
            /
            nome_waveform
        )


        n = min(
            len(ch1),
            len(ch2)
        )


        eixo_tempo = (
            np.arange(n)
            /
            FS
        )


        with open(
            arquivo_waveform,
            "w",
            newline="",
            encoding="utf-8"
        ) as arquivo:


            writer = csv.writer(
                arquivo
            )


            writer.writerow(
                [
                    "time_s",
                    "ch1_V",
                    "ch2_V"
                ]
            )


            writer.writerows(
                zip(
                    eixo_tempo,
                    ch1[:n],
                    ch2[:n]
                )
            )


        # ====================================================
        # TIMER
        # ====================================================

        tempo_agora = (
            time.time()
        )


        tempo_ponto = (
            tempo_agora
            -
            tempo_inicio_ponto
        )


        tempo_decorrido = (
            tempo_agora
            -
            tempo_inicio_experimento
        )


        tempo_medio = (
            tempo_decorrido
            /
            indice
        )


        pontos_restantes = (
            TOTAL_PONTOS
            -
            indice
        )


        tempo_restante = (
            tempo_medio
            *
            pontos_restantes
        )


        progresso = (
            indice
            /
            TOTAL_PONTOS
            *
            100
        )


        # ====================================================
        # SALVAR RESUMO
        # ====================================================

        with open(
            CSV_RESUMO,
            "a",
            newline="",
            encoding="utf-8"
        ) as arquivo:


            writer = csv.writer(
                arquivo
            )


            writer.writerow(
                [
                    indice,

                    base_deg,
                    inclinacao_deg,

                    base_rel,
                    inclinacao_rel,

                    max_ch1,
                    min_ch1,
                    p2p_ch1,

                    max_ch2,
                    min_ch2,
                    p2p_ch2,

                    magnitude,

                    str(
                        arquivo_waveform
                    ),

                    tempo_ponto,
                    tempo_decorrido,
                    tempo_medio,
                    tempo_restante
                ]
            )


        # ====================================================
        # PRINT
        # ====================================================

        print()

        print(
            f"CH1 P2P = "
            f"{p2p_ch1:.6f} V"
        )

        print(
            f"CH2 P2P = "
            f"{p2p_ch2:.6f} V"
        )

        print(
            f"Magnitude = "
            f"{magnitude:.6f} V"
        )


        print()
        print("-" * 75)
        print("TIMER")
        print("-" * 75)

        print(
            f"Progresso: "
            f"{progresso:.2f}%"
        )

        print(
            f"Pontos: "
            f"{indice}/{TOTAL_PONTOS}"
        )

        print(
            f"Tempo deste ponto: "
            f"{tempo_ponto:.2f} s"
        )

        print(
            f"Tempo decorrido: "
            f"{formatar_tempo(tempo_decorrido)}"
        )

        print(
            f"Media por ponto: "
            f"{tempo_medio:.2f} s"
        )

        print(
            f"Tempo restante estimado: "
            f"{formatar_tempo(tempo_restante)}"
        )

        print("-" * 75)


        # ====================================================
        # INTERVALO
        # ====================================================

        if indice < TOTAL_PONTOS:

            time.sleep(
                TEMPO_ENTRE_DISPAROS
            )


    # ========================================================
    # FINAL
    # ========================================================

    tempo_total = (
        time.time()
        -
        tempo_inicio_experimento
    )


    print()
    print("=" * 75)
    print("MAPEAMENTO FINALIZADO")
    print("=" * 75)

    print(
        f"{TOTAL_PONTOS}/{TOTAL_PONTOS} "
        f"pontos concluidos."
    )

    print(
        f"Tempo total = "
        f"{formatar_tempo(tempo_total)}"
    )

    print(
        f"Media por ponto = "
        f"{tempo_total/TOTAL_PONTOS:.2f} s"
    )


# ============================================================
# CTRL + C
# ============================================================

except KeyboardInterrupt:

    tempo_total = (
        time.time()
        -
        tempo_inicio_experimento
    )

    print()
    print("=" * 75)
    print("MAPEAMENTO INTERROMPIDO")
    print("=" * 75)

    print(
        f"Tempo decorrido = "
        f"{formatar_tempo(tempo_total)}"
    )


# ============================================================
# ERRO
# ============================================================

except Exception as erro:

    tempo_total = (
        time.time()
        -
        tempo_inicio_experimento
    )

    print()
    print("=" * 75)
    print("ERRO")
    print("=" * 75)

    print(
        erro
    )

    print(
        f"Tempo decorrido = "
        f"{formatar_tempo(tempo_total)}"
    )


# ============================================================
# FINALIZAR
# ============================================================

finally:

    print()
    print(
        "Retornando servos ao centro mecanico..."
    )


    try:

        esp.reset_input_buffer()

        enviar_esp(
            "CENTER"
        )

        esperar_linha_esp(
            "SERVOS_OK",
            timeout=5
        )

    except Exception:

        pass


    try:

        esp.close()

    except Exception:

        pass


    print()
    print("=" * 75)

    print(
        "RESULTADOS SALVOS EM:"
    )

    print(
        PASTA.resolve()
    )

    print("=" * 75)
