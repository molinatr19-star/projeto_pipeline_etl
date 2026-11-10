"""Página Mercado e expectativas: Focus (esperado x realizado), desocupação, CDI e IGP-M."""

import streamlit as st

from pipeline_etl.dashboard.analise import previsto_vs_realizado
from pipeline_etl.dashboard.dados import texto_variacao, ultimo
from pipeline_etl.dashboard.estilo import (
    COR_DESOCUPACAO,
    COR_DIAS_UTEIS,
    COR_EXPECTATIVA,
    COR_IGPM,
    cabecalho,
    cartao_kpi,
    chips,
    formatar,
    mostrar_kpis,
    titulo_cartao,
)
from pipeline_etl.dashboard.graficos import (
    CONFIG_PLOTLY,
    grafico_linha_unica,
    grafico_previsto_realizado,
)

mart = st.session_state["_mart"]
df = st.session_state["_mart_periodo"]

cabecalho(
    "Mercado e expectativas",
    "O que o mercado espera para a inflação (Boletim Focus), desemprego, CDI e IGP-M.",
)
if df.empty:
    st.warning("Nenhum mês no período selecionado. Ajuste o período na barra lateral.")
    st.stop()

focus = ultimo(df, "expectativa_ipca_12m_pct")
desocupacao = ultimo(df, "desocupacao_pct")
cdi = ultimo(df, "cdi_fim_mes_pct")
igpm = ultimo(df, "igpm_acumulado_12m_pct")
mostrar_kpis(
    [
        cartao_kpi(
            "IPCA esperado (Focus)",
            formatar(focus.valor, 2),
            f"próximos 12 meses, {focus.referencia}",
            COR_EXPECTATIVA,
            unidade="%",
            delta=texto_variacao(focus.variacao),
            dica="Mediana das projeções do mercado na última pesquisa do mês",
        ),
        cartao_kpi(
            "Desocupação",
            formatar(desocupacao.valor, 1),
            f"PNAD, {desocupacao.referencia}",
            COR_DESOCUPACAO,
            unidade="%",
            delta=texto_variacao(desocupacao.variacao, 1),
        ),
        cartao_kpi(
            "CDI",
            formatar(cdi.valor, 2),
            f"fim de {cdi.referencia}",
            COR_DIAS_UTEIS,  # neutro: o azul é da Selic (cor fixa por indicador)
            unidade="% a.a.",
            delta=texto_variacao(cdi.variacao),
        ),
        cartao_kpi(
            "IGP-M 12 meses",
            formatar(igpm.valor, 2),
            f"até {igpm.referencia}",
            COR_IGPM,
            unidade="%",
            delta=texto_variacao(igpm.variacao),
        ),
    ]
)
st.write("")

previsao = previsto_vs_realizado(mart)
previsao = previsao[
    previsao["primeiro_dia_mes"].between(df["primeiro_dia_mes"].min(), df["primeiro_dia_mes"].max())
]
comparaveis = previsao.dropna(subset=["realizado_pct", "esperado_pct"])
if not comparaveis.empty:
    acima = int((comparaveis["erro_pp"] > 0).sum())
    chips(
        [
            (
                "Erro médio absoluto:",
                f"{formatar(comparaveis['erro_pp'].abs().mean(), 2)} p.p.",
                COR_EXPECTATIVA,
            ),
            (
                "Inflação acima do esperado em:",
                f"{acima} de {len(comparaveis)} meses",
                COR_EXPECTATIVA,
            ),
        ]
    )

with st.container(key="card_previsto"):
    titulo_cartao(
        "Inflação esperada x realizada",
        "Linha tracejada: o que o mercado (Focus) projetava para os 12 meses seguintes, 12 meses "
        "antes. Linha cheia: o IPCA que de fato ocorreu nesses 12 meses.",
    )
    st.plotly_chart(
        grafico_previsto_realizado(previsao),
        width="stretch",
        config=CONFIG_PLOTLY,
        alt="IPCA em 12 meses realizado comparado com a expectativa do mercado 12 meses antes",
    )

with st.container(key="card_desocupacao"):
    titulo_cartao(
        "Taxa de desocupação",
        "PNAD Contínua (IBGE), trimestre móvel, via SGS 24369. A data é a do mês informado pela "
        "série (convenção a verificar).",
    )
    st.plotly_chart(
        grafico_linha_unica(df, "desocupacao_pct", "Desocupação", COR_DESOCUPACAO, 1, "%"),
        width="stretch",
        config=CONFIG_PLOTLY,
        alt="Taxa de desocupação ao longo do período",
    )
