# BRIEFING — TERMINAL 1 (T1) · Operacional + Campo + Saúde + Jurídico + Relatórios + GED/Docs + BI

> Missão: ligar botões **abrir HTML + baixar PDF** em TODO documento do seu território no **redesign**.
> Trabalhe em **LOOP** até fechar o checklist. **NÃO faça deploy** (o release é único, feito pelo orquestrador/T1-release). Leia antes: `CONTRATO-FUNDACAO.md`, `MATRIZ-MESTRE-REDESIGN.md`, `PRE-MORTEM.md`.

## Seu território (edite SÓ estes builders)
`redesign_builders/`: **operacional.py · campo.py · saude_ocupacional.py · juridico.py · relatorios.py · documentos.py · bi.py**
Módulos redesign correspondentes: operacional (37 telas), campo, saude-ocupacional, juridico, relatorios, documentos, bi.

> **NUNCA** edite arquivo fora desta lista, nem a fundação (`ModuleView.tsx`, `docsource.ts`, `DocButtons.tsx`, `doc()`/`tbl` no `redesign_data_controller.py`). Precisa de caso novo → fale com o orquestrador.

## Documentos a ligar (da MATRIZ — confira a rota EXATA no código antes)
**✅ ready (rota real, só ligar):**
- operacional/rondas → `GET /api/v1/operacional/rondas/{id}/relatorio/pdf` (por-linha, PDF) — **provado 200**.
- operacional (ocorrencias/turnos/colaboradores/escalas/alocacoes/rondas/postos) → export da lista (client-side `<ExportMenu>` — ver nota abaixo).
- documentos/kits → ZIP por kit `/api/v1/ged/kits/{id}/download-zip` (**já feito na piloto** — expanda o padrão).
- juridico/pareceres → `/api/v1/juridico/pareceres/{id}/pdf` (por-linha).
- juridico/det → `/api/v1/juridico/det/comunicacoes/{id}/pdf` (por-linha).
- saude (SST) → ASO/EPI/NR-1/PPP via `lib/services/sst.ts` equivalentes: `/api/v1/people-management/sst/nr1/compliance/pdf`, `/sst/epi/fichas/{id}/pdf`, etc. (confirme cada uma).
- relatorios/central → relatórios PDF do hub.

**🔨 criar rota/render (só-JSON hoje — sinalize se precisar de rota nova no backend):**
- operacional: cobertura, horas, custos, diárias, fechamento diaristas, passagem de turno, instruções de posto, presença, banco de horas, grade, OS, avaliação — **buraco grande**, hoje só JSON. Para cada: ou o backend ganha `/pdf` (peça ao orquestrador), ou exporta a lista client-side (`<ExportMenu>`).
- juridico: dossiês/processos/análise (só-JSON).

**⛔ NÃO ligar (corrigir antes / desabilitar honesto):**
- `/campo/visitas/{id}/pdf` — **SEM auth**. Deixe `disabled=True, motivo="rota sem autenticação — aguardando correção"` até o backend adicionar `CurrentActiveUser`.
- documentos/arquivos (ged_kit_documents) — **sem rota de download por-doc** (a `/ged/documents/{id}/download` serve tabela vazia). Não invente botão por-doc; o download real é o ZIP do kit. (Gap registrado: se quiser download por-doc, peça rota nova ao backend.)

## Ferramenta a construir/portar (fale com orquestrador antes — pode virar fundação)
`<ExportMenu>` (Excel/PDF/CSV client-side, libs `xlsx`/`jspdf`/`jspdf-autotable` já instaladas) para as 7 telas operacionais que exportam a lista. Se for genérico, o orquestrador coloca na fundação.

## Fluxo do loop
1. Pegue a próxima tela do checklist. Confirme a rota REAL no backend (grep + montada em `main_production.py`).
2. Adicione `scr["docs"]` (nível-tela) ou `docsfn` (por-linha) no seu builder — importe `doc` no topo.
3. `python3 -m py_compile <seu_builder>.py`.
4. Rode o oráculo in-process (`documentos.build(db)` → confira os docs emitidos).
5. `git add <seu_builder>.py` (só o seu) + commit por etapa (2-3 telas/commit, `--no-verify`, `Co-Authored-By: Claude Opus 4.8`).
6. Marque no checklist. Repita. **Sem deploy.**

## Regras de ouro (pré-mortem)
Rota EXATA · nunca fabricar (⛔=disabled honesto) · gate é no backend · importe todos os helpers · id na 1ª coluna p/ por-linha · modo certo (json vs blob).
