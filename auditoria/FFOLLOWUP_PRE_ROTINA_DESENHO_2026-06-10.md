# Rotina de follow-up de propostas — desenho (READ-ONLY)

- **Data:** 2026-06-10
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Mapear o que falta para uma rotina de follow-up (cadência 2d + a cada 7d), com disparo DESLIGADO por flag (gera lista, não contata cliente — gate LGPD).
- **Veredito:** Infra de envio + entrega (Telegram) + Celery prontos. **Falta estado de cadência** em `proposals` (campo/tabela novos) — sem ele, remandaria todo dia.
- **NADA implementado.** Só desenho.

---

## 1. Estado de cadência em `proposals` — NÃO existe
`proposals` tem `sent_at`, `viewed_at`, `responded_at`, `client_email`, `client_phone`, `opportunity_id`. **Sem** `last_followup_at`/`followup_count`/`next_followup_at`.
- ➡️ Falta criar (migration futura) para a cadência não remandar diariamente:
  - **Opção A (mínima):** colunas `last_followup_at` (timestamp) + `followup_count` (int default 0) em `proposals`.
  - **Opção B (auditável — recomendada p/ LGPD):** tabela `proposal_followups` (proposal_id, sequence, channel, scheduled_for, sent_at, status).
- **Regra "vencido p/ follow-up":** `status='sent' AND responded_at IS NULL AND ( (followup_count=0 AND now ≥ sent_at+2d) OR (followup_count≥1 AND now ≥ last_followup_at+7d) )`.

## 2. Plugar no Celery
- `celery_app.py:141` → `app.conf.beat_schedule = { "<nome>": {"task":"<task.name>", "schedule": crontab(...)} }`. `include=[...]` lista os módulos de tasks.
- Tasks: `@app.task(name="...")` em `modules/<x>/tasks.py`. **Async-em-task:** função sync chama `_run_async(coro)` (engine/session async própria) — padrão em `financial/tasks.py`.
- ➡️ Criar `modules/crm/tasks.py::@app.task(name="crm.followup_proposals")` + entry no `beat_schedule` (ex. `crontab(hour=8, minute=0)`) + registrar em `include`.

## 3. Contato do destinatário
- **Direto da `proposals`:** `client_email` + `client_phone` (preenchidos no create). `opportunity_id` disponível para enriquecer, mas não necessário.

## 4. Assinaturas de envio (código pronto mesmo desligado)
- E-mail: `core.mailer.send_email(to_email: str, subject: str, html_body: str) -> bool` (async, validado).
- WhatsApp: `whatsapp_service.send_custom(phone: str, message: str) -> dict` (async, wrapper público de `_send_message`).

## 5. Entrega da LISTA de leads frios → Telegram (canal existente)
- Há infra de relatório Telegram p/ o Jordan: host crontab roda `agents/cto/relatorio_matinal.py`; helper `monitor_bot.send(msg)` (`from monitor_bot import send`); `MONITOR_BOT_TOKEN` no env das rotinas CTO (token NÃO reproduzido aqui) + `TELEGRAM_CHAT_ID` do Jordan.
- **Precedente direto:** `agents/cto/proatividade.py` faz `verificar_e_gerar_propostas` → `formatar_propostas_telegram` → `send`.
- ➡️ Entregar a lista de propostas frias **no mesmo canal Telegram** (reusar `monitor_bot.send`). Alternativa/complemento: gravar `.md`/log em `/opt/conecta-pro/rotinas/` (como o briefing diário).
- ⚠️ Observação de segurança: o `MONITOR_BOT_TOKEN` aparece em **texto plano no crontab** — fora de escopo agora, mas vale mover para arquivo de env protegido um dia.

## 6. Proposta de desenho (1 parágrafo)
Criar `modules/crm/tasks.py::followup_proposals` (Celery `@app.task`, agendada diária no `beat_schedule` via `crontab`), que via `_run_async` consulta as propostas **vencidas para follow-up** (`status='sent' AND responded_at IS NULL` + regra 2d/7d usando o **estado novo** `last_followup_at`/`followup_count` — coluna ou tabela `proposal_followups`, a criar por migration); a task **lê a flag `FOLLOWUP_AUTO_SEND` (default false)** — **desligada (gate LGPD)** apenas **monta a lista** (número, cliente, valor, dias desde envio, contato) e **entrega ao Jordan via Telegram** (reusando `monitor_bot.send`) + log em `rotinas/`, **sem contatar o cliente**; quando o Jordan **ligar a flag** (pós-LGPD), a mesma task passa a **disparar** `send_custom`(WhatsApp)/`send_email` e **atualizar `last_followup_at`+`followup_count`** atômico (respeitando a cadência, sem remandar todo dia).

## 7. O que faltaria (resumo)
| Peça | Estado | Falta |
|------|--------|-------|
| Estado de cadência | 🔴 inexistente | migration: 2 colunas OU tabela `proposal_followups` |
| Task + schedule | ✅ infra pronta | criar `crm/tasks.py` + entry no beat_schedule + include |
| Contato (email/phone) | ✅ na `proposals` | — |
| Envio (email/WhatsApp) | ✅ assinaturas prontas | usar só quando flag=true |
| Entrega da lista | ✅ Telegram (monitor_bot) | reusar; sem canal novo |
| Flag de gate | 🔴 inexistente | env `FOLLOWUP_AUTO_SEND=false` |

---
*Read-only: `\d proposals` (campos), `celery_app.py` (beat_schedule/include), `financial/tasks.py` (padrão), assinaturas `send_email`/`send_custom`, crontab do host (entrega Telegram via monitor_bot/CTO agents). Nada implementado, sem migration.*
