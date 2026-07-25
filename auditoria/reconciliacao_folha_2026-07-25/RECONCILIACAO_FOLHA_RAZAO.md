# Reconciliação folha → razão (jan–jun/2026, Eletrônica) — 2026-07-25

**Autorizada por Jordan.** Objetivo: o razão (`accounting_entries`) passar a refletir a folha
**autoritativa da Portte** (`hr_payslips`, espelhada pelo T2, 100% conferida), substituindo a
folha *reconstruída* (forense, processo antigo) e removendo duplicidades.

## Diagnóstico (antes)
Conta 4.1.1 (salários) / 4.1.2 (FGTS), empresa Eletrônica (619a3df1), por competência:
- Jan, Fev, Abr, Mai: só `folha_reconstruida` (subestimada vs Portte).
- Mar: `folha` real antiga (âncora).
- **Jun: DUPLICADA** — `folha` real R$111.388,40 **+** `folha_reconstruida` R$81.181,75.
- Reconstrução subestimava a folha; jun contava dobrado.

## Operação (idempotente, reversível)
1. **Backup** de 659 lançamentos (folha+FGTS, jan–jun) → `backup_folha_razao.json` (PII, NÃO versionado).
2. **Purga** dos tipos `folha`, `folha_reconstruida`, `encargo_fgts`, `encargo_fgts_reconstruido`
   em jan–jun, escopo empresa Eletrônica (659 removidos).
3. **Repost** via `LedgerAutoService._lancar_folha` a partir de `hr_payslips` (Portte):
   314 salários (D 4.1.1.01 / C 2.1.2.01) + 304 FGTS (D 4.1.2.01 / C 2.1.3.02).
4. **Verificação em transação** (commit só se passar): folha jan–jun = 314 ✓ · reconstruída = 0 ✓.

## Resultado (depois) — uma folha por competência, = Portte
| Comp | Folha bruta | FGTS |
|------|-------------|------|
| 2026-01 | 99.054,28 | 6.876,90 |
| 2026-02 | 98.640,39 | 6.816,78 |
| 2026-03 | 97.607,18 | 7.106,81 |
| 2026-04 | 101.576,75 | 7.507,24 |
| 2026-05 | 108.442,01 | 8.169,76 |
| 2026-06 | 111.388,40 | 7.971,38 |
| **Total** | **616.709,01** | **44.448,87** |

## Efeitos verificados (oráculo)
- **Balanço fecha**: Ativo 1.629.822,40 = Passivo 999.128,41 + PL 630.693,99 (Δ 0,00).
- **Apuração Lucro Real 2026**: despesa_pessoal 616.709,01 (= Portte) · lucro 541.410,98 · IRPJ+CSLL 160.079,73.
- Telas contábeis do redesign (Balanço, DRE, Liquidez, Apuração, Provisões) leem o razão vivo → refletem já.

## Reversão
Re-inserir as 659 linhas de `backup_folha_razao.json` e remover os 618 lançamentos `FOLHA-PORTTE-*`/`FGTS-PORTTE-*`.
Nada de código; operação só de dado. Não depende do bake.
