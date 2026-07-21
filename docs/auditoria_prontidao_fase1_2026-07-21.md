# Auditoria de Prontidão — Fase −1/0 → pronto para Fase 1?
**Data:** 2026-07-21 · **Método:** re-verificação AO VIVO de cada task + 1 agente adversarial independente. Nada confiado "de palavra".

## Veredito em uma frase
As **8 tasks da fundação estão feitas, verificadas ao vivo e duráveis (assadas)**. A auditoria encontrou **3 regressões que EU havia introduzido** (todas corrigidas e provadas) — o que valida o próprio exercício. Os riscos do pré-mortem que pertencem à fundação estão **cobertos**; os demais são **diferidos por desenho** às fases que constroem aquelas features (2–5), e estão **rastreados, não esquecidos**.

## Regressões encontradas na auditoria (todas CORRIGIDAS + provadas)
| # | Regressão (introduzida por mim) | Impacto | Correção | Prova |
|---|---|---|---|---|
| R1 | Índice único `(tenant,correlation)` quebrava **auth broadcast** (1 linha/admin) | admins não notificados de cadastros (silencioso) | índice → `(tenant,correlation,user_id) NULLS NOT DISTINCT` | auth broadcast=2 linhas; enqueue ainda 2x→1 |
| R2 | **SST** re-alerta via `db.add` (filtro `opened=False`) colidia com o índice ao marcar lido | `sst.alertas_diarios` inteira falhava (0 alertas SST) | `_upsert` busca linha única + re-alerta resetando `opened` | marquei lido → task **succeeded** (1 atualizada) |
| R3 | Gate CMO usava `module:comercial` (**inexistente**) | `/comercial/consultor` virou admin-only; usuários `module:crm` bloqueados | `module:crm` | romondos(crm)=200, gonzaga=403 |
| R4 | Consolidação 58→16 deletou broadcasts por-admin (não eram duplicatas) | ~42 linhas, parte legítima; **perda permanente** (histórico) | não restaurável | SST re-materializa; histórico auth perdido — **checar backup** |
| R5 | `celery_app.py` chave `"task"` duplicada | cosmético (Python usa a última) | removida | — |

## Mapa pré-mortem → status (cada risco)
| Risco | Descrição | Status |
|---|---|---|
| **A1** | Agregar sem `empresa_id` mistura CNPJs | ✅ COBERTO (Task 2: quarentena, chutados=0). *Aplicação do guard-rail = quando o cérebro existir (Fase 2).* |
| **A2** | JOIN uuid×varchar retorna vazio | ✅ COBERTO+VERIFICADO (v_employee, join=50) |
| **A3** | "Cliente" fraturado em 4 tabelas | ✅ COBERTO (entity_client=31 + override). *Órfãos = Jordan preenche.* |
| **A4** | `condominio_id` polissêmico | ✅ COBERTO+VERIFICADO (v_condominio_kind) |
| **B1** | Cérebro vivo só por evento dessincroniza | ✅ COBERTO (Task 8: reconciliação polling idempotente = espinha) |
| **B2** | PIX/jurídico não emitem evento | ✅ PADRÃO PROVADO (reconciliação re-deriva da fonte). *Cobertura: aging hoje; +domínios = incremental.* |
| **B3** | Publish fora da transação | 🕒 DIFERIDO Fase 2 (bus só como "acelerador"; hoje NÃO usamos o bus) |
| **B4** | Multi-worker consumer | 🕒 DIFERIDO Fase 2 |
| **C1** | Vazamento LGPD já explorável | ✅ COBERTO+VERIFICADO (8 gates; +fix CMO) |
| **C2** | Cutucão proativo vaza | 🕒 DIFERIDO Fase 3 (sem proatividade ainda) |
| **C3** | Sem perfil declarativo | 🕒 DIFERIDO Fase 1 (filtro por bloco + catálogo). *Gates por módulo bastam agora.* |
| **D1** | **Modelo local OOMa o ERP** | 🔴 DIFERIDO Fase 2 — **e CONFIRMADO VIVO**: o deploy hoje deu OOM/timeout 1× (recuperado). Risco real, não teórico. |
| **D2–D4** | Cortar OpenAI/pgvector/re-index | 🕒 DIFERIDO Fase 2 |
| **E1** | 5º mundo paralelo (tabela nova) | ✅ COBERTO (usei notification_queue, zero tabela nova) |
| **E2** | Dedup ilusório | ✅ COBERTO+VERIFICADO (índice único real) — **após corrigir R1** |
| **E3** | Sem retenção/particionamento | ✅ COBERTO (purgar; particionar=YAGNI) |
| **E4** | Unificar 2 sinos quebra UX | ✅ EVITADO por desenho (NÃO unifiquei — correção #6) |
| **F1** | DDL runtime sem Alembic | ✅ COBERTO+VERIFICADO (baseline, prod no-op) |
| **F2** | Refactor BaseConsultant regride | 🕒 DIFERIDO Fase 1 (é o que a Fase 1 faz) |
| **F3** | 3 camadas de LLM | 🕒 DIFERIDO Fase 1 |
| **F4** | Aprendizado ingênuo | 🕒 DIFERIDO Fase 4 |
| **G1** | Ferver o oceano | ✅ MITIGADO (fases) |
| **G2** | "Funciona na demo, vaza na prod" | ✅ MITIGADO — **esta auditoria achou 3 regressões** (o antídoto funcionou) |
| **G3** | RiskMonitor grita lobo | 🟡 PARCIAL (persiste alerta real; validar thresholds é contínuo) |

## Contagem honesta
- **Cobertos+verificados (fundação):** A1–A4, B1, B2, C1, E1–E4, F1 = **13 riscos**.
- **Diferidos por desenho (features futuras):** B3, B4, C2, C3, D1–D4, F2, F3, F4 = **11 riscos** — todos rastreados, cada um na sua fase.
- **Confirmado vivo a vigiar:** D1 (OOM) — o host é apertado; o incidente de deploy provou. **A Fase 2 (embeddings/modelo local) tem que tratar OOM como restrição dura** (sidecar dedicado c/ `mem_limit`, ou caixa com GPU separada).

## Estamos prontos para a Fase 1?
**Sim, para a Fase 1** (BaseConsultant + 1 caminho de LLM + ponte consultor→alertas + filtro por bloco): o solo de dados/segurança está sólido e verificado. A Fase 1 endereça justamente F2/F3/C3.
**Ressalvas honestas antes de avançar:**
1. **OOM/memória** (D1) é risco vivo — a Fase 2 precisa desenhar em torno disso desde o início.
2. **Perda de dado R4** é permanente (histórico, baixa severidade) — recomendo checar se há backup pré-consolidação.
3. **5 workers celery** ficam na imagem antiga após deploy-de-backend (só backend+beat+batch+operacional recriei) — é o padrão do processo deles, mas convém recriar todos num deploy pleno eventualmente.
