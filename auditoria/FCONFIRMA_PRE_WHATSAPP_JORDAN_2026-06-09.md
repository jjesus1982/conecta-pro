# Confirmação de visita por WhatsApp do Jordan — viabilidade (READ-ONLY)

- **Data:** 2026-06-09
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Avaliar viabilidade de um fluxo onde o agente PERGUNTA disponibilidade ao Jordan (92986465328) e INTERPRETA a resposta livre para confirmar a visita.
- **Veredito:** "Iniciar conversa ativa" ✅ já é possível. **O bloqueio é correlacionar a resposta livre a uma visita pendente** 🔴 — exige infraestrutura nova. Número do Jordan não está cadastrado.
- **NADA implementado.** Só leitura.

---

## Ponto 1 — Envio ATIVO (iniciar conversa com número novo) → ✅ VIÁVEL
`modules/integrations/connectors/whatsapp/service.py` → `_send_message(phone, message)`:
1. `_resolve_contact` → **POST `/contacts`** (cria contato se não existir) → `contact_id`+`source_id`; fallback busca por dígitos + `contactable_inboxes`.
2. **POST `/conversations`** (cria conversa) → `conv_id`.
3. **POST `/conversations/{conv_id}/messages`** (envia).

- **Não precisa de conversa pré-existente** — cria contato e conversa para número arbitrário.
- Canal **Baileys (WhatsApp não-oficial)** → **sem regra de template/janela 24h** (≠ API oficial Meta) → cold-send ao número do Jordan é tecnicamente possível.
- **Falta:** apenas um **gatilho/chamador** de `_send_message(numero_jordan, pergunta)` — orquestração, **não** infra nova. Ressalva: confiabilidade/ban do Baileys em cold-send (baixo risco p/ número próprio).

## Ponto 2 — Correlacionar resposta livre do Jordan a uma visita pendente → 🔴 PRECISA CONSTRUIR
- **Sem noção de estado/pendência** no stack (grep `pending/state/fsm/aguardando` só achou texto de e-mail, não FSM).
- **`cwi_message_log`** (colunas: `id, direction, phone_canonical, chatwoot_conversation_id, chatwoot_message_id, content, client_id, lead_id, status, created_at`) → **nenhum vínculo a visita** nem "aguardando resposta".
- **`visitas`** tem `confirmada/confirmada_at/confirmada_por` → mas **nenhum vínculo a conversa/Chatwoot/WhatsApp**.
- **Webhook** correlaciona só por **telefone → conversation_id → lead** (cria/dedup) e **não distingue remetente interno**.
- ➡️ "Jordan responde 'pode'" → hoje **impossível** saber a qual visita se refere. Precisa criar:
  1. **Elo** pergunta↔`visita_id`↔conversa do Jordan (tabela/campo novo, ex. `visita_confirmacao_pendente`).
  2. **Estado** "aguardando_confirmacao".
  3. **Branch no webhook**: se mensagem vem **do número do Jordan** E há visita pendente → rotear p/ **interpretador** (LLM) em vez do fluxo lead/copiloto.
  4. **Ação de confirmar**: interpretar resposta livre → setar `visita.confirmada` (+ `confirmada_at/por`) → avisar o cliente.

## Ponto 3 — Número do Jordan (92986465328) cadastrado? → 🔴 NÃO
- Ausente em `users.phone` (0), `clients.phone`/`whatsapp` (0), `leads` (0), `employees` (0), e **no env** (nenhuma var de número/responsável).
- Coluna `users.phone` **existe mas vazia para todos** (0/59).
- ➡️ Registrar via **env** (`AGENT_CONFIRM_PHONE`) ou `users.phone` do Jordan corporativo (`ad9abb59`). Pequeno, mas "a criar".

---

## Veredito
| Ponto | Com o que existe? | O que falta |
|-------|-------------------|-------------|
| 1. Iniciar conversa ativa c/ número novo | ✅ Sim (`_send_message` cria contato+conversa) | só **gatilho** (orquestração) |
| 2. Correlacionar resposta livre → visita | 🔴 Não | **infra nova**: elo visita↔conversa, estado pendente, branch webhook p/ remetente interno, interpretador + ação confirmar |
| 3. Número do Jordan cadastrado | 🔴 Não | registrar (env ou `users.phone`) — pequeno |

**Bloqueio real = Ponto 2.** Enviar pergunta ativa está pronto; correlacionar a resposta a uma visita pendente exige **estado + elo conversa↔visita + roteamento do remetente interno + interpretador**.

### Observações de produto (para o Jordan decidir)
- Como distinguir resposta do Jordan da de um cliente? (pelo número — exige cadastrar o nº e o branch no webhook).
- Uma pergunta por visita ou em lote (várias visitas pendentes)? → muda a complexidade do elo/estado.
- Interpretação livre ("pode", "só amanhã", "remarca 15h") = nova chamada LLM dedicada (não o copiloto atual).

---
*Read-only: leitura de `service.py`/`controller.py`/`agent_service.py`, schema de `cwi_message_log`/`visitas`/`users`, buscas do número em users/clients/leads/employees/env. Nada implementado.*
