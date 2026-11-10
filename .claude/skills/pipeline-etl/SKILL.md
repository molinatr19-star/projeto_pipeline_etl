---
name: pipeline-etl
description: Padrões de pipeline ETL/ELT do projeto_pipeline_etl - extração de APIs REST e arquivos, camadas raw/staging/warehouse, limpeza com pandas, carga em Parquet e DuckDB, idempotência, carga incremental, logging, configuração e qualidade de dados. Use ao planejar, escrever ou revisar qualquer etapa de extração, transformação, carga ou orquestração deste projeto.
---

Projeto: `projeto_pipeline_etl`. Ler o `CLAUDE.md` da raiz antes de começar.

# Fluxo padrão de uma nova fonte
1. Documentar a fonte em `docs/`: origem, formato, autenticação, limites, frequência, chave única.
2. Extração (`src/pipeline_etl/extracao/`): salvar a resposta como veio em `data/raw/<fonte>/data_extracao=AAAA-MM-DD/`.
3. Staging (`src/pipeline_etl/transformacao/` ou `sql/staging/`): tipos, nomes, duplicatas, nulos -> Parquet em `data/staging/`.
4. Carga (`src/pipeline_etl/carga/`): gravar no DuckDB em `warehouse/` de forma idempotente.
5. Marts (`sql/marts/`): fatos e dimensões para consumo analítico.
6. Qualidade (`src/pipeline_etl/qualidade/` e `sql/qualidade/`): validar após cada camada.
7. Registrar tabelas e colunas em `docs/dicionario_dados.md`.

# Extração de APIs
- Ler a documentação oficial antes; não supor endpoints, parâmetros ou formato de resposta.
- Sempre definir `timeout` nas requisições.
- Novas tentativas com espera crescente para erros temporários (429, 5xx); falhar rápido em 4xx de cliente.
- Tratar paginação até o fim e registrar quantas páginas e registros vieram.
- Pausa entre chamadas para respeitar o limite de requisições.
- Credenciais via variáveis de ambiente (`.env`), nunca no código.

# Checklist de staging
- Nomes de colunas em `snake_case`, sem acento.
- Tipos corretos (datas como `datetime`, números como numérico, categorias normalizadas).
- Remover duplicatas pela chave definida e registrar quantas foram removidas.
- Nulos em colunas obrigatórias: rejeitar ou separar em arquivo de rejeitados, nunca descartar em silêncio.
- Texto: `strip`, padronizar caixa quando for categoria.
- Colunas de auditoria: `fonte`, `data_extracao`, `carregado_em`.

# Carga e idempotência
- Carga completa: substituir a tabela inteira (adequado para tabelas pequenas).
- Carga incremental: filtrar pela marca d'água (maior data ou ID já carregado) e fazer upsert pela chave.
- Reexecutar o mesmo dia não pode duplicar dados. Testar isso explicitamente.
- Parquet como formato intermediário padrão (tipado e compacto).

# Logging e execução
- Módulo `logging` configurado em `src/pipeline_etl/utils/`; saída em `logs/`.
- Registrar por etapa: início, fim, duração, linhas lidas, linhas gravadas, linhas rejeitadas.
- Cada etapa pode rodar sozinha (útil para depurar) e o orquestrador roda todas em ordem.
- Falha em uma etapa interrompe as seguintes e registra o erro com contexto.

# Testes
- pytest em `tests/`, espelhando a estrutura de `src/`.
- Testar funções de transformação com DataFrames pequenos montados no próprio teste.
- Não chamar APIs reais nos testes; usar respostas de exemplo salvas.

# Boas práticas
- Configuração em `config/` (YAML) e segredos no `.env`; `config/.env.example` sem valores reais.
- Não versionar dados reais nem o arquivo do warehouse.
- Nunca inventar fonte de dados, endpoint ou parâmetro de biblioteca; marcar "verificar" quando houver dúvida.
