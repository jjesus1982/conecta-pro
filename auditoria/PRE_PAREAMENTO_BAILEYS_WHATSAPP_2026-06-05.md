# Pré-Pareamento — Como o Baileys expõe o pareamento WhatsApp (READ-ONLY)

- **Data:** 2026-06-05 ~16:18 UTC
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Escopo:** Entender como parear o WhatsApp via Baileys e qual o estado atual. Nenhuma alteração feita; nenhuma sessão iniciada.
- **Veredito:** 🟡 **Baileys está de pé e saudável, mas SEM sessão WhatsApp pareada e SEM canal configurado no Chatwoot.** O pareamento (QR/código) é conduzido pela UI do Chatwoot, não por chamada direta à API.

---

## 1. O serviço Baileys

| Item | Valor |
|------|-------|
| Container | `baileys-api` — `Up 6 days (healthy)` |
| Imagem | `ghcr.io/fazer-ai/baileys-api:latest` (**v3.1.5**, runtime Bun/Elysia) |
| Porta | `127.0.0.1:3025` (loopback — não exposto à internet) |
| Healthcheck | `wget --spider http://127.0.0.1:3025/status` → **200** a cada 30s |
| Persistência de sessão | **Redis db4** (`REDIS_URL=redis://…/4`, no `chatwoot-fazerai-redis`) |

> Observação: `docker logs baileys-api` trava (driver de log); os logs foram lidos direto do arquivo `-json.log`. Os `404` em `/` e `/health` no log são apenas as sondagens deste diagnóstico — as rotas reais são outras (ver §3).

---

## 2. Estado atual: nada pareado

| Checagem | Resultado | Significado |
|----------|-----------|-------------|
| Redis **db4** (`dbsize`) | **0 chaves** | **nenhuma credencial/sessão WhatsApp** — nunca pareado (ou deslogado) |
| Chaves `baileys*` / `*creds*` (todos os db) | nenhuma | idem |
| Chatwoot `inboxes` | **0** | nenhuma caixa de entrada configurada |
| Chatwoot `channel_whatsapp` | **0** | **nenhum canal WhatsApp/Baileys criado** |
| Banco `chatwoot_fazerai` | vazio (0 conversas/contatos/mensagens) | instância nunca operou WhatsApp |

**Conclusão:** o WhatsApp nunca foi conectado nesta instância. Não há o que "reconectar" — é um **pareamento do zero**.

---

## 3. Como o pareamento é exposto

A baileys-api da fazer.ai é uma API **multi-sessão dirigida pelo Chatwoot** (fork fazer-ai com canal Baileys nativo). O fluxo correto de pareamento é:

1. No Chatwoot ativo (`https://chat.conectamais.pro`) → **Configurações → Caixas de entrada → Adicionar → WhatsApp**, provider **Baileys** (fazer-ai).
2. O Chatwoot chama a `baileys-api` (em `127.0.0.1:3025`) para **criar a conexão da sessão**.
3. A baileys-api gera o **QR Code** (ou **código de pareamento** por número) e o Chatwoot **exibe na própria tela**.
4. Você escaneia com o WhatsApp do celular (Aparelhos conectados → Conectar aparelho).
5. A sessão autenticada passa a ser persistida no **Redis db4**; a partir daí mensagens fluem Baileys ↔ Chatwoot (com o Sidekiq, agora ativo, processando os jobs/webhooks).

> O endpoint `/status` é só saúde/info (config da API). As rotas de sessão/QR são acionadas pelo Chatwoot — **não recomendo** chamá-las direto via curl, pois isso **iniciaria** uma sessão (sairia do modo read-only).

### Dependências já prontas para o pareamento
- ✅ baileys-api healthy (3025) + Redis db4 acessível.
- ✅ **Sidekiq do Chatwoot religado hoje** — necessário para processar os jobs/webhooks do canal (sem ele, mensagens não fluiriam).
- ✅ Chatwoot web no ar (`chat.conectamais.pro` → 127.0.0.1:3003, HTTPS).

---

## 4. Recomendações (propostas — nada executado)
1. **Parear pela UI do Chatwoot** (passo a passo do §3) — caminho oficial e seguro; evita mexer direto na API.
2. **Antes de parear, confirmar o papel da instância** `chatwoot-fazerai` (está vazia): é ela a oficial para o WhatsApp da operação? (Existe ainda a stack antiga `chatwoot`/`chatwoot-postgres` separada.)
3. **Definir o provider oficial de WhatsApp:** o `backend/.env` aponta para **Evolution API** (`EVOLUTION_API_URL`), enquanto o Chatwoot usaria **Baileys**. Vale alinhar qual é o canal de produção para não manter dois caminhos concorrentes.

---
*Read-only: `docker inspect`, leitura de log em arquivo, `redis-cli dbsize/keys`, `psql` SELECT e `GET /status`. Nenhuma sessão foi iniciada; nenhum container/banco/config alterado.*
