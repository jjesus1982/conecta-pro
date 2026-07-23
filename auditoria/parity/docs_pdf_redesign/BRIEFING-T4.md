# BRIEFING — TERMINAL 4 (T4) · Operacional + Campo + Saúde + Jurídico + Relatórios + GED/Docs + BI

> Missão: ligar botões **abrir HTML + baixar PDF** em TODO documento do seu território no **redesign**.
> Trabalhe em **LOOP** até fechar o checklist. **NÃO faça deploy nem use o browser** (release + E2E são do orquestrador).
> Leia antes: `REGRAS-SESSAO.md`, `CONTRATO-FUNDACAO.md`, `MATRIZ-MESTRE-REDESIGN.md`, `PRE-MORTEM.md`.
> **Commit por etapa com PATHSPEC**: `git commit --no-verify -- <seu_builder.py>` (retry 2s se `index.lock`).

## Seu território (edite SÓ estes builders)
`redesign_builders/`: **operacional.py · campo.py · saude_ocupacional.py · juridico.py · relatorios.py · documentos.py · bi.py**
Módulos redesign: operacional (37 telas), campo, saude-ocupacional, juridico, relatorios, documentos, bi.

> **NUNCA** edite fora da lista nem a fundação. Documentos/GED e saude são SEUS; DP/ponto/portal são do T2 — não colida. Caso novo → orquestrador.

## Documentos a ligar (rota EXATA — curl-verifique 200+type antes)
**✅ ready:**
- operacional/rondas → `GET /api/v1/operacional/rondas/{id}/relatorio/pdf` (por-linha, PDF) — **provado 200**.
- operacional (ocorrencias/turnos/colaboradores/escalas/alocacoes/rondas/postos) → export da lista (client-side — ver `<ExportMenu>` abaixo).
- documentos/kits → ZIP por kit `/api/v1/ged/kits/{id}/download-zip` (**JÁ FEITO na piloto** — expanda o padrão; é o seu builder documentos.py).
- juridico/pareceres → `/api/v1/juridico/pareceres/{id}/pdf` (por-linha).
- juridico/det → `/api/v1/juridico/det/comunicacoes/{id}/pdf` (por-linha).
- saude (SST) → ASO/EPI/NR-1/PPP: `/api/v1/people-management/sst/nr1/compliance/pdf`, `/sst/epi/fichas/{id}/pdf`, etc. (confirme cada uma via curl).
- relatorios/central → relatórios PDF do hub.

**🔨 criar rota/render (só-JSON — sinalize ao orquestrador se precisar rota nova):**
- operacional (buraco grande): cobertura, horas, custos, diárias, fechamento diaristas, passagem de turno, instruções de posto, presença, banco de horas, grade, OS, avaliação — hoje só JSON. Para cada: rota `/pdf` (peça) OU export client-side.
- juridico: dossiês/processos/análise (só-JSON).

**⛔ NÃO ligar (disabled honesto):**
- `/campo/visitas/{id}/pdf` — **SEM auth** → `disabled=True, motivo="rota sem autenticação — aguardando correção"`.
- documentos/arquivos (ged_kit_documents) — **sem rota por-doc** (a `/ged/documents/{id}/download` serve tabela VAZIA). Download real = ZIP do kit. Não invente botão por-doc.

## Ferramenta a construir/portar (fale com orquestrador — pode virar fundação)
`<ExportMenu>` (Excel/PDF/CSV client-side; libs `xlsx`/`jspdf`/`jspdf-autotable` já instaladas) p/ as 7 telas operacionais que exportam a lista.

## Fluxo do loop
rota real (curl 200) → `scr.docs`/`docsfn` → py_compile → `git commit -- operacional.py` (só o seu) → checklist. **Sem deploy, sem browser.** Ao terminar, reporte o checklist ao orquestrador.

## Regras de ouro (pré-mortem)
Rota EXATA · nunca fabricar (⛔=disabled honesto) · gate no backend · importe todos os helpers · id na 1ª coluna p/ por-linha · modo certo (json vs blob).
