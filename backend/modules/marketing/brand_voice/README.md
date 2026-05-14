# Submodulo `marketing/brand_voice`

> **Status:** 🟡 Foundation (Slice 1 - Backend dinamica de leitura)
> **Branch:** `feature/marketing-brand-voice-backend`
> **Owner:** Pedro Rafael ([@PedroRafael13](https://github.com/PedroRafael13))

## Objetivo

Tornar a pagina `/modulos/marketing/brand-voice` **dinamica** — substituir o
conteudo hardcoded em `frontend/src/app/modulos/marketing/brand-voice/page.tsx`
por dados gerenciaveis no banco, por condomino.

## Estrutura

```
backend/modules/marketing/brand_voice/
├── __init__.py
├── README.md (este arquivo)
├── models/
│   ├── __init__.py
│   └── brand_voice.py             # BrandVoiceConfig (tabela marketing_brand_voice)
├── schemas/
│   ├── __init__.py
│   └── brand_voice.py             # BrandVoiceResponse, BrandVoiceUpdate, PersonalityTrait, ToneRule
├── repositories/
│   ├── __init__.py
│   └── brand_voice.py             # BrandVoiceRepository (get_by_condominio, create, update)
└── controllers/
    ├── __init__.py
    └── brand_voice.py             # router GET /marketing/brand-voice/
```

## Schema do banco (tabela `marketing_brand_voice`)

| Coluna | Tipo | Descricao |
|---|---|---|
| id | UUID | PK (BaseModel) |
| condominio_id | UUID | FK condominios.id, UNIQUE (1 brand voice por condomino) |
| personality | JSONB | `[{"label": "Profissional", "description": "..."}, ...]` |
| tone_of_voice | JSONB | `[{"title": "Formal mas acessivel", "description": "..."}, ...]` |
| keywords | TEXT[] | Lista de palavras-chave |
| avoid_list | JSONB | Lista de strings ("Linguagem agressiva", "Promessas 100%", ...) |
| slogan | TEXT | Slogan oficial |
| updated_by_user_id | UUID | Ultimo usuario que editou (lazy FK pra users.id) |
| created_at, updated_at, is_active | (BaseModel) |

## Endpoint disponivel (Slice 1)

```
GET /api/v1/marketing/brand-voice/

Auth: Bearer JWT (usuario com condominio_id)

Resposta 200:
{
  "id": "uuid",
  "condominio_id": "uuid",
  "personality": [{"label": "Profissional", "description": "..."}],
  "tone_of_voice": [{"title": "Formal mas acessivel", "description": "..."}],
  "keywords": ["seguranca", "tecnologia", ...],
  "avoid_list": ["Linguagem agressiva", ...],
  "slogan": "Conecta Mais — ...",
  "updated_by_user_id": null,
  "created_at": "2026-05-13T15:00:00Z",
  "updated_at": "2026-05-13T15:00:00Z"
}

Erros:
- 401: nao autenticado
- 404: usuario sem condominio_id OU brand voice nao existe pro condomino
```

## ⚠️ Pendencias pra deploy (Jordan precisa fazer)

### 1. Registrar router em `main_production.py`

Adicionar (perto dos outros `safe_import`):

```python
# Marketing - Brand Voice
brand_voice_router = safe_import(
    "modules.marketing.brand_voice.controllers",
    router_name="router",
)
if brand_voice_router:
    app.include_router(brand_voice_router, prefix="/api/v1")
```

### 2. Aplicar migration Alembic

Migration sera criada no proximo commit (Slice 1D). Apos merge:
```bash
alembic upgrade head
```

### 3. Seed inicial do brand voice de cada condomino

A migration vai incluir um seed com o conteudo atual da pagina hardcoded,
ja apontando pro condomino-teste (`a1b2c3d4-e5f6-7890-abcd-ef1234567890`).

Pra outros condominos, preciso criar manualmente via UI (Fase 2) ou via SQL.

## Proximas Fases

| Fase | Conteudo | Status |
|---|---|---|
| 1 (esta) | Backend dinamica de leitura (GET endpoint) | ✅ Slice 1A/B/C entregues |
| 1D | Migration Alembic + seed inicial | ⏳ Proximo commit |
| 2 | Edicao via UI (PUT endpoint + auth role-based) | ⏳ Pendente |
| 3 | Versionamento + preview de mensagem | ⏳ Backlog |

## Tests

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/modules/marketing/brand_voice/ -v
```

## Decisoes arquiteturais

- **Por condomino:** brand voice e multi-tenant (cada empresa tem o seu).
  Casa com padrao do projeto (todo modelo tem condominio_id).
- **JSONB pra listas:** flexibilidade pra adicionar campos sem mudar schema.
- **Sem FK constraints a nivel de model:** FKs sao adicionadas na migration
  pra evitar imports circulares.
- **GET aberto pra qualquer logado:** brand voice nao e secreto, todo
  funcionario consulta. PUT (Fase 2) sera restrito a admin/marketing role.
