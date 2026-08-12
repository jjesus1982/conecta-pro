# Quarentena — `costing_controller.py`

**Decisão do Jordan em 12/08/2026.** Não é exclusão: o trabalho fica visível e o `git mv` se
desfaz numa linha.

## Por quê

1.085 linhas, **50 rotas declaradas, zero alcançáveis**. O router era incluído em
`financial_router`, mas o app monta os routers do financeiro individualmente — e este ficou
de fora. Medido: das 360 rotas de `financial_router`, as **37 únicas** que não estão no app
são todas `/api/v1/financial/costing`. Confirmado por HTTP: 404.

Pior que morto, era **armadilha**: o controller inteiro foi escrito contra uma interface CRUD
de repositório que nunca existiu (`get_multi`, `get`, `soft_delete`, `get_statistics`). São
**19 das 61 chamadas quebradas do sistema** — e nenhuma trava consegue distinguir código
morto quebrado de código vivo quebrado.

## O que NÃO foi movido, e por quê

`models/`, `repositories/`, `services/` e `schemas/` continuam onde estavam. Os modelos
registram tabelas no metadata do SQLAlchemy: tirá-los do import faria o Alembic enxergar
tabelas "sobrando" e propor DROP. Custeio ABC continua existindo como dado; o que saiu foi a
casca de API que ninguém alcança.

## Para reativar

1. `git mv` de volta para `controllers/`;
2. restaurar o import em `controllers/__init__.py` e em `costing/__init__.py`;
3. restaurar `include_router(costing_router)` em `financial/__init__.py`;
4. **e então consertar as 19 chamadas** — elas continuam quebradas. Reativar sem isso
   devolve 50 rotas em 500.
