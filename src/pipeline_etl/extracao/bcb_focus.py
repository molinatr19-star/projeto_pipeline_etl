"""Extração das expectativas de mercado para o IPCA dos próximos 12 meses (Boletim Focus).

Etapa de EXTRAÇÃO apenas: salva a lista `value` da API OData como veio em
data/raw/bcb_focus/data_extracao=AAAA-MM-DD/ipca_12m.json, com um .meta.json ao lado.

Regras da API conferidas em 2026-11-10:
- Endpoint OData (Olinda): .../ExpectativasMercadoInflacao12Meses?$filter=...&$format=json
- Os espaços da query precisam ir como %20. Com "+" (padrão do `requests`), a API
  responde HTTP 400 "The types 'Edm.Boolean' and 'Edm.String' are not compatible".
- Campos usados: Data (dia da pesquisa), Mediana, Media, DesvioPadrao, numeroRespondentes.
- Filtro do projeto: IPCA, série suavizada (Suavizada = 'S'), baseCalculo = 0.

Uso:
    python -m pipeline_etl.extracao.bcb_focus
    python -m pipeline_etl.extracao.bcb_focus --completo
"""

import argparse
import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

from pipeline_etl.utils.caminhos import caminho_projeto
from pipeline_etl.utils.configuracao import carregar_config, config_fonte
from pipeline_etl.utils.http import baixar
from pipeline_etl.utils.log import configurar_logging
from pipeline_etl.utils.raw import arquivo_para_gravar, caminho_meta, listar_arquivos

NOME_FONTE = "bcb_focus"
NOME_BASE = "ipca_12m"  # arquivo do dia: ipca_12m.json; novas versões: ipca_12m__HHMMSS.json

logger = logging.getLogger(__name__)


def montar_url(cfg: dict[str, Any], inicio: date) -> str:
    """URL OData com a query codificada em %20 (nunca "+")."""
    parametros = {
        "$filter": f"{cfg['filtro']} and Data ge '{inicio.isoformat()}'",
        "$select": ",".join(cfg["campos"]),
        "$orderby": "Data",
        "$format": "json",
    }
    seguros = "'(),"  # mantidos literais; espaço vira %20
    query = "&".join(f"{chave}={quote(valor, safe=seguros)}" for chave, valor in parametros.items())
    return f"{cfg['url']}?{query}"


def pasta_fonte() -> Path:
    return caminho_projeto(carregar_config()["caminhos"]["raw"], NOME_FONTE)


def pasta_particao(data_extracao: date) -> Path:
    return pasta_fonte() / f"data_extracao={data_extracao.isoformat()}"


def ultima_data_raw() -> date | None:
    """Maior data de pesquisa já presente no raw (todas as partições)."""
    datas = [
        date.fromisoformat(registro["Data"])
        for arquivo in listar_arquivos(pasta_fonte(), NOME_BASE)
        for registro in json.loads(arquivo.read_text(encoding="utf-8"))
    ]
    return max(datas) if datas else None


def executar(completo: bool = False, reextrair_hoje: bool = False) -> int:
    """Extrai as expectativas e devolve a quantidade de registros gravados.

    `reextrair_hoje=True` busca de novo mesmo que já tenha extraído hoje (nova versão
    do arquivo do dia; o raw nunca é sobrescrito).
    """
    cfg = config_fonte(NOME_FONTE)
    hoje = date.today()
    destino = arquivo_para_gravar(pasta_particao(hoje), NOME_BASE, reextrair_hoje)
    if destino is None:
        logger.info("%s: já extraído hoje; pulado (raw não é sobrescrito)", NOME_FONTE)
        return 0

    inicio_padrao = date.fromisoformat(cfg["data_inicial_padrao"])
    ultima = None if completo or cfg.get("modo") != "incremental" else ultima_data_raw()
    inicio = (
        inicio_padrao
        if ultima is None
        else max(inicio_padrao, ultima - timedelta(days=cfg["sobreposicao_dias"]))
    )
    url = montar_url(cfg, inicio)
    logger.info("Início da extração %s a partir de %s", NOME_FONTE, inicio)

    corpo = baixar(url, cfg).json()
    if "value" not in corpo:
        raise ValueError(f"{NOME_FONTE}: resposta sem a lista 'value': {str(corpo)[:200]}")
    registros = corpo["value"]

    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(registros, ensure_ascii=False), encoding="utf-8")
    metadados = {
        "fonte": NOME_FONTE,
        "url": url,
        "inicio_solicitado": inicio.isoformat(),
        "modo": "completo" if ultima is None else "incremental",
        "quantidade_registros": len(registros),
        "extraido_em": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    caminho_meta(destino).write_text(
        json.dumps(metadados, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info(
        "Fim da extração %s: %s registros -> %s",
        NOME_FONTE,
        len(registros),
        destino.relative_to(caminho_projeto()),
    )
    return len(registros)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extrai expectativas do Focus para data/raw.")
    parser.add_argument("--completo", action="store_true", help="ignora o raw e baixa tudo")
    args = parser.parse_args()
    configurar_logging()
    executar(args.completo)


if __name__ == "__main__":
    main()
