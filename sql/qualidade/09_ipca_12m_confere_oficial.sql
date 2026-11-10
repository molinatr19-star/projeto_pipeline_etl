-- Objetivo: o IPCA 12 meses calculado na mart precisa bater com o publicado pelo BCB
--           (SGS 13522), com tolerância de 0,02 p.p. para o arredondamento das taxas
--           mensais (correto = zero linhas). Meses sem valor oficial não são comparados.
-- Origem: marts.mart_indicadores_mensal, marts.fct_indicador, marts.dim_serie
-- Granularidade: uma linha por mês com divergência
WITH oficial AS (
    SELECT
        fato.data_referencia AS primeiro_dia_mes,
        fato.valor AS ipca_12m_oficial_pct
    FROM marts.fct_indicador AS fato
    INNER JOIN marts.dim_serie AS serie
        ON fato.codigo_serie = serie.codigo_serie
    WHERE serie.nome_serie = 'ipca_12m_oficial'
)

SELECT
    mart.ano_mes,
    mart.ipca_acumulado_12m_pct,
    oficial.ipca_12m_oficial_pct,
    ROUND(mart.ipca_acumulado_12m_pct - oficial.ipca_12m_oficial_pct, 4) AS diferenca
FROM marts.mart_indicadores_mensal AS mart
INNER JOIN oficial
    ON mart.primeiro_dia_mes = oficial.primeiro_dia_mes
WHERE mart.ipca_acumulado_12m_pct IS NOT NULL
  AND abs(mart.ipca_acumulado_12m_pct - oficial.ipca_12m_oficial_pct) > 0.02;
