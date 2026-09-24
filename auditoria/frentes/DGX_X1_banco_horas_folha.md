# DGX X1 — Banco de horas × folha: a ponte que nunca existiu (24/09/2026)

**Branch:** `dgx/x1-banco-horas-folha` (base `327297120`, fase5-hermes-camada-cognitiva)
**Módulo:** folha (`banco_horas_conferencia`) + telas do redesign do DP · **Sessão:** agent-x1
**Paralelo cego absoluto.** `calculo_service.py` e `time_bank_controller.py` só foram LIDOS.
Nada escreve em folha, holerite, pagamento ou `time_bank`. DDL idempotente aplicada só no
sandbox (`_ensure`); em produção acontece no 1º acesso à aba.
**Container HTTP:** `teste-dgx-x1`, porta 8261 — **parado ao fim**.

---

## 1. A medição, nominal — o que existe hoje e quanto disso é passivo

A W5 §7 disse: «o banco de horas está completo no Operacional e **nunca conversa com a folha**;
é o maior buraco desta lista». Medido no sandbox (cópia de produção de hoje), o buraco é maior
do que parecia:

> **`time_bank` tem 0 linhas — em produção E no sandbox.**
> O módulo do banco de horas existe inteiro (modelo, repositório, serviço com regra da CLT,
> controller com 11 rotas, 8 telas `banco-horas*` em g-equipe: lançar, aprovar, rejeitar,
> compensar, editar, excluir, apuração) e **nunca recebeu um único lançamento**.

A hora, porém, existe — está no espelho de ponto. `time_sheets.hours_balance_minutes`
(= trabalhado − previsto, escrito por `espelho_service.py` L767) é o saldo que o ponto mede todo
mês e que ninguém transporta para o banco de horas nem para a folha:

| Competência | Pessoas | Crédito medido | Débito medido | Vence em (CLT 180d) | Valia como HE (art. 59 §3) | Folha pagou como HE | **Não pago nem compensado** |
|---|---:|---:|---:|---|---:|---:|---:|
| 03/2026 | 44 | 119,59 h | 152,22 h | **27/09/2026** | R$ 1.663,02 | R$ 203,14 | **R$ 1.459,88** |
| 05/2026 | 38 | 188,22 h | 6,66 h | 27/11/2026 | R$ 2.622,42 | R$ 875,88 | **R$ 1.746,54** |
| 06/2026 | 46 | 242,90 h | 186,79 h | 27/12/2026 | R$ 3.391,43 | R$ 2.587,08 | **R$ 804,35** |
| 07/2026 | 58 | 8,96 h | 2.988,14 h | 27/01/2027 | R$ 82,96 | R$ 280,53 | (pagou a mais: −R$ 197,57) |
| 08/2026 | 65 | 328,77 h | 673,96 h | 27/02/2027 | R$ 4.175,87 | R$ 208,94 | **R$ 3.966,93** |
| 09/2026 | 51 | 44,88 h | 760,07 h | 29/03/2027 | R$ 624,73 | R$ 0,00 | **R$ 624,73** |
| **Total** | **82 pessoas** | **933,32 h** | **4.767,84 h** | — | **R$ 12.560,43** | **R$ 4.155,57** | **R$ 8.404,86** |

**O número que o dono precisa ver: R$ 8.404,86.** É crédito de hora medido pelo nosso ponto em
2026, que não virou lançamento no banco de horas, não foi compensado em folga e não foi pago como
hora extra no holerite. Pela CLT art. 59 §3 o crédito não compensado no prazo é devido como extra,
com adicional mínimo de 50% — é essa a conta (`horas × valor_hora × 1,5`, valor-hora pelo divisor
da escala, a mesma conta do motor em `calculo_service` L404-406).

**Já venceu:** a parcela de **03/2026 — 119,59 h de 16 pessoas, R$ 1.663,02, dos quais R$ 61,18
pagos — vence em 27/09/2026**, três dias depois desta medição. É por isso que a tela
`banco-horas-vencendo` existe.

Os 10 maiores, nominal (pessoa · competência · crédito · não pago · vence):

| Colaborador | Comp. | Crédito | Valor-hora | Devido CLT | Pago | Não pago | Vence |
|---|---|---:|---:|---:|---:|---:|---|
| PAULO SERGIO ALMEIDA RIBEIRO | 08/2026 | 42,00 h | R$ 7,92 | R$ 498,96 | — | **R$ 498,96** | 27/02/2027 |
| MARIA APARECIDA GOMES DE OLIVEIRA | 08/2026 | 42,00 h | R$ 7,59 | R$ 478,17 | — | **R$ 478,17** | 27/02/2027 |
| ROSANGELA DIAS FERNANDES | 08/2026 | 42,00 h | R$ 7,59 | R$ 478,17 | — | **R$ 478,17** | 27/02/2027 |
| ANTONIO MARCOS CAVALCANTE | 08/2026 | 42,00 h | R$ 7,59 | R$ 478,17 | — | **R$ 478,17** | 27/02/2027 |
| RAFAEL AUGUSTO NASCIMENTO | 08/2026 | 16,00 h | R$ 9,28 | R$ 222,72 | — | **R$ 222,72** | 27/02/2027 |
| THIAGO HENRIQUE MOURA SILVA | 08/2026 | 16,00 h | R$ 9,28 | R$ 222,72 | — | **R$ 222,72** | 27/02/2027 |
| WELLINGTON BRAGA MONTEIRO | 08/2026 | 16,00 h | R$ 9,28 | R$ 222,72 | — | **R$ 222,72** | 27/02/2027 |
| MARCOS VINICIUS SOUZA LIMA | 08/2026 | 16,00 h | R$ 9,28 | R$ 222,72 | — | **R$ 222,72** | 27/02/2027 |
| ANTONIO DINIZ ASSIS DOS SANTOS | 05/2026 | 16,42 h | R$ 9,28 | R$ 228,57 | R$ 12,21 | **R$ 216,36** | 27/11/2026 |
| EDUARDO PAIVA DOS SANTOS | 08/2026 | 15,00 h | R$ 9,28 | R$ 208,80 | — | **R$ 208,80** | 27/02/2027 |

**O débito (4.767,84 h) não é dinheiro e não entra na conta.** É hora que a pessoa deve —
principalmente 07/2026, com 2.988 h de débito concentradas, que é o mês da cobertura incompleta de
batidas já conhecida (a mesma que a `COBERTURA_MINIMA_FALTAS` protege no motor, W5 §7.2). Descontar
débito medido assim seria exatamente o erro que aquela trava impede; a tela mostra o número e não
propõe nada.

**O prazo — a fonte, dita por extenso.** A CCT SINDECOMPRESTS AM000613/2025, a que temos **como
dado** (`cct_convencoes` — registro MTE AM000613/2025, vigência 01/01–31/12/2026, Manaus/AM; mais
`cct_beneficios`, `cct_cargos`, `cct_funcao_eventos`, `cct_feriados`), **não tem cláusula de banco
de horas**. Procurado em 24/09/2026 por texto em todas as tabelas `cct_*`, no módulo
`backend/modules/cct/` e nos documentos de CCT do repositório: nada sobre compensação ou prazo.
O prazo aplicado é o que o **próprio sistema já usa**:
`operacional/services/time_bank_service.TimeBankService.DEFAULT_EXPIRATION_DAYS = 180` —
**CLT art. 59 §5** (acordo individual, compensação em até 6 meses). A mesma classe tem
`COLLECTIVE_AGREEMENT_EXPIRATION_DAYS = 365`, a **CLT art. 59 §2** (acordo ou convenção coletiva,
até 1 ano). **Qual dos dois vale aqui é decisão do dono** — §7, item 1. Se for o de 1 ano, a
parcela de 03/2026 não vence em 27/09/2026, vence em 31/03/2027, e o número muda.

## 2. O que o DGX tem

Na DGX o banco de horas é `/frontend/CalcularBancoHoras` (APIs `bancohorasjob`,
`bancohoraslotejob`, `bancohoras/filtro`): job por colaborador e por lote (`{idColaborador, dia}` →
`Succeeded {banco}`), «Último cálculo» × «Cálculo dia», saldo por pessoa, `ZerarBancoHorasColaborador(es)`,
calcular saldo do dia anterior (`docs/dgx/lacunas/ponto.md` L39). O elo com a folha é o **Evento**:
o evento decide SOMAR ou SUBTRAIR do banco (`bancoHoras`, um dos 40 atributos do Evento, já virou
coluna de `rubricas_folha` na F1), e o **tipo de cálculo BANCO DE HORAS** na Configuração de Ponto
faz o motor tratar a jornada por banco em vez de por HE (L27). Ou seja: lá, banco de horas e folha
são o mesmo cadastro visto de dois lados; aqui eram dois módulos que não se falavam.

O mapa do §5 daquele documento já registrava «TEMOS (falta zerar — decisão de dono)» para o banco
de horas. A medição do §1 mostra que «temos» era o código, não o dado.

## 3. O que foi feito

| Arquivo | O quê |
|---|---|
| `backend/modules/people_management/folha/services/banco_horas_folha.py` (novo) | `COMPENSACAO_DIAS`, `FATOR_HE`, `DIVISOR_ESCALA`, `DDL`, `_ensure(db)`, `competencia_periodo`, `valor_hora`, **`apurar(db, competencia)`**, `competencias(db)`. Uma consulta só junta ledger (`time_bank`) + espelho (`time_sheets`) + HE do holerite (`hr_payslips.earnings`) + cadastro do empregado |
| `backend/modules/operacional/controllers/redesign_builders/_dgx_x1_banco_horas_folha.py` (novo) | `telas(db, out)` → `banco-horas-folha` (table), `banco-horas-folha-apurar` (form), `banco-horas-vencendo` (table); `router` com `POST /action/banco-horas-folha-apurar` |
| `backend/scripts/orq/test_oraculo_x1_banco_horas_folha.py` (novo) | O oráculo (§4) |
| `.../redesign_builders/departamento_pessoal.py` | 2 linhas no topo (`router`) + 2 no fim do `build()`, comentário `# dgx x1` |
| `.../redesign_builders/_dp_grupos.py` | 3 tuplas no fim do g-folha |

### A decisão de fonte — e por que `estado` existe

`apurar` lê **as duas** fontes, porque a verdade está dividida entre elas (§1):

- **`time_bank`** é o LEDGER — crédito, débito, compensação, vencimento, aprovação. É a fonte viva
  do banco de horas e é dela que saem `saldo_inicial`, `creditado`, `debitado`, `compensado` e
  `vencido_no_periodo`. Hoje ela devolve zero em tudo, porque está vazia.
- **`time_sheets`** é a MEDIÇÃO do ponto — `saldo_ponto` e `he_ponto`. Não é banco de horas; é a
  hora que existiria no banco se alguém a lançasse.

Por isso `estado` tem quatro valores, e o que importa é o segundo:

| estado | quando | como a tela mostra |
|---|---|---|
| `apurado` | há lançamento no `time_bank` | «lançado no banco» (verde) |
| `sem_lancamento` | **saldo medido pelo ponto e NENHUM lançamento no banco** | «saldo no ponto, nada no banco» (**vermelho**) |
| `sem_saldo` | espelho do mês existe e o saldo é zero | «sem saldo no mês» (cinza) |
| `sem_dado` | nem ledger nem espelho | «sem dado» (cinza) |

Hoje **273 das 301 linhas apuradas são `sem_lancamento`**. Zero por falta de dado nunca é escrito
como zero por ausência de saldo — é a regra da casa, e aqui ela é o achado inteiro.

**Nenhuma tabela de saldo paralela foi criada.** `banco_horas_conferencia` é conferência (a mesma
ideia de `folha_beneficio_conferencia`, frente 03), idempotente por `(employee_id, competencia)`
via `ON CONFLICT DO UPDATE`. O saldo continua morando em `time_bank`.

### DDL que `_ensure` aplica em produção no 1º acesso (idempotente)

```sql
CREATE TABLE IF NOT EXISTS banco_horas_conferencia (
  id bigserial PRIMARY KEY,
  employee_id uuid NOT NULL,
  competencia date NOT NULL,
  estado varchar(24) NOT NULL,          -- apurado | sem_lancamento | sem_saldo | sem_dado
  fonte  varchar(20) NOT NULL,          -- time_bank | espelho | sem_dado
  saldo_inicial numeric(10,2) NOT NULL DEFAULT 0,
  creditado     numeric(10,2) NOT NULL DEFAULT 0,
  debitado      numeric(10,2) NOT NULL DEFAULT 0,
  compensado    numeric(10,2) NOT NULL DEFAULT 0,
  vencido_no_periodo numeric(10,2) NOT NULL DEFAULT 0,
  saldo_final   numeric(10,2) NOT NULL DEFAULT 0,
  saldo_ponto   numeric(10,2) NOT NULL DEFAULT 0,   -- espelho: trabalhado − previsto
  he_ponto      numeric(10,2) NOT NULL DEFAULT 0,   -- espelho: overtime_total
  valor_hora    numeric(12,2),
  a_pagar_por_vencimento numeric(12,2) NOT NULL DEFAULT 0,
  ja_pago_como_he        numeric(12,2) NOT NULL DEFAULT 0,
  vence_em date,
  calculado_em timestamptz NOT NULL DEFAULT now(),
  UNIQUE (employee_id, competencia));
CREATE INDEX IF NOT EXISTS ix_banco_horas_conferencia_venc
  ON banco_horas_conferencia (vence_em) WHERE vence_em IS NOT NULL;
```

Nenhuma semente. Nenhum DROP/DELETE/UPDATE em dado que a frente não criou. Nenhuma linha em
`time_bank`, `hr_payslips`, `hr_payslip_items` ou `time_sheets`.

### Telas (g-folha, deep-link `/redesign/departamento-pessoal?t=<id>`)

Grupo **`g-folha`**, não `g-ponto`: o ponto MEDE a hora; é a folha que decide se ela vira dinheiro,
e quem responde por hora vencida sem pagar é o DP. As abas ficam encostadas em «Rubricas» (F1) e
«Mapa evento → rubrica» (W5), as outras partes do mesmo assunto.

- **`banco-horas-folha`** (table, 51 linhas em 09/2026): Colaborador · Saldo inicial · Creditado ·
  Debitado · Compensado · **Saldo do ponto** · Vencido · A pagar (vencido) · Já pago como HE ·
  Vence em · Situação. Filtros Situação × Fonte. O subtítulo carrega o número do §1 inteiro,
  incluindo **o acumulado de todas as competências apuradas** — é lá que aparece o R$ 8.404,86.
- **`banco-horas-folha-apurar`** (form, 1 campo): escolhe a competência e roda. Idempotente.
- **`banco-horas-vencendo`** (table, 16 linhas hoje): Colaborador · Vence em · Horas · Faltam ·
  Referência · **Fonte**. Duas fontes na mesma tabela, cada uma dizendo o que é: «lançado»
  (crédito aprovado no `time_bank` com `expiration_date` na janela) e «projeção» (crédito medido
  pelo espelho, sem lançamento — `competência + 180 dias`). Hoje são 16 projeções de 03/2026
  vencendo em **27/09/2026, faltam 3 dias**.

As três telas carregam, no subtítulo, a frase «PARALELO CEGO: esta apuração grava só em
`banco_horas_conferencia` — não muda folha, holerite nem pagamento, e não lança nada no banco de
horas». Não é decoração: é o que o oráculo (d) prova.

### O cadastro `ponto_evento_rubrica` (item 4 do brief) — NÃO foi mexido

`banco_horas_credito` e `banco_horas_debito` **não ganharam linha no mapa da W5**, porque a
condição do brief não se cumpre: **não existe rubrica para eles em `rubricas_folha`**. As 35
rubricas ativas foram varridas — não há nenhuma de banco de horas, compensação ou crédito/débito de
hora (`descricao ILIKE '%banco%' OR '%compens%'` → 0 linhas). Inventar um código seria fabricar
dado trabalhista. Os dois eventos seguem no combo da tela da W5 marcados «(o motor não produz)».
**É essa rubrica que falta decidir, e é ela que trava a ligação** — §7, item 2.

## 4. Oráculo — `backend/scripts/orq/test_oraculo_x1_banco_horas_folha.py`

Afirma: **(a)** `apurar` 2× não duplica nem muda número; **(b)** saldo/crédito/débito/compensado/
vencido == recontados por SQL PRÓPRIO direto em `time_bank`; **(c)** `ja_pago_como_he` == a soma
das verbas de hora extra do holerite, recontada por SQL próprio sobre `hr_payslips.earnings`;
**(d)** **nenhuma linha de folha muda** — Σ|Δ| de `total_earnings + total_deductions + net_salary`
sobre TODOS os `hr_payslips`, fotografado antes e depois, = R$ 0,00, e a contagem de holerites não
muda; **(e)** `vencido_no_periodo` e `a_pagar_por_vencimento` nunca são negativos; **(f)** fixture
de crédito vencido aparece em `a_pagar_por_vencimento` com o valor CLT (horas × valor_hora × 1,5);
**(g)** fiação (o build do DP chama a frente e as três abas estão em `_dp_grupos`).

```bash
WT=$(git rev-parse --show-toplevel)
ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' \
       | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\n' ' ')
docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" \
  --tmpfs /app/logs:rw,mode=1777 --tmpfs /app/uploads:rw,uid=999,gid=999 \
  -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env \
  -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \
  conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_x1_banco_horas_folha.py
```

**VERMELHO** (antes de qualquer código):
```
FALHOU: banco_horas_folha não importa: ImportError: cannot import name 'banco_horas_folha' from 'modules.people_management.folha.services'
TOTAL desvios: 1
exit=1
```

**VERMELHO na fiação** (serviço pronto, telas ainda não plugadas — o passo do meio):
```
09/2026 · 51 pessoa(s) apurada(s) · time_bank: 0 lançamento(s) · espelho: 51 linha(s) · saldo do ponto: -715.19 h · vencido: 10.00 h (R$ 139,20) · já pago como HE: R$ 0,00 · Σ|Δ| folha = R$ 0,00
FALHOU: (g) fiação não verificável: ImportError: cannot import name '_dgx_x1_banco_horas_folha' from 'modules.operacional.controllers.redesign_builders'
TOTAL desvios: 1
exit=1
```

**VERDE** (depois do serviço + telas + fiação):
```
09/2026 · 51 pessoa(s) apurada(s) · time_bank: 0 lançamento(s) · espelho: 51 linha(s) · saldo do ponto: -715.19 h · vencido: 10.00 h (R$ 139,20) · já pago como HE: R$ 0,00 · Σ|Δ| folha = R$ 0,00
TOTAL desvios: 0
OK banco de horas × folha: apuração idempotente, saldo == recontado no time_bank, HE == a do holerite, vencido ≥ 0, crédito vencido vira a pagar (CLT art. 59 §3), e nenhuma linha de folha mudou (Σ|Δ| = R$ 0,00)
exit=0
```

**O oráculo morde.** Trocando `vc = max(_h(vc), 0)` por `vc = 0` no serviço (ignorar crédito vencido):
```
09/2026 · 51 pessoa(s) apurada(s) · ... · vencido: 0.00 h (R$ 0,00) · ... · Σ|Δ| folha = R$ 0,00
FALHOU: (b) 2430761d-172e-44b8-a817-edfea166e321 vencido_no_periodo: apurado 0.00 × recontado 10.00
FALHOU: (f) crédito vencido da fixture não entrou: vencido_no_periodo=0.00 (esperado ≥ 10)
TOTAL desvios: 2
exit=1
```
(revertido em seguida; o verde acima é o do código commitado)

**Prova por HTTP** (`teste-dgx-x1`, porta 8261, **parado ao fim**):
```
GET /api/v1/redesign/data/departamento-pessoal → 200
g-folha tabs: [... 'folha-apontamentos-importar', 'banco-horas-folha', 'banco-horas-folha-apurar', 'banco-horas-vencendo']

banco-horas-folha: table · 51 linhas · cols [Colaborador, Saldo inicial, Creditado, Debitado,
  Compensado, Saldo do ponto, Vencido, A pagar (vencido), Já pago como HE, Vence em, Situação]
  sub: «51 pessoa(s) · 0 com lançamento no banco de horas · 51 com saldo medido pelo ponto e
       NENHUM lançamento no banco · o ponto mediu 44.88h de crédito e 760.07h de débito no mês ·
       ACUMULADO em 6 competência(s), 82 pessoa(s): 933.32h de crédito e 4767.84h de débito;
       pela CLT art. 59 §3 o crédito valeria R$ 12.560,43 como hora extra e o holerite pagou
       R$ 4.155,57 — sobram R$ 8.404,86 que não foram pagos nem compensados. …»
  ['ADAILSON SERRA ALVES','+0.00h','0.00h','0.00h','0.00h','-33.03h','0.00h','—','—','—','saldo no ponto, nada no banco']
  ['ALAN VIEIRA DA SILVA','+0.00h','0.00h','0.00h','0.00h','+4.53h','0.00h','—','—','29/03/2027','saldo no ponto, nada no banco']

banco-horas-folha-apurar: form · 1 campo · submit banco-horas-folha-apurar
POST 2026-03 → 200 «44 pessoa(s) · 40 com saldo no ponto e nenhum lançamento no banco …»
POST 2026-05 → 200 (38) · 2026-06 → 200 (46) · 2026-07 → 200 (58) · 2026-08 → 200 (65) · 2026-09 → 200 (51)
POST 'xx/yy' → 400 · POST '' → 400 «Escolha a competência.»

banco-horas-vencendo: table · 16 linhas · cols [Colaborador, Vence em, Horas, Faltam, Referência, Fonte]
  ['ADAILSON SERRA ALVES','27/09/2026','0.08h','3 dia(s)','03/2026','projeção']
  ['AILTON CÉSAR VASCONCELOS','27/09/2026','10.22h','3 dia(s)','03/2026','projeção']
  ['ANTONIO DINIZ ASSIS DOS SANTOS','27/09/2026','11.15h','3 dia(s)','03/2026','projeção']

QA_API=http://127.0.0.1:8261 checar_tela_sem_porta.py → TOTAL: 1 sem porta (crm/atividades, anterior à X1)
```
Fixtures `'FIXTURE DGX X1'` apagadas do sandbox ao fim (`count(*) = 0`; `time_bank` voltou a 0 linhas).

**Vizinhos, todos verdes** depois da frente:
`test_oraculo_w5_mapa_evento_rubrica` → 0 desvios (Σ|Δ| = R$ 0,00, 153 verbas) ·
`test_oraculo_w1_dias_trabalhados` → 0 desvios (Σ|Δ| verba a verba R$ 0,00) ·
`test_oraculo_rubricas_dizem_a_verdade` → 0 desvios.

**Uma mina registrada de passagem:** importar QUALQUER `_dgx_*` antes do `departamento_pessoal`
dispara import circular (o discovery do `redesign_data_controller` carrega o builder do DP no meio
da inicialização da frente). O `safe_import` engole e o app sobe igual, mas o aviso confunde.
Medido também com a W3 — **não é próprio da X1**. O `# isort: skip` no bloco (g) do oráculo existe
por isso: o `ruff --fix` reordenou os dois imports alfabeticamente e acendeu o aviso.

## 5. O que NÃO foi feito e por quê

- **O motor não lê nada disto.** `calculo_service.py` segue igual, não emite verba de banco de
  horas e não compensa HE contra saldo. Caminho de dinheiro: Σ|Δ| = R$ 0,00 garantido por não
  tocar. A apuração é conferência, não cálculo.
- **Nada foi lançado no `time_bank`.** Seria a coisa óbvia — transportar as 933,32 h medidas pelo
  ponto para o ledger e o banco de horas passaria a existir de verdade. Não foi feito de propósito:
  criar 273 lançamentos de crédito/débito num ledger que tem aprovação, compensação e vencimento é
  criar 273 obrigações trabalhistas de uma vez, a partir de uma medição de ponto que em 07/2026
  tem 2.988 h de débito por cobertura incompleta de batidas. «Se vai consertar muitos registros de
  uma vez, pare» — e aqui a regra que falta é a decisão do §7.1 (qual prazo) e do §7.3 (se há
  acordo de banco de horas assinado).
- **`banco_horas_credito`/`banco_horas_debito` não entraram em `ponto_evento_rubrica`.** Não há
  rubrica real para eles (§3). O brief previa exatamente isso: não inventar. §7.2.
- **Não há botão «lançar no banco de horas a partir do ponto».** É o passo seguinte natural e
  depende inteiramente do §7. Quando existir, este oráculo é a trava dele: no dia em que a folha
  passar a ler o banco, (d) continua exigindo Σ|Δ| = R$ 0,00 contra o que estiver publicado.
- **`zerar saldo`** (o `ZerarBancoHorasColaborador` da DGX) não entrou — já estava marcado como
  «decisão de dono» no mapa da lacuna, e apagar saldo é a operação mais perigosa deste módulo.
- **Não se mexeu nas 8 telas `banco-horas*` do Operacional** (g-equipe). Elas continuam sendo a
  porta de lançamento/aprovação/compensação. A X1 é a leitura do outro lado, na folha.
- **02/2026 ficou de fora da apuração de demonstração** (1 linha de espelho, saldo zero). Aparece
  no combo; basta apurar.
- **Frontend**: nada. `table` e `form` renderizam genericamente; as abas vêm do `_dp_grupos`.
- **`checar_regressao.py`**: nada — `scripts/orq/test_*.py` é globado pela meia-noite (o
  orquestrador registra, conforme o contrato).

## 6. Como o Jordan testa amanhã

1. Depois do bake: **Departamento Pessoal → Folha de pagamento → aba «Banco de horas vencendo
   (60 dias)»** (`/redesign/departamento-pessoal?t=banco-horas-vencendo`). Comece por ela: são as
   16 pessoas com crédito de março vencendo em **27/09/2026**. A coluna «Fonte» diz «projeção» —
   quer dizer que a hora foi medida pelo ponto e **nunca virou lançamento no banco de horas**.
2. Vá para a aba **«Banco de horas × folha»**. Leia o subtítulo inteiro: ele traz o acumulado —
   **933,32 h de crédito, R$ 12.560,43 devidos pela CLT art. 59 §3, R$ 4.155,57 pagos, R$ 8.404,86
   não pagos nem compensados**. Esse é o número da frente.
3. Olhe a coluna **«Situação»**: todas em vermelho, «saldo no ponto, nada no banco». Isso não é
   defeito da tela — é o estado real: `time_bank` tem zero linhas desde sempre.
4. Compare com a coluna **«Já pago como HE»**: ela vem do holerite. Onde há valor, a folha pagou
   aquela hora; onde há «—», não pagou.
5. Aba **«Apurar banco de horas × folha»**: escolha 08/2026 e rode. Rode de novo: o resultado é
   idêntico (idempotente). Depois volte à primeira aba e troque de competência mentalmente pelo
   subtítulo — o acumulado sobe conforme você apura mais meses.
6. Confira que **nada mudou na folha**: abra um holerite de 08 ou 09/2026 antes e depois. É o que
   o oráculo (d) prova com Σ|Δ| = R$ 0,00, mas vale ver com os olhos.

## 7. Decisões que só o dono pode tomar

1. **Qual é o prazo de compensação: 6 meses ou 1 ano?** A CLT art. 59 §5 dá 6 meses ao acordo
   individual e o §2 dá 1 ano ao acordo/convenção coletiva. A CCT SINDECOMPRESTS AM000613/2025
   que temos como dado **não fala de banco de horas** — então hoje o sistema aplica 180 dias por
   padrão do código, não por cláusula. A resposta muda o §1 inteiro: com 1 ano, o crédito de
   03/2026 vence em 31/03/2027 em vez de 27/09/2026, e nada está prestes a virar passivo.
2. **Qual rubrica recebe o banco de horas?** É a pergunta que trava a ligação com a folha. Não
   existe rubrica de banco de horas em `rubricas_folha` — e enquanto não existir, os eventos
   `banco_horas_credito`/`banco_horas_debito` não podem entrar no mapa da W5 sem virar ficção.
   São duas decisões juntas: (a) o crédito vencido é pago na rubrica de HE que já existe (0010
   Hora Extra 50%) ou numa rubrica própria de «banco de horas»? (b) o débito desconta em folha —
   e, se sim, com que trava de cobertura de batidas (a de 07/2026 sozinha valeria R$ 26.234,49 de
   desconto, contra gente que trabalhou)?
3. **Existe acordo de banco de horas assinado?** Sem acordo (individual escrito ou coletivo), a
   CLT não admite banco de horas — a hora extra é simplesmente devida no mês, com adicional. Se
   não há acordo, os R$ 8.404,86 não são «saldo a compensar», são **hora extra vencida não paga**,
   e a conversa passa a ser com a contabilidade e não com a escala. Se há, o documento precisa
   entrar no GED e a data dele define de quando conta o prazo.
4. **O que fazer com os R$ 1.459,88 de março, que vencem em 27/09/2026?** Três caminhos: pagar
   como HE na folha de 09 ou 10/2026, programar folga compensatória antes do dia 27 (não dá tempo
   para as 119 h), ou reconhecer o passivo. É decisão de caixa e de risco, não de sistema.
5. **Transportar as 933,32 h medidas pelo ponto para o `time_bank`?** É o que faria o módulo do
   Operacional passar a existir de verdade. Não foi feito (§5) porque cria 273 obrigações de uma
   vez a partir de uma medição que em julho está visivelmente contaminada. Se o dono quiser,
   o caminho honesto é por competência, começando pelas que têm cobertura de batidas boa
   (08 e 09/2026), e com aprovação humana linha a linha — que é exatamente o que as telas
   `banco-horas-lancar` e `banco-horas-aprovar` já fazem.
6. **O débito de 07/2026 (2.988 h) é real?** É o mesmo mês que a `COBERTURA_MINIMA_FALTAS` protege
   no motor de folha. Se for cobertura incompleta de batidas, o número não significa nada e a tela
   deveria marcá-lo como tal; se for real, é 2.988 h que a empresa pagou e não recebeu. Só quem
   conhece a operação de julho responde.
