# Fiscal multi-CNPJ — fechar o módulo

> **Para quem executa:** tarefas em ordem; cada uma termina com oráculo verde e commit por
> pathspec. Nada de fabricar dado: buraco real vira "aguardando dado", nunca linha inventada.

**Goal:** o módulo fiscal para de tratar o grupo como uma empresa só — cada tela diz de qual
CNPJ é o dado, e o painel denuncia onde a Patrimonial está descoberta.

**Architecture:** tudo em `redesign_builders/fiscal.py` (território do redesign; endpoint
clássico não se toca). `empresas` é a tabela-âncora: `fiscal_obligations.empresa_id`,
`nfse_emitidas_nacional.empresa_id` e `ged_certidoes.cnpj` já existem e estão preenchidos —
é wiring, não migração.

**Tech Stack:** FastAPI + SQLAlchemy async + Postgres; builder devolve dict de telas;
oráculos em `backend/scripts/orq/`.

## Global Constraints

- **Não fabricar.** Patrimonial tem 0 obrigações e 1 certidão: isso é ACHADO, mostrado como
  buraco. Criar linha para "completar" é proibido.
- **Redesign apenas.** Não gatear nem alterar endpoint clássico compartilhado.
- **Sem transmitir ao governo.** Só leitura.
- Commit por pathspec (índice git compartilhado com outras sessões).
- Todo número novo na tela nasce com asserção no oráculo, comparando com a VERDADE do banco
  escrita de forma independente — não com a query do builder.

## Estado medido (11/08/2026, base real)

| | Eletrônica `35.710.481` | Patrimonial `66.014.833` |
|---|---|---|
| Certidões | 8 (3 VENCIDAS) | **1** (só Trabalhista) |
| Obrigações fiscais | 31 (5 pendentes) | **0** |
| NFS-e 2026 | 83 · R$ 1.544.613,06 | 16 · R$ 443.381,11 |
| Regime | Lucro Real | Simples Anexo III |

Vencidas na Eletrônica: Alvará (28/02), CRF-FGTS (09/08), Neg. Estadual (09/08).

Nenhuma tela fiscal exibe a empresa da linha. `nfse-tomadas` tem coluna CNPJ, mas é do
PRESTADOR (fornecedor), não nossa.

---

### Task 1: Painel por CNPJ

**Files:** Modify `backend/modules/operacional/controllers/redesign_builders/fiscal.py`
(bloco de KPIs, ~linha 124) · Test `backend/scripts/orq/test_oraculo_fiscal_multicnpj.py`

**Interfaces:**
- Consome: `empresas(id, cnpj, nome_fantasia, razao_social)`, `ged_certidoes.cnpj`,
  `fiscal_obligations.empresa_id`, `nfse_emitidas_nacional.empresa_id`
- Produz: helper `_por_empresa(db)` → `list[dict]` com
  `{empresa_id, nome, cnpj, cnd_total, cnd_vencidas, obr_pendentes, fat12}`

- [ ] **Passo 1: escrever o oráculo que falha**

Asserção central: para CADA empresa em `empresas`, existe um KPI ou linha no painel com o
nome dela; e a soma das partes bate com o total.

- [ ] **Passo 2: ver falhar** — hoje o painel tem 4 KPIs agregados, nenhum por empresa.

- [ ] **Passo 3: implementar `_por_empresa` + tela `painel-por-empresa` (type table)**

Colunas: Empresa · CNPJ · Regime · Certidões (ok/total) · Vencidas · Obrigações pendentes ·
Faturamento 12m. Uma linha por empresa, direto de `empresas` — empresa nova aparece sozinha.

- [ ] **Passo 4: rodar o oráculo (verde) e o `test_oraculo_fiscal_painel` (não regrediu)**

- [ ] **Passo 5: commit**

### Task 2: Cobertura de certidões por CNPJ

**Files:** Modify `fiscal.py` · Test: mesmo oráculo da Task 1

O buraco real: Patrimonial tem 1 dos 8 tipos que a Eletrônica tem. Sem CRF-FGTS e CND
Federal não se fatura em cliente grande nem se entra em licitação.

- [ ] **Passo 1: oráculo exige que os tipos FALTANTES apareçam** (não só os presentes)

- [ ] **Passo 2: tela `certidoes-cobertura`** — matriz tipo × empresa, com três estados:
  `ok` (válida), `VENCIDA` (com a data), `FALTA` (nunca cadastrada). O catálogo de tipos sai
  do que existe na base (`DISTINCT name`), não de lista fixa no código.

- [ ] **Passo 3: rodar, commitar**

### Task 3: Coluna Empresa nas tabelas fiscais

**Files:** Modify `fiscal.py` (telas `certidoes`, `certidoes-cnd`, `nfse`, `guias`)

- [ ] **Passo 1: oráculo exige 'Empresa' em `cols` das quatro telas**
- [ ] **Passo 2: adicionar a coluna** — JOIN em `empresas` por `empresa_id`; em
  `ged_certidoes` o vínculo é por `cnpj` (texto), então normalizar dígitos nos dois lados.
- [ ] **Passo 3: conferir que a contagem de linhas NÃO mudou** (JOIN não pode filtrar:
  usar LEFT JOIN, linha sem empresa mostra "—" em vez de sumir)
- [ ] **Passo 4: commit**

### Task 4: O buraco da Patrimonial, dito na cara

**Files:** Modify `fiscal.py`

Patrimonial fatura R$ 443.381,11 e tem ZERO obrigação fiscal cadastrada, sendo Simples
(DAS mensal). Ou ninguém cadastrou, ou o cadastro só olha um CNPJ.

- [ ] **Passo 1: descobrir de onde vêm as obrigações** (`sync_guias_drive` / cadastro manual)
      e se o caminho é cego a CNPJ — ler `guias_drive_service._empresa_por_cnpj`
- [ ] **Passo 2: se o sync é cego** → relatar no relatório; **não** criar obrigação à mão
- [ ] **Passo 3: painel mostra "empresa sem obrigação cadastrada"** como alerta, não como zero
      silencioso
- [ ] **Passo 4: commit**

### Task 5: Fechamento — QA três lentes + relatório

- [ ] **Passo 1:** rodar TODOS os oráculos fiscais
- [ ] **Passo 2:** navegador real nas telas novas (cache-bust)
- [ ] **Passo 3:** `ruff` limpo
- [ ] **Passo 4:** `auditoria/qa/fiscal_multicnpj_20260811.md` com veredito por lente
- [ ] **Passo 5:** commit + bake
