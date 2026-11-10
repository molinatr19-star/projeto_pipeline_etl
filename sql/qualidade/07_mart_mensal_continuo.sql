-- Objetivo: mart mensal sem meses faltando e não vazia (correto = zero linhas)
-- Origem: marts.mart_indicadores_mensal
-- Granularidade: no máximo uma linha (resumo do problema)
SELECT
    MIN(primeiro_dia_mes) AS primeiro_mes,
    MAX(primeiro_dia_mes) AS ultimo_mes,
    COUNT(*) AS meses
FROM marts.mart_indicadores_mensal
HAVING COUNT(*) = 0
    OR COUNT(*) <> date_diff('month', MIN(primeiro_dia_mes), MAX(primeiro_dia_mes)) + 1;
