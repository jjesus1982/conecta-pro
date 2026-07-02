# Estabilização WhatsApp/Chatwoot — Tarefas 1, 2 e 3

- **Data:** 2026-06-08
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Escopo:** Senders duplicados (T1), rotação do segredo do webhook (T2), preparação do rebuild (T3).
- **Regras honradas:** read-only antes de escrita; backup antes de tocar sensível; **backend nunca recriado**; host==container confirmado; **parar nos gates e nas decisões de produto**.

---

# TAREFA 1 — Senders duplicados → 🟠 PARADA (decisão de produto)

**A premissa da missão não bateu com a realidade.** Li os dois arquivos inteiros (read-only). Nenhum é um "sender simples que chama Evolution e quebra". **Não editei nada** — reporto para o Jordan decidir.

### Arquivo 1 — `modules/operacional/diaristas/services/notificacao_service.py` (`_enviar_whatsapp`, linha 449)
- É um **STUB**: o código Evolution está **comentado** (linhas 461-468). O método só faz `logger.info(...)` e `return True`. **Nunca chamou Evolution; não quebra.**
- Repontá-lo para o cliente Chatwoot **ativaria envio real de WhatsApp para diaristas**, onde hoje **não envia nada**.
- ❓ **Decisão de produto:** vocês querem que as notificações de diarista passem a **enviar de verdade** via WhatsApp agora? (hoje é só log)

### Arquivo 2 — `modules/client_portal/controllers/whatsapp_controller.py`
- **Não é um sender** — é um **sistema legado completo**: webhook próprio (`POST /api/v1/portal/whatsapp/webhook`) que recebe payload **formato Evolution/Baileys** (`remoteJid`, `data.message.conversation`), roda **IA de auto-resposta** (`responder_com_ia`), casa cliente por `clients.whatsapp` e **cria tickets de suporte** (`client_portal_tickets`), respondendo via Evolution.
- O `_send_whatsapp_reply` (linha 193) já **no-opa** hoje (linha 202: `if not evolution_url: return` — e a URL está vazia). **Não quebra.**
- **Sem conflito de rota** com o webhook novo: legado em `/api/v1/portal/whatsapp/webhook`, novo em `/api/v1/whatsapp/webhook`.
- Repontar **só** o `_send_whatsapp_reply` para Chatwoot seria **incoerente**: o webhook espera payload Evolution (o Chatwoot não posta ali → nada chega). É um subsistema inteiro, não um sender.
- ❓ **Decisão de produto:** esse fluxo **WhatsApp→ticket+IA** ainda é desejado? Opções: **(a)** desativar/remover (morto); **(b)** migrar para receber do Chatwoot (reescrita grande); **(c)** deixar como está (dormante). E o `WhatsApp→Lead` (novo) vs `WhatsApp→ticket` (legado) — qual é a estratégia?

### Validação T1
- `grep EVOLUTION_API`: ambos ainda referenciam (arquivo 1 comentado; arquivo 2 ativo mas guardado por url vazia). **Nenhum edit feito** → sem diff, sem cp, sem restart.

---

# TAREFA 2 — Rotação do segredo do webhook → 🟢 PRONTO, aguardando gate manual

### Feito
- **Novo segredo** gerado (`openssl rand -hex 32`): `len=64, prefixo=750af6…`. Antigo: `prefixo=8ab9e3…`.
- **Backup do `.env`**: `.env.bak-secretrot-<ts>`.
- **`.env` atualizado** para o NOVO (durabilidade; o compose já passa `WHATSAPP_WEBHOOK_SECRET` ao backend num futuro rebuild). *Não ativa no runtime* — o container roda com env vazio e lê o **arquivo**.
- **NOVO staged** em `/app/.whatsapp_webhook_secret.new` nos **9 containers** (não ativa). **Arquivo ativo `/app/.whatsapp_webhook_secret` continua o ANTIGO.**
- Cópia de referência (host, 600): `/opt/conecta-pro/.webhook_secret.new`.

### Validação (prova de que a entrada NÃO quebrou)
| Teste no webhook | Resultado |
|------------------|-----------|
| `POST ?token=<ANTIGO>` | **200** (entrada segue ativa) ✅ |
| `POST ?token=<NOVO>` (staged) | **401** (ainda inativo) ✅ |
| arquivo ativo (backend) | prefixo `8ab9e3` (ANTIGO) ✅ |
| arquivo `.new` (backend) | prefixo `750af6` (NOVO) ✅ |

### 🚦 GATE MANUAL (não executei — para não derrubar a entrada)
Para ativar o segredo novo, **nesta ordem**:
1. **Atualizar a URL do webhook no Chatwoot** (via CIC/UI) com o NOVO token:
   `http://conecta-pro-backend:8080/api/v1/whatsapp/webhook?token=<NOVO>`
2. **Só então ativar** no backend (swap do arquivo — não precisa recriar):
   ```bash
   for c in conecta-pro-backend; do docker exec -u 0 $c sh -c 'cp /app/.whatsapp_webhook_secret.new /app/.whatsapp_webhook_secret'; done
   ```
   (o webhook lê o arquivo a cada request → ativa imediatamente; um `docker restart conecta-pro-backend` é opcional para também pegar o env.)
3. Validar: `POST ?token=<NOVO>` → 200; `?token=<ANTIGO>` → 401.
- **Até esse gate, o ANTIGO permanece ativo** e a entrada do Chatwoot funciona normalmente.
- Observação: o `WHATSAPP_WEBHOOK_SECRET` também é lido pelo webhook **legado** do portal (T1, arquivo 2) — dormante, sem impacto.

---

# TAREFA 3 — Rebuild da imagem → 🔵 PREPARAÇÃO read-only (NÃO buildei)

### Divergência imagem (30/mai, `bfa169a24c06`) vs container vivo
- **61 arquivos `.py` divergem**: **51 modificados** + **10 adicionados** (migrations).
- **Não são só do WhatsApp** — incluem models de `ai/`, `config/`, `notifications/`, `integrations/`, `services/`, `crm/`, `monitoring/`, `people_management/`, etc. A imagem está bem defasada.
- Migrations adicionadas: `camada3_*` (5), `drop_openclaw_tables`, `findp_b1b2_20260601`, `frente2_renames_20260530`, `sprint90_cwi_message_log`, `sprint91_lead_email_nullable`.
- Arquivos cp'ados não-código: `/app/.chatwoot_token`, `/app/.whatsapp_webhook_secret`, `/app/.whatsapp_webhook_secret.new`.

### O Dockerfile capturaria tudo? **SIM.**
- `backend/Dockerfile` linha 57: **`COPY --chown=erp:erp . .`** (não-seletivo) → copia todo o contexto do host para `/app`, incluindo `modules/` e `alembic/`.
- **host == container nos 61 arquivos (DRIFT=0, AUSENTE=0)** → o host é a fonte da verdade; um rebuild a partir do host **baka todos os 61 corretamente**.
- O `REBUILD_IMAGEM_2026-05-30.md` confirma o processo (mesmo Dockerfile, build do host, imagem antiga preservada por tag p/ rollback).

### O que faltaria / pontos de atenção
1. **Segredos NÃO seriam baked** (bom): `.whatsapp_webhook_secret`, `.chatwoot_token`, `.new` **não existem no contexto do host** → `COPY . .` não os inclui. Após rebuild+recreate, o container usaria os **env vars** (o compose já passa `CHATWOOT_API_TOKEN` e `WHATSAPP_WEBHOOK_SECRET` do `.env`). ⚠️ Confirmar que o env supre o token antes de aposentar os arquivos.
2. **`.dockerignore` não lista os arquivos de segredo** — recomendo **adicionar** `.whatsapp_webhook_secret*` e `.chatwoot_token` ao `.dockerignore` (defesa em profundidade, caso alguém os crie no host).
3. **Recreate só DEPOIS do rebuild bem-sucedido** — a imagem nova terá todo o código; recriar a partir dela é o único recreate seguro. Seguir o roteiro do doc de 30/mai (tag de rollback `pre-rebuild-<data>`, validar em container efêmero, swap do `:latest`, recreate, validar, rollback pronto).

### 🚦 GATE: rebuild NÃO executado
Conforme a missão, **não rodei `docker build` nem recriei nada**. O build será decidido com o Jordan após revisão desta lista.

---

# GATES PENDENTES (resumo)
| Item | Estado | Ação manual necessária |
|------|--------|------------------------|
| T1 — senders | 🟠 parado | decisão de produto (ativar diaristas? destino do fluxo portal legado?) |
| T2 — segredo | 🟢 pronto | atualizar URL no Chatwoot c/ novo token → swap do arquivo `.new` |
| T3 — rebuild | 🔵 preparado | aprovar e executar o build (roteiro do doc 30/mai) + `.dockerignore` dos segredos |

## Commit
- **Nada de código de aplicação foi alterado no host** (T1 parada; T2 mexeu só em `.env` (segredo, gitignored) + arquivos staged; T3 read-only). **Sem commit de código.** O `.env` com segredo **não** deve ir para git.

---
*T1: leitura read-only, zero edit (decisão de produto). T2: novo segredo gerado/staged, antigo ativo (entrada validada 200/401). T3: análise read-only, nenhum build/recreate. Segredos não expostos (só len+prefixo).*
