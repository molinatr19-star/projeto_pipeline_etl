"""Extração de séries temporais da API SGS do Banco Central do Brasil.

Etapa de EXTRAÇÃO apenas: salva os dados como vieram da API em
data/raw/bcb_sgs/data_extracao=AAAA-MM-DD/, sem transformar valores.

Regras da API conferidas em 2026-11-10:
- Endpoint: {url_base}?formato=json&dataInicial=dd/mm/aaaa&dataFinal=dd/mm/aaaa
- Séries diárias exigem dataInicial e aceitam janela de no máximo 10 anos.
- Resposta: lista de {"data": "dd/mm/aaaa", "valor": "texto"}.
- HTTP 404 com "Value(s) not found" = janela sem dados (não é erro).
- HTTP 404 com "A serie nao existe" = código de série inválido (é erro).
- HTTP 304 sem corpo, mesmo sem cabeçalho condicional: falha do cache do servidor
  para aquela URL exata (dura até 15 min). Contorno: repetir com dataFinal um dia
  depois e descartar registros posteriores ao fim pedido. Se a janela já está no
  limite de 10 anos (estender estouraria o limite), ela é dividida em duas.

Modo incremental (padrão): cada série é extraída a partir da última data já presente
no raw menos `sobreposicao_dias` (para pegar revisões). Sem raw anterior, ou com
--completo, extrai desde `data_inicial_padrao`.

Uso:
    python -m pipeline_etl.extracao.bcb_sgs
    python -m pipeline_etl.extracao.bcb_sgs --series 433 --data-inicial 2020-01-01
    python -m pipeline_etl.extracao.bcb_sgs --completo
"""

import argparse
import json
import logging
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import requests

from pipeline_etl.utils.caminhos import caminho_projeto
from pipeline_etl.utils.configuracao import carregar_config, config_fonte
from pipeline_etl.utils.log import configurar_logging

NOME_FONTE = "bcb_sgs"
STATUS_TEMPORARIOS = {429, 500, 502, 503, 504}

logger = logging.getLogger(__name__)


class SerieInexistenteError(Exception):
    """O código de série informado não existe no SGS."""


def somar_anos(dia: date, anos: int) -> date:
    """Soma anos a uma data; 29/02 vira 28/02 quando o ano de destino não é bissexto."""
    try:
        return dia.replace(year=dia.year + anos)
    except ValueError:
        return dia.replace(year=dia.year + anos, day=28)


def gerar_janelas(inicio: date, fim: date, anos: int) -> list[tuple[date, date]]:
    """Divide o período em janelas consecutivas de no máximo `anos` anos (limite da API)."""
    if inicio > fim:
        raise ValueError(f"Data inicial {inicio} é posterior à data final {fim}")

    janelas = []
    atual = inicio
    while atual <= fim:
        fim_janela = min(somar_anos(atual, anos) - timedelta(days=1), fim)
        janelas.append((atual, fim_janela))
        atual = fim_janela + timedelta(days=1)
    return janelas


def filtrar_ate(registros: list[dict[str, str]], fim: date) -> list[dict[str, str]]:
    """Mantém só os registros com data até `fim` (data no formato dd/mm/aaaa da API)."""
    return [r for r in registros if datetime.strptime(r["data"], "%d/%m/%Y").date() <= fim]


def pode_estender(inicio: date, novo_fim: date, anos: int) -> bool:
    """A janela [inicio, novo_fim] ainda cabe no limite de `anos` anos da API?"""
    return novo_fim < somar_anos(inicio, anos)


def requisitar_janela(
    sessao: requests.Session,
    codigo: int,
    inicio: date,
    fim: date,
    cfg: dict[str, Any],
) -> list[dict[str, str]]:
    """Faz uma requisição para uma janela, com novas tentativas em erros temporários."""
    url = cfg["url_base"].format(codigo=codigo)
    espera = cfg["espera_inicial_s"]
    dias_extras = 0  # usado só no contorno do HTTP 304

    for tentativa in range(1, cfg["tentativas"] + 1):
        parametros = {
            "formato": "json",
            "dataInicial": inicio.strftime("%d/%m/%Y"),
            "dataFinal": (fim + timedelta(days=dias_extras)).strftime("%d/%m/%Y"),
        }
        try:
            resposta = sessao.get(url, params=parametros, timeout=cfg["timeout_s"])
        except (requests.ConnectionError, requests.Timeout) as erro:
            motivo = f"falha de conexão: {erro.__class__.__name__}"
        else:
            status = resposta.status_code
            if status == 200:
                registros = resposta.json()
                return filtrar_ate(registros, fim) if dias_extras else registros
            if status == 404:
                if "nao existe" in resposta.text.lower():
                    raise SerieInexistenteError(f"Série {codigo} não existe no SGS")
                return []  # janela sem dados
            if status == 304:
                novo_fim = fim + timedelta(days=dias_extras + 1)
                if not pode_estender(inicio, novo_fim, cfg["janela_max_anos"]) and inicio < fim:
                    meio = inicio + (fim - inicio) // 2
                    logger.warning(
                        "Série %s: HTTP 304 com a janela no limite; dividindo %s a %s em duas",
                        codigo,
                        inicio,
                        fim,
                    )
                    return requisitar_janela(sessao, codigo, inicio, meio, cfg) + (
                        requisitar_janela(sessao, codigo, meio + timedelta(days=1), fim, cfg)
                    )
                motivo = "HTTP 304 sem corpo (cache do servidor); dataFinal será estendida"
                dias_extras += 1
            elif status in STATUS_TEMPORARIOS:
                motivo = f"HTTP {status}"
            else:
                raise RuntimeError(f"Série {codigo}: resposta inesperada HTTP {status}")

        if tentativa == cfg["tentativas"]:
            raise RuntimeError(
                f"Série {codigo}: {motivo} após {tentativa} tentativas ({inicio} a {fim})"
            )
        logger.warning(
            "Série %s: %s. Tentativa %s/%s, nova tentativa em %ss",
            codigo,
            motivo,
            tentativa,
            cfg["tentativas"],
            espera,
        )
        time.sleep(espera)
        espera *= 2

    return []  # inalcançável; mantém o type checker satisfeito


def extrair_serie(
    sessao: requests.Session,
    codigo: int,
    inicio: date,
    fim: date,
    cfg: dict[str, Any],
) -> list[dict[str, str]]:
    """Extrai todas as janelas de uma série e devolve os registros na ordem da API."""
    registros: list[dict[str, str]] = []
    janelas = gerar_janelas(inicio, fim, cfg["janela_max_anos"])
    for indice, (ini_janela, fim_janela) in enumerate(janelas):
        if indice > 0:
            time.sleep(cfg["pausa_entre_chamadas_s"])
        lote = requisitar_janela(sessao, codigo, ini_janela, fim_janela, cfg)
        logger.info("Série %s: %s a %s -> %s registros", codigo, ini_janela, fim_janela, len(lote))
        registros.extend(lote)
    return registros


def pasta_particao(data_extracao: date) -> Path:
    """Pasta da partição raw do dia: data/raw/bcb_sgs/data_extracao=AAAA-MM-DD/."""
    raw = carregar_config()["caminhos"]["raw"]
    return caminho_projeto(raw, NOME_FONTE, f"data_extracao={data_extracao.isoformat()}")


def arquivo_raw(codigo: int, data_extracao: date) -> Path:
    """Caminho do arquivo raw de uma série em uma data de extração."""
    return pasta_particao(data_extracao) / f"serie_{codigo}.json"


def ultima_data_raw(codigo: int) -> date | None:
    """Maior data já extraída da série, somando todas as partições do raw."""
    raw = caminho_projeto(carregar_config()["caminhos"]["raw"], NOME_FONTE)
    ultima = None
    for arquivo in raw.glob(f"data_extracao=*/serie_{codigo}.json"):
        for registro in json.loads(arquivo.read_text(encoding="utf-8")):
            dia = datetime.strptime(registro["data"], "%d/%m/%Y").date()
            ultima = dia if ultima is None or dia > ultima else ultima
    return ultima


def inicio_da_extracao(ultima: date | None, inicio_padrao: date, sobreposicao_dias: int) -> date:
    """Incremental: última data menos a sobreposição (nunca antes do início padrão)."""
    if ultima is None:
        return inicio_padrao
    return max(inicio_padrao, ultima - timedelta(days=sobreposicao_dias))


def salvar_raw(
    registros: list[dict[str, str]],
    serie: dict[str, Any],
    inicio: date,
    fim: date,
    data_extracao: date,
    modo: str = "completo",
) -> Path:
    """Grava os registros como vieram, mais um arquivo de metadados.

    Não sobrescreve: falha se a série já foi gravada na mesma data de extração.
    """
    arquivo_dados = arquivo_raw(serie["codigo"], data_extracao)
    if arquivo_dados.exists():
        raise FileExistsError(f"{arquivo_dados} já existe; raw não é sobrescrito")

    pasta = arquivo_dados.parent
    pasta.mkdir(parents=True, exist_ok=True)
    metadados = {
        "fonte": NOME_FONTE,
        "codigo_serie": serie["codigo"],
        "nome_serie": serie["nome"],
        "periodicidade": serie["periodicidade"],
        "unidade": serie["unidade"],
        "periodo_solicitado": [inicio.isoformat(), fim.isoformat()],
        "modo": modo,
        "quantidade_registros": len(registros),
        "extraido_em": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    arquivo_dados.write_text(json.dumps(registros, ensure_ascii=False), encoding="utf-8")
    (pasta / f"serie_{serie['codigo']}.meta.json").write_text(
        json.dumps(metadados, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return arquivo_dados


def executar(
    codigos: list[int] | None = None,
    inicio: date | None = None,
    fim: date | None = None,
    completo: bool = False,
) -> dict[int, int]:
    """Extrai as séries configuradas e devolve {codigo: quantidade_de_registros}.

    Sem `inicio` explícito, usa o modo do config: incremental (a partir do raw já
    existente) ou completo. `completo=True` força o histórico inteiro.
    """
    cfg = config_fonte(NOME_FONTE)
    inicio_padrao = date.fromisoformat(cfg["data_inicial_padrao"])
    incremental = inicio is None and not completo and cfg.get("modo") == "incremental"
    fim = fim or date.today()
    hoje = date.today()

    series = cfg["series"]
    if codigos:
        series = [s for s in series if s["codigo"] in codigos]
        faltando = set(codigos) - {s["codigo"] for s in series}
        if faltando:
            raise ValueError(f"Códigos fora de config/pipeline.yaml: {sorted(faltando)}")

    logger.info(
        "Início da extração %s: %s séries, modo %s, até %s",
        NOME_FONTE,
        len(series),
        "incremental" if incremental else "completo",
        fim,
    )
    resumo: dict[int, int] = {}
    with requests.Session() as sessao:
        sessao.headers["Accept"] = "application/json"
        for serie in series:
            if arquivo_raw(serie["codigo"], hoje).exists():
                logger.info(
                    "Série %s (%s): já extraída hoje; pulada (raw não é sobrescrito)",
                    serie["codigo"],
                    serie["nome"],
                )
                continue
            inicio_serie = time.perf_counter()
            if incremental:
                inicio_desta = inicio_da_extracao(
                    ultima_data_raw(serie["codigo"]), inicio_padrao, cfg["sobreposicao_dias"]
                )
            else:
                inicio_desta = inicio or inicio_padrao
            registros = extrair_serie(sessao, serie["codigo"], inicio_desta, fim, cfg)
            arquivo = salvar_raw(
                registros,
                serie,
                inicio_desta,
                fim,
                hoje,
                "incremental" if incremental else "completo",
            )
            resumo[serie["codigo"]] = len(registros)
            logger.info(
                "Série %s (%s): %s registros em %.1fs -> %s",
                serie["codigo"],
                serie["nome"],
                len(registros),
                time.perf_counter() - inicio_serie,
                arquivo.relative_to(caminho_projeto()),
            )
    logger.info("Fim da extração %s: %s", NOME_FONTE, resumo)
    return resumo


def main() -> None:
    """Ponto de entrada de linha de comando."""
    parser = argparse.ArgumentParser(description="Extrai séries do SGS/BCB para data/raw.")
    parser.add_argument("--series", type=int, nargs="+", help="códigos das séries (padrão: todas)")
    parser.add_argument("--data-inicial", type=date.fromisoformat, help="AAAA-MM-DD")
    parser.add_argument("--data-final", type=date.fromisoformat, help="AAAA-MM-DD")
    parser.add_argument("--completo", action="store_true", help="ignora o raw e baixa tudo")
    args = parser.parse_args()

    configurar_logging()
    executar(args.series, args.data_inicial, args.data_final, args.completo)


if __name__ == "__main__":
    main()
