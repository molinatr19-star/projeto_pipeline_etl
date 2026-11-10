"""Orquestra o staging do SGS/BCB: raw -> transformação -> qualidade -> Parquet.

Reconstrói a tabela inteira a cada execução (a partir do raw mais recente de
cada série), então rodar de novo gera o mesmo resultado, sem duplicar linhas.

Uso:
    python -m pipeline_etl.orquestracao.staging_bcb_sgs
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
from pipeline_etl.transformacao.bcb_sgs import (
    CHAVE_STAGING,
    COLUNAS_STAGING,
    NOME_FONTE,
    ResultadoStaging,
    transformar,
)
from pipeline_etl.utils.caminhos import caminho_projeto
from pipeline_etl.utils.configuracao import carregar_config, config_fonte
from pipeline_etl.utils.log import configurar_logging
from pipeline_etl.utils.tempo import agora_no_fuso

logger = logging.getLogger(__name__)


def checagens_staging(
    resultado: ResultadoStaging, series: list[dict[str, Any]]
) -> list[ResultadoChecagem]:
    """Regras de qualidade da tabela de staging do SGS."""
    dados = resultado.dados
    checagens = [
        checar_chave_unica(dados, CHAVE_STAGING),
        checar_sem_nulos(dados, COLUNAS_STAGING),
        checar_condicao(
            "data_referencia não posterior à data_extracao",
            dados["data_referencia"] <= dados["data_extracao"],
        ),
        checar_igualdade(
            "conciliação raw = válidas + rejeitadas + duplicatas",
            resultado.linhas_raw,
            len(dados) + len(resultado.rejeitados) + resultado.duplicatas_removidas,
        ),
    ]
    for serie in series:
        da_serie = dados[dados["codigo_serie"] == serie["codigo"]]
        checagens.append(
            checar_condicao(f"série {serie['codigo']} não vazia", pd.Series([len(da_serie) > 0]))
        )
        minimo, maximo = serie["faixa_valida"]
        checagens.append(checar_faixa(da_serie, "valor", minimo, maximo, serie["nome"]))
    return checagens


def executar() -> ResultadoStaging:
    """Roda o staging de todas as séries configuradas."""
    inicio = time.perf_counter()
    config = carregar_config()
    cfg_fonte = config_fonte(NOME_FONTE)
    series = cfg_fonte["series"]
    tabela = cfg_fonte["tabela_staging"]
    carregado_em = agora_no_fuso(config["fuso_horario"])

    logger.info("Início do staging %s: %s séries", NOME_FONTE, len(series))
    resultado = transformar([s["codigo"] for s in series], carregado_em)
    avaliar(checagens_staging(resultado, series), etapa=tabela)

    pasta_staging = caminho_projeto(config["caminhos"]["staging"])
    salvar_parquet(resultado.dados, pasta_staging / f"{tabela}.parquet")
    salvar_parquet(resultado.rejeitados, pasta_staging / "rejeitados" / f"{tabela}.parquet")

    logger.info(
        "Fim do staging %s: %s linhas raw -> %s válidas, %s rejeitadas, "
        "%s duplicatas removidas (%.1fs)",
        NOME_FONTE,
        resultado.linhas_raw,
        len(resultado.dados),
        len(resultado.rejeitados),
        resultado.duplicatas_removidas,
        time.perf_counter() - inicio,
    )
    return resultado


def main() -> None:
    """Ponto de entrada de linha de comando."""
    configurar_logging()
    executar()


if __name__ == "__main__":
    main()
