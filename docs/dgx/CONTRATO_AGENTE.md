# Contrato do agente de frente — paridade DGX (24/09/2026)

Você é UMA frente de um plano maior (`docs/dgx/PLANO_IMPLEMENTACAO.md`). Trabalha numa worktree
própria, na sua branch. O orquestrador (a sessão principal) faz merge, bake e deploy — **você não**.

## Leia antes de escrever (nesta ordem, é rápido)
1. `docs/dgx/PLANO_IMPLEMENTACAO.md` — o diagnóstico e as regras.
2. A seção do DGX que o seu brief aponta (`docs/dgx/01..09`).
3. O exemplar de frente: `backend/modules/operacional/controllers/redesign_builders/_frente_08.py`
   (como uma frente se pluga) e `auditoria/frentes/FRENTE_08_mapa_ferias.md` (o relatório que
   se espera de você, especialmente §5 "o que NÃO foi feito").
4. `backend/modules/operacional/controllers/redesign_builders/_fin_pagar.py` — DSL de tela:
   `_helpers(db)` → `mine, safe, tbl`; forms `{"type":"form","submit":{endpoint, okMsg, gated?,
   confirm?, showResult?},"fields":[{key,label,type:text|select|number|date|textarea,options,span,ph}]}`;
   linhas de tabela com `{"cells": [...], "actions": [...]}` para editar/excluir.
5. `grep -rln <conceito> backend/modules frontend/src/app` — **cave antes de construir**. Esta
   casa tem muito código bom e mal divulgado. Reusar > estender > criar.

## Forma da entrega
- Código em `backend/modules/operacional/controllers/redesign_builders/_dgx_fN_<nome>.py`
  (prefixo `_` = o discovery pula; expõe `async def telas(db, out)` e `router`), mais serviço em
  `backend/modules/<modulo>/services/<nome>.py` quando houver regra.
- Plug no builder do módulo: 2+1 linhas (import do `router` no topo, `telas(db, out)` no fim
  do `build()`), comentário `# dgx fN`. Aba no `_dp_grupos.py` / `_op_grupos.py` / `EXTRA_MENU`
  do builder — **tela sem porta não existe**.
- **DDL idempotente dentro do arquivo** (`CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN
  IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`), numa `async def _ensure(db)` chamada por `telas()`
  e por cada ação. Nunca `alembic/versions/`. Nunca DROP/DELETE/UPDATE em dado que você não criou.
- Seed de dado (ex.: rubricas, parâmetros): `INSERT ... ON CONFLICT DO NOTHING`, dentro de `_ensure`.
- Formato brasileiro (`MM/AAAA`, `DD/MM/AAAA`, `R$`). Texto em PT-BR. Nunca Telegram.
- Caminho de dinheiro/folha: **paralelo cego**. Nada muda o valor calculado hoje sem um oráculo
  que prove igualdade contra o código atual (Σ|Δ| = 0 nos holerites publicados de 09/2026).
- Não edite: `checar_regressao.py` (o orquestrador registra), `alembic/`, `docker-compose*`,
  `.env*`, `main_production.py`, `frontend/` (table/form/panels renderizam genericamente — se
  precisar de JSON de menu, escreva no relatório e o orquestrador faz).

## Como testar — container efêmero contra o SANDBOX (cópia de produção de hoje)
```bash
WT=$(git rev-parse --show-toplevel)   # a sua worktree
ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\n' ' ')
# oráculo / script
docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_<nome>.py
# HTTP (porta 82NN = sua frente; pare ao fim)
docker run --rm -d --name teste-dgx-fN --network conecta-staging-network -p 127.0.0.1:82NN:8080 -v "$WT/backend:/app:ro" --tmpfs /app/logs:rw,mode=1777 --tmpfs /app/uploads:rw,mode=1777 -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS -e PORT=8080 conecta-pro-backend:latest
# token: POST 127.0.0.1:82NN/api/v1/auth/login (form: username=jjesus@conectamais.pro, senha em CLAUDE.md) — rate limit 5/min, guarde o token
# a tela: GET /api/v1/redesign/data/<modulo> (com Bearer) → screens[<id>]; ação: POST /api/v1/redesign/action/<nome>
docker stop teste-dgx-fN
```
(`-e SMTP_HOST=` etc. é OBRIGATÓRIO: o `.env` é o de produção e em 24/09 um teste mandou e-mail real a um cliente. `--tmpfs /app/logs` é obrigatório: o bind é só-leitura e o startup escreve em `/app/logs` — sem isso o container morre com "Read-only file system", exit 3.)
SQL direto no sandbox: `docker exec conecta-pro-postgres-staging psql -U postgres -d conecta_pro_staging -Atc "..."`.
Fixture no sandbox é permitida, marcada com `'FIXTURE DGX FN'` num campo de texto. **Produção
(`conecta-pro-postgres`/`conecta_pro`) é só leitura para você.**

## Oráculo (obrigatório)
`backend/scripts/orq/test_oraculo_<nome>.py`, mesmo formato do `test_oraculo_mapa_ferias.py`:
docstring com *por que existe / o que afirma / estado medido no nascimento / como roda*; sessão
por `from core.database import async_session_factory`; afirma a REGRA (recontada por SQL próprio,
não pelo serviço); sai 0 verde / 1 vermelho; linha final `TOTAL ...: N`. Rode ANTES do código
(deve ficar vermelho) e DEPOIS (verde). Cole as duas saídas no relatório.

## Commit e relatório
- Commit por pathspec (`git add <arquivos>`), na sua branch. Mensagem longa de propósito: o número
  medido (antes → depois), a decisão que respeita, o que NÃO foi feito. Rodapé:
  `[session: agent-fN] [module: <modulo>]` + `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Relatório em `auditoria/frentes/DGX_FN_<nome>.md`: §1 estado antes (medido) · §2 o que o DGX
  tem · §3 o que foi feito (arquivos, DDL, telas com deep-link `/redesign/<modulo>?t=<id>`) ·
  §4 oráculo (comandos + saídas vermelha e verde) · §5 o que NÃO foi feito e por quê · §6 como o
  Jordan testa amanhã (passos de clique) · §7 decisões que só o dono pode tomar.
- Mensagem final para o orquestrador (≤ 40 linhas): branch, arquivos, telas (ids e grupo),
  oráculo (nome + resultado), DDL que `_ensure` vai aplicar em produção no 1º acesso, portas/
  containers que você parou, decisões pendentes.

## Ponytail
Menor diff PROVÁVEL, não o mais curto. Sem abstração para um caso. Deleção > adição. Se vai
"consertar" muitos registros de uma vez, pare — há uma regra que você não procurou.
