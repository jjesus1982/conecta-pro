# Frente Agente WhatsApp — mapa do webhook + decisões (READ-ONLY)

- **Data:** 2026-06-08
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Mapear como plugar um agente de IA no webhook do WhatsApp (responder mensagens de entrada).
- **Veredito:** Pontos de integração claros; **infra de IA já existe** (SDKs instalados). Mas há **várias decisões de produto** antes de implementar.

---

## 1. Ponto de integração (webhook → agente)
No `modules/integrations/connectors/whatsapp/controller.py` (`chatwoot_webhook`):
- Linha 256: ignora se `event != message_created`.
- Linha 262: `direction = "in" if message_type in ("incoming","0") else "out"`.
- Linha 272: `if direction == "in"` → cria/acha Lead.
- Linha 280-291: grava `cwi_message_log`.
- **O agente entra aqui:** após logar uma mensagem **incoming**, disparar (de preferência em **background**, para responder o webhook rápido): ler histórico → gerar resposta → enviar.

## 2. Histórico da conversa (o agente é o 1º leitor)
- `cwi_message_log` hoje é **só escrito** — **nada lê** (confirmado por grep).
- O agente montaria o histórico com: `SELECT direction, content, created_at FROM cwi_message_log WHERE chatwoot_conversation_id = :conv ORDER BY created_at` → vira o `messages[]` do LLM (in=user, out=assistant).
- A coluna `chatwoot_conversation_id` já está no log → chave natural do histórico.

## 3. SDKs de IA — já instalados (nada a adicionar)
- `openai 2.38.0` ✅
- `anthropic 0.105.2` ✅ (o projeto usa Claude em outros pontos — ex.: agentes CTO, licitações)

## 4. Caminho de resposta
- **Opção A (recomendada):** `whatsapp_service.send_custom(phone, reply)` — o chokepoint canônico já validado (posta no Chatwoot → Baileys). Mantém tudo no Chatwoot (histórico/agentes humanos veem).
- **Opção B:** chamar a API do Chatwoot direto na `conversation_id`.

## 5. Segurança do loop (importante)
- O webhook **distingue in/out**. O agente dispara **só em `direction=="in"`** → não responde às próprias saídas nem às mensagens digitadas por um atendente humano (que entram como `outgoing`).
- Ainda assim: a resposta do agente sai como `outgoing` e **volta** ao webhook (logada, sem lead, sem re-disparo) — sem loop, desde que o gatilho seja `in`.

## 6. ⚠️ Já existe um auto-responder de IA legado
- `modules/client_portal/controllers/whatsapp_controller.py` usa `responder_com_ia(...)` (serviço `whatsapp_ia_service`) para o fluxo **WhatsApp→ticket de suporte** (formato Evolution, hoje dormante).
- **Decisão:** o novo agente é o **mesmo** propósito (reusar/migrar `whatsapp_ia_service`) ou **outro** (ex.: vendas/qualificação de Lead)? Evitar dois agentes concorrentes.

---

## 7. DECISÕES DE PRODUTO (preciso de você antes de implementar)
1. **Papel do agente:** atendimento/suporte? **vendas/qualificação de Lead**? FAQ? Cada um muda o prompt e o fluxo.
2. **Quando responde:** TODA mensagem de entrada? Só de leads novos? Só fora do horário comercial? Só até um humano assumir a conversa no Chatwoot?
3. **Escalonamento:** quando passar para humano? (palavra-chave, intenção, nº de turnos, pedido explícito) — e como sinalizar no Chatwoot (atribuir/tag/nota)?
4. **Modelo:** Claude (anthropic) ou OpenAI? Qual modelo? (custo vs qualidade)
5. **Persona/prompt + base de conhecimento:** o agente responde de quê? (catálogo de serviços, preços, horários?) Precisa de RAG/contexto da empresa?
6. **Guard-rails:** rate limit, custo máximo, não inventar preço/prazo, LGPD (dados do cliente no prompt).
7. **Reuso vs novo:** aproveitar o `whatsapp_ia_service` legado ou começar limpo?

## 8. Esboço técnico (quando as decisões fecharem) — PROPOSTA
1. Serviço `whatsapp_agent_service` (em `integrations/connectors/whatsapp/`): `async def responder(conversation_id, phone) -> str|None`.
2. Lê histórico de `cwi_message_log` → monta mensagens → chama LLM (anthropic/openai) com prompt/guard-rails.
3. Aplica regras (responder? escalar?).
4. Se responder → `whatsapp_service.send_custom(phone, reply)`.
5. No webhook, em `direction=="in"`, agendar via `BackgroundTasks` (não bloquear o 200 do webhook).
6. Config por env (modelo, on/off, horário) — nada hardcoded.

---
*Read-only: leitura do controller, grep de `cwi_message_log`, `pip show`. Nada implementado. Decisões de produto pendentes.*
