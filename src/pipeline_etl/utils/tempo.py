"""Datas e horas com fuso, com tipo garantido (sem NaT) para o verificador de tipos."""

from typing import Any

import pandas as pd


def como_timestamp(valor: Any) -> pd.Timestamp:
    """Converte para Timestamp e falha se o resultado for NaT (data ausente)."""
    convertido = pd.Timestamp(valor)
    if not isinstance(convertido, pd.Timestamp):  # pd.NaT não é Timestamp
        raise ValueError(f"Data inválida: {valor!r}")
    return convertido


def agora_no_fuso(fuso: str) -> pd.Timestamp:
    """Agora no fuso informado, sem frações de segundo (usado em `carregado_em`)."""
    return como_timestamp(pd.Timestamp.now(tz=fuso).floor("s"))
