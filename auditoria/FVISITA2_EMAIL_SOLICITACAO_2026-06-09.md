# F-VISITA.2 — E-mail de solicitação de visita (interno + cliente, best-effort) ✅

- **Data:** 2026-06-09
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Status:** ✅ **Entregue e validado.** Ao criar visita, o agente dispara e-mail(s) via `core/mailer` (validado). **Best-effort:** e-mail nunca quebra a visita nem o webhook. Continua copiloto.
- **Arquivo:** `modules/integrations/connectors/whatsapp/agent_service.py` · **Backup:** `agent_service.py.bak-fvisita2-20260609-160054`
- **Commit:** **`983378bb`** — `feat(whatsapp): F-VISITA.2 email de solicitacao de visita (interno sempre + cliente se cadastrado, best-effort)`

---

## 1. O que mudou (diff)
Novo helper `_enviar_emails_visita(...)` + chamada **logo após `criar_visita(...)`** e antes do `return {"ok":True,...}`:
- **Bloco try/except ISOLADO** (best-effort) — qualquer falha (SMTP/query) → `logger.warning` e segue. O `{ok:true}` acontece SEMPRE.
- **(a) E-mail INTERNO — SEMPRE:** `to=jjesus@conectamais.pro`, assunto `[Conecta PRO] Nova solicitação de visita {numero}`, corpo com dados (número, data/hora, local, objetivo, contato, origem cliente/prospect) + aviso de que é SOLICITAÇÃO aguardando confirmação da equipe.
- **(b) E-mail ao CLIENTE — só se `cliente_id` e houver email:** `SELECT email FROM clients WHERE id=:cliente_id` (async, mesma sessão). Assunto `[Conecta Mais] Recebemos sua solicitação de visita`, teor de **SOLICITAÇÃO** ("recebemos sua solicitação para {data} às {hora}; nossa equipe **confirmará** o horário" — nunca "agendado/confirmado"). Sem cliente_id OU sem email → pula (log do motivo).
- **Logs:** interno enviado (True/False), cliente enviado/pulado (+ motivo: sem_cliente_id / sem_email).

## 2. Testes (A/B/C/D)
| Teste | Resultado |
|-------|-----------|
| **A** prospect (sem cliente_id) | interno **enviado=True** (REAL → `jje***@conectamais.pro`); cliente **PULADO** (`sem_cliente_id`); `{ok:true}` ✅ |
| **B** cliente identificado (Michelangelo) | interno (`jje***@`) + **cliente** (`mic***@conectamais.pro`), ambos assunto correto e **teor solicitação=True**; `{ok:true}` ✅ |
| **C** best-effort (send_email **lança exceção**) | `warning` best-effort logado; **visita AINDA criada**; `{ok:true}` ✅ |
| **D** limpeza | 3 visitas → **0** ✅ |

**Nota de segurança no Teste B:** usei um **recorder** (captura destinatário/assunto/teor **sem enviar**) para **não disparar e-mail real a um cliente externo**. A entrega real já foi provada no smoke test (`core/mailer` OK). O Teste A enviou de verdade, mas só o **interno** (para o Jordan).

## 3. Garantias
- **Best-effort comprovado (Teste C):** exceção no e-mail → visita criada + `{ok:true}`. Webhook nunca cai.
- **Copiloto intacto:** nada enviado ao cliente **via WhatsApp** (e-mail é canal separado); a sugestão WhatsApp segue como nota privada/rascunho.
- **Teor correto:** e-mail ao cliente fala em "solicitação" e "equipe confirmará" — nunca "agendado/confirmado".
- **host==container** (`d775d4b5…`) · backend **healthy** · **health 200** · webhook token errado **401** · `visitas` = 0.

## 4. Fora de escopo (decisão Jordan)
- **NÃO** coleta e-mail de prospect na conversa (fica pós-LGPD). Schema da tool inalterado. Para prospect, só o e-mail interno avisa a equipe.

## 5. Durabilidade
- Commit `983378bb` vive via docker cp sobre a imagem `b18575b9` → **bakar no próximo rebuild** (acumula). **NÃO rebuildei.**

## 6. Para o Jordan
- O **Teste A enviou um e-mail interno real** → cheque `jjesus@conectamais.pro` (inclusive spam): assunto **"[Conecta PRO] Nova solicitação de visita VIS-2026-00001"**.

---

## Resumo
- E-mail de solicitação no `agendar_visita`: interno SEMPRE + cliente se cadastrado, **best-effort**. ✅
- Testes A/B/C/D OK (incl. best-effort com exceção). Teor de solicitação. Copiloto intacto. ✅
- host==container, health 200, commit `983378bb`. Pendente: bakar no rebuild. ⏸️

*PAREI. Não rebuildei. Não coletei e-mail de prospect (fora de escopo).*
