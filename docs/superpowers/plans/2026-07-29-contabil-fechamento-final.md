# Contábil Autônomo — Fechamento Final & Prova de Paridade — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (execução inline em loop, autonomia total). Steps usam checkbox `- [ ]`. **ponytail OBRIGATÓRIO.**

**Goal:** Consolidar o contábil autônomo: confirmar o razão reconciliado (Folha/INSS ✓, FGTS ~5%) durável nos dois CNPJs, e produzir a PROVA persistida de paridade razão×oráculo (o artefato dos 6 meses em paralelo com a Portte).

**Architecture:** O motor (`LedgerAutoService.fechar_grupo`) já posta folha + ISS + INSS empregado + INSS patronal (guia − retido) e já é orquestrado pelo Celery `financial.fechar_razao_auto`. Falta: (1) confirmar o bake e o fechamento end-to-end por CNPJ; (2) persistir um relatório mensal de reconciliação em `auditoria/`; (3) medir/classificar o resíduo FGTS; (4) confirmar o agendamento. NÃO transmite a gov nem paga — gate humano.

**Tech Stack:** Python no container (`docker exec`), SQLAlchemy/psycopg2, harness `scripts/contabil_recon_razao.py`, Celery `modules/financial/tasks.py`.

## Global Constraints
- **Reusar, não recodar** (ponytail). O motor e a orquestração existem; só verificar e persistir a prova.
- **Nunca fabricar.** Oráculo = guia/nota oficial no banco. Vazio real = "aguardando dado".
- **CNPJ-scoped.** Eletrônica=619a3df1… (Lucro Real), Patrimonial=7d79ed12… (Simples).
- **Read-only até gate.** Harness/relatório NUNCA transmite nem paga.

---

### Task 1: Confirmar bake + fechar_grupo reconciliado (ambos CNPJs)

**Files:** Modify: nenhum (verificação). Read: `modules/financial/services/ledger_auto_service.py`.

**Interfaces:**
- Consumes: `LedgerAutoService().fechar_grupo()` → `{empresas: {slug: {novos_lancamentos:{...,inss_empregado,inss_patronal}, ...}}}`.
- Produces: prova de que o código baked posta INSS empregado+patronal e o razão reconcilia.

- [ ] **Step 1:** Confirmar bake concluído: `tail bake.log` até "removido/FIM"; `curl -sf http://127.0.0.1:8080/health`.
- [ ] **Step 2:** Confirmar no container que `/app/.../ledger_auto_service.py` contém `lancar_inss_patronal` e a chamada em `fechar()`; e `das_extractor.py` no EXTRACTOR_MAP.
- [ ] **Step 3:** Rodar `LedgerAutoService().fechar_grupo()` (idempotente). Esperado: `inss_empregado`/`inss_patronal` presentes; sem erro por CNPJ.
- [ ] **Step 4:** Rodar `scripts/contabil_recon_razao.py`. Esperado: Folha Δ=0, INSS Σ|Δ|<1% (bate), FGTS Σ|Δ|~2,3k.
- [ ] **Step 5:** Despausar `conecta-pro-det-robot` (foi pausado no bake).

### Task 2: Relatório de reconciliação persistido (a PROVA dos 6 meses)

**Files:**
- Create: `scripts/contabil_reconciliacao_report.py`
- Output: `auditoria/contabil_reconciliacao_<YYYY-MM-DD>.md`

**Interfaces:**
- Consumes: `accounting_entries` (razão, por empresa_id/periodo/tipo), `hr_payslips`, `fgts_guias`/`inss_guias` (oráculo), `nfse_emitidas_nacional`.
- Produces: markdown com tabela **por CNPJ × pilar × competência**: Σ nosso, Σ oráculo, Δ, status; + rodapé com data e ressalvas ("junho = lag postagem", "FGTS resíduo timing").

- [ ] **Step 1:** Copiar a lógica de `contabil_recon_razao.py` para o report, adicionando `GROUP BY empresa_id` (Eletrônica vs Patrimonial) e escrita em arquivo. Reusar as mesmas queries/pares (mes_ref "MM.YYYY", FGTS tipo='GUIA').
- [ ] **Step 2:** Rodar no container; salvar a saída em `auditoria/contabil_reconciliacao_<data>.md` (via `docker exec ... > arquivo` no host).
- [ ] **Step 3:** Validar que o arquivo existe, tem as duas empresas, e os totais batem com o harness da Task 1.

### Task 3: Resíduo FGTS ~5% — medir e classificar (não fabricar)

**Files:** Read-only investigação; se fix trivial, Modify `ledger_auto_service.py` OU só documentar.

**Interfaces:**
- Consumes: `hr_payslips.fgts_value` (base do razão), `fgts_guias` tipo='GUIA' (oráculo).
- Produces: classificação do Δ (+133..+806/mês) — timing (guia de mês fechado no mês seguinte), 13º/base, ou consignado vazando.

- [ ] **Step 1:** Comparar por competência `sum(hr_payslips.fgts_value)` vs `fgts_guias(GUIA).valor`; ver se o Δ é constante (base) ou cresce (13º/timing).
- [ ] **Step 2:** Checar se a guia GUIA de um mês corresponde à folha do MESMO mês ou do anterior (FGTS Digital vence mês seguinte) — possível desalinhamento de competência.
- [ ] **Step 3:** Se for desalinhamento de competência (não erro de valor): documentar no relatório como ressalva conhecida (não mexer — é característica do FGTS Digital). Se for erro real de base: corrigir a fonte. **Decidir por medição, não suposição.**

### Task 4: Confirmar agendamento + estado do DAS

**Files:** Read: `modules/financial/tasks.py`, config do celery-beat.

- [ ] **Step 1:** Confirmar que `financial.fechar_razao_auto` está no schedule do celery-beat (grep beat config / `celery inspect`). Se SIM: nada a fazer (ponytail). Se NÃO: reportar (não adicionar sem aval — pode duplicar).
- [ ] **Step 2:** Confirmar DAS: valores em `onvio_documents.detalhes_json` (categoria das_simples_nacional). Registrar que a reconciliação do DAS/parcelamento exige o "lado nosso" (posting do parcelamento no razão) — próxima fatia, fora deste plano.
- [ ] **Step 3:** Atualizar memória `project_contabil_autonomo_baseline.md` com o estado final e o caminho do relatório persistido.

## Guardrails / Ordem
T1 confirma o durável. T2 entrega a prova. T3 fecha (ou documenta honestamente) o último resíduo. T4 confirma que roda sozinho. Nunca transmite/paga. Métrica: Σ|Δ| por pilar/CNPJ no relatório persistido.
