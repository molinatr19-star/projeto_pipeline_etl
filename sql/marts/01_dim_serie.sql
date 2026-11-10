-- Objetivo: dimensão com a descrição de cada série
-- Origem: staging.stg_bcb_series
-- Granularidade: uma linha por série
-- Chave: codigo_serie (código SGS, estável; dispensa surrogate key)
CREATE OR REPLACE TABLE marts.dim_serie (
    codigo_serie  INTEGER PRIMARY KEY,
    nome_serie    VARCHAR NOT NULL,
    unidade       VARCHAR NOT NULL,
    periodicidade VARCHAR NOT NULL,
    fonte         VARCHAR NOT NULL,
    carregado_em  TIMESTAMPTZ NOT NULL
);

-- Se a mesma série vier com descrições diferentes, o DISTINCT gera duas linhas
-- com o mesmo código e a chave primária bloqueia a carga (comportamento desejado).
INSERT INTO marts.dim_serie (
    codigo_serie, nome_serie, unidade, periodicidade, fonte, carregado_em
)
SELECT DISTINCT
    codigo_serie,
    nome_serie,
    unidade,
    periodicidade,
    fonte,
    current_timestamp
FROM staging.stg_bcb_series
ORDER BY codigo_serie;
