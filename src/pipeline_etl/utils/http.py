"""Download HTTP com timeout e novas tentativas em erros temporários."""

import logging
import time
from typing import Any

import requests

STATUS_TEMPORARIOS = {429, 500, 502, 503, 504}

logger = logging.getLogger(__name__)


def baixar(
    url: str, cfg: dict[str, Any], sessao: requests.Session | None = None
) -> requests.Response:
    """GET com até cfg["tentativas"] tentativas e espera crescente (cfg["espera_inicial_s"]).

    Repete em falha de conexão, timeout e HTTP 429/5xx. Falha direto em outros erros.
    """
    sessao = sessao or requests.Session()
    espera = cfg["espera_inicial_s"]
    for tentativa in range(1, cfg["tentativas"] + 1):
        try:
            resposta = sessao.get(url, timeout=cfg["timeout_s"])
        except (requests.ConnectionError, requests.Timeout) as erro:
            motivo = f"falha de conexão: {erro.__class__.__name__}"
        else:
            if resposta.status_code == 200:
                return resposta
            if resposta.status_code not in STATUS_TEMPORARIOS:
                raise RuntimeError(f"{url}: resposta inesperada HTTP {resposta.status_code}")
            motivo = f"HTTP {resposta.status_code}"

        if tentativa == cfg["tentativas"]:
            raise RuntimeError(f"{url}: {motivo} após {tentativa} tentativas")
        logger.warning(
            "%s: %s. Tentativa %s/%s, nova em %ss",
            url,
            motivo,
            tentativa,
            cfg["tentativas"],
            espera,
        )
        time.sleep(espera)
        espera *= 2

    raise AssertionError("inalcançável")
