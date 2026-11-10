"""Página Câmbio: dólar médio e de fim de mês, e variação mensal."""

import streamlit as st

from pipeline_etl.dashboard.analise import parametros_do_config
from pipeline_etl.dashboard.estilo import (
    COR_DOLAR,
    COR_NEGATIVO,
    COR_POSITIVO,
    cabecalho,
    chips,
    formatar,
    titulo_cartao,
)
from pipeline_etl.dashboard.graficos import CONFIG_PLOTLY, grafico_barras_sinal, grafico_dolar

df = st.session_state["_mart_periodo"]
limite = parametros_do_config().dolar_variacao_mes_pct

cabecalho("Câmbio", "Dólar comercial (venda), em R$ por US$.")
dolar = df.dropna(subset=["dolar_medio_mes"])
if dolar.empty:
    st.warning("Nenhum mês com cotação no período selecionado. Ajuste o período na barra lateral.")
    st.stop()

minimo = dolar.loc[dolar["dolar_fim_mes"].idxmin()]
maximo = dolar.loc[dolar["dolar_fim_mes"].idxmax()]
variacoes = dolar.dropna(subset=["dolar_variacao_mes_pct"])
itens = [
    (
        "Menor no fim do mês:",
        f"R$ {formatar(minimo['dolar_fim_mes'], 4)} ({minimo['mes_rotulo']})",
        COR_DOLAR,
    ),
    (
        "Maior no fim do mês:",
        f"R$ {formatar(maximo['dolar_fim_mes'], 4)} ({maximo['mes_rotulo']})",
        COR_DOLAR,
    ),
]
if not variacoes.empty:
    alta = variacoes.loc[variacoes["dolar_variacao_mes_pct"].idxmax()]
    queda = variacoes.loc[variacoes["dolar_variacao_mes_pct"].idxmin()]
    itens += [
        (
            "Maior alta mensal:",
            f"{formatar(alta['dolar_variacao_mes_pct'], 2, '%')} ({alta['mes_rotulo']})",
            COR_POSITIVO,
        ),
        (
            "Maior queda mensal:",
            f"{formatar(queda['dolar_variacao_mes_pct'], 2, '%')} ({queda['mes_rotulo']})",
            COR_NEGATIVO,
        ),
    ]
chips(itens)

with st.container(key="card_dolar"):
    titulo_cartao(
        "Dólar: média do mês e fim do mês",
        "A média suaviza a oscilação diária; o fim do mês é a última cotação publicada.",
    )
    st.plotly_chart(
        grafico_dolar(df),
        width="stretch",
        config=CONFIG_PLOTLY,
        alt="Dólar médio e de fim de mês ao longo do período",
    )

with st.container(key="card_dolar_variacao"):
    titulo_cartao(
        "Variação mensal do dólar",
        "Fim do mês contra o fim do mês anterior. Alta do dólar = real mais fraco. "
        f"Losangos amarelos: alertas de variação de {formatar(limite, 0)}% ou mais.",
    )
    st.plotly_chart(
        grafico_barras_sinal(
            df,
            "dolar_variacao_mes_pct",
            "Variação",
            "Alta",
            "Queda",
            destaques=df["dolar_variacao_mes_pct"].abs() >= limite,
            rotulo_destaque=f"Variação forte (≥ {formatar(limite, 0)}%)",
        ),
        width="stretch",
        config=CONFIG_PLOTLY,
        alt="Variação mensal do dólar, com altas e quedas",
    )
