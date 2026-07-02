# RAIO-X DO ESTADO REAL — Central de Atendimento (Chatwoot/WhatsApp) — READ-ONLY

**Gerado:** 2026-06-05 (arquivo nomeado conforme solicitado). **Tipo:** inventário read-only, nada alterado. **Base de comparação:** PRD T5 Chatwoot fazer.ai de 2026-05-08.

---

## VEREDITO EM 1 LINHA
A Fase 1 (5 containers fazer.ai) **foi provisionada e sobreviveu à limpeza** (4/5 healthy), **a RAM destravou** (90% → 60,8%, 12,3 GB livres), **MAS** a stack nova está **VAZIA** (0 inbox, 0 mensagem — nunca conectou WhatsApp) e o atendimento que de fato operou (vanilla Chatwoot + Evolution) foi **parado na limpeza de 29/mai**. Hoje **nenhuma stack está atendendo WhatsApp ativamente**. O T5-F2 está **destravado de RAM**, mas tem pré-requisitos de configuração antes de retomar.

---

## PASSO 1 — CONTAINERS HOJE

### Stack NOVA (alvo fazer.ai) — provisionada, 4/5 de pé
| Container | Status | Porta | RAM |
|---|---|---|---|
| `chatwoot-fazerai` | 🟢 Up 6d (healthy) | 127.0.0.1:3003→3000 | 385 MB |
| `chatwoot-fazerai-postgres` (pgvector pg16) | 🟢 Up 6d (healthy) | 127.0.0.1:5433→5432 | 40 MB |
| `chatwoot-fazerai-redis` | 🟢 Up 6d (healthy) | 6379 | 10 MB |
| `baileys-api` | 🟢 Up 6d (healthy) | 127.0.0.1:3025→3025 | 100 MB |
| `chatwoot-fazerai-sidekiq` | 🔴 **Exited (137)** 29/mai | 3000 | — |

### Stack ANTIGA (a aposentar) — parcialmente viva
| Container | Status | Porta | RAM |
|---|---|---|---|
| `evolution-api` | 🟡 Up 6d (sem health) | **0.0.0.0:8081**→8080 | 99 MB |
| `chatwoot-postgres` (vanilla DB) | 🟢 Up 6d (healthy) | 5432 | 37 MB |
| `chatwoot` (vanilla web) | 🔴 **Exited (137)** 29/mai | 0.0.0.0:3002→3000 | — |
| `chatwoot-sidekiq` (vanilla) | 🔴 **Exited (137)** 29/mai | 3000 | — |

**Total de RAM da stack de atendimento rodando hoje: ~670 MB** (irrisório).

> **Causa dos Exited (137):** `OOMKilled=false` nos 3, e todos pararam no **mesmo instante (2026-05-29 20:33)** → foi **parada deliberada (docker stop)** na limpeza, **não** crash de RAM. Ou seja, podem ser reiniciados.

## PASSO 2 — RAM (o que bloqueou o T5-F2)
- **Hoje: 31 GB total, 19 GB usados (60,8%), 12,3 GB disponíveis.** Swap quase zerado (154 MB).
- **PRD dizia ~90% (bloqueio).** → **A limpeza recente resolveu**: caíram ~30 pontos percentuais.
- **Top consumidores:** ~12 processos `python3.12` de ~1 GB cada (= `conecta-pro-backend` + 7 workers Celery + flower, cada um carrega o app inteiro) ≈ 12 GB; `clamd` ~1 GB. **A stack de atendimento NÃO é a vilã de RAM** (usa <0,7 GB).
- **Veredito RAM:** subir os ~5-6 containers fazer.ai cabe folgado (eles já estão de pé usando <0,7 GB). **O bloqueio de RAM do T5-F2 não existe mais.**

## PASSO 3 — CONECTIVIDADE E DOMÍNIO
- `https://chat.conectamais.pro` → **HTTP/2 200** (nginx). **Cert Let's Encrypt (E7) válido**: 26/mai/2026 → **24/ago/2026**. (Provavelmente faz proxy para `chatwoot-fazerai:3003` — *confirmar upstream no nginx*.)
- `baileys-api` (3025) → responde (404 na raiz com headers CORS = serviço vivo, sem rota `/`). 🟢 vivo.
- `chatwoot-fazerai` (3003) → **HTTP 200**. 🟢 vivo (mas vazio).
- **Onde está o número WhatsApp (sem enviar mensagem):**
  - **Stack que operou de verdade = a ANTIGA.** `chatwoot_production` (vanilla) tem **1 inbox** ("WhatsApp 0800 880 4414", `Channel::Api`), **7 conversas, 111 mensagens**.
  - Instância **Evolution** `conecta-pro` (DB `evolution_api` em conecta-pro-postgres): `connectionStatus = "connecting"` → **não está "open"/conectada agora** (limbo).
  - **Stack NOVA (fazer.ai): 0 inbox, 0 channel_whatsapp, 0 conversa, 0 mensagem** — nunca conectou o número.
  - ⚠️ Divergência de número: PRD cita **+55 92 98221-4414**; o inbox vanilla está rotulado **"0800 880 4414"**. *Re-confirmar qual número/instância.*

## PASSO 4 — INTEGRAÇÃO COM O CONECTA PRO (O-02..O-09 do PRD)
- **Rotas no backend (8), todas via Evolution API:**
  `/notifications/webhooks/whatsapp`, `/portal/whatsapp/config`, `/portal/whatsapp/webhook`, `/whatsapp/send/{certificate-alert,custom,kit-notification,nfse-notification}`, `/whatsapp/status`.
  → São **disparos de saída (notificações)** + webhooks. O `backend/.env` rotula explicitamente "WhatsApp API (Evolution API)".
- **Tabela `cwi_message_log` (D-18 do PRD): NÃO EXISTE.** Só há `assistant_conversations` e `chatbot_conversations` (IA interna, não Chatwoot). → **A integração profunda CRM↔atendimento (O-02..O-09) não foi para o banco.**
- **CRM (`/modulos/crm`): desconectado do atendimento**, como o PRD já descrevia (sistemas em paralelo). Nenhum vínculo cwi_*/inbox↔lead.
- **Chaves no `.env` (só nomes):** `CHATWOOT_URL`, `CHATWOOT_SECRET_KEY`, `EVOLUTION_API_KEY/URL/DATABASE_URL/INSTANCE`, `WHATSAPP_API_ENABLED/INSTANCE_ID/NUMBER/WEBHOOK_SECRET`. → backend cabeado ao **Evolution + Chatwoot (genérico)**, **não ao baileys/fazer.ai**.

## PASSO 5 — DIFF: PRD (8/mai) × REALIDADE (hoje)
| Item do PRD | Estado hoje |
|---|---|
| Fase 1: 5 containers fazer.ai provisionados | ✅ Provisionados e **sobreviveram** — 4/5 healthy; **sidekiq parado** (docker stop 29/mai) |
| Bloqueio de RAM do T5-F2 (~90%) | ✅ **Resolvido** pela limpeza — 60,8%, 12,3 GB livres |
| Migração Evolution→baileys | ❌ **Não ocorreu** — número nunca migrou; fazer.ai vazio; backend ainda no Evolution |
| Stack antiga removida | ❌ **Ainda existe**: evolution-api UP, chatwoot-postgres UP; vanilla web/sidekiq parados (29/mai) |
| Subdomínio chat.conectamais.pro + cert | ✅ Vivo, HTTP 200, cert LE válido até 24/ago |
| Operação real (inbox/conversas) | Vivia na **vanilla** (1 inbox, 7 conv, 111 msg) — hoje **parada** (web/sidekiq down) |
| cwi_message_log + integração CRM | ❌ Não existe — integração não implementada |

### O que RE-VERIFICAR antes de retomar (PRD tem 1 mês, servidor mudou)
1. **Decidir a stack canônica:** seguir com fazer.ai (vazio, precisa conectar) ou voltar a ligar a vanilla (tem as 111 msg/7 conversas reais)? As duas estão paradas em peças diferentes.
2. **Reativar o sidekiq** da stack escolhida (sem ele Chatwoot não processa jobs/webhooks/automação). Foi só `docker stop`, deve subir.
3. **Conectar o WhatsApp na fazer.ai** (baileys → inbox) — nunca foi feito; confirmar qual número (92 98221-4414 vs 0800).
4. **Estado da instância Evolution** "connecting" — destravar ou aposentar.
5. **Confirmar upstream do nginx** de chat.conectamais.pro (fazerai 3003?).
6. **Preservar dado da vanilla** antes de remover (7 conversas/111 msgs reais) se a decisão for migrar para fazer.ai.
7. **Wire backend↔fazer.ai** se adotar a nova: hoje o `.env`/rotas apontam para Evolution.

## VEREDITO FINAL
- **RAM: destravada.** O bloqueio que parou o T5-F2 não existe mais (60,8%, 12,3 GB livres; a stack toda usa <0,7 GB).
- **Infra fazer.ai: de pé, mas inerte** (4/5 healthy, sidekiq parado, **zero configuração/tráfego**).
- **Pré-requisitos antes de retomar o T5-F2 (não é só "continuar"):** (a) reativar o `chatwoot-fazerai-sidekiq`; (b) conectar o número WhatsApp no baileys→inbox; (c) decidir o destino da stack antiga (e preservar as 111 msgs vanilla); (d) confirmar nginx upstream + número correto. **Destravado de RAM, mas com configuração pendente — não está pronto pra "só seguir".**
