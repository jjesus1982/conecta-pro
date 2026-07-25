# Sub-projeto A — Folha Autoritativa · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline) para implementar task-a-task. Steps usam checkbox (`- [ ]`).

**Goal:** Tornar a folha nativa do Conecta PRO a fonte primária confiável — persistida, com IRRF certificado e conciliada centavo-a-centavo com a Portte — sem tocar no espelho Portte.

**Architecture:** Motor nativo já calcula (`calculo_service.calcular_folha_colaborador`). O plano: certifica IRRF, persiste em `hr_payslips` com `source_system='conecta'` (isolado do `'portte'`), unifica faltas/benefícios, e prova por conciliação cega. O guard (`calcular_folha_batch_com_guard`) só inverte para o nativo quando a conciliação bate zero.

**Tech Stack:** FastAPI, SQLAlchemy (Session sync), Postgres, Decimal p/ dinheiro. Verificação por ORÁCULO (curl/query vs dado real), não pytest.

## Global Constraints
- **Dado legal não se fabrica** — enquanto `IRRF_CERTIFICADA_2026=False`, holerite nativo carrega selo de estimativa; só vira legal após conciliar. [[feedback_dado_real_vs_simulado]]
- **Nunca sobrescrever `source_system='portte'`** — nativo grava só `'conecta'`. Multi-CNPJ por `empresa_id`.
- **Money-out não entra aqui** (A não paga nada). Sem deploy no meio de trabalho de outra sessão (árvore compartilhada) — build+commit, bake só em árvore limpa.
- Verificação: `docker exec conecta-pro-backend` + query real; NUNCA importar `main_production` em processo (OOM).

---

> **ACHADO DE EXECUÇÃO 2026-07-25 (A1, oráculo real):** **0 payslips Portte têm IRRF>0** — toda
> a folha está sob a isenção (piso portaria). Ao computar o nativo nos maiores brutos, 3/8
> divergem (nativo cobra IRRF onde a Portte tem 0) — MAS a causa é estrutural, não fórmula: esses
> brutos altos têm **INSS=0 na Portte** (liminar "INSS não retido" da PATRIMONIAL e/ou verbas
> não-tributáveis), o que muda a base. **Conclusão: NÃO certificar (flag `IRRF_CERTIFICADA_2026`
> fica False)** — certificar exige tratar o liminar por CNPJ + composição de verbas, que só a
> conciliação (A4) mapeia. A1 fica BLOQUEADA por dependência técnica de A4, não por fórmula.
> Reordem autônoma: **A4 (conciliação diagnóstica) vira prioridade** — ela quantifica todos os
> gaps (IRRF, INSS-liminar, faltas) por rubrica×CNPJ e vira o roteiro data-driven de A1/A3.
>
> **MÉTODO (corrigido):** container backend tem limite de **6GB**; importar a cadeia da folha num
> 2º processo via `docker exec python` estoura o cgroup e mata o container. Verificar SEMPRE pela
> **rota da API** (curl no app já carregado) ou query SQL mínima — NUNCA importar a cadeia pesada
> (folha/main_production) em processo novo. [[feedback_verificar_rota_da_tela]]

### Task A1: Certificar IRRF 2026 (validar redutor vs Portte → virar a flag)

**Files:**
- Modify: `backend/modules/people_management/common/utils/clt_calculator.py:27` (`IRRF_CERTIFICADA_2026`)
- Oráculo: `hr_payslips` (irrf_value real da Portte) × `calcular_irrf`

- [ ] **Step 1 (falha/oráculo):** Para cada funcionário com `hr_payslips` source='portte' e `irrf_value>0` (jan–jun), computar `calcular_irrf(base, dependentes, pensao, rendimento_bruto=bruto)` e comparar com `irrf_value`. Rodar via `docker exec ... python` com query real. Esperado inicial: pode divergir (redutor não validado).
- [ ] **Step 2:** Se divergir, ajustar o redutor da reforma em `calcular_irrf:97-142` até bater centavo-a-centavo nos casos reais (base = bruto − INSS − deduções; redutor Lei 15.270). Documentar os casos-teste no próprio commit.
- [ ] **Step 3 (oráculo verde):** Re-rodar: nativo IRRF == Portte IRRF em ≥90% dos funcionários com IRRF>0 (os que divergem, listar com causa — dependente/pensão não cadastrada = dado a corrigir, não erro de fórmula).
- [ ] **Step 4:** Só então `IRRF_CERTIFICADA_2026 = True` e reavaliar `TABELAS_LEGAIS_CERTIFICADAS_2026`.
- [ ] **Step 5:** Commit `feat(folha): certifica IRRF 2026 (redutor reforma conciliado vs Portte)`.

### Task A2: Persistir a folha nativa (`source_system='conecta'`, idempotente)

**Files:**
- Modify: `backend/modules/people_management/folha/services/calculo_service.py` (`fechar_folha:373` e/ou novo `persistir_folha_nativa`)
- Ref: caminho de escrita de `hr_payslips` (calculo_service já referencia; `dp_payslips_controller.py:309` /importar-lote é o molde de INSERT)

- [ ] **Step 1 (oráculo):** Query `SELECT count(*) FROM hr_payslips WHERE source_system='conecta'` → 0 (ainda não persiste).
- [ ] **Step 2:** Implementar `persistir_folha_nativa(db, mes, ano, empresa_id)`: roda `calcular_folha_batch`, faz UPSERT em `hr_payslips` com `source_system='conecta'`, idempotente por `(employee_id, reference_month, reference_year, source_system)`. Grava bruto/líquido/INSS/IRRF/FGTS/rubricas. NÃO toca linhas `'portte'`.
- [ ] **Step 3 (oráculo verde):** Rodar p/ 1 competência de teste → `SELECT count(*), source_system FROM hr_payslips GROUP BY source_system` mostra linhas `conecta` novas; re-rodar não duplica.
- [ ] **Step 4:** Commit `feat(folha): persiste folha nativa em hr_payslips (source=conecta, idempotente)`.

### Task A3: Unificar motores — aplicar faltas + benefícios reais no motor CCT

**Files:**
- Modify: `backend/modules/people_management/folha/services/calculo_service.py` (importar lógica de faltas de `payroll_service.py:190-201` e benefícios reais de `EmployeeBenefit` `payroll_service.py:168-188`)

- [ ] **Step 1 (oráculo):** Achar funcionário com falta registrada (`gp_justifications`/ponto) e comparar líquido nativo (motor CCT) vs Portte — hoje diverge (CCT não desconta falta).
- [ ] **Step 2:** No `calculo_service`, aplicar desconto de faltas/atrasos (reusar a fonte de `payroll_service:413-474`) e trocar odonto/taxa hardcoded (`calculo_service:61,440-464`) por `EmployeeBenefit` real quando existir.
- [ ] **Step 3 (oráculo verde):** Nativo com faltas bate o Portte para os casos com falta.
- [ ] **Step 4:** Commit `feat(folha): motor CCT aplica faltas + benefícios reais (unifica com payroll_service)`.

> **RESTRIÇÃO DE EXECUÇÃO A4 (2026-07-25, provada):** o cálculo em LOTE
> (`calcular_folha_batch` via `/resumo` ou `/dashboard`) **OOM-mata o container backend (6GB)** —
> o app já usa ~5GB, o batch de 56 func estoura o cgroup (isolado do host, mas derruba a produção
> ~40s). O cálculo INDIVIDUAL (`/calcular/{id}/{mes}/{ano}`) é **seguro** (leve, 200). Logo A4
> deve rodar **funcionário-a-funcionário** (acumulando do lado de fora), NUNCA o batch; ou bump
> temporário do `--memory` do container (host tem ~13GB livres; earlyoom+guardian protegem). NÃO
> repetir o batch. [[project_oom_blindagem_v2]]
>
> **REFINAMENTOS DE REQUISITO (Jordan 2026-07-25) — a A4 tem que segmentar:**
> - **jan–maio/2026 = ELETRÔNICA** (Lucro Real; INSS/IRRF normais). **junho e julho = PATRIMONIAL**
>   (Simples Anexo III; CPP patronal vai no DAS, não em GPS; retenção de INSS 11% na nota de cessão).
> - **Liminar PIS/COFINS/INSS NÃO obtida** → retenção ativa; **INSS em dobro (nota + DAS)**. Não
>   zerar nada até deferir.
> - **Competência × caixa:** julho gera (NFS-e + folha) → agosto recebe/paga (folha até 5º dia útil).
> - 1º ponto real (ADAILSON, Patrimonial, jun): nativo bruto 2286 / INSS 181 / líq 1832 vs Portte
>   2928 / 79 / 643 → divergências estruturais (verbas, INSS, ~R$1830 descontos) a mapear, NÃO chutar.

### Task A4: Conciliação cega nativo × Portte (relatório de divergência por rubrica)

**Files:**
- Create: `backend/modules/people_management/folha/services/conciliacao_folha_service.py`
- Expose: tela redesign DP (g-folha) "Conciliação nativo×Portte" (read-only)

- [ ] **Step 1:** `conciliar(db, mes, ano)`: para cada CLT × 2 CNPJs, computa nativo e diffa vs `hr_payslips` source='portte' por rubrica (bruto, INSS, IRRF, FGTS, líquido); retorna {n, batem, divergem[], por_rubrica}.
- [ ] **Step 2 (oráculo):** Rodar jan–jun; relatório de divergência. Meta = 0 divergência de líquido; divergências restantes com causa (dado cadastral).
- [ ] **Step 3:** Tela read-only mostra o status real (nunca fabrica "0%" — mostra o que a query retorna).
- [ ] **Step 4:** Commit `feat(folha): conciliação cega nativo×Portte por rubrica + tela`.

### Task A5: Recibos de férias e 13º (PDF padrão-ouro)

**Files:**
- Create: `backend/modules/people_management/hr/services/recibo_ferias_pdf.py`, `recibo_13_pdf.py` (molde `trct_pdf.py:59`, `holerite_pdf.py`)
- Expose: endpoints + botões doc no redesign DP

- [ ] **Step 1:** Gerar PDF de recibo de férias (cálculo já existe `clt_calculator:250-274`) e de 13º (`:277-288`, 1ª/2ª parcela).
- [ ] **Step 2 (oráculo):** curl endpoint → 200 + `application/pdf` + bytes>0.
- [ ] **Step 3:** Botão doc nas telas DP (helper `doc(...)`).
- [ ] **Step 4:** Commit `feat(folha): recibos de férias e 13º em PDF`.

### Task A6: Saldo FGTS real na rescisão (multa 40% correta)

**Files:**
- Modify: `backend/modules/people_management/hr/services/termination_service.py` (alimentar `saldo_fgts` em `calcular_rescisao:437`)

- [ ] **Step 1 (oráculo):** Hoje `calcular_rescisao` recebe `saldo_fgts=0` default → multa 40% zerada. Confirmar.
- [ ] **Step 2:** Alimentar `saldo_fgts` do acumulado real (soma de FGTS 8% dos `hr_payslips` do vínculo, ou extrato FGTS Digital quando C entregar). Marcar honesto se a fonte for parcial.
- [ ] **Step 3 (oráculo verde):** Rescisão de teste → multa 40% = 0,4 × saldo real.
- [ ] **Step 4:** Commit `feat(folha): rescisão usa saldo FGTS real na multa 40%`.

## Self-Review
- Cobertura da spec A: certificar IRRF (A1), persistir (A2), unificar motores (A3), conciliar (A4), recibos férias/13º (A5), saldo FGTS (A6) — 6/6 componentes cobertos.
- Sem placeholders: cada task tem arquivo + oráculo concreto.
- Consistência: `source_system='conecta'` usado igual em A2/A4; `calcular_irrf`/`calcular_rescisao` assinaturas conferidas contra clt_calculator.
