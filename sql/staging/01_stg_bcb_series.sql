-- Objetivo: trazer o staging (Parquet gerado em pandas) para dentro do warehouse
-- Origem: data/staging/stg_bcb_series.parquet
-- Granularidade: uma linha por série por data de referência
CREATE OR REPLACE TABLE staging.stg_bcb_series AS
SELECT
    codigo_serie,
    nome_serie,
    data_referencia,
    valor,
    unidade,
    periodicidade,
    fonte,
    data_extracao,
    carregado_em
FROM read_parquet('{{caminho_stg_bcb_series}}');
