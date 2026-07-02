# REBUILD + REDEPLOY DA IMAGEM DO BACKEND — CONECTA PRO

**Data:** 2026-05-30
**Operação:** reconstrução da imagem Docker do backend a partir do código do host + redeploy seguro (com rollback, validação em efêmero e checkpoint).
**Supervisão:** Jordan em tempo real, com pontos de pausa aprovados.
**Resultado:** ✅ **SUCESSO** — 10 módulos + cadeia de DP restaurados em produção, sem regressão.

> Regra mantida: nenhum conteúdo de zona protegida foi editado (`financial/`, `government_integrations/`, `alembic/versions/`, `main_production.py`, `credentials/`, `.env*`). Nenhuma migration aplicada. Banco tocado apenas para **backup de leitura**.

---

## 1. PASSO 0 — O Dockerfile capturava os arquivos? (Chesterton)

**Sim — o Dockerfile não tinha defeito; a imagem só estava velha.**
- `COPY --chown=erp:erp . .` (não-seletivo) + `context: ./backend` (compose) → captura `modules/operacional/ai/` e os demais.
- `.dockerignore` exclui só `*.py[cod]`, `venv/`, `*.md`, `*.bak`, `logs/`, `backups/` — **não** exclui `modules/` nem `*.py` fonte.
- Entrypoint correto: `uvicorn main_production:app`.
- **Causa real da defasagem:** imagem em produção criada em **2026-04-07**; os 98 arquivos foram adicionados ao host depois → nunca entraram.
- **Viabilidade offline:** host e container-na-bridge têm rede externa (pypi/docker.com `200`); base `python:3.12-slim` ausente local + `requirements.txt` alterado em 18/04 → build completo (feito, ~OK).

## 2. Imagens — antiga vs nova (rollback)

| Papel | Tag | Image ID | Criada |
|---|---|---|---|
| **Rollback (antiga)** | `conecta-pro-backend:pre-rebuild-20260407` | `facf345e4741` | 2026-04-07 |
| **Produção (nova)** | `conecta-pro-backend:latest` → `conecta-pro-backend:rebuild-20260530b` | `bfa169a24c06` | 2026-05-30 15:26 |
| Intermediária (com bug GEDEON, não usada) | `conecta-pro-backend:rebuild-20260530` | `4239c1102ba9` | 2026-05-30 15:06 |

A imagem antiga **não foi sobrescrita** — preservada sob tag explícita antes de mover o `:latest`.

## 3. Correção aplicada durante o processo (colisão GEDEON)

Durante a validação em efêmero, a 1ª imagem nova (`rebuild-20260530`) introduziu **1 regressão**: `GEDEON: falha na inicialização (No module named 'modules.gedeon.gedeon.gedeon')`.
- **Causa raiz:** no host coexistiam `modules/gedeon/gedeon.py` (493 linhas — implementação real: `class Gedeon`, `registrar_subscribers()`, singleton `gedeon`) **e** `modules/gedeon/gedeon/` (pacote de 1 arquivo, **artefato de `docker cp` recursivo**, cujo `__init__` reexporta de um `gedeon.py` interno inexistente). O pacote sombreava o módulo → import quebrava. A imagem antiga (pré-07/04 20:47) só tinha o `.py`, por isso funcionava.
- **Decisão (Jordan):** o `gedeon.py` é o canônico → **removido o diretório-artefato** `modules/gedeon/gedeon/` (backup em `backups/gedeon_dir_artifact_20260530_152556/`).
- **Varredura:** procurei outras colisões pacote-vs-módulo em `modules/` → **só esta 1**. Sem outras regressões de import.
- **Rebuild → `rebuild-20260530b`:** import resolve (`from modules.gedeon.gedeon import gedeon` → tipo `Gedeon`), GEDEON `orquestrador ativo`.

## 4. Validação da imagem nova (container efêmero isolado em staging)

Efêmero rodou **somente na rede `conecta-staging-network`** (Postgres/Redis de staging), **sem rota para produção** — escolha de segurança, pois o `lifespan` inicia um consumidor de EventBus + GEDEON que, no Redis de produção, poderia roubar/processar eventos reais.

| Verificação | Resultado |
|---|---|
| `import modules.operacional.ai` | ✅ OK |
| `modules/operacional/ai` na imagem | ✅ presente (antes ausente) |
| Contagem `.py` em `/app/modules` | **2283** (nova) vs **2185** (antiga) = +98 |
| Startup: `No module named 'modules.operacional.ai'` | **0** (antes derrubava 10 módulos + 15 routers DP) |
| `DP: falha ao incluir` | **0** (antes: 15) |
| `GEDEON: orquestrador ativo` | ✅ |
| Único warning restante | `OpenClaw` (pré-existente, não-fatal) |
| `/health` | 200 |

## 5. Antes → Depois (PRODUÇÃO, porta 8080)

| Métrica | Antes (imagem 04-07) | Depois (imagem 05-30b) |
|---|---|---|
| Rotas vivas | **1671** | **3520** |
| Módulos com 0 rotas | operacional, campo, crm, bidding, services, equipment, document-kits, empresas, fiscal, government (10) | **0** — todos restaurados |
| `/operacional/*` | 0 | **246** |
| `/crm/*` | 0 | **115** |
| Routers de DP (admissão→folha→eSocial→ponto) | 15 falhando | **15 registrados** |
| GEDEON orquestrador (lifespan) | ativo | **ativo** (mantido) |
| Erros de import no startup | `operacional.ai` (cascata) + OpenClaw | **só OpenClaw** |
| Celery: tasks `sincronizar_nfse/nfe_entrada` | não-registradas (KeyError) | **registradas** (~366 tasks/worker) |
| Containers conecta-pro healthy | 14/14 (mas backend defasado) | **14/14** (com código atual) |
| Curl rotas restauradas (operacional/crm/empresas/equipment) | 404 | **401** (existem, pedem auth) |

## 6. Sequência de deploy executada

```bash
# Backend (via tag — compose NÃO editado)
docker tag conecta-pro-backend:latest conecta-pro-backend:pre-rebuild-20260407   # rollback anchor
docker tag conecta-pro-backend:rebuild-20260530b conecta-pro-backend:latest      # latest -> nova
docker compose -f /opt/conecta-pro/docker-compose.yml up -d --no-deps --no-build backend

# Celery (1 canário + 7 demais), via docker-compose.yml + docker-compose.celery.yml
docker compose -f .../docker-compose.yml -f .../docker-compose.celery.yml up -d --no-deps --no-build <celery-priority|beat|operacional|nfse|sefaz|batch|integrations|flower>
```

## 7. 🔙 ROLLBACK (sempre disponível, 1 sequência)

```bash
# Backend
docker tag conecta-pro-backend:pre-rebuild-20260407 conecta-pro-backend:latest
docker compose -f /opt/conecta-pro/docker-compose.yml up -d --no-deps --no-build backend
# Celery (mesma ideia, se necessário)
docker compose -f /opt/conecta-pro/docker-compose.yml -f /opt/conecta-pro/docker-compose.celery.yml \
  up -d --no-deps --no-build celery-beat celery-operacional celery-nfse celery-sefaz celery-batch celery-priority celery-integrations flower
```
A imagem antiga `facf345e` permanece intacta sob a tag `pre-rebuild-20260407`.

## 8. O que este rebuild NÃO resolveu (honestidade — próximas fases)

- 🔸 **Schema drift (B3)** — os ~25/91 GETs que davam **500** por coluna/tabela/enum faltante **continuam 500**. Depende de **migrations** (`alembic/versions/`, zona protegida) — operação **separada e futura**. O rebuild apenas faz as rotas existirem; não cria colunas no banco.
- 🔸 **OpenClaw (B2)** — `modules/ai/openclaw` não existe nem no host; warning não-fatal persiste. Pendência de código (criar ou remover a importação).
- 🔸 **Celery-batch / Redis localhost (B4)** — **não observado** nos logs pós-deploy (0 ocorrências em 3 min), mas era intermitente; **monitorar**. Se reaparecer, é config de conexão, não imagem.
- 🔸 **Enum `tenant_status`/`alertstatus` (dado em maiúsculo/minúsculo)** — não tratado (dado/migration).
- 🔸 Imagem intermediária `rebuild-20260530` (`4239c110`, com bug GEDEON) ficou no host — pode ser removida depois (`docker rmi`), fora de escopo agora.

## 9. Estado final

**14/14 containers conecta-pro UP e HEALTHY** (backend + 8 celery + flower na imagem nova `bfa169a2`; frontend/postgres/redis intocados). Backend `/health` 200, 3520 rotas, GEDEON ativo, DP restaurado. Backup pré-rebuild: `backups/conecta_pro_PRE_REBUILD_20260530_150432.dump` (4533 objetos). Rollback a 1 sequência.
