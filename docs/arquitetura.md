# Arquitetura do pipeline

## Visão geral
```
API SGS (JSON)        API Focus (OData)        Planilha ANBIMA (.xls)
     |                       |                          |
     v                       v                          v
raw/bcb_sgs/          raw/bcb_focus/            raw/anbima_feriados/   EXTRAÇÃO (incremental,
     |                       |                          |                partição por dia)
     v                       v                          v
stg_bcb_series        stg_focus_ipca_12m        stg_feriados           STAGING (pandas + checagens)
     |                       |                          |
     +-----------------------+--------------------------+
                             v
      DuckDB (DUCKDB_CAMINHO)                                   WAREHOUSE (SQL, uma transação)
        staging.*  ->  dim_serie, dim_data, fct_indicador, fct_expectativa
                   ->  mart_indicadores_mensal
                             |
                             v
      data/processed/indicadores_mensal.{parquet,csv}           EXPORTAÇÃO (relida e conferida)
                             |
                             v
      app.py (Streamlit)                                        PAINEL
```
Comando único: `pipeline-etl` (ou `python -m pipeline_etl.orquestracao.pipeline`).

## Fontes de dados
| Fonte | Tipo | Formato | Autenticação | Frequência | Chave única |
|-------|------|---------|--------------|------------|-------------|
| SGS / Banco Central (`bcb_sgs`) | API REST pública | JSON | nenhuma | diária e mensal, conforme a série | `codigo_serie` + `data` |
| Feriados nacionais ANBIMA (`anbima_feriados`) | arquivo baixado por URL | Excel 97-2003 (.xls) | nenhuma | atualização eventual (última: 22/12/2023) | `data` |
| Boletim Focus / Banco Central (`bcb_focus`) | API OData pública (Olinda) | JSON | nenhuma | diária (dias úteis) | `data_pesquisa` |

Séries SGS adicionadas em 2026-11-10:

| Código | Nome no projeto | Periodicidade | Uso |
|--------|-----------------|---------------|-----|
| 13522 | ipca_12m_oficial | mensal | só na checagem `09_ipca_12m_confere_oficial` |
| 189 | igpm_variacao_mensal | mensal | IGP-M mensal e 12 meses na mart |
| 4389 | cdi_anualizado | diária | CDI no fim do mês (% a.a.) |
| 24369 | desocupacao | mensal (trimestre móvel) | PNAD Contínua; convenção de data do SGS: verificar |

### Boletim Focus (expectativas de mercado)
- Endpoint: `https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/ExpectativasMercadoInflacao12Meses`.
- Filtro: `Indicador eq 'IPCA' and Suavizada eq 'S' and baseCalculo eq 0` (mais `Data ge` no incremental).
- **Espaços na query precisam ir como `%20`**: com `+` (padrão do `requests`), a API responde HTTP 400
  "The types 'Edm.Boolean' and 'Edm.String' are not compatible". A URL é montada com `urllib.parse.quote`.
- Primeira extração: 2.972 pesquisas, de 2015-01-02 a 2026-11-06.

### SGS / Banco Central
- Endpoint: `https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json&dataInicial=dd/mm/aaaa&dataFinal=dd/mm/aaaa`.
- Séries:

| Código | Nome no projeto | Periodicidade | Unidade |
|--------|-----------------|---------------|---------|
| 433 | ipca_variacao_mensal | mensal | % a.m. |
| 432 | selic_meta | diária | % a.a. |
| 1 | dolar_venda | diária (dias úteis) | R$/US$ |
| 13521 | meta_inflacao | anual (dia 1º de janeiro) | % a.a. |

- Regras observadas na API em 2026-11-10:
  - Séries diárias exigem `dataInicial`; a janela máxima é de 10 anos (sem isso, HTTP 406).
  - Resposta: lista de `{"data": "dd/mm/aaaa", "valor": "texto"}`. O valor vem como texto, com ponto decimal.
  - HTTP 404 com "Value(s) not found" significa janela sem dados; HTTP 404 com "A serie nao existe!" significa código inválido.
  - HTTP 304 com corpo vazio, mesmo sem a requisição pedir cache: o cache do servidor fica preso a uma URL exata (cache de até 15 min). Contorno no extrator: repetir com `dataFinal` um dia depois e descartar registros após o fim pedido. Observado na série 1 em 2026-11-10.
  - HTTP 502 ocasional (série 432 em 2026-11-10), resolvido na primeira nova tentativa.
- Raw: `data/raw/bcb_sgs/data_extracao=AAAA-MM-DD/serie_<codigo>.json`, com um `.meta.json` ao lado (período, quantidade, horário).
- Não confirmado: limite de requisições por minuto. Por precaução: pausa de 1 s entre chamadas e novas tentativas com espera crescente. Verificar.

### Feriados nacionais ANBIMA
- URL: `https://www.anbima.com.br/feriados/arqs/feriados_nacionais.xls`.
- Conteúdo conferido em 2026-11-10: aba "Feriados", colunas Data | Dia da Semana | Feriado, de 2001 a 2099 (1.264 feriados), com 9 linhas de rodapé (fonte e notas).
- Critério da ANBIMA (nota da própria planilha): feriados em que não há movimentação das reservas bancárias. Não inclui feriados municipais, eleições nem o último dia do ano.
- Já inclui o Dia da Consciência Negra (20/11) a partir de 2024.
- Raw: `data/raw/anbima_feriados/data_extracao=AAAA-MM-DD/feriados_nacionais.xls` + `.meta.json` (URL, bytes, sha256, data de modificação no servidor).
- O extrator confere a assinatura de arquivo .xls antes de salvar (evita gravar uma página de erro em HTML).
- Leitura com `pandas.read_excel(engine="calamine")`. O engine `xlrd` está obsoleto no pandas 3.
- Limitação: arquivo atualizado em 22/12/2023; mudanças de lei posteriores não aparecem. A checagem `08_dolar_somente_em_dia_util` detecta o caso mais provável (feriado faltando).

## Camadas
| Camada | Local | Formato | Conteúdo |
|--------|-------|---------|----------|
| raw | `data/raw/` | como veio da fonte | cópia fiel, particionada por data de extração |
| staging | `data/staging/` | Parquet | tipos e nomes padronizados, sem duplicatas; inválidos em `rejeitados/` |
| warehouse | `warehouse/` | DuckDB | fatos, dimensões e mart mensal |
| processed | `data/processed/` | Parquet e CSV | exportação final para consumo |

## Estratégia de carga
- **Incremental (padrão desde 2026-11-10):** cada série é extraída a partir da última data presente no raw
  menos `sobreposicao_dias` (SGS 62; Focus 30), para pegar revisões. Sem raw anterior, ou com `--completo`,
  baixa desde `data_inicial_padrao`. O staging junta todas as partições; data repetida fica com a extração
  mais recente.
- **HTTP 304 com janela de 10 anos:** se o contorno (estender `dataFinal` em 1 dia) estouraria o limite da
  API, a janela é dividida em duas.
- Extração SGS: histórico completo desde `data_inicial_padrao` a cada execução, em uma nova partição por dia.
- Extração ANBIMA: arquivo inteiro, uma partição por dia.
- Nas duas extrações, o que já foi extraído no dia é pulado (raw nunca é sobrescrito).
- Staging: reconstrução completa a partir do raw mais recente. Volume pequeno (~7,5 mil e ~1,3 mil linhas, menos de 1 s), então reconstruir é mais simples e seguro que incremental.
- Warehouse: reconstrução completa (`CREATE OR REPLACE`) dentro de uma única transação. DDL, staging, marts e checagens de qualidade rodam juntos; qualquer falha faz rollback e mantém o warehouse anterior.
- Exportação: arquivos substituídos de forma atômica e relidos para conferir a contagem de linhas.

## Warehouse
- Arquivo: `warehouse/pipeline.duckdb` (pode ser trocado por `DUCKDB_CAMINHO` no `.env`).
- Schemas: `staging` (cópia dos Parquets) e `marts` (modelo em estrela e mart mensal).
- Ordem de execução: `sql/ddl/` -> `sql/staging/` -> `sql/marts/` -> `sql/qualidade/`, cada pasta em ordem de nome.
- Parâmetros nos arquivos SQL no formato `{{nome}}`, substituídos pelo Python; falha se algum ficar sem valor.
- Chaves primárias declaradas (bloqueiam duplicatas na inserção). Chaves estrangeiras não declaradas, porque impediriam recriar as dimensões a cada carga; a integridade é conferida em `sql/qualidade/`.

## Orquestração
- `src/pipeline_etl/orquestracao/pipeline.py` roda, em ordem: `extracao_bcb_sgs`, `extracao_anbima_feriados`, `staging_bcb_sgs`, `staging_anbima_feriados`, `warehouse`, `exportacao`.
- Para na primeira falha, registra quais etapas não rodaram e termina com código de saída 1 (permite agendar e monitorar).
- Opções: `--sem-extracao` (usa o raw já baixado, sem acessar a internet) e `--etapas` (só algumas, sempre na ordem oficial).
- Cada execução tem um identificador (`AAAAMMDD-HHMMSS`) nos logs, que ficam em `logs/pipeline_AAAA-MM-DD.log`.
- Cada etapa também pode rodar sozinha com `python -m pipeline_etl.<pacote>.<modulo>`.

## Qualidade
Toda checagem que falha interrompe a etapa antes de gravar.

Staging das séries (`stg_bcb_series`, 10 checagens):
- chave única (`codigo_serie` + `data_referencia`);
- nenhum nulo nas colunas obrigatórias;
- `data_referencia` não posterior a `data_extracao`;
- conciliação: linhas raw = válidas + rejeitadas + duplicatas removidas;
- cada série configurada com pelo menos uma linha;
- valor dentro da `faixa_valida` da série (`config/pipeline.yaml`). Limites de sanidade escolhidos no projeto, não oficiais.

Staging dos feriados (`stg_feriados`, 8 checagens):
- chave única (`data`); nenhum nulo; nome não vazio;
- dia da semana da planilha confere com a data;
- conciliação: linhas da planilha = feriados + rodapé; feriados = datas + datas repetidas;
- pelo menos `min_feriados_por_ano` (10) feriados em cada ano; nenhum ano faltando no intervalo.

Warehouse (`sql/qualidade/`, 8 consultas; zero linhas = aprovado):
1. fato sem série na dimensão;
2. fato sem data no calendário;
3. staging e fato com mesma contagem e mesma soma de valores por série;
4. calendário contínuo e não vazio;
5. série da dimensão sem nenhum fato;
6. ano do calendário sem nenhum feriado (arquivo não cobre o período);
7. mart mensal sem meses faltando;
8. cotação do dólar em dia não útil (cruza as duas fontes).

Exportação (2 checagens): cada arquivo relido tem as mesmas linhas da tabela de origem.

## Painel (consumo)
- `app.py` (Streamlit 1.67) lê a exportação `data/processed/indicadores_mensal.parquet`; sem ela, lê `marts.mart_indicadores_mensal` do DuckDB em modo somente leitura. Sem nenhum dos dois, mostra como rodar o pipeline.
- Cache (`st.cache_data`) com a data de modificação dos arquivos na chave: depois de um `pipeline-etl`, basta recarregar a página.
- Filtro de período sem callbacks: atalhos (12 meses, 3 anos, 5 anos, Tudo) e "Personalizado", que mostra o slider de meses.
- Gráficos seguem a skill de dataviz: um eixo por gráfico, cor fixa por indicador, legenda com 2+ séries, rótulo direto só no último valor, polaridade (inflação x deflação, alta x queda) com par quente/frio, mapa de calor sequencial de um só matiz.
- Verificado com `AppTest` (testes) e com a agent API do Streamlit no app real (todas as páginas e filtros, console sem avisos).
- Filtros guardados entre páginas com `persist_state="session"` (sem isso, o período personalizado se perdia ao trocar de página).

### Exportação, comparador e alertas (2026-11-10)
- **Exportar (barra lateral, todas as páginas):** relatório executivo em HTML (resumo, comparação MoM/YoY, alertas, dados mensais e método; tema claro, imprimível como PDF) e CSV do período. Página Alertas exporta a lista de alertas.
- **Comparador:** mês de referência (padrão: último com IPCA) contra o mês anterior (MoM), o mesmo mês do ano anterior (YoY) e um mês opcional; Δ absoluto (p.p. para taxas) e variação relativa (%). Janelas de 3, 6 ou 12 meses contra a janela anterior (IPCA acumulado, médias, soma de dias úteis). Usa a mart inteira para achar os meses de base.
- **Alertas** (`src/pipeline_etl/dashboard/analise.py`, limites em `painel` no `config/pipeline.yaml`):

| Severidade | Regra | Limite |
|------------|-------|--------|
| Crítico | IPCA 12 meses acima do teto da meta | centro (SGS 13521) + tolerância do CMN (1,5 p.p.; 2,0 em 2015-2016) |
| Atenção | IPCA 12 meses acima do centro (dentro da tolerância) ou abaixo do piso | centro / centro - tolerância |
| Atenção | IPCA mensal elevado | 1,0% no mês (escolha do projeto) |
| Atenção | Variação forte do dólar | alta ou queda de 5% no mês (escolha do projeto) |
| Atenção | Dólar em nível recorde | acima de todos os meses anteriores, após 12 meses de histórico |
| Atenção | Juro real negativo | Selic meta abaixo do IPCA 12 meses |
| Informativo | Deflação | IPCA do mês < 0 |

- Tolerância da meta: de memória, marcada "verificar". Conferência indireta: as regras apontam teto estourado em dez/2015, 2021, 2022 e 2024 e piso em 2017, os anos com carta aberta do BCB ao CMN; 2016 (6,29%) fica dentro só com a tolerância de 2,0 p.p.
- Sinalização visual: destaques dos últimos 3 meses na Visão geral (`st.error`/`st.warning`/`st.info` com ícone e título); gráfico IPCA 12 meses x meta (faixa de tolerância, quadrados vermelhos acima do teto); losangos nas variações fortes do dólar; linha do tempo na página Alertas (cor + símbolo por severidade). Cores de status da paleta da skill de dataviz, sempre com ícone e texto.

## Qualidade (atualização 2026-11-10)
46 checagens: staging SGS 20 (8 séries), feriados 8, Focus 6, warehouse 10, exportação 2. Novas no warehouse:
- `09_ipca_12m_confere_oficial`: IPCA 12 meses calculado x SGS 13522, tolerância de 0,02 p.p.
  (diferença máxima observada: 0,01 p.p. em 3 de 130 meses, por arredondamento);
- `10_expectativa_sem_dim_data`: pesquisa do Focus sem data no calendário.

## Ambiente local
- `DUCKDB_CAMINHO` no `.env` aponta o warehouse para `C:/Users/Usuario/dados_pipeline_etl/`, fora do OneDrive
  (a sincronização pode travar o arquivo durante a carga).
- **Não usar `AppData`**: o Python da Microsoft Store (usado neste projeto) redireciona gravações em
  `AppData\Local` para `AppData\Local\Packages\PythonSoftwareFoundation.Python.3.13_...\LocalCache`;
  o Python enxerga o arquivo, mas o Explorer, o `cmd` e outras ferramentas não.
- Execução agendada: tarefa `PipelineETL_Indicadores` (dias úteis, 19h), registrada por
  `scripts/agendar_tarefa_windows.ps1`. Configurada para iniciar também na bateria: o padrão do `schtasks`
  deixa a execução na fila ("Queued") em notebook fora da tomada.

## Atualização pelo painel (botão "Atualizar dados")
- Barra lateral do `app.py` (`src/pipeline_etl/dashboard/atualizacao.py`): roda as 8 etapas do pipeline com
  `reextrair_hoje=True`, mostra o progresso de cada etapa (`st.status`), limpa o cache da mart e recarrega a
  página. Em 2026-11-10 a primeira execução levou 5 s (incremental) e trouxe a cotação do dólar do próprio dia,
  publicada depois da extração da manhã.
- **Raw versionado no mesmo dia:** a primeira extração do dia grava `serie_<codigo>.json`; as seguintes gravam
  `serie_<codigo>__HHMMSS.json` na mesma partição (o raw continua imutável). `src/pipeline_etl/utils/raw.py`
  lista os arquivos na ordem de extração e o staging fica com a versão mais nova de cada data. A planilha da
  ANBIMA continua com uma extração por dia.
- Proteções: trava por servidor (uma atualização por vez, para todos os usuários) e intervalo mínimo entre
  atualizações (`painel.atualizacao.intervalo_minimo_minutos`, padrão 10), contado a partir da última carga.
  `painel.atualizacao.permitir: false` desativa o botão.
- Falha: erro na tela e dados anteriores mantidos (warehouse em transação; exportação só depois dela).
- Pela linha de comando: `pipeline-etl --reextrair-hoje`.

## CI e publicação
- GitHub Actions (`.github/workflows/ci.yml`): `ruff check`, `ruff format --check`, `ty check`
  (código de produção: `src/`, `app.py`, `paginas/`) e `pytest` a cada envio para `main`.
- Dependências: `requirements.txt` (pipeline e painel; é o que o Streamlit Cloud instala) e
  `requirements-dev.txt` (testes, lint, notebooks, Playwright).
- A mart final `data/processed/indicadores_mensal.parquet` é versionada (exceção no `.gitignore`) para o
  painel publicado. O resto de `data/` e o warehouse ficam fora do Git.
- `app.py` coloca `src/` no caminho de importação, porque o Streamlit Cloud não roda `pip install -e .`.
- Capturas do painel para o README: `scripts/capturar_telas.py` (Playwright, Chromium sem janela).

## Notas técnicas
- DuckDB 2.0: o resultado de `duckdb.sql()` não tem mais `.fetchone()`; usar `.fetchall()` (ou `.limit(1).fetchall()`). Observado em 2026-11-10.
- `carregado_em` volta do Parquet em UTC: converter para `America/Sao_Paulo` antes de exibir.
- Um `streamlit run` em execução não recarrega módulos de `src/` alterados: reiniciar depois de mudar o pacote.
- Variação relativa (%) só é calculada sobre base positiva: de -0,32% para 0,82% não é "-356%".
- pandas 3: `Series.dt.dayofweek` está obsoleto; usar `dt.day_of_week`. O engine `xlrd` de `read_excel` está obsoleto; usar `calamine`.
- Terminal do Windows (Git Bash) pode exibir acentos como "�"; os dados estão corretos (conferido comparando os textos).

## Decisões
| Data | Decisão | Motivo |
|------|---------|--------|
| 2026-11-07 | DuckDB como warehouse local | sem servidor, lê Parquet direto, bom para portfólio |
| 2026-11-10 | SGS/BCB como primeira fonte | pública, sem chave, estável, dados brasileiros, séries temporais permitem carga incremental por data |
| 2026-11-10 | Raw não é sobrescrito no mesmo dia | se já foi extraído na data, é pulado antes de acessar a fonte |
| 2026-11-10 | Staging em pandas, uma tabela longa para as 3 séries | mesmo formato (data, valor) nas séries; facilita checagens e carga |
| 2026-11-10 | Linhas inválidas vão para `rejeitados/` | nada é descartado em silêncio |
| 2026-11-10 | Gravação de Parquet atômica (.tmp e depois troca) | falha no meio não corrompe o arquivo anterior |
| 2026-11-10 | Fato `fct_indicador` (não `fct_indicador_diario`) | a granularidade varia por série: IPCA é mensal |
| 2026-11-10 | `codigo_serie` como chave de `dim_serie`, sem surrogate key | código SGS é estável |
| 2026-11-10 | Sem FOREIGN KEY declarada; integridade checada em SQL | FK impediria o `CREATE OR REPLACE` das dimensões |
| 2026-11-10 | Carga do warehouse em uma transação | falha não deixa o warehouse pela metade |
| 2026-11-10 | Feriados da ANBIMA como segunda fonte (arquivo) | referência de dias úteis do mercado financeiro; evita montar feriados móveis à mão |
| 2026-11-10 | Dois feriados na mesma data viram uma linha ("A / B") | mantém a chave `data` única sem perder informação |
| 2026-11-10 | Mart mensal "larga" (uma coluna por indicador) | formato pronto para planilha e BI; o modelo longo continua no warehouse |
| 2026-11-10 | CSV com vírgula e ponto decimal | padrão que abre em qualquer ferramenta; para Excel em português usar o Parquet ou importar o CSV |
| 2026-11-10 | Checagem 08 só no sentido "cotação em dia não útil" | o sentido inverso falharia à toa enquanto o BCB não publica a cotação do dia |
| 2026-11-10 | Painel com Plotly e CSS neon (não Vega/ECharts nativos) | mesmo padrão visual dos outros projetos do portfólio, pedido explícito |
| 2026-11-10 | Paleta escurecida para a faixa do modo escuro e juro real em magenta | validador reprovou o neon claro (luminosidade) e azul x violeta (daltonismo) |
| 2026-11-10 | Meta de inflação como série do pipeline (SGS 13521) | dado oficial em vez de valores fixos no código; tolerância fica no config |
| 2026-11-10 | Relatório executivo em HTML (não PDF/Word gerado no servidor) | sem dependências novas, abre em qualquer navegador, imprime como PDF |
| 2026-11-10 | Tolerância da meta confirmada (2,0 p.p. até 2016; 1,5 p.p. desde 2017) | Resolução CMN 4.419/2015; 2025+ (meta contínua) ainda a verificar |
| 2026-11-10 | Focus em fato próprio (`fct_expectativa`) | expectativa (projeção numa data) e realizado têm significados diferentes |
| 2026-11-10 | Extração incremental com sobreposição | menos chamadas à API; a sobreposição pega revisões; `--completo` refaz tudo |
| 2026-11-10 | Warehouse fora do OneDrive e fora do AppData | sincronização trava arquivos; Python da Store redireciona AppData |
| 2026-11-10 | Agendador do Windows (não Prefect) | sem dependência nova; o orquestrador já devolve código de saída |
| 2026-11-10 | IGP-M (verde-água) nunca no mesmo gráfico que o dólar (ciano) | validador de paleta: parecidos na visão normal (ΔE 10,6) |
| 2026-11-10 | Botão do painel grava nova versão do raw do dia (`__HHMMSS`) | buscar dados publicados ao longo do dia sem sobrescrever o raw |
| 2026-11-10 | Intervalo mínimo de 10 min entre atualizações pelo painel | painel público: evita excesso de chamadas às APIs do BCB |

## Execuções
| Data | Fonte | Registros | Período retornado | Observação |
|------|-------|-----------|-------------------|------------|
| 2026-11-10 | 433 IPCA | 141 | 2015-01 a 2026-09 | IPCA de outubro ainda não divulgado |
| 2026-11-10 | 432 Meta Selic | 4.332 | 2015-01-01 a 2026-11-10 | inclui fins de semana (valor vigente) |
| 2026-11-10 | 1 Dólar venda | 2.973 | 2015-01-02 a 2026-11-09 | só dias úteis; 304 contornado |
| 2026-11-10 | Feriados ANBIMA | 1.264 feriados / 1.263 datas | 2001 a 2099 | 21/04/2079 com dois feriados |
| 2026-11-10 | Pipeline completo | mart: 143 meses | 2015-01 a 2026-11 | 28 checagens aprovadas; 2,8 s |

Cruzamento de 2015-01-02 a 2026-11-09: os 2.973 dias úteis da ANBIMA são exatamente os 2.973 dias com cotação do dólar (zero divergências).
