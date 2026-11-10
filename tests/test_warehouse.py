"""Testes da carga do warehouse e da exportação. Rodam os arquivos SQL reais do
projeto sobre stagings pequenos, em um DuckDB temporário."""

from datetime import date

import duckdb
import pandas as pd
import pytest

from pipeline_etl.carga.parquet import salvar_parquet
from pipeline_etl.orquestracao import exportacao
from pipeline_etl.orquestracao.warehouse import executar
from pipeline_etl.transformacao.anbima_feriados import COLUNAS_STAGING as COLUNAS_FERIADOS
from pipeline_etl.transformacao.bcb_focus import COLUNAS_STAGING as COLUNAS_FOCUS
from pipeline_etl.transformacao.bcb_sgs import COLUNAS_STAGING
from pipeline_etl.utils.sql import ler_sql

CARREGADO_EM = pd.Timestamp("2026-11-10 13:00:00", tz="America/Sao_Paulo")
NOMES = {1: "dolar_venda", 432: "selic_meta", 433: "ipca_variacao_mensal"}


def _staging(linhas: list[tuple]) -> pd.DataFrame:
    """linhas: (codigo, data_referencia, valor)."""
    return pd.DataFrame(
        [
            {
                "codigo_serie": codigo,
                "nome_serie": NOMES[codigo],
                "data_referencia": data_ref,
                "valor": valor,
                "unidade": "u",
                "periodicidade": "diaria",
                "fonte": "bcb_sgs",
                "data_extracao": date(2026, 11, 10),
                "carregado_em": CARREGADO_EM,
            }
            for codigo, data_ref, valor in linhas
        ],
        columns=COLUNAS_STAGING,
    )


def _feriados(linhas: list[tuple]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "data": data,
                "nome_feriado": nome,
                "fonte": "anbima_feriados",
                "data_extracao": date(2026, 11, 10),
                "carregado_em": CARREGADO_EM,
            }
            for data, nome in linhas
        ],
        columns=COLUNAS_FERIADOS,
    )


def _focus(linhas: list[tuple]) -> pd.DataFrame:
    """linhas: (data_pesquisa, mediana)."""
    return pd.DataFrame(
        [
            {
                "data_pesquisa": data,
                "indicador": "IPCA",
                "horizonte": "12 meses",
                "mediana_pct": mediana,
                "media_pct": mediana,
                "desvio_padrao": 0.3,
                "numero_respondentes": pd.NA,
                "fonte": "bcb_focus",
                "data_extracao": date(2026, 11, 10),
                "carregado_em": CARREGADO_EM,
            }
            for data, mediana in linhas
        ],
        columns=COLUNAS_FOCUS,
    ).astype({"numero_respondentes": "Int64"})


# IPCA de 1% ao mês de out/2025 a set/2026 (12 meses), Selic e dólar em alguns dias
IPCA_12_MESES = [(433, date(2025 + (m > 12), (m - 1) % 12 + 1, 1), 1.0) for m in range(10, 22)]
LINHAS_OK = IPCA_12_MESES + [
    (432, date(2026, 9, 15), 15.0),
    (432, date(2026, 9, 30), 14.0),
    (1, date(2026, 8, 31), 5.0),
    (1, date(2026, 9, 1), 5.2),
    (1, date(2026, 9, 30), 5.5),
]
FERIADOS_OK = [(date(2025, 12, 25), "Natal"), (date(2026, 9, 7), "Independência do Brasil")]


@pytest.fixture
def caminhos(tmp_path):
    stg_series, stg_feriados = tmp_path / "stg.parquet", tmp_path / "fer.parquet"
    salvar_parquet(_staging(LINHAS_OK), stg_series)
    salvar_parquet(_feriados(FERIADOS_OK), stg_feriados)
    stg_focus = tmp_path / "focus.parquet"
    salvar_parquet(_focus([(date(2025, 10, 3), 4.5), (date(2026, 9, 25), 4.6)]), stg_focus)
    parametros = {
        "caminho_stg_bcb_series": stg_series,
        "caminho_stg_feriados": stg_feriados,
        "caminho_stg_focus": stg_focus,
    }
    return tmp_path / "wh.duckdb", parametros


def _consultar(caminho_warehouse, sql: str) -> list[tuple]:
    with duckdb.connect(str(caminho_warehouse), read_only=True) as con:
        return con.execute(sql).fetchall()


def test_carga_cria_modelo(caminhos):
    contagens = executar(*caminhos)
    assert contagens["marts.fct_indicador"] == len(LINHAS_OK)
    assert contagens["marts.dim_serie"] == 3
    assert contagens["marts.dim_data"] == 365 + 365  # 2025 e 2026 completos
    assert contagens["marts.mart_indicadores_mensal"] == 12  # out/2025 a set/2026


def test_dim_data_atributos_e_dia_util(caminhos):
    warehouse, _ = caminhos
    executar(*caminhos)
    sql = (
        "SELECT data, nome_dia_semana, eh_fim_de_semana, eh_feriado, nome_feriado, eh_dia_util "
        "FROM marts.dim_data WHERE data IN "
        "(DATE '2026-11-10', DATE '2026-11-14', DATE '2026-09-07') ORDER BY data"
    )
    assert _consultar(warehouse, sql) == [
        (date(2026, 9, 7), "segunda-feira", False, True, "Independência do Brasil", False),
        (date(2026, 11, 10), "terça-feira", False, False, None, True),
        (date(2026, 11, 14), "sábado", True, False, None, False),
    ]


def test_mart_calcula_indicadores(caminhos):
    warehouse, _ = caminhos
    executar(*caminhos)
    linhas = _consultar(
        warehouse,
        "SELECT ano_mes, dias_uteis, ipca_acumulado_ano_pct, ipca_acumulado_12m_pct, "
        "selic_meta_fim_mes_pct, juro_real_12m_pct, dolar_medio_mes, dolar_fim_mes, "
        "dolar_variacao_mes_pct, dias_com_cotacao_dolar, mes_completo "
        "FROM marts.mart_indicadores_mensal WHERE ano_mes IN ('2025-10', '2026-09') ORDER BY 1",
    )
    outubro_2025, setembro_2026 = linhas
    # out/2025: primeiro mês da série -> sem acumulado no ano (faltam jan-set) e sem 12 meses
    assert outubro_2025[2] is None and outubro_2025[3] is None
    # set/2026: 21 dias úteis (30 dias - 8 de fim de semana - feriado de 7/9)
    assert setembro_2026[1] == 21
    assert setembro_2026[2] == pytest.approx(round((1.01**9 - 1) * 100, 2))
    assert setembro_2026[3] == pytest.approx(round((1.01**12 - 1) * 100, 2))  # 12,68
    assert setembro_2026[4] == 14.0  # último valor do mês, não o maior
    assert setembro_2026[5] == pytest.approx(round((1.14 / (1.01**12) - 1) * 100, 2))
    assert setembro_2026[6] == pytest.approx(5.35)
    assert setembro_2026[7] == 5.5
    assert setembro_2026[8] == pytest.approx(10.0)  # 5,5 / 5,0 - 1
    assert setembro_2026[9] == 2
    assert setembro_2026[10] is True


def test_reexecucao_nao_duplica(caminhos):
    assert executar(*caminhos) == executar(*caminhos)


def test_falha_desfaz_carga_e_mantem_warehouse_anterior(caminhos, tmp_path):
    warehouse, parametros = caminhos
    executar(warehouse, parametros)

    staging_ruim = tmp_path / "stg_ruim.parquet"
    salvar_parquet(_staging(LINHAS_OK + [(1, date(2026, 9, 30), 9.9)]), staging_ruim)
    with pytest.raises(duckdb.ConstraintException):
        executar(warehouse, {**parametros, "caminho_stg_bcb_series": staging_ruim})

    assert _consultar(warehouse, "SELECT COUNT(*) FROM marts.fct_indicador") == [(len(LINHAS_OK),)]


def test_ano_sem_feriado_falha_na_qualidade(caminhos, tmp_path):
    warehouse, parametros = caminhos
    so_2026 = tmp_path / "fer_2026.parquet"
    salvar_parquet(_feriados([(date(2026, 9, 7), "Independência do Brasil")]), so_2026)
    with pytest.raises(Exception, match="06_calendario_com_feriados"):
        executar(warehouse, {**parametros, "caminho_stg_feriados": so_2026})


def test_cotacao_do_dolar_em_feriado_falha_na_qualidade(caminhos, tmp_path):
    warehouse, parametros = caminhos
    com_feriado = tmp_path / "fer_extra.parquet"
    # 31/08/2026 tem cotação no staging de teste; marcá-lo como feriado deve reprovar a carga
    salvar_parquet(_feriados(FERIADOS_OK + [(date(2026, 8, 31), "Feriado fictício")]), com_feriado)
    with pytest.raises(Exception, match="08_dolar_somente_em_dia_util"):
        executar(warehouse, {**parametros, "caminho_stg_feriados": com_feriado})


def test_staging_inexistente_gera_erro(caminhos, tmp_path):
    warehouse, parametros = caminhos
    with pytest.raises(FileNotFoundError):
        executar(warehouse, {**parametros, "caminho_stg_feriados": tmp_path / "nao_existe.parquet"})


def test_exportacao_gera_parquet_e_csv_conferidos(caminhos, tmp_path):
    warehouse, _ = caminhos
    executar(*caminhos)
    destino = tmp_path / "processed"
    gerados = exportacao.executar(warehouse, destino)

    assert sorted(p.name for p in gerados) == [
        "indicadores_mensal.csv",
        "indicadores_mensal.parquet",
    ]
    mart = pd.read_parquet(destino / "indicadores_mensal.parquet")
    assert len(mart) == 12
    assert mart["ano_mes"].is_monotonic_increasing
    assert len(pd.read_csv(destino / "indicadores_mensal.csv")) == 12
    assert not list(destino.glob("*.tmp"))


def test_ler_sql_exige_todos_os_parametros(tmp_path):
    arquivo = tmp_path / "x.sql"
    arquivo.write_text("SELECT * FROM read_parquet('{{caminho}}')", encoding="utf-8")
    assert ler_sql(arquivo, {"caminho": "a.parquet"}) == "SELECT * FROM read_parquet('a.parquet')"
    with pytest.raises(KeyError):
        ler_sql(arquivo)
