"""Testes da fonte de feriados (ANBIMA) e do download HTTP. Não acessam a internet."""

from datetime import date, datetime
from unittest.mock import MagicMock

import pandas as pd
import pytest

from pipeline_etl.extracao.anbima_feriados import validar_xls
from pipeline_etl.orquestracao.staging_anbima_feriados import checagens_feriados
from pipeline_etl.transformacao.anbima_feriados import DIAS_SEMANA, padronizar_feriados
from pipeline_etl.utils.http import baixar

CARREGADO_EM = pd.Timestamp("2026-11-10 13:00:00", tz="America/Sao_Paulo")
CFG_HTTP = {"timeout_s": 1, "tentativas": 3, "espera_inicial_s": 0}


def _planilha(linhas: list[tuple]) -> pd.DataFrame:
    """Simula a planilha lida: Data como datetime (ou texto no rodapé)."""
    return pd.DataFrame(linhas, columns=["data", "dia_semana_fonte", "nome_feriado"])


PLANILHA = _planilha(
    [
        (datetime(2079, 4, 21), "sexta-feira", "Tiradentes"),
        (datetime(2079, 4, 21), "sexta-feira", "Paixão de Cristo"),
        (datetime(2025, 12, 25), "quinta-feira", " Natal "),
        ("Fonte: ANBIMA", None, None),
        (None, None, None),
        ("1) Nota de rodapé", None, None),
    ]
)


def test_padronizar_remove_rodape_e_limpa_texto():
    resultado = padronizar_feriados(PLANILHA, date(2026, 11, 10), CARREGADO_EM)
    assert resultado.linhas_rodape == 3
    assert resultado.linhas_feriado == 3
    assert resultado.dados["data"].tolist() == [date(2025, 12, 25), date(2079, 4, 21)]
    assert resultado.dados["nome_feriado"].iloc[0] == "Natal"


def test_dois_feriados_na_mesma_data_viram_uma_linha():
    resultado = padronizar_feriados(PLANILHA, date(2026, 11, 10), CARREGADO_EM)
    assert resultado.datas_com_mais_de_um_feriado == 1
    assert resultado.dados["nome_feriado"].iloc[1] == "Paixão de Cristo / Tiradentes"


def test_dia_da_semana_divergente_e_contado():
    planilha = _planilha([(datetime(2025, 12, 25), "sexta-feira", "Natal")])  # foi quinta
    assert (
        padronizar_feriados(planilha, date(2026, 11, 10), CARREGADO_EM).divergencias_dia_semana == 1
    )


def test_checagens_aprovam_planilha_valida_e_reprovam_ano_incompleto():
    dias = [datetime(2025, 1, d) for d in range(1, 11)]  # 10 feriados em 2025
    linhas = [(dia, DIAS_SEMANA[dia.weekday()], f"Feriado {dia.day}") for dia in dias]
    resultado = padronizar_feriados(_planilha(linhas), date(2026, 11, 10), CARREGADO_EM)
    assert all(c.ok for c in checagens_feriados(resultado, {"min_feriados_por_ano": 10}))
    assert not all(c.ok for c in checagens_feriados(resultado, {"min_feriados_por_ano": 11}))


def test_validar_xls_recusa_pagina_html():
    validar_xls(bytes.fromhex("d0cf11e0a1b11ae1") + b"resto")
    with pytest.raises(ValueError):
        validar_xls(b"<!DOCTYPE html><html>erro</html>")


def test_baixar_repete_erro_temporario_e_falha_em_erro_definitivo():
    sessao = MagicMock()
    sessao.get.side_effect = [MagicMock(status_code=503), MagicMock(status_code=200)]
    assert baixar("http://x", CFG_HTTP, sessao).status_code == 200
    assert sessao.get.call_count == 2

    sessao = MagicMock()
    sessao.get.return_value = MagicMock(status_code=404)
    with pytest.raises(RuntimeError, match="404"):
        baixar("http://x", CFG_HTTP, sessao)
    assert sessao.get.call_count == 1
