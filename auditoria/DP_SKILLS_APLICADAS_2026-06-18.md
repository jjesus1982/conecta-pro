# Departamento Pessoal (DP) — Skills Superpowers aplicadas + 5 tabelas resolvidas

**Data:** 2026-06-18 · **Escopo:** módulo `hr` (DP-folha). **Autorização:** "aplique as skills no que for importante, confio em você".
**Princípio mantido:** dado real trabalhista intocável — autônomo só o seguro (aditivo, reversível), PARAR com evidência no que mexe nos 67 registros de férias.

---

## RESULTADO EM 1 LINHA
DP saiu de **9→14 models sãos** (FAIL 7→2) com a criação segura de 5 tabelas vazias. **Zero dado tocado** (67 férias, 15 requests, 58 employees intactos), backend **HTTP 200**, **20 containers healthy**. As 2 tabelas de férias (dado real) ficaram **paradas para sua decisão** — isso É a skill funcionando.

---

## Skills aplicadas (de verdade, não cerimônia)
| Skill | Como foi usada aqui |
|---|---|
| **finding-schema-drift** (nossa) | Detectou o estado do DP read-only e classificou: 5 suspeitos + 2 férias (balde 3). |
| **writing-plans** | Estruturou o trabalho: o que é autônomo-seguro vs o que para na decisão. |
| **superpowers:verification-before-completion** | Gate final: nenhuma afirmação sem rodar o comando e ler o output (tabela de evidências abaixo). |
| **(princípio balde 3)** | PARAR no dado real — as férias não foram tocadas; trago evidência para você decidir. |
> Honestidade: **TDD/code-reviewer/worktrees NÃO se aplicam** a criar tabela vazia (não há lógica a testar). Eles entram quando formos escrever cálculo de folha/férias — forçá-los aqui seria teatro.

## O que foi feito (autônomo, seguro)
Criadas **5 tabelas vazias, sem FK constraint** (o que as bloqueava era só a FK→`funcionarios`, tabela inexistente; criar sem ela é additivo e reversível — mesmo padrão das 17 tabelas do balde 2 anterior):
`employee_documents`, `employee_notifications`, `employee_payroll_configs`, `employee_preferences`, `payroll_events`.
- Confirmado antes: **nenhuma tem tabela legada com dado** → nascem vazias, sem fragmentar nada.
- FK omitida e documentada: o model ainda referencia `funcionarios` (deveria ser `employees`) — **fix de código pendente**, adicionar a FK quando o model for revisado.

## O que NÃO foi feito (balde 3 — sua decisão)
2 tabelas de **férias rename-com-dado** — model novo ↔ tabela legada com dado real:
| Model (portal) | Legado com dado | Decisão |
|---|---|---|
| `employee_vacation_periods` | `hr_vacation_periods` = **67 períodos reais** | apontar/migrar para o legado, ou portal nasce separado? |
| `employee_vacation_requests` | `hr_vacation_requests` = **15 reais** | idem |
→ Não criei vazio para não fragmentar 67 registros de férias. Precisa da sua decisão de negócio (CLT/portal).

## EVIDÊNCIA (verification-before-completion)
| Checagem | Resultado |
|---|---|
| hr models (ORM-load prod) | **OK=14, FAIL=2** (antes 9/7 → 5 corrigidos; restam só as 2 férias) |
| Férias preservadas | `hr_vacation_periods=67`, `hr_vacation_requests=15`, `employees=58` (idênticos ao backup) |
| 5 tabelas novas | todas **=0 linhas** (vazias) |
| Backend | **HTTP 200** |
| Containers | **20 healthy** |
| Staging validado antes | OK=14/FAIL=2 idêntico, antes de prod |

## Segurança / reversibilidade
- **Backup PRE:** `backups/postgresql/conecta_pro_PRE_DP_20260617_195144.dump` (3,98 MB, validado).
- **FORWARD:** `auditoria/FORWARD_DP_SUSPEITOS_2026-06-18.sql` (5 CREATE TABLE sem FK, idempotente).
- **REVERSAL:** `auditoria/REVERSAO_DP_SUSPEITOS_2026-06-18.sql` (5 DROP TABLE IF EXISTS). ⚠️ DROP só seguro enquanto vazias.
- **Alembic:** `dp_suspeitos_20260618` (child de `sprint98_mkt_content`, upgrade/downgrade embutidos).
- Só `CREATE TABLE` rodou — nenhum UPDATE/DROP/DELETE; dado intacto.

## Contagem final
| Métrica | Antes | Depois |
|---|---:|---:|
| hr models sãos (carregáveis) | 9 de 16 (56%) | **14 de 16 (88%)** |
| hr models FAIL | 7 | **2** (só férias, balde 3) |
| Linhas de dado tocadas | — | **0** |

## Próximo passo (sua decisão)
Para chegar a 16/16 (100%): decidir as 2 tabelas de férias. Quando definir se o portal lê de `hr_vacation_periods` (67) ou nasce separado, eu aplico — com backup→staging→prod e os 67 registros preservados.
