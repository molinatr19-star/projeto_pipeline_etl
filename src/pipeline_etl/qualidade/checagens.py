"""Checagens genéricas de qualidade de dados.

Cada checagem devolve um ResultadoChecagem; `avaliar` registra todos no log
e interrompe a etapa se algum falhou.
"""

import logging
from dataclasses import dataclass

import pandas as pd

logger = logging.getLogger(__name__)


class FalhaQualidadeError(Exception):
    """Uma ou mais checagens de qualidade falharam."""


@dataclass
class ResultadoChecagem:
    nome: str
    ok: bool
    detalhe: str


def checar_condicao(nome: str, linhas_validas: pd.Series) -> ResultadoChecagem:
    """Passa se todas as linhas atendem à condição (True = linha correta)."""
    falhas = int((~linhas_validas).sum())
    detalhe = f"{falhas} de {len(linhas_validas)} linhas violam a regra" if falhas else "ok"
    return ResultadoChecagem(nome, falhas == 0, detalhe)


def checar_chave_unica(df: pd.DataFrame, chave: list[str]) -> ResultadoChecagem:
    """Nenhuma combinação de chave pode se repetir."""
    return checar_condicao(f"chave única {chave}", ~df.duplicated(subset=chave, keep=False))


def checar_sem_nulos(df: pd.DataFrame, colunas: list[str]) -> ResultadoChecagem:
    """Colunas obrigatórias não podem ter valor vazio."""
    return checar_condicao(f"sem nulos em {colunas}", df[colunas].notna().all(axis=1))


def checar_faixa(
    df: pd.DataFrame, coluna: str, minimo: float, maximo: float, rotulo: str = ""
) -> ResultadoChecagem:
    """Valores dentro de [minimo, maximo]."""
    nome = f"{coluna} entre {minimo} e {maximo}" + (f" ({rotulo})" if rotulo else "")
    return checar_condicao(nome, df[coluna].between(minimo, maximo))


def checar_igualdade(nome: str, esperado: int, obtido: int) -> ResultadoChecagem:
    """Dois números precisam bater (ex.: conciliação de contagens entre camadas)."""
    detalhe = "ok" if esperado == obtido else f"esperado {esperado}, obtido {obtido}"
    return ResultadoChecagem(nome, esperado == obtido, detalhe)


def avaliar(resultados: list[ResultadoChecagem], etapa: str) -> None:
    """Registra cada checagem no log e falha se alguma não passou."""
    for resultado in resultados:
        nivel = logging.INFO if resultado.ok else logging.ERROR
        status = "OK   " if resultado.ok else "FALHA"
        logger.log(nivel, "[%s] %s %s: %s", etapa, status, resultado.nome, resultado.detalhe)

    falhas = [r.nome for r in resultados if not r.ok]
    if falhas:
        raise FalhaQualidadeError(f"{etapa}: {len(falhas)} checagens falharam: {falhas}")
    logger.info("[%s] %s checagens aprovadas", etapa, len(resultados))
