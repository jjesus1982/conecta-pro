# Inventário dos arquivos de instrução (CLAUDE.md / AGENTS.md) — Conecta PRO

**Data:** 2026-06-18 · **Tipo:** read-only (find + cat). **Objetivo:** existe CLAUDE.md? onde? o que diz? — consolidado num relatório.

---

## RESPOSTA DIRETA
**Sim, existe** — e são **4 arquivos de instrução** (fora 1 em node_modules, irrelevante):

| Arquivo | Linhas | Última atualização | Foco |
|---|---:|---|---|
| `/opt/conecta-pro/CLAUDE.md` | 378 | **2026-04-01** | Regras gerais, infra, **zonas proibidas**, governança, deploy |
| `/opt/conecta-pro/AGENTS.md` | 619 | (Kimi CLI v1.9.0) | Estrutura de 33 módulos backend / 21 frontend |
| `/opt/conecta-pro/backend/CLAUDE.md` | 271 | 2026-01-27 | Arquitetura do backend (core, models, módulos) |
| `/opt/conecta-pro/frontend/CLAUDE.md` | 531 | 2026-02-02 | Frontend Next.js, hooks Orval, cobertura |
| `frontend/node_modules/recharts/AGENTS.md` | — | (de lib) | Ignorar (terceiros) |

---

## ⚠️ ACHADO CRÍTICO PARA NOSSO TRABALHO — Zonas Proibidas

O `CLAUDE.md` raiz define **"Zonas Proibidas"** e **"PROIBIDO ABSOLUTO"**:

| Path / comando | Motivo (do arquivo) |
|---|---|
| **`alembic/versions/`** | "Migrations — nunca editar manualmente" / "risco de corrupção do banco" |
| `main_production.py` | Entry point produção — nunca modificar |
| `docker-compose*.yml` | Orquestração — nunca modificar |
| `.env*` | Variáveis — nunca commitar |
| `credentials/` | Chaves/certificados — nunca tocar |
| `git revert` / `git reset --hard` / `git push --force` | Destrói trabalho de outras sessões |

### Honestidade — tensão com o que fiz nesta sessão
Nas rodadas de migração (financial/hr/DP) eu **criei arquivos em `alembic/versions/`** (`findp_b1b2_20260601`, `dp_suspeitos_20260618`, `dp_ferias_20260618`) e avancei o `alembic_version` por UPDATE atômico — o que cai na zona proibida acima. **Por que aconteceu:** você autorizou explicitamente, por missão ("você está AUTORIZADO a criar migrations nesta missão", "pode aplicar em produção", "confio em você"). Ou seja, houve **override explícito por sessão**, mas **eu não conhecia este CLAUDE.md** quando comecei (ele não foi carregado no meu contexto). Registro isso para você decidir se mantemos o approach ou ajustamos a forma de versionar migrations daqui pra frente.

### Info desatualizada no CLAUDE.md (2026-04-01)
O arquivo lista **todos os módulos como "10/10 ✅"**, incluindo **"Departamento Pessoal 10/10"**. Isso **conflita com a realidade** que medimos: o `hr` estava com **38% dos models carregáveis** (10 de 16 falhando por schema drift) no início da sessão — só agora chegou a 100%. Os "10/10" são **scores aspiracionais do sistema de agentes**, não o estado real de schema. Vale atualizar o CLAUDE.md.

---

## Conteúdo-chave do `/opt/conecta-pro/CLAUDE.md`

### Identidade
- ERP proprietário (segurança/vigilância). Empresa: Conecta Mais. CNPJ 35.710.481/0001-03, Lucro Real.
- **MRR R$ 272.086,96 · 52 funcionários · 13 clientes ativos.**
- VPS `82.25.75.74` (Hostinger KV4). Backend FastAPI :8080 · Frontend Next.js :3001.

### Regras operacionais (relevantes para o PRÓXIMO passo — fix de código)
- **Backend baked no Docker:** mudança via `docker cp` (hot-copy), **nunca rebuild**, depois `docker exec ... kill -HUP 1` (não `docker restart`).
- **HOT-COPY PARA TODOS OS CELERY:** copiar módulo só para o `backend` causou 46 dias de crash do beat. Copiar para os 7 workers Celery relevantes + **limpar `__pycache__` antes** (pyc stale). Script: `./scripts/deploy/sync_celery_workers.sh <modulo>`.
- **Deploy frontend:** SEMPRE `./scripts/deploy/deploy_frontend.sh` (preserva chunks → evita ChunkLoadError). Nunca `npm run build` + `pm2 restart` direto.
- Sempre `127.0.0.1`, nunca `localhost`. Rate limit auth 5/min.
- **Token de auth (dev):** login em `/api/v1/auth/login` com `jjesus@conectamais.pro` (form-urlencoded) — credencial está no CLAUDE.md.

### Governança de sessões autônomas
- **Escopo de módulo obrigatório:** declarar qual módulo edita; não tocar em outros. (Houve 3 reverts cruzados em 2026-04-05.)
- **`git revert` proibido sem aprovação explícita** sua no chat (hook `commit-msg` bloqueia mensagens começando com "revert").
- **Sem push para main/develop**; commit fica na branch de trabalho.
- Commits devem ter sufixo `[session: tmux-<id>] [module: <nome>]`.

## `AGENTS.md` (raiz) — resumo
- Config para **Kimi CLI v1.9.0** (outra ferramenta, não Claude). ERP v2.0.0, 33 módulos backend / 21 frontend. Mapa de diretórios dos módulos. É um guia paralelo ao CLAUDE.md, voltado a outro agente.

## `backend/CLAUDE.md` — resumo
- Arquitetura do backend: `main_production.py` (prod) / `main.py` (dev); `core/` (auth, cache, database session async+sync, models base com TimestampMixin/SoftDeleteMixin), 32 módulos. Útil como mapa do código.

## `frontend/CLAUDE.md` — resumo
- Next.js 16 + React 19 + Orval (gera hooks React Query do OpenAPI). Cobertura ~95% (105/108 páginas com API real). Build passa. Arquitetura de hooks em camadas.

---

## RECOMENDAÇÃO ANTES DE SEGUIR PARA O FIX DE CÓDIGO (FK funcionarios→employees)
O próximo passo (corrigir os 5 models) **vai editar código de `hr/` + hot-copy**. Para respeitar o CLAUDE.md:
1. **Declarar escopo:** módulo `hr` (DP) apenas.
2. **Hot-copy para os 7 Celery + backend**, limpando `__pycache__` antes (`sync_celery_workers.sh hr`), `kill -HUP 1` — **não** rebuild/restart.
3. **Commit na branch de trabalho** com sufixo de sessão; **sem** revert/push para main.
4. **Não tocar** `alembic/versions/` sem seu OK explícito — ou decidir juntos como versionar a correção.
5. Editar model de `hr` **não** é zona proibida (só `main_production.py`/`alembic`/`.env`/`credentials`/`docker-compose` são) → o fix da FK é permitido.

**Pergunta para você:** mantenho o padrão de criar migration alembic para as mudanças (como fiz), ou você prefere outro mecanismo de versionamento, dado que o CLAUDE.md marca `alembic/versions/` como zona proibida?
