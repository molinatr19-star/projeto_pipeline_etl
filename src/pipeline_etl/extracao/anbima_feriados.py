"""Extração da planilha de feriados nacionais da ANBIMA (fonte em ARQUIVO).

Etapa de EXTRAÇÃO apenas: baixa o .xls e salva os bytes como vieram em
data/raw/anbima_feriados/data_extracao=AAAA-MM-DD/, com um .meta.json ao lado.

Formato conferido em 2026-11-10: planilha Excel 97-2003 (.xls), aba "Feriados",
colunas Data | Dia da Semana | Feriado, de 2001 a 2099, com notas no rodapé.

Uso:
    python -m pipeline_etl.extracao.anbima_feriados
"""

import hashlib
import json
import logging
from datetime import date, datetime
from pathlib import Path

from pipeline_etl.utils.caminhos import caminho_projeto
from pipeline_etl.utils.configuracao import carregar_config, config_fonte
from pipeline_etl.utils.http import baixar
from pipeline_etl.utils.log import configurar_logging

NOME_FONTE = "anbima_feriados"
# Assinatura dos arquivos Office antigos (.xls); evita salvar uma página de erro em HTML
ASSINATURA_XLS = bytes.fromhex("d0cf11e0a1b11ae1")

logger = logging.getLogger(__name__)


def pasta_particao(data_extracao: date) -> Path:
    raw = carregar_config()["caminhos"]["raw"]
    return caminho_projeto(raw, NOME_FONTE, f"data_extracao={data_extracao.isoformat()}")


def validar_xls(conteudo: bytes) -> None:
    """Garante que o download é mesmo uma planilha .xls."""
    if not conteudo.startswith(ASSINATURA_XLS):
        raise ValueError(f"Conteúdo baixado não é .xls (início: {conteudo[:20]!r})")


def executar() -> Path:
    """Baixa a planilha, se ainda não foi baixada hoje, e devolve o caminho do raw."""
    cfg = config_fonte(NOME_FONTE)
    hoje = date.today()
    arquivo = pasta_particao(hoje) / cfg["arquivo_raw"]
    if arquivo.exists():
        logger.info("%s: já extraído hoje; pulado (raw não é sobrescrito)", NOME_FONTE)
        return arquivo

    logger.info("Início da extração %s: %s", NOME_FONTE, cfg["url"])
    resposta = baixar(cfg["url"], cfg)
    validar_xls(resposta.content)

    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_bytes(resposta.content)
    metadados = {
        "fonte": NOME_FONTE,
        "url": cfg["url"],
        "bytes": len(resposta.content),
        "sha256": hashlib.sha256(resposta.content).hexdigest(),
        "last_modified_servidor": resposta.headers.get("Last-Modified"),
        "extraido_em": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    arquivo.with_name(arquivo.name + ".meta.json").write_text(
        json.dumps(metadados, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info(
        "Fim da extração %s: %s bytes (arquivo modificado no servidor em %s) -> %s",
        NOME_FONTE,
        metadados["bytes"],
        metadados["last_modified_servidor"],
        arquivo.relative_to(caminho_projeto()),
    )
    return arquivo


def main() -> None:
    configurar_logging()
    executar()


if __name__ == "__main__":
    main()
