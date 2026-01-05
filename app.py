import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from pathlib import Path

# ============================================================
# CONFIG
# ============================================================
st.set_page_config(
    page_title="Dashboard de Operações",
    layout="wide",
    initial_sidebar_state="expanded"
)

DATA_PATH = Path(__file__).parent / "data" / "DataFrame_geral_simulador.csv"

# ============================================================
# LOAD DATA
# ============================================================
@st.cache_data
def load_data():
    # Ajuste este caminho quando rodar localmente / no Streamlit Cloud
    
    df = pd.read_csv(DATA_PATH, sep=",", encoding="utf-8", low_memory=False)

    # DataHora = Data + Abertura (você usa Abertura/Fechamento como hh:mm:ss)
    df["DataHora"] = pd.to_datetime(
        df["Data"].astype(str) + " " + df["Abertura"].astype(str),
        errors="coerce"
    )
    df = df.dropna(subset=["DataHora"]).sort_values("DataHora")

    df["Ano-Mes"] = df["DataHora"].dt.strftime("%Y-%m")
    df["Hora"] = df["DataHora"].dt.floor("H")

    # Custo e lucro líquido
    df["Custo Operação (pts)"] = 2.5
    df["Lucro Líquido (pts)"] = df["Res. Operação (pts)"] - df["Custo Operação (pts)"]

    return df

df = load_data()

# ============================================================
# HELPERS
# ============================================================
def resumo(df_x: pd.DataFrame):
    if df_x is None or len(df_x) == 0:
        return 0, 0.0, float("inf")

    lucro = df_x[df_x["Lucro Líquido (pts)"] > 0]["Lucro Líquido (pts)"].sum()
    preju = df_x[df_x["Lucro Líquido (pts)"] < 0]["Lucro Líquido (pts)"].sum()
    saldo = float(lucro + preju)
    fator = abs(lucro / preju) if preju != 0 else float("inf")
    return int(len(df_x)), saldo, float(fator)

def simular_stop_diario(df_in: pd.DataFrame, limite_perda: float, objetivo_ganho: float, loss_consecutivos: int) -> pd.DataFrame:
    df_tmp = df_in.copy()
    df_tmp["Data"] = df_tmp["DataHora"].dt.date

    linhas = []

    for _, grupo in df_tmp.groupby("Data"):
        saldo_acumulado = 0.0
        perdas_consecutivas = 0
        grupo = grupo.sort_values("DataHora")

        for _, row in grupo.iterrows():
            linhas.append(row)
            saldo_acumulado += float(row["Lucro Líquido (pts)"])

            if float(row["Lucro Líquido (pts)"]) < 0:
                perdas_consecutivas += 1
            else:
                perdas_consecutivas = 0

            if (
                saldo_acumulado >= objetivo_ganho
                or saldo_acumulado <= -limite_perda
                or perdas_consecutivas >= loss_consecutivos
            ):
                break

    df_sim = pd.DataFrame(linhas)

    if len(df_sim) > 0:
        df_sim = df_sim.sort_values("DataHora")
        df_sim["Total Parcial (pts)"] = df_sim["Lucro Líquido (pts)"].astype(float).cumsum()

    return df_sim

def filtrar_por_tres_janelas_abertura(
    df_in: pd.DataFrame,
    hora1_inicio, hora1_fim,
    usar_janela2: bool = False,
    hora2_inicio=None, hora2_fim=None,
    usar_janela3: bool = False,
    hora3_inicio=None, hora3_fim=None
) -> pd.DataFrame:
    """
    Filtra operações cuja Abertura (DataHora) esteja dentro:
    - Janela 1
    - OU Janela 2 (se ativada)
    - OU Janela 3 (se ativada)

    Suporta janelas que cruzam meia-noite.
    """
    df_tmp = df_in.copy()

    def time_to_minutes(t):
        return t.hour * 60 + t.minute

    def mask_janela(mins_series, ini, fim):
        if fim >= ini:
            return (mins_series >= ini) & (mins_series <= fim)
        else:
            return (mins_series >= ini) | (mins_series <= fim)

    mins_abertura = df_tmp["DataHora"].dt.hour * 60 + df_tmp["DataHora"].dt.minute

    # Janela 1 (obrigatória)
    ini1 = time_to_minutes(hora1_inicio)
    fim1 = time_to_minutes(hora1_fim)
    mask_final = mask_janela(mins_abertura, ini1, fim1)

    # Janela 2 (opcional)
    if usar_janela2 and (hora2_inicio is not None) and (hora2_fim is not None):
        ini2 = time_to_minutes(hora2_inicio)
        fim2 = time_to_minutes(hora2_fim)
        mask_final = mask_final | mask_janela(mins_abertura, ini2, fim2)

    # Janela 3 (opcional)
    if usar_janela3 and (hora3_inicio is not None) and (hora3_fim is not None):
        ini3 = time_to_minutes(hora3_inicio)
        fim3 = time_to_minutes(hora3_fim)
        mask_final = mask_final | mask_janela(mins_abertura, ini3, fim3)

    out = df_tmp.loc[mask_final].copy().sort_values("DataHora")
    return out

def filtrar_por_duas_janelas_abertura(df_in, hora1_inicio, hora1_fim, usar_janela2=False, hora2_inicio=None, hora2_fim=None):
    return filtrar_por_tres_janelas_abertura(
        df_in,
        hora1_inicio, hora1_fim,
        usar_janela2=usar_janela2, hora2_inicio=hora2_inicio, hora2_fim=hora2_fim,
        usar_janela3=False
    )

def filtrar_por_janela_abertura(df_in, hora_inicio, hora_fim):
    return filtrar_por_tres_janelas_abertura(
        df_in,
        hora_inicio, hora_fim,
        usar_janela2=False,
        usar_janela3=False
    )

def plot_patrimonio_4_linhas(df_real, df_stop, df_janela, df_combo):
    # Paleta fixa (pedido)
    COR_REAL = "#000000"     # Preto
    COR_STOPS = "#FFD400"    # Amarelo
    COR_JANELA = "#1F77B4"   # Azul
    COR_COMBO = "#2CA02C"    # Verde

    # Linhas finas / elegantes
    W_BASE = 1.1
    W_DESTAQUE = 1.4

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df_real["DataHora"], y=df_real["Total Parcial (pts)"],
        mode="lines", name="Real",
        line=dict(color=COR_REAL, width=W_DESTAQUE)
    ))

    if df_stop is not None and len(df_stop) > 0:
        fig.add_trace(go.Scatter(
            x=df_stop["DataHora"], y=df_stop["Total Parcial (pts)"],
            mode="lines", name="Só Stops",
            line=dict(color=COR_STOPS, width=W_BASE)
        ))

    fig.add_trace(go.Scatter(
        x=df_janela["DataHora"], y=df_janela["Total Parcial (pts)"],
        mode="lines", name="Só Janela",
        line=dict(color=COR_JANELA, width=W_BASE)
    ))

    if df_combo is not None and len(df_combo) > 0:
        fig.add_trace(go.Scatter(
            x=df_combo["DataHora"], y=df_combo["Total Parcial (pts)"],
            mode="lines", name="Stops + Janela",
            line=dict(color=COR_COMBO, width=W_DESTAQUE)
        ))

    fig.update_layout(
        title="Comparação de Patrimônio",
        xaxis_title="Data e Hora",
        yaxis_title="Total Parcial (pts)",
        hovermode="x unified",
        height=800
    )
    return fig

# ============================================================
# SIDEBAR - PERÍODO
# ============================================================
st.sidebar.header("Filtrar por período")
data_min = df["DataHora"].min().date()
data_max = df["DataHora"].max().date()

data_inicio, data_fim = st.sidebar.date_input(
    "Selecione o período",
    [data_min, data_max],
    min_value=data_min,
    max_value=data_max
)

df_filtrado = df[(df["DataHora"].dt.date >= data_inicio) & (df["DataHora"].dt.date <= data_fim)].copy()
df_filtrado["Total Parcial (pts)"] = df_filtrado["Lucro Líquido (pts)"].astype(float).cumsum()

# ============================================================
# MENU
# ============================================================
menu = st.sidebar.radio(
    "Selecione a Visualização",
    [
        "Operações",
        "Análise por Faixa Horária",
        "Análise por Dia do Mês",
        "Simulação",
    ]
)

# ============================================================
# 1) OPERAÇÕES
# ============================================================
if menu == "Operações":
    lucro_bruto = df_filtrado[df_filtrado["Res. Operação (pts)"] > 0]["Res. Operação (pts)"].sum()
    prejuizo_bruto = df_filtrado[df_filtrado["Res. Operação (pts)"] < 0]["Res. Operação (pts)"].sum()
    saldo_total = lucro_bruto + prejuizo_bruto
    custos_totais = df_filtrado["Custo Operação (pts)"].sum()
    saldo_liquido = saldo_total - custos_totais
    fator_lucro = abs(lucro_bruto / prejuizo_bruto) if prejuizo_bruto != 0 else float("inf")

    total_operacoes = len(df_filtrado)
    operacoes_gain = len(df_filtrado[df_filtrado["Res. Operação (pts)"] > 0])
    operacoes_loss = len(df_filtrado[df_filtrado["Res. Operação (pts)"] < 0])
    percentual_gain = (operacoes_gain / total_operacoes * 100) if total_operacoes > 0 else 0

    def highlight_values(val):
        try:
            val = float(val)
            color = "green" if val > 0 else "red" if val < 0 else "black"
        except Exception:
            color = "black"
        return f"color: {color}"

    col_tabela, col_resumo = st.columns([3, 1])

    with col_tabela:
        st.subheader("Tabela de Operações Filtradas")

        styled_df = df_filtrado[
            ["DataHora", "Ativo", "Lado", "Abertura", "Fechamento", "Tempo Operação",
             "Preço Compra", "Preço Venda", "Res. Operação (pts)", "Total Parcial (pts)"]
        ].copy()

        styled_df["Res. Operação (pts)"] = styled_df["Res. Operação (pts)"].map("{:,.1f}".format)
        styled_df["Preço Compra"] = styled_df["Preço Compra"].map("{:,.0f}".format)
        styled_df["Preço Venda"] = styled_df["Preço Venda"].map("{:,.0f}".format)
        styled_df["Total Parcial (pts)"] = styled_df["Total Parcial (pts)"].map("{:,.1f}".format)

        st.dataframe(styled_df.style.applymap(highlight_values, subset=["Res. Operação (pts)", "Total Parcial (pts)"]))

    with col_resumo:
        st.markdown("<style> .small-font { font-size:12px; } </style>", unsafe_allow_html=True)
        st.markdown("### Resumo das Operações", unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f'<p class="small-font">Lucro Bruto: <b>{lucro_bruto:.1f} pts</b></p>', unsafe_allow_html=True)
            st.markdown(f'<p class="small-font">Prejuízo Bruto: <b>{prejuizo_bruto:.1f} pts</b></p>', unsafe_allow_html=True)
            st.markdown(f'<p class="small-font">Saldo Total: <b>{saldo_total:.1f} pts</b></p>', unsafe_allow_html=True)
            st.markdown(f'<p class="small-font">Custos: <b>{custos_totais:.1f} pts</b></p>', unsafe_allow_html=True)
            st.markdown(f'<p class="small-font">Saldo Líquido Total: <b>{saldo_liquido:.1f} pts</b></p>', unsafe_allow_html=True)
            st.markdown(f'<p class="small-font">Fator de Lucro: <b>{fator_lucro:.2f}</b></p>', unsafe_allow_html=True)

        with col2:
            st.markdown(f'<p class="small-font">Total de Operações: <b>{total_operacoes}</b></p>', unsafe_allow_html=True)
            st.markdown(f'<p class="small-font">Operações Gain: <b>{operacoes_gain}</b></p>', unsafe_allow_html=True)
            st.markdown(f'<p class="small-font">Operações Loss: <b>{operacoes_loss}</b></p>', unsafe_allow_html=True)
            st.markdown(f'<p class="small-font">% Operações Gain: <b>{percentual_gain:.1f}%</b></p>', unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["Patrimônio (pts)", "Resultados por Operação", "Mês a Mês"])

    with tab1:
        st.subheader("Patrimônio (pts)")
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_filtrado["DataHora"],
            y=df_filtrado["Total Parcial (pts)"],
            mode="lines",
            name="Patrimônio (pts)",
            line=dict(width=1.2)
        ))
        fig.update_layout(title="Patrimônio (pts)", xaxis_title="Data e Hora", yaxis_title="Total Parcial (pts)",
                          hovermode="x unified", height=800)
        st.plotly_chart(fig, use_container_width=True)

    with tab2:
        st.subheader("Resultados por Operação")
        colors = ["green" if x > 0 else "red" for x in df_filtrado["Res. Operação (pts)"]]
        fig = go.Figure()
        fig.add_trace(go.Bar(x=list(range(len(df_filtrado))), y=df_filtrado["Res. Operação (pts)"], marker=dict(color=colors)))
        fig.update_layout(title="Resultados por Operação", xaxis_title="Operações", yaxis_title="Resultado da Operação (pts)",
                          hovermode="x unified", height=800)
        st.plotly_chart(fig, use_container_width=True)

    with tab3:
        st.subheader("Mês a Mês")
        df_mensal = df_filtrado.groupby("Ano-Mes")["Lucro Líquido (pts)"].sum().reset_index()
        cores = ["green" if x > 0 else "red" for x in df_mensal["Lucro Líquido (pts)"]]

        fig = go.Figure()
        fig.add_trace(go.Bar(x=df_mensal["Ano-Mes"], y=df_mensal["Lucro Líquido (pts)"], marker=dict(color=cores)))
        fig.update_layout(title="Mês a Mês", xaxis_title="Mês", yaxis_title="Total de Pontos Líquidos",
                          hovermode="x unified", height=800)
        st.plotly_chart(fig, use_container_width=True)

# ============================================================
# 2) ANÁLISE POR FAIXA HORÁRIA
# ============================================================
elif menu == "Análise por Faixa Horária":
    st.subheader("Análise por Faixa Horária")

    df_tmp = df_filtrado.copy()

    # ----------------------------
    # A) Slots de 15 minutos (por horário do dia)
    # ----------------------------
    df_tmp["min_do_dia"] = df_tmp["DataHora"].dt.hour * 60 + df_tmp["DataHora"].dt.minute
    df_tmp["slot_15m"] = (df_tmp["min_do_dia"] // 15).astype(int)          # 0..95
    df_tmp["slot_ini_min"] = df_tmp["slot_15m"] * 15
    df_tmp["slot_fim_min"] = df_tmp["slot_ini_min"] + 14
    df_tmp["ordem_faixa"] = df_tmp["slot_15m"]

    # Label 15m (vetorizado)
    ini = df_tmp["slot_ini_min"]
    fim = df_tmp["slot_fim_min"]
    df_tmp["Faixa Horária"] = (
        (ini // 60).astype(str).str.zfill(2) + ":" + (ini % 60).astype(str).str.zfill(2)
        + "–" +
        (fim // 60).astype(str).str.zfill(2) + ":" + (fim % 60).astype(str).str.zfill(2)
    )

    # ----------------------------
    # B) Slots de 1 hora (para o "fundo" do gráfico)
    # ----------------------------
    df_tmp["slot_1h"] = (df_tmp["min_do_dia"] // 60).astype(int)            # 0..23
    df_tmp["slot1h_ini_min"] = df_tmp["slot_1h"] * 60
    df_tmp["slot1h_fim_min"] = df_tmp["slot1h_ini_min"] + 59
    df_tmp["ordem_1h"] = df_tmp["slot_1h"]

    ini_h = df_tmp["slot1h_ini_min"]
    fim_h = df_tmp["slot1h_fim_min"]
    df_tmp["Faixa 1h"] = (
        (ini_h // 60).astype(str).str.zfill(2) + ":" + (ini_h % 60).astype(str).str.zfill(2)
        + "–" +
        (fim_h // 60).astype(str).str.zfill(2) + ":" + (fim_h % 60).astype(str).str.zfill(2)
    )

    # ----------------------------
    # C) Métricas
    # ----------------------------
    def calc_expectancia(grupo: pd.DataFrame) -> float:
        ganhos = grupo.loc[grupo["Lucro Líquido (pts)"] > 0, "Lucro Líquido (pts)"]
        perdas = grupo.loc[grupo["Lucro Líquido (pts)"] < 0, "Lucro Líquido (pts)"]

        n = len(grupo)
        if n == 0:
            return 0.0

        winrate = len(ganhos) / n
        lossrate = 1 - winrate

        avg_gain = ganhos.mean() if len(ganhos) else 0.0
        avg_loss = abs(perdas.mean()) if len(perdas) else 0.0

        return (winrate * avg_gain) - (lossrate * avg_loss)

    # ----------------------------
    # D) Aggreg 15m (frente)
    # ----------------------------
    df_hor_15 = (
        df_tmp.groupby(["ordem_faixa", "Faixa Horária"], as_index=False)
        .apply(lambda g: pd.Series({
            "Soma (pts)": g["Lucro Líquido (pts)"].sum(),
            "Expectância (pts)": calc_expectancia(g),
            "Qtd Ops": len(g),
            "Taxa Acerto (%)": (g["Lucro Líquido (pts)"] > 0).mean() * 100
        }))
        .reset_index(drop=True)
        .sort_values("ordem_faixa")
    )

    # ----------------------------
    # E) Aggreg 1h (fundo)
    # ----------------------------
    df_hor_1h = (
        df_tmp.groupby(["ordem_1h", "Faixa 1h"], as_index=False)
        .apply(lambda g: pd.Series({
            "Soma (pts)": g["Lucro Líquido (pts)"].sum(),
            "Expectância (pts)": calc_expectancia(g),
            "Qtd Ops": len(g),
            "Taxa Acerto (%)": (g["Lucro Líquido (pts)"] > 0).mean() * 100
        }))
        .reset_index(drop=True)
        .sort_values("ordem_1h")
    )

    # ----------------------------
    # F) Para o overlay: mapear cada 15m -> sua "hora cheia"
    # (Ex: 09:00–09:14 pertence à hora 09:00–09:59)
    # ----------------------------
    df_hor_15["ordem_1h"] = (df_hor_15["ordem_faixa"] // 4).astype(int)
    df_hor_15 = df_hor_15.merge(
        df_hor_1h[["ordem_1h", "Soma (pts)", "Expectância (pts)"]]
            .rename(columns={"Soma (pts)": "Soma_1h (pts)", "Expectância (pts)": "Expectância_1h (pts)"}),
        on="ordem_1h",
        how="left"
    )

    # ----------------------------
    # G) Gráficos
    # ----------------------------
    col1, col2 = st.columns(2)

    # -------------------------------------------------
    # Labels do eixo X:
    # mantém barras 15m, mas mostra 1 label por hora
    # -------------------------------------------------
    tickvals_1h = df_hor_15["Faixa Horária"].iloc[::4].tolist()

    def label_hora(slot_15m: int) -> str:
        h_ini = slot_15m // 4
        h_fim = h_ini + 1
        return f"{h_ini}h–{h_fim}h"

    ticktext_1h = (
        df_hor_15["ordem_faixa"]
        .iloc[::4]
        .astype(int)
        .apply(label_hora)
        .tolist()
    )

    # =================================================
    # 1) Soma de Pontos (15m sobre 1h)
    # =================================================
    with col1:
        st.subheader("Soma de Pontos")

        fig1 = go.Figure()

        # Fundo 1h
        fig1.add_bar(
            x=df_hor_15["Faixa Horária"],
            y=df_hor_15["Soma_1h (pts)"],
            name="1h (fundo)",
            marker_color=[
                "rgba(0,160,0,0.30)" if v > 0 else "rgba(200,0,0,0.30)"
                for v in df_hor_15["Soma_1h (pts)"].fillna(0)
            ],
            width=1.0
        )

        # Frente 15m
        fig1.add_bar(
            x=df_hor_15["Faixa Horária"],
            y=df_hor_15["Soma (pts)"],
            name="15m",
            marker_color=[
                "rgba(0,160,0,0.90)" if v > 0 else "rgba(200,0,0,0.90)"
                for v in df_hor_15["Soma (pts)"]
            ],
            width=0.70
        )

        fig1.update_layout(
            title="Soma de Pontos (15m sobre 1h)",
            yaxis_title="Pontos",
            height=750,
            barmode="overlay"
        )

        fig1.update_xaxes(
            tickmode="array",
            tickvals=tickvals_1h,
            ticktext=ticktext_1h,
            tickangle=0
        )

        st.plotly_chart(fig1, use_container_width=True)

    # =================================================
    # 2) Expectância por Operação (15m sobre 1h)
    # =================================================
    with col2:
        st.subheader("Expectância por Operação")

        fig2 = go.Figure()

        # Fundo 1h
        fig2.add_bar(
            x=df_hor_15["Faixa Horária"],
            y=df_hor_15["Expectância_1h (pts)"],
            name="1h (fundo)",
            marker_color=[
                "rgba(0,160,0,0.30)" if v > 0 else "rgba(200,0,0,0.30)"
                for v in df_hor_15["Expectância_1h (pts)"].fillna(0)
            ],
            width=1.0
        )

        # Frente 15m
        fig2.add_bar(
            x=df_hor_15["Faixa Horária"],
            y=df_hor_15["Expectância (pts)"],
            name="15m",
            marker_color=[
                "rgba(0,160,0,0.90)" if v > 0 else "rgba(200,0,0,0.90)"
                for v in df_hor_15["Expectância (pts)"]
            ],
            width=0.70
        )

        fig2.add_hline(y=0, line_width=2, line_color="black")

        fig2.update_layout(
            title="Expectância por Operação (15m sobre 1h)",
            yaxis_title="Pts / Trade",
            height=750,
            barmode="overlay"
        )

        fig2.update_xaxes(
            tickmode="array",
            tickvals=tickvals_1h,
            ticktext=ticktext_1h,
            tickangle=0
        )

        st.plotly_chart(fig2, use_container_width=True)

    # =================================================
    # 3) Quantidade de Operações (15m)
    # =================================================
    col3, col4 = st.columns(2)

    with col3:
        st.subheader("Quantidade de Operações")

        fig3 = go.Figure()
        fig3.add_bar(
            x=df_hor_15["Faixa Horária"],
            y=df_hor_15["Qtd Ops"],
            marker_color="steelblue"
        )

        fig3.update_layout(
            title="Quantidade de Operações (15m)",
            yaxis_title="Nº de Trades",
            height=650
        )

        fig3.update_xaxes(
            tickmode="array",
            tickvals=tickvals_1h,
            ticktext=ticktext_1h,
            tickangle=0
        )

        st.plotly_chart(fig3, use_container_width=True)

    # =================================================
    # 4) Taxa de Acerto (15m)
    # =================================================
    with col4:
        st.subheader("Taxa de Acerto")

        fig4 = go.Figure()
        fig4.add_bar(
            x=df_hor_15["Faixa Horária"],
            y=df_hor_15["Taxa Acerto (%)"]
        )

        fig4.update_layout(
            title="Taxa de Acerto (15m)",
            yaxis_title="Taxa de Acerto (%)",
            height=650
        )

        fig4.update_xaxes(
            tickmode="array",
            tickvals=tickvals_1h,
            ticktext=ticktext_1h,
            tickangle=0
        )

        st.plotly_chart(fig4, use_container_width=True)



    # ----------------------------
    # H) Tabela resumo (15m)
    # ----------------------------
    st.subheader("Resumo por Faixa Horária (15m)")
    st.dataframe(
        df_hor_15
        .sort_values("Expectância (pts)", ascending=False)
        .style.format({
            "Soma (pts)": "{:,.1f}",
            "Soma_1h (pts)": "{:,.1f}",
            "Expectância (pts)": "{:,.2f}",
            "Expectância_1h (pts)": "{:,.2f}",
            "Taxa Acerto (%)": "{:.1f}"
        })
    )

# ============================================================
# 3) ANÁLISE POR DIA DO MÊS
# ============================================================
elif menu == "Análise por Dia do Mês":
    st.subheader("Análise por Dia do Mês")

    df_tmp = df_filtrado.copy()
    df_tmp["Dia do Mês"] = df_tmp["DataHora"].dt.day
    df_dia = df_tmp.groupby("Dia do Mês")["Lucro Líquido (pts)"].mean().reset_index()

    st.subheader("Média de Pontos por Dia do Mês")
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df_dia["Dia do Mês"], y=df_dia["Lucro Líquido (pts)"]))
    fig.update_layout(title="Média de Pontos por Dia do Mês", xaxis_title="Dia do Mês", yaxis_title="Média de Pontos",
                      hovermode="x unified", height=600)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Tabela")
    st.dataframe(df_dia)

# ============================================================
# 6) SIMULAÇÃO HORÁRIO + STOP
# ============================================================
elif menu == "Simulação":
    st.subheader("Simulação Combinada: 3 Janelas (Abertura) + Stop Diário")

    cJ1, cJ2, cJ3, cSTOP = st.columns([1, 1, 1, 1.2], vertical_alignment="top")

    # ---------- JANELA 1 (sempre ativa)
    with cJ1:
        st.markdown("### 🕒 Janela 1")

        st.checkbox("Ativar", value=True, disabled=True, key="j1_dummy")

        cj1a, cj1b = st.columns(2)
        with cj1a:
            hora1_inicio = st.time_input("Início", value=pd.to_datetime("09:00").time(), key="j1_ini")
        with cj1b:
            hora1_fim = st.time_input("Fim", value=pd.to_datetime("10:45").time(), key="j1_fim")

        st.caption("Sempre ativa")

    # ---------- JANELA 2
    with cJ2:
        st.markdown("### 🕒 Janela 2")

        usar_janela2 = st.checkbox("Ativar", value=True, key="usar_j2")

        cj2a, cj2b = st.columns(2)
        with cj2a:
            hora2_inicio = st.time_input(
                "Início",
                value=pd.to_datetime("13:30").time(),
                key="j2_ini",
                disabled=not usar_janela2
            )
        with cj2b:
            hora2_fim = st.time_input(
                "Fim",
                value=pd.to_datetime("15:30").time(),
                key="j2_fim",
                disabled=not usar_janela2
            )

        st.caption("Opcional")

    # ---------- JANELA 3
    with cJ3:
        st.markdown("### 🕒 Janela 3")

        usar_janela3 = st.checkbox("Ativar", value=True, key="usar_j3")

        cj3a, cj3b = st.columns(2)
        with cj3a:
            hora3_inicio = st.time_input(
                "Início",
                value=pd.to_datetime("17:00").time(),
                key="j3_ini",
                disabled=not usar_janela3
            )
        with cj3b:
            hora3_fim = st.time_input(
                "Fim",
                value=pd.to_datetime("17:45").time(),
                key="j3_fim",
                disabled=not usar_janela3
            )

        st.caption("Opcional")

    # ---------- STOPS
    with cSTOP:
        st.markdown("### ⛔ Stops diários")

        limite_perda = st.number_input(
            "Limite de Perda (pts)",
            min_value=0,
            value=1000,
            step=50
        )
        objetivo_ganho = st.number_input(
            "Objetivo de Ganho (pts)",
            min_value=0,
            value=1100,
            step=50
        )
        loss_consecutivos = st.number_input(
            "Loss consecutivos",
            min_value=1,
            max_value=20,
            value=10
        )


    # 1) REAL
    df_real = df_filtrado.copy()
    df_real["Total Parcial (pts)"] = df_real["Lucro Líquido (pts)"].astype(float).cumsum()

    # 2) SÓ STOPS (em cima do real)
    df_stop = simular_stop_diario(df_real, limite_perda, objetivo_ganho, int(loss_consecutivos))
    if len(df_stop) > 0 and "Total Parcial (pts)" not in df_stop.columns:
        df_stop["Total Parcial (pts)"] = df_stop["Lucro Líquido (pts)"].astype(float).cumsum()

    # 3) SÓ JANELA (3 janelas)
    df_janela = filtrar_por_tres_janelas_abertura(
        df_real,
        hora1_inicio, hora1_fim,
        usar_janela2=usar_janela2, hora2_inicio=hora2_inicio, hora2_fim=hora2_fim,
        usar_janela3=usar_janela3, hora3_inicio=hora3_inicio, hora3_fim=hora3_fim
    )
    df_janela["Total Parcial (pts)"] = df_janela["Lucro Líquido (pts)"].astype(float).cumsum()

    # 4) STOPS + JANELA
    df_combo = simular_stop_diario(df_janela, limite_perda, objetivo_ganho, int(loss_consecutivos))
    if len(df_combo) > 0 and "Total Parcial (pts)" not in df_combo.columns:
        df_combo["Total Parcial (pts)"] = df_combo["Lucro Líquido (pts)"].astype(float).cumsum()

    # KPIs (4 colunas)
    st.markdown("### 📊 Resultados")
    c1, c2, c3, c4 = st.columns(4)

    ops_r, saldo_r, fator_r = resumo(df_real)
    ops_s, saldo_s, fator_s = resumo(df_stop)
    ops_j, saldo_j, fator_j = resumo(df_janela)
    ops_c, saldo_c, fator_c = resumo(df_combo)

    with c1:
        st.markdown("#### Real")
        st.metric("Ops", ops_r)
        st.metric("Saldo (pts)", f"{saldo_r:,.1f}")
        st.metric("Fator", f"{fator_r:.2f}")

    with c2:
        st.markdown("#### Só Stops")
        st.metric("Ops", ops_s)
        st.metric("Saldo (pts)", f"{saldo_s:,.1f}")
        st.metric("Fator", f"{fator_s:.2f}")

    with c3:
        st.markdown("#### Só Janela")
        st.metric("Ops", ops_j)
        st.metric("Saldo (pts)", f"{saldo_j:,.1f}")
        st.metric("Fator", f"{fator_j:.2f}")

    with c4:
        st.markdown("#### Stops + Janela")
        st.metric("Ops", ops_c)
        st.metric("Saldo (pts)", f"{saldo_c:,.1f}")
        st.metric("Fator", f"{fator_c:.2f}")

    tab1, tab2, tab3 = st.tabs(["Patrimônio (comparação)", "Resultados por Operação", "Mês a Mês"])

    # TAB1: 4 linhas com cores fixas
    with tab1:
        st.subheader("Comparação de Patrimônio")
        fig = plot_patrimonio_4_linhas(df_real, df_stop, df_janela, df_combo)
        st.plotly_chart(fig, use_container_width=True)

    # TAB2: barras do combo
    with tab2:
        st.subheader("Resultados por Operação — Stops + Janelas")
        if len(df_combo) == 0:
            st.warning("Nenhuma operação após aplicar Stops + Janelas (verifique filtros/valores).")
        else:
            colors = ["green" if x > 0 else "red" for x in df_combo["Lucro Líquido (pts)"]]
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=list(range(len(df_combo))),
                y=df_combo["Lucro Líquido (pts)"],
                marker=dict(color=colors)
            ))
            fig.update_layout(
                title="Resultados por Operação (Stops + Janelas)",
                xaxis_title="Operações",
                yaxis_title="Lucro Líquido (pts)",
                height=800
            )
            st.plotly_chart(fig, use_container_width=True)

    # TAB3: Mês a mês com 4 séries e cores fixas
    with tab3:
        st.subheader("Mês a Mês — Real vs Stops vs Janelas vs Stops+Janelas")

        real_m = df_real.groupby(df_real["DataHora"].dt.strftime("%Y-%m"))["Lucro Líquido (pts)"].sum().reset_index()
        real_m.columns = ["Ano-Mes", "Real"]

        stop_m = (
            df_stop.groupby(df_stop["DataHora"].dt.strftime("%Y-%m"))["Lucro Líquido (pts)"].sum().reset_index()
            if len(df_stop) else pd.DataFrame({"Ano-Mes": [], "Stops": []})
        )
        if len(stop_m):
            stop_m.columns = ["Ano-Mes", "Stops"]

        jan_m = df_janela.groupby(df_janela["DataHora"].dt.strftime("%Y-%m"))["Lucro Líquido (pts)"].sum().reset_index()
        jan_m.columns = ["Ano-Mes", "Janelas"]

        combo_m = (
            df_combo.groupby(df_combo["DataHora"].dt.strftime("%Y-%m"))["Lucro Líquido (pts)"].sum().reset_index()
            if len(df_combo) else pd.DataFrame({"Ano-Mes": [], "Stops+Janelas": []})
        )
        if len(combo_m):
            combo_m.columns = ["Ano-Mes", "Stops+Janelas"]

        comp = (
            real_m.merge(stop_m, on="Ano-Mes", how="outer")
                  .merge(jan_m, on="Ano-Mes", how="outer")
                  .merge(combo_m, on="Ano-Mes", how="outer")
                  .fillna(0)
                  .sort_values("Ano-Mes")
        )

        fig = go.Figure()
        fig.add_trace(go.Bar(x=comp["Ano-Mes"], y=comp["Real"], name="Real", marker_color="#000000"))
        fig.add_trace(go.Bar(x=comp["Ano-Mes"], y=comp.get("Stops", 0), name="Stops", marker_color="#FFD400"))
        fig.add_trace(go.Bar(x=comp["Ano-Mes"], y=comp["Janelas"], name="Janelas", marker_color="#1F77B4"))
        fig.add_trace(go.Bar(x=comp["Ano-Mes"], y=comp.get("Stops+Janelas", 0), name="Stops+Janelas", marker_color="#2CA02C"))

        fig.update_layout(
            title="Lucro Líquido Mês a Mês — Comparação",
            xaxis_title="Mês",
            yaxis_title="Lucro Líquido (pts)",
            barmode="group",
            hovermode="x unified",
            height=600
        )
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(comp)

    st.subheader("Tabela — Operações (Stops + Janelas)")
    st.dataframe(df_combo.drop(columns=["Data"], errors="ignore") if len(df_combo) else pd.DataFrame())

# ============================================================
# Rodar:
# python -m streamlit run Dashboard.py
# ============================================================
