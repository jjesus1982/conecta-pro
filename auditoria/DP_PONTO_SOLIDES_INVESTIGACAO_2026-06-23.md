# Investigação: ponto "zerado" do DP + integração Sólides — READ-ONLY

**Data:** 2026-06-23 · **Escopo:** ponto (DP) + connector Sólides. **Read-only**, nada alterado. **§13.1/§13.4/§13.5.**

---

## RESUMO (o achado é maior que "ponto zerado")
O ponto **não está vazio** — está **parado em 30/mar**. E ele **não vem do Sólides** (arquitetura é o inverso do esperado). A integração Sólides está **"verde mas morta"**: roda a cada 15 min reportando sucesso, mas os dados estão congelados (jan/mar).

## 1. Correção do falso alarme: ponto não está em `time_entries`
- `time_entries`/`time_sheets`/`overtimes` (módulo `hr.time_tracking`) = **0** → sistema de ponto **paralelo, nunca usado**.
- O ponto REAL está em **`gp_clock_punches` = 1830 batidas** (módulo GP/people_management; facial + GPS + geofence + posto).

## 2. Ponto nativo PAROU em 30/mar
- `gp_clock_punches`: 1830 registros, de **01/mar a 30/mar**, depois **nada**. device_type: `web` (1828) + `manual` (2).
- Volume caiu abruptamente: 100 batidas em 20/mar → 2/dia no fim → zero após 30/mar.

## 3. Arquitetura real (INVERSO do que se esperava)
Código (`connectors/solides/tasks.py:427`, `connector.py:671`):
- **Sólides → Conecta** puxa só: `["employees", "job_roles", "workplaces", "work_schedules"]`. **NÃO traz batidas.**
- **Conecta → Sólides**: `push_punch_as_occurrence()` — Conecta captura batida nativa e **empurra** pro Sólides como ocorrência.
- Conclusão: **as batidas nunca foram sourced do Sólides.** O Conecta tem captura própria (web/facial/GPS).

## 4. Sólides está "verde mas morto"
| Sinal | Evidência |
|---|---|
| Sync roda hoje | `solides_sync_log`: a cada 15 min, status `completed`, 47 processados, 40 "created", 0 failed/erros |
| MAS dados congelados | `solides_employees.updated_at` máx = **18/jan** · `solides_work_schedules` = **18/jan** |
| entity_mapping travado | máx `last_synced_at` = **15/mar** (44 linhas) |
| Push pro Sólides nunca rodou | `solides_occurrences = 0` |

→ O sync reporta "40 created" todo ciclo, mas a tabela tem só 44 linhas e `updated_at` não muda desde jan. **Os números reportados não refletem escrita real** — sync efetivamente no-op (a investigar: escreve em condominio/local errado? upsert não toca updated_at? grava e dá rollback?).

## 5. Resposta: o DP está pronto para uso real?
**Não, no que toca ponto/Sólides:**
- ✅ Funciona com dado real: cadastro (58 funcionários, 44 do Sólides até jan), folha (51 contracheques), férias (67).
- 🔴 **Ponto parado desde 30/mar** (captura nativa cessou).
- 🔴 **Sólides congelado** (funcionários em jan, mapping em mar) apesar de logs verdes.
- 🔴 **Batidas não fluem do Sólides** (nunca fluíram — direção inversa) e o push Conecta→Sólides nunca rodou (0 ocorrências).

## Pontos de decisão (nada alterado — sua direção)
1. **Por que a captura nativa de ponto parou em 30/mar?** App/posto deixou de enviar? Endpoint de marcação quebrou? (precisa investigar o fluxo de captura — mobile/web + `gp_clock_punches`).
2. **O Sólides DEVERIA trazer batidas?** Se sim, é uma feature **não implementada** (hoje só puxa employees/roles/workplaces/schedules). Se não, o ponto é nativo e o problema é (1).
3. **Sólides "verde mas morto":** o sync precisa de auditoria — completa reportando sucesso mas não atualiza desde jan. Possível credencial expirada / token / endpoint mudou / escrita silenciosamente falha.
4. **Esclarecer o modelo de operação:** os funcionários vieram do Sólides (até jan); confirmar se hoje o cadastro-mestre é Sólides (e precisa voltar a sincronizar) ou se virou nativo.

> Nada foi alterado. Recomendo começar por (3) auditar por que o sync Sólides está congelado (é a raiz: se ele voltar, funcionários atualizam; e esclarece se batidas entram por lá), e (1) por que a captura nativa parou em março.
