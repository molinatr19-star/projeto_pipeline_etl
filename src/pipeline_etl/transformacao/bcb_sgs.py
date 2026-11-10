"""Staging das séries do SGS/BCB: tipagem, padronização e separação de rejeitados.

Etapa de TRANSFORMAÇÃO: lê o raw e devolve DataFrames. Não grava nada.
"""

import json
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from pipeline_etl.utils.caminhos import caminho_projeto
from pipeline_etl.utils.configuracao import carregar_config
from pipeline_etl.utils.raw import caminho_meta, listar_arquivos

NOME_FONTE = "bcb_sgs"
PREFIXO_PARTICAO = "data_extracao="
CHAVE_STAGING = ["codigo_serie", "data_referencia"]
COLUNAS_STAGING = [
    "codigo_serie",
    "nome_serie",
    "data_referencia",
    "valor",
    "unidade",
    "periodicidade",
    "fonte",
    "data_extracao",
    "carregado_em",
]
COLUNAS_REJEITADOS = [
    "codigo_serie",
    "data_raw",
    "valor_raw",
    "motivo",
    "data_extracao",
    "carregado_em",
]

logger = logging.getLogger(__name__)


@dataclass
class RawSerie:
    """Conteúdo de um arquivo raw e de seus metadados."""

    codigo: int
    registros: list[dict[str, Any]]
    metadados: dict[str, Any]
    data_extracao: date
    arquivo: Path


@dataclass
class ResultadoStaging:
    """Saída da transformação, com as contagens para conciliação."""

    dados: pd.DataFrame
    rejeitados: pd.DataFrame
    linhas_raw: int
    duplicatas_removidas: int


def pasta_raw_fonte() -> Path:
    """Pasta raw da fonte: data/raw/bcb_sgs/."""
    return caminho_projeto(carregar_config()["caminhos"]["raw"], NOME_FONTE)


def localizar_raw_mais_recente(codigo: int, pasta_fonte: Path | None = None) -> Path:
    """Arquivo raw da série na partição de extração mais recente.

    As partições usam data ISO (AAAA-MM-DD), então a ordem alfabética é a cronológica.
    """
    pasta_fonte = pasta_fonte or pasta_raw_fonte()
    candidatos = listar_arquivos(pasta_fonte, f"serie_{codigo}")
    if not candidatos:
        raise FileNotFoundError(f"Nenhum raw da série {codigo} em {pasta_fonte}")
    return candidatos[-1]


def ler_raws(codigo: int, pasta_fonte: Path | None = None) -> list[RawSerie]:
    """Todas as partições da série, da extração mais antiga para a mais recente.

    Com extração incremental cada partição traz só um trecho da série; juntas formam
    o histórico completo.
    """
    pasta_fonte = pasta_fonte or pasta_raw_fonte()
    arquivos = listar_arquivos(pasta_fonte, f"serie_{codigo}")
    if not arquivos:
        raise FileNotFoundError(f"Nenhum raw da série {codigo} em {pasta_fonte}")
    return [_ler_arquivo(codigo, arquivo) for arquivo in arquivos]


def ler_raw(codigo: int, pasta_fonte: Path | None = None) -> RawSerie:
    """Lê o raw mais recente da série e o .meta.json ao lado."""
    return _ler_arquivo(codigo, localizar_raw_mais_recente(codigo, pasta_fonte))


def _ler_arquivo(codigo: int, arquivo: Path) -> RawSerie:
    arquivo_meta = caminho_meta(arquivo)
    return RawSerie(
        codigo=codigo,
        registros=json.loads(arquivo.read_text(encoding="utf-8")),
        metadados=json.loads(arquivo_meta.read_text(encoding="utf-8")),
        data_extracao=date.fromisoformat(arquivo.parent.name.removeprefix(PREFIXO_PARTICAO)),
        arquivo=arquivo,
    )


def padronizar_serie(
    raw: RawSerie, carregado_em: pd.Timestamp
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Converte tipos e separa linhas inválidas. Retorna (validos, rejeitados)."""
    bruto = pd.DataFrame(raw.registros, columns=["data", "valor"])
    data_referencia = pd.to_datetime(bruto["data"], format="%d/%m/%Y", errors="coerce")
    valor = pd.to_numeric(bruto["valor"], errors="coerce")

    motivo = np.select(
        [data_referencia.isna(), valor.isna()],
        ["data_invalida", "valor_invalido"],
        default="",
    )
    invalido = motivo != ""

    validos = pd.DataFrame(
        {
            "codigo_serie": raw.codigo,
            "nome_serie": raw.metadados["nome_serie"],
            "data_referencia": data_referencia[~invalido].dt.date,
            "valor": valor[~invalido].astype("float64"),
            "unidade": raw.metadados["unidade"],
            "periodicidade": raw.metadados["periodicidade"],
            "fonte": NOME_FONTE,
            "data_extracao": raw.data_extracao,
            "carregado_em": carregado_em,
        },
        columns=COLUNAS_STAGING,
    )
    rejeitados = pd.DataFrame(
        {
            "codigo_serie": raw.codigo,
            "data_raw": bruto.loc[invalido, "data"],
            "valor_raw": bruto.loc[invalido, "valor"],
            "motivo": motivo[invalido],
            "data_extracao": raw.data_extracao,
            "carregado_em": carregado_em,
        },
        columns=COLUNAS_REJEITADOS,
    )
    return validos, rejeitados


def remover_duplicatas(df: pd.DataFrame, chave: list[str]) -> tuple[pd.DataFrame, int]:
    """Remove linhas repetidas pela chave (mantém a última) e devolve quantas saíram."""
    sem_duplicatas = df.drop_duplicates(subset=chave, keep="last")
    return sem_duplicatas, len(df) - len(sem_duplicatas)


def transformar(
    codigos: list[int], carregado_em: pd.Timestamp, pasta_fonte: Path | None = None
) -> ResultadoStaging:
    """Monta o staging de todas as séries informadas, juntando todas as partições.

    A mesma data pode vir em mais de uma partição (sobreposição da extração
    incremental): vale a extração mais recente.
    """
    partes_validas, partes_rejeitadas = [], []
    linhas_raw = 0
    for codigo in codigos:
        particoes = ler_raws(codigo, pasta_fonte)
        linhas_serie = validas_serie = rejeitadas_serie = 0
        for raw in particoes:  # da extração mais antiga para a mais recente
            validos, rejeitados = padronizar_serie(raw, carregado_em)
            linhas_serie += len(raw.registros)
            validas_serie += len(validos)
            rejeitadas_serie += len(rejeitados)
            partes_validas.append(validos)
            partes_rejeitadas.append(rejeitados)
        linhas_raw += linhas_serie
        logger.info(
            "Série %s: %s linhas em %s partição(ões) -> %s válidas, %s rejeitadas",
            codigo,
            linhas_serie,
            len(particoes),
            validas_serie,
            rejeitadas_serie,
        )

    dados = pd.concat(partes_validas, ignore_index=True)
    dados, duplicatas = remover_duplicatas(dados, CHAVE_STAGING)  # "last" = extração mais nova
    if duplicatas:
        logger.info(
            "%s linhas repetidas por %s (sobreposição entre extrações) consolidadas",
            duplicatas,
            CHAVE_STAGING,
        )
    dados = dados.sort_values(CHAVE_STAGING, ignore_index=True)

    return ResultadoStaging(
        dados=dados,
        rejeitados=pd.concat(partes_rejeitadas, ignore_index=True),
        linhas_raw=linhas_raw,
        duplicatas_removidas=duplicatas,
    )
