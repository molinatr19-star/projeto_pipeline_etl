-- Objetivo: fato com a expectativa do mercado (Boletim Focus) para a inflação dos próximos 12 meses
-- Origem: staging.stg_focus_ipca_12m
-- Granularidade: uma linha por indicador por dia de pesquisa
-- Separado de fct_indicador de propósito: expectativa (projeção feita numa data) e valor
-- realizado (publicado para uma data de referência) têm significados diferentes.
-- Relacionamento: data_pesquisa -> marts.dim_data (conferido em sql/qualidade/)
CREATE OR REPLACE TABLE marts.fct_expectativa (
    indicador           VARCHAR NOT NULL,
    horizonte           VARCHAR NOT NULL,
    data_pesquisa       DATE NOT NULL,
    mediana_pct         DOUBLE NOT NULL,
    media_pct           DOUBLE,
    desvio_padrao       DOUBLE,
    numero_respondentes INTEGER,
    data_extracao       DATE NOT NULL,
    carregado_em        TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (indicador, horizonte, data_pesquisa)
);

INSERT INTO marts.fct_expectativa (
    indicador, horizonte, data_pesquisa, mediana_pct, media_pct, desvio_padrao,
    numero_respondentes, data_extracao, carregado_em
)
SELECT
    indicador,
    horizonte,
    data_pesquisa,
    mediana_pct,
    media_pct,
    desvio_padrao,
    numero_respondentes,
    data_extracao,
    current_timestamp
FROM staging.stg_focus_ipca_12m
ORDER BY data_pesquisa;
