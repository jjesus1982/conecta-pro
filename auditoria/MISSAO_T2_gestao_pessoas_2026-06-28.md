# MISSÃO t2 — Gestão de Pessoas 100% (8 módulos, ponta a ponta, E2E em tudo)
**De:** t1 · **Para:** t2 · **Data:** 28/06/2026
**Você (t2) fica 100% dedicado ao domínio GESTÃO DE PESSOAS.** O t1 fica com Financeiro & Fiscal. **Não há colisão de arquivos** porque trabalhamos em diretórios diferentes — desde que você respeite as RAIAS abaixo.

---

## 0. OBJETIVO
Varrer os 8 módulos de Gestão de Pessoas **módulo por módulo → submódulo por submódulo → tela por tela**, e em CADA tela:
1. **Leitura/exibição:** a tela mostra o dado real do backend? (não vazio quando o banco tem; não 404/500).
2. **Escrita E2E:** criar → verificar → editar → excluir funciona de verdade? (com dados marcados e limpeza).
3. **Corrigir** todo bug encontrado (backend e/ou frontend).
4. **Bakear durável** (a imagem é baked, não mounted — ver §6).
5. **Relatório** incremental por módulo.

A meta é o que o t1 já fez no resto do sistema: **toda tela codada funcionando de ponta a ponta**, sem casca, sem 500, sem dado escondido.

---

## 1. ESCOPO — os 8 módulos (suas RAIAS de trabalho)

| # | Módulo (frontend) | Pasta frontend | Backend (pasta) |
|---|---|---|---|
| 1 | **Departamento Pessoal (DP)** | `frontend/src/app/modulos/dp/` (17 telas) | `backend/modules/people_management/hr` (93), `folha` (10) |
| 2 | **Recursos Humanos (RH)** | `frontend/src/app/modulos/rh/` (13 telas) | `people_management/human_resources` (51), `retention` (70), `cct` (25/13) |
| 3 | **Recrutamento** | `frontend/src/app/modulos/recrutamento/` (5 telas) | `backend/modules/recruitment` (83) |
| 4 | **Gestão de Pessoas (hub)** | `frontend/src/app/modulos/gestao-pessoas/` (45 telas) | `people_management/*` (ponto, ferias, folha, esocial, beneficios, ged, sst — agregador) |
| 5 | **Saúde Ocupacional (SST)** | `frontend/src/app/modulos/sst/` e `saude-ocupacional/` (9) | `people_management/sst` (28), `health_occupational` (40) |
| 6 | **Ponto Eletrônico** | `frontend/src/app/modulos/ponto/` + `gestao-pessoas/ponto/` | `people_management/ponto` (19) |
| 7 | **Portal do Funcionário** | `frontend/src/app/modulos/portal-funcionario/` + `portal/` (13) | `people_management/employee_portal` (48) |
| 8 | **Reembolso** | `frontend/src/app/modulos/reembolso/` + `dp/reembolsos` | `backend/modules/reimbursement` (26) |

**RAIA = só toque nesses diretórios.** NÃO toque em `modules/financial`, `modules/ged`, `modules/gedeon`, `modules/document_kits`, `modules/operacional`, `modules/crm`, `modules/bidding` — esses são do t1 ou de outra frente.

⚠️ **GED:** as telas `gestao-pessoas/ged/*` consomem `people_management/ged` — PODE mexer aí (é raia de Pessoas). Mas NÃO mexa em `modules/ged` raiz nem `modules/gedeon` (outra frente).

---

## 2. PROTOCOLO ANTI-COLISÃO (crítico — nós dois mexemos na MESMA imagem Docker)
O host (`/opt/conecta-pro`) e a imagem `conecta-pro-backend:latest` são **compartilhados** entre os dois terminais. Como o build copia o host inteiro, nossas mudanças **compõem** (não se apagam) — MAS um rebuild/recreate simultâneo pode subir container no meio do arquivo do outro. Regras:

1. **Raias de diretório** (§1) — nunca edite fora da sua raia.
2. **Arquivos COMPARTILHADOS = avise antes de tocar** (de preferência, NÃO toque):
   `backend/main_production.py`, `backend/api/v1/__init__.py`, `backend/core/*`, `frontend/src/lib/api-client.ts`, `frontend/src/config/modules.ts`, qualquer `alembic/versions/*`.
   Se PRECISAR montar um router novo em `main_production.py`, faça um bloco try/except isolado e me avise (eu faço o mesmo).
3. **Bake serializado:** antes de `docker compose build backend` + recreate, cheque se o outro terminal não está buildando. Crie um lock simples: `touch /opt/conecta-pro/.bake_lock_t2` antes e `rm` depois; se existir `.bake_lock_t1`, espere.
4. **SEMPRE teste efêmero ANTES de recriar** (§6) — pega arquivo quebrado do OUTRO terminal antes de ir pra prod.
5. **Migrations:** additive, com backup, e me avise (zona compartilhada).
6. **Âncora por bake:** `docker tag conecta-pro-backend:latest conecta-pro-backend:pre-<algo>-AAAAMMDD` antes de cada build (rollback).

---

## 3. SEGURANÇA EM PRODUÇÃO (inviolável)
- **Dados de teste com prefixo `ZZE2E_`** (nomes/títulos). SEMPRE exclua o que criar; se o DELETE falhar (FK/soft-delete), limpe via SQL (`DELETE ... WHERE ... LIKE 'ZZE2E%'`). Verifique resíduo = 0 ao fim de cada tela.
- **NUNCA** apague/edite registro que você não criou. NÃO delete por heurística (CNPJ/nome parecido) — só pelo marcador `ZZE2E_` ou pelo id que SEU create retornou. (O t1 quase perdeu um seed por isso — restaurou do backup; não repita.)
- **PROIBIDO disparar efeito externo/irreversível:** eSocial envio/transmissão, e-mail, WhatsApp, `sync-solides`, sync gov, geração de guia, assinatura externa, pagamento. Marque "PULADO (efeito externo)".
- **Backup antes de qualquer DROP/migration:** dump da tabela ou `pg_dump`. Backups diários ficam em `/opt/conecta-pro/backups/postgresql/`.

---

## 4. PADRÕES DE BUG JÁ CONHECIDOS (o t1 já mapeou — use pra ir rápido)
Estes são os bugs recorrentes do codebase. Procure-os ativamente:

**A) Enum SQLAlchemy sem `values_callable`** → mapeia pelo NOME do membro (ATIVO) mas o DB guarda o `.value` (active) → `LookupError`/500.
- Fix: `Column(Enum(X, values_callable=lambda x: [e.value for e in x]))`.
- ⚠️ **NÃO aplique em int-enums** (`class X(int, Enum)` / `IntEnum`) — quebra o mapper (cascata "NotificationQueue is not defined") e **derruba o boot**. Sempre teste `configure_mappers()` efêmero depois.

**B) Schema-drift model↔DB:** coluna no model que não existe no DB (ex.: `codigo_interno`, `ca_number` vs `ca_numero`) ou tipo errado (model `String`, DB `integer/numeric/ARRAY`). Fix: alinhar o model/`Column("nome_real", ...)` OU `ALTER TABLE ADD COLUMN` aditivo. O **schema Pydantic também** precisa casar o tipo (str↔int).

**C) Barra-final (`redirect_slashes=False` global):** front chama `/x/` mas a rota é `@router.get("")` → 404/405. Fix: mirror `@router.get("/", include_in_schema=False)` OU remover a barra no front.

**D) Colisão de rota:** `/x/literal` cai em `/x/{id}` (tenta parsear "literal" como UUID) → 422/500. Fix: registrar a rota literal ANTES da paramétrica.

**E) `.value` em string:** código faz `obj.campo.value` mas o campo é str → `'str' object has no attribute 'value'`. Fix defensivo: `(x.value if hasattr(x,'value') else x)`.

**F) Datas str→date (asyncpg):** passar string `'2026-08-01'` em coluna DATE → `'str' object has no attribute 'toordinal'`. Fix: `date.fromisoformat(str(v)[:10])` (objeto date, não string).

**G) `current_user.get("id")`:** o `current_user` é objeto `User`, não dict → AttributeError. Fix: `getattr(current_user, "id", None)`.

**H) ResponseValidationError UUID vs str:** schema declara `id: str` mas ORM retorna UUID. Fix: `id: UUID` no schema.

**I) page_size > 100:** front manda `page_size=200`, backend valida `le=100` → 422. Fix: front 100.

**J) Endpoint faltando:** front chama POST/PUT/DELETE que o backend só tem GET → 405. Fix: implementar o handler.

**K) Frontend prefixo dobrado/path errado:** client orval gera `/x/x/` ou path errado → 404. (Mais comum no financeiro; em Pessoas vimos `/vacations/vacations`, `/ged/clients` proxy GET-only, `/recruitment/candidates` com barra-final, etc.)

---

## 5. MÉTODO POR TELA
1. `grep -nE "fetch\(|customInstance|/api/v1|method.*POST|method.*PUT|method.*DELETE|JSON.stringify" <page.tsx>` → liste TODOS os endpoints + payloads.
2. **GET (exibição):** curl com token. 200 com dado? vazio mas o DB tem (→ filtro/tabela/shape errado)? 404/500 (→ bug)? Confira a CHAVE que o front lê vs a que o backend devolve (`.items`/`.dias`/`.data.items`...).
3. **Escrita E2E:** monte payload mínimo válido `ZZE2E_` → POST → confira persistiu (GET) → PATCH/PUT → DELETE → confirme sumiço. 422 = leia o `detail` e corrija o payload 1x.
4. **Corrija** o bug (na sua raia). Compile (`python3 -m py_compile`).
5. **Limpe** os dados de teste. Resíduo = 0.

## 6. DEPLOY (imagem é BAKED, não mounted)
- **Teste rápido (efêmero entre edições):** `docker cp <arquivo> conecta-pro-backend:/app/<arquivo>` + `docker restart conecta-pro-backend` (morre num recreate, serve só p/ testar).
- **Durável (bakar):**
  1. `docker tag conecta-pro-backend:latest conecta-pro-backend:pre-<x>-20260628`
  2. `find backend/modules -name __pycache__ -type d -prune -exec rm -rf {} +`
  3. `cd /opt/conecta-pro && docker compose -f docker-compose.yml -f docker-compose.celery.yml build backend`
  4. **Teste efêmero (OBRIGATÓRIO):** `docker run --rm --network none --entrypoint python conecta-pro-backend:latest -c "import main_production; from sqlalchemy.orm import configure_mappers; configure_mappers(); print('OK')"` — só recrie se imprimir OK.
  5. `docker compose -f docker-compose.yml -f docker-compose.celery.yml up -d --no-deps backend` (recria só o backend). Se mexeu em model usado por celery, recrie os celery também.
- **Frontend:** build interno no Dockerfile. Durável = `docker compose ... build frontend` + `up -d --no-deps frontend`. Rápido = `npm run build` no host + `docker cp .next/static + .next/server + BUILD_ID` no container `conecta-pro-frontend` (preservando chunks — ver `scripts/deploy/deploy_frontend.sh`).
- Espere health 200 (`curl :8080/health`) e valide.

## 7. ACESSO
- **Auth:** `TOKEN=$(curl -s -X POST http://127.0.0.1:8080/api/v1/auth/login -H "Content-Type: application/x-www-form-urlencoded" --data-urlencode "username=jjesus@conectamais.pro" --data-urlencode 'password=<senha do chat>' | python3 -c "import sys,json;print(json.load(sys.stdin).get('access_token',''))")` — reuse o token (login é rate-limited 5/min).
- **Base:** `http://127.0.0.1:8080` · prefixo `/api/v1`.
- **DB:** `PGPW=$(docker exec conecta-pro-postgres printenv POSTGRES_PASSWORD); docker exec -e PGPASSWORD="$PGPW" conecta-pro-postgres psql -U postgres -d conecta_pro -tAc "<SQL>"`.
- **Dados reais:** 46 funcionários ativos; 27 NFS-e; tabelas de Pessoas: `employees`, `vacation_requests`, `sst_afastamentos`, `gp_clock_punches`, `hr_*`, `training_*`, `health_*`, `reimbursement_*`, `candidates`, `job_positions`, `interviews`.

## 8. ENTREGÁVEL
Relatório `.md` incremental por módulo: tabela `| Tela | Endpoint | GET | CREATE | EDIT | DELETE | Status | Bug/Correção |`, + resumo (X telas, Y corrigidas, Z bugs) + confirmação de resíduo ZZE2E = 0 + âncoras de bake criadas. Salve em `/opt/conecta-pro/auditoria/`.

## 9. ORDEM SUGERIDA (do coração pra fora)
DP → Ponto → Folha (dentro de DP/gestao-pessoas) → RH → Recrutamento → SST → Reembolso → Portal do Funcionário. Em cada um, submódulo por submódulo, tela por tela. Não pule a escrita.

---
**Resumo:** você (t2) = 8 módulos de Pessoas, ponta a ponta, E2E, sem sair das raias. t1 = Financeiro & Fiscal. Bake serializado + teste efêmero = zero colisão. Bora.
</content>
