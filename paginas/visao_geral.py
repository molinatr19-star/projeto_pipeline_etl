"""Página Visão geral: cartões com os últimos valores e os principais gráficos."""

import streamlit as st

from pipeline_etl.dashboard.analise import alertas_recentes
from pipeline_etl.dashboard.dados import texto_variacao, ultimo
from pipeline_etl.dashboard.estilo import (
    COR_DIAS_UTEIS,
    COR_DOLAR,
    COR_IPCA,
    COR_JURO_REAL,
    COR_SELIC,
    ICONE_SEVERIDADE,
    cabecalho,
    cartao_kpi,
    formatar,
    mostrar_kpis,
    titulo_cartao,
)
from pipeline_etl.dashboard.graficos import (
    CONFIG_PLOTLY,
    grafico_dias_uteis_mes,
    grafico_juros,
    grafico_linha_unica,
)

GLOSSARIO = [
    (
        "IPCA 12 meses",
        "Inflação oficial acumulada nos últimos 12 meses: produto de (1 + taxa mensal). "
        "Só aparece quando os 12 meses já foram publicados.",
    ),
    (
        "Selic meta",
        "Taxa básica de juros definida pelo Copom, em % ao ano. "
        "O cartão mostra o valor vigente no fim do mês.",
    ),
    (
        "Juro real",
        "Aproximação: (1 + Selic meta) / (1 + IPCA 12 meses) - 1. "
        "Compara a meta atual com a inflação passada.",
    ),
    (
        "Dólar",
        'Taxa de câmbio livre, venda (SGS 1). "Fim do mês" é a última cotação publicada no mês.',
    ),
    (
        "Dias úteis",
        "Segunda a sexta, sem feriados nacionais do calendário bancário da ANBIMA. "
        "Não considera feriados estaduais e municipais.",
    ),
    (
        "Variação",
        "Diferença para o valor anterior disponível: em pontos percentuais (p.p.) para taxas "
        "e em % para o dólar.",
    ),
]

df = st.session_state["_mart_periodo"]

cabecalho(
    "Indicadores econômicos",
    "Inflação, juros, câmbio e calendário bancário, atualizados pelo pipeline ETL.",
)
if df.empty:
    st.warning("Nenhum mês no período selecionado. Ajuste o período na barra lateral.")
    st.stop()

ipca = ultimo(df, "ipca_acumulado_12m_pct")
selic = ultimo(df, "selic_meta_fim_mes_pct")
juro = ultimo(df, "juro_real_12m_pct")
dolar = ultimo(df, "dolar_fim_mes")
dolar_var = ultimo(df, "dolar_variacao_mes_pct")
ultimo_mes = df.iloc[-1]

mostrar_kpis(
    [
        cartao_kpi(
            "IPCA 12 meses",
            formatar(ipca.valor, 2),
            f"até {ipca.referencia}",
            COR_IPCA,
            unidade="%",
            delta=texto_variacao(ipca.variacao),
            dica="Inflação acumulada nos últimos 12 meses",
        ),
        cartao_kpi(
            "Selic meta",
            formatar(selic.valor, 2),
            f"em {selic.referencia}",
            COR_SELIC,
            unidade="% a.a.",
            delta=texto_variacao(selic.variacao),
        ),
        cartao_kpi(
            "Juro real",
            formatar(juro.valor, 2),
            f"aproximado, {juro.referencia}",
            COR_JURO_REAL,
            unidade="%",
            delta=texto_variacao(juro.variacao),
            dica="(1 + Selic meta) / (1 + IPCA 12 meses) - 1",
        ),
        cartao_kpi(
            "Dólar",
            formatar(dolar.valor, 4),
            f"fim de {dolar.referencia}",
            COR_DOLAR,
            prefixo="R$",
            delta=texto_variacao(dolar_var.valor, 2, "%").replace(" vs mês anterior", " no mês"),
        ),
        cartao_kpi(
            "Dias úteis",
            formatar(ultimo_mes["dias_uteis"], 0),
            f"em {ultimo_mes['mes_rotulo']}",
            COR_DIAS_UTEIS,
            delta=f"média de {formatar(df['dias_uteis'].mean(), 1)} por mês no período",
        ),
    ]
)
st.write("")

# Destaques: alertas dos últimos 3 meses do período (um por regra, o mais recente).
recentes = alertas_recentes(
    st.session_state["_alertas_periodo"], df["primeiro_dia_mes"].iloc[-1], meses=3
)
with st.container(key="card_destaques"):
    titulo_cartao(
        "Destaques e alertas recentes",
        f"Regras acionadas nos últimos 3 meses do período (até {df['mes_rotulo'].iloc[-1]}).",
    )
    if recentes.empty:
        st.success("Nenhum alerta nos últimos 3 meses do período.", icon=":material/check_circle:")
    else:
        meses_por_regra = recentes.groupby("regra")["mes_rotulo"].agg(list)
        exibir = {"Crítico": st.error, "Atenção": st.warning, "Informativo": st.info}
        for _, alerta in recentes.drop_duplicates("regra").head(4).iterrows():
            meses = meses_por_regra[alerta["regra"]]
            quando = (
                f"{len(meses)} dos últimos 3 meses, até {alerta['mes_rotulo']}"
                if len(meses) > 1
                else alerta["mes_rotulo"]
            )
            exibir[alerta["severidade"]](
                f"{alerta['mensagem']} Valor: {formatar(alerta['valor'], 2)} · "
                f"limite: {formatar(alerta['limite'], 2)}.",
                title=(
                    f"{alerta['severidade']} · {alerta['indicador']}: {alerta['regra']} ({quando})"
                ),
                icon=ICONE_SEVERIDADE[alerta["severidade"]],
            )
    st.page_link(
        "paginas/alertas.py",
        label="Ver todos os alertas do período",
        icon=":material/arrow_forward:",
    )

with st.container(key="card_juros"):
    titulo_cartao(
        "Selic, inflação e juro real",
        "Meta Selic no fim de cada mês, IPCA acumulado em 12 meses e o juro real aproximado "
        "(% ao ano). O último ponto de cada linha mostra o valor mais recente.",
    )
    st.plotly_chart(
        grafico_juros(df),
        width="stretch",
        config=CONFIG_PLOTLY,
        alt="Selic meta, IPCA acumulado em 12 meses e juro real ao longo do período",
    )

col_a, col_b = st.columns(2, gap="medium")
with col_a:
    with st.container(key="card_dolar_resumo"):
        titulo_cartao(
            "Dólar comercial (média do mês)", "R$ por US$, venda. Detalhes na página Câmbio."
        )
        st.plotly_chart(
            grafico_linha_unica(
                df, "dolar_medio_mes", "Dólar médio", COR_DOLAR, 4, "", prefixo_hover="R$ "
            ),
            width="stretch",
            config=CONFIG_PLOTLY,
            alt="Dólar médio mensal ao longo do período",
        )
with col_b:
    with st.container(key="card_dias_resumo"):
        titulo_cartao(
            "Dias úteis por mês",
            "Calendário bancário ANBIMA (sem fins de semana e feriados nacionais).",
        )
        st.plotly_chart(
            grafico_dias_uteis_mes(df),
            width="stretch",
            config=CONFIG_PLOTLY,
            alt="Quantidade de dias úteis em cada mês do período",
        )

with st.expander("Como ler os indicadores", icon=":material/help:"):
    itens = "".join(f"<dt>{termo}</dt><dd>{texto}</dd>" for termo, texto in GLOSSARIO)
    st.markdown(f'<dl class="glossario">{itens}</dl>', unsafe_allow_html=True)
