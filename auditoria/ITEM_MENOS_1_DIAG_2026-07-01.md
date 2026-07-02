# ITEM −1 · FASE A — DIAGNÓSTICO READ-ONLY (motores + event-buses de GP)
**Token:** STEP-0-ITEM-MENOS-1-DIAG · **Data:** 2026-07-01 · **Modo:** 100% read-only (nada escrito/morto/commitado)
**Missão:** provar quantos motores de cálculo e quantos event-buses REALMENTE existem, quem chama cada um, e qual é o correto — pra Jordan aprovar a consolidação (FASE B).

> ⚠️ Este diagnóstico **confirma**, **refuta** e **refina** a hipótese da auditoria. Duas correções evitam erro destrutivo na FASE B — ver §4.

---

## STEP 0 — ESTADO
- **git branch:** `fix/crm-qa-aprovado-20260614`
- **working tree:** SUJO — **356 arquivos** (majoritariamente `agents/cto/memory/snapshots/*` deletados + `CLAUDE.md` modificado). É **resíduo de sessão anterior, não desta FASE A.** Read-only não adicionou nada. ⚠️ Recomendo `git stash`/limpeza consciente antes da FASE B, pra não misturar com a consolidação.
- Read-only confirmado: só `grep`/`sed`/`ls`/`psql SELECT`. Nenhuma escrita.

---

## STEP 1 — MOTORES DE CÁLCULO DE FOLHA

### Motores encontrados (evidência arquivo:linha)
| # | Motor | Arquivo:linha | Tabela/base | Estado |
|---|---|---|---|---|
| **M1** | `calculo_service` (funções soltas) | `people_management/folha/services/calculo_service.py:55,69,80` | **LÊ dados importados** (`hr_payslips`), guard *"Sistema B: sem dados importados — NUNCA recalcular"* (linha 438) | **VIVO** |
| **M2** | `clt_calculator` (biblioteca legal completa) | `people_management/common/utils/clt_calculator.py:47,73,263,325…` | Cabeçalho diz **"2026"** mas valores são **2024**: `SALARIO_MINIMO 1412.00`, `TETO_INSS 7786.02` (l.16-19) | **VIVO** (via M3) |
| **M3** | `PayrollService` | `people_management/hr/services/payroll_service.py:49,59` | **usa M2** (`import calcular_inss/irrf/fgts_mensal`, l.17-25; chama l.134-135) | **VIVO** |
| M4 | `PayrollSkill` (agents/dp) | `people_management/agents/dp_agent.py:22,43,58,66` | Própria tabela "INSS 2026 (simplificada)" = mesmos valores 2024 (l.25-30) | **ÓRFÃO** (só self-register l.294 + teste) |
| M5 | `PayrollSkill` (hr/skills) | `people_management/hr/skills/payroll_skill.py:17` | sem tabela (mensagens) | **ÓRFÃO** (só `hr/skills/__init__.py:6`) |
| M6 | `cct_service.calcular_rescisao` | `people_management/cct/services/cct_service.py:162` | CCT (rescisão) | caminho de rescisão separado |
| M7 | `PayrollService` (módulo legado) | ref. em `hr/services/payroll_service.py:34` → `modules/hr/payroll_integration/services` | pré-reorg (fora de people_management) | referência aninhada — a confirmar |

### Veredito STEP 1 — **há motor duplicado, SIM, mas não como a auditoria teorizou**
- **Dois motores VIVOS calculam folha, por rotas diferentes:**
  - **M1** serve `/folha/*` e é o **correto por design** — ele **defere à Domínio** (lê `hr_payslips`, nunca recalcula quando há dado). É o que respeita o golden set.
  - **M3→M2** serve `/payroll/*` e **RECALCULA** com a biblioteca `clt_calculator`, cujas tabelas estão **rotuladas "2026" mas com valores 2024** (1412/7786.02 — nem 2025, que foi 1518/8157,41).
- **Correção à hipótese:** não é "motor A CCT-2026 correto vs motor B INSS-2024 errado". É **"M1 lê Domínio (seguro) vs M3 recalcula com tabela defasada e mal-rotulada"**. **Nenhum dos dois é um motor 2026 correto de verdade** — M1 acerta porque copia a Domínio; M2 precisa das tabelas 2026 reais (item −0.5, referência legal certificada).
- **2 motores órfãos** (M4, M5) no framework de agents — candidatos a quarentena, aparentemente sem rota viva.

---

## STEP 2 — QUEM CHAMA CADA MOTOR
| Motor | Chamadores (arquivo:linha) | Rota/Tela |
|---|---|---|
| **M1** `calculo_service` | `folha/controllers/folha_controller.py:42,59,82,98,115,128,160` | **`/folha/*`** (dashboard, colaborador, batch, resumo, rubricas) |
| **M3** `PayrollService` | `hr/controllers/payroll_controller.py:137` + `hr/controllers/payroll_export_controller.py:47,101,149` | **`/payroll/*`** (cálculo + export) |
| **M2** `clt_calculator` | `hr/services/payroll_service.py:17-25` (+ testes) | indireto, via M3 |
| M4 `PayrollSkill`(dp) | `dp_agent.py:294` (self) + teste | **sem controller** → órfão |
| M5 `PayrollSkill`(hr) | `hr/skills/__init__.py:6` | **sem controller** → órfão |

### Veredito STEP 2
- **`/folha/*` (M1) e `/payroll/*` (M3) são DUAS rotas vivas do mesmo domínio** → split-brain **CONFIRMADO**. Duas telas de DP/Folha podem mostrar números diferentes (M1 = Domínio; M3 = recálculo defasado).
- Os motores errados (M4, M5) parecem **órfãos** (sem chamador de rota) → seguros pra quarentena **após confirmação** de que nenhum boot/agents-orchestrator os aciona (resíduo §5).
- **M2 (`clt_calculator`) NÃO deve ser morto** — é a biblioteca legal (rescisão, férias, 13º, noturno, DSR, insalubridade). Ela precisa das **tabelas 2026 corretas**, não ser eliminada.

---

## STEP 3 — EVENT-BUSES

### Mecanismos encontrados
| Bus | Arquivo | Estado |
|---|---|---|
| **ConectaEventBus** (Redis Streams) | `infrastructure/event_bus/bus.py:314` | **VIVO** (GEDEON/SOPHIA consomem) |
| **MessageBus** (in-memory) | `infrastructure/message_bus/bus.py:263` | usado p/ publicar em `message_bus/events.py:249,286,323`; **consumer-start não confirmado** (resíduo §5) |
| ~~GPEventBus~~ | `people_management/core/events/__init__.py:11`: **`ConectaEventBus as GPEventBus`** | **É ALIAS de ConectaEventBus**, não bus separado |

### 🔴 Correção crítica à hipótese (evita erro destrutivo na FASE B)
A auditoria (e o rascunho v2 do spec) mandava **"deletar GPEventBus, o bus morto"**. **ERRADO:** `GPEventBus` é um **alias retrocompatível de `ConectaEventBus`** (`core/events/__init__.py:11`). **Deletar "GPEventBus" = deletar o bus VIVO.** `handlers.py:6` e `base_agent.py:22` importam esse alias — eles estão no bus vivo, não num morto.

### Split-brain REAL de eventos: duas tabelas de EventTypes
| Registro | Arquivo:linha | String | Uso |
|---|---|---|---|
| Infra (vivo) | `infrastructure/event_bus/bus.py:207` | `DP_FUNCIONARIO_ADMITIDO = "dp.funcionario.admitido"` | **usado por publisher E GEDEON** |
| people_management (paralelo) | `core/events/event_types.py:36` | `FUNCIONARIO_ADMITIDO = "gp.funcionario.admitido"` | aparentemente órfão |
→ **O split real não é "3 buses"; é UM bus vivo (ConectaEventBus) + MessageBus + duas tabelas de constantes (`dp.*` viva, `gp.*` paralela).**

### A aresta admissão → GEDEON (o achado #1 da auditoria) — VERDADE precisa
- **Tópico BATE:** publisher (`hr/publishers.py:13`) e GEDEON (`gedeon.py:55`) usam a **mesma** constante `DP_FUNCIONARIO_ADMITIDO = "dp.funcionario.admitido"`. → **a teoria de "bus/tópico divergente" está REFUTADA para esta aresta.**
- **Payload NÃO bate — CONFIRMADO:** publisher envia `payload={"funcionario_nome": …, "cargo":…, "data_admissao":…}` (`hr/publishers.py:31-37`); GEDEON lê **`p.get("name","")`** (`gedeon.py:113,122`) — chave **`name` que o publisher NUNCA envia**. → kit montado com **funcionário vazio**.
- **Segundo bloqueio:** `gedeon.py:115` `if cliente_id:` — só monta o kit se `cliente_id` vier no evento; `publish_funcionario_admitido` tem `cliente_id=None` por padrão. Se o `admission_controller` não passar, o bloco inteiro é pulado.

### Veredito STEP 3
- **1 bus vivo** (ConectaEventBus, alias GPEventBus) + **1 in-memory** (MessageBus, consumer duvidoso) + **2 registros de EventTypes** (dp.* vivo / gp.* paralelo).
- A aresta admissão→GEDEON morre por **payload (`name` vs `funcionario_nome`) + `cliente_id` ausente**, **não** por bus/tópico.

---

## STEP 4 — PLANO DE CONSOLIDAÇÃO PROPOSTO (NÃO EXECUTADO — aguarda seu aval)

### Motores
1. **Eleger M1 (`calculo_service`, lê Domínio) como fonte da folha mensal** servida ao usuário. Migrar as telas de `/payroll/*` (M3) para consumir M1 **ou** reduzir M3 a exportação/recálculo-de-conferência (não fonte da verdade exibida).
2. **NÃO matar M2 (`clt_calculator`)** — corrigir suas tabelas para **2026 reais** via item −0.5 (referência legal certificada). Ele é o motor legal de rescisão/férias/13º.
3. **Quarentenar M4, M5** (agents órfãos) — **após** confirmar no boot que nenhum orchestrator os aciona (§5). §13.6: quarentena, não delete.
4. Confirmar/resolver M7 (PayrollService legado em `modules/hr/`).

### Buses
5. **Eleger ConectaEventBus** (já é o vivo). **NÃO "deletar GPEventBus"** — é alias; no máximo, remover o alias e reapontar imports para o nome canônico, com cuidado.
6. **Unificar as duas tabelas de EventTypes** — aposentar `gp.*` (people_management/core/events/event_types.py) em favor de `dp.*` (infra), OU vice-versa; hoje coexistem.
7. **MessageBus:** confirmar se tem consumer rodando; se não, quarentenar (é a terceira via de evento que a auditoria diz morta).
8. A aresta admissão→GEDEON (payload `name`→`funcionario_nome` + garantir `cliente_id`) é **correção de módulo (Fase 1/A1 da síntese)**, não de arquitetura — sai do escopo do Item −1, mas fica registrada.

### RISCO de cada correção
| Ação | Risco | Mitigação |
|---|---|---|
| Migrar `/payroll/*`→M1 | telas de DP que usam `/payroll` mudam de número (passam a refletir Domínio) | é o efeito desejado; validar com gate "dois endpoints, um valor" |
| Remover alias GPEventBus | **quebra `handlers.py`, `base_agent.py`, `gp_websocket.py`** se feito sem reapontar | reapontar imports antes; ou manter o alias (baixo custo) |
| Quarentenar M4/M5 | se um agents-orchestrator os aciona no boot, quebra | confirmar boot (§5) antes |
| Corrigir tabelas M2 | rescisão/férias mudam de valor | **exige item −0.5 + certificação humana** (não é auto-verde) |

---

## §5 — RESÍDUOS DE FASE A (o que NÃO confirmei — honestidade)
1. **MessageBus tem consumer iniciado no boot?** (grep achou `get_message_bus()` publicando, não achei `.start()` de consumer). Decide se é morto ou vivo.
2. **O agents-orchestrator (`people_management/agents/orchestrator.py`) é instanciado no startup?** Se sim, M4/M5 e os subscribers de agents estão vivos; se não, órfãos. Decide a quarentena.
3. **Registro `gp.*` EventTypes** é 100% órfão? (achei o `dp.*` em uso; não exaurí os usos de `gp.*`).
4. **M7** (`modules/hr/payroll_integration`) — é um 3º PayrollService real ou import morto?
5. **Payload das outras arestas** (demitido, férias, folha_fechada) — confirmei só admitido; a síntese alega mismatch nas demais.

Esses 5 são baratos de fechar e não bloqueiam sua decisão sobre motores/buses.

---

## §5 — RESOLVIDO (2026-07-01, 2ª passada read-only)
1. **MessageBus:** nenhum `.start()` de consumer é chamado (só em docstring, `bus.py:275`); nada fora de `message_bus/events.py` consome. → **morto pra consumo** (publica no vácuo). Confirma a auditoria. Seguro quarentenar.
2. **Agents-orchestrator (people_management):** **NÃO sobe no boot.** `main_production.py:113` só chama `gedeon.registrar_subscribers()` — GEDEON vivo. Nenhum `Orchestrator()` de people_management no lifespan. → **M4, M5 e `ops_agent` são órfãos em produção.** Seguro quarentenar.
3. **`gp.*` EventTypes** (`core/events/event_types.py`): usado **só** por `agents/ops_agent.py:143-156` (`GPEventTypes.*`), que é órfão (item 2). → **órfão-em-produção**, mas remover exige tocar/quarentenar os agents antes.
4. **M7 (`modules/hr/payroll_integration`):** é módulo de **configs de integração** (`hr_payroll_integrations`, migration sprint20), **não um 3º motor de cálculo**. Referência aninhada em `payroll_service.py:34` como fallback. Fora do escopo de "motor duplo".
5. **Payload das outras arestas — mismatch sistêmico CONFIRMADO:**
   - **demitido:** envia `funcionario_nome`/`motivo` (publishers.py:61-62); GEDEON lê `name`/`tipo` (→ vazio).
   - **férias:** envia `funcionario_nome` (publishers.py:91); GEDEON lê `nome` (→ vazio).
   - **folha_fechada:** `total_funcionarios` **bate**, mas gated em `cliente_id` + `competencia` no payload.
   - **Causa-raiz única:** handlers do GEDEON leem chaves (`name`/`nome`/`tipo`) que os publishers nunca enviam. **Uma correção de convenção revive todas** (Fase 1/A1, fora do Item −1).

---

## NOTA DE COMPLETUDE DO DIAGNÓSTICO: **9.5 / 10** (após §5 resolvido)
**Era 8.5 / 10:**
Motores vivos + chamadores + rotas: mapeados com evidência (STEP 1-2 sólidos). Buses: mecanismos e a aresta #1 cravados, com 2 correções à hipótese. Faltou fechar os 5 resíduos do §5 (boot do MessageBus/orchestrator, órfãos), que são confirmações de boot — não mudam o desenho da consolidação, só o gatilho da quarentena.

**PARE AQUI.** Mapa + plano entregues. Aguardando seu aval (ou ajuste) antes da FASE B.
