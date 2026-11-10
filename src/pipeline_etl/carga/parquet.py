"""Gravação de DataFrames em Parquet.

Etapa de CARGA: só grava, sem regra de negócio.
"""

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def salvar_parquet(df: pd.DataFrame, caminho: Path) -> Path:
    """Grava o DataFrame substituindo o arquivo de forma atômica.

    Escreve primeiro em um .tmp e só então troca pelo definitivo, para que uma
    falha no meio da gravação nunca deixe um Parquet corrompido no lugar do antigo.
    """
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_name(caminho.name + ".tmp")
    df.to_parquet(temporario, index=False)
    temporario.replace(caminho)
    logger.info("Gravado %s/%s (%s linhas)", caminho.parent.name, caminho.name, len(df))
    return caminho
