# FRENTE A — Limpeza Geral de Agentes + Telegram (autônoma, quarentena reversível)

**Data:** 2026-05-31 · **Status:** ✅ **CONCLUÍDO** — quarentena reversível, zero quebra, dashboard+backend 100%.
**Princípio:** nada deletado. Tudo MOVIDO p/ `_quarentena_20260531/` ou cron COMENTADO com `#`.

## Backups (Passo 0)
- Crontab: `_quarentena_20260531/crontab/crontab_PRE_LIMPEZA_20260531_235424.txt` (119 linhas).
- Agents (tar): `_quarentena_20260531/agents_FULL_PRE_LIMPEZA.tgz` (3.9M).

## Passo 1 — Crons COMENTADOS (7) — não apagados, prefixo `# [LIMPEZA 20260531]`
| Cron | Motivo |
|---|---|
| `1h-sentinela.sh` | arquivo inexistente (erro horário) |
| `orchestrator_unificado.py completo` | rate-limit de API, 100% falha, queima quota |
| `proatividade` (cto) | log 0 bytes |
| `relatorio_semanal.py` (cto) | log 0 bytes |
| `auto_evolucao` (cto) | log 0 bytes |
| `turno` (cto) | log 0 bytes |
| `check-conectado-health.sh` | bot Telegram órfão |

Crons **PRESERVADOS ativos:** orchestrator (rapido */5, heartbeat), `dashboard_api.py` (*/2 → dashboard vivo), `context_builder.py`, `backup_database.sh` (03:00), cto (relatorio_matinal, aprendizado, reindexar, preditor), system_monitor/metrics/security.

## Passo 2 — Trava de import (OBRIGATÓRIA) — resultado conservador
80 candidatos analisados (grep de referência por nome de módulo + caminho + JSON index + crontab). **Regra: na dúvida, MANTER.**
- **MOVIDOS p/ quarentena (4 — sem referência alguma):**
  - `agents/knowledge/memory_service_original.py`
  - `agents/knowledge/remediation_service_original.py`
  - `agents/knowledge/telegram_service_original.py`
  - `agents/nivel3/master_orchestrator.py`
- **MANTIDOS por referência/entrypoint (76):** todo o resto do framework (nivel3/modules/core/corretor/knowledge/cto) está cross-referenciado (imports entre si OU listado em `agents_index.json`/`knowledge_base.json`) → mantido por segurança (falso-mantido > falso-movido).
- **REVERTIDOS por import: 0** — nenhum dos 4 movidos era referenciado; nenhum ImportError.

## Passo 3 — Bot Telegram órfão
- `check-conectado-health.sh` → `_quarentena_20260531/scripts/` (cron já comentado).
- **NÃO tocados** (válidos): `monitor_bot.py` + bot `@conecta_pro_monitor_bot` (token 8562…SuBQ), `telegram_assistant.py` + bot `@conectapro_alertas_bot` (token 8343…DVOQ).

## Passo 4 — Validação final
| Item | Resultado |
|---|---|
| `bash -n backup_database.sh` | ✅ OK |
| `dashboard_api.py` regenera JSON | ✅ Containers 25/31, RAM 58.2%, Tickets 100 — sem ImportError |
| Import dos preservados (orchestrator, context_builder, cto.brain, core.auto_remediator, telegram_assistant, monitor_bot) | ✅ todos OK |
| Os 4 movidos referenciados? | ✅ nenhum (sem refs) |
| Backend health | ✅ 200 |
| Containers conecta-pro healthy | ✅ 14/14 |
| Crontab | ✅ 7 comentados, preservados intactos |

## Contagem
- **7** crons comentados · **4** .py movidos · **76** mantidos-por-referência · **0** revertidos-por-import · **1** bot órfão quarentenado.

## 🔄 BLOCO DE REVERSÃO TOTAL (desfaz tudo de uma vez)
```bash
cd /opt/conecta-pro
# 1) restaurar os .py da quarentena (preservando subpath)
for f in $(find _quarentena_20260531/agents -name '*.py'); do dest="${f#_quarentena_20260531/}"; mkdir -p "$(dirname "$dest")"; mv "$f" "$dest"; done
# 2) restaurar o bot órfão
mv _quarentena_20260531/scripts/check-conectado-health.sh /root/ 2>/dev/null
# 3) restaurar o crontab original (descomenta tudo)
crontab _quarentena_20260531/crontab/crontab_PRE_LIMPEZA_20260531_235424.txt
```
