"""Orquestra a exportação final: tabelas do warehouse -> data/processed.

As tabelas e formatos ficam em `exportacoes` no config/pipeline.yaml.
Cada arquivo é relido depois de gravado para conferir a quantidade de linhas.

Uso:
    python -m pipeline_etl.orquestracao.exportacao
"""

import logging
import time
from pathlib import Path

import duckdb

from pipeline_etl.carga.exportacao import contar_linhas_arquivo, exportar_tabela
from pipeline_etl.carga.warehouse import contar_linhas
from pipeline_etl.orquestracao.warehouse import caminho_warehouse_padrao
from pipeline_etl.qualidade.checagens import avaliar, checar_igualdade
from pipeline_etl.utils.caminhos import caminho_projeto
from pipeline_etl.utils.configuracao import carregar_config
from pipeline_etl.utils.log import configurar_logging

logger = logging.getLogger(__name__)


def executar(
    caminho_warehouse: Path | None = None, pasta_destino: Path | None = None
) -> list[Path]:
    """Exporta as tabelas configuradas e devolve os arquivos gerados."""
    inicio = time.perf_counter()
    config = carregar_config()
    caminho_warehouse = caminho_warehouse or caminho_warehouse_padrao()
    pasta_destino = pasta_destino or caminho_projeto(config["caminhos"]["processed"])
    if not caminho_warehouse.exists():
        raise FileNotFoundError(
            f"Warehouse não encontrado: {caminho_warehouse}. Rode a carga antes."
        )

    gerados, checagens = [], []
    with duckdb.connect(str(caminho_warehouse), read_only=True) as con:
        for exportacao in config["exportacoes"]:
            tabela = exportacao["tabela"]
            linhas_tabela = contar_linhas(con, tabela)
            for formato in exportacao["formatos"]:
                destino = pasta_destino / f"{exportacao['arquivo']}.{formato}"
                exportar_tabela(con, tabela, destino, formato)
                checagens.append(
                    checar_igualdade(
                        f"{destino.name} com as mesmas linhas de {tabela}",
                        linhas_tabela,
                        contar_linhas_arquivo(destino, formato),
                    )
                )
                gerados.append(destino)
                logger.info("Exportado %s (%s linhas)", destino.name, linhas_tabela)

    avaliar(checagens, etapa="exportacao")
    logger.info(
        "Fim da exportação: %s arquivos (%.1fs)", len(gerados), time.perf_counter() - inicio
    )
    return gerados


def main() -> None:
    configurar_logging()
    executar()


if __name__ == "__main__":
    main()
