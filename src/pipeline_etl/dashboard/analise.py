"""Análises do painel: comparação entre períodos (MoM, YoY, outro mês, janelas) e alertas.

Funções puras (sem Streamlit), testadas em tests/test_dashboard_analise.py.
Os limites dos alertas ficam em `painel` no config/pipeline.yaml.
"""

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from pipeline_etl.utils.configuracao import carregar_config
from pipeline_etl.utils.tempo import como_timestamp

# Indicadores comparáveis: (coluna, nome, unidade, tipo)
#   tipo "taxa": a diferença é em pontos percentuais (p.p.)
#   tipo "nivel": a diferença natural é em % (ex.: dólar)
#   tipo "contagem": diferença em unidades (dias)
INDICADORES = [
    ("ipca_mensal_pct", "IPCA no mês", "%", "taxa"),
    ("ipca_acumulado_12m_pct", "IPCA 12 meses", "%", "taxa"),
    ("expectativa_ipca_12m_pct", "Expectativa IPCA 12m (Focus)", "%", "taxa"),
    ("igpm_mensal_pct", "IGP-M no mês", "%", "taxa"),
    ("igpm_acumulado_12m_pct", "IGP-M 12 meses", "%", "taxa"),
    ("selic_meta_fim_mes_pct", "Selic meta", "% a.a.", "taxa"),
    ("cdi_fim_mes_pct", "CDI", "% a.a.", "taxa"),
    ("juro_real_12m_pct", "Juro real", "%", "taxa"),
    ("dolar_medio_mes", "Dólar médio", "R$", "nivel"),
    ("dolar_fim_mes", "Dólar fim do mês", "R$", "nivel"),
    ("desocupacao_pct", "Desocupação", "%", "taxa"),
    ("dias_uteis", "Dias úteis", "dias", "contagem"),
]

SEVERIDADES = ["Crítico", "Atenção", "Informativo"]
INDICADORES_ALERTA = ["IPCA 12 meses", "IPCA no mês", "Expectativa IPCA", "Dólar", "Juro real"]
COLUNAS_ALERTA = [
    "primeiro_dia_mes",
    "mes_rotulo",
    "indicador",
    "regra",
    "severidade",
    "valor",
    "limite",
    "mensagem",
]


# ---------- comparação entre períodos ----------


def valor_em(df: pd.DataFrame, coluna: str, mes: pd.Timestamp | None) -> float | None:
    """Valor da coluna no mês (None se o mês não existe ou o valor não foi publicado)."""
    if mes is None:
        return None
    linha = df.loc[df["primeiro_dia_mes"] == mes, coluna]
    if linha.empty or pd.isna(linha.iloc[0]):
        return None
    return float(linha.iloc[0])


def diferenca(atual: float | None, base: float | None) -> tuple[float | None, float | None]:
    """(diferença absoluta, variação relativa em %). None quando falta um dos lados
    ou quando a base é zero/negativa (variação relativa sem sentido)."""
    if atual is None or base is None:
        return None, None
    # Variação relativa só tem sentido sobre base positiva: de -0,32% para 0,82% não é
    # "-356%". Nesses casos fica só a diferença absoluta (em p.p. para taxas).
    relativa = (atual / base - 1) * 100 if base > 0 else None
    return atual - base, relativa


def comparar(
    df: pd.DataFrame, referencia: pd.Timestamp, outro_mes: pd.Timestamp | None = None
) -> pd.DataFrame:
    """Compara cada indicador no mês de referência com o mês anterior (MoM), o mesmo mês
    do ano anterior (YoY) e, opcionalmente, outro mês escolhido.

    `df` deve ser a mart inteira (não só o período filtrado), para achar os meses de base.
    """
    bases = {
        "mom": referencia - pd.DateOffset(months=1),
        "yoy": referencia - pd.DateOffset(years=1),
        "outro": outro_mes,
    }
    linhas = []
    for coluna, nome, unidade, tipo in INDICADORES:
        atual = valor_em(df, coluna, referencia)
        linha: dict[str, Any] = {
            "coluna": coluna,
            "indicador": nome,
            "unidade": unidade,
            "tipo": tipo,
            "valor": atual,
        }
        for chave, mes in bases.items():
            base = valor_em(df, coluna, mes)
            delta, relativa = diferenca(atual, base)
            linha |= {f"base_{chave}": base, f"delta_{chave}": delta, f"var_{chave}_pct": relativa}
        linhas.append(linha)
    return pd.DataFrame(linhas)


def comparar_janelas(df: pd.DataFrame, referencia: pd.Timestamp, meses: int) -> pd.DataFrame:
    """Janela atual (os `meses` até a referência) contra a janela anterior de mesmo tamanho.

    IPCA é acumulado na janela (produto de 1 + taxa); Selic, juro real e dólar usam a
    média; dias úteis usam a soma. Janela com mês faltando fica vazia (None).
    """
    fim_atual = referencia
    inicio_atual = referencia - pd.DateOffset(months=meses - 1)
    fim_anterior = inicio_atual - pd.DateOffset(months=1)
    inicio_anterior = fim_anterior - pd.DateOffset(months=meses - 1)

    def janela(inicio: pd.Timestamp, fim: pd.Timestamp) -> pd.DataFrame:
        return df[df["primeiro_dia_mes"].between(inicio, fim)]

    def resumir(parte: pd.DataFrame, coluna: str, modo: str) -> float | None:
        valores = parte[coluna]
        if len(parte) < meses or valores.isna().any():
            return None
        if modo == "acumulado":
            return float(((1 + valores / 100).prod() - 1) * 100)
        if modo == "soma":
            return float(valores.sum())
        return float(valores.mean())

    regras = [
        ("ipca_mensal_pct", "IPCA acumulado", "%", "taxa", "acumulado"),
        ("igpm_mensal_pct", "IGP-M acumulado", "%", "taxa", "acumulado"),
        ("selic_meta_fim_mes_pct", "Selic meta (média)", "% a.a.", "taxa", "media"),
        ("cdi_fim_mes_pct", "CDI (média)", "% a.a.", "taxa", "media"),
        ("juro_real_12m_pct", "Juro real (média)", "%", "taxa", "media"),
        ("desocupacao_pct", "Desocupação (média)", "%", "taxa", "media"),
        ("dolar_medio_mes", "Dólar (média)", "R$", "nivel", "media"),
        ("dias_uteis", "Dias úteis (total)", "dias", "contagem", "soma"),
    ]
    atual_df, anterior_df = janela(inicio_atual, fim_atual), janela(inicio_anterior, fim_anterior)
    linhas = []
    for coluna, nome, unidade, tipo, modo in regras:
        atual, anterior = resumir(atual_df, coluna, modo), resumir(anterior_df, coluna, modo)
        delta, relativa = diferenca(atual, anterior)
        linhas.append(
            {
                "indicador": nome,
                "unidade": unidade,
                "tipo": tipo,
                "janela_atual": atual,
                "janela_anterior": anterior,
                "delta": delta,
                "var_pct": relativa,
            }
        )
    resultado = pd.DataFrame(linhas)
    resultado.attrs["periodos"] = (inicio_anterior, fim_anterior, inicio_atual, fim_atual)
    return resultado


def mes_referencia_padrao(df: pd.DataFrame) -> pd.Timestamp:
    """Último mês com IPCA publicado (todos os indicadores disponíveis); senão, o último mês."""
    com_ipca = df.dropna(subset=["ipca_mensal_pct"])
    base = com_ipca if not com_ipca.empty else df
    return como_timestamp(base["primeiro_dia_mes"].iloc[-1])


def previsto_vs_realizado(df: pd.DataFrame) -> pd.DataFrame:
    """IPCA 12 meses realizado em cada mês contra o que o Focus esperava 12 meses antes.

    Para o mês M: esperado = mediana do Focus (horizonte 12 meses) no mês M-12;
    realizado = IPCA acumulado nos 12 meses até M; erro = realizado - esperado (p.p.).
    Use a mart inteira: a expectativa de base pode estar antes do período filtrado.
    """
    base = df[["primeiro_dia_mes", "expectativa_ipca_12m_pct"]].assign(
        primeiro_dia_mes=lambda d: d["primeiro_dia_mes"] + pd.DateOffset(years=1)
    )
    juntos = df[["primeiro_dia_mes", "mes_rotulo", "ipca_acumulado_12m_pct"]].merge(
        base.rename(columns={"expectativa_ipca_12m_pct": "esperado_pct"}),
        on="primeiro_dia_mes",
        how="left",
    )
    juntos = juntos.rename(columns={"ipca_acumulado_12m_pct": "realizado_pct"})
    juntos["erro_pp"] = juntos["realizado_pct"] - juntos["esperado_pct"]
    return juntos


# ---------- alertas ----------


@dataclass(frozen=True)
class ParametrosAlerta:
    """Limites dos alertas (config/pipeline.yaml, seção `painel`)."""

    tolerancia_padrao: float = 1.5
    tolerancia_por_ano: dict[int, float] = field(default_factory=dict)
    ipca_mensal_alto_pct: float = 1.0
    dolar_variacao_mes_pct: float = 5.0
    meses_historico_recorde: int = 12

    def tolerancia(self, ano: int) -> float:
        return self.tolerancia_por_ano.get(ano, self.tolerancia_padrao)


def parametros_do_config() -> ParametrosAlerta:
    painel = carregar_config().get("painel", {})
    tolerancia = painel.get("tolerancia_meta_inflacao", {})
    alertas = painel.get("alertas", {})
    return ParametrosAlerta(
        tolerancia_padrao=float(tolerancia.get("padrao", 1.5)),
        tolerancia_por_ano={int(a): float(t) for a, t in tolerancia.get("por_ano", {}).items()},
        ipca_mensal_alto_pct=float(alertas.get("ipca_mensal_alto_pct", 1.0)),
        dolar_variacao_mes_pct=float(alertas.get("dolar_variacao_mes_pct", 5.0)),
        meses_historico_recorde=int(alertas.get("meses_historico_recorde", 12)),
    )


def adicionar_faixa_meta(df: pd.DataFrame, params: ParametrosAlerta) -> pd.DataFrame:
    """Colunas piso_meta_pct e teto_meta_pct: centro da meta -/+ tolerância do ano."""
    df = df.copy()
    tolerancia = df["ano"].map(params.tolerancia)
    df["piso_meta_pct"] = df["meta_inflacao_pct"] - tolerancia
    df["teto_meta_pct"] = df["meta_inflacao_pct"] + tolerancia
    return df


def _eventos(
    df: pd.DataFrame,
    mascara: pd.Series,
    indicador: str,
    regra: str,
    severidade: str,
    coluna_valor: str,
    limite: pd.Series | float,
    mensagem: str,
) -> pd.DataFrame:
    """Linhas de alerta para os meses em que `mascara` é verdadeira."""
    selecionados = df[mascara.fillna(False).astype(bool)]
    limites = limite[selecionados.index] if isinstance(limite, pd.Series) else limite
    return pd.DataFrame(
        {
            "primeiro_dia_mes": selecionados["primeiro_dia_mes"],
            "mes_rotulo": selecionados["mes_rotulo"],
            "indicador": indicador,
            "regra": regra,
            "severidade": severidade,
            "valor": selecionados[coluna_valor],
            "limite": limites,
            "mensagem": mensagem,
        },
        columns=COLUNAS_ALERTA,
    )


def detectar_alertas(df: pd.DataFrame, params: ParametrosAlerta) -> pd.DataFrame:
    """Aplica as regras de alerta em todos os meses e devolve um evento por linha.

    Use a mart inteira: a regra de recorde do dólar depende do histórico anterior.
    """
    df = adicionar_faixa_meta(df, params)
    ipca12, ipca = df["ipca_acumulado_12m_pct"], df["ipca_mensal_pct"]
    var_dolar, dolar_fim = df["dolar_variacao_mes_pct"], df["dolar_fim_mes"]
    maximo_anterior = dolar_fim.cummax().shift(1)
    com_historico = dolar_fim.notna().cumsum() > params.meses_historico_recorde

    partes = [
        _eventos(
            df,
            ipca12 > df["teto_meta_pct"],
            "IPCA 12 meses",
            "Acima do teto da meta",
            "Crítico",
            "ipca_acumulado_12m_pct",
            df["teto_meta_pct"],
            "Inflação em 12 meses acima do limite superior da meta do CMN.",
        ),
        _eventos(
            df,
            (ipca12 > df["meta_inflacao_pct"]) & (ipca12 <= df["teto_meta_pct"]),
            "IPCA 12 meses",
            "Acima do centro da meta",
            "Atenção",
            "ipca_acumulado_12m_pct",
            df["meta_inflacao_pct"],
            "Inflação em 12 meses acima do centro da meta, dentro da tolerância.",
        ),
        _eventos(
            df,
            ipca12 < df["piso_meta_pct"],
            "IPCA 12 meses",
            "Abaixo do piso da meta",
            "Atenção",
            "ipca_acumulado_12m_pct",
            df["piso_meta_pct"],
            "Inflação em 12 meses abaixo do limite inferior da meta do CMN.",
        ),
        _eventos(
            df,
            ipca >= params.ipca_mensal_alto_pct,
            "IPCA no mês",
            "IPCA mensal elevado",
            "Atenção",
            "ipca_mensal_pct",
            params.ipca_mensal_alto_pct,
            f"IPCA de um único mês a partir de {params.ipca_mensal_alto_pct:.1f}%.",
        ),
        _eventos(
            df,
            ipca < 0,
            "IPCA no mês",
            "Deflação",
            "Informativo",
            "ipca_mensal_pct",
            0.0,
            "Variação de preços negativa no mês.",
        ),
        _eventos(
            df,
            var_dolar.abs() >= params.dolar_variacao_mes_pct,
            "Dólar",
            "Variação forte no mês",
            "Atenção",
            "dolar_variacao_mes_pct",
            params.dolar_variacao_mes_pct,
            f"Alta ou queda do dólar de {params.dolar_variacao_mes_pct:.0f}% ou mais no mês.",
        ),
        _eventos(
            df,
            (dolar_fim > maximo_anterior) & com_historico,
            "Dólar",
            "Nível recorde",
            "Atenção",
            "dolar_fim_mes",
            maximo_anterior,
            "Dólar de fim de mês acima de todos os meses anteriores da série.",
        ),
        _eventos(
            df,
            df["expectativa_ipca_12m_pct"] > df["teto_meta_pct"],
            "Expectativa IPCA",
            "Expectativa acima do teto da meta",
            "Atenção",
            "expectativa_ipca_12m_pct",
            df["teto_meta_pct"],
            "Mercado (Focus) espera inflação em 12 meses acima do teto da meta: "
            "sinal de expectativas desancoradas.",
        ),
        _eventos(
            df,
            df["juro_real_12m_pct"] < 0,
            "Juro real",
            "Juro real negativo",
            "Atenção",
            "juro_real_12m_pct",
            0.0,
            "Selic meta abaixo da inflação dos últimos 12 meses.",
        ),
    ]
    com_eventos = [p for p in partes if not p.empty]
    if not com_eventos:  # período calmo: nenhuma regra acionada
        return pd.DataFrame(columns=COLUNAS_ALERTA)
    alertas = pd.concat(com_eventos, ignore_index=True)
    ordem = {s: i for i, s in enumerate(SEVERIDADES)}
    return alertas.sort_values(
        ["primeiro_dia_mes", "severidade"],
        key=lambda s: s.map(ordem) if s.name == "severidade" else s,
        ascending=[False, True],
        ignore_index=True,
    )


def alertas_recentes(alertas: pd.DataFrame, fim: pd.Timestamp, meses: int = 3) -> pd.DataFrame:
    """Alertas dos últimos `meses` meses até `fim`, mais graves primeiro."""
    inicio = fim - pd.DateOffset(months=meses - 1)
    recentes = alertas[alertas["primeiro_dia_mes"].between(inicio, fim)]
    ordem = {s: i for i, s in enumerate(SEVERIDADES)}
    return recentes.sort_values(
        ["severidade", "primeiro_dia_mes"],
        key=lambda s: s.map(ordem) if s.name == "severidade" else s,
        ascending=[True, False],
        ignore_index=True,
    )
