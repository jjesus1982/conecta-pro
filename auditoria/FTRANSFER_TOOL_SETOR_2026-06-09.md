# Tool transferir_conversa por setor (assign team Chatwoot) ✅

- **Data:** 2026-06-09
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Status:** ✅ **Entregue e validado.** 4ª tool do agente: encaminha a conversa ao time do setor no Chatwoot. Best-effort; copiloto no resto.
- **Arquivos:** `agent_service.py` (tool+dispatcher+prompt) + `service.py` (assign_team) · **Backups:** `*.bak-transfer-20260609-174158`
- **Commit:** **`026f6f85`** — `feat(whatsapp): tool transferir_conversa por setor (assign team Chatwoot, copiloto)`

---

## 1. Times reais (GET /api/v1/accounts/1/teams)
| team_id | nome |
|---------|------|
| 1 | comercial |
| 2 | administrativo |
| 3 | suporte tecnico |
| 4 | operacional |

(Agentes nomeados ainda NÃO existem como users do Chatwoot — só os times.)

## 2. O que mudou (diff)
- **`service.py` → `assign_team(conversation_id, team_id)`:** reusa `_api`, `POST /conversations/{id}/assignments` body `{"team_id": id}`. try/except, loga resultado. Best-effort.
- **`agent_service.py`:**
  - **Mapa** `SETOR_TEAM_ID = {comercial:1, administrativo:2, suporte_tecnico:3, operacional:4}` (ids reais, comentado).
  - **Tool `transferir_conversa`** (schema): `setor` (enum comercial/suporte_tecnico/operacional/administrativo) + `motivo`. Descrição mapeia cada setor ao tipo de demanda.
  - **`_tool_transferir_conversa`**: resolve setor→team_id, chama `whatsapp_service.assign_team`, try/except (nunca derruba).
  - **Dispatcher** `_exec_tool`: branch `transferir_conversa`.
  - **SYSTEM_PROMPT**: transferir é ÚLTIMO recurso (resolver primeiro); usar quando não resolver OU cliente pedir humano; SEMPRE avisar antes; **DEVE chamar a tool de fato** (reforço — ver §4).

## 3. Testes
| Teste | Resultado |
|-------|-----------|
| **A** assign REAL + reverte | conv 8: team None → **comercial (id=1)** → revertido None. Endpoint `assignments` aceita `team_id` ✅ |
| **B** "câmera de CFTV parou, manutenção" | modelo chamou `transferir_conversa` **setor=suporte_tecnico** (team 3); resposta avisa: *"Já encaminhei sua conversa para o nosso time de suporte técnico… Um momento"* ✅ |
| **C** "quero falar com uma pessoa" | modelo chamou `transferir_conversa` **setor=comercial** (default); avisa o cliente ✅ |

## 4. Correção durante a validação (honestidade)
- 1ª rodada do Teste C: o modelo **disse** "vou te encaminhar" mas **NÃO chamou** a tool → conversa não transferida (UX quebrada).
- **Fix:** reforcei o SYSTEM_PROMPT ("ao decidir encaminhar, você DEVE chamar a ferramenta de fato — não basta dizer"). Re-deploy + re-teste C → **modelo passou a chamar** a tool (setor=comercial). ✅

## 5. Garantias
- **Best-effort:** falha na atribuição → `{erro}` ao modelo + log; webhook nunca cai.
- **Copiloto intacto:** respostas de texto seguem como rascunho (drf) + nota privada; a transferência é ação interna no Chatwoot (assign ao time), o cliente só vê o aviso textual (que no modo copiloto é rascunho/nota privada).
- **host==container** (`ca08ff91` agent / `e8253210` service) · backend **healthy** · **health 200** · webhook token errado **401**.
- Limpeza: conversa 8 revertida a team=None; `cwi_message_log` de teste = 0.

## 6. Durabilidade (PENDÊNCIAS acumuladas p/ próximo rebuild)
Vivem via docker cp sobre a imagem `b18575b9` (commitadas):
1. F-VISITA.2 e-mail — `983378bb`.
2. Tool transferir_conversa — `026f6f85`.
➡️ Bakar no próximo rebuild. **NÃO rebuildei.**

---

## Resumo
- 4ª tool `transferir_conversa` + `assign_team` no service — encaminha ao time do setor. ✅
- Testes A (assign real)/B (suporte_tecnico)/C (comercial default) OK; prompt reforçado p/ forçar a chamada real. ✅
- Best-effort, copiloto intacto, host==container, health 200, commit `026f6f85`. ✅
- Pendente: bakar no rebuild (F-VISITA.2 + transferir). Não rebuildei.

*PAREI. Não rebuildei.*
