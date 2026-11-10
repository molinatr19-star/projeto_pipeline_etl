"""Leitura da configuração do pipeline (config/pipeline.yaml e .env)."""

from functools import cache
from typing import Any

import yaml
from dotenv import load_dotenv

from pipeline_etl.utils.caminhos import caminho_projeto


@cache
def carregar_config() -> dict[str, Any]:
    """Lê o pipeline.yaml e carrega as variáveis do .env (se existir)."""
    load_dotenv(caminho_projeto(".env"))
    with caminho_projeto("config", "pipeline.yaml").open(encoding="utf-8") as arquivo:
        return yaml.safe_load(arquivo)


def config_fonte(nome_fonte: str) -> dict[str, Any]:
    """Retorna o bloco de configuração de uma fonte de dados."""
    fontes = carregar_config().get("fontes", {})
    if nome_fonte not in fontes:
        raise KeyError(f"Fonte '{nome_fonte}' não está em config/pipeline.yaml")
    return fontes[nome_fonte]
