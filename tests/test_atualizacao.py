"""Testes do botão "Atualizar dados": versionamento do raw no mesmo dia, orquestrador
(reextrair_hoje e progresso) e o botão no app (pipeline substituído; sem chamar APIs)."""

import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from pipeline_etl.dashboard import atualizacao
from pipeline_etl.dashboard.dados import caminho_parquet_mart
from pipeline_etl.orquestracao import pipeline
from pipeline_etl.transformacao.bcb_sgs import transformar
from pipeline_etl.utils.raw import arquivo_para_gravar, caminho_meta, listar_arquivos

RAIZ = Path(__file__).resolve().parents[1]
CARREGADO_EM = pd.Timestamp("2026-11-10 13:00", tz="America/Sao_Paulo")


# ---------- raw versionado no mesmo dia ----------


def _gravar(pasta: Path, extracao: str, nome: str, registros: list[dict]) -> Path:
    destino = pasta / f"data_extracao={extracao}" / nome
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(registros), encoding="utf-8")
    meta = {"nome_serie": "dolar_venda", "unidade": "R$/US$", "periodicidade": "diaria"}
    caminho_meta(destino).write_text(json.dumps(meta), encoding="utf-8")
    return destino


def test_arquivo_para_gravar_respeita_raw_imutavel(tmp_path):
    particao = tmp_path / "data_extracao=2026-11-10"
    particao.mkdir()
    base = arquivo_para_gravar(particao, "serie_1", nova_versao=False)
    assert base == particao / "serie_1.json"
    base.write_text("[]")
    assert arquivo_para_gravar(particao, "serie_1", nova_versao=False) is None  # pula
    versao = arquivo_para_gravar(particao, "serie_1", True, datetime(2026, 11, 10, 15, 4, 5))
    assert versao == particao / "serie_1__150405.json"
    versao.write_text("[]")
    with pytest.raises(FileExistsError):
        arquivo_para_gravar(particao, "serie_1", True, datetime(2026, 11, 10, 15, 4, 5))


def test_listar_arquivos_ordena_por_extracao_e_ignora_meta(tmp_path):
    _gravar(tmp_path, "2026-11-10", "serie_1__150405.json", [])
    _gravar(tmp_path, "2026-11-10", "serie_1.json", [])
    _gravar(tmp_path, "2026-11-09", "serie_1.json", [])
    _gravar(tmp_path, "2026-11-10", "serie_13.json", [])  # outra série, não entra
    nomes = [f"{a.parent.name}/{a.name}" for a in listar_arquivos(tmp_path, "serie_1")]
    assert nomes == [
        "data_extracao=2026-11-09/serie_1.json",
        "data_extracao=2026-11-10/serie_1.json",
        "data_extracao=2026-11-10/serie_1__150405.json",
    ]


def test_staging_usa_a_versao_mais_nova_do_mesmo_dia(tmp_path):
    _gravar(tmp_path, "2026-11-10", "serie_1.json", [{"data": "10/11/2026", "valor": "5.50"}])
    _gravar(
        tmp_path,
        "2026-11-10",
        "serie_1__183000.json",
        [{"data": "10/11/2026", "valor": "5.53"}, {"data": "11/11/2026", "valor": "5.55"}],
    )
    dados = transformar([1], CARREGADO_EM, tmp_path).dados.set_index("data_referencia")
    assert dados.loc[date(2026, 11, 10), "valor"] == pytest.approx(5.53)
    assert len(dados) == 2


# ---------- orquestrador ----------


def test_reextrair_hoje_vai_so_para_as_extracoes_de_api(monkeypatch):
    chamadas: dict[str, dict] = {}

    def falsa(nome):
        return lambda **kwargs: chamadas.__setitem__(nome, kwargs)

    monkeypatch.setattr(pipeline, "ETAPAS", {nome: falsa(nome) for nome in pipeline.ETAPAS})
    eventos = []
    pipeline.executar(
        reextrair_hoje=True, progresso=lambda p, t, n, e: eventos.append((p, t, n, e))
    )
    assert chamadas["extracao_bcb_sgs"] == {"reextrair_hoje": True}
    assert chamadas["extracao_bcb_focus"] == {"reextrair_hoje": True}
    assert chamadas["extracao_anbima_feriados"] == {}  # planilha: uma vez por dia
    assert chamadas["warehouse"] == {}
    assert eventos[0] == (1, 8, "extracao_bcb_sgs", "inicio")
    assert eventos[-1] == (8, 8, "exportacao", "fim")


def test_minutos_para_liberar():
    df = pd.DataFrame({"carregado_em": [pd.Timestamp("2026-11-10 14:00", tz="UTC")]})
    agora = pd.Timestamp("2026-11-10 14:03:30", tz="UTC")
    assert atualizacao.minutos_para_liberar(df, 10, agora) == 7  # 6,5 min -> arredonda para cima
    assert atualizacao.minutos_para_liberar(df, 3, agora) == 0


# ---------- botão no app ----------

sem_dados = pytest.mark.skipif(
    not caminho_parquet_mart().exists(), reason="rode o pipeline para gerar a mart"
)


@pytest.fixture
def app_sem_intervalo(monkeypatch):
    monkeypatch.setattr(
        atualizacao, "config_atualizacao", lambda: {"permitir": True, "intervalo_minimo_minutos": 0}
    )
    monkeypatch.setattr(atualizacao, "configurar_logging", lambda: None)
    return AppTest.from_file(str(RAIZ / "app.py"), default_timeout=60).run()


@sem_dados
def test_botao_roda_pipeline_com_reextracao_e_recarrega(monkeypatch, app_sem_intervalo):
    chamadas = []

    def pipeline_falso(**kwargs):
        chamadas.append(kwargs["reextrair_hoje"])
        kwargs["progresso"](1, 1, "warehouse", "inicio")
        kwargs["progresso"](1, 1, "warehouse", "fim")

    monkeypatch.setattr(pipeline, "executar", pipeline_falso)
    app = app_sem_intervalo
    assert not app.button(key="botao_atualizar").disabled
    app.button(key="botao_atualizar").click().run()
    assert chamadas == [True]
    assert not app.exception
    assert any("Dados atualizados" in t.proto.body for t in app.toast)


@sem_dados
def test_falha_na_atualizacao_mostra_erro_e_mantem_o_painel(monkeypatch, app_sem_intervalo):
    def pipeline_com_erro(**kwargs):
        raise RuntimeError("API fora do ar (simulado)")

    monkeypatch.setattr(pipeline, "executar", pipeline_com_erro)
    app = app_sem_intervalo
    app.button(key="botao_atualizar").click().run()
    assert not app.exception
    assert any("API fora do ar" in (e.proto.body or "") for e in app.error)
    assert app.session_state["_mart_periodo"] is not None  # painel continua com os dados


@sem_dados
def test_botao_bloqueado_dentro_do_intervalo(monkeypatch):
    monkeypatch.setattr(
        atualizacao,
        "config_atualizacao",
        lambda: {"permitir": True, "intervalo_minimo_minutos": 10**9},
    )
    app = AppTest.from_file(str(RAIZ / "app.py"), default_timeout=60).run()
    assert app.button(key="botao_atualizar").disabled
