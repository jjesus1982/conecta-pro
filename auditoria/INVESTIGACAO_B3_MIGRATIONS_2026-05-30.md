# INVESTIGAÇÃO B3 — Schema Drift / Migrations (READ-ONLY)

**Data:** 2026-05-30
**Tipo:** diagnóstico 100% read-only — **nenhuma migration aplicada, nenhum DDL, nada escrito no banco**.
**Objetivo:** foto do estado antes da operação de correção (fase futura).

> Confirmação: só foram executados `SELECT` (information_schema/pg_catalog/alembic_version) e `alembic heads/current/history` (leitura). Nenhum `upgrade/downgrade/stamp`, nenhum CREATE/ALTER/DROP, nenhuma edição em `alembic/versions/`.

---

## 🚨 DESCOBERTA PRINCIPAL (muda a estratégia de correção)

**O banco está registrado na HEAD do alembic (`sprint89_inter_kit_fk`).** Logo:
> **`alembic upgrade head` seria NO-OP — não criaria nenhuma das colunas/tabelas faltantes.**

O drift **não** é "migrations pendentes que ninguém rodou". É **model-without-migration**: os models do código foram além do histórico de migrations — esperam colunas/tabelas/enums para os quais **nunca foi escrita migration**. Rodar `upgrade head` não resolve nada. (Confiança: **ALTA**.)

---

## 1. Estado do Alembic — banco vs código

| Item | Valor |
|---|---|
| Head no **código** | `sprint89_inter_kit_fk` (**1 head única**) |
| `alembic current` (resolve) | `sprint89_inter_kit_fk (head)` |
| **`alembic_version` no banco** | **3 linhas**: `sprint87_d7_payments`, `sprint88_inter_cat`, `sprint89_inter_kit_fk` |
| Migrations pendentes (banco→head) | **0** (banco já na folha) |
| Total de arquivos de migration | 111 |
| Grafo geral | **ramificado** — múltiplos `<base>` e `branchpoint` no histórico (legado), **mas converge para 1 head** |

### 🚨 ALERTA A — `alembic_version` em estado ANÔMALO/CORROMPIDO (confiança ALTA)
A cadeia perto da head é **linear**:
```
sprint86_d6_inter_addendum → sprint87_d7_payments → sprint88_inter_cat → sprint89_inter_kit_fk(head)
```
O `alembic_version` correto deveria conter **apenas a folha** (`sprint89_inter_kit_fk`). Conter também `sprint87` e `sprint88` (que são **ancestrais** de sprint89) é **anomalia**: pai, filho e neto marcados como "current" ao mesmo tempo. Quase certamente resultado de **`stamp` manual** ou migração malfeita no passado.
- **Impacto:** operações de alembic (downgrade, stamp, autogenerate) podem se comportar de forma inesperada nesse estado. **Limpar o `alembic_version` para uma única linha (`sprint89_inter_kit_fk`) deve ser o PRIMEIRO passo** de qualquer correção — antes disso, não confiar em `upgrade/downgrade`.

---

## 2. Migrations "pendentes" — não há (banco na head)

Não existem migrations entre o banco e a head: o banco está em `sprint89` (a própria head). Portanto **não há tabela de pendentes a aplicar**. As 2 migrations do OpenClaw **já foram aplicadas** (as 3 tabelas `openclaw_*` existem no banco):

| Revisão | Descrição | Tipo | Risco | Tabelas | Estado |
|---|---|---|---|---|---|
| `sprint77_openclaw_interventions` | cria `openclaw_interventions` (+índices) | 🟢 Aditiva | Baixo | openclaw_interventions | **JÁ APLICADA** |
| `sprint77_openclaw_memory` | cria `openclaw_patterns`, `openclaw_knowledge_base` + add colunas em interventions | 🟢 Aditiva | Baixo | openclaw_patterns, openclaw_knowledge_base, openclaw_interventions | **JÁ APLICADA** |

> Para o **Nível 2 do B2** (drop das tabelas `openclaw_*`): isso **não** é "reverter migration pendente" — exigiria uma **nova migration de downgrade** (ou DROP manual), pois as tabelas já existem e o alembic se considera na head. Operação destrutiva → tratar na fase de banco, com dump fresco. (Confiança: ALTA.)

**Nota:** como o banco está na head, **não há o cenário "migration pendente tentaria recriar coluna já existente"** (PASSO 3.3) — esse trap específico não se aplica aqui. O risco equivalente aparece se alguém usar `--autogenerate` (ver Alerta C).

---

## 3. Mapa do DRIFT REAL — banco vs models (por família de endpoint 500)

| Família / endpoint | Objeto esperado pelo model | Existe no banco? | Migration cria? | Classificação | Confiança |
|---|---|---|---|---|---|
| audit `/audit/access` | `access_history.extra_metadata` (JSONB) | ❌ **AUSENTE** | ❌ não p/ esta tabela (migrations criam `extra_metadata` em ged/data_quality/meeting, não em access_history) | **model-without-migration** | ALTA |
| integrations `/integrations/sync` | `sync_queue.extra_metadata` | ❌ **AUSENTE** | ❌ | **model-without-migration** | ALTA |
| reports `/reports/kpis` `/reports/templates` | `executive_kpis.tenant_id`, `report_templates.tenant_id` | ❌ **AUSENTE** | ❌ p/ estas tabelas (19 migrations citam tenant_id em outras) | **model-without-migration** | ALTA |
| retention `/retention/profile/questionnaire` | tabela `profile_questions` | ❌ **AUSENTE** (`to_regclass` nulo) | ❌ nenhuma migration cria | **model-without-migration** (tabela inteira) | ALTA |
| audit/compliance `/audit/compliance/overview` | enum `rulestatus` | ❌ **AUSENTE** (tipo não existe) | ❌ | **drift de SCHEMA real** (enum faltante) | ALTA |

### 🚨 ALERTA B — Os enums `tenant_status`/`alertstatus` NÃO são drift de schema (confiança ALTA)
Os tipos **existem** no banco, com valores **corretos**:
- `tenant_status` = `active, inactive, suspended, blocked, trial, cancelled`
- `alertstatus` = `pending, investigating, confirmed, false_positive, resolved, escalated, closed, active`

O model (`modules/config/models/tenant.py`) define `class TenantStatus(StrEnum): ATIVO = "active"` — **nome** `ATIVO`, **valor** `"active"`. Os erros `invalid input value for enum tenant_status: "ATIVO"` (celery) e `'active' not among enum tenantstatus (ATIVO/INATIVO)` (config/tenants) são o **bug `values_callable`**: sem `values_callable`, o SQLAlchemy grava/lê o **nome** (`ATIVO`/`ACTIVE`) em vez do **valor** (`active`), e o enum do banco só aceita o valor.
- **Consequência:** isto é **correção de CÓDIGO** (os ~208 `Column(Enum)` sem `values_callable` do CHECAGEM_GERAL), **não** uma migration. O dado no banco está correto (minúsculo); o schema está correto. Só `rulestatus` precisa de migration.
- **Distinção pedida (PASSO 3.4):** drift de SCHEMA = só `rulestatus` (enum não existe). O resto dos erros de enum = **bug de ORM (nome vs valor)**, nem schema nem dado.

### 🚨 ALERTA C — `--autogenerate` é arriscado neste estado (confiança MÉDIA-ALTA)
A tentação de gerar tudo com `alembic revision --autogenerate` tem 2 riscos: (1) roda sobre o `alembic_version` corrompido (3 linhas) → comportamento imprevisível; (2) autogenerate compara models×banco e pode propor **DROP** de objetos que existem no banco mas não nos models atuais (ex.: tabelas de módulos removidos como openclaw, ou colunas legadas) — gerando uma migration **destrutiva** silenciosa. **Nunca aplicar autogenerate cego.**

---

## 4. 🚨 Resumo dos ALERTAS (o que decide a estratégia)

- **A — `alembic_version` corrompido** (3 linhas, ancestrais + folha juntos): limpar para 1 linha **antes** de qualquer operação.
- **B — Metade do "drift de enum" é bug de código** (`values_callable`), não schema: separar essa correção (código) da operação de banco.
- **C — `upgrade head` = no-op**; **`--autogenerate` = risco de DROP destrutivo** sobre estado corrompido.
- **D — Tudo que falta é ADITIVO** (add column/create table/create enum): a correção de banco em si é de **baixo risco intrínseco** (nada precisa dropar para corrigir o drift) — o risco está no **processo/estado do alembic**, não nas operações.

---

## 5. RECOMENDAÇÃO DE ESTRATÉGIA (proposta — nada executado)

Para o Jordan decidir na fase de correção (sempre com **dump fresco** antes):

1. **NÃO** rodar `alembic upgrade head` (no-op) nem `--autogenerate` cego.
2. **Passo 0 da correção:** sanear o `alembic_version` → deixar **apenas** `sprint89_inter_kit_fk`. (Operação de 1 linha, mas é DML no controle do alembic → backup antes.)
3. **Correção do drift de schema** — abordagem **cirúrgica, aditiva, objeto-a-objeto** (não autogenerate cego):
   - `access_history.extra_metadata` (JSONB, nullable) · `sync_queue.extra_metadata` (JSONB, nullable)
   - `executive_kpis.tenant_id` · `report_templates.tenant_id`
   - tabela `profile_questions` (criar conforme o model do retention)
   - enum `rulestatus` (criar tipo + usar onde o model espera)
   - Forma recomendada: **migrations novas escritas à mão** (uma por família), revisadas, encadeadas a partir de `sprint89` — em vez de autogenerate. Validar cada uma contra um **restore do backup** (staging), nunca direto em produção.
4. **Correção do bug de enum (B)** — **separada, no código**: aplicar `values_callable` nos `Column(Enum)` afetados (tenant_status/alertstatus/etc.). Isso **resolve a maioria dos 500 de enum sem tocar no banco**. (Itens em `financial/`/`government_integrations/` ficam fora — zona protegida.)
5. **Nível 2 OpenClaw** (drop das 3 tabelas + limpeza das 2 migrations já aplicadas): operação destrutiva separada, só após decisão e com dump.
6. **Validar a extensão total do drift** num ambiente de restore (não-prod): rodar um `--autogenerate` **apenas para DIFF/leitura** (revisar o que ele propõe, sem aplicar) ajuda a achar colunas faltantes além da amostra deste relatório.

---

## 6. Limitações / o que NÃO foi verificado (honestidade)

- O mapa do drift cobre as **5 famílias** que davam 500 no CHECAGEM_GERAL + amostras. **Não** fiz diff exaustivo de todos os models × schema — a extensão completa do model-without-migration pode ser maior (ver recomendação 6).
- **Como** o `alembic_version` chegou a 3 linhas não foi possível determinar (sem histórico de quem stampou) — afirmo o estado (corrompido), não a causa exata. Confiança no estado: ALTA; na causa: BAIXA.
- Não executei `alembic upgrade --sql` (modo offline) para não arriscar leitura confusa sobre o estado multi-linha; baseei-me no grafo + `alembic_version` + `heads/current`, que são consistentes.
- Confiança geral dos achados de schema (information_schema): **ALTA** (consultas diretas). Distinção enum schema-vs-código: **ALTA**.
