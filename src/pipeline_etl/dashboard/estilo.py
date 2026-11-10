"""Estilo do painel: paleta (dark mode), CSS e componentes HTML (cartões de KPI e títulos).

Mesmo padrão visual dos outros projetos do portfólio (tema escuro com destaque neon).
As cores das séries foram validadas com o validador de paleta da skill de dataviz
(fundo #12141c): faixa de luminosidade, separação para daltonismo e contraste.
"""

import pandas as pd
import streamlit as st

# Superfícies e texto
COR_FUNDO = "#0a0b10"
COR_CARTAO = "#12141c"
COR_TEXTO = "#f4f5fb"
COR_TEXTO_SEC = "#b4b8c8"
COR_MUTED = "#7c8197"
COR_GRADE = "#1f2230"
COR_EIXO = "#2a2e3d"

# Destaques da interface (bordas, título, abas)
NEON_AZUL = "#3b9eff"
NEON_CIANO = "#22d3ee"

# Cores das séries: cada indicador tem sempre a mesma cor em todas as páginas
COR_SELIC = "#3987e5"
COR_IPCA = "#c98500"
COR_JURO_REAL = "#d55181"
COR_DOLAR = "#1aa3b8"
COR_DIAS_UTEIS = "#6b7a99"  # neutro: não compete com os indicadores
COR_IGPM = "#199e70"  # nunca no mesmo gráfico que o dólar (ciano): parecidos na visão normal
COR_DESOCUPACAO = "#9085e9"  # nunca no mesmo gráfico que a Selic (azul): parecidos p/ daltonismo
COR_EXPECTATIVA = COR_IPCA  # mesma família do IPCA; diferenciada por linha tracejada

# Polaridade (barras de variação): positivo quente, negativo frio
COR_POSITIVO = COR_IPCA
COR_NEGATIVO = COR_DOLAR

# Status dos alertas (paleta de status da skill de dataviz; reservada, nunca usada como série).
# Sempre acompanhada de ícone e texto: a cor nunca carrega o significado sozinha.
COR_CRITICO = "#d03b3b"
COR_ATENCAO = "#fab219"
COR_INFORMATIVO = COR_TEXTO_SEC
COR_SEVERIDADE = {"Crítico": COR_CRITICO, "Atenção": COR_ATENCAO, "Informativo": COR_INFORMATIVO}
ICONE_SEVERIDADE = {
    "Crítico": ":material/error:",
    "Atenção": ":material/warning:",
    "Informativo": ":material/info:",
}
SIMBOLO_SEVERIDADE = {"Crítico": "square", "Atenção": "triangle-up", "Informativo": "circle"}

# Sequencial (mapa de calor de dias úteis): um só matiz, do escuro ao claro
ESCALA_SEQUENCIAL = [[0.0, "#14325c"], [0.5, "#1f4f8f"], [1.0, "#2a6fc9"]]


def aplicar_css() -> None:
    """Injeta o CSS do painel (cartões de KPI, cartões de gráfico, chips)."""
    st.markdown(
        f"""
        <style>
        .stApp {{
            background:
                radial-gradient(1200px 500px at 85% -10%, rgba(59,158,255,0.10), transparent 60%),
                radial-gradient(900px 400px at -10% 10%, rgba(34,211,238,0.06), transparent 60%),
                {COR_FUNDO};
        }}
        .block-container {{padding-top: 2.2rem; padding-bottom: 2rem; max-width: 1500px;}}
        [data-testid="stSidebar"] {{
            background: linear-gradient(180deg, #10121a 0%, #0b0c12 100%);
            border-right: 1px solid {COR_GRADE};
        }}

        /* Cabeçalho */
        .titulo {{
            font-size: 2.4rem; font-weight: 800; line-height: 1.1; margin: 0;
            background: linear-gradient(90deg, {COR_TEXTO} 0%, {NEON_CIANO} 55%, {NEON_AZUL} 100%);
            -webkit-background-clip: text; background-clip: text; color: transparent;
        }}
        .subtitulo {{color: {COR_TEXTO_SEC}; margin: .35rem 0 1.4rem 0; font-size: .98rem;}}
        .selo {{
            display: inline-block; margin-left: .6rem; padding: .15rem .6rem; border-radius: 999px;
            font-size: .72rem; font-weight: 600; letter-spacing: .04em; text-transform: uppercase;
            color: {NEON_CIANO}; border: 1px solid rgba(34,211,238,.45);
            background: rgba(34,211,238,.08); vertical-align: middle;
        }}

        /* Cartões de KPI */
        .kpi {{
            position: relative; overflow: hidden; height: 100%; min-width: 0;
            container-type: inline-size;
            padding: 1rem 1.1rem 1.05rem 1.1rem; border-radius: 16px;
            background: linear-gradient(150deg,
                color-mix(in srgb, var(--acc) 16%, {COR_CARTAO}) 0%, {COR_CARTAO} 65%);
            border: 1px solid color-mix(in srgb, var(--acc) 60%, transparent);
            box-shadow: 0 0 22px -6px var(--acc), inset 0 1px 0 rgba(255,255,255,.05);
            transition: transform .15s ease, box-shadow .15s ease;
        }}
        .kpi:hover {{transform: translateY(-2px);
            box-shadow: 0 0 30px -4px var(--acc), inset 0 1px 0 rgba(255,255,255,.06);}}
        .kpi::before {{
            content: ""; position: absolute; inset: 0 0 auto 0; height: 3px;
            background: linear-gradient(90deg, var(--acc), transparent);
        }}
        .kpi-rotulo {{display: flex; align-items: center; gap: .45rem; color: {COR_TEXTO_SEC};
            font-size: clamp(.62rem, 7cqi, .82rem); font-weight: 600; letter-spacing: .03em;
            text-transform: uppercase; white-space: nowrap;}}
        .kpi-ponto {{flex-shrink: 0; width: 8px; height: 8px; border-radius: 50%;
            background: var(--acc); box-shadow: 0 0 10px var(--acc);}}
        .kpi-valor {{color: {COR_TEXTO}; font-size: clamp(1.5rem, 19cqi, 2.45rem); font-weight: 800;
            line-height: 1.15; margin-top: .35rem; font-variant-numeric: tabular-nums;
            white-space: nowrap;}}
        .kpi-valor small {{font-size: .45em; font-weight: 600; color: {COR_TEXTO_SEC};
            margin-left: .2rem;}}
        .kpi-valor small.prefixo {{margin-left: 0; margin-right: .25rem;}}
        .kpi-nota {{color: {COR_MUTED}; font-size: .8rem; margin-top: .15rem;}}
        .kpi-delta {{font-size: clamp(.62rem, 6.2cqi, .76rem); margin-top: .3rem; font-weight: 600;
            white-space: nowrap; color: {COR_TEXTO_SEC};}}

        /* Cartões dos gráficos (containers com key "card_...") */
        [class*="st-key-card_"] {{
            background: linear-gradient(180deg, #131620 0%, #0f1118 100%);
            border: 1px solid {COR_GRADE}; border-radius: 18px;
            padding: 1.1rem 1.2rem .6rem 1.2rem;
            box-shadow: 0 10px 30px -18px rgba(0,0,0,.9);
        }}
        .card-titulo {{color: {COR_TEXTO}; font-size: 1.08rem; font-weight: 700; margin: 0;}}
        .card-nota {{color: {COR_MUTED}; font-size: .84rem; margin: .2rem 0 .2rem 0;}}

        /* Chips de destaque */
        .chips {{display: flex; flex-wrap: wrap; gap: .5rem; margin: .1rem 0 1rem 0;}}
        .chip {{padding: .3rem .7rem; border-radius: 999px; font-size: .8rem;
            color: {COR_TEXTO_SEC};
            background: #0b0d14; border: 1px solid {COR_EIXO};}}
        .chip b {{color: {COR_TEXTO};}}
        .chip i {{display: inline-block; width: 7px; height: 7px; border-radius: 50%;
            margin-right: .4rem; background: var(--acc); box-shadow: 0 0 8px var(--acc);
            font-style: normal;}}

        [data-testid="stExpander"] details {{border-radius: 14px; border-color: {COR_GRADE};
            background: #10121a;}}
        .glossario dt {{color: {COR_TEXTO}; font-weight: 700; margin-top: .5rem;}}
        .glossario dd {{color: {COR_TEXTO_SEC}; margin-left: 0;}}
        </style>
        """,
        unsafe_allow_html=True,
    )


def formatar(valor: float | None, casas: int = 1, sufixo: str = "") -> str:
    """Número no padrão brasileiro (vírgula decimal, ponto de milhar)."""
    if valor is None or pd.isna(valor):
        return "-"
    texto = f"{valor:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return texto + sufixo


def largura_coluna(
    valores: pd.Series, titulo: str, px_por_caractere: float = 7.0, folga: int = 28
) -> int:
    """Largura em pixels para uma coluna de st.dataframe mostrar o texto mais longo inteiro.

    Considera o título e o maior valor. `folga` cobre o espaçamento interno da célula e o
    ícone de ordenação do cabeçalho.
    """
    maior = max([len(titulo), *(len(str(v)) for v in valores)])
    return int(maior * px_por_caractere + folga)


def cartao_kpi(
    rotulo: str,
    valor: str,
    nota: str,
    cor: str,
    unidade: str = "",
    prefixo: str = "",
    delta: str = "",
    dica: str = "",
    delta2: str = "",
) -> str:
    """HTML de um cartão de KPI com borda neon. `delta` é um texto pronto (ex.: variação)."""
    unidade_html = f"<small>{unidade}</small>" if unidade else ""
    prefixo_html = f'<small class="prefixo">{prefixo}</small>' if prefixo else ""
    delta_html = "".join(f'<div class="kpi-delta">{d}</div>' for d in (delta, delta2) if d)
    return (
        f'<div class="kpi" style="--acc:{cor}" title="{dica}">'
        f'<div class="kpi-rotulo"><span class="kpi-ponto"></span>{rotulo}</div>'
        f'<div class="kpi-valor">{prefixo_html}{valor}{unidade_html}</div>'
        f'<div class="kpi-nota">{nota}</div>{delta_html}</div>'
    )


def mostrar_kpis(cartoes: list[str]) -> None:
    """Linha de cartões de KPI com a mesma largura."""
    for coluna, cartao in zip(st.columns(len(cartoes), gap="small"), cartoes, strict=True):
        coluna.markdown(cartao, unsafe_allow_html=True)


def chips(itens: list[tuple[str, str, str]]) -> None:
    """Linha de chips: (texto, valor em destaque, cor do ponto)."""
    html = "".join(
        f'<span class="chip" style="--acc:{cor}"><i></i>{texto} <b>{valor}</b></span>'
        for texto, valor, cor in itens
    )
    st.markdown(f'<div class="chips">{html}</div>', unsafe_allow_html=True)


def titulo_cartao(titulo: str, nota: str = "") -> None:
    """Título e nota de um cartão de gráfico."""
    nota_html = f'<div class="card-nota">{nota}</div>' if nota else ""
    st.markdown(f'<div class="card-titulo">{titulo}</div>{nota_html}', unsafe_allow_html=True)


def cabecalho(titulo: str, subtitulo: str, selo: str = "dados oficiais BCB e ANBIMA") -> None:
    """Título da página em degradê, com selo da origem dos dados."""
    st.markdown(
        f'<h1 class="titulo">{titulo}<span class="selo">{selo}</span></h1>'
        f'<div class="subtitulo">{subtitulo}</div>',
        unsafe_allow_html=True,
    )
