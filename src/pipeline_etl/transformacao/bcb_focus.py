"""Staging das expectativas do Focus: tipagem, junção das partições e uma linha por data.

Etapa de TRANSFORMAÇÃO: lê o raw e devolve DataFrames. Não grava nada.
Com extração incremental, a mesma data pode estar em mais de uma partição; vale a
extração mais recente (revisões da API substituem o valor antigo).
"""

import json
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from pipeline_etl.extracao.bcb_focus import ARQUIVO, NOME_FONTE, pasta_fonte

PREFIXO_PARTICAO = "data_extracao="
COLUNAS_STAGING = [
    "data_pesquisa",
    "indicador",
    "horizonte",
    "mediana_pct",
    "media_pct",
    "desvio_padrao",
    "numero_respondentes",
    "fonte",
    "data_extracao",
    "carregado_em",
]

logger = logging.getLogger(__name__)


@dataclass
class ResultadoFocus:
    dados: pd.DataFrame
    rejeitados: pd.DataFrame
    linhas_raw: int
    sobreposicoes: int
    particoes: int


def ler_particoes(pasta: Path | None = None) -> pd.DataFrame:
    """Todas as partições do raw, com a data de extração de cada linha."""
    pasta = pasta or pasta_fonte()
    partes = []
    for arquivo in sorted(pasta.glob(f"{PREFIXO_PARTICAO}*/{ARQUIVO}")):
        registros = json.loads(arquivo.read_text(encoding="utf-8"))
        extracao = date.fromisoformat(arquivo.parent.name.removeprefix(PREFIXO_PARTICAO))
        partes.append(pd.DataFrame(registros).assign(data_extracao=extracao))
    if not partes:
        raise FileNotFoundError(f"Nenhum raw de {NOME_FONTE} em {pasta}")
    return pd.concat(partes, ignore_index=True)


def padronizar(bruto: pd.DataFrame, carregado_em: pd.Timestamp) -> ResultadoFocus:
    """Converte tipos, separa inválidos e mantém a extração mais recente de cada data."""
    data = pd.to_datetime(bruto["Data"], format="%Y-%m-%d", errors="coerce")
    mediana = pd.to_numeric(bruto["Mediana"], errors="coerce")
    invalido = data.isna() | mediana.isna()

    validos = pd.DataFrame(
        {
            "data_pesquisa": data[~invalido].dt.date,
            "indicador": bruto.loc[~invalido, "Indicador"],
            "horizonte": "12 meses",
            "mediana_pct": mediana[~invalido].astype("float64"),
            "media_pct": pd.to_numeric(bruto.loc[~invalido, "Media"], errors="coerce"),
            "desvio_padrao": pd.to_numeric(bruto.loc[~invalido, "DesvioPadrao"], errors="coerce"),
            "numero_respondentes": pd.to_numeric(
                bruto.loc[~invalido, "numeroRespondentes"], errors="coerce"
            ).astype("Int64"),
            "fonte": NOME_FONTE,
            "data_extracao": bruto.loc[~invalido, "data_extracao"],
            "carregado_em": carregado_em,
        },
        columns=COLUNAS_STAGING,
    )
    # partições em ordem crescente de extração: "last" = extração mais recente
    ordenados = validos.sort_values("data_extracao", kind="stable")
    unicos = ordenados.drop_duplicates(subset=["data_pesquisa"], keep="last")
    rejeitados = bruto[invalido].assign(
        motivo="data_ou_mediana_invalida", carregado_em=carregado_em
    )
    return ResultadoFocus(
        dados=unicos.sort_values("data_pesquisa", ignore_index=True),
        rejeitados=rejeitados.reset_index(drop=True),
        linhas_raw=len(bruto),
        sobreposicoes=len(validos) - len(unicos),
        particoes=int(bruto["data_extracao"].nunique()),
    )


def transformar(carregado_em: pd.Timestamp, pasta: Path | None = None) -> ResultadoFocus:
    resultado = padronizar(ler_particoes(pasta), carregado_em)
    logger.info(
        "%s: %s linhas em %s partições -> %s datas, %s rejeitadas, %s sobreposições",
        NOME_FONTE,
        resultado.linhas_raw,
        resultado.particoes,
        len(resultado.dados),
        len(resultado.rejeitados),
        resultado.sobreposicoes,
    )
    return resultado
