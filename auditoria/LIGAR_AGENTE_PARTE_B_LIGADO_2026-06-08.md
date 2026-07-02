# Ligar o agente WhatsApp — Parte B: AGENTE LIGADO (copiloto) + regressão corrigida

- **Data:** 2026-06-08
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Habilitar o agente (Fase A) — compose + `.env` + recreate.
- **Resultado:** ✅ **Agente LIGADO e funcionando ao vivo (copiloto).** ⚠️ **Mas a imagem está stale → frágil a recreate (precisa re-rebuild).**

---

## 1. O que foi feito
1. **Compose** (`docker-compose.yml`, backup `…bak-agent-20260608_180428`): inseridas 4 vars após `LLM_FALLBACK_ENABLED` (linhas 114-117):
   `AGENT_ENABLED`, `OPENAI_AGENT_MODEL=gpt-4o-mini`, `AGENT_MAX_HISTORY=20`, `AGENT_MAX_TOKENS=500`. **YAML validado** (`docker compose config` OK).
2. **`.env`** (backup `.env.bak-agenton-…`): `AGENT_ENABLED=false → true`.
3. **Recreate do backend** (`docker compose up -d --no-deps --no-build backend`) → pegou as 4 vars + a **chave OpenAI NOVA** (válida) do `.env`.

## 2. 🔴 Regressão detectada e corrigida (importante)
- O recreate puxou a imagem `47b3f70359a5` (buildada **15:08**), que **NÃO contém** o `agent_service.py` nem o hook do agente no controller (foram criados **depois** do rebuild, via `docker cp`). Resultado pós-recreate: `ImportError: agent_service` — **o agente sumiu do container**.
- A **entrada (Fase 2)** continuou intacta (está baked na imagem) — webhook 200, dados OK.
- **Correção:** re-deploy do `agent_service.py` + `controller.py` (host → backend) por `docker cp` + `docker restart` (**sem recriar**). **host == container** confirmado.

## 3. Agente LIGADO — prova ao vivo (webhook → agente)
- `agent_enabled() = True`; chave OpenAI **nova ativa no container** (gera sem override).
- POST `message_created` (incoming) no webhook → **200 rápido** (background não bloqueia).
- O BackgroundTask gerou o rascunho com a **persona v2**:
  > "Olá! Fico feliz em ajudar você com isso. Para entender melhor suas necessidades, poderia me informar alguns detalhes? 1. Qual é o porte da sua empresa?…"
  (qualificando, on-brand, sem preço).
- **Copiloto confirmado:** entrega como rascunho `drf` + nota privada — **não envia ao cliente**.
- Dados de teste limpos.

## 4. Gates de produção (OK)
| Gate | Resultado |
|------|-----------|
| `/health` | 200 |
| webhook `?token=<ativo>` | 200 |
| backend | running/healthy, IMG `47b3f7`, RestartCount=0 |
| 4 vars `AGENT_*` no container | presentes (`AGENT_ENABLED=true`) |
| dados | `cwi_message_log=20`, `leads whatsapp=5` (intactos) |

## 5. ⚠️ CRÍTICO — imagem stale, agente FRÁGIL a recreate
- A imagem `conecta-pro-backend:latest` (`47b3f7`) **NÃO tem** `agent_service.py` (confirmado).
- O agente roda hoje porque foi **re-cp'ado** no container vivo. **Qualquer recreate do backend (ex.: deploy futuro) reverteria o agente de novo.**
- **Recomendação forte (próximo passo):** **re-rebuild da imagem** para bakar o agente (agent_service.py + controller com hook + prompt v2). O processo já é conhecido (build com tag → validar efêmero → swap → up --no-deps). Enquanto não for feito, evitar `--force-recreate` do backend; usar `docker cp` + `restart`.

## 6. Backups / rollback
- Compose: `docker-compose.yml.bak-agent-20260608_180428`.
- `.env`: `.env.bak-agenton-…`.
- Desligar o agente: `AGENT_ENABLED=false` no `.env` + restart (ou recreate).
- Backup do banco do dia: `backups/rebuild/pre_rebuild_20260608_150847.dump`.

## 7. Pendências
- **Re-rebuild da imagem** (durabilidade do agente) — recomendado.
- 🔐 Rotacionar a chave OpenAI (foi colada no chat).
- Acompanhar custo (cada mensagem de entrada agora gera 1 chamada OpenAI enquanto `AGENT_ENABLED=true`).

---
*Parte B: compose (4 vars, YAML validado) + `.env` (AGENT_ENABLED=true) + recreate. Regressão do agente (imagem stale) corrigida por re-cp + restart. Agente ao vivo em modo copiloto, validado ponta a ponta. host==container. Imagem precisa de re-rebuild para durabilidade.*
