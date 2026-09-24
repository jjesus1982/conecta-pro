# DGX V1 — Um plantão é UM dia trabalhado (24/09/2026)

**Frente:** V1, onda 4 · **Branch:** `dgx/v1-motor-beneficio-noturno` · **Módulo:** folha (motor de benefício)
**Defeito:** no 12x36 NOTURNO com intervalo (19:00 → 02:00 · 03:00 → 07:00), o segmento pós-intervalo
virava outro dia trabalhado. Achado registrado em `DGX_U5_entrega_beneficio.md` §7.

**A regra afirmada (regra, não fotografia):** um plantão é UM dia trabalhado, ainda que as batidas
cruzem a meia-noite e haja intervalo. O "dia" de um turno noturno é a data de INÍCIO
(`shifts.shift_date`); toda batida entre início−tolerância e fim+tolerância pertence a ele, nunca ao
dia seguinte só por ter ocorrido depois das 00:00.

---

## 1. Medição ANTES → DEPOIS (staging = cópia de produção de 24/09, sem tocar em produção)

Coorte: todo ativo (não homologação) com ao menos um turno `planned_start_time > planned_end_time`
no mês. Referência recontada por SQL próprio: `shift_date` distinto, não cancelado, com ao menos uma
batida na janela do turno ±1h (`plant.` abaixo).

### 08/2026 — 15 ativos em 12x36 noturna

| Colaborador | Trabalhado ANTES | Trabalhado DEPOIS | plant. | Δ antes | Δ depois |
|---|---:|---:|---:|---:|---:|
| ADAILSON SERRA ALVES | 31 | **15** | 15 | +16 | 0 |
| ADEILSON DINIZ DEODATO | 29 | **17** | 1 ¹ | +28 | +16 ¹ |
| AILTON CÉSAR VASCONCELOS | 26 | **14** | 14 | +12 | 0 |
| ANDREA GONÇALVES DOS SANTOS | 31 | **15** | 15 | +16 | 0 |
| ANILSON JOSE SEIXAS NEVES | 31 | **16** | 16 | +15 | 0 |
| ANTONIO DINIZ ASSIS DOS SANTOS | 28 | **15** | 14 | +14 | +1 |
| EDUARDO OLIVEIRA DE SOUZA | 27 | **14** | 13 | +14 | +1 |
| EDWARD JOSÉ ATENCIO DOMINGUEZ | 30 | **17** | 16 | +14 | +1 |
| EIDY CULIER DE CASTRO | 5 | **3** | 8 ² | −3 | −5 ² |
| FERNANDO SOUZA SIMPLICIO JUNIOR | 27 | **14** | 14 | +13 | 0 |
| JONHATA DINIZ BENAION | 24 | **15** | 15 | +9 | 0 |
| JONILSON MARTINS DE SOUZA | 27 | **15** | 15 | +12 | 0 |
| MAIARA MUNIZ DE SANTOS | 30 | **15** | 13 | +17 | +2 |
| RENE RICARDO CRUZ GONÇALVES | 29 | **14** | 14 | +15 | 0 |
| RILEM FERREIRA DE SOUZA | 28 | **15** | 0 ¹ | +28 | +15 ¹ |
| **Σ\|Δ\| contra a referência** | | | | **226** | **41** |

### 09/2026 — 16 ativos em 12x36 noturna

| Colaborador | ANTES | DEPOIS | plant. | Δ antes | Δ depois |
|---|---:|---:|---:|---:|---:|
| ADAILSON SERRA ALVES | 23 | **12** | 12 | +11 | 0 |
| ADEILSON DINIZ DEODATO | 16 | **10** | 8 ¹ | +8 | +2 |
| AILTON CÉSAR VASCONCELOS | 22 | **11** | 11 | +11 | 0 |
| ANDREA GONÇALVES DOS SANTOS | 23 | **12** | 12 | +11 | 0 |
| ANILSON JOSE SEIXAS NEVES | 23 | **11** | 11 | +12 | 0 |
| ANTONIO DINIZ ASSIS DOS SANTOS | 20 | **11** | 11 | +9 | 0 |
| DANIEL VIDAL LARROQUE | 21 | **14** | 10 ¹ | +11 | +4 |
| EDUARDO OLIVEIRA DE SOUZA | 23 | **13** | 12 | +11 | +1 |
| EDWARD JOSÉ ATENCIO DOMINGUEZ | 23 | **12** | 11 | +12 | +1 |
| EIDY CULIER DE CASTRO | 6 | **3** | 3 | +3 | 0 |
| FERNANDO SOUZA SIMPLICIO JUNIOR | 11 | **6** | 6 | +5 | 0 |
| JONHATA DINIZ BENAION | 12 | **12** | 12 | 0 | 0 |
| JONILSON MARTINS DE SOUZA | 18 | **10** | 10 | +8 | 0 |
| MAIARA MUNIZ DE SANTOS | 15 | **8** | 8 | +7 | 0 |
| MAURICIO ALVES CHAGAS | 23 | **13** | 11 ¹ | +12 | +2 |
| RENE RICARDO CRUZ GONÇALVES | 23 | **12** | 12 | +11 | 0 |
| **Σ\|Δ\| contra a referência** | | | | **142** | **10** |

¹ **O resto do Δ NÃO é do motor, é da escala.** RILEM FERREIRA tem `shifts` nos dias ÍMPARES de
08/2026 (18:00–06:00) e bate nos PARES: 15 plantões reais, 0 dentro da janela lançada — a referência
é que não os enxerga. ADEILSON, DANIEL e MAURICIO têm o mesmo desencontro em parte do mês. O motor
conta esses dias como `E` (trabalhou fora da escala), que é o correto.
² EIDY esteve de FÉRIAS 25 dias em 08/2026; férias sai do `Trabalhado` (mapa `V`) e a referência não
sabe disso. Motor certo, referência grossa — está aqui para não esconder o sinal.

**Efeito no que a correção realmente governa** (`folha_beneficio_conferencia`, recalculada no
sandbox com o motor corrigido):

| Competência | linhas | `trabalhado_anterior` Σ | `quantidade` Σ | `total` Σ |
|---|---:|---:|---:|---:|
| 08/2026 antes | 108 | — (sem anterior) | 1065 | R$ 20.922,00 |
| 08/2026 depois | 108 | — | 1065 | **R$ 20.922,00** (não muda) |
| 09/2026 antes | 102 | 462 | 1126 | R$ 22.228,00 |
| 09/2026 depois | 102 | **381** | **1045** | **R$ 20.842,00** (−R$ 1.386,00) |

Os 81 dias a menos em 09/2026 são exatamente os plantões noturnos de 08/2026 contados em dobro, que
entravam como `+ponto` (crédito) na competência seguinte. **Era esse o "ajuste +16 dias" que a U5
mandou não aprovar.** 08/2026 não muda porque toda linha está em `sem_anterior` (previsão pura).

---

## 2. O que o DGX tem

O DGX trata o plantão como a unidade do apontamento — a entrega de benefício é por plantão, não por
data civil de batida. `DGX_F3_tipos_beneficio.md` (integração com o ponto) e
`FRENTE_03_beneficio_ponto.md` já previam `Planejado × Trabalhado` por plantão; o que faltava era o
motor honrar isso quando o plantão atravessa a meia-noite.

---

## 3. O que foi feito (diff mínimo, 2 arquivos, 98 linhas)

**`backend/modules/people_management/ponto/services/horas_service.py`** — a régua, na FONTE ÚNICA.
Nenhuma cópia nova: o pareamento já morava aqui, e é daqui que o motor de benefício importa
`SQL_BATIDAS`/`MAX_TURNO_H`.

- `TOLERANCIA_TURNO_H = 1.0` — folga nas duas pontas da janela do turno.
- `INTERVALO_MAX_H = 3.0` — o par que recomeça em até 3h depois do anterior terminar, já do outro
  lado da meia-noite, é o mesmo plantão. Só vale quando NENHUM turno cobre a batida.
- `SQL_TURNOS_JANELA` + `janelas_de_turno(rows)` — `(início−tol, fim+tol, shift_date)` por turno não
  cancelado; noturno é o que termina antes de começar (`planned_start_time > planned_end_time`, o
  mesmo que `is_night_shift` marca) e a janela vai até o dia seguinte.
- `dia_do_plantao(entrada, janelas, ultimo)` — a data do plantão de uma batida. Janela que começou
  por ÚLTIMO vence (noturno de D terminando 07:00 × diurno de D+1 começando 07:00); sem janela, a
  continuidade; sem as duas, o dia civil — que é o que o código fazia sempre, e por isso o diurno
  não muda.
- `_self_check()` ganhou o caso 4 (roda com `python3 horas_service.py`): 4/4 OK.

**`backend/modules/people_management/folha/services/beneficio_ponto.py`** — `_horas_por_dia` passa a
atribuir cada par ao dia do PLANTÃO, e a varredura das batidas solitárias usa o mesmo mapeamento
(senão a saída de 02:00 do plantão da véspera criava um dia de 0h no dia seguinte).

`mapa_frequencia`, `calcular_competencia` e a tela não mudaram de forma — só passaram a receber o
dia certo. **Nenhuma DDL**, nenhuma tela nova, nenhum `_ensure` novo.

Telas afetadas (já existentes): `/redesign/departamento-pessoal?t=beneficio-frequencia` e
`?t=beneficio-conferencia`.

---

## 4. Oráculo — `backend/scripts/orq/test_oraculo_v1_plantao_e_um_dia.py`

```bash
ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\n' ' ')
docker run --rm --network conecta-staging-network -v "$PWD/backend:/app:ro" \
  --tmpfs /app/logs:rw,mode=1777 --tmpfs /app/uploads:rw,uid=999,gid=999 \
  -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env \
  -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \
  conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_v1_plantao_e_um_dia.py
```

**VERMELHO (árvore-base d76e1df3d, os dois arquivos restaurados com `git show HEAD:`):**

```
(a) fixture 3 plantões noturnos: Trabalhado 6 (régua anterior daria 6)
(b) ADAILSON SERRA ALVES 08/2026: Trabalhado 31 × plantões com batida 15 (antes: 31 dias)
(c) pessoa×mês que não trabalham à noite: 64 · Σ|Δ| horas: 0.0000 · pessoa×mês noturnas (fora da conta, é o alvo): 36
FALHOU: (a) 3 plantões com intervalo deram 6 dias trabalhados — o plantão virou 2 dias
FALHOU: (a) 2026-07-03: dia seguinte ao plantão marcado 'E' — o segmento pós-intervalo virou um dia trabalhado à parte
FALHOU: (a) 2026-07-05: dia seguinte ao plantão marcado 'E' — o segmento pós-intervalo virou um dia trabalhado à parte
FALHOU: (a) 2026-07-07: dia seguinte ao plantão marcado 'E' — o segmento pós-intervalo virou um dia trabalhado à parte
FALHOU: (b) ADAILSON SERRA ALVES 08/2026: Trabalhado 31 ≠ 15 plantões com batida
TOTAL desvios: 5
```

**VERDE (com a correção):**

```
(a) fixture 3 plantões noturnos: Trabalhado 3 (régua anterior daria 6)
(b) ADAILSON SERRA ALVES 08/2026: Trabalhado 15 × plantões com batida 15 (antes: 31 dias)
(c) pessoa×mês que não trabalham à noite: 68 · Σ|Δ| horas: 0.0000 · pessoa×mês noturnas (fora da conta, é o alvo): 36
TOTAL desvios: 0
OK plantão é um dia: noturno com intervalo conta 1, ADAILSON bate com os plantões, diurno intacto
```

Fixtures `'FIXTURE DGX V1'` apagadas ao fim (conferido: 0 em `employees`, `shifts`, `gp_clock_punches`).

### Os outros quatro oráculos

| Oráculo | Resultado |
|---|---|
| `test_oraculo_beneficio_regra_e_dado.py` | verde · `Σ\|Δ total\|: R$ 0.00` · 208 linhas comparadas |
| `test_oraculo_beneficio_fecha.py` (com `-v /opt/conecta-pro/uploads:/app/uploads:ro`) | verde · 23 pessoa×benefício no portal, 23 casadas, 0 divergentes |
| `test_oraculo_mapa_de_ponto_5_estados.py` | verde · dia fechado 23/09: ok=21, atraso=3, posto incorreto=1, fora de escala=8, descoberto=2 |
| `test_oraculo_grid_bate_com_a_triagem.py` | verde · régua hoje 29 turnos · mapa 29 · excluídos 0 |

**Atenção ao `beneficio_regra_e_dado`:** ele ficou VERMELHO logo após a correção
(`Σ|Δ total|: R$ 1386.00`, 7 desvios) porque o item (c) compara o motor com o que estava GUARDADO em
`folha_beneficio_conferencia` — linhas calculadas pelo motor defeituoso, exatamente como a U5 §7
antecipou ("exige re-medir o oráculo da F3, cujas linhas guardadas carregam o defeito"). Rodei
`calcular_competencia(2026, 8)` e `(2026, 9)` com `gravar=True` **no sandbox** e ele voltou a
`R$ 0,00`. Em produção isso acontece sozinho no primeiro "Calcular" da tela de conferência —
**mas os números de 09/2026 vão mudar (§1), e é o dono que decide quando**.

---

## 5. Paralelo cego — o que muda e o que NÃO muda

**MUDA:** `folha_beneficio_conferencia` (`trabalhado_anterior`, `+ponto`, `quantidade`, `total`) e as
telas `beneficio-frequencia` / `beneficio-conferencia`. Números exatos no §1. É uma tela de
CONFERÊNCIA — nada dali é pago sem alguém aprovar.

**NÃO MUDA — medido, não suposto:**

- **Folha / holerite / pagamento.** `calculo_service` não passa por `_horas_por_dia`; ele usa
  `horas_reais_ponto` → `parear_batidas`, **que eu não toquei**. VT/VR do holerite saem de
  `dias_vt_vr(escala, mes, ano)` (escala, não ponto). O único campo do holerite que vem de
  `parear_batidas['dias_trabalhados']` é o informativo `dias_trabalhados` (linha 1052).
- **A régua da frente 04 (`mapa_de_ponto.py`) — ZERO mudança.** Ela não usa o pareamento: casa turno
  × batida por `presence_controller._janela_turno` / `_janela_presenca`, turno a turno. Não editei
  `mapa_de_ponto.py`, `presence_controller.py` nem `coorte_ponto.py`, e os dois oráculos dela estão
  verdes com os mesmos números de antes (tabela acima). **O mapa de ponto e a grade não mudam.**

**O gêmeo que continua torto, com número** — `horas_service.parear_batidas['dias_trabalhados']`
conta a mesma data-de-entrada. Não corrigi porque é caminho de folha e o brief fecha
`calculo_service.py`. O que mudaria se o dono mandar corrigir (staging, hoje):

| | 08/2026 | 09/2026 |
|---|---:|---:|
| Σ\|Δ\| gêmeo × corrigido, 12x36 noturna | **86 dias** | **51 dias** |
| Piores | ADAILSON 31→15 · ANDREA 31→15 · ANILSON 29→16 · RILEM 25→15 | ANILSON 23→11 · ANDREA 23→12 · ADAILSON 22→12 |

Consumidores: `dias_trabalhados` do holerite (informativo) e
`gp_monthly_closings.total_dias_trabalhados` (`punch_service`). Nenhum dos dois entra em conta de
dinheiro hoje — mas os dois são LIDOS por gente.

---

## 6. O que NÃO foi feito e por quê

1. **`parear_batidas` não foi corrigido** (acima). Um plantão continua valendo dois dias no campo
   `dias_trabalhados` do holerite e no fechamento do ponto.
2. **A escala deslocada não foi corrigida.** RILEM FERREIRA tem `shifts` nos ímpares e bate nos
   pares desde agosto; ADEILSON, DANIEL e MAURICIO idem em parte do mês. Isso é dado, não código —
   "se vai consertar muitos registros de uma vez, pare". Está no §7.
3. **`INTERVALO_MAX_H` é heurística**, marcada com `ponytail:` no código. Ela só entra quando a
   escala não cobre a batida; quando a escala estiver certa ela nunca dispara. Um risco conhecido:
   dobra que começa até 3h depois de um plantão noturno terminar, em quem não tem escala lançada,
   seria colada ao plantão da véspera. É ilegal por interjornada (11h) e não apareceu nos dois meses
   medidos.
4. **Produção não foi tocada.** Toda medição e todo recálculo foram no sandbox
   (`conecta_pro_staging`). Container `teste-dgx-v1` na porta 8241 subiu, respondeu `/health` e
   `GET /api/v1/redesign/data/departamento-pessoal` 200 (6,5 MB), com ADAILSON mostrando
   `T=12 E=0` em 09/2026 na aba de frequência — e foi **parado**.

---

## 7. Decisões que só o dono pode tomar

1. **Quando recalcular 09/2026 em produção.** A conferência de 09/2026 cai de R$ 22.228,00 para
   R$ 20.842,00 (−R$ 1.386,00 / −81 dias de crédito). O número de hoje está errado a favor do
   colaborador; o novo é o certo. Recalcular é um clique em "Calcular" na tela de conferência.
2. **A escala de RILEM, ADEILSON, DANIEL e MAURICIO está lançada no dia errado** (RILEM: ímpares na
   grade, pares na vida, 15 plantões em 08/2026 marcados `E`). Enquanto não for arrumada, essas
   pessoas contam certo no total mas aparecem como "fora de escala" — e o mapa de ponto as chama de
   descobertas todo dia. Quem corrige a grade: a operação.
3. **Corrigir o gêmeo da folha** (`parear_batidas`)? É outra frente, toca `calculo_service` e mexe no
   campo `dias_trabalhados` do holerite de 15 pessoas. Números no §5.
4. A liberação da U5 ("não aprovar entrega por apontamento de escala noturna") **pode cair** depois
   do recálculo do item 1 — o ajuste de +16 dias que a travava não existe mais.
