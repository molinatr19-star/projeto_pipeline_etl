"""Testes do orquestrador único, com etapas falsas (não roda o pipeline real)."""

import pytest

from pipeline_etl.orquestracao import pipeline


@pytest.fixture
def etapas_falsas(monkeypatch):
    chamadas: list[str] = []
    falsas = {nome: (lambda n=nome: chamadas.append(n)) for nome in pipeline.ETAPAS}
    monkeypatch.setattr(pipeline, "ETAPAS", falsas)
    return falsas, chamadas


def test_roda_todas_as_etapas_na_ordem(etapas_falsas):
    _, chamadas = etapas_falsas
    duracoes = pipeline.executar()
    assert chamadas == [
        "extracao_bcb_sgs",
        "extracao_anbima_feriados",
        "extracao_bcb_focus",
        "staging_bcb_sgs",
        "staging_anbima_feriados",
        "staging_bcb_focus",
        "warehouse",
        "exportacao",
    ]
    assert list(duracoes) == chamadas


def test_sem_extracao_pula_as_fontes(etapas_falsas):
    _, chamadas = etapas_falsas
    pipeline.executar(sem_extracao=True)
    assert "extracao_bcb_sgs" not in chamadas and chamadas[0] == "staging_bcb_sgs"


def test_etapas_escolhidas_seguem_a_ordem_oficial(etapas_falsas):
    _, chamadas = etapas_falsas
    pipeline.executar(etapas=["exportacao", "warehouse"])
    assert chamadas == ["warehouse", "exportacao"]


def test_para_na_primeira_falha(etapas_falsas):
    falsas, chamadas = etapas_falsas

    def falha():
        raise RuntimeError("erro simulado")

    falsas["staging_bcb_sgs"] = falha
    with pytest.raises(RuntimeError, match="simulado"):
        pipeline.executar()
    assert chamadas == ["extracao_bcb_sgs", "extracao_anbima_feriados", "extracao_bcb_focus"]


def test_etapa_desconhecida_gera_erro():
    with pytest.raises(ValueError):
        pipeline.selecionar_etapas(["nao_existe"], sem_extracao=False)
