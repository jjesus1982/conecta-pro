# CENSO DOS AGENTES — Auditoria forense READ-ONLY (2026-05-31)

**Pergunta:** dos 80+ "agentes", quais funcionam, quais rodam sem agir, quais são lixo? E **por que nenhum pegou a crise de 20-30/mai?**
**Método:** inventário + cruzamento com cron + datas de log + leitura dos logs arquivados da crise (.gz). Nada alterado.

---

## NÚMEROS REAIS
- **84 arquivos `.py` + 7 `.sh`** em `/opt/conecta-pro/agents/` (subdirs: nivel3=17, modules=17, cto=17, raiz=14, core=8, cto/predicao=4, cto/corretor=4, knowledge=3).
- **Mas só ~16 jobs no cron.** Os outros ~68 `.py` são bibliotecas importadas OU código morto sem gatilho.
- **82 de 84 `.py` modificados em 01-07/ABR** — o enxame está **congelado há ~2 meses** (só `context_builder.py` e `dashboard_api.py` foram tocados em maio, por mim).

## 🔥 TESTE DE FOGO — a crise de 20-30/mai (com evidência dos logs .gz)
- Os monitores **RODARAM** na crise: há archives `monitor_completo.log.{11..2}.gz` de **20 a 29/mai** (rotação diária, `rotate 7`).
- **NÃO dependem de docker** (`docker_calls=0` no orchestrator/system_monitor) → não travaram no dockerd hang.
- **MAS registraram 0 indicadores de crise:** `alertas_crise=0` em quase todos os archives de 20-28/mai (nenhum "RAM 90%", "load 127", "zumbis", "dockerd").
- **`alertas.log` na crise = vazio de infra:** 93 bytes/dia; o único conteúdo é alerta de **negócio** ("12 vencidos, R$ 319.131" = inadimplência). **Nenhum alerta de infra disparado.**
- **O `monitor_completo` de 22/mai (auge) tem só 241 bytes** (vs ~1700 normal) — truncado/falhou, provavelmente sufocado pela própria RAM que deveria ter detectado.
- **Hoje o `monitor_completo` falha por rate-limit:** `[TOKEN] Rate limit — aguardando 65s/130s/195s... Falhou após todas as tentativas` — depende de chamada de API que estoura quota e não conclui a análise.

**→ Veredito do teste de fogo: os agentes RODARAM mas eram CEGOS para infra.** Monitoravam negócio (inadimplência) e faziam "análise inteligente" via API que falha/trunca. Nenhum tinha um check simples e robusto de RAM/load/zumbi que disparasse alerta.

---

## TABELA-MESTRE (agentes com gatilho de cron)

| Agente | Caminho | Cron | Última exec (log) | AGE ou só roda? | Teria pego a crise? | Veredito |
|---|---|---|---|---|---|---|
| backup_database.sh | scripts/ | 0 3 | hoje 03:00 ✅ | AGE (gera dump) | n/a (backup) | 🟢 FUNCIONA |
| dashboard_api.py | agents/ | */2 | hoje 14:54 | AGE (gera JSON vivo) | n/a (mostra) | 🟢 FUNCIONA |
| orchestrator_unificado (rapido) | agents/ | */5 | hoje 14:55 | só roda (heartbeat) | ❌ logou 0 crise em 20-28/mai | 🟡 RODA, NÃO AGE |
| orchestrator_unificado (completo) | agents/ | */30 | hoje 14:36 | **FALHA** (rate-limit API) | ❌ não conclui análise | 🔴 QUEBRADO |
| orchestrator_unificado (heartbeat) | agents/ | 0 */6 | hoje 12:06 | só heartbeat | ❌ | 🟡 RODA, NÃO AGE |
| cto/predicao/preditor_principal.py | agents/cto/predicao | */5 | hoje 14:55 (8.8KB) | "prediz" | ❌ não previu a crise (0 alertas) | 🟡 RODA, NÃO AGE |
| context_builder.py | agents/ | */2 | hoje | monta contexto p/ assistente | ❌ (não alerta) | 🟡 RODA, NÃO AGE |
| cto/reindexar.sh | agents/cto | 0 * | hoje 14:00 (1KB) | reindexa knowledge | ❌ | 🟡 RODA, NÃO AGE |
| cto/aprendizado | agents/cto | 0 */6 | hoje 12:00 (345b) | "aprende" | ❌ | 🟡 RODA, NÃO AGE |
| cto/relatorio_matinal.py | agents/cto | 0 10 | hoje 10:00 (113b) | relatório mínimo | ❌ | 🟡 RODA, NÃO AGE |
| cto/proatividade | agents/cto | 0 */4 | 30/mai (**0 bytes**) | nada | ❌ | 🔴 VAZIO |
| cto/relatorio_semanal.py | agents/cto | 0 11 seg | **0 bytes** | nada | ❌ | 🔴 VAZIO |
| cto/auto_evolucao | agents/cto/core | mensal | **0 bytes** | nada | ❌ | 🔴 VAZIO |
| cto/turno | agents/cto | 0 * | 29/mai (**0 bytes**) | nada | ❌ | 🔴 VAZIO |
| system_monitor.sh | /opt/scripts | */15 | (roda) | monitora sistema | ❌ não alertou na crise | 🟡 RODA, NÃO AGE |
| metrics_collector.sh | scripts/ | */5 | (roda) | coleta métricas | ❌ | 🟡 RODA, NÃO AGE |
| security_monitor.sh | scripts/ | */30 | (roda) | segurança | ❌ (escopo diferente) | 🟡 RODA |
| 1h-sentinela.sh | rotinas/scripts | 0 * | **ARQUIVO NÃO EXISTE** | nada (cron erra de hora em hora) | ❌ | 🔴 MORTO/QUEBRADO |
| preventive_action.py (OpenClaw) | agents/ | (removido hoje) | — | era "0 ações" | ❌ | 🔴 REMOVIDO |
| pattern_learner.py (OpenClaw) | agents/ | (removido hoje) | — | aprendia ruído | ❌ | 🔴 REMOVIDO |

## OS ~68 `.py` SEM CRON (bibliotecas ou código morto)
`agents/nivel3/` (17), `agents/modules/` (17), `agents/core/` (8), `agents/cto/corretor/` (4), `agents/knowledge/` (3) + raiz (knowledge_builder, action_executor, conversation_memory, monitor_state, regression_detector, skills_agent, orchestrator_geral, telegram_assistant…). **Nenhum tem gatilho de cron próprio.** Alguns são importados pelo orchestrator/cto; a maioria parece **framework morto** (business_agent, etc.) de 01-07/abr nunca exercitado. `regression.log`, `auto_evolucao.log` = 0 bytes.

## CONTAGEM (dos que têm gatilho)
- 🟢 **FUNCIONA E AGREGA: 2** — `backup_database.sh`, `dashboard_api.py`.
- 🟡 **RODA MAS NÃO AGE: ~10** — orchestrators (rapido/heartbeat), preditor, context_builder, system_monitor, metrics_collector, reindexar, aprendizado, relatorio_matinal, security_monitor.
- 🔴 **MORTO/LIXO/QUEBRADO: ~7** — orchestrator completo (rate-limit), 1h-sentinela (arquivo ausente), proatividade/relatorio_semanal/auto_evolucao/turno (0 bytes), + OpenClaw (removido hoje).
- + **~68 `.py` sem gatilho** (framework morto/bibliotecas) — a esmagadora maioria dos "80+".

## OS POUCOS QUE VALEM MANTER (com prova)
1. **`backup_database.sh`** — gera dump válido diário (provado: `backup_20260531_*.sql.gz`, 525 tabelas). 🟢
2. **`dashboard_api.py`** — gera o `dashboard_data.json` com métricas vivas reais (containers/RAM/tickets). 🟢
3. *(Condicional)* `system_monitor.sh`/`metrics_collector.sh` — coletam métricas, mas **não alertam** — só valem se ganharem um alerta de threshold simples.

## CANDIDATOS A APOSENTAR (decisão do Jordan — NÃO removidos)
- `1h-sentinela.sh` no cron (arquivo não existe → erro horário).
- Os 4 crons CTO de 0 bytes (proatividade, relatorio_semanal, auto_evolucao, turno).
- `orchestrator_unificado completo` (rate-limit, queima quota de API e falha).
- Os ~68 `.py` de framework sem gatilho (nivel3/modules/core/corretor).

## 🎯 RESPOSTA DIRETA: por que os agentes não pegaram a crise de 20-30/mai?
**Não foi "não rodavam" — eles rodavam.** Foi uma combinação:
1. **Monitoravam a coisa errada:** os alertas que disparavam eram de **negócio** (inadimplência), não de **infra** (RAM/load/zumbi). Não havia um check robusto de recurso que disparasse alerta.
2. **A "análise inteligente" depende de API e falha:** o `monitor_completo` chama IA/Telegram que **estoura rate-limit** e falha — então a parte "esperta" não conclui (provado nos logs de hoje e no archive de 241 bytes de 22/mai, truncado no auge).
3. **Auto-engano:** na crise, a RAM a 90% provavelmente **sufocou os próprios agentes** (log de 22/mai truncado) — o monitor foi vítima do que deveria detectar.
4. **Enxame congelado e inflado:** 84 scripts de 01-07/abr, ~68 sem gatilho, vários logando 0 bytes — muito "agente" no papel, pouquíssimo que realmente age. A quantidade deu falsa sensação de cobertura.
