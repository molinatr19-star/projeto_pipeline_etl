"""Staging dos feriados da ANBIMA: leitura da planilha, limpeza e uma linha por data.

Etapa de TRANSFORMAÇÃO: lê o raw e devolve DataFrames. Não grava nada.
"""

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from pipeline_etl.utils.caminhos import caminho_projeto
from pipeline_etl.utils.configuracao import carregar_config

NOME_FONTE = "anbima_feriados"
PREFIXO_PARTICAO = "data_extracao="
COLUNAS_PLANILHA = {"Data": "data", "Dia da Semana": "dia_semana_fonte", "Feriado": "nome_feriado"}
COLUNAS_STAGING = ["data", "nome_feriado", "fonte", "data_extracao", "carregado_em"]
DIAS_SEMANA = [
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
]

logger = logging.getLogger(__name__)


@dataclass
class ResultadoFeriados:
    """Saída da transformação, com as contagens usadas nas checagens."""

    dados: pd.DataFrame
    linhas_planilha: int
    linhas_rodape: int
    linhas_feriado: int
    datas_com_mais_de_um_feriado: int
    divergencias_dia_semana: int


def localizar_raw_mais_recente(nome_arquivo: str, pasta_fonte: Path | None = None) -> Path:
    """Planilha da partição de extração mais recente."""
    pasta_fonte = pasta_fonte or caminho_projeto(carregar_config()["caminhos"]["raw"], NOME_FONTE)
    candidatos = sorted(pasta_fonte.glob(f"{PREFIXO_PARTICAO}*/{nome_arquivo}"))
    if not candidatos:
        raise FileNotFoundError(f"Nenhum raw de {NOME_FONTE} em {pasta_fonte}")
    return candidatos[-1]


def data_extracao_do_caminho(arquivo: Path) -> date:
    return date.fromisoformat(arquivo.parent.name.removeprefix(PREFIXO_PARTICAO))


def ler_planilha(arquivo: Path) -> pd.DataFrame:
    """Lê a aba de feriados como texto bruto (a data é convertida em padronizar)."""
    bruto = pd.read_excel(arquivo, sheet_name="Feriados", engine="calamine")
    faltando = set(COLUNAS_PLANILHA) - set(bruto.columns)
    if faltando:
        raise ValueError(f"Planilha sem as colunas esperadas: {sorted(faltando)}")
    return bruto[list(COLUNAS_PLANILHA)].rename(columns=COLUNAS_PLANILHA)


def padronizar_feriados(
    bruto: pd.DataFrame, data_extracao: date, carregado_em: pd.Timestamp
) -> ResultadoFeriados:
    """Remove o rodapé, limpa textos e deixa uma linha por data.

    - Rodapé: linhas cuja coluna Data não é uma data ("Fonte: ANBIMA", notas).
    - Dois feriados na mesma data (ex.: 21/04/2079) viram uma linha com os nomes
      unidos por " / ".
    """
    data = pd.to_datetime(bruto["data"], errors="coerce")
    eh_feriado = data.notna()
    feriados = bruto[eh_feriado].assign(
        data=data[eh_feriado].dt.date,
        nome_feriado=bruto.loc[eh_feriado, "nome_feriado"].str.strip(),
        dia_semana_fonte=bruto.loc[eh_feriado, "dia_semana_fonte"].str.strip().str.lower(),
    )

    dia_semana_calculado = data[eh_feriado].dt.day_of_week.map(dict(enumerate(DIAS_SEMANA)))
    divergencias = int((feriados["dia_semana_fonte"] != dia_semana_calculado).sum())

    por_data = (
        feriados.groupby("data", as_index=False)
        .agg(nome_feriado=("nome_feriado", lambda nomes: " / ".join(sorted(nomes.dropna()))))
        .sort_values("data", ignore_index=True)
    )
    dados = por_data.assign(
        fonte=NOME_FONTE, data_extracao=data_extracao, carregado_em=carregado_em
    )[COLUNAS_STAGING]

    return ResultadoFeriados(
        dados=dados,
        linhas_planilha=len(bruto),
        linhas_rodape=int((~eh_feriado).sum()),
        linhas_feriado=int(eh_feriado.sum()),
        datas_com_mais_de_um_feriado=len(feriados) - len(por_data),
        divergencias_dia_semana=divergencias,
    )


def transformar(
    nome_arquivo: str, carregado_em: pd.Timestamp, pasta_fonte: Path | None = None
) -> ResultadoFeriados:
    """Lê o raw mais recente e devolve o staging de feriados."""
    arquivo = localizar_raw_mais_recente(nome_arquivo, pasta_fonte)
    resultado = padronizar_feriados(
        ler_planilha(arquivo), data_extracao_do_caminho(arquivo), carregado_em
    )
    logger.info(
        "%s (%s): %s linhas na planilha -> %s feriados, %s linhas de rodapé, "
        "%s datas com mais de um feriado -> %s datas",
        NOME_FONTE,
        arquivo.parent.name,
        resultado.linhas_planilha,
        resultado.linhas_feriado,
        resultado.linhas_rodape,
        resultado.datas_com_mais_de_um_feriado,
        len(resultado.dados),
    )
    return resultado
