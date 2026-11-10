"""Dados do painel: leitura da mart mensal, filtro de período e indicadores dos cartões.

Fonte preferida: a exportação final `data/processed/indicadores_mensal.parquet`.
Se ela não existir, lê a mesma tabela direto do warehouse DuckDB.
"""

from dataclasses import dataclass
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

from pipeline_etl.orquestracao.warehouse import caminho_warehouse_padrao
from pipeline_etl.utils.caminhos import caminho_projeto
from pipeline_etl.utils.configuracao import carregar_config

TABELA_MART = "marts.mart_indicadores_mensal"
COLUNAS_OPCIONAIS = [
    "meta_inflacao_pct",
    "igpm_mensal_pct",
    "igpm_acumulado_12m_pct",
    "expectativa_ipca_12m_pct",
    "cdi_fim_mes_pct",
    "desocupacao_pct",
]
MESES_ABREV = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

# Atalhos de período (meses; None = desde o início)
PERIODOS = {"12 meses": 12, "3 anos": 36, "5 anos": 60, "Tudo": None}
PERIODO_PADRAO = "5 anos"
PERSONALIZADO = "Personalizado"


@dataclass
class Mart:
    """Tabela mensal carregada e de onde ela veio."""

    dados: pd.DataFrame
    origem: str


@dataclass
class Indicador:
    """Último valor disponível de uma coluna e a variação contra o valor anterior."""

    valor: float | None
    referencia: str
    variacao: float | None


def caminho_parquet_mart() -> Path:
    """Arquivo da exportação final configurada para a mart mensal."""
    config = carregar_config()
    exportacao = next(e for e in config["exportacoes"] if e["tabela"] == TABELA_MART)
    return caminho_projeto(config["caminhos"]["processed"], f"{exportacao['arquivo']}.parquet")


def rotulo_mes(data: pd.Timestamp) -> str:
    """Mês no formato curto em português: set/2026."""
    return f"{MESES_ABREV[data.month - 1]}/{data.year}"


def preparar(df: pd.DataFrame) -> pd.DataFrame:
    """Tipos e colunas auxiliares usados nos gráficos."""
    df = df.copy()
    df["primeiro_dia_mes"] = pd.to_datetime(df["primeiro_dia_mes"])
    df = df.sort_values("primeiro_dia_mes", ignore_index=True)
    df["mes_rotulo"] = df["primeiro_dia_mes"].map(rotulo_mes)
    # colunas que podem faltar numa mart gerada por versão anterior do pipeline
    for coluna in COLUNAS_OPCIONAIS:
        if coluna not in df.columns:
            df[coluna] = float("nan")
    return df


def dias_desde_carga(df: pd.DataFrame, agora: pd.Timestamp | None = None) -> int:
    """Dias inteiros desde a última carga do pipeline (coluna carregado_em)."""
    carga = pd.Timestamp(df["carregado_em"].max())
    agora = agora if agora is not None else pd.Timestamp.now(tz=carga.tz)
    return int((agora - carga).total_seconds() // 86400)


def ler_mart(parquet: Path, warehouse: Path) -> Mart:
    """Lê a mart do Parquet exportado ou, na falta dele, do DuckDB."""
    if parquet.exists():
        return Mart(preparar(pd.read_parquet(parquet)), f"data/processed/{parquet.name}")
    if warehouse.exists():
        with duckdb.connect(str(warehouse), read_only=True) as con:
            df = con.sql(f"SELECT * FROM {TABELA_MART}").df()
        return Mart(preparar(df), f"warehouse/{warehouse.name} ({TABELA_MART})")
    raise FileNotFoundError(
        f"Mart não encontrada em {parquet} nem em {warehouse}. Rode o pipeline: pipeline-etl"
    )


def _assinatura(caminho: Path) -> float:
    """Data de modificação do arquivo (0 se não existir); invalida o cache após nova carga."""
    return caminho.stat().st_mtime if caminho.exists() else 0.0


@st.cache_data(show_spinner="Carregando indicadores...", max_entries=4)
def _ler_mart_em_cache(parquet: str, warehouse: str, versao: tuple[float, float]) -> Mart:
    """`versao` (datas de modificação) faz parte da chave do cache: arquivo novo = nova leitura.

    Atenção: não renomear para `_versao`; parâmetros com "_" ficam fora da chave do cache.
    """
    return ler_mart(Path(parquet), Path(warehouse))


def obter_mart() -> Mart:
    """Mart em cache; recarrega sozinha quando o pipeline gera arquivos novos."""
    parquet, warehouse = caminho_parquet_mart(), caminho_warehouse_padrao()
    versao = (_assinatura(parquet), _assinatura(warehouse))
    return _ler_mart_em_cache(str(parquet), str(warehouse), versao)


def recortar(df: pd.DataFrame, inicio: pd.Timestamp, fim: pd.Timestamp) -> pd.DataFrame:
    """Meses entre `inicio` e `fim` (inclusive)."""
    return df[df["primeiro_dia_mes"].between(inicio, fim)].reset_index(drop=True)


def intervalo_do_periodo(rotulos: list[str], meses: int | None) -> tuple[str, str]:
    """Primeiro e último rótulo para um atalho de período (últimos N meses)."""
    inicio = 0 if meses is None else max(0, len(rotulos) - meses)
    return rotulos[inicio], rotulos[-1]


def ultimo(df: pd.DataFrame, coluna: str) -> Indicador:
    """Último valor não nulo da coluna e a diferença para o valor anterior não nulo."""
    serie = df[["mes_rotulo", coluna]].dropna(subset=[coluna])
    if serie.empty:
        return Indicador(None, "-", None)
    valor = float(serie[coluna].iloc[-1])
    variacao = valor - float(serie[coluna].iloc[-2]) if len(serie) > 1 else None
    return Indicador(valor, serie["mes_rotulo"].iloc[-1], variacao)


def texto_variacao(variacao: float | None, casas: int = 2, unidade: str = " p.p.") -> str:
    """'▲ 0,25 p.p. vs mês anterior' (sem cor de bom/ruim: os indicadores são neutros)."""
    if variacao is None or pd.isna(variacao):
        return ""
    if abs(variacao) < 10**-casas / 2:
        return "= estável vs mês anterior"
    seta = "▲" if variacao > 0 else "▼"
    numero = f"{abs(variacao):,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{seta} {numero}{unidade} vs mês anterior"


def intervalo_escolhido(rotulos: list[str], periodo: str, personalizado: object) -> tuple[str, str]:
    """Primeiro e último mês do período escolhido na barra lateral.

    `personalizado` é o valor do slider; aceita par (início, fim) ou um único mês.
    """
    if periodo != PERSONALIZADO:
        return intervalo_do_periodo(rotulos, PERIODOS.get(periodo, PERIODOS[PERIODO_PADRAO]))
    if isinstance(personalizado, (tuple, list)) and len(personalizado) == 2:
        inicio, fim = personalizado
    elif isinstance(personalizado, str):
        inicio = fim = personalizado
    else:
        return intervalo_do_periodo(rotulos, PERIODOS[PERIODO_PADRAO])
    if inicio not in rotulos or fim not in rotulos:
        return intervalo_do_periodo(rotulos, PERIODOS[PERIODO_PADRAO])
    return (inicio, fim) if rotulos.index(inicio) <= rotulos.index(fim) else (fim, inicio)


def barra_lateral(mart: Mart) -> pd.DataFrame:
    """Filtro de período na barra lateral. Devolve a mart recortada.

    Sem callbacks: o seletor escolhe um atalho; o slider só aparece em "Personalizado".
    """
    df = mart.dados
    rotulos = df["mes_rotulo"].tolist()

    with st.sidebar:
        st.header("Período")
        periodo = st.segmented_control(
            "Mostrar",
            [*PERIODOS, PERSONALIZADO],
            default=PERIODO_PADRAO,
            required=True,
            key="f_periodo",
            persist_state="session",
        )
        personalizado = None
        if periodo == PERSONALIZADO:
            personalizado = st.select_slider(
                "Meses",
                options=rotulos,
                value=intervalo_do_periodo(rotulos, PERIODOS[PERIODO_PADRAO]),
                key="f_intervalo",
                persist_state="session",
            )
        inicio_rot, fim_rot = intervalo_escolhido(rotulos, periodo or PERIODO_PADRAO, personalizado)
        st.caption(f"De **{inicio_rot}** a **{fim_rot}**")
        st.divider()
        # o Parquet devolve o horário em UTC: converte para o fuso do projeto antes de exibir
        carga = pd.Timestamp(df["carregado_em"].max()).tz_convert(carregar_config()["fuso_horario"])
        origem = "exportação final (Parquet)" if "processed" in mart.origem else "warehouse DuckDB"
        st.caption(
            f"Fontes: Banco Central (SGS) e ANBIMA. Dados de {rotulos[0]} a {rotulos[-1]}. "
            f"Leitura: {origem}, "
            f"gerada em {carga:%d/%m/%Y %H:%M}. "
            "Para atualizar, rode `pipeline-etl` e recarregue a página."
        )

    inicio = df.loc[df["mes_rotulo"] == inicio_rot, "primeiro_dia_mes"].iloc[0]
    fim = df.loc[df["mes_rotulo"] == fim_rot, "primeiro_dia_mes"].iloc[0]
    return recortar(df, inicio, fim)
