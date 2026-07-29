# Fase 6 — Fatia 1: gera-doc comercial no chat (proposta/orçamento branded) — Plan

> SUB-SKILL: superpowers:subagent-driven-development. Ponytail OBRIGATÓRIO em todo pareamento.

**Goal:** No chat interno (consultor-ia escopado), quem tem o módulo `crm` pede "monta uma proposta/orçamento de <produto do portfólio> pro condomínio X" e recebe o PDF BRANDED — reusando os geradores reais + preço real, nunca fabricando número.

**Architecture:** Registrar 2-3 ToolDefs gera-doc no orquestrador escopado (`orquestrador/`), módulo `crm`, chamando os geradores branded existentes (`crm/services/proposal_pdf.py`/`doc_pdf.py`) com dados de PREÇO/CLIENTE vindos de tools de consulta reais. Sem propor→aprovar (é rascunho de doc, não move dinheiro/não envia). Frontend: reusar o chat consultor-ia (o user com módulo crm já vê a tool) — SEM UI nova no MVP.

**Contexto p/ retomar (spec + discovery):** `docs/superpowers/specs/2026-07-29-fase6-consultores-executores-design.md`. Discovery: conector MCP `mcp-server/server.py` (~230 tools, conta de serviço) NÃO reusar cru; geradores reais em `crm/services/{proposal_pdf,doc_pdf,pdf_generator,report_pdf}.py`; orquestrador `tool_registry.ToolDef` handler `(db,user,scope,**args)`, filtra por `module`; molde de tool = `orquestrador/tools_modulos.py`; molde de doc = a skill `conecta-pro-skills:gold-standard-pdf`.

## Global Constraints (invioláveis)
- RBAC pela identidade real (módulo crm). NUNCA fabricar: valor/preço vêm de tool de consulta real (simular_preco / parametros_precificacao / listar_precos_funcao) no mesmo turno — se o LLM tentar preencher valor livre sem lastro, BLOQUEIA (não gera). Nunca margem/custo/MRR em doc de cliente.
- Doc SÓ pelo gerador branded real (regra do conector MCP + skill gold-standard-pdf). É RASCUNHO — enviar/criar-contrato = fase de ação (propor→aprovar), NÃO nesta fatia.
- Ponytail: reusar gerador + chat existentes; menor diff; 1 self-check. Bancada throwaway (rede conecta-pro_conecta-pro-network, nunca backend vivo/green:8080); git add próprios + commit imediato; --no-verify + Co-Authored-By Opus 4.8; TZ Manaus.

## Tasks
### F1T1 — ToolDefs gera-doc comercial
- LER: os geradores reais de proposta/orçamento em `crm/services/` (assinatura: que dados exigem) + as tools de preço reais (simular_preco/parametros_precificacao — serviço) + `tools_modulos.py` (molde ToolDef) + invocar skill `conecta-pro-skills:gold-standard-pdf`.
- Criar `orquestrador/tools_comercial_doc.py`: ToolDef(s) `gerar_proposta_comercial_doc` / `gerar_orcamento_doc`, module="crm", handler `(db,user,scope,**args)` que: (1) resolve cliente/condomínio real; (2) puxa PREÇO do serviço real de precificação p/ o produto do portfólio (NUNCA do arg livre do LLM); (3) chama o gerador branded → PDF; (4) retorna link/base64 + resumo. Se preço não-lastreado → recusa ("preciso do preço via cadastro real"), não fabrica.
- Importar o arquivo no ponto que dispara register() (mesmo padrão do wiring 5.4: `consultor_escopado_controller` importa acoes/onda_*). 
- Self-check bancada: user com crm + produto do portfólio → gera PDF branded com preço REAL; sem lastro de preço → recusa (não fabrica). Commit.

### F1T2 — oráculos + mutação
- `scripts/orq/test_oraculos_fase6_f1.py`: (1) branding — doc sai pelo gerador real; (2) nunca-fabricar — valor no doc == valor da tool de preço real, nunca do LLM; (3) RBAC — tool não aparece p/ user sem crm. Mutação: LLM injeta valor livre → bloqueio morde. Bancada. Commit.

### F1T3 — deploy + verify
- Blue-green (peer-churn provável). Verify: user crm no chat consultor-ia → "monta proposta de portaria remota" → PDF branded com preço real. Push com OK Jordan.

## Próximas fatias (fora desta)
Fatia 2 = adaptador READ genérico (todos módulos respondem tudo). Fatia 3+ = ações-gated por módulo (financeiro/DP/operacional) via propor(). Fatia 4 = chat embutido em cada tela de módulo (frontend).
