# Investigação READ-ONLY — Dashboard de Agentes / Auto-Remediação (OpenClaw)

**Data:** 2026-05-31 · **Tipo:** 100% read-only (nada alterado/reiniciado/removido).
**Pergunta do Jordan:** o sistema AINDA age sozinho (auto-remedia) ou só observa/mostra histórico?

---

## VEREDITO: **(c) PARCIALMENTE MORTO — roda e observa, mas NÃO age efetivamente (degradado)**

Não está totalmente morto (o motor executa a cada 15 min; o dashboard atualiza métricas vivas). Mas não está vivo de verdade: **executa 0 ações de remediação, não acha sua base de conhecimento, e a última prevenção real foi 21/05.**

---

## 1. Fonte de dados de cada bloco do dashboard

`https://erp.conectamais.pro/agents/dashboard` → nginx serve um **HTML estático** (`/opt/conecta-pro/agents/dashboard.html`, de **01/abr**) que faz `fetch('/agents/dashboard/dashboard_data.json')` em loop (`setInterval`). O JSON é **regenerado** por `agents/dashboard_api.py` (snapshot: lê tabelas + sistema).

| Bloco do dashboard | Fonte | Estado |
|---|---|---|
| Métricas (RAM, swap, containers, score agentes, tickets) | `dashboard_api.py` lê o sistema AO VIVO | 🟢 **VIVO/REAL** (atual) |
| "Intervenções OPENCLAW" | tabela `openclaw_interventions` | 🟡 real mas **congelado** (última 29/05) |
| "Padrões Aprendidos" | tabela `openclaw_patterns` | 🟡 observado (last_seen hoje) mas **0 prevenções desde 21/05** |
| Knowledge base | `agent_knowledge_base.json` | 🔴 motor não acha (mismatch host/container) |

## 2. O motor ainda roda? — SIM, mas não age

- **Crons ativos** (em `/opt/conecta-pro/agents/`):
  - `run_preventive_action.sh` (cron `*/15`) → `docker exec ... python3 preventive_action.py` — **roda a cada 15 min** (53 execuções só hoje).
  - `run_pattern_learner.sh` (cron `0 3`) → atualiza `openclaw_patterns.last_seen` (rodou **hoje 03:00**).
  - `orchestrator_unificado.py` (rapido `*/5`, completo `*/30`) — regenera o `dashboard_data.json`.
- **MAS cada execução do motor:**
  - `0 acoes preventivas do banco executadas` — **53 runs hoje, todos com 0 ações**.
  - `AVISO: Knowledge base nao encontrada` — **52×** hoje.
  - `Erro ao atualizar state: No such file or directory: '/opt/conecta-pro/AGENT_STATE.json'` — toda run.
  - `PROBLEMA [CRITICAL]: redis` e `PROBLEMA [CRITICAL]: nginx` — **FALSOS POSITIVOS** (redis Up 31h healthy, nginx active). O health check do motor está **quebrado**.

**Causa da degradação (read-only):** o `preventive_action.py` roda **dentro do container** (`docker exec`), mas seus arquivos de estado/conhecimento (`AGENT_STATE.json`, `agent_knowledge_base.json`) estão no **host** (`/opt/conecta-pro/`) — que não existe dentro do container. Logo, **não lê o conhecimento nem persiste estado** → o loop de aprendizado/decisão está partido.

## 3. Quando parou de agir e por quê

- **Última PREVENÇÃO real** (`openclaw_patterns.last_prevented`): **21/05/2026 16:31**.
- Intervenções reais registradas: `HighMemoryUsage` e `PostgresConnectionLost` em **20-21/05** (durante a crise de RAM/dockerd). A de 29/05 (`PREVENTIVE_peak_celery_check`) é um **check agendado de horário de pico**, não remediação de problema.
- **Por quê:** as remediações reais aconteceram **durante a crise** (20-21/05). Depois que a crise foi resolvida e o sistema ficou saudável, **não há incidentes reais para remediar** → parte do "0 ações" é "nada a fazer". MAS o motor também **degradou** (sem knowledge base no container, health check quebrado) — então, mesmo se um incidente real ocorresse, a confiabilidade da ação é duvidosa.

## 4. Estado das 3 tabelas openclaw_*

| Tabela | Linhas | Último registro |
|---|---|---|
| `openclaw_interventions` | 60 | created/resolved **29/05 21:30** |
| `openclaw_patterns` | 18 | last_seen **hoje 03:00** · last_prevented **21/05** |
| `openclaw_knowledge_base` | 5 | last_incident **23/03** |

Os `openclaw_patterns` têm **ruído**: nomes duplicados (3× `PM2ExcessiveRestarts`, vários `RedisDown`/`HighMemoryUsage` repetidos, combos estranhos como `HighMemoryUsage+RedisDown`) — o pattern_learner gera padrões de baixa qualidade.

## 5. Resíduo morto vs monitoramento vivo

- 🟢 **VIVO e útil:** métricas de sistema/containers/RAM/tickets no `dashboard_data.json` (geradas ao vivo); Grafana/Prometheus (stack de observabilidade separado).
- 🟡 **REAL mas congelado:** histórico de intervenções/padrões OpenClaw (parado em 21-29/05).
- 🔴 **Degradado/quebrado:** o motor de remediação (roda mas 0 ações, sem knowledge base, health check com falso positivo).
- ⚠️ **Correção de premissa:** **PM2 NÃO é resíduo morto** — há **4 processos PM2 online** (o frontend de produção na porta 3000 + bots rodam via PM2). Então `PM2ExcessiveRestarts` monitora algo real (embora nunca tenha disparado prevenção). Não há resíduo de `conecta-plus` nos padrões.

---

## 6. Três opções para o Jordan decidir DEPOIS (nenhuma aplicada agora)

### Opção 1 — REATIVAR o motor (fazer agir de novo)
Corrigir o mismatch host/container (montar `/opt/conecta-pro/agents` + os JSONs de estado no container, OU rodar `preventive_action.py` no host em vez de `docker exec`), consertar o health check (falsos positivos redis/nginx), restaurar a knowledge base.
- **Prós:** auto-remediação real volta a funcionar (memória/disco/postgres em picos).
- **Contras:** esforço + **risco**: um motor que faz `docker exec`/restart automático, com health check **já comprovadamente com falso positivo**, pode tomar **ação errada** (ex.: "reiniciar" redis/nginx que estão saudáveis). Reativar exige primeiro consertar a detecção, senão é perigoso.

### Opção 2 — REMOVER de vez o OpenClaw, manter só o dashboard de métricas vivas
Aposentar os crons (`run_preventive_action`, `run_pattern_learner`), dropar as 3 tabelas `openclaw_*` (Nível 2 do B2, com backup), e manter o `dashboard_data.json` só com as métricas vivas (sistema/containers/tickets) + Grafana.
- **Prós:** elimina o motor meio-morto e o ruído; o que sobra é observabilidade real e confiável; fecha o ciclo do OpenClaw (já parcialmente removido).
- **Contras:** perde o conceito de auto-remediação; o bloco "Intervenções/Padrões" do dashboard some (ou vira histórico estático).

### Opção 3 — DEIXAR como está (observabilidade passiva)
Não mexer. O motor segue rodando (sem agir), o dashboard segue mostrando métricas vivas + histórico congelado.
- **Prós:** zero esforço/risco; o dashboard de métricas continua útil.
- **Contras:** **enganoso** (parece que age, mas não age desde 21/05); gasta ciclos de cron a cada 15 min gerando erro (`knowledge base nao encontrada`, falsos CRITICAL) no log; dívida técnica que confunde quem olha o dashboard.

---

### Nota honesta
Nada foi alterado. O motor **está vivo no sentido de "executa"**, mas **morto no sentido de "remedia"** — e o que mais o trava é o **mismatch host/container** (não acha o conhecimento) + **health check com falso positivo**. A reativação (Opção 1) **só é segura depois de consertar a detecção**, senão ele agiria sobre problemas inexistentes.
