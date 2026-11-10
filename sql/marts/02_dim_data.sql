-- Objetivo: calendário com atributos de data, feriados nacionais e dias úteis
-- Origem: staging.stg_bcb_series (define só o intervalo: anos completos do primeiro ao último dado)
--         staging.stg_feriados (feriados nacionais da ANBIMA)
-- Granularidade: uma linha por dia
-- Dia útil: segunda a sexta que não é feriado nacional (critério bancário da ANBIMA;
--           não considera feriados estaduais ou municipais)
CREATE OR REPLACE TABLE marts.dim_data (
    data             DATE PRIMARY KEY,
    ano              INTEGER NOT NULL,
    trimestre        INTEGER NOT NULL,
    mes              INTEGER NOT NULL,
    nome_mes         VARCHAR NOT NULL,
    ano_mes          VARCHAR NOT NULL,
    primeiro_dia_mes DATE NOT NULL,
    dia              INTEGER NOT NULL,
    dia_semana_iso   INTEGER NOT NULL,  -- 1 = segunda ... 7 = domingo
    nome_dia_semana  VARCHAR NOT NULL,
    eh_fim_de_semana BOOLEAN NOT NULL,
    eh_feriado       BOOLEAN NOT NULL,
    nome_feriado     VARCHAR,           -- nulo quando não é feriado
    eh_dia_util      BOOLEAN NOT NULL,
    carregado_em     TIMESTAMPTZ NOT NULL
);

INSERT INTO marts.dim_data (
    data, ano, trimestre, mes, nome_mes, ano_mes, primeiro_dia_mes,
    dia, dia_semana_iso, nome_dia_semana, eh_fim_de_semana,
    eh_feriado, nome_feriado, eh_dia_util, carregado_em
)
WITH limites AS (
    SELECT
        CAST(date_trunc('year', MIN(data_referencia)) AS DATE) AS inicio,
        CAST(date_trunc('year', MAX(data_referencia)) + INTERVAL 1 YEAR - INTERVAL 1 DAY AS DATE)
            AS fim
    FROM staging.stg_bcb_series
),

dias AS (
    SELECT CAST(unnest(generate_series(inicio, fim, INTERVAL 1 DAY)) AS DATE) AS data
    FROM limites
)

SELECT
    dias.data,
    year(dias.data),
    quarter(dias.data),
    month(dias.data),
    ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho',
     'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'][month(dias.data)],
    strftime(dias.data, '%Y-%m'),
    CAST(date_trunc('month', dias.data) AS DATE),
    day(dias.data),
    isodow(dias.data),
    ['segunda-feira', 'terça-feira', 'quarta-feira', 'quinta-feira',
     'sexta-feira', 'sábado', 'domingo'][isodow(dias.data)],
    isodow(dias.data) >= 6,
    feriados.data IS NOT NULL,
    feriados.nome_feriado,
    isodow(dias.data) <= 5 AND feriados.data IS NULL,
    current_timestamp
FROM dias
LEFT JOIN staging.stg_feriados AS feriados
    ON dias.data = feriados.data
ORDER BY dias.data;
