# projeto_pipeline_etl

Terceiro projeto de portfólio da Molina, focado em engenharia e análise de dados: pipelines automatizados de extração (APIs, arquivos, bancos), limpeza, transformação e carga em um modelo pronto para consumo analítico.

## Status atual
- Fase: projeto completo e publicado (2026-11-10). Repositório público: github.com/molinatr19-star/projeto_pipeline_etl (CI no GitHub Actions).
- Fontes: API SGS do BCB (433 IPCA, 432 Selic meta, 1 dólar venda, 13521 meta de inflação, 13522 IPCA 12m oficial, 189 IGP-M, 4389 CDI, 24369 desocupação), API OData do Focus (expectativa IPCA 12 meses) e planilha .xls de feriados da ANBIMA.
- Comando único: `pipeline-etl` (8 etapas; incremental por padrão; `--sem-extracao` não acessa a internet; `--completo` só na extração SGS/Focus via módulo).
- Fluxo: extração -> staging (pandas) -> warehouse DuckDB (SQL em `sql/`, uma transação) -> exportação `data/processed/indicadores_mensal.{parquet,csv}` -> painel `app.py`.
- 46 checagens de qualidade (20 + 8 + 6 no staging, 10 SQL no warehouse, 2 na exportação) e 89 testes. `ruff`, `ty` (só código de produção) e `pytest` rodam no CI.
- Warehouse local em `C:/Users/Usuario/dados_pipeline_etl/pipeline.duckdb` via `DUCKDB_CAMINHO` no `.env` (fora do OneDrive; nunca em AppData: o Python da Microsoft Store redireciona).
- Agendamento: tarefa do Windows `PipelineETL_Indicadores`, dias úteis 19h (`scripts/agendar_tarefa_windows.ps1`, log em `logs/agendador.log`).
- Painel: 8 páginas (`paginas/`), lógica em `src/pipeline_etl/dashboard/` (dados, analise, relatorio, estilo, graficos). Filtros com `persist_state="session"`. Reiniciar o `streamlit run` depois de mudar `src/`.
- Cores fixas por indicador, validadas (dark, fundo #12141c): Selic #3987e5, IPCA #c98500 (Focus = IPCA tracejado), juro real #d55181, dólar #1aa3b8, IGP-M #199e70, desocupação #9085e9, dias úteis/CDI #6b7a99. IGP-M nunca junto do dólar; desocupação nunca junto da Selic. Revalidar antes de trocar.
- Painel online: falta a Molina publicar em share.streamlit.io (passos no README); a mart final é versionada para isso.
- Pendências "verificar": tolerância da meta de 2025 em diante; convenção de data da desocupação no SGS 24369.
- Detalhes em `docs/arquitetura.md` (decisões, regras das fontes, execuções) e `docs/dicionario_dados.md`.
- Não executar o pipeline nem implementar novas etapas sem pedido explícito da Molina.

## Objetivo do projeto
- Construir um pipeline ETL/ELT reproduzível, de ponta a ponta:
  - Extrair dados de pelo menos uma API pública e um arquivo (CSV/JSON).
  - Limpar e padronizar com Python (pandas) e SQL.
  - Modelar em camadas até tabelas analíticas (fatos e dimensões).
  - Validar qualidade a cada etapa e registrar logs de execução.
  - Permitir reexecução sem duplicar dados (idempotência).
- Entregável final: código em `src/`, SQL versionado em `sql/`, documentação da arquitetura em `docs/`, testes e README de portfólio.

## Tecnologias
- Python 3.13 (ambiente virtual `.venv` local).
- Extração: requests (APIs REST), leitura de CSV/JSON/Parquet com pandas.
- Transformação: pandas, numpy, pyarrow (Parquet), SQL.
- Banco analítico local: DuckDB (caminho em `DUCKDB_CAMINHO`; padrão `warehouse/`).
- Configuração: python-dotenv (`.env`) e YAML (`config/`).
- Qualidade e testes: pytest; validações próprias em `src/pipeline_etl/qualidade/`.
- Orquestração: início com script de linha de comando; agendador (Prefect ou Airflow) só em fase posterior, se a Molina pedir.
- Estilo: ruff.
- Dependências listadas em `requirements.txt`; adicionar novas lá ao usá-las.

## Arquitetura em camadas
```
fonte (API / arquivo / banco)
   -> data/raw/        cópia fiel da fonte, nunca editada (bronze)
   -> data/staging/    tipos corrigidos, nomes padronizados, sem duplicatas (silver)
   -> warehouse/       DuckDB com fatos e dimensões (gold / marts)
   -> data/processed/  exportações finais em Parquet/CSV para consumo
```

## Estrutura
```
config/                 configurações (YAML) e .env.example
data/raw/               dados brutos extraídos, particionados por data de extração
data/staging/           dados limpos intermediários (Parquet)
data/processed/         saídas finais para consumo analítico
data/external/          tabelas de apoio (calendário, códigos IBGE etc.)
warehouse/              arquivo do banco analítico (DuckDB)
sql/ddl/                criação de schemas e tabelas
sql/staging/            SQL de limpeza e padronização
sql/marts/              SQL de fatos, dimensões e agregações
sql/qualidade/          consultas de validação (contagens, nulos, chaves)
src/pipeline_etl/
  extracao/             conectores de API, arquivos e bancos
  transformacao/        limpeza e regras de negócio em pandas
  carga/                escrita em Parquet e no warehouse
  qualidade/            checagens de dados
  orquestracao/         ordem de execução das etapas e CLI
  utils/                logging, caminhos, leitura de configuração
notebooks/              exploração e demonstração (numerados: 01_, 02_)
logs/                   logs de execução do pipeline
docs/                   arquitetura, dicionário de dados e decisões
reports/figures/        imagens para README e documentação
tests/                  testes com pytest
```

## Diretrizes de código
- Lógica reutilizável em `src/pipeline_etl/`; notebooks só exploram e demonstram.
- Separar as etapas: extrair não transforma; transformar não grava; carregar não aplica regra de negócio.
- Funções pequenas, com type hints e docstring curta. Nomes em português, de forma consistente.
- Caminhos com `pathlib.Path`, relativos à raiz do projeto. Nada de caminho absoluto no código.
- Configuração fora do código: URLs, parâmetros e nomes de tabela em `config/`; segredos só no `.env`.
- Usar `logging` (não `print`) para registrar início, fim, quantidade de linhas e erros de cada etapa.

## Diretrizes de engenharia de dados
- Fluxo em uma direção: raw -> staging -> warehouse -> processed. Nunca sobrescrever `data/raw`.
- Idempotência: rodar o pipeline duas vezes com a mesma entrada gera o mesmo resultado, sem duplicar linhas.
- Carga incremental quando a fonte permitir (por data ou ID); documentar a estratégia em `docs/`.
- Particionar dados brutos por data de extração (`data/raw/<fonte>/data_extracao=AAAA-MM-DD/`).
- Toda tabela tem chave definida (natural ou surrogate) e colunas de auditoria (`carregado_em`, `fonte`).
- Datas em ISO 8601; fuso explícito (`America/Sao_Paulo`) quando houver hora.
- Unidade ou tipo no nome quando ajudar: `valor_brl`, `peso_kg`, `data_pedido`.
- Nomes de tabelas e colunas em `snake_case`, sem acento. Prefixos: `stg_` (staging), `dim_` (dimensão), `fct_` (fato).
- Validar a cada camada: contagem de linhas, nulos em colunas obrigatórias, chaves únicas, faixas de valores.
- Registrar cada tabela e coluna nova em `docs/dicionario_dados.md`.

## APIs e segredos
- Chaves de API e senhas só no `.env` (nunca versionado). Manter `config/.env.example` atualizado, sem valores reais.
- Respeitar limites de requisição da API: pausa entre chamadas, tentativas com espera crescente, timeout definido.
- Ler a documentação oficial da API antes de implementar; não supor nomes de endpoints ou parâmetros.
- Dados pessoais: anonimizar antes de versionar ou publicar no portfólio.

## SQL
- Um arquivo por objeto ou transformação, com nome numerado quando houver ordem (`01_stg_clientes.sql`).
- Usar CTEs para legibilidade; evitar `SELECT *` nas camadas finais.
- Palavras-chave em maiúsculas, nomes em minúsculas.
- Comentar no topo do arquivo: objetivo, tabelas de origem e granularidade do resultado.

## Apoio do Claude
- Agente do projeto: `.claude/agents/engenheiro-dados-etl.md`.
- Skills do projeto: `.claude/skills/pipeline-etl/SKILL.md` e `.claude/skills/sql-analitico/SKILL.md`.
- Responder em português do Brasil, direto, em tópicos, sem emojis.
- Explicar o porquê de cada etapa (o projeto também é de aprendizado).
- Nunca inventar APIs, endpoints, funções ou parâmetros de bibliotecas. Em dúvida, marcar como "verificar".
