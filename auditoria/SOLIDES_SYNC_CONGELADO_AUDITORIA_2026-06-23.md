# Auditoria: por que o sync Sólides congelou — READ-ONLY

**Data:** 2026-06-23 · **Escopo:** integração Sólides/Tangerino. **Read-only** (nenhuma escrita; só GETs de teste à API, sem persistir). **§13.1/§13.4.**

---

## VEREDITO
**Não é infra nem credencial — é lógica da task.** O sync agendado roda a cada 15 min, reporta `completed / 40 created`, mas com **`api_requests=0`**: ele **propaga os 44 funcionários CACHEADOS (congelados em 18/jan)** sem buscar dados frescos do Tangerino. Resultado: "verde mas morto".

## O que foi DESCARTADO como causa (com evidência)
| Hipótese | Resultado |
|---|---|
| Token ausente | ❌ `SOLIDES_API_TOKEN` **presente** (88 chars) em celery-integrations + backend (onde a task roda). Ausente só no celery-beat (mas beat só agenda). |
| Sem internet | ❌ container alcança `google.com` (HTTP 200). |
| Host fora do ar | ❌ `employer.tangerino.com.br` responde (401 na raiz, 404 em paths) — vivo. |
| Token expirado/inválido | ⚠️ não confirmado contra o path real (paths testados deram 404 por serem chute meu), mas o host autentica. |
| Conflitos bloqueando | ❌ `solides_sync_conflict = 0`. |

## CAUSA-RAIZ (lógica)
1. **A task lê o token de `os.getenv("SOLIDES_API_TOKEN")`** (tasks.py:404/494/572), **não** da tabela `solides_credential` — que tem o token criptografado mas `last_used_at=None` (**o caminho da tabela nunca foi usado**).
2. O contador `created` vem de `ret["propagation"]["propagated"]` (tasks.py:83) → **"40 created" = 40 funcionários re-propagados do CACHE** (os 44 `solides_employees`), não buscados da API. Por isso `api_requests=0`.
3. O `fetch_entities` ou não roda, ou **falha silenciosamente** (try/except em tasks.py:57 loga `error` e **continua** o loop sem contabilizar) → o sync segue, propaga cache e marca `completed`.
4. **Config inconsistente:** `solides_integration_config` tem **2 linhas** (uma com `base_url`, outra com `url=None`); `sync_entities=None`; `is_connected=True` mas `last_health_check_at=None` (health check **nunca rodou** — flag estática); `last_incremental_sync_at=None`.

## Cronologia do congelamento
- **18/jan:** último webhook real do Sólides + `solides_employees.updated_at` máx. → última entrada de dado fresco.
- **15/mar:** `solides_entity_mapping` máx. → última atualização de mapping.
- **30/mar:** `gp_clock_punches` (ponto nativo) parou.
- **Desde então:** sync roda a cada 15 min propagando cache, sem fetch real.

## Arquitetura (recap do laudo anterior)
- Sólides/Tangerino → Conecta puxa `employees, job_roles, workplaces, work_schedules` (**não** batidas).
- Conecta → Sólides empurra batidas (`push_punch_as_occurrence`) — **nunca rodou** (`solides_occurrences=0`).

## RECOMENDAÇÃO (próximo passo — precisa de autorização, pois ESCREVE)
1. **Rodar 1 sync incremental manualmente com trace** (`sync_solides_incremental`) e observar `fetch_entities` chamar o Tangerino: ver HTTP real (200 com dados? 401? schema mudou?). Isso confirma se o fetch funciona e por que está silencioso. **É ação (grava se funcionar)** → seu OK.
2. **Limpar config duplicada:** decidir qual das 2 linhas de `solides_integration_config` é canônica; preencher `sync_entities`.
3. **Health check real:** rodar `solides.health_check` (hoje nunca rodou — `is_connected=True` é fantasma).
4. **Corrigir o contador enganoso:** `items_created`/`api_requests` deveriam refletir fetch real, não propagação de cache (senão o log "verde" sempre mente). Tech-debt.
5. **Decidir a fonte do ponto:** se as batidas devem vir do Tangerino, é **feature nova** (o pull de ponto não existe — só employees/roles/workplaces/schedules).

> Nada foi alterado. Os testes à API foram GET read-only sem persistência. O passo 1 (sync com trace) é o que fecha o diagnóstico — aguarda seu OK por gravar dados.

---

## ⚠️ CORREÇÃO (teste real com trace — autorizado por Jordan)
O teste ao vivo **corrigiu o veredito** "verde mas morto":
- **Fetch funciona:** `GET employer.tangerino.com.br/employee/find-all` → **HTTP 200**, retornou **47 funcionários reais**.
- **Persiste de verdade:** `_propagate_employees_to_db` fez **UPDATE em 40 employees ativos (rowcount>0) + commit**. Os campos (nome, cargo, data_admissao, pis, escala...) SÃO atualizados.
- **O que me enganou:** o UPDATE **não seta `updated_at`** (máx fica 06/mai) e a tabela-espelho `solides_employees` é escrita por outro caminho (congelada em jan) — mas a tabela **operacional `employees` É atualizada**.

### Buracos REAIS (priorizados)
1. **UPDATE-only, sem INSERT** → Sólides tem 47 ativos, só 40 casam por CPF; **7 não entram** (novos contratados ficam fora). **Causa principal da "lista desatualizada".**
2. **Não bumpa `updated_at`** → parece congelado, não-auditável.
3. **Não atualiza `solides_employees`/`entity_mapping`** (espelho stale).
4. **Ponto não vem do Sólides** (push, não pull) + captura nativa parou 30/mar.

### Ação executada
- Rodado `sync_solides_incremental` p/ condominio `615bbcf6-...` → 40 employees atualizados (persistido). Backup pré: `backups/postgresql/PRE_SOLIDES_SYNC_20260623_125303.dump`.

### Recomendação de fix (para 24/7 confiável)
- **A) Adicionar INSERT de novos** no `_propagate_employees_to_db` (criar employee quando CPF não existe) — resolve os 7 + futuros contratados.
- **B) Setar `updated_at = now()`** no UPDATE — auditabilidade.
- **C) Investigar os 7 not_found** (são novos? CPF com formato diferente? inativos no Conecta?).
- **D) Ponto:** decisão à parte (pull do Tangerino = feature nova, ou consertar captura nativa).

---

## ✅ FIX A+B APLICADO E VALIDADO (2026-06-23)
### Investigação dos 7 not_found (read-only)
- **6 NOVOS contratados** (CPF inexistente no Conecta): JEOVANE, MEIRE GABRIELA, SEBASTIAO, JONILSON, FERNANDO MIGUEL, MATHEUS HENRIQUE.
- **1 (ARYELTON BRAGA FIGUEIRA)** existe mas `inativo` no Conecta, ativo no Sólides → caso de reativação. **NÃO reativado automaticamente** (decisão manual do Jordan).

### Fixes (em `connectors/solides/tasks.py::_propagate_employees_to_db`)
- **Fix A:** quando o UPDATE não casa e o CPF não existe → **INSERT** funcionário ativo com nome/cpf/cargo/escala/pis/admissão/solides_id. Se existe inativo → não insere (evita CPF duplicado).
- **Fix B:** UPDATE agora seta `updated_at = NOW()`.

### Resultado em produção (validado §13.4)
- **6 novos funcionários criados** (status ativo, com cargo/escala/solides_id/admissão reais).
- **Fix B:** `updated_at` bumpou hoje em 46/64 (40 atualizados + 6 criados).
- **employees: 58 → 64** (46 ativos, vs 47 ativos no Sólides — diferença = Aryelton inativo).
- **Zero CPF duplicado.** Sintaxe OK. Backup pré: `PRE_SOLIDES_SYNC_20260623_125303.dump`.
- Commit `d90e5d46` (pushado, branch fix/crm-qa-aprovado-20260614).

### ⚠️ Correção ao CLAUDE.md (B.3.1)
Descoberto: `/app/modules` está **bind-mounted do host** nos containers celery (mtime host==container). O edit ficou live sem hot-copy explícito, e o worker do beat pegou o código novo (recycle de child). **B.3.1 diz que o código é "baked, precisa hot-copy"** — para os celery workers de código Python isso parece NÃO ser verdade (é mount). Vale revisar o CLAUDE.md.

### Pendências
- **Aryelton:** decidir reativação (inativo no Conecta, ativo no Sólides).
- **Contador do sync_log:** `items_created` ainda reflete só `propagated` (updated), não inclui os `created` (INSERTs) — cosmético, corrigir depois.
- **solides_employees/entity_mapping:** espelho ainda stale (caminho separado; o sync operacional usa employees direto, então não bloqueia uso).
- **Ponto:** captura nativa parada 30/mar + decisão pull-do-Tangerino (feature nova) — assunto à parte.

---

## RESOLUÇÃO #3 + status #2 (2026-06-23)

### Aryelton — esclarecido
Contrato **suspenso** → sem atualizações é o comportamento correto. Segue inativo, sem ação. ✅

### #3a — contador do sync_log: RESOLVIDO ✅
`_log_sync_end` agora distingue `items_created` (INSERTs) de `items_updated` (UPDATEs).
Validado: `proc=47 created=0 updated=46` (antes mentia "created=40"). Commit `f2198372` (pushado).

### #3b — espelho `solides_employees` stale: ACOPLADO AO #2
- O espelho mapeia `solides_id ↔ employee_id`; é lido por ponto dashboard + punch_service + vacation_service.
- É alimentado por **webhooks** (parados 18/jan), **não** pelo sync incremental.
- Só importa quando o **ponto voltar a fluir** (= #2). Decisão na hora do #2: refrescar o espelho OU apontar os serviços de ponto para ler `solides_id` direto de `employees` (que agora está fresco — fonte única). Não construído agora (§13.2: evitar complexidade em caminho dormente).

### #2 — Ponto: É FEATURE NOVA, precisa de decisão/insumo
- Captura nativa (`gp_clock_punches`, web/facial) parou **30/mar**.
- O connector **não tem endpoint de batida**; probe ao Tangerino: `/time-clock` e `/marking` deram **HTTP 502** (existem mas erro de upstream/params), resto 404. **Não dá pra confirmar/implementar o pull sem a documentação da API Tangerino.**
- **Duas opções (decisão do Jordan):**
  - **A) Pull do Tangerino** (alinha com "batidas vêm do Sólides"): requer a **doc da API Tangerino** (endpoint de batidas + auth/params) → aí implemento fetch → `gp_clock_punches`.
  - **B) Consertar captura nativa**: investigar por que o app/posto parou de enviar batidas em 30/mar (frontend? device? endpoint de ingestão?).
- **Bloqueado** até: (A) você fornecer/apontar a doc do Tangerino, ou (B) autorizar a investigação da captura nativa.

---

## #2 — Captura nativa parou 30/mar: CAUSA IDENTIFICADA (uso migrou, não quebrou)
- **30/mar/2026:** landou a integração bidirecional Sólides/Tangerino (commits `aeea43b9`, `30f94884`).
- **30/mar:** as batidas nativas pararam **no mesmo dia** (última 30/mar 23:32). 1830 batidas reais (43 funcionários) de 1-30/mar = piloto de ponto nativo.
- Endpoints nativos **funcionam** (`/ponto/batida`=422, `/batida/me`=401 — vivos). `registrar_batida` empurra pro Sólides (`_push_punch_to_solides`).
- **Conclusão:** o **Tangerino virou o sistema-de-registro do ponto**; o piloto nativo foi descontinuado em 30/mar. Bidirecional previsto, mas só o push existe (e nem roda: `solides_occurrences=0`); **pull do Tangerino nunca foi construído**.

### Decisão #2 fechada
- **Opção B (consertar nativo): DESCARTADA** — nada quebrado; funcionários batem no Tangerino, não no Conecta.
- **Opção A (pull do Tangerino): único caminho** → requer a **documentação da API Tangerino** (endpoint de batidas; `/time-clock` e `/marking` deram 502 no probe). Bloqueado até a doc.

### Pergunta de negócio a confirmar (Jordan)
Confirmar que hoje os funcionários **batem ponto no Tangerino** (app/dispositivo próprio), não no Conecta. Se sim, Opção A é o caminho e preciso da doc da API Tangerino para implementar o pull batidas→`gp_clock_punches`.
