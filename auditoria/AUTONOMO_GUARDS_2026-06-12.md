# Modo AUTÔNOMO do agente WhatsApp — guards + kill-switch + rebuild ✅

- **Data:** 2026-06-12
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Token:** STEP-0-AUTONOMO-GUARDS (Jordan autorizou o autônomo; gate LGPD removido por decisão dele)
- **Status:** ✅ **Implementado, baked (imagem `0c36d8c6` nos 9, healthy) e DESLIGADO por default** (`AGENT_MODE` unset → `copilot`). **Nada muda em produção até o Jordan setar a flag.** Guards provados em conversas reais.

---

## FASE 0 — Reconhecimento (decisões con evidência) — Nota 10/10
- **0.1 GRUPO (critério conservador):** contatos individuais no Chatwoot real = identifier `...@lid` + `phone_number` presente (8 contatos verificados no DB do Chatwoot). Grupos baileys = `@g.us` e/ou sem fone individual. **Critério:** `('@g.us' in identifier) OR (sem phone_number)` → **trata como grupo → NÃO responde público.** Na dúvida (GET falhou) → copiloto.
- **0.2 ASSIGNEE:** validado com **GET real** `GET /api/v1/accounts/1/conversations/{id}` (aiohttp+token): conv 4 → `meta.assignee = Jordan Jesus`; conv 9 → `assignee = None`. DB confirma: convs 1-8 atribuídas (assignee_id=1), 9 não. **Critério:** `meta.assignee != None` → humano atribuído → copiloto.
- **0.3 ANTI-LOOP CONFIRMADO (pré-requisito do deploy):** o eco da resposta pública volta no webhook como `message_type=outgoing` → `direction='out'` (controller l.265: `"in" if mtype in ("incoming","0") else "out"`) → é **logado como 'out'** (memória histórica correta) e **NÃO agenda** o agente (`if direction == "in"`). Nota privada → `private→ignored_private` (nem loga). **Loop impossível pelos gates existentes — intocados.**

## FASE 1 — Implementação (`agent_service.py`, commit `3eff6d5d`, +113/-4) — Nota 10/10
- Backup: `agent_service.py.bak-autonomo-20260612`.
- **`agent_mode()`**: `os.getenv("AGENT_MODE", "copilot")`, whitelist `copilot|autonomous` (valor inválido → copilot). **Kill-switch documentado** (env + recreate).
- **`_get_conversation_info(conv_id)`**: GET best-effort → `{'is_group', 'assignee'}`; **falha → None → chamador cai p/ copiloto** (conservador).
- **`_post_public_reply(conv_id, texto)`**: igual à nota mas `private: False` (outgoing real → Chatwoot → baileys → WhatsApp do cliente). **Falha → fallback nota privada** (não perde o trabalho do LLM).
- **Decisão em `processar_incoming`** (após gerar + **draft SEMPRE logado**):
  ```
  autonomous E não-grupo E sem assignee → autonomous_sent (cliente recebe)
  senão → nota privada (copiloto) com motivo logado:
    copilot_note | copilot_note_info_fail | skipped_group | skipped_assigned | copilot_note_send_fail
  ```
  Cada decisão logada com conv_id (auditoria dos primeiros dias).
- **Persona:** abre como **"assistente virtual da Conecta Mais"** + instrução de se apresentar na 1ª interação (transparência em autônomo). Regras preservadas (nunca preço/prazo, transferências, triagem).
- **Intocados:** `FOLLOWUP_AUTO_SEND=False`, e-mail ao cliente, gates anti-loop, filtro `content<>''`, STT.
- `py_compile` OK (py3.12 do container).

## FASE 2 — Rebuild (procedimento provado) — Nota 10/10
- Âncora `pre-rebuild-autonomo-20260612` = **2316d5b9** (anterior, com STT); dump `backup_pre_autonomo_20260612.dump` (3.9MB).
- Build `rebuild-autonomo-20260612` → **exit 0**; efêmero `--network none` → código novo (6 refs) + compila → OK; swap → 2A + 2B.
- **Pós-swap:** /health **200**; imagem **`0c36d8c6`** nos 9; **9/9 healthy**; **rede `chatwoot-fazerai-net` SOBREVIVEU** (2º rebuild consecutivo — durabilidade consolidada); env_file sobreviveu (`AGENT_ENABLED=true`); `AGENT_MODE=unset → copilot` (**produção sem mudança de comportamento**); proposals=**4**.
- **Smoke dos guards em produção (read-only):** `agent_mode()=copilot`; `_get_conversation_info(4)={'is_group': False, 'assignee': 'Jordan Jesus'}`; `(9)={'is_group': False, 'assignee': None}` — exatamente os cenários `skipped_assigned` e `autonomous_sent`.

---

## 🔛 INSTRUÇÃO PARA LIGAR (Jordan executa; eu não edito .env)
1. Adicionar ao `/opt/conecta-pro/.env` (qualquer linha):
   ```
   AGENT_MODE=autonomous
   ```
2. Aplicar: `cd /opt/conecta-pro && docker compose -f docker-compose.yml up -d --no-deps --no-build --force-recreate backend`
3. **Kill-switch (desligar):** trocar para `AGENT_MODE=copilot` (ou remover a linha) + mesmo recreate. Rollback de imagem: âncora `pre-rebuild-autonomo-20260612`.

## 🧪 PLANO DE TESTE (autônomo ligado)
1. **Sua conversa #4 está ATRIBUÍDA a você** → guard `skipped_assigned` → continuará **copiloto** (nota privada). **Isso é o esperado, não falha.** Para testar o autônomo: **desatribuir a #4 no Chatwoot** (ou usar outro número que abra conversa nova) e mandar um texto → **a resposta deve CHEGAR no seu WhatsApp** (com a apresentação "assistente virtual").
2. **Áudio** na mesma condição → transcreve (STT) + responde no WhatsApp.
3. **Grupo:** mandar mensagem num grupo de ronda → agente **NÃO responde** (guard `skipped_group`; nota privada apenas).
4. **Re-atribuir** a conversa a um humano e mandar outra msg → agente **volta a nota privada** (guard `skipped_assigned`).
- Auditoria: `docker logs conecta-pro-backend | grep 'Agente: decisao='` mostra cada decisão (autonomous_sent/skipped_*) por conversa.

## Resumo de segurança
- Default **copilot** (flag desligada) — deploy não mudou comportamento.
- Guards **conservadores**: na dúvida (grupo incerto, GET falhou, envio falhou) → **nota privada**, nunca silêncio nem envio às cegas.
- Anti-loop garantido pelos gates existentes (validado antes do deploy).
- Draft sempre logado (auditoria completa).

*Backups: agent_service .bak + compose intocado nesta missão + âncora de imagem + dump. .env não editado (instrução entregue). FOLLOWUP_AUTO_SEND/e-mail intocados.*
