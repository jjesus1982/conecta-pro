# F-B.1 pré — Mapa para dar "tools" ao agente WhatsApp (READ-ONLY)

- **Data:** 2026-06-09
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Mapear o que já existe para o agente usar ferramentas (function calling) — sem duplicar nada.
- **Veredito:** Infra de reuso existe (BrasilAPI + repo de clientes). Mas **o escopo exato das tools é decisão de produto** — não inventei.

---

## 1. BrasilAPI — JÁ EXISTE (reusar, não duplicar)
`modules/integrations/brasilapi/` é um pacote completo: `client.py`, `schemas.py`, `exceptions.py`, **`circuit_breaker.py`**, **`cache.py`**.
- `class BrasilAPIClient(timeout_seconds=5.0)`
- **`async def get_cnpj(cnpj) -> tuple[CNPJResponse, bool]`** — valida CNPJ, usa **cache**, **circuit breaker** e retry. Retorna `(resposta, veio_do_cache)`.
- Também `get_cep(cep)`, `get_taxas()`.
- ➜ A tool `consultar_cnpj` do agente = `await BrasilAPIClient().get_cnpj(cnpj)`. **Async, pronta pra reuso.**
- Também há `crm/controllers/enrichment_controller.py` (enriquecimento de lead) e `bidding/integrations/receita_federal/cnd_client.py` — infra de CNPJ/Receita já existente.

## 2. Repositório de clientes (para `buscar_cliente`)
`modules/clients/repositories/client_repository.py` (+ `client_service.py`, `models/client.py`):
- `get_client_by_document(document)` — por CNPJ/CPF ✅
- `get_client_by_code(code)`
- ⚠️ **NÃO há `get_client_by_phone`** — busca por telefone exigiria query nova.
- ⚠️ Métodos são **síncronos** (`def`) — o agente é **async**; precisa de ponte (ex.: `run_in_executor` ou sessão sync separada) para não bloquear o loop.

## 3. Modelo Lead (para futuro `criar_lead`/enriquecer)
`modules/crm/models/lead.py`: `name`, `email` (nullable), `phone`, `company`, `position`, `company_size`, `industry`, `source`, `status`, `score`, `notes`, `last_contact_at`...
- **Não há coluna `cnpj`** — dados de CNPJ caberiam em `company`/`notes` ou exigiriam migration (zona proibida).

## 4. OpenAI / agente
- `openai 2.38.0` → suporta **tool use** (`tools=[...]` + `tool_calls`).
- O `agent_service.gerar_resposta` hoje faz `chat.completions.create(model, messages, max_tokens, temperature)` — **sem tools** (0 refs).
- **Mudança para F-B.1:** adicionar `tools` na chamada + um **loop de tool-calling** (modelo pede tool → executa → anexa resultado → chama de novo até não pedir mais). Cada tool-call = chamada(s) OpenAI extra(s) (custo/latência).

---

## 5. DECISÕES DE PRODUTO (preciso de você antes de implementar)
1. **Quais tools** na F-B.1? Candidatas: `consultar_cnpj` (BrasilAPI), `buscar_cliente` (por documento; por telefone exige query nova), outras (`agendar_visita`? `criar/atualizar_lead`?).
2. **Quando disparam?** Ex.: só quando o cliente fornece um CNPJ? `buscar_cliente` por quê (telefone? documento?) — lembrando que `clients` está com telefones vazios (match por telefone hoje não acha cliente).
3. **Continua COPILOTO?** A resposta com dados das tools vira **rascunho/nota privada** (humano revisa) ou já é envio? (F-B.1 = ainda copiloto?)
4. **Custo/latência:** o tool-loop multiplica chamadas OpenAI. Teto de iterações? Modelo (gpt-4o-mini aguenta tool use)?
5. **Ponte sync→async** para o `client_repository` (síncrono) — ok usar `run_in_executor`?

## 6. Esboço técnico (quando o escopo fechar) — PROPOSTA
- Em `agent_service`: definir `TOOLS` (JSON schema), um dispatcher `async def _exec_tool(name, args)` que chama `BrasilAPIClient().get_cnpj` / `client_repository` (via executor), e um loop de tool-calling em `gerar_resposta` (com teto de iterações).
- Manter try/except (falha de tool → segue sem ela; nunca derruba o webhook).
- Manter o gate `AGENT_ENABLED` e o modo copiloto (a não ser que você decida o contrário).
- Deploy: `docker cp` + restart; **e re-rebuild da imagem** para durabilidade (como aprendemos — senão o próximo recreate reverte).

---
*Read-only: grep + leitura de interfaces (`brasilapi/client.py`, `client_repository.py`, `lead.py`, `agent_service.py`), `pip show`. Nada implementado. Escopo das tools aguardando sua definição.*
