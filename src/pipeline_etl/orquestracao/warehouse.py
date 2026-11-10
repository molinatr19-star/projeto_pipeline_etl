"""Orquestra a carga do warehouse DuckDB: Parquets de staging -> schemas staging e marts.

Tudo roda em UMA transação: DDL, staging, marts e checagens de qualidade.
Se algo falhar, a transação é desfeita e o warehouse anterior fica intacto.
Reconstrói as tabelas a cada execução, então rodar de novo dá o mesmo resultado.

Uso:
    python -m pipeline_etl.orquestracao.warehouse
"""

import logging
import os
import time
from pathlib import Path

import duckdb

from pipeline_etl.carga.warehouse import contar_linhas, executar_pasta
from pipeline_etl.qualidade.checagens import avaliar
from pipeline_etl.qualidade.sql import checar_pasta
from pipeline_etl.utils.caminhos import caminho_projeto
from pipeline_etl.utils.configuracao import carregar_config, config_fonte
from pipeline_etl.utils.log import configurar_logging

PASTAS_CONSTRUCAO = ["ddl", "staging", "marts"]
# parâmetro usado nos arquivos SQL -> fonte cujo staging ele aponta
PARAMETROS_STAGING = {
    "caminho_stg_bcb_series": "bcb_sgs",
    "caminho_stg_feriados": "anbima_feriados",
    "caminho_stg_focus": "bcb_focus",
}
TABELAS = [
    "staging.stg_bcb_series",
    "staging.stg_feriados",
    "staging.stg_focus_ipca_12m",
    "marts.dim_serie",
    "marts.dim_data",
    "marts.fct_indicador",
    "marts.fct_expectativa",
    "marts.mart_indicadores_mensal",
]

logger = logging.getLogger(__name__)


def caminho_warehouse_padrao() -> Path:
    """DUCKDB_CAMINHO do .env, se existir; senão o caminho do pipeline.yaml."""
    config = carregar_config()  # também carrega o .env
    relativo = os.getenv("DUCKDB_CAMINHO") or config["caminhos"]["warehouse"]
    return caminho_projeto(relativo)


def caminhos_staging_padrao() -> dict[str, Path]:
    """{parametro_sql: Parquet de staging} a partir do pipeline.yaml."""
    pasta = caminho_projeto(carregar_config()["caminhos"]["staging"])
    return {
        parametro: pasta / f"{config_fonte(fonte)['tabela_staging']}.parquet"
        for parametro, fonte in PARAMETROS_STAGING.items()
    }


def executar(
    caminho_warehouse: Path | None = None, caminhos_staging: dict[str, Path] | None = None
) -> dict[str, int]:
    """Reconstrói o warehouse e devolve {tabela: linhas}."""
    inicio = time.perf_counter()
    caminho_warehouse = caminho_warehouse or caminho_warehouse_padrao()
    caminhos_staging = caminhos_staging or caminhos_staging_padrao()
    faltando = [str(c) for c in caminhos_staging.values() if not c.exists()]
    if faltando:
        raise FileNotFoundError(f"Staging não encontrado: {faltando}. Rode o staging antes.")

    pasta_sql = caminho_projeto("sql")
    parametros = {nome: caminho.as_posix() for nome, caminho in caminhos_staging.items()}
    caminho_warehouse.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Início da carga do warehouse: %s", caminho_warehouse.name)
    con = duckdb.connect(str(caminho_warehouse))
    try:
        con.begin()
        for pasta in PASTAS_CONSTRUCAO:
            executar_pasta(con, pasta_sql / pasta, parametros)
        avaliar(checar_pasta(con, pasta_sql / "qualidade"), etapa="warehouse")
        contagens = {tabela: contar_linhas(con, tabela) for tabela in TABELAS}
        con.commit()
    except Exception:
        con.rollback()
        logger.error("Carga desfeita (rollback); warehouse anterior mantido")
        raise
    finally:
        con.close()

    for tabela, linhas in contagens.items():
        logger.info("%s: %s linhas", tabela, linhas)
    logger.info("Fim da carga do warehouse (%.1fs)", time.perf_counter() - inicio)
    return contagens


def main() -> None:
    configurar_logging()
    executar()


if __name__ == "__main__":
    main()
