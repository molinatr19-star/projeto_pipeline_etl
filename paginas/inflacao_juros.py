"""Página Inflação e juros: IPCA x meta, IPCA mensal, IPCA por ano e juro real."""

import streamlit as st

from pipeline_etl.dashboard.estilo import (
    COR_CRITICO,
    COR_IPCA,
    COR_JURO_REAL,
    COR_NEGATIVO,
    cabecalho,
    chips,
    formatar,
    titulo_cartao,
)
from pipeline_etl.dashboard.graficos import (
    CONFIG_PLOTLY,
    grafico_barras_sinal,
    grafico_ipca_anual,
    grafico_ipca_igpm,
    grafico_ipca_meta,
    grafico_linha_unica,
)

df = st.session_state["_mart_periodo"]

cabecalho(
    "Inflação e juros", "IPCA contra a meta, IPCA mês a mês, inflação de cada ano e o juro real."
)
if df.empty:
    st.warning("Nenhum mês no período selecionado. Ajuste o período na barra lateral.")
    st.stop()

ipca = df.dropna(subset=["ipca_mensal_pct"])
ipca_12m = df.dropna(subset=["ipca_acumulado_12m_pct"])
if ipca.empty:
    st.info("O IPCA dos meses selecionados ainda não foi publicado.", icon=":material/schedule:")
    st.stop()

maior = ipca.loc[ipca["ipca_mensal_pct"].idxmax()]
chips_itens = [
    (
        "Maior IPCA mensal:",
        f"{formatar(maior['ipca_mensal_pct'], 2, '%')} ({maior['mes_rotulo']})",
        COR_IPCA,
    ),
    ("Meses com deflação:", str(int((ipca["ipca_mensal_pct"] < 0).sum())), COR_NEGATIVO),
]
if not ipca_12m.empty:
    pico = ipca_12m.loc[ipca_12m["ipca_acumulado_12m_pct"].idxmax()]
    chips_itens.insert(
        1,
        (
            "Pico do IPCA 12 meses:",
            f"{formatar(pico['ipca_acumulado_12m_pct'], 2, '%')} ({pico['mes_rotulo']})",
            COR_IPCA,
        ),
    )
acima_teto = int((ipca_12m["ipca_acumulado_12m_pct"] > ipca_12m["teto_meta_pct"]).sum())
chips_itens.append(("Meses acima do teto da meta:", str(acima_teto), COR_CRITICO))
chips(chips_itens)

with st.container(key="card_ipca_meta"):
    titulo_cartao(
        "IPCA 12 meses contra a meta de inflação",
        "Faixa cinza: intervalo de tolerância do CMN; linha tracejada: centro da meta (SGS 13521). "
        "Quadrados vermelhos: meses acima do teto.",
    )
    st.plotly_chart(
        grafico_ipca_meta(df),
        width="stretch",
        config=CONFIG_PLOTLY,
        alt="IPCA em 12 meses comparado com o centro e o intervalo da meta de inflação",
    )

with st.container(key="card_ipca_mensal"):
    titulo_cartao(
        "IPCA mensal",
        "Variação de preços em cada mês. Barras abaixo de zero são meses de deflação.",
    )
    st.plotly_chart(
        grafico_barras_sinal(df, "ipca_mensal_pct", "IPCA", "Inflação", "Deflação"),
        width="stretch",
        config=CONFIG_PLOTLY,
        alt="IPCA de cada mês, com os meses de deflação destacados",
    )

with st.container(key="card_ipca_igpm"):
    titulo_cartao(
        "IPCA x IGP-M em 12 meses",
        "IGP-M (FGV) pesa mais preços no atacado e câmbio e corrige muitos aluguéis; "
        "costuma oscilar mais que o IPCA.",
    )
    st.plotly_chart(
        grafico_ipca_igpm(df),
        width="stretch",
        config=CONFIG_PLOTLY,
        alt="IPCA e IGP-M acumulados em 12 meses ao longo do período",
    )

col_a, col_b = st.columns(2, gap="medium")
with col_a:
    with st.container(key="card_ipca_anual"):
        titulo_cartao(
            "IPCA acumulado em cada ano",
            "Anos com * estão incompletos no período: acumulado até o último mês publicado.",
        )
        st.plotly_chart(
            grafico_ipca_anual(df),
            width="stretch",
            config=CONFIG_PLOTLY,
            alt="Inflação acumulada em cada ano do período",
        )
with col_b:
    with st.container(key="card_juro_real"):
        titulo_cartao(
            "Juro real aproximado",
            "(1 + Selic meta) / (1 + IPCA 12 meses) - 1. Acima de zero, a Selic supera a inflação.",
        )
        st.plotly_chart(
            grafico_linha_unica(
                df, "juro_real_12m_pct", "Juro real", COR_JURO_REAL, 2, "%", area=True
            ),
            width="stretch",
            config=CONFIG_PLOTLY,
            alt="Juro real aproximado ao longo do período",
        )

st.caption(
    "IPCA acumulado calculado a partir das taxas mensais do BCB (já arredondadas); pode diferir "
    "em 0,01 p.p. do acumulado divulgado pelo IBGE."
)
