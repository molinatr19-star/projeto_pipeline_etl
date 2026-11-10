-- Objetivo: fatos cuja data não existe em dim_data (correto = zero linhas)
-- Origem: marts.fct_indicador, marts.dim_data
-- Granularidade: uma linha por fato órfão
SELECT
    fato.codigo_serie,
    fato.data_referencia
FROM marts.fct_indicador AS fato
LEFT JOIN marts.dim_data AS calendario
    ON fato.data_referencia = calendario.data
WHERE calendario.data IS NULL;
