"""Página Comparador: indicadores de um mês contra o mês anterior (MoM), o mesmo mês do ano
anterior (YoY), outro mês à escolha e janelas de 3, 6 ou 12 meses."""

import pandas as pd
import streamlit as st

from pipeline_etl.dashboard.analise import comparar, comparar_janelas, mes_referencia_padrao
from pipeline_etl.dashboard.dados import rotulo_mes
from pipeline_etl.dashboard.estilo import (
    COR_DOLAR,
    COR_IPCA,
    COR_JURO_REAL,
    COR_SELIC,
    cabecalho,
    cartao_kpi,
    formatar,
    mostrar_kpis,
    titulo_cartao,
)

CASAS = {"taxa": 2, "nivel": 4, "contagem": 0}
CARTOES = [
    ("ipca_acumulado_12m_pct", "IPCA 12 meses", COR_IPCA, "%", ""),
    ("selic_meta_fim_mes_pct", "Selic meta", COR_SELIC, "% a.a.", ""),
    ("juro_real_12m_pct", "Juro real", COR_JURO_REAL, "%", ""),
    ("dolar_fim_mes", "Dólar fim do mês", COR_DOLAR, "", "R$"),
]


def texto_delta(delta: float | None, tipo: str) -> str:
    """'▲ 0,25 p.p.' para taxas, '▲ 0,1234' para níveis, '▲ 2' para contagens."""
    if delta is None or pd.isna(delta):
        return "-"
    seta = "▲" if delta > 0 else ("▼" if delta < 0 else "=")
    unidade = " p.p." if tipo == "taxa" else ""
    return f"{seta} {formatar(abs(delta), CASAS[tipo])}{unidade}"


def linha_delta(rotulo: str, linha: pd.Series, chave: str) -> str:
    """'MoM ▲ 0,25 p.p. (+1,8%)' para o cartão."""
    delta = texto_delta(linha[f"delta_{chave}"], linha["tipo"])
    return f"{rotulo} {delta} ({texto_var(linha[f'var_{chave}_pct'])})"


def texto_var(relativa: float | None) -> str:
    if relativa is None or pd.isna(relativa):
        return "-"
    if abs(relativa) < 0.05:  # evita "-0,0%"
        return "0,0%"
    return f"{'+' if relativa > 0 else ''}{formatar(relativa, 1, '%')}"


mart = st.session_state["_mart"]
periodo = st.session_state["_mart_periodo"]

cabecalho(
    "Comparador de períodos",
    "Variação de cada indicador contra o mês anterior (MoM), o mesmo mês do ano anterior "
    "(YoY), outro mês à sua escolha e janelas de meses.",
)
if periodo.empty:
    st.warning("Nenhum mês no período selecionado. Ajuste o período na barra lateral.")
    st.stop()

# Mês de referência: meses do período; comparação livre: qualquer mês anterior da série.
rotulos = periodo["mes_rotulo"].tolist()
por_rotulo = dict(zip(mart["mes_rotulo"], mart["primeiro_dia_mes"], strict=True))
if st.session_state.get("cmp_ref") not in rotulos:
    st.session_state["cmp_ref"] = rotulo_mes(mes_referencia_padrao(periodo))

col_ref, col_outro, col_janela = st.columns([1, 1, 1.2], vertical_alignment="bottom")
ref_rotulo = col_ref.selectbox(
    "Mês de referência",
    rotulos,
    key="cmp_ref",
    persist_state="session",
    help="Padrão: último mês com IPCA publicado, para que todos os indicadores existam.",
)
referencia = por_rotulo[ref_rotulo]
anteriores = [r for r, d in por_rotulo.items() if d < referencia]
if st.session_state.get("cmp_outro") not in anteriores:
    st.session_state["cmp_outro"] = None
outro_rotulo = col_outro.selectbox(
    "Comparar também com",
    anteriores[::-1],
    key="cmp_outro",
    persist_state="session",
    placeholder="Opcional: outro mês",
)
janela = col_janela.segmented_control(
    "Janela de comparação",
    [3, 6, 12],
    default=12,
    required=True,
    key="cmp_janela",
    persist_state="session",
    format_func=lambda n: f"{n} meses",
)

comparacao = comparar(mart, referencia, por_rotulo.get(outro_rotulo) if outro_rotulo else None)
por_coluna = comparacao.set_index("coluna")

mostrar_kpis(
    [
        cartao_kpi(
            nome,
            formatar(por_coluna.loc[col, "valor"], CASAS[por_coluna.loc[col, "tipo"]]),
            f"em {ref_rotulo}",
            cor,
            unidade=unidade,
            prefixo=prefixo,
            delta=linha_delta("MoM", por_coluna.loc[col], "mom"),
            delta2=linha_delta("YoY", por_coluna.loc[col], "yoy"),
        )
        for col, nome, cor, unidade, prefixo in CARTOES
    ]
)
st.write("")

mes_anterior = rotulo_mes(referencia - pd.DateOffset(months=1))
ano_anterior = rotulo_mes(referencia - pd.DateOffset(years=1))
tabela = pd.DataFrame(
    {
        "Indicador": comparacao["indicador"] + " (" + comparacao["unidade"] + ")",
        ref_rotulo: [
            formatar(v, CASAS[t])
            for v, t in zip(comparacao["valor"], comparacao["tipo"], strict=True)
        ],
        mes_anterior: [
            formatar(v, CASAS[t])
            for v, t in zip(comparacao["base_mom"], comparacao["tipo"], strict=True)
        ],
        "Δ MoM": [
            texto_delta(d, t)
            for d, t in zip(comparacao["delta_mom"], comparacao["tipo"], strict=True)
        ],
        "Var. % MoM": comparacao["var_mom_pct"].map(texto_var),
        ano_anterior: [
            formatar(v, CASAS[t])
            for v, t in zip(comparacao["base_yoy"], comparacao["tipo"], strict=True)
        ],
        "Δ YoY": [
            texto_delta(d, t)
            for d, t in zip(comparacao["delta_yoy"], comparacao["tipo"], strict=True)
        ],
        "Var. % YoY": comparacao["var_yoy_pct"].map(texto_var),
    }
)
if outro_rotulo:
    tabela[outro_rotulo] = [
        formatar(v, CASAS[t])
        for v, t in zip(comparacao["base_outro"], comparacao["tipo"], strict=True)
    ]
    tabela[f"Δ vs {outro_rotulo}"] = [
        texto_delta(d, t)
        for d, t in zip(comparacao["delta_outro"], comparacao["tipo"], strict=True)
    ]
    tabela[f"Var. % vs {outro_rotulo}"] = comparacao["var_outro_pct"].map(texto_var)

with st.container(key="card_comparacao"):
    titulo_cartao(
        f"{ref_rotulo} contra outros meses",
        "Δ: diferença absoluta (taxas em pontos percentuais). Var. %: variação relativa "
        '(ex.: Selic de 10% para 11% = +1 p.p. = +10%). "-" = valor ainda não publicado.',
    )
    st.dataframe(
        tabela,
        hide_index=True,
        column_config={"Indicador": st.column_config.TextColumn(pinned=True)},
        alt=f"Indicadores de {ref_rotulo} comparados com o mês anterior e o ano anterior",
    )

janelas = comparar_janelas(mart, referencia, janela)
ini_ant, fim_ant, ini_atu, fim_atu = janelas.attrs["periodos"]
rotulo_atual = f"{rotulo_mes(ini_atu)} a {rotulo_mes(fim_atu)}"
rotulo_anterior = f"{rotulo_mes(ini_ant)} a {rotulo_mes(fim_ant)}"
tabela_janelas = pd.DataFrame(
    {
        "Indicador": janelas["indicador"] + " (" + janelas["unidade"] + ")",
        rotulo_anterior: [
            formatar(v, CASAS[t])
            for v, t in zip(janelas["janela_anterior"], janelas["tipo"], strict=True)
        ],
        rotulo_atual: [
            formatar(v, CASAS[t])
            for v, t in zip(janelas["janela_atual"], janelas["tipo"], strict=True)
        ],
        "Δ": [texto_delta(d, t) for d, t in zip(janelas["delta"], janelas["tipo"], strict=True)],
        "Var. %": janelas["var_pct"].map(texto_var),
    }
)
with st.container(key="card_janelas"):
    titulo_cartao(
        f"Janelas de {janela} meses: {rotulo_atual} contra {rotulo_anterior}",
        "IPCA acumulado na janela; Selic, juro real e dólar pela média; dias úteis pela soma. "
        'Janela com mês sem dado aparece como "-".',
    )
    st.dataframe(
        tabela_janelas,
        hide_index=True,
        alt=f"Indicadores na janela de {janela} meses até {ref_rotulo} contra a janela anterior",
    )
