# Religação do Sidekiq do Chatwoot — Execução

- **Data:** 2026-06-05 ~16:07 UTC
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Ação:** Religar o `chatwoot-fazerai-sidekiq` (parado desde 29/mai) + fixar política de restart.
- **Resultado:** ✅ **Sucesso.** Worker vivo, processando jobs, sem erro. Causa-raiz do abandono corrigida.
- **Autorização:** solicitada pelo administrador (comando enviado por ele). Pré-check de segurança feito antes (banco vazio → sem risco de disparar mensagens antigas).

---

## 1. O que foi feito

```
docker update --restart unless-stopped chatwoot-fazerai-sidekiq   # (1) política
docker start chatwoot-fazerai-sidekiq                              # (2) subir
```
- **(1)** `restart: unless-stopped` — garante que o worker volte sozinho em futuros restarts (foi exatamente isso que faltou em 29/mai, quando ficou para trás).
- **(2)** start do container existente (sem recriar, sem mexer em imagem/código).

---

## 2. Verificação pós-religação

| Checagem | Resultado |
|----------|-----------|
| Status do container | `running`, `RestartCount=0`, `Running=true` |
| StartedAt | 2026-06-05 16:07:17 UTC |
| Política de restart | `unless-stopped` ✅ |
| Processo Sidekiq | **novo e vivo**: `4c87b1c42692:1:cbc4bbb4e3ab` (nonce novo ≠ órfão anterior `43552d7213c5`) |
| Heartbeat (`beat`) | **fresco** (~8s antes da checagem) — antes era órfão sem beat |
| Config do worker | Sidekiq 7.3.1, concorrência 12, filas: critical/high/medium/default/mailers/low/scheduled_jobs/deferred/… |
| sidekiq-alive | healthcheck ativo na porta 7433, registrado no Redis |

### Jobs processados nos primeiros segundos (sem erro fatal)
- `Channels::Whatsapp::BaileysConnectionCheckSchedulerJob` → **performed em 119ms** (monitor do WhatsApp/Baileys voltou a rodar)
- `ScheduledMessages::TriggerScheduledMessagesJob` → performed (nada a enviar — banco vazio)
- `Inboxes::FetchImapEmailInboxesJob` → performed (~42–72ms)

Todos completando em milissegundos, em loop normal de cron. **Nenhuma mensagem antiga disparada** (confirmado pelo pré-check: 0 conversas / 0 contatos / 0 mensagens agendadas).

---

## 3. Estado final

- 🟢 **Chatwoot ativo agora completo:** web (`chatwoot-fazerai`, 127.0.0.1:3003) + **Sidekiq processando** + Redis (db3) + Postgres — todos saudáveis.
- O processamento assíncrono (webhooks Evolution/Baileys, automações, IMAP, scheduled messages, notificações) está **restabelecido** após ~6 dias parado.

---

## 4. Pendências (propostas — não executadas)
1. **Persistir a política no compose:** o `docker update` vale para este container, mas o ideal é gravar `restart: unless-stopped` no arquivo compose do stack `chatwoot-fazerai`, para sobreviver a um `docker compose up` que recrie o container.
2. **Confirmar o papel da instância** (banco vazio): validar se `chatwoot-fazerai` é a instância oficial a ser usada.
3. **Limpeza** da stack antiga `chatwoot` / `chatwoot-sidekiq` (Exited).
4. **Alerta de container crítico parado:** este incidente passou 6 dias despercebido — reforça a recomendação do Censo Telegram de ter monitoramento que avise quando um serviço cai.

---
*Ação aplicada: `docker update` (política de restart) + `docker start`. Nenhuma imagem, código, banco, fila ou config de rede/SSH alterada.*
