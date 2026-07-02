# Pré-Religação do Sidekiq — O que ele reenfileiraria? (READ-ONLY)

- **Data:** 2026-06-05 ~15:40 UTC
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Antes de religar o `chatwoot-fazerai-sidekiq` (parado desde 29/mai), verificar **o que dispararia** ao subir — evitar enviar mensagens antigas a clientes.
- **Veredito:** 🟢 **Religar é SEGURO.** A instância está vazia; não há mensagens agendadas, campanhas nem conversas para reprocessar.

---

## 1. Cron jobs registrados (sidekiq-cron)

São agendamentos **estáticos** do Chatwoot (configuração, não backlog). Ao subir, voltam ao ciclo normal:

| Cron job | Natureza |
|----------|----------|
| `trigger_scheduled_messages_job` | dispara mensagens agendadas (ver §2 — não há nenhuma) |
| `trigger_scheduled_items_job` / `trigger_hourly_scheduled_items_job` | itens agendados |
| `trigger_imap_email_inboxes_job` | busca e-mail IMAP |
| `periodic_assignment_job` | atribuição automática de conversas |
| `remove_orphan_conversations_job` / `remove_stale_contact_inboxes_job` / `remove_stale_redis_keys_job` | limpeza/manutenção |
| `remove_old_notification_job` | limpeza de notificações |
| `delete_accounts_job` | exclusão de contas agendadas |
| `internal_check_new_versions_job` | checagem de versão |

> São rotinas de manutenção/operação — nenhuma delas envia mensagem a cliente por conta própria. A única que enviaria (`trigger_scheduled_messages_job`) depende de haver mensagens agendadas, e **não há** (§2).

---

## 2. Dados no banco `chatwoot_fazerai` (instância ATIVA)

Usuário/db corretos: `chatwoot` / `chatwoot_fazerai` (o `postgres`/`chatwoot_production` do bloco original era de outra instância).

| Item | Contagem | Significado |
|------|---------:|-------------|
| `conversations` | **0** | nenhuma conversa |
| `contacts` | **0** | nenhum contato |
| `messages` | **0** | nenhuma mensagem (nem nos últimos 7 dias) |
| `conversas_abertas` (status=0) | **0** | nada aberto |
| `campaigns_total` / `campaigns_pendentes` | **0 / 0** | nenhuma campanha |
| `scheduled_messages` (linhas) | **0** | **nenhuma mensagem agendada** |

**A instância `chatwoot-fazerai` está completamente vazia / sem uso real.**

---

## 3. Conclusão para a decisão

- **Risco de disparar mensagens antigas a clientes ao religar: NENHUM.** Não há conversas, contatos, campanhas nem mensagens agendadas. A ressalva levantada no diagnóstico anterior (revisar antes de subir) **fica descartada** — não há o que reprocessar.
- Ao subir o Sidekiq, ele apenas retoma os cron jobs de manutenção e fica disponível para processar tráfego **novo**.
- **Observação:** como o Chatwoot ativo está vazio, vale também a pergunta de negócio — esta instância está realmente em uso/produção, ou é um ambiente ainda não populado? (Há ainda a stack antiga `chatwoot`/`chatwoot-postgres` com o db `chatwoot_production`, separada.)

---

## 4. Recomendações (PROPOSTAS — nada executado)
1. **Religar o `chatwoot-fazerai-sidekiq`** com segurança (sem pré-limpeza necessária), garantindo `restart: unless-stopped` no compose para não ficar para trás em futuros restarts.
2. **Confirmar o papel desta instância** (vazia): se é a oficial a popular, ou se a stack antiga é que deveria estar ativa.
3. Manter no radar a limpeza da stack antiga `chatwoot`/`chatwoot-sidekiq` (Exited).

---
*Read-only. Consultas via `redis-cli` e `psql` somente leitura (SELECT/keys). Nenhum container, fila, banco ou config foi alterado.*
