"""Botão "Atualizar dados" do painel: roda o pipeline e recarrega a tela.

Fluxo: extração (APIs SGS e Focus, buscando de novo mesmo que já tenham sido consultadas
hoje) -> staging -> warehouse DuckDB -> exportação -> limpa o cache -> recarrega a página.

Proteções:
- trava: uma atualização por vez no servidor (vale para todos os usuários do painel);
- intervalo mínimo entre atualizações (`painel.atualizacao` no config), para não
  sobrecarregar as APIs do Banco Central num painel público;
- falha: o erro aparece na tela e o painel continua com os dados anteriores (a carga
  do warehouse é uma transação; a exportação só acontece depois dela).
"""

import threading
import time
from typing import Any

import pandas as pd
import streamlit as st

from pipeline_etl.dashboard.dados import Mart, limpar_cache_mart
from pipeline_etl.orquestracao import pipeline
from pipeline_etl.utils.configuracao import carregar_config
from pipeline_etl.utils.log import configurar_logging

ROTULOS_ETAPAS = {
    "extracao_bcb_sgs": "Extraindo séries do Banco Central (SGS)",
    "extracao_anbima_feriados": "Conferindo feriados da ANBIMA",
    "extracao_bcb_focus": "Extraindo expectativas do Boletim Focus",
    "staging_bcb_sgs": "Staging das séries",
    "staging_anbima_feriados": "Staging dos feriados",
    "staging_bcb_focus": "Staging do Focus",
    "warehouse": "Carregando o warehouse DuckDB",
    "exportacao": "Exportando a tabela mensal",
}


def config_atualizacao() -> dict[str, Any]:
    padrao = {"permitir": True, "intervalo_minimo_minutos": 10}
    return padrao | carregar_config().get("painel", {}).get("atualizacao", {})


def minutos_desde_carga(df: pd.DataFrame, agora: pd.Timestamp | None = None) -> float:
    """Minutos desde a última carga do pipeline (coluna carregado_em)."""
    carga = pd.Timestamp(df["carregado_em"].max())
    agora = agora if agora is not None else pd.Timestamp.now(tz=carga.tz)
    return (agora - carga).total_seconds() / 60


def minutos_para_liberar(
    df: pd.DataFrame, intervalo: float, agora: pd.Timestamp | None = None
) -> int:
    """Minutos que faltam para o botão ser liberado (0 = liberado)."""
    restante = intervalo - minutos_desde_carga(df, agora)
    return max(0, int(-(-restante // 1)))  # arredonda para cima


@st.cache_resource
def _trava() -> threading.Lock:
    """Uma trava por servidor: impede duas atualizações ao mesmo tempo."""
    return threading.Lock()


def _executar() -> None:
    """Roda o pipeline mostrando o progresso; em caso de sucesso, recarrega a página."""
    trava = _trava()
    if not trava.acquire(blocking=False):
        st.warning(
            "Outra atualização está em andamento. Aguarde alguns segundos e recarregue a página.",
            icon=":material/hourglass_top:",
        )
        return

    configurar_logging()  # registra a execução em logs/pipeline_AAAA-MM-DD.log
    inicio = time.perf_counter()
    try:
        with st.status("Atualizando dados...", expanded=True) as status:

            def progresso(posicao: int, total: int, nome: str, estado: str) -> None:
                rotulo = ROTULOS_ETAPAS.get(nome, nome)
                if estado == "inicio":
                    status.update(label=f"[{posicao}/{total}] {rotulo}...")
                else:
                    status.write(f":material/check: {rotulo}")

            try:
                pipeline.executar(reextrair_hoje=True, progresso=progresso)
            except Exception as erro:  # mostra o erro e mantém os dados anteriores
                status.update(label="A atualização falhou", state="error", expanded=True)
                st.error(
                    f"{type(erro).__name__}: {erro}",
                    title="Os dados anteriores foram mantidos",
                    icon=":material/error:",
                )
                return
            status.update(label="Dados atualizados", state="complete", expanded=False)
    finally:
        trava.release()

    limpar_cache_mart()
    st.session_state["_aviso_atualizacao"] = (
        f"Dados atualizados em {time.perf_counter() - inicio:.0f} s."
    )
    st.rerun()


def secao_atualizacao(mart: Mart) -> None:
    """Botão na barra lateral; a execução (com progresso) aparece no topo da página."""
    cfg = config_atualizacao()
    espera = minutos_para_liberar(mart.dados, float(cfg["intervalo_minimo_minutos"]))
    with st.sidebar:
        st.header("Dados")
        clicou = st.button(
            "Atualizar dados",
            icon=":material/refresh:",
            width="stretch",
            disabled=not cfg["permitir"] or espera > 0,
            help="Busca os dados mais recentes nas APIs do Banco Central, refaz o staging, "
            "atualiza o warehouse DuckDB e recarrega o painel (leva cerca de 20 segundos).",
            key="botao_atualizar",
        )
        if not cfg["permitir"]:
            st.caption("Atualização pelo painel desativada na configuração.")
        elif espera > 0:
            st.caption(
                f"Disponível em {espera} min: intervalo mínimo de "
                f"{cfg['intervalo_minimo_minutos']} min entre atualizações."
            )

    aviso = st.session_state.pop("_aviso_atualizacao", None)
    if aviso:
        st.toast(aviso, icon=":material/check_circle:")
    if clicou:
        _executar()
