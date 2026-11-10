-- Objetivo: trazer o staging de feriados (Parquet gerado em pandas) para dentro do warehouse
-- Origem: data/staging/stg_feriados.parquet
-- Granularidade: uma linha por data de feriado nacional
CREATE OR REPLACE TABLE staging.stg_feriados AS
SELECT
    data,
    nome_feriado,
    fonte,
    data_extracao,
    carregado_em
FROM read_parquet('{{caminho_stg_feriados}}');
