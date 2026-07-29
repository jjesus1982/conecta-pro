# Fase 6 — Consultores que PRODUZEM/AGEM por módulo no chat in-ERP — Design
**Data:** 2026-07-29 · Discovery a46b6401 (graphify+ponytail). Jordan: chat interno de cada módulo recebe ordem do que ele representa (RH calcula folha, comercial monta proposta, etc.), reusando o que já existe.

## Achado (governa o design)
Conector MCP `mcp-server/server.py` (~230 tools FastMCP) roda com CONTA DE SERVIÇO fixa (não identidade do user) e `tool_risk_manifest.py` rotula quase tudo "read" (inclusive criar_contrato/fechar_folha/enviar_proposta/excluir_*). NÃO importar cru → LLM executaria dinheiro/efeito sozinho (fura propor→aprovar 5.4). Orquestrador escopado (engine.py+tool_registry.ToolDef, handler `(db,user,scope,**args)`) roda com identidade+RBAC real e chama serviço direto.

## Objetivo (1 frase)
Cada módulo, pelo chat interno, produz/age no que representa — reusando geradores branded + serviços reais + RBAC + propor→aprovar já existentes, sem recodar endpoint.

## Arquitetura — 3 baldes (reuso máximo)
1. **LER (~150-180):** adaptador genérico que gera ToolDef a partir dos endpoints/schema que o MCP já usa, MAS com identidade real do user (JWT logado) + `module`+`_gate` do orquestrador (RBAC na fonte). Reusa description/params do MCP. Auto-registro por tabela `{nome:(módulo,path)}`.
2. **GERAR DOC (~30-40: gerar_*_pdf/baixar_*/gerar_apresentacao/orçamento):** ToolDef direto (sem gate) — produz artefato BRANDED pelo gerador real; não move dinheiro/direito. TRAVA DURA: os dados (valor/descrição) vêm de uma tool de CONSULTA real no mesmo turno, NUNCA preenchidos livres pelo LLM (nunca fabricar em doc de cliente → bloqueio, não aviso).
3. **AÇÃO-GATED (~15-25: criar/enviar/excluir/fechar/ativar/lote_pagamento/transmissão):** NÃO reusa função MCP — replica molde `acoes/onda_*.py::propor()` (idempotência+RBAC aprovador+audit), reclassificado por EFEITO REAL (não pelo rótulo "read" do manifesto).

## Global Constraints (invioláveis)
- RBAC pela identidade REAL do user (nunca conta de serviço). Tool só aparece p/ quem tem o módulo (`tools_for_modules`).
- LLM NUNCA executa dinheiro/efeito — propor→aprovar (5.4). Dinheiro/eSocial 🔴 humano+OTP.
- NUNCA fabricar: doc de cliente branded só com número de tool real (bloqueio duro); nunca margem/custo/MRR em material de cliente.
- Doc branded só pelos geradores reais (regra do conector). Audit append-only de todo write. TZ Manaus.
- Ponytail: adaptador genérico p/ read (não reescrever 180 à mão); molde propor() existente p/ ação (não reinventar).

## Decomposição (cada balde/módulo = fatia própria; NÃO fazer 230 de uma vez)
- **Fatia 1 (recomendada — o exemplo do Jordan):** GERAR DOC comercial — "monta proposta/orçamento de <produto do portfólio>" no chat do CRM, reusando proposal_pdf/doc_pdf + preço real (simular_preco/parametros). Prova o balde gera-doc + a trava anti-fabricação.
- **Fatia 2:** adaptador READ genérico → todos os módulos passam a "responder qualquer coisa" (o balde read, ~150 tools de uma vez pelo adaptador).
- **Fatia 3+:** ação-gated por módulo (financeiro/DP/operacional...), molde propor().

## Testabilidade
Oráculos por fatia: RBAC (tool não vaza p/ módulo alheio), nunca-executa-dinheiro (baseline), nunca-fabrica (doc só com dado de tool real; mutação: LLM inventa valor → bloqueio morde), branding (doc sai pelo gerador real). Bancada throwaway; nunca backend vivo.

## Resumo
3 baldes reusando o que existe: adaptador read (identidade real), gera-doc branded (trava anti-fabricação), ação via propor() (reclassificado por efeito). Começar pela fatia comercial (proposta/orçamento), expandir módulo a módulo.
