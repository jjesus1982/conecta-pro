# DP — Fix FK `funcionarios` (Opção A: remover ForeignKey) + incidente de conexões resolvido

**Data:** 2026-06-23 · **Escopo (§13.3):** módulo `hr` apenas. **Princípios:** §13.1 (investigar antes), §13.4 (falsificação rigorosa), §13.5 (medir real), §13.6 (backup/rollback), B.4 (hot-copy Celery), B.8 (governança).

---

## RESUMO
Durante o STEP 0 apareceu um **incidente de produção** (Postgres no teto de conexões) — resolvido com sua autorização. Depois, o fix do DP: removidas as **7 FKs `funcionarios.id`** dos 6 models hr, alinhando à convenção real do módulo (employee_id = coluna pura indexada). **0 dado tocado**, hr segue 16/16, app HTTP 200.

---

## PARTE 1 — INCIDENTE (achado no STEP 0): Postgres no teto de conexões
- **Sintoma:** "too many clients already" — toda conexão nova falhava (travou as queries do fix).
- **Causa:** `conecta-pro-celery-batch` **vazando 129–130 conexões idle** (de `max_connections=150`).
- **Ação (autorizada por Jordan):** `docker restart conecta-pro-celery-batch`.
- **Resultado:** conexões **150/150 → 30/150**; celery-batch 130 → 0; app HTTP 200 mantido.
- **Pendência (não-resolvida):** causa-raiz do leak no código batch (sessão/engine não-fechada em alguma task). **A investigar** — o restart só liberou; o leak pode reacumular.

## PARTE 2 — Por que "FK funcionarios→employees" virou "remover FK" (§13.1)
Investiguei antes de mexer:
- Os 7 FKs diziam `ForeignKey("funcionarios.id")` → tabela **inexistente**.
- **Nenhum** model hr que funciona usa `ForeignKey("employees.id")` (zero). A convenção real dos models sãos (`time_entry`, `payslip`, `overtime`…) é **employee_id como coluna pura indexada, SEM ForeignKey**:
  ```python
  employee_id = Column(UUID(as_uuid=True), nullable=False, index=True)
  ```
- Apresentei as 2 opções; você escolheu **A (remover o ForeignKey)** — segue o estilo existente (§13.3), sem criar dependência de tabela-alvo nem DDL.

## PARTE 3 — O que foi feito (Opção A)
Removida a linha `ForeignKey("funcionarios.id"),` de cada `employee_id`, em 6 arquivos (7 ocorrências):
| Arquivo | FKs removidas |
|---|---|
| `payroll_integration/models/payroll_event.py` | 1 |
| `payroll_integration/models/employee_payroll_config.py` | 1 |
| `employee_portal/models/employee_notification.py` | 1 |
| `employee_portal/models/employee_preferences.py` | 1 |
| `employee_portal/models/employee_document.py` | 1 |
| `employee_portal/models/vacation_request.py` | 2 |

- Cada `employee_id` ficou `Column(UUID(as_uuid=True), nullable=False, index=True)` — idêntico à convenção.
- Import `ForeignKey` **mantido** em todos (cada arquivo tem outras FKs válidas). Sem import órfão (§13.3).
- **Sem DDL / sem alembic:** as 5 tabelas já existiam no banco SEM constraint de FK (criadas assim na sessão anterior). Remover a FK do model apenas alinha código↔banco. Zona proibida `alembic/versions/` **não tocada**.
- Deploy: `./scripts/deploy/sync_celery_workers.sh hr` → backend + 7 Celery, pyc limpo, `kill -HUP` (B.4).

## VERIFICAÇÃO (§13.4 — verdade, não aparência)
| Checagem | Resultado |
|---|---|
| **FK funcionarios no runtime (SQLAlchemy)** | **0** em 16 models hr (verdade absoluta, não grep) |
| `.py` no host com funcionarios.id | 0 |
| hr models carregam | **16/16 OK** |
| Dados intactos | `hr_vacation_periods=67`, `hr_vacation_requests=15`, `employees=58` |
| Backend | **HTTP 200** (após boot completo ~40s do kill -HUP) |
| Containers healthy | 20 |
| git diff escopo | **6 arquivos, 7 deleções**, nada fora de hr |

> Nota honesta (§13.4): o "16/16 loads" **sozinho não provava** o fix — FK para tabela inexistente não quebra SELECT, só CREATE. A prova real é a checagem no SQLAlchemy em runtime (0 FKs funcionarios). Por isso não me contentei com o load test.

## ROLLBACK
- Código: `git checkout HEAD -- backend/modules/hr/<arquivo>` restaura a FK (ou re-adicionar a linha). Mudança é puramente remoção de 7 linhas.
- Sem backup de banco necessário (nenhum DDL/dado tocado).

## PENDÊNCIAS REGISTRADAS
1. **Leak de conexões do celery-batch** — restart liberou, mas causa-raiz no código batch não foi corrigida. Pode reacumular. **Próxima investigação prioritária.**
2. **Commit:** o fix está LIVE (hot-copied), mas NÃO commitado. A árvore tem **49 arquivos modificados fora de hr** (CLAUDE.md, agents/*, snapshots deletados) e a branch ativa é `fix/crm-qa-aprovado-20260614` (nome de CRM, não hr). **Decisão sua:** commitar só os 6 hr aqui (com sufixo B.8) ou criar branch `fix/hr-fk-funcionarios`?
3. **Warning GEDEON** (`No module named modules.gedeon.gedeon.gedeon`) no boot — pré-existente, fora de escopo, apenas registrado.
