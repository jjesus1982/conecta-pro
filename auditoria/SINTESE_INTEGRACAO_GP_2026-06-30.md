Vou produzir a síntese de integração. Não preciso de ferramentas — os 11 relatórios já contêm toda a evidência técnica necessária. Entrego a análise consolidada diretamente.

---

# SÍNTESE DE INTEGRAÇÃO — Ecossistema de Gestão de Pessoas (Conecta PRO)

*Visão do arquiteto-chefe: como os 11 módulos se conversam — e onde isso quebra.*

A tese do ERP é "módulos que se conversam". A auditoria mostra que **a conversa é majoritariamente teatro**: há um backbone tecnicamente sólido (Redis Streams), mas ele liga quase nada — só **GEDEON e SOPHIA** consomem eventos, e mesmo as 3 arestas vivas de maior valor estão quebradas por mismatch de payload. O resto são publicadores falando para o vácuo, integrações "bidirecionais" que na verdade são endpoints HTTP manuais, e dois barramentos legados mortos. Abaixo, o grafo, as causas-raiz transversais, a matriz e o plano por alavancagem.

---

## 1) GRAFO DE FLUXO DE DADOS ENTRE OS MÓDULOS

### Convenção
- **VIVA**: produtor publica/escreve e há consumidor que efetivamente reage.
- **VIVA-QUEBRADA**: o wiring existe e dispara, mas o efeito é nulo por bug (payload, tipo, filtro).
- **MORTA**: evento publicado sem consumidor, OU consumidor inscrito sem produtor, OU dado esperado que nunca chega.

### 1.A — Arestas via EVENT-BUS (ConectaEventBus / Redis Streams)

| # | Produtor | Consumidor | Canal / evento | Estado | Por quê |
|---|---|---|---|---|---|
| E1 | DP/folha (admissão) | GEDEON `_on_funcionario_admitido` | `dp.funcionario.admitido` (stream `dp`) | **VIVA-QUEBRADA** | publisher manda `funcionario_nome`/`nome`; GEDEON lê `p.get("name")` → kit montado com funcionário vazio. `cliente_id` nunca setado → bloco `if cliente_id:` nunca executa. **Stream `ged` parado desde 2026-04-07.** |
| E2 | DP/folha (rescisão) | GEDEON `_on_funcionario_demitido` | `dp.funcionario.demitido` | **VIVA-QUEBRADA** | GEDEON lê `name`/`tipo`; publisher manda `funcionario_nome`/`motivo`. Mismatch duplo. Além disso, publish via `asyncio.create_task` fire-and-forget pode ser GC'd. |
| E3 | DP (férias) | GEDEON `_on_ferias_aprovadas` | `dp.ferias.aprovadas` | **VIVA-QUEBRADA** | GEDEON lê `p.get("nome")`; publisher manda `funcionario_nome`. |
| E4 | DP (folha fechada) | GEDEON `_on_folha_fechada` | `dp.folha.fechada` | **VIVA-QUEBRADA** | `close_payroll` filtra `status=="Ativo"` (banco usa `'ativo'`) → 0 employees; retorna `total_employees` mas controller publica `total_funcionarios` → evento sai com **total=0**. |
| E5 | SST | GEDEON `_on_aso_*` | `saude.aso.emitido` | **MORTA** | `sst/publishers.py` é **100% código morto** — nenhum caller. O único `publish_aso_emitido` chamado vem do módulo-fantasma `health_occupational` (1 exame). GEDEON nunca recebe ASO do fluxo real. |
| E6 | SST | GEDEON `_on_cat_registrada` | `operacional.cat.registrada` / `saude.cat` | **MORTA** | CAT criada em `gp_cats` não publica nada. Acoplada a nada (sem afastamento, sem S-2210, sem estabilidade). |
| E7 | Operações | GEDEON `_on_escala_publicada` | `operacional.escala.publicada` | **VIVA-QUEBRADA** | `Scale` não tem atributo `client_id` → `hasattr` sempre False → `cliente_id=None`, `funcionarios=[]` hardcoded. GEDEON ignora (handler só age se `cliente_id`). |
| E8 | Operações | GEDEON `_on_ocorrencia_registrada` | `operacional.ocorrencia.registrada` | **MORTA (sem dado)** | wiring OK, mas `occurrences=0` no banco — nunca dispara. |
| E9 | Ponto | GEDEON `_on_espelho_fechado` | `ponto.espelho.fechado` | **VIVA** | única aresta ponto→GEDEON realmente funcional (mas o espelho contém totais fictícios). |
| E10 | Ponto | GEDEON `_on_falta_confirmada` | `ponto.falta.confirmada` | **MORTA (sem dado)** | `gp_justifications=0` (endpoints Tangerino 404) — nunca dispara. |
| E11 | qualquer `dp.* rh.* operacional.* fiscal.* financeiro.*` | SOPHIA (indexação) | wildcard patterns | **VIVA** | indexa semanticamente; **`portal.*` está fora da lista** → todos os eventos do portal caem no vácuo. |
| E12 | RH (7 eventos: carreira/avaliação/360/onboarding) | — | `rh.*` (stream `rh`) | **MORTA** | publicados no Redis, dispatchados para **zero handlers**. Verificado no stream. |
| E13 | Portal (férias/doc solicitado/assinado) | — | `portal.*` | **MORTA** | 0 consumidores + SOPHIA não inscreve `portal.*`. Além disso, 2 dos 3 publishers nunca são chamados. |
| E14 | Operações (banco_horas, disciplinar, alocação, turno, diarista, substituição, comunicado — ~10 tipos) | — | `operacional.*` | **MORTA** | publish-no-op; nenhum consumidor. |
| E15 | DP (benefício, contrato, ponto_registrado, esocial, transferido) | — | `dp.*` extras | **MORTA** | maioria dos 15 eventos `dp` no Redis são arestas mortas. |
| E16 | Ponto | — | `ponto.batida.registrada` | **MORTA** | fire-and-forget, sem consumidor. |

### 1.B — Arestas via TABELA COMPARTILHADA (sem evento)

| # | Produtor | Consumidor | Tabela | Estado | Por quê |
|---|---|---|---|---|---|
| T1 | Domínio Sistemas (import externo) | DP/folha (leitura), Portal (contracheque) | `hr_payslips` (51 linhas, 03/2026) | **VIVA** | único caminho com dado real; mas IRRF=R$0 em 100% (suspeito), detalhamento pobre. |
| T2 | DP (vacation sync Sólides) | DP motor B (`_get_faltas_atrasos`) | `gp_justifications` (`type='falta'`) | **VIVA-QUEBRADA** | férias gravadas como **falta** → folha desconta férias como falta (dupla penalização). |
| T3 | DP (tela `dp/licencas` via `leave_controller`) | SST (leitura) | `sst_afastamentos` | **VIVA-QUEBRADA** | INSERT do DP **omite campos CCT** (estabilidade, ajuda-medicamento) → afastamento criado pela tela DP perde toda a lógica CCT. Dois caminhos de escrita divergentes. |
| T4 | DP (`dp_payslips_controller.publicar`) | Portal (`AutoNotificationService`) | `portal_notifications` | **VIVA-QUEBRADA** | pipeline existe e funciona por chamada direta, mas **0 linhas** — ninguém publicou holerite por esse fluxo. |
| T5 | Tangerino (sync Celery) | Ponto, Portal | `gp_clock_punches` (4158) | **VIVA-QUEBRADA** | dado corrompido **+4h** (TZ na origem); Portal importa classe inexistente (`ClockPunch` de tabela `clock_punches` que não existe) → ponto sempre vazio no portal. |
| T6 | — (nunca populado) | DP/folha (motor) | `gp_clock_punches` → folha | **MORTA** | folha **não importa ponto**; usa premissas fixas (noturno=`dias*7`). Ponto→folha inexiste. |
| T7 | — (nunca populado) | GED kits | `posts.ged_client_id` (0/12) | **MORTA** | FK zerada → kit depende de fuzzy-match por nome. |
| T8 | Operações | GED, GEDEON, Portal, Financeiro | `posts.client_id` (1/12), `contract_id` (0/12) | **MORTA** | elo posto↔cliente↔contrato solto → esvazia todos os dashboards por cliente. |
| T9 | Recrutamento (`hire()`) | DP (`admission_processes`) | `admission_processes` (0 linhas) | **MORTA** | `hire()` não cria admissão; ponte `on_candidate_approved` tem 3 bugs e é órfã. |
| T10 | Reembolso (`process_payment`) | Financeiro (`payable_accounts`) | `payable_account_id` | **MORTA** | grava `uuid4()` **falso**; `_create_payable_account` 100% comentado. Reembolso "pago" não vira lançamento. |
| T11 | Retention (climate) | HR-raso (leitura SQL-cru) | `climate_surveys` | **VIVA-QUEBRADA** | acoplamento por tabela; drift de schema seed↔código; `climate_responses=0` (coleta em 500 por TZ). |

### 1.C — Arestas via CHAMADA DIRETA / HTTP (integração "bidirecional")

| # | Caminho | Estado | Por quê |
|---|---|---|---|
| C1 | `POST /integration/...` (8 fluxos: shift_closed, occurrence, vacation_approved, candidate_approved, document_signed, termination, admission, mandatory_training) | **MORTA / STUB** | não são subscribers do bus — exigem chamada HTTP manual que ninguém faz. Vários são stubs (termination/admission só logam; vacation_approved instancia `ScaleOptimizerAI` e **descarta** resultado). |
| C2 | `health_occupational` consome `FUNCIONARIO_ADMITIDO` (MessageBus in-memory) | **MORTA** | MessageBus nunca tem `.start()` chamado → mensagens enfileiram e nunca processam. ASO admissional nunca agendado. |
| C3 | DP `complete_admission` → publica `DP_FUNCIONARIO_ADMITIDO` | **VIVA-QUEBRADA** | publica no ConectaEventBus (só GEDEON ouve, quebrado por payload); `health_occupational` ouve no MessageBus (morto) → exame admissional nunca agenda. |

### Resumo do grafo
- **Arestas VIVAS de fato úteis: 2** (E9 ponto→GEDEON espelho; E11 SOPHIA indexação; T1 Domínio→folha/portal).
- **Arestas VIVAS-QUEBRADAS (disparam, efeito nulo): ~9** (E1–E4, E7, T2–T5, C3).
- **Arestas MORTAS (~70% dos event_types): dezenas** (E5, E6, E8, E10, E12–E16, T6–T11, C1, C2).

O nó **GEDEON** é o único hub consumidor de negócio; o nó **`posts`** é o hub de dados que deveria amarrar operação↔cliente↔contrato↔GED↔financeiro e está solto. Quase todo o valor transversal passa por esses dois nós — e ambos estão quebrados.

---

## 2) PROBLEMAS SISTÊMICOS TRANSVERSAIS (causa-raiz + módulos afetados)

### S1 — TRÊS event-buses coexistindo, dois mortos (split-brain de barramento)
**Causa-raiz:** evolução histórica sem consolidação. Há `ConectaEventBus` (Streams, VIVO), `GPEventBus` (PubSub legado, nunca instanciado) e `MessageBus` (in-memory, `.start()` nunca chamado). Pior: `core/events/handlers.py:6` importa o `GPEventBus` legado (classe distinta do alias) — duas classes `Event`/`GPEventBus` em memória.
**Módulos afetados:** TODOS. Sintomas concretos: agents de `people_management` (dp_agent, ponto_agent, etc.) inscritos no GPEventBus morto → toda a cadeia "falta→desconto folha", "mês fechado→gerar folha" está morta; `health_occupational` inscrito no MessageBus morto → ASO admissional nunca dispara; portal publica no ConectaEventBus mas SOPHIA não inscreve `portal.*`.

### S2 — Contratos de payload não tipados e divergentes (a aresta viva que não entrega)
**Causa-raiz:** eventos são `dict` solto sem schema. Duas convenções de chave coexistem: `nome`/`employee_id` (SST) vs `funcionario_nome`/`funcionario_id` (DP). GEDEON lê chaves que ninguém envia (`name`, `tipo`, `nome`).
**Módulos afetados:** DP→GEDEON (E1–E4), SST→GEDEON. Efeito: GEDEON monta kits com funcionário vazio; **stream `ged` parado desde abril** enquanto admissões continuaram até junho. É a falha que invalida o único hub vivo.

### S3 — Split-brain de módulos paralelos (dois motores/duas tabelas/duas APIs por domínio)
**Causa-raiz:** retrabalho sem aposentar a versão anterior. Padrão repetido em **6 dos 11 módulos**:
- **Folha:** motor A (`calculo_service`, CCT 2026 correta) vs motor B (`payroll_service`, INSS 2024). INSS divergente por endpoint.
- **Ponto:** motor A (`ponto/`, pares brutos) vs motor B (`hr/time-records`, 8h CLT fixo). Telas DP e GP mostram números diferentes.
- **SST:** `people_management/sst` (real, `gp_*`/`sst_*`) vs `health_occupational` (fantasma, `health_*` quase vazio). Dashboard mistura os dois → 220 EPIs reais invisíveis, 1 exame fantasma exibido.
- **Clima:** `retention` (profundo, morto) vs `human_resources` (raso, vivo).
- **GED:** `/ged/*` (legado) vs `/people-management/ged/*` (pm-ged) sobre as MESMAS tabelas, respostas divergentes.
- **Frontend:** duplicação `/rh` vs `/gestao-pessoas/rh`, `portal-funcionario` vs `modulos/portal`, dois trees de saúde.

**Módulos afetados:** Folha, Ponto, SST, Clima/Retenção, GED, RH, Portal. Efeito: números contraditórios na mesma tela, manutenção dupla, frontend chamando o endpoint errado.

### S4 — Elo posto↔cliente↔contrato↔GED quebrado (o nó central solto)
**Causa-raiz:** `posts.client_id` preenchido em 1/12, `contract_id` 0/12, `ged_client_id` 0/12. Ninguém preenche a FK; criação de posto não exige cliente.
**Módulos afetados:** Operações (dashboards por cliente vazios), GED (kit depende de fuzzy-match), GEDEON (não associa escala/ocorrência ao condomínio → `cliente_id=None`), Portal do condomínio, Financeiro (não custeia posto por contrato). É a aresta de **maior impacto transversal** — um backfill aqui destrava 4 módulos.

### S5 — Corrupção de dado na origem (TZ +4h) e tabelas vazias
**Causa-raiz:** container UTC, `datetime.fromtimestamp(ts/1000)` grava naive +4h; leitura em America/Manaus. 4158 batidas corrompidas.
**Tabelas vazias estruturais:** `admission_processes`=0, `gp_justifications`=0, `gp_monthly_closings`=0, `climate_responses`=0, `portal_notifications`=0, `reimbursement_categories`=0, `evaluation_360_responses`=0. Cada vazio invalida uma cadeia inteira (recrutamento→DP, ponto→folha, clima→turnover).
**Módulos afetados:** Ponto, Folha, SST (noturno errado), Retenção, Portal, Recrutamento, RH.

### S6 — Bugs de rota/tipo que viram 500 ou silêncio
**Causa-raiz:** path params não tipados como UUID + `except Exception` que mascara falha como `[]`.
**Exemplos:** `/medidas-administrativas/stats` → 500 (`"stats"` vira UUID); `gp_monthly_closings.employee_id` int vs uuid (fechamento sempre 0); `registrar_ajuste` hash int em coluna uuid (nunca funcionou); `IntegrationService` usa `Shift.start_time` inexistente; portal `/my-schedules` → 500 (4 campos None). **Módulos afetados:** Operações, Ponto, Portal, SST.

### S7 — Compliance legal não conectado (o que gera multa/passivo)
**Causa-raiz:** os fluxos que geram obrigação legal não têm wiring.
- **eSocial SST:** S-2210 (CAT, prazo 1 dia útil), S-2220 (ASO), S-2240 (PPP) **inexistem**. Só S-2200/S-2299.
- **Afastamento→folha:** suspensão de salário (15º dia empresa→INSS), ajuda-medicamento R$300 (4 colab = R$1.200/mês calculado mas nunca lançado), **estabilidade não trava demissão** (passivo trabalhista).
- **INSS 2024 no clt_calculator** → rescisão/férias com valor legalmente incorreto.
- **AFD/Portaria 671 (REP-P)** inexistente no ponto.
**Módulos afetados:** SST, Folha, Ponto. São os que mais expõem a empresa juridicamente.

---

## 3) MATRIZ DE PRONTIDÃO CONSOLIDADA

| Módulo | Nota | Bloqueador principal (causa-raiz) |
|---|---|---|
| **RH Estratégico** | **48%** | 7 eventos `rh.*` sem consumidor (S1/E12); RH→SST com payload vazio (S2); 3 IAs do foco = código morto |
| **DP / Folha + CCT** | **42%** | INSS 2024 no clt_calculator (S7); 2 motores divergentes (S3); folha não persiste; admissão→GED quebrada (S2); férias viram falta (T2) |
| **SST / Saúde Ocupacional** | **38%** | Split-brain 3 camadas (S3); zero integração com folha (S7); eSocial SST inexistente (S7); publishers código morto (E5) |
| **Recrutamento** | **38%** | `hire()` não vira admissão; ponte com 3 bugs + órfã (T9); IA crasha 100% em dados reais |
| **Portal do Funcionário** | **38%** | Agregador que não agrega: 4/6 fluxos quebrados (500/vazio); 100% eventos sem consumidor (E13); `portal.*` fora do SOPHIA |
| **Backbone (event-bus)** | **34%** | Cola que liga quase nada: 2 consumidores, ~70% arestas mortas (S1); payload mismatch (S2); 2 buses mortos |
| **Reembolso** | **34%** | `process_payment` grava payable_account_id falso (T10); zero eventos; condominio_id NULL 100%; sem RBAC |
| **Operações** | **34%** | Ciclo escala→ponto→folha cortado em 3 pontos; elo posto↔cliente solto 1/12 (S4); pay sempre 0; bugs runtime |
| **GED / Kits** | **34%** | Handlers órfãos (nunca disparam); download quebrado 60% docs; 2 APIs concorrentes (S3); completude mede a coisa errada |
| **Ponto Eletrônico** | **32%** | Cálculo fictício (extras/noturno/banco=0/fixo); TZ +4h na origem (S5); ponto→folha inexiste (T6); 2 motores (S3) |
| **Retenção & Clima** | **22%** | Coleta em 500 por TZ; `climate_responses=0`; tabelas turnover inexistem; frontend aponta para o sistema raso; zero eventos |

**Média ponderada do ecossistema: ~35%.** Nenhum módulo passa de 48%. O teto é baixo justamente porque a nota de cada um é puxada para baixo pela **integração** (a tese do produto), não pela camada de cadastro/CRUD (que em vários casos está ~70%).

---

## 4) PLANO DE EXECUÇÃO PRIORIZADO POR ALAVANCAGEM

Princípio: priorizar correções que **destravam vários módulos de uma vez**. Esforço relativo em P (pequeno, <1 dia), M (médio, 1-3 dias), G (grande, semana+).

### FASE 0 — Decisões de arquitetura (bloqueia tudo, fazer primeiro, sequencial)
1. **Eleger UM event-bus (ConectaEventBus) e matar os 2 legados.** Deletar `agents/` (código morto, 49k+ linhas como o Guardian), `GPEventBus` PubSub, `MessageBus` in-memory. Corrigir `handlers.py:6` (import errado). **[M]** — destrava S1, limpa SST/Operações/Portal de wiring fantasma.
2. **Eleger fonte única por domínio** (split-brain S3): folha=motor A, ponto=um motor, SST=`gp_*`/`sst_*`, GED=pm-ged, clima=decidir. Reapontar o resto como fachada. **[M decisão / G execução]**

### FASE 1 — Máxima alavancagem (paralelizável após Fase 0)
*Estes 3 itens, sozinhos, ressuscitam o hub GEDEON e o nó `posts`.*

- **A1 — Padronizar contrato de payload dos eventos** (S2). Pydantic/dataclass por event_type, chave única `funcionario_nome`/`funcionario_id`. Corrigir GEDEON para ler as chaves certas. **[P]** → destrava E1–E4, E5: **revive o stream `ged` e 4 arestas DP→GEDEON + SST→GEDEON de uma vez.** Maior ROI absoluto.
- **A2 — Backfill `posts.client_id`/`contract_id`/`ged_client_id`** a partir dos 11 contratos reais + UI obrigatória + NOT NULL gradual (S4/T7/T8). **[M]** → destrava Operações (dashboards por cliente), GED (fim do fuzzy-match), GEDEON (`cliente_id` real), Portal-condomínio, Financeiro. **Destrava 5 módulos.**
- **A3 — Corrigir os bugs de filtro/tipo que zeram cadeias** (S6): `close_payroll` `'ativo'` + persistência + `total_employees` (E4); status capitalizado nos skills RH; path params UUID (Operações/Ponto/Portal/SST). **[P, paralelizável entre módulos]** → destrava E4, folha fechada real, e elimina os 500.

Paralelizáveis: A1, A2, A3 são independentes (3 terminais).

### FASE 2 — Conectar os fluxos legais e financeiros (paralelizável)
- **B1 — TZ na origem do ponto + migration dos 4158 punches** (S5). **[M]** → pré-requisito de ponto→folha e de noturno/extras corretos.
- **B2 — Motor único de cálculo CLT/CCT do ponto** (12x36/44h, noturno 52'30", banco de horas) alimentado por batidas reais. **[G]**
- **B3 — Ponto→folha**: `calculo_service` lê `gp_monthly_closings` fechado em vez de premissas fixas (T6). **[M, depende de B1+B2]**
- **B4 — INSS 2026 único no clt_calculator** (S7) + VR fora do líquido + parar de gravar férias como falta (T2). **[P]** — bloqueador legal, alta alavancagem (corrige rescisão+férias+folha).
- **B5 — Afastamento→folha + estabilidade→trava demissão + ajuda-medicamento** (S7): publicar `saude.afastamento.iniciado` no caminho real + handler na folha. Rotear INSERT do DP (`leave_controller`) para `SSTService.registrar_afastamento` (T3). **[M]**
- **B6 — eSocial SST** (S7): geradores S-2210/S-2220/S-2240. **[G]** — obrigação legal, mas isolável.

Paralelizáveis: B4 (independente, fazer já), B5 (independente), B6 (independente). B1→B2→B3 é cadeia sequencial.

### FASE 3 — Fechar os ciclos de pessoas (paralelizável)
- **C1 — `hire()`→admissão→employee** (T9): chamar `AdmissionService.create_admission(dict)` no `hire()` ou publicar `recrutamento.candidato.contratado`. Corrigir os 3 bugs da ponte + commit. **[M]** → fecha recrutamento→DP→portal→SST.
- **C2 — Reembolso→financeiro real** (T10): implementar `_create_payable_account` (PayableService já existe), transação atômica, vincular a `employee_id`. **[M]**
- **C3 — Converter arestas mortas de alto valor** em handlers reais: `portal.*`→DP (submissão de férias), `rh.*`→onboarding, `operacional.demissao`→desalocação. Inscrever `portal.*` no SOPHIA. **[M]**
- **C4 — GED**: corrigir download (path-base S6), completude (medir presença de arquivo, não assinatura), wire `payroll.closed`→`auto_build_all_kits`. **[M]**

### FASE 4 — Higiene e robustez (paralelizável, contínuo)
- DLQ/retry no bus (não-ack em falha); dedup por-item (TTL por evento). **[M]**
- Consolidar trees de frontend duplicados; regenerar orval. **[M]**
- Limpar lixo: 2.833 reuniões CIPA idênticas, registro espúrio Conecta Mais como ged_client, status órfãos de reembolso. **[P]**
- Endpoint de observabilidade do bus (`/admin/eventbus/health`). **[P]**

---

## 5) VEREDITO

### O ecossistema está a ~**30-35% de produção real ponta a ponta** (com os módulos se conversando).

A camada de **cadastro/CRUD isolado** está em ~60-70% em vários módulos (treinamento, contracheque-leitura, agendamento de entrevistas, captura de batida, CCT carregada). Mas a tese do produto — **"módulos que se conversam"** — está em ~20%: o backbone é sólido mas liga quase nada, o único hub consumidor (GEDEON) está cego por mismatch de payload desde abril, o nó de dados central (`posts`) está solto, e os três ciclos que justificam um ERP de Gestão de Pessoas estão **todos cortados**:

- **escala→ponto→folha** (cortado em 3 pontos: evento sem cliente, ponto corrompido +4h, folha não lê ponto),
- **recrutamento→admissão→DP→portal** (`hire()` não tem efeito downstream, `admission_processes`=0),
- **SST→folha/eSocial** (afastamento não suspende salário, CAT não vira S-2210, estabilidade não trava demissão).

Hoje o ecossistema funciona como **um conjunto de cadastros e dashboards visuais que compartilham um banco**, não como um organismo integrado. O dado que de fato circula vem de **import externo** (Domínio→`hr_payslips`, Tangerino→`gp_clock_punches`), não da conversa entre módulos.

### Os 3 movimentos de maior impacto

1. **Padronizar o contrato de payload dos eventos e corrigir GEDEON** (Fase 1/A1, esforço P). Sozinho, ressuscita o stream `ged` e 4-5 arestas DP/SST→GEDEON. É a correção de **maior ROI por unidade de esforço** de todo o sistema — transforma o hub vivo-quebrado em hub vivo.

2. **Backfill do elo posto↔cliente↔contrato↔GED** (Fase 1/A2, esforço M). Destrava **5 módulos** de uma vez (Operações, GED, GEDEON, Portal-condomínio, Financeiro). É o nó de dados que amarra toda a dimensão "por cliente" do ERP.

3. **Consolidar para UM event-bus + eleger fonte única por domínio** (Fase 0, esforço M). Elimina o split-brain que produz números contraditórios na mesma tela e mata o wiring fantasma (agents, MessageBus, GED duplo). Sem isso, qualquer correção pontual é construída sobre areia — dois motores continuarão divergindo e dois buses continuarão confundindo.

Os três juntos não "terminam" o produto, mas elevam o ecossistema de **~35% para ~60%** ao tornar reais as arestas que hoje são teatro — e, crucialmente, fazem-no atacando a **causa-raiz transversal** (S1, S2, S4), não os sintomas módulo a módulo.
