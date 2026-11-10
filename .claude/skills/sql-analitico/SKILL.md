---
name: sql-analitico
description: Padrões de SQL e modelagem analítica do projeto_pipeline_etl - camadas staging e marts, modelagem dimensional (fatos, dimensões, star schema), granularidade, chaves, CTEs, consultas de qualidade de dados e boas práticas em DuckDB. Use ao escrever, revisar ou explicar qualquer arquivo em sql/ ou ao desenhar tabelas do warehouse.
---

Projeto: `projeto_pipeline_etl`. Ler o `CLAUDE.md` da raiz antes de começar.

# Organização dos arquivos
- `sql/ddl/`: criação de schemas e tabelas.
- `sql/staging/`: `stg_<fonte>_<entidade>.sql` - limpeza e padronização, uma linha por registro da fonte.
- `sql/marts/`: `dim_<entidade>.sql` e `fct_<processo>.sql` - modelo para consumo.
- `sql/qualidade/`: consultas que devem retornar zero linhas quando o dado está correto.
- Numerar quando houver ordem de execução (`01_`, `02_`).

# Cabeçalho obrigatório em cada arquivo
```sql
-- Objetivo: o que esta consulta entrega
-- Origem: tabelas de entrada
-- Granularidade: uma linha por <entidade/evento>
```

# Modelagem dimensional
- Começar pela granularidade da fato: o que uma linha representa.
- Fatos: eventos e medidas numéricas (valores, quantidades), com chaves para as dimensões.
- Dimensões: contexto descritivo (cliente, produto, data, local).
- Surrogate key nas dimensões quando a chave natural não for estável.
- `dim_data` (calendário) gerada uma vez e reutilizada.
- Star schema como padrão; evitar snowflake sem motivo.

# Estilo
- Palavras-chave em maiúsculas, nomes em minúsculas e `snake_case`.
- CTEs nomeadas pelo que fazem (`pedidos_validos`, `ultimo_status`), uma responsabilidade por CTE.
- Listar colunas explicitamente nas camadas finais; sem `SELECT *`.
- Aliases claros; nada de `a`, `b`, `c`.

# Armadilhas a checar
- Joins que multiplicam linhas: conferir contagem antes e depois do join.
- `LEFT JOIN` com filtro no `WHERE` que vira `INNER JOIN` sem querer.
- Divisão por zero e médias de médias.
- Filtros de data com limite incluso ou excluso definido.
- `NULL` em comparações e agregações.

# Consultas de qualidade (modelos)
- Chave duplicada: `GROUP BY chave HAVING COUNT(*) > 1`.
- Nulo em obrigatória: `WHERE coluna IS NULL`.
- Integridade referencial: fato sem dimensão correspondente (`LEFT JOIN ... WHERE dim.chave IS NULL`).
- Contagem entre camadas: staging vs. marts, diferença explicada.

# DuckDB
- Lê Parquet e CSV direto em consultas; preferir isso a carregar tudo em pandas quando o volume crescer.
- Confirmar na documentação oficial do DuckDB qualquer função específica antes de usar; marcar "verificar" em caso de dúvida.
- Versão instalada: DuckDB 2.0. O resultado de `duckdb.sql()` não tem `.fetchone()`; usar `.fetchall()` ou `.limit(1).fetchall()`.
