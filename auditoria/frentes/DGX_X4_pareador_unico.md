# DGX X4 — O terceiro pareador de batidas: o espelho na régua única (24/09/2026)

**Frente:** X4, onda 6 · **Branch:** `dgx/x4-terceiro-pareador` · **Módulo:** ponto
**Continuação de:** `DGX_V1_plantao_um_dia.md` (a régua) e `DGX_W1_gemeo_noturno.md` §5.1/§7.4
(o terceiro pareador, que a W1 mediu e deixou de fora).

**O defeito:** `time_record_service._pair_punches` datava cada turno no dia **civil da entrada**.
No 12x36 noturno com intervalo, quando os dois segmentos **não se fundem** num registro só, o
pedaço depois da meia-noite virava um **segundo dia trabalhado** na tela de ponto do DP e no
resumo mensal — enquanto a folha e o fechamento, desde a W1, contam **um plantão, um dia**.

**A regra afirmada:** o dia de um turno noturno é a data de INÍCIO (`shifts.shift_date`); toda
batida entre início−tolerância e fim+tolerância é dele. Vale nos TRÊS caminhos.

---

## 1. Medição ANTES

### 1a. Quem lê `_pair_punches` — rastreado por grep até o fim do caminho

| # | Entrada | Caminho | Vivo? |
|---|---|---|---|
| 1 | `GET /api/v1/people-management/hr/time-records` | `list_records` → `_pair_punches` | **sim** — rota montada (`hr/aggregator.py:188`) |
| 2 | `GET .../time-records/{id}` e o retorno do `PATCH` | `get_by_id` / `update_record` → `_pair_punches` | **sim** — o `PATCH` é a correção de batida do DP (`gestao_de_pessoas.py:128`) |
| 3 | `POST .../time-records` (lançamento manual) | `create_manual` (não pareia) | sim, mas não passa pelo pareador |
| 4 | `TimeRecordService.get_summary` / `_calculate_summary_from_punches` | resumo mensal | **sem chamador vivo** — nenhuma rota, nenhum MCP, nenhum builder o chama; só testes |
| 5 | `TimeRecordService.get_daily` | registros do dia | **sem chamador vivo** — idem |
| 6 | `frontend/src/app/modulos/dp/ponto/page.tsx` | tela clássica | **não existe mais** (só sobrou `layout.tsx`) |

**Correção de premissa, medida e registrada.** O brief (e a W1 §5.1) diz que `_pair_punches`
alimenta o ESPELHO. **Não alimenta.** O espelho legal — o documento que o colaborador assina,
que vira PDF, entra no kit GEDEON e vai à homologação — é outro motor:
`hr/services/espelho_service.py` → tabela `time_sheets` → `espelho_ponto_service.ler_espelho`
→ `espelho_ponto_pdf` / portal / MCP. Esse é um **quarto** pareador, com régua própria, e o
brief manda declará-lo sem corrigir: está no §7.

O que `_pair_punches` alimenta é a **tela de ponto do DP** e o resumo mensal. O risco continua
existindo — o DP confere e corrige batida por essa tela, e o número que ela mostra tem de ser o
mesmo da folha —, mas ele **não** toca documento assinado. Por isso o item (c) do oráculo prova
o que o brief pediu por outro caminho: os espelhos protegidos não mudam porque `get_summary` lê
`time_sheets` quando a linha existe, e `calcular_espelho` recusa recalcular o protegido.

### 1b. O número, staging (cópia de produção de 24/09), 155 pessoa×competência

Coorte: todo ativo não-homologação com ao menos uma batida no mês. Comparação: dias e horas de
`horas_reais_ponto` (a régua única — folha e fechamento) × `_calculate_summary_from_punches`
(o espelho/tela, via `_pair_punches`).

| Competência | pessoas com batida | divergentes | **Σ\|Δ\| dias** | Σ\|Δ\| horas |
|---|---:|---:|---:|---:|
| 07/2026 | 53 | 29 | **57** | 23,95 |
| 08/2026 | 51 | 49 | **41** | 107,25 |
| 09/2026 | 51 | 44 | **64** | 61,31 |
| **total** | **155** | **122** | **162** | **192,51** |

Nominal, os piores (dias régua × dias tela):

| Colaborador | 07/2026 | 08/2026 | 09/2026 |
|---|---|---|---|
| ADAILSON SERRA ALVES | 15 × **17** | 15 × **16** | 11 × **15** |
| ANILSON JOSE SEIXAS NEVES | 13 × **17** | 16 × **21** | 11 × **15** |
| JONILSON MARTINS DE SOUZA | 11 × **13** | 13 × **20** | 7 × **12** |
| EDWARD JOSÉ ATENCIO DOMINGUEZ | 10 × **15** | 14 × **18** | 10 × **12** |
| ERIKA CRISTINA MAQUINE PEREIRA | 12 × **13** | — | 6 × **11** |
| GRACIENE PEREIRA DE CASTRO | 15 × **20** | 25 × **27** | 18 × **19** |
| ADEILSON DINIZ DEODATO | 3 × **8** | 15 × **19** | 7 × **11** |

A tela **sempre** dizia igual ou mais, nunca menos.

### 1c. Espelhos já ASSINADOS / HOMOLOGADOS / FECHADOS — **19, todos de 07/2026, NÃO tocados**

`time_sheets` vivos: 285. Protegidos (fechado/aprovado/revisado/enviado_folha, ou `closed_at`,
ou `approved_by_employee`): **19**.

| Competência | Colaborador | status | fechado | homologado pelo colaborador |
|---|---|---|---|---|
| 07/2026 | (emp `65d8573f…`, sem nome em `employees`) | fechado | sim | sim |
| 07/2026 | ADEMIR SALUSTIANO DE SOUZA FILHO | calculado | não | **sim** |
| 07/2026 | ALEXANDRE SOUZA DA SILVA | calculado | não | **sim** |
| 07/2026 | ANILSON JOSE SEIXAS NEVES | calculado | não | **sim** |
| 07/2026 | ANTONIO CARLOS CASTRO GAMA | calculado | não | **sim** |
| 07/2026 | ANTONIO DINIZ ASSIS DOS SANTOS | calculado | não | **sim** |
| 07/2026 | ANTONIO WALCICLEY PEREIRA DA SILVA | calculado | não | **sim** |
| 07/2026 | DANIEL SOUZA DOS SANTOS | calculado | não | **sim** |
| 07/2026 | DANIEL VIDAL LARROQUE | calculado | não | **sim** |
| 07/2026 | EULER FELIPE FERNANDES DA COSTA | calculado | não | **sim** |
| 07/2026 | FRANCISCO RAMON FARIAS DE SOUZA | calculado | não | **sim** |
| 07/2026 | GERNANES BINDA APARICIO | calculado | não | **sim** |
| 07/2026 | JAQUELINE CARLOS DOS SANTOS | calculado | não | **sim** |
| 07/2026 | JONHATA DINIZ BENAION | calculado | não | **sim** |
| 07/2026 | JONILSON MARTINS DE SOUZA | calculado | não | **sim** |
| 07/2026 | KELLY PATRICIA DA SILVA DE SOUZA | calculado | não | **sim** |
| 07/2026 | OSCAR SOARES DA COSTA FILHO | calculado | não | **sim** |
| 07/2026 | RENE RICARDO CRUZ GONÇALVES | calculado | não | **sim** |
| 07/2026 | VANDERLICE SANTOS DA SILVA | calculado | não | **sim** |

**Nenhum deles foi tocado** — nem por código, nem por SQL. O item (c) do oráculo relê os 19 e
compara com o que está gravado: 0 reescritos.

---

## 2. O que o DGX tem

O DGX trata o **plantão** como a unidade do apontamento: a folha de ponto informa plantões
cumpridos, não datas civis de batida. É a mesma régua de `DGX_F3_tipos_beneficio.md` /
`FRENTE_03_beneficio_ponto.md` que a V1 escreveu e a W1 levou ao pareador canônico; aqui ela
chega ao terceiro, o da tela do DP.

---

## 3. O que foi feito (1 arquivo tocado, 1 arquivo novo)

**`backend/modules/people_management/hr/services/time_record_service.py`** — reuso, nada de
régua nova. `dia_do_plantao` e `janelas_de_turno` são da V1; `SQL_TURNOS_JANELA` é da W1.

- `_registro(..., dia=None)` — o `dia` passa a vir de quem chama. Sem ele vale o dia civil da
  entrada, que é o que o método fazia sempre (e por isso o diurno não muda).
- `_pair_punches(..., janelas=None)` — quarto argumento opcional, no mesmo formato do `escalas`
  que já existia. Dentro do laço, cada registro nasce com
  `dia_do_plantao(entrada, jan_emp, ultimo)` e `ultimo = (saída, dia)` mantém a continuidade
  quando não há turno lançado — a mesma mecânica do `parear_batidas`.
- `_janelas_por_funcionario(rows)` — uma consulta por funcionário presente nas batidas, na
  janela das próprias batidas ±1 dia, com a MESMA `SQL_TURNOS_JANELA` da folha. Falha em
  silêncio devolvendo `{}` (sem janela, dia civil — nunca piora nada).
- Os 4 chamadores (`list_records`, `get_by_id`, `_calculate_summary_from_punches`, `get_daily`)
  passam as janelas.
- `_calculate_summary_from_punches` — **ponta solta não é dia trabalhado.** O laço somava
  `record_date` de TODO registro, inclusive o `inconsistencia` (batida sem par). É a mesma
  convenção do `parear_batidas`, que conta `batidas_orfas` à parte e nunca as vira dia. Era daí
  que vinha a maior parte do Σ|Δ| (ANILSON 08/2026: 21 dias no espelho para 16 plantões, sendo
  5 buracos de ponto).

`calculo_service.py`, `horas_service.py`, `espelho_service.py`, `alembic/`, `frontend/` e
`checar_regressao.py` **não foram tocados**. Nenhuma DDL, nenhuma tela nova, nenhum `_ensure`.

Telas afetadas (já existentes, só passam a mostrar o dia certo):
`/redesign/departamento-pessoal?t=ponto-registros` e a correção de batida em
`/redesign/gestao-de-pessoas`.

### Medição DEPOIS — mesma coorte, mesmo comando

| Competência | divergentes | **Σ\|Δ\| dias** | Σ\|Δ\| horas |
|---|---:|---:|---:|
| 07/2026 | 6 | **0** (era 57) | 30,94 |
| 08/2026 | 47 | **1** (era 41) | 107,24 |
| 09/2026 | 37 | **1** (era 64) | 61,27 |
| **total** | | **2** (era 162) | 192,45 |

Os **2 dias** que sobram são ADEILSON DINIZ DEODATO (08 e 09/2026) — e não são de dia: os dois
pareadores formam **pares diferentes** para ele (horas 174,01 × 161,28 e 79,67 × 67,93). É o
assunto do §7.1, que esta frente não decide.

**As horas não são alvo desta frente e não mudaram por causa dela** — a Σ|Δ| de horas é a mesma
antes e depois (192,51 → 192,45), e o §3b isola o que de fato mexeu.

### 3b. Paralelo cego do ESPELHO — a mesma competência com as duas réguas

`dia_do_plantao` neutralizada (dia civil) × régua X4, no mesmo processo, sobre o resumo mensal
de toda a coorte. Só quem muda aparece; **HE = 0,00 em todos, nos dois lados**.

| Competência | Colaborador | dias antes | dias depois | horas antes | horas depois |
|---|---|---:|---:|---:|---:|
| 07/2026 | ADAILSON SERRA ALVES | 17 | **15** | 167,08 | 167,08 |
| 07/2026 | ANDREA GONÇALVES DOS SANTOS | 15 | **14** | 151,15 | 151,15 |
| 07/2026 | ANILSON JOSE SEIXAS NEVES | 16 | **13** | 135,17 | **128,18** |
| 07/2026 | JONHATA DINIZ BENAION | 12 | **11** | 108,57 | 108,57 |
| 08/2026 | ADAILSON SERRA ALVES | 16 | **15** | 171,72 | 171,72 |
| 08/2026 | ANILSON JOSE SEIXAS NEVES | 17 | **16** | 149,83 | 149,83 |
| 08/2026 | JONHATA DINIZ BENAION | 16 | **15** | 152,13 | 152,13 |
| 08/2026 | JONILSON MARTINS DE SOUZA | 15 | **13** | 145,88 | 145,88 |
| 08/2026 | MAIARA MUNIZ DE SANTOS | 16 | **15** | 173,77 | 173,77 |
| 08/2026 | RILEM FERREIRA DE SOUZA | 15 | **14** | 149,38 | 149,38 |
| 09/2026 | ADAILSON SERRA ALVES | 13 | **11** | 100,38 | 100,38 |
| 09/2026 | ANILSON JOSE SEIXAS NEVES | 12 | **11** | 93,35 | 93,35 |
| | **Σ\|Δ\|** | | **17 dias** | | **6,98 h** |

**As 6,98h do ANILSON em 07/2026 são a única hora que se move** — e não se perdem: é o segmento
pós-meia-noite de um plantão que começou em **30/06**, que passa a contar em JUNHO, no mês em
que o plantão começou. É a mesma convenção do espelho legal (`espelho_service`: «o turno
pertence ao mês em que COMEÇA»). A régua única faz diferente na borda (conta as horas do par no
mês da ENTRADA do par e o dia no mês do plantão); a decisão de qual convenção vale está no §7.3.

### 3c. A folha não muda — R$ 0,00, com a prova dupla

- **Paralelo cego (item (d) do oráculo):** os 167 holerites gravados de 07+08+09/2026
  recalculados no mesmo processo com a régua X4 e sem ela, verba a verba e líquido a líquido —
  **Σ|Δ| = R$ 0,00**.
- **Prova estrutural:** a folha de 09/2026 calcula normalmente com `_pair_punches` **minado para
  explodir** (`AssertionError` em qualquer chamada). Líquido R$ 1.594,33, sem exceção. A folha
  não passa por este pareador — não é leitura de código, é o caminho de dinheiro rodando com o
  pareador da tela quebrado de propósito.

---

## 4. Oráculo — `backend/scripts/orq/test_oraculo_x4_pareador_unico.py`

```bash
ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\n' ' ')
docker run --rm --network conecta-staging-network -v "$PWD/backend:/app:ro" \
  --tmpfs /app/logs:rw,mode=1777 --tmpfs /app/uploads:rw,uid=999,gid=999 \
  -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env \
  -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \
  conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_x4_pareador_unico.py
```

**VERMELHO** (árvore-base 327297120, `time_record_service.py` restaurado com `git stash`):

```
(a) 3 plantões noturnos, intervalo CURTO (1h, os pares se fundem) — dias: folha 3 · fechamento 3 · espelho 3 (régua anterior daria 6) · horas: 33.0 / 33.0 / 33.0
(a) 3 plantões noturnos, intervalo longo + 14h brutas (os pares NÃO se fundem) — dias: folha 3 · fechamento 3 · espelho 6 (régua anterior daria 6) · horas: 37.5 / 37.5 / 37.5
(b) pessoa×competência com batida em 07+08+09/2026: 155 · registros do espelho com turno cobrindo a entrada e data FORA do dia do plantão: 32
(f) dias diferentes com as MESMAS horas: 33 · com horas diferentes (é do tipo da batida, não do dia — §7): 47
    (b) ADAILSON SERRA ALVES 07/2026 registro 2026-07-12 (entrada 12/07 03:00) devia ser 2026-07-11
    (b) ANILSON JOSE SEIXAS NEVES 07/2026 registro 2026-07-27 (entrada 27/07 00:07) devia ser 2026-07-26
(c) espelhos protegidos (assinado/homologado/fechado): 19 · reescritos: 0
(d) folha 07+08+09/2026 régua X4 × anterior: 167 holerites gravados · Σ|Δ| verba a verba R$ 0.00
    (d) prova estrutural: folha de 09/2026 calculou com `_pair_punches` minado: líquido R$ 1594.33
(e) pareadores de batida em backend/modules: 8 declarados (3 na régua única + 5 com régua própria, §7) · NÃO declarados: 0
FALHOU: (a) intervalo longo + 14h brutas: os três caminhos não contam o mesmo plantão — folha 3, fechamento 3, espelho 6, esperado 3
FALHOU: (b) 32 registro(s) do espelho fora do dia do plantão
FALHOU: (f) ADEILSON DINIZ DEODATO 07/2026: régua 3 × espelho 8 com as MESMAS 35.67h
… (mais 31 linhas de (f))
TOTAL desvios: 35
```

**VERDE** (com a correção):

```
(a) 3 plantões noturnos, intervalo CURTO (1h, os pares se fundem) — dias: folha 3 · fechamento 3 · espelho 3 (régua anterior daria 6) · horas: 33.0 / 33.0 / 33.0
(a) 3 plantões noturnos, intervalo longo + 14h brutas (os pares NÃO se fundem) — dias: folha 3 · fechamento 3 · espelho 3 (régua anterior daria 6) · horas: 37.5 / 37.5 / 37.5
(b) pessoa×competência com batida em 07+08+09/2026: 155 · registros do espelho com turno cobrindo a entrada e data FORA do dia do plantão: 0
(f) dias diferentes com as MESMAS horas: 0 · com horas diferentes (é do tipo da batida, não do dia — §7): 2
(c) espelhos protegidos (assinado/homologado/fechado): 19 · reescritos: 0
(d) folha 07+08+09/2026 régua X4 × anterior: 167 holerites gravados · Σ|Δ| verba a verba R$ 0.00
    (d) prova estrutural: folha de 09/2026 calculou com `_pair_punches` minado: líquido R$ 1594.33
(e) pareadores de batida em backend/modules: 8 declarados (3 na régua única + 5 com régua própria, §7) · NÃO declarados: 0
TOTAL desvios: 0
OK pareador único: o plantão é UM dia na folha, no fechamento e no espelho; assinado intacto; folha R$ 0,00
```

**Duas fixtures, e a segunda é a que prova.** A primeira (intervalo de 1h) fica VERDE mesmo na
árvore-base: o `_pair_punches` funde os dois pares num registro só quando o intervalo é ≤ 3h e o
bruto ≤ 13h, e já datava certo. Escrever só ela teria dado um verde cego. A segunda
(19:00 → 02:00 · 03:30 → 09:00, 14h brutas) passa do teto, a fusão não acontece — e era ali que
o plantão virava dois dias.

Item **(f)** afirma uma regra, não uma fotografia: **horas iguais ⟹ dias iguais**. Se os dois
caminhos chegam às mesmas horas é porque formaram os mesmos pares, e então só o DIA pode
separá-los. Onde as horas diferem, a divergência é de PAR (o tipo da batida), e fica registrada
sem reprovar — porque escolher entre as duas direções muda a hora da FOLHA, e isso é do dono.

Fixtures `'FIXTURE DGX X4'` apagadas ao fim — conferido no sandbox: `0|0|0|0` em `employees`,
`shifts`, `gp_clock_punches` e `gp_monthly_closings`.

### Vizinhos, todos verdes DEPOIS da correção

| Oráculo | Resultado |
|---|---|
| `test_oraculo_v1_plantao_e_um_dia.py` | verde · (a) 3 · (b) ADAILSON 15 × 15 plantões · (c) Σ\|Δ\| 0.0000 |
| `test_oraculo_w1_dias_trabalhados.py` | verde · (c) 167 holerites, Σ\|Δ\| R$ 0,00, informativo mudou em 25 |
| `test_oraculo_espelho_falta.py` | verde · 153 espelhos com escala publicada, 0 com falta acima da escala |
| `test_oraculo_mapa_de_ponto_5_estados.py` | verde · dia fechado 23/09: ok=21, atraso=3, posto incorreto=1, fora de escala=8, descoberto=2 |
| `test_oraculo_integracao_batimentos.py` | verde · parser 1510/671, idempotente, mês fechado trava |

Os números dos vizinhos são **os mesmos** que a V1 e a W1 registraram.

**Testes de unidade:** `pytest tests/people_management/hr/test_pair_punches_virada.py` →
**16 passed** (os 16 que existem; nenhum quebrou — eles chamam `_pair_punches` sem `janelas`,
e sem janela a régua é o dia civil, como sempre foi).

**Ruff:** `ruff check` limpo nos dois arquivos.

**HTTP:** container `teste-dgx-x4` na porta 8264. `/health` **200**;
`GET /api/v1/people-management/hr/time-records?employee_id=<ADAILSON>&date_from=2026-09-01&date_to=2026-09-30`
→ **200 · 9.311 bytes · 19 registros · 11 dias com turno fechado** (a régua única também diz 11).
A régua aparece na resposta: as batidas de **02/09 01:04 e 02/09 07:00** saem datadas em
`2026-09-01` — o dia do plantão que começou às 19:00 do dia 1º. Antes da correção elas nasciam
em `2026-09-02` e faziam o dia 2 parecer trabalhado. O container foi **parado e removido**.

---

## 5. O que NÃO foi feito e por quê

1. **O espelho LEGAL (`espelho_service.py`) não foi tocado.** É o quarto pareador, o que produz
   `time_sheets`, o PDF assinado e a homologação. O brief manda declarar, não corrigir. §7.2.
2. **As HORAS continuam divergindo** entre a tela e a folha (Σ|Δ| 192h em três meses) por causa
   de uma régua DIFERENTE da do dia: a direção por `punch_type`. §7.1 — é decisão do dono e toca
   caminho de dinheiro.
3. **`espelho_service`, `dashboard_service`, `time_tracking_service`,
   `fechamento_turno_service` e o builder `departamento_pessoal.py` continuam com pareamento
   próprio.** São oito pareadores no total, não três. §7.2.
4. **Nenhum dado foi corrigido.** Nem em produção nem no sandbox — só as fixtures, apagadas.
   Os 19 espelhos protegidos não foram lidos para escrita em momento algum.
5. **Produção não foi tocada.** Toda medição foi no sandbox (`conecta_pro_staging`).
6. **`checar_regressao.py` não foi editado** — a linha sugerida está no §7.5, para o
   orquestrador registrar.

---

## 6. Como o Jordan testa amanhã

1. **A tela de ponto do DP.** Abra os registros de ponto de **ADAILSON SERRA ALVES** em 09/2026.
   Os plantões noturnos têm de aparecer **11**, não 15 — e cada plantão numa linha só, datado no
   dia em que ele **entrou**, não no dia seguinte. Confira contra a escala: 11 plantões no mês.
2. **ANILSON JOSE SEIXAS NEVES, 08/2026.** A tela dizia 21 dias trabalhados; agora diz 16, igual
   à folha. Os 5 que sumiram eram **buracos de ponto** (batida sem par) que a tela contava como
   dia trabalhado — eles continuam aparecendo na lista como `inconsistência`, para o DP fechar.
3. **O holerite não pode mudar.** Calcule 09/2026 de qualquer pessoa: proventos, descontos e
   líquido idênticos aos de hoje. Se um centavo se mexer, o oráculo mentiu e a frente volta.
4. **Os espelhos de 07/2026.** Os 19 homologados continuam exatamente como estão — abra o de
   ANILSON e confira que o número gravado não mudou.

---

## 7. Decisões que só o dono pode tomar

### 7.1 — A direção da batida: `punch_type` manda ou não?

Esta é a divergência que **sobra**, e ela não é de dia — é de **par**. Σ|Δ| de **192 horas** em
07+08+09/2026, 90 pessoa×competência.

- `_pair_punches` (tela) tem a **regra dura**: *batida tipada `saida` não ABRE turno*. Ela
  nasceu de um defeito real (commit 5e0bbc1f): sem ela, `[saída de ontem 07:00, entrada de hoje
  19:00]` viravam 12h de trabalho **sobre o período de descanso**.
- `parear_batidas` (folha e fechamento) **ignora o tipo** por outro motivo igualmente real: as
  batidas do noturno vêm tipadas erradas com frequência, e confiar no tipo fazia o turno inteiro
  sumir — levando junto o adicional noturno.

Caso de escola, ANILSON 25–26/08/2026 (batidas 19:02, 23:10, 00:00, 01:00, 06:59):
a régua pareia `(00:00 → 01:00)` = 1h e deixa 06:59 órfã; a tela descarta a `saída` de 00:00 e
pareia `(01:00 → 06:59)` = 5h59. **A tela acerta e a folha erra** nesse dia. Em outros dias é o
contrário.

Escolher uma das duas muda a **hora da folha** — hora extra 50% e adicional noturno saem de
`horas_trabalhadas`/`horas_noturnas`. **Não fiz a escolha.** É outra frente, com paralelo cego
de dinheiro próprio.

### 7.2 — São OITO pareadores de batida, não três

Varredura estática (item (e) do oráculo: arquivo que consulta `gp_clock_punches` **e** mede a
duração de um par):

| # | Arquivo | O que alimenta | Régua |
|---|---|---|---|
| 1 | `ponto/services/horas_service.py` | folha + fechamento | **CANÔNICA** (V1/W1) |
| 2 | `folha/services/beneficio_ponto.py` | motor de benefício | usa `dia_do_plantao` (V1) |
| 3 | `hr/services/time_record_service.py` | tela de ponto do DP | usa `dia_do_plantao` (**X4**) |
| 4 | `hr/services/espelho_service.py` | **o espelho LEGAL** (`time_sheets`, PDF, homologação) | própria — turno = pares com gap < 180 min, datado na 1ª entrada |
| 5 | `ponto/services/dashboard_service.py` | banco de horas por escala | própria — pareia por `punch_type` estrito |
| 6 | `hr/services/time_tracking_service.py` | folha de ponto antiga do RH | própria — entrada+saída consecutivas |
| 7 | `operacional/services/fechamento_turno_service.py` | fechamento de TURNO (operacional) | própria — entrada/saída já agregadas no `shift` |
| 8 | `operacional/.../redesign_builders/departamento_pessoal.py` | a linha do dia na tela do redesign | própria — SQL próprio, corte de 16h |

**O #4 é o que carrega o risco que o brief descreve** (documento assinado × folha). A boa
notícia medida: ele **já** agrupa os pares de um plantão pelo gap (< 180 min) e data o turno na
**1ª entrada**, então o caso clássico do 12x36 com intervalo de 1h ele já acerta. O que ele não
tem é a janela de turno de `shifts` — com intervalo maior, ou sem o tipo certo, ele parte o
plantão. **Unificar o #4 é a próxima frente**, e ela precisa de uma medição própria: são 285
espelhos, 19 deles protegidos por assinatura.

Os #5 a #8 são réguas periféricas. Nenhuma delas entra em dinheiro hoje — mas todas são lidas
por gente, e cada uma pode dizer um número diferente para o mesmo mês da mesma pessoa.

### 7.3 — A borda do mês: o plantão pertence a que competência?

Com a X4, um turno que começa 30/06 19:00 e termina 01/07 09:00 conta **inteiro em junho** na
tela — igual ao espelho legal. A régua única faz diferente: as **horas** do par que começa em
01/07 03:30 contam em **julho**, mas o **dia** conta em junho. É a única hora que se moveu
(ANILSON 07/2026, 6,98h — §3b). Qual convenção vale para a casa é decisão do dono; alinhar
exige tocar `horas_service`, que está fora do escopo desta frente.

### 7.4 — `get_summary` e `get_daily` do `TimeRecordService` estão MORTOS

Nenhuma rota, nenhum MCP, nenhum builder os chama (§1a). O resumo mensal que a X4 corrigiu só é
exercido por teste e pelo oráculo. Ou se liga uma porta para ele, ou se apaga — mas apagar exige
o cuidado do `feedback_import_tardio_antes_de_apagar`.

### 7.5 — Linha para o `CACADORES_HOST`/oráculos de `checar_regressao.py` (o orquestrador registra)

```python
    # Um pareador de batida NOVO é uma nona régua para a mesma pergunta: quantos dias essa
    # pessoa trabalhou. Em 24/09/2026 havia OITO (DGX X4 §7.2), e três delas discordavam em
    # 162 dias sobre os mesmos três meses. O oráculo carrega a lista dos oito e fica vermelho
    # no dia em que aparecer um nono não declarado.
    "test_oraculo_x4_pareador_unico.py": lambda s: _n(r"^TOTAL desvios: (\d+)", s),
```
