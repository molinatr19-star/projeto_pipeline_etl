-- Objetivo: staging e fato com a mesma quantidade de linhas e a mesma soma de valores por série
--           (correto = zero linhas)
-- Origem: staging.stg_bcb_series, marts.fct_indicador
-- Granularidade: uma linha por série com divergência
WITH staging_por_serie AS (
    SELECT
        codigo_serie,
        COUNT(*) AS linhas,
        ROUND(SUM(valor), 6) AS soma_valor
    FROM staging.stg_bcb_series
    GROUP BY codigo_serie
),

fato_por_serie AS (
    SELECT
        codigo_serie,
        COUNT(*) AS linhas,
        ROUND(SUM(valor), 6) AS soma_valor
    FROM marts.fct_indicador
    GROUP BY codigo_serie
)

SELECT
    COALESCE(stg.codigo_serie, fato.codigo_serie) AS codigo_serie,
    stg.linhas AS linhas_staging,
    fato.linhas AS linhas_fato,
    stg.soma_valor AS soma_staging,
    fato.soma_valor AS soma_fato
FROM staging_por_serie AS stg
FULL OUTER JOIN fato_por_serie AS fato
    ON stg.codigo_serie = fato.codigo_serie
WHERE stg.linhas IS DISTINCT FROM fato.linhas
   OR stg.soma_valor IS DISTINCT FROM fato.soma_valor;
