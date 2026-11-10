"""Testes do staging do SGS/BCB, da qualidade e da gravação em Parquet."""

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from pipeline_etl.carga.parquet import salvar_parquet
from pipeline_etl.qualidade.checagens import (
    FalhaQualidadeError,
    avaliar,
    checar_chave_unica,
    checar_faixa,
    checar_sem_nulos,
)
from pipeline_etl.transformacao.bcb_sgs import (
    RawSerie,
    localizar_raw_mais_recente,
    padronizar_serie,
    remover_duplicatas,
    transformar,
)

CARREGADO_EM = pd.Timestamp("2026-11-10 13:00:00", tz="America/Sao_Paulo")
META = {"nome_serie": "dolar_venda", "unidade": "R$/US$", "periodicidade": "diaria"}


def _raw(registros: list[dict]) -> RawSerie:
    return RawSerie(1, registros, META, date(2026, 11, 10), Path("serie_1.json"))


def _gravar_raw(pasta_fonte: Path, data_extracao: str, codigo: int, registros: list[dict]):
    pasta = pasta_fonte / f"data_extracao={data_extracao}"
    pasta.mkdir(parents=True)
    (pasta / f"serie_{codigo}.json").write_text(json.dumps(registros), encoding="utf-8")
    (pasta / f"serie_{codigo}.meta.json").write_text(json.dumps(META), encoding="utf-8")


# ---------- transformação ----------


def test_padronizar_converte_tipos():
    validos, rejeitados = padronizar_serie(
        _raw([{"data": "06/11/2026", "valor": "5.5013"}]), CARREGADO_EM
    )
    linha = validos.iloc[0]
    assert linha["data_referencia"] == date(2026, 11, 6)
    assert linha["valor"] == pytest.approx(5.5013)
    assert linha["nome_serie"] == "dolar_venda"
    assert linha["data_extracao"] == date(2026, 11, 10)
    assert rejeitados.empty


def test_padronizar_separa_invalidos_com_motivo():
    registros = [
        {"data": "06/11/2026", "valor": "5.50"},
        {"data": "31/02/2026", "valor": "5.51"},
        {"data": "09/11/2026", "valor": ""},
        {"data": "10/11/2026", "valor": None},
    ]
    validos, rejeitados = padronizar_serie(_raw(registros), CARREGADO_EM)
    assert len(validos) == 1
    assert rejeitados["motivo"].tolist() == ["data_invalida", "valor_invalido", "valor_invalido"]
    assert rejeitados["data_raw"].tolist() == ["31/02/2026", "09/11/2026", "10/11/2026"]


def test_remover_duplicatas_mantem_a_ultima():
    df = pd.DataFrame({"chave": [1, 1, 2], "valor": [10, 11, 20]})
    resultado, removidas = remover_duplicatas(df, ["chave"])
    assert removidas == 1
    assert resultado["valor"].tolist() == [11, 20]


def test_localizar_raw_escolhe_particao_mais_recente(tmp_path):
    _gravar_raw(tmp_path, "2026-11-09", 1, [])
    _gravar_raw(tmp_path, "2026-11-10", 1, [])
    assert localizar_raw_mais_recente(1, tmp_path).parent.name == "data_extracao=2026-11-10"


def test_localizar_raw_inexistente_gera_erro(tmp_path):
    with pytest.raises(FileNotFoundError):
        localizar_raw_mais_recente(1, tmp_path)


def test_transformar_concilia_contagens(tmp_path):
    _gravar_raw(
        tmp_path,
        "2026-11-10",
        1,
        [
            {"data": "05/11/2026", "valor": "5.46"},
            {"data": "06/11/2026", "valor": "5.50"},
            {"data": "06/11/2026", "valor": "5.50"},
            {"data": "xx", "valor": "5.51"},
        ],
    )
    resultado = transformar([1], CARREGADO_EM, tmp_path)
    assert resultado.linhas_raw == 4
    assert len(resultado.dados) == 2
    assert len(resultado.rejeitados) == 1
    assert resultado.duplicatas_removidas == 1


# ---------- qualidade ----------


def test_chave_duplicada_falha():
    df = pd.DataFrame({"a": [1, 1], "b": [1, 1]})
    assert not checar_chave_unica(df, ["a", "b"]).ok


def test_nulo_em_obrigatoria_falha():
    assert not checar_sem_nulos(pd.DataFrame({"a": [1, None]}), ["a"]).ok


def test_faixa():
    df = pd.DataFrame({"valor": [1.0, 25.0]})
    assert checar_faixa(df, "valor", 0, 30).ok
    assert not checar_faixa(df, "valor", 0, 20).ok


def test_avaliar_interrompe_quando_algo_falha():
    falha = checar_sem_nulos(pd.DataFrame({"a": [None]}), ["a"])
    with pytest.raises(FalhaQualidadeError):
        avaliar([falha], etapa="teste")


# ---------- carga ----------


def test_salvar_parquet_preserva_tipos_e_substitui(tmp_path):
    caminho = tmp_path / "stg" / "tabela.parquet"
    df = pd.DataFrame({"data_referencia": [date(2026, 11, 6)], "valor": [5.5]})
    salvar_parquet(df, caminho)
    salvar_parquet(df, caminho)  # segunda gravação substitui, não acumula

    lido = pd.read_parquet(caminho)
    assert len(lido) == 1
    assert lido["data_referencia"].iloc[0] == date(2026, 11, 6)
    assert not (tmp_path / "stg" / "tabela.parquet.tmp").exists()
