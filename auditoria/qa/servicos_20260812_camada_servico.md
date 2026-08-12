# Serviços — as 78 da camada de serviço (2026-08-12)

Continuação de [servicos_20260812.md](servicos_20260812.md), que fechou 10 chamadas no
controller e deixou 78 registradas como "não feito, e por quê". Jordan mandou concluir —
**e aprender com os erros**. A segunda parte rendeu mais que a primeira.

## O que foi feito

| | |
|---|---|
| **59 renomeações puras** | o método sempre existiu com outro nome |
| **19 adaptações de assinatura** | `list_orders` recebe `ServiceOrderFilter` e devolve `(lista, total)` |
| **2 envelopes de schema** | achado NOVO, ver abaixo |
| `checar_repositorio` em serviços | **78 → 0** (sistema: 139 → 61 em 7 módulos) |

Verificação sem reiniciar produção — import isolado no container, **10 métodos sem
argumento exercitados contra o banco real**, todos OK:

```
ServiceAIService          analyze_all_services · analyze_order_patterns · get_executive_dashboard
                          get_order_stats · get_service_catalog_stats · get_service_recommendations
                          get_sla_dashboard · identify_bottlenecks
ServiceManagementService  get_orders_at_risk · get_overdue_orders
```

## O erro que mais ensinou: o verde incompleto

Com as 78 renomeações prontas, `checar_repositorio` disse **`services: 0`**. E o dashboard
executivo continuava estourando:

```
AttributeError: 'dict' object has no attribute 'total_services'
```

`get_service_catalog_stats()` está anotado `-> ServiceCatalogStats`, devolve o **dict cru**
do repositório, e quem consome faz `catalog_stats.total_services`. A anotação já dizia o
contrato; o código é que não o cumpria. `get_order_stats` tinha o gêmeo.

**A lição:** *"o método existe"* não é o contrato inteiro. **Existe e devolve outra forma
quebra igual** — e a trava que eu tinha acabado de escrever não enxergava isso. Verde de
trava incompleta é pior que vermelho, porque encerra a investigação.

### A trava ganhou um segundo olho

`checar_repositorio.py` agora roda **duas**:

| Trava | Pergunta |
|---|---|
| 1 | o método existe no repositório? |
| 2 | o método anotado `-> Schema` devolve o **dict** do repositório sem envelopar? |

A trava 2 só acusa quando o repositório devolve **dict literal** — repositório que devolve
objeto do ORM é legítimo e comum, e acusar isso seria ruído.

**Provada contra o estado real**, não contra um exemplo inventado: reconstruí o estado
intermediário (renomeado, sem envelope) e medi:

```
trava 1 (método não existe): 0   <- era isto que dizia VERDE
trava 2 (forma errada):      2   <- get_service_catalog_stats, get_order_stats
```

Sistema inteiro hoje: **0 contratos de forma quebrados** (os 2 eram estes).

Terceiro defeito de tabela junto: `checar_regressao` contava só a trava 1 (lia
`"N chamada(s)"`). Teria deixado passar exatamente os 2 casos. Agora `checar_repositorio`
imprime uma linha canônica `TOTAL:` que soma as duas.

## O outro achado: o modelo não é o que o código pensa

Três campos usados pela camada de serviço **não existem nos modelos**:

| Campo | Modelo |
|---|---|
| `ativo` | `ServiceOrder` |
| `is_default`, `contract_id` | `SLAConfig` |
| `is_available` | `ServiceCatalog` |

Não é só API de repositório errada — é **modelo de dados diferente**. O caso mais visível:
`_get_applicable_sla` tinha cascata de 4 níveis (cliente → contrato → serviço → padrão);
os níveis de contrato e padrão dependiam de colunas inexistentes. Reduzida a 2 níveis reais,
com `logger.info` nomeando a lacuna — **filtro descartado em silêncio é pior que filtro
ausente**, porque o chamador acha que filtrou.

## Erro meu, registrado

Instanciei `ServiceAIService(ServiceRepository(db))` no teste; o construtor recebe `db`.
Resultado: `AttributeError: 'ServiceRepository' object has no attribute 'query'` — que
parecia defeito do código e era do meu arreio. Peguei antes de reportar.

**Regra que fica: erro de teste imita defeito. Antes de acusar o código, prove o arreio.**

## Veredito por lente

| Lente | Status | Evidência |
|---|---|---|
| **DADO** | ⚠️ parcial | 10 métodos exercitados contra o banco; **as tabelas estão vazias** (0 ordens, 0 execuções) — prova que resolve, não que a listagem está certa |
| **TELA** | 🚫 pendente do bake | as mudanças eram `docker cp` (volátil); bake em curso. Rotas `/services/analytics/*` a reconferir depois |
| **CÓDIGO** | ✅ | compila e importa; `checar_repositorio` serviços 78→0; trava nova com self-check e prova contra o estado real |

## Não coberto

- Métodos que **exigem argumento** — sem dado nas tabelas, não há como exercitar de verdade.
- Navegador real.
- Os **61 restantes** em 7 módulos (`financial` 19, `operacional` 17, e outros 5). Ficam na
  linha de base: dívida velha não vira ruído, dívida nova acusa.
