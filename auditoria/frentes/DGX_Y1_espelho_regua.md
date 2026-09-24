# DGX Y1 — O espelho LEGAL na régua única (24/09/2026)

**Frente:** Y1, onda 7 · **Branch:** `dgx/y1-espelho-regua-unica` · **Módulo:** ponto
**Continuação de:** `DGX_V1_plantao_um_dia.md` (a régua), `DGX_W1_gemeo_noturno.md` (o pareador
canônico) e `DGX_X4_pareador_unico.md` §7.2 (que mediu este quarto pareador e o deixou declarado).

**O defeito:** `hr/services/espelho_service.py` é o motor do espelho de ponto **LEGAL** — o PDF
que o colaborador assina, que entra no kit do GEDEON e vai à homologação. Ele tinha régua
**própria** para dizer a que dia um turno pertence: agrupava pares de batida por gap < 180 min
(`INTRA_SHIFT_GAP_MAX`) e datava o turno na **1ª entrada**, sem olhar a janela de `shifts`.
Folha, fechamento e tela do DP já falavam a régua única desde a V1/W1/X4.

**A regra afirmada:** o dia de um turno é a data de INÍCIO do plantão (`shifts.shift_date`);
toda batida entre início−tolerância e fim+tolerância é dele. Vale nos QUATRO caminhos.

**O que isso custava, em uma linha:** o documento trabalhista acusava **falta em dia
trabalhado**. Caso de escola no §1c.

---

## 1. Medição ANTES

### 1a. Quem lê o produto do `espelho_service` — rastreado por grep até a ponta

**Quem CHAMA o motor** (`calcular_espelho` / `fechar_mes`) — todos por import TARDIO dentro da
função, nenhum aparece em grep de import no topo:

| # | Chamador | O que chama | Entrada | Vivo? |
|---|---|---|---|---|
| 1 | `hr/controllers/espelho_ponto_controller.py:80` | `fechar_mes` | `POST /api/v1/people-management/hr/ponto/fechar-mes` — as ações **Recalcular** (`fechar=false`) e **Aprovar** (`fechar=true`) da tela `fechamento-ponto` (`departamento_pessoal.py:1202,1223,4644`) | **sim** — único ponto de entrada do fechamento do espelho |
| 2 | `ponto/controllers/punch_controller.py:349` | `calcular_espelho` (fallback quando não há linha) | `GET /people-management/ponto/espelho/{id}` — e é a rota da tool MCP **`espelho_ponto`** | **sim** |
| 3 | `employee_portal/.../self_service_controller.py:1543` | `calcular_espelho` | `GET /portal/self-service/meu-espelho/{mes}/{ano}/pdf` — o **Meu Espaço** do colaborador | **sim** |
| 4 | `folha/services/gerar_docs_mes_service.py:86` | `calcular_espelho` | ação `gerar-docs-mes` do redesign + disparo ao **publicar holerite** (`dp_payslips_controller.py:287`) | **sim** |
| 5 | `espelho_service.fechamento_status` | — | **zero chamadores no repositório inteiro** | **morto** |

**Quem LÊ `time_sheets`** (o que o motor grava) — por destino:

| Destino | Onde | Campos | Vivo? |
|---|---|---|---|
| **PDF assinado** | `hr/services/espelho_ponto_pdf.py:133` via `espelho_ponto_service.ler_espelho`; rota `GET /hr/ponto/espelho/{id}/{mes}/{ano}/pdf`; lote `ponto/cartao_lote.py` (tela `cartao-ponto-lote`) | todos | **sim** |
| **Kit GEDEON** | `gedeon/services/ponto_kit_service.py:80` (`espelho_pdf_do_mes`) e `:107` (`arquivar_ponto_proprio`), etapa `"ponto"` do `kit_orchestrator.py:284`; `ged/services/kit_builder_service.py:455` | dict completo do `ler_espelho` | **sim** |
| **Homologação / assinatura** | `signatures/services/universal_signature_service.py:1496` **escreve** `approved_by_employee`; `espelho_ponto_service.garantir_homologacao_espelho` / `solicitar_homologacao_mes`; tela `espelho-solicitar-homologacao` | `id`, `status`, `approved_by_employee` | **sim** |
| **Portal do colaborador** | `self_service_controller.py:1554` | idem + carimbo de signatários | **sim** |
| **eSocial** | — | **nenhum**: `grep -rn "time_sheets\|TimeSheet" modules/government_integrations/` → 0. O «espelho» de lá é de EVENTOS transmitidos (`esocial_eventos_espelho`), homônimo | não se aplica |
| **MCP** | `espelho_ponto`, `painel_espelho_ponto`, `baixar_espelho_ponto_pdf` (registradas em `mcp-server/server.py`); orquestrador IA `tools_rh_doc._espelho_render`, `tools_self._totais_do_espelho` | horas, extras, noturno, faltas, status | **sim** |
| **Telas do redesign** | `fechamento-ponto` (`departamento_pessoal.py:3318`, SQL cru), `ponto-reaberturas`/`ponto-reabrir-mes` (`_dgx_t2_ponto.py`), `cartao-ponto-lote` (`_dgx_f7_ponto.py`), `he-classificar*` (`_dgx_w3_he_classificada.py` → `he_classificacao.py`), `banco-horas-folha*` (`_dgx_x1…` → `banco_horas_folha.py`), `atraso-conferencia`/`falta-justificada-conferencia` (`_dgx_x2…`), `feriado-trabalhado` (`_dgx_x3…`) | `daily_summary`, `hours_balance_minutes`, `overtime_*`, `unjustified_absent_days`, `dsr_lost_days`, `hourly_rate` | **sim** |
| 🔴 **FOLHA — caminho de DINHEIRO** | `folha/services/calculo_service.py:565-575` (SQL cru) | `unjustified_absent_days` → verba **1051 Faltas**; `dsr_lost_days` → verba **1053 DSR sobre Faltas** | **sim** |
| Morto | `hr/services/time_record_service.get_summary`; todo o pacote `modules/hr/time_tracking` como superfície HTTP (`time_sheet_controller.py` tem **0 rotas**) | — | não |

> **Correção de premissa em relação ao brief.** O brief diz que o espelho «não entra em
> dinheiro». **Entra.** `calculo_service` lê `time_sheets.unjustified_absent_days` e
> `dsr_lost_days` e emite as verbas 1051/1053. Por isso o paralelo cego desta frente (§3c) foi
> construído **recalculando os espelhos abertos dos dois lados** — medir a folha sem exercer
> esse caminho seria um verde cego.

### 1b. O número — staging (cópia de produção de 24/09), 160 pessoa×competência

Comparação entre o que o espelho diz (`_parear` + `_agrupar_turnos`, recontado sem gravar) e o
que a régua única diria (`horas_reais_ponto`), em 07, 08 e 09/2026.

**ESPELHOS ASSINADOS / HOMOLOGADOS / FECHADOS — não podem mudar (18 medidos, todos de 07/2026)**

| competência | pessoas | divergentes | Σ\|Δ\| dias | Σ\|Δ\| horas |
|---|---:|---:|---:|---:|
| 07/2026 | 18 | 4 | **11** | 133,16 |

| colaborador | espelho dias | régua dias | espelho h | régua h |
|---|---:|---:|---:|---:|
| RENE RICARDO CRUZ GONÇALVES | 5 | **13** | 54,52 | 150,57 |
| ALEXANDRE SOUZA DA SILVA | 0 | **2** | 0,00 | 24,17 |
| ANILSON JOSE SEIXAS NEVES | 14 | **13** | 128,18 | 135,17 |
| JONHATA DINIZ BENAION | 11 | **11** | 108,57 | 102,62 |

**ESPELHOS ABERTOS (142 medidos)**

| competência | pessoas | divergentes | Σ\|Δ\| dias | Σ\|Δ\| horas |
|---|---:|---:|---:|---:|
| 07/2026 | 38 | 11 | **10** | 152,07 |
| 08/2026 | 53 | 45 | **56** | 847,54 |
| 09/2026 | 51 | 35 | **13** | 343,18 |

Os piores (espelho × régua, dias):

| colaborador | comp. | espelho | régua | espelho h | régua h |
|---|---|---:|---:|---:|---:|
| ANTONIO DINIZ ASSIS DOS SANTOS | 08/2026 | 8 | **14** | 105,75 | 168,11 |
| EDWARD JOSÉ ATENCIO DOMINGUEZ | 08/2026 | 9 | **14** | 110,34 | 168,30 |
| AILTON CÉSAR VASCONCELOS | 08/2026 | 9 | **13** | 107,58 | 156,08 |
| RENE RICARDO CRUZ GONÇALVES | 08/2026 | 11 | **14** | 131,17 | 167,32 |
| MALAQUIAS PEREIRA FERREIRA | 08/2026 | 22 | **25** | 128,10 | 167,15 |
| ADAILSON SERRA ALVES | 08/2026 | 12 | **15** | 132,59 | 175,72 |
| EDWARD JOSÉ ATENCIO DOMINGUEZ | 07/2026 | 12 | **10** | 147,62 | 120,02 |

> **Honestidade sobre este Σ.** A maior parte dele **não é do dia** — é de **par** e de
> **fonte**. O espelho aplica `_uma_fonte_por_dia` (no dia em que a pessoa bateu no app, a grade
> importada do Tangerino sai do pareamento) e respeita `punch_type` estritamente; a régua única
> usa TODAS as batidas e ignora o tipo. São duas réguas diferentes, e nenhuma delas é o alvo
> desta frente. O que a Y1 corrige é **só o dia**, e o §3b isola exatamente isso.

### 1c. 🔴 O caso de escola — ADAILSON SERRA ALVES, 01→02/09/2026

Escala lançada: `shifts` em **01/09, 19:00→07:00** (noturno). Batidas do plantão:

```
01/09 19:00  entrada  (tangerino — grade)
02/09 00:00  entrada  (mobile — app)      ← as duas do app descartam as do Tangerino no dia 02
02/09 01:04  saida    (mobile — app)
02/09 07:00  saida    (tangerino — grade)
```

| | régua ANTERIOR | régua Y1 |
|---|---|---|
| turno | datado **02/09** | datado **01/09** |
| dia 01/09 no espelho | «dia de escala sem nenhuma batida» → **FALTA injustificada** | dia trabalhado |
| `unjustified_absent_days` de 09/2026 | **3** | **2** |

**A folha de ponto assinada dizia que ele faltou num dia em que trabalhou.** E `faltas_dias`
sai pela rota viva `GET /ponto/espelho/{id}` (tool MCP `espelho_ponto`) e pelo PDF do kit.

---

## 2. O que o DGX tem

O DGX trata o **plantão** como a unidade do apontamento: a folha de ponto informa plantões
cumpridos, não datas civis de batida. É a régua de `DGX_F3_tipos_beneficio.md` /
`FRENTE_03_beneficio_ponto.md`, que a V1 escreveu, a W1 levou ao pareador canônico, a X4 à tela
do DP — e que aqui chega ao **documento legal**.

---

## 3. O que foi feito (1 arquivo tocado, 2 arquivos novos — 61 linhas a mais, 19 a menos)

> **Dois commits, de propósito.** `espelho_service.py` nunca tinha passado pelo `ruff-format`
> do pre-commit, e qualquer commit que o toque é obrigado a reformatá-lo inteiro (213 linhas de
> re-quebra) — isso enterraria as 60 linhas que importam. O commit `afb36fbbc` é **só forma**
> (`ruff format` + o `N814` pré-existente do `ZoneInfo as _ZI`, que bloqueava o hook); o commit
> seguinte é a mudança de comportamento, e o `git show` dele mostra exatamente o diff abaixo.

**`backend/modules/people_management/hr/services/espelho_service.py`** — reuso, nada de régua
nova. `dia_do_plantao`, `janelas_de_turno` e `SQL_TURNOS_JANELA` são de `horas_service`.

- `_agrupar_turnos(pares, janelas=None)` — o miolo. Cada par nasce com
  `dia_do_plantao(entrada, janelas, ultimo)`; pares consecutivos com o **mesmo dia de plantão**
  são o mesmo turno, e o turno é datado nesse dia (antes: data civil da 1ª entrada).
  `ultimo = (saída, dia)` mantém a continuidade na virada — a mesma mecânica do `parear_batidas`.
- `_janelas_de_turno(db, employee_id, mes, ano)` — uma consulta, a **mesma** `SQL_TURNOS_JANELA`
  da folha, na mesma janela de spill das batidas (mês ± 24h). Falha em silêncio devolvendo `[]`
  (sem janela a régua cai no dia civil, que é o que o espelho fazia sempre — nunca piora nada).
- `calcular_espelho` passa as janelas: **uma linha**.
- `INTRA_SHIFT_GAP_MAX = 180` **apagado**. Quem agrupa agora é `dia_do_plantao`, e lá o mesmo
  corte de 3h é `INTERVALO_MAX_H`. Uma régua só — e o item (e) do oráculo trava a volta dele.
- Docstring do módulo (item 1 das FÓRMULAS) reescrito para a régua nova.

`calculo_service.py`, `horas_service.py`, `alembic/`, `frontend/` e `checar_regressao.py`
**não foram tocados**. Nenhuma DDL, nenhum `_ensure`, nenhuma tela nova.

Telas afetadas (já existentes, só passam a mostrar o dia certo):
`/redesign/departamento-pessoal?t=fechamento-ponto`, `?t=cartao-ponto-lote`,
`?t=he-classificar`, `?t=banco-horas-folha`, `?t=atraso-conferencia`, `?t=feriado-trabalhado`,
o PDF do espelho e o Meu Espaço do colaborador.

### 3a. Prova (a) — nenhum espelho assinado/homologado/fechado é reescrito: **0 de 19**

Item (c) do oráculo: relê os **19** protegidos campo a campo (27 colunas, incluindo
`pending_issues`, `daily_summary`, `extra_metadata` e `last_calculated_at`), roda
`calcular_espelho(force=True)` em **cada um** e relê. **0 alterados.** A guarda é anterior à
frente (`calcular_espelho` sai por `_resumo_do_timesheet` quando o espelho está protegido) —
esta frente a **confirma**, não a cria.

Os 19 são os mesmos que a X4 listou: 18 de 07/2026 homologados pelo colaborador
(`approved_by_employee`) + 1 fechado.

### 3b. Prova (b) — paralelo cego dos espelhos ABERTOS, verba a verba

`calcular_espelho` rodado **duas vezes no mesmo processo** sobre cada espelho aberto de 07, 08 e
09/2026 — uma com a régua anterior, outra com a régua única — sempre com ROLLBACK. Só quem muda
aparece. **142 espelhos abertos medidos, 7 mudaram.**

| competência | abertos | mudaram | campos que se moveram (Σ\|Δ\|) |
|---|---:|---:|---|
| 07/2026 | 38 | **0** | — |
| 08/2026 | 53 | **5** | esperado 3.780 min · saldo 3.780 · HE 50% 725 · atraso 915 · intervalo 2.230 · dias 6 |
| 09/2026 | 51 | **2** | esperado 1.140 min · saldo 1.140 · HE 50% 119 · atraso 841 · intervalo 235 · dias 1 · **faltas 1** |

| comp. | colaborador | o que mudou |
|---|---|---|
| 08/2026 | ADEILSON DINIZ DEODATO | esperado 15.180→14.520 · saldo −7.347→−6.687 · HE50 206→866 · intervalo 480→1.210 · dias 12→11 |
| 08/2026 | ERIKA CRISTINA MAQUINE PEREIRA | esperado 9.900→9.240 · saldo −2.879→−2.219 · atraso 287→44 · intervalo 615→857 · dias 12→11 |
| 08/2026 | JONHATA DINIZ BENAION | esperado 11.220→9.900 · saldo −2.393→−1.073 · HE50 176→241 · intervalo 534→1.247 · dias 17→15 |
| 08/2026 | MATHEUS HENRIQUE CABRAL DA SILVA | esperado 9.900→9.240 · saldo −2.633→−1.973 · atraso 893→533 · intervalo 515→869 · dias 14→13 |
| 08/2026 | PAULO DA SILVA LAMEGO | esperado 10.560→10.080 · saldo −743→−263 · atraso 3.096→2.784 · intervalo 1.012→1.203 · dias 25→24 |
| 09/2026 | **ADAILSON SERRA ALVES** | esperado 8.580→7.920 · saldo −2.638→−1.978 · atraso 15→316 · **faltas 3→2** · anomalias 8→7 |
| 09/2026 | GRACIENE PEREIRA DE CASTRO | esperado 9.840→9.360 · saldo −4.247→−3.767 · HE50 150→269 · atraso 2.508→1.968 · intervalo 312→547 · dias 17→16 |

**`hours_worked_minutes` e `night_hours_minutes` não se movem em NENHUM dos 142** — e isso é por
construção: as horas trabalhadas são a soma da duração dos pares e o noturno é medido par a par;
a Y1 só muda a que TURNO cada par pertence. O que se move é o que depende do agrupamento:
o **esperado** (660 min por turno, e dois turnos onde havia um plantão cobravam 1.320), o
**saldo**, a **HE**, o **atraso** (comparado contra o horário planejado do dia certo), o
**intervalo** e o **dia**.

### 3c. Prova (c) — a folha não muda: **Σ|Δ| = R$ 0,00**

Três medições, no mesmo processo, sempre com ROLLBACK, sobre os **167 holerites gravados** de
07+08+09/2026 (`hr_payslips`, status ≠ cancelled), verba a verba e líquido a líquido:

| # | o que compara | Σ\|Δ\| |
|---|---|---:|
| **(1)** | régua anterior × régua Y1, **sem** recalcular espelho — o que acontece no bake | **R$ 0,00** |
| **(2)** | régua anterior × régua Y1, **com os espelhos abertos recalculados dos dois lados** — o clique «Recalcular» do DP | **R$ 0,00** |
| (3) | espelho GRAVADO hoje × espelho recalculado (qualquer régua) — **não é da Y1**, está aqui só para o §7 | R$ 3.572,52 |

A medição **(2)** é a que importa, porque é ela que exerce o caminho de dinheiro (verbas
1051/1053 saem de `time_sheets`). Conferido que o recálculo **acontece dentro da transação**
(ADAILSON 09/2026: `work_days_worked` 6→10 no banco, dentro da transação) — um R$ 0,00 obtido
sem o recálculo teria sido verde cego.

A medição **(3)** é o **drift do que está gravado**: os espelhos de 09/2026 foram calculados em
algum dia do mês, com o corte de falta em «hoje». Recalculá-los hoje já mudaria a folha em
R$ 3.572,52 — **com ou sem a Y1**, e a prova disso é que (2) dá R$ 0,00. Está no §7.

---

## 4. Oráculo — `backend/scripts/orq/test_oraculo_y1_espelho_regua.py`

```bash
ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\n' ' ')
docker run --rm --network conecta-staging-network -v "$PWD/backend:/app:ro" \
  --tmpfs /app/logs:rw,mode=1777 --tmpfs /app/uploads:rw,uid=999,gid=999 \
  -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env \
  -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \
  conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_y1_espelho_regua.py
```

**VERMELHO** (árvore-base d81cbc661, `espelho_service.py` restaurado com `git checkout`):

```
(a) 3 plantões noturnos, intervalo de 1h (gap < 180 min — a régua anterior já agrupava) — dias: folha 3 · fechamento 3 · espelho 3 (régua anterior daria 3) · tela do DP 3 · horas: 33.0 / 33.0 / 33.0 / 33.0
(a) 3 plantões noturnos, intervalo de 3h30 (gap > 180 min — a régua anterior partia o plantão) — dias: folha 3 · fechamento 3 · espelho 6 (régua anterior daria 6) · tela do DP 3 · horas: 25.5 / 25.5 / 25.5 / 25.5
(b) pessoa×competência com batida em 07+08+09/2026: 155 · turnos do espelho fora do dia do plantão: 5
    (b) ANILSON JOSE SEIXAS NEVES 07/2026: turno datado 2026-07-09 (entrada 09/07 03:20) devia ser 2026-07-08
    (b) RENE RICARDO CRUZ GONÇALVES 07/2026: turno datado 2026-07-02 (entrada 02/07 01:54) devia ser 2026-07-01
    (b) ADEILSON DINIZ DEODATO 08/2026: turno datado 2026-08-31 (entrada 31/08 06:01) devia ser 2026-08-30
    (b) JONHATA DINIZ BENAION 08/2026: turno datado 2026-08-19 (entrada 19/08 01:00) devia ser 2026-08-18
    (b) ADAILSON SERRA ALVES 09/2026: turno datado 2026-09-02 (entrada 02/09 00:00) devia ser 2026-09-01
(c) espelhos protegidos (assinado/homologado/fechado): 19 · reescritos: 0
(d) folha 07+08+09/2026 régua Y1 × anterior (com os espelhos abertos recalculados dos dois lados): 167 holerites gravados · Σ|Δ| verba a verba R$ 0.00
(e) espelho_service usa as primitivas da régua única: False · tem corte de gap próprio: True
FALHOU: (a) intervalo de 3h30 (gap > 180 min — a régua anterior partia o plantão): os quatro caminhos não contam o mesmo plantão — folha 3, fechamento 3, espelho 6, tela 3, esperado 3
FALHOU: (b) 5 turno(s) do espelho fora do dia do plantão
FALHOU: (e) espelho_service deixou de usar dia_do_plantao/janelas_de_turno da régua única
FALHOU: (e) espelho_service voltou a ter um corte de gap próprio (INTRA_SHIFT_GAP_MAX)
TOTAL desvios: 4
```

**VERDE** (com a correção):

```
(a) 3 plantões noturnos, intervalo de 1h (gap < 180 min — a régua anterior já agrupava) — dias: folha 3 · fechamento 3 · espelho 3 (régua anterior daria 3) · tela do DP 3 · horas: 33.0 / 33.0 / 33.0 / 33.0
(a) 3 plantões noturnos, intervalo de 3h30 (gap > 180 min — a régua anterior partia o plantão) — dias: folha 3 · fechamento 3 · espelho 3 (régua anterior daria 6) · tela do DP 3 · horas: 25.5 / 25.5 / 25.5 / 25.5
(b) pessoa×competência com batida em 07+08+09/2026: 155 · turnos do espelho fora do dia do plantão: 0
(c) espelhos protegidos (assinado/homologado/fechado): 19 · reescritos: 0
(d) folha 07+08+09/2026 régua Y1 × anterior (com os espelhos abertos recalculados dos dois lados): 167 holerites gravados · Σ|Δ| verba a verba R$ 0.00
(e) espelho_service usa as primitivas da régua única: True · tem corte de gap próprio: False
TOTAL desvios: 0
OK espelho na régua única: o plantão é UM dia na folha, no fechamento, no espelho LEGAL e na tela do DP; assinado intacto; folha R$ 0,00
```

**Duas fixtures, e a segunda é a que prova.** A primeira (intervalo de 1h) fica VERDE mesmo na
árvore-base: o gap de 60 min está abaixo dos 180 e a régua anterior já agrupava. Escrever só
ela teria dado um verde cego. A segunda (**19:00 → 23:00 · 02:30 → 07:00**, gap de 3h30) passa
do corte, a régua anterior partia o plantão em dois turnos e datava o segundo no dia seguinte —
6 dias para 3 plantões, enquanto folha, fechamento e tela do DP já diziam 3.

O item **(e)** é uma trava estrutural: lê o próprio `espelho_service.py` e exige que ele use
`dia_do_plantao`/`janelas_de_turno` e **não** tenha corte de gap próprio. Se alguém reintroduzir
uma régua local no espelho, o oráculo fica vermelho no mesmo dia.

O item **(b)** reconta o dia de cada par com janelas de `shifts` montadas **dentro do oráculo**
(cópia deliberada da régua) — a referência não é pedida ao serviço medido.

Fixtures `'FIXTURE DGX Y1'` apagadas ao fim — conferido no sandbox: `0|0|0|0|0` em `employees`,
`shifts`, `gp_clock_punches`, `gp_monthly_closings` e `time_sheets`.

### Vizinhos, todos verdes DEPOIS da correção

| Oráculo | Resultado |
|---|---|
| `test_oraculo_x4_pareador_unico.py` | verde · (a) 3/3/3 nas duas fixtures · (b) 0 · (c) 19·0 · (d) R$ 0,00 · (e) 8 declarados, 0 novos |
| `test_oraculo_w1_dias_trabalhados.py` | verde · (c) 167 holerites, Σ\|Δ\| R$ 0,00, informativo mudou em 25 |
| `test_oraculo_v1_plantao_e_um_dia.py` | verde · (a) 3 · (b) ADAILSON 15 × 15 plantões · (c) Σ\|Δ\| 0.0000 |
| `test_oraculo_espelho_falta.py` | verde · 153 espelhos com escala publicada, 0 com falta acima da escala |
| `test_oraculo_integracao_batimentos.py` | verde · parser 1510/671, idempotente, mês fechado trava |
| `test_ponto_pareamento.py` | verde · `TOTAL: 0 regra(s) de pareamento violada(s)` |
| `test_espelho_tela_igual_pdf.py` | **não rodado** — ele se recusa a rodar dentro de container (mede o HOST via docker); é do orquestrador |

Os números dos vizinhos são **os mesmos** que a V1, a W1 e a X4 registraram.

**Testes de unidade:** `pytest tests/people_management/hr/test_pair_punches_virada.py
tests/multicnpj_release/test_cnpj_guardrail.py` → **16 passed, 1 failed**. A falha
(`test_sem_cnpj_hardcoded_novo`) é **pré-existente** — conferido restaurando a árvore com
`git stash`: falha igual, e nada dela é deste arquivo.

**Ruff:** limpo nos dois arquivos. O `N814` pré-existente (`ZoneInfo as _ZI`) foi corrigido no
commit de forma `afb36fbbc`, porque bloqueava o pre-commit — uma linha e um uso, sem
comportamento. O oráculo foi rodado VERDE de novo **depois** do `ruff format`, com os mesmos
números (o item (e) lê o arquivo por substring; reformatar não o cega).

**HTTP:** container `teste-dgx-y1` na porta **8271**. `/health` **200** em ~65s.

| rota | resultado |
|---|---|
| `GET /api/v1/people-management/ponto/espelho/{ADAILSON}?month=9&year=2026` (rota da MCP `espelho_ponto`) | **200 · 1.471 bytes** — `faltas_dias: 2`, 6 linhas de espelho |
| `GET /api/v1/people-management/hr/ponto/espelho/{ADAILSON}/9/2026/pdf` (o PDF que vai assinado) | **200 · 39.639 bytes · application/pdf** |
| `GET /api/v1/people-management/hr/ponto/espelho/painel/9/2026` | **200 · 27.011 bytes** |

O container foi **parado e removido**.

> Nota honesta sobre o HTTP: a rota devolve o que está **gravado** em `time_sheets` (só calcula
> quando não há linha). O espelho gravado do ADAILSON é anterior; a régua nova aparece ali
> depois do «Recalcular» do DP. Por isso o §3b mede o A/B **no motor**, que é onde a régua vive.

---

## 5. O que NÃO foi feito e por quê

1. **`MAX_TURNO_H` (13h) não foi adotado no espelho.** A régua única invalida um par acima de
   13h; o espelho invalida acima de 24h (`MAX_PAIR_MIN`). Adotar as 13h transformaria pares
   longos em anomalia `par_invalido` e **removeria horas de um documento legal** — é decisão de
   dono, não de diff mínimo. §7.3.
2. **A divergência de HORAS entre o espelho e a folha continua** (Σ|Δ| de 1.476h em três meses,
   §1b). Ela não é de dia: é de **fonte** (`_uma_fonte_por_dia` descarta a grade do Tangerino no
   dia em que há batida do app; a régua única usa tudo) e de **par** (o espelho respeita
   `punch_type`, `parear_batidas` ignora). Escolher qualquer um dos dois lados muda a hora da
   FOLHA. §7.1 e §7.2.
3. **Nenhum espelho foi recalculado.** Nem em produção nem no sandbox — todo recálculo desta
   frente foi em transação com ROLLBACK. Os 19 protegidos nunca foram lidos para escrita.
4. **Produção não foi tocada.** Toda medição foi no sandbox (`conecta_pro_staging`).
5. **`checar_regressao.py` não foi editado** — a linha sugerida está no §7.6, para o orquestrador
   registrar.
6. **Os pareadores #5 a #8 da X4 §7.2** (`dashboard_service`, `time_tracking_service`,
   `fechamento_turno_service`, `departamento_pessoal.py`) continuam com régua própria. Com a Y1,
   são **4 na régua única** e 4 periféricos — nenhum deles em dinheiro.

---

## 6. Como o Jordan testa amanhã

1. **O caso do ADAILSON.** `/redesign/departamento-pessoal?t=fechamento-ponto` → 09/2026 →
   **Recalcular** ADAILSON SERRA ALVES. O dia **01/09** deve aparecer como dia trabalhado (o
   plantão que ele entrou às 19:00 e cujas batidas do app caíram depois da meia-noite), **não**
   como falta. As faltas injustificadas caem de **3 para 2**.
2. **O PDF assinado.** Baixe o espelho dele em 09/2026. A linha de **02/09 00:00 → 01:04** deve
   passar para **01/09**, junto do resto do plantão. Era essa linha solta que virava um segundo
   dia e deixava 01/09 «sem batida».
3. **Os 19 espelhos de 07/2026 homologados não podem mudar.** Abra o de ANILSON JOSE SEIXAS
   NEVES: o número gravado é exatamente o de hoje. O oráculo relê os 19 campo a campo e conta 0.
4. **O holerite não pode mudar.** Calcule 09/2026 de qualquer pessoa **antes** de recalcular
   espelho: proventos, descontos e líquido idênticos. Se um centavo se mexer sem recálculo de
   espelho, o oráculo mentiu e a frente volta.
5. **Depois de recalcular os espelhos**, aí sim a folha muda — R$ 3.572,52 em 09/2026 — e isso
   **não é da Y1**: é o espelho gravado estar velho (§7.4).

---

## 7. Decisões que só o dono pode tomar

### 7.1 — `_uma_fonte_por_dia`: a grade do Tangerino entra ou não na conta de HORAS?

O espelho descarta a grade importada no dia em que houve batida do app (defeito real, medido em
13/09: 134 de 180 anomalias de setembro eram isso). A régua única **não** descarta. Resultado:
no 01→02/09 do ADAILSON, o espelho vê um plantão de **1h04** e a folha vê **12h**. As duas
leituras são defensáveis e a diferença é de **1.476 horas** em três meses. Alinhar muda a HORA
da folha (HE 50% e adicional noturno) — decisão do dono, com paralelo cego próprio.

### 7.2 — A direção da batida: `punch_type` manda ou não? (herdado da X4 §7.1)

O espelho respeita o tipo; `parear_batidas` ignora. Continua em aberto e continua sendo o que
separa as horas dos dois caminhos. Nada mudou aqui.

### 7.3 — O teto do par: 13h (régua única) ou 24h (espelho)?

`MAX_TURNO_H = 13.0` recusa pares acima de 13h como emenda de batida faltando; o espelho aceita
até 24h e conta as horas. Unificar para 13h **tira horas** de um documento assinado; unificar
para 24h **infla o noturno** da folha. Não fiz a escolha.

### 7.4 — 🔴 Recalcular os espelhos abertos de 09/2026 mexe R$ 3.572,52 na folha — e isso é ANTERIOR à Y1

Medido (§3c item 3): a folha recalculada com os espelhos de hoje × com os espelhos recalculados
difere em **R$ 3.572,52** sobre 09/2026, em ~20 pessoas — verbas **1051 Faltas** e
**1053 DSR sobre Faltas**. Exemplos: GRACIENE PEREIRA DE CASTRO líquido R$ 858,16 → R$ 524,14;
CARLOS EDUARDO DA SILVA FAÇANHA R$ 1.023,07 → R$ 744,72; ANTONIO CARLOS CASTRO GAMA
R$ 1.210,59 → R$ 1.043,58.

**Nada disso é da Y1** — a prova é o item (2) do §3c: com os espelhos recalculados dos **dois**
lados, Σ|Δ| = R$ 0,00. O que move o dinheiro é o espelho gravado estar **velho**: 09/2026 foi
calculado em algum dia do mês, e o corte de falta (`limite_falta = min(fim do mês, hoje)`) só
enxergava os dias decorridos até ali. Quem clicar «Recalcular» em 09/2026 verá esses valores —
e o mês ainda não acabou. **Quando recalcular é decisão sua.**

### 7.5 — A trava de cobertura segura quase todo mundo, e isso é uma faca de dois gumes

`COBERTURA_MINIMA_FALTAS = 0,80`: a folha só desconta falta quando ≥ 80% das batidas do mês são
do Conecta PRO. Medido em 24/09: a casa está em **39%** (2.985 de 7.673 batidas em 07..09/2026),
e só **31 pessoa×mês** passam do corte. O ADAILSON está em **79%** — um ponto abaixo. A trava
está certa (ela impediu um desconto de ~R$ 18 mil em julho), mas significa que o espelho
corrigido **ainda não chega na folha da maioria**. Quando o rollout do ponto próprio passar dos
80%, esse caminho acorda de uma vez — e é bom que as faltas estejam certas antes disso.

### 7.6 — Linha para `checar_regressao.py` (o orquestrador registra)

```python
    # O espelho de ponto é o documento que o colaborador ASSINA. Até 24/09/2026 ele tinha régua
    # PRÓPRIA para dizer a que dia um turno pertence (gap < 180 min, datado na 1ª entrada) — e
    # por causa dela acusava FALTA em dia trabalhado: ADAILSON SERRA ALVES, 01/09/2026, plantão
    # lançado às 19:00 cujas batidas do app caíram depois da meia-noite. O oráculo afirma que
    # folha, fechamento, espelho LEGAL e tela do DP contam o MESMO plantão, que espelho assinado
    # não é reescrito e que a folha não muda um centavo. Fica vermelho se alguém reintroduzir
    # uma régua de agrupamento local no espelho.
    "test_oraculo_y1_espelho_regua.py": lambda s: _n(r"^TOTAL desvios: (\d+)", s),
```
