"""Relatório executivo em HTML (um arquivo, sem dependências externas, pronto para imprimir).

Abre em qualquer navegador; para PDF, use Imprimir > Salvar como PDF.
Tema claro de propósito: o relatório é feito para leitura e impressão.
"""

from html import escape

import pandas as pd

from pipeline_etl.dashboard.estilo import formatar

ICONE_SEVERIDADE = {"Crítico": "■", "Atenção": "▲", "Informativo": "●"}
CLASSE_SEVERIDADE = {"Crítico": "critico", "Atenção": "atencao", "Informativo": "info"}

CSS = """
body{font-family:"Segoe UI",Arial,sans-serif;color:#1b1d24;max-width:960px;margin:32px auto;
padding:0 24px;line-height:1.45}
h1{font-size:26px;margin:0} h2{font-size:18px;margin:28px 0 8px;border-bottom:2px solid #2a6fc9;
padding-bottom:4px} .sub{color:#555b6e;margin:4px 0 18px}
table{border-collapse:collapse;width:100%;font-size:13px;margin:6px 0 4px}
th,td{border-bottom:1px solid #e1e3ea;padding:6px 8px;text-align:right;white-space:nowrap}
th{background:#f3f5f9;color:#33384a} td:first-child,th:first-child{text-align:left}
td.texto{text-align:left;white-space:normal}
.kpis{display:flex;flex-wrap:wrap;gap:10px} .kpi{flex:1 1 150px;border:1px solid #d5d9e4;
border-radius:10px;padding:10px 12px} .kpi b{display:block;font-size:22px;color:#1b1d24}
.kpi span{color:#555b6e;font-size:12px}
.critico{color:#b02727;font-weight:700} .atencao{color:#9a6a00;font-weight:700}
.info{color:#4b5163;font-weight:700} .nota{color:#555b6e;font-size:12px}
@media print{body{margin:0} h2{break-after:avoid} tr{break-inside:avoid}}
"""


def _num(valor: float | None, casas: int, sufixo: str = "") -> str:
    return escape(formatar(valor, casas, sufixo))


def _delta(delta: float | None, tipo: str) -> str:
    if delta is None or pd.isna(delta):
        return "-"
    seta = "▲" if delta > 0 else ("▼" if delta < 0 else "=")
    if tipo == "taxa":
        return f"{seta} {formatar(abs(delta), 2)} p.p."
    if tipo == "contagem":
        return f"{seta} {formatar(abs(delta), 0)}"
    return f"{seta} {formatar(abs(delta), 4)}"


def _casas(tipo: str) -> int:
    return {"taxa": 2, "nivel": 4, "contagem": 0}[tipo]


def tabela_comparacao(comparacao: pd.DataFrame) -> str:
    linhas = []
    for _, c in comparacao.iterrows():
        casas = _casas(c["tipo"])
        linhas.append(
            "<tr>"
            f"<td>{escape(c['indicador'])} <span class='nota'>({escape(c['unidade'])})</span></td>"
            f"<td><b>{_num(c['valor'], casas)}</b></td>"
            f"<td>{_num(c['base_mom'], casas)}</td><td>{_delta(c['delta_mom'], c['tipo'])}</td>"
            f"<td>{_num(c['var_mom_pct'], 1, '%')}</td>"
            f"<td>{_num(c['base_yoy'], casas)}</td><td>{_delta(c['delta_yoy'], c['tipo'])}</td>"
            f"<td>{_num(c['var_yoy_pct'], 1, '%')}</td>"
            "</tr>"
        )
    return (
        "<table><tr><th>Indicador</th><th>Valor</th><th>Mês anterior</th><th>Δ MoM</th>"
        "<th>Var. % MoM</th><th>12 meses antes</th><th>Δ YoY</th><th>Var. % YoY</th></tr>"
        + "".join(linhas)
        + "</table>"
    )


def tabela_alertas(alertas: pd.DataFrame, limite_linhas: int = 40) -> str:
    if alertas.empty:
        return "<p>Nenhum alerta no período.</p>"
    linhas = []
    for _, a in alertas.head(limite_linhas).iterrows():
        classe = CLASSE_SEVERIDADE[a["severidade"]]
        icone = ICONE_SEVERIDADE[a["severidade"]]
        linhas.append(
            f"<tr><td>{escape(a['mes_rotulo'])}</td>"
            f"<td class='texto {classe}'>{icone} {escape(a['severidade'])}</td>"
            f"<td class='texto'>{escape(a['indicador'])}</td>"
            f"<td class='texto'>{escape(a['regra'])}</td>"
            f"<td>{_num(a['valor'], 2)}</td><td>{_num(a['limite'], 2)}</td></tr>"
        )
    extra = (
        f"<p class='nota'>Mostrando os {limite_linhas} mais recentes de {len(alertas)}. "
        "A lista completa está na página Alertas do painel.</p>"
        if len(alertas) > limite_linhas
        else ""
    )
    return (
        "<table><tr><th>Mês</th><th>Severidade</th><th>Indicador</th><th>Regra</th>"
        "<th>Valor</th><th>Limite</th></tr>" + "".join(linhas) + "</table>" + extra
    )


def tabela_mensal(df: pd.DataFrame) -> str:
    colunas = [
        ("mes_rotulo", "Mês", None),
        ("ipca_mensal_pct", "IPCA mês %", 2),
        ("ipca_acumulado_12m_pct", "IPCA 12m %", 2),
        ("meta_inflacao_pct", "Meta %", 2),
        ("expectativa_ipca_12m_pct", "Focus 12m %", 2),
        ("igpm_acumulado_12m_pct", "IGP-M 12m %", 2),
        ("selic_meta_fim_mes_pct", "Selic %", 2),
        ("juro_real_12m_pct", "Juro real %", 2),
        ("dolar_medio_mes", "Dólar médio", 4),
        ("dolar_fim_mes", "Dólar fim", 4),
        ("desocupacao_pct", "Desoc. %", 1),
        ("dias_uteis", "Dias úteis", 0),
    ]
    cabecalho = "".join(f"<th>{escape(titulo)}</th>" for _, titulo, _ in colunas)
    corpo = []
    for _, linha in df.sort_values("primeiro_dia_mes", ascending=False).iterrows():
        celulas = [
            f"<td>{escape(str(linha[col]))}</td>"
            if casas is None
            else f"<td>{_num(linha[col], casas)}</td>"
            for col, _, casas in colunas
        ]
        corpo.append("<tr>" + "".join(celulas) + "</tr>")
    return f"<table><tr>{cabecalho}</tr>{''.join(corpo)}</table>"


def gerar_relatorio_html(
    periodo: pd.DataFrame,
    comparacao: pd.DataFrame,
    referencia_rotulo: str,
    alertas_periodo: pd.DataFrame,
    origem: str,
    gerado_em: pd.Timestamp,
) -> str:
    """Monta o relatório executivo do período selecionado no painel."""
    inicio, fim = periodo["mes_rotulo"].iloc[0], periodo["mes_rotulo"].iloc[-1]
    destaque = comparacao.set_index("coluna")
    kpis = [
        ("IPCA 12 meses", "ipca_acumulado_12m_pct", 2, "%"),
        ("Selic meta", "selic_meta_fim_mes_pct", 2, "% a.a."),
        ("Juro real", "juro_real_12m_pct", 2, "%"),
        ("Dólar fim do mês", "dolar_fim_mes", 4, ""),
    ]
    cartoes = "".join(
        f"<div class='kpi'><span>{escape(nome)}</span>"
        f"<b>{_num(destaque.loc[col, 'valor'], casas, suf)}</b>"
        f"<span>YoY: {escape(_delta(destaque.loc[col, 'delta_yoy'], destaque.loc[col, 'tipo']))}"
        "</span></div>"
        for nome, col, casas, suf in kpis
    )
    contagem = alertas_periodo["severidade"].value_counts()
    resumo_alertas = " · ".join(
        f"<span class='{CLASSE_SEVERIDADE[s]}'>{ICONE_SEVERIDADE[s]} {s}: "
        f"{int(contagem.get(s, 0))}</span>"
        for s in ["Crítico", "Atenção", "Informativo"]
    )
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Relatório de indicadores econômicos</title><style>{CSS}</style></head><body>
<h1>Relatório de indicadores econômicos</h1>
<p class="sub">Período: <b>{escape(inicio)} a {escape(fim)}</b> · Mês de referência das
comparações: <b>{escape(referencia_rotulo)}</b> · Gerado em {gerado_em:%d/%m/%Y %H:%M}</p>

<h2>Resumo em {escape(referencia_rotulo)}</h2>
<div class="kpis">{cartoes}</div>

<h2>Comparação com períodos anteriores</h2>
<p class="nota">MoM: contra o mês anterior. YoY: contra o mesmo mês do ano anterior.
Taxas comparadas em pontos percentuais (p.p.); "Var. %" é a variação relativa.</p>
{tabela_comparacao(comparacao)}

<h2>Alertas no período</h2>
<p>{resumo_alertas}</p>
{tabela_alertas(alertas_periodo)}

<h2>Dados mensais</h2>
{tabela_mensal(periodo)}

<h2>Fontes e método</h2>
<p class="nota">Banco Central do Brasil (SGS: IPCA 433, meta Selic 432, dólar venda 1, meta de
inflação 13521, IGP-M 189, CDI 4389, desocupação 24369; Boletim Focus para a expectativa de
IPCA em 12 meses) e ANBIMA (feriados nacionais). Dados processados pelo pipeline ETL do projeto
(leitura de {escape(origem)}). IPCA acumulado composto a partir das taxas mensais; juro real é
aproximação: (1 + Selic meta) / (1 + IPCA 12 meses) - 1. Tolerância da meta conforme o CMN
(configurada no projeto). Limites de "IPCA mensal elevado" e "variação forte do dólar" são
definidos pelo projeto, não são oficiais.</p>
</body></html>"""
