"""Execução de scripts SQL no warehouse DuckDB.

Etapa de CARGA: só executa os arquivos de sql/ na ordem. A modelagem
(regras de negócio) fica nos próprios arquivos .sql.
"""

import logging
from pathlib import Path

import duckdb

from pipeline_etl.utils.sql import arquivos_sql, ler_sql

logger = logging.getLogger(__name__)


def executar_pasta(
    con: duckdb.DuckDBPyConnection, pasta: Path, parametros: dict[str, str] | None = None
) -> None:
    """Executa todos os .sql da pasta em ordem de nome."""
    for arquivo in arquivos_sql(pasta):
        con.execute(ler_sql(arquivo, parametros))
        logger.info("Executado sql/%s/%s", pasta.name, arquivo.name)


def contar_linhas(con: duckdb.DuckDBPyConnection, tabela: str) -> int:
    """Quantidade de linhas de uma tabela (nome qualificado: schema.tabela)."""
    return con.execute(f"SELECT COUNT(*) FROM {tabela}").fetchall()[0][0]
