-- Objetivo: todo ano do calendário precisa ter feriados carregados (correto = zero linhas).
--           Pega o caso de o arquivo de feriados não cobrir o período dos indicadores.
-- Origem: marts.dim_data
-- Granularidade: uma linha por ano sem feriado
SELECT
    ano,
    COUNT(*) FILTER (WHERE eh_feriado) AS feriados
FROM marts.dim_data
GROUP BY ano
HAVING COUNT(*) FILTER (WHERE eh_feriado) = 0;
