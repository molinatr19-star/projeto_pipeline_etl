"""Página Dias úteis: calendário bancário (ANBIMA) por mês e por ano."""

import streamlit as st

from pipeline_etl.dashboard.estilo import COR_DIAS_UTEIS, cabecalho, chips, formatar, titulo_cartao
from pipeline_etl.dashboard.graficos import (
    CONFIG_PLOTLY,
    grafico_dias_uteis_ano,
    grafico_mapa_dias_uteis,
)

df = st.session_state["_mart_periodo"]

cabecalho(
    "Dias úteis",
    "Dias com expediente bancário: segunda a sexta, sem feriados nacionais (ANBIMA).",
)
if df.empty:
    st.warning("Nenhum mês no período selecionado. Ajuste o período na barra lateral.")
    st.stop()

menor = df.loc[df["dias_uteis"].idxmin()]
maior = df.loc[df["dias_uteis"].idxmax()]
chips(
    [
        ("Total no período:", formatar(df["dias_uteis"].sum(), 0), COR_DIAS_UTEIS),
        ("Média por mês:", formatar(df["dias_uteis"].mean(), 1), COR_DIAS_UTEIS),
        ("Mês com menos:", f"{int(menor['dias_uteis'])} ({menor['mes_rotulo']})", COR_DIAS_UTEIS),
        ("Mês com mais:", f"{int(maior['dias_uteis'])} ({maior['mes_rotulo']})", COR_DIAS_UTEIS),
    ]
)

with st.container(key="card_mapa_dias"):
    titulo_cartao(
        "Dias úteis por mês e ano",
        "Cores mais claras = mais dias úteis. Fevereiro com Carnaval costuma ter o menor número.",
    )
    st.plotly_chart(
        grafico_mapa_dias_uteis(df),
        width="stretch",
        config=CONFIG_PLOTLY,
        alt="Mapa de calor com os dias úteis de cada mês, por ano",
    )

with st.container(key="card_dias_ano"):
    titulo_cartao(
        "Dias úteis por ano",
        "Anos com * estão incompletos no período selecionado (barra mais clara).",
    )
    st.plotly_chart(
        grafico_dias_uteis_ano(df),
        width="stretch",
        config=CONFIG_PLOTLY,
        alt="Total de dias úteis em cada ano do período",
    )

st.caption(
    "Fonte: planilha de feriados nacionais da ANBIMA (atualizada em 22/12/2023). Não inclui "
    "feriados estaduais e municipais. No pipeline, os dias úteis conferem 100% com os dias que "
    "tiveram cotação do dólar no Banco Central."
)
