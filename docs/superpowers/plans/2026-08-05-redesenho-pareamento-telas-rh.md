# Redesenho do pareamento de batidas — telas de RH Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fazer as telas de ponto do RH mostrarem o plantão 12x36 noturno corretamente, **sem nunca fabricar um turno** sobre o período de descanso.

**Architecture:** `hr/services/time_record_service._pair_punches` é o terceiro pareador de batida do sistema e o único ainda desalinhado (os outros dois foram corrigidos no commit `9dd89246`). O redesenho troca o agrupamento-por-dia por pareamento **direcional**: o `punch_type` deixa de ser a fonte da verdade do horário mas continua sendo a única **dica de direção** disponível — uma batida tipada `saida` não pode ABRIR turno. Onde a direção é ambígua, a batida vira registro parcial (`inconsistencia`) em vez de par inventado.

**Tech Stack:** Python 3.12 · SQLAlchemy async · pytest (`asyncio_mode=auto`) · PostgreSQL 16

## Global Constraints

- **NUNCA FABRICAR.** Duas pontas soltas de turnos diferentes nunca viram um turno. Na dúvida, registro parcial com `status="inconsistencia"`. Esta é a regra que derrubou a tentativa anterior.
- `MAX_TURNO_H = 13.0`, importado de `ponto/services/horas_service.py:33`. Nunca redefinir.
- `gp_clock_punches.punch_timestamp` é **hora LOCAL de Manaus (naive)**. Ler como está, NUNCA converter fuso (regressão do release 2026-07-17).
- Contrato de saída de `_pair_punches` inalterado: as 18 chaves de `hr/schemas/time_record.py:85-107`. Quatro chamadores dependem.
- `status` continua emitindo `regular` | `inconsistencia` | `falta`. Três consumidores leem esses valores (ver Task 1).
- **Não tocar** em `horas_service.py` nem `punch_service.py` — alimentam a folha e já estão certos.
- Commits com `--no-verify`, pathspec explícito (`git commit -- <arquivos>`), nunca `git add -A`.
- Rodar testes no venv do host: `cd /opt/conecta-pro/backend && venv/bin/python -m pytest ...` (o container de produção não tem pytest; o venv do host não tinha `reportlab` — já instalado em 2026-08-05).

## Método — dirigido por teste, não por código pré-escrito

**A tentativa anterior (`5e0bbc1f`, revertida) falhou porque o plano trazia a implementação inteira pronta e ela parecia certa.** Este plano especifica **invariantes e casos**, não o corpo do método. O implementador escreve o código mínimo que faz um xfail virar verde por vez, e roda a suíte inteira a cada passo.

A spec executável já está no repositório:
`backend/tests/people_management/hr/test_pair_punches_virada.py` — **3 xfail(strict) + 3 guardas**.

Estado inicial (medido 2026-08-05): `3 passed, 3 xfailed`.

`strict=True` significa que quando um xfail passar, o pytest **falha de propósito** até o marcador ser removido. É o sinal de progresso. Nunca remova um `xfail` sem que o teste esteja verde.

---

## Baseline medido (julho/2026, banco real)

Instrumento: `backend/scripts/diag_pair_punches_telas.py` (READ-ONLY, já commitado).

```bash
cd /opt/conecta-pro/backend
PGIP=$(docker inspect conecta-pro-postgres -f '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' | awk '{print $1}')
PGPW=$(grep -oP '^POSTGRES_PASSWORD=\K.*' /opt/conecta-pro/.env)
DATABASE_URL="postgresql+asyncpg://postgres:${PGPW}@${PGIP}:5432/conecta_pro" \
  venv/bin/python scripts/diag_pair_punches_telas.py --mes 7 --ano 2026
```

```
ALGORITMO ATUAL:   2246 batidas · 853 pareados · 606 fechados · 2 cruzam meia-noite · 540 órfãs
```

**Alvo do redesenho:** turnos que cruzam a meia-noite deve subir de 2 para a ordem de ~120.

> ⚠️ **A faixa de `fechados` que este plano estimou (850–1000) estava errada** e a métrica
> de `órfãs` do script também (a fórmula `batidas − 2×registros` assume que todo registro
> consome 2 batidas; com registros parciais e com almoço isso é falso — deu **−94**).
>
> A checagem que vale é a **CONTABILIDADE**: cada batida tem de ser usada exatamente uma vez.
> `fechados_sem_almoço×2 + com_almoço×4 + parciais×1 == total_de_batidas`. Se não fechar,
> há batida duplicada ou perdida. Complemento: **nenhum turno fechado pode abrir numa batida
> tipada `saida`** (tem de dar 0).
>
> **Resultado real da Task 1** (07/2026): 769 registros · 675 fechados · 401 com almoço ·
> 136 cruzam meia-noite · 94 parciais · `274×2 + 401×4 + 94×1 = 2246` ✅ · 0 abrindo em saída ✅

---

## File Structure

| Arquivo | Responsabilidade | Ação |
|---|---|---|
| `backend/tests/people_management/hr/test_pair_punches_virada.py` | Spec executável — 3 xfail + 3 guardas | **Já existe**; Tasks removem xfail e adicionam casos |
| `backend/modules/people_management/hr/services/time_record_service.py` | `_pair_punches` + as 3 consultas SQL que o alimentam | **Modificar** (Tasks 1–4) |
| `backend/scripts/diag_pair_punches_telas.py` | Oráculo contra o banco | **Já existe**; só rodar |

---

### Task 1: Pareamento direcional (fecha os 3 xfail) — ✅ CONCLUÍDA 2026-08-05

**Files:**
- Modify: `backend/modules/people_management/hr/services/time_record_service.py` — método `_pair_punches` (linha ~946)
- Test: `backend/tests/people_management/hr/test_pair_punches_virada.py` (já existe)

**Interfaces:**
- Consumes: `MAX_TURNO_H` de `modules.people_management.ponto.services.horas_service`; `_calc_minutes_between` e `_format_minutes`, ambos já no mesmo arquivo
- Produces: `_pair_punches(rows: list[Mapping]) -> list[dict]` com as 18 chaves do contrato

**Invariantes que o algoritmo tem de respeitar** (esta é a especificação — o código é do implementador):

1. **Agrupar por funcionário, não por dia.** O dia do registro sai do par (dia da ENTRADA), nunca da batida solta.
2. **Direção manda.** Uma batida tipada `saida` **não abre** turno. Uma tipada `entrada` **não fecha** turno. Um par `(saida, entrada)` é período de DESCANSO — jamais vira registro.
3. **Tipo ausente ou contraditório → alternância.** Quando ambos os tipos são iguais (o bug do noturno: duas `entrada` seguidas), a ordem cronológica decide, mas só se a duração for turno plausível (`0 < dur <= MAX_TURNO_H*60`).
4. **Batida sem par vira registro PARCIAL**, nunca desaparece:
   - só entrada → `clock_in` preenchido, `clock_out=None`, `status="inconsistencia"`
   - só saída → `clock_out` preenchido, `clock_in=None`, `status="inconsistencia"`
5. **Órfã avança UMA posição.** Avançar duas desalinha o resto do mês.
6. **`total_hours` só existe quando o turno fecha.** Registro parcial tem `total_hours=None`.

- [ ] **Step 1: Rodar a spec e confirmar o estado inicial**

```bash
cd /opt/conecta-pro/backend
venv/bin/python -m pytest tests/people_management/hr/test_pair_punches_virada.py -v -p no:warnings
```
Esperado: `3 passed, 3 xfailed`.

- [ ] **Step 2: Implementar o pareamento direcional**

Reescrever `_pair_punches` conforme as 6 invariantes acima. Guia de estrutura (NÃO é código pronto — adapte e prove com os testes):

```
agrupa rows por employee_id
para cada funcionário:
    ordena por punch_timestamp
    i = 0
    enquanto i < len(punches):
        a = punches[i]
        b = punches[i+1] se existir
        se b não existe:
            emite PARCIAL(a); break
        tipo_a, tipo_b = tipo normalizado de cada
        # invariante 2 — descanso nunca vira turno
        se tipo_a == 'saida' e tipo_b == 'entrada':
            emite PARCIAL(a); i += 1; continua
        dur = _calc_minutes_between(a.ts, b.ts)
        se não (0 < dur <= MAX_TURNO_H*60):
            emite PARCIAL(a); i += 1; continua
        # aqui o par é plausível E direcionalmente válido
        emite FECHADO(a, b, dur); i += 2
```

Atenção ao detalhe que derrubou a tentativa anterior: `tipo_a == 'saida'` na PRIMEIRA
posição de uma janela é o caso do `get_daily` do noturno. Ele tem de virar parcial, não par.

- [ ] **Step 3: Rodar a spec até os 3 xfail passarem**

```bash
venv/bin/python -m pytest tests/people_management/hr/test_pair_punches_virada.py -v -p no:warnings
```
Esperado ao final: **6 failed** — os 3 xfail agora dão `XPASS(strict)`, que o pytest reporta
como falha. Isso é o sinal de sucesso.

- [ ] **Step 4: Remover os 3 marcadores `@pytest.mark.xfail`**

Apagar os três decoradores (e o `import pytest` se ficar sem uso). Rodar de novo:
```bash
venv/bin/python -m pytest tests/people_management/hr/test_pair_punches_virada.py -v -p no:warnings
```
Esperado: **6 passed**.

- [ ] **Step 5: Provar que não há regressão — medir a linha de base primeiro**

```bash
cd /opt/conecta-pro/backend
S=/tmp/recon && mkdir -p $S
cp modules/people_management/hr/services/time_record_service.py $S/NOVO.py
git show HEAD:backend/modules/people_management/hr/services/time_record_service.py > $S/ORIG.py

cp $S/ORIG.py modules/people_management/hr/services/time_record_service.py
echo "=== BASELINE ==="
venv/bin/python -m pytest tests/people_management/hr/ tests/ponto_release/ -p no:warnings 2>&1 | tail -3

cp $S/NOVO.py modules/people_management/hr/services/time_record_service.py
echo "=== DEPOIS ==="
venv/bin/python -m pytest tests/people_management/hr/ tests/ponto_release/ -p no:warnings 2>&1 | tail -3
```

Em 2026-08-05 a baseline era **9 falhas em `hr/`** e **18 falhas + 4 erros em `ponto_release/`**,
todas pré-existentes (E2E que precisam de API viva). O número DEPOIS tem de ser igual ou menor.
Se subir, o fix regrediu algo — pare e investigue.

- [ ] **Step 6: Rodar o oráculo e conferir contra a faixa esperada**

```bash
PGIP=$(docker inspect conecta-pro-postgres -f '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' | awk '{print $1}')
PGPW=$(grep -oP '^POSTGRES_PASSWORD=\K.*' /opt/conecta-pro/.env)
DATABASE_URL="postgresql+asyncpg://postgres:${PGPW}@${PGIP}:5432/conecta_pro" \
  venv/bin/python scripts/diag_pair_punches_telas.py --mes 7 --ano 2026
```
Esperado: `cruzam a meia-noite` na ordem de ~120 (era 2). `fechados` entre 850 e 1000.
**Acima de 1050 = suspeita de fabricação. Pare.**

- [ ] **Step 7: Commit**

```bash
cd /opt/conecta-pro
git commit --no-verify -m "fix(ponto): pareamento DIRECIONAL nas telas de RH

punch_type deixa de ditar o horario mas continua sendo a dica de DIRECAO:
batida tipada 'saida' nao abre turno, o par (saida, entrada) e periodo de
DESCANSO e nunca vira registro. Batida sem par vira registro PARCIAL com
status inconsistencia -- nunca some da tela.

Fecha os 3 xfail da spec. Oraculo 07/2026: <preencher>.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" \
  -- backend/modules/people_management/hr/services/time_record_service.py \
     backend/tests/people_management/hr/test_pair_punches_virada.py
```

---

### Task 2: ~~Teto no intervalo de almoço~~ — DOBRADA NA TASK 1 (2026-08-05) ✅

> **A premissa desta task estava errada.** Ela supunha que o ramo de almoço casava por
> `punch_type == 'saida_almoco'` e só faltava um teto. Medição na base real: **esse tipo
> não existe** — julho/2026 tem 1171 `entrada` + 1075 `saida` e **zero** de almoço. O ramo
> era código morto, e um teto num ramo que nunca dispara não resolve nada.
>
> Pior: sem detecção de almoço, a Task 1 sozinha partia **401 dos 754 dias-funcionário** em
> dois registros de ~4h e inflava o contador de dias trabalhados em ~55% — regressão visível
> na tela. Task 1 não era entregável sem isto, então as duas foram feitas juntas.
>
> **O que foi implementado:** almoço reconhecido pelo **intervalo** (buraco curto entre dois
> pares de batida), não pelo tipo, com `MAX_ALMOCO_H = 3.0` separando intervalo de descanso.
> Três testes novos cobrem: jornada com almoço sem tipo de almoço, intervalo de 8h que não
> pode virar almoço, e as 36h entre plantões 12x36 que não podem ser absorvidas.
>
> Detalhe original preservado abaixo para registro.

#### (original) Teto no intervalo de almoço

**Files:**
- Modify: `backend/modules/people_management/hr/services/time_record_service.py` — ramo de almoço dentro de `_pair_punches`
- Test: `backend/tests/people_management/hr/test_pair_punches_virada.py`

**Defeito:** o almoço só é limitado pelo total do turno (13h), então um intervalo de 8h entre
dois turnos distintos é engolido como "almoço" e a tela mostra a pessoa em serviço das 08:00
às 21:00. Presente no algoritmo original **e** na tentativa revertida.

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar ao arquivo de spec:

```python
def test_intervalo_longo_nao_vira_almoco():
    """8h entre dois turnos sao DOIS turnos, nao um almoco de 8h."""
    rows = [
        _punch("emp-5", "2026-07-10T08:00:00", "entrada", "a"),
        _punch("emp-5", "2026-07-10T12:00:00", "saida_almoco", "b"),
        _punch("emp-5", "2026-07-10T20:00:00", "retorno_almoco", "c"),
        _punch("emp-5", "2026-07-10T21:00:00", "saida", "d"),
    ]

    recs = TimeRecordService(None)._pair_punches(rows)

    for r in recs:
        assert not (r["clock_in"] == "08:00" and r["clock_out"] == "21:00"), (
            f"intervalo de 8h virou almoco — pessoa aparece 13h em servico: {r}"
        )
```

- [ ] **Step 2: Rodar e confirmar FAIL**

```bash
venv/bin/python -m pytest tests/people_management/hr/test_pair_punches_virada.py::test_intervalo_longo_nao_vira_almoco -v -p no:warnings
```

- [ ] **Step 3: Introduzir `MAX_ALMOCO_H = 3.0`**

Constante no topo do módulo, com comentário citando a CCT (intervalo intrajornada de 1h;
3h é folga generosa para cobrir jornada partida legítima). Rejeitar o ramo de almoço acima
disso — o par seguinte vira turno separado.

- [ ] **Step 4: Rodar a suíte inteira**

```bash
venv/bin/python -m pytest tests/people_management/hr/test_pair_punches_virada.py -v -p no:warnings
```
Esperado: **7 passed** (6 da Task 1 + este).

- [ ] **Step 5: Commit**

```bash
git commit --no-verify -m "fix(ponto): teto de 3h no intervalo de almoco (jornada partida != turno unico)

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" \
  -- backend/modules/people_management/hr/services/time_record_service.py \
     backend/tests/people_management/hr/test_pair_punches_virada.py
```

---

### Task 3: Alargar a janela SQL (dia civil e virada de mês) — ✅ CONCLUÍDA 2026-08-05

**Files:**
- Modify: `backend/modules/people_management/hr/services/time_record_service.py:919-929` (`get_daily`)
- Modify: `backend/modules/people_management/hr/services/time_record_service.py:824-835` (`_calculate_summary_from_punches`)

**Defeito:** as duas consultas filtram exatamente o período pedido. Um turno que começa
31/07 21:00 e termina 01/08 09:00 fica sem a saída em julho e sem a entrada em agosto —
some dos dois meses. No `get_daily`, o dia civil de um noturno nunca contém um turno inteiro.

**Correção:** consultar `[início − 1 dia, fim + 1 dia]`, parear na janela larga, e **depois**
filtrar os registros pelo `record_date` pedido. O par pertence ao dia da ENTRADA (mesma
convenção de `horas_service.parear_batidas`), então a virada não é contada duas vezes.

- [ ] **Step 1: Teste do turno da virada de mês**

```python
def test_turno_da_virada_de_mes_conta_no_mes_da_entrada():
    """31/07 21:00 -> 01/08 09:00 pertence a JULHO (mes da entrada)."""
    rows = [
        _punch("emp-6", "2026-07-31T21:00:00", "entrada", "a"),
        _punch("emp-6", "2026-08-01T09:00:00", "saida", "b"),
    ]

    recs = TimeRecordService(None)._pair_punches(rows)

    assert len(recs) == 1
    assert recs[0]["record_date"] == "2026-07-31"
    assert recs[0]["total_hours"] == "12:00"
```

- [ ] **Step 2: Rodar — deve passar já com a Task 1** (o pareador não filtra por mês; quem filtra é o SQL). Se passar, seguir para o Step 3; se falhar, corrigir o pareador antes.

- [ ] **Step 3: Alargar as duas consultas**

Em `get_daily`: trocar `WHERE punch_timestamp::date = :pdate` por um intervalo
`>= :pdate - 1 dia AND < :pdate + 2 dias`, e filtrar o resultado com
`[r for r in records if r["record_date"] == str(pdate)]`.

Em `_calculate_summary_from_punches`: idem, `first_day - 1 dia` a `last_day + 2 dias`,
filtrando por `record_date` dentro do mês depois de parear.

- [ ] **Step 4: Provar no banco real que o noturno aparece**

Escolher um funcionário do noturno (batida de entrada entre 16h e 22h em julho):
```bash
docker exec conecta-pro-postgres psql -U postgres -d conecta_pro -c "
SELECT employee_id, count(*) FROM gp_clock_punches
WHERE punch_timestamp >= '2026-07-01' AND punch_timestamp < '2026-08-01'
  AND extract(hour from punch_timestamp) BETWEEN 19 AND 22
GROUP BY 1 ORDER BY 2 DESC LIMIT 3;"
```
Rodar `get_daily` para um dia desse funcionário e conferir que devolve o turno fechado,
datado no dia da entrada, e **não** um turno sobre o descanso.

- [ ] **Step 5: Commit**

---

### Task 4: `get_by_id` devolve o registro que contém a batida pedida — ✅ CONCLUÍDA 2026-08-05

**Files:**
- Modify: `backend/modules/people_management/hr/services/time_record_service.py:246-250`

**Defeito:** re-consulta só o dia civil da batida e devolve `records[0]`. Com o pareamento
novo, `records[0]` pode ser outro turno do mesmo dia — pede-se a batida `b`, recebe-se `a`.

- [ ] **Step 1: Teste**

```python
def test_get_by_id_devolve_o_turno_que_contem_a_batida():
    """Dois turnos no mesmo dia: pedir a batida do segundo nao pode devolver o primeiro."""
    rows = [
        _punch("emp-7", "2026-07-10T08:00:00", "entrada", "a"),
        _punch("emp-7", "2026-07-10T12:00:00", "saida", "b"),
        _punch("emp-7", "2026-07-10T18:00:00", "entrada", "c"),
        _punch("emp-7", "2026-07-10T22:00:00", "saida", "d"),
    ]

    recs = TimeRecordService(None)._pair_punches(rows)
    por_id = {r["id"]: r for r in recs}

    assert "c" in por_id, f"o segundo turno perdeu o id da entrada: {recs}"
    assert por_id["c"]["clock_in"] == "18:00"
```

- [ ] **Step 2: Rodar, implementar (selecionar por `id` em vez de `records[0]`), rodar de novo, commitar.**

---

### Task 5: Re-medir e verificar NA TELA

- [ ] **Step 1: Oráculo final**

Rodar `diag_pair_punches_telas.py` para julho e agosto/2026 e registrar os números no
relatório. Conferir contra a faixa esperada (fechados 850–1000).

- [ ] **Step 2: Deploy durável** — **pedir autorização ao Jordan antes.**

```bash
/opt/conecta-pro/scripts/deploy_backend_bluegreen.sh   # em background, ~4min
```

- [ ] **Step 3: Verificar NA TELA, não no builder**

Regra do projeto: API 200 ≠ entregue. Abrir a tela de ponto do RH de um funcionário do
noturno e confirmar que o plantão aparece como UM dia fechado, e que quem esqueceu de bater
a saída aparece com o botão "Saída" disponível.

---

## Decisão pendente do Jordan — hora extra no 12x36

`overtime_minutes = max(0, dur - 480)` dispara em **todo** plantão de 12h. Quando o
pareamento passar a fechar ~120 turnos noturnos que hoje não fecham, o total mensal de hora
extra de um agente 12x36 salta cerca de **+60h/mês** — contra uma CCT que compensa o 12x36
**por escala**, não por hora extra.

É a mesma família de decisão do "pagar noturno pela escala" (2026-08-04). Duas saídas:

1. **Não computar hora extra para escala 12x36** — o excedente de 4h é a própria natureza do plantão.
2. **Manter e tratar como informativo** — a tela mostra, a folha ignora.

**Não implementar nenhuma das duas sem a decisão.** Enquanto não houver decisão, a Task 1
não altera o cálculo de `overtime_minutes` — só o número de turnos que fecham.

---

## Fora deste plano

- **Paginação de `list_records`** (`:182-185`): `LIMIT page_size*4` assume 4 batidas/dia. Com 2 batidas/turno no noturno, a página 1 mostra metade dos registros construídos e a página 2 pula o resto. Defeito **pré-existente**, independente do pareamento. Plano próprio.
- As **77 rotas de escrita órfãs** (`auditoria/backend_recon/peoplemgmt_writes_20260805.md`) — 9 planos, um por subsistema, ordem sugerida no plano anterior.

---

## Self-Review

**1. Cobertura.** Os 7 defeitos da revisão adversarial estão cobertos: #1 e #4 na Task 1, #2 na Task 2, #3 na Task 1 (invariante 3), #5 na Task 3, #6 na Task 4, #7 declarado fora do plano com justificativa. O efeito colateral de hora extra virou decisão do Jordan.

**2. Placeholders.** O plano descreve **invariantes e casos de teste completos**, e deliberadamente **não** traz o corpo do método pronto — a tentativa anterior falhou exatamente por confiar em implementação pré-escrita que parecia certa. Todo passo tem comando exato e saída esperada.

**3. Consistência.** `MAX_TURNO_H` importado (nunca redefinido); `MAX_ALMOCO_H` introduzido na Task 2 e usado só lá; `record_date` sempre o dia da ENTRADA em todas as tasks; contrato de 18 chaves preservado em todas.

**Risco residual declarado:** a invariante 2 (par `saida→entrada` = descanso) depende do
`punch_type` estar certo na direção, ainda que errado no resto. Se um dia as batidas vierem
com o tipo completamente aleatório, o pareamento degrada para alternância pura e o caso do
`get_daily` volta a poder fabricar. O guarda contra isso é o teste
`test_janela_de_um_dia_do_noturno_nao_fabrica_turno`, que deve permanecer na suíte para sempre.
