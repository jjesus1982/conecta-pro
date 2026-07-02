# FRENTE 1 — PASSO 4: Extensão de `values_callable` em lotes

**Data:** 2026-05-30
**Tipo:** correção de **CÓDIGO** (SQLAlchemy). **Banco NÃO tocado**.
**Status:** ✅ concluído com **1 incidente detectado, revertido e corrigido** (IntEnum) — produção estável.

> Método: introspecção dos mappers do SQLAlchemy (precisa) + cruzamento com `pg_enum` (TRAVA de valores). Edição por classe SAFE, exclusão automática de zonas proibidas e de enums não-string.

---

## 1. Inventário (introspecção real, não grep)

- **Total de colunas Enum:** 298
- **Com `values_callable` (antes desta sessão):** 19 → após Lote 1: 22
- **Sem `values_callable`:** 276 → classificadas pela TRAVA:

| Classe da TRAVA | Qtd | Ação |
|---|---:|---|
| ✅ **SAFE** (valores Python ⊆ banco) | 69 | corrigir |
| 🚫 **DIVERGENTE** (conjunto difere) | 14 | decisão do Jordan — NÃO tocar |
| 🟠 **COL_AUSENTE** (coluna não existe no banco) | 128 | schema drift → **Frente 2** |
| 🔒 **ZONA PROIBIDA** (financial/gov) | 65 | NÃO tocar — listar |

SAFE por módulo: integrations 24, notifications 18, ai 13, document_kits 6, people_management 3, services 2, monitoring 1, + 2 sem classe identificável (`?`, pulados).

## 2. 🚨 Incidente: IntEnum quebrou os mappers (detectado, revertido, corrigido)

Na 1ª aplicação (81 inserções), o backend caiu de **3520 → 3193 rotas** com
`TypeError: object of type 'int' has no len()` em `sqlalchemy/sqltypes._enum_init`.
- **Causa:** `QueuePriority` (`modules/notifications/models/notification_queue.py`) é um **IntEnum** com valores `[1, 2, 5, 8]`. `values_callable=lambda obj: [e.value for e in obj]` retornava **inteiros**, e o SQLAlchemy faz `len(x)` sobre cada valor → quebra **toda** a configuração de mappers (derrubou notifications + módulos dependentes, -327 rotas).
- **Por que passou na TRAVA:** a comparação de valores foi feita como string (`1,2,5,8` casava com os labels do banco), sem checar o **tipo** do `.value`.
- **Resposta (regra PASSO 3.3):** **revertido o lote inteiro** (restore dos 38 `.bak-frente1-lote`) → produção voltou a **3520 rotas / health 200 / `configure_mappers` OK** imediatamente.
- **Correção:** adicionada **TRAVA de tipo** — introspecção achou que **`QueuePriority` é o ÚNICO** enum não-string em todo o sistema. Excluído e o lote reaplicado.

## 3. Lotes aplicados (após correção)

- **79 inserções de `values_callable`** em **38 arquivos**, cobrindo **60 classes SAFE de valor string** (QueuePriority excluído).
- Inserções por módulo: integrations 29, notifications 17, ai 15, document_kits 6, people_management 3, automation 2, services 2, config 1, ged 1, monitoring 1, reports 1, scheduler 1.
- `python3 -m py_compile`: **38/38 OK**.
- **Teste pré-deploy** em processo separado: `configure_mappers()` OK + 3520 rotas **antes** de reiniciar (não arriscou produção desta vez).
- Backups: `*.bak-frente1-lote` (38 arquivos, ao lado de cada original).

## 4. Validação final

| Item | Resultado |
|---|---|
| Backend `/health` | **200** |
| Rotas | **3520** (sem regressão) |
| `configure_mappers()` | **OK** (sem erro de int) |
| Erros de import/Traceback no startup | **0** (boot atual) |
| Novos `invalid input value for enum` | **0** (backend e Celery) |
| Containers conecta-pro | **14/14 healthy, 0 unhealthy** |
| Propagação | backend + 7 workers Celery + flower (docker cp + restart), todos healthy |

**Estado de runtime:** colunas Enum com `values_callable` **22 → 97**; sem `values_callable` **276 → 201**.

## 5. 🚫 DIVERGÊNCIAS DE CONJUNTO (decisão de negócio do Jordan — NÃO tocadas)

14 colunas onde os valores Python ≠ valores do banco (`values_callable` não resolve, pioraria):
`CampaignType, DeviceStatus, ExecutionStatus, FlagStatus, KitType, NotificationPriority, NotificationStatus, OrderPriority, ReportType, ServiceCategory, ServiceStatus, ServiceType, SyncSource, TargetType` — além de `TenantType`/`TenantPlan` (já listados no Lote 1). Exigem reconciliar o enum Python ↔ banco (decisão de qual é o canônico).

## 6. 🟠 Caso especial — IntEnum

`QueuePriority` (valores inteiros) **não recebe `values_callable`** (quebraria). Funciona como está (SQLAlchemy usa os nomes). Se houver erro de enum nele no futuro, é tratamento diferente (mapear int explicitamente), não values_callable.

## 7. 🔒 ZONA PROIBIDA — não tocados (pendência)

65 colunas Enum sem `values_callable` em `financial/` e `government_integrations/`. **Não editadas.** Quando/se for necessário, exigem autorização explícita por serem zona protegida.

## 8. 🟠 Dependentes de SCHEMA (Frente 2) — não são values_callable

128 colunas cujo **table.column não existe no banco** (model-without-migration). `values_callable` não as conserta — dependem de **migrations** (Frente 2 / B3). Listadas em `/tmp/enum_COL_MISSING.txt` durante a análise.

## 9. Totais e lembrete

- **Corrigidos nesta sessão:** Lote 1 (3) + este lote (79) = **82 inserções** de `values_callable`.
- **Restam sem values_callable:** 201, assim distribuídos: 14 divergentes (decisão), 128 schema-drift (Frente 2), 65 zona proibida, + casos como QueuePriority.
- **Lembrete:** todas as edições estão no **HOST** (fonte-de-verdade) → entram **automaticamente no próximo rebuild** de imagem (todos os containers). O `docker cp` desta sessão foi só para efeito imediato.

---

### Nota honesta
O incidente do IntEnum mostra o valor da TRAVA e do teste pré-deploy: a primeira TRAVA (só valores) era insuficiente; foi reforçada com checagem de **tipo**. A reversão foi imediata e a produção nunca ficou comprometida além dos ~minutos do diagnóstico (e mesmo assim respondendo, só com 327 rotas a menos temporariamente). Nenhum dado ou schema foi tocado.
