# FRENTE 2A — Aditivo Seguro (SEGURADO) + Descoberta sobre a Fase de Rename

**Data:** 2026-05-30
**Decisão do Jordan:** **segurar o aditivo, ir para a fase de rename.** → **Nenhuma DDL aplicada em produção.**
**Produção:** intocada. Validações em staging (`conecta_pro_drift_check`, descartável).

---

## 1. Frente 2A (aditivo) — conclusão: conjunto seguro é PEQUENO

A análise new-vs-rename mostrou que a maioria dos "1.176 faltando" **não é coluna nova** — é rename ou redesenho. O conjunto **genuinamente aditivo e seguro** (sem esconder dado) é só:

| Item | Qtd | Observação |
|---|---:|---|
| `tenant_id` (UUID, nullable) | 10 tabelas | genuinamente novo (sem fonte de rename); mas tabelas são rename-heavy → não destrava os endpoints |
| `extra_metadata` (JSONB) **genuíno** | 6 tabelas | `checklist_itens, device_tokens, financial_kpis, mobile_sessions, notification_templates, work_schedules` |
| `extra_metadata` que é **RENAME** | 21 tabelas | **EXCLUÍDAS** — têm coluna db-only `metadata` (nome reservado no SQLAlchemy → renomeado). Adicionar esconderia dado. |
| `rulestatus` (enum) | — | **adiado** — acoplado a decisão de `values_callable` (não é aditivo puro) |

→ **16 `ADD COLUMN` seguros** no total (testados limpos em staging, exit 0). **Não aplicados em produção** por decisão do Jordan, e porque **não destravam os 500 nomeados** (que dependem de rename/redesenho).

## 2. 🔑 DESCOBERTA DECISIVA — a "fase de rename" é, na verdade, REDESENHO de model

As tabelas que bloqueiam os 500 (`executive_kpis`, `report_templates`, `report_schedules`, `benchmarks`, `financial_kpis`) **não sofreram um rename PT→EN simples** — o model foi **reescrito numa geração diferente** do banco. Evidência (`executive_kpis`):

| Banco (atual) | Model (esperado) | Tipo de mudança |
|---|---|---|
| `threshold_critical` | `critical_threshold_high` + `critical_threshold_low` | **split** (1→2 colunas) |
| `threshold_warning` | `warning_threshold_high` + `warning_threshold_low` | **split** |
| `precision` | `decimal_places` | rename EN→EN |
| `visibility` | `visible_on_dashboard` | rename EN→EN (semântica diferente) |
| `trend_percentage` | `historical_values`, `last_12_months`… | reestruturação |

→ Isto **não é mecânico**. Cada tabela redesenhada precisa de **migration de dados sob medida** (mapear estrutura antiga→nova), decidida caso a caso. Os 500 dessas tabelas **não têm correção rápida**.

## 3. Mapa de rename — o que É mecânico (data-preserving)

Pares PT→EN de **alta confiança** (dicionário), seguros para `ALTER ... RENAME COLUMN` (preserva dado):
- **35 pares** em todo o banco (23 tabelas), dominados por: `codigo→code`, `nome→name`, `descricao→description`, `metadata→extra_metadata`, `ordem→order`.
- Tabelas simples 100% resolvíveis por rename: `access_history` (`metadata→extra_metadata`), `sync_queue` (`metadata→extra_metadata`) — **estas SIM destravariam os 500** de `/audit/access` e `/integrations/sync` com 1 rename cada.

Mapa detalhado das tabelas-chave: `auditoria/FRENTE2_RENAME_MAP_KEY_2026-05-30.txt`.

## 4. Recomendação de caminho (para a fase de rename, validar em staging primeiro)

Ordenado por valor × segurança:

1. 🟢 **Renames mecânicos de 1 coluna que destravam 500** — `access_history.metadata→extra_metadata` e `sync_queue.metadata→extra_metadata`. **Data-preserving, baixo risco, destrava 2 dos 5 endpoints 500.** Melhor candidato para a primeira ação de rename.
2. 🟢 **Demais renames de alta confiança** (33 pares: codigo/nome/descricao/ordem) — mecânicos, mas as tabelas (kpis/reports/benchmarks) **continuarão 500** por causa do redesenho (item 3). Renomear ajuda mas não fecha.
3. 🔴 **Tabelas redesenhadas** (`executive_kpis`, `report_templates`, `report_schedules`, `benchmarks`, `financial_kpis`) — exigem **decisão de produto + migration de dados bespoke** por tabela (splits, semântica nova). Alto esforço, alto cuidado. **Não há atalho.**
4. 🟢 **Aditivo seguro** (os 16 da Frente 2A) — pode ir junto quando fizer sentido; reversível.

## 5. Alertas para a fase de rename

- **`ALTER TABLE ... RENAME COLUMN` preserva dado** (seguro), mas o app precisa estar no código que espera o nome novo (já está — os models). Renomear no banco alinha banco→model. Reversível (rename de volta).
- **NUNCA** "adicionar a coluna EN + dropar a PT" — isso perde dado. Sempre `RENAME`.
- **Validar cada rename contra o restore** (`conecta_pro_drift_check`) e confirmar que o endpoint correspondente sai do 500, antes de produção.
- **Tabelas redesenhadas:** não tentar rename mecânico — o pareamento é ambíguo (splits/semântica). Tratar como migração de dados dedicada.
- **Pré-requisito (B3):** sanear o `alembic_version` de produção antes de registrar qualquer migration.

## 6. Estado

- **Produção:** nenhuma DDL aplicada. `alembic_version` de prod intacto (3 linhas).
- **Staging `conecta_pro_drift_check`:** recebeu os 16 ADD COLUMN de teste (descartável) — pode ser recriado do dump quando a fase de rename começar.
- Mapa de rename salvo; conjunto aditivo seguro identificado e testado, à espera de decisão.
