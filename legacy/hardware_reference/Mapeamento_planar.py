import time
import csv
from pathlib import Path
from datetime import datetime
import matplotlib.pyplot as plt

from efield_control.drivers.red_pitaya import scpi
from efield_control.drivers.robots.elfin import Elfin


# ============================================================
# CONFIGURAÇÕES — RED PITAYA
# ============================================================

RP_IP = "169.254.197.73"
RP_PORT = 5000

DEC = 8

FS_ADC = 125e6
FS = FS_ADC / DEC

TIMEOUT_TRIGGER_S = 20

# Apenas garante que o buffer terminou de preencher
# depois que o trigger ocorreu
TEMPO_APOS_TRIGGER_S = 0.2


# ============================================================
# CONFIGURAÇÕES — ROBÔ ELFIN
# ============================================================

ROBOT_IP = "169.254.153.251"

# Tempo máximo permitido para um movimento
TIMEOUT_MOVIMENTO_S = 30

# Tempo depois que o robô parar antes de armar o TMS
TEMPO_ESTABILIZACAO_S = 1.0


# ============================================================
# MAPEAMENTO PLANAR
# ============================================================

# Todos os valores em mm.
#
# A posição em que o robô estiver quando o programa começar
# será considerada:
#
# x = 0
# y = 0
#
# do nosso mapa.

POSICOES_X_MM = [
    -20,
    -10,
    0,
    10,
    20
]

POSICOES_Y_MM = [
    -20,
    -10,
    0,
    10,
    20
]

N_X = len(POSICOES_X_MM)
N_Y = len(POSICOES_Y_MM)

N_PONTOS_TOTAL = N_X * N_Y


# ============================================================
# TMS
# ============================================================

# Intensidade fixa durante TODO o mapa
INTENSIDADE_TMS = 60


# ============================================================
# PASTAS DE SAÍDA
# ============================================================

timestamp_experimento = datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

PASTA_SAIDA = (
    Path("data/data")
    / (
        f"mapeamento_planar_"
        f"TMS_{INTENSIDADE_TMS}percent_"
        f"{timestamp_experimento}"
    )
)

PASTA_SAIDA.mkdir(
    parents=True,
    exist_ok=True
)

PASTA_WAVEFORMS = (
    PASTA_SAIDA
    / "waveforms"
)

PASTA_WAVEFORMS.mkdir(
    parents=True,
    exist_ok=True
)

ARQUIVO_RESUMO = (
    PASTA_SAIDA
    / "resumo_mapeamento_planar.csv"
)


# ============================================================
# FUNÇÕES RED PITAYA
# ============================================================

def enviar(rp, comando):
    rp.tx_txt(comando)


def perguntar(rp, comando):
    return rp.txrx_txt(comando).strip()


def perguntar_dados(rp, comando):

    rp.tx_txt(comando)

    resposta = rp.rx_txt()

    return resposta.strip()


def limpar_dados(texto):

    texto = (
        texto
        .strip()
        .replace("{", "")
        .replace("}", "")
    )

    dados = []

    for p in texto.split(","):

        p = p.strip()

        if p:

            try:
                dados.append(float(p))

            except ValueError:
                pass

    return dados


def esperar_trigger(rp):

    inicio = time.time()

    while True:

        estado = perguntar(
            rp,
            "ACQ:TRIG:STAT?"
        )

        if estado == "TD":

            return True

        if (
            time.time() - inicio
            > TIMEOUT_TRIGGER_S
        ):

            print(
                "\nTIMEOUT esperando "
                "trigger do TMS."
            )

            print(
                "Estado:",
                estado
            )

            return False

        time.sleep(0.001)


def calcular_metricas(x):

    if len(x) == 0:

        return (
            None,
            None,
            None
        )

    vmax = max(x)
    vmin = min(x)

    vpp = vmax - vmin

    return (
        vmax,
        vmin,
        vpp
    )


# ============================================================
# FUNÇÕES ROBÔ
# ============================================================

def obter_pose(robo):

    resultado = robo.get_pose()

    # A API está retornando:
    #
    # (True, [X,Y,Z,RX,RY,RZ])

    if (
        not isinstance(resultado, tuple)
        or len(resultado) < 2
    ):

        raise RuntimeError(
            "Formato inesperado retornado "
            "por get_pose()."
        )

    sucesso = resultado[0]
    pose = resultado[1]

    if not sucesso:

        raise RuntimeError(
            "Não foi possível obter "
            "a pose do robô."
        )

    if len(pose) < 6:

        raise RuntimeError(
            "Pose incompleta retornada "
            "pelo robô."
        )

    return pose


def esperar_robo_parar(robo):

    inicio = time.time()

    # Dá tempo para o controlador atualizar
    # o estado após o comando
    time.sleep(0.2)

    while True:

        if robo.is_error_state():

            print(
                "\nERRO detectado "
                "no robô."
            )

            return False

        if not robo.is_moving():

            return True

        if (
            time.time() - inicio
            > TIMEOUT_MOVIMENTO_S
        ):

            print(
                "\nTIMEOUT esperando "
                "o robô parar."
            )

            return False

        time.sleep(0.05)


def mover_robo(
    robo,
    pose_alvo
):

    print(
        "\nMovendo robô para:"
    )

    print(
        f"X = {pose_alvo[0]:.3f} mm | "
        f"Y = {pose_alvo[1]:.3f} mm | "
        f"Z = {pose_alvo[2]:.3f} mm"
    )

    print(
        f"RX = {pose_alvo[3]:.3f}° | "
        f"RY = {pose_alvo[4]:.3f}° | "
        f"RZ = {pose_alvo[5]:.3f}°"
    )

    # ========================================================
    # IMPORTANTE
    #
    # NÃO usamos robo.move_linear()
    #
    # porque essa função executa antes:
    #
    # set_speed_ratio(...)
    #
    # que estava produzindo:
    #
    # SetOverride error 1011
    #
    # Portanto o movimento é enviado diretamente.
    # ========================================================

    sucesso = (
        robo
        .connection
        .move_linear(
            pose_alvo
        )
    )

    if not sucesso:

        print(
            "\nFalha ao enviar "
            "movimento ao robô."
        )

        return False

    print(
        "Comando enviado."
    )

    sucesso = esperar_robo_parar(
        robo
    )

    if not sucesso:

        return False

    print(
        "Robô parado."
    )

    print(
        f"Esperando "
        f"{TEMPO_ESTABILIZACAO_S:.1f} s "
        "para estabilização..."
    )

    time.sleep(
        TEMPO_ESTABILIZACAO_S
    )

    return True


# ============================================================
# SALVAR WAVEFORM
# ============================================================

def salvar_waveform(
    nome,
    ch1,
    ch2
):

    n = min(
        len(ch1),
        len(ch2)
    )

    with open(
        nome,
        "w",
        newline=""
    ) as arquivo:

        writer = csv.writer(
            arquivo
        )

        writer.writerow(
            [
                "indice",
                "tempo_us",
                "ch1_V",
                "ch2_V"
            ]
        )

        for k in range(n):

            tempo_us = (
                k / FS * 1e6
            )

            writer.writerow(
                [
                    k,
                    tempo_us,
                    ch1[k],
                    ch2[k]
                ]
            )


# ============================================================
# CSV RESUMO
# ============================================================

def inicializar_resumo():

    with open(
        ARQUIVO_RESUMO,
        "w",
        newline=""
    ) as arquivo:

        writer = csv.writer(
            arquivo
        )

        writer.writerow(
            [
                "i",
                "j",

                "x_offset_mm",
                "y_offset_mm",

                "x_robot_mm",
                "y_robot_mm",
                "z_robot_mm",

                "rx_robot_deg",
                "ry_robot_deg",
                "rz_robot_deg",

                "intensidade_TMS_percent",

                "arquivo_waveform",

                "n_pontos",
                "dec",
                "fs_Hz",
                "janela_us",

                "ch1_vmax_V",
                "ch1_vmin_V",
                "ch1_vpp_V",

                "ch2_vmax_V",
                "ch2_vmin_V",
                "ch2_vpp_V",

                "timestamp"
            ]
        )


def adicionar_linha_resumo(
    i,
    j,
    dx,
    dy,
    pose_real,
    arquivo_waveform,
    n_pontos,
    vmax1,
    vmin1,
    vpp1,
    vmax2,
    vmin2,
    vpp2,
    timestamp
):

    janela_us = (
        n_pontos
        / FS
        * 1e6
    )

    with open(
        ARQUIVO_RESUMO,
        "a",
        newline=""
    ) as arquivo:

        writer = csv.writer(
            arquivo
        )

        writer.writerow(
            [
                i,
                j,

                dx,
                dy,

                pose_real[0],
                pose_real[1],
                pose_real[2],

                pose_real[3],
                pose_real[4],
                pose_real[5],

                INTENSIDADE_TMS,

                str(
                    arquivo_waveform
                ),

                n_pontos,
                DEC,
                FS,
                janela_us,

                vmax1,
                vmin1,
                vpp1,

                vmax2,
                vmin2,
                vpp2,

                timestamp
            ]
        )


# ============================================================
# AQUISIÇÃO DE UM PONTO
# ============================================================

def adquirir_ponto(rp):

    # --------------------------------------------------------
    # Reset
    # --------------------------------------------------------

    enviar(
        rp,
        "ACQ:RST"
    )

    time.sleep(0.1)

    # --------------------------------------------------------
    # Configuração
    # --------------------------------------------------------

    enviar(
        rp,
        "ACQ:DATA:FORMAT ASCII"
    )

    enviar(
        rp,
        "ACQ:DATA:Units VOLTS"
    )

    enviar(
        rp,
        f"ACQ:DEC {DEC}"
    )

    # Debounce mínimo
    enviar(
        rp,
        "ACQ:TRig:EXT:DEBouncer:US 1"
    )

    # --------------------------------------------------------
    # Inicia aquisição
    # --------------------------------------------------------

    enviar(
        rp,
        "ACQ:START"
    )

    time.sleep(0.1)

    # Rising edge externo
    enviar(
        rp,
        "ACQ:TRIG EXT_PE"
    )

    print(
        "\nRed Pitaya ARMADO."
    )

    print(
        "Aguardando rising edge "
        "no trigger do TMS..."
    )

    print(
        "DISPARE O TMS."
    )

    # --------------------------------------------------------
    # Trigger
    # --------------------------------------------------------

    ok = esperar_trigger(
        rp
    )

    if not ok:

        return None

    print(
        "\nTRIGGER RECEBIDO!"
    )

    time.sleep(
        TEMPO_APOS_TRIGGER_S
    )

    # --------------------------------------------------------
    # CH1
    # --------------------------------------------------------

    print(
        "Lendo CH1..."
    )

    resposta_ch1 = (
        perguntar_dados(
            rp,
            "ACQ:SOUR1:DATA?"
        )
    )

    # --------------------------------------------------------
    # CH2
    # --------------------------------------------------------

    print(
        "Lendo CH2..."
    )

    resposta_ch2 = (
        perguntar_dados(
            rp,
            "ACQ:SOUR2:DATA?"
        )
    )

    ch1 = limpar_dados(
        resposta_ch1
    )

    ch2 = limpar_dados(
        resposta_ch2
    )

    print(
        f"Pontos CH1 = {len(ch1)}"
    )

    print(
        f"Pontos CH2 = {len(ch2)}"
    )

    if (
        len(ch1) == 0
        or len(ch2) == 0
    ):

        print(
            "Erro: algum canal "
            "veio vazio."
        )

        return None

    vmax1, vmin1, vpp1 = (
        calcular_metricas(
            ch1
        )
    )

    vmax2, vmin2, vpp2 = (
        calcular_metricas(
            ch2
        )
    )

    return (
        ch1,
        ch2,

        vmax1,
        vmin1,
        vpp1,

        vmax2,
        vmin2,
        vpp2
    )


# ============================================================
# PLOT
# ============================================================

plt.ion()

fig, ax = plt.subplots(
    figsize=(10, 5)
)

fig.show()


def plotar(
    ch1,
    ch2,
    i,
    j,
    dx,
    dy,
    vpp1,
    vpp2
):

    n = min(
        len(ch1),
        len(ch2)
    )

    t = [
        k / FS * 1e6
        for k in range(n)
    ]

    ax.clear()

    ax.plot(
        t,
        ch1[:n],
        label=(
            f"IN1 — "
            f"Vpp = {vpp1:.6f} V"
        )
    )

    ax.plot(
        t,
        ch2[:n],
        label=(
            f"IN2 — "
            f"Vpp = {vpp2:.6f} V"
        )
    )

    ax.set_title(
        f"Mapa TMS "
        f"— i={i}, j={j} "
        f"— ΔX={dx:+.1f} mm "
        f"— ΔY={dy:+.1f} mm"
    )

    ax.set_xlabel(
        "Tempo (µs)"
    )

    ax.set_ylabel(
        "Tensão (V)"
    )

    ax.grid(
        True
    )

    ax.legend()

    fig.canvas.draw()

    fig.canvas.flush_events()

    plt.pause(
        0.05
    )


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

print(
    "\n===================================================="
)

print(
    "       MAPEAMENTO PLANAR TMS"
)

print(
    "===================================================="
)

print(
    f"\nRobô: {ROBOT_IP}"
)

print(
    f"Red Pitaya: {RP_IP}"
)

print(
    f"\nIntensidade TMS = "
    f"{INTENSIDADE_TMS}%"
)

print(
    f"\nX = {POSICOES_X_MM}"
)

print(
    f"Y = {POSICOES_Y_MM}"
)

print(
    f"\nTotal = "
    f"{N_X} x {N_Y} "
    f"= {N_PONTOS_TOTAL} pontos"
)

print(
    f"\nDEC = {DEC}"
)

print(
    f"Fs = "
    f"{FS/1e6:.3f} MHz"
)

print(
    f"Janela aproximada = "
    f"{16384/FS*1e6:.1f} µs"
)

print(
    "\nTrigger:"
)

print(
    "rising edge externo "
    "em DIO0_P"
)

print(
    "\nO TRIÂNGULO DEVE "
    "PERMANECER PARADO."
)

print(
    "Somente o robô será "
    "movimentado."
)


# ============================================================
# OBJETOS
# ============================================================

rp = None
robo = None


try:

    # ========================================================
    # RED PITAYA
    # ========================================================

    print(
        "\nConectando ao Red Pitaya..."
    )

    rp = scpi(
        RP_IP,
        timeout=30,
        port=RP_PORT
    )

    enviar(
        rp,
        "*CLS"
    )

    print(
        "Red Pitaya conectado."
    )

    # ========================================================
    # ROBÔ
    # ========================================================

    print(
        "\nConectando ao robô Elfin..."
    )

    robo = Elfin(
        ROBOT_IP
    )

    sucesso_conexao = robo.connect()

    print(
        "Robô conectado."
    )

    # ========================================================
    # POSIÇÃO INICIAL
    # ========================================================

    pose_inicial = obter_pose(
        robo
    )

    print(
        "\n===================================================="
    )

    print(
        "POSIÇÃO INICIAL DO ROBÔ"
    )

    print(
        "===================================================="
    )

    print(
        pose_inicial
    )

    X0 = pose_inicial[0]
    Y0 = pose_inicial[1]
    Z0 = pose_inicial[2]

    RX0 = pose_inicial[3]
    RY0 = pose_inicial[4]
    RZ0 = pose_inicial[5]

    print(
        "\nCENTRO DO MAPA:"
    )

    print(
        f"X0 = {X0:.3f} mm"
    )

    print(
        f"Y0 = {Y0:.3f} mm"
    )

    print(
        f"Z0 = {Z0:.3f} mm"
    )

    print(
        "\nORIENTAÇÃO FIXA:"
    )

    print(
        f"RX = {RX0:.3f}°"
    )

    print(
        f"RY = {RY0:.3f}°"
    )

    print(
        f"RZ = {RZ0:.3f}°"
    )

    print(
        "\nA posição ATUAL "
        "será considerada:"
    )

    print(
        "i,j central do mapa "
        "= (x=0, y=0)"
    )

    print(
        f"\nAjuste o TMS "
        f"para {INTENSIDADE_TMS}%."
    )

    print(
        "\nCONFIRA se a região "
        "de ±20 mm em X e Y "
        "está livre para movimento."
    )

    input(
        "\nQuando estiver tudo "
        "seguro e pronto, "
        "pressione ENTER..."
    )

    # ========================================================
    # INICIALIZA CSV
    # ========================================================

    inicializar_resumo()

    contador = 0


    # ========================================================
    # VARREDURA
    # ========================================================

    for j, dy in enumerate(
        POSICOES_Y_MM,
        start=1
    ):

        # ====================================================
        # ZIG-ZAG
        # ====================================================

        lista_x_normal = list(
            enumerate(
                POSICOES_X_MM,
                start=1
            )
        )

        if j % 2 == 1:

            lista_x = (
                lista_x_normal
            )

        else:

            lista_x = list(
                reversed(
                    lista_x_normal
                )
            )


        # ====================================================
        # PONTOS DA LINHA
        # ====================================================

        for i, dx in lista_x:

            contador += 1

            print(
                "\n\n===================================================="
            )

            print(
                f"PONTO "
                f"{contador}/"
                f"{N_PONTOS_TOTAL}"
            )

            print(
                "===================================================="
            )

            print(
                f"i = {i}"
            )

            print(
                f"j = {j}"
            )

            print(
                f"ΔX = {dx:+.1f} mm"
            )

            print(
                f"ΔY = {dy:+.1f} mm"
            )


            # =================================================
            # POSE ALVO
            # =================================================

            pose_alvo = [
                X0 + dx,
                Y0 + dy,
                Z0,

                RX0,
                RY0,
                RZ0
            ]


            # =================================================
            # MOVE ROBÔ
            # =================================================

            sucesso = mover_robo(
                robo,
                pose_alvo
            )

            if not sucesso:

                raise RuntimeError(
                    "Movimento do "
                    "robô falhou."
                )


            # =================================================
            # LEITURA DA POSIÇÃO REAL
            # =================================================

            pose_real = obter_pose(
                robo
            )

            print(
                "\nPosição real "
                "após movimento:"
            )

            print(
                f"X = "
                f"{pose_real[0]:.3f} mm"
            )

            print(
                f"Y = "
                f"{pose_real[1]:.3f} mm"
            )

            print(
                f"Z = "
                f"{pose_real[2]:.3f} mm"
            )


            # =================================================
            # AQUISIÇÃO
            # =================================================

            print(
                "\nAgora o robô "
                "fica PARADO."
            )

            print(
                "Armando Red Pitaya..."
            )

            resultado = adquirir_ponto(
                rp
            )


            # =================================================
            # CASO TIMEOUT
            # =================================================

            if resultado is None:

                print(
                    "\nAquisição falhou "
                    "ou houve timeout."
                )

                resposta = input(
                    "\nDigite R para "
                    "repetir ESTE ponto "
                    "ou qualquer outra "
                    "tecla para encerrar: "
                )

                if (
                    resposta
                    .strip()
                    .lower()
                    == "r"
                ):

                    print(
                        "\nRearmando..."
                    )

                    resultado = (
                        adquirir_ponto(
                            rp
                        )
                    )

                if resultado is None:

                    raise RuntimeError(
                        "Aquisição "
                        "interrompida."
                    )


            # =================================================
            # RESULTADOS
            # =================================================

            (
                ch1,
                ch2,

                vmax1,
                vmin1,
                vpp1,

                vmax2,
                vmin2,
                vpp2

            ) = resultado


            n_pontos = min(
                len(ch1),
                len(ch2)
            )

            print(
                "\n===================="
            )

            print(
                "RESULTADOS"
            )

            print(
                "===================="
            )

            print(
                f"CH1:"
            )

            print(
                f"Vmax = "
                f"{vmax1:.6f} V"
            )

            print(
                f"Vmin = "
                f"{vmin1:.6f} V"
            )

            print(
                f"Vpp  = "
                f"{vpp1:.6f} V"
            )

            print(
                f"\nCH2:"
            )

            print(
                f"Vmax = "
                f"{vmax2:.6f} V"
            )

            print(
                f"Vmin = "
                f"{vmin2:.6f} V"
            )

            print(
                f"Vpp  = "
                f"{vpp2:.6f} V"
            )


            # =================================================
            # NOME DO ARQUIVO
            # =================================================

            timestamp = (
                datetime
                .now()
                .strftime(
                    "%Y%m%d_%H%M%S"
                )
            )

            nome_waveform = (
                PASTA_WAVEFORMS
                /
                (
                    f"waveform_"
                    f"i{i:02d}_"
                    f"j{j:02d}_"
                    f"x{dx:+05.1f}mm_"
                    f"y{dy:+05.1f}mm_"
                    f"{timestamp}.csv"
                )
            )


            # =================================================
            # SALVA WAVEFORM
            # =================================================

            salvar_waveform(
                nome_waveform,
                ch1,
                ch2
            )


            # =================================================
            # SALVA RESUMO
            # =================================================

            adicionar_linha_resumo(

                i=i,
                j=j,

                dx=dx,
                dy=dy,

                pose_real=pose_real,

                arquivo_waveform=(
                    nome_waveform
                ),

                n_pontos=n_pontos,

                vmax1=vmax1,
                vmin1=vmin1,
                vpp1=vpp1,

                vmax2=vmax2,
                vmin2=vmin2,
                vpp2=vpp2,

                timestamp=timestamp
            )


            print(
                "\nWaveform salva:"
            )

            print(
                nome_waveform
            )

            print(
                "\nResumo atualizado:"
            )

            print(
                ARQUIVO_RESUMO
            )


            # =================================================
            # PLOT
            # =================================================

            plotar(
                ch1,
                ch2,

                i,
                j,

                dx,
                dy,

                vpp1,
                vpp2
            )


    # ========================================================
    # FIM
    # ========================================================

    print(
        "\n\n===================================================="
    )

    print(
        "MAPEAMENTO FINALIZADO"
    )

    print(
        "===================================================="
    )

    print(
        f"\nTotal adquirido: "
        f"{contador} pontos."
    )

    print(
        "\nResumo salvo em:"
    )

    print(
        ARQUIVO_RESUMO
    )

    print(
        "\nWaveforms salvas em:"
    )

    print(
        PASTA_WAVEFORMS
    )


# ============================================================
# CTRL+C
# ============================================================

except KeyboardInterrupt:

    print(
        "\n\nPrograma interrompido "
        "pelo usuário."
    )


# ============================================================
# ERRO
# ============================================================

except Exception as erro:

    print(
        f"\n\nERRO: {erro}"
    )


# ============================================================
# FINALIZAÇÃO
# ============================================================

finally:

    if rp is not None:

        try:

            rp.close()

            print(
                "\nConexão "
                "Red Pitaya fechada."
            )

        except Exception:
            pass


    if robo is not None:

        try:

            robo.disconnect()

            print(
                "Conexão com "
                "robô fechada."
            )

        except Exception:
            pass


print(
    "\nFinalizado."
)
