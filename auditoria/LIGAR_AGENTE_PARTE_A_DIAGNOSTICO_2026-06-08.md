# Ligar o agente WhatsApp — Parte A (diagnóstico, NADA editado)

- **Data:** 2026-06-08
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Preparar a habilitação do agente (Fase A) no compose. Parte A = só diagnóstico + backup.
- **Status:** ⏸️ **Parado para sua revisão.** Compose NÃO editado, backend NÃO recriado.

---

## 1. Feito (seguro)
- **Backup do compose:** `docker-compose.yml.bak-agent-20260608_180428`.
- Inspeção do bloco `environment` do backend (read-only).

## 2. Estado atual do compose (vars do agente)
- `OPENAI_API_KEY: ${OPENAI_API_KEY:-}` **já existe** (linha 107, seção "Bartolo AI - LLM Configuration").
- `AGENT_ENABLED`, `OPENAI_AGENT_MODEL`, `AGENT_MAX_HISTORY`, `AGENT_MAX_TOKENS` → **ainda NÃO estão** no compose.

Bloco (linhas ~106-113):
```yaml
      # Bartolo AI - LLM Configuration
      LLM_PROVIDER: ${LLM_PROVIDER:-openai}
      OPENAI_API_KEY: ${OPENAI_API_KEY:-}          # linha 107 (já existe)
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:-}
      LLM_MODEL: ${LLM_MODEL:-gpt-4o-mini}
      LLM_MAX_TOKENS: ${LLM_MAX_TOKENS:-2000}
      LLM_TEMPERATURE: ${LLM_TEMPERATURE:-0.7}
      LLM_FALLBACK_ENABLED: ${LLM_FALLBACK_ENABLED:-true}   # fim do bloco LLM
```

## 3. Proposta de inserção (Parte B, sob sua aprovação)
Adicionar logo após `LLM_FALLBACK_ENABLED`:
```yaml
      # Agente WhatsApp (Fase A — copiloto)
      AGENT_ENABLED: ${AGENT_ENABLED:-false}
      OPENAI_AGENT_MODEL: ${OPENAI_AGENT_MODEL:-gpt-4o-mini}
      AGENT_MAX_HISTORY: ${AGENT_MAX_HISTORY:-20}
      AGENT_MAX_TOKENS: ${AGENT_MAX_TOKENS:-500}
```

## 4. ⚠️ Pontos críticos da Parte B (precisam da sua decisão)
1. **Ligar de fato exige `AGENT_ENABLED=true` no `.env`.** Hoje o `.env` está `AGENT_ENABLED=false` → mesmo adicionando ao compose, o agente fica **desligado** até mudar para `true`.
   - **Decisão:** mudo o `.env` para `true` (liga de fato) ou deixo `false` (só prepara, liga depois)?
2. **O recreate aplica a chave OpenAI NOVA.** O container ainda tem em memória a chave **antiga (inválida, 401)**; o recreate puxa a NOVA (válida) do `.env`. Sem o recreate, o agente não conseguiria chamar a OpenAI em produção.
3. **Recreate é seguro agora** (pós-rebuild: a imagem tem todo o código baked). Mas há **breve downtime da API** (~30-60s).
4. Mesmo ligado, é **copiloto**: gera sugestão → nota privada no Chatwoot + rascunho. **Não envia ao cliente.**

## 5. O que falta eu fazer na Parte B (quando aprovar)
1. (Se você quiser ligar) `AGENT_ENABLED=true` no `.env`.
2. Editar o compose (inserir as 4 vars — §3).
3. `docker compose up -d --no-deps --no-build backend` (recreate).
4. Validar: vars no env do container, chave OpenAI nova ativa, e um teste real (mensagem sua → sugestão vira nota privada, sem ir ao cliente).

---
*Parte A: só backup do compose + leitura. Nada editado, nada recriado. Aguardando sua decisão sobre AGENT_ENABLED e autorização para editar o compose + recreate.*
