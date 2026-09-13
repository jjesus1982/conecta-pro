# FRENTE 4 — Grid real/contratual + Mapa de Ponto com os 5 estados

**Branch:** `frente/04-grid-mapa-ponto` · **Sessão:** `tmux-agente-04` · **Módulo:** `operacional`
**Data:** 12–13/09/2026 · **Onde foi testado:** staging (`conecta_pro_staging`) via **modo efêmero**
(porta 8204) — o `/app` do `conecta-pro-backend-staging` é bind **só-leitura** da árvore principal,
então `docker cp` para lá falha e não se testa a worktree por ele (correção do contrato §2).

---

## 1. Estado ANTES, medido

### O que não existia
| Coisa | Estado em 12/09 |
|---|---|
| Grid `real/contratual` cliente × dia | **não existia** — benchmark §9.5 marcava ❌ "a tela não existe" |
| Mapa de Ponto com 5 estados | **não existia** — só `posto_descoberto` como TIPO DE ALERTA em `operacional/communication/services/alert_service.py` |
| Régua compartilhada grade ↔ triagem | **não existia** — a triagem das 08:30 produz PROSA do Hermes; nenhuma tela consumia a mesma régua |

### Oráculos VERMELHOS (saída colada, staging)

```
$ docker exec -e PYTHONPATH=/app conecta-pro-backend-staging \
    python3 /app/scripts/orq/test_oraculo_grid_bate_com_a_triagem.py
FALHOU: tela 'mapa-de-ponto' ausente do builder do operacional (ou sem _meta)
FALHOU: tela 'grid-real-contratual' ausente do builder do operacional (ou sem _meta)
2 desvio(s): a grade/mapa não existem ainda
exit=1
```

```
$ docker exec -e PYTHONPATH=/app conecta-pro-backend-staging \
    python3 /app/scripts/orq/test_oraculo_mapa_de_ponto_5_estados.py
FALHOU: mapa-de-ponto não existe no builder do operacional: KeyError: 'mapa-de-ponto'
o mapa de ponto com os 5 estados não existe
exit=1
```

### Números do terreno (staging, 12/09)
- **833 turnos** em `shifts` no mês de 09/2026 · **29 turnos** hoje · 15 postos ativos (8 com escala).
- **13 dias-pessoa** com batida e **sem turno** na escala nos últimos 7 dias (o "fora de escala").
- **1 turno de hoje** lançado para quem a régua exclui (ADAILSON, reta final) — sem a régua, ele
  seria pintado como ausente.
- `geofence_zones`: 31 registros, **todos** com `entry_tolerance_minutes` **NULO** → a tolerância
  cai na do quadro ao vivo (15 min), e a tela **diz isso** no subtítulo.
- Tempo da rota `/redesign/data/operacional` ANTES das telas novas: **0,46–0,66 s** (quente).

---

## 2. O que foi feito, arquivo por arquivo

| Arquivo | O que é |
|---|---|
| `backend/modules/people_management/ponto/mapa_de_ponto.py` **(novo)** | A régua. `classificar(turno, batidas, tolerância, agora)` é **pura** — é o que os oráculos reproduzem. Mais `mapa_do_dia(db, dia)` e `grade_do_mes(db, ano, mês)`. |
| `backend/modules/operacional/controllers/redesign_builders/_frente_04.py` **(novo)** | Só pinta: monta as telas `mapa-de-ponto` e `grid-real-contratual` com os tipos genéricos do redesign (`table`). |
| `.../redesign_builders/operacional.py` | **2 linhas** no fim do `build()`, antes do `return out`. |
| `backend/scripts/orq/test_oraculo_grid_bate_com_a_triagem.py` **(novo)** | Grade × régua, pessoa a pessoa. |
| `backend/scripts/orq/test_oraculo_mapa_de_ponto_5_estados.py` **(novo)** | Cada estado reproduzido das fontes, hoje **e** no último dia com batida. |
| `backend/scripts/qa/checar_tela_lenta.py` **(novo, HOST)** | `TOTAL telas lentas: N` contra teto de 3 s. |
| `backend/scripts/qa/checar_at_time_zone_sem_fuso.py` **(novo, HOST)** | `TOTAL conversões erradas: N`. |

**Frontend: zero arquivos tocados.**

### UMA RÉGUA — o que exatamente é reutilizado
`mapa_de_ponto.py` **importa**, não copia:
- `coorte_ponto.SQL_NAO_AUSENTE_HOJE` — férias/afastado/reta final. Para a grade do mês existe
  `nao_ausente_em(expr)`, que troca o "hoje de Manaus" pela data de cada dia **no mesmo texto**.
  Se o texto original mudar de forma, levanta `RuntimeError` em vez de calar a exclusão.
- `presence_controller._SHIFT_ESPERADO`, `_janela_presenca`, `_janela_turno`,
  `_primeira_batida_na_janela`, `TOLERANCIA_ATRASO` — a mesma definição de turno esperado que
  `presenca_ao_vivo` aplica, que é a ferramenta que o Hermes usa na triagem.
- `punch_service._haversine` — distância ao posto.

### As decisões respeitadas
- **Tolerância do banco**, não chumbada: `geofence_zones.entry_tolerance_minutes` do posto; sem
  valor lá, a do quadro ao vivo. A tela declara qual está usando.
- **Fuso:** `gp_clock_punches.punch_timestamp` é `timestamp without time zone` guardando hora
  **LOCAL de Manaus** (convenção do `punch_service`; conferido: batida `17:02:39` com `created_at`
  `21:02:39` UTC). Por isso **não há nenhum `AT TIME ZONE` sobre essa coluna** — nem o par
  UTC→Manaus, que tiraria mais 4h.
- **Sensível é o default:** turno cuja tolerância ainda não venceu devolve `None`, é **contado**
  (`ainda não venceram 15`) e não pintado de descoberto. "Não sei" ≠ "faltou".
- **Turno de quem a régua exclui** não vira descoberto e não some: aparece no subtítulo como
  *"⚠ 1 turno(s) de gente de férias/afastada/saindo, NÃO cobrados: Adailson Serra Alves…"*.
- **Falha não cala:** a tela aparece com o erro no título em vez de sumir do menu.

---

## 3. Estado DEPOIS, medido

### Oráculos VERDES (saída colada)

```
$ docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" \
    -e PYTHONPATH=/app --env-file /opt/conecta-pro/.env $ENVS \
    conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_grid_bate_com_a_triagem.py
régua hoje: 15 turno(s) · mapa: 15 · excluídos pela régua: 1 · postos na grade hoje: 6
OK grade/mapa: a mesma régua da triagem, pessoa a pessoa; ninguém de férias/afastado cobrado
exit=0
```

```
$ ... python3 /app/scripts/orq/test_oraculo_mapa_de_ponto_5_estados.py
mapa 13/09 às 03:50 · ok=0 · atendido_com_atraso=0 · atendido_posto_incorreto=0 ·
  atendido_fora_de_escala=0 · descoberto=0 · ainda não venceram=15
dia fechado 11/09 · ok=14 · atendido_com_atraso=2 · atendido_posto_incorreto=0 ·
  atendido_fora_de_escala=12 · descoberto=12
OK mapa de ponto: só os cinco estados, e cada um se reproduz de shifts × batidas × geofence
exit=0
```

> O oráculo 2 rodou às 03:50 — nenhum turno do dia tinha vencido a tolerância. Ele saía verde
> sobre uma lista **vazia**, então passou a reproduzir também o **último dia com batida**
> (11/09), que exercitou 40 itens. `atendido_posto_incorreto = 0` é honesto: no staging as
> batidas fora do geofence caem a 4–12 km, **fora de qualquer posto**, não dentro do geofence de
> outro. O estado existe e é reproduzível; o dado do dia não o produziu.

### Rota montada e telas entregues

```
$ docker exec -e PYTHONPATH=/app teste-frente-04 python3 /tmp/f04_rotas.py
rota: ['/api/v1/redesign/data/{slug}']
telas da frente 4: ['mapa-de-ponto', 'grid-real-contratual']
```

### curl que prova o dado real

```
GRID: Grid real/contratual | 09/2026 · 8 posto(s) · real/contratual por dia · vermelho = turno
descoberto (76 no mês até hoje) · cinza = ainda não venceu · —/N = futuro
linhas: 8 | colunas: 32
  ['Condominio Do Edificio Michelangelo · Condomínio Michelangelo', '2/2','2/2','2/2','2/2','1/2','·','1/2','2/2','2/2','2/2']
  ['Condominio Ideal Flores Da Cidade · Condomínio Ideal Flores da Cidade', '4/6','7/8','6/6','8/8','3/6','4/4','2/6','8/8','6/6','7/8']
  ['Condominio Mirante Das Flores · Condomínio Mirante das Flores', '5/5','6/6','5/5','6/6','3/4','4/4','3/5','6/6','5/5','6/6']
  ['Condominio Prime Arena · Condomínio Prime Arena', '3/4','2/2','4/4','2/2','3/4','·','3/4','2/2','3/4','2/2']

MAPA: 13/09 às 03:52 · 15 turno(s) na escala · ok 0 · atraso 0 · posto incorreto 0 ·
fora de escala 0 · descoberto 0 · ainda não venceram 15 · ⚠ 1 turno(s) de gente de
férias/afastada/saindo, NÃO cobrados: Adailson Serra Alves (Residencial Laranjeiras Village
19:00) · tolerância 15 min (quadro ao vivo; banco sem valor)
```

### DESEMPENHO — teto de 3 s cumprido

```
$ QA_BASE=http://127.0.0.1:8204 python3 backend/scripts/qa/checar_tela_lenta.py
  operacional: 2.23s (106 telas) · frio 0.28s · teto 3s · ok
  departamento-pessoal: 0.66s (68 telas) · frio 1.05s · teto 3s · ok
  financeiro: 1.62s (150 telas) · frio 2.45s · teto 3s · ok
  rh: 0.11s · crm: 0.20s · gestao-de-pessoas: 0.13s · todos ok
TOTAL telas lentas: 0
```

**Tempo do módulo operacional com o mês inteiro: 2,23 s** (teto 3 s). Sem as telas novas era
0,46–0,66 s — o custo das duas é da ordem de 1,5 s, dentro do teto mas **é a maior fatia do
módulo**. Cache de 60 s em memória do processo (`_CACHE` em `_frente_04.py`) está ligado; é folga,
não necessidade, e cada worker tem o seu.

> ⚠️ A **primeira** chamada depois de subir o processo levou **78,87 s** — import dos módulos e
> pool, não a tela (a segunda deu 0,26 s). O caçador mede duas vezes e vale a segunda, de
> propósito; mas se o Jordan abrir a tela logo após um deploy, vai esperar isso **uma vez**.

### Caçador de fuso

```
$ python3 backend/scripts/qa/checar_at_time_zone_sem_fuso.py --self-check
self-check: 6/6 casos corretos

$ python3 backend/scripts/qa/checar_at_time_zone_sem_fuso.py
  modules/financial/pagamentos_diaristas_service.py:512 — `financial_pagamentos_pj.updated_at`
  modules/integrations/inter/services/payment_service.py:132 — idem
  modules/crm/controllers/growth_controller.py:1048 — `opportunities.updated_at`
TOTAL conversões erradas: 3
```

Nenhuma delas é do meu módulo e **nenhuma foi corrigida** (financial/crm são território de outras
frentes). As três estão conferidas contra o `information_schema`: as duas colunas são mesmo
`timestamp without time zone`.

---

## 4. Fiação pendente para o integrador

### `backend/scripts/qa/checar_regressao.py` — arquivo proibido para mim
Em `CACADORES_HOST` (rodam no host):

```python
    # Grade/mapa que demora é grade que o supervisor abandona (frente 4, 13/09/2026). Mede
    # GET /redesign/data/<slug> com token real contra teto de 3 s, valendo a SEGUNDA chamada.
    "checar_tela_lenta.py": lambda s: _n(r"^TOTAL telas lentas: (\d+)", s, "TOTAL telas lentas: 0"),
    # `AT TIME ZONE 'America/Manaus'` sobre coluna SEM fuso SOMA 4h (leu-se 16:32 no lugar de
    # 08:32). Cruza cada ocorrência com o information_schema. 3 dívidas na estreia.
    "checar_at_time_zone_sem_fuso.py": lambda s: _n(r"^TOTAL conversões erradas: (\d+)", s, "TOTAL conversões erradas: 0"),
```

> `checar_at_time_zone_sem_fuso.py` **precisa do Postgres** (`docker exec` no
> `conecta-pro-postgres-staging`, sobrescritível por `QA_PG`/`QA_PG_DB`) e **recusa com exit 2**
> se ele não responder — nunca sai verde por falta de medição.
> `checar_tela_lenta.py` aceita `QA_BASE` (default `http://127.0.0.1:8081`), `QA_TETO_S`, `QA_SLUGS`.

### `main_production.py` — **nada a fazer**
As telas entram pelo builder já montado (`/api/v1/redesign/data/{slug}`). Nenhum router novo.

### `celery_app.py` — **nada a fazer**. Nenhuma task nova.

### `frontend/src/app/redesign/_modules/operacional.json` — **opcional**
As telas respondem por deep-link (`/redesign/operacional?t=mapa-de-ponto` e `?t=grid-real-contratual`)
sem nenhuma edição. Para ficarem no **menu**, elas precisam entrar como abas em
`redesign_builders/_op_grupos.py` (arquivo do meu módulo, mas mexido por outras frentes — não
toquei para não colidir). Linhas sugeridas, no grupo `g-visao`:

```python
        ("grid-real-contratual", "Grid real/contratual"), ("mapa-de-ponto", "Mapa de ponto"),
```

> Atenção à ordem: `montar_grupos(out)` roda **antes** das minhas 2 linhas no `build()`. Se as
> abas forem adicionadas, mover a chamada de `_telas_04` para **antes** de `montar_grupos`, senão
> a aba nasce vazia (o helper omite tela ainda não montada).

### DDL de produção — **nenhum**
Não criei tabela nem coluna. A tolerância é lida de `geofence_zones.entry_tolerance_minutes`, que
já existe (e está nula em todos os 31 registros do staging — decisão de operação, não de código).

---

## 5. CADASTROS SUJOS ENCONTRADOS — listados, **não corrigidos**

Decisão registrada: o estado **mostra** a sujeira e o relatório lista; nenhum script escreve em
cadastro de posto ou de escala. O pré-mortem mandava "corrigir o geofence antes de pintar posto
incorreto"; o prompt decidiu o contrário, e é o conservador.

### 5.1 Geofence — batida sempre fora do posto (30 dias, só app `mobile`)

| Pessoa | Posto da batida | Fora/Total | Distância |
|---|---|---|---|
| **FRANCISCO RAMON FARIAS DE SOUZA** | Residencial Laranjeiras Village | **19/19** | 8.382–8.420 m |
| **RILEM FERREIRA DE SOUZA** | Condomínio Prime Arena | **16/16** | 4.870–4.894 m |
| **MAIARA MUNIZ DE SANTOS** | Condomínio Ideal Flores da Cidade | **8/8** | 4.817–4.841 m |
| MALAQUIAS PEREIRA FERREIRA | Condomínio Prime Arena | 17/33 | 936–1.737 m |
| MAURICIO ALVES CHAGAS | Condomínio Mirante das Flores | 11/27 | 29–10.711 m |
| KALEL SILVA DE JESUS | Condomínio Michelangelo | 5/67 | 0–5.954 m |
| OSCAR SOARES DA COSTA FILHO | Condomínio Villa dos Pássaros | 3/83 | 1–12.854 m |
| (+15 pessoas com 1–2 ocorrências isoladas) | | | |

**Leitura:** os três primeiros são **100% fora** — isso é cadastro de posto errado (ou pessoa
alocada a posto diferente do que trabalha), não indisciplina. Os de 1–2 ocorrências parecem GPS
ruim ou batida feita a caminho. Ninguém foi movido de posto por este trabalho.

### 5.2 Escala × batida — horário prometido diferente do praticado (≥3 dias, desvio médio > 30 min)

| Pessoa | Posto | Escala promete | Dias | Desvio médio |
|---|---|---|---|---|
| PAULO DA SILVA LAMEGO | Mirante das Flores | 07:00 | 22 | **+1h48** |
| CELIANE GARCIA DE SOUSA | Ideal Flores | 07:00 | 22 | +1h11 |
| GRACIENE PEREIRA DE CASTRO | Prime Arena | 07:00 | 22 | +1h04 |
| MALAQUIAS PEREIRA FERREIRA | Prime Arena | 07:00 | 20 | +1h04 |
| OSCAR SOARES DA COSTA FILHO | Villa dos Pássaros | 07:00 | 22 | +1h01 |
| KALEL SILVA DE JESUS | Michelangelo | 07:00 | 22 | +1h00 |
| GEILSON RODRIGUES DE ANDRADE | Ideal Flores | 07:00 | 23 | +1h00 |
| EDILENE SALES SOUSA | Ideal Flores | 07:00 | 19 | +1h00 |
| ANGELA LOPES MACEDO | Villa Dei Fiori | 07:00 | 21 | +1h00 |
| JAQUELINE CARLOS DOS SANTOS | Villa Dei Fiori | 07:00 | 20 | +57 min |
| ADEMIR SALUSTIANO DE SOUZA FILHO | Villa dos Pássaros | 07:00 | 22 | +57 min |
| ANTONIO CARLOS VIEIRA | Michelangelo | 07:00 | 23 | +39 min |
| DANIEL VIDAL LARROQUE | Ideal Flores | 07:00 | 14 | +51 min |
| MAURICIO ALVES CHAGAS | Mirante das Flores | 07:00 | 8 | +2h43 |
| ~~EDIWILSON CORREA MARQUES~~ | Mirante das Flores | 10:00 | 13 | ~~20h59~~ ← **artefato da consulta** |

**Leitura:** **treze pessoas com desvio de exatamente ~1h** sobre turnos que prometem 07:00 é a
assinatura do defeito de escala 1h errada, e no acervo do **staging** ele ainda está presente nos
turnos antigos do mês. Isso é dado histórico do staging, não necessariamente produção.
A linha do EDIWILSON é **falso positivo da minha consulta** (turno que cruza a meia-noite mede
mal com média de intervalos) — registrada riscada para ninguém agir sobre ela.

### 5.3 Bateu sem turno na escala (11/09) — vira `atendido_fora_de_escala`
ELEN XAVIER NUNES (4 batidas), NAILSON GARCIA GOMES (4), ANILSON JOSE SEIXAS NEVES (3),
JONILSON MARTINS DE SOUZA (2), AILTON CÉSAR VASCONCELOS (2), e mais 7 com 1 batida —
incluindo **EIDY CULIER DE CASTRO**, que a memória do projeto registra como saída negociada.
São 12 pessoas: ou a escala não foi lançada para elas, ou a pessoa cobriu turno de outro sem
substituição registrada. **Nenhuma escala foi criada por mim.**

---

## 6. O que NÃO foi feito, e por quê

1. **Nenhum cadastro corrigido** (geofence, escala, alocação) — §5. Decisão do prompt, é a
   conservadora: o estado mostra, o humano decide.
2. **`triagem_hermes.py` não foi tocada** (o prompt proíbe agora). Ela continua produzindo prosa.
   **Recomendação para quando for autorizado:** `rodar()` passar a injetar no PEDIDO o resultado
   de `mapa_de_ponto.mapa_do_dia(db)` — os cinco estados com nome, posto e horário — em vez de
   deixar o modelo redescobrir isso pelas ferramentas. Aí a régua vira uma só de verdade, e o
   oráculo 1 passa a comparar tela × triagem em vez de tela × régua.
3. **As telas não entram no menu** — depende de `_op_grupos.py`, que outras frentes estão mexendo
   (§4). Funcionam por deep-link hoje.
4. **Painel de CNH/crachá vencendo:** fora do escopo (frente 5), como o prompt determinou.
5. **`checar_regressao.py` não foi editado** — zona proibida; as linhas exatas estão em §4.
6. **Nada foi para produção.** Nenhum `docker cp`, nenhum bake, nenhum container de produção
   tocado. O `conecta-pro-backend-staging` foi reiniciado duas vezes e está no código do HEAD.

---

## 7. Como o Jordan testa amanhã

1. **Ver a grade e o mapa** (depois que o integrador publicar):
   `https://<host>/redesign/operacional?t=grid-real-contratual`
   `https://<host>/redesign/operacional?t=mapa-de-ponto`
   > Se o menu não mostrar os itens, é a fiação de `_op_grupos.py` (§4) — o link direto funciona.
2. **Na grade:** cada célula é `real/contratual` do dia. Vermelho = teve turno **descoberto**.
   Cinza = ainda não venceu a tolerância. `—/N` = dia futuro. A última coluna é o mês.
3. **No mapa:** uma linha por posto/turno de hoje, com o **horário exato da batida** e a coluna
   **"Onde"**, que diz `no posto`, `geofence de OUTRO posto · N m` ou `fora de qualquer geofence · N m`.
   É por ali que o cadastro sujo do §5.1 aparece sozinho.
4. **Conferir contra a triagem das 08:30:** abrir o mapa logo depois que o Hermes escrever no sino.
   Os nomes têm de ser os mesmos. Se divergirem, o oráculo
   `test_oraculo_grid_bate_com_a_triagem.py` fica vermelho e diz **quem**.
5. **Medir o tempo:** `QA_BASE=http://127.0.0.1:8080 python3 backend/scripts/qa/checar_tela_lenta.py`
   — tem de dizer `TOTAL telas lentas: 0`.
6. **Decisão que só o Jordan toma:** a tolerância de entrada por posto está **nula** em todos os
   `geofence_zones`. Hoje o sistema usa 15 min (a do quadro ao vivo). Se algum posto tem outra,
   é preencher `entry_tolerance_minutes` — a tela passa a respeitar sem mudar código.

---

## 8. Riscos residuais do pré-mortem que continuam

| Risco | Situação |
|---|---|
| **0.1 Sem Sentry** (`SENTRY_DSN=` vazio) | **Continua.** Exceção nas telas novas cai no log de um container que ninguém lê. Mitigado só em parte: a tela falha **visível**, com o erro no título. |
| **0.2 Saldo do LLM US$ 1,10** | **Continua** e a frente 4 herda: se o Hermes parar, a triagem some — mas **a grade e o mapa não dependem dele**, porque a régua é SQL. Isso é ganho, não solução. |
| **0.3 `docker cp` não publica** | **Não aplicável aqui** (não publiquei nada), mas vale para o integrador: as telas só existem depois do **bake**, e `checar_bake_pendente` tem de voltar a 0. |
| **4.3 Fuso** | **Coberto** pelo caçador novo, com self-check 6/6. Restam **3 dívidas** em financial/crm (§3). |
| **4.4 Tela pesada** | **Coberto** com folga (2,23 s de 3 s), mas a primeira chamada pós-deploy custa ~79 s de import. Se incomodar, é aquecer a rota no fim do deploy. |
| **4.5 Dois dos cinco estados nascem mentindo** | **Parcial, e assumido.** `atendido_posto_incorreto` e `atendido_fora_de_escala` lêem fontes sujas (§5). Os estados são reproduzíveis e honestos sobre o que a fonte diz — mas **até o cadastro ser limpo, "posto incorreto" aponta o cadastro, não a pessoa**. Está escrito na coluna "Onde", com a distância, justamente para não virar acusação. |
