-- Objetivo: fatos cuja série não existe em dim_serie (correto = zero linhas)
-- Origem: marts.fct_indicador, marts.dim_serie
-- Granularidade: uma linha por fato órfão
SELECT
    fato.codigo_serie,
    fato.data_referencia
FROM marts.fct_indicador AS fato
LEFT JOIN marts.dim_serie AS serie
    ON fato.codigo_serie = serie.codigo_serie
WHERE serie.codigo_serie IS NULL;
