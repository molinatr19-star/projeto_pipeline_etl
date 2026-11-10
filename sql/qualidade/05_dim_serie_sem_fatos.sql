-- Objetivo: séries da dimensão sem nenhum fato (correto = zero linhas)
-- Origem: marts.dim_serie, marts.fct_indicador
-- Granularidade: uma linha por série vazia
SELECT
    serie.codigo_serie,
    serie.nome_serie
FROM marts.dim_serie AS serie
WHERE NOT EXISTS (
    SELECT 1
    FROM marts.fct_indicador AS fato
    WHERE fato.codigo_serie = serie.codigo_serie
);
