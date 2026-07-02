# DIAGNÓSTICO FASE 1 — AUDITORIA PROFUNDA CONECTA PRO
**Data:** 2026-05-29
**Fase:** 1 — Diagnóstico READ-ONLY (nada foi modificado)
**Branch:** `feature/people-management-reorganization`
**Escopo:** mapeamento total + diagnóstico de qualidade + inventário de lixo, **sem nenhuma correção/remoção**

> ⚠️ **NADA FOI MODIFICADO, MOVIDO OU APAGADO.** O único arquivo escrito é este relatório.
> As Fases 2 (correção) e 3 (limpeza destrutiva) só começam após Jordan ler e aprovar.

---

## 1. SUMÁRIO EXECUTIVO — NOTA DE SAÚDE: **6.0 / 10**

O Conecta PRO é um ERP **funcional e em produção real** (11 clientes, 27 NFS-e, MRR ~R$272k), com cobertura de domínio muito ampla (48 módulos backend, 3.702 endpoints, 299 páginas frontend). O núcleo de negócio funciona. **Porém**, a base acumulou dívida técnica e entropia organizacional em ritmo maior que a consolidação:

**O que sustenta a nota (pontos fortes):**
- Arquitetura modular clara; reorganização 35→9 módulos documentada e com aliases.
- Componentes removidos saíram de fato do código ativo: **"Banco Cora" = 0 referências em `.py` ativo**, `piso_vigilante = 0`. Migração bem executada nesse ponto.
- Camada de roteamento canônica (`api/v1/__init__.py`) coesa e versionada.

**O que derruba a nota (pontos fracos):**
- **Entropia documental severa:** 528 arquivos `.md` soltos na raiz (407 `RELATORIO_*`, 21 `AUDITORIA_*`). Sinal de processo sem fechamento de ciclo.
- **Dívida técnica de tipagem alta:** 1.703 ocorrências de `any` e 158 `useState([])` (anti-pattern vs `useQuery`) no frontend.
- **Bug latente sistêmico:** 227 colunas `Column(Enum)` e apenas 19 com `values_callable` (~208 modelos expostos a divergência Python↔DB).
- **Divergência de branch perigosa:** **1.021 commits à frente de `main`**, último commit 2026-05-06. O branch de trabalho virou o de-facto trunk sem merge.
- **Working tree sujo:** 30 deletados + 5 modificados + 46 não rastreados não commitados.
- **~830 MB de artefatos regeneráveis/lixo** facilmente recuperáveis (caches + arquivos de archive).
- **Infra em alerta:** quase todos os containers Docker em `(unhealthy)` e `erp-grafana` derrubado há 5 semanas (detalhe na §2.5). Contradiz o "22/22 healthy" da Sessão 28.

**Veredito honesto:** sistema **operante mas com manutenibilidade comprometida**. Não está quebrado, mas o custo de evolução está subindo. A nota seria 7+ se a higiene documental/git e o padrão de enum fossem resolvidos; seria <5 se houvesse bugs críticos em produção — não encontrei evidência de quebra crítica nas zonas analisáveis.

### ⚠️ Limitações desta auditoria (sem invenção)
- **`tsc --noEmit` NÃO concluiu:** morto por OOM (exit 137) mesmo com heap de 8 GB. A VPS está com **28/31 GB de RAM usados e swap esgotado** — não há memória para o type-check completo. **A contagem exata de erros de tipo não foi obtida**; o sinal de qualidade do frontend vem de análise estática (greps).
- **Docker:** o `docker ps` inicial deu timeout (RAM saturada deixou o daemon lento), mas a consulta concluiu depois — estado **confirmado** e registrado na §2.5. Achado relevante: **quase todos os containers estão `(unhealthy)`** e `erp-grafana` está `Exited (255)`.
- `pylint` completo em milhares de arquivos é inviável no tempo/RAM disponível; usei **`ruff`** (cobertura ampla, rápido) como linter primário — declarado abaixo.

---

## 2. MAPA ESTRUTURAL (`/opt/conecta-pro/`, com zonas protegidas)

### 2.1 Tamanho por diretório (nível 1)
| Dir | Tamanho | Observação |
|-----|--------:|-----------|
| `frontend/` | 1.8 G | inclui node_modules 1.4G + .next 303M |
| `backend/` | 1.5 G | inclui venv 728M + node_modules 187M + caches ~430M |
| `reports/` | 301 M | artefatos de relatório — **[REVISAR]** |
| `logs/` | 78 M | rotativos |
| `uploads/` | 53 M | dados de usuário — **[NÃO TOCAR]** |
| `agents/` | 45 M | estado de agentes CTO/GEDEON |
| `backups/` | 27 M | dumps de DB — **[NÃO TOCAR]** |
| `docs/` | 16 M | |
| `_backup_modulos_consolidados/` | 3.6 M | backup de reorg — **[REVISAR]** |
| `.chunk_archive/` (untracked) | **200 M** | archive não rastreado — **[REVISAR]** |

### 2.2 Zonas [INTOCÁVEL] (lidas, nunca propostas p/ alteração)
```
backend/modules/financial/                    [INTOCÁVEL] (191 .py)
backend/modules/government_integrations/      [INTOCÁVEL] (173 .py)
backend/alembic/versions/                     [INTOCÁVEL]
backend/main_production.py                    [INTOCÁVEL] (46 KB, entrypoint ativo)
docker-compose*.yml                           [INTOCÁVEL]
backend/.env* / frontend/.env*                [INTOCÁVEL]
credentials/                                  [INTOCÁVEL] (44 KB)
certs/                                         [INTOCÁVEL] (16 KB)
backups/ , uploads/                           [INTOCÁVEL] (dados/dumps)
```

### 2.3 Backend — 48 módulos (top por nº de `.py`)
```
people_management 273 | ai 249 | financial 191 [INTOCÁVEL] | government_integrations 173 [INTOCÁVEL]
hr 172 | operacional 155 | integrations 117 | bidding 100 | notifications 66 | ged 52
retention 47 | crm 43 | gedeon 41 | campo 39 | security_lgpd 35 | recruitment 33 | ...
```
Módulos **agregadores** (camada da reorg 9 módulos, NÃO são dead code):
- `financeiro/`, `gestao/` → apenas `__init__.py` (re-export puro).
- `comercial/`, `operacoes/`, `inteligencia/`, `tecnico/` → subpastas PT-BR (estrutura canônica em construção).

### 2.4 Rotas
- **Backend:** 3.702 decorators `@router.*`; 686 `include_router`; registro canônico em `api/v1/__init__.py` (`prefix=/api/v1`).
- **Frontend:** 299 `page.tsx`. 31 rotas de módulo em `app/modulos/`: agendador, analytics, area-cliente, assistente, automacoes, bi, campo, configuracoes, crm, documentos, dp, empresas, equipamentos, financeiro, fiscal, gestao-pessoas, integracoes, licitacoes, marketing, operacional, portal, recrutamento, reembolso, relatorios, rh, saude-ocupacional, seguranca, servicos, suprimentos. + 11 rotas raiz (login, auth, dashboard, portal-funcionario, etc.).

### 2.5 Serviços / processos / crons
- **Docker — 31 containers (estado confirmado):** ⚠️ **quase todos `(unhealthy)`**.
  - **Conecta PRO:** `conecta-pro-backend` (8080, unhealthy), `conecta-pro-frontend` (3001, unhealthy), `conecta-pro-postgres` (unhealthy), `conecta-pro-redis` (unhealthy), `conecta-pro-celery-beat/flower/integrations/priority/sefaz/nfse/batch/operacional` (todos unhealthy), + `postgres-staging`/`redis-staging` (unhealthy).
  - **Observabilidade:** `erp-prometheus` (ok), `erp-grafana` **Exited (255) há 5 semanas** ❌, `erp-loki`/`erp-alertmanager` (unhealthy), `erp-node-exporter`/`erp-redis-exporter`/`erp-postgres-exporter`/`erp-promtail` (ok).
  - **Outros (fora do escopo Conecta PRO):** `chatwoot*`, `evolution-api`, `baileys-api` (vários unhealthy).
  - ⚠️ **Ressalva honesta:** `(unhealthy)` no Docker reflete o resultado do *healthcheck* configurado — pode indicar healthcheck mal-configurado **ou** degradação real. O sistema segue servindo (MRR/NFS-e ativos), mas o sinal precisa de investigação na Fase 2.
- **Crons de aplicação** (`rotinas/scripts/`): `onvio-auth-refresh.sh`, `onvio-sync-mensal.sh`.
- **Crontab do sistema:** scanners de segurança (`rkhunter`, `security_audit`), `system_monitor.sh`, `zombie_cleaner.sh`, e um **find-killer** (`*/5 * * * *` mata `find` longos) — *foi este cron que matou o `du` inicial desta auditoria*.
- **Celery beat:** agendado em `backend/celery_app.py`.

### 2.6 Estado do Git
| Item | Valor |
|------|-------|
| Branch atual | `feature/people-management-reorganization` |
| Commits à frente de `main` | **1.021** ⚠️ |
| Último commit | 2026-05-06 20:34 |
| Deletados (não commitados) | 30 (snapshots `agents/cto/memory/`) |
| Modificados | 5 (`alembic/env.py`, `integrations/.../solides/models.py`, 3 state JSON de agentes) |
| Não rastreados | 46 (inclui `.chunk_archive/`, 7 `RELATORIO_*.md`, vários `.bak`) |

---

## 3. BUGS ENCONTRADOS POR SEVERIDADE

| Sev | Local (arquivo:linha) | Descrição | Confiança |
|-----|----------------------|-----------|-----------|
| 🔴 CRÍTICO | `modules/ai/inventory_forecast/controllers/forecast_controller.py:69,75,230` | Endpoint de previsão **retorna dados MOCK** ("usar dados mock para demonstracao" / "em producao, buscar do banco") — nunca toca o DB. Defeito funcional confirmado. | Alta |
| 🟠 ALTO | `modules/*` (modelos) — ~208 ocorrências | **`Column(Enum)` sem `values_callable`**: 227 colunas Enum, só 19 com `values_callable`. Confirmado real em `operacional/diaristas/models/documento_fiscal.py:107-249`, `security_lgpd/models/{pia_assessment,consent}.py`, `audit/models/access_history.py`. Risco de divergência Python↔Postgres (grava/lê valor errado do enum). | Alta |
| 🟠 ALTO | Infra Docker (31 containers) | **Quase todos os containers do Conecta PRO em `(unhealthy)`** (backend, frontend, postgres, redis, todos os celery) + `erp-grafana` **Exited(255)** há 5 semanas. Pode ser healthcheck mal-configurado ou degradação real — exige investigação. Contradiz "22/22 healthy" registrado na Sessão 28. | Alta (estado) / Média (causa) |
| 🟠 ALTO | `modules/financial/controllers/supplier_controller.py:58-122` | **`/financial/suppliers/list` → 422**. Confirmado: não existe rota `/list`; as rotas são `GET ""`, `/stats`, `/search`, `/{supplier_id}`. `"list"` casa com `/{supplier_id}` e falha validação UUID → 422. `/financial/suppliers` (200) é o correto. *(Zona protegida — apenas documentado, não corrigir.)* | Alta |
| 🟡 MÉDIO | `modules/ged/controllers/kit_real_controller.py:990,1148` | **`kit_mensal`** ainda referenciado em SQL raw (`WHERE ... kit_mensal = true`). Migração p/ `portaria_presencial` incompleta no GED (em `financial` há alias retrocompat — protegido). | Alta |
| 🟡 MÉDIO | Backend — 708 ocorrências (`B904`) | `raise HTTPException(...)` dentro de `except` **sem `from e`** — perde a cadeia de exceção original, dificulta debug em produção. | Alta |
| 🟡 MÉDIO | Frontend — 158 ocorrências | **`useState([])` para dados de API** em vez de `useQuery` (que existe em 289 arquivos). Anti-pattern: sem cache/refetch/loading states; fonte de telas piscando/stale. | Alta |
| 🟡 MÉDIO | Frontend — 164 ocorrências (`.toFixed(`) | Uso de `.toFixed()` sobre valores que vêm do backend (frequentemente string/Decimal serializado) sem `Number()` explícito — risco de `NaN`/concatenação. **Requer inspeção caso a caso.** | Média |
| 🟢 BAIXO | Backend — 1.889 (`PLR2004`) | "Magic values" (números mágicos) hardcoded. | Alta |
| 🟢 BAIXO | Frontend — 7 | `console.log` em `src/` de produção. | Alta |
| ⚪ INFO | `condominio_id` — 3.253 refs | Padrão multi-tenant. **Não foi possível isolar automaticamente** os casos `None → IS NULL` sem tratamento; exige revisão manual dirigida. Declarado como não-quantificado. | — |
| ⚪ INFO/Falso+ | `vigilante` — 21 backend / 13 frontend | "Vigilante" é **termo legítimo de domínio** (cargo na vigilância patrimonial). NÃO classifiquei como bug; ver [REVISAR] na §5. | — |

**Observação sobre `client_name` vs `customer_name`:** 163 usos de `client_name` vs 23 de `customer_name`. Não é possível afirmar bug em massa sem contexto por-tabela (ambos podem ser campos legítimos em entidades diferentes). **Requer mapeamento manual** antes de qualquer troca.

---

## 4. DÍVIDA TÉCNICA / CODE SMELLS

### 4.1 Backend — `ruff` (cobertura ampla: E,F,W,B,UP,SIM,C4,ARG,PLR,PLW; exclui zonas protegidas)
**Total: 10.737 issues.** Top regras:
| Regra | Qtd | Interpretação |
|-------|----:|---------------|
| `B008` | 3.957 | ⚠️ **Falso-positivo** — `Depends()` em default de função é o padrão idiomático do FastAPI. Ignorar. |
| `ARG001` | 2.145 | Argumentos de função não usados (muitos são `current_user`/`condominio_id` exigidos pela DI). Revisar amostra. |
| `PLR2004` | 1.889 | Números mágicos. |
| `B904` | 708 | `raise` sem `from` (ver §3). |
| `ARG002` | 669 | Args de método não usados. |
| `PLR0913` | 652 | Funções com argumentos demais (>5). |
| `E501` | 159 | Linha longa. |
| `PLR0912/0915/0911` | 218 | Complexidade alta (branches/statements/returns). |
| `SIM102/108/103` | 222 | Condicionais simplificáveis. |

**Sinal líquido real (descontando B008):** ~6.780 smells. Concentração em complexidade e args não usados — típico de código gerado por agentes em alta velocidade.

> Ruff com a config *default do projeto* reporta apenas **4 erros** — a config está extremamente permissiva (só pega I001/A003/UP). A dívida acima só aparece com ruleset ampliado.

### 4.2 Frontend — análise estática (tsc indisponível por OOM)
| Métrica | Qtd | Risco |
|---------|----:|-------|
| `any` / `as any` / `<any>` | **1.703** | Alto — anula a segurança de tipos |
| `useState([])` (dados de API) | **158** | Médio — anti-pattern vs `useQuery` |
| Arquivos com `useQuery` | 289 | (uso correto — referência) |
| `fetch(` direto em `.tsx` | 489 | Médio — bypass da camada de serviço/cache |
| `.toFixed(` | 164 | Médio — risco numérico (ver §3) |
| `console.log` em `src/` | 7 | Baixo |

### 4.3 Dívida por módulo (qualitativa)
| Módulo | Dívida dominante |
|--------|------------------|
| `ai/` (249 py) | Mock em forecast; complexidade alta |
| `people_management/` (273) + `hr/` (172) | **Possível duplicação/legado** (ver §5) |
| `operacional/diaristas/` | Enums sem `values_callable` |
| `security_lgpd/`, `audit/` | Enums sem `values_callable` |
| `bidding/`, `gedeon/` | Simuladores intencionais (não-bug) + complexidade |
| Raiz do projeto | 528 `.md` — entropia documental |

---

## 5. CANDIDATOS A LIMPEZA (CLASSIFICADOS — NADA REMOVIDO)

| Item | Tamanho/Qtd | Classe | Justificativa |
|------|------------|--------|---------------|
| `backend/.mypy_cache/` | 190 M | **[SEGURO REMOVER]** | Cache regenerável |
| `backend/htmlcov/` | 188 M | **[SEGURO REMOVER]** | Relatório de cobertura HTML regenerável |
| `backend/.ruff_cache/` | 49 M | **[SEGURO REMOVER]** | Cache (3 versões: 0.9.4/0.14.14/0.15.0) |
| `backend/.pytest_cache/` | 1.7 M | **[SEGURO REMOVER]** | Cache de testes |
| `__pycache__/` (todos) | — | **[SEGURO REMOVER]** | Bytecode regenerável |
| Arquivos `*.bak`/`*.backup` de **código** (≈40, ex.: `frontend/src/.../page.tsx.bak`, `modules/scheduler/.../*.py.bak`) | — | **[SEGURO REMOVER]** | Versões antigas de fonte; git é a fonte de verdade. **Exceção:** ver `.env.backup` abaixo. |
| `CLAUDE.md.backup`, `CLAUDE.md.backup-20260111_124344` | 28 KB | **[SEGURO REMOVER]** | Backup de doc |
| `logs/*.log.1` (rotacionados) | ~10 M | **[SEGURO REMOVER]** | Logs rotativos antigos |
| `.chunk_archive/` (untracked) | **200 M** | **[REVISAR]** | Archive não rastreado; verificar se é insumo de algum pipeline antes de remover |
| `reports/` | 301 M | **[REVISAR]** | Pode conter PDFs/CSVs entregues a clientes |
| `_backup_modulos_consolidados/` | 3.6 M | **[REVISAR]** | Backup da reorg; confirmar reorg 100% estável antes |
| 528 `.md` na raiz (`RELATORIO_*`, `AUDITORIA_*`, etc.) | — | **[REVISAR]** | Mover p/ `docs/historico/`, não deletar (histórico de auditoria). Não remover às cegas. |
| `docker-compose.yml.backup*`, `.pre-patch` | ~23 KB | **[REVISAR]** | Relacionado a infra/compose → cautela |
| `main_simple.py.bak`, `main_debug.py`, `main_lite.py`, `main_minimal.py` | — | **[REVISAR]** | Entrypoints alternativos; confirmar que nenhum compose/script os usa antes |
| `modules/hr/` (172py) **vs** `modules/people_management/hr/` (60py) | — | **[REVISAR]** | **Possível legado.** `modules.hr` só é importado por testes/`diagnose_modules.py` (não por `main_production`). Pode ser dead code, mas é DP ativo → **NÃO remover sem mapa de imports completo + validação CIC**. |
| `modules/fase5/` (23py), `modules/search/` (2py) | — | **[REVISAR]** | Memória cita "deprecado"/"vazio"; confirmar zero rotas montadas antes |
| `backend/.env.backup*`, `frontend/.env.local.backup*` | — | **[NÃO TOCAR]** | **Contêm segredos.** Sensível. |
| `backups/*.dump`, `*.sql` | 27 M | **[NÃO TOCAR]** | Dumps de banco |
| `credentials/`, `certs/` | 60 KB | **[NÃO TOCAR]** | Certificado A1, chaves |
| `uploads/` | 53 M | **[NÃO TOCAR]** | Dados de usuário/ponto/onvio |
| Qualquer item em zona [INTOCÁVEL] | — | **[NÃO TOCAR]** | Regra absoluta |

**Dependências não usadas:** não auditadas em profundidade nesta fase (cross-check `requirements.txt`/`package.json` × imports reais exige execução dedicada). **Declarado como pendente** — não inventar resultado.

---

## 6. PLANO DE CORREÇÃO PROPOSTO — FASE 2 (ordenado por prioridade × risco)

| # | Ação | Prioridade | Esforço | Autônomo? |
|---|------|-----------|---------|-----------|
| 1 | Corrigir mock em `forecast_controller.py` → consultar DB real | 🔴 Alta | M (3-5h) | **Validação CIC** (lógica de negócio + dados reais) |
| 2 | Padronizar **`values_callable`** nos ~208 `Column(Enum)` fora de zona protegida | 🟠 Alta | G (1-2 dias) | **Validação CIC** (toca modelos → exige migration + teste de leitura/escrita; NÃO mexer em `financial`/`gov`) |
| 3 | Documentar/alinhar frontend p/ usar `/financial/suppliers` (não `/list`) | 🟠 Alta | P (1h) | Autônomo **no frontend** (backend é zona protegida — só ajustar a chamada) |
| 4 | Completar migração `kit_mensal → portaria_presencial` no GED (`kit_real_controller.py`) | 🟡 Média | M | **Validação CIC** (SQL raw sobre `contracts`) |
| 5 | Adicionar `from e` nos 708 `B904` | 🟡 Média | M (script-assistido) | Autônomo (mudança mecânica, baixo risco) |
| 6 | Migrar 158 `useState([])` críticos → `useQuery` (priorizar telas de dados financeiros/operacionais) | 🟡 Média | G | Semi-autônomo (revisar por tela) |
| 7 | Auditar 164 `.toFixed()` e envolver com `Number()` onde a fonte é backend | 🟡 Média | M | **Validação CIC** (caso a caso) |
| 8 | Reduzir `any` (1.703) por módulo, começando pelos serviços de API | 🟢 Baixa | G (incremental) | Autônomo (incremental, por PR pequeno) |
| 9 | Tornar `tsc --noEmit` executável (rodar fora de horário de pico ou com mais swap) p/ quantificar erros de tipo | 🟢 Baixa | P | Autônomo (infra) |
| 10 | **Git:** planejar merge/rebase de `feature/people-management-reorganization` → `main` (1.021 commits) | 🟠 Alta | G | **Validação CIC** (decisão de release) |
| 11 | **Infra:** investigar `(unhealthy)` dos containers (revisar healthchecks + logs) e religar `erp-grafana` | 🟠 Alta | M | **Validação CIC** (toca infra/observabilidade) |
| 12 | **RAM:** mitigar saturação (28/31 GB usados, swap esgotado) — causa do OOM no `tsc` e da lentidão do daemon | 🟠 Alta | M | **Validação CIC** (capacidade/infra) |

**Regra mantida:** nenhuma ação toca `financial/`, `government_integrations/`, `alembic/versions/`, `main_production.py`, `docker-compose*`, `.env*`, `credentials/`.

---

## 7. PLANO DE LIMPEZA PROPOSTO — apenas [SEGURO REMOVER] (comandos COMENTADOS p/ aprovação)

> Tudo abaixo está **comentado**. NÃO executar até Jordan aprovar. Recuperável (caches) ou coberto por git (`.bak`).

```bash
# === CACHES REGENERÁVEIS (recupera ~430 MB) — [SEGURO] ===
# rm -rf /opt/conecta-pro/backend/.mypy_cache       # 190 M
# rm -rf /opt/conecta-pro/backend/htmlcov           # 188 M
# rm -rf /opt/conecta-pro/backend/.ruff_cache       # 49 M
# rm -rf /opt/conecta-pro/backend/.pytest_cache     # 1.7 M
# find /opt/conecta-pro/backend -type d -name "__pycache__" -prune -exec rm -rf {} +

# === BACKUPS DE FONTE (git é a fonte de verdade) — [SEGURO], MAS NÃO os .env.backup ===
#   Listar primeiro para conferência:
# find /opt/conecta-pro -path "*/node_modules" -prune -o -path "*/venv" -prune -o \
#   \( -name "*.bak" -o -name "*.backup" \) -not -name "*.env*" -not -path "*/credentials/*" -print
#   (revisar a lista acima ANTES de remover)

# === BACKUPS DE DOC — [SEGURO] ===
# rm -f /opt/conecta-pro/CLAUDE.md.backup /opt/conecta-pro/CLAUDE.md.backup-20260111_124344

# === LOGS ROTACIONADOS — [SEGURO] ===
# rm -f /opt/conecta-pro/logs/*.log.1

# === NÃO INCLUÍDO (exige decisão humana — [REVISAR]): ===
#   .chunk_archive/ (200M) | reports/ (301M) | _backup_modulos_consolidados/ (3.6M)
#   | 528 .md da raiz (mover p/ docs/historico, não deletar)
#   | modules/hr vs people_management/hr | modules/fase5 | modules/search
#   | main_*.py alternativos | docker-compose.*.backup
# === NUNCA ([NÃO TOCAR]): .env.backup* | backups/ | uploads/ | credentials/ | certs/ | zonas protegidas
```

---

## 8. PRÓXIMOS PASSOS
1. Jordan revisa este relatório.
2. Decidir escopo da Fase 2 (correções) — recomendo iniciar pelos itens #1, #3, #5 (alto valor, baixo/médio risco).
3. Fase 3 (limpeza) só após aprovação explícita dos blocos [SEGURO REMOVER].
4. Reexecutar `tsc --noEmit` em janela de baixa carga p/ fechar a lacuna de tipagem.

**Lembrete final: nada foi modificado nesta fase.**
