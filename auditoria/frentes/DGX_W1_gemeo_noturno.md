# DGX W1 — O gêmeo do plantão noturno: `dias_trabalhados` do pareamento (24/09/2026)

**Frente:** W1, onda 5 · **Branch:** `dgx/w1-gemeo-noturno` · **Módulo:** folha (pareamento do ponto)
**Continuação de:** `DGX_V1_plantao_um_dia.md` §5/§7.3 — o gêmeo que a V1 mediu e deixou de fora
porque toca `calculo_service`, que é caminho de dinheiro.

**O defeito:** `horas_service.parear_batidas` atribuía cada par de batidas ao **dia civil da
entrada**. No 12x36 noturno com intervalo (19:00 → 02:00 · 03:00 → 07:00) o segmento depois da
meia-noite virava um **segundo dia trabalhado**. A V1 já tinha curado a mesma régua no motor de
benefício; aqui ela chega à fonte única do pareamento.

**A regra afirmada:** `dias_trabalhados` conta **plantões**, não datas civis de entrada. O dia de
um turno noturno é a data de INÍCIO (`shifts.shift_date`); toda batida entre início−tolerância e
fim+tolerância é dele.

---

## 1. Medição ANTES — quem lê o número, e o que muda se ele mudar

### 1a. Os leitores, rastreados por grep até o fim do caminho

| # | Quem produz | Quem lê | O que é | Vira dinheiro? |
|---|---|---|---|---|
| 1 | `calculo_service.py:419` `dias_reais` | **só** `calculo_service.py:1052`, o campo `dias_trabalhados` do dict do holerite | daí para `departamento_pessoal.py:594` → `hr_payslips.informative` (JSON) e para o PDF do holerite | **NÃO** — `dias_reais` aparece em duas linhas no arquivo inteiro (419 e 1052) e nenhuma verba o usa |
| 2 | `punch_service.fechar_mes_ponto:469` | `gp_monthly_closings.total_dias_trabalhados` | `monthly_closing.to_dict()`, `redesign_data_controller.py:3167`, `gestao_de_pessoas.py:612`, `juridico/context_engine.py:188` | **NÃO** — coluna de leitura do fechamento, nenhum cálculo a consome |
| 3 | `dashboard_service.py:474` (banco de horas) | — | usa `horas_trabalhadas`, **não** `dias_trabalhados` | não se aplica (e `horas_trabalhadas` não mudou) |
| 4 | Ferramentas MCP | nenhuma lê `dias_trabalhados` do pareamento | `espelho_ponto`/`ponto_dashboard` vão por outros caminhos | — |

**Nenhum leitor leva o número a valor pago.** As verbas de dinheiro que dependem do ponto usam
outras chaves do mesmo dicionário: horas extras 50% (`0040`) vêm de `horas_trabalhadas`, o
adicional noturno (`0020`) de `plantoes_noturnos` ou `horas_noturnas`, e VT/VR de
`dias_vt_vr(escala, …)` — escala, não ponto. Por isso a correção **prossegue**; o §7 registra o
gatilho que a mandaria parar e o oráculo o mantém armado (item (c)).

Não é suposição: o item (c) do oráculo recalcula a folha inteira de 07, 08 e 09/2026 com as duas
réguas no mesmo processo e mede **Σ|Δ| = R$ 0,00 em 167 holerites**.

### 1b. Tabela nominal — 12x36 noturna, sandbox (cópia de produção de 24/09)

Coorte: ativo, não-homologação, com ao menos um turno `planned_start_time > planned_end_time` no
mês. Só quem muda aparece.

**08/2026 — 19 ativos em 12x36 noturna**

| Colaborador | ANTES | DEPOIS | Δ |
|---|---:|---:|---:|
| ADAILSON SERRA ALVES | 31 | **15** | −16 |
| ADEILSON DINIZ DEODATO | 22 | **15** | −7 |
| ANDREA GONÇALVES DOS SANTOS | 31 | **15** | −16 |
| ANILSON JOSE SEIXAS NEVES | 29 | **16** | −13 |
| JONHATA DINIZ BENAION | 24 | **15** | −9 |
| JONILSON MARTINS DE SOUZA | 24 | **13** | −11 |
| MAIARA MUNIZ DE SANTOS | 16 | **15** | −1 |
| RILEM FERREIRA DE SOUZA | 25 | **14** | −11 |
| **Σ\|Δ\|** | | | **84** |

**09/2026 — 16 ativos em 12x36 noturna**

| Colaborador | ANTES | DEPOIS | Δ |
|---|---:|---:|---:|
| ADAILSON SERRA ALVES | 22 | **11** | −11 |
| ADEILSON DINIZ DEODATO | 13 | **7** | −6 |
| AILTON CÉSAR VASCONCELOS | 11 | **10** | −1 |
| ANDREA GONÇALVES DOS SANTOS | 23 | **12** | −11 |
| ANILSON JOSE SEIXAS NEVES | 23 | **11** | −12 |
| DANIEL VIDAL LARROQUE | 16 | **11** | −5 |
| JONILSON MARTINS DE SOUZA | 12 | **7** | −5 |
| RENE RICARDO CRUZ GONÇALVES | 12 | **11** | −1 |
| **Σ\|Δ\|** | | | **52** |

A V1 estimou 86 e 51 em §5; a diferença (84 e 52) é o filtro de coorte — ela usou a lista de 15/16
pessoas do mapa de benefício, aqui é todo ativo com turno noturno lançado no mês. O quadro é o
mesmo: o número sobrava, nunca faltava.

Nos 167 holerites gravados de 07+08+09/2026, **25** têm o campo informativo `dias_trabalhados`
alterado. **Nenhuma verba muda** (item (c)).

---

## 2. O que o DGX tem

O DGX trata o plantão como a unidade do apontamento — o holerite informa **plantões cumpridos**, e
o fechamento do ponto fecha por plantão, não por data civil de batida. É a mesma régua da V1
(`DGX_F3_tipos_beneficio.md` / `FRENTE_03_beneficio_ponto.md`), aplicada agora ao pareador
canônico, de onde a folha e o fechamento leem.

---

## 3. O que foi feito (diff mínimo: 2 arquivos tocados, 2 arquivos novos)

**`backend/modules/people_management/ponto/services/horas_service.py`** — a régua na fonte única.
Nada de novo foi inventado: `dia_do_plantao` e `janelas_de_turno` são da V1, **reusados**.

- `parear_batidas(rows, ini_mes, fim_mes, janelas=None)` — quarto argumento opcional. Dentro do
  laço, `dia = dia_do_plantao(entrada, janelas or [], ultimo)` e `ultimo = (saida, dia)` são
  calculados **antes** do filtro de mês (a continuidade tem de atravessar a virada), e só
  `dias_distintos` passa a usar `dia`. `total_min`, `noturno_min`, `pares` e `batidas_orfas`
  seguem exatamente como estavam — é por construção que o dinheiro não se mexe.
- O dia do plantão só entra em `dias_distintos` quando cai **dentro** da competência: sem isso o
  segmento de 01/08 03:00 de um plantão de 31/07 criava um dia fantasma em agosto.
- `params_turnos(p)` — três linhas, para os dois chamadores montarem os params do
  `SQL_TURNOS_JANELA` na mesma janela (mês ± 1 dia) do `params_batidas`, sem copiar a expressão.
- `horas_reais_ponto` (caminho sync — folha, dashboard) passa as janelas.
- `_self_check()` ganhou o **caso 5** (`python3 horas_service.py` → `5/5 OK`): 3 plantões noturnos
  com intervalo dão 3 dias e 33h; sem escala lançada, também 3 (continuidade); diurno com almoço
  segue 1. De quebra, o `_FakeDB` passou a ordenar como o `SQL_BATIDAS` de verdade
  (timestamp, saída antes de entrada) — ordenava pela tupla `(tipo, ts)` e embaralhava os pares.

**`backend/modules/people_management/ponto/services/punch_service.py`** — `fechar_mes_ponto`
busca os turnos pela mesma query e passa as janelas. 14 linhas.

**`backend/scripts/qa/checar_escala_paridade.py`** — caçador novo (§4b).
**`backend/scripts/orq/test_oraculo_w1_dias_trabalhados.py`** — oráculo novo (§4a).

`calculo_service.py` **não foi tocado** — a régua estava toda a montante dele. Nenhuma DDL,
nenhuma tela nova, nenhum `_ensure`. Telas afetadas (já existentes, só passam a mostrar o número
certo): `/redesign/departamento-pessoal?t=folha-holerites` e a tela de fechamento de ponto.

---

## 4. Oráculo e caçador

```bash
ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\n' ' ')
docker run --rm --network conecta-staging-network -v "$PWD/backend:/app:ro" \
  --tmpfs /app/logs:rw,mode=1777 --tmpfs /app/uploads:rw,uid=999,gid=999 \
  -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env \
  -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \
  conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_w1_dias_trabalhados.py
```

### 4a. `test_oraculo_w1_dias_trabalhados.py`

**VERMELHO** (os dois arquivos restaurados com `git show HEAD:` na árvore-base 98961d795):

```
(a) fixture 3 plantões noturnos: dias_trabalhados 6 (régua anterior daria 6) · dias_com_par 6 · horas 33.0
(d) caçador de paridade: 5 acusado(s) na janela 2026-07-01→2026-10-01 · contrafase achada: True · alinhado acusado: False
(b) pessoa×mês que não cruzam a meia-noite: 64 · Σ|Δ| dias: 0 · pessoa×mês noturnas (fora da conta, é o alvo): 36
(c) folha 07+08+09/2026 régua antiga × nova: 167 holerites gravados · Σ|Δ| verba a verba R$ 0.00 · informativo dias_trabalhados mudou em 0
FALHOU: (a) 3 plantões com intervalo deram 6 dias trabalhados — o plantão virou 2 dias
FALHOU: (a) sem escala lançada o gêmeo voltou: 6 dias para 3 plantões
TOTAL desvios: 2
```

**VERDE** (com a correção):

```
(a) fixture 3 plantões noturnos: dias_trabalhados 3 (régua anterior daria 6) · dias_com_par 6 · horas 33.0
(d) caçador de paridade: 5 acusado(s) na janela 2026-07-01→2026-10-01 · contrafase achada: True · alinhado acusado: False
(b) pessoa×mês que não cruzam a meia-noite: 64 · Σ|Δ| dias: 0 · pessoa×mês noturnas (fora da conta, é o alvo): 36
(c) folha 07+08+09/2026 régua antiga × nova: 167 holerites gravados · Σ|Δ| verba a verba R$ 0.00 · informativo dias_trabalhados mudou em 25
TOTAL desvios: 0
OK gêmeo curado: plantão noturno conta 1 dia, diurno intacto, folha sem um centavo de diferença
```

O item (c) é o **paralelo cego**: a mesma folha, no mesmo processo, com `dia_do_plantao`
neutralizado (dia civil da entrada) e com a régua nova, comparada verba a verba sobre os 167
holerites gravados em `hr_payslips` de 07, 08 e 09/2026 (07/2026 são os **publicados**; 08 e 09
estão em `draft`). Σ|Δ| = R$ 0,00 **e** o líquido de cada um bate. Se algum dia der diferente, o
número passou a ser usado em dinheiro e a correção tem de parar — está escrito no oráculo.

> **Uma régua que reprova o certo, registrada para ninguém repetir.** A primeira tentativa foi
> comparar o recálculo de hoje com o que está gravado em `hr_payslips`. Deu **R$ 196.638,08** — e
> nada disso é meu: a maior parte é a rubrica `0001` que mudou de `Salario Base` para
> `Salário Base` (com acento) entre a geração do holerite e hoje, mais recálculos de base de
> quem teve férias. Medido com a correção e **sem** ela: os dois lados dão exatamente
> R$ 196.638,08. O drift é anterior e a W1 não move um centavo dele. A prova válida é o A/B.

Fixtures `'FIXTURE DGX W1'` apagadas ao fim — conferido no sandbox: `0|0|0` em `employees`,
`shifts`, `gp_clock_punches`.

**Vizinhos, todos verdes depois da correção:**

| Oráculo | Resultado |
|---|---|
| `test_oraculo_v1_plantao_e_um_dia.py` | verde · (a) 3, (b) ADAILSON 15 × 15 plantões, (c) Σ\|Δ\| 0.0000 |
| `test_oraculo_beneficio_regra_e_dado.py` | verde · 208 linhas · `Σ\|Δ total\|: R$ 0.00` |
| `test_oraculo_espelho_falta.py` | verde · 153 espelhos com escala publicada, 0 com falta acima da escala |
| `test_oraculo_mapa_de_ponto_5_estados.py` | verde · dia fechado 23/09: ok=21, atraso=3, posto incorreto=1, fora de escala=8, descoberto=2 |

Os números dos vizinhos são **os mesmos** que a V1 registrou — a W1 não mexeu em nada deles.

**Self-check no host:** `python3 backend/modules/people_management/ponto/services/horas_service.py`
→ `horas_service: 5/5 OK`.

**Testes de unidade:** `pytest tests/people_management/ponto/test_punch_service.py
tests/people_management/hr/test_pair_punches_virada.py` → `14 failed, 57 passed`, **os mesmos 14**
na árvore-base (conferido restaurando os dois arquivos) — falhas pré-existentes de INSS/IRRF/CCT e
de `_FakeDB`, nenhuma delas minha.

**HTTP:** container `teste-dgx-w1` na porta 8251 subiu, `/health` 200 em 50s,
`GET /api/v1/redesign/data/departamento-pessoal` **200 · 6.487.767 bytes · 127 telas** — e foi
**parado**.

### 4b. Caçador `backend/scripts/qa/checar_escala_paridade.py`

Acusa 12x36 cuja escala lançada está **sistematicamente na paridade oposta** às batidas do mês — a
classe que a V1 achou: escala nos ímpares, vida nos pares. Régua: dentro de um mês, **≥ 70% das
batidas fora de toda janela de turno E ≥ 70% dos turnos lançados sem nenhuma batida**, com piso de
5 turnos e 5 batidas. Janela do turno = `[início−1h, fim+1h]`, a mesma tolerância do
`horas_service`. As duas metades juntas descrevem contrafase e só ela: quem faltou muito falha só
a segunda; quem fez hora extra falha só a primeira.

```bash
python3 backend/scripts/qa/checar_escala_paridade.py
CP_PG=conecta-pro-postgres-staging CP_BANCO=conecta_pro_staging python3 backend/scripts/qa/checar_escala_paridade.py
```

Saída no sandbox (24/09, janela 07→09/2026):

```
  ✗ ADEILSON DINIZ DEODATO       08/2026  14/15 turnos sem batida · 49/51 batidas fora de toda janela
  ✗ RILEM FERREIRA DE SOUZA      08/2026  16/16 turnos sem batida · 53/53 batidas fora de toda janela
  ✗ ADEILSON DINIZ DEODATO       07/2026  12/12 turnos sem batida · 11/11 batidas fora de toda janela
  ✗ MAIARA MUNIZ DE SANTOS       07/2026  15/15 turnos sem batida · 58/58 batidas fora de toda janela
TOTAL escalas na paridade errada: 4
```

Achou a classe (RILEM 100%/100%, ADEILSON 93%/96%) e **não** achou DANIEL VIDAL LARROQUE nem
MAURÍCIO ALVES CHAGAS em 09/2026 — medido: 30%/55% e 40%/56%. A V1 disse "o mesmo desencontro **em
parte do mês**", e meio mês não é contrafase; é o limiar fazendo o que deve. Quem chegar a 70%
aparece no mês seguinte.

**Linha a acrescentar em `CACADORES_HOST` de `backend/scripts/qa/checar_regressao.py`** (o
orquestrador registra — eu não toquei no arquivo):

```python
    # Num 12x36 a escala alterna dia sim, dia não: lançar o ciclo um dia adiantado produz uma
    # grade inteira em CONTRAFASE, e nada reclama — cada turno isolado parece plausível. Medido
    # em 24/09/2026 (DGX V1 §1 nota ¹): RILEM FERREIRA com 16/16 turnos de 08/2026 sem uma
    # batida e 53/53 batidas fora de toda janela; ADEILSON, MAIARA idem. O mapa de ponto chama o
    # posto de descoberto todo dia, a cobertura mede buraco onde há gente, e o benefício conta
    # tudo como 'fora de escala'. Quem corrige é a operação — o caçador só não deixa esquecer.
    "checar_escala_paridade.py": lambda s: _n(r"^TOTAL escalas na paridade errada: (\d+)", s),
```

---

## 5. O que NÃO foi feito e por quê

1. **`time_record_service._calculate_summary_from_punches` (o espelho) continua com a régua do dia
   civil.** Ele tem pareamento PRÓPRIO (`_pair_punches`, linhas 994 e 1151, com o comentário "mesma
   convenção de `horas_service.parear_batidas`") e devolve `total_worked_days`. Não é o gêmeo que
   o brief manda corrigir, tem chamadores diferentes (espelho de ponto / portal) e corrigi-lo
   exige medir aqueles leitores — é outra frente. Está no §7.
2. **A escala em contrafase não foi corrigida** — é dado, não código, e são dezenas de registros
   de `shifts`. "Se vai consertar muitos registros de uma vez, pare." O caçador passa a acusar;
   quem corrige a grade é a operação.
3. **`gp_monthly_closings` não foi recalculado.** As linhas já fechadas guardam o número antigo; o
   novo só entra quando o mês for fechado (ou reaberto/fechado) de novo. Decisão do dono (§7).
4. **`hr_payslips.informative` de 07/2026 (publicado) não foi tocado.** O campo informativo de 25
   holerites gravados fica com o número velho até um recálculo — e recalcular holerite publicado é
   decisão do dono, não minha.
5. **Produção não foi tocada.** Toda medição e todo recálculo foram no sandbox
   (`conecta_pro_staging`). O container `teste-dgx-w1` (porta 8251) foi parado.

---

## 6. Como o Jordan testa amanhã

1. **O holerite.** `/redesign/departamento-pessoal?t=folha-holerites` → calcular 09/2026 para
   ADAILSON SERRA ALVES. O campo informativo **Dias trabalhados** deve dizer **11** (plantões), não
   22. Confira contra a escala dele no mês: 11 plantões noturnos.
   **Os valores do holerite não podem mudar** — proventos, descontos e líquido iguais aos de hoje.
   Se algum centavo mudar, o oráculo mentiu e a frente tem de voltar.
2. **O fechamento do ponto.** Feche 09/2026 de ANDREA GONÇALVES: `total_dias_trabalhados` sai de 23
   para **12**.
3. **A escala torta.** `python3 backend/scripts/qa/checar_escala_paridade.py` no host, contra
   produção. Cada linha é um mês de grade lançada na paridade errada — leve para a operação.
   RILEM FERREIRA em 08/2026 é o caso de escola: 16 turnos lançados, 16 sem uma batida sequer.

---

## 7. Decisões que só o dono pode tomar

1. **Recalcular os holerites já gravados de 08 e 09/2026?** 25 deles têm o campo informativo
   `dias_trabalhados` com o número inflado. **Nenhum valor muda** — é só o informativo ficando
   honesto. 07/2026 está **publicado**; mexer nele é decisão sua, e eu não mexi.
2. **Refechar os meses de ponto já fechados?** `gp_monthly_closings.total_dias_trabalhados` só
   corrige no próximo fechamento. Meses fechados no passado continuam com o número velho até que
   alguém os reabra.
3. **A escala de RILEM, ADEILSON e MAIARA está lançada no dia errado** (RILEM: ímpares na grade,
   pares na vida, 16 turnos de 08/2026 sem batida). Enquanto não for arrumada, o mapa de ponto
   chama o posto de descoberto todo dia e essas pessoas aparecem como "fora de escala". Quem
   corrige a grade é a operação — o caçador agora não deixa esquecer.
4. **Corrigir o espelho (`time_record_service.total_worked_days`) também?** É o terceiro pareador
   da casa, com a mesma régua velha e outros leitores (portal do colaborador, espelho de ponto).
   Outra frente, com a sua própria medição de leitores.
5. **O gatilho que mandaria parar continua armado.** Se um dia alguma verba passar a usar
   `dias_trabalhados`, o item (c) do oráculo fica vermelho no mesmo dia — é ele que autoriza esta
   correção, não a minha leitura do código.
