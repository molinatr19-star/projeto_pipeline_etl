"""Testes do extrator SGS/BCB. Não chamam a API real."""

from datetime import date
from unittest.mock import MagicMock

import pytest

from pipeline_etl.extracao.bcb_sgs import (
    SerieInexistenteError,
    gerar_janelas,
    requisitar_janela,
)

CFG = {
    "url_base": "https://exemplo/bcdata.sgs.{codigo}/dados",
    "timeout_s": 1,
    "tentativas": 3,
    "espera_inicial_s": 0,
    "pausa_entre_chamadas_s": 0,
    "janela_max_anos": 10,
}


def _resposta(status: int, corpo: object = None, texto: str = "") -> MagicMock:
    resposta = MagicMock(status_code=status, text=texto)
    resposta.json.return_value = corpo
    return resposta


def test_periodo_curto_gera_uma_janela():
    assert gerar_janelas(date(2024, 1, 1), date(2024, 12, 31), 10) == [
        (date(2024, 1, 1), date(2024, 12, 31))
    ]


def test_periodo_longo_e_dividido_sem_lacunas_nem_sobreposicao():
    janelas = gerar_janelas(date(2000, 1, 1), date(2026, 11, 10), 10)
    assert janelas[0] == (date(2000, 1, 1), date(2009, 12, 31))
    assert janelas[-1][1] == date(2026, 11, 10)
    for (_, fim_anterior), (inicio_seguinte, _) in zip(janelas, janelas[1:], strict=False):
        assert (inicio_seguinte - fim_anterior).days == 1


def test_inicio_em_29_de_fevereiro():
    assert gerar_janelas(date(2016, 2, 29), date(2030, 1, 1), 10)[0][1] == date(2026, 2, 27)


def test_data_inicial_maior_que_final_gera_erro():
    with pytest.raises(ValueError):
        gerar_janelas(date(2025, 1, 2), date(2025, 1, 1), 10)


def test_resposta_200_devolve_registros():
    sessao = MagicMock()
    sessao.get.return_value = _resposta(200, [{"data": "01/01/2026", "valor": "0.33"}])
    assert requisitar_janela(sessao, 433, date(2026, 1, 1), date(2026, 1, 31), CFG) == [
        {"data": "01/01/2026", "valor": "0.33"}
    ]


def test_404_sem_dados_devolve_lista_vazia():
    sessao = MagicMock()
    sessao.get.return_value = _resposta(404, texto='{"erro": "Value(s) not found"}')
    assert requisitar_janela(sessao, 433, date(1900, 1, 1), date(1900, 12, 31), CFG) == []


def test_404_serie_inexistente_gera_erro():
    sessao = MagicMock()
    sessao.get.return_value = _resposta(404, texto="A serie nao existe!")
    with pytest.raises(SerieInexistenteError):
        requisitar_janela(sessao, 99999999, date(2026, 1, 1), date(2026, 1, 31), CFG)


def test_erro_temporario_e_repetido_ate_dar_certo():
    sessao = MagicMock()
    sessao.get.side_effect = [_resposta(503), _resposta(200, [])]
    assert requisitar_janela(sessao, 1, date(2026, 1, 1), date(2026, 1, 31), CFG) == []
    assert sessao.get.call_count == 2


def test_304_estende_data_final_e_filtra_registros_extras():
    sessao = MagicMock()
    sessao.get.side_effect = [
        _resposta(304),
        _resposta(
            200,
            [
                {"data": "30/01/2026", "valor": "5.1"},
                {"data": "01/02/2026", "valor": "5.2"},  # fora da janela pedida
            ],
        ),
    ]
    registros = requisitar_janela(sessao, 1, date(2026, 1, 1), date(2026, 1, 31), CFG)
    assert registros == [{"data": "30/01/2026", "valor": "5.1"}]
    assert sessao.get.call_args.kwargs["params"]["dataFinal"] == "01/02/2026"


def test_status_inesperado_gera_erro_sem_repetir():
    sessao = MagicMock()
    sessao.get.return_value = _resposta(400)
    with pytest.raises(RuntimeError, match="inesperada"):
        requisitar_janela(sessao, 1, date(2026, 1, 1), date(2026, 1, 31), CFG)
    assert sessao.get.call_count == 1


def test_erro_temporario_persistente_esgota_tentativas():
    sessao = MagicMock()
    sessao.get.return_value = _resposta(503)
    with pytest.raises(RuntimeError):
        requisitar_janela(sessao, 1, date(2026, 1, 1), date(2026, 1, 31), CFG)
    assert sessao.get.call_count == CFG["tentativas"]
