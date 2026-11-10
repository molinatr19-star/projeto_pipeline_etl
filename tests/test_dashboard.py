"""Testes do painel: leitura da mart, recorte, indicadores, gráficos e execução das páginas."""

from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import plotly.graph_objects as go
import pytest
from streamlit.testing.v1 import AppTest

from pipeline_etl.dashboard import graficos
from pipeline_etl.dashboard.dados import (
    caminho_parquet_mart,
    intervalo_do_periodo,
    intervalo_escolhido,
    ler_mart,
    preparar,
    recortar,
    rotulo_mes,
    texto_variacao,
    ultimo,
)

RAIZ = Path(__file__).resolve().parents[1]
PAGINAS = [
    "paginas/visao_geral.py",
    "paginas/inflacao_juros.py",
    "paginas/cambio.py",
    "paginas/dias_uteis.py",
    "paginas/mercado.py",
    "paginas/comparador.py",
    "paginas/alertas.py",
    "paginas/tabela.py",
]


def _mart(meses: int = 14) -> pd.DataFrame:
    """Mart sintética de jan/2025 em diante, com IPCA ausente nos dois últimos meses."""
    datas = pd.date_range("2025-01-01", periods=meses, freq="MS")
    df = pd.DataFrame(
        {
            "ano_mes": datas.strftime("%Y-%m"),
            "primeiro_dia_mes": datas.date,
            "ano": datas.year,
            "mes": datas.month,
            "dias_uteis": [20 + (i % 3) for i in range(meses)],
            "ipca_mensal_pct": [0.5 - 0.1 * (i % 7) for i in range(meses)],
            "ipca_acumulado_ano_pct": [1.0 + i * 0.3 for i in range(meses)],
            "ipca_acumulado_12m_pct": [None] * 11 + [4.5 + 0.1 * i for i in range(meses - 11)],
            "selic_meta_fim_mes_pct": [12.25 + 0.25 * min(i, 6) for i in range(meses)],
            "juro_real_12m_pct": [None] * 11 + [8.0 + 0.1 * i for i in range(meses - 11)],
            "dolar_medio_mes": [5.0 + 0.05 * i for i in range(meses)],
            "dolar_fim_mes": [5.02 + 0.05 * i for i in range(meses)],
            "dolar_variacao_mes_pct": [None] + [1.0 - 0.5 * (i % 4) for i in range(1, meses)],
            "dias_com_cotacao_dolar": [20] * meses,
            "mes_completo": [True] * (meses - 1) + [False],
            "carregado_em": pd.Timestamp("2026-11-10 13:00", tz="America/Sao_Paulo"),
        }
    )
    df.loc[meses - 2 :, ["ipca_mensal_pct", "ipca_acumulado_ano_pct"]] = None
    df.loc[meses - 2 :, ["ipca_acumulado_12m_pct", "juro_real_12m_pct"]] = None
    return df


# ---------- dados ----------


def test_rotulo_mes_em_portugues():
    assert rotulo_mes(pd.Timestamp("2026-09-01")) == "set/2026"


def test_ler_mart_prefere_parquet(tmp_path):
    parquet = tmp_path / "indicadores_mensal.parquet"
    _mart().to_parquet(parquet, index=False)
    mart = ler_mart(parquet, tmp_path / "nao_existe.duckdb")
    assert mart.origem.startswith("data/processed/")
    assert mart.dados["mes_rotulo"].iloc[0] == "jan/2025"


def test_ler_mart_usa_duckdb_sem_parquet(tmp_path):
    warehouse = tmp_path / "wh.duckdb"
    mart_df = _mart()
    with duckdb.connect(str(warehouse)) as con:
        con.execute("CREATE SCHEMA marts")
        con.execute("CREATE TABLE marts.mart_indicadores_mensal AS SELECT * FROM mart_df")
    mart = ler_mart(tmp_path / "nao_existe.parquet", warehouse)
    assert "warehouse" in mart.origem
    assert len(mart.dados) == len(mart_df)


def test_ler_mart_sem_dados_gera_erro(tmp_path):
    with pytest.raises(FileNotFoundError, match="pipeline-etl"):
        ler_mart(tmp_path / "a.parquet", tmp_path / "b.duckdb")


def test_recorte_e_atalhos_de_periodo():
    df = preparar(_mart())
    rotulos = df["mes_rotulo"].tolist()
    assert intervalo_do_periodo(rotulos, 12) == ("mar/2025", "fev/2026")
    assert intervalo_do_periodo(rotulos, None) == ("jan/2025", "fev/2026")
    assert intervalo_do_periodo(rotulos, 999)[0] == "jan/2025"
    parte = recortar(df, pd.Timestamp("2025-03-01"), pd.Timestamp("2025-05-01"))
    assert parte["mes_rotulo"].tolist() == ["mar/2025", "abr/2025", "mai/2025"]


def test_intervalo_escolhido_aceita_formatos_do_slider():
    rotulos = preparar(_mart())["mes_rotulo"].tolist()  # jan/2025 a fev/2026
    assert intervalo_escolhido(rotulos, "12 meses", None) == ("mar/2025", "fev/2026")
    assert intervalo_escolhido(rotulos, "Personalizado", ("fev/2025", "abr/2025")) == (
        "fev/2025",
        "abr/2025",
    )
    # par invertido, valor único e valor inválido não quebram o painel
    assert intervalo_escolhido(rotulos, "Personalizado", ("abr/2025", "fev/2025")) == (
        "fev/2025",
        "abr/2025",
    )
    assert intervalo_escolhido(rotulos, "Personalizado", "mai/2025") == ("mai/2025", "mai/2025")
    assert intervalo_escolhido(rotulos, "Personalizado", ("x", "y"))[1] == "fev/2026"


def test_ultimo_ignora_meses_sem_valor():
    df = preparar(_mart())
    ipca = ultimo(df, "ipca_mensal_pct")
    assert ipca.referencia == "dez/2025"  # jan e fev/2026 ainda sem IPCA
    vazio = ultimo(df.iloc[:5], "ipca_acumulado_12m_pct")
    assert vazio.valor is None and vazio.referencia == "-"


def test_texto_variacao():
    assert texto_variacao(0.25) == "▲ 0,25 p.p. vs mês anterior"
    assert texto_variacao(-1.5, 2, "%") == "▼ 1,50% vs mês anterior"
    assert texto_variacao(0.001) == "= estável vs mês anterior"
    assert texto_variacao(None) == ""


# ---------- gráficos ----------


def test_graficos_montam_sem_erro():
    df = preparar(_mart())
    figuras = [
        graficos.grafico_juros(df),
        graficos.grafico_barras_sinal(df, "ipca_mensal_pct", "IPCA", "Inflação", "Deflação"),
        graficos.grafico_ipca_anual(df),
        graficos.grafico_linha_unica(df, "juro_real_12m_pct", "Juro", "#d55181", 2, "%", area=True),
        graficos.grafico_dolar(df),
        graficos.grafico_dias_uteis_mes(df),
        graficos.grafico_mapa_dias_uteis(df),
        graficos.grafico_dias_uteis_ano(df),
    ]
    assert all(isinstance(f, go.Figure) and f.data for f in figuras)


def test_barras_sinal_separa_positivos_e_negativos():
    df = preparar(_mart())
    fig = graficos.grafico_barras_sinal(df, "ipca_mensal_pct", "IPCA", "Inflação", "Deflação")
    nomes = [trace.name for trace in fig.data]
    assert nomes == ["Inflação", "Deflação"]
    assert all(v >= 0 for v in fig.data[0].y) and all(v < 0 for v in fig.data[1].y)


def test_ipca_por_ano_marca_ano_incompleto():
    anual = graficos.ipca_por_ano(preparar(_mart()))
    assert anual["rotulo_ano"].tolist() == ["2025"]  # 2026 sem IPCA publicado na mart sintética
    assert bool(anual["completo"].iloc[0])


def test_tabela_dias_uteis_tem_12_colunas():
    grade = graficos.tabela_dias_uteis(preparar(_mart()))
    assert list(grade.columns)[:2] == ["jan", "fev"] and grade.shape == (2, 12)
    assert pd.isna(grade.loc[2026, "mar"])


# ---------- app (execução real das páginas, sem navegador) ----------

sem_dados = pytest.mark.skipif(
    not caminho_parquet_mart().exists(), reason="rode o pipeline para gerar a mart"
)


@sem_dados
@pytest.mark.parametrize("pagina", PAGINAS)
def test_paginas_rodam_sem_erro(pagina):
    app = AppTest.from_file(str(RAIZ / "app.py"), default_timeout=60).run()
    assert not app.exception
    app.switch_page(pagina).run()
    assert not app.exception, app.exception
    # st.error aparece legitimamente para alertas críticos; não pode ser o erro de "sem dados".
    assert all("Dados ainda não gerados" not in (e.proto.body or "") for e in app.error)


@sem_dados
def test_filtro_de_periodo_pelos_widgets():
    app = AppTest.from_file(str(RAIZ / "app.py"), default_timeout=60).run()
    assert len(app.session_state["_mart_periodo"]) == 60  # padrão: 5 anos
    assert not app.select_slider  # slider só aparece em "Personalizado"

    app.segmented_control(key="f_periodo").set_value("12 meses").run()
    assert len(app.session_state["_mart_periodo"]) == 12

    app.segmented_control(key="f_periodo").set_value("Tudo").run()
    assert app.session_state["_mart_periodo"]["primeiro_dia_mes"].iloc[0].date() == date(2015, 1, 1)

    app.segmented_control(key="f_periodo").set_value("Personalizado").run()
    assert len(app.session_state["_mart_periodo"]) == 60  # slider começa em 5 anos
    assert app.select_slider(key="f_intervalo")
    assert not app.exception
