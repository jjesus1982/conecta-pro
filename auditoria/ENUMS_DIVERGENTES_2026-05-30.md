# FRENTE 3 — 14 Divergências de Enum (INTERATIVO)

**Data:** 2026-05-30
**Status:** ✅ **APLICADO EM PRODUÇÃO** (11 enums) — validado em staging antes, sem regressão.
**Abordagem (decisão do Jordan):** adicionar os valores do código ao banco (ALTER TYPE ADD VALUE) + `values_callable` — mantém o código canônico, **sem adivinhar semântica**, sem remover membros.

> Mapa completo lado-a-lado: `auditoria/ENUMS_DIVERGENTES_RAW_2026-05-30.txt`.

---

## 1. Diagnóstico (read-only) — código vs banco vs dado real

16 enums analisados (14 divergentes + TenantType/TenantPlan). **Achado decisivo: TODAS as colunas estão VAZIAS** (0 linhas/0 preenchidas), exceto `SyncSource` (44× `solides`, valor presente em ambos). → **Zero dado em risco** em qualquer escolha.

## 2. Decisão do Jordan

- **Reconciliação:** alinhar mantendo o **código canônico** → **adicionar os valores faltantes ao banco** (não remover do código, não adivinhar mapeamento semântico).
- **ServiceType:** código canônico (domínios) → migration de banco **à parte** (não nesta leva).

## 3. Aplicado (11 enums)

**3a. Banco — 19 `ALTER TYPE ADD VALUE` (aditivo):**
| Enum (tipo banco) | Valor(es) adicionado(s) |
|---|---|
| device_status | expired |
| executionstatus | finalizada |
| kit_type_enum | MENSAL |
| notification_priority | critical |
| notification_status | unregistered |
| orderpriority | emergencial |
| servicestatus | rascunho |
| target_type | condition, tag |
| solides_sync_source | webhook |
| flag_status | ativo, inativo, gradual, beta, deprecated |
| servicecategory | monitoramento, suporte, treinamento, manutencao |

**3b. Código — 11 `values_callable`** (para o SQLAlchemy emitir o `.value`, agora presente no banco), nos arquivos exatos (evitando classes homônimas): `push_device, service_execution, document_kit, push_notification (×2), service_order, service_catalog (×2), push_campaign, solides/models, feature_flag`. Backups `.bak-frente3`.

## 4. Validação

**Staging (`conecta_pro_drift_check`):** 19 ALTER OK; casts diretos provam aceitação (`'critical'::notification_priority` → critical, etc.); `configure_mappers OK, 3520 rotas` (lição do IntEnum — testado em processo separado ANTES de deploy).

**Produção:**
- 19 ALTER aplicados; `SELECT 'critical'::notification_priority, 'gradual'::flag_status, 'MENSAL'::kit_type_enum` → **todos aceitos**.
- 11 `values_callable` deployados (backend + 8 celery + flower, restart); `values_callable` ativo nas colunas divergentes (introspecção live).
- **backend health 200, 3520 rotas, 14/14 containers healthy, 0 unhealthy, 0 erros de mapper/enum.**
- *(O warning `bcrypt has no attribute __about__` no startup é pré-existente do passlib, trapped, sem relação com enums.)*

## 5. Reversibilidade

- Código (`values_callable`): reverte por `*.bak-frente3` + redeploy.
- `ALTER TYPE ADD VALUE`: o Postgres **não** remove labels de enum facilmente — mas são **valores extras inofensivos** (cosmético, sem dado). Backup: `conecta_pro_PRE_RENAME_20260530_181725.dump`.

## 6. Fora desta leva (decisões/pendências)

- 🔴 **ServiceType** (código canônico = domínios portaria/limpeza): migration de banco dos valores de domínio — operação à parte (você definiu o canônico; falta executar com cuidado de Frente 2).
- 🟠 **CampaignType, ReportType:** a **coluna não existe** no banco (`email_campaigns.campaign_type`, `financial_scheduled_reports.tipo`) → **schema drift / Frente 2**, não é divergência de enum.
- 🟠 **TenantType, TenantPlan:** a tabela `tenants` foi **redesenhada** (colunas viraram varchar) → **Camada 3 / Frente 4**.

**Resumo:** 11 dos 14 enums divergentes reconciliados em produção mantendo o código canônico (sem adivinhar semântica), colunas vazias = zero risco de dado, validado staging→prod, sem regressão. 3 restantes mapeados como ServiceType (migration de domínios) / schema drift / Camada 3.
