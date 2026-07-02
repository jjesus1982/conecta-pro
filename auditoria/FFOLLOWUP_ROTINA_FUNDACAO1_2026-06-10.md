# Rotina `crm.followup_proposals` — Fundação 1 (gera lista, disparo desligado) ✅

- **Data:** 2026-06-10
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Status:** ✅ **Entregue e validado.** Task Celery diária que seleciona propostas vencidas, registra a cadência e entrega a lista ao Jordan via Telegram. **NÃO contata o cliente** (`FOLLOWUP_AUTO_SEND=False` — gate LGPD).
- **Arquivos:** `modules/crm/tasks.py` (novo) + `celery_app.py` (include + beat_schedule) · **Backup:** `celery_app.py.bak-followuptask-20260610-022541`
- **Commit:** **`38baa711`** — `feat(crm): rotina followup_proposals (gera lista, disparo desligado por flag - gate LGPD)`

---

## 1. Horário do schedule
- **`crontab(hour=8, minute=30)` diário**, fila **`gov.batch`** (consumida por celery-batch). Escolhido por estar **livre** (ocupados: 8:00/7:30/9:00/…), e gov.batch já roda jobs diários de lote.
- Entry: `"crm-followup-proposals-0830"` no `app.conf.beat_schedule`. Include: `"modules.crm.tasks"`.

## 2. Como funciona (diff resumido)
- `@app.task(name="crm.followup_proposals")` → `_run_async(_followup_async)` (engine própria, padrão financial).
- **Seleção:** `proposals WHERE status='sent' AND responded_at IS NULL AND sent_at IS NOT NULL`. Para cada uma, consulta o último `proposal_followups` (maior sequence): se **nenhum** → vence em `sent_at + 2d`; se **há** → vence em `último + 7d`.
- **Registro (avança a cadência):** insere em `proposal_followups` `sequence=próximo`, `scheduled_for=now`. Com flag **OFF**: `status='skipped'`, `channel='none'`, `detail='lista gerada, disparo desligado (gate LGPD)'`. Commit atômico.
  - **Semântica documentada:** registrar 'skipped' faz a próxima janela de 7d contar a partir de agora → o mesmo lead **não reaparece todo dia** (volta em +7d), e fica a trilha (LGPD).
- **Entrega:** monta a lista (number, cliente, valor, dias sem resposta, nº do próximo follow-up) e envia ao Jordan via **Telegram Bot API** (`TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` lidos do **env do container** — `monitor_bot` está no host `/agents/cto/`, fora do `/app`, então usei `requests` com as credenciais já existentes, sem hardcode). Se 0 vencidos → mensagem curta "nenhuma proposta vencida".
- **Gate LGPD:** `FOLLOWUP_AUTO_SEND = False` (constante no **código**, não no .env). Bloco `_enviar_followup_cliente` (WhatsApp `send_custom` + e-mail `send_email`) **implementado mas atrás do `if`** — NÃO executado. Docstring explica que ligar exige (1) revisão LGPD, (2) `True` no código, (3) rebuild.

## 3. Validação (proposta de teste retroativa, efêmera)
Proposta criada + `/send` + `sent_at` backdatado -3 dias (vencida >2d):
| Ponto | Resultado |
|-------|-----------|
| (a) apareceu na lista | rodada 1 `vencidos=1` ✅ |
| (b) registro em proposal_followups | `sequence=1, status='skipped', channel='none', detail='...gate LGPD'` ✅ |
| (c) Telegram ao Jordan | `telegram_ok=True` (mensagem entregue ao chat 5536961034) ✅ |
| (d) ZERO envio ao cliente | `auto_send=False`, channel='none', sent_at null ✅ |
| (e) não-duplica (2ª rodada imediata) | `vencidos=0`, followups continua **1** (sem novo registro) ✅ |

## 4. Limpeza e estado
- Proposta + followups de teste deletados → **proposals=0, proposal_followups=0**. **opportunities seed (5) intactas.**
- **host==container** (`tasks.py`=`2bf7193d…`, `celery_app.py`=`a9750f91…`) · backend **healthy** · **health 200**.
- Restart de backend + celery-batch + beat (carregam a task/schedule).

## 5. Durabilidade (3 itens acumulados p/ próximo rebuild)
Vivem via docker cp sobre a imagem `c4bde53` (commitados):
1. fix create de proposta — `eb60ea82`
2. migration `proposal_followups` — `dd57f47b` (mudança de BANCO já permanente; arquivo a bakar)
3. rotina `followup_proposals` — `38baa711`
➡️ Bakar no próximo rebuild. **NÃO rebuildei. NÃO liguei FOLLOWUP_AUTO_SEND.**

## 6. Decisão futura (Jordan)
- Para LIGAR o contato ao cliente: revisão LGPD → `FOLLOWUP_AUTO_SEND=True` no código → rebuild. Aí a task passa a disparar WhatsApp/e-mail e gravar `status='sent'`+`channel`+`sent_at` reais.
- (Opcional) decidir se a mensagem de "0 vencidos" deve ser enviada diariamente ou silenciada.

---

## Resumo
- Task `crm.followup_proposals` (8:30 diário, gov.batch): seleciona vencidas, registra cadência, entrega lista no Telegram. ✅
- Gate LGPD `FOLLOWUP_AUTO_SEND=False` — bloco de envio pronto mas desligado; zero contato ao cliente. ✅
- 5 pontos da validação OK (incl. não-duplica). Limpo. host==container, health 200, commit `38baa711`. ✅
- Pendente: bakar no rebuild (3 itens). Não rebuildei, não liguei a flag.

*PAREI. Não liguei FOLLOWUP_AUTO_SEND. Não rebuildei.*
