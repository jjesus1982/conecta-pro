# Validação do fluxo bidirecional WhatsApp (Baileys ↔ Chatwoot) — READ-ONLY

- **Data:** 2026-06-05 ~17:50 UTC
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Validar envio de saída pelo Chatwoot (fluxo bidirecional).
- **Veredito:** ✅ **Fluxo bidirecional PROVADO funcionando** — com tráfego real já existente. Nenhuma mensagem de teste nova foi enviada (não foi necessário).

---

## 1. Evidência (conversa real, inbox "Atendimento Conecta Mais", +558008804414)

Contatos sincronizados: **Jordan Jesus** (você) e **Rafa-el**. A conversa com Rafa-el registrou um teste completo às **17:29–17:30**:

| msg | direção | status | Baileys (`source_id`) | prévia |
|----|---------|--------|----------------------|--------|
| 5 | **IN** (entrada) | sent | ✅ presente | "Opa" |
| 7 | **OUT** (saída) | **read** | ✅ presente | "teste de envio e recebimento de mensagem" |
| 8 | **IN** (entrada) | sent | ✅ presente | "Ok" |
| 9 | **OUT** (saída) | **read** | ✅ presente | (mídia/sem texto) |

## 2. Agregado de saída (todas as conversas)
```
mensagens de saída (message_type=1) ............ 3
saída com FALHA (status=3) ..................... 0
saída com source_id (aceitas pelo Baileys) ..... 3 / 3
```

## 3. Interpretação
- **Saída (Chatwoot → WhatsApp):** 3 mensagens enviadas, **0 falhas**, todas com `source_id` (o Baileys gerou o ID da mensagem no WhatsApp). Duas chegaram a **`read`** → o destinatário **recebeu e leu** (read receipt retornou pelo Baileys).
- **Entrada (WhatsApp → Chatwoot):** mensagens recebidas com `source_id`, criando contato/conversa automaticamente.
- **Conclusão:** o ciclo completo está fechado — **Chatwoot → Baileys → WhatsApp (entregue/lido)** e **WhatsApp → Baileys → Chatwoot**. O Sidekiq (religado hoje) está processando os jobs/webhooks dos dois sentidos.

## 4. Por que não enviei um teste novo
O fluxo já está comprovado por mensagens **reais** (envio + leitura confirmada). Enviar outra mensagem só geraria um WhatsApp desnecessário a um contato real. Se você quiser uma confirmação **ao vivo** adicional, o caminho mais seguro é um teste para o **seu próprio número** (contato "Jordan Jesus", conversa 1) — me avisa que eu envio só para você.

## 5. Estado operacional
- 🟢 Baileys conectado (`+558008804414`), Chatwoot healthy, Sidekiq processando.
- 🟢 Envio e recebimento validados com read receipts.
- ⚠️ Continuar de olho nos warnings `timed out waiting for message` do Baileys (estabilidade) — até agora sem impacto (mensagens entregues e lidas).

---
*Read-only: consultas `psql` (SELECT) na base do Chatwoot. Nenhuma mensagem enviada, nenhuma config alterada. Números mascarados.*
