# Triagem antes de transferir pedido vago de humano (ajuste de prompt) ✅

- **Data:** 2026-06-09
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Status:** ✅ **Entregue.** Pedido VAGO de "falar com humano" → agente faz 1 pergunta de triagem antes de transferir (não cai mais direto no colo do Jordan/comercial). Só prompt; copiloto inalterado.
- **Arquivo:** `agent_service.py` (só SYSTEM_PROMPT) · **Backup:** `agent_service.py.bak-triagem-20260609-221836`
- **Commit:** **`31b8195f`** — `feat(whatsapp): triagem antes de transferir pedido vago de humano`

---

## 1. Diff (só adicionado, nada removido)
Acrescentado ao parágrafo de transferência do SYSTEM_PROMPT:
> *"Triagem antes de transferir um pedido VAGO: se o cliente pedir para falar com uma pessoa mas o assunto não estiver claro, faça UMA pergunta breve de triagem ANTES de chamar transferir_conversa, por exemplo: 'Claro! Só pra te direcionar à pessoa certa — é sobre orçamento/visita, um equipamento ou manutenção, portaria/escala, ou financeiro?'. Com base na resposta, escolha o setor (suporte_tecnico para equipamento/manutenção; operacional para portaria/escala/posto; administrativo para boleto/nota/financeiro/contrato; comercial para orçamento/visita/cotação). Só transfira para comercial como último recurso se o cliente não quiser especificar o assunto."*

Tool/dispatcher/assign_team **inalterados**.

## 2. Testes
### Teste 1 — pedido VAGO → triagem (2 turnos) ✅
- **Turno 1** ("quero falar com uma pessoa"): agente **NÃO transferiu**; perguntou: *"Claro! Só pra te direcionar à pessoa certa — é sobre orçamento/visita, um equipamento ou manutenção, portaria/escala, ou financeiro?"*
- **Turno 2** ("é sobre uma câmera com defeito"): agente **chamou transferir_conversa setor=suporte_tecnico** e avisou o cliente. ✅

### Teste 2 — assunto CLARO → triagem NÃO vaza ✅ (com nuance honesta)
- O **menu de triagem NÃO aparece** em assunto claro (objetivo central: triagem só no vago) ✅.
- Direct-transfer no assunto claro é **inconsistente no gpt-4o-mini**: "câmera parou… **urgente**" → transferiu direto suporte_tecnico; "câmera quebrou" / "alarme com defeito" → **qualificou primeiro** (perguntou se é cliente/CNPJ) em vez de transferir.
- **Não é regressão da edição:** a mesma frase "urgente" que transferia direto antes **continua** transferindo direto; o qualificar-primeiro é comportamento **pré-existente** ("transferir = último recurso / resolver primeiro", já no prompt antes desta edição).

## 3. Garantias
- **host==container** (`78467910…`) · backend **healthy** · **health 200**.
- Copiloto intacto. `cwi_message_log` de teste = 0.

## 4. Durabilidade (PENDÊNCIAS — agora 3 itens p/ próximo rebuild)
Vivem via docker cp sobre a imagem `b18575b9` (commitados):
1. F-VISITA.2 e-mail — `983378bb`
2. Tool transferir_conversa — `026f6f85`
3. Triagem no vago — `31b8195f`
➡️ Bakar no próximo rebuild. **NÃO rebuildei** (é o próximo passo, separado).

---

## Resumo
- Triagem no pedido vago: agente pergunta o assunto antes de transferir; comercial só último recurso. ✅
- Teste 1 (vago→triagem→suporte) OK; Teste 2 (triagem não vaza no claro) OK. Direct-transfer no claro é variável no gpt-4o-mini (não regressão). ✅
- Só prompt; host==container; health 200; commit `31b8195f`. ✅
- Pendente: bakar no rebuild (3 itens). Não rebuildei.

*PAREI. Não rebuildei.*
