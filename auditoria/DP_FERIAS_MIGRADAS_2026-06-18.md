# Departamento Pessoal — Migração das Férias (balde 3 resolvido) — DP-hr 100%

**Data:** 2026-06-18 · **Escopo:** `hr.employee_portal` (férias) · **Decisão do Jordan:** "Migrar preservando".
**Resultado:** DP-hr saiu de **88% → 100%** de models sãos. 67 períodos + 15 solicitações de férias preservados; legado mantido intacto como backup; zero dado perdido.

---

## Decisão (sua) e por quê
Os 67 registros de `hr_vacation_periods` **não eram legado morto**: ligados a **52 de 58 funcionários ativos**, **0 órfãos**, 52 períodos vigentes, `days_used=0` (períodos aquisitivos — direito a 30 dias). Criar o portal vazio mostraria "0 férias" para todos = errado. Você escolheu **migrar preservando**.

## O que foi feito
1. Criadas `employee_vacation_periods` (18 col) e `employee_vacation_requests` (54 col) do schema do model, sem FK.
2. **Migrados preservando:** 67 períodos + 15 requests via `INSERT...SELECT` com mapeamento explícito.
3. **Legado `hr_vacation_*` mantido intacto** (backup completo — nada dropado).

### Mapeamento aplicado (períodos)
| Model | ← Legado |
|---|---|
| total_days_entitled | days_entitled |
| expires_at | limit_date |
| double_payment | `false` (default CLT) |
| concession_start / concession_end | **NULL** (sem origem no legado — não inventei data de período concessivo CLT) |
| demais (employee_id, datas, days_used/sold/remaining, absences, flags) | 1:1 direto |

### Mapeamento aplicado (requests)
- Diretos: employee_id, vacation_period_id←period_id, request_code, status, datas, days_requested, sell_days, advance_13th_requested←advance_13th, net_value, calculation_details, notes, flags de aprovação, cancel/interrupt, return_date, actual_return_date←actual_end_date, created_by.
- **NULL (sem origem / ambíguo):** vacation_type (NOT NULL no model → criado nullable), e os campos financeiros detalhados.
- **Sem perda:** os campos ambíguos do legado estavam **vazios** (gross_value 0/15, rejection 0/15, net_value 0/15). O único com dado sem casa no model é `internal_notes` (10/15) — **fica preservado no legado**.

## Ajustes de schema documentados
- `concession_start`, `concession_end` (períodos) e `vacation_type` (requests) são `NOT NULL` no model mas **não têm origem no legado** → criados **NULLABLE** (não inventei valor trabalhista). Endurecer quando a regra de preenchimento (período concessivo CLT / tipo de férias) for definida.

## EVIDÊNCIA (verification-before-completion)
| Checagem | Resultado |
|---|---|
| **hr models (ORM-load prod)** | **OK=16, FAIL=0** (era 14/2 → **100%**) |
| Migrados | `employee_vacation_periods=67` = legado 67 · `employee_vacation_requests=15` = legado 15 |
| **Spot-check saldo** | `sum(days_remaining)` novo=**2010** = legado **2010** (bate exato) |
| Legado preservado | `hr_vacation_periods=67`, `hr_vacation_requests=15` intactos |
| Staging validado antes | hr OK=16/FAIL=0 idêntico, antes de prod |
| Backend / containers | **HTTP 200** · **20 healthy** |

## Segurança / reversibilidade
- **Backup PRE:** `backups/postgresql/conecta_pro_PRE_FERIAS_20260618_214700.dump` (validado).
- **FORWARD:** `auditoria/FORWARD_FERIAS_2026-06-18.sql` (CREATE + ALTER + INSERT…SELECT, replayável enquanto o legado existir).
- **REVERSAL:** `auditoria/REVERSAO_FERIAS_2026-06-18.sql` (DROP das 2 tabelas do portal; legado `hr_vacation_*` é a origem, dado recriável).
- **Alembic:** `dp_ferias_20260618` (child de `dp_suspeitos_20260618`).
- Só CREATE + INSERT (dado novo) — **nenhum UPDATE/DROP/DELETE** sobre dado existente.

## Estado final do DP-hr (sessão completa)
| Marco | hr models sãos |
|---|---|
| Início (raio-x) | 6/16 (38%) |
| Pós-migração financial+hr | 9/16 (56%) |
| Pós-5 suspeitos | 14/16 (88%) |
| **Pós-férias (agora)** | **16/16 (100%)** |

## Pendência de código (não-DDL)
- 5 models ainda com FK→`funcionarios` (deveria ser `employees`); as tabelas de férias e suspeitas foram criadas sem FK. Corrigir o model é fix de código.
- Endurecer `concession_*` / `vacation_type` para NOT NULL quando houver regra de preenchimento.
