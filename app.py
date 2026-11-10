"""Painel de indicadores econômicos gerado pelo pipeline ETL (IPCA, Selic, dólar e dias úteis).

Executar na raiz do projeto (depois de rodar o pipeline ao menos uma vez):
    .venv\\Scripts\\python.exe -m streamlit run app.py

Estrutura:
- app.py: configuração, estilo, filtro de período e exportação (barra lateral, valem para
  todas as páginas) e navegação;
- paginas/: Visão geral, Inflação e juros, Câmbio, Dias úteis, Comparador, Alertas e Dados;
- src/pipeline_etl/dashboard/: dados, análises (comparações e alertas), relatório, estilo e
  gráficos compartilhados.

Fonte dos dados: data/processed/indicadores_mensal.parquet (exportação final do pipeline);
se o arquivo não existir, a tabela marts.mart_indicadores_mensal do warehouse DuckDB.
"""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# No Streamlit Community Cloud o pacote não é instalado com `pip install -e .`:
# coloca src/ no caminho de importação (localmente não muda nada).
SRC = Path(__file__).resolve().parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pipeline_etl.dashboard.analise import (  # noqa: E402
    adicionar_faixa_meta,
    comparar,
    detectar_alertas,
    mes_referencia_padrao,
    parametros_do_config,
)
from pipeline_etl.dashboard.dados import (  # noqa: E402
    Mart,
    barra_lateral,
    dias_desde_carga,
    obter_mart,
    rotulo_mes,
)
from pipeline_etl.dashboard.estilo import aplicar_css  # noqa: E402
from pipeline_etl.dashboard.relatorio import gerar_relatorio_html  # noqa: E402
from pipeline_etl.utils.configuracao import carregar_config  # noqa: E402

st.set_page_config(
    page_title="Indicadores econômicos",
    page_icon=":material/monitoring:",
    layout="wide",
)
aplicar_css()

try:
    mart = obter_mart()
except FileNotFoundError:
    st.error(
        "Rode o pipeline ao menos uma vez para gerar os dados: `pipeline-etl` "
        "(ou `python -m pipeline_etl.orquestracao.pipeline`). Depois recarregue esta página.",
        title="Dados ainda não gerados",
        icon=":material/database_off:",
    )
    st.stop()

paginas = st.navigation(
    [
        st.Page(
            "paginas/visao_geral.py", title="Visão geral", icon=":material/dashboard:", default=True
        ),
        st.Page("paginas/inflacao_juros.py", title="Inflação e juros", icon=":material/percent:"),
        st.Page("paginas/cambio.py", title="Câmbio", icon=":material/currency_exchange:"),
        st.Page("paginas/dias_uteis.py", title="Dias úteis", icon=":material/calendar_month:"),
        st.Page("paginas/mercado.py", title="Mercado e expectativas", icon=":material/insights:"),
        st.Page("paginas/comparador.py", title="Comparador", icon=":material/compare_arrows:"),
        st.Page("paginas/alertas.py", title="Alertas", icon=":material/notifications:"),
        st.Page("paginas/tabela.py", title="Dados", icon=":material/table_view:"),
    ]
)

# Mart inteira com a faixa da meta (piso/teto) e todos os alertas: as páginas filtram depois.
parametros = parametros_do_config()
mart = Mart(adicionar_faixa_meta(mart.dados, parametros), mart.origem)
alertas = detectar_alertas(mart.dados, parametros)

# Filtro de período na barra lateral: vale para todas as páginas.
periodo = barra_lateral(mart)

# Aviso de dados desatualizados (pipeline sem rodar há mais de N dias).
dias = dias_desde_carga(mart.dados)
limite_dias = carregar_config().get("painel", {}).get("dias_dados_desatualizados", 3)
st.session_state["_dias_desde_carga"] = dias
if dias > limite_dias:
    st.sidebar.warning(
        f"A última carga foi há {dias} dias. Rode `pipeline-etl` para atualizar.",
        title="Dados desatualizados",
        icon=":material/update:",
    )
st.session_state["_mart"] = mart.dados
st.session_state["_mart_periodo"] = periodo
st.session_state["_alertas"] = alertas
st.session_state["_alertas_periodo"] = alertas[
    alertas["primeiro_dia_mes"].between(
        periodo["primeiro_dia_mes"].min(), periodo["primeiro_dia_mes"].max()
    )
].reset_index(drop=True)

# Exportação: relatório executivo e dados do período, em qualquer página.
with st.sidebar:
    st.header("Exportar")
    if periodo.empty:
        st.caption("Nenhum mês no período selecionado.")
    else:
        referencia = mes_referencia_padrao(periodo)
        nome = f"indicadores_{periodo['ano_mes'].iloc[0]}_a_{periodo['ano_mes'].iloc[-1]}"
        relatorio = gerar_relatorio_html(
            periodo,
            comparar(mart.dados, referencia),
            rotulo_mes(referencia),
            st.session_state["_alertas_periodo"],
            mart.origem,
            pd.Timestamp.now(tz="America/Sao_Paulo"),
        )
        st.download_button(
            "Relatório executivo",
            relatorio.encode("utf-8"),
            file_name=f"relatorio_{nome}.html",
            mime="text/html",
            icon=":material/description:",
            on_click="ignore",
            width="stretch",
            help="Resumo, comparações MoM/YoY, alertas e dados do período em HTML. "
            "Para PDF: abra no navegador e use Imprimir > Salvar como PDF.",
        )
        colunas = [c for c in periodo.columns if c not in ("mes_rotulo",)]
        st.download_button(
            "Dados do período (CSV)",
            periodo[colunas].to_csv(index=False).encode("utf-8"),
            file_name=f"{nome}.csv",
            mime="text/csv",
            icon=":material/download:",
            on_click="ignore",
            width="stretch",
        )

paginas.run()
