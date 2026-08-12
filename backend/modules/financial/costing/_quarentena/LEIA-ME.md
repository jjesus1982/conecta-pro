# Quarentena — `costing_controller.py`

**Movido em 12/08/2026 por decisão do Jordan.** Não é lixo: é uma casca de API que
nunca chegou ao app, e ficava disparando a trava `checar_repositorio` como se fosse
defeito vivo.

## Por que saiu

As 50 rotas deste controller **nunca foram alcançáveis**. Provado por HTTP:
`/api/v1/financial/costing/cost-drivers` → **404**. O `include_router(costing_router)`
existia em `financial/__init__.py`, mas `main_production.py` monta os routers
**individualmente** — `financial_router` nunca é incluído no app. Das 360 rotas dele,
as 37 ausentes eram todas `/api/v1/financial/costing`.

E não é caso de renomeação: o controller inteiro foi escrito contra uma interface CRUD
genérica que **nunca existiu** neste módulo.

| o controller chama | o repositório tem |
|---|---|
| `get_multi(filters, skip, limit)` | `list_all(...)` |
| `get(id)` | `get_by_id(id, condominio_id)` |
| `soft_delete(id)` | `delete(obj, deleted_by)` |
| `get_statistics(cid)` | `get_stats(cid)` |
| `create(schema)` | `create(**modelo**)` — recebe modelo, não schema |
| `update(id, schema)` | `update(**modelo**)` — idem |

`create` e `update` são o caso traiçoeiro: **existem pelo nome** e estão errados pela
**forma**. Uma trava que só confere nome diria verde.

## ⚠️ O caminho de volta

Reativar sem consertar as 19 chamadas **devolve 50 rotas em 500**, não em 404 — e 500 é
pior, porque parece que funciona até alguém clicar.

Para reativar:
1. reescrever as 19 chamadas contra a interface real (`costing_repository.py`);
2. recriar `costing/controllers/__init__.py` exportando o `router`;
3. devolver as 3 linhas em `financial/__init__.py` (import, `include_router`, `__all__`);
4. **e montar `financial_router` no `main_production.py`** — sem isso continua 404,
   que é o estado de hoje.

## O que NÃO saiu, de propósito

`models/`, `repositories/`, `services/` e `schemas/` **ficaram**. Os modelos registram
tabelas no metadata do SQLAlchemy; tirá-los do import faria o Alembic enxergar tabelas
sobrando e **propor DROP**. Saiu a casca de API — o dado fica.
