# Transferência de conversa por setor no Chatwoot — viabilidade (READ-ONLY)

- **Data:** 2026-06-09
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Mapear como atribuir conversa a time/agente via API do Chatwoot para o agente transferir por setor.
- **Veredito:** ⚠️ **A memória estava desatualizada:** o Chatwoot real tem **0 times** e **só 2 agentes** (Bot + Jordan). O código de assign é pequeno (reusa `_api`), mas **não há destino** até criarem times/agentes no Chatwoot.
- **NADA implementado, NENHUMA escrita** (só GET de leitura).

---

## 1. Times no Chatwoot → 0 (GET /teams)
`GET /api/v1/accounts/1/teams` → **lista vazia**. Os 5 times (Comercial/DP/Operacional/Suporte/Fiscal) da memória **NÃO existem** nesta instância.

## 2. Agentes → apenas 2 (GET /agents)
| agent_id | nome | email | role |
|----------|------|-------|------|
| 1 | Jordan Jesus | jjesus@conectamais.pro | administrator |
| 2 | Bot Conecta PRO | noreply@conectamais.pro | agent |

Os agentes nomeados (Pyetra, Eliziel, Orlailson, Rafael, Ramon, Ruan…) **não existem** no Chatwoot — precisam ser criados.

## 3. Auth do service.py no Chatwoot
- `base_url = http://chatwoot-fazerai:3000` · `account_id = 1` · header **`api_access_token`** (token via `CHATWOOT_API_TOKEN`, fallback `/app/.chatwoot_token`).
- Helper genérico `_api(session, method, path, body)` já existe. **Nenhuma função de assign/transfer/team** no stack (grep vazio).

## 4. Endpoints de atribuição (documentado — NÃO executado)
Chatwoot Application API, endpoint único `assignments`:
- **Agente:** `POST /api/v1/accounts/1/conversations/{conv_id}/assignments` → `{"assignee_id": <agent_id>}`
- **Time:** `POST /api/v1/accounts/1/conversations/{conv_id}/assignments` → `{"team_id": <team_id>}`
- ⚠️ `team_assignments` (citado no briefing) **não é** rota pública; usar `assignments` com `team_id`. Confirmar na 1ª escrita.
- Estrutura confirmada por GET (9 conversas): `meta.assignee` (id+nome) e `meta.team` existem. Ex.: conv_id=8 → assignee=Jordan(1), team=None.
- (Alternativa por rótulo: `POST .../conversations/{id}/labels` — se preferirem marcar setor por label em vez de time.)

## 5. conversation_id no fluxo do agente → ✅ disponível
- Webhook: `conv_id = conv.get("id")` (controller.py:267) → `background_tasks.add_task(processar_incoming, conv_id, phone)` (304).
- `agent_service` carrega `conversation_id` em gerar_resposta/tools. No momento de decidir transferir, **o agente já tem o conv_id**.

---

## O que falta para implementar
| Camada | Estado | Falta |
|--------|--------|-------|
| **Setup Chatwoot (admin)** | 🔴 0 times, 2 agentes | **Criar** times + contas de agente dos setores + memberships. **Pré-condição — sem isso não há destino** |
| Auth/HTTP (`_api`) | ✅ pronto | — |
| Função assign | 🔴 inexistente | `assign_team(conv_id, team_id)` / `assign_agent(conv_id, assignee_id)` reusando `_api` |
| Mapa setor→team_id | 🔴 inexistente | const/tabela de roteamento |
| Gatilho | 🔴 inexistente | tool `transferir_conversa` (LLM) **ou** regra (cliente pede / agente não resolve) — decisão de produto |
| conv_id | ✅ disponível | — |

**Bloqueio nº 1 = setup no Chatwoot** (admin/operação), não código.

## Decisões / pré-requisitos (Jordan)
1. **Criar no Chatwoot** os times e os agentes (com e-mail/convite) — quem faz e quais setores exatamente? (a memória cita 5, mas é preciso definir os reais).
2. Roteamento por **time** (assignee fica para o time distribuir) ou direto por **agente**?
3. Gatilho: o **agente (LLM) decide** transferir (tool `transferir_conversa` com setor) **ou** o cliente escolhe um menu / regra fixa?
4. Mensagem ao transferir (avisar o cliente "vou te encaminhar para o setor X")?

---
*Read-only: leitura de `service.py` (auth), grep de assign no stack, GET `/teams` e `/agents` e `/conversations` na API do Chatwoot (token do backend), confirmação do conv_id no fluxo. Nenhuma escrita/assign. Nada implementado.*
