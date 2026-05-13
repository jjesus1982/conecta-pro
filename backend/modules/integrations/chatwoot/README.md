# Modulo `chatwoot_integration`

> **Status:** 🟡 Foundation (Slice 1)
> **PRD:** T5 v1.0 — Migracao Chatwoot fazer.ai + Integracao total Conecta PRO
> **Branch:** `feature/chatwoot-integration`
> **Owner:** Pedro Rafael ([@PedroRafael13](https://github.com/PedroRafael13))

## Visao geral

Modulo responsavel pela integracao bidirecional entre o **Conecta PRO** e o
**Chatwoot fazer.ai** (que opera o atendimento WhatsApp via baileys-api).

```
Conecta PRO  <-- webhooks ---  Chatwoot fazer.ai
             --- REST API -->  (chat.conectamais.pro)
```

Cobre os modulos do Conecta PRO:
- CRM (`/modulos/crm`) — Leads, clientes
- Marketing/Funil (`/modulos/marketing/funil`) — Cards de funil
- Vendas — Propostas, contratos
- Operacional (`/modulos/operacional`) — Ocorrencias, rondas
- Financeiro — Boletos, NFS-e, cobrancas

## Status do Slice 1 (esta PR)

Esta PR entrega **apenas a fundacao**: estrutura de pastas + esqueleto do
`ChatwootClient` + schema Pydantic de exemplo + este README.

**Objetivo:** Jordan revisar o approach e aprovar arquitetura **antes**
de a gente comprometer com migrations, env vars e infra.

### O que ja esta neste PR
- ✅ Estrutura do modulo (`backend/modules/integrations/chatwoot/`)
- ✅ `client.py` — esqueleto da classe `ChatwootClient`
- ✅ `schemas/webhook.py` — schema `CwiInboxEvent` como exemplo
- ✅ `README.md` (este arquivo)

### O que **NAO** esta (proximos slices)

| Slice | Conteudo | Bloqueio |
|---|---|---|
| 2 | Implementacao real do `ChatwootClient` + WebhookHandler com HMAC | Aprovacao do approach |
| 3 | Models SQLAlchemy das 7 tabelas (Sec. 6.1 do PRD) | Aprovacao + decisao schema |
| 4 | Migrations Alembic | Aprovacao p/ tocar `alembic/versions/` (arquivo proibido) |
| 5 | Workers Celery (inbox/outbox patterns) | Slice 4 mergeado |
| 6 | Features P0 (CRM-01, CRM-02, FUN-01, OPE-01/02, FIN-01/02, VEN-01) | Slice 5 mergeado |
| 7 | Frontend Sidebar (`/chatwoot-sidebar`) | Slice 6 mergeado |
| 8 | Features P1 | Slice 7 mergeado |

## Decisoes pendentes (Sec. 12 do PRD)

Antes de eu prosseguir pro Slice 2, Jordan precisa responder:

- **D-PEND-01:** Confirmar subdominio `chat.conectamais.pro`
- **D-PEND-02:** Quem controla DNS de `conectamais.pro`
- **D-PEND-03:** Chip/numero WhatsApp descartavel pra testes
- **D-PEND-04:** Esse numero pode ficar conectado por ~7 dias
- **D-PEND-05:** Confirmar capacidade do VPS (16GB RAM? 4 vCPUs?)
- **D-PEND-06...09:** demais decisoes da Sec. 12

## Como rodar localmente (quando estiver pronto)

> **Atencao:** ainda nao funcional. Estrutura apenas.

```bash
# Criar tabelas (requer Slice 4 mergeado)
cd backend
alembic upgrade head

# Subir backend
uvicorn main:app --reload --port 8080

# Webhook do Chatwoot apontar pra
# http://localhost:8080/api/v1/integrations/chatwoot/webhook
```

## Como contribuir

1. Pull a branch `feature/chatwoot-integration` do fork `PedroRafael13/conecta-pro`
2. Mudancas em sub-slices: criar branch derivada (`feature/chatwoot-integration-slice2-client`)
3. PR pro upstream `jjesus1982/conecta-pro` com base `feature/chatwoot-integration`
4. Apos todos slices mergeados nessa branch, abrir PR final pra `main`

## Referencias

- **PRD completo:** Mensagem do Jordan de 2026-05-08, T5 v1.0
- **Repo fazer.ai Chatwoot:** https://github.com/fazer-ai/chatwoot
- **Repo fazer.ai baileys-api:** https://github.com/fazer-ai/baileys-api
- **Chatwoot API docs:** https://www.chatwoot.com/developers/api/
