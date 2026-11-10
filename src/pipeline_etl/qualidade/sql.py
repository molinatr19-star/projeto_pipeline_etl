"""Checagens de qualidade escritas em SQL (sql/qualidade/).

Convenção: cada consulta devolve as linhas com problema; zero linhas = aprovado.
"""

import duckdb

from pipeline_etl.qualidade.checagens import ResultadoChecagem
from pipeline_etl.utils.sql import arquivos_sql, ler_sql


def checar_sql(con: duckdb.DuckDBPyConnection, arquivo) -> ResultadoChecagem:
    """Roda uma consulta de qualidade e passa se ela não retornar linhas."""
    linhas = con.execute(ler_sql(arquivo)).fetchall()
    if not linhas:
        return ResultadoChecagem(arquivo.stem, True, "ok")
    exemplos = ", ".join(str(linha) for linha in linhas[:3])
    return ResultadoChecagem(arquivo.stem, False, f"{len(linhas)} linhas com problema: {exemplos}")


def checar_pasta(con: duckdb.DuckDBPyConnection, pasta) -> list[ResultadoChecagem]:
    """Roda todas as consultas de qualidade da pasta."""
    return [checar_sql(con, arquivo) for arquivo in arquivos_sql(pasta)]
