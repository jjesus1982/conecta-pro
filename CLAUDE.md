# CLAUDE.md — Conecta PRO ERP
**Última atualização:** 2026-04-01
**Branch ativa:** feature/people-management-reorganization
**Responsável:** Jordan Jesus (jjesus@conectamais.pro)

## Visão Geral
ERP proprietário para empresas de segurança e tecnologia.
Compete com SAP/NetSuite/Salesforce com compliance brasileiro nativo.

**Empresa:** Conecta Mais — Segurança e Tecnologia
**CNPJ:** 35.710.481/0001-03 | Lucro Real desde 01/2026
**MRR:** R$ 272.086,96 | 52 funcionários | 13 clientes ativos

## Infraestrutura
| Item | Valor |
|------|-------|
| VPS | srv1134814.hstgr.cloud (82.25.75.74) — Hostinger KV4 |
| Backend | FastAPI + PostgreSQL + Redis · porta 8080 |
| Frontend | Next.js 16 + React 19 + TypeScript + Tailwind · porta 3001 |
| Path | /opt/conecta-pro/ |
| SSH | tmux sessions t1–t5 |

## Arquitetura
```
/opt/conecta-pro/
├── backend/          # FastAPI + SQLAlchemy
├── frontend/         # Next.js 16
├── agents/           # Sistema de agentes 24h
│   ├── core/         # BaseAgent + BaseOrchestrator
│   ├── modules/      # 13 orquestradores + 80 agentes
│   └── orchestrator_geral.py
├── skills/           # 10 skills de auditoria
├── reports/          # Relatórios dos ciclos
└── logs/             # Logs do sistema
```

## Sistema de Agentes 24h
- **80 agentes** em **13 orquestradores**
- Ciclo: a cada 30min via cron
- Score atual: **10.0/10** (2026-04-01)
- Alertas via Telegram: @conecta_pro_monitor_bot

## Módulos do ERP
| Módulo | Score | Status |
|--------|-------|--------|
| Departamento Pessoal | 10/10 | ✅ |
| Recursos Humanos | 10/10 | ✅ |
| Ponto Eletrônico | 10/10 | ✅ |
| Financeiro | 10/10 | ✅ |
| Fiscal & Contábil | 10/10 | ✅ |
| Operacional | 10/10 | ✅ |
| GED — Kits Documentais | 10/10 | ✅ |
| Inteligência | 10/10 | ✅ |
| Negócios (CRM + Marketing + Licitações) | 10/10 | ✅ |
| Saúde Ocupacional | 10/10 | ✅ |
| Portais | 10/10 | ✅ |
| Equipamentos | 10/10 | ✅ |
| Administrativo | 10/10 | ✅ |

## Auditorias de Qualidade (Skills 01-10)
| Skill | Score | Status |
|-------|-------|--------|
| 01 Debugger | corrigido | ✅ |
| 02 Code Review | 9.3/10 | ✅ |
| 03 API RESTful | 6.2/10 | 🔄 em correção |
| 04 Testes | 4.1/10 | 🔄 pendente |
| 05 Banco | 6.4/10 | 🔄 em correção |
| 06 Auth | 5.7/10 | 🔄 em correção |
| 07 Docker | 5.8/10 | 🔄 pendente |
| 08 CI/CD | 9.5/10 | ✅ |
| 09 UX | 6.9/10 | 🔄 em correção |
| 10 Docs | 5.2/10 | 🔄 este fix |

## Arsenal de QA — leia antes de dizer "pronto"
Uma página: `docs/ARSENAL_OPERACAO.md` (o que roda à 00:00, os três estados de um oráculo,
os caçadores e suas linhas canônicas, comandos). As lições por trás: `docs/ARSENAL_SKILLS.md`.
Instrumento do mapa VIVO · DESLIGADO · MORTO: `python3 backend/scripts/qa/checar_uso_real.py`.
Trava nova entra em `backend/scripts/qa/checar_regressao.py` ou é declarada órfã com dono.

## Comandos Essenciais
```bash
# Token de autenticação
TOKEN=$(curl -sf -X POST http://127.0.0.1:8080/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=jjesus@conectamais.pro&password=JsJ618908@#%" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Container backend
CONTAINER=$(docker ps --filter ancestor=conecta-pro-backend \
  --format '{{.Names}}' | head -1)

# Hot copy backend (não rebuild)
docker cp /opt/conecta-pro/backend/modules/ $CONTAINER:/app/modules/
docker exec $CONTAINER kill -HUP 1

# Deploy frontend CORRETO (preserva chunks antigos — evita ChunkLoadError)
./scripts/deploy/deploy_frontend.sh

# Build frontend manual (somente se deploy_frontend.sh não aplicável)
cd /opt/conecta-pro/frontend
NODE_OPTIONS=--max-old-space-size=4096 npm run build
pm2 restart all

# Rodar ciclo de agentes manualmente
cd /opt/conecta-pro
python3 agents/orchestrator_geral.py
```

## REGRA CRÍTICA — NUNCA CONSTRUIR A IMAGEM DO BACKEND FORA DO LOCK
### Origem: 2026-08-10 — drift de workers medido duas vezes no mesmo dia

**NUNCA** rodar `docker compose build backend` (nem `up -d --build backend`) direto.
**SEMPRE** um destes, que seguram o lock `/tmp/conecta_deploy.lock`:

```bash
./scripts/deploy_backend_bluegreen.sh          # deploy completo (já builda dentro do lock)
./scripts/build_backend.sh                     # só a imagem, esperando o lock
./scripts/com_lock.sh <qualquer comando>       # qualquer operação que mexa na imagem
```

### Por que essa regra existe

`conecta-pro-backend:latest` é a **mesma imagem dos 8 workers de celery**. Um build avulso
troca essa tag. Se isso acontece durante o passo 7 do deploy — que recria os workers **um a
um**, levando ~12 min — a tag muda no meio do laço: os workers já recriados ficam com a
imagem anterior (que vira órfã) e o resto pega a nova.

Medido em 10/08/2026, duas vezes: **2 e depois 4 workers** rodando código velho, **todos
reportando `healthy`**. `docker ps` mostrava oito containers saudáveis.

O lock **serializa deploys**, não builds avulsos — era exatamente esse o buraco. E "healthy"
nunca denunciou código velho: foi assim que o `celery-beat` rodou **46 dias** em loop de
crash sem ninguém ver.

O deploy agora roda `./scripts/checar_drift_workers.sh` no fim e **falha** se sobrar drift.
Se você viu esse erro, o culpado provável é um build fora do lock rodando em paralelo.

## REGRA CRÍTICA — DEPLOY FRONTEND SEM ChunkLoadError
### Origem: CPRO12 (2026-05-05) — DevOps fix chunks

**NUNCA** fazer deploy frontend com `npm run build` + `pm2 restart all` direto.
**SEMPRE** usar `./scripts/deploy/deploy_frontend.sh`.

### Por que essa regra existe

Next.js gera chunks com hash de conteúdo (ex: `ee79b3aa27b940fc.js`).
Browsers cacheiam com `Cache-Control: immutable, 1y` — o browser continua pedindo o chunk antigo após o deploy.
O nginx faz `proxy_pass http://frontend` (container) para `/_next/static/` — **não** serve do host.
Se o container for reiniciado sem preservar os chunks antigos, o browser pede o hash antigo → nginx não encontra no container → 404 → **ChunkLoadError**.

### Como o nginx funciona aqui (importante)

```nginx
# nginx.conf linha 169-178:
location /_next/static/ {
    proxy_pass http://frontend;          # ← container, NÃO host filesystem
    proxy_cache static_cache;
    proxy_cache_valid 200 365d;
    proxy_cache_use_stale error timeout updating;
}
```

Os chunks ficam **no container**. O host guarda o `.next/` como fonte de build mas o nginx não lê de lá.

### Fluxo correto de deploy frontend

```bash
# Script completo (preferencial):
./scripts/deploy/deploy_frontend.sh

# O script faz:
# 1. Arquiva chunks antigos do container → /opt/conecta-pro/.chunk_archive/TIMESTAMP/
# 2. npm run build no host
# 3. docker cp .next/{static,standalone,server,BUILD_ID} → container
# 4. Reinjecta chunks antigos no container (preservação anti-ChunkLoadError)
# 5. docker restart + pm2 restart all
# 6. Valida HTTP 200 + BUILD_ID host==container
```

### Dry-run (sem executar)

```bash
./scripts/deploy/deploy_frontend.sh --dry-run
```

---

## REGRA CRÍTICA — HOT-COPY PARA TODOS OS CONTAINERS CELERY
### Origem: CPRO12 (2026-05-04) — §66 (inventário módulos), §69 (fix sync session), T4 CPRO12 (pyc stale)

**NUNCA copie um módulo apenas para o container `backend`.**
**TODO hot-copy deve incluir TODOS os containers Celery relevantes.**

### Por que esta regra existe

Em 2026-03-20, o `celery-beat` parou de funcionar. A causa foi que `punch_controller.py`
foi corrigido no disco mas nunca copiado para os containers `celery-beat` e `celery-batch`.
O beat ficou **46 dias em loop de crash** por essa omissão.
Adicionalmente, descobriu-se que limpar o `__pycache__` é obrigatório antes do `docker cp` —
sem isso, o container usa bytecode antigo mesmo com o arquivo novo copiado (pyc stale).

### Lista completa de containers (verificar quais são relevantes por módulo)

```
conecta-pro-backend                    ← sempre incluir
conecta-pro-celery-beat                ← incluir se módulo tem tasks agendadas (beat schedule)
conecta-pro-celery-batch               ← incluir se módulo tem tasks batch/import
conecta-pro-celery-operacional         ← incluir se módulo tem tasks operacionais
conecta-pro-celery-integrations        ← incluir se módulo tem tasks de integração externa
conecta-pro-celery-priority            ← incluir se módulo tem tasks eSocial/FGTS
conecta-pro-celery-nfse                ← incluir se módulo tem tasks NFS-e
conecta-pro-celery-sefaz               ← incluir se módulo tem tasks SEFAZ/NF-e
```

> ⚠️ Alguns containers têm prefixo de hash no nome (ex: `297439d0453a_conecta-pro-celery-operacional`).
> Sempre resolver com: `docker ps --format "{{.Names}}" | grep "celery-operacional"`

### Fluxo obrigatório de hot-copy

```bash
# OPÇÃO 1 — Script padrão (preferencial):
./scripts/deploy/sync_celery_workers.sh nome_do_modulo

# OPÇÃO 2 — Manual (quando precisar controlar quais containers):
MODULO=nome_do_modulo
for CONTAINER in conecta-pro-backend conecta-pro-celery-beat conecta-pro-celery-batch \
  conecta-pro-celery-operacional conecta-pro-celery-integrations \
  conecta-pro-celery-priority conecta-pro-celery-nfse conecta-pro-celery-sefaz; do
  # 1. Limpar pyc ANTES do cp (obrigatório — evita pyc stale)
  docker exec $CONTAINER find /app/modules/$MODULO/__pycache__ -name "*.pyc" -delete 2>/dev/null || true
  # 2. Copiar módulo
  docker cp backend/modules/$MODULO/ $CONTAINER:/app/modules/$MODULO/ && echo "OK: $CONTAINER"
done
# 3. Recarregar apenas o backend (workers Celery recarregam automaticamente)
docker exec conecta-pro-backend kill -HUP 1
```

### Por que limpar pyc antes do cp (pyc stale — T4 CPRO12)

O Python carrega bytecode compilado (`.pyc`) em preferência ao `.py` se o pyc existir.
Sem limpar o cache, o container continua usando o bytecode antigo mesmo após o `docker cp`.
**Sintoma:** fix commitado e copiado, mas o erro persiste — worker lê `.pyc` antigo.

### NUNCA usar docker restart

```bash
# ERRADO — derruba e reinicia o container, perde contexto:
docker restart conecta-pro-backend

# CORRETO — hot-reload sem derrubar:
docker exec conecta-pro-backend kill -HUP 1

# Para workers Celery sem kill binary:
docker exec $CELERY_CONTAINER python3 -c "import os, signal; os.kill(1, signal.SIGHUP)"
```

### celery_app.py também precisa de sync

O `celery_app.py` controla quais módulos de tasks os workers carregam (`include=[]`).
Se um módulo novo foi adicionado ao `include`, o `celery_app.py` deve ser copiado
para TODOS os workers — caso contrário as tasks não são descobertas mesmo com o módulo presente.

```bash
for CONTAINER in conecta-pro-celery-beat conecta-pro-celery-batch \
  conecta-pro-celery-operacional conecta-pro-celery-integrations \
  conecta-pro-celery-priority conecta-pro-celery-nfse conecta-pro-celery-sefaz; do
  docker cp backend/celery_app.py $CONTAINER:/app/celery_app.py && echo "OK: $CONTAINER"
done
```

---

## Zonas Proibidas
| Path | Motivo |
|------|--------|
| `alembic/versions/` | Migrations — nunca editar manualmente |
| `main_production.py` | Entry point produção — nunca modificar |
| `docker-compose*.yml` | Orquestração — nunca modificar |
| `.env*` | Variáveis de ambiente — nunca commitar |
| `credentials/` | Chaves e certificados — nunca tocar |

## Regras de Trabalho
- Sempre usar `127.0.0.1`, nunca `localhost`
- Terminais via `tmux attach -t tN` (t1–t5)
- Frontend builds: serializados, nunca simultâneos
- Backend changes: hot copy via `docker cp`, nunca rebuild completo
- Commit após cada correção com mensagem descritiva
- Rate limit de auth: 5 req/min — usar token compartilhado nos agentes
- Pré-commit hooks ativos: ruff, detect-secrets, bandit

---

## Regras de Governança para Sessões Autônomas

> **Contexto:** Em 2026-04-05 ocorreram 3 reverts automáticos (65c3ce14, f87e9c5b,
> f866cc6a) causados por sessões tmux paralelas revertendo commits de outros módulos.
> Estas regras são obrigatórias para todas as sessões Claude Code.

### Escopo de módulo obrigatório
Cada sessão Claude DEVE declarar no início qual módulo está editando.
Uma sessão que trabalha em `ged/` NÃO deve tocar em arquivos de `rh/`,
`operacional/`, `financeiro/` ou qualquer outro módulo não declarado.

### Proibição absoluta de git revert
Nenhuma sessão Claude pode executar `git revert` sem confirmação
explícita de Jordan Jesus no chat.
Antes de reverter qualquer coisa, a sessão DEVE escrever:
```
AGUARDANDO APROVAÇÃO: pretendo executar git revert <hash> porque <motivo>.
Confirma? (sim/não)
```
E aguardar resposta antes de prosseguir.

### Proibição de git push para main/develop
Sessões autônomas não podem fazer push direto para main ou develop.
Todo commit deve ficar na branch de trabalho declarada no início da sessão.

### Verificação de conflito antes de commit
Antes de qualquer `git commit`, executar:
```bash
git diff --name-only HEAD
```
e verificar se algum arquivo modificado pertence a módulo diferente do declarado.
Se sim, remover esse arquivo do stage e registrar no relatório final.

### Identificação da sessão
Todo commit de sessão autônoma DEVE incluir no final da mensagem:
```
[session: tmux-<id>] [module: <nome>]
```
Exemplo: `fix(ged): correção E2E [session: tmux-t1] [module: ged]`

### Como desfazer um commit com segurança (quando autorizado por Jordan)

**NUNCA usar:**
```bash
git revert <hash-de-outro-módulo>
git reset --hard
```

**Usar apenas (quando Jordan autorizar explicitamente):**
```bash
# Desfazer o último commit mantendo as mudanças em stage:
git reset --soft HEAD~1

# Ou, se Jordan autorizou reverter um commit específico:
git revert <hash> --no-edit
# Seguido de push para a branch de trabalho — NUNCA para main/develop
```

### Resolução de conflito entre sessões
Se uma sessão detectar que seu commit foi revertido por outra sessão:
1. **NÃO re-aplicar automaticamente**
2. Notificar Jordan com:
   ```
   ATENÇÃO: commit <hash> foi revertido por <hash-revert>.
   Aguardo sua instrução para re-aplicar ou descartar.
   ```
3. Aguardar confirmação antes de qualquer ação

---

## Mecanismo Anti-Revert — commit-msg hook

**Instalado em:** 2026-04-07 (Operação Conecta-Drive T7)
**Arquivo:** `.git/hooks/commit-msg`

O hook bloqueia automaticamente qualquer commit cuja mensagem comece com "revert" (case-insensitive).
Se uma sessão tentar fazer `git revert` sem autorização, o commit será bloqueado com:

```
╔══════════════════════════════════════════════╗
║  CONECTA PRO — REVERT BLOQUEADO              ║
║  Reverts requerem autorização de Jordan Jesus ║
║  Confirme no chat antes de executar.         ║
╚══════════════════════════════════════════════╝
```

Para restaurar o hook se for deletado acidentalmente:

```bash
cat > /opt/conecta-pro/.git/hooks/commit-msg << 'HOOK'
#!/bin/bash
COMMIT_MSG_FILE="$1"
if [ -f "$COMMIT_MSG_FILE" ]; then
    MSG=$(cat "$COMMIT_MSG_FILE" | head -1 | tr '[:upper:]' '[:lower:]')
    if echo "$MSG" | grep -q "^revert"; then
        echo ""; echo "╔══════════════════════════════════════════════╗"
        echo "║  CONECTA PRO — REVERT BLOQUEADO              ║"
        echo "║  Reverts requerem autorização de Jordan Jesus ║"
        echo "╚══════════════════════════════════════════════╝"; echo ""
        exit 1
    fi
fi
exit 0
HOOK
chmod +x /opt/conecta-pro/.git/hooks/commit-msg
```

## PROIBIDO ABSOLUTO

As seguintes operações são PROIBIDAS em todas as sessões autônomas:

| Comando | Motivo |
|---------|--------|
| `git revert <hash>` | Reverte commits de outros módulos sem autorização |
| `git reset --hard` | Destrói trabalho de outras sessões |
| `git push --force` | Sobrescreve histórico remoto |
| Editar `alembic/versions/` | Migrations — risco de corrupção do banco |
| Editar `docker-compose*.yml` | Orquestração — pode derrubar produção |
| Editar `.env*` | Variáveis de ambiente — nunca commitar |
| Editar `credentials/` | Chaves e certificados — nunca tocar |
| Editar `main_production.py` | Entry point de produção — nunca modificar |
