"""Leitura de arquivos .sql do projeto, com parâmetros no formato {{nome}}."""

import re
from pathlib import Path

PADRAO_PARAMETRO = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def arquivos_sql(pasta: Path) -> list[Path]:
    """Arquivos .sql da pasta em ordem de nome (01_, 02_...)."""
    return sorted(pasta.glob("*.sql"))


def ler_sql(arquivo: Path, parametros: dict[str, str] | None = None) -> str:
    """Lê o SQL e substitui os {{parametros}}. Falha se algum ficar sem valor."""
    parametros = parametros or {}
    texto = arquivo.read_text(encoding="utf-8")

    faltando = set(PADRAO_PARAMETRO.findall(texto)) - parametros.keys()
    if faltando:
        raise KeyError(f"{arquivo.name}: parâmetros sem valor: {sorted(faltando)}")

    return PADRAO_PARAMETRO.sub(lambda m: parametros[m.group(1)], texto)
