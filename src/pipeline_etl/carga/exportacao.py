"""Exportação de tabelas do warehouse para arquivos (Parquet e CSV).

Etapa de CARGA: copia a tabela como está, sem regra de negócio.
"""

import logging
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)

OPCOES_FORMATO = {
    "parquet": "FORMAT parquet",
    # CSV padrão internacional: vírgula como separador e ponto decimal (abre em qualquer ferramenta)
    "csv": "FORMAT csv, HEADER true, DELIMITER ','",
}


def exportar_tabela(
    con: duckdb.DuckDBPyConnection, tabela: str, destino: Path, formato: str
) -> Path:
    """Exporta a tabela inteira, ordenada pela 1ª coluna, com troca atômica do arquivo."""
    if formato not in OPCOES_FORMATO:
        raise ValueError(f"Formato não suportado: {formato}. Use {sorted(OPCOES_FORMATO)}")

    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_name(destino.name + ".tmp")
    caminho_sql = temporario.as_posix().replace("'", "''")
    con.execute(
        f"COPY (SELECT * FROM {tabela} ORDER BY 1) TO '{caminho_sql}' ({OPCOES_FORMATO[formato]})"
    )
    temporario.replace(destino)
    return destino


def contar_linhas_arquivo(caminho: Path, formato: str) -> int:
    """Relê o arquivo exportado e conta as linhas (conferência pós-exportação)."""
    leitor = "read_parquet" if formato == "parquet" else "read_csv"
    caminho_sql = caminho.as_posix().replace("'", "''")
    relacao = duckdb.sql(f"SELECT COUNT(*) FROM {leitor}('{caminho_sql}')")
    if relacao is None:  # só acontece com instruções sem resultado; aqui é um SELECT
        raise RuntimeError(f"Não foi possível contar as linhas de {caminho}")
    return relacao.fetchall()[0][0]
