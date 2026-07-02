# Fase 1.1-pré — Credenciais Chatwoot API, IDs e gap de rede (READ-ONLY)

- **Data:** 2026-06-05 ~18:24 UTC
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Levantar o que o backend precisa para enviar via Chatwoot API (IDs, token, conectividade).
- **Veredito:** IDs e token já existem; **mas há um bloqueio de rede** — backend e Chatwoot estão em redes Docker isoladas. Resolver isso é pré-requisito da migração.

---

## 1. IDs do inbox de destino
```
account_id = 1
inbox_id   = 1
name       = "Atendimento Conecta Mais"
```
A API de envio do Chatwoot usa: `POST /api/v1/accounts/1/conversations/{id}/messages` (e criação de conversa no inbox 1).

## 2. Token de API
- Existe **1 `access_token`**, `owner_type = User` (token pessoal do agente/Jordan).
- **Serve** para autenticar na API do Chatwoot (header `api_access_token`).
- **Recomendação:** criar um **agente "bot" dedicado** com token próprio (em vez de reusar o token pessoal) — melhor rastreabilidade e revogação.

## 3. Config no backend
- **Nenhuma var `CHATWOOT_*`** no `backend/.env` hoje → a migração precisa adicionar (ex.: `CHATWOOT_BASE_URL`, `CHATWOOT_ACCOUNT_ID=1`, `CHATWOOT_INBOX_ID=1`, `CHATWOOT_API_TOKEN`).

## 4. API do Chatwoot
- Responde em `http://127.0.0.1:3000` (dentro do container) → `GET /api/v1/accounts/1/inboxes` sem token = **401** (esperado; API viva).

---

## 5. 🚧 BLOQUEIO DE REDE (pré-requisito)

| Container | Rede Docker |
|-----------|-------------|
| `conecta-pro-backend` | `conecta-pro_conecta-pro-network` |
| `chatwoot-fazerai` | `chatwoot-fazerai-net` |
| `baileys-api` | `chatwoot-fazerai-net` |

Testes a partir do `conecta-pro-backend`:
- `chatwoot-fazerai` → **NÃO resolve** (DNS gaierror)
- `baileys-api` → **NÃO resolve** (DNS gaierror)
- Via gateway do host `172.17.0.1:3003` → **timeout** (porta publicada só em `127.0.0.1` do host)

**Conclusão:** as redes são **isoladas**. O backend, hoje, **não consegue falar** com o Chatwoot nem com a baileys-api. Isso vale tanto para a opção "Chatwoot API" quanto "Baileys direto".

### Como resolver (PROPOSTAS — nada executado)
1. **(Recomendada) Conectar o backend à rede `chatwoot-fazerai-net`** — no `docker-compose.yml` do backend, adicionar a rede externa `chatwoot-fazerai-net` ao serviço `conecta-pro-backend` (e workers que enviem). Depois o backend resolve `chatwoot-fazerai:3000` e `baileys-api:3025` por nome.
2. **Alternativa:** colocar `chatwoot-fazerai`/`baileys-api` também na `conecta-pro-network`.
3. **Alternativa (sem rede):** backend chama via HTTPS público `https://chat.conectamais.pro/api/...` — funciona (hairpin pelo nginx) mas adiciona latência e dependência de DNS/cert público.

> ⚠️ Conectar redes/recriar o backend = mudança que **recria o container** → atenção ao risco de reverter código live-patched (lição do flower). Avaliar `docker network connect` a quente (sem recriar) como caminho de menor risco para a rede, e aplicar a config no compose para persistir.

---

## 6. Checklist para a Fase 1 (migração de saída)
- [ ] Resolver a **rede** backend ↔ chatwoot/baileys (item 5).
- [ ] Criar **agente bot + token** dedicado no Chatwoot (ou reusar o token existente).
- [ ] Adicionar `CHATWOOT_BASE_URL`/`ACCOUNT_ID=1`/`INBOX_ID=1`/`API_TOKEN` ao backend.
- [ ] Repontar o chokepoint `connectors/whatsapp/service.py::_send_message` (do mapa da Fase 1-pré) para o Chatwoot.
- [ ] Consolidar os senders duplicados (`diaristas`, `client_portal`).
- [ ] Reativar `WHATSAPP_API_ENABLED=true` (hoje `false` após remover Evolution) apontando para o novo transporte.

---
*Read-only: `psql` SELECT, leitura de `.env`, `docker inspect` de redes e testes de socket/HTTP (sem efeito colateral). Nada alterado; token não exposto.*
