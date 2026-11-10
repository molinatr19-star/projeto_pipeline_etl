-- Objetivo: cruzar as duas fontes - não pode haver cotação do dólar (BCB) em dia que a ANBIMA
--           marca como não útil (correto = zero linhas). Se aparecer, falta feriado no arquivo
--           da ANBIMA (ex.: lei nova) ou há data errada na série do dólar.
--           O sentido inverso (dia útil sem cotação) não é checado: acontece legitimamente
--           enquanto o BCB ainda não publicou a cotação do dia.
-- Origem: marts.fct_indicador, marts.dim_serie, marts.dim_data
-- Granularidade: uma linha por cotação em dia não útil
SELECT
    fato.data_referencia,
    calendario.nome_dia_semana,
    calendario.nome_feriado,
    fato.valor
FROM marts.fct_indicador AS fato
INNER JOIN marts.dim_serie AS serie
    ON fato.codigo_serie = serie.codigo_serie
INNER JOIN marts.dim_data AS calendario
    ON fato.data_referencia = calendario.data
WHERE serie.nome_serie = 'dolar_venda'
  AND NOT calendario.eh_dia_util;
