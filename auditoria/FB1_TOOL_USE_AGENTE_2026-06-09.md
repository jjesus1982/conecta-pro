# F-B.1 — Tool use no agente WhatsApp (consultar_cnpj + buscar_cliente)

- **Data:** 2026-06-09
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Escopo:** Dar **2 tools de LEITURA** ao agente WhatsApp (copiloto), com loop de tool-calling. Nada de escrita no CRM.
- **Arquivo:** `backend/modules/integrations/connectors/whatsapp/agent_service.py`
- **Backup:** `agent_service.py.bak-fb1-20260609-032358`
- **Commit:** `ba7f2559` — `feat(whatsapp): tool use agente F-B.1 (consultar_cnpj + buscar_cliente, leitura)` (1 file, +190/-13)
- **Veredito:** ✅ Funcionando e testado. Continua **copiloto** (nota privada + rascunho, não envia ao cliente) e **gated** por `AGENT_ENABLED`.

---

## 1. O que mudou (3 edições no `agent_service.py`)

1. **`SYSTEM_PROMPT`** — acrescentado 1 parágrafo: quando o cliente fornecer/mencionar CNPJ, usar `consultar_cnpj` (validar, nunca inventar) e `buscar_cliente` (se já é cliente → acolher como cliente, não prospecção). **Todos os guard-rails antigos mantidos** (nunca preço, nunca inventar). Prompt não reescrito.
2. **2 tools + dispatcher** (novas funções, só leitura):
   - `consultar_cnpj(cnpj)` → **reusa** `BrasilAPIClient().get_cnpj` (cache + circuit breaker). Retorna `razao_social, nome_fantasia, situacao_cadastral, municipio, uf, cnae_principal`. Não encontrado/inválido → `{"erro": "CNPJ não encontrado ou inválido"}`; timeout/circuit-open/qualquer erro → `{"erro": "não foi possível consultar agora"}`. **Nunca estoura.**
   - `buscar_cliente(cnpj)` → query **async própria** (`async_session_factory()` + `text()`, padrão do módulo) em `clients WHERE regexp_replace(document_number) = :cnpj` (normaliza só dígitos). Retorna `{existe:true, nome, status}` ou `{existe:false}`; erro → `{"erro":...}`. **Não** usa o `client_repository` (síncrono).
   - `_exec_tool(name, args)` — dispatcher em try/except (falha → `{erro}` ao modelo, nunca derruba).
3. **Loop de tool-calling em `gerar_resposta`**: chama OpenAI com `tools=[...]`, `tool_choice="auto"`; se vier `tool_calls`, executa cada um, anexa `role=tool`, repete. **Teto 3 rodadas** (`AGENT_MAX_TOOL_ROUNDS`); ao atingir, **última chamada SEM tools** (força texto). Loga `tool_rounds`, `tokens_in`, `tokens_out` (custo). Mantém o `except → return None` global (exceção nunca derruba o webhook).

## 2. Os 3 testes (E2E via `gerar_resposta`, com histórico simulado em `cwi_message_log`, conv 99000x, limpos após)

### Teste A — CNPJ real que NÃO é cliente (`00.000.000/0001-91`)
```
tool-call round=1 consultar_cnpj -> {razao_social: BANCO DO BRASIL SA, situacao: ATIVA, municipio: BRASILIA, uf: DF, cnae: Bancos múltiplos...}
tool-call round=1 buscar_cliente -> {existe: False}
resposta gerada tool_rounds=2 tokens_in=2341 tokens_out=176
```
✅ Agente **chamou as tools**, usou os **dados reais** (sem inventar) e qualificou como **lead novo**.

### Teste B — CNPJ de cliente EXISTENTE (`04.911.208/0001-13` = Condomínio Michelangelo, status active)
```
tool-call round=1 consultar_cnpj -> {razao_social: CONDOMINIO DO EDIFICIO MICHELANGELO, municipio: MANAUS, uf: AM, cnae: Condomínios prediais}
tool-call round=1 buscar_cliente -> {existe: True, nome: CONDOMINIO DO EDIFICIO MICHELANGELO, status: active}
resposta gerada tool_rounds=2 tokens_in=2369 tokens_out=125
```
Sugestão: *"Que bom receber o contato do Condomínio do Edifício Michelangelo. Estou aqui para ajudar com o que precisar em relação ao seu contrato."*
✅ Reconheceu como **cliente** e adotou **tom de relacionamento** (não prospecção).

### Teste C — CNPJ malformado (`123`)
```
resposta gerada tool_rounds=1 tokens_in=1078 tokens_out=51
```
Sugestão: pediu o CNPJ completo de 14 dígitos, com gentileza. ✅ **Não travou.**
(Prova adicional, tool direta: `consultar_cnpj("123") -> {"erro": "CNPJ não encontrado ou inválido"}` — a tool degrada graciosamente.)

> Teste direto das tools também confirmou: `consultar_cnpj(BB)` retorna dados reais da BrasilAPI; `buscar_cliente(BB) -> {existe:false}`. BrasilAPI **alcançável** do container (HTTP 200).

## 3. Garantias
- **Copiloto intacto:** `gerar_resposta` só **retorna texto**; `processar_incoming` segue entregando como `_log_draft` (drf) + `_post_private_note` (privada). **Nada enviado ao cliente.**
- **Gated:** `AGENT_ENABLED` inalterado.
- **Webhook 200 / backend healthy** após deploy.
- **Custo logado:** cada resposta loga `tool_rounds` + tokens in/out. Tool-loop multiplica chamadas OpenAI (Teste A/B = 2 chamadas; teto 3 + 1 final).
- **Limpeza:** 0 linhas de teste remanescentes em `cwi_message_log`.
- **host == container:** `md5 b5bd389326b76479ff3037dfa5ce0d70` (idêntico, inclusive pós-commit).

## 4. ⚠️ Durabilidade (acumula com a SQLi pendente)
Código novo na imagem, vivo via `docker cp` + commitado. **Precisa bakar no PRÓXIMO rebuild da imagem do backend** — junto com a correção SQLi (`417d1a75`, `contact_controller.py`) que também aguarda rebuild. **NÃO reconstruí agora** (fora do escopo). Até o rebuild, não recriar o container do zero (recreate reverteria ambos).

**Pendências para o próximo rebuild (acumuladas):**
1. SQLi `contact_controller.py` (commit `417d1a75`).
2. Tool use `agent_service.py` (commit `ba7f2559`).

---

## Resumo
- 2 tools de leitura (`consultar_cnpj` via BrasilAPI reusada, `buscar_cliente` async própria) + loop de tool-calling (teto 3, fallback sem tools). ✅
- 3 testes A/B/C passaram com logs de tool-call e tokens. ✅
- Copiloto + gated mantidos; webhook 200; custo logado; host==container; commit `ba7f2559`. ✅
- Durabilidade: bakar no próximo rebuild junto com a SQLi. ⏸️

*Tarefa encerrada (PARAR). NÃO liguei escrita no CRM (F-B.2). NÃO rebuildei.*
