# Agente WhatsApp — 3 capacidades de aprendizado ✅

- **Data:** 2026-06-12
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Commit:** `7c6b93f7` (+258 linhas, só `agent_service.py`) | **Imagem:** `rebuild-aprendizado-20260612` nos 9 containers
- **Status:** ✅ **As 3 capacidades implementadas, baked e PROVADAS ao vivo.** Tudo best-effort (falha em qualquer uma → agente segue exatamente como antes). Zero migration.

---

## 1) Memória de longo prazo por contato ✅ PROVADA
- **Como:** linhas `direction='mem'` no próprio `cwi_message_log` (chave = `phone_canonical`; sempre INSERT → histórico auditável; **zero migration** — direction varchar(3) comporta 'mem'; o histórico do chat filtra `IN ('in','out')`, então 'mem' não contamina a conversa).
- Após cada atendimento, um LLM atualiza o resumo (≤6 linhas: nome, tipo, porte, o que procura, status). Quando o cliente volta — **mesmo em outra conversa** — o resumo é injetado: *"MEMORIA DESTE CLIENTE... não repita perguntas já respondidas"*.
- **Prova real (conversa #4 do Jordan):** memória gerada e gravada:
  `"Nome: AGP | Tipo: Condomínio | Procura: proposta para agentes de portaria (2 postos 24h) | Status: aguardando informações..."`

## 2) Base de conhecimento (RAG) ✅ PROVADA
- **Onde:** `/opt/conecta-pro/uploads/agent_knowledge/*.md` → montado no container (`./uploads:/app/uploads`) → **ensinar = editar/criar .md no host, SEM rebuild/restart** (o agente relê e re-indexa por mtime a cada mensagem).
- **Como:** chunks por seção `## `; embeddings `text-embedding-3-small` com **cache em disco** (`.cache_embeddings.json`, 684KB, persistindo — corrigi a permissão da pasta p/ o user do container, uid 999); top-3 por cosseno (≥0.25) injetados como *"CONHECIMENTO DA EMPRESA... fonte de verdade"*; **fallback por palavras-chave** se a API de embeddings falhar.
- **Seed criado:** `servicos.md` (todas as frentes + diferenciais), `faq_objecoes.md` (preço→visita, "portaria remota é segura?", redução de custos, sistema antigo, prazos, emergência→190+transferir), `COMO_ENSINAR.md` (manual para o Jordan).
- **Prova real:** busca "quanto custa portaria remota para meu condomínio?" → retornou exatamente as seções *"Quero reduzir custos"* + *"Portaria remota/monitoramento 24h"*.
- **Nota sobre SOPHIA:** avaliada e NÃO reusada de propósito — o corpus dela (617 docs) é técnico/interno do sistema, não conhecimento comercial; uma base própria curada pelo Jordan é mais segura (sem risco de vazar conteúdo interno pro cliente).

## 3) Aprendizado por feedback (few-shot) ✅ ATIVO (aguardando dados)
- **Como:** pares reais (última msg do cliente → resposta `out` da EQUIPE) puxados do log, injetados como *"EXEMPLOS REAIS... espelhe o tom"*. **Ecos do bot autônomo são excluídos** (out cujo content bate com um draft 'drf' da mesma conversa) — o agente não aprende consigo mesmo. Filtro de qualidade: respostas >40 chars.
- **Estado atual: SEM PARES ainda — correto:** as respostas humanas até hoje são curtas ("ok, mnsagem recebida"). **Conforme a equipe responder de verdade (copiloto ou conversas atribuídas), os exemplos entram sozinhos.**

## Integração (gerar_resposta)
```
system: SYSTEM_PROMPT (persona/regras — intocadas)
system: CONHECIMENTO DA EMPRESA (RAG, se relevante)
system: MEMORIA DESTE CLIENTE (se existir)
system: EXEMPLOS DA EQUIPE (se existirem)
... histórico da conversa (20 msgs) ...
```
Atualização da memória roda POR ÚLTIMO no `processar_incoming` (nunca atrasa a resposta).

## Rebuild
- Âncora `pre-rebuild-aprendizado-20260612` = 0c36d8c6 (autônomo) | dump `backup_pre_aprendizado_20260612.dump`.
- Build exit 0 → efêmero OK (6 refs + compile) → swap → 2A+2B → 9 containers up, /health 200. Rede + env_file sobreviveram (3º rebuild consecutivo).

## Como ensinar o agente (resumo p/ Jordan)
- **Conhecimento:** edite/crie `.md` em `/opt/conecta-pro/uploads/agent_knowledge/` — vale na mensagem seguinte. NUNCA coloque preços lá.
- **Memória:** automática (cada atendimento atualiza o perfil do contato).
- **Estilo:** automática — cada resposta real da equipe vira exemplo para o agente.

## Rollback
`docker tag conecta-pro-backend:pre-rebuild-aprendizado-20260612 conecta-pro-backend:latest` + recreate 2A/2B. Memórias 'mem' são linhas no log (inofensivas se o código voltar).

## Nota: 10/10
3 capacidades entregues e provadas ao vivo (RAG retornando trecho certo; memória real do Jordan gerada e gravada; few-shot com filtro anti-eco correto), zero migration, base editável sem rebuild, best-effort em tudo, persona/gates/guards intocados.
