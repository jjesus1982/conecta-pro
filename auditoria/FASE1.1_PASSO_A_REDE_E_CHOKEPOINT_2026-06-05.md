# Fase 1.1 — Passo A: rede conectada + chokepoint lido

- **Data:** 2026-06-05 ~18:58 UTC
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Resolver o bloqueio de rede backend↔Chatwoot e ler o ponto único de envio antes de repontar.
- **Resultado:** ✅ **Rede resolvida (a quente, sem recriar o backend).** Chokepoint mapeado linha a linha, pronto para repontar.

---

## 1. Rede conectada — bloqueio resolvido

Ação aplicada (aditiva, reversível):
```
docker network connect chatwoot-fazerai-net conecta-pro-backend
```

Prova (de dentro do `conecta-pro-backend`):
| Destino | Antes | Depois |
|---------|-------|--------|
| `http://chatwoot-fazerai:3000/api/v1/accounts/1/inboxes` | não resolvia | **HTTP 401** (alcançou; sem token = esperado) ✅ |
| `http://baileys-api:3025/status` | não resolvia | **HTTP 200** ✅ |

- Backend agora em **2 redes:** `chatwoot-fazerai-net` + `conecta-pro_conecta-pro-network`.
- Backend **seguiu `healthy`**, `StartedAt` inalterado (2026-05-30) → **não foi recriado** (sem risco de reverter código live-patched).

### ⚠️ Persistência (pendência)
A conexão via `docker network connect` é **runtime**: **não está no compose** (`refs_no_compose=0`). Se o `conecta-pro-backend` for recriado via `docker compose`, a rede se perde. **Persistir** depois, adicionando ao serviço no `docker-compose.yml`:
```yaml
  conecta-pro-backend:
    networks:
      - conecta-pro-network
      - chatwoot-fazerai-net   # adicionar
# e no topo:
networks:
  chatwoot-fazerai-net:
    external: true
```
Deixado para o próximo restart planejado do backend (evita recriar agora).
> Reverter a conexão a quente, se necessário: `docker network disconnect chatwoot-fazerai-net conecta-pro-backend`.

---

## 2. Chokepoint lido — `connectors/whatsapp/service.py`

Estrutura confirmada (175 linhas):
- **`__init__`**: `base_url=EVOLUTION_API_URL`, `api_key=EVOLUTION_API_KEY`, `instance=WHATSAPP_INSTANCE_ID`, `enabled=WHATSAPP_API_ENABLED`.
- **`_clean_phone`**: tira formatação e força DDI `55`.
- **`_send_message(phone, message)`** ← **ÚNICO ponto de transporte**:
  - guarda: se `not enabled` → "disabled"; se `not api_key` → "error".
  - `POST {base_url}/message/sendText/{instance}` com header `apikey`, payload `{"number","text"}`.
  - retorna dict `{status: sent|error|exception, ...}`.
- **Senders de alto nível** (só montam texto e chamam `_send_message`): `send_kit_notification`, `send_certificate_alert`, `send_nfse_notification`, `send_custom`.
- **`check_status`**: `GET {base_url}/instance/fetchInstances` (específico Evolution).
- Singleton de módulo: `whatsapp_service = WhatsAppService()`.

### Implicação para o repointing (Fase 1.1 passo B — PROPOSTA)
- **Reescrever apenas `_send_message`** (e `check_status`) para falar com o Chatwoot:
  - usar `CHATWOOT_BASE_URL=http://chatwoot-fazerai:3000`, `CHATWOOT_API_TOKEN` (bot user 2), `account_id=1`, `inbox_id=1`;
  - fluxo: buscar/criar contato por telefone → criar/abrir conversa no inbox 1 → `POST /conversations/{id}/messages`.
- **Os 4 senders e os endpoints HTTP `/send/*` ficam idênticos** (URLs de API inalteradas) — só muda o transporte interno.
- `check_status` passa a checar o Chatwoot/Baileys (`/status/auth`) em vez de `fetchInstances`.
- Trocar a leitura de env de `EVOLUTION_*` para `CHATWOOT_*` no `__init__`.

---

## 3. Estado da Fase 1.1
- [x] **Rede** backend ↔ chatwoot/baileys (a quente). ✅
- [x] **Bot + token** (user 2, agent) e IDs (`account_id=1`, `inbox_id=1`). ✅
- [x] **Chokepoint** lido e entendido. ✅
- [ ] Persistir a rede no compose (no próximo restart do backend).
- [ ] Adicionar `CHATWOOT_*` ao `backend/.env`.
- [ ] **Passo B:** repontar `_send_message`/`check_status` para o Chatwoot (com `docker cp` + restart, padrão do projeto) e reativar `WHATSAPP_API_ENABLED=true`.
- [ ] Consolidar senders duplicados (`diaristas`, `client_portal`).

---
*Ação aplicada: 1 `docker network connect` (reversível). Backend não recriado. Leitura de código (read-only). Nenhum outro serviço/config alterado.*
