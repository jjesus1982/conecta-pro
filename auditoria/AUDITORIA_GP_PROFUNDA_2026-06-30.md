# AUDITORIA PROFUNDA — Gestão de Pessoas (11 módulos) — 2026-06-30

## SÍNTESE DE INTEGRAÇÃO

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

---

## ANÁLISES POR MÓDULO

### ?

I have a complete picture. `dependentes` is JSONB array `[]` so `len()` works correctly (0 deps). Frontend is wired. Now I'll compile the exhaustive report.

---

# AUDITORIA PROFUNDA — Módulo DP / Folha de Pagamento + CCT (Conecta PRO)

## 1) INVENTÁRIO — LÓGICA REAL

### 1.A — Há DOIS motores de folha paralelos e desconectados

**Motor A — `folha/services/calculo_service.py`** (sync, SQL cru, "CCT 2026 SINDECOMPRESTS")
- `calcular_folha_colaborador()` (linha 80): lê `employees` por `status='ativo'`, monta proventos/descontos hardcoded. Proventos: Salário Base, Intrajornada não concedida (só 12x36, 1,5×hora×15 dias, linha 128), Adicional Noturno (só `turno='noturno'`, fator redução 60/52,5, linha 143), **Vale Refeição (VR_DIA=22×dias, linha 157)**. Descontos: INSS, IRRF, VT 4%, VR 1%, Odonto R$9, Seguro R$2, Taxa Negocial R$22 bimestral (meses ímpares).
- `calcular_folha_batch_com_guard()` (linha 317) e `get_dashboard_folha()` (linha 394): **"guard"** — se há linhas em `hr_payslips` para o período (importadas do Domínio Sistemas), agrega esses dados e **NÃO usa o motor interno**; senão retorna ZEROS (não recalcula). O motor interno só roda em `/calcular/{emp}` e `/conferencia` e `/calcular/todos`.
- Tabelas legais 2026 embutidas (linhas 18-31): INSS `1518/2793.88/4190.83/8157.41`, IRRF até teto 4664.68.

**Motor B — `hr/services/payroll_service.py`** (async, ORM, "visão DP com cálculos CLT reais")
- `calculate_employee_payroll()` (linha 59): usa `clt_calculator`. Busca horas extras de `overtime_records`, noturnas, faltas/atrasos de `gp_justifications`+`solides_absences`, benefícios de `EmployeeBenefit`, dependentes (JSONB). Proventos: salário, periculosidade (30%, via `getattr(employee,'adicional_periculosidade')` — **coluna inexistente**), noturno, HE 50/100, DSR. Descontos: INSS, IRRF (com dependentes), VT, benefícios, faltas, atrasos.
- `close_payroll()` (linha 222): itera `Employee.status == "Ativo"`, soma, publica `DP_FOLHA_FECHADA`. **Não persiste nada em hr_payslips** (nenhum INSERT). É um "fechamento" que não fecha nada.

**Motor C (cálculo) — `common/utils/clt_calculator.py`**: INSS/IRRF/férias/13º/rescisão/HE/adicionais. Usado por payroll_service, termination_service, vacation_service.

### 1.B — CCT (`cct/`)
- `cct_service.py`: hierarquia cache Redis → banco (`cct_convencoes/cargos/feriados/beneficios`) → fallback constantes Python (`modules.cct.models.*`). `get_direitos_cargo`, `get_beneficios_cct`, `get_feriados`, `get_adicional_noturno`. `calcular_rescisao` delega a `modules.cct.validators.termination_validator.TerminationValidator` (módulo legado externo, import com try/except).
- `admin_cct_controller.py`: CRUD de convenções/cargos. Repositório com cache Redis 24h, lookup de cargo por nome UPPER (linha 138-140).
- **1 convenção vigente no banco**, 52 cargos, 8 benefícios — dados reais carregados.

### 1.C — Rescisão (`hr/services/termination_service.py`)
- `calculate_severance()` (linha 108): estima saldo FGTS = `salario×0.08×meses` (linha 149, **aproximação grosseira, ignora HE/adicionais e variação salarial**), férias vencidas "30 dias se >12 meses" (linha 152, **simplificação que ignora múltiplos períodos aquisitivos vencidos**), chama `calcular_rescisao`. `complete_termination` (linha 189): muda Employee.status='Desligado', publica `DP_FUNCIONARIO_DEMITIDO` via `asyncio.create_task` (fire-and-forget).

### 1.D — Férias (`hr/services/vacation_service.py`)
- `calculate_vacation_balance()` (linha 96): dias direito = `(meses//12)*30 + int(30/12*meses%12)`. Busca gozadas de `VacationRequest` status approved. `sync_vacations_from_solides()`: importa férias do Tangerino/Sólides → grava em **gp_justifications como `justification_type='falta'`** (linha 343 — semântica errada, férias viram falta).

### 1.E — Admissão (`hr/services/admission_service.py`)
- `complete_admission()` (linha 209): cria `Employee` em `modules.operacional.models.employee` com `salario_base=admission.salary_proposed`, publica `DP_FUNCIONARIO_ADMITIDO`.

## 2) FRONTEND
- **Wired**: `dp/folha/page.tsx` (→ `/people-management/folha/dashboard|rubricas|resumo|calcular/todos` + `/dp/payroll/pay-batch`), `dp/rescisao/page.tsx` (→ `/hr/terminations` + calculate/complete), `dp/ferias`, `dp/admissao`, `portal/contracheque`, `portal-funcionario/contracheques`.
- **UX/robustez**: `folha/page.tsx` linha 242-247 tem cascata de fallbacks (`resumo ?? dashboard ?? reduce(salary_proposed...)`) que, quando não há payslips, **soma `salary_proposed`/`salario_base` cru como "bruto"**, exibindo número que não bate com nenhuma folha real. `||` (linha 243-246) zera valores legitimamente 0 (IRRF=0 vira fallback).
- Botão "pay-batch" aponta para `/dp/payroll/pay-batch` (outro módulo) — fluxo de pagamento PIX separado.

## 3) BANCO (dados reais)
- `hr_payslips`: **51 linhas, TODAS em 03/2026**, status `published`. Totais: proventos R$97.504,07, líquido R$66.677,59, INSS R$6.811,67, FGTS R$6.944,65, **IRRF R$0,00 em todas** (suspeito — nenhum dos 51 paga IR). `hr_payslip_items`: 560. JSONB `earnings`/`deductions` com apenas **1 item cada** por payslip (linha sample) — detalhamento pobre.
- `employees`: 53 ativos / 18 inativos. **13 ativos com `salario_base` NULL** (`com_sal=40, sem_sal=13`). `escala_padrao`: 1 NULL, 35×12x36, 17×44h. `turno_padrao`: **19 NULL**, 9 noturno, 25 diurno.
- `cct_cargos`: 52; `cct_beneficios`: 8; `cct_convencoes`: 1 vigente; `rubricas_folha`: 24 ativas.
- `hr_vacation_requests`: 15. `dependentes`: JSONB array (sample `[]`).
- **Coluna `adicional_periculosidade` NÃO existe** em `employees`.

## 4) ⚠️ INTEGRAÇÃO (seção crítica)

### Eventos que o módulo PUBLICA → consumidores
| Evento | Onde nasce | Payload | Consumidor |
|---|---|---|---|
| `DP_FUNCIONARIO_ADMITIDO` | admission_service:271 | `employee_id, nome, cargo, departamento, data_admissao, admission_id` | `gedeon._on_funcionario_admitido` |
| `DP_FUNCIONARIO_DEMITIDO` | termination_service:241 | `employee_id, termination_id, tipo_rescisao, ultimo_dia, cargo` | `gedeon._on_funcionario_demitido` |
| `DP_FERIAS_APROVADAS` | vacation_service:228 | `vacation_id, employee_id, start_date, end_date, days_requested` | `gedeon._on_ferias_aprovadas` |
| `DP_FOLHA_FECHADA` | payroll_service:286 + controller publish_folha_fechada | `competencia, total_funcionarios/total_employees(!), total_bruto...` | `gedeon._on_folha_fechada` |
| `DP_HOLERITE_GERADO` | (só publisher, **nenhum caller real**) | — | gedeon (subscribe sem produtor) |

### Eventos que CONSOME ← origem
- O módulo DP **não consome** eventos de outros módulos diretamente nos services de folha. O consumo cross-módulo é todo no **gedeon** (orquestrador GED), que escuta DP + Operacional + Fiscal + Saúde + Ponto.

### Tabelas COMPARTILHADAS
- **lê**: `employees` (operacional), `overtime_records`, `gp_justifications` (ponto/GP), `solides_absences`/`solides_employees` (staging Sólides), `cct_*`, `rubricas_folha`, `EmployeeBenefit`.
- **lê/escreve**: `hr_payslips`/`hr_payslip_items` (escrita **só** via `dp_payslips_controller` import e Domínio; o motor de folha **não escreve**), `gp_justifications` (vacation sync grava aqui), `termination_processes`, `admission_processes`, `hr_vacation_requests`.

### 🔴 ARESTAS QUEBRADAS (as conexões que falham)
1. **Admissão → Gedeon: payload incompatível.** Admissão publica `payload["nome"]` mas `gedeon._on_funcionario_admitido` lê `p.get("name")` (vazio sempre) e usa `event.cliente_id` que **nunca é setado** no publish (linha 271-285 não passa `cliente_id`) → bloco de criação de kit GED (`if cliente_id:`) **nunca executa**. Admissão não gera kit no GED.
2. **`DP_FOLHA_FECHADA` carrega total errado.** `payroll_service.close_payroll` retorna chave `total_employees` (linha 273) mas o controller publica `result.get("total_funcionarios", 0)` → **sempre 0**. Gedeon recebe folha fechada com 0 funcionários.
3. **`close_payroll` filtra `status=="Ativo"`** (linha 239/243) enquanto o banco usa **`'ativo'` minúsculo** → consulta retorna **ZERO employees**, folha "fecha" vazia. (O motor A usa `'ativo'` correto.)
4. **`DP_HOLERITE_GERADO`**: publisher existe, gedeon assina, mas **nenhum código chama** `publish_holerite_gerado` no fluxo de folha → kit mensal nunca recebe o holerite por esse evento.
5. **Dois event buses**: services usam `infrastructure.event_bus`; existe também `modules/people_management/core/events/event_bus.py` (handlers próprios) — risco de evento publicado num bus e consumidor registrado no outro. Gedeon assina o `infrastructure` bus, então o `core/events` fica órfão.
6. **Férias do Sólides gravadas como `'falta'`** (vacation_service:343) → o motor B `_get_faltas_atrasos` conta `justification_type='falta'` (payroll_service:401) e **desconta férias como falta na folha**. Bug de dupla penalização.

## 5) BUGS CONCRETOS (file:line + fix)

1. **INSS 2026 DESATUALIZADO no clt_calculator** — `clt_calculator.py:16-25`: usa salário mínimo R$1.412 e teto INSS R$7.786,02 (tabela **2024**). O motor A já tem a tabela 2026 correta (1518/2793.88/4190.83/8157.41, teto contrib. R$951,63). Resultado: payroll_service, **termination e férias calculam INSS errado** (R$908,86 de teto vs R$951,63 correto). *Fix*: substituir `INSS_FAIXAS`, `SALARIO_MINIMO=1518.00`, `TETO_INSS=8157.41` e unificar com `FAIXAS_INSS_2026`.

2. **DUAS tabelas INSS divergentes** — `calculo_service.py:18` vs `clt_calculator.py:20`. Mesma folha pode dar INSS diferente conforme o endpoint. *Fix*: fonte única (idealmente `cct_*` no banco; hoje hardcoded em 2 lugares).

3. **VR somado ao bruto e ao líquido** — `calculo_service.py:157-166`: Vale Refeição (R$330) entra em `proventos`→`total_proventos`→`liquido`, mas só desconta 1% (R$16,70, linha 211). VR é benefício, **não compõe salário em dinheiro**. Inflaciona o líquido em ~R$313 por colaborador. *Fix*: tratar VR como informativo/benefício fora do líquido em caixa, ou descontar valor proporcional correto.

4. **`close_payroll` status capitalizado** — `payroll_service.py:239,243` `Employee.status == "Ativo"` vs banco `'ativo'`. *Fix*: `func.lower(Employee.status) == "ativo"`.

5. **Evento folha total=0** — `payroll_controller.py` (close_payroll publish) usa `total_funcionarios` ausente. *Fix*: `result.get("total_employees")`.

6. **Periculosidade nunca paga** — `payroll_service.py:91` lê coluna inexistente `adicional_periculosidade` via getattr → sempre None. *Fix*: criar coluna ou ler de `cct_cargos.adicional_tipo`.

7. **Rescisão: avos por subtração de mês** — `clt_calculator.py:351` `meses_ano=(demissao.month-admissao.month)%12` ignora o ano e a regra de 15 dias por mês trabalhado; multi-ano só não estoura por `min(...,12)`. 13º/férias proporcionais podem sair errados. *Fix*: contar avos reais mês a mês (≥15 dias = 1 avo).

8. **Aviso prévio: dias retornados inconsistentes** — `clt_calculator.py:413`: `aviso_previo_dias` retorna 0 quando não há aviso, mas em acordo retorna dias cheios mesmo pagando 50% (confunde relatório).

9. **`complete_termination` usa `asyncio.create_task`** (linha 241) dentro de request — task pode ser garbage-collected/perdida antes de rodar; evento de demissão pode não chegar ao GED. *Fix*: await direto ou outbox.

10. **Dashboard sem dados retorna zeros silenciosos** — `calculo_service.py:441`: meses sem import do Domínio mostram R$0 (não "erro"), e o frontend cai no fallback `salary_proposed` (page.tsx:242) exibindo número fantasma. *Fix*: status explícito na UI.

11. **IRRF R$0 em 100% dos 51 payslips** — dado importado suspeito; nenhum colaborador acima da faixa de isenção? Possível falha no parser de import do Domínio (fora deste módulo, mas afeta a folha exibida).

12. **`importar-alterdata` é stub** — `folha_controller.py:218`: lê o CSV, conta linhas e descarta; não persiste nem confronta. `/conferencia` sempre retorna `liquido_alterdata=None`. Funcionalidade de conciliação **inexistente**.

13. **`/ajuste` é stub** — `folha_controller.py:132`: retorna sucesso sem gravar nada ("será aplicado no próximo cálculo" — não é).

## 6) GAPS DE PRODUÇÃO
- **Persistência da folha calculada**: o motor interno nunca grava `hr_payslips`. Toda a folha real vem de import do Domínio (T2). O ERP é leitor, não calculador de verdade. *Por quê*: decisão "Domínio é fonte de verdade" (guard). *Como*: ou assumir 100% Domínio (remover motor interno enganoso) ou persistir cálculo próprio para conciliação real.
- **Conciliação Alterdata/Domínio**: stub. Falta parser + diff + persistência de divergências.
- **13º e folha anual**: não há geração de 13º (1ª/2ª parcela) no motor — só dentro de rescisão.
- **eSocial / SEFIP / FGTS Digital**: publisher `DP_ESOCIAL_GERADO` existe mas sem geração de eventos S-1200/S-2299 reais.
- **Cadastro incompleto**: 13 ativos sem salário, 19 sem turno → motor interno produz INSS/noturno errados para eles.
- **Múltiplos períodos aquisitivos de férias**: simplificação "30 dias se >12 meses" subestima passivo.
- **Idempotência de fechamento**: `close_payroll` não trava reprocessamento nem cria registro de competência fechada.

## 7) NOTA DE PRONTIDÃO: **42%**

**Justificativa:**
- **A favor (+)**: Portal do funcionário lê corretamente `hr_payslips` (51 contracheques reais 03/2026 exibíveis em PDF); CCT carregada no banco (1 convenção, 52 cargos, 8 benefícios) com cache+fallback robusto; rescisão/férias têm motor Decimal estruturado e telas wired; eventos de admissão/demissão/férias publicam.
- **Contra (−)**: **Tabela INSS 2026 errada no clt_calculator** (cálculos legais de rescisão/férias incorretos) — bloqueador legal; **dois motores divergentes** sem fonte única; **VR infla líquido**; **close_payroll quebrado** (status 'Ativo' → 0 funcionários, não persiste, evento com total 0); **integração admissão→GED quebrada** (payload `name` vs `nome`, `cliente_id` nunca setado → kit nunca criado); **férias do Sólides viram falta na folha**; conciliação e ajuste são stubs; 13 funcionários sem salário; IRRF zerado em 100% dos dados.

O contracheque (leitura) está perto de produção (~75%), mas o **motor de cálculo de folha, rescisão e a integração GED não estão production-ready** e contêm erros que produzem valores legalmente incorretos. Média ponderada → **42%**.

**Prioridades P0**: (1) unificar e corrigir INSS 2026 no clt_calculator; (2) corrigir VR no líquido; (3) corrigir filtro `'ativo'` + persistência em close_payroll; (4) corrigir payload admissão→gedeon (`nome`/`cliente_id`); (5) parar de gravar férias como `falta`.

Arquivos-chave:
- `/opt/conecta-pro/backend/modules/people_management/folha/services/calculo_service.py`
- `/opt/conecta-pro/backend/modules/people_management/common/utils/clt_calculator.py`
- `/opt/conecta-pro/backend/modules/people_management/hr/services/payroll_service.py`
- `/opt/conecta-pro/backend/modules/people_management/hr/services/termination_service.py`
- `/opt/conecta-pro/backend/modules/people_management/hr/services/vacation_service.py`
- `/opt/conecta-pro/backend/modules/people_management/hr/services/admission_service.py`
- `/opt/conecta-pro/backend/modules/people_management/hr/publishers.py`
- `/opt/conecta-pro/backend/modules/gedeon/gedeon.py`
- `/opt/conecta-pro/backend/modules/people_management/cct/services/cct_service.py`
- `/opt/conecta-pro/backend/modules/people_management/folha/controllers/folha_controller.py`

---

### ?

Final critical confirmation: `gp_monthly_closings.employee_id` is **integer**, but the controller `POST /fechamento` takes `employee_id: int` and `fechar_mes` queries `gp_clock_punches` (uuid column) with that int — so the count returns 0 and it inserts an empty closing with a fabricated employee_id that won't match anything. The whole closing flow is type-broken between int and uuid.

I now have everything needed. Here is the comprehensive audit report.

---

# AUDITORIA PROFUNDA — Módulo Ponto Eletrônico (Conecta PRO)
**Data:** 2026-06-30 · **Escopo:** READ-ONLY · **Veredito:** 32/100 — registra batidas e exibe dashboards, mas o núcleo de cálculo (horas/extras/noturno/banco) é fictício, há corrupção de timezone na fonte de dados, e a integração ponto→folha **não existe**.

---

## 1) INVENTÁRIO — A LÓGICA REAL

Existem **DUAS implementações paralelas e divergentes** do ponto, com cálculos diferentes, expostas em prefixos diferentes e consumidas por telas diferentes:

### A. `ponto/` (PunchService + dashboard_service) — prefixo `/api/v1/people-management/ponto`
- **`punch_service.py` (691 linhas)** — escrita real via ORM `ClockPunchModel`.
  - `registrar_batida` (l.54): gera UUID, valida geofence Haversine (l.28-45) com raio 200m, resolve posto por `posto_id`→`allocations`→`geofence_zones`, persiste, faz push best-effort ao Sólides. Sólido.
  - `get_espelho_mensal` (l.194-279): agrupa batidas por dia, classifica `entrada/retorno`→entradas e `saida`→saídas, monta até 2 pares (manhã/tarde) e soma minutos. **Não conhece jornada, intervalo legal, noturno nem extras** — só soma os pares brutos. Quando não há tipagem, intercala par/ímpar (l.241-243) — frágil.
  - `fechar_mes` (l.380-440): **TOTAIS FICTÍCIOS** — `total_horas_trabalhadas = dias_trabalhados * 8.0`; `extras_50 = extras_100 = noturnas = faltas = atrasos = 0` hardcoded (l.418-424). `dias_trabalhados = total_batidas // 4` (l.412), premissa de 4 batidas/dia que **não bate** com os dados reais (a maioria tem 1–2 batidas/dia).
- **`dashboard_service.py` (835 linhas)** — leitura sync raw-SQL.
  - `get_dashboard` (l.36): presença/ausência/escala reais; `banco_horas` hardcoded `0.0` (l.115).
  - `get_inconsistencias` (l.121): 4 regras CCT em SQL (sem escala, ponto em aberto, jornada >12h, intrajornada <60min). As regras **rodam**, mas geram falsos positivos massivos (ver §5).
  - `get_banco_horas` (l.255): saldo = soma de `(saída-entrada)-12h` do mês; débitos sempre `0.0`; não há tabela de banco de horas — é calculado on-the-fly e descartado.
  - `registrar_ajuste` (l.760): **BUG GRAVE** — `emp_int = abs(hash(uuid)) % 2147483647` (l.768) insere int na coluna `employee_id` que é **uuid** → INSERT falha (0 registros `ajuste_dp` no banco confirmam que nunca funcionou).
  - `sync_solides_ponto` (l.378): importa ausências/ocorrências do Tangerino para `gp_justifications`; mas os endpoints `/absence/find-all` e `/occurrence/find-all` retornam 404 no plano atual (l.348-356) → 0 justificativas no banco.
  - `sync_escalas_from_solides` (l.663): popula `employees.escala_padrao`. **Funciona** (53 ativos, só 1 sem escala).
  - Constantes CCT `HORA_NOTURNA_MINUTOS=52.5`, `ADICIONAL_NOTURNO_PCT`, `HORA_EXTRA_50/100_PCT` (l.27-33) **definidas e nunca usadas** — decoração.

### B. `hr/services/time_record_service.py` (914 linhas) — prefixo `/api/v1/people-management/hr/time-records`
- Implementação **independente** (raw-SQL async) usada pela tela **DP**. `clock_in`/`clock_out`/`create_manual`/`get_summary`/`get_daily`/`_pair_punches`.
- `_pair_punches` (l.744): emparelha entrada/almoço/saída por dia, calcula total e overtime = `max(0, total-480min)` — regime **8h CLT fixo**, ignorando 12x36 (que predomina: 35 de 53). Errado para a empresa.
- `clock_out` (l.299) insere `saida` mas **não vincula** à entrada original a não ser pelo timestamp; em `_pair_punches` `saida` sempre sobrescreve `clock_out` (l.802, sem `is None`) → com 2 saídas/dia pega a última, ignora a primeira.
- `_calc_minutes_between` (l.37) tem cap de 16h→12h (l.52-54): qualquer turno >16h é silenciosamente truncado para 12h — esconde erros e mascara turnos noturnos cruzando meia-noite.

**Conclusão de inventário:** dois motores de cálculo divergentes (8h CLT vs pares brutos), nenhum implementa noturno/extras/banco corretamente, e o fechamento mensal grava números inventados.

---

## 2) FRONTEND

- **`dp/ponto/page.tsx` (547 linhas)** — WIRED, mas aponta para `/hr/time-records/*` (motor B). Faz `clock-in`/`clock-out`/`daily`/list. UX completa (busca, paginação, modais).
- **`gestao-pessoas/ponto/page.tsx`** — WIRED ao motor A (`/people-management/ponto/dashboard` via react-query). Hub com 6 sub-telas: batida, espelho, justificativas, atrasos, banco-horas, fechamento.
- **`portal/ponto/page.tsx`** — portal do colaborador (`/batida/me`).
- **`components/ponto/FacialCapture.tsx`** — captura facial (o backend persiste `facial_match/confidence` mas **nunca valida** — sempre aceita).
- **Problema de UX/arquitetura:** duas telas (DP e Gestão de Pessoas) mostram o **mesmo ponto com números diferentes** porque batem em motores diferentes. Banco de horas e extras aparecem zerados/fixos para o usuário final.

---

## 3) BANCO — QUALIDADE DO DADO

| Tabela | Linhas | Observação |
|---|---|---|
| `gp_clock_punches` | **4158** | `employee_id` **uuid**; 55 funcionários distintos (todos casam com `employees`, 0 órfãos) |
| `gp_monthly_closings` | **0** | `employee_id` **integer** — incompatível com uuid das batidas; nunca usado |
| `gp_justifications` | **0** | tem colunas `source/source_id`; vazia (endpoints Tangerino 404) |
| `solides_employees` | 44 | 44/44 com `solides_id` (mapeamento OK) |
| `solides_sync_log` | 4586 | última `completed` 2026-06-30 20:41 (sync ativo) |

**Distribuição de batidas:** `entrada` 2113 · `saida` 2044 · `saida_almoco` **1** · `retorno_almoco` **0**. Por device: `tangerino` 2328, `web` 1828, `manual` 2.
**Por dia:** 745 dias com 1 batida, 382 com 2, 200 com 3 (ímpar→inconsistência), 501 com 4, 1 com 10.
**Período:** 2026-03-01 a 2026-06-30.

**Achado de qualidade nº1 — almoço perdido:** virtualmente **não existem** batidas de almoço. A fonte (Tangerino `payssego/punches`) só entrega `startDateTimestamp`/`endDateTimestamp` por registro → o sync mapeia apenas `entrada`/`saida`. Toda a lógica de intrajornada (intervalo legal) é cega.

**Achado de qualidade nº2 — TIMEZONE CORROMPIDO (raiz):** o container roda **UTC** (`TZ` vazio). Em `tasks.py:921` `punch_dt = datetime.fromtimestamp(ts/1000)` gera timestamp **UTC-naive**, gravado direto. Mas `dashboard_service` lê "hoje" em `America/Manaus` (UTC-4). **Todos os horários ficam +4h.** Evidência: pico de `entrada` às 16h e 11h (real Manaus = 12h e 7h — turno diurno 12x36 começa 7h), `saida` às 15h/20h. Isso joga turnos para a faixa noturna errada e cruza meia-noite indevidamente, corrompendo presença, noturno e extras de toda a base.

---

## 4) ⚠️ INTEGRAÇÃO (seção destacada) — ARESTAS QUEBRADAS

### 4.1 DOIS event buses incompatíveis (aresta quebrada nº1)
- `ponto/publishers.py` publica em **`infrastructure.event_bus`** (`ConectaEvent`): `PONTO_BATIDA_REGISTRADA`, `PONTO_ESPELHO_FECHADO`, `PONTO_FALTA_CONFIRMADA`.
- Os **agents** (`ponto_agent`, `dp_agent`, `ops_agent`) usam **`people_management/core/events/event_bus`** (`GPEventBus`, evento `gp.ponto.falta`). Nomes e classes **diferentes**.

**Eventos que o módulo PUBLICA → consumidores reais:**
| Evento (infra bus) | Publicado quando | Consumidor | Estado |
|---|---|---|---|
| `ponto.batida.registrada` | `POST /batida` (controller l.54, fire-and-forget `asyncio.create_task`) | **NINGUÉM** | órfão |
| `ponto.espelho.fechado` | `POST /fechamento` (l.283) | `gedeon._on_espelho_fechado` (gedeon.py:83) | ✅ ligado |
| `ponto.falta.confirmada` | revisar justificativa de falta aprovada (l.248) | `gedeon._on_falta_confirmada` (gedeon.py:84) | ✅ ligado, mas **nunca dispara** (0 justificativas no banco) |

**Eventos que o módulo CONSOME:** o módulo `ponto/` **não tem `handlers.py`** — não consome nada. O `dp_agent._on_ponto_falta` (dp_agent.py:377) e `_on_ponto_mes_fechado` ouvem `GPEventTypes.PONTO_FALTA`/`PONTO_MES_FECHADO` no **GPEventBus**, publicados só por `ponto_agent.py:502` — e **`ponto_agent`/`dp_agent` não são instanciados em lugar nenhum** (grep não achou nenhuma instância nem registro no startup). Logo toda a cadeia DP-agent (falta→desconto em folha, mês fechado→gerar folha) está **morta**.

### 4.2 Ponto → Folha: integração INEXISTENTE (aresta quebrada nº2 — a mais grave)
- O módulo `folha/services/calculo_service.py` **não importa ponto, não lê `gp_clock_punches` nem `gp_monthly_closings`** (grep retornou vazio).
- A folha calcula horas noturnas como `dias_trab * 7` fixo (calculo_service.py:142) e intrajornada como valor fixo — **premissas, não dados reais de ponto**.
- Resultado: extras, faltas, atrasos e adicional noturno **apurados pelo ponto nunca chegam à folha**. O "ponto alimenta a folha" do requisito **não acontece**.

### 4.3 Ponto → Escala/Alocação (aresta quebrada nº3)
- Ponto **só lê** `employees.escala_padrao` e `allocations` (geofence). **Não escreve** em escala/scheduling. Não há fechamento de escala vs. realizado, nem geração de espelho por posto. A "escala" é um campo string em `employees`, não uma entidade com turnos.

### 4.4 Tabelas compartilhadas
- **Lê:** `employees` (status/escala/nome), `posts`+`geofence_zones`+`allocations` (geofence), `solides_employees`+`solides_sync_log` (sync).
- **Escreve:** `gp_clock_punches`, `gp_monthly_closings` (nunca), `gp_justifications` (nunca).
- **Imports cruzados:** `punch_service` → `modules.integrations.connectors.solides.connector.SolidesConnector` (push bidirecional, métodos existem: `push_punch_as_occurrence` l.671, `push_justification_as_absence` l.741, `update_absence_status` l.798). Quem depende de `ponto`: só `gedeon` (via infra bus).

---

## 5) BUGS CONCRETOS (file:line + fix)

1. **`dashboard_service.py:768` — int(hash) em coluna uuid.** `emp_int = abs(hash(...)) % 2147483647` → INSERT em `gp_clock_punches.employee_id` (uuid) falha sempre. **Fix:** `"eid": str(ajuste["employee_id"])` e `CAST(:eid AS uuid)`, removendo o hash.

2. **`tasks.py:921` — timestamp UTC-naive (corrupção sistêmica).** `datetime.fromtimestamp(ts/1000)` no container UTC grava +4h. **Fix:** `datetime.fromtimestamp(ts/1000, ZoneInfo("America/Manaus")).replace(tzinfo=None)` (ou padronizar tudo em UTC e converter só na exibição). Requer re-sync/migração dos 4158 registros existentes.

3. **`punch_service.py:412-424` — fechamento fictício.** `dias = batidas//4`, extras/noturno/faltas/atrasos = 0 fixos. **Fix:** apurar a partir das batidas emparelhadas com regra 12x36/44h, noturno 22h-05h c/ hora reduzida 52'30", extras conforme CCT.

4. **`dashboard_service.py:181-207` — `jornada_excedida` falso-positivo.** Faz `JOIN` entrada×saída na mesma data sem garantir adjacência: com múltiplas batidas/dia cross-pareia entrada da manhã com saída da tarde → 65 "violações" espúrias (ex.: 08:53→21:10 = 12.3h marcado como excesso, sendo turno normal + o +4h do TZ). **Fix:** parear por sequência temporal adjacente (LAG/window) e descontar intervalo.

5. **`time_record_service.py:802` — `saida` sobrescreve `clock_out` sem guarda.** Em dias com 2 saídas, perde a primeira. **Fix:** tratar pares ordenados (entrada→saída) em vez de slots fixos.

6. **`time_record_service.py:52-54` — cap silencioso 16h→12h** mascara turnos cruzando meia-noite. **Fix:** detectar pernoite por punch_type/sequência, não por heurística de magnitude.

7. **`punch_service.py:380` vs `gp_monthly_closings.employee_id` integer** — `fechar_mes(employee_id:int)` consulta `gp_clock_punches` (uuid) com int → `total_batidas=0` sempre; e o controller `POST /fechamento` (l.273) tipa `employee_id:int`. **Fix:** uniformizar para uuid (alterar coluna + assinatura).

8. **`punch_controller.py:54-63` — evento `batida.registrada` órfão e fire-and-forget** em `asyncio.create_task` sem await pode ser descartado se a request terminar antes. Sem consumidor, é só ruído/risco.

9. **Facial sempre aceito** — `registrar_batida` persiste `facial.match` vindo do cliente sem validação server-side; controle de fraude inexistente.

---

## 6) GAPS DE PRODUÇÃO (o quê / por quê / como)

1. **Motor de cálculo CLT/CCT real** — *Por quê:* extras, adicional noturno (52'30"/hora, 20%), DSR, intrajornada, banco de horas 6 meses, regimes 12x36/44h são a razão de ser do módulo e hoje são 0/fixos. *Como:* um único `calculation_service` parametrizado por regime, alimentado pelas batidas emparelhadas, consumido por espelho+fechamento+folha.
2. **Unificar os dois motores (A `ponto/` e B `hr/time-records`)** — *Por quê:* divergência produz números contraditórios nas telas. *Como:* eleger um, redirecionar o outro como fachada.
3. **Corrigir TZ na origem + remediar histórico** — *Por quê:* base inteira +4h invalida presença/noturno. *Como:* gravar timezone-aware, migration de correção dos 4158 punches.
4. **Captura de almoço (intrajornada)** — *Por quê:* CCT exige intervalo; hoje invisível. *Como:* usar endpoint de batidas detalhadas do Tangerino (não o resumo `payssego/punches`) ou AFD.
5. **Integração ponto→folha** — *Por quê:* requisito central ausente. *Como:* `calculo_service` lê `gp_monthly_closings` fechado em vez de premissas fixas.
6. **AFD / Portaria 671 (REP-P)** — *Por quê:* exigência legal para registro eletrônico; inexistente. *Como:* gerar AFD assinado, NSR sequencial, hash.
7. **Reativar a malha de agents** (`ponto_agent`/`dp_agent`) ou remover — hoje código morto que sugere automação que não roda.
8. **Banco de horas persistido** — hoje calculado e descartado; sem ledger de crédito/débito/compensação/vencimento.
9. **Anti-fraude facial server-side.**

---

## 7) NOTA DE PRONTIDÃO: **32/100**

**Justificativa:**
- **+** Captura de batida real, geofence Haversine funcional, sync Tangerino ativo (4158 batidas, hourly via Celery), dashboard/inconsistências com dados reais, push bidirecional Sólides implementado, escalas sincronizadas (52/53), frontend amplo e wired, TZ-Manaus tratado na *leitura* do dashboard.
- **–** Os dois itens que justificam um módulo de ponto — **cálculo correto de horas/extras/noturno/banco** e **alimentar a folha** — estão **ausentes ou fictícios**. A base está **+4h corrompida** na origem. Fechamento mensal grava números inventados (0 closings reais). Há **dois motores divergentes**. `registrar_ajuste` está quebrado (uuid vs int) e nunca funcionou. Almoço/intrajornada invisíveis. Sem AFD/671. A malha de agents DP está morta. Justificativas: 0.

**Veredito:** serve como **coletor/visualizador** de batidas, **não** como sistema de apuração de jornada para fins trabalhistas ou de folha. Não está pronto para produção nesse papel. As correções de maior alavancagem, em ordem: (1) TZ na origem + migration, (2) motor único de cálculo 12x36/44h+noturno, (3) integração ponto→folha, (4) fix `registrar_ajuste`/`fechar_mes` uuid, (5) captura de almoço.

---

### ?

`get_db` **auto-commits on success** — so the flush-only POSTs DO persist (the explicit commits in afastamento/cipa are redundant but harmless). That downgrades the "missing commit" from data-loss to a minor inconsistency. Good — I won't overstate it.

I now have all evidence needed. Here is the complete audit.

---

# AUDITORIA PROFUNDA — Módulo Saúde Ocupacional / SST (Conecta PRO)

**Data:** 2026-06-30 · **Modo:** read-only · **Veredito de prontidão: 38/100**

O módulo "funciona" na superfície (endpoints retornam 200 com números plausíveis), mas tem **split-brain estrutural em 3 camadas** (banco, backend, frontend), **cálculo NR-1 silenciosamente quebrado**, **integração com folha/eSocial inexistente** e **2.833 linhas de lixo idêntico** na CIPA. Não está pronto para produção como sistema de conformidade legal (SST é área de fiscalização/multas).

---

## 1) INVENTÁRIO — Lógica real

Existem **DOIS módulos concorrentes** cobrindo o mesmo domínio:

### A) `modules/people_management/sst/` — o que está EM USO real
Montado em `/api/v1/people-management/sst/*` (prefixo `/sst` aninhado sob `/people-management` — `__init__.py:83-85`). **Esta é a fonte de verdade operacional**: lê/escreve as tabelas `gp_*` e `sst_*` que de fato têm dados.

- **`sst_service.py` (564 linhas)** — wiring real ao banco. Lógica notável:
  - `registrar_afastamento` (l.98): aplica regras CCT 2026 — estabilidade 12 meses se `tipo ∈ {acidente_trabalho, acidente_trajeto}` OU CID com prefixo W/V/X/Y (`_deve_gerar_estabilidade`, l.558); ajuda-medicamento R$300/mês se atestado e tipo doença/acidente (l.116).
  - **BUG de cálculo de estabilidade (l.112-113):** `estab_ate = data_fim + 12*30 dias`. Usa `data_fim_prevista` (não a data real de retorno) e aproxima "12 meses" como `360 dias` — subestima a estabilidade em ~5 dias e parte de uma data estimada. A CCT/lei conta estabilidade **a partir da alta/retorno**, não do fim previsto. Em `registrar_retorno` (l.160) recalcula com `data_retorno + 360 dias` — melhor, mas ainda 360≠365 e mistura com o cálculo errado na criação.
  - `_calcular_indice_nr1` (l.488): índice ponderado (afastamento 30% + grau-de-risco-por-cargo 30% + medidas 20% + PCMSO 20%). **Quebrado — ver §5.**
  - `verificar_vencimentos_aso` / `_get_pcmso_stats` / `_get_risk_stats`: SQL cru sobre `gp_asos` e `gp_risks`, todos envoltos em `try/except` que engole erro e retorna vazio (mascara falhas silenciosamente).
- **`sst_controller.py` (767 linhas, 24 endpoints):** dashboard, afastamentos CRUD, NR-1, PCMSO/PPRA status, ASO CRUD, CAT, EPI, riscos, estabilidade, ajuda-medicamento, CIPA, **LTCAT e PPP**.
  - `ltcat/status` (l.661) e `ppp/{employee_id}` (l.689): **100% hardcoded** — `responsavel_tecnico: "A definir"`, `fatores_risco` é array literal fixo (Ruído/Calor/Jornada/Agressão), CNAE "8011-1/01" no LTCAT mas "8011-1/01" idem PPP enquanto a memória diz CNAE real 8111-7/00. PPP só puxa nome/CPF/ASOs reais; o resto é texto-modelo. Não gera XML S-2240.
- **Models:** `Afastamento`→`sst_afastamentos`; `ASOModel`→`gp_asos`; `CATModel`→`gp_cats`; `EPIDeliveryModel`→`gp_epi_deliveries`; `RiskModel`→`gp_risks`; `CIPAMembro`/`CIPAReuniao`→`sst_cipa_*`.
- **`tasks/afastamento_tasks.py`:** Celery beat — encerra afastamentos vencidos e alerta INSS >15 dias. Usa coluna `encaminhado_inss` (existe no banco; OK). O alerta INSS só faz `logger.warning` — **não publica evento, não cria pendência, não notifica DP**.

### B) `modules/health_occupational/` — arquitetura "bonita", dados fantasma
Montado em `/api/v1/health-occupational/*` (40+ endpoints PCMSO/PPRA/EPI com repos/services/schemas bem estruturados — 8.305 linhas). **Escreve em tabelas `health_*` paralelas que estão quase vazias** (ver §3). É a camada que o frontend usa para os cards de "estatísticas" do dashboard, mas ela não enxerga os dados reais que vivem em `gp_*`.

**Conclusão de inventário:** o `health_occupational` é o "split-brain vazio" e o `people_management/sst` é o "real" — confirmado. Mas ambos estão montados e ativos simultaneamente, e o frontend consome os dois.

---

## 2) FRONTEND

- **Split-brain de páginas:** existem DOIS árvores — `app/modulos/saude-ocupacional/*` e `app/modulos/gestao-pessoas/saude-ocupacional/*`. A primeira é só um `redirect()` (page.tsx 5 linhas) para a segunda (canônica).
- **Dashboard canônico (`gestao-pessoas/saude-ocupacional/page.tsx`, 186 linhas):** **mistura os dois backends na mesma tela** — `useSSTDashboard()` (→ `gp_*`) + `usePCMSOStatistics/useEPIStatistics/usePPRAStatistics()` (→ `health_*`). Resultado prático: o card "EPI" mostra `total_epis_ativos:5, entregas_ano:0` (de `health_epi_*`), enquanto as **220 entregas reais** em `gp_epi_deliveries` ficam invisíveis. PCMSO mostra `total_exames_ano:1` (de `health_medical_exams`=1) enquanto há **96 ASOs reais** em `gp_asos`. Números contraditórios na mesma página.
- **Subpáginas wired (via `sstService`→`people-management/sst`):** afastamentos, cat, estabilidade, riscos, epi, ajuda-medicamento, exames, alertas — apontam para o backend real (`/api/v1/people-management/sst`, base correta em `lib/services/sst.ts:189`). Estas exibem dados verdadeiros.
- **UX:** loading states presentes (`statsLoading`). O problema não é UX, é **coerência de dados** entre cards.

---

## 3) BANCO — qualidade do dado (medido ao vivo)

| Tabela | Linhas | Observação |
|---|---|---|
| `gp_asos` | 96 | 44 vencido / 52 realizado. **Fonte real** lida pelo SST. |
| `health_asos` | 96 | **DUPLICATA** — join por `aso_id` = 96/96 overlap. Mesmos UUIDs em dois schemas. |
| `health_medical_exams` | 1 | exame fantasma; `/pcmso/estatisticas` reporta "1 exame/ano". |
| `gp_epi_deliveries` | 220 | **Real** (SST). |
| `health_epi_deliveries` | 0 | vazio; `health_epi_catalog`=5 (só catálogo); `health_epi_inventory`=0. |
| `gp_risks` | 15 | **Real** (SST/PPRA). |
| `health_risk_mappings` | 3 / `health_occupational_risks` 0 / `health_control_measures` 0 | fantasma. |
| `gp_cats` | 2 | abertas. |
| `sst_afastamentos` | 6 | 3 ativos / 3 encerrados; 4 c/ ajuda-medicamento, **0 c/ estabilidade**. |
| `sst_cipa_membros` | 4 | OK. |
| **`sst_cipa_reunioes`** | **2.833** | **TODAS idênticas**: `data=2026-04-01, tipo=ordinaria, status=agendada`. 1 único `data_reuniao` distinto. Lixo de loop de inserção. |
| `gp_audit_logs` / `gp_justifications` / `gp_monthly_closings` | 0 | vazias. |

**`employees`: 71 total, 53 ativos.** Cargos reais (UPPERCASE c/ acento): `AGENTE DE PORTARIA` 34, `AGENTE DE SERVIÇOS GERAIS` 14, `ARTÍFICE` 2, `LÍDER DE PORTARIA` 2, `JARDINEIRO` 1.

---

## 4) ★ INTEGRAÇÃO (seção crítica) ★

### 4.1 Dois barramentos que não se falam
Existem **dois sistemas de eventos independentes**:
- `infrastructure/event_bus` (`ConectaEventBus`, classe `EventTypes` com `SAUDE_*`, `DP_*`, `OPS_CAT_REGISTRADA`).
- `infrastructure/message_bus` (`EventType` / `subscribe_to_event` / `subscribe_to_pattern`).

`health_occupational/integrations/hr_events.py` **subscreve no `message_bus`** (`FUNCIONARIO_ADMITIDO/DEMITIDO/MUDANCA_FUNCAO`) para auto-agendar exames. Já os publishers de SST/saúde usam o **`event_bus`**. **Arestas que dependem de cruzar os dois barramentos quebram.**

### 4.2 Eventos que o módulo PUBLICA → consumidores
- `sst/publishers.py` define `publish_aso_emitido`, `publish_atestado_registrado`, `publish_afastamento_iniciado` — **mas NINGUÉM os chama**. `grep` por chamadas: zero fora do próprio arquivo. **`sst/publishers.py` é 100% código morto.** O `sst_controller` cria afastamento/CAT/ASO/EPI **sem publicar nenhum evento**.
- `health_occupational/publishers.py`: `publish_aso_emitido` é chamado **apenas** por `pcmso_controller.py:342` (o módulo fantasma) via `asyncio.create_task` (fire-and-forget, sem await/retry — perde evento se a task falhar ou o request encerrar).
- **Único consumidor real de eventos de saúde: GEDEON** (`modules/gedeon/gedeon.py`) subscreve `DP_ATESTADO_REGISTRADO`, `OPS_CAT_REGISTRADA`, `SAUDE_ASO_EMITIDO`, `SAUDE_EPI_ENTREGUE` para montar kits documentais. Como o SST real nunca publica, **GEDEON nunca recebe ASO/CAT/atestado vindos do fluxo operacional** — só recebe o que o módulo fantasma `pcmso_controller` emite (que tem 1 exame).

### 4.3 Eventos que o módulo CONSOME ← origem
- `health_occupational` consome `FUNCIONARIO_ADMITIDO/DEMITIDO/MUDANCA_FUNCAO` (message_bus) → `_schedule_exam_sync` agenda exame em `health_*`. Mas como esses exames vão para `health_medical_exams` (fantasma) e o operacional lê `gp_asos`, **o exame auto-agendado não aparece no dashboard real**.
- `people_management/sst` **não consome nenhum evento** — sem `handlers.py`.

### 4.4 Tabelas compartilhadas
- **`sst_afastamentos` é compartilhada entre DP e SST.** `hr/controllers/leave_controller.py` (tela `dp/licencas`) faz `INSERT INTO sst_afastamentos` (l.99) e o SST lê dela. **PORÉM o INSERT do DP NÃO preenche os campos CCT** (`gera_estabilidade`, `ajuda_medicamento_ativa`, `ajuda_medicamento_valor`, `estabilidade_ate`) — l.97-113 só grava id/employee/tipo/datas/cid/motivo/status. **Afastamento criado pela tela DP perde toda a lógica CCT** (sem estabilidade, sem ajuda-medicamento). Só afastamentos criados via `POST /sst/afastamentos` recebem as regras. Dois caminhos de escrita divergentes na mesma tabela.
- `employees` (lida por count/cargo), `posts` (LTCAT count), `gp_asos`/`gp_risks`/`gp_cats`/`gp_epi_deliveries`.

### 4.5 Integração com FOLHA (a pergunta central): **INEXISTENTE**
- Nenhum módulo financeiro/folha (`financial`, `hr/folha`) lê `sst_afastamentos`, `ajuda_medicamento` ou `estabilidade`. `grep` por `afastamento|estabilidade|ajuda_medicamento` em `financial`/`hr` → só publishers/leave, nada na folha.
- **Afastamento NÃO vira evento na folha.** As regras CLT que dependem disso **não acontecem automaticamente**:
  - Primeiros 15 dias de doença pagos pela empresa vs. 16º+ pelo INSS (suspensão de salário).
  - Suspensão de salário durante afastamento INSS.
  - Lançamento da **ajuda-medicamento R$300** (4 colaboradores ativos hoje = R$1.200/mês) na folha — calculada no dashboard SST mas **nunca enviada à folha**.
  - Bloqueio de demissão durante **estabilidade** (12 meses pós-acidente) — não há trava no DP/folha.
- A task `verificar_inss_pendente` detecta >15 dias mas só faz `logger.warning` — não cria evento de transição empresa→INSS.

### 4.6 Integração com eSocial: **INEXISTENTE para SST**
- `hr/services/esocial_service.py` só gera **S-2200 (admissão)** e **S-2299 (desligamento)**. Os eventos de SST — **S-2210 (CAT), S-2220 (monitoramento da saúde/ASO), S-2240 (condições ambientais/PPP)** — **não existem em lugar nenhum** (`grep S-2210/S-2220/S-2240` só acha em strings de texto/comentários e no PPP hardcoded). Abrir uma CAT no sistema **não gera o evento S-2210 obrigatório** (prazo legal: 1 dia útil). O PPP cita "esocial_evento: S-2240" mas é só rótulo num JSON estático.

### 4.7 CAT órfã
`POST /sst/cat` cria registro em `gp_cats` e **para por aí**: não cria afastamento, não publica `OPS_CAT_REGISTRADA`/`SAUDE_CAT_REGISTRADA`, não gera S-2210, não dispara estabilidade. O acidente fica registrado mas desconectado de toda a cadeia (folha, eSocial, GEDEON, estabilidade).

---

## 5) BUGS CONCRETOS (file:line + fix)

1. **NR-1 cálculo silenciosamente quebrado — `sst_service.py:33-38` + 181-183 + 502.**
   `GRAU_RISCO_CARGO` tem chaves Title-Case ASCII (`"Agente de Portaria"`, `"Artifice"`) mas o banco tem `"AGENTE DE PORTARIA"`, `"ARTÍFICE"` (UPPERCASE + acento). **Zero matches** → `GRAU_RISCO_CARGO.get(c, 1)` cai sempre no default 1. Efeito ao vivo: dashboard NR-1 retorna `colaboradores_risco_alto:3` (só os afastados) + `risco_baixo:53` (TODOS) = 56 > 53 total (double-count), e `fator_cargo` fica travado em 33,3% para qualquer composição de cargos. O "índice de risco dinâmico" não reage a cargo nenhum.
   *Fix:* normalizar chaves e comparação (`unicodedata`/`.upper()` em ambos os lados) e classificar excludentemente (afastado não deve somar em alto **e** baixo).

2. **Double-count no dashboard NR-1 — `sst_service.py:200-202.`** `colaboradores_risco_alto = alto + afastados` e `risco_baixo` conta todos os 53 (por causa do bug 1), somando >100% da força de trabalho. Classificar cada colaborador em exatamente um balde.

3. **CIPA: 2.833 reuniões idênticas — `sst_cipa_reunioes`.** `POST /sst/cipa/reunioes` (controller l.628) não tem idempotência; algum loop/seed/teste inseriu 2.833× a mesma reunião (2026-04-01). `GET /sst/cipa/reunioes` (l.604) faz `SELECT ... ORDER BY data_reuniao` **sem LIMIT** → retorna 2.833 linhas. *Fix:* dedup (`DELETE` mantendo 1), UNIQUE(`data_reuniao`,`tipo`) e paginação no GET.

4. **Afastamento via DP não aplica CCT — `leave_controller.py:97-113.`** INSERT em `sst_afastamentos` omite campos CCT. *Fix:* rotear o POST do DP para `SSTService.registrar_afastamento` (caminho único) em vez de SQL cru.

5. **Estabilidade calculada sobre data estimada e 360≠365 — `sst_service.py:112-113.`** Usa `data_fim_prevista` + `12*30`. *Fix:* basear em `data_retorno` real (já feito no retorno) e usar `relativedelta(months=12)` ou 365 dias; não pré-calcular na criação a partir de estimativa.

6. **Split-brain de persistência ASO/EPI/risco.** `gp_asos`≡`health_asos` (96 UUIDs duplicados), `gp_epi_deliveries`(220) vs `health_epi_deliveries`(0), `gp_risks`(15) vs `health_risk_mappings`(3). Frontend mistura os dois. *Fix:* eleger `gp_*` como fonte única, reapontar os endpoints `health_occupational` para `gp_*` (ou desativar o módulo fantasma) e migrar/descartar `health_*`.

7. **`listar_sem_aso` — risco de tipo — `sst_service.py:310.`** `WHERE a.employee_id = e.id::text` compara `gp_asos.employee_id` (tipo **uuid**) com `e.id::text` (text). Ao vivo retornou `total:0` — ou o Postgres coage, ou a comparação uuid=text falha e o `try/except` (l.317) engole e devolve `[]`, escondendo que **todos os 53 podem estar sem ASO periódico**. *Fix:* `a.employee_id = e.id` (uuid=uuid) e remover o `::text`; não silenciar a exceção.

8. **`except` que mascara falhas** em todo o service/controller (`sst_service.py:298,317,381,393,410,441,467,482; controller 271,375,460,520`). Erros de schema/SQL viram "vazio" e o dashboard parece saudável. *Fix:* logar como error e propagar onde for crítico.

9. **`POST /sst/cat|aso|epi|risco` só fazem `flush()` sem `commit()`** (l.230,336,429,489). **Não é data-loss** porque `get_db` (`session.py:34`) faz `commit()` no teardown — mas é inconsistente com os outros endpoints e frágil se o padrão de sessão mudar. *Fix:* padronizar (ou todos commit explícito, ou nenhum).

10. **`publish_aso_emitido` fire-and-forget — `pcmso_controller.py:342` (`asyncio.create_task`)** sem await/retry → evento perdido silenciosamente em erro. *Fix:* await ou outbox.

---

## 6) GAPS DE PRODUÇÃO (o que falta · por quê · como)

| Gap | Por quê é crítico | Como |
|---|---|---|
| **eSocial S-2210/S-2220/S-2240** ausente | Obrigação legal; CAT sem S-2210 em 1 dia útil = infração | Implementar geradores XML análogos ao S-2200, ligados a CAT/ASO/PPP; submeter via gov_integrations |
| **Afastamento→folha** | Sem suspensão de salário/transição INSS/ajuda-medicamento na folha = erro de pagamento | Publicar `SAUDE_AFASTAMENTO_INICIADO` no caminho real e criar handler na folha (lançamento + corte 15º dia) |
| **Estabilidade→trava demissão** | Demitir estável pós-acidente = passivo trabalhista | Handler no DP/desligamento que bloqueia/avisa se `sst_afastamentos.estabilidade_ate >= hoje` |
| **Unificar split-brain (3 camadas)** | Números contraditórios; conformidade não confiável | Eleger `gp_*`+`sst_*` como fonte; reapontar ou aposentar `health_occupational`; unir os dois event buses |
| **SST publica eventos** | `sst/publishers.py` é código morto; GEDEON não recebe nada | Chamar publishers em `registrar_afastamento`/`abrir_cat`/`registrar_resultado_aso`/`registrar_entrega_epi` |
| **Limpar CIPA** | 2.833 lixos; relatório NR-5 inválido | Dedup + UNIQUE + paginação |
| **LTCAT/PPP reais** | Hardcoded; PPP é doc previdenciário com fé pública | Modelar laudo/RT por posto a partir de `gp_risks`; PPP gerado de dados reais + assinatura do RT |
| **Mapa de grau de risco** | NR-1 não funciona | Normalizar cargos; idealmente tabela `cargo→grau` no banco, não dict no código |
| **eventos INSS** | Task só loga | Transformar `verificar_inss_pendente` em pendência/notificação |

---

## 7) NOTA DE PRONTIDÃO: **38/100**

**Justificativa:**
- **+ (o que funciona):** endpoints respondem 200 com dados reais (afastamentos, ASOs, EPIs, CATs, riscos via `gp_*`/`sst_*`); regras CCT de estabilidade/ajuda-medicamento existem e são corretas em conceito; frontend wired às telas reais via `sstService`; Celery task encerra afastamentos vencidos; auth OK.
- **− (o que reprova para produção):**
  - **Split-brain em 3 camadas** (banco `gp_*`/`health_*`, backend dois módulos+dois event buses, frontend dois trees + dashboard misturando fontes) → números **contraditórios na mesma tela**.
  - **NR-1 silenciosamente quebrado** (mapa de cargos não casa; double-count >100%).
  - **Zero integração com folha** — afastamento/estabilidade/ajuda-medicamento não chegam ao pagamento; ajuda R$300 é calculada mas nunca lançada.
  - **eSocial SST inexistente** (S-2210/2220/2240) — descumprimento legal direto.
  - **CAT órfã** (sem S-2210, sem afastamento, sem estabilidade).
  - **Publishers do SST = código morto**; GEDEON não recebe os documentos do fluxo real.
  - **2.833 linhas de lixo** na CIPA.
  - LTCAT/PPP hardcoded (documentos de fé pública previdenciária).

SST é módulo de **conformidade legal e cálculo financeiro** (folha). Os fluxos que geram obrigação legal e impacto em pagamento (CAT→eSocial, afastamento→folha, estabilidade→trava demissão) **não estão conectados**. O módulo serve hoje como **cadastro/dashboard visual**, não como sistema de SST de produção. Nota 38 reflete uma fundação de dados real e telas funcionais, penalizada pesadamente pela ausência das integrações que são a razão de existir do módulo e por bugs de cálculo/duplicação que corrompem os indicadores apresentados.

**Arquivos-chave:**
- `/opt/conecta-pro/backend/modules/people_management/sst/services/sst_service.py` (bugs NR-1 l.33-38/181-202; estabilidade l.112-113; sem-aso l.310)
- `/opt/conecta-pro/backend/modules/people_management/sst/controllers/sst_controller.py` (LTCAT/PPP hardcoded l.661-768; CIPA sem paginação l.604-653; CAT órfã l.207-239)
- `/opt/conecta-pro/backend/modules/people_management/sst/publishers.py` (código morto)
- `/opt/conecta-pro/backend/modules/people_management/hr/controllers/leave_controller.py:97-113` (INSERT DP sem campos CCT)
- `/opt/conecta-pro/backend/modules/health_occupational/` (módulo fantasma, tabelas `health_*` quase vazias; `integrations/hr_events.py` no message_bus errado)
- `/opt/conecta-pro/backend/modules/people_management/hr/services/esocial_service.py` (só S-2200/S-2299)
- `/opt/conecta-pro/frontend/src/app/modulos/gestao-pessoas/saude-ocupacional/page.tsx` (dashboard mistura dois backends)

---

### ?

I now have a complete, deep picture. Let me compile the final audit report.

---

# AUDITORIA PROFUNDA — Módulo RH Estratégico (`human_resources`)

**Conecta PRO · people_management/human_resources · READ-ONLY · 2026-06-30**
Prefixo real montado: `/api/v1/people-management/human-resources` (NÃO `/human-resources` — toda doc/teste que usa o prefixo curto falha com 404).

---

## 1) INVENTÁRIO — Controllers / Services / Models (com a lógica real)

### 1.1 Treinamento (`training_*`) — **o submódulo mais sólido**
- **Model** (`models/training.py`, 440 linhas): `TrainingCourse` (catálogo, `validity_months`, `is_mandatory`, `required_for_workplace_types` JSON), `Training` (turma: `title`, `start/end_date`, `current_participants`, `max_participants`, FK `course_id`, `created_by_id`), `TrainingEnrollment` (UniqueConstraint `training_id+employee_id`), `TrainingCertificate` (`certificate_number` único, `expires_at`).
- **Service** (`training_service.py`, 469 linhas) — lógica real e correta na maior parte:
  - `complete_training` (l.185): seta status COMPLETED, faz dois `UPDATE` em lote — CONFIRMED→ATTENDED(+`attended_at`), ENROLLED→ABSENT. **Edge:** enrollment já em ATTENDED/CANCELLED é ignorado (ok). Não decrementa `current_participants` em cancelamento (ver bug §5).
  - `enroll_employee` (l.229): valida vagas (`has_available_slots`), `is_active`, duplicidade (notin CANCELLED), incrementa contador. **Race condition** (§5): checagem de vaga + incremento sem lock → overbooking sob concorrência.
  - `issue_certificate` (l.326): exige status ATTENDED; valida; calcula `expires_at = now + validity_months*30` (**bug de arredondamento**: 30 dias/mês — 12 meses = 360 dias, não 1 ano; §5); gera `CERT-YYYYMMDD-<hex8>`.
  - `check_mandatory_for_workplace` (l.398): cruza cursos obrigatórios × certificados válidos → `is_compliant`. **Bom**, é a única função de compliance NR real do submódulo.
- **Controller** (`training_controller.py`, 458 linhas, prefixo `/training`): CRUD completo + certificados + `mandatory-check/{employee_id}`. Testado live: `GET /training/courses` (9 cursos), `/training/` (5 turmas), `/training/certificates` (20 certs) → **200 com dados reais**.

### 1.2 Avaliação de Desempenho (`performance_*`)
- Service `create_review`/`list_reviews` com paginação; controller `/performance/reviews` → **200, 15 reviews reais**. Publica `RH_AVALIACAO_CRIADA/CONCLUIDA` (órfãos, §4).

### 1.3 Plano de Carreira (`career_*`)
- `create_plan` (l.42): impede 2º plano ACTIVE por funcionário; milestones em coluna JSON (`milestones`). Controller `/career/plans` → **200, 11 planos**. **Mas** `models/__init__` exporta `CareerLevel` e a tabela `career_levels` **NÃO EXISTE** no banco (§5) — qualquer query a esse model dá `UndefinedTable`.

### 1.4 Avaliação 360 (`evaluation_360_*`) — **bem desenhada, mas nunca rodou E2E**
- Service (331 linhas) com máquina de estado DRAFT→COLLECTING→CALCULATING→COMPLETED, pesos por tipo de avaliador (SELF/MANAGER/PEER/SUBORDINATE/CLIENT) normalizados sobre os tipos presentes, dimensão-ponderação (8 dimensões de vigilância), `generate_report` (pontos fortes/melhoria/comentários). Persistência real em `evaluation_360_cycles`/`_responses`.
- **DB:** 1 ciclo em `draft`, **0 respostas** → o caminho `calculate_final_score`/`generate_report` nunca executou com dados. `_weighted_score_for_response` (l.65) é função morta (duplicada inline no controller l.140).

### 1.5 Clima, Turnover, Onboarding — **re-exports quebrados + controllers SQL-raw paralelos**
- `services/climate_service.py`, `turnover_service.py`, `onboarding_service.py` são **re-exports** de `modules.retention.*`. **`turnover_service` aponta para `modules.retention.turnover.services.turnover_service` que NÃO EXISTE** (lá só há `risk_analyzer.py` e `turnover_predictor.py`) → `TurnoverService = None`. Idem `OnboardingChecklist` (model `rh_onboarding_checklist` ≠ caminho importado).
- Os **controllers reais** de clima/turnover/onboarding NÃO usam esses services: usam SQL cru (`text(...)`) direto na tabela `employees`/`climate_surveys`/`rh_onboarding_checklist`. Funcionam (200), mas duplicam lógica e ignoram a camada de service/IA.

### 1.6 Currículos (`resume_*`) — **parcial**
- `resume_parser_service.py` (320 linhas) + controller `/recruitment/resume` só expõe `POST /parse` e `/parse-text` (upload). **Não há GET/list/persistência** — é um parser stateless. Não há tela de listagem.

---

## 2) FRONTEND (telas wired / stub / vazio)

**Há DUAS árvores RH concorrentes** + clients gerados apontando para a API antiga `/retention/*` (drift):
- `/modulos/rh/*` (principal) e `/modulos/gestao-pessoas/rh/*` (duplicata: desempenho/clima/treinamentos).
- `src/api/generated/retention/*` — clients orval para `retention-turnover-prediction`, `retention-climate-survey`, `retention-onboarding-digital` (rotas que hoje vivem sob `/people-management/human-resources/*`).

| Tela | Linhas | Status |
|---|---|---|
| `turnover` | 246 | **WIRED** → `/people-management/human-resources/turnover/dashboard` + `/motivos` (este último sempre vazio, §3) |
| `clima` | 233 | WIRED, mas backend devolve indicadores `null` (fake) |
| `treinamentos` | 284 | WIRED (dados reais) |
| `avaliacoes` | 298 | WIRED |
| `carreira` | 181 | WIRED |
| `onboarding` | 229 | WIRED |
| `dashboard` | 252 | WIRED |
| `ia` | 156 | **Pseudo-wired**: só faz `fetch(endpoint?limit=1)` p/ checar se a rota responde — não consome scoring/predição real; mistura `/hr` e `/human-resources` |
| `candidatos` | 14 | **REDIRECT-stub** → `/modulos/recrutamento/candidatos` |

UX: a página `ia` é um “health-check de endpoints” disfarçado de IA — nenhuma das 3 IAs reais (`ai/*`) é chamada.

---

## 3) BANCO (tabelas, linhas, qualidade)

`employees`: **71 linhas** (53 `ativo`, 18 `inativo` — **minúsculo**). Tem AMBAS as colunas: `data_demissao` (6 preenchidas), `data_desligamento` (**0**), `motivo_desligamento` (**0**), `escala_padrao` (70), `salario_base` (58/71 → 13 NULL).

| Tabela | Linhas | Nota |
|---|---|---|
| training_courses / trainings / enrollments / certificates | 9 / 5 / 20 / 20 | Saudável. Certs expiram 2027-03 |
| performance_reviews | 15 | OK |
| career_plans | 11 | OK |
| **career_levels** | — | **TABELA NÃO EXISTE** (model exportado) |
| evaluation_360_cycles / _responses | 1 / **0** | 360 nunca coletou |
| climate_surveys | 3 | Existe, mas dashboard não lê score |
| rh_alertas_absenteismo | 3 | OK |
| **onboarding_checklists** | — | **NÃO EXISTE** (nome real: `rh_onboarding_checklist`) |
| candidates / job_positions | 10 / 10 | OK (recrutamento) |
| sst_afastamentos | 6 | Usado por `climate/absenteismo` |

**Qualidade do dado — divergência crítica de coluna:** o DP preenche `data_demissao`, mas as queries de motivo de turnover leem `data_desligamento`/`motivo_desligamento` (ambas 0) → relatório de motivos **sempre vazio**.

---

## 4) ⚠️ INTEGRAÇÃO (seção destacada)

### Arquitetura de eventos (2 barramentos coexistindo)
1. **`infrastructure.event_bus`** — Redis Streams real (`bus.py`). `publish()`=`xadd` no stream do prefixo; `start_consuming()` lê TODOS os streams e faz `_dispatch` para handlers in-process. **Ativado no startup** (`main_production.py:94-98`).
2. **`people_management.core.events` (GPEventBus)** + agents (`rh_agent.py` etc.) — barramento separado. **Os agents NUNCA são instanciados/registrados no startup** (só `gedeon.registrar_subscribers()` roda). Logo `gp.treinamento.*` não tem consumidor vivo.

### Eventos que o RH PUBLICA → quem consome
| Evento (publishers.py) | Quando | Consumidor |
|---|---|---|
| `rh.avaliacao_desempenho.criada` | POST /performance/reviews | **NINGUÉM** (verificado live: 2 eventos no stream `conecta:stream:rh`, dispatch→0 handlers) |
| `rh.avaliacao_desempenho.concluida` | concluir review | **NINGUÉM** |
| `rh.plano_carreira.criado` / `rh.milestone.concluido` | carreira | **NINGUÉM** |
| `rh.onboarding.item_concluido` | onboarding | **NINGUÉM** |
| `rh.avaliacao_360.criada` / `.iniciada` | 360 | **NINGUÉM** |
| `saude.treinamento.concluido` | POST /training/{id}/complete | **Gedeon** (`gedeon.py:80` → kit GED) — **mas payload vazio (§5)** |

**ARESTA QUEBRADA #1 (a mais grave da seção):** os 7 eventos `rh.*` são publicados no Redis e **dispatchados para ZERO handlers**. Nenhum módulo (DP, GED, SST, Portal) chama `event_bus.subscribe("rh.*"...)`. O RH “fala” no event-bus mas ninguém escuta.

### Eventos que o RH CONSOME ← origem
- **Nenhum.** O RH não registra subscribers no `infrastructure.event_bus`. O `RHAgent` (que *teria* `handled_events = [DP_*, TREINAMENTO_*]`) não é instanciado no boot → consumo zero.

### RH → SST (treinamento → SST) — **caminho existe, payload quebrado**
- `training_controller.py:370` chama `health_occupational.publishers.publish_treinamento_concluido(...)` lendo `getattr(training,"employee_id")`, `employee_name`, `workload`, `end_date` do objeto **`Training` (turma)**. O model `Training` **não tem** `employee_id`/`employee_name`/`workload` (treinamento é turma; quem tem funcionário é `TrainingEnrollment`). Resultado: `funcionario_id=""`, `funcionario_nome=""`, `carga_horaria=0` → SST/Gedeon recebem treinamento “fantasma”. (Confirmado: stream `saude` não tem nenhum `saude.treinamento.concluido`.)

### Tabelas compartilhadas
- **Lê:** `employees` (turnover/clima/onboarding/skills), `sst_afastamentos` (absenteísmo), `climate_surveys`, `rh_onboarding_checklist`, `candidates`/`job_positions`.
- **Escreve:** `training_*`, `performance_reviews`, `career_plans`, `evaluation_360_*`. Não escreve em tabelas de outros módulos.

### Imports cruzados
- RH → `modules.operacional.models.employee.Employee` (skills), `modules.people_management.hr.*` (orchestrator: PayrollService, VacationService, ComplianceSkill, AdmissionProcess), `modules.health_occupational.publishers`, `modules.retention.*` (re-exports, parcialmente quebrados).
- Quem depende do RH: `integration/skills/orchestrator_skill.py` (importa `EvaluatorSkill`); `agents/rh_agent.py` (re-declara skills próprias, **não** usa `human_resources/skills`). **Gedeon** depende indiretamente via `saude.treinamento.concluido`.

### IAs do FOCO (candidate_scoring / turnover_prediction / climate_analysis) — **CÓDIGO MORTO confirmado**
- `grep` global: as classes `CandidateScoringAI/TurnoverPredictionAI/ClimateAnalysisAI` têm **ZERO callers** fora de `ai/__init__.py`. São heurísticas multifatoriais bem escritas (pesos, alertas, ações, janela de saída), mas **nenhum endpoint/skill/agent as instancia**. A tela `ia` não as usa. Custo afundado.
- Os **skills** (`skills/*`) SÃO usados pelo `OrchestratorSkill` (só `EvaluatorSkill`) — os outros 4 (recruiter/trainer/predictor/onboarder) também são código vivo só via testes, sem endpoint dedicado.

---

## 5) BUGS CONCRETOS (file:line + fix)

1. **RH→SST payload vazio** — `training_controller.py:373-376`: lê `employee_id/employee_name/workload` do `Training` (turma), que não tem esses campos. **Fix:** o evento de treinamento concluído deve iterar os `TrainingEnrollment` ATTENDED da turma e publicar 1 evento por funcionário, com `funcionario_id=enrollment.employee_id`, `carga_horaria=course.duration_hours`.

2. **`trainer_skill.py:71`** — `TrainingCertificate.expires_at is not None` usa `is not` Python (avalia para `True` constante), não cláusula SQL → o filtro de expiração é **ignorado**, retorna todos os certs válidos. **Fix:** `TrainingCertificate.expires_at.isnot(None)`.

3. **Divergência de status nas skills** — `predictor_skill.py:25`, `recruiter_skill.py:25,47,55` filtram `Employee.status == "Ativo"`/`"Desligado"` (capitalizado), mas o banco usa **`ativo`/`inativo`** (minúsculo, sem “Desligado”). Resultado: turnover/headcount/workforce dos skills retornam **0**. **Fix:** `func.lower(Employee.status) == "ativo"` e usar `data_demissao`/`inativo` para desligados.

4. **Relatório de motivos de turnover sempre vazio** — `turnover_controller.py:92-93` filtra por `data_desligamento`/`motivo_desligamento` (0 linhas), enquanto o DP grava `data_demissao`. **Fix:** padronizar em `data_demissao` + um `motivo_*` único, ou backfill `data_desligamento ← data_demissao`.

5. **Fórmula de turnover infla a taxa** — `turnover_controller.py:50-51`: `(admitidos + desligados)/2 / média` mistura admissões na taxa de *turnover* (turnover é saída). Live deu 15,32% inflado por 13 admissões. **Fix:** `desligados / headcount_médio * 100`.

6. **Validade de certificado por “mês=30 dias”** — `training_service.py:354`: `validity_months*30` → 12 meses=360 dias (erra ~5 dias/ano, acumula). **Fix:** `dateutil.relativedelta(months=...)`.

7. **Race em `enroll_employee`** — `training_service.py:238-266`: checa vaga e incrementa `current_participants` sem lock → overbooking concorrente. **Fix:** `SELECT ... FOR UPDATE` na turma ou constraint/contagem atômica.

8. **`career_levels`/`onboarding_checklists` models órfãos** — `models/__init__.py:9,59` exportam `CareerLevel` e `OnboardingChecklist` cujas tabelas não existem (`career_levels` ausente; nome real `rh_onboarding_checklist`). Risco de `UndefinedTable`/`MapperError` se referenciados.

9. **`turnover_service` re-export quebrado** — `services/turnover_service.py:8` importa de caminho inexistente → `TurnoverService = None` silencioso.

10. **`asyncio.create_task(publish_...)` com sessão de request** — controllers (perf/career/onb/360) disparam publish fire-and-forget; o publish em si não toca a sessão (ok), mas a task pode logar/morrer fora do ciclo de request sem await — sem rollback/observabilidade. Aceitável, porém frágil.

---

## 6) GAPS DE PRODUÇÃO (o quê / por quê / como)

- **Coleta de clima inexistente** (POR QUÊ: `climate/dashboard` hard-coda `nps_colaborador=null`, `indice_satisfacao=null`; há 3 surveys mas nenhum endpoint de submissão de resposta nem agregação por dimensão). **COMO:** criar `climate_responses` + endpoint de resposta + plugar `ClimateAnalysisAI.analyze_survey_results` (que já existe, morto).
- **360 sem fluxo de coleta operacional** (0 respostas; falta convite/coleta por avaliador, e nenhum consumidor do resultado). **COMO:** seed E2E + UI de respostas; ligar `rh.avaliacao_360.*` a um handler real (ou remover publish).
- **IAs mortas** — 3 classes em `ai/*` + 5 skills sem endpoint. **COMO:** expor `POST /turnover/predict/{employee_id}` que monte o dict de fatores a partir de `employees`+ponto+folha+clima e chame `TurnoverPredictionAI`; idem scoring no recrutamento. Hoje a “IA” é fake na tela.
- **Eventos RH órfãos** — 7 eventos sem consumidor. **COMO:** ou registrar handlers reais (DP/GED/Portal/Notif) para `rh.*`, ou remover os publishers (evitar custo Redis + ruído).
- **Currículos sem persistência** — só parser. **COMO:** persistir candidato parseado em `candidates` + rota de listagem; integrar `CandidateScoringAI`.
- **Duplicação frontend** (`/rh` vs `/gestao-pessoas/rh`) e clients `retention/*` desatualizados → ChunkLoad/404 latente. **COMO:** consolidar uma árvore, regenerar orval para `/people-management/human-resources/*`.
- **Dados ínfimos** — 71 funcionários, 0 desligamentos com motivo; impossível validar turnover/360 em produção real.

---

## 7) NOTA DE PRONTIDÃO: **48/100**

**Justificativa:**
- **+** CRUD de Treinamento, Desempenho, Carreira e o service de 360 são código real, persistente e respondem 200 com dados (training/performance/career/360-list/onboarding/absenteísmo testados live).
- **−** **Integração é o ponto mais fraco:** os 7 eventos `rh.*` são publicados no Redis e dispatchados para **zero handlers** (verificado no stream); o único elo real RH→SST/Gedeon (`saude.treinamento.concluido`) envia **payload vazio** (`funcionario_id=""`) por ler campos inexistentes do model `Training`.
- **−** **3 IAs do foco são código morto** (zero callers) e a tela “IA” é um health-check disfarçado.
- **−** Bugs de cálculo/coluna concretos: taxa de turnover inflada, motivos sempre vazios (coluna divergente DP), status capitalizado nos skills (retorna 0), `is not None` em SQL, validade 30-dias, race de matrícula.
- **−** Clima é fachada (indicadores `null`, sem coleta); 360 nunca rodou E2E; `career_levels`/`onboarding_checklists` apontam para tabelas inexistentes; currículos sem persistência.

Os submódulos “de cadastro” (treinamento/desempenho/carreira) estão ~70% prontos; clima/turnover-analítico/360/IA/integração estão entre 20-40%. Média ponderada pela criticidade da integração (que é a tese do ERP “módulos se conversam”) → **48%**. Não está pronto para produção sem corrigir os bugs §5.1-§5.5 e decidir o destino dos eventos `rh.*` e das IAs mortas.

**Arquivos-chave:**
- `/opt/conecta-pro/backend/modules/people_management/human_resources/controllers/training_controller.py:370` (bug RH→SST)
- `/opt/conecta-pro/backend/modules/people_management/human_resources/skills/trainer_skill.py:71` (is-not-None SQL)
- `/opt/conecta-pro/backend/modules/people_management/human_resources/skills/predictor_skill.py:25` e `recruiter_skill.py:25,47` (status capitalizado)
- `/opt/conecta-pro/backend/modules/people_management/human_resources/controllers/turnover_controller.py:50,92` (fórmula + coluna divergente)
- `/opt/conecta-pro/backend/modules/people_management/human_resources/services/training_service.py:354,238` (validade 30d, race)
- `/opt/conecta-pro/backend/modules/people_management/human_resources/publishers.py` (7 eventos órfãos)
- `/opt/conecta-pro/backend/modules/people_management/human_resources/ai/*.py` (código morto)
- `/opt/conecta-pro/backend/infrastructure/event_bus/bus.py:331-340,440,467` (streams/dispatch)

---

### ?

All findings confirmed. One subscriber (`gedeon`) listens to `DP_FUNCIONARIO_ADMITIDO`, but health_occupational listens on a DIFFERENT bus (`message_bus`/`fase2.*`), so the admissional ASO scheduling never triggers from the DP admission path. I have everything I need for the exhaustive report.

---

# Auditoria Profunda — Módulo Recrutamento & Seleção (Conecta PRO)

**Status geral:** Funcional para CRUD básico de vagas/candidatos/candidaturas/entrevistas, mas **a IA de matching está quebrada em runtime** e **a ponte contratação→admissão→DP não existe na prática** (e o único caminho que tentaria fazê-la está com 3 bugs que o impedem de funcionar). Módulo marcado DEPRECATED porém é o código vivo (re-exportado por `pessoas` e `human_resources`).

---

## 1) Inventário (lógica real)

### Models (`modules/recruitment/models/`)
- **`application.py`** — Reescrito em 15/03 para "refletir o schema real". Status enum (`ApplicationStatus`) tem 14 valores (`inscrito`, `triagem`, `entrevista_rh`, `entrevista_tecnica`, `entrevista_gestor`, `teste`, `referencias`, `proposta`, `contratado`, etc.). Métodos de mutação (`hire()`, `advance_stage()`, `send_proposal()`, `reject()`) só mexem em colunas locais e gravam `step_history` (JSONB). `hire()` (linha 239-245) **apenas** seta `status=contratado` + `hired_at` — nenhum efeito colateral externo. `is_deleted` é hybrid_property mapeando `NOT is_active`. Colunas de score do design original (`test_score`, `reference_score`, `is_favorite`, `is_shortlisted`, `ranking_position`) **não existem no banco** → os métodos correspondentes no service são **no-ops silenciosos** (`toggle_favorite`, `toggle_shortlist`, `update_ranking`).
- **`candidate.py`** — name/email obrigatórios, `cpf` único, endereço, `salary_expectation`, `tags` (ARRAY), `ai_score`/`ai_analysis` (JSONB), status enum (`ativo`/`contratado`/`bloqueado`...). **Não tem FK para `employees`** — quando contratado, vínculo se perde. **Não tem** `years_experience`, `available_immediately`, `notice_period_days`, `available_for_relocation` (críticos abaixo).
- **`job_position.py`** — `required_skills`/`desired_skills` (ARRAY), `min_experience_years`, `education_level` (**String**, não enum), `work_model` (**String**, não enum), `salary_min/max`, `is_urgent`.

### Services
- **`application_service.py`** — Orquestra o pipeline. `create()` (48-101): valida duplicidade, vaga aberta, candidato não bloqueado; cria; incrementa contador; tenta calcular matching em `try/except (ValueError, KeyError, TypeError)` (**não captura `AttributeError`** — ver Bug 1). `hire()` (324-355): chama `repo.hire`, `candidate_repo.mark_as_hired`, `position_repo.fill_vacancy`, commit. **NÃO cria Employee, NÃO cria AdmissionProcess, NÃO publica evento, NÃO dispara onboarding.** Esta é a aresta quebrada central.
- **`recruitment_ai_service.py`** (788 linhas) — Matcher **heurístico/rule-based** (sem LLM), 6 dimensões ponderadas (skills 35%, experiência 25%, educação 15%, salário 10%, localização 10%, disponibilidade 5%). Skills via `SequenceMatcher` (fuzzy ≥0.8). `parse_resume()` extrai skills de uma lista **hardcoded de tecnologia** (python/react/docker/aws...) — **inútil para vigilância** (não procura curso de vigilante, CNV, reciclagem, antecedentes, CNH). Saída final escala 0-100.
- **`candidate_service.py`** — CRUD limpo; `create()` valida email+CPF únicos, **não chama IA** (logo, criação de candidato é segura).
- **`interview_service.py`** (605 linhas) — Rico: agendamento, confirmação dupla (candidato+entrevistador), `start/complete/cancel/reschedule/no_show`, detecção de conflito de horário (`_check_schedule_conflict`), `get_available_slots`, calendário mensal. `complete()` (246-289) calcula média de ratings e grava em `application.rating`. **Nenhuma transição de entrevista promove a candidatura nem inicia admissão.**

### Repositories
- `application_repository.py` — `hire()` (268) faz `application.hire()` + flush. `get_stats()` itera em memória (não agrega no SQL — N+1 potencial em escala). `advance_stage`/`reject` delegam aos métodos do model.
- `candidate_repository.py` — `mark_as_hired()` (300) seta `status=contratado`.
- `job_position_repository.py` — `fill_vacancy()` (214) decrementa vagas.

### Controllers — todos com `get_current_user` (autenticados). Endpoints `/hire`, `/advance`, `/reject`, `/proposal`, `/matching`, `/bulk-action`, `/stats`, CRUD completo de candidatos/vagas/entrevistas. Roteador montado em `api/v1/__init__.py:150` e `main_production.py:575` sob `/recruitment`, e re-exportado por `human_resources` sob `/human-resources/recruitment`.

---

## 2) Frontend

5 páginas em `src/app/modulos/recrutamento/` (2831 linhas), **todas wired à API real** (sem mock; usam `fetch` + `getAuthHeaders`):
- `page.tsx` (dashboard), `candidatos/`, `candidaturas/` (594 ln), `vagas/`, `entrevistas/` (732 ln).
- `candidaturas/page.tsx` chama `/advance`, `/reject`, `/proposal`, `/toggle-favorite`, `/stats`. **Não há botão/chamada de `/hire`** nem de admissão — o pipeline visual termina em "proposta", e mesmo o vocabulário de avanço (`statusOrder` linha 159: `inscrito→triagem→entrevista_rh→...→proposta`) **não inclui `contratado`**. O frontend usa o enum correto (`entrevista_rh`), mas o **seed do banco usa `nova`/`entrevista`** (incompatível) → ao avançar um registro real cujo status é `nova`, `statusOrder.indexOf('nova') === -1` e o "próximo" vira o índice 0 (`inscrito`), corrompendo o fluxo.
- UX: toggle-favorite/shortlist têm botões na UI mas o backend é no-op → **ação aparenta funcionar mas não persiste nada**.

---

## 3) Banco (qualidade do dado)

| Tabela | Linhas | Observações |
|---|---|---|
| job_positions | 10 | títulos reais ("Vigilante CIC-Test", VAG-2026-xxxx) |
| candidates | 10 | CPF preenchido, Manaus/AM — perfil seguro |
| applications | 8 | **status inválidos**: `triagem`(3), `entrevista`(3), `nova`(2) — não pertencem ao `ApplicationStatus` enum |
| interviews | 4 | |
| **admission_processes** | **0** | **Nunca foi usada — ponte recrutamento→DP jamais executou** |
| employees | 71 | Vieram do Tangerino/seed, **não do recrutamento** |

**Problemas de dado:**
- `ai_match_score` no banco está em escala **0-10** (8.50, 7.80, 9.00), mas o código gera **0-100** → `avg_score:7.8` no /stats está numa escala, recálculo geraria 0-100. Inconsistência herdada de seed manual.
- `step_order` = 1 em todos; `current_step` NULL em todos → histórico de pipeline nunca foi alimentado de verdade.
- 0 contratações reais → conversão real do funil = não testada em produção.

---

## 4) ⚠️ INTEGRAÇÃO (seção crítica — onde tudo quebra)

### Eventos que o módulo PUBLICA
**NENHUM.** O grep por `publish/event_bus/emit` em `modules/recruitment/` retorna **zero**. Não há `publishers.py`, não há handlers. O `hire()` não emite nada. Consequência: nenhum módulo downstream (DP, saúde ocupacional, operações, GED) é notificado de uma contratação.

### Eventos que o módulo CONSOME
**NENHUM.** Sem `handlers.py`, sem subscribe.

### A ponte pretendida (e por que está quebrada)
Existe a **intenção** de bridge em dois lugares, ambos não-funcionais:

1. **`people_management/integration/events.py::on_candidate_approved`** (linha 193-240) — deveria criar a admissão. Exposto via HTTP em `aggregator.py:181` → `POST /rh-to-dp/candidate-approved`. **3 bugs o impedem:**
   - **Assinatura incompatível**: chama `create_admission(candidate_id=..., job_position_id=..., expected_start_date=..., salary_proposed=..., workplace_id=...)` (kwargs), mas `AdmissionService.create_admission(self, data: dict, created_by_id=None)` espera um **dict posicional** → `TypeError: unexpected keyword argument 'candidate_id'`.
   - **Tipo de retorno**: lê `admission.get("id")` / `admission.get("checklist")`, mas `create_admission` retorna um **objeto ORM `AdmissionProcess`**, não dict → `AttributeError`.
   - **Não-transacional**: `create_admission` faz `flush` mas **nunca `commit`** (e o `on_candidate_approved` também não) → nada persiste mesmo se os bugs acima fossem corrigidos.

2. **Recrutamento → este endpoint**: **ninguém chama** `candidate_approved_to_dp`. Nenhum evento, nenhuma chamada interna do `hire()`. É um endpoint órfão que precisaria ser invocado manualmente via HTTP — e mesmo assim falharia pelos bugs acima. Daí **0 linhas em `admission_processes`**.

### Tabelas compartilhadas
- `admission_processes` tem `candidate_id` (FK lógica a recruitment) e `job_position_id` — **nunca populados** (0 linhas).
- `employees` (compartilhada com operacional/DP) — recrutamento **deveria** alimentá-la via `AdmissionService.complete_admission` (que cria `Employee` corretamente, linha 233-245, e publica `DP_FUNCIONARIO_ADMITIDO`), mas esse caminho **nunca é alcançado** a partir do recrutamento.

### Duplicação de event-bus (aresta quebrada extra, downstream do DP)
Mesmo quando a admissão é criada manualmente (controller DP), há fragmentação de barramentos:
- `admission_service.complete_admission` publica `DP_FUNCIONARIO_ADMITIDO` (`dp.funcionario.admitido`) no **`infrastructure.event_bus`** (in-process). Único consumidor: **`gedeon`** (`gedeon.py:55`).
- `health_occupational` (que agenda **ASO admissional** automaticamente) subscreve `EventType.FUNCIONARIO_ADMITIDO` e padrão `fase2.funcionario.*` no **OUTRO** barramento (`infrastructure.message_bus`). **Não escuta `dp.funcionario.admitido`** → o exame admissional **não é agendado** pela via DP. Dois barramentos paralelos sem ponte = evento publicado, consumidor relevante nunca recebe.
- `asyncio.create_task(event_bus.publish(...))` (admission_service:271) é **fire-and-forget**: exceções no publish são engolidas e a task pode ser GC'd antes de rodar.

### Imports cruzados
- Recrutamento é **autocontido** (só importa de si mesmo). Quem depende dele: `human_resources` e `pessoas` (re-export de routers), `human_resources/skills/recruiter_skill.py` (lê contagem de `hired`).
- `admission_service` importa `Employee` de `modules.operacional.models.employee` (acoplamento DP↔operacional OK).

---

## 5) Bugs concretos (file:line + fix)

1. **AI de matching crasha 100% em dados reais** — `recruitment_ai_service.py:242` `candidate.years_experience` (e `:405` `available_for_relocation`, `:416/423` `available_immediately`, `:431` `notice_period_days`). Esses atributos **não existem** no model/DB → `AttributeError`. Confirmado em runtime: `POST /recruitment/applications/{id}/matching` → **500** (traceback exato capturado). **Fix:** adicionar as colunas ao model/migration OU usar `getattr(candidate, 'years_experience', 0)`.
2. **`.value` em colunas String** — `recruitment_ai_service.py:289` `required_level.value`, `:315`, `:380` `position.work_model.value`. `education_level`/`work_model` são `String` no DB → `AttributeError`. **Fix:** tratar como string crua (`required_level` direto).
3. **`except` não captura o erro real** — `application_service.py:87` captura `(ValueError, KeyError, TypeError)` mas o crash do matching é `AttributeError` → na criação de candidatura via API com matching, propaga 500. **Fix:** incluir `AttributeError` ou (melhor) corrigir Bugs 1-2.
4. **`on_candidate_approved` kwargs vs dict** — `events.py:219-225` passa kwargs a `create_admission(data: dict, ...)`. **Fix:** `create_admission({"candidate_id":..., "job_position_id":..., ...}, created_by_id=...)`.
5. **`on_candidate_approved` lê dict de um ORM** — `events.py:229-230` `admission.get("id")`. **Fix:** `str(admission.id)` / `admission.checklist`.
6. **Nenhum commit no fluxo de admissão via integração** — `create_admission` só faz flush; `on_candidate_approved` não commita. **Fix:** `await db.commit()`.
7. **Enum vs seed divergente** — `applications.status` no DB = `nova`/`entrevista` (inexistentes no enum). Quebra `/stats` (classifica errado: `in_process` ignora `entrevista`/`nova`) e o `statusOrder` do frontend. **Fix:** migration de normalização (`nova→inscrito`, `entrevista→entrevista_rh`).
8. **Escala ai_match_score inconsistente** (0-10 no seed vs 0-100 no código).
9. **No-ops silenciosos** — `toggle_favorite/shortlist`, `update_ranking` retornam sucesso sem persistir (botões na UI enganam o usuário).

---

## 6) Gaps de produção

| Gap | Por quê | Como |
|---|---|---|
| **Contratação não vira admissão/employee** | `hire()` não tem efeito downstream; bridge órfã e bugada | No `ApplicationService.hire()`, após marcar contratado, chamar `AdmissionService.create_admission(dict, created_by)` passando `candidate_id`, `job_position_id`, `cpf`, `salary_proposed`; OU publicar evento `recrutamento.candidato.contratado` consumido pelo DP. Corrigir Bugs 4-6. |
| **Sem onboarding disparado** | Nenhum evento publicado | Após admissão concluída, `DP_FUNCIONARIO_ADMITIDO` já existe — unificar barramentos para que `health_occupational` (ASO admissional) e RH (onboarding) escutem o mesmo canal. |
| **IA inútil para vigilância** | parse/skills hardcoded em TI; matching crasha | Reescrever `parse_resume`/skills para domínio (curso vigilante, CNV/PF, reciclagem, antecedentes, CNH, idade). Corrigir atributos faltantes. |
| **Sem persistência de favorito/shortlist/ranking** | Colunas removidas do DB | Adicionar colunas via migration ou remover botões da UI. |
| **Dados de seed corrompidos** | Status inválidos, score em escala errada | Migration de saneamento. |
| **Módulo DEPRECATED mas vivo** | `__init__.py` emite DeprecationWarning (remoção alvo 2026-05-11, já vencida) | Decidir: promover oficialmente ou migrar para `pessoas`. |

---

## 7) Nota de prontidão: **38/100**

**Justificativa:**
- **CRUD + entrevistas (sólido, ~75%):** vagas, candidatos, candidaturas e o `interview_service` (agendamento, conflito, confirmação dupla, calendário) são bem implementados e wired ao frontend real. (+)
- **IA de matching (quebrada, ~15%):** crasha com 500 em qualquer dado real (3 `AttributeError` confirmados em runtime), heurística inadequada ao domínio de segurança. (−)
- **Integração contratação→DP (inexistente, ~5%):** o efeito mais importante de um módulo de R&S — transformar candidato em funcionário — **não acontece**. A ponte pretendida (`on_candidate_approved`) tem 3 bugs que a impedem, é órfã (ninguém chama), e a tabela `admission_processes` está vazia apesar de 71 employees. Zero eventos publicados/consumidos. Fragmentação de event-bus impede até o agendamento de ASO admissional. (−−)
- **Dados de seed inconsistentes** (status fora do enum, escala de score) corroem `/stats` e o pipeline do frontend.

Para produção real numa empresa de vigilância, o módulo serve hoje como cadastro/agenda de R&S, mas **não fecha o ciclo de pessoas** — exige correção dos Bugs 1-6 e implementação do gatilho `hire()→admissão` antes de ser confiável.

**Arquivos-chave:** `/opt/conecta-pro/backend/modules/recruitment/services/application_service.py` (hire sem efeito, 324-355), `/opt/conecta-pro/backend/modules/recruitment/services/recruitment_ai_service.py` (crashes 242/289/380), `/opt/conecta-pro/backend/modules/people_management/integration/events.py` (bridge bugada, 193-240), `/opt/conecta-pro/backend/modules/people_management/hr/services/admission_service.py` (create_admission/complete_admission corretos mas nunca chamados pelo recrutamento), `/opt/conecta-pro/backend/modules/people_management/integration/aggregator.py:181` (endpoint órfão).

---

### ?

I have everything needed. The `/calculate` endpoint works structurally (returns 200) but has nothing to aggregate (0 responses). Here is my complete deep audit.

---

# AUDITORIA PROFUNDA — Módulo Retenção & Clima (Conecta PRO)

## Resumo executivo
O módulo `modules/retention` (DEPRECATED, removal-target 2026-05-11 já vencido) contém **dois sistemas de "clima" que não se conversam** e **duplicam** a funcionalidade com o `human_resources`. A engenharia do retention é sofisticada (service de clima de 1.350 linhas, predictor de turnover heurístico de 769 linhas), mas está **morta na prática**: o frontend não aponta para ela, não há job que a alimente, e o caminho central de coleta de respostas está **100% quebrado por um bug de timezone**. O que de fato roda em produção são os controllers SQL-cru simples do `human_resources` (clima, absenteísmo, turnover), que funcionam mas são rasos. **Prontidão: 22%.**

---

## 1) Inventário (lógica real)

### 1a. retention/climate — o sistema "profundo" (DEAD em produção)
- **Controller** (`climate_controller.py`): 20 endpoints REST sob `/retention/climate/*`. CRUD de surveys, `/respond`, `/results/{posto,equipe,empresa}`, `/trends`, `/dashboard`, `/alerts`, `/calculate`, `/check-alerts`. `POST /respond` é o **único endpoint sem auth** (intencional, para coleta anônima de campo).
- **Service** (`climate_service.py:159-1349`): lógica real e bem pensada:
  - `_calcular_score_resposta` (l.275): escala **1-4** sem ponto neutro, normaliza `((valor-1)/3)*100` → 0/33.3/66.7/100. Agrupa por dimensão via `pergunta.dimensao`.
  - `_calcular_enps` (l.668): eNPS na escala 1-4 (4=promotor, 3=neutro, 1-2=detrator), `%promotores - %detratores`.
  - `calcular_scores_periodo` (l.427): job de agregação por posto/equipe/empresa; lê TODAS as respostas do período via um `type("Filters",...)()` dinâmico (hack feio mas funcional), agrupa em dicts e chama `_calcular_e_salvar_score`.
  - `_verificar_alertas` (l.764): 3 tipos — queda >20% (severidade graduada por -30/-40%), score <35 (crítica), dimensão <35 (alta). Idempotência via `check_existing_alert`.
  - Dashboard/tendências com `relativedelta` para 6 períodos.
- **Models** (`climate_models.py`): 4 tabelas — `climate_surveys`, `climate_responses` (anonimizada via `funcionario_hash` SHA-256), `climate_scores` (agregado), `climate_alerts`. Bem modeladas, com índices corretos, JSONB para perguntas/respostas/dimensões.
- **Repository**: CRUD async limpo, queries corretas, paginação OK.

### 1b. human_resources/climate — o sistema "raso" (LIVE em produção)
- **Controller** (`human_resources/controllers/climate_controller.py`, 154 linhas): 5 endpoints SQL-cru sob `/people-management/human-resources/climate/*`:
  - `/dashboard`: conta `employees` ativos + distribuição por escala. `pesquisas_realizadas: 0` hardcoded, `nps_colaborador: null`, status `aguardando_pesquisa`.
  - `/surveys`: lê `climate_surveys` direto por SQL (lê a MESMA tabela do retention).
  - `/alerts`: **stub puro** — `return {"items": [], "total": 0}` (l.99).
  - `/absenteismo/alertas` e `/absenteismo/dashboard`: leem `rh_alertas_absenteismo` e `sst_afastamentos` — **funcionais e com dados reais**.
- **`human_resources/services/climate_service.py`**: só re-exporta `ClimateService` do retention (l.8). Não usado pelo controller HR (que é SQL-cru).
- **`human_resources/ai/climate_analysis_ai.py`**: motor de recomendações por dimensão (`DIMENSION_ACTIONS`), porém **órfão** — não é importado por nenhum controller/endpoint (grep confirma só auto-referência).

### 1c. retention/turnover — predictor heurístico (DEAD)
- `turnover_predictor.py` (769 linhas): modelo heurístico v1.0 com 10 features ponderadas (faltas, atrasos, advertências, `score_clima_atual`, `tendencia_clima`, distância, HE, tempo de casa, dias sem aumento), normalização 0-1, penalização +20% por threshold violado, geração de alertas (NOVO_RISCO/AUMENTO/CRÍTICO/MUDANÇA_NÍVEL). Engenharia boa.
- **Controller** (`turnover_controller.py:289, 354`): alimenta o predictor com **dados HARDCODED de demonstração** ("Por enquanto, usar dados mockados"). Nunca lê `employees`/ponto/clima reais.

---

## 2) Frontend
- `frontend/src/app/modulos/rh/clima/page.tsx` (233 l.): wired, mas aponta para `/api/v1/people-management/human-resources` (l.8) → consome o controller **RASO** (dashboard/surveys/alerts). O `/alerts` que chama é o **stub vazio**. Não usa o sistema profundo do retention.
- `frontend/src/app/modulos/rh/turnover/page.tsx` (246 l.): aponta para `/people-management/human-resources/turnover/*` → consome o turnover SQL-cru **funcional** (não o predictor heurístico).
- `frontend/src/app/modulos/gestao-pessoas/rh/clima/page.tsx` (291 l.): **página duplicada** apontando para `/people-management/human-resources/climate`. Duas telas de clima coexistem.
- Não há nenhuma tela que consuma `/retention/climate/*` nem `/retention/turnover/*`. Não há tela de coleta de resposta (`/respond`) — a pesquisa de clima **não tem formulário para o vigilante responder**.

---

## 3) Banco (qualidade do dado)
| Tabela | Linhas | Observação |
|---|---|---|
| `climate_surveys` | **3** | Seed. `perguntas` com schema DRIFTADO (ver §5). Todas com `data_fim` vencida (max 2026-06-20 < hoje 2026-06-30) e `empresa_id=NULL`. |
| `climate_responses` | **0** | **Nenhuma resposta jamais coletada.** |
| `climate_scores` | **0** | Nunca agregado. |
| `climate_alerts` | **0** | Nunca gerado. |
| `turnover_predictions` / `turnover_risk_factors` / `turnover_alerts` | **NÃO EXISTEM** | Migração das tabelas de turnover nunca aplicada → `/retention/turnover/*` dá 500. |
| `operational_profiles` / `profile_questions` | **NÃO EXISTEM** | retention/profile sem tabelas. |
| `rh_alertas_absenteismo` | 3 | Real (sprint76), derivado de `sst_afastamentos`. |
| `sst_afastamentos` | 6 | Real. |
| `employees` | 71 (53 ativos) | Fonte real do clima/turnover RASO. |

---

## 4) INTEGRAÇÃO (seção crítica)

### Eventos PUBLICA → consumidores
- **NENHUM.** `grep` por `publish/emit/event_bus` em `modules/retention/` retorna zero. O módulo não publica nada no event-bus (`people_management/core/events/`). `event_types.py` e `handlers.py` não têm um único evento de clima/turnover/absenteísmo/eNPS.

### Eventos CONSOME ← origem
- **NENHUM.** Nenhum `handler` reage a admissão/desligamento/falta/afastamento para alimentar clima ou turnover. O predictor de turnover, que **deveria** consumir faltas (ponto), advertências (RH), score de clima (climate) e afastamentos (SST), é alimentado por mocks.

### Tabelas compartilhadas (lê/escreve)
- `climate_surveys`: **escrita** pelo retention; **lida** por SQL-cru pelo HR controller (acoplamento por tabela, não por service). Risco de drift de schema entre os dois.
- `employees`: lido (read-only) pelos controllers RASOS (HR climate dashboard + turnover dashboard).
- `rh_alertas_absenteismo` / `sst_afastamentos`: lidos pelo HR climate controller; populados por SST/migração — não pelo retention.

### Imports cruzados
- `human_resources/services/climate_service.py` → importa `ClimateService` de `retention.climate` (ponte que **ninguém usa**).
- `turnover_predictor` referencia conceitualmente `score_clima_atual`/`tendencia_clima` mas **sem nenhum import/query** ao climate_service — a ligação clima→turnover existe só no nome das features.
- `modules.pessoas` e `main_production.py` (l.586) re-exportam `climate_router`/`turnover_router`.

### ARESTAS QUEBRADAS (as conexões que falham)
1. **Clima → Turnover (esperado, inexistente):** o predictor lista `score_clima_atual` e `tendencia_clima` como features de peso 0.18+0.08 (26% do score!), mas **nunca lê** `climate_scores`. Alimentado por mock `3.5`/`0.1`. Além disso há **mismatch de escala**: clima persiste 0-100, predictor espera 1-5 (`score_clima_atual (1-5)`, normalização assume `>=4.0`).
2. **Frontend → backend (drift de rota):** as telas apontam para `/people-management/human-resources/*` (raso), deixando todo o `/retention/*` (profundo) sem consumidor. O esforço de engenharia do retention é invisível ao usuário.
3. **Coleta de resposta quebrada:** `POST /retention/climate/respond` → **500** (TZ, §5). Sem coleta, `climate_scores`/`climate_alerts`/eNPS/turnover nunca terão dado. É a aresta que invalida a cadeia inteira.
4. **Sem job de agregação:** nenhum Celery/beat chama `calcular_scores_periodo`/`verificar_quedas`. Mesmo com respostas, scores só sairiam por POST manual em `/calculate`.
5. **Absenteísmo isolado:** os alertas reais de absenteísmo (`rh_alertas_absenteismo`) vivem em `/climate/absenteismo/alertas`, mas o `/climate/alerts` que o frontend chama é **stub vazio** — o usuário vê "0 alertas" mesmo com 3 afastamentos críticos INSS_PENDENTE no banco.
6. **`api/v1/__init__.py` (fallback) tem double-prefix:** l.153 `include_router(climate_router, prefix="/retention/climate")` sobre um router que já tem `prefix="/retention/climate"` → geraria `/retention/climate/retention/climate/*`. Não afeta produção (main_production usa `prefix=""`, l.586), mas é uma bomba se alguém voltar ao fallback.

---

## 5) Bugs concretos (file:line + fix)

1. **[CRÍTICO] TZ — quebra TODA a coleta** `climate_models.py:189`
   `now = datetime.now()` (naive) comparado com `self.data_fim` (aware, vem do DB com `DateTime(timezone=True)`) → `TypeError: can't compare offset-naive and offset-aware`. Confirmado via traceback no `/respond`. **Fix:** `now = datetime.now(timezone.utc)`. O mesmo padrão naive contamina `repository.py:99` (`get_active`) e todas as ~20 ocorrências de `datetime.now()` em §inventário — padronizar para `datetime.now(timezone.utc)`.

2. **[CRÍTICO] Tabelas de turnover ausentes** — migração nunca aplicada. `/retention/turnover/dashboard` → 500 (`relation "turnover_predictions" does not exist`). **Fix:** criar/aplicar a migração Alembic das 3 tabelas (READ-ONLY: não fazer agora, mas é pré-requisito).

3. **[ALTO] Drift de schema seed↔código nas perguntas** — seed grava `{"id":1 (int),"tipo":"escala_1_5","categoria":"ambiente"}`; código exige `QuestionSchema{id:str(min1), tipo:"escala", dimensao:ClimateDimension}`. `GET /surveys/ativa` faz `QuestionSchema(**p)` (controller l.142) → 500 latente (hoje mascarado pelo 404 de data vencida). Escala `1_5` no seed vs `1-4` validada no `ResponseCreate` (`schemas:202`). **Fix:** alinhar seed ao schema (`id` string, `dimensao`, escala 1-4) OU tornar o parser tolerante.

4. **[ALTO] eNPS por chave fixa "enps"** `climate_service.py:694` — `resposta.respostas.get("enps", 0)`. Se a pergunta de recomendação tiver outro id (ex.: seed usa ids numéricos), eNPS é sempre 0/detrator. Acoplamento frágil a um id mágico.

5. **[MÉDIO] `/climate/alerts` stub** `human_resources/controllers/climate_controller.py:99` — retorna `[]` fixo enquanto existem 3 alertas reais de absenteísmo. O frontend exibe "0 alertas". **Fix:** apontar para `rh_alertas_absenteismo` ou ao retention.

6. **[MÉDIO] Turnover com dados mockados** `turnover_controller.py:289,354` — endpoints de recálculo gravam predições baseadas em mock. Se as tabelas existissem, gerariam dado **falso** em produção.

7. **[BAIXO] Surveys "ativas" mas vencidas** — seed com `data_fim` no passado; `ativo=True` é enganoso. `is_active` (model) corretamente as exclui, mas a UX mostra 3 ativas na listagem e 404 em "ativa".

8. **[BAIXO] double-prefix** `api/v1/__init__.py:153` (ver aresta 6).

---

## 6) Gaps de produção (o quê / por quê / como)
- **Formulário de coleta inexistente (POR QUÊ falta o core):** não há tela `/respond`. O vigilante nunca responde → `climate_responses=0` perpetuamente. **COMO:** criar página pública mobile de resposta (escala 1-4) + corrigir bug TZ #1 + alinhar seed #3.
- **Job de agregação ausente:** **COMO:** Celery beat mensal → `calcular_scores_periodo(periodo_atual)` + `verificar_quedas`.
- **Turnover sem fonte real:** **COMO:** substituir mock por loader que monta `dados_funcionario` de `employees` + ponto (faltas/atrasos) + `climate_scores` + `sst_afastamentos`; resolver mismatch de escala clima (0-100→1-5).
- **Duas implementações de clima:** consolidar. Decidir: ou o frontend passa a usar `/retention/climate/*` (profundo) ou deprecar o retention de vez. Hoje paga-se custo de manutenção dos dois.
- **Integração por evento:** publicar `funcionario.desligado`/`afastamento.iniciado` e consumir no turnover/clima; nada disso existe.
- **Anti-fraude incompleto:** `tempo_resposta < 30s` só loga warning, não bloqueia (`climate_service.py:347`); `ip_hash`/`ua_hash` coletados mas nunca usados para detecção.

---

## 7) Nota de prontidão: **22 / 100**

Justificativa:
- **+22** pela engenharia real e correta do retention (score/eNPS/alertas/heurística de turnover bem escritos) e pelos controllers RASOS do HR que **de fato funcionam** com dados reais (turnover trimestral 15.32% calculado de `employees`; absenteísmo com 3 afastamentos reais, custo R$900, taxa 4.23%).
- **−78** porque o módulo "profundo" alvo está **inutilizável**: caminho de coleta em 500 por TZ (#1), 0 respostas/scores/alertas históricos, tabelas de turnover inexistentes (#2), seed driftado (#3), **zero integração por eventos**, **zero job de agregação**, frontend apontando para o sistema raso (clima profundo é dead code), AI de recomendação órfã, e turnover alimentado por mock. As features clima→turnover (26% do peso) nunca recebem dado real.

Em produção hoje funciona apenas o "clima/turnover/absenteísmo raso" do `human_resources` (dashboards descritivos sobre `employees`/`sst_afastamentos`). O sistema de **pesquisa de clima com coleta de respostas reais, eNPS e alertas** — o objeto central deste módulo — **não coleta uma única resposta** e está quebrado de ponta a ponta.

### Arquivos-chave
- `/opt/conecta-pro/backend/modules/retention/climate/models/climate_models.py:189` (bug TZ)
- `/opt/conecta-pro/backend/modules/retention/climate/services/climate_service.py` (lógica profunda)
- `/opt/conecta-pro/backend/modules/retention/climate/controllers/climate_controller.py:142,255` (parse QuestionSchema; /respond)
- `/opt/conecta-pro/backend/modules/retention/turnover/services/turnover_predictor.py:101-123` (features clima sem fonte)
- `/opt/conecta-pro/backend/modules/retention/turnover/controllers/turnover_controller.py:289,354` (mock)
- `/opt/conecta-pro/backend/modules/people_management/human_resources/controllers/climate_controller.py:99` (alerts stub; absenteísmo real)
- `/opt/conecta-pro/backend/main_production.py:586` (mount real); `/opt/conecta-pro/backend/api/v1/__init__.py:153` (double-prefix dead)
- `/opt/conecta-pro/frontend/src/app/modulos/rh/clima/page.tsx:8` e `gestao-pessoas/rh/clima/page.tsx:8` (apontam para HR raso; clima profundo sem consumidor)

---

### ?

I have all the evidence needed. Here is the complete audit report.

---

# AUDITORIA PROFUNDA — Módulo Reembolso (Conecta PRO)
**Escopo:** `modules/reimbursement` + re-exports em `people_management/hr` + frontend `modulos/reembolso`, `modulos/dp/reembolsos`, `modulos/operacional/reembolsos`. READ-ONLY (nada foi modificado; o POST `/process` foi corretamente bloqueado pela trava de write e não foi executado).

## 1) INVENTÁRIO (lógica real)

**Models (4)** — `modules/reimbursement/models/`
- `ReimbursementRequest` (`reimbursement_request.py`): máquina de estados **rica e bem-feita no código** (`submit`/`approve`/`reject`/`cancel`/`mark_as_processed`/`return_to_draft`). Enum `ReimbursementStatus` = `rascunho, pendente, em_analise, aprovado, rejeitado, processado, cancelado`. Cálculos:
  - `calculate_total()` (l.165) soma `item.amount` dos itens ativos.
  - `determine_approval_level()` (l.175) define nível por faixa de valor: SUPERVISOR ≤500, GERENTE ≤2000, DIRETOR ≤10000, FINANCEIRO acima. **Mas esse nível nunca é usado para gating de permissão** — qualquer usuário autenticado aprova qualquer valor (ver §5).
  - `mark_as_processed()` (l.242) exige status APROVADO e grava `payable_account_id`.
- `ReimbursementItem` (`reimbursement_item.py`): **dupla coluna redundante** `category` + `category_type` (l.97-98), ambas preenchidas com o mesmo valor pelo repo (l.371-372). `approve()`/`reject()` por item, `final_amount` (aprovado ou solicitado). `category_id` FK opcional para `reimbursement_categories` — **nunca preenchido** (a categoria é sempre o enum string).
- `ReimbursementCategory` (`reimbursement_category.py`): regras de limite (`check_limit`, l.71), auto-aprovação (`can_auto_approve`, l.84), conta contábil, centro de custo. **Tabela 100% vazia → toda essa lógica é código morto** (ver §3).
- `ReimbursementAttachment` (`reimbursement_attachment.py`): storage em filesystem, validação `is_valid`, thumbnails (campo existe, nunca gerado).

**Repository** (`reimbursement_repository.py`): CRUD + queries de listagem/stats. Sequência de código `_get_next_sequence()` (l.345) conta **globalmente** por `REI-{ano}-%` (corrigido contra colisão entre condomínios) — **mas é race-condition-prone**: dois POSTs concorrentes geram o mesmo `count+1` → `UniqueViolation` no `code` (l.74 unique). Não usa sequence do Postgres nem advisory lock.

**Services (3)**:
- `ReimbursementService`: CRUD de request/item/attachment. Faz `commit` próprio em cada método.
- `ApprovalService`: fluxo de aprovação. `process_payment()` (l.210) é o ponto crítico — **stub** (ver §4).
- `FileValidator`: valida tamanho (10MB) e MIME. **Valida apenas `content_type` declarado pelo cliente** — não verifica magic bytes; um arquivo malicioso com `Content-Type: image/png` passa.

**Controller** (`reimbursement_controller.py`): ~30 endpoints sob `/api/v1/reimbursements`. Ordem de rotas corrigida (`ready-for-payment` antes de `/{request_id}`, comentário l.222). Padrão de re-fetch pós-commit em todos os mutadores (workaround do session-expire).

## 2) FRONTEND

| Tela | Estado | Observações |
|---|---|---|
| `modulos/reembolso/page.tsx` | **Wired** | Usa `useReimbursements({myOnly:true})` + `useReimbursementStats`. Modais form/detail. Statuses via `REIMBURSEMENT_STATUS_LABELS` de `types/reimbursement.ts` (vocabulário `pendente`/`processado`). |
| `modulos/reembolso/aprovacoes/page.tsx` | **Wired** | Fluxo de aprovação + modal. |
| `modulos/dp/reembolsos/page.tsx` | **Wired, mas divergente** | Chama `/api/v1/reimbursements/` direto com `fetch` cru. `statusConfig` (l.23) mistura **3 vocabulários**: PT-BR-novo (`submetido`,`pago`), PT-BR-enum (`rascunho`,`aprovado`) e EN (`pending`,`approved`,`rejected`). Sinal claro de retrabalho sem alinhamento. |
| `modulos/operacional/reembolsos/page.tsx` | **Wired (duplicado)** | Terceira UI para o mesmo dado. |
| Componentes `components/reembolso/` | OK | form-modal (19KB), detail-modal, approval-modal, attachment-upload. |

**Problema de UX/dado:** O `types/reimbursement.ts` (canônico) NÃO tem `submetido` nem `pago` no type union (l.6-12: `rascunho/pendente/em_analise/aprovado/rejeitado/processado/cancelado`). Os 6 registros do banco com status `submetido`/`pago` **caem fora do `STATUS_COLORS`/`REIMBURSEMENT_STATUS_LABELS`** → renderizam sem label/cor (badge quebrado/`undefined`) na tela principal e de aprovações.

## 3) BANCO

```
reimbursement_requests   = 21  (1 soft-deleted → API lista 20)
reimbursement_categories =  0  ← VAZIA
reimbursement_items      =  6  (só 6 das 21 requests têm itens!)
reimbursement_attachments=  0  ← VAZIA (nenhum comprovante jamais anexado)
```
Breakdown de status (real no banco):
```
rascunho  10 | aprovado 4 | submetido 4 | pago 2 | rejeitado 1
```

**Achados de qualidade de dado (graves):**
1. **`condominio_id` é NULL em TODAS as 21 linhas** — apesar de `nullable=False` no model (l.69). Isso prova que os dados foram inseridos por **SQL/seed externo bypassando a ORM** (o `NOT NULL` não está aplicado no banco ou foi inserido com constraint desabilitada). Consequência: `list_pending_approvals` e `list_ready_for_payment` filtram por `condominio_id == X` (repo l.189, l.225) — para qualquer usuário não-admin (que tem condominio_id setado) **essas 21 linhas são invisíveis**. Só admin (que vira `condominio_id=None` → sem filtro) as vê.
2. **Status `submetido` e `pago` não existem no enum** `ReimbursementStatus`. Nenhum código Python escreve esses valores (grep confirmou: só aparecem em comentários). São dados órfãos de um seed antigo com vocabulário diferente. Resultado direto no smoke test: `stats.pending_count = 0` apesar de **4 requests "submetido"** — porque o stats conta `pendente`+`em_analise` (repo l.308). **As 4 solicitações submetidas estão num limbo: nenhum endpoint as trata como pendentes de aprovação.**
3. **15 das 21 requests não têm itens.** `submit()` exige ≥1 item (model l.193) — logo essas 15 nunca poderiam ter sido submetidas pelo fluxo normal; mais evidência de seed manual.
4. `payable_account_id` NULL em 100% das linhas; `status='processado'` = 0; mas 2 linhas têm `paid_amount > 0` com status `pago` (inexistente). **Zero rastro de integração financeira real.**
5. `reimbursement_categories` tem FK para `condominiums.id` (existe) mas está vazia.

## 4) **INTEGRAÇÃO** (seção crítica)

### Eventos que PUBLICA → consumidores
**NENHUM.** Não há `publishers.py`/`handlers.py` no módulo, e grep no event-bus de `people_management/core/events/` por "reimbursement"/"reembolso" retornou vazio. O módulo é **totalmente mudo** no barramento de eventos.

### Eventos que CONSOME ← origem
**NENHUM.** Não escuta nada de DP/folha/financeiro.

### Tabelas compartilhadas
- **Lê** `users` (FK `requester_id`, `approved_by`, `processed_by`, `uploaded_by`) — 21/21 requesters válidos em `users` (OK).
- **Lê** `condominios`/`tenants` (via `CondominioRepository.get_first_active_condominio`, raw SQL).
- **Não toca** `employees`, `posts`, `allocations`, `hr_payslips`, `gp_*`. **O reembolso é vinculado a `users`, não a `employees`** — desconexão estrutural com DP/folha. Um reembolso aprovado não tem como virar verba na folha porque não conhece o `employee_id`.

### Imports cruzados
- `people_management/hr/controllers/reimbursement_controller.py` e `.../services/reimbursement_service.py` apenas **re-exportam** o módulo `reimbursement` (com fallback stub em ImportError). São cascas finas.
- `modules/pessoas/__init__.py` re-exporta o router.

### ARESTAS QUEBRADAS (as conexões que falham)
1. **🔴 Integração financeira é um STUB com ID FALSO.** `ApprovalService.process_payment` (`approval_service.py` l.210-252): em vez de criar conta a pagar, faz `fake_payable_id = uuid_lib.uuid4()` (l.242) e grava esse UUID inventado em `payable_account_id`. O método real `_create_payable_account` (l.254-283) está **inteiramente comentado**. **Confirmado: `PayableService.create_account` EXISTE** (`modules/financial/services/payable_service.py:49`) e `PayableAccountCreate` existe (`schemas/payable.py:81`) — ou seja, a integração foi deixada pela metade de propósito. Em produção, "processar" um reembolso **mente**: marca como `processado` apontando para uma conta a pagar que não existe → o financeiro nunca paga, e o `payable_account_id` é um ponteiro órfão. **Reembolso PAGO NÃO vira lançamento financeiro. NÃO vira verba de folha.**
2. **🔴 Router montado 2-3x no mesmo prefixo.** `reimbursement_router` é incluído em `/api/v1/reimbursements` por `main_production.py:589` E via `people_management` aggregator → `hr/aggregator.py:118` → `hr/controllers/reimbursement_controller.py:22` (prefix `/reimbursements`) → que também está em `people_management/__init__`. Rotas duplicadas no mesmo path; FastAPI usa a primeira registrada, mas polui o OpenAPI e cria ambiguidade de tags (`Reimbursement` vs `DP - Reembolsos`).
3. **🟠 Vínculo condominio_id NULL** quebra todo filtro multi-tenant (detalhado em §3.1).
4. **🟠 Vocabulário de status divergente** entre DB / backend-enum / frontend-canônico / frontend-DP (detalhado em §3.2 e §2).

## 5) BUGS CONCRETOS (file:line + fix)

1. **`approval_service.py:242` — `fake_payable_id`.** Integração financeira falsa. **Fix:** descomentar/implementar `_create_payable_account` chamando `PayableService(self.session).create_account(PayableAccountCreate(...))`, passar o ID real e tratar transação atômica (mesma sessão). Hoje grava UUID inventado.

2. **`approval_service.py:210` (`process_payment`) — sem rollback/atomicidade.** Faz `mark_as_processed` + `commit` sem try/except. Quando a integração real existir, criar payable e marcar request **devem ser uma transação**; hoje cada `commit` é isolado em vários services → risco de estado parcial.

3. **`reimbursement_repository.py:345` (`_get_next_sequence`) — race condition.** `SELECT count(*)` + `+1` sob carga concorrente gera `code` duplicado → `UniqueViolation` (model l.74). **Fix:** Postgres `SEQUENCE` por ano ou `INSERT ... ON CONFLICT` com retry, ou advisory lock `pg_advisory_xact_lock`.

4. **Status `submetido`/`pago` órfãos no banco.** Model usa `pendente`/`processado`. **Fix (dado):** migration de normalização `submetido→pendente`, `pago→processado`; e popular `condominio_id`. **Fix (código):** alinhar `dp/reembolsos/page.tsx:23` ao enum único.

5. **`reimbursement_controller.py:41` — RBAC inexistente.** `get_condominio_id` só checa `user.role == "admin"`. **Qualquer usuário autenticado pode aprovar/rejeitar/processar qualquer reembolso.** `ApprovalService.check_approval_permission` (l.285) existe mas **nunca é chamado**. `determine_approval_level` é calculado e ignorado. **Fix:** chamar `check_approval_permission(user_level, request.approval_level)` em `approve_request`/`process_payment` e 403 se falhar.

6. **`file_validator.py:74` — validação MIME por content-type declarado.** Não checa magic bytes. **Fix:** validar assinatura real (`python-magic`).

7. **`reimbursement_request.py:199,211` — `datetime.utcnow()` naive** gravado em colunas `DateTime(timezone=True)`. Mistura naive/aware → comparações e ordenação por `submitted_at`/`approved_at` ficam ambíguas em TZ. **Fix:** `datetime.now(timezone.utc)`.

8. **`reimbursement_item.py:97-98` — colunas `category` e `category_type` redundantes**, sempre iguais. Risco de divergência futura. **Fix:** remover `category` (manter `category_type`) ou consolidar.

9. **`approval_service.py:73` — `rejected_items: dict[UUID,str]` mas schema é `dict` solto** (`reimbursement_request.py:181`). As chaves chegam como **string** do JSON, não `UUID`; o lookup `item.id in rejected_items` (l.89) compara `UUID` com chaves-string → **rejeição de itens silenciosamente nunca casa**. **Fix:** normalizar chaves para `UUID` no service.

## 6) GAPS DE PRODUÇÃO (o quê / por quê / como)

- **Integração financeira real (BLOQUEADOR).** Por quê: reembolso aprovado não gera pagamento — funcionário nunca recebe. Como: implementar `_create_payable_account` (PayableService já existe), transação atômica, e idealmente publicar evento `reimbursement.processed` para o financeiro/folha.
- **Vínculo com `employees`/folha.** Por quê: hoje liga a `users`, não a funcionário; impossível virar verba de folha (CCT/CLT). Como: adicionar `employee_id` e decidir trilho — conta a pagar avulsa **ou** rubrica na folha do mês.
- **Categorias (tabela vazia).** Por quê: `reimbursement_categories` vazia → limites por categoria, auto-aprovação, conta contábil e centro de custo são código morto; o front cai no fallback hardcoded do enum (controller l.194). Como: seed de categorias por condomínio + wire do `category_id` no item + aplicar `check_limit`/`can_auto_approve` no `submit`/`approve`.
- **RBAC/hierarquia de aprovação.** Por quê: sem gating, qualquer um aprova/paga. Como: §5.5.
- **Eventos.** Por quê: módulo isolado do barramento; nenhum outro módulo sabe que um reembolso ocorreu. Como: publishers para `submitted`/`approved`/`processed`.
- **Saneamento de dados.** Por quê: `condominio_id` NULL + status órfãos + requests sem itens. Como: migration de limpeza + aplicar `NOT NULL` real no banco.
- **Anexos = 0.** Por quê: comprovante é obrigatório em reembolso corporativo, mas nenhum dos 21 tem anexo e `requires_receipt` nunca é checado. Como: tornar comprovante obrigatório no `submit` quando categoria exigir.
- **Concorrência de código** (§5.3) e **magic-byte validation** (§5.6).

## 7) NOTA DE PRONTIDÃO: **34/100**

**Justificativa:** A camada de domínio (máquina de estados, schemas, validações de transição) é de boa qualidade e os endpoints CRUD respondem 200. Porém o módulo **falha no seu propósito final**: o reembolso aprovado **não se conecta ao financeiro nem à folha** — `process_payment` grava um `payable_account_id` **falso** (`uuid4()` inventado), com a integração real 100% comentada embora o `PayableService` já exista. Some-se: zero integração de eventos; `condominio_id` NULL em 100% dos dados quebrando o multi-tenant; vocabulário de status divergente em 4 camadas deixando 6/21 registros em estado fantasma e `pending_count=0` para 4 submetidos; vínculo a `users` em vez de `employees`; tabela de categorias vazia (lógica de limites morta); ausência total de RBAC (qualquer usuário aprova/paga); bug de rejeição de itens por mismatch de tipo; e race condition na geração de código. É um **protótipo funcional de UI/CRUD**, não um módulo de reembolso pronto para produção. O fluxo rascunho→submetido→aprovado funciona; o **"→pago" é teatro**.

**Arquivos-chave:**
- `/opt/conecta-pro/backend/modules/reimbursement/services/approval_service.py` (l.210-283 — stub financeiro)
- `/opt/conecta-pro/backend/modules/reimbursement/models/reimbursement_request.py` (l.31-58 enum/limites; l.199,211 TZ)
- `/opt/conecta-pro/backend/modules/reimbursement/repositories/reimbursement_repository.py` (l.345 race)
- `/opt/conecta-pro/backend/modules/reimbursement/controllers/reimbursement_controller.py` (l.39-56 RBAC)
- `/opt/conecta-pro/backend/modules/reimbursement/services/file_validator.py` (l.74 MIME)
- `/opt/conecta-pro/frontend/src/app/modulos/dp/reembolsos/page.tsx` (l.23 status divergente)
- `/opt/conecta-pro/frontend/src/types/reimbursement.ts` (l.6-12 enum canônico)
- `/opt/conecta-pro/backend/modules/financial/services/payable_service.py` (l.49 — integração que deveria ser usada)

---

### ?

Final picture is clear. `portal_notifications.employee_id` is UUID type, but `my_notifications_controller` queries with `== str(employee_id)` (works via coercion). The notification table has 0 rows (never populated in practice — no payslips were "published" via the DP flow). `escala_padrao`/`turno_padrao` are set for most, but ~1 in 52 employees has NULL turno_padrao → triggers the 500. The `shifts` list is ALWAYS empty (the service never queries any allocation/escala table to build actual shifts).

I have a complete, evidence-backed picture. Compiling the final report.

---

# Auditoria Profunda — Portal do Funcionário (`modules/people_management/employee_portal`)

**Veredicto:** Camada de autenticação sólida, mas o portal é majoritariamente uma **fachada de agregação que não agrega**. A maioria dos endpoints cross-módulo retorna vazio ou 500 por bugs concretos de schema, import errado, tabela inexistente e divergência de status entre módulos. É o maior consumidor cross-módulo do sistema e é exatamente onde mais arestas estão quebradas.

---

## 1) Inventário (controllers / services / models — lógica real)

**Mount real:** `/api/v1/people-management/portal/...` (via `people_management/__init__.py:43`, dentro de `register_routers()`). **Atenção:** todo o `register_routers()` usa `except Exception: pass` (linhas 25,33,40,46,53) — se o aggregator do portal falhar ao importar, ele simplesmente **não é montado, sem nenhum log**.

**Controllers (13 routers):**
- `portal_controller.py` — auth real e funcional: login CPF+senha/data-nasc, primeiro-acesso, reset-senha (escrevem `portal_password_hash` via SQL cru, `employees` não tem o campo no ORM), refresh, me, dashboard. **Funciona** (validado 200 ao vivo).
- `my_schedules_controller.py` → `DocumentViewService.get_my_schedules`. **500 ao vivo.** Lê só campos escalares do `Employee`; `shifts` é **sempre `[]`** — nunca consulta nenhuma tabela de escala/alocação. `total_hours = carga_semanal * 4.33` (estimativa, não escala real).
- `my_payslips_controller.py` → `PayslipPortalService` → repo real `hr_payslips`. **Funciona** (200, lê dado real). PDF via reportlab inline.
- `my_vacations_controller.py` — **quebrado** (detalhes §5). Lê tabela `vacation_requests` (legada).
- `my_ponto_controller.py` — **quebrado** (import de classe inexistente + tabela errada, §5).
- `my_benefits_controller.py` — funcional, cruza CCT 2026 (`modules.cct`) com `EmployeeBenefit` (`hr`). Cacheado (TTL 1h).
- `my_documents_controller.py` — GET funciona; **POST `/sign` tem NameError garantido** (§5).
- `my_data_controller.py` — GET ok; PUT engole exceção de commit e retorna 200 mesmo em falha.
- `my_notifications_controller.py` — funcional; tabela `portal_notifications` tem **0 linhas** (nunca populada na prática).
- `my_trainings_controller.py`, `my_cct_controller.py`, `my_comunicados_controller.py`, `my_profile_controller.py` — leitura, retornam `[]` em qualquer erro.

**Services:**
- `PortalService` — auth + dashboard. `_validate_credentials` já foi corrigido contra bypass por data-nasc nula (linha 148). `get_dashboard`: `pending_documents = max(0, 0 - signed_count)` → **matematicamente sempre 0** (lógica placeholder, linha 223). `log_access` está **desabilitado** ("enum mismatch no DB", linha 94).
- `DocumentViewService` — **tem `get_my_payslips` que gera contracheques FALSOS** com tabela INSS/IRRF hardcoded antiga (teto `877.24`, dedução `528.0` — valores ~2019). **Não está wired** (o controller usa `PayslipPortalService` real), mas é uma bomba relógio: qualquer chamador novo gera holerite fictício. `get_my_schedules` é a origem do 500.
- `PayslipPortalService` — bem feito, delega a `modules.hr.employee_portal.repositories.payslip_repository`, fallback seguro com mensagem.
- `AutoNotificationService` — real, grava em `portal_notifications`. Disparado de verdade por `dp_payslips_controller.publicar` (DP → portal).

---

## 2) Frontend

**DOIS conjuntos de telas duplicados:**
- `src/app/portal-funcionario/*` (login, primeiro-acesso, reset-senha, dashboard, contracheques, ferias, dados-pessoais, treinamentos, documentos, notificacoes) — usa fetch direto para `/api/v1/people-management/portal/...` (prefixo **correto**, validado em `login/page.tsx:31`).
- `src/app/modulos/portal/*` (cct, documentos, ferias, dados-pessoais, contracheque, escalas, assinatura, beneficios, notificacoes, treinamentos, perfil, ponto) — segundo tree, provavelmente o "admin/preview" dentro do ERP.

Problemas de UX previsíveis pela falha de backend: **escalas** (500), **ferias** (lista sempre vazia + saldo errado), **ponto** (sempre vazio), **assinatura de documento** (500 no POST). As telas existem (wired), mas exibem dados quebrados/vazios. Há também `.next.bak-*` antigos no disco.

---

## 3) Banco (dados reais, hoje)

| Tabela | Linhas | Observação |
|---|---|---|
| employees ativos | 53 | |
| com `portal_password_hash` | **3** | só 3 conseguem logar de fato |
| com `data_nascimento` | 61 | login modo-2 disponível |
| com `salario_base` | 58 | 0/null → benefícios/férias R$0 |
| `posto_atual_nome` NULL | **71** | gatilho do 500 em /my-schedules |
| `escala_padrao` not null | 70 | |
| `turno_padrao` not null | 52 | os ~demais → 500 |
| hr_payslips | 51 | fonte real do contracheque |
| **gp_clock_punches** (ponto real) | existe | **mas controller importa classe errada** |
| `clock_punches` | **NÃO EXISTE** | controller tenta importar daqui |
| `time_bank` (fallback ponto) | **0** | fallback inútil |
| `vacation_requests` (legada) | 10 | `days` = string `'30 dias'`; status `'aprovado'` |
| `hr_vacation_requests` | 15 | status `'APPROVED'/'SUBMITTED'` |
| `portal_notifications` | **0** | nunca populada |

**Qualidade do dado:** `vacation_requests.days` é `VARCHAR(10)` contendo `'30 dias'` (deveria ser inteiro). Holerite real de exemplo com `gross_salary: 489.86` (dado parcial/teste).

---

## 4) ⚠️ INTEGRAÇÃO (seção crítica)

### Eventos que o portal PUBLICA → consumidores
| Evento | Onde | Chamado? | Consumidor |
|---|---|---|---|
| `portal.documento.assinado` | publishers.py:65 | sim (my_documents:88, mas dentro de bloco com NameError) | **NENHUM** |
| `portal.ferias.solicitadas` | publishers.py:13 | **nunca chamado** | **NENHUM** |
| `portal.documento.solicitado` | publishers.py:39 | **nunca chamado** | **NENHUM** |

**ARESTA QUEBRADA #1 (estrutural):** o portal publica em `infrastructure.event_bus` (`ConectaEvent`). O único subscriber relevante é o **Sophia/Gedeon** (`gedeon/subscribers/sophia_subscriber.py:249`), cujos patterns são `dp.*, rh.*, ged.*, operacional.*, fiscal.*, financeiro.*, gp.*` — **`portal.*` não está na lista**. Logo, **100% dos eventos do portal caem no vácuo**. Não há handler em `people_management/core/events/handlers.py` para eles tampouco (e esse é um *segundo* event bus — `GPEventBus`, diferente do `infrastructure.event_bus`).

**ARESTA QUEBRADA #2:** Não existe endpoint para o funcionário **solicitar** férias ou documento pelo portal. Os publishers `publish_ferias_solicitadas`/`publish_documento_solicitado` existem mas nenhum controller os chama. O portal é **read-only de fato** para férias — o funcionário não consegue iniciar nada.

### Eventos que o portal CONSOME ← origem
**Nenhum, via event bus.** A única integração de entrada real é por **chamada direta**: `dp_payslips_controller.publicar()` → `AutoNotificationService.notify_payslip_published()` → grava `portal_notifications`. (DP "publica contracheque" → notificação aparece no portal). Funciona, mas a tabela está com 0 linhas porque ninguém publicou holerite por esse fluxo ainda.

### Tabelas compartilhadas (lê)
- `employees` (operacional) — perfil, auth, dashboard, dados, salário.
- `hr_payslips` (hr) — contracheques. ✅ funcional.
- `vacation_requests` (operacional/vacations, legada) — férias. ❌ tabela/status/tipo errados.
- `gp_clock_punches` (ponto) — ponto. ❌ import quebrado, lê tabela inexistente.
- `time_bank` (operacional) — banco de horas. Vazia.
- `EmployeeBenefit` (hr) + CCT (cct) — benefícios. ✅.
- `training_enrollments`/`training_certificates` (human_resources) — treinamentos. ✅ (20 enrollments).
- `portal_notifications`, `portal_digital_signatures`, `portal_access` (próprias).

### Imports cruzados diretos
Portal importa de: `operacional.models.employee`, `operacional.vacations.models`, `operacional.models.time_bank`, `operacional.disciplinary`, `hr.employee_portal.repositories`, `hr.models.benefits`, `human_resources.models.training`, `people_management.ponto.models.clock_punch`, `cct.models.benefits`, `people_management.common.utils.clt_calculator`. **Ninguém importa o portal** (consumo é só via DP→AutoNotification por chamada direta).

---

## 5) Bugs concretos (file:line + fix)

1. **`/my-schedules` → 500 (4 erros de validação).** `schedule.py:46-51` tipa `turno_padrao/posto_atual_nome/escala_padrao/jornada_trabalho` como `str`, mas `document_view_service.py:149-154` faz `getattr(emp, x, "")` que retorna **o valor `None`** quando a coluna existe-mas-é-nula (o default `""` só vale se o atributo não existir). Traceback ao vivo confirma os 4 campos. **Fix:** tornar os 4 campos `str | None = None` no schema, OU coalescer no service: `getattr(emp,"turno_padrao",None) or ""`. (O fix isolado de `posto_atual_nome` é **insuficiente** — são 4 campos.)

2. **`/my-vacations/requests` → sempre `[]`.** `my_vacations_controller.py:174`: `dias=getattr(v,"dias",None) or getattr(v,"days",None)` retorna a **string `'15 dias'`**, atribuída a `VacationRequestResponse.dias: int | None` → **ValidationError** engolida pelo `except Exception` da linha 182 → `[]`. Validado ao vivo (employee com 2 férias retorna vazio). **Fix:** parsear o int (`int(re.match(r'\d+', str(v.days)).group())`) e/ou corrigir o tipo da coluna `vacation_requests.days` (hoje `VARCHAR(10)` com `'30 dias'`).

3. **`/my-vacations/balance` → saldo sempre errado.** `my_vacations_controller.py:101` filtra `VacationRequest.status == "approved"`, mas a tabela armazena `"aprovado"` (PT). `dias_gozados` fica **sempre 0** → saldo sempre 30. Validado: ADAILSON tem 30 dias aprovados, balance retornou `dias_gozados:0, dias_saldo:30`. **Fix:** `status.in_(["approved","aprovado"])`. (E se status casasse, `dias_gozados += dias` quebraria com `'30 dias'` — bug #2 de novo.)

4. **`/ponto/historico` e `/banco-horas` → sempre vazios.** `my_ponto_controller.py:39`: `from modules.people_management.ponto.models.clock_punch import ClockPunch` → **ImportError** (a classe não se chama `ClockPunch`; existe `ClockPunchType`; a tabela real é `gp_clock_punches`). Cai no `except` silencioso → fallback `TimeBank` (tabela `time_bank` tem 0 linhas). Resultado: ponto e banco de horas **nunca mostram nada**. **Fix:** importar a model correta (`GPClockPunch`/nome real) e usar a tabela `gp_clock_punches`.

5. **POST `/my-documents/{id}/sign` → NameError 500.** `my_documents_controller.py:90`: `funcionario_nome=getattr(current_user, "full_name", "")` — `current_user` **não é parâmetro** desta função (ela recebe `employee_id`). `NameError` em toda assinatura. **Fix:** trocar por nome buscado via `employee_id` ou `""`. Além disso o evento publicado não tem consumidor (aresta #1).

6. **`get_dashboard` `pending_documents` placeholder.** `portal_service.py:223`: `max(0, 0 - signed_count)` → matematicamente sempre 0. Conta assinaturas *feitas*, não pendentes. Lógica inexistente.

7. **`DocumentViewService.get_my_payslips` gera holerite FALSO** com tabela INSS hardcoded desatualizada (`document_view_service.py:72-73`). Não wired hoje, mas é landmine — deve ser removido para evitar uso acidental.

8. **`PUT /my-data` mascara falhas.** `my_data_controller.py:138` engole exceção de commit e retorna 200 com os campos do request (linha 144), dando falso sucesso ao funcionário mesmo se nada persistiu.

9. **`_mask_cpf` malformado.** `portal_controller.py:308`/`my_data_controller.py:72` produzem máscaras inconsistentes (`405.***.*29-1` com 1 dígito final; outra com `***.***.***.***-**`).

10. **`log_access` desabilitado** (`portal_service.py:94`) por "enum mismatch no DB" — **sem trilha de auditoria de acesso** ao portal (LGPD/compliance).

---

## 6) Gaps de produção

- **Submissão de férias/documentos**: não existe. Portal é read-only; publishers órfãos. *Como:* criar `POST /my-vacations/request` chamando `publish_ferias_solicitadas` E registrar em `hr_vacation_requests`, e inscrever `portal.*` no Sophia/handler de DP.
- **Escala real**: `shifts` nunca é populado. *Por quê:* o service nunca consulta tabela de alocação/escala. *Como:* JOIN com a tabela de escalas do operacional por `employee_id` + mês.
- **Ponto**: corrigir model/tabela (`gp_clock_punches`) — é o ponto eletrônico real do sistema (Tangerino).
- **Notificações**: pipeline existe (DP→AutoNotification) mas 0 linhas — depende de DP publicar holerites por aquele fluxo; outros eventos (escala publicada, férias aprovada, alerta H.E.) não disparam notificação de verdade fora do test-trigger.
- **Auditoria de acesso (LGPD)**: reabilitar `log_access` corrigindo o enum.
- **Adoção**: só 3/53 funcionários têm senha — sem onboarding em massa o portal está praticamente vazio de usuários.
- **Consolidar os dois trees de frontend** (`portal-funcionario` vs `modulos/portal`).
- **Higiene**: 3 arquivos `.bak-frente1-lote` em `models/`; `register_routers` com `except: pass` que esconde falhas de mount.

---

## 7) Nota de prontidão: **38/100**

**Justificativa:**
- **Auth (sólido, +):** JWT com audience isolada, bcrypt, primeiro-acesso/reset, fix de bypass por data-nasc nula. Login/me/dashboard/my-data validados 200 ao vivo. (~9/10)
- **Agregação cross-módulo (o core do portal — falha grave):** dos 5 fluxos-chave que o portal deveria agregar, **só contracheque e benefícios funcionam**. Escalas=500, férias=lista vazia + saldo errado, ponto=sempre vazio (tabela/import errados), assinatura de doc=500. (~3/10)
- **Integração por eventos (quebrada):** 100% dos eventos publicados não têm consumidor (bus errado + pattern ausente no Sophia); publishers de férias/documento nunca chamados; sem caminho de escrita. Única integração viva é DP→notificação por chamada direta, com tabela vazia. (~2/10)
- **Qualidade de dado/robustez:** `except Exception` mascarando bugs em quase todos os endpoints (transformam falha em `[]` silencioso), holerite-falso latente, dado sujo (`'30 dias'` em coluna numérica), auditoria desligada, mask de CPF bugada.

Não está pronto para produção. Os 4 bugs P0 (#1 escalas, #2/#3 férias, #4 ponto, #5 assinatura) precisam ser corrigidos e, sobretudo, a **camada de integração por eventos precisa ser efetivamente conectada** — hoje o portal "agrega" mas o que ele agrega está, em sua maioria, quebrado ou vazio.

**Arquivos-chave:** `/opt/conecta-pro/backend/modules/people_management/employee_portal/schemas/schedule.py:46-51`, `controllers/my_vacations_controller.py:101,174,182`, `controllers/my_ponto_controller.py:39,69`, `controllers/my_documents_controller.py:90`, `services/document_view_service.py:72-73,149-154`, `services/portal_service.py:94,223`, `publishers.py`, `__init__.py:19-47`, e o subscriber órfão `/opt/conecta-pro/backend/modules/gedeon/subscribers/sophia_subscriber.py:249`.

---

### ?

Confirmed: the Scale model has NO `client_id` attribute. In `scale_controller.py:448`, `publish_escala_publicada` uses `str(scale.client_id) if hasattr(scale, "client_id") and scale.client_id else None` — `hasattr` returns False, so `cliente_id` is ALWAYS None. Combined with the post.client_id NULL issue, GEDEON's escala consumer never fires. I now have a complete, deep picture. Let me write the final report.

# AUDITORIA PROFUNDA — Módulo Operações (operacional)

## 1) INVENTÁRIO (controllers / services / models — com a lógica real)

O módulo `modules/operacional` é o maior do ERP (~48 mil linhas). Núcleo: `posts → allocations → scales → shifts`, mais 6 submódulos (disciplinary, diaristas, occurrences, inspection_rounds, communication, vacations). O segundo path (`modules/people_management/operations`) é só um wrapper de IA (`scale_optimizer`, `occurrence_classifier`) — não toca DB de produção.

### Ciclo central escala → ponto → folha

**Gerador de escala** (`services/scale_generator.py`): singleton in-memory (sem IA real, apesar do nome). Lógica por tipo:
- `_generate_12x36` (linhas 151-231): **NÃO é um 12x36 real**. Divide a equipe em metade diurna/metade noturna (`mid = len(employee_ids)//2`), gera UM turno por dia para cada metade e troca de funcionário a cada 2 dias (`if day % 2 == 0: day_idx += 1`, linha 203). Isso produz 6 dias de trabalho seguidos por funcionário antes do rodízio — viola o padrão real 12x36 (1 dia on / 1 dia off intercalado por par par/ímpar). Comentário do próprio código admite: "Simplificação". Não gera folgas (`is_off_day` sempre False no 12x36) — ou seja, o funcionário aparece trabalhando TODOS os dias do mês no turno dele.
- `_generate_6x1` / `_generate_5x2` / `_generate_turno_revezamento` / `_generate_generic`: mais corretos, calculam folgas por padrão escalonado.
- `optimize_scale` / `_validate_rest_intervals` (linhas 526-563): valida intervalo de 11h CLT mas **só faz logging** — nunca corrige nem rejeita. E acessa `prev.end_time` / `curr.start_time` (linhas 549-553), atributos **que não existem** no `ShiftCreate` (os campos são `planned_start_time`/`planned_end_time`). Se `optimize_scale` fosse chamado, lançaria AttributeError — mas o controller `/generate` NUNCA chama optimize, então é código morto que esconde um bug.

**Cálculo de horas/folha** (`models/shift.py`):
- `calculate_hours()` (linha 181) e `shift_repository.check_out()` (linha 362): ambos fazem `shift_date.replace(day=shift_date.day + 1)` para turno que vira a noite. **Crash garantido no último dia do mês** (ex.: 30/04 → day=31 → `ValueError: day is out of range for month`). Bug de virada de mês em turno noturno.
- **Os campos de pagamento `base_pay`, `night_bonus`, `holiday_bonus`, `overtime_pay`, `total_pay`, `night_hours` NUNCA são calculados** em lugar nenhum (`grep` em shift_repository = vazio). Ficam todos em 0.0. Confirmado em produção: `scales/stats` retorna `total_estimated_cost: 0.0`, `total_hours: 0.0`. Ou seja **a escala não alimenta custo nem folha** — o ciclo escala→folha está cortado na origem.

**Check-in/check-out** (`shift_repository.py:295-378`): funcionais — gravam `actual_start_time`, mudam status para IN_PROGRESS/COMPLETED, calculam `actual_hours` e `overtime_hours` (com a regra fixa de 8h, errada para 12x36 onde a jornada é 12h). Publicam `OPS_TURNO_INICIADO/ENCERRADO`. **Mas nada de fora chama esses endpoints** a partir do ponto (batida) — não há vínculo automático ponto→shift.

### Submódulos
- **disciplinary** (816+990+805 linhas): controller/repo/service completos; `get_stats` (repo:521) é robusto. 0 registros em DB.
- **occurrences / inspection_rounds**: services completos (857/746 linhas), endpoints 200, mas 0/3 registros.
- **diaristas**: o mais maduro (modelo 696 linhas, fiscal, AI). `IntegrationService` cruza diaristas×postos.
- **substitution / time_bank / vacations**: controllers presentes, 0 registros.

## 2) FRONTEND (telas)

30 páginas em `src/app/modulos/operacional/`. Amostragem:
- **escalas** (`escalas/page.tsx`): totalmente wired — `useScaleOperations` (generate/submit/approve/publish/delete), filtros por status/mês/ano, modal de geração. Fluxo de status completo na UI.
- **medidas-administrativas**: wired via cliente gerado Orval, hook `useDisciplinaryStats` → chama corretamente `/estatisticas` (não o `/stats` quebrado).
- **substituicoes / alocacoes / turnos / postos / ocorrencias**: têm `useQuery`/`refetch` — wired, mas mostram listas vazias porque o DB está vazio (substituições/ocorrências = 0).
- UX: páginas existem para todos os submódulos (rondas, banco-horas, diaristas, comunicados, kpi, cobertura, ai-command-center). O problema não é tela faltando — é **dado de origem ausente** e o **elo posto↔cliente quebrado** que esvazia dashboards por cliente.

## 3) BANCO (tabelas, linhas, qualidade)

Consulta real (`SyncSessionLocal`):
| Tabela | Linhas | Observação |
|---|---|---|
| posts | 12 (9 active/3 inactive) | **client_id preenchido em 1/12; ged_client_id 0/12; contract_id 0/12** |
| allocations | 58 (46 active) | 57 employees distintos / 10 postos. **Todos os employee_id existem em employees (0 órfãos)** — esse elo está OK |
| scales | 3 (todas `draft`) | os 3 postos com escala têm **client_id = NULL** |
| shifts | 180 (todos com employee, todos `scheduled`) | abril/2026, 3 escalas, nenhum check-in |
| substitutions | 0 | |
| occurrences | 0 | |
| disciplinary_actions | 0 | |
| inspection_rounds | 3 | |
| time_bank | tabela existe (modelo correto) | |
| gp_clock_punches | tabela de ponto separada | **sem FK para shifts** |

Qualidade: o vínculo **allocation→employee é sólido**; o vínculo **post→client/contract/ged_client é o buraco estrutural** (1/12, 0/12, 0/12).

## 4) INTEGRAÇÃO (seção destacada) — ARESTAS QUEBRADAS

### Eventos que o módulo PUBLICA (`publishers.py`) → consumidores reais
Todos vão para o bus unificado `infrastructure.event_bus` (`EventTypes.OPS_*`). **O único subscriber de eventos OPS em todo o backend é o GEDEON** (`modules/gedeon/gedeon.py:63-65`):
- `OPS_OCORRENCIA_REGISTRADA` → GEDEON `_on_ocorrencia_registrada` ✅ (mas occurrences=0, nunca dispara)
- `OPS_ESCALA_PUBLICADA` → GEDEON `_on_escala_publicada` (gedeon.py:254) — **dispara mas é inútil**: só atualiza contexto SE `event.cliente_id` existir (linha 256), e o cliente_id chega sempre None (ver abaixo)
- `OPS_CAT_REGISTRADA` → GEDEON `_on_cat_registrada` ✅

**Eventos publicados SEM nenhum consumidor (publish-no-op):** `OPS_ALOCACAO_CRIADA`, `OPS_TURNO_INICIADO`, `OPS_TURNO_ENCERRADO`, `OPS_SUBSTITUICAO_REALIZADA`, `OPS_BANCO_HORAS_CRIADO`, `OPS_MEDIDA_DISCIPLINAR_CRIADA`, `OPS_FERIAS_APROVADAS_OP`, `OPS_DIARISTA_*`, `OPS_COMUNICADO_PUBLICADO`. São disparados no vazio.

### ARESTA QUEBRADA #1 — escala publicada nunca cria ponto nem notifica (a mais grave)
- `scale_controller.publish_scale` (linha 445-455) chama `publish_escala_publicada(... cliente_id = str(scale.client_id) if hasattr(scale,"client_id") and scale.client_id else None ...)`. **O modelo `Scale` NÃO tem atributo `client_id`** (confirmado em `models/scale.py`). Logo `hasattr` é sempre False → **`cliente_id` é SEMPRE None**, e `funcionarios=[]` é hardcoded. O evento sai sem cliente e sem funcionários.
- Há **DOIS sistemas de "escala publicada" desconectados**:
  - O moderno: `OPS_ESCALA_PUBLICADA` = `"operacional.escala.publicada"` (publicado pelo controller).
  - O legado GP: `GPEventTypes.ESCALA_PUBLICADA` = `"gp.escala.publicada"`, ao qual `people_management/agents/ponto_agent.py:417` e `portal_agent.py:125` se inscrevem. **Ninguém publica `gp.escala.publicada`** (grep por publish/emit = vazio). E mesmo o handler `ponto_agent._on_escala_publicada` (linha 439) é **um no-op que só faz `logger.info`** — não cria ClockPunch esperado, não popula horário esperado.
  - Os agents/orchestrator do GPEventBus (Redis pubsub separado, `core/events/event_bus.py`) **não são iniciados no `main_production.py`** (grep por orchestrator/PontoAgent/register_agent no startup = vazio). É código legado órfão.
- **Resultado:** publicar uma escala não notifica funcionário, não cria batida esperada, não gera espelho de ponto. O ciclo escala→ponto está completamente cortado.

### ARESTA QUEBRADA #2 — posto sem cliente quebra TODO o ecossistema transversal
O `post.client_id`/`contract_id`/`ged_client_id` quase sempre NULL significa que:
- `IntegrationService.get_dashboard_unificado(cliente_id=...)` e `get_ocupacao_postos` filtram por `Post.client_id` → retornam vazio por cliente.
- GEDEON não consegue associar escala/ocorrência ao condomínio (depende de `event.cliente_id`).
- Área-cliente / portal do condomínio não enxerga os postos dele.
- Financeiro/contratos não conseguem custear posto por contrato.
É a aresta de maior impacto: **o posto é o nó central que deveria amarrar operação ↔ cliente ↔ contrato ↔ GED, e está solto.**

### ARESTA QUEBRADA #3 — IntegrationService consulta colunas inexistentes (crash latente)
`services/integration_service.py` linhas 237, 241, 443, 450-451: `func.date(Shift.start_time)`. **O modelo Shift não tem `start_time`** (é `planned_start_time` + `shift_date`). Qualquer chamada a `get_dashboard_unificado` / `get_metricas_periodo` levanta erro de atributo/SQL. O dashboard unificado de diaristas+operacional está quebrado em runtime.

### Imports cruzados
- operacional → `infrastructure.event_bus`, `core.*`. Não importa people_management diretamente (bom).
- people_management/ponto e hr publicam no MESMO bus (`infrastructure.event_bus`) — então a infra está unificada; o problema é só os agents legados (GPEventBus Redis) que ficaram para trás.
- Dependentes de operacional (memória/AST): ai, document_kits — mas o acoplamento real de eventos é só GEDEON.

## 5) BUGS CONCRETOS (file:line + fix)

1. **500 em `/medidas-administrativas/stats`** — `disciplinary_controller.py:466` `GET /{action_id}` captura `"stats"` e passa para query UUID → `asyncpg.DataError: invalid UUID 'stats'` (reproduzido; log confirmado). **Fix:** validar `action_id` como UUID no início do handler e retornar 404, ou declarar `action_id: UUID` no path param (FastAPI rejeita não-UUID com 422 antes de tocar o DB).

2. **`Scale.client_id` inexistente** — `scale_controller.py:448`. `hasattr(scale,"client_id")` sempre False → evento de escala publicada sai com `cliente_id=None`. **Fix:** derivar o cliente via `post.client_id` (ou `ged_client_id`) buscando o Post; e popular `funcionarios` com os `employee_id` distintos dos shifts.

3. **Crash de virada de mês em turno noturno** — `models/shift.py:181-184` e `shift_repository.py:362`: `shift_date.replace(day=shift_date.day+1)`. **Fix:** usar `shift_date + timedelta(days=1)`.

4. **`Shift.start_time` inexistente no IntegrationService** — `integration_service.py:237,241,443,450,451`. **Fix:** trocar por `func.date(Shift.shift_date)` (já é Date) ou `Shift.shift_date`.

5. **`diarista_id` vs `diarist_id`** — `integration_service.py:586`: `{s.diarista_id for s in schedules_ocupados}`. O modelo DiaristSchedule usa `diarist_id` (PT? checar) — o set fica com chave errada e o filtro de conflito de diarista (linha 593) nunca casa → sugere diaristas já ocupados. **Fix:** usar `s.diarist_id`.

6. **`optimize_scale` quebrado e morto** — `scale_generator.py:549-553` acessa `prev.end_time/start_time` que não existem. Não é chamado, mas é uma bomba. **Fix:** usar `planned_end_time/planned_start_time` ou remover.

7. **12x36 não gera folgas e não respeita o padrão** — `scale_generator.py:151-231`: `is_off_day` sempre False; rodízio a cada 2 dias gera 6 dias on consecutivos. **Fix:** implementar o ciclo real on/off por par de funcionários (escala A dias ímpares, escala B dias pares).

8. **`overtime` fixo em 8h** — `models/shift.py:189` `calculate_overtime(regular_hours=8.0)` aplicado a turnos de 12h → toda jornada 12x36 vira 4h extra. **Fix:** derivar `regular_hours` do tipo de escala/posto.

9. **`asyncio.create_task` em publish sem retenção de referência** — `scale_controller.py:445`: task pode ser coletada pelo GC antes de rodar. **Fix:** `await` direto (o publisher já é fail-safe) ou guardar a referência.

10. **Pagamentos nunca calculados** — `shift_repository` nunca seta `base_pay/night_bonus/holiday_bonus/total_pay`. `scale.estimated_cost` sempre 0. **Fix:** calcular pay no check_out e em update_metrics, usando `post.night_shift_bonus_percent`, `hazard_pay_percent` e adicional de feriado.

## 6) GAPS DE PRODUÇÃO (o que falta, por quê, como)

- **Elo posto↔cliente↔contrato↔GED (CRÍTICO):** preencher `posts.client_id`, `contract_id`, `ged_client_id`. Por quê: é o nó que liga operação a cliente/financeiro/GED/portal. Como: backfill a partir dos contratos reais (11 contratos em memória) + UI obrigatória de cliente ao criar posto + validação NOT NULL gradual.
- **Ciclo escala→ponto→folha:** hoje cortado em 3 pontos (evento sem cliente/funcionários; handler ponto no-op; pay não calculado). Como: ao publicar escala, criar registros de "ponto esperado" por shift e notificar; conectar `gp_clock_punches` a `shifts` (FK + matcher por employee+data); calcular pay.
- **Dados operacionais reais:** escalas só em draft (nenhuma aprovada/publicada), 0 substituições/ocorrências/advertências. Por quê: módulo nunca foi exercitado end-to-end. Como: rodar o fluxo completo (gerar→submeter→aprovar→publicar) com dados reais e popular ocorrências/substituições.
- **Unificar/remover bus legado GP:** os agents `people_management/agents/*` + `core/events/event_bus.py` (Redis pubsub) estão órfãos e confundem (subscribers `gp.escala.publicada` sem publisher). Como: remover ou migrar para `infrastructure.event_bus`.
- **Validação CLT/CCT real:** intervalo de 11h só logado; 12x36 simplificado; sem teto de horas mensais; sem adicional noturno reduzido (hora noturna de 52'30"). Como: motor de regras CCT por categoria.
- **Hardening de rotas dinâmicas:** vários `GET /{id}` aceitam strings e dão 500 em vez de 404/422 (mesmo padrão do `/stats`). Como: tipar path params como UUID.

## 7) NOTA DE PRONTIDÃO: **34/100**

Justificativa:
- **+** Infra sólida: 30 telas wired, controllers/repos completos, permissões, cache, rate-limit, fluxo de status de escala correto na UI, allocation→employee íntegro, endpoints respondendo 200.
- **−** O **propósito central do módulo não funciona end-to-end**: a escala não gera folga correta (12x36), não calcula custo/folha (tudo 0), não vira ponto, não notifica. O ciclo escala→ponto→folha está cortado em 3 pontos independentes.
- **−** O **nó posto está desconectado de cliente/contrato/GED** (1/12), o que esvazia todo o valor transversal (dashboards por cliente, GEDEON, portal, financeiro).
- **−** Integração de eventos é teatro: 12 tipos publicados, **1 consumidor real (GEDEON)** e mesmo esse falha por `cliente_id=None`. Subscribers GP legados sem publisher.
- **−** Bugs de produção reproduzidos (500 em `/stats`) e crashes latentes garantidos (virada de mês noturno, `Shift.start_time` no IntegrationService, `diarista_id`).
- **−** Dados quase zerados (escalas só draft; substituições/ocorrências/advertências = 0): o módulo nunca foi exercitado de verdade.

Para chegar a ~70%: corrigir os 5 bugs de runtime (1-5), implementar cálculo de pay, conectar escala publicada → cliente real + ponto esperado, e fazer o backfill posto↔cliente↔contrato.

Arquivos-chave: `modules/operacional/services/scale_generator.py`, `modules/operacional/services/integration_service.py`, `modules/operacional/repositories/shift_repository.py`, `modules/operacional/models/shift.py`, `modules/operacional/models/post.py`, `modules/operacional/controllers/scale_controller.py:445-455`, `modules/operacional/disciplinary/controllers/disciplinary_controller.py:466`, `modules/operacional/publishers.py`, `modules/gedeon/gedeon.py:254`, `modules/people_management/agents/ponto_agent.py:439`.

---

### ?

Confirmed the final critical semantic bug: `completion_percentage = documents_signed / total_documents`, but `is_signed` means "digitally signed", NOT "file present". A kit can have 100% of files attached and show 0% completion because nothing is signed. Conversely, 120 docs have NULL file_path but `is_signed=true` (certidões), inflating completion without a real file. The export ZIP join (line 98) uses `os.path.join(GED_STORAGE_BASE, doc.file_path)` — for abs paths like `/app/uploads/...`, `os.path.join` discards the base and keeps the abs path (works), but for `/inter/...` it builds `/inter/...` which doesn't exist → placeholder. I have enough. Let me write the report.

I have completed the deep audit. Here is the full structured report.

---

# AUDITORIA PROFUNDA — Módulo GED / Kits Documentais (Conecta PRO)

**Escopo:** `modules/people_management/ged` (kit-documental mensal por condomínio) + `modules/gedeon` (orquestrador multiagente Drive). Read-only. Smoke tests executados via API (`localhost:8080`) e queries diretas no Postgres.

**Veredito antecipado:** O módulo tem modelagem sólida e lógica de coleta bem escrita, mas está **fraturado em produção** por (a) duas APIs GED concorrentes sobre as MESMAS tabelas, (b) event-handlers de integração 100% órfãos (nunca disparados), (c) download quebrado para 60% dos documentos por bug de path-base, e (d) vínculo employee→condomínio dependendo de fuzzy-match porque a FK real está zerada.

---

## 1) INVENTÁRIO (lógica real)

### Modelos (`ged/models/`)
- **`GedDocumentKit`** (`document_kit.py`): kit mensal. UNIQUE(`client_id`,`reference_month`). Campos de contagem (`total_documents`, `documents_signed`, `completion_percentage`), envio, aprovação. `recalculate_completion()` (linha 176) define `completion = documents_signed/total_documents`. **Bug de semântica** — ver §5.
- **`KitDocument`** (`kit_document.py`): doc individual. `employee_id` NULL = doc de empresa. `source_module` ∈ {dp, rh, fiscal, operacoes, manual}. Rastreabilidade via `source_record_id` existe no schema mas **nunca é preenchida** por nenhum collector (sempre NULL) — quebra a trilha "de onde nasceu o dado".
- **`GedClient`** (`client.py`): condomínio/administradora. 11 registros. Tem `google_drive_folder_id`, portal access. **Não há FK para `clients` (comercial) nem para `condominios` (gedeon)** — o vínculo é só por nome.
- **`KitDocumentAccessLog`**, **`ColetaAutomatica`** (config de agendamento).

### Services
- **`KitBuilderService`** (`kit_builder_service.py`, 919 linhas) — coração do agregador. `build_kit_for_client` → busca funcionários (`get_employees_for_client`), cria kit, chama `collect_payslips / collect_time_sheets / collect_benefit_receipts / collect_schedules / collect_company_certificates`, recalcula totais, depois `_match_onvio_docs`.
  - `collect_payslips` (264): cria placeholder `file_path=None` (honesto — comentário D3.1.1) por funcionário.
  - `collect_time_sheets` (321): **único collector que gera arquivo REAL** — lê `gp_clock_punches` (batidas de ponto reais), gera HTML via `PontoFolhaPDFService`, grava em `/app/uploads/ponto/...`. Boa lógica, datas como `date/datetime` (corrige DataError asyncpg).
  - `collect_benefit_receipts/schedules`: placeholders NULL.
  - `collect_company_certificates`: cria 5 CNDs com `is_signed=True` e `file_path=None` (placeholder, mas marcado assinado — infla completude).
  - `_match_onvio_docs` (677): casa placeholders com PDFs do Onvio via fuzzy-match `ged_client.name ↔ condominios.nome` (subset de palavras significativas) + `onvio_documents`. UPDATE só preenche file_path NULL/fake, nunca sobrescreve `/app/%` ou `http%`. Conservador e idempotente — bem feito.
  - `get_employees_for_client` (802): **2 passos** — (1) FK `posts.ged_client_id`; (2) fallback fuzzy por nome de posto. Emite WARNING no fallback.
- **`KitService`** (`kit_service.py`): CRUD + ciclo de vida (em_montagem→completo→enviado→conferido→aprovado). `recalculate_kit_completion` (297) duplica a fórmula de completude. `mark_kit_sent` usa `datetime.utcnow()` (naive) gravando em coluna `DateTime(timezone=True)` — ver §5.
- **`SignatureIntegrationService`**: SHA-256 do arquivo; `_calculate_file_hash` (357) usa `os.path.join(GED_STORAGE_BASE, file_path)` e, se o arquivo não existe, faz **fallback de hash com `datetime.utcnow()` no conteúdo** (linha 379) → hash não-determinístico → `verify_signature` SEMPRE retorna inválido em re-verificação para docs sem arquivo físico.
- **`ExportService`**: ZIP/PDF consolidado. Para arquivos ausentes gera placeholder `.txt`. Join de path em `GED_STORAGE_BASE` (linha 98) — ver §5.
- **`CertidoesUpdaterService`**, **`DocumentCollectorService`**, **`GoogleDriveService`**, **`IngestaoHistorica`**.

### Controllers (`ged/controllers/`, 48 rotas)
- `kit_controller` (566 l): CRUD, `/build`, `/auto-assemble`, `/send`, `/send-email`, `/enviar` (GDrive+email atômico), `/approve`, `/export/zip`, `/export/pdf`. **Montado só em `/people-management/ged/*`**, não em `/ged/*`.
- `document_controller`: upload/sign/download/list. Download com bug de path-base (§5).
- `client_controller`, `config_controller`, `coleta_automatica_controller`, `auto_assemble_controller`.

### gedeon (`modules/gedeon`)
Orquestrador separado (`kit_orchestrator.py`, agentes Kronos/Hermes/Themis/Sophia/Atlas/Argos). Opera sobre `condominios` + integrações (Onvio/Inter/Receita) e monta kits **no Google Drive**, não no `ged_document_kits`. É um SEGUNDO universo de "kit" que se cruza com o GED apenas pelo `_match_onvio_docs`.

---

## 2) FRONTEND

| Tela | API que chama | Estado |
|---|---|---|
| `gestao-pessoas/ged/kits/[id]` | `/api/v1/ged/kit-real/{id}` (legacy) + `/api/v1/people-management/ged/documents/{id}/download` (pm-ged) | **Wired, mas misto** — lista por uma API, baixa por outra |
| `gestao-pessoas/ged/montar-kit` | `/api/v1/gedeon/kits/completude` | Wired → gedeon, não pm-ged |
| `gestao-pessoas/ged` (página principal) | `/api/v1/gedeon/kits/completude` | Wired → gedeon |
| `documentos/kits` | nenhuma chamada `/api/v1/` detectada | **Stub/vazio** |
| `src/services/ged/*` (signatures, shares, versions, tags) | `/api/v1/ged/documents/*` (legacy enterprise GED) | Wired ao GED LEGADO, não ao kit-documental |

**UX:** a tela de detalhe lista documentos via `kit-real` (gedeon/Drive) mas o botão de download aponta para `people-management/ged` — para um doc cujo `file_path` é relativo `documents/...`, o download retorna **400 "Path de arquivo invalido"** (confirmado em runtime). Usuário vê o doc na lista mas não consegue baixá-lo.

---

## 3) BANCO (dados reais)

- `ged_clients`: **11** (9 condomínios + 1 administradora-ish + a própria Conecta Mais como "cliente" — registro espúrio CNPJ 35.710.481/0001-03).
- `ged_document_kits`: **38** kits. Status: 37 `em_montagem`, 1 `enviado`. **0** completo/aprovado. Meses: 2026-03..06 (+1 kit órfão `2020-01`, dado de teste). 7 kits com completude 0%, 31 entre 0-100, **nenhum** 100%.
- `ged_kit_documents`: **2046** (não 1966 como no enunciado — cresceu). Apenas **567** com `file_path` (28%). Por origem: dp=1033, gedeon=564, operacoes=210, fiscal=195, inter=44.
- **Qualidade dos paths (achado crítico):** dos 567 com path, só **163 existem em disco**. Os 346 `documents/...` (relativos) e 44 `/inter/...` apontam para `/opt/conecta-pro/storage/ged/documents/...` — **diretório que não existe** (`storage/ged` ausente). **404 paths são fantasma.**
- **120 docs com `file_path IS NULL` mas `is_signed=true`** (certidões/benefícios) — inflam completude sem arquivo.
- `posts`: 12 no total, **0 com `ged_client_id` preenchido** → fuzzy-match obrigatório.
- `condominios`: 11 ativos; `onvio_documents`: 732; `ged_certidoes`: 8.

---

## 4) INTEGRAÇÃO ⚠️ (seção crítica)

### Eventos que o GED CONSOME — todos ÓRFÃOS
`ged/events/handlers.py` define 5 handlers async sofisticados:
- `on_payroll_closed(db, month, year)` → `auto_build_all_kits`
- `on_cnd_renewed(db, cnd_type, file_path)`
- `on_document_signed(db, document_id, employee_id)`
- `on_employee_allocated / on_employee_deallocated(db, employee_id, post_id)`

**Nenhum deles está inscrito no event-bus** (`core/events/event_bus.py`). O bus exige `subscribe(event_type, handler)` via `EventHandler._register_handlers`; **nenhum módulo GED instancia um EventHandler nem chama `bus.subscribe`** (grep confirmou zero inscrições). Além disso:
- **`payroll_closed` não é publicado por ninguém** (grep em todo `modules/` = 0 publishers). O DP fecha folha e o GED nunca fica sabendo.
- `on_employee_allocated/deallocated` **nunca são chamados** por nenhum código (0 callers fora do próprio arquivo). Alocar/desalocar funcionário NÃO atualiza kits.
- O ÚNICO handler efetivamente acionado é `on_cnd_renewed`, e só via a Celery task `ged.sync_cnds` (`cnd_sync_task.py:133`) — que por sua vez só dispara se um arquivo existir em `/opt/conecta-pro/storage/ged/documents/fiscal/certidoes/*.pdf` (diretório inexistente, ver §3) → **na prática nunca dispara**.
- Existe um `on_document_signed` HOMÔNIMO e DIFERENTE em `integration/events.py:301` (marca payslip/disciplina), exposto em `integration/aggregator.py:239`. **Confusão de nomes**: o do GED recalcula completude do kit; o do integration não toca no GED. Quando o portal assina um documento, o kit do GED **não** é recalculado por evento (só se chamarem o `/sign` do pm-ged diretamente, que aí sim usa `SignatureIntegrationService._update_kit_signed_count`).

**Aresta quebrada nº1 (a mais grave):** toda a "integração bidirecional automática" descrita nas docstrings do GED é teatro — o event-wiring não existe. Kits só se montam quando alguém chama manualmente `POST /people-management/ged/kits/auto-assemble`.

### Tabelas compartilhadas (lê/escreve)
- **Lê:** `employees`, `posts`, `allocations` (via SQL cru em `get_employees_for_client`), `gp_clock_punches` (batidas reais → folha de ponto), `condominios` + `onvio_documents` (match Onvio), `clients` (busca CNPJ na task de certidões), `ged_certidoes`.
- **Escreve:** `ged_document_kits`, `ged_kit_documents`, `ged_certidoes`, `ged_kit_document_access_logs`; arquivos em `/app/uploads/ponto/...`.

### Imports cruzados diretos
- GED → `modules.operacional.models.post.Post` (handler `_get_client_id_from_post`, com try/except ImportError).
- GED → `modules.people_management.ponto.services.folha_pdf_service` (gera folha real).
- GED → `modules.bidding.integrations.receita_federal.*` (CND clients).
- GED → `modules.fiscal.publishers.publish_certidao_renovada`.
- GED → `modules.gdrive.services.email_kit_service` (envio).
- **Quem depende do GED:** praticamente ninguém via import; o frontend depende, mas aponta majoritariamente para o GED LEGADO (`modules.ged`) e para `gedeon`, não para o pm-ged.

### Aresta quebrada nº2 — duas APIs GED sobre as mesmas tabelas
`/ged/*` é servido pelo **GED legado** (`modules/ged/auto_assemble_controller`, `kit_pdf_controller`, `document_controller`), registrado em `main_production.py:629/656/592`. O **pm-ged** (alvo desta auditoria) é registrado em `/people-management/ged/*` (via `modules.people_management` aggregator, linha 1000). Ambos leem/escrevem `ged_document_kits`/`ged_kit_documents`. Consequências verificadas em runtime:
- `GET /api/v1/ged/kits/summary` → respondido pelo **legado** (`auto_assemble_controller.py:136`), retorna `total_kits:8` (só do mês corrente, SQL diferente) e schema diferente (sem `by_status`).
- `GET /api/v1/people-management/ged/kits/summary` → respondido pelo **pm-ged**, retorna 38, schema rico.
- `GET /api/v1/ged/documents/{id}/download` → respondido pelo **legado** (módulo `modules.ged.controllers.document_controller`), retornou 404 mesmo para doc com arquivo válido.
- `GET /api/v1/people-management/ged/documents/{id}/download` → pm-ged, retornou 200 para o mesmo doc.

Dois times de código resolvendo o mesmo problema, com comportamentos divergentes, sob prefixos parecidos. **Risco altíssimo de o frontend chamar o endpoint errado** (já acontece: a tela de kit mistura `kit-real` legado + `download` pm-ged).

---

## 5) BUGS CONCRETOS (file:line + fix)

1. **Download quebrado p/ paths relativos — guard hardcoded** — `ged/controllers/document_controller.py:273-281`.
   ```python
   full_path = doc.file_path
   if not os.path.isabs(doc.file_path):
       full_path = os.path.join(GED_STORAGE_BASE, doc.file_path)  # = /opt/conecta-pro/storage/ged/documents/...
   _base = Path("/app/uploads").resolve()   # ← base ERRADA, não bate com GED_STORAGE_BASE
   if not _target.is_relative_to(_base):
       raise HTTPException(400, "Path de arquivo invalido")
   ```
   Resultado: todos os 346 docs `documents/...` e 44 `/inter/...` → **400**. Confirmado em runtime. **Fix:** alinhar `_base` a `GED_STORAGE_BASE` (ou a um set de bases permitidas `{GED_STORAGE_BASE, "/app/uploads"}`), e garantir que `storage/ged` exista / migrar os paths legados para `/app/uploads`.

2. **`completion_percentage` mede assinatura, não presença de arquivo** — `models/document_kit.py:176` e `services/kit_service.py:327`. `completion = documents_signed/total_documents` com `documents_signed = COUNT(is_signed=true)`. Como contracheque/folha/VT/escala entram `is_signed=False` e certidões entram `is_signed=True` com `file_path=NULL`, a completude **não reflete** "kit pronto p/ enviar". 120 docs NULL+signed inflam; kits 100% preenchidos podem mostrar 0%. **Fix:** definir completude por `COUNT(file_path IS NOT NULL)/total` (cobertura de arquivos) ou separar dois indicadores (cobertura vs. assinatura). Hoje o gate `INV-5` (envio só com 100%) bloqueia indevidamente.

3. **Hash de assinatura não-determinístico** — `signature_integration_service.py:379`. Fallback usa `datetime.utcnow()` no conteúdo do hash quando o arquivo não existe. `verify_signature`/`bulk_check_signatures` recalculam e **sempre acusam integridade inválida**. **Fix:** se não há arquivo, não permitir assinatura (ou hash só do path estável, sem timestamp).

4. **Datas naive em colunas timezone-aware** — `kit_service.py:375,407` (`datetime.utcnow()`) gravando em `DateTime(timezone=True)`. Inconsistente com `kit_controller.py:449` que usa `datetime.now(UTC)`. Risco de offset/compare. **Fix:** padronizar `datetime.now(UTC)`.

5. **ZIP/PDF não acham arquivos abs fora do base** — `export_service.py:98,233`. `os.path.join(GED_STORAGE_BASE, doc.file_path)`: para `/app/uploads/...` o `join` mantém o abs (ok por acaso), mas para `/inter/...` gera `/inter/...` inexistente → placeholder `.txt`. Folhas de ponto reais (em `/app/uploads/ponto`) também só entram porque são abs. Frágil. **Fix:** resolver path com a mesma lógica do download corrigido.

6. **`on_employee_allocated` cria placeholders com path fake** — `events/handlers.py:260`: `file_path=f"documents/dp/{doc_type}/{ref}/{employee_id}.pdf"` (path que não existe), contradizendo a política "placeholder honesto = NULL" adotada no builder. Se o handler fosse acionado, repoluiria o banco com os 404 que o builder evitou. **Fix:** `file_path=None`.

7. **Contador `total_employees` incrementado sem idempotência** — `events/handlers.py:270`: `kit.total_employees += 1` toda vez que o handler roda, mesmo sem adicionar docs (se já existiam). Drift de contador.

8. **Registro espúrio:** a própria empresa ("Conecta Mais", CNPJ 35.710.481) é um `ged_client` → entra no `auto_build_all_kits` como se fosse condomínio.

---

## 6) GAPS DE PRODUÇÃO (o quê / por quê / como)

- **Pipeline de geração de arquivos reais inexistente para 5 dos 6 tipos.** Contracheque, VT/VA/VR, escala = sempre NULL; só folha-de-ponto gera arquivo. **Por quê:** os collectors são honestos mas o DP/Operações não exportam PDFs. **Como:** ligar `collect_payslips` ao `hr_payslips`/serviço de folha real; `collect_schedules` ao export de escala.
- **Event-bus desconectado.** **Como:** num startup hook, instanciar um `EventHandler` do GED que faça `bus.subscribe("payroll.closed", ...)` etc., e publicar `payroll.closed` no fechamento de folha do DP. Sem isso, kits nunca se montam sozinhos.
- **`posts.ged_client_id` zerado (0/12).** **Por quê:** ninguém preenche a FK; só fuzzy-match por nome. **Como:** backfill via match único + UI para vincular posto↔ged_client; o WARN já sinaliza.
- **`storage/ged` ausente + paths legados `documents/...`.** 404 fantasma para 60% dos docs. **Como:** migração de paths para `/app/uploads` + criação do volume, ou re-pointer no banco.
- **Consolidação das duas APIs GED.** Decidir qual `/ged` é canônico e deprecar a outra; hoje há divergência observável de respostas.
- **`source_record_id` nunca preenchido** → sem rastreabilidade real à origem.
- **Sem testes E2E de montagem→download→envio** cobrindo paths relativos.

---

## 7) NOTA DE PRONTIDÃO: **34/100**

Justificativa:
- **+** Modelagem de dados limpa, UNIQUE correta, collectors bem escritos e honestos (NULL em vez de path fake), folha-de-ponto gerada de batidas reais, `_match_onvio` conservador e idempotente, fluxo de envio GDrive+email atômico bem feito, path-traversal *intencionado* (ainda que com base errada).
- **–** Integração automática é fictícia (handlers órfãos, `payroll.closed` sem publisher, alocação não atualiza kit); **–** download falha para 60% dos docs (bug de base); **–** 404 fantasma em 71% dos file_paths persistidos; **–** completude mede a coisa errada e bloqueia envio; **–** hash de assinatura não-determinístico; **–** duas APIs concorrentes sobre as mesmas tabelas com respostas divergentes; **–** FK de escopo zerada (fuzzy-match obrigatório); **–** frontend kit-documental aponta majoritariamente para gedeon/legado, não para o pm-ged auditado.

O núcleo CRUD funciona (kits listam, summary do pm-ged correto, upload/sign manual operam, folha-de-ponto real). Mas como **agregador documental automático** — a razão de existir do módulo — ele não está pronto: nada se agrega por evento, a maioria dos arquivos não baixa, e a completude não significa "pronto".

**Arquivos-chave:** `modules/people_management/ged/events/handlers.py` (órfão), `.../services/kit_builder_service.py` (coleta), `.../controllers/document_controller.py:273` (download bug), `.../services/signature_integration_service.py:379` (hash bug), `.../models/document_kit.py:176` (completude), `main_production.py:629,656,1000` (colisão de rotas `/ged` vs `/people-management/ged`).

---

### ?

I have a complete, evidence-backed picture. Writing the final report.

---

# AUDITORIA PROFUNDA — Backbone de Integração (Event-Bus + Core)
## Conecta PRO / módulo `people_management` + `infrastructure/event_bus`

Auditoria READ-ONLY. Nada foi modificado. Todos os achados verificados em runtime (Redis do container `conecta-pro-backend`) e por leitura de código com file:line.

---

## 1) INVENTÁRIO — a COLA real (não só os nomes)

### 1.1 Existem TRÊS barramentos coexistindo (raiz de quase todos os problemas)

| Bus | Arquivo | Transporte | Dispatch | Status runtime |
|---|---|---|---|---|
| **ConectaEventBus** (oficial) | `infrastructure/event_bus/bus.py` | Redis **Streams** (`xadd`/`xreadgroup`, consumer group `conecta-pro`) | consumer loop `start_consuming` | **VIVO** — iniciado no lifespan (`main_production.py:96-103`) |
| **GPEventBus** (legado GP) | `modules/people_management/core/events/event_bus.py` | Redis **PubSub** (`publish`/`psubscribe`) | `start_listening` | **MORTO** — nunca instanciado nem iniciado; só existe o arquivo |
| **MessageBus** (legado "fase") | `infrastructure/message_bus/bus.py` | in-memory `asyncio.PriorityQueue` | `_process_loop` requer `.start()` | **MORTO-VIVO** — recebe `publish()`, mas `.start()` NUNCA é chamado → mensagens enfileiram e nunca são processadas |

`core/events/__init__.py` faz o aliasing certo (`GPEventBus → ConectaEventBus`, linhas 7-20), MAS `core/events/handlers.py:6` ainda importa `from .event_bus import Event, GPEventBus` — isto é, do arquivo legado `event_bus.py` (o GPEventBus PubSub real, classe diferente do alias). Resultado: `EventHandler` base referencia uma classe de bus diferente da que está em produção. Hoje é inócuo porque ninguém usa `EventHandler`, mas é uma armadilha latente (dois tipos `Event`/`GPEventBus` distintos em memória).

### 1.2 ConectaEventBus — lógica real (boa qualidade, com ressalvas)
- `publish()` (bus.py:386) → roteia por domínio em `_stream_for` (`event_type.split(".")[0]`) → `xadd(stream, maxlen=10000)`. **Não bloqueia** (try/except retorna `False`). Avisa 1x se desconectado (bom anti-flood, bus.py:391-396).
- `start_consuming()` (bus.py:483) → cria consumer group em **todos** os 12 streams, `xreadgroup` com `block=1000 count=50`, dedup por `event_id`, `xack` após dispatch. Wildcards `*`, `.*`, `.**` no `_matches` (bus.py:456).
- **Dedup set `conecta:processed_events`** com TTL 24h aplicado ao SET inteiro (bus.py:539-540) — `expire` no set todo a cada evento ⇒ o set nunca expira de fato enquanto houver tráfego, e quando expira perde TODOS os IDs de uma vez (dedup quebra em janela). Em runtime o set está **vazio** (`scard=0`) — ou expirou em bloco, ou os eventos consumidos foram poucos. Não há `SREM` individual; cresce sem limite real.

### 1.3 Publishers (todos escrevem no ConectaEventBus, todos não-bloqueantes)
- `dp` (hr/publishers.py, 309 linhas): admitido, demitido, férias, folha_fechada, benefício, contrato, holerite, atualizado, ponto_registrado, esocial, atestado.
- `ponto` (ponto/publishers.py): batida_registrada, espelho_fechado, falta_confirmada.
- `sst/saude` (sst/publishers.py): aso_emitido, atestado_registrado, afastamento_iniciado.
- `rh` (human_resources/publishers.py): plano_carreira, milestone, avaliação (criada/concluída/360), onboarding.
- `portal` (employee_portal/publishers.py): ferias_solicitadas, documento_solicitado, **documento_assinado** (event_type literal `"portal.documento.assinado"` — sem constante em `EventTypes`).
- `operacional` (modules/operacional/publishers.py, 16 tipos): ocorrência, escala, cat, banco_horas, disciplinar, alocação, turno, diarista, comunicado, substituição.
- `PublisherMixin` (infrastructure/event_bus/mixins): helper sem boilerplate. Todos publicam OK e estão **efetivamente chamados** pelos controllers (verifiquei: punch_controller, admission_controller, payroll_controller, vacation_controller, shift_controller, occurrence_controller, etc.).

### 1.4 Consumidores reais (subscribers)
Só **DOIS** consumidores existem no bus vivo:
- **GEDEON** (`modules/gedeon/gedeon.py:49-99`): 22 handlers `subscribe(...)`. É o único consumidor de negócio.
- **SOPHIA** (`modules/gedeon/subscribers/sophia_subscriber.py`): 15 patterns wildcard para indexação semântica.

Os **8 "Agents" de people_management** (`agents/dp_agent.py`, `ops_agent`, `ponto_agent`, `sst_agent`, `rh_agent`, `portal_agent`, `ged_agent`, `orchestrator.py`) herdam `BaseAgent`, que subscreve em `_setup()` (base_agent.py:114-115). **Mas nenhum é instanciado em lugar nenhum** (grep confirma 0 instanciações; os `*Agent` instanciados em `empresas/` e `financial/` são outras classes — TaxCalculator, Bookkeeper). → **toda a pasta `agents/` é código morto.**

---

## 2) FRONTEND
Fora de escopo direto (backbone é backend), mas relevante: não há tela de observabilidade do event-bus. `get_stats()`/`get_health()` (bus.py:565-580) existem mas **não há endpoint** que os exponha (grep não achou rota). Logo nenhuma UI mostra streams/lag/handlers. O WhatsApp/portal recebem broadcast via WebSocket (`_broadcast_websocket`) mas só se houver WS registrado — não vi registro de WS para o bus em runtime.

---

## 3) BANCO / RUNTIME DOS STREAMS (evidência coletada ao vivo)

Redis `db1`, consumer group `conecta-pro` (1 consumer, **lag=0, pending=0** em todos os streams → o consumer LÊ e ACK tudo):

```
conecta:stream:dp          15 eventos   last 2026-06-28  (dp.contrato.criado, dp.beneficio.adicionado)
conecta:stream:sistema     32 eventos   last 2026-06-23  (crm.cliente.ativo, crm.contrato.assinado)  ← CRM cai aqui!
conecta:stream:operacional  4 eventos   last 2026-06-23
conecta:stream:saude        3 eventos   last 2026-06-28
conecta:stream:fiscal       3 | ponto 1 | financeiro 3 | rh 2 | ged 2
conecta:processed_events: 0  ← dedup set VAZIO
```

**Achado de ouro:** o stream `ged` tem só 2 eventos `ged.kit.iniciado`, o último de **2026-04-07** (`src=gedeon`), enquanto admissões DP continuaram até **2026-06-28**. GEDEON consome (`lag=0`) mas **não produziu kit novo desde abril** — ou não houve admissão real, ou (mais provável, ver §4) o handler roda mas com payload vazio e não gera efeito visível.

---

## 4) **INTEGRAÇÃO — O GRAFO DE EVENTOS (arestas VIVAS vs MORTAS)**

### 4.1 ARESTAS VIVAS (publisher → consumidor real, no bus rodando)
GEDEON é o único nó-consumidor. Arestas vivas confirmadas (`gedeon.py:55-88`):

| Evento publicado | Publisher | Stream | Consumidor | Viva? |
|---|---|---|---|---|
| `dp.funcionario.admitido` | hr | dp | GEDEON `_on_funcionario_admitido` | **VIVA mas QUEBRADA** (payload, §4.3) |
| `dp.funcionario.demitido` | hr | dp | GEDEON | VIVA/quebrada |
| `dp.atestado.registrado` | hr+sst | dp | GEDEON | VIVA |
| `dp.ferias.aprovadas` | hr | dp | GEDEON | VIVA |
| `dp.folha.fechada` | hr | dp | GEDEON | VIVA |
| `dp.holerite.gerado` | hr | dp | GEDEON | VIVA |
| `operacional.ocorrencia.registrada` | operacional | operacional | GEDEON | VIVA |
| `operacional.escala.publicada` | operacional | operacional | GEDEON | VIVA |
| `operacional.cat.registrada` | operacional | operacional | GEDEON | VIVA |
| `saude.aso.emitido` | sst | saude | GEDEON | VIVA |
| `ponto.espelho.fechado` | ponto | ponto | GEDEON | VIVA |
| `ponto.falta.confirmada` | ponto | ponto | GEDEON | VIVA |
| `fiscal.*`, `financeiro.nota.emitida`, `crm.cliente.ativo`, `crm.contrato.assinado` | — | fiscal/financeiro/**sistema** | GEDEON + SOPHIA | VIVA |
| qualquer `dp.* rh.* ged.* operacional.* fiscal.* financeiro.*` | todos | — | **SOPHIA** (indexação) | VIVA |

### 4.2 ARESTAS MORTAS (publicado SEM consumidor) — a maioria
Eventos publicados que **ninguém** consome (nem GEDEON nem SOPHIA específico). São pura escrita no Redis sem efeito de negócio:

- **Toda família RH**: `rh.plano_carreira.criado`, `rh.milestone.concluido`, `rh.avaliacao_desempenho.criada/concluida`, `rh.onboarding.item_concluido`, `rh.avaliacao_360.*` → só SOPHIA (indexa), **nenhum handler de ação**.
- **Portal**: `portal.ferias.solicitadas`, `portal.documento.solicitado`, `portal.documento.assinado` → **0 consumidores**. Ninguém transforma "férias solicitadas no portal" em fluxo no DP.
- **DP extras**: `dp.beneficio.adicionado`, `dp.contrato.criado`, `dp.ponto.registrado`, `dp.esocial.gerado`, `dp.funcionario.transferido` → **0 consumidores** (os 15 eventos DP no Redis são em maioria benefício/contrato = arestas mortas).
- **Operacional extras**: `operacional.banco_horas.criado`, `medida_disciplinar.criada`, `alocacao.criada`, `turno.iniciado/encerrado`, `ferias.aprovadas`, **toda a família diarista** (`diarista.checkin/checkout/pagamento`), `substituicao.realizada`, `comunicado.publicado` → **0 consumidores**.
- **SST/Saúde**: `saude.afastamento.iniciado`, `saude.epi.entregue`, `saude.treinamento.concluido` (GEDEON subscreve EPI/treinamento mas **ninguém publica** com esses tipos → aresta morta do lado oposto: consumidor sem produtor).
- **Ponto**: `ponto.batida.registrada` → 0 consumidores (espelho/falta sim, batida não).

### 4.3 ARESTAS QUEBRADAS por CONTRATO DE PAYLOAD (bug silencioso, file:line)
GEDEON lê chaves que o publisher **não envia**:
- `_on_funcionario_admitido` lê `p.get("name")` e `p.get("cargo")` (gedeon.py:112,122,123,141), mas o publisher manda **`funcionario_nome`** e `cargo` (hr/publishers.py:31-34). → GEDEON cria kit de admissão com `funcionario=""`, loga "admissão detectada — " (vazio). **Esta é a causa provável do stream `ged` parado desde abril**: o handler roda, mas com dados vazios o efeito é nulo/silencioso.
- `_on_funcionario_demitido` lê `p.get("name")` e `p.get("tipo")` (gedeon.py:162-163); publisher manda `funcionario_nome` e `motivo` (publishers.py:60-62). Mismatch duplo.
- `_on_ferias_aprovadas` lê `p.get("nome")` (gedeon.py:207); publisher manda `funcionario_nome` (publishers.py:91). Mismatch.
- SST `publish_aso_emitido` manda `nome`; `publish_atestado_registrado` manda `nome`+`employee_id`, enquanto DP manda `funcionario_nome`+`funcionario_id`. **Duas convenções de chave** (`nome` vs `funcionario_nome`, `employee_id` vs `funcionario_id`) coexistem no mesmo bus → qualquer consumidor genérico erra.

### 4.4 ARESTAS MORTAS por ROTEAMENTO DE STREAM
`_stream_for` (bus.py:382) usa o 1º segmento como chave de stream. Domínios SEM chave em `STREAMS` caem no fallback `sistema`:
- `crm.*` (5 tipos), `contratos.*`, `licitacoes.*`, `financial.*`, `gedeon.*` → todos no stream **sistema**. Funciona para consumo (o consumer lê `sistema`), mas: (a) mistura tráfego heterogêneo num só stream com `maxlen=10000` compartilhado (risco de truncar eventos importantes), (b) GEDEON subscreve `crm.cliente.ativo` por string e funciona, mas qualquer expectativa de "stream crm" é falsa.

### 4.5 INTEGRAÇÃO PARALELA E DESCONECTADA — `people_management/integration/`
Os 8 "fluxos" bidirecionais (`integration/events.py`: `on_shift_closed`, `on_occurrence_registered`, `on_vacation_approved`, `on_candidate_approved`, `on_document_signed`, `on_termination_initiated`, `on_admission_completed`, `check_mandatory_training`) **NÃO são subscribers do event-bus**. São funções async expostas como **endpoints HTTP manuais** via `integration/aggregator.py` (montado em `api/v1` e `main_production.py:955`). Ou seja: a "integração entre módulos" de verdade exige que alguém chame `POST /integration/...` manualmente. **Nenhum evento do bus aciona esses fluxos.** Vários ainda são stubs (ex.: `on_termination_initiated` e `on_admission_completed` só logam e retornam `status=processed` sem desalocar nada — events.py:380-394, 419-430). `on_vacation_approved` instancia `ScaleOptimizerAI()` e **descarta** o resultado (events.py:172).

### 4.6 TERCEIRA INTEGRAÇÃO MORTA — legacy MessageBus
`health_occupational/__init__.py:131-134` chama `register_hr_event_subscribers()` no import → registra handlers (`FUNCIONARIO_ADMITIDO`, `FUNCIONARIO_DEMITIDO`, `fase2.funcionario.*`) no **MessageBus in-memory**. `hr/services/employee_service.py:186-204` publica via `publish_event` nesse mesmo MessageBus. **MAS** o MessageBus dispara handlers só pelo `_process_loop` (`while self._running`), e `.start()` **nunca é chamado** no startup (grep confirma). → admissão publica no MessageBus, a mensagem entra na `PriorityQueue` e **nunca é processada**; o subscriber de health_occupational **nunca dispara**. Inteira aresta DP→SST via legacy = morta.

---

## 5) BUGS CONCRETOS (file:line + fix)

1. **Payload contract mismatch GEDEON↔DP** — `modules/gedeon/gedeon.py:112,122,141,162,207`. GEDEON lê `name`/`nome`/`tipo`; publishers enviam `funcionario_nome`/`motivo`. **Fix:** padronizar a chave (`funcionario_nome`) em ambos os lados ou ler `p.get("funcionario_nome") or p.get("name")`. Sem isso GEDEON monta kits sem identificar o funcionário (causa provável do stream `ged` morto desde 2026-04-07).

2. **`handlers.py` importa o bus errado** — `modules/people_management/core/events/handlers.py:6` `from .event_bus import Event, GPEventBus` puxa o **GPEventBus PubSub legado** (classe distinta do alias em `__init__.py`). **Fix:** `from infrastructure.event_bus import event_bus as _bus, ConectaEvent as Event` ou importar do `__init__` (que já reexporta o alias).

3. **MessageBus legado nunca iniciado** — `infrastructure/message_bus/bus.py` (`.start()` ausente no lifespan). Subscribers de `health_occupational` registram mas nunca disparam; `employee_service` publica para o nada. **Fix:** ou iniciar o MessageBus no lifespan, ou (melhor) **migrar `employee_service` e `health_occupational/hr_events` para o ConectaEventBus** e deletar o MessageBus.

4. **Dedup set sem expiração efetiva / sem SREM** — `bus.py:536-540`. `EXPIRE` é re-aplicado no SET inteiro a cada evento → nunca expira sob carga; quando expira, perde todos os IDs de uma vez. **Fix:** usar chave por evento `SET conecta:dedup:{event_id} 1 EX 86400 NX` (TTL por item), não um SET global.

5. **`agents/` é código morto** — `modules/people_management/agents/*` (8 agents + orchestrator) nunca instanciados. Subscrições em `base_agent.py:114` jamais ocorrem. **Fix:** ou wire um `init_agents()` no lifespan, ou **deletar** (49k+ linhas de superfície morta, como já aconteceu com Guardian).

6. **SOPHIA `_sync_callback` usa `get_event_loop()`** — `sophia_subscriber.py:241`. `asyncio.get_event_loop()` é deprecado e, fora de coroutine, levanta. Como o dispatch do bus já é async (`_dispatch` chama handler com `await` se for coroutine), envolver em callback síncrono + `ensure_future` é frágil. **Fix:** registrar `processar_evento_sophia` (coroutine) diretamente — o bus já suporta handlers async (`bus.py:472`).

7. **`portal.documento.assinado` sem constante** — `employee_portal/publishers.py:74` usa string literal; não está em `EventTypes`. Inconsistência que esconde typos. **Fix:** adicionar `PORTAL_DOCUMENTO_ASSINADO` em `EventTypes`.

8. **Fallback de stream esconde domínios reais** — `crm/contratos/licitacoes/financial` → `sistema`. **Fix:** adicionar essas chaves a `STREAMS` para isolamento e maxlen independente.

---

## 6) GAPS DE PRODUÇÃO (o quê / por quê / como)

- **Sem DLQ / retry real no ConectaEventBus.** Handler que lança é só logado (`bus.py:476-479`) e a mensagem é **ACKada mesmo assim** (xack após dispatch, sem checar sucesso) → evento perdido em falha. *Como:* não ackar em exceção; usar `XPENDING`/`XCLAIM` ou DLQ stream.
- **Idempotência frágil** (bug #4): risco de reprocessamento e de não-dedup.
- **Sem observabilidade exposta:** `get_health/get_stats` existem mas sem rota; nenhuma métrica de lag/erro/handler. *Como:* endpoint `/admin/eventbus/health` + alerta de lag.
- **Três buses, dois mortos:** dívida técnica severa. A "cola" real é só GEDEON+SOPHIA sobre o ConectaEventBus; o resto é teatro de eventos.
- **Maioria das arestas mortas:** ~70% dos event_types publicados não têm consumidor. Publicar custa I/O Redis sem ROI. *Como:* ou criar handlers (RH→onboarding, portal→DP, diarista→financeiro), ou parar de publicar.
- **Integração "bidirecional" é manual via HTTP** (§4.5), com stubs. O ERP não auto-reage a admissão/rescisão/férias — depende de chamada externa ao `/integration/...`.
- **Contrato de payload não tipado:** dois dicionários soltos com chaves divergentes (`nome` vs `funcionario_nome`). *Como:* dataclasses/Pydantic por event_type, validadas no publish.

---

## 7) NOTA DE PRONTIDÃO: **34/100**

Justificativa:
- **+** O backbone escolhido (ConectaEventBus / Redis Streams) é tecnicamente sólido: persistência, consumer group, dedup, wildcards, não-bloqueante, anti-flood. Está **vivo e consumindo** (lag=0 confirmado em runtime). Publishers bem espalhados e efetivamente chamados.
- **−** É uma **cola que liga quase nada**: só GEDEON+SOPHIA consomem; ~70% dos eventos são arestas mortas. As 3 arestas vivas de maior valor (admissão/demissão/férias → GEDEON) estão **quebradas por mismatch de payload** (stream `ged` parado desde abril). Há **dois buses legados mortos** (GPEventBus PubSub e MessageBus in-memory sem `.start()`), com subscribers de `health_occupational` que nunca disparam. Os 8 Agents e a `integration/` "bidirecional" são código morto / endpoints manuais com stubs. Dedup e DLQ têm defeitos que causam perda/reprocesso de eventos.

Para chegar a ~75%: corrigir contratos de payload (#1), unificar para um único bus e deletar os dois mortos (#2,#3,#5), corrigir dedup/ack (#4 + não-ack em falha), e converter ao menos 4-5 arestas mortas de alto valor (portal→DP, RH→onboarding, demissão→desalocação) em handlers reais.

---

### Arquivos-chave (caminhos absolutos)
- `/opt/conecta-pro/backend/infrastructure/event_bus/bus.py` (bus oficial vivo)
- `/opt/conecta-pro/backend/modules/people_management/core/events/event_bus.py` (GPEventBus legado MORTO) + `handlers.py` (import errado) + `event_types.py`
- `/opt/conecta-pro/backend/infrastructure/message_bus/bus.py` (MessageBus legado MORTO-VIVO)
- `/opt/conecta-pro/backend/modules/gedeon/gedeon.py` (único consumidor de negócio; payload bug)
- `/opt/conecta-pro/backend/modules/gedeon/subscribers/sophia_subscriber.py` (indexação; get_event_loop frágil)
- `/opt/conecta-pro/backend/modules/people_management/integration/{events,aggregator}.py` (integração HTTP manual, stubs)
- `/opt/conecta-pro/backend/modules/people_management/agents/*` (8 agents — código morto)
- Publishers: `.../{hr,human_resources,ponto,sst,employee_portal}/publishers.py` e `/opt/conecta-pro/backend/modules/operacional/publishers.py`
- `/opt/conecta-pro/backend/main_production.py:90-116` (lifespan: inicia ConectaEventBus + GEDEON; NÃO inicia MessageBus nem Agents)

---
