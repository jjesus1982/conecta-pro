# F-VISITA.1 — tool agendar_visita: implementada, mas BLOQUEADA por bug pré-existente

- **Data:** 2026-06-09
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Status:** ⛔ **Não entregue como funcional.** A 3ª tool foi implementada e dispara corretamente, mas a **criação de visita falha por um bug PRÉ-EXISTENTE no módulo `campo`** (FK cross-schema) — fora da zona que a missão autorizou tocar (model/service/schema).
- **Decisão produção:** revertida ao estado conhecido-bom (2 tools). Trabalho preservado.
- **Commit:** ❌ não feito (feature não funciona).

---

## 1. O que foi feito (correto e provado)
No `agent_service.py` (host): adicionada tool `agendar_visita` (schema OpenAI), `_tool_agendar_visita`, helper `_resolve_lead_id`, dispatcher atualizado (`_exec_tool(name, args, conversation_id)`), e orientação no SYSTEM_PROMPT (fraseado de SOLICITAÇÃO, nunca "confirmado"). Padrão idêntico às 2 tools da F-B.1.

**Provas de que o meu lado está correto:**
- `py_compile`/import OK; 3 tools carregam.
- **GUARD:** chamada sem endereço/data/horário → `{"erro":"faltam dados..."}` (não cria). ✅
- **Teste B (sem endereço):** o agente **pergunta o endereço**, não cria visita incompleta. ✅
- **E2E (msg completa):** o modelo **CHAMOU** `agendar_visita` com args corretos (`data_visita=2026-06-12, horario_inicio=09:00, endereco=..., bairro, cidade, nome_contato, telefone_contato`) — o caminho LLM→tool funciona. ✅
- Erro **degrada graciosamente** (webhook nunca cai; retorna `{erro}`). ✅

## 2. O bloqueio (bug PRÉ-EXISTENTE, não do meu código)
Ao criar a visita, o flush do SQLAlchemy falha:
```
sqlalchemy.exc.NoReferencedTableError: Foreign key associated with column
'visitas.proposta_id' could not find table 'crm.proposals' ...
(idem 'visitas.oportunidade_id' -> 'crm.opportunities', 'visitas.cliente_id' -> 'clients.clients')
```
- O model `modules/campo/models/visita.py` tem **FKs cross-schema** (`crm.proposals`, `crm.opportunities`, `clients.clients`) cuja **tabela-alvo não está na MetaData do `Visita`** → o mapper não resolve no flush.
- **Não é o meu código:** o endpoint REAL `POST /api/v1/campo/visitas/` no app vivo (uvicorn, todos os models carregados) **também retorna 500** com o mesmo erro.
- **Explica os 0 registros** em `visitas`: o módulo `campo/visitas` **nunca conseguiu criar uma visita** — bug latente, jamais exercido.
- Conserto exige mexer no **model** (zona proibida nesta missão).

## 3. Ação tomada (produção segura)
- Revertido o `agent_service.py` em produção para a versão **2 tools** (= imagem bakada `5958168f`). Motivo: evitar que o agente LIVE gere **rascunhos quebrados** ("não consegui registrar...") em pedidos de visita. Sem a 3ª tool, o agente conduz o agendamento conversando (rascunho limpo).
- **host==container** (`b5bd389…`), backend **healthy**, **health 200**, 2 tools ativas.
- Trabalho de 3 tools **preservado** em `agent_service.py.fvisita3tools-pending-modelfix` (host) para reaplicar após o fix.
- `visitas` limpa (0), `cwi_message_log` sem lixo de teste, scripts de teste removidos.

## 4. DECISÃO necessária (sua) — como destravar
O único caminho é corrigir as FKs cross-schema do model `Visita` (autorizar tocar o `campo`). Opções:
1. **Cirúrgico (recomendado):** remover os `ForeignKey(...)` das 3 colunas problemáticas (`oportunidade_id`, `proposta_id`, `cliente_id`), deixando-as UUID puro — **igual ao `responsavel_id`, que já é UUID sem FK**. São links soft/nullable; baixo risco. Pode exigir migration p/ dropar a FK no banco.
2. **`use_alter=True`** nas 3 FKs — mantém a intenção de FK, contorna a ordenação de tabelas no flush.
3. **Unificar MetaData/Base** dos módulos (arquitetural, amplo, arriscado) — não recomendado agora.

> Observação extra: este bug **também quebra o endpoint `POST /campo/visitas/` em produção** (qualquer criação de visita, não só pelo agente). Vale corrigir de qualquer forma.

## 5. Durabilidade
- Nada commitado/bakado desta tarefa. Produção = imagem `5958168f` (2 tools), íntegra.
- Quando você autorizar o fix: aplicar correção no model → re-testar criação (Test A deve criar AGENDADA, responsavel `ad9abb59`, origem `lead`) → reaplicar a 3ª tool (arquivo preservado) → deploy → e bakar no próximo rebuild.

---

## Resumo
- 3ª tool `agendar_visita` **implementada e disparando** (LLM→tool OK, guard OK, copiloto OK), mas **criação bloqueada** por FK cross-schema **pré-existente** no `campo` (prod `POST /campo/visitas/` também 500). ⛔
- Produção **revertida** para 2 tools (estado seguro), trabalho preservado, **sem commit**. ✅
- **Decisão sua:** autorizar o fix no model `Visita` (opção 1 recomendada) para destravar.

*PAREI. Não toquei no model (proibido). Não rebuildei. Aguardo decisão sobre o fix.*
