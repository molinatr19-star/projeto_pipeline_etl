"""Caminhos do projeto, sempre relativos à raiz."""

from pathlib import Path

# src/pipeline_etl/utils/caminhos.py -> sobe 3 níveis até a raiz do projeto
RAIZ_PROJETO = Path(__file__).resolve().parents[3]


def caminho_projeto(*partes: str) -> Path:
    """Monta um caminho a partir da raiz do projeto."""
    return RAIZ_PROJETO.joinpath(*partes)
