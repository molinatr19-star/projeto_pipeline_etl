-- Objetivo: trazer o staging do Focus (Parquet gerado em pandas) para dentro do warehouse
-- Origem: data/staging/stg_focus_ipca_12m.parquet
-- Granularidade: uma linha por dia de pesquisa
CREATE OR REPLACE TABLE staging.stg_focus_ipca_12m AS
SELECT
    data_pesquisa,
    indicador,
    horizonte,
    mediana_pct,
    media_pct,
    desvio_padrao,
    numero_respondentes,
    fonte,
    data_extracao,
    carregado_em
FROM read_parquet('{{caminho_stg_focus}}');
