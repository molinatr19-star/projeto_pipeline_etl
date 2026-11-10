"""Testes das análises do painel (comparações e alertas) e do relatório executivo."""

import pandas as pd
import pytest

from pipeline_etl.dashboard.analise import (
    ParametrosAlerta,
    adicionar_faixa_meta,
    alertas_recentes,
    comparar,
    comparar_janelas,
    detectar_alertas,
    diferenca,
    mes_referencia_padrao,
)
from pipeline_etl.dashboard.dados import preparar
from pipeline_etl.dashboard.relatorio import gerar_relatorio_html

PARAMS = ParametrosAlerta(
    tolerancia_padrao=1.5,
    tolerancia_por_ano={2024: 2.0},
    ipca_mensal_alto_pct=1.0,
    dolar_variacao_mes_pct=5.0,
    meses_historico_recorde=3,
)


def _mart(**colunas) -> pd.DataFrame:
    """Mart de 24 meses (jan/2024 a dez/2025) com valores neutros; `colunas` sobrescreve."""
    datas = pd.date_range("2024-01-01", periods=24, freq="MS")
    base = {
        "ano_mes": datas.strftime("%Y-%m"),
        "primeiro_dia_mes": datas,
        "ano": datas.year,
        "mes": datas.month,
        "dias_uteis": [21] * 24,
        "ipca_mensal_pct": [0.3] * 24,
        "ipca_acumulado_ano_pct": [1.0] * 24,
        "ipca_acumulado_12m_pct": [3.0] * 24,
        "meta_inflacao_pct": [3.0] * 24,
        "selic_meta_fim_mes_pct": [10.0] * 24,
        "juro_real_12m_pct": [6.8] * 24,
        "dolar_medio_mes": [5.0] * 24,
        "dolar_fim_mes": [5.0] * 24,
        "dolar_variacao_mes_pct": [0.0] * 24,
        "dias_com_cotacao_dolar": [21] * 24,
        "mes_completo": [True] * 24,
        "carregado_em": pd.Timestamp("2026-11-10 13:00", tz="America/Sao_Paulo"),
    }
    for nome, valores in colunas.items():
        base[nome] = valores
    return preparar(pd.DataFrame(base))


def _com(valores_padrao: float, alteracoes: dict[int, float]) -> list[float]:
    lista = [valores_padrao] * 24
    for posicao, valor in alteracoes.items():
        lista[posicao] = valor
    return lista


# ---------- comparação ----------


def test_diferenca_absoluta_e_relativa():
    assert diferenca(11.0, 10.0) == pytest.approx((1.0, 10.0))
    assert diferenca(None, 10.0) == (None, None)
    assert diferenca(5.0, 0.0) == (5.0, None)
    # base negativa: sem variação relativa (seria "-356%"), só a diferença absoluta
    assert diferenca(0.82, -0.32) == pytest.approx((1.14, None))


def test_comparar_mom_yoy_e_outro_mes():
    df = _mart(selic_meta_fim_mes_pct=[10.0 + 0.25 * i for i in range(24)])
    ref = pd.Timestamp("2025-06-01")  # posição 17 -> 14,25
    linha = (
        comparar(df, ref, pd.Timestamp("2024-01-01"))
        .set_index("coluna")
        .loc["selic_meta_fim_mes_pct"]
    )
    assert linha["valor"] == pytest.approx(14.25)
    assert linha["delta_mom"] == pytest.approx(0.25)
    assert linha["delta_yoy"] == pytest.approx(3.0)
    assert linha["var_yoy_pct"] == pytest.approx((14.25 / 11.25 - 1) * 100)
    assert linha["delta_outro"] == pytest.approx(4.25)


def test_comparar_sem_mes_base_fica_vazio():
    df = _mart()
    linha = comparar(df, pd.Timestamp("2024-03-01")).set_index("coluna").loc["dolar_fim_mes"]
    assert linha["base_yoy"] is None and linha["delta_yoy"] is None  # mar/2023 não existe


def test_janelas_acumulam_ipca_e_somam_dias():
    df = _mart(ipca_mensal_pct=[1.0] * 24)
    janelas = comparar_janelas(df, pd.Timestamp("2025-12-01"), 12).set_index("indicador")
    assert janelas.loc["IPCA acumulado", "janela_atual"] == pytest.approx((1.01**12 - 1) * 100)
    assert janelas.loc["Dias úteis (total)", "janela_anterior"] == 21 * 12
    assert janelas.loc["Dólar (média)", "delta"] == pytest.approx(0.0)


def test_janela_incompleta_fica_vazia():
    df = _mart()
    janelas = comparar_janelas(df, pd.Timestamp("2024-06-01"), 12).set_index("indicador")
    assert janelas.loc["Selic meta (média)", "janela_atual"] is None


def test_referencia_padrao_e_o_ultimo_mes_com_ipca():
    df = _mart(ipca_mensal_pct=_com(0.3, {22: None, 23: None}))
    assert mes_referencia_padrao(df) == pd.Timestamp("2025-10-01")


# ---------- alertas ----------


def _regras(alertas: pd.DataFrame) -> set[tuple[str, str]]:
    return set(zip(alertas["mes_rotulo"], alertas["regra"], strict=True))


def test_sem_alertas_em_mart_neutra():
    assert detectar_alertas(_mart(), PARAMS).empty


def test_faixa_da_meta_usa_tolerancia_do_ano():
    df = adicionar_faixa_meta(_mart(), PARAMS)
    assert df.loc[0, "teto_meta_pct"] == pytest.approx(5.0)  # 2024: 3,0 + 2,0
    assert df.loc[23, "teto_meta_pct"] == pytest.approx(4.5)  # 2025: 3,0 + 1,5


def test_ipca_12m_acima_do_teto_e_critico_e_do_centro_e_atencao():
    # 2025 (teto 4,5): jan = 4,6 (crítico), fev = 4,5 (no teto: atenção, não crítico)
    df = _mart(ipca_acumulado_12m_pct=_com(3.0, {12: 4.6, 13: 4.5, 14: 1.4}))
    alertas = detectar_alertas(df, PARAMS)
    criticos = alertas[alertas["severidade"] == "Crítico"]
    assert _regras(criticos) == {("jan/2025", "Acima do teto da meta")}
    assert ("fev/2025", "Acima do centro da meta") in _regras(alertas)
    assert ("mar/2025", "Abaixo do piso da meta") in _regras(alertas)  # piso 1,5


def test_ipca_mensal_alto_e_deflacao():
    df = _mart(ipca_mensal_pct=_com(0.3, {5: 1.0, 6: -0.2}))
    regras = _regras(detectar_alertas(df, PARAMS))
    assert ("jun/2024", "IPCA mensal elevado") in regras
    assert ("jul/2024", "Deflação") in regras


def test_dolar_variacao_forte_nos_dois_sentidos():
    df = _mart(dolar_variacao_mes_pct=_com(0.0, {4: 5.0, 8: -6.0, 9: 4.99}))
    regras = _regras(detectar_alertas(df, PARAMS))
    assert {("mai/2024", "Variação forte no mês"), ("set/2024", "Variação forte no mês")} <= regras
    assert ("out/2024", "Variação forte no mês") not in regras


def test_dolar_recorde_exige_historico():
    subida = [5.0 + 0.1 * i for i in range(24)]  # todo mês é recorde
    alertas = detectar_alertas(_mart(dolar_fim_mes=subida), PARAMS)
    recordes = alertas[alertas["regra"] == "Nível recorde"]
    assert len(recordes) == 24 - PARAMS.meses_historico_recorde
    assert "jan/2024" not in set(recordes["mes_rotulo"])


def test_juro_real_negativo():
    df = _mart(juro_real_12m_pct=_com(6.8, {20: -0.5}))
    assert ("set/2025", "Juro real negativo") in _regras(detectar_alertas(df, PARAMS))


def test_alertas_recentes_ordenam_por_gravidade():
    df = _mart(ipca_acumulado_12m_pct=_com(3.0, {23: 5.0}), ipca_mensal_pct=_com(0.3, {22: -0.1}))
    recentes = alertas_recentes(detectar_alertas(df, PARAMS), pd.Timestamp("2025-12-01"), 3)
    assert recentes["severidade"].tolist() == ["Crítico", "Informativo"]


# ---------- relatório ----------


def test_relatorio_tem_secoes_e_escapa_texto():
    df = _mart(ipca_acumulado_12m_pct=_com(3.0, {23: 5.0}))
    alertas = detectar_alertas(df, PARAMS)
    html = gerar_relatorio_html(
        df,
        comparar(df, pd.Timestamp("2025-12-01")),
        "dez/2025",
        alertas,
        "<origem>",
        pd.Timestamp("2026-11-10 13:00"),
    )
    assert html.startswith("<!doctype html>")
    for secao in [
        "Resumo em dez/2025",
        "Comparação com períodos anteriores",
        "Alertas no período",
        "Dados mensais",
        "Fontes e método",
    ]:
        assert secao in html
    assert "Acima do teto da meta" in html
    assert "&lt;origem&gt;" in html and "<origem>" not in html
    assert "<script" not in html


def test_indicadores_dos_alertas_estao_na_lista_fixa_do_filtro():
    from pipeline_etl.dashboard.analise import INDICADORES_ALERTA

    df = _mart(
        ipca_acumulado_12m_pct=_com(3.0, {13: 9.0}),
        ipca_mensal_pct=_com(0.3, {3: 1.5}),
        dolar_variacao_mes_pct=_com(0.0, {5: 8.0}),
        juro_real_12m_pct=_com(6.8, {7: -1.0}),
    )
    assert set(detectar_alertas(df, PARAMS)["indicador"]) <= set(INDICADORES_ALERTA)


def test_expectativa_acima_do_teto_gera_alerta():
    from pipeline_etl.dashboard.analise import detectar_alertas as detectar

    df = _mart(expectativa_ipca_12m_pct=_com(3.5, {20: 4.8}))
    assert ("set/2025", "Expectativa acima do teto da meta") in _regras(detectar(df, PARAMS))


def test_previsto_vs_realizado_compara_com_expectativa_de_12_meses_antes():
    from pipeline_etl.dashboard.analise import previsto_vs_realizado

    df = _mart(
        expectativa_ipca_12m_pct=_com(3.5, {0: 4.0}),
        ipca_acumulado_12m_pct=_com(3.0, {12: 4.6}),
    )
    linha = previsto_vs_realizado(df).set_index("mes_rotulo").loc["jan/2025"]
    assert linha["esperado_pct"] == pytest.approx(4.0)  # pesquisa de jan/2024
    assert linha["realizado_pct"] == pytest.approx(4.6)
    assert linha["erro_pp"] == pytest.approx(0.6)


def test_dias_desde_carga():
    from pipeline_etl.dashboard.dados import dias_desde_carga

    df = _mart()
    agora = pd.Timestamp("2026-11-14 12:59", tz="America/Sao_Paulo")
    assert dias_desde_carga(df, agora) == 3


def test_largura_coluna_cabe_o_texto_mais_longo():
    from pipeline_etl.dashboard.estilo import largura_coluna

    regras = pd.Series(["Deflação", "Expectativa acima do teto da meta"])
    assert largura_coluna(regras, "Regra") == len("Expectativa acima do teto da meta") * 7 + 28
    assert largura_coluna(pd.Series(["1,0"]), "Limite") == len("Limite") * 7 + 28  # título maior
