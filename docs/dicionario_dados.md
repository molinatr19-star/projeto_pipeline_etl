# Dicionário de dados

> Registrar cada tabela e coluna nova ao criá-la.

## `stg_bcb_series`
- Camada: staging
- Arquivo: `data/staging/stg_bcb_series.parquet`
- Granularidade: uma linha por série por data de referência.
- Chave: `codigo_serie` + `data_referencia`.
- Origem: todas as partições de cada série em `data/raw/bcb_sgs/data_extracao=*/serie_<codigo>.json` (extração incremental); data repetida fica com a extração mais recente.
- Carga: reconstrução completa a cada execução (`python -m pipeline_etl.orquestracao.staging_bcb_sgs`).

| Coluna | Tipo | Unidade | Obrigatória | Origem | Regra de cálculo |
|--------|------|---------|-------------|--------|------------------|
| codigo_serie | int64 | - | sim | nome do arquivo raw | código SGS (433, 432, 1, 13521, 13522, 189, 4389, 24369) |
| nome_serie | texto | - | sim | `.meta.json` | nome dado no `config/pipeline.yaml` |
| data_referencia | date | - | sim | campo `data` da API | `dd/mm/aaaa` convertido para data; séries mensais usam o dia 1 |
| valor | float64 | ver `unidade` | sim | campo `valor` da API | texto convertido para número (ponto decimal) |
| unidade | texto | - | sim | `.meta.json` | `% a.m.`, `% a.a.` ou `R$/US$` |
| periodicidade | texto | - | sim | `.meta.json` | `mensal` ou `diaria` |
| fonte | texto | - | sim | fixo | `bcb_sgs` |
| data_extracao | date | - | sim | nome da partição raw | data em que a API foi consultada |
| carregado_em | timestamp com fuso | - | sim | relógio da execução | horário do staging em `America/Sao_Paulo`, sem frações de segundo |

Observações:
- Dólar (série 1): só dias úteis.
- Meta Selic (série 432): inclui fins de semana e feriados, repetindo a meta vigente.
- IPCA (série 433): um valor por mês, publicado depois do mês de referência. Em 10/11/2026, o último disponível era setembro/2026. Calendário de divulgação do IBGE: verificar.

## `stg_bcb_series` (rejeitados)
- Arquivo: `data/staging/rejeitados/stg_bcb_series.parquet`
- Granularidade: uma linha por registro do raw que não pôde ser convertido.

| Coluna | Tipo | Regra |
|--------|------|-------|
| codigo_serie | int64 | código SGS |
| data_raw | texto | campo `data` original |
| valor_raw | texto | campo `valor` original |
| motivo | texto | `data_invalida` ou `valor_invalido` |
| data_extracao | date | partição de origem |
| carregado_em | timestamp com fuso | horário do staging |

## `stg_feriados`
- Camada: staging
- Arquivo: `data/staging/stg_feriados.parquet`
- Granularidade: uma linha por data de feriado nacional. Chave: `data`.
- Origem: planilha mais recente em `data/raw/anbima_feriados/data_extracao=*/feriados_nacionais.xls`.
- Cobertura: 2001 a 2099 (1.264 feriados em 1.263 datas). Arquivo atualizado pela ANBIMA em 22/12/2023.
- Carga: reconstrução completa (`python -m pipeline_etl.orquestracao.staging_anbima_feriados`).

| Coluna | Tipo | Obrigatória | Origem | Regra |
|--------|------|-------------|--------|-------|
| data | date | sim | coluna "Data" | linhas sem data válida são o rodapé da planilha e ficam de fora |
| nome_feriado | texto | sim | coluna "Feriado" | sem espaços nas pontas; dois feriados na mesma data são unidos com " / " (ex.: 21/04/2079, "Paixão de Cristo / Tiradentes") |
| fonte | texto | sim | fixo | `anbima_feriados` |
| data_extracao | date | sim | nome da partição raw | data do download |
| carregado_em | timestamp com fuso | sim | relógio da execução | horário do staging |

A coluna "Dia da Semana" da planilha não é guardada; ela só é usada para conferir a data (checagem de qualidade).

## `stg_focus_ipca_12m`
- Camada: staging. Arquivo: `data/staging/stg_focus_ipca_12m.parquet`.
- Granularidade: uma linha por dia de pesquisa do Focus. Chave: `data_pesquisa`.
- Origem: todas as partições de `data/raw/bcb_focus/data_extracao=*/ipca_12m.json`; data repetida fica com a
  extração mais recente.

| Coluna | Tipo | Regra |
|--------|------|-------|
| data_pesquisa | date | campo `Data` da API |
| indicador | texto | `IPCA` |
| horizonte | texto | `12 meses` |
| mediana_pct | float64 | campo `Mediana` (% para os 12 meses seguintes) |
| media_pct | float64 | campo `Media` |
| desvio_padrao | float64 | campo `DesvioPadrao` |
| numero_respondentes | Int64 | campo `numeroRespondentes` (nulo nos anos mais antigos) |
| fonte | texto | `bcb_focus` |
| data_extracao | date | partição de origem |
| carregado_em | timestamp com fuso | horário do staging |

## Warehouse (`DUCKDB_CAMINHO`; padrão `warehouse/pipeline.duckdb`)

Modelo em estrela: `fct_indicador` no centro, ligada a `dim_serie` e `dim_data`.
Mais uma tabela de consumo, `mart_indicadores_mensal`, construída sobre o modelo.
Reconstruído a cada carga (`python -m pipeline_etl.orquestracao.warehouse`).
O schema `staging` tem cópias de `stg_bcb_series` e `stg_feriados` (mesmas colunas dos Parquets).

### `marts.dim_serie`
- Granularidade: uma linha por série. Chave: `codigo_serie`.
- SQL: `sql/marts/01_dim_serie.sql`.

| Coluna | Tipo | Regra |
|--------|------|-------|
| codigo_serie | INTEGER (PK) | código SGS; estável, por isso sem surrogate key |
| nome_serie | VARCHAR | do staging |
| unidade | VARCHAR | do staging |
| periodicidade | VARCHAR | do staging |
| fonte | VARCHAR | `bcb_sgs` |
| carregado_em | TIMESTAMPTZ | horário da carga do warehouse |

### `marts.dim_data`
- Granularidade: uma linha por dia. Chave: `data`.
- Intervalo: de 1º de janeiro do ano do primeiro dado a 31 de dezembro do ano do último.
- Feriados: nacionais da ANBIMA (critério bancário). Não inclui feriados estaduais ou municipais.
- SQL: `sql/marts/02_dim_data.sql`.

| Coluna | Tipo | Regra |
|--------|------|-------|
| data | DATE (PK) | dia do calendário |
| ano, trimestre, mes, dia | INTEGER | partes da data |
| nome_mes | VARCHAR | `janeiro` ... `dezembro` |
| ano_mes | VARCHAR | `AAAA-MM` |
| primeiro_dia_mes | DATE | útil para agrupar séries diárias por mês |
| dia_semana_iso | INTEGER | 1 = segunda ... 7 = domingo |
| nome_dia_semana | VARCHAR | `segunda-feira` ... `domingo` |
| eh_fim_de_semana | BOOLEAN | sábado ou domingo |
| eh_feriado | BOOLEAN | data presente em `stg_feriados` |
| nome_feriado | VARCHAR | nome do feriado; nulo quando não é feriado |
| eh_dia_util | BOOLEAN | segunda a sexta e não feriado nacional |
| carregado_em | TIMESTAMPTZ | horário da carga do warehouse |

### `marts.fct_indicador`
- Granularidade: uma linha por série por data de referência (diária para Selic e dólar; mensal, no dia 1, para o IPCA).
- Chave: `codigo_serie` + `data_referencia`.
- Relacionamentos: `codigo_serie` -> `dim_serie`; `data_referencia` -> `dim_data.data`.
- SQL: `sql/marts/03_fct_indicador.sql`.

| Coluna | Tipo | Unidade | Regra |
|--------|------|---------|-------|
| codigo_serie | INTEGER | - | código SGS |
| data_referencia | DATE | - | data do valor publicado |
| valor | DOUBLE | ver `dim_serie.unidade` | valor do staging, sem alteração |
| data_extracao | DATE | - | data em que a API foi consultada |
| carregado_em | TIMESTAMPTZ | - | horário da carga do warehouse |

Cuidado ao agregar: a fato mistura unidades diferentes. Sempre filtrar ou agrupar por série antes de somar ou tirar média.

### `marts.fct_expectativa`
- Granularidade: uma linha por indicador, horizonte e dia de pesquisa.
  Chave: (`indicador`, `horizonte`, `data_pesquisa`).
- Origem: `staging.stg_focus_ipca_12m`. SQL: `sql/marts/04_fct_expectativa.sql`.
- Separado de `fct_indicador`: expectativa é uma projeção feita numa data; o realizado é publicado para uma
  data de referência.

### `marts.mart_indicadores_mensal` (exportada para `data/processed/`)
- Granularidade: uma linha por mês, do primeiro ao último mês com algum dado. Chave: `ano_mes`.
- Arquivos: `data/processed/indicadores_mensal.parquet` e `indicadores_mensal.csv` (vírgula como separador, ponto decimal, UTF-8).
- SQL: `sql/marts/04_mart_indicadores_mensal.sql`.
- Valores nulos são intencionais: indicador ainda não publicado ou janela incompleta.

| Coluna | Tipo | Unidade | Regra de cálculo |
|--------|------|---------|------------------|
| ano_mes | VARCHAR (PK) | - | `AAAA-MM` |
| primeiro_dia_mes | DATE | - | dia 1 do mês |
| ano, mes | INTEGER | - | partes da data |
| dias_uteis | INTEGER | dias | dias com `eh_dia_util` no mês (calendário ANBIMA) |
| ipca_mensal_pct | DOUBLE | % | IPCA do mês (série 433) |
| ipca_acumulado_ano_pct | DOUBLE | % | (produto de (1 + IPCA/100) de janeiro até o mês - 1) x 100; nulo se faltar algum mês |
| ipca_acumulado_12m_pct | DOUBLE | % | mesmo cálculo nos últimos 12 meses; nulo se não houver 12 meses |
| meta_inflacao_pct | DOUBLE | % | centro da meta de inflação do ano (SGS 13521, anual) |
| igpm_mensal_pct | DOUBLE | % | IGP-M do mês (SGS 189) |
| igpm_acumulado_12m_pct | DOUBLE | % | produto de (1 + IGP-M/100) nos últimos 12 meses - 1; nulo sem 12 meses |
| expectativa_ipca_12m_pct | DOUBLE | % | mediana do Focus para o IPCA dos 12 meses seguintes, na última pesquisa do mês |
| selic_meta_fim_mes_pct | DOUBLE | % a.a. | último valor da meta Selic no mês |
| cdi_fim_mes_pct | DOUBLE | % a.a. | último CDI anualizado do mês (SGS 4389) |
| desocupacao_pct | DOUBLE | % | desocupação, PNAD Contínua, trimestre móvel (SGS 24369; convenção de data: verificar) |
| juro_real_12m_pct | DOUBLE | % | aproximação: ((1 + Selic meta/100) / (1 + IPCA 12m/100) - 1) x 100 |
| dolar_medio_mes | DOUBLE | R$/US$ | média das cotações de venda do mês |
| dolar_fim_mes | DOUBLE | R$/US$ | última cotação do mês |
| dolar_variacao_mes_pct | DOUBLE | % | (dólar fim do mês / dólar fim do mês anterior - 1) x 100 |
| dias_com_cotacao_dolar | INTEGER | dias | quantidade de cotações no mês |
| mes_completo | BOOLEAN | - | o mês já tinha terminado na data da extração mais recente |
| carregado_em | TIMESTAMPTZ | - | horário da carga do warehouse |

Arredondamento: percentuais com 2 casas e dólar médio com 4. O IPCA acumulado é composto a partir das taxas mensais já arredondadas pelo BCB, então pode diferir em 0,01 p.p. do acumulado oficial do IBGE (ex.: 2022 = 5,78 aqui, 5,79 oficial).

## Modelo de registro

### `nome_da_tabela`
- Camada: staging | marts
- Granularidade: uma linha por ...
- Origem: ...

| Coluna | Tipo | Unidade | Obrigatória | Origem | Regra de cálculo |
|--------|------|---------|-------------|--------|------------------|
| | | | | | |
