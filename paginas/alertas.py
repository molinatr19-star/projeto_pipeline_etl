"""Página Alertas: todos os pontos críticos do período, com filtros, linha do tempo e regras."""

import streamlit as st

from pipeline_etl.dashboard.analise import INDICADORES_ALERTA, SEVERIDADES, parametros_do_config
from pipeline_etl.dashboard.estilo import (
    COR_SEVERIDADE,
    cabecalho,
    chips,
    formatar,
    largura_coluna,
    titulo_cartao,
)
from pipeline_etl.dashboard.graficos import CONFIG_PLOTLY, grafico_linha_tempo_alertas

SIMBOLO_TEXTO = {"Crítico": "■", "Atenção": "▲", "Informativo": "●"}

alertas = st.session_state["_alertas_periodo"]
params = parametros_do_config()

cabecalho(
    "Alertas",
    "Meses em que inflação, câmbio ou juros cruzaram limites definidos (meta do CMN e "
    "limites do projeto).",
)

contagem = alertas["severidade"].value_counts()
chips([(f"{s}:", str(int(contagem.get(s, 0))), COR_SEVERIDADE[s]) for s in SEVERIDADES])
if alertas.empty:
    st.success(
        "Nenhum alerta no período selecionado.",
        icon=":material/check_circle:",
    )
    st.stop()

# Indicador tem mais opções (5) que Severidade (3): coluna mais larga.
# wrap=True: dentro de colunas o st.pills fica numa linha só e rola na horizontal
# (cortava "Juro real" em telas menores); com wrap, os botões quebram de linha.
col_sev, col_ind = st.columns([2, 3], gap="medium")
severidades = col_sev.pills(
    "Severidade",
    SEVERIDADES,
    selection_mode="multi",
    default=SEVERIDADES,
    key="al_severidade",
    persist_state="session",
    wrap=True,
)
# Lista fixa (não depende do período), para o valor guardado entre páginas ser sempre válido.
indicadores = INDICADORES_ALERTA
escolhidos = col_ind.pills(
    "Indicador",
    indicadores,
    selection_mode="multi",
    default=indicadores,
    key="al_indicador",
    persist_state="session",
    wrap=True,
)
filtrados = alertas[
    alertas["severidade"].isin(severidades) & alertas["indicador"].isin(escolhidos)
].reset_index(drop=True)
if filtrados.empty:
    st.info("Nenhum alerta com os filtros escolhidos.", icon=":material/filter_alt_off:")
    st.stop()

with st.container(key="card_linha_tempo"):
    titulo_cartao(
        "Linha do tempo dos alertas",
        "Cada marcador é um mês em que a regra foi acionada. Quadrado = crítico, "
        "triângulo = atenção, círculo = informativo.",
    )
    st.plotly_chart(
        grafico_linha_tempo_alertas(filtrados),
        width="stretch",
        config=CONFIG_PLOTLY,
        alt="Linha do tempo com os meses em que cada regra de alerta foi acionada",
    )

# Tabela sem a descrição longa: o st.dataframe não quebra texto dentro da célula, e a
# descrição é a mesma em todas as linhas de uma regra (fica no gráfico, no CSV e em
# "Regras e limites"). Cada coluna tem a largura do seu texto mais longo, para nada
# aparecer cortado com "...".
tabela = filtrados.assign(
    severidade=filtrados["severidade"].map(lambda s: f"{SIMBOLO_TEXTO[s]} {s}"),
    valor=filtrados["valor"].map(lambda v: formatar(v, 2)),
    limite=filtrados["limite"].map(lambda v: formatar(v, 2)),
)[["mes_rotulo", "severidade", "indicador", "regra", "valor", "limite"]]
TITULOS = {
    "mes_rotulo": "Mês",
    "severidade": "Severidade",
    "indicador": "Indicador",
    "regra": "Regra",
    "valor": "Valor",
    "limite": "Limite",
}
larguras = {col: largura_coluna(tabela[col], titulo) for col, titulo in TITULOS.items()}
st.dataframe(
    tabela,
    hide_index=True,
    column_config={
        "mes_rotulo": st.column_config.TextColumn("Mês", width=larguras["mes_rotulo"], pinned=True),
        "severidade": st.column_config.TextColumn("Severidade", width=larguras["severidade"]),
        "indicador": st.column_config.TextColumn("Indicador", width=larguras["indicador"]),
        "regra": st.column_config.TextColumn(
            "Regra",
            width=larguras["regra"],
            help='Descrição de cada regra em "Regras e limites", abaixo da tabela.',
        ),
        "valor": st.column_config.TextColumn("Valor", width=larguras["valor"], alignment="right"),
        "limite": st.column_config.TextColumn(
            "Limite", width=larguras["limite"], alignment="right"
        ),
    },
    height=420,
    alt="Lista de alertas do período, do mais recente ao mais antigo",
)
st.download_button(
    "Baixar alertas (CSV)",
    filtrados.drop(columns=["primeiro_dia_mes"]).to_csv(index=False).encode("utf-8"),
    file_name="alertas_indicadores.csv",
    mime="text/csv",
    icon=":material/download:",
    on_click="ignore",
)

with st.expander("Regras e limites", icon=":material/rule:"):
    tolerancias = ", ".join(
        f"{ano}: {formatar(t, 1)} p.p." for ano, t in sorted(params.tolerancia_por_ano.items())
    )
    st.markdown(
        f"""
- **■ Crítico · IPCA 12 meses acima do teto da meta:** teto = centro da meta (SGS 13521) +
  tolerância de {formatar(params.tolerancia_padrao, 1)} p.p. (exceções: {tolerancias}).
- **▲ Atenção · IPCA 12 meses acima do centro da meta** (dentro da tolerância)
  ou **abaixo do piso**.
- **▲ Atenção · IPCA mensal elevado:** a partir de
  {formatar(params.ipca_mensal_alto_pct, 1)}% no mês.
- **▲ Atenção · Variação forte do dólar:** alta ou queda de
  {formatar(params.dolar_variacao_mes_pct, 0)}% ou mais no mês.
- **▲ Atenção · Dólar em nível recorde:** fim de mês acima de todos os meses anteriores (após
  {params.meses_historico_recorde} meses de histórico).
- **▲ Atenção · Juro real negativo:** Selic meta abaixo do IPCA de 12 meses.
- **● Informativo · Deflação:** IPCA do mês negativo.

Limites em `config/pipeline.yaml` (seção `painel`). A tolerância da meta segue as resoluções
do CMN e está marcada para verificação; os limites de IPCA mensal e dólar são escolhas do
projeto, não oficiais.
        """
    )
