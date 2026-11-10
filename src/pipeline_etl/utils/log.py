"""Configuração de logging: saída no terminal e em logs/pipeline_AAAA-MM-DD.log."""

import logging
from datetime import date

from pipeline_etl.utils.caminhos import caminho_projeto

FORMATO = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"


def configurar_logging(nivel: int = logging.INFO) -> None:
    """Configura o logger raiz uma única vez por execução."""
    raiz = logging.getLogger()
    if raiz.handlers:
        return

    pasta_logs = caminho_projeto("logs")
    pasta_logs.mkdir(exist_ok=True)
    arquivo = pasta_logs / f"pipeline_{date.today().isoformat()}.log"

    formatador = logging.Formatter(FORMATO)
    for handler in (logging.StreamHandler(), logging.FileHandler(arquivo, encoding="utf-8")):
        handler.setFormatter(formatador)
        raiz.addHandler(handler)
    raiz.setLevel(nivel)
