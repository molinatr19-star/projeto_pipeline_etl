"""Testes da extração incremental, do contorno do HTTP 304, do Focus e da junção de partições."""

import json
from datetime import date
from unittest.mock import MagicMock
from urllib.parse import unquote

import pandas as pd
import pytest

from pipeline_etl.extracao.bcb_focus import montar_url
from pipeline_etl.extracao.bcb_sgs import inicio_da_extracao, pode_estender, requisitar_janela
from pipeline_etl.transformacao.bcb_focus import padronizar
from pipeline_etl.transformacao.bcb_sgs import transformar

CARREGADO_EM = pd.Timestamp("2026-11-10 13:00", tz="America/Sao_Paulo")
CFG_SGS = {
    "url_base": "https://exemplo/bcdata.sgs.{codigo}/dados",
    "timeout_s": 1,
    "tentativas": 3,
    "espera_inicial_s": 0,
    "pausa_entre_chamadas_s": 0,
    "janela_max_anos": 10,
}


def _resposta(status: int, corpo: object = None) -> MagicMock:
    resposta = MagicMock(status_code=status, text="")
    resposta.json.return_value = corpo
    return resposta


# ---------- incremental ----------


def test_inicio_incremental_usa_ultima_data_menos_sobreposicao():
    padrao = date(2015, 1, 1)
    assert inicio_da_extracao(None, padrao, 62) == padrao  # sem raw: histórico completo
    assert inicio_da_extracao(date(2026, 11, 9), padrao, 62) == date(2026, 9, 8)
    assert inicio_da_extracao(date(2015, 1, 20), padrao, 62) == padrao  # nunca antes do padrão


def _gravar(pasta, extracao: str, codigo: int, registros: list[dict]) -> None:
    destino = pasta / f"data_extracao={extracao}"
    destino.mkdir(parents=True, exist_ok=True)
    (destino / f"serie_{codigo}.json").write_text(json.dumps(registros), encoding="utf-8")
    meta = {"nome_serie": "dolar_venda", "unidade": "R$/US$", "periodicidade": "diaria"}
    (destino / f"serie_{codigo}.meta.json").write_text(json.dumps(meta), encoding="utf-8")


def test_staging_junta_particoes_e_vale_a_extracao_mais_recente(tmp_path):
    _gravar(
        tmp_path,
        "2026-11-09",
        1,
        [
            {"data": "05/11/2026", "valor": "5.40"},
            {"data": "06/11/2026", "valor": "5.50"},
        ],
    )
    # extração seguinte (incremental) repete 06/11 com valor revisado e traz 09/11
    _gravar(
        tmp_path,
        "2026-11-10",
        1,
        [
            {"data": "06/11/2026", "valor": "5.51"},
            {"data": "09/11/2026", "valor": "5.52"},
        ],
    )
    resultado = transformar([1], CARREGADO_EM, tmp_path)
    assert resultado.linhas_raw == 4
    assert resultado.duplicatas_removidas == 1
    dados = resultado.dados.set_index("data_referencia")
    assert list(dados.index) == [date(2026, 11, 5), date(2026, 11, 6), date(2026, 11, 9)]
    assert dados.loc[date(2026, 11, 6), "valor"] == pytest.approx(5.51)
    assert dados.loc[date(2026, 11, 6), "data_extracao"] == date(2026, 11, 10)


# ---------- HTTP 304 ----------


def test_pode_estender_respeita_limite_de_10_anos():
    assert pode_estender(date(2015, 1, 1), date(2024, 12, 31), 10)
    assert not pode_estender(date(2015, 1, 1), date(2025, 1, 1), 10)


def test_304_com_janela_no_limite_divide_em_duas():
    sessao = MagicMock()
    sessao.get.side_effect = [
        _resposta(304),
        _resposta(200, [{"data": "02/01/2015", "valor": "1"}]),
        _resposta(200, [{"data": "30/12/2024", "valor": "2"}]),
    ]
    registros = requisitar_janela(sessao, 1, date(2015, 1, 1), date(2024, 12, 31), CFG_SGS)
    assert [r["valor"] for r in registros] == ["1", "2"]
    primeira, segunda = (c.kwargs["params"] for c in sessao.get.call_args_list[1:])
    assert primeira["dataInicial"] == "01/01/2015" and segunda["dataFinal"] == "31/12/2024"
    assert primeira["dataFinal"] != segunda["dataInicial"]  # metades sem sobreposição


# ---------- Focus ----------


def test_url_do_focus_usa_porcento_20_e_nunca_mais():
    cfg = {
        "url": "https://exemplo/odata/Expectativas",
        "filtro": "Indicador eq 'IPCA' and Suavizada eq 'S'",
        "campos": ["Data", "Mediana"],
    }
    url = montar_url(cfg, date(2026, 10, 1))
    query = url.split("?", 1)[1]
    assert "+" not in query and " " not in query and "%20" in query
    assert "Data ge '2026-10-01'" in unquote(query)


def test_padronizar_focus_mantem_extracao_mais_recente_e_rejeita_invalidos():
    bruto = pd.DataFrame(
        [
            {
                "Data": "2026-11-05",
                "Indicador": "IPCA",
                "Mediana": 4.98,
                "Media": 5.0,
                "DesvioPadrao": 0.3,
                "numeroRespondentes": 130,
                "data_extracao": date(2026, 11, 9),
            },
            {
                "Data": "2026-11-05",
                "Indicador": "IPCA",
                "Mediana": 4.99,
                "Media": 5.0,
                "DesvioPadrao": 0.3,
                "numeroRespondentes": 131,
                "data_extracao": date(2026, 11, 10),
            },
            {
                "Data": "xx",
                "Indicador": "IPCA",
                "Mediana": 5.0,
                "Media": 5.0,
                "DesvioPadrao": 0.3,
                "numeroRespondentes": None,
                "data_extracao": date(2026, 11, 10),
            },
        ]
    )
    resultado = padronizar(bruto, CARREGADO_EM)
    assert len(resultado.dados) == 1 and resultado.sobreposicoes == 1
    assert len(resultado.rejeitados) == 1
    assert resultado.dados["mediana_pct"].iloc[0] == pytest.approx(4.99)
    assert resultado.linhas_raw == len(resultado.dados) + len(resultado.rejeitados) + 1
