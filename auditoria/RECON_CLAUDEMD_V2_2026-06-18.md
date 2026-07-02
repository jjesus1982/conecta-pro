# RECON para reescrever o CLAUDE.md (v2) — estado REAL da operação

**Data:** 2026-06-18 · **Token:** STEP-0-CLAUDEMD-V2-RECON · **Tipo:** READ-ONLY (zero escrita; nada editado).
**Objetivo:** levantar fatos para você redigir o CLAUDE.md v2. O atual (2026-04-01) contradiz a operação em vários pontos — marcados com ⚠️.

---

## STEP 1 — REBUILD vs HOT-COPY
- `scripts/deploy/` tem **exatamente 2 scripts**: `deploy_frontend.sh` (6.3 KB) e `sync_celery_workers.sh` (1.2 KB). Ambos **batem com o que o CLAUDE.md descreve**.
  - `deploy_frontend.sh`: preserva chunks antigos no container (anti-ChunkLoadError), valida BUILD_ID host==container, `--dry-run`. ✅
  - `sync_celery_workers.sh <modulo>`: limpa `__pycache__` → `docker cp` para **backend + 7 workers Celery** + `celery_app.py` + `kill -HUP 1`. ✅
- ⚠️ **NÃO existe script de rebuild** (backend nem frontend nem imagem). **Rebuild de imagem é 100% manual** — registrar no v2 o procedimento: âncora (tag da imagem atual) + dump do banco + build + container efêmero p/ teste + swap 2A/2B.

## STEP 2 — SISTEMA DE AGENTES 24h → **PARCIALMENTE VIVO** (não "10.0/10, ciclo 30min")
⚠️ O CLAUDE.md diz "80 agentes, 13 orquestradores, ciclo 30min, score 10.0/10". **Realidade:**

**🟢 VIVO (roda no cron + produz output):** — `reports/monitor/` e `monitor_state.json` atualizados **hoje 22:28**.
| Cron | Frequência |
|---|---|
| `orchestrator_unificado.py rapido` | */5 min |
| `orchestrator_unificado.py escaladas` | */5 min |
| `orchestrator_unificado.py heartbeat` | 6h |
| `dashboard_api.py` | */2 min |
| `context_builder.py` | */2 min |
| `cto/predicao/preditor_principal.py` | */5 min |
| `cto/relatorio_matinal.py` | diário 10h |
| `cto/aprendizado` + `reindexar.sh` | 6h / horário |

**🔴 QUARENTENADO** (comentado `# [LIMPEZA 20260531]`): o **ciclo `completo` */30** (o "ciclo 30min" do CLAUDE.md), `proatividade`, `auto_evolucao` (mensal), `relatorio_semanal`, `turno`, `1h-sentinela`.

**⚠️ CRON QUEBRADO (silencioso):** o cron chama `rotinas/scripts/{6h-testes,12h-qualidade,18h-analise,24h-briefing}.sh`, mas **esses arquivos NÃO existem** — `rotinas/scripts/` só tem `onvio-auth-refresh.sh` e `onvio-sync-mensal.sh`. → 4 jobs falham toda execução. (O "5 scripts sentinela/CEO" do plano antigo: 4 sumiram, 1 está comentado.)

**Resumo honesto:** o que sobrevive é o **monitor leve + Telegram + predição + CTO matinal**. O motor pesado de auto-evolução/proatividade/briefing-CEO está morto/quarentenado. Não é "score 10/10 ciclo 30min".

## STEP 3 — ESTADO REAL DOS MÓDULOS (medido, não aspiracional)
| Módulo | Models carregam | % |
|---|---|---|
| **crm** | 18 OK / 0 FAIL | **100%** 🟢 |
| **hr (DP)** | 16 OK / 0 FAIL | **100%** 🟢 (corrigido nesta sessão) |
| **integrations (whatsapp)** | 21 OK / **13 FAIL** | **62%** 🟡 (drift ainda alto) |

⚠️ O CLAUDE.md marca **todos** os módulos "10/10 ✅", incluindo DP. Era falso (DP estava em 38% no início da sessão). Os "10/10" são scores aspiracionais do sistema de agentes, **não** estado de schema.

### git — trabalho recente que o CLAUDE.md NÃO conhece
- **Branch ativa real: `fix/crm-qa-aprovado-20260614`** ⚠️ (CLAUDE.md diz `feature/people-management-reorganization`).
- Últimos 20 commits = duas frentes grandes:
  1. **Agente WhatsApp "José Luís"** — consultor de vendas Nível 3 + suporte técnico N1 (segurança eletrônica): scoring, cross-sell, agenda, memória, dashboard, A/B, follow-up multi-toque, qualificação de lead, briefing→Telegram, auditorias sucessivas (16→14→9→8 bugs).
  2. **Módulo Campo** — tela de Ordens de Serviço (lista/filtros/ações) + fluxo **OS WhatsApp→Campo→tela** + atualizações proativas de status no WhatsApp; 8 bugs corrigidos.
  - Também: fixes de CRM front (Tailwind v4).
- → O v2 precisa registrar: **agente José Luís (WhatsApp vendas+suporte)** e **OS no Campo** como features reais ativas.

## STEP 4 — DURABILIDADE (a lição que matou o agente)
- **Compose canônico do runtime:** `docker-compose.yml` + `docker-compose.celery.yml` (label `com.docker.compose.project=conecta-pro`).
- ✅ Backend tem **`env_file: .env`** no `docker-compose.yml` (linha 63; comentário "injeta o .env inteiro — AGENT_ENABLED/CHATWOOT_*/WHATSAPP_WEBHOOK_SECRET"). 17 vars-chave confirmadas no runtime.
- ✅ **`chatwoot-fazerai-net` declarada** no `docker-compose.yml` (linhas 169-172 no backend + 395 na definição). Runtime do backend tem `chatwoot-fazerai-net` + `conecta-pro_conecta-pro-network`. → recreate pelo compose canônico **NÃO derruba** essas correções.
- ⚠️ **Risco de canonicidade:** **4 composes** definem `conecta-pro-backend` (`docker-compose.yml`, `.prod.yml`, `.staging.yml`, `.celery.yml`). Só o `docker-compose.yml` tem `chatwoot-fazerai-net`. **`.prod.yml` e `.staging.yml` NÃO têm** → se alguém recriar o backend por `.prod.yml`, **perde a rede do chatwoot** (e o backend perde acesso ao chatwoot-fazerai:3000). Registrar no v2: **usar sempre `docker-compose.yml` (+ `.celery.yml`)** como par canônico; `.prod.yml` está defasado.

---

## STEP 5 — RESUMO PARA O v2
1. **Deploy:** `deploy_frontend.sh` + `sync_celery_workers.sh` existem e valem. **Rebuild = manual** (sem script; documentar o procedimento âncora+dump+efêmero+swap).
2. **Agentes:** **parcialmente vivo** — monitor leve + Telegram + predição + CTO matinal rodam (output hoje); ciclo `completo`/proatividade/auto_evolucao/semanal/turno **quarentenados**; rotinas CEO (testes/qualidade/analise/briefing) **com scripts faltando = cron quebrado**. Corrigir a narrativa "10/10 ciclo 30min".
3. **Crons:** 33 jobs ativos (segurança/rkhunter/clamav, backup 03h + retention, metrics */5, monitor rapido/escaladas */5, dashboard/context */2, heartbeat 6h, predicao */5, relatorio_matinal 10h, briefing_jordan 07h30, alerta_inadimplencia 08h, kits mensais, onvio auth/sync, gerar_kits, @reboot monitor_startup).
4. **Módulos:** crm **100%**, hr **100%**, integrations/whatsapp **62%** (13 models ainda em drift — próximo alvo de drift-finder).
5. **Commits recentes:** agente WhatsApp "José Luís" (vendas+suporte N1) + OS no Campo — **ausentes do CLAUDE.md atual**.
6. **Durabilidade:** `env_file` + `chatwoot-fazerai-net` **presentes no compose canônico** (`docker-compose.yml`). Único risco runtime: usar `.prod.yml`/`.staging.yml` (sem a rede) num recreate → documentar par canônico.
7. **Branch real:** `fix/crm-qa-aprovado-20260614` (atualizar no v2).

> Nada foi escrito. Fatos levantados para você redigir o CLAUDE.md v2.
