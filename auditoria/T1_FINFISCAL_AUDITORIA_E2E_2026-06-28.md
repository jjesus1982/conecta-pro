# Auditoria E2E Fiscal & Financeiro — continuação do trabalho da t1

**Data:** 2026-06-28 (UTC) · **Escopo (raia):** `backend/modules/financial` (inclui fiscal_controller) · READ→FIX→VERIFY
**Método:** playbook da t1 — token real, probe endpoint-a-endpoint, fix cirúrgico alinhado ao schema REAL, verificação com dado real (§13.5), deploy hot-copy + restart, re-probe.

---

## Resultado — superfície de LEITURA (GET) 100% sem erros

| Métrica | Antes | Depois |
|---|---|---|
| Endpoints GET fiscal/financeiro | 302 | 302 |
| **Erros 500 na raia** | **49** | **0** |
| Respostas 200 | 170 | **205** |
| 500 fora da raia (operacional/diaristas) | — | 2 (flag) |

Varredura completa dos 302 GET re-executada: **0 × 500 no módulo financial**. Os 60×404 e 34×422 são respostas corretas (id-dummy "não encontrado" / param obrigatório ausente no probe), não bugs.

## Causas-raiz corrigidas (todas SEM migration — alinhamento de código ao schema real)

1. **Drift de coluna (model à frente do banco):** `fiscal_obligations` (model pedia `frequencia/mes/ano` inexistentes → usar `competencia_mes/ano/valor_devido`); `financial_widgets` (sem `condominio_id` → filtrar via join em `financial_dashboards`); `cashflow_forecasts` (sem `description` → `name`).
2. **Métodos de repositório ausentes:** `CustomerRepository.get_debtors/get_by_document/get_by_morador`, `ReceivableCategoryRepository.get_root_categories`, `BillingRuleRepository.get_due_for_generation` — implementados no padrão async.
3. **Enum nativo PG vs String no model:** cashflow, inventário (`fin_stock_*`: labels reais EN maiúsculo vs `.value` PT), bank-accounts (`.value` em str).
4. **Response schema errado:** cost-centers/periods (wrapper paginado vs item); journal-entries (já corrigido); bi/widgets (6 campos NULL no banco vs non-Optional → validator before).
5. **Schema enum defasado:** `ObrigacaoFiscalResponse.status` (banco tem `cumprida`, fora do enum → `str`); `competencia_mes=0` (obrigação anual) rejeitado por `ge=1` → override sem constraint.
6. **Bugs de código:** `analyze_supplier` faltava param `condominio_id` (NameError); `legacy/predict` GroupingError (`date_trunc` parametrizado → `literal_column`); `customer-risk` 500→404 em cliente inexistente.
7. **Regressão própria contida:** 3 subagentes paralelos editaram o mesmo `receivable_repository.py`; um introduziu `list[...]` sem `builtins.` (convenção do arquivo por causa de `def list` sombreando o builtin) → módulo financial inteiro caiu (404 geral). Detectado no re-probe (§13.4), corrigido, re-verificado.

## Arquivos alterados (raia financial): 32 arquivos, +1224 / −798

## Durabilidade (§13.7/B.7)
- Âncora pré-trabalho: `conecta-pro-backend:pre-finfiscal-audit-20260628`.
- **Âncora pós-fix (estado funcional):** `conecta-pro-backend:finfiscal-fixed-20260628` (docker commit do container).
- ⚠️ As correções estão no container rodando (hot-copy) + nessa âncora. **NÃO commitadas no git nem bakeadas via rebuild canônico.** Um recreate por `docker-compose` ainda usaria `:latest` antiga. **Pendência crítica:** commit git + rebuild canônico (B.3.3) para durabilidade real.

## O QUE FALTA (próximas fases)
1. **Write E2E (criar/editar/excluir) função-por-função** — esta auditoria cobriu LEITURA. Falta exercitar escrita com marcadores `ZZE2E_` + limpeza (método t1). Subagentes já sinalizaram drifts latentes em paths de escrita: POST `/fiscal/das` (cols legadas NOT-NULL), PATCH NFe/NFSe (models legados), POST inventory (enum PT), POST widget.
2. **2 endpoints fora da raia:** `/operacional/diaristas/fiscal/documentos` (bug `AsyncSession.query` — módulo operacional).
3. **Durabilidade:** commit git isolado de `backend/modules/financial` + rebuild canônico.
4. **Frontend:** confirmar que as telas renderizam os dados agora servidos.

## Nota de completude (leitura): 9.5/10 — superfície GET fiscal/financeiro sem erros, dado real, verificado. -0.5 pela durabilidade ainda não no git/rebuild.
