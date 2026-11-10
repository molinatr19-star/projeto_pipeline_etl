-- Objetivo: fato com o valor de cada série em cada data publicada pelo BCB
-- Origem: staging.stg_bcb_series
-- Granularidade: uma linha por série por data de referência
--   (diária para Selic e dólar; mensal, no dia 1, para o IPCA)
-- Relacionamentos: codigo_serie -> marts.dim_serie; data_referencia -> marts.dim_data
--   (conferidos em sql/qualidade/, não declarados como FOREIGN KEY para permitir a reconstrução)
CREATE OR REPLACE TABLE marts.fct_indicador (
    codigo_serie    INTEGER NOT NULL,
    data_referencia DATE NOT NULL,
    valor           DOUBLE NOT NULL,
    data_extracao   DATE NOT NULL,
    carregado_em    TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (codigo_serie, data_referencia)
);

INSERT INTO marts.fct_indicador (
    codigo_serie, data_referencia, valor, data_extracao, carregado_em
)
SELECT
    codigo_serie,
    data_referencia,
    valor,
    data_extracao,
    current_timestamp
FROM staging.stg_bcb_series
ORDER BY codigo_serie, data_referencia;
