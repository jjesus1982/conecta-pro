# Contábil Autônomo — Reconciliação (rumo a desligar a Portte contábil) — Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development ou executing-plans. Steps usam checkbox (`- [ ]`). **ponytail OBRIGATÓRIO em todo pareamento.**

**Goal:** Construir a RÉGUA de reconciliação da contabilidade (nossa saída vs oráculo Onvio/Portte) e medir o baseline por pilar, para depois fechar só os gaps medidos — igual ao C1 fez na folha. **NÃO reconstruir** o que já existe (razão, SPED, DCTFWeb, eSocial, FGTS, apuração lucro real, guias já estão codados e reais).

**Architecture:** Um harness read-only roda cada pilar para uma competência e compara ao oráculo (valores oficiais que o Onvio traz do contador + espelho Portte da folha). Saída = Σ|Δ| por pilar/conta. A medição — não a suposição — revela o que já bate e o que falta, como o C1 revelou as 6 verbas.

**Tech Stack:** Python no container (docker exec -e PYTHONPATH=/app), SQLAlchemy, serviços existentes em `government_integrations/`, `financial/services/ledger_auto_service.py`, `gedeon/onvio/`.

## Global Constraints
- **Reusar, não recodar.** Recon+graphify+veracity (2026-07-29) provaram: razão (`ledger_auto_service`, accounting_entries 1.298 linhas), SPED-contábil/ECD, SPED-fiscal, DCTFWeb (transmite), eSocial folha+SST (transmite), FGTS-digital, EFD-REINF, apuração-lucro-real, guias(Onvio) — TODOS reais. Só medir e fechar gaps.
- **Nunca fabricar dado.** Oráculo = valor oficial exibido == banco (Onvio-extraído / espelho Portte). Vazio real = "aguardando dado".
- **CNPJ-scoped.** Todo query filtra `empresa_id` (CNPJ1=619a3df1… Eletrônica, CNPJ2=7d79ed12… Patrimonial). Divergência de escopo é gap a reportar.
- **Read-only até aprovação.** Harness NUNCA transmite ao gov nem paga. Transmissão/dinheiro = gate humano (T1/OTP). Portte/Onvio intocados.
- **source='conecta' nunca vira oficial** sem aval da diretoria.

---

### Task 1: Mapear o oráculo Onvio (valores oficiais por empresa/competência)

**Files:**
- Create: `scripts/contabil_recon_oraculo.py`

**Interfaces:**
- Produces: função/relatório que lista, por (empresa_id, competência), os valores oficiais que o Onvio trouxe (guias FGTS/INSS/DAS/ISS/DARF, DRE se houver) — o alvo da reconciliação.

- [ ] **Step 1: Inventariar as tabelas Onvio + valores.** Ler `gedeon/onvio/onvio_sync_service.py::_salvar_db` e as tabelas que ele popula (`onvio_documents` + fgts/inss). Listar colunas e amostra por competência via `docker exec`. Sem escrita.
- [ ] **Step 2: Escrever `contabil_recon_oraculo.py`** que dumpa, por (empresa_id, competência 2026-01..06), cada valor oficial (tipo, valor, fonte). Rodar no container. Saída em `auditoria/contabil_oraculo_<data>.md`.
- [ ] **Step 3: Validar** que os valores batem com o que o Jordan vê no Onvio (spot-check 1 competência). Se o Onvio não tiver um pilar (ex.: DRE), marcar "oráculo ausente p/ esse pilar" — não inventar.

### Task 2: Harness de reconciliação do RAZÃO (accounting_entries vs oráculo)

**Files:**
- Create: `scripts/contabil_recon_razao.py`

**Interfaces:**
- Consumes: o oráculo da Task 1.
- Produces: Σ|Δ| do razão vs oficial, por conta/competência/empresa. READ-ONLY.

- [ ] **Step 1: Ler `ledger_auto_service.py`** inteiro — o que ele lança (`_lancar_folha`, `_lancar_receita_e_iss`, impostos), com que fontes, escopo empresa_id. Mapear as contas de `accounting_entries`.
- [ ] **Step 2: Harness** que soma `accounting_entries` por (empresa_id, periodo_competencia, tipo/conta) e compara aos valores da folha (espelho hr_payslips) e às guias Onvio (INSS/FGTS/impostos). Σ|Δ| por conta. Reusar o padrão do `folha_c1_fase_a.py`.
- [ ] **Step 3: Rodar baseline** jan-jun. Relatório `auditoria/contabil_recon_razao_<data>.md`: quais contas batem, quais divergem e quanto. **Isso substitui suposição por medição.**

### Task 3: Baseline dos demais pilares (SPED/DCTFWeb/guias/apuração) — medir antes de mexer

**Files:**
- Create: `scripts/contabil_recon_pilares.py`

- [ ] **Step 1: Para cada pilar** (SPED-contábil gera do razão; DCTFWeb consolida eSocial/REINF; guias; apuração lucro real), chamar o serviço existente em modo geração/consulta (SEM transmitir) para uma competência e capturar o total produzido.
- [ ] **Step 2: Comparar** ao oráculo Onvio correspondente (DARF/DAS/guia). Σ|Δ| por pilar. Onde o serviço exige input que falta (ex.: certificado, empresa_id), registrar o BLOQUEIO explícito (não é gap de cálculo, é de config).
- [ ] **Step 3: Relatório consolidado** `auditoria/contabil_baseline_<data>.md`: tabela pilar × Σ|Δ| × bloqueio. **Este é o mapa real de "quanto falta" — a régua dos 6 meses.**

### Task 4: Fechar o primeiro gap medido (dirigido pelo baseline)

- [ ] **Step 1:** Pegar o maior Δ do baseline (Task 3). Investigar a fonte (ponytail: reusar a função existente, achar o que a alimenta errado — como o C1 achou `import calendar` e o filtro-de-data).
- [ ] **Step 2:** Corrigir SÓ o que está errado. Re-rodar o harness, medir o Δ cair. Commit + bake.
- [ ] **Step 3:** Repetir para o próximo Δ (loop), até o baseline ficar aceitável ou restar só gap de dado/config (reportar ao Jordan).

### Task 5: Orquestração do fechamento mensal (só depois dos pilares baterem)

- [ ] **Step 1:** Mapear `gedeon_financial_orchestrator` + scheduler — o que já roda o fechamento. Reusar.
- [ ] **Step 2:** Amarrar a sequência (folha→razão→SPED/DCTFWeb→guias) + rodar o harness de reconciliação ao fim, gerando o relatório mensal de paridade (a "prova" do parênteses de 6 meses). NÃO transmite sozinho — gate humano.

## Guardrails / Ordem
A→B→C revela o mapa real. D fecha gaps por medição (nunca por suposição — foi o erro que originou este plano). E orquestra. Métrica única: Σ|Δ| por pilar caindo, mês a mês. Nunca transmite/paga sem gate. Onvio/Portte = verdade, intocados.
