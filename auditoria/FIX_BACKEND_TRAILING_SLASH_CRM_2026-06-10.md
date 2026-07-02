# Endurecimento backend CRM — aceitar trailing slash (Opção A) ✅

- **Data:** 2026-06-10
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Status:** ✅ **Corrigido.** proposals/opportunities/leads agora aceitam a rota-raiz **com E sem** barra (antes 404 com barra). Espelha o padrão de clients. `redirect_slashes` global **NÃO** tocado.
- **Arquivos:** `modules/crm/controllers/{proposal,opportunity,lead}_controller.py` · **Backups:** `*.bak-slugfix-20260610-085715`
- **Commit:** **`36e1c203`** — `fix(crm): aceita trailing slash em proposals/opportunities/leads (espelha clients, opcao A)`
- `redirect_slashes=False` (main_production.py:174) **intacto** (cerca incidental, deixada quieta). Blast radius só CRM.

---

## 1. Rotas-raiz encontradas (path "") nos 3 alvos
| Controller | Raiz declarada (antes) |
|------------|------------------------|
| proposal | `@router.post("")` (l.36) · `@router.get("")` (l.81) |
| opportunity | `@router.post("")` (l.28) · `@router.get("")` (l.73) |
| lead | `@router.post("")` (l.29) · `@router.get("")` (l.57) |
**6 rotas-raiz** (POST+GET em cada).

## 2. Como espelhei clients (decisão sobre include_in_schema)
- **clients** declara `@router.get("")` + `@router.get("/")` **puro** (sem `include_in_schema=False`, sem `response_model` — suas rotas são "bare").
- As raízes dos 3 alvos têm `response_model`/`status_code` → o irmão `/` precisa **carregar os mesmos args** para comportar idêntico.
- **Decisão (reportada):** adicionei o irmão `/` com os **mesmos args + `include_in_schema=False`**. Pequeno desvio do clients (cujo `/` é in-schema/bare), justificado: evita **operationId duplicado** no OpenAPI mantendo comportamento idêntico. Em produção o OpenAPI está desligado (`_is_production` → docs/openapi None), então é cosmético; o `include_in_schema=False` garante zero duplicação em dev.

## 3. Diff (essência — 6 linhas adicionadas)
```python
# proposal_controller.py
@router.post("", response_model=ProposalDetailResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=ProposalDetailResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
...
@router.get("", response_model=ProposalListResponse)
@router.get("/", response_model=ProposalListResponse, include_in_schema=False)
# idem opportunity_controller (OpportunityResponse/ListResponse) e lead_controller (LeadResponse/ListResponse)
```
Lógica das funções **inalterada** (só decorator extra). (Black colapsou os multiline para 1 linha — cosmético.)

## 4. Validação (direto :8080, com JWT)
| Recurso | sem barra | com barra (antes 404) |
|---------|-----------|------------------------|
| proposals | **200** | **200** ✅ |
| opportunities | **200** | **200** ✅ |
| leads | **200** | **200** ✅ |
| **clients** (não regrediu) | **200** | **200** ✅ |
- **POST com barra:** `POST /api/v1/crm/proposals/` → **201** (antes 404) — proposta de teste criada e **limpa** (proposals=0). Create-com-barra também endurecido.
- **OpenAPI:** rotas `/` adicionadas com `include_in_schema=False` → não duplicam (e prod tem openapi desligado).
- **host==container** (3 controllers) · backend **healthy** · **health 200**.

## 5. Durabilidade
- Commit `36e1c203` vive via docker cp sobre a imagem `5a14e5db` → **bakar no próximo rebuild** (1 item backend). **NÃO rebuildei.**
- Observação: como a cerca `redirect_slashes=False` continua, **novas rotas-raiz futuras** precisarão do mesmo duplo-decorator (ou um helper) — senão repetem o bug. (Hardening global via `redirect_slashes=True` segue como decisão à parte, com re-teste amplo — ver Chesterton.)

---

## Resumo
- 6 rotas-raiz (proposals/opportunities/leads, POST+GET) ganharam o irmão `@router.<verb>("/", ..., include_in_schema=False)`. ✅
- Os 4 recursos do CRM agora 200 com e sem barra; clients sem regressão; POST com barra 201. ✅
- `redirect_slashes` intocado; host==container; health 200; commit `36e1c203`. ✅
- Pendente: bakar no rebuild. Não rebuildei, não toquei redirect_slashes.

*PAREI. Não rebuildei. Não toquei redirect_slashes.*
