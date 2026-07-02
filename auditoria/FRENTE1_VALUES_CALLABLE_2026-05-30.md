# FRENTE 1 — `values_callable` nos Column(Enum) que causam 500

**Data:** 2026-05-30
**Tipo:** correção de **CÓDIGO** (SQLAlchemy). **Banco NÃO tocado** (nenhum DDL/migration/dado).
**Status:** ✅ **LOTE 1 aplicado e validado** — ⏸️ aguardando Jordan antes de estender.

> Banco confirmado CORRETO (valores minúsculos). A correção faz o SQLAlchemy gravar/ler o **`.value`** do enum (que o banco tem) em vez do **nome** do membro.

---

## 1. Padrão correto usado (referência dos 19 que já tinham)

Referência no projeto: `modules/ged/models/folder.py:86` →
```python
values_callable=lambda e: [m.value for m in e]
```
Os models definem `class X(StrEnum): NOME = "valor"`. Aplicado o padrão preservando o enum **nativo** do Postgres (sem `native_enum=False`):
```python
Column(Enum(MeuEnum, values_callable=lambda obj: [e.value for e in obj]), ...)
```

## 2. Verificação prévia (read-only) — valores Python `.value` vs enum do banco

| Enum (model) | Valores `.value` | Enum no banco | Bate? |
|---|---|---|---|
| `TenantStatus` (config/tenant) | active, inactive, suspended, blocked, trial, cancelled | `tenant_status` idem | ✅ **100%** |
| `AlertLevel` (monitoring/alert) | green, yellow, orange, red | `alertlevel` idem | ✅ **100%** |
| `AlertStatus` (monitoring/alert) | active, acknowledged, resolved, escalated, suppressed | `alertstatus` = pending, investigating, confirmed, false_positive, resolved, escalated, closed, active | ⚠️ parcial (active/resolved/escalated ✅; acknowledged/suppressed não existem no banco) |

Só corrigi enums onde o valor **realmente usado** bate com o banco. Os de **divergência de conjunto** ficaram de fora (seção 5).

## 3. LOTE 1 — enums corrigidos (diffs)

**`modules/config/models/tenant.py`** (coluna `status`):
```diff
-    status = Column(Enum(TenantStatus), nullable=False, default=TenantStatus.TRIAL)
+    status = Column(
+        Enum(TenantStatus, values_callable=lambda obj: [e.value for e in obj]),
+        nullable=False,
+        default=TenantStatus.TRIAL,
+    )
```

**`modules/monitoring/models/alert.py`** (colunas `level` e `status`):
```diff
-        Enum(AlertLevel),
+        Enum(AlertLevel, values_callable=lambda obj: [e.value for e in obj]),
...
-        Enum(AlertStatus),
+        Enum(AlertStatus, values_callable=lambda obj: [e.value for e in obj]),
```

- Backups: `tenant.py.bak-frente1-20260530_162856`, `alert.py.bak-frente1-20260530_162856`.
- `python3 -m py_compile` em ambos: **OK**.

## 4. Validação — endpoints antes → depois e logs

| Endpoint | Antes | Depois | Nota |
|---|---|---|---|
| `/api/v1/monitoring/health` | 500 (enum "ACTIVE") | **200** ✅ | destravado |
| `/api/v1/monitoring/alerts` | 500 (enum "ACTIVE") | **200** ✅ | destravado |
| `/api/v1/config/tenants` | 500 (enum `tenant_status` "ATIVO") | **500** ⚠️ | erro **mudou** para `tenant_type` (prova que o fix do status funcionou; bloqueio restante é divergência mais profunda — seção 5) |

**Logs (o erro de enum sumiu para os corrigidos):**
- Backend `enum tenant_status "ATIVO"`: **0 ocorrências** ✅
- Backend `enum alertstatus "ACTIVE"`: **0 ocorrências** ✅
- `celery-operacional` `invalid input value for enum tenant_status`: **0 após restart** ✅ (eram ~10/3min antes)

**Propagação:** o fix foi aplicado no HOST (fonte-de-verdade) e replicado via `docker cp` no **backend + 8 workers Celery + flower**, todos reiniciados e **healthy**. Rotas mantidas em **3520**, sem regressão.

## 5. 🚨 Descobertas mais profundas (NÃO são values_callable — exigem decisão)

Estas **não foram tocadas** — `values_callable` não resolve (o conjunto de valores Python diverge do banco):

| Enum | Valores model | Valores banco | Problema | Efeito |
|---|---|---|---|---|
| `TenantType` (tenant.py `tipo`) | empresa, condominio, franquia, parceiro, interno | **company, individual, government, nonprofit, educational** | conjuntos **totalmente diferentes** | **`/config/tenants` continua 500** (dado real `tipo=company` não existe no enum Python) |
| `TenantPlan` (tenant.py `plano`) | free, **starter**, professional, enterprise, custom | free, **basic**, professional, enterprise, custom | `starter`↔`basic` | latente (dado atual `enterprise` ✅) |
| `AlertStatus` (monitoring) | + acknowledged, suppressed | não tem acknowledged/suppressed | tipo `alertstatus` **compartilhado com fraud** | latente: gravar acknowledged/suppressed falharia |

**Recomendação (decisão do Jordan):** reconciliar `TenantType`/`TenantPlan` — alinhar os **valores do enum Python ao banco** (ex.: `EMPRESA = "company"`) **ou** decidir que o banco está errado. É mudança de **conteúdo de model** (afeta todo código que usa `TenantType.EMPRESA`), fora do escopo mecânico de `values_callable`. Enquanto não decidido, `/config/tenants` segue 500.

## 6. Enums em ZONA PROIBIDA — não tocados (pendência)

Não editei nenhum enum em `financial/`, `government_integrations/`, `alembic/versions/`, `main_production.py`. Dos ~208 `Column(Enum)` sem `values_callable`, parte está nessas zonas (no CHECAGEM, ~396 issues B904 estavam em zonas protegidas; a fração de enums protegidos será contada no lote a lote). **Listar e NÃO editar** quando aparecerem.

## 7. Contagem e lembrete

- **Corrigidos no lote 1:** 3 colunas enum (tenant `status`; monitoring `level` + `status`).
- **Restam:** ~205 dos ~208 (a estender em lotes por módulo, fora de zona proibida).
- **Lembrete:** as edições estão no HOST → **entram automaticamente no próximo rebuild** de imagem (todos os containers usam a mesma imagem). O `docker cp` foi só para efeito imediato nesta sessão.

## ⏸️ PONTO DE PAUSA

Lote 1 validado: 2 endpoints de monitoring destravados (200), erros de enum `tenant_status`/`alertstatus` eliminados de backend e Celery, sem regressão. `/config/tenants` exige decisão sobre `TenantType` (seção 5). **Aguardo OK do Jordan para estender aos demais ~205 enums em lotes por módulo (PASSO 4).**
