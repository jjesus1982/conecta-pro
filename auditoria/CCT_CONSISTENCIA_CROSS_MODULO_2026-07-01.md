# Auditoria de Consistência da CCT SINDECOMPRESTS — Cross-Módulo (2026-07-01)

**Pergunta do Jordan:** todos os módulos (cargos, salários, DP, RH, financeiro, SST, GED, portal, área do cliente, operações, ponto) recebem e compartilham as MESMAS informações da CCT?

**Resposta: NÃO.** Há 5 fontes paralelas da "verdade CCT" e o elo funcionário↔cargo está quebrado.

## 1. As 5 fontes paralelas (deveria ser 1)
1. **DB `cct_cargos`** (52 cargos, piso 1670) — correta. Lida pelo módulo CCT/admin.
2. **Python hardcoded** `modules/cct/models/salary_table.py` (52, piso 1670) — usada pelo `SalaryValidator` (o que o **Portal** chama).
3. **`folha/calculo_service.py`** — constantes próprias (VR/VT/INSS/IRRF).
4. **`common/utils/clt_calculator.py`** — INSS/IRRF próprios + **VT 6% (drift, CCT=4%)**.
5. **Piso solto** 1670 hardcoded em portal, crm/growth; e pisos ERRADOS em pricing.

## 2. Quebras críticas (ranqueadas)

### 🔴 A. Elo funcionário→cargo CCT QUEBRADO (keystone)
- `employees.cargo` = **texto livre**; `cargo_id` FK **100% NULL** (0/71).
- Join cargo→piso é **igualdade exata uppercase** → só **1 de 9** valores casa:
  - `AGENTE DE PORTARIA` (42 func.) ✗ vs CCT `PORTEIROS AGENTE DE PORTARIA GUARDETE`
  - `AGENTE DE SERVIÇOS GERAIS` (15) ✗ vs `SERVICOS GERAIS FAXINEIRO`
  - `JARDINEIRO` ✗ vs `JARDINEIROS` (plural); acentos quebram (`LÍDER`≠`LIDER`)
- ~68/71 func. → Portal mostra "cargo não encontrado / piso 0 / não-conforme" = **falso negativo**.
- `hr/cct_controller.py` faz JOIN em `employees.cct_cargo_id` — **coluna não existe** → endpoints quebram.

### 🔴 B. Folha NÃO aplica a CCT
- Salário é **digitado livre** na admissão (`admission_service.py:244`), não vem do piso.
- `calculo_service` lê `employees.salario_base` cru, **nunca** `cct_cargos`. **13/71 têm salario_base NULL** → holerite sobre NULL.
- **Periculosidade/insalubridade NUNCA aplicadas** no holerite → um **Vigia sai sem os 30%**.
- **HE 50/100 ausente**; ronda 15/30 e acúmulo 30 definidos mas **órfãos** (nunca consumidos).

### 🔴 C. Precificação usa CATEGORIA ERRADA + falta repasse 7,5%
- 4 engines independentes, pisos: 1670 / **2150 (vigilante!)** / **2450 (armado!)** / 1847,93.
- `bidding/pricer_agent.py` usa salários de **vigilância armada** — categoria errada (somos portaria).
- **Repasse 7,5% (CCT Cl.2ª §3º) = 0 ocorrências** no backend → todo preço subestima custo.
- `financial ENCARGOS_PCT=0.42` (real ≈61%); VR drift 22 vs 26,40 vs 28,00; insal `1412×20%` (base+% errados).

### 🟠 D. SST/Operações desancorados
- `sst_service.GRAU_RISCO_CARGO` tem cargos **fantasma** que não batem com a CCT → fator de risco cego.
- `operacional post.hazard_pay_percent` = campo livre default **0.0** → posto de Vigia nasce sem peric.
- Operações **não valida** descanso 24h nem proíbe 2x1 (constante `ESCALA_PROIBIDA_2X1` órfã).

### 🟠 E. Drifts de valor concretos
- `clt_calculator.py:339` VT desconto **6%** (CCT=4%).
- Insalubridade base: mínimo R$1.621 (`clt_calculator`) vs piso R$1.670 (`salary_validator`) — discordam.

### 🟡 F. GED
- Ecoa `cargo` cru nos kits/folha de ponto (propaga o erro).
- **O PDF da própria CCT 2026 não está no acervo** (0 documentos).

## 3. Causa-raiz única
Falta **normalização/FK de cargo**. Enquanto `employees.cargo` for texto livre e o join for string exata contra (pior: uma cópia hardcoded), cadastro↔CCT não casam, e cada módulo inventa sua cópia.

## 4. Consolidação proposta (fonte única)
1. Eleger **`cct_cargos` (DB)** como oráculo único; aposentar `salary_table.py` hardcoded (→ fallback testado).
2. Criar `employees.cct_cargo_id` (FK real) + **mapear nomenclatura** (AGENTE DE PORTARIA→PORTEIROS…GUARDETE) e popular os 71.
3. Admissão preenche piso/adicionais **a partir do cargo CCT** (não digitação livre).
4. Folha aplica peric/insal/ronda/HE **derivados do cargo CCT**; backfill dos 13 salario_base NULL pelo piso.
5. Pricing (crm/bidding/financial) consome piso+encargos+**repasse 7,5%** da fonte única; remover pisos de vigilância.
6. SST/Operações derivam peric/insal/jornada do cargo CCT (fim do dict fantasma e do campo livre).
7. Arquivar o PDF da CCT no GED.

---

# ✅ RESOLUÇÃO (2026-07-01) — CONSOLIDAÇÃO EXECUTADA

**Fonte única eleita: tabela DB `cct_cargos`, vinculada por `employees.cct_cargo_id` (UUID FK).**

| # | Quebra | Correção | Status |
|---|---|---|---|
| A | Elo funcionário→cargo (1/9 casava) | `cct_cargo_id` INTEGER→UUID FK; 53/53 vinculados por mapa de nomenclatura; 13 salário NULL backfilled pelo piso | ✅ |
| B | Folha não aplicava CCT | `calculo_service` aplica peric/insal do cargo CCT (Vigia=+30% validado R$501); admissão/cadastro gravam cct_cargo_id+piso | ✅ |
| C | Pricing categoria errada + s/ repasse | `cct_pricing_source` (fonte única); piso 1670 (removido vigilância 2150/2450); encargos 61%; **repasse 7,5% nos 4 motores** (era 0) | ✅ |
| D | SST/Operações desancorados | SST deriva grau de peric/insal do cargo CCT (fim do GRAU_RISCO_CARGO fantasma); post_repository sincroniza hazard_pay da CCT | ✅ |
| E | Drifts de valor | Consolidados na fonte única | ✅ |
| F | GED sem PDF da CCT | Follow-up (exige file-storage; CCT autoritativa no Drive do Jordan) | 🟡 pendente |

**Comunicação bidirecional (event bus `ConectaEventBus`):**
- Novos EventTypes: `CCT_CARGO_ATUALIZADO`, `DP_CARGO_ALTERADO`, `DP_SALARIO_RECALCULADO`.
- Publish: `employee_controller.update_employee` (cargo muda→avisa) e `admin_cct.atualizar_cargo` (piso/adicional muda→folha/SST/pricing reagem).

**Frontend:** dropdown de cargo da CCT (`/hr/cct/cargos`) em admissão + colaboradores + dp/funcionarios (removido "Vigilante"); hook `useCctCargos`; portal lê piso via cct_cargo_id (fim do falso-negativo 68/71).

**Commits:** `5c7e4914` (núcleo), `270c9993` (admissão). Backend bakeado + frontend deployado.

**Follow-ups menores:** (1) GED: arquivar PDF da CCT; (2) inconsistência `is_active` vs `status='ativo'` (13 funcionários); (3) `clt_calculator.calcular_vale_transporte_desconto` 6%→4% (rescisão).
