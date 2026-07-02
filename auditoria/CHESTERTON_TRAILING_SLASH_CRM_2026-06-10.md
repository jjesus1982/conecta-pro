# Chesterton — divergência de trailing slash nas rotas do CRM (READ-ONLY)

- **Data:** 2026-06-10
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Entender POR QUE clients aceita `/` e proposals/opportunities/leads não, antes de uniformizar o backend.
- **Veredito:** A divergência é uma **inconsistência acidental**, não um design deliberado. `redirect_slashes=False` (global) + clients recebeu um patch de duplo-decorator que os outros nunca receberam.
- **NADA alterado.** Só leitura.

---

## 1. A história (git blame)
1. **22/03/2026** (`d775ea20`, commit "feat(people-management): 10/10..." — **não sobre rotas**): adicionado `redirect_slashes=False` em `main_production.py`. **Sem comentário/razão registrada** — entrou incidentalmente num refactor maior.
2. Isso desligou o 307 do Starlette → toda rota-raiz declarada só com `""` passou a dar **404** na variante com barra.
3. **29/03/2026** (`2876e2fa`, "feat(crm): CRM fonte oficial de clientes"): clients bateu no 404 e foi corrigido **só ele** com `@router.get("/")`.
4. proposals/opportunities/leads **nunca** receberam o patch → 404 no slash (o bug que o front bateu). O duplo-decorator existe **só em client_controller** (grep) → workaround pontual, não convenção.

## 2. Decorator da rota-raiz
| Controller | Prefix | Raiz declarada | Aceita `/`? |
|------------|--------|----------------|-------------|
| **clients** | `/clients` | `@router.get("")` **e** `@router.get("/")` (l.24-25) | ✅ sim |
| **proposals** | `/proposals` | só `@router.get("")` / `post("")` | 🔴 não → 404 |
| **opportunities** | `/opportunities` | só `""` | 🔴 não → 404 |
| **leads** | `/leads` | só `""` | 🔴 não → 404 |

## 3. `redirect_slashes`
- **`main_production.py:174` → `redirect_slashes=False`** (default do Starlette = True). Por isso **404 direto** (sem 307) na variante com barra.
- Sem comentário; adicionado em `d775ea20` (incidental).

## 4. Causa EXATA (trechos)
```python
# client_controller.py:21-25  (ACEITA OS DOIS)
router = APIRouter(prefix="/clients", ...)
@router.get("")
@router.get("/")
async def listar_clientes(...):

# proposal_controller.py:30,81  (SÓ SEM BARRA)
router = APIRouter(prefix="/proposals", ...)
@router.get("", response_model=ProposalListResponse)   # sem @router.get("/")
```
- Cadeia de include: `api/v1` → `crm` (prefix `/crm`) → `proposals` (prefix `/proposals`). `redirect_slashes` é setting do **app** → vale global.
- **Prova ao vivo (direto :8080, sem nginx):** `/api/v1/crm/proposals` → 401 (existe) · `/api/v1/crm/proposals/` → **404** (não existe) · `/api/v1/crm/clients/` → 401 (existe, pelo duplo-decorator).

## 5. nginx interfere? NÃO
- `erp.conectamais.pro`: `location /api/ { proxy_pass http://backend; }` — repasse simples, **sem** `proxy_redirect off`. O 404 **nasce no backend** (confirmado bypassing nginx). Se houvesse 307, o nginx o repassaria. nginx não é parte do problema.

## 6. Recomendação (NÃO aplicada)
| Opção | Prós | Contras / risco |
|-------|------|-----------------|
| **(A) Padronizar decorators** ⭐ — add `@router.get("/")`/`post("/")` nas raízes de proposals/opportunities/leads (espelha clients) | cirúrgico; **blast radius só CRM**; respeita a cerca; padrão já provado | toca 3 controllers; não cura o resto da API → **MENOR risco** |
| **(B) `redirect_slashes=True`** (religar global) | 1 linha; cura a API inteira (307 em qualquer mismatch) | **mudança global** em produção: 307 em todo endpoint (incl. POST/PUT/DELETE; +1 round-trip; alguns clients tropeçam); cerca posta sem razão documentada → exige **re-teste amplo** → **MAIOR** blast radius |
| **(C) nginx strip slash** | backend intocado | **camada errada** (404 é do backend); pode quebrar rotas que queiram barra; afeta todo /api → MÉDIO-ALTO |

**Recomendado: (A).** Mata o bug do CRM com o padrão existente (clients), sem mexer na cerca global. Para endurecer a **API toda**, (B) é defensável (a cerca foi incidental, não deliberada) mas deve vir com re-teste amplo — não flipar às cegas.

### Por que NÃO simplesmente flipar (B) agora
Apesar de a cerca parecer incidental, `redirect_slashes=False` afeta **todas** as rotas da API (não só CRM). Religá-lo muda o comportamento de toda a superfície em produção. O ganho (cura geral) não justifica, neste momento, o risco de regressão sistêmica sem um ciclo de re-teste. (A) entrega o objetivo imediato (CRM) com risco mínimo; (B) fica como decisão de hardening global à parte.

---

## Resumo
- clients aceita `/` porque declara `@router.get("")` **e** `@router.get("/")` (patch de 29/03 só nele). Os outros declaram só `""`. ✅
- `redirect_slashes=False` (l.174, incidental em 22/03) → sem 307 → 404 na variante com barra. ✅
- nginx não interfere (404 é backend-native). ✅
- **Fix recomendado: (A) padronizar decorators** (menor risco); (B) global só com re-teste amplo; (C) descartado.

*Read-only: grep dos decorators/prefixos, `redirect_slashes`, cadeia de include, git blame, teste ao vivo no :8080 (sem redirect), nginx. Nada alterado.*
