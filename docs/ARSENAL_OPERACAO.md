# Arsenal — página operacional (1 página)

**O que roda, quando, e como ler.** As lições e a história estão em `docs/ARSENAL_SKILLS.md`;
esta página é só operação. `backend/scripts/qa/checar_arsenal.py` confere as duas contra o disco.

## O que roda sozinho

| Quando | O quê | Onde ler |
|---|---|---|
| 00:00 (cron do host) | `scripts/oraculos_diarios.sh` → varredura dos oráculos `test_*.py` de `backend/scripts/orq/` | `/var/log/conecta-oraculos.log` |
| logo depois | `backend/scripts/qa/checar_regressao.py` → caçadores contra a linha de base + travas de sim/não | mesmo log |
| domingo, na mesma rodada | gates `fechado_*.py` e `varredura_op_acoes.py` — conta condições ✅, acusa quando CAI | mesmo log |
| logo depois | `checar_bake_pendente.py --assar` — assa o que está por docker cp se: lock livre, 01–05h, `backend/` limpo no git, WhatsApp quieto 30 min, sem migration pendente | `/var/log/conecta-bake-auto.log` |
| beat do Celery | `orq.checar_varredura_ausente` — grita se a varredura não rodou em 30h | sino |

**Sino: corte automático.** `checar_sino_surdo` corta sozinho a origem surda há 14 medições
seguidas (gatilho `sino_corte_bi`; nunca o arsenal nem o digest) e avisa uma vez. Comandos:
`--cortar <origem>` · `--religar <origem>` · `--cortadas`.

**Leitura de tela com pessoa.** `crm_audit_log` passa a receber `GET /api/v1/redesign/data/<slug>`
(middleware) — `checar_uso_real` mostra quem abriu qual tela e quando. Vale a partir do bake.

**Sino só recebe NOVIDADE**: vermelho novo, resolvido, oráculo que passou a bloqueado, trava que
passou a falhar ou voltou a passar. O mesmo vermelho repetido fica no log e volta ao sino na
segunda-feira. Medido em 06/09/2026: 5.387 avisos em 30 dias, 19 abertos — avisar todo dia é
o mesmo que não avisar.

## Como ler o log

```
[oraculos] 118 verdes, 2 vermelhos, 2 bloqueados, 0 não rodados em 2100s
  x test_x.py — AssertionError: …          ← VERMELHO: divergência (defeito, ou oráculo congelado)
  ? test_y.py — BLOQUEADO: LLM sem crédito  ← não deu para medir hoje; não é defeito, não é verde
  - test_z.py — não rodou (lote estourou)   ← o teto de 90min foi batido; ver "mais lentos"
[oraculos] Comparado à rodada anterior: 1 NOVO(s): test_x.py; 1 resolvido(s).
── travas mecânicas ──
  cacar_fabricacao.py: 37 (estável)         ← dívida conhecida, base em /var/lib/conecta/qa_baseline.json
  x checar_vocabulario.py: 11 -> 13 REGRESSÃO   ← código novo trouxe pista nova
  x checar_beats.py: NÃO VERIFICADO           ← a trava não respondeu; NÃO é verde
```

Três estados por oráculo, e nenhum se confunde com o outro:

| Estado | Exit | Significa |
|---|---|---|
| verde | 0 | exibido == banco |
| vermelho | ≠0, ≠3 | divergência — ou defeito de produto, ou o oráculo ficou preso a uma versão antiga |
| BLOQUEADO | 3 (`_fixtures.bloqueado`) | pré-condição ausente ou dependência externa fora; "não deu para medir" |

## Os caçadores (`backend/scripts/qa/`)

**Contados** (têm linha de base; acusam quando a dívida CRESCE):

| Caçador | Onde roda | Linha canônica | Pergunta |
|---|---|---|---|
| `cacar_fabricacao.py` | container | `N pista(s) em` | valor inventado quando a fonte falha? |
| `checar_vocabulario.py` | container | `(N crítica(s)` | lista literal que a coluna não tem? |
| `checar_varchar_teto.py` | container | `TOTAL: N coluna(s) no teto` | varchar(N) com valor encostado no teto? |
| `checar_repositorio.py` | host | `TOTAL: N` | chamada a método que o repositório não tem? |
| `checar_rotas_frontend.py` | host | `TOTAL: N` | front chamando rota que o backend não tem? |
| `checar_oraculo_externo.py` | host | `TOTAL: N` | número que ninguém de fora confirma? |
| `checar_uso_real.py` | host (delega banco ao container) | `TOTAL: N tabela(s) com 0 linhas` | quem escreve, quem chama, e quando? tabela nascida morta? `--quem <email>` · `--mortas` mostra nascimento |
| `checar_sino_surdo.py` | container | `TOTAL: N origem(ns) surda(s)` | origem do sino com volume e ninguém abre? |
| `checar_llm_martelando.py` | container | `TOTAL: N origem(ns) martelando` | origem chamando o LLM em loop com <5% de sucesso nas últimas 24h? |
| `checar_nao_vigiado.py` | container (~5 min) | `TOTAL: N tela(s) sem vigia` | tela do redesign sem oráculo nem regra que a cite? |
| `checar_irreversivel.py` | host | `TOTAL: N função(ões) que disparam antes de gravar` | registro criado depois do disparo externo? |
| `checar_dominio.py` | host (banco via docker) | `TOTAL: N divergência(s) de domínio` | o código diz o que `verdades_dominio.py` diz? a verdade venceu? |
| `checar_beat_engole_falha.py` | host | `TOTAL: N task(s) que engolem falha` | beat que absorve a própria falha? (linha de base) |
| `checar_botao_morto.py` | container | `TOTAL: N botão(ões) morto(s)` | tela do redesign chamando endpoint que o app não tem? (linha de base) |
| `checar_tabela_fantasma.py` | container | `fantasmas N (U usadas · E entulho)` | modelo declara tabela que não existe? (linha de base, ~90 s) |
| `checar_cobertura_rotas.py` | host (enumera as rotas dentro do container) | `TOTAL nenhum: N · classico: M · rotas: R` (binária: 0 · 0) | rota montada sem tela no redesign e sem chamador interno? alias/externo/dono contam à parte |
| `checar_chamadas_sem_rota.py` | host (enumera as rotas dentro do container) | `TOTAL chamadas sem rota: N (alcançável pelo redesign) · M (só clássico)` (binária: N = 0) | o frontend chama rota que o backend não tem? inversa da cobertura; só clássico é dívida contada |
| `checar_fantasmas_container.py` | host (lista o container) | `TOTAL fantasmas no container: N` (binária: N = 0) | o container tem `.py` que o repositório não tem? `docker cp` não apaga — o fantasma faz as duas travas acima medirem rota que o bake vai derrubar (09/09) |
| `checar_oraculos_no_container.py` | host (lista o container) | `TOTAL instrumentos fora do container: N` (binária: N = 0) | oráculo (`scripts/orq`) ou caçador (`scripts/qa`) que está no git e não está na imagem NÃO roda — a varredura e o checar_regressao chamam de dentro do container; contar pelo disco é afirmar sobre o repositório, não sobre quem vigia (09/09) |
| `checar_import_orfao.py` | host | `OK checar_import_orfao` / `FAIL checar_import_orfao` | algum import de topo aponta para módulo apagado? (binária) |
| `checar_bake_pendente.py` | host | `TOTAL: N arquivo(s) no ar fora da imagem` | o que está por docker cp? (`--assar`: assa na madrugada se as 6 guardas passam) |

Sem a linha canônica a rodada é **NÃO VERIFICADA**: acusa e a base não se move (foi assim que a
base caiu a 0 em 23/08 e acusou "0 → 25" por dez noites).

**Sim/não** (exit code decide; teto por trava): `checar_beats.py` (rotina agendada que não
produz), `checar_periodo_do_servidor.py` (data vinda do modelo), `checar_desmonte_comportamento.py`
(oráculo que deixa linha em produção — ~1h, só `test_*`), `checar_sucesso_vazio.py` (motor responde
200 sem frase), `checar_registros_servidor.py` (registro vazio ou encolhido no processo do servidor;
memória em `system_configs`, `--aceitar` para encolhimento deliberado), `checar_arsenal.py` (este documento mentindo), `checar_mcp_tools.py` (peça de
parede fora do git ou da imagem).

**Paridade com a DGX (13/09/2026)** — nove caçadores nascidos com as 10 frentes do benchmark
(`auditoria/BENCHMARK_DIGIEXPRESS_DGX_2026-09-12.md` + `PREMORTEM_10_FRENTES_2026-09-12.md`):

| Caçador | Onde roda | Linha canônica | Pergunta |
|---|---|---|---|
| `checar_modulo_morto.py` | container | `TOTAL módulos mortos: N` | módulo com código e 0 rotas montadas, 0 imports, 0 task? Nasce em 4 e só cai por DECISÃO do dono (ligar ou aposentar) |
| `checar_ponto_sem_instrumento.py` | container | `TOTAL pessoas sem instrumento: N` | gente batendo ponto sem linha AFD desde o corte de 13/09? |
| `checar_batida_offline_suspeita.py` | container | `TOTAL batidas offline suspeitas: N` | relógio do aparelho fora do limite, duplicata por chave, ou dia com taxa facial 100% (taxa perfeita = não comparou) |
| `checar_repasse_sem_aditivo.py` | container | `TOTAL repasses sem aditivo: N` | preço de contrato alterado por rotina sem aditivo assinado? Alvo permanente: 0 |
| `checar_arma_sem_serie.py` | container | `TOTAL armas sem série/responsável: N` | arma/colete alocado sem série ou sem responsável — contador não responde "onde está a arma 3" |
| `checar_fila_offline_estourando.py` | container | `TOTAL itens offline atrasados: N` | item da ronda parado há mais de 24h no aparelho (o servidor não vê o que não subiu) |
| `checar_frota_sem_km.py` | container | `TOTAL veículos sem KM no período: N` | sem leitura de KM o painel marca todo veículo como vencido e é ignorado em uma semana |
| `checar_tela_lenta.py` | host (`QA_BASE`, `QA_TETO_S`) | `TOTAL telas lentas: N` | tela do redesign acima do teto de 3s — tela que demora é tela que o supervisor abandona |
| `checar_at_time_zone_sem_fuso.py` | host (varre o repo + `information_schema`) | `TOTAL conversões erradas: N` | `AT TIME ZONE 'America/Manaus'` direto em coluna sem fuso: SOMA 4h em vez de subtrair |

**MCP e agente** (nascidos em 11–12/09, estavam fora deste documento): `checar_escopo_mcp.py`,
`checar_etiqueta_de_risco.py`, `checar_tool_quebrada.py`, `checar_telefone_funcionario.py`,
`checar_mcp_tools.py`, `checar_changelog_mcp.py`, `checar_imagem_mcp.py`,
`checar_mcp_declara_escrita.py`, `checar_regressao_mcp.py`, `checar_vazamento_interno.py`,
`checar_contrato_sem_cobranca.py`.

**Gates semanais** (condições ✅ entram na base; acusa quando o número cai): `fechado_bartolo.py`,
`fechado_contratos.py`, `fechado_fiscal.py`, `fechado_gedeon.py`, `fechado_operacional.py`,
`varredura_op_acoes.py`.

**À mão** (com argumentos): `provar_desmonte.py <oráculo> <tabela>` — prova de desmonte de um
oráculo recém-escrito. Mutação em produção: sempre via `_mutacao.Mutacao` (ensaio, `--aplicar`).

### As que faltavam neste documento (conferido em 25/09/2026)

O `checar_arsenal` acusa quando o DOCUMENTO e o disco discordam — instrução velha faz o
próximo errar com confiança. Estas existem, rodam pelo `checar_regressao.py`, e a pergunta
de cada uma sai da primeira linha do docstring dela, não de uma cópia que envelhece aqui:

| Caçador | Pergunta |
|---|---|
| `checar_acao_faltando.py` | Tela que LISTA e não deixa MEXER — o mapa do que obriga o dono a ir ao terminal |
| `checar_acesso_de_quem_saiu.py` | Quem não trabalha mais aqui não entra no sistema |
| `checar_afastamento_vs_cadastro.py` | Afastamento aberto e cadastro dizendo outra coisa |
| `checar_alocacao_de_quem_saiu.py` | Alocação ATIVA de quem não trabalha mais: a cobertura do posto mente para cima |
| `checar_aso_sem_lastro.py` | ASO que não prova exame nenhum — e por isso o número de "vencidos" não quer dizer nada |
| `checar_batida_sem_foto.py` | Batida do app sem a selfie guardada — a evidência que o app tira e o servidor perdia |
| `checar_capacidade_sem_botao.py` | CAPACIDADE SEM BOTÃO: o sistema sabe fazer e nenhuma tela oferece — o mapa do terminal |
| `checar_contrato_front_back.py` | Chave do contrato que o backend EMITE e o frontend publicado NÃO SABE LER |
| `checar_contrato_vs_nota.py` | O que está no CONTRATO é o que foi para a NOTA? — a conferência que ninguém fazia |
| `checar_data_do_banco_no_fuso.py` | Data que o banco manda em UTC gravada como dia de Manaus — 15% dos lançamentos da Cora no dia errado |
| `checar_imagem_sumida.py` | Container de produção rodando imagem SEM TAG ou AUSENTE — o drift que `checar_drift_workers` não vê, porque compara os containers entre si |
| `checar_diarista_impagavel.py` | Diarista que trabalhou e não tem como receber — e nome fora do padrão da lista |
| `checar_chave_pix.py` | Chave PIX que não leva o dinheiro até a pessoa (tipo × valor, CPF inválido, chave repetida, folha pagando chave nunca provada pelo banco) |
| `checar_tela_sem_porta.py` | Tela que o backend serve e nenhum menu alcança · ação /redesign/action que nenhuma tela chama |
| `checar_escala_paridade.py` | Escala 12x36 lançada na paridade OPOSTA às batidas (grade nos ímpares, vida nos pares) — faz ponto, benefício e cobertura mentirem juntos |
| `checar_parametro_ambiguo.py` | O mesmo `:p` em `SET col = :p` e em `CASE WHEN :p = …` sem CAST — o asyncpg deduz dois tipos e recusa a query (500 mudo; derrubou o lote Inter e o webhook da Cora) |
| `checar_hermes_skill_retrieval.py` | O skill-retrieval está de fato ENCOLHENDO o prompt — e não escondendo as nossas skills |
| `checar_hermes_so_ve_o_que_executa.py` | O Hermes só enxerga, do conector `conecta`, as ferramentas que ele CONSEGUE executar |
| `checar_holerite_de_mes_futuro.py` | Holerite de competência que ainda não aconteceu — e holerite sem origem declarada |
| `checar_id_tipo_divergente.py` | Coluna `*_id` de um tipo comparando com um `id` de outro: o JOIN devolve 500 ou zero linha |
| `checar_pessoa_fora_do_app_de_ponto.py` | Gente ativa que não bate ponto pelo Conecta PRO — desde 13/09 isso é gente SEM ponto |
| `checar_natureza_saldo_contabil.py` | Conta com saldo CONTRÁRIO à natureza — ativo credor, passivo devedor, receita a débito: o lugar mais barato onde erro de classificação aparece |
| `checar_pronto_para_produzir.py` | Endereço do emitente completo e município do tomador — o que a SEFAZ recusa antes de olhar o resto |
| `checar_receita_nao_lancada.py` | NFS-e emitida que não virou receita no razão, lançamento em competência diferente da nota, e nota de HOMOLOGAÇÃO contada como faturamento |
| `checar_apuracao_sem_empresa.py` | Encerramento de resultado com `empresa_id` nulo — a ECD de cada CNPJ sai sem o Diário de encerramento e as duas PJ fecham juntas |
| `checar_transitoria_aberta.py` | O que sobrou em «Saídas/Entradas a Classificar», agrupado por contraparte — fila de decisão finita em vez de uma linha sem significado no DRE |
| `checar_custo_recorrente_nao_mapeado.py` | Compromisso que se repete todo mês e não está em `financial_custos_recorrentes` — e o que PAROU de ser pago, que também é decisão |
| `checar_nota_duplicada.py` | Mesma competência, mesmo tomador, mesmo valor, duas notas — cliente cobrado em dobro e ISS sobre faturamento que não existiu |
| `checar_contrato_vs_faturado.py` | Contrato vigente que não virou nota no mês, nota fora do contratado, e nota sem contrato — a base de uma receita previsível |
| `checar_dinheiro_fora_do_sistema.py` | Contrato ativo cujo dinheiro não aparece em conta nenhuma que o sistema conheça — inadimplência invisível, ou recebimento fora do sistema |
| `checar_recebimento_sem_nota.py` | Cliente que depositou mais do que foi faturado para ele no período — o terceiro lado do triângulo (nota ←→ dinheiro); os outros dois partem do contrato e não alcançam quem recebe fora dele |
| `checar_obrigacao_sem_gerador.py` | Obrigação que o regime EXIGE e para a qual não há rota PRODUTORA no app — a conta da rescisão com a Portte; `GET .../status` não conta, consultar não é produzir |
| `checar_abertura_nao_levantada.py` | O que impede o balanço de abertura de 31/12/2025 ficar de pé sem a contabilidade anterior — dado que falta E saldo de natureza impossível; e o que dele NÃO pode ser inventado (saldo invertido é PISTA, não prova) |
| `checar_parcelamento_em_atraso.py` | Parcelamento tributário fora do balanço e em atraso — R$ 582.262,83 na PGFN (recibo de adesão de 20/10/2025) contra o que o razão registra; atraso acumulado RESCINDE, perde 60,02% de desconto e tranca nova transação por 2 anos |
| `checar_patronal_nao_declarada.py` | Empresa do Simples cuja CPP patronal não está NEM dentro do DAS NEM na DCTFWeb — no Anexo III ela é ~43% da guia; na Patrimonial a guia de 07/2026 traz R$ 171,06 e a de 08/2026, nada, enquanto a DCTFWeb declara só `1082-01 CP SEGURADOS`. ~R$ 24 mil/mês sem documento, com o dinheiro já retido pelos clientes (Lei 9.711) e sobrando como crédito |
| `checar_fornecedor_saldo_invertido.py` | `2.1.4.01 Fornecedores a Pagar` com saldo DEVEDOR: pagou-se mais do que se escriturou por competência — o preço honesto do casamento pagamento×nota tomada, que quando erra inverte o passivo em vez de sumir com a despesa calada |
| `checar_credito_retencao_dormente.py` | Crédito de retenção na fonte (11%, Lei 9.711/98) crescendo sem ser compensado — R$ 84.709,90 parados na Patrimonial em 26/09, ~R$ 25 mil/mês entrando, porque a CPP patronal que ele existe para abater não está sendo declarada. Não é inadimplência de cliente: é tributo já recolhido em nosso nome |
| `checar_operacao_que_nao_se_paga.py` | Empresa cuja OPERAÇÃO não se paga — receita de serviço menor que a despesa operacional (financeiras fora) em TODOS os meses olhados. Resultado total pode estar no azul por receita que não vem da operação; só o operacional diz se o negócio deve existir. Eletrônica em −136,5% em 08/2026 |
| `checar_contrato_sem_nota_no_mes.py` | Contrato ativo, fora da carência, sem nota na competência CORRENTE — os dois parentes olham meses anteriores e não pegaram o buraco de 09/2026. Respeita `grace_period_days`, campo que existia preenchido e que nenhuma lógica de faturamento lia. E DECLARA o que descarta: foi assim que apareceram um contrato vencido ainda `active` e um ativo de valor zero faturando R$ 23 mil |

## Comandos

```bash
# rodar a rodada da noite agora (leva 1–2h; não rode com deploy em curso)
/opt/conecta-pro/scripts/oraculos_diarios.sh && tail -80 /var/log/conecta-oraculos.log

# um oráculo
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_<nome>.py

# só os caçadores contados, e aceitar a dívida atual como base (decisão vai na mensagem do commit)
python3 backend/scripts/qa/checar_regressao.py --gravar

# forçar os gates semanais
python3 backend/scripts/qa/checar_regressao.py --gates

# uso real por família (o instrumento do mapa VIVO · DESLIGADO · MORTO)
python3 backend/scripts/qa/checar_uso_real.py            # famílias
python3 backend/scripts/qa/checar_uso_real.py --tabelas  # + por tabela
python3 backend/scripts/qa/checar_uso_real.py --mortas   # só as com 0 linhas
```

## Regras que valem sempre

- Trava nova entra em `checar_regressao.py` (contada, sim/não ou gate) **ou** em `ORFAS_DECLARADAS`
  com dono e motivo. Trava que ninguém invoca reprova a rodada.
- Oráculo que não pode medir hoje chama `bloqueado("motivo")`, nunca `assert False`.
- Número em comentário leva a data em que foi medido.
- `git commit -m … -- <arquivos>`; arquivo novo exige `git add` nomeado; confira o EXIT CODE.
- Dinheiro que sai e governo: nunca happy-path. Operacional: relatório, nunca correção.

## Cobertura rotas × telas (08/09/2026)
`python3 backend/scripts/qa/checar_cobertura_rotas.py [--tsv saida.tsv]` — enumera as rotas montadas dentro do container (método, path, handler) e classifica cada uma pelo chamador, nesta precedência: **redesign** (builders, `redesign_data_controller`, apps vivos: `/redesign`, `/modulos/meu-espaco`, área do cliente, assinar, homologação, painel de ponto, login, candidato, PJ, primeiro acesso) · **interna** (MCP, agents, tasks, orquestrador, serviços, core, scripts, robôs, cron, nginx — inclusive handler reusado por import ou referência) · **alias** (montagem dupla: mesmo handler já coberto) · **externo** (webhook/callback/oauth) · **dono** (`/api/v1/reimbursements/*`, decisão de 07/09) · **classico** (só `/modulos` antigo) · **nenhum**. Casa path literal, prefixo, rota com parâmetro por regex, URL montada em pedaços (constante de prefixo, concatenação implícita, `portalFetch`).
Linha canônica: `TOTAL nenhum: N · classico: M · rotas: R`. Alvo: `nenhum: 0 · classico: 0`. Série de 08/09 em `auditoria/qa/revisao_20260908/cobertura_rotas_T{0..6}.tsv`: T0 1752 · 569 · 249 → T6 **1220 · 0 · 0** (redesign 819 · interna 357 · alias 23 · externo 15 · dono 6). Leva ~1 min. Trava declarada com dono (sessão fase5) até entrar no `checar_regressao.py`; rota nova sem chamador volta a aparecer aqui no dia seguinte.
