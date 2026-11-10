-- Objetivo: pesquisas do Focus cuja data não existe em dim_data (correto = zero linhas)
-- Origem: marts.fct_expectativa, marts.dim_data
-- Granularidade: uma linha por pesquisa órfã
SELECT
    expectativa.indicador,
    expectativa.data_pesquisa
FROM marts.fct_expectativa AS expectativa
LEFT JOIN marts.dim_data AS calendario
    ON expectativa.data_pesquisa = calendario.data
WHERE calendario.data IS NULL;
