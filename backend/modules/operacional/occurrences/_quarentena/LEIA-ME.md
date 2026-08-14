# Quarentena — camada de serviço de Ocorrências

**Movido em 13/08/2026** (ordem de fechamento T4, item F4). Não é lixo: é uma camada
de serviço que **nunca chegou a rodar uma vez sequer**, e ficava disparando a trava
`checar_repositorio` como se fosse defeito vivo no operacional.

Saíram `occurrence_service.py` e `occurrence_ai_analyzer.py`. O `services/__init__.py`
virou `__init__.py.orig` aqui do lado (não é importável de onde está).

## Por que saiu

**1. Não importa.** Provado no container:

```
modules.operacional.occurrences.services.occurrence_service     -> ImportError
modules.operacional.occurrences.services.occurrence_ai_analyzer -> ImportError
    cannot import name 'OccurrencePriority' from '...occurrences.models'
```

O nome certo é `OccurrenceSeverity`. Qualquer `from ... import OccurrenceService`
estourava na hora — o que significa que **ninguém nunca importou**: se tivesse
importado, o app não subia.

**2. Ninguém chama.** `grep` por `OccurrenceService` / `OccurrenceAIAnalyzer` /
`occurrences.services` em `modules/` e `scripts/`, fora da própria pasta: **zero**.

**3. As 16 rotas montadas não passam por aqui.** O `occurrence_controller.py` usa o
`OccurrenceRepository` **direto** (`repo.create`, `repo.list`, `repo.get_stats`) —
todos métodos que existem de verdade. Ou seja: as ocorrências funcionam, e funcionam
apesar desta camada, não através dela.

**4. É escrita contra um repositório que não existe.** 18 chamadas a 14 métodos que o
`OccurrenceRepository` (12 métodos reais) nunca teve:

| o serviço chama | o repositório tem |
|---|---|
| `list_by_tenant(...)` | `list(filters, page, page_size, post_ids)` |
| `get_next_sequence()` | — |
| `get_category_config()` / `create_category_config()` / `list_category_configs()` | — |
| `get_by_code()` | `get_by_id(...)` |
| `get_attachments()` / `delete_attachment()` | — |
| `add_comment()` / `get_comments()` / `delete_comment()` | — |
| `list_sla_breaching()` / `check_and_update_sla_breaches()` | — |
| `list_by_user()` | — |

Atinge o miolo: `create()`, `list()`, `add_comment()`, `get_dashboard_stats()`.

## ⚠️ O caminho de volta

Reativar sem consertar troca `ImportError` (barulhento, na subida) por **500 na cara do
usuário** (silencioso até alguém clicar). Para reativar:

1. `OccurrencePriority` → `OccurrenceSeverity` nos dois arquivos;
2. reescrever as 18 chamadas contra `occurrence_repository.py` — 8 dos métodos não têm
   equivalente nenhum, então é **implementar no repositório**, não renomear;
3. devolver os arquivos para `occurrences/services/` e restaurar o `__init__.py`;
4. só então ligar no controller — hoje ele não depende de nada disto.

## O que NÃO saiu, de propósito

`models/`, `repositories/`, `schemas/` e `controllers/` **ficaram**. Os modelos
registram tabelas no metadata do SQLAlchemy; tirá-los do import faria o Alembic ver
tabelas sobrando e **propor DROP**. Saiu a camada morta — o dado e as rotas ficam.

## Contexto que o Jordan precisa saber

`occurrences` tem **4 linhas, todas `cancelada`**, a última de 09/07/2026. E
`operacional/tasks.py:552,565` filtram `status IN ('aberta','em_analise')` — literais
que **não existem** na coluna. O alerta de ocorrência aberta nunca disparou e nunca
disparará. A camada de serviço estar morta não é o motivo de ninguém usar ocorrências;
é sintoma do mesmo abandono.
