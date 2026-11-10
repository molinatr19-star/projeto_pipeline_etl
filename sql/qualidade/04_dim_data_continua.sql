-- Objetivo: calendário sem dias faltando e não vazio (correto = zero linhas)
-- Origem: marts.dim_data
-- Granularidade: no máximo uma linha (resumo do problema)
SELECT
    MIN(data) AS primeiro_dia,
    MAX(data) AS ultimo_dia,
    COUNT(*) AS dias
FROM marts.dim_data
HAVING COUNT(*) = 0
    OR COUNT(*) <> date_diff('day', MIN(data), MAX(data)) + 1;
