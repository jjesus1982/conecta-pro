# FRENTE 2 — PASSO 1: Mapa Completo do Schema Drift (READ-ONLY, em STAGING)

**Data:** 2026-05-30
**Tipo:** diagnóstico — **nada aplicado**, **produção intocada**.
**Objetivo:** medir a extensão total do drift model↔banco antes de escrever migrations (fase futura).

> Mapa bruto completo: `auditoria/FRENTE2_DIFF_RAW_2026-05-30.txt` (lista item-a-item).

---

## 1. Confirmação de isolamento — produção INTOCADA

- Todo o trabalho rodou contra **STAGING**: instância `conecta-pro-postgres-staging` (172.21.0.2, rede `conecta-staging-network`), DB de trabalho **`conecta_pro_drift_check`** (clone do backup de produção).
- Backup restaurado: `conecta_pro_PRE_REBUILD_20260530_150432.dump` (534 tabelas, 317 enums).
- **Produção (`conecta-pro-postgres`, 172.18.0.7, `conecta_pro`) só foi LIDA** para confirmar identidade. Seu `alembic_version` permanece com as 3 linhas originais (sprint87/88/89) — **não foi saneado em produção**, apenas na cópia de staging.
- O saneamento do `alembic_version` (deixar só `sprint89_inter_kit_fk`) e a geração do diff ocorreram **exclusivamente** no staging descartável.
- Container de geração (`drift-gen`) ficou **somente na rede de staging** (sem rota para produção) e já foi removido. DB `conecta_pro_drift_check` preservado para a fase de escrita das migrations.

## 2. ⚠️ Metodologia — autogenerate BLOQUEADO, usado diff por introspecção (mais completo)

O `alembic revision --autogenerate` **falhou** (mesmo com `alembic_version` saneado e todos os models importados):
```
sqlalchemy.exc.NoReferencedTableError: Foreign key associated with column
'documentos_fiscais_diaristas.diarist_id' could not find table 'diaristas'
```
**Causa:** o `env.py` usa `target_metadata = core.models.Base.metadata` + uma lista **curada** de imports, mas os models estão **fragmentados em múltiplos `Base`/metadatas**. A tabela `diaristas` vive num metadata diferente do `documentos_fiscais_diaristas`, então o autogenerate (que compara **um** metadata) não resolve a FK.

**Solução:** gerei o diff por **introspecção de TODOS os metadatas** (via registries do SQLAlchemy, capturando os múltiplos `Base`) cruzado com o `information_schema` do staging. É **mais completo** que o autogenerate do projeto. **Validado** contra achados conhecidos da Frente 1:
- ✅ `access_history.extra_metadata` → aparece como ADD_COLUMN (faltava no banco)
- ✅ `profile_questions` → aparece como CREATE_TABLE (tabela ausente)
- ✅ `diaristas` está no model (não em DROP) — confirma que a introspecção capturou o que o env.py não capturava

> Limitação honesta: a introspecção cobre os models **carregados** por `main_production`. Tabelas no banco sem model carregado entram como "só-no-banco" — podem ser **legado real** OU models não importados. Distinção exige revisão manual (ver §4).

## 3. Extensão TOTAL do drift

| Categoria | Tabelas | Colunas |
|---|---:|---:|
| 🟢 **ADITIVO — faltando no banco** (drift real a corrigir) | **78** | **1.176** |
| 🔴 **SÓ-NO-BANCO** (autogenerate proporia DROP — ruído/perigo) | **234** | **995** |

Model: 377 tabelas · Banco (staging): 534 tabelas.

### Onde o drift de COLUNAS se concentra (top tabelas existentes com mais colunas faltando)
`push_campaigns (29), financial_widgets (24), work_schedules (22), benchmarks (21), push_notifications (20), push_devices (20), notification_templates (20), cashflow_forecasts (19), push_ab_test_results (16), nfe_itens (16), financial_kpis (16), executive_kpis (16)` …
→ Núcleos: **push/notifications**, **dashboards financeiros** (widgets/kpis/forecasts), **work_schedules**, **benchmarks**, **nfe_itens**.

## 4. Classificação 🟢🟡🔴 (todas as operações do diff)

| Operação | Qtd | Tipo | Risco | Intenção |
|---|---:|---|---|---|
| `create_table` (78 tabelas no model, ausentes no banco) | 78 | 🟢 Aditiva | Baixo | **DRIFT REAL** — criar |
| `add_column` (nullable na maioria) | 1.176 | 🟢 Aditiva | Baixo | **DRIFT REAL** — adicionar |
| `create enum/type` (ex.: `rulestatus`) | (subset) | 🟢 Aditiva | Baixo | DRIFT REAL — criar tipo |
| `drop_table` (234 tabelas só-no-banco) | 234 | 🔴 Destrutiva | **ALTO** | **RUÍDO do autogenerate — NÃO aplicar** |
| `drop_column` (995 colunas só-no-banco) | 995 | 🔴 Destrutiva | **ALTO** | **RUÍDO do autogenerate — NÃO aplicar** |
| `alter_column` (tipo/nullable) | não medido | 🟡 Alteradora | Médio | autogenerate bloqueado — requer comparação fina futura |

> `alter_column`: a comparação de **tipos** exige o autogenerate funcional (bloqueado pela fragmentação de metadata). Esta foto cobre **presença** (tabela/coluna existe ou não), que é o cerne do "model-without-migration". Diferenças de tipo/nullable de colunas existentes **não foram medidas** — pendência para quando o autogenerate for desbloqueado (corrigir a FK `diaristas`/metadata).

## 5. DRIFT REAL (a corrigir) × RUÍDO do autogenerate (a IGNORAR)

### 🟢 DRIFT REAL — vira as migrations da fase futura (aditivo, baixo risco)
- **78 tabelas** a criar (ex.: `documentos_fiscais_diaristas`, `profile_questions`, `email_queue/templates/campaigns`, `ecd_resumos`, `efd_contribuicoes_resumos`, `cct_benefit_configs`, `campo_tecnicos`, `access_logs` …).
- **1.176 colunas** a adicionar (concentradas nas tabelas da §3).
- **Enum `rulestatus`** a criar (Frente 1 / B3).

### 🔴 RUÍDO / PERIGO — autogenerate proporia DROP, **NÃO aplicar**
- **234 tabelas só-no-banco**, das quais:
  - **3 backups manuais óbvios:** `allocations_backup_20260506`, `employees_backup_20260506`, `ged_document_kits_backup_20260404` (cópias de segurança — **não dropar**; limpeza manual separada se desejado).
  - **3 tabelas openclaw** (`openclaw_interventions`, `openclaw_patterns`, `openclaw_knowledge_base`) — do módulo removido (Nível 2 do B2, decisão separada com dump).
  - **~228 demais:** tabelas sem model carregado — **legado real OU models não importados**. **Revisão manual obrigatória; NUNCA auto-dropar.**
- **995 colunas só-no-banco:** mesma natureza (colunas legadas/divergentes). **NÃO dropar.**
- **Divergências de enum (Frente 1):** `TenantType`, `TenantPlan` + 14 classes (`ServiceStatus`, `NotificationStatus`, etc.) — valores Python ≠ banco. **Não são create/add**; são decisão de reconciliação (não entram nas migrations aditivas).

## 6. Estimativa da fase de aplicação (futura)

- **Volume aditivo:** 78 create_table + 1.176 add_column + ≥1 create enum. **Intrinsecamente baixo risco** (tudo aditivo, nullable), mas **alto volume**.
- **Não dá para autogenerate cego** (bloqueado + proporia 234+995 DROPs catastróficos). Caminhos:
  - (a) **Desbloquear o autogenerate** primeiro: corrigir a fragmentação de metadata (a FK `documentos_fiscais_diaristas → diaristas`) para o env.py enxergar tudo, então gerar e **filtrar manualmente** removendo TODOS os drops; ou
  - (b) **Escrever migrations aditivas à mão** por feature/módulo, derivadas do diff bruto (mais trabalhoso, mais seguro).
- **Estimativa:** agrupando por feature (push, notifications, financial-dashboards, fiscal/SPED, cct, campo, email, diaristas, retention…), ~**12–20 migrations aditivas**. Cada uma validada contra o `conecta_pro_drift_check` (restore) antes de qualquer toque em produção.
- **Passo 0 obrigatório da aplicação:** sanear o `alembic_version` de **produção** (remover sprint87/88, deixar sprint89) — operação de 1 linha, com dump fresco antes.

## 7. 🚨 ALERTAS para a fase de aplicação

1. **NUNCA rodar `alembic upgrade head` cego nem autogenerate-apply:** o autogenerate proporia **DROP de 234 tabelas + 995 colunas** (inclui backups e tabelas legadas com dados). Aplicar isso seria **catastrófico**. Toda migration da fase futura deve ser **somente aditiva** e revisada linha a linha.
2. **`alembic_version` de produção está corrompido** (3 linhas) — sanear ANTES, no controle, com dump.
3. **3 tabelas de backup** no banco não devem ser confundidas com drift — são cópias de segurança intencionais.
4. **Diferenças de tipo/nullable** (`alter_column`) não foram medidas (autogenerate bloqueado) — lacuna conhecida a fechar.
5. **Validar cada migration contra o restore** (`conecta_pro_drift_check` no staging), nunca direto em produção.

---

### Estado final
Produção intocada (lida apenas). Staging: cópia restaurada + `alembic_version` saneado + diff completo gerado e salvo. Container descartável removido. Mapa bruto em `FRENTE2_DIFF_RAW_2026-05-30.txt`.
