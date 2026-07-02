# Agente WhatsApp — troca do SYSTEM_PROMPT (v2, catálogo real)

- **Data:** 2026-06-08
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Escopo:** Substituir **apenas** a constante `SYSTEM_PROMPT` do `agent_service.py`. Nada mais.
- **Resultado:** ✅ **Feito, validado, commitado.** Agente segue **desligado** em produção (`AGENT_ENABLED=false`).

---

## 1. Mudança (cirúrgica)
- Arquivo: `modules/integrations/connectors/whatsapp/agent_service.py`.
- **Só a constante `SYSTEM_PROMPT`** foi trocada (de string concatenada para triple-quoted, **UTF-8 com acentos**).
- Diff: **1 arquivo, +39 / -11** (só o bloco do prompt). Imports, lógica e as 5 funções (`gerar_resposta`, `_log_draft`, `_post_private_note`, `processar_incoming`, `agent_enabled`) **intactos**.
- Backup: `agent_service.py.bak-prompt-20260608_174415`.
- `py_compile`/import: **OK**. `AGENT_ENABLED` segue `false` (não liguei nada).

## 2. Novo prompt (resumo do que mudou)
A persona v2 traz o **catálogo real** e foco em **qualificação de lead**:
- Site `conectamais.pro`; foco em **condomínios** (síndicos/administradoras), mas atende empresas/indústrias/residências.
- Duas frentes: **mão de obra** (agentes de portaria, ASG, artífice) e **segurança eletrônica** (portaria remota 24h, CFTV inteligente, controle de acesso, automação de portões, alarme, manutenção, software de gestão condominial).
- Carros-chefe: agentes de portaria, portaria remota, segurança eletrônica.
- **Missão: qualificar** (tipo de solução, perfil/porte, sistema atual, motivação, preocupação) e **conduzir à visita**.
- Travas mantidas e reforçadas: nunca preço/prazo/condições; nunca inventar; assumir ser assistente virtual se perguntado; só falar de assuntos da Conecta Mais; escalar para humano quando pedir/urgência/emergência.

## 3. Deploy
- `docker cp` do arquivo para os **9 containers** backend-image + `docker restart conecta-pro-backend` (sem recriar).
- **host == container** confirmado (md5 `81a0e9ca…`).

## 4. Validação (resposta de teste — nova persona)
Conversa de teste (síndico perguntando sobre câmeras e portaria) → `gerar_resposta` retornou:

> "Olá! Sim, atendemos condomínios e ficamos felizes em saber que você está buscando soluções para segurança e portaria. Para entender melhor suas necessidades, você pode me contar um pouco mais sobre o seu condomínio? Por exemplo:
> - Quantas unidades e portarias você tem?
> - Já possui algum sistema de câmeras ou portaria atualmente?
> - O que motivou a busca por essas soluções agora? É mais por segurança, custo ou talvez uma troca de fornecedor?
> - Qual é a sua principal preocupação em relação à segurança e portaria?
> Assim, poderei ajudá-lo de forma mais eficaz!"

✅ Reflete a nova persona: confirma atendimento a condomínio, faz **as perguntas de qualificação** do prompt, tom acolhedor, **sem informar preço**. (Conversa de teste limpa após.)

## 5. Commit
- `5b96db84 feat(whatsapp): system prompt agente v2 (catalogo real)` (só o `agent_service.py`).

## 6. Estado / pendências
- Agente **OFF em produção** (`AGENT_ENABLED=false`) — sem mudança. Para ligar: gate já documentado (AGENT_* no compose + recreate).
- 🔐 Lembrete: rotacionar a chave OpenAI (foi colada no chat).

---
*Mudança cirúrgica: só a constante SYSTEM_PROMPT (UTF-8 acentuado). Deploy por docker cp + restart (sem recriar). host==container. Validado com resposta de teste. Nada além do prompt tocado.*
