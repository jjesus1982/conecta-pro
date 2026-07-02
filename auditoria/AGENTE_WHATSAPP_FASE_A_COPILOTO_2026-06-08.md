# Agente de atendimento WhatsApp — Fase A (COPILOTO) — IMPLEMENTADA

- **Data:** 2026-06-08
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Escopo:** Agente lê a conversa e **GERA** uma sugestão de resposta, entregue em modo **copiloto** (NÃO envia ao cliente).
- **Resultado:** ✅ **Funcionando e testado.** Desligado em produção (`AGENT_ENABLED=false`) até seu OK.

---

## 1. Arquivos
| Arquivo | Mudança |
|---------|---------|
| `modules/integrations/connectors/whatsapp/agent_service.py` | **NOVO** — serviço do agente |
| `modules/integrations/connectors/whatsapp/controller.py` | webhook agenda o agente (BackgroundTasks) + guard de `private` |
| Backup pré-FA do controller | `controller.py.bak-preFA-<ts>` |
| Commit | `84c59d07 feat(whatsapp): agente copiloto Fase A` (só os 2 arquivos; `.env` é gitignored) |

## 2. Como funciona
1. `gerar_resposta(conversation_id)`:
   - Lê o histórico de `cwi_message_log` por `chatwoot_conversation_id` (últimas `AGENT_MAX_HISTORY`, só `in`/`out` reais), monta `messages[]` (in→user, out→assistant).
   - Chama OpenAI (`OPENAI_AGENT_MODEL`, default `gpt-4o-mini`) com a **persona Conecta Mais** e guard-rails (nunca preço/prazo; conduzir para visita; assumir que é assistente virtual se perguntado; nunca inventar).
   - Retorna o texto. Falha → `None` (nunca derruba o webhook). Loga tokens (custo).
2. **Entrega copiloto** (`processar_incoming`): **NÃO envia ao cliente** — entrega como:
   - **Nota PRIVADA** na conversa do Chatwoot (`private:true`; cliente não vê, atendente vê no painel).
   - **Rascunho** em `cwi_message_log` com `direction='drf'` (rastreio/revisão).
3. **Webhook:** em `direction=="in"` e se `AGENT_ENABLED=true`, agenda `processar_incoming` em **BackgroundTasks** (não bloqueia o 200). Novo **guard**: ignora mensagens `private` (não loga/reprocessa → sem poluir histórico nem loop).

## 3. Config por ENV (nada hardcoded)
- `OPENAI_API_KEY` — **configurada e validada** (chave nova fornecida; já no `/opt/conecta-pro/.env`). *Valor não incluído neste relatório.*
- `OPENAI_AGENT_MODEL=gpt-4o-mini`, `AGENT_ENABLED=false`, `AGENT_MAX_HISTORY=20`, `AGENT_MAX_TOKENS=500`.

## 4. Validação (sem tocar cliente real)
| Teste | Resultado |
|-------|-----------|
| `gerar_resposta(5)` (conversa real) | **OpenAI 200**, resposta coerente e on-brand; `tokens_in=224 tokens_out≈30` (custo logado) |
| `processar_incoming(5)` (entrega copiloto) | rascunho `drf` gravado + **nota privada postada** (conv 5, `private=true`) |
| webhook incoming normal | **200** (rápido; agente OFF em prod) |
| webhook mensagem `private=true` | `{"status":"ignored_private"}` ✅ |
| chave OpenAI antiga (estava no container) | **inválida (401)** — por isso a troca; erro tratado (retorna `None`, não derruba) |
| `agent_enabled()` em produção | **False** (gated) |
| host==container | ✅ | backend | healthy |

**Evidências (artefatos de teste, podem ser limpos):** 1 linha `direction='drf'` em `cwi_message_log` + 1 nota privada na conversa 5 do Chatwoot (visível no painel como "🤖 Sugestão do assistente").

## 5. 🚦 GATES (não executados — aguardando seu OK)
1. **Ligar o agente em produção** (`AGENT_ENABLED=true`):
   - **(a)** Adicionar ao bloco env do backend no `docker-compose.yml` (⚠️ **zona proibida** — precisa da sua autorização): `AGENT_ENABLED`, `OPENAI_AGENT_MODEL`, `AGENT_MAX_HISTORY`, `AGENT_MAX_TOKENS` (o `OPENAI_API_KEY` já passa, linha 107).
   - **(b)** `docker compose up -d --no-deps --no-build backend` (recreate — **agora seguro** pós-rebuild; pega a chave OpenAI NOVA do `.env` + `AGENT_ENABLED=true`).
   - **Importante:** o container em produção ainda tem a chave OpenAI **antiga (inválida)** em memória; só o recreate aplica a nova do `.env`. (Por isso testei via override de env.)
2. **NÃO avançar para F-B** (envio automático / tools) sem decisão.

## 6. 🔐 Recomendação de segurança (importante)
A chave OpenAI foi colada em texto no chat → ficou no histórico da conversa. **Recomendo rotacioná-la** no painel da OpenAI após esta sessão (gerar nova, revogar a atual) e atualizar o `.env`. No futuro, prefira colocar segredos direto no `.env` do servidor.

## 7. Pendências relacionadas (não-F-A)
- T1 senders duplicados (decisão de produto), T2 rotação do segredo do webhook (parqueada) — separadas.

---
*F-A: 2 arquivos (novo serviço + hook no webhook), deploy por docker cp + restart (sem recriar), host==container, commit. Agente OFF em produção. Chave configurada no env (valor não exposto). Testado sem enviar ao cliente.*
