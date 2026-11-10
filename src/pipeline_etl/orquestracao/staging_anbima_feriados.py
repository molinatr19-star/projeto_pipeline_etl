"""Orquestra o staging de feriados: raw (.xls) -> transformação -> qualidade -> Parquet.

Uso:
    python -m pipeline_etl.orquestracao.staging_anbima_feriados
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
    checar_igualdade,
    checar_sem_nulos,
)
from pipeline_etl.transformacao.anbima_feriados import (
    COLUNAS_STAGING,
    NOME_FONTE,
    ResultadoFeriados,
    transformar,
)
from pipeline_etl.utils.caminhos import caminho_projeto
from pipeline_etl.utils.configuracao import carregar_config, config_fonte
from pipeline_etl.utils.log import configurar_logging
from pipeline_etl.utils.tempo import agora_no_fuso

logger = logging.getLogger(__name__)


def checagens_feriados(
    resultado: ResultadoFeriados, cfg: dict[str, Any]
) -> list[ResultadoChecagem]:
    """Regras de qualidade do staging de feriados."""
    dados = resultado.dados
    anos = pd.Series([d.year for d in dados["data"]])
    por_ano = anos.value_counts()
    return [
        checar_chave_unica(dados, ["data"]),
        checar_sem_nulos(dados, COLUNAS_STAGING),
        checar_condicao("nome_feriado não vazio", dados["nome_feriado"].str.len() > 0),
        checar_igualdade(
            "dia da semana da planilha confere com a data", 0, resultado.divergencias_dia_semana
        ),
        checar_igualdade(
            "conciliação planilha = feriados + rodapé",
            resultado.linhas_planilha,
            resultado.linhas_feriado + resultado.linhas_rodape,
        ),
        checar_igualdade(
            "conciliação feriados = datas + datas repetidas",
            resultado.linhas_feriado,
            len(dados) + resultado.datas_com_mais_de_um_feriado,
        ),
        checar_condicao(
            f"pelo menos {cfg['min_feriados_por_ano']} feriados em cada ano",
            por_ano >= cfg["min_feriados_por_ano"],
        ),
        checar_igualdade(
            "nenhum ano faltando no intervalo",
            int(anos.max() - anos.min() + 1) if len(anos) else 0,
            int(anos.nunique()),
        ),
    ]


def executar() -> ResultadoFeriados:
    """Roda o staging de feriados."""
    inicio = time.perf_counter()
    config = carregar_config()
    cfg = config_fonte(NOME_FONTE)
    tabela = cfg["tabela_staging"]
    carregado_em = agora_no_fuso(config["fuso_horario"])

    logger.info("Início do staging %s", NOME_FONTE)
    resultado = transformar(cfg["arquivo_raw"], carregado_em)
    avaliar(checagens_feriados(resultado, cfg), etapa=tabela)
    salvar_parquet(
        resultado.dados, caminho_projeto(config["caminhos"]["staging"], f"{tabela}.parquet")
    )
    logger.info("Fim do staging %s (%.1fs)", NOME_FONTE, time.perf_counter() - inicio)
    return resultado


def main() -> None:
    configurar_logging()
    executar()


if __name__ == "__main__":
    main()
