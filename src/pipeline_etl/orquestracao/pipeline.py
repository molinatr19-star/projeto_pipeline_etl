"""Orquestrador único: roda o pipeline inteiro, de ponta a ponta, na ordem certa.

    extração (API SGS + API Focus + arquivo ANBIMA) -> staging -> warehouse -> exportação

Para no primeiro erro (as etapas seguintes dependem das anteriores) e termina
com código de saída 1, o que permite agendar e monitorar a execução.

Uso:
    python -m pipeline_etl.orquestracao.pipeline
    python -m pipeline_etl.orquestracao.pipeline --sem-extracao        # usa o raw já baixado
    python -m pipeline_etl.orquestracao.pipeline --etapas warehouse exportacao
    python -m pipeline_etl.orquestracao.pipeline --reextrair-hoje      # busca de novo hoje
    pipeline-etl                                                        # atalho instalado pelo pip
"""

import argparse
import logging
import sys
import time
from collections.abc import Callable
from datetime import datetime
from functools import partial

from pipeline_etl.extracao import anbima_feriados as extracao_feriados
from pipeline_etl.extracao import bcb_focus as extracao_focus
from pipeline_etl.extracao import bcb_sgs as extracao_bcb
from pipeline_etl.orquestracao import (
    exportacao,
    staging_anbima_feriados,
    staging_bcb_focus,
    staging_bcb_sgs,
    warehouse,
)
from pipeline_etl.utils.log import configurar_logging

# Ordem de execução. Cada etapa levanta exceção se falhar; as extrações de API aceitam
# `reextrair_hoje` (ver funcao_da_etapa).
ETAPAS: dict[str, Callable[..., object]] = {
    "extracao_bcb_sgs": extracao_bcb.executar,
    "extracao_anbima_feriados": extracao_feriados.executar,
    "extracao_bcb_focus": extracao_focus.executar,
    "staging_bcb_sgs": staging_bcb_sgs.executar,
    "staging_anbima_feriados": staging_anbima_feriados.executar,
    "staging_bcb_focus": staging_bcb_focus.executar,
    "warehouse": warehouse.executar,
    "exportacao": exportacao.executar,
}
ETAPAS_EXTRACAO = {"extracao_bcb_sgs", "extracao_anbima_feriados", "extracao_bcb_focus"}
# Extrações de API que aceitam buscar de novo no mesmo dia (nova versão do arquivo do raw).
# A planilha da ANBIMA muda raramente: continua uma extração por dia.
ETAPAS_REEXTRAIVEIS = {"extracao_bcb_sgs", "extracao_bcb_focus"}

# Progresso: (posição, total, nome da etapa, estado) com estado "inicio" ou "fim".
Progresso = Callable[[int, int, str, str], None]

logger = logging.getLogger(__name__)


def selecionar_etapas(etapas: list[str] | None, sem_extracao: bool) -> list[str]:
    """Etapas a rodar, sempre na ordem oficial de ETAPAS."""
    escolhidas = set(etapas) if etapas else set(ETAPAS)
    desconhecidas = escolhidas - set(ETAPAS)
    if desconhecidas:
        raise ValueError(f"Etapas desconhecidas: {sorted(desconhecidas)}")
    if sem_extracao:
        escolhidas -= ETAPAS_EXTRACAO
    return [nome for nome in ETAPAS if nome in escolhidas]


def funcao_da_etapa(nome: str, reextrair_hoje: bool) -> Callable[[], object]:
    """Função da etapa; nas extrações de API, repassa `reextrair_hoje`."""
    if reextrair_hoje and nome in ETAPAS_REEXTRAIVEIS:
        return partial(ETAPAS[nome], reextrair_hoje=True)
    return ETAPAS[nome]


def executar(
    etapas: list[str] | None = None,
    sem_extracao: bool = False,
    reextrair_hoje: bool = False,
    progresso: Progresso | None = None,
) -> dict[str, float]:
    """Roda as etapas em ordem e devolve {etapa: segundos}. Para no primeiro erro.

    `reextrair_hoje`: as APIs são consultadas de novo mesmo que já tenham sido hoje.
    `progresso`: chamado no início e no fim de cada etapa (usado pelo painel).
    """
    execucao_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    selecionadas = selecionar_etapas(etapas, sem_extracao)
    logger.info(
        "=== Pipeline %s: início (%s etapas: %s)", execucao_id, len(selecionadas), selecionadas
    )

    inicio_total = time.perf_counter()
    duracoes: dict[str, float] = {}
    for posicao, nome in enumerate(selecionadas, start=1):
        logger.info("=== [%s/%s] %s", posicao, len(selecionadas), nome)
        if progresso:
            progresso(posicao, len(selecionadas), nome, "inicio")
        inicio = time.perf_counter()
        try:
            funcao_da_etapa(nome, reextrair_hoje)()
        except Exception:
            logger.exception(
                "=== Pipeline %s: FALHOU na etapa %s; etapas seguintes não executadas: %s",
                execucao_id,
                nome,
                selecionadas[posicao:],
            )
            raise
        duracoes[nome] = time.perf_counter() - inicio
        logger.info("=== [%s/%s] %s: OK (%.1fs)", posicao, len(selecionadas), nome, duracoes[nome])
        if progresso:
            progresso(posicao, len(selecionadas), nome, "fim")

    logger.info(
        "=== Pipeline %s: concluído com sucesso (%.1fs)",
        execucao_id,
        time.perf_counter() - inicio_total,
    )
    return duracoes


def main() -> None:
    parser = argparse.ArgumentParser(description="Roda o pipeline ETL de ponta a ponta.")
    parser.add_argument("--etapas", nargs="+", choices=list(ETAPAS), help="só estas etapas")
    parser.add_argument(
        "--sem-extracao", action="store_true", help="não chama as fontes; usa o raw já baixado"
    )
    parser.add_argument(
        "--reextrair-hoje",
        action="store_true",
        help="consulta as APIs de novo mesmo que já tenham sido consultadas hoje",
    )
    args = parser.parse_args()

    configurar_logging()
    try:
        executar(args.etapas, args.sem_extracao, args.reextrair_hoje)
    except Exception:
        sys.exit(1)


if __name__ == "__main__":
    main()
