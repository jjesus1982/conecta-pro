# Mapa completo do agente WhatsApp + diagnóstico da conversa #4 (READ-ONLY)

- **Data:** 2026-06-11
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Token:** STEP-0-AGENTE-MAPA-COMPLETO-RO
- **Modo:** 100% READ-ONLY — nada editado/buildado/reiniciado; nenhuma chamada que mude estado.
- **Veredito antecipado (B):** 🎯 **O copiloto RODOU na #4 e gerou os 3 rascunhos** (estão no banco). O que falhou foi a **entrega da nota privada ao Chatwoot**: `Cannot connect to host chatwoot-fazerai:3000 [Name or service not known]` — **o backend está FORA da rede docker `chatwoot-fazerai-net`** (conexão era manual, perdida em recreate). **BUG de infraestrutura (estado não-durável), não de lógica.**

---

## PARTE A — Arquitetura e fluxo

### a) Diagrama textual (mensagem entra → rascunho sai)
```
WhatsApp do cliente → baileys-api → Chatwoot (conta 1)
  └─ Chatwoot webhook → POST https://erp.conectamais.pro/api/v1/whatsapp/webhook?token=<secret>   [entrada via nginx público]
       controller.py:229 chatwoot_webhook
         ├─ valida token (hmac.compare_digest vs WHATSAPP_WEBHOOK_SECRET; agora SET 64c e VALIDANDO)
         ├─ event != message_created → ignora | private=true → ignora (anti-loop de notas)
         ├─ extrai: content (l.263), message_type (l.264), conversation.id, sender.phone/name
         ├─ direction = 'in' se message_type ∈ ('incoming','0'), senão 'out'  (l.265)
         ├─ se in: _match_or_create_lead (l.277) — dedup por telefone normalizado → cria Lead(source=whatsapp)
         ├─ INSERT cwi_message_log (idempotente ON CONFLICT chatwoot_message_id)
         └─ se direction='in' AND conv_id AND agent_enabled():  → BackgroundTask processar_incoming(conv,phone)
              agent_service.py:654 processar_incoming
                └─ gerar_resposta(conv)  (l.470)
                     ├─ lê histórico do PRÓPRIO cwi_message_log (l.486): direction in/out, content<>'' , LIMIT AGENT_MAX_HISTORY=20
                     ├─ messages = [SYSTEM_PROMPT] + histórico (in→user, out→assistant)
                     ├─ AsyncOpenAI (gpt-4o-mini, OPENAI_AGENT_MODEL) com TOOLS, loop até AGENT_MAX_TOOL_ROUNDS=3
                     └─ retorna texto
                ├─ _log_draft (l.597): INSERT cwi_message_log direction='drf' (rascunho)
                └─ _post_private_note (l.619): POST aiohttp → {CHATWOOT_BASE_URL}/api/v1/accounts/1/conversations/{id}/messages
                     (private note "🤖 Sugestao do assistente (copiloto)" — header api_access_token)   ← AQUI FALHOU (DNS)
```
- **COPILOTO:** nunca envia ao cliente — só nota privada + draft. Confirmação no código e no comportamento.

### A2 — Decisão responder/tool/transferir + persona
- **Tool-calling nativo OpenAI** (`tools=TOOLS, tool_choice="auto"`, loop de até 3 rounds; `_exec_tool` l.453 roteia).
- **SYSTEM_PROMPT (l.23):** assistente da Conecta Mais (Manaus/AM, segurança e mão de obra; foco condomínios/síndicos). Regras embutidas: quando transferir a humano (pedido explícito, irritação, urgência, emergência, fora de escopo) e **triagem antes de transferir pedido vago** (1 pergunta p/ rotear setor: suporte_tecnico/operacional/administrativo/comercial; mapa setor→team_id real do Chatwoot l.417).
- **TOOLS (4):** `consultar_cnpj` (l.82), `buscar_cliente` (l.100), `agendar_visita` (l.118), `transferir_conversa` (l.152).

### A3 — Integração CRM
- **Lead:** criado/dedupado **na entrada do webhook** (não pelo agente): `_match_or_create_lead` (controller l.192) — busca `leads.phone` por dígitos normalizados (`_normalize_phone` remove +/DDI 55); se novo → `LeadRepository.create(LeadCreate(name|'WhatsApp <fone>', email=None, phone, source=WHATSAPP))`. **Provado íntegro:** leads "Jordan Jesus" (9286465328, 06-08) e "Junior Feitoza" (9284393279, 06-09), source=whatsapp.
- `buscar_cliente`/`consultar_cnpj`: leem base interna/externa (read). `agendar_visita`: cria visita no módulo campo + `_resolve_lead_id` via cwi_message_log (l.236) + e-mails internos (`_enviar_emails_visita` — mailer validado). `transferir_conversa`: assign team no Chatwoot.

### A4 — Memória/contexto
- Query (l.486-491): `cwi_message_log WHERE conv=:c AND direction IN ('in','out') AND content IS NOT NULL AND content <> '' ORDER BY created_at DESC LIMIT 20` → reverso p/ cronologia. **Exclui drafts e vazios** (consequência: áudio sem transcrição fica invisível — item da feature STT).

---

## PARTE B — Por que a #4 "não rascunhou" (DIAGNÓSTICO)

### B1 — As 3 msgs ESTÃO no log e RASCUNHARAM
(18:52/18:54/18:55 Manaus = 22:52/22:54/22:55 UTC, conv=4, phone 9286465328):
```
22:52:56 in  msg61 "Teste"                                  → 22:52:59 drf "Olá! Como posso ajudar você hoje?"
22:53:36 out msg62 "ok, mnsagem recebida"                   (resposta humana do operador)
22:54:16 in  msg63 "queria informações sobre portaria..."   → 22:54:19 drf "Claro! A portaria remota é..."
22:55:16 in  msg64 "Quero informações"                      → 22:55:21 drf "Claro! A portaria remota é..."
```
**direction='in' (correto)**, e **cada `in` gerou um `drf` 3-5s depois**. O pipeline inteiro até o draft FUNCIONOU.

### B2 — Logs do backend (a prova da falha)
```
22:52:59 INFO  Agente: resposta gerada conv=4 model=gpt-4o-mini tool_rounds=1 tokens_in=2022 tokens_out=9
22:52:59 ERROR Agente: excecao ao postar nota privada conv=4: Cannot connect to host chatwoot-fazerai:3000
               ssl:default [Name or service not known]
(idem 22:54:19 e 22:55:21 — 3× geração OK + 3× ERRO de DNS na nota)
```

### B3/B4 — Gates e guards (NÃO barraram)
- Direction: Jordan escreveu **do telefone dele (contato externo)** para o 0800 → `message_type=incoming` → `in` → agendou. ✅ O único guard adicional é `private=true → ignored_private` (anti-loop de notas — correto). **Não há** guard de assignee/sender interno para incoming (outgoing já é tratado pelo direction).

### B5 — Comparação com "Supervisor Operacional" (que mostrava nota)
- Notas visíveis nas outras conversas (conv 5/9) são de **06-08/06-09**, quando o container backend ANTIGO estava conectado à rede `chatwoot-fazerai-net` (conexão manual, docs `FASE1.1_PASSO_A_REDE_E_CHOKEPOINT_2026-06-05.md`).
- HOJE: backend está **só** em `conecta-pro_conecta-pro-network`; `chatwoot-fazerai-net` contém chatwoot(+redis/pg/sidekiq)+baileys — **sem o backend**. O compose **não declara** essa rede (zero menções) → **`docker network connect` manual NÃO sobrevive a recreate**. Houve ≥3 recreates do backend desde 06-09 (rebuild followup 06-10 manhã; rebuild multiprazo 06-10 20:44; env_file 06-11 22:41) — **não dá pra cravar qual derrubou** (sem incoming entre 06-09 13:32 e hoje p/ observar), mas a classe é a mesma do env: **estado runtime não-durável**.
- **Entrada não quebrou** porque o Chatwoot chama o webhook pela **URL pública** (nginx) — só a **saída** backend→chatwoot usa o DNS interno.

### b) VEREDITO: **BUG (i)** — de infraestrutura, não de lógica
O copiloto está **funcionalmente perfeito** (gate, lead, LLM, draft). O rascunho não APARECEU no Chatwoot porque a nota privada falha em DNS (backend fora da rede). **Não foi** "Jordan testou consigo mesmo" — a msg entrou como contato externo e o agente respondeu.

### c) Teste válido pós-fix
O mesmo teste do Jordan JÁ é válido (entrou como `in`). Após religar a rede: mandar 1 texto novo → a nota "🤖 Sugestao do assistente" deve aparecer na conversa em segundos.

---

## PARTE C — Inventário de travas (classificado)

| # | Trava | Classe | Evidência | Estado |
|---|-------|--------|-----------|--------|
| 1 | **Backend fora da `chatwoot-fazerai-net`** → nota privada falha (DNS) | **(i) BUG** (regressão de recreate; conexão era manual) | ERROR 3× nos logs 22:52-22:55 | 🔴 **ATIVO — a causa do #4** |
| 2 | Webhook não lê `attachments` (áudio descartado; filtro `content<>''` o exclui do contexto) | **(iii) FALTA FEATURE** (STT já desenhado) | grep attachments=0; 2 msgs sem texto 06-09 | aberto |
| 3 | Env do agente não-durável | (i) BUG — **RESOLVIDO hoje** (env_file no compose) | agente gerou 3× hoje | ✅ |
| 4 | `WHATSAPP_WEBHOOK_SECRET` unset (webhook aberto) | (i) risco — **RESOLVIDO hoje** (SET 64c **e validando**: as 3 msgs entraram após o recreate 22:41 com `?token=` correto) | env + msgs aceitas | ✅ |
| 5 | `private=true → ignored` (não processa notas) | **(ii) CORRETO** — anti-loop (a própria nota do agente não realimenta) | código l.259 | não mexer |
| 6 | Filtro `content<>''` no histórico | (ii) correto p/ texto / consequência da #2 p/ áudio | l.489 | resolve-se com STT |
| 7 | Tools falhando silenciosamente | **não observado** — tool_rounds=1 sem erro de tool nos 3 disparos; `_exec_tool` retorna erro como dict p/ o LLM tratar | logs limpos | ok |
| 8 | Follow-up automático ao cliente / envio autônomo | **(iv) GATE LGPD** — `FOLLOWUP_AUTO_SEND=False` constante; copiloto nunca envia | tasks.py:28 | não tocar |

### C3 — Baked × quebrado × falta
| Funciona (baked) | Quebrado | Falta (feature) |
|---|---|---|
| Webhook+token, log idempotente, lead dedup/create (CRM ✅), gate AGENT_ENABLED (env_file ✅), LLM+4 tools, draft em cwi_message_log | **Entrega da nota privada (rede docker)** — único elo quebrado | STT de áudio (attachments→Whisper→content); [material/ticket — futuros] |

---

## f) RECOMENDAÇÃO de sequência (NÃO executei)
1. **Religar a rede de forma DURÁVEL** (a mesma lição do env_file): no `docker-compose.yml`, declarar a rede externa e anexar o backend:
   ```yaml
   # top-level
   networks:
     chatwoot-fazerai-net:
       external: true
   # no serviço backend
   networks:
     - default            # (a rede atual do projeto)
     - chatwoot-fazerai-net
   ```
   + recreate `--no-deps backend`. ⚠️ Atenção: ao declarar `networks:` no serviço, a rede default do compose deve ser listada junto (senão o backend sai dela). Alternativa paliativa (1 comando, zero downtime, mas **não-durável**): `docker network connect chatwoot-fazerai-net conecta-pro-backend` — morre no próximo recreate; útil só p/ validar já.
2. **Re-teste de texto** (Jordan manda 1 msg) → nota privada deve aparecer na conversa.
3. **Só então o STT de áudio** (desenho pronto do STEP-0-AUDIO-RO): webhook lê attachment → aiohttp download (CHATWOOT_API_TOKEN, mesma rede agora) → Whisper → content.
4. (iv) LGPD permanece intocado.

## g) Riscos (o que NÃO mexer)
- **Gate `direction=='in'` e `private→ignored`:** são o anti-loop (impedem o agente de responder a si mesmo/operador). Mexer = risco de loop de notas.
- **Filtro `content<>''`:** remover sem STT colocaria msgs vazias no contexto do LLM. Resolver via transcrição, não via filtro.
- **Compose networks:** declarar `external: true` exige a rede existir (existe); listar a rede default junto ao anexar a nova (senão backend perde a rede do projeto → quebra DB/redis).
- Idempotência por `chatwoot_message_id` UNIQUE: não alterar (protege contra retry do Chatwoot).

---

## Resumo executivo
- **O agente está VIVO e correto:** msg do Jordan entrou, lead ok, LLM gerou, draft no banco — 3 de 3.
- **Único elo quebrado:** backend **fora da rede `chatwoot-fazerai-net`** (conexão manual perdida em recreate) → nota privada não chega ao Chatwoot (DNS). **Fix recomendado: rede no compose (durável) + recreate**, depois re-teste.
- Env (#3) e webhook-secret (#4) **já resolvidos hoje** e provados em produção.
- Áudio = feature (desenho pronto), LGPD intocado, CRM íntegro.

*Read-only: SELECTs, docker logs/inspect/network inspect, leitura de código/compose/docs. Zero escrita/build/restart/POST. Forbidden zones apenas lidas.*
