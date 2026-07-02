# F-CRM.2 pré — Como buscar cliente/contato hoje (READ-ONLY)

- **Data:** 2026-06-09
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Mapear o caminho técnico real para o agente/webhook **identificar cliente** (por telefone/CNPJ) sem duplicar nem bloquear o loop async.
- **Veredito:** O padrão async correto **já existe** (agent_service/webhook). O `client_repository` é **síncrono** (não usar direto no async). Match por telefone segue **impossível por falta de dados** (tabelas vazias), não de estrutura.

---

## 1. `client_repository` — SÍNCRONO (não usar direto no async)
`modules/clients/repositories/client_repository.py`:
- `def __init__(self, db: Session)` — **ORM síncrono** (`sqlalchemy.orm.Session`).
- Busca disponível: `get_client_by_document(document)` (CNPJ), `get_client_by_code(code)`, `get_client(id)`.
- ⚠️ **Não existe `get_client_by_phone`** — exigiria método novo.
- ⚠️ Todos os métodos são `def` (sync). O agente/webhook são `async` → usar direto **bloqueia o event loop**. Opções: `run_in_executor`/sessão sync separada **ou** (melhor) query async crua no padrão abaixo.

## 2. `agent_service` — padrão async limpo (REUSAR este)
`modules/integrations/connectors/whatsapp/agent_service.py`:
- `from core.database import async_session_factory`
- `async with async_session_factory() as db: await db.execute(text("SELECT ..."))`
- É o padrão a seguir para qualquer busca nova (async, sem bridge, sem tocar no repo sync).

## 3. Webhook — ponto de extensão JÁ existe
`modules/integrations/connectors/whatsapp/controller.py`:
- `_normalize_phone(phone)` (l.182) → reduz a **só dígitos**.
- `async def _match_or_create_lead(db: AsyncSession, phone_canonical, name)` (l.192):
  - Dedup em `leads.phone` via `regexp_replace(coalesce(phone,''), '\D','','g') = :p`.
  - Cria Lead `source=whatsapp` se novo.
- ➜ **É aqui** que um "tentar casar telefone→cliente antes de criar Lead" se plugaria.

## 4. `crm_contacts` — estrutura real (para query por telefone)
| Coluna | Tipo | Obs |
|--------|------|-----|
| id | uuid | PK |
| client_id | uuid | FK→clients(id), **indexado** (`idx_crm_contacts_client`) |
| name | varchar(255) | not null |
| role | varchar(100) | |
| email | varchar(255) | |
| **phone** | varchar(20) | **sem índice** |
| **whatsapp** | varchar(20) | **sem índice** |
| is_primary | bool | |
| notes | text | |

- **Índice apenas em `client_id`** — busca por telefone hoje seria seq-scan (inócuo: **0 linhas**).

## 5. Implicações (fatos)
- **Match telefone→cliente: impossível hoje** — `crm_contacts` vazia + `clients.phone` vazio (mapeado em F-CRM pré). É **problema de DADOS**, não de estrutura.
- **Caminho async correto:** padrão `async_session_factory + text()` (como agent_service/webhook), **não** o `client_repository` síncrono.
- **Gancho de implementação:** `_match_or_create_lead` no `controller.py`.
- **Match por CNPJ:** viável (clients 100% CNPJ), mas o repo que faz isso é sync → precisaria de query async equivalente ou bridge.

## 6. DECISÕES (suas — não decidi escopo)
1. Busca async por telefone varre **`crm_contacts.phone/whatsapp` + `leads.phone`** ou só um?
2. Vale **popular `crm_contacts`/`clients.phone`** (das NFS-e/contratos) para habilitar o match, ou seguir só por **CNPJ** (agente pergunta)?
3. Se popular telefone: criar **índice** em `crm_contacts.phone`/`whatsapp` (hoje inexistente)?
4. Identificação por CNPJ: escrever query **async** equivalente ao `get_client_by_document` (recomendado) ou usar o repo sync via `run_in_executor`?

---
*Read-only: grep de assinaturas (`client_repository.py`, `agent_service.py`, `controller.py`) + `\d crm_contacts`. Nada implementado. Escopo aguardando sua definição.*
