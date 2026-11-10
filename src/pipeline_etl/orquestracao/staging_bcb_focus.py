"""Orquestra o staging do Focus: raw -> transformação -> qualidade -> Parquet.

Uso:
    python -m pipeline_etl.orquestracao.staging_bcb_focus
"""

import logging
import time
from typing import Any

import pandas as pd

from pipeline_etl.carga.parquet import salvar_parquet
from pipeline_etl.qualidade.checagens import (
    ResultadoChecagem,
    avaliar,
    checar_chave_unica,
    checar_condicao,
    checar_faixa,
    checar_igualdade,
    checar_sem_nulos,
)
from pipeline_etl.transformacao.bcb_focus import ResultadoFocus, transformar
from pipeline_etl.utils.caminhos import caminho_projeto
from pipeline_etl.utils.configuracao import carregar_config, config_fonte
from pipeline_etl.utils.log import configurar_logging
from pipeline_etl.utils.tempo import agora_no_fuso

NOME_FONTE = "bcb_focus"
OBRIGATORIAS = ["data_pesquisa", "indicador", "mediana_pct", "fonte", "data_extracao"]

logger = logging.getLogger(__name__)


def checagens_focus(resultado: ResultadoFocus, cfg: dict[str, Any]) -> list[ResultadoChecagem]:
    dados = resultado.dados
    minimo, maximo = cfg["faixa_valida"]
    return [
        checar_chave_unica(dados, ["data_pesquisa"]),
        checar_sem_nulos(dados, OBRIGATORIAS),
        checar_faixa(dados, "mediana_pct", minimo, maximo, "mediana IPCA 12 meses"),
        checar_condicao(
            "data_pesquisa não posterior à data_extracao",
            dados["data_pesquisa"] <= dados["data_extracao"],
        ),
        checar_condicao("série não vazia", pd.Series([len(dados) > 0])),
        checar_igualdade(
            "conciliação raw = válidas + rejeitadas + sobreposições",
            resultado.linhas_raw,
            len(dados) + len(resultado.rejeitados) + resultado.sobreposicoes,
        ),
    ]


def executar() -> ResultadoFocus:
    inicio = time.perf_counter()
    config = carregar_config()
    cfg = config_fonte(NOME_FONTE)
    tabela = cfg["tabela_staging"]
    carregado_em = agora_no_fuso(config["fuso_horario"])

    resultado = transformar(carregado_em)
    avaliar(checagens_focus(resultado, cfg), etapa=tabela)
    pasta = caminho_projeto(config["caminhos"]["staging"])
    salvar_parquet(resultado.dados, pasta / f"{tabela}.parquet")
    salvar_parquet(resultado.rejeitados, pasta / "rejeitados" / f"{tabela}.parquet")
    logger.info("Fim do staging %s (%.1fs)", NOME_FONTE, time.perf_counter() - inicio)
    return resultado


def main() -> None:
    configurar_logging()
    executar()


if __name__ == "__main__":
    main()
