# F-VISITA.1 — tool agendar_visita REAPLICADA e VALIDADA ✅ (agente cria visita)

- **Data:** 2026-06-09
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Status:** ✅ **Entregue e funcional.** Agora que o `POST /campo/visitas/` funciona (fix `4a1296e3`), a 3ª tool foi reaplicada e o agente cria visita de verdade — em modo COPILOTO.
- **Arquivo:** `modules/integrations/connectors/whatsapp/agent_service.py` · **Backup do ativo (2 tools):** `agent_service.py.bak-reaply2tools-20260609-135805`
- **Commit:** **`87f0def9`** — `feat(whatsapp): tool agendar_visita F-VISITA.1 (propoe visita AGENDADA, copiloto)`

---

## 1. Diff — confirma "só a tool"
Diff entre o arquivo preservado (3 tools) e o ativo (2 tools) → única diferença é a 3ª tool:
- **Adicionado:** schema `agendar_visita`, `_tool_agendar_visita`, `_resolve_lead_id`, `AGENT_VISITA_RESPONSAVEL_ID`, branch no `_exec_tool`, parágrafo "Agendamento de visita" no SYSTEM_PROMPT.
- **Alterado:** `_exec_tool(name, args)` → `_exec_tool(name, args, conversation_id)` (assinatura + chamada).
- **Nada mais** (3 linhas `<` removidas, todas esperadas). Aplicado por cópia do arquivo preservado.

## 2. Testes E2E (agente de verdade, copiloto)

### Teste A — lead pede visita COM endereço + data/hora → CRIA
- **Tool-call:** `agendar_visita args={data_visita:2026-06-12, horario_inicio:09:00, endereco:'Rua das Acácias, 456', bairro:'Cidade Nova', cidade:'Manaus', nome_contato:'Carlos Mendes', telefone_contato:...}` → `{ok:True, numero:VIS-2026-00001, status:AGENDADA}`. tool_rounds=2.
- **Visita no banco:** `numero=VIS-2026-00001, status=AGENDADA, responsavel_id=ad9abb59-..., origem=LEAD, tipo=COMERCIAL, is_prospect=True, endereco/data/hora corretos`. ✅
- **Resposta (nota privada/rascunho) — linguagem de SOLICITAÇÃO:**
  > "Vou encaminhar sua **solicitação de visita** para quinta-feira, 12 de junho de 2026, às 09:00, na Rua das Acácias, 456, Cidade Nova, Manaus. Nossa **equipe confirmará** o horário com você em breve."
  - ✅ Nunca diz "agendada/confirmada". Gerencia expectativa corretamente.

### Teste B — lead pede visita SEM endereço → NÃO cria, pergunta
- Resposta: *"Qual o endereço onde você gostaria que a visita fosse realizada? ... poderei fazer a solicitação para a equipe confirmar o horário com você."* — agente **pergunta o endereço**, não cria visita incompleta. ✅

### Teste C — limpeza
- Visitas de teste deletadas → `visitas` = **0**. `cwi_message_log` de teste = **0**. ✅

## 3. Garantias
- **Copiloto intacto:** `gerar_resposta` só retorna texto; entrega via `_log_draft` (drf) + `_post_private_note`. **Nada enviado ao cliente** (sem `send_custom`).
- **3 tools ativas:** `consultar_cnpj`, `buscar_cliente`, `agendar_visita`.
- **host==container** (`3dfd63a3…`) · backend **healthy** · **health 200** · webhook token errado → **401**.
- Custo logado: `tool_rounds` + tokens por resposta.

## 4. Durabilidade (pendências para o PRÓXIMO rebuild)
Vivem via docker cp sobre a imagem `5958168f` (commitadas):
1. Fix do model `campo` — commit `4a1296e3` (FK + enum + tipos).
2. Tool `agendar_visita` — commit `87f0def9`.
➡️ O rebuild baka as duas. **NÃO feito agora** (passo separado, sob seu comando).

---

## Resumo
- 3ª tool `agendar_visita` reaplicada (diff = só a tool), **commit `87f0def9`**. ✅
- Teste A: agente criou `VIS-2026-00001` (AGENDADA, responsavel ad9abb59, origem LEAD) com fraseado de **solicitação**. ✅
- Teste B: sem endereço → pergunta, não cria. ✅ · Teste C: limpo (visitas=0). ✅
- Copiloto + 3 tools + host==container + health 200. ✅
- Pendente p/ rebuild: `4a1296e3` + `87f0def9`. Não rebuildei.

*PAREI. Não rebuildei.*
