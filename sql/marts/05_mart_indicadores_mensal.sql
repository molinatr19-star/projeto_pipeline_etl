-- Objetivo: tabela mensal consolidada de indicadores, pronta para consumo (exportada para data/processed)
-- Origem: marts.fct_indicador, marts.fct_expectativa, marts.dim_serie, marts.dim_data
-- Granularidade: uma linha por mês, do primeiro ao último mês com algum dado
-- Regras:
--   ipca_acumulado_ano_pct / ipca_acumulado_12m_pct: produto de (1 + taxa mensal), calculado
--     como exp(soma de ln(1 + taxa)). Só preenchido quando todos os meses da janela existem.
--   meta_inflacao_pct: centro da meta de inflação do ano (série SGS 13521, anual).
--   igpm_acumulado_12m_pct: mesmo cálculo do IPCA 12 meses, sobre o IGP-M (SGS 189).
--   expectativa_ipca_12m_pct: mediana do Focus para o IPCA dos 12 meses seguintes, na
--     última pesquisa do mês.
--   selic_meta_fim_mes_pct / cdi_fim_mes_pct / dolar_fim_mes: último valor publicado no mês.
--   desocupacao_pct: PNAD Contínua, trimestre móvel (SGS 24369) com a data do mês da série.
--   dolar_variacao_mes_pct: dólar de fim de mês contra o fim do mês anterior.
--   juro_real_12m_pct: aproximação = (1 + Selic meta no fim do mês) / (1 + IPCA 12 meses) - 1.
--   mes_completo: o mês já tinha terminado na data da extração mais recente
--     (não garante que o IPCA do mês já foi publicado; ver ipca_mensal_pct nulo).
CREATE OR REPLACE TABLE marts.mart_indicadores_mensal (
    ano_mes                 VARCHAR PRIMARY KEY,
    primeiro_dia_mes        DATE NOT NULL,
    ano                     INTEGER NOT NULL,
    mes                     INTEGER NOT NULL,
    dias_uteis              INTEGER NOT NULL,
    ipca_mensal_pct         DOUBLE,
    ipca_acumulado_ano_pct  DOUBLE,
    ipca_acumulado_12m_pct  DOUBLE,
    meta_inflacao_pct       DOUBLE,
    igpm_mensal_pct         DOUBLE,
    igpm_acumulado_12m_pct  DOUBLE,
    expectativa_ipca_12m_pct DOUBLE,
    selic_meta_fim_mes_pct  DOUBLE,
    cdi_fim_mes_pct         DOUBLE,
    desocupacao_pct         DOUBLE,
    juro_real_12m_pct       DOUBLE,
    dolar_medio_mes         DOUBLE,
    dolar_fim_mes           DOUBLE,
    dolar_variacao_mes_pct  DOUBLE,
    dias_com_cotacao_dolar  INTEGER NOT NULL,
    mes_completo            BOOLEAN NOT NULL,
    carregado_em            TIMESTAMPTZ NOT NULL
);

INSERT INTO marts.mart_indicadores_mensal (
    ano_mes, primeiro_dia_mes, ano, mes, dias_uteis,
    ipca_mensal_pct, ipca_acumulado_ano_pct, ipca_acumulado_12m_pct, meta_inflacao_pct,
    igpm_mensal_pct, igpm_acumulado_12m_pct, expectativa_ipca_12m_pct,
    selic_meta_fim_mes_pct, cdi_fim_mes_pct, desocupacao_pct, juro_real_12m_pct,
    dolar_medio_mes, dolar_fim_mes, dolar_variacao_mes_pct, dias_com_cotacao_dolar,
    mes_completo, carregado_em
)
WITH fatos AS (
    SELECT
        fato.data_referencia,
        fato.valor,
        serie.nome_serie,
        CAST(date_trunc('month', fato.data_referencia) AS DATE) AS primeiro_dia_mes
    FROM marts.fct_indicador AS fato
    INNER JOIN marts.dim_serie AS serie
        ON fato.codigo_serie = serie.codigo_serie
),

meses AS (
    SELECT
        primeiro_dia_mes,
        ano,
        mes,
        ano_mes,
        COUNT(*) FILTER (WHERE eh_dia_util) AS dias_uteis,
        MAX(data) AS ultimo_dia_mes
    FROM marts.dim_data
    WHERE primeiro_dia_mes BETWEEN (SELECT MIN(primeiro_dia_mes) FROM fatos)
                               AND (SELECT MAX(primeiro_dia_mes) FROM fatos)
    GROUP BY primeiro_dia_mes, ano, mes, ano_mes
),

ipca AS (
    SELECT primeiro_dia_mes, valor AS ipca_mensal_pct
    FROM fatos
    WHERE nome_serie = 'ipca_variacao_mensal'
),

meta AS (
    SELECT
        year(data_referencia) AS ano,
        valor AS meta_inflacao_pct
    FROM fatos
    WHERE nome_serie = 'meta_inflacao'
),

igpm AS (
    SELECT primeiro_dia_mes, valor AS igpm_mensal_pct
    FROM fatos
    WHERE nome_serie = 'igpm_variacao_mensal'
),

desocupacao AS (
    SELECT primeiro_dia_mes, valor AS desocupacao_pct
    FROM fatos
    WHERE nome_serie = 'desocupacao'
),

cdi AS (
    SELECT
        primeiro_dia_mes,
        arg_max(valor, data_referencia) AS cdi_fim_mes_pct
    FROM fatos
    WHERE nome_serie = 'cdi_anualizado'
    GROUP BY primeiro_dia_mes
),

expectativa AS (
    SELECT
        CAST(date_trunc('month', data_pesquisa) AS DATE) AS primeiro_dia_mes,
        arg_max(mediana_pct, data_pesquisa) AS expectativa_ipca_12m_pct
    FROM marts.fct_expectativa
    WHERE indicador = 'IPCA' AND horizonte = '12 meses'
    GROUP BY 1
),

selic AS (
    SELECT
        primeiro_dia_mes,
        arg_max(valor, data_referencia) AS selic_meta_fim_mes_pct
    FROM fatos
    WHERE nome_serie = 'selic_meta'
    GROUP BY primeiro_dia_mes
),

dolar AS (
    SELECT
        primeiro_dia_mes,
        AVG(valor) AS dolar_medio_mes,
        arg_max(valor, data_referencia) AS dolar_fim_mes,
        COUNT(*) AS dias_com_cotacao_dolar
    FROM fatos
    WHERE nome_serie = 'dolar_venda'
    GROUP BY primeiro_dia_mes
),

base AS (
    SELECT
        meses.primeiro_dia_mes,
        meses.ano,
        meses.mes,
        meses.ano_mes,
        meses.dias_uteis,
        meses.ultimo_dia_mes,
        ipca.ipca_mensal_pct,
        meta.meta_inflacao_pct,
        igpm.igpm_mensal_pct,
        expectativa.expectativa_ipca_12m_pct,
        selic.selic_meta_fim_mes_pct,
        cdi.cdi_fim_mes_pct,
        desocupacao.desocupacao_pct,
        dolar.dolar_medio_mes,
        dolar.dolar_fim_mes,
        COALESCE(dolar.dias_com_cotacao_dolar, 0) AS dias_com_cotacao_dolar
    FROM meses
    LEFT JOIN ipca ON meses.primeiro_dia_mes = ipca.primeiro_dia_mes
    LEFT JOIN meta ON meses.ano = meta.ano
    LEFT JOIN igpm ON meses.primeiro_dia_mes = igpm.primeiro_dia_mes
    LEFT JOIN expectativa ON meses.primeiro_dia_mes = expectativa.primeiro_dia_mes
    LEFT JOIN cdi ON meses.primeiro_dia_mes = cdi.primeiro_dia_mes
    LEFT JOIN desocupacao ON meses.primeiro_dia_mes = desocupacao.primeiro_dia_mes
    LEFT JOIN selic ON meses.primeiro_dia_mes = selic.primeiro_dia_mes
    LEFT JOIN dolar ON meses.primeiro_dia_mes = dolar.primeiro_dia_mes
),

janelas AS (
    SELECT
        base.*,
        exp(SUM(ln(1 + ipca_mensal_pct / 100)) OVER no_ano) - 1 AS fator_ipca_ano,
        COUNT(ipca_mensal_pct) OVER no_ano AS meses_ipca_ano,
        exp(SUM(ln(1 + ipca_mensal_pct / 100)) OVER ultimos_12m) - 1 AS fator_ipca_12m,
        COUNT(ipca_mensal_pct) OVER ultimos_12m AS meses_ipca_12m,
        exp(SUM(ln(1 + igpm_mensal_pct / 100)) OVER ultimos_12m) - 1 AS fator_igpm_12m,
        COUNT(igpm_mensal_pct) OVER ultimos_12m AS meses_igpm_12m,
        LAG(dolar_fim_mes) OVER (ORDER BY primeiro_dia_mes) AS dolar_fim_mes_anterior
    FROM base
    WINDOW
        no_ano AS (
            PARTITION BY ano ORDER BY primeiro_dia_mes
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ),
        ultimos_12m AS (ORDER BY primeiro_dia_mes ROWS BETWEEN 11 PRECEDING AND CURRENT ROW)
),

indicadores AS (
    SELECT
        janelas.*,
        CASE
            WHEN ipca_mensal_pct IS NOT NULL AND meses_ipca_ano = mes
                THEN fator_ipca_ano * 100
        END AS ipca_acumulado_ano_pct,
        CASE
            WHEN ipca_mensal_pct IS NOT NULL AND meses_ipca_12m = 12
                THEN fator_ipca_12m * 100
        END AS ipca_acumulado_12m_pct,
        CASE
            WHEN igpm_mensal_pct IS NOT NULL AND meses_igpm_12m = 12
                THEN fator_igpm_12m * 100
        END AS igpm_acumulado_12m_pct
    FROM janelas
)

SELECT
    ano_mes,
    primeiro_dia_mes,
    ano,
    mes,
    dias_uteis,
    ROUND(ipca_mensal_pct, 2),
    ROUND(ipca_acumulado_ano_pct, 2),
    ROUND(ipca_acumulado_12m_pct, 2),
    meta_inflacao_pct,
    ROUND(igpm_mensal_pct, 2),
    ROUND(igpm_acumulado_12m_pct, 2),
    ROUND(expectativa_ipca_12m_pct, 2),
    selic_meta_fim_mes_pct,
    cdi_fim_mes_pct,
    desocupacao_pct,
    ROUND(((1 + selic_meta_fim_mes_pct / 100) / (1 + ipca_acumulado_12m_pct / 100) - 1) * 100, 2),
    ROUND(dolar_medio_mes, 4),
    dolar_fim_mes,
    ROUND((dolar_fim_mes / dolar_fim_mes_anterior - 1) * 100, 2),
    dias_com_cotacao_dolar,
    ultimo_dia_mes < (SELECT MAX(data_extracao) FROM marts.fct_indicador),
    current_timestamp
FROM indicadores
ORDER BY primeiro_dia_mes;
