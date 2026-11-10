"""Gráficos Plotly do painel (fundo transparente para herdar o tema escuro).

Regras seguidas (skill de dataviz): um eixo por gráfico (sem eixo duplo), linhas de 2px,
legenda sempre que houver mais de uma série, rótulo direto só no último valor,
cor fixa por indicador e texto sempre nas cores de texto, nunca na cor da série.
"""

import pandas as pd
import plotly.graph_objects as go

from pipeline_etl.dashboard.dados import MESES_ABREV
from pipeline_etl.dashboard.estilo import (
    COR_CARTAO,
    COR_CRITICO,
    COR_DIAS_UTEIS,
    COR_DOLAR,
    COR_EIXO,
    COR_EXPECTATIVA,
    COR_GRADE,
    COR_IGPM,
    COR_IPCA,
    COR_JURO_REAL,
    COR_MUTED,
    COR_NEGATIVO,
    COR_POSITIVO,
    COR_SELIC,
    COR_SEVERIDADE,
    COR_TEXTO,
    COR_TEXTO_SEC,
    ESCALA_SEQUENCIAL,
    NEON_AZUL,
    SIMBOLO_SEVERIDADE,
    formatar,
)

CONFIG_PLOTLY = {"displayModeBar": False}

# (coluna, nome na legenda, cor) do gráfico de juros
SERIES_JUROS = [
    ("selic_meta_fim_mes_pct", "Selic meta", COR_SELIC),
    ("ipca_acumulado_12m_pct", "IPCA 12 meses", COR_IPCA),
    ("juro_real_12m_pct", "Juro real", COR_JURO_REAL),
]


def aplicar_layout(fig: go.Figure, altura: int = 340, cor_destaque: str = NEON_AZUL) -> go.Figure:
    """Estilo comum: grade discreta, eixos recessivos, tooltip escuro com borda colorida."""
    fig.update_layout(
        height=altura,
        margin=dict(l=8, r=16, t=8, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, Segoe UI, sans-serif", size=13, color=COR_TEXTO_SEC),
        hoverlabel=dict(
            bgcolor="#0b0d14", bordercolor=cor_destaque, font=dict(color=COR_TEXTO, size=13)
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            x=0,
            title=None,
            font=dict(color=COR_TEXTO_SEC),
        ),
        bargap=0.25,
        separators=",.",  # padrão brasileiro: 1.500 e 7,5
    )
    fig.update_xaxes(
        gridcolor=COR_GRADE, linecolor=COR_EIXO, zeroline=False, tickfont=dict(color=COR_MUTED)
    )
    fig.update_yaxes(
        gridcolor=COR_GRADE, linecolor=COR_EIXO, zeroline=False, tickfont=dict(color=COR_MUTED)
    )
    return fig


def _eixo_mensal(fig: go.Figure) -> None:
    """Eixo de datas mensal com rótulos numéricos (mm/aaaa), sem nomes de mês em inglês."""
    fig.update_xaxes(tickformat="%m/%Y", hoverformat="%m/%Y", showgrid=False)


def _rotulo_final(
    fig: go.Figure, serie: pd.DataFrame, coluna: str, cor: str, casas: int, sufixo: str
) -> None:
    """Rótulo direto no último ponto: ponto na cor da série, número na cor do texto."""
    ultimo = serie.iloc[-1]
    fig.add_annotation(
        x=ultimo["primeiro_dia_mes"],
        y=ultimo[coluna],
        text=f"<span style='color:{cor}'>●</span> {formatar(ultimo[coluna], casas, sufixo)}",
        showarrow=False,
        xanchor="left",
        xshift=6,
        font=dict(color=COR_TEXTO, size=12),
    )


def grafico_juros(df: pd.DataFrame) -> go.Figure:
    """Selic meta, IPCA 12 meses e juro real: mesma unidade (%), um só eixo."""
    fig = go.Figure()
    for coluna, nome, cor in SERIES_JUROS:
        serie = df[["primeiro_dia_mes", "mes_rotulo", coluna]].dropna(subset=[coluna])
        if serie.empty:
            continue
        fig.add_scatter(
            x=serie["primeiro_dia_mes"],
            y=serie[coluna],
            name=nome,
            mode="lines",
            line=dict(color=cor, width=2),
            customdata=serie["mes_rotulo"],
            hovertemplate=f"{nome}: %{{y:.2f}}%<extra></extra>",
        )
        _rotulo_final(fig, serie, coluna, cor, 2, "%")
    fig.add_hline(y=0, line=dict(color=COR_EIXO, width=1))
    fig.update_layout(hovermode="x unified", margin=dict(r=70))
    fig.update_yaxes(ticksuffix="%")
    _eixo_mensal(fig)
    return aplicar_layout(fig, altura=380)


def grafico_barras_sinal(
    df: pd.DataFrame,
    coluna: str,
    nome: str,
    rotulo_positivo: str,
    rotulo_negativo: str,
    altura: int = 320,
    destaques: pd.Series | None = None,
    rotulo_destaque: str = "",
) -> go.Figure:
    """Barras mensais coloridas pelo sinal (polaridade): positivo quente, negativo frio.

    `destaques` (máscara alinhada a `df`) marca meses de alerta com um losango acima/abaixo
    da barra, na cor de status "Atenção" e com legenda própria.
    """
    serie = df[["primeiro_dia_mes", "mes_rotulo", coluna]].dropna(subset=[coluna])
    fig = go.Figure()
    for rotulo, cor, filtro in [
        (rotulo_positivo, COR_POSITIVO, serie[coluna] >= 0),
        (rotulo_negativo, COR_NEGATIVO, serie[coluna] < 0),
    ]:
        parte = serie[filtro]
        if parte.empty:
            continue
        fig.add_bar(
            x=parte["primeiro_dia_mes"],
            y=parte[coluna],
            name=rotulo,
            marker=dict(color=cor, line=dict(color=COR_CARTAO, width=1)),
            customdata=parte["mes_rotulo"],
            hovertemplate=f"<b>%{{customdata}}</b><br>{nome}: %{{y:.2f}}%<extra></extra>",
        )
    if destaques is not None:
        marcados = df[destaques.fillna(False).astype(bool)].dropna(subset=[coluna])
        if not marcados.empty:
            folga = serie[coluna].abs().max() * 0.08
            fig.add_scatter(
                x=marcados["primeiro_dia_mes"],
                y=marcados[coluna] + marcados[coluna].apply(lambda v: folga if v >= 0 else -folga),
                mode="markers",
                name=rotulo_destaque,
                marker=dict(
                    symbol="diamond",
                    size=9,
                    color=COR_SEVERIDADE["Atenção"],
                    line=dict(color=COR_CARTAO, width=2),
                ),
                customdata=marcados[["mes_rotulo", coluna]].values,
                hovertemplate=(
                    f"<b>%{{customdata[0]}}</b><br>{rotulo_destaque}: %{{customdata[1]:.2f}}%"
                    "<extra></extra>"
                ),
            )
    fig.add_hline(y=0, line=dict(color=COR_EIXO, width=1))
    fig.update_layout(barmode="relative", barcornerradius=3)
    fig.update_yaxes(ticksuffix="%")
    _eixo_mensal(fig)
    return aplicar_layout(fig, altura=altura)


def ipca_por_ano(df: pd.DataFrame) -> pd.DataFrame:
    """IPCA acumulado de cada ano: valor do último mês publicado; ano incompleto sinalizado."""
    com_ipca = df.dropna(subset=["ipca_acumulado_ano_pct"])
    ultimos = com_ipca.groupby("ano", as_index=False).last()
    ultimos["completo"] = ultimos["mes"] == 12
    ultimos["rotulo_ano"] = [
        str(ano) if completo else f"{ano}*"
        for ano, completo in zip(ultimos["ano"], ultimos["completo"], strict=True)
    ]
    return ultimos[["ano", "rotulo_ano", "mes_rotulo", "ipca_acumulado_ano_pct", "completo"]]


def grafico_ipca_anual(df: pd.DataFrame) -> go.Figure:
    """Barras com o IPCA acumulado em cada ano (ano corrente até o último mês publicado)."""
    anual = ipca_por_ano(df)
    fig = go.Figure(
        go.Bar(
            x=anual["rotulo_ano"],
            y=anual["ipca_acumulado_ano_pct"],
            marker=dict(
                color=COR_IPCA,
                opacity=[1.0 if c else 0.55 for c in anual["completo"]],
                cornerradius=4,
            ),
            text=[formatar(v, 2, "%") for v in anual["ipca_acumulado_ano_pct"]],
            textposition="outside",
            textfont=dict(color=COR_TEXTO_SEC, size=12),
            cliponaxis=False,
            customdata=anual["mes_rotulo"],
            hovertemplate="<b>%{x}</b><br>IPCA acumulado até %{customdata}: %{y:.2f}%"
            "<extra></extra>",
            showlegend=False,
        )
    )
    fig.update_xaxes(type="category", showgrid=False, tickfont=dict(color=COR_TEXTO_SEC))
    fig.update_yaxes(ticksuffix="%", range=[0, anual["ipca_acumulado_ano_pct"].max() * 1.2])
    return aplicar_layout(fig, altura=320, cor_destaque=COR_IPCA)


def grafico_linha_unica(
    df: pd.DataFrame,
    coluna: str,
    nome: str,
    cor: str,
    casas: int,
    sufixo: str,
    prefixo_hover: str = "",
    area: bool = False,
    altura: int = 320,
) -> go.Figure:
    """Uma série no tempo (o título do cartão dá o nome; sem legenda)."""
    serie = df[["primeiro_dia_mes", "mes_rotulo", coluna]].dropna(subset=[coluna])
    fig = go.Figure(
        go.Scatter(
            x=serie["primeiro_dia_mes"],
            y=serie[coluna],
            name=nome,
            mode="lines",
            line=dict(color=cor, width=2),
            fill="tozeroy" if area else None,
            fillcolor=f"rgba({int(cor[1:3], 16)},{int(cor[3:5], 16)},{int(cor[5:7], 16)},0.12)",
            customdata=serie["mes_rotulo"],
            hovertemplate=(
                f"<b>%{{customdata}}</b><br>{nome}: {prefixo_hover}%{{y:.{casas}f}}{sufixo}"
                "<extra></extra>"
            ),
            showlegend=False,
        )
    )
    if not serie.empty:
        _rotulo_final(fig, serie, coluna, cor, casas, sufixo)
    if area:
        fig.add_hline(y=0, line=dict(color=COR_EIXO, width=1))
    fig.update_layout(margin=dict(r=70))
    fig.update_yaxes(ticksuffix=sufixo)
    _eixo_mensal(fig)
    return aplicar_layout(fig, altura=altura, cor_destaque=cor)


def grafico_dolar(df: pd.DataFrame) -> go.Figure:
    """Dólar médio do mês (linha cheia) e de fim de mês (tracejada): mesma unidade, um eixo."""
    serie = df.dropna(subset=["dolar_medio_mes"])
    fig = go.Figure()
    fig.add_scatter(
        x=serie["primeiro_dia_mes"],
        y=serie["dolar_medio_mes"],
        name="Média do mês",
        mode="lines",
        line=dict(color=COR_DOLAR, width=2),
        hovertemplate="Média do mês: R$ %{y:.4f}<extra></extra>",
    )
    fig.add_scatter(
        x=serie["primeiro_dia_mes"],
        y=serie["dolar_fim_mes"],
        name="Fim do mês",
        mode="lines",
        line=dict(color=COR_DOLAR, width=2, dash="dot"),
        hovertemplate="Fim do mês: R$ %{y:.4f}<extra></extra>",
    )
    if not serie.empty:
        _rotulo_final(fig, serie, "dolar_fim_mes", COR_DOLAR, 2, "")
    fig.update_layout(hovermode="x unified", margin=dict(r=70))
    fig.update_yaxes(tickprefix="R$ ")
    _eixo_mensal(fig)
    return aplicar_layout(fig, altura=380, cor_destaque=COR_DOLAR)


def grafico_dias_uteis_mes(df: pd.DataFrame, altura: int = 320) -> go.Figure:
    """Dias úteis de cada mês (calendário bancário ANBIMA)."""
    fig = go.Figure(
        go.Bar(
            x=df["primeiro_dia_mes"],
            y=df["dias_uteis"],
            marker=dict(color=COR_DIAS_UTEIS, line=dict(color=COR_CARTAO, width=1)),
            customdata=df["mes_rotulo"],
            hovertemplate="<b>%{customdata}</b><br>Dias úteis: %{y}<extra></extra>",
            showlegend=False,
        )
    )
    fig.update_layout(barcornerradius=3)
    fig.update_yaxes(range=[0, 25], dtick=5)
    _eixo_mensal(fig)
    return aplicar_layout(fig, altura=altura)


def tabela_dias_uteis(df: pd.DataFrame) -> pd.DataFrame:
    """Dias úteis em grade ano x mês (linhas = anos, colunas = jan..dez)."""
    grade = df.pivot_table(index="ano", columns="mes", values="dias_uteis", aggfunc="sum")
    grade = grade.reindex(columns=range(1, 13))
    grade.columns = MESES_ABREV
    return grade


def grafico_mapa_dias_uteis(df: pd.DataFrame) -> go.Figure:
    """Mapa de calor ano x mês com o número de dias úteis escrito em cada célula."""
    grade = tabela_dias_uteis(df)
    fig = go.Figure(
        go.Heatmap(
            z=grade.values,
            x=grade.columns,
            y=[str(ano) for ano in grade.index],
            colorscale=ESCALA_SEQUENCIAL,
            xgap=2,
            ygap=2,
            texttemplate="%{z:.0f}",
            textfont=dict(color=COR_TEXTO, size=12),
            hovertemplate="<b>%{x}/%{y}</b><br>Dias úteis: %{z:.0f}<extra></extra>",
            colorbar=dict(
                title=dict(text="dias", font=dict(color=COR_MUTED)),
                tickfont=dict(color=COR_MUTED),
                thickness=10,
                outlinewidth=0,
            ),
        )
    )
    fig.update_yaxes(autorange="reversed", showgrid=False, type="category")
    fig.update_xaxes(showgrid=False, side="top")
    return aplicar_layout(fig, altura=max(260, 34 * len(grade) + 60))


def grafico_dias_uteis_ano(df: pd.DataFrame) -> go.Figure:
    """Total de dias úteis por ano; ano incompleto no recorte aparece mais claro e com *."""
    anual = df.groupby("ano").agg(dias_uteis=("dias_uteis", "sum"), meses=("mes", "count"))
    completo = anual["meses"] == 12
    rotulos = [str(a) if c else f"{a}*" for a, c in zip(anual.index, completo, strict=True)]
    fig = go.Figure(
        go.Bar(
            x=rotulos,
            y=anual["dias_uteis"],
            marker=dict(
                color=COR_DIAS_UTEIS, opacity=[1.0 if c else 0.5 for c in completo], cornerradius=4
            ),
            text=anual["dias_uteis"],
            textposition="outside",
            textfont=dict(color=COR_TEXTO_SEC, size=12),
            cliponaxis=False,
            customdata=anual["meses"],
            hovertemplate="<b>%{x}</b><br>Dias úteis: %{y}<br>Meses no recorte: %{customdata}"
            "<extra></extra>",
            showlegend=False,
        )
    )
    fig.update_xaxes(type="category", showgrid=False, tickfont=dict(color=COR_TEXTO_SEC))
    fig.update_yaxes(range=[0, anual["dias_uteis"].max() * 1.15])
    return aplicar_layout(fig, altura=320)


def grafico_ipca_meta(df: pd.DataFrame) -> go.Figure:
    """IPCA 12 meses contra a meta: faixa de tolerância sombreada, centro tracejado e
    quadrados vermelhos nos meses acima do teto. `df` precisa de piso/teto (analise)."""
    base = df.dropna(subset=["meta_inflacao_pct"])
    fig = go.Figure()
    fig.add_scatter(
        x=base["primeiro_dia_mes"],
        y=base["teto_meta_pct"],
        mode="lines",
        line=dict(width=0),
        line_shape="hv",
        hoverinfo="skip",
        showlegend=False,
    )
    fig.add_scatter(
        x=base["primeiro_dia_mes"],
        y=base["piso_meta_pct"],
        mode="lines",
        line=dict(width=0),
        line_shape="hv",
        fill="tonexty",
        fillcolor="rgba(180,184,200,0.12)",
        name="Tolerância da meta",
        customdata=base[["mes_rotulo", "teto_meta_pct"]].values,
        hovertemplate="Tolerância: %{y:.2f}% a %{customdata[1]:.2f}%<extra></extra>",
    )
    fig.add_scatter(
        x=base["primeiro_dia_mes"],
        y=base["meta_inflacao_pct"],
        mode="lines",
        line_shape="hv",
        line=dict(color=COR_TEXTO_SEC, width=1.5, dash="dash"),
        name="Centro da meta",
        hovertemplate="Centro da meta: %{y:.2f}%<extra></extra>",
    )
    ipca = df.dropna(subset=["ipca_acumulado_12m_pct"])
    fig.add_scatter(
        x=ipca["primeiro_dia_mes"],
        y=ipca["ipca_acumulado_12m_pct"],
        mode="lines",
        line=dict(color=COR_IPCA, width=2),
        name="IPCA 12 meses",
        hovertemplate="IPCA 12 meses: %{y:.2f}%<extra></extra>",
    )
    acima = ipca[ipca["ipca_acumulado_12m_pct"] > ipca["teto_meta_pct"]]
    if not acima.empty:
        fig.add_scatter(
            x=acima["primeiro_dia_mes"],
            y=acima["ipca_acumulado_12m_pct"],
            mode="markers",
            marker=dict(
                symbol="square", size=8, color=COR_CRITICO, line=dict(color=COR_CARTAO, width=2)
            ),
            name="Acima do teto (crítico)",
            hovertemplate="Acima do teto: %{y:.2f}%<extra></extra>",
        )
    if not ipca.empty:
        _rotulo_final(fig, ipca, "ipca_acumulado_12m_pct", COR_IPCA, 2, "%")
    fig.update_layout(hovermode="x unified", margin=dict(r=70))
    fig.update_yaxes(ticksuffix="%")
    _eixo_mensal(fig)
    return aplicar_layout(fig, altura=380, cor_destaque=COR_IPCA)


def grafico_linha_tempo_alertas(alertas: pd.DataFrame) -> go.Figure:
    """Linha do tempo: um marcador por alerta (mês x regra). Severidade em cor + símbolo."""
    fig = go.Figure()
    regras = list(dict.fromkeys(alertas.sort_values("indicador")["regra"]))
    for severidade, cor in COR_SEVERIDADE.items():
        parte = alertas[alertas["severidade"] == severidade]
        if parte.empty:
            continue
        fig.add_scatter(
            x=parte["primeiro_dia_mes"],
            y=parte["regra"],
            mode="markers",
            name=severidade,
            marker=dict(
                symbol=SIMBOLO_SEVERIDADE[severidade],
                size=10,
                color=cor,
                line=dict(color=COR_CARTAO, width=2),
            ),
            customdata=parte[["mes_rotulo", "mensagem", "valor"]].values,
            hovertemplate=(
                f"<b>%{{customdata[0]}}</b> · {severidade}<br>%{{y}}<br>"
                "Valor: %{customdata[2]:.2f}<br>%{customdata[1]}<extra></extra>"
            ),
        )
    fig.update_yaxes(
        categoryorder="array",
        categoryarray=regras,
        showgrid=True,
        tickfont=dict(color=COR_TEXTO_SEC),
    )
    _eixo_mensal(fig)
    return aplicar_layout(fig, altura=max(280, 46 * len(regras) + 80))


def grafico_ipca_igpm(df: pd.DataFrame) -> go.Figure:
    """IPCA e IGP-M acumulados em 12 meses: mesma unidade, um eixo."""
    fig = go.Figure()
    for coluna, nome, cor in [
        ("ipca_acumulado_12m_pct", "IPCA 12 meses", COR_IPCA),
        ("igpm_acumulado_12m_pct", "IGP-M 12 meses", COR_IGPM),
    ]:
        serie = df[["primeiro_dia_mes", coluna]].dropna(subset=[coluna])
        if serie.empty:
            continue
        fig.add_scatter(
            x=serie["primeiro_dia_mes"],
            y=serie[coluna],
            name=nome,
            mode="lines",
            line=dict(color=cor, width=2),
            hovertemplate=f"{nome}: %{{y:.2f}}%<extra></extra>",
        )
        _rotulo_final(fig, serie, coluna, cor, 2, "%")
    fig.add_hline(y=0, line=dict(color=COR_EIXO, width=1))
    fig.update_layout(hovermode="x unified", margin=dict(r=70))
    fig.update_yaxes(ticksuffix="%")
    _eixo_mensal(fig)
    return aplicar_layout(fig, altura=360, cor_destaque=COR_IPCA)


def grafico_previsto_realizado(comparacao: pd.DataFrame) -> go.Figure:
    """IPCA 12 meses realizado (linha cheia) x o que o Focus esperava 12 meses antes
    (tracejada). Mesma cor (mesmo indicador); a linha tracejada é a codificação extra."""
    fig = go.Figure()
    for coluna, nome, tracejado in [
        ("realizado_pct", "IPCA 12 meses realizado", None),
        ("esperado_pct", "Esperado 12 meses antes (Focus)", "dot"),
    ]:
        serie = comparacao.dropna(subset=[coluna])
        if serie.empty:
            continue
        fig.add_scatter(
            x=serie["primeiro_dia_mes"],
            y=serie[coluna],
            name=nome,
            mode="lines",
            line=dict(color=COR_EXPECTATIVA, width=2, dash=tracejado),
            hovertemplate=f"{nome}: %{{y:.2f}}%<extra></extra>",
        )
    fig.update_layout(hovermode="x unified")
    fig.update_yaxes(ticksuffix="%")
    _eixo_mensal(fig)
    return aplicar_layout(fig, altura=360, cor_destaque=COR_EXPECTATIVA)
