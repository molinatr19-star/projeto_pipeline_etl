"""Página Dados: tabela mensal do período, downloads e informações do pipeline."""

import io

import streamlit as st

from pipeline_etl.dashboard.estilo import cabecalho

COLUNAS = {
    "mes_rotulo": st.column_config.TextColumn("Mês", pinned=True),
    "dias_uteis": st.column_config.NumberColumn("Dias úteis", format="%d"),
    "ipca_mensal_pct": st.column_config.NumberColumn("IPCA mês (%)", format="%.2f"),
    "ipca_acumulado_ano_pct": st.column_config.NumberColumn("IPCA no ano (%)", format="%.2f"),
    "ipca_acumulado_12m_pct": st.column_config.NumberColumn("IPCA 12 meses (%)", format="%.2f"),
    "expectativa_ipca_12m_pct": st.column_config.NumberColumn(
        "IPCA esperado 12m (%)", format="%.2f"
    ),
    "meta_inflacao_pct": st.column_config.NumberColumn("Meta inflação (%)", format="%.2f"),
    "teto_meta_pct": st.column_config.NumberColumn("Teto da meta (%)", format="%.2f"),
    "igpm_acumulado_12m_pct": st.column_config.NumberColumn("IGP-M 12 meses (%)", format="%.2f"),
    "selic_meta_fim_mes_pct": st.column_config.NumberColumn("Selic meta (% a.a.)", format="%.2f"),
    "cdi_fim_mes_pct": st.column_config.NumberColumn("CDI (% a.a.)", format="%.2f"),
    "juro_real_12m_pct": st.column_config.NumberColumn("Juro real (%)", format="%.2f"),
    "dolar_medio_mes": st.column_config.NumberColumn("Dólar médio (R$)", format="%.4f"),
    "dolar_fim_mes": st.column_config.NumberColumn("Dólar fim (R$)", format="%.4f"),
    "dolar_variacao_mes_pct": st.column_config.NumberColumn("Dólar var. (%)", format="%.2f"),
    "desocupacao_pct": st.column_config.NumberColumn("Desocupação (%)", format="%.1f"),
    "mes_completo": st.column_config.CheckboxColumn("Mês encerrado"),
}

df = st.session_state["_mart_periodo"]

cabecalho("Dados", "Tabela mensal consolidada (mart do pipeline) para o período selecionado.")
if df.empty:
    st.warning("Nenhum mês no período selecionado. Ajuste o período na barra lateral.")
    st.stop()

tabela = df.sort_values("primeiro_dia_mes", ascending=False)[list(COLUNAS)]
st.dataframe(
    tabela,
    column_config=COLUNAS,
    hide_index=True,
    height=520,
    alt="Indicadores mensais do período selecionado",
)

exportar = df.drop(columns=["mes_rotulo"])
parquet = io.BytesIO()
exportar.to_parquet(parquet, index=False)
nome = f"indicadores_{df['ano_mes'].iloc[0]}_a_{df['ano_mes'].iloc[-1]}"
with st.container(horizontal=True):
    st.download_button(
        "Baixar CSV",
        exportar.to_csv(index=False).encode("utf-8"),
        file_name=f"{nome}.csv",
        mime="text/csv",
        icon=":material/download:",
    )
    st.download_button(
        "Baixar Parquet",
        parquet.getvalue(),
        file_name=f"{nome}.parquet",
        mime="application/octet-stream",
        icon=":material/download:",
    )

with st.expander("Sobre os dados e o pipeline", icon=":material/info:"):
    st.markdown(
        """
- **Fontes:** API SGS do Banco Central (IPCA 433, meta Selic 432, dólar venda 1) e planilha de
  feriados nacionais da ANBIMA.
- **Fluxo:** extração (raw) -> staging em pandas -> warehouse DuckDB (modelo em estrela) ->
  exportação `data/processed/indicadores_mensal`.
- **Qualidade:** 28 checagens automáticas (chaves, nulos, faixas, conciliação entre camadas e
  cruzamento entre fontes). Se uma falhar, nada é publicado.
- **Valores vazios** são intencionais: indicador ainda não publicado (ex.: IPCA do mês corrente)
  ou janela incompleta (ex.: IPCA 12 meses no início da série).
- **CSV:** vírgula como separador e ponto decimal.
- **Atualizar:** rode `pipeline-etl` e recarregue a página.
        """
    )
