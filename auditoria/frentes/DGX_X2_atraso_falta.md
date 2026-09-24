# DGX X2 — Atraso e falta justificada: o ponto mede, a folha nunca vê

**Branch** `dgx/x2-atraso-falta-justificada` · **Módulo** folha (+ leitura de ponto/SST) ·
**Data** 24/09/2026 · **Sandbox** `conecta_pro_staging` · **Porta de teste** 8262
(`teste-dgx-x2`, parado ao fim)

> **Paralelo cego.** Nada nesta frente muda um centavo de holerite. O oráculo prova
> Σ|Δ| = R$ 0,00 em `total_earnings`, `total_deductions` e `net_salary` das duas competências,
> antes e depois de cada apuração.

---

## 1. Estado antes — a medição nominal (08 e 09/2026)

### 1.a Atraso: o ponto mede, a folha não desconta

Régua: a da frente 04 (`ponto/mapa_de_ponto.py`) — **importada, não recriada**
(`_carregar`, `_tolerancia`, `classificar`). Estado `atendido_com_atraso`, tolerância de
**15 min** resolvida pela cascata da F7 (hoje só existe a linha `empresa`; `geofence_zones`
tem zero tolerâncias cadastradas).

| Competência | Pessoas | Turnos com atraso | Minutos | Além da tolerância | **R$ estimado** | Descontado na folha |
|---|---:|---:|---:|---:|---:|---:|
| 08/2026 | 23 | 354 | 23.042 | 17.957 | **R$ 2.378,86** | **R$ 0,00** |
| 09/2026 | 28 | 146 | 7.294 | 5.434 | **R$ 698,71** | **R$ 0,00** |
| **Total** | — | 500 | 30.336 | 23.391 | **R$ 3.077,57** | **R$ 0,00** |

Se o dono decidir descontar o atraso **inteiro** (sem tolerância), o mesmo dado dá
**R$ 3.983,18** (R$ 3.042,01 + R$ 941,17). A diferença — R$ 905,61 — é exatamente o que a
tolerância de 15 min custa por mês e meio. §7, decisão 2.

Os dez maiores de 08/2026 (minutos além da tolerância × valor-hora do holerite):

| Pessoa | Turnos | Minutos | Além | R$/h | R$ |
|---|---:|---:|---:|---:|---:|
| PAULO DA SILVA LAMEGO | 25 | 2.724 | 2.349 | 7,59 | 297,15 |
| DANIEL VIDAL LARROQUE | 21 | 1.792 | 1.477 | 9,28 | 228,45 |
| MAURICIO ALVES CHAGAS | 10 | 1.467 | 1.332 | 9,28 | 206,00 |
| GRACIENE PEREIRA DE CASTRO | 26 | 1.680 | 1.305 | 7,59 | 165,14 |
| MALAQUIAS PEREIRA FERREIRA | 25 | 1.571 | 1.211 | 7,59 | 153,21 |
| OSCAR SOARES DA COSTA FILHO | 26 | 1.588 | 1.198 | 7,59 | 151,55 |
| CELIANE GARCIA DE SOUSA | 26 | 1.579 | 1.189 | 7,59 | 150,47 |
| ADEMIR SALUSTIANO DE SOUZA FILHO | 26 | 1.575 | 1.185 | 7,59 | 149,94 |
| GEILSON RODRIGUES DE ANDRADE | 25 | 1.500 | 1.125 | 7,59 | 142,31 |
| ANGELA LOPES MACEDO | 24 | 1.444 | 1.084 | 7,59 | 137,17 |

E os seis maiores de 09/2026: CELIANE (995 min além, R$ 125,83) · PAULO LAMEGO (739,
R$ 93,53) · ANTONIO CARLOS VIEIRA (393, R$ 51,89) · GRACIENE (392, R$ 49,55) ·
KALEL (364, R$ 48,02) · GEILSON (360, R$ 45,54). A lista nominal completa (51 linhas)
está na tela `atraso-conferencia` e na tabela `ponto_folha_conferencia`.

**O achado que quase virou dinheiro errado.** A régua da frente 04 aceita como presença a
primeira batida entre 2 h antes do início e o fim do turno. Quem **esqueceu a batida de
entrada** e só bateu na saída aparece como `atendido_com_atraso` com o turno inteiro de
"atraso": EDIWILSON CORREA MARQUES, 4.563 min em 9 turnos de agosto — 8 h de "atraso" por
turno. Isso não é atraso, é batida faltando, e descontá-lo seria tirar um dia inteiro de quem
trabalhou. Por isso todo turno cujo atraso alcança **50 % da jornada planejada** é marcado
`entrada_ausente`, sai da conta de dinheiro e vai para uma coluna própria:

| Competência | Minutos descartados | (valor que NÃO virou estimativa) |
|---|---:|---:|
| 08/2026 | 7.459 | R$ 1.153,52 |
| 09/2026 | 12.986 | R$ 2.008,60 |

Em 09/2026 os descartados (12.986 min) são **64 %** de tudo que o ponto chamou de atraso.
Sete pessoas ficaram com R$ 0,00 de estimativa porque **todos** os seus turnos caíram nessa
classificação (MAURICIO, EDIWILSON, DANIEL, AILTON, JEOVANE, EULER, ANTONIO CASTRO GAMA).
Isso é, em si, o maior achado operacional da frente: **não é gente atrasada, é batida de
entrada que não está sendo feita** — e é o supervisor, não a folha, quem resolve. §7, decisão 3.

### 1.b Falta descontada que tinha justificativa aprovada — o passivo

Rubricas confirmadas em `rubricas_folha`: **1051 «Faltas»** e **1053 «DSR sobre Faltas»**,
ambas ativas, ambas `desconto`. São as únicas — não há rubrica de atraso, nem de falta
justificada/abono (§7, decisão 1).

| Competência | Pessoas com 1051 | R$ 1051 | Pessoas com 1053 | R$ 1053 | **Total descontado** |
|---|---:|---:|---:|---:|---:|
| 08/2026 | 0 | R$ 0,00 | 0 | R$ 0,00 | **R$ 0,00** |
| 09/2026 | 19 | R$ 2.575,28 | 12 | R$ 2.018,58 | **R$ 4.593,86** |

08/2026 saiu zerado por causa da trava de cobertura do `calculo_service` (L548-582): as
nossas batidas ainda não eram a maioria do mês.

Das 19 pessoas descontadas em 09/2026, **quantas tinham justificativa aprovada ou atestado?**

> **Zero. R$ 0,00 de passivo medido.**

Mas o motivo não é que o sistema acerta — é que **ninguém aprova justificativa**:

| `gp_justifications` | Quantidade |
|---|---:|
| Total na base (toda a história) | 13 |
| `pendente` | **13** |
| `aprovada` | **0** |
| `rejeitada` | 0 |
| Mais antiga parada | 21/07/2026 (atestado médico, 65 dias) |
| Do tipo `falta` | **0** (12 são `atraso`, 1 é `atestado_medico`) |

E `sst_afastamentos` com atestado cobrindo 09/2026: 2 pessoas (CARLOS ALBERTO ASSIS DE LIMA,
CID M51; CINTIA BEZERRA OLIVEIRA, CID T07) — nenhuma das duas está entre as 19 descontadas.

Duas das 19 (EDILENE SALES SOUSA e TELMA MARIA LAGES MEIRA) **têm justificativa na base** —
e ela está `pendente`. Se alguém apertar «aprovar» nessas duas, o passivo deixa de ser R$ 0,00
no mesmo instante, porque o motor de folha **não consulta `gp_justifications` em momento
nenhum**: ele lê `time_sheets.unjustified_absent_days` e desconta. A aprovação não volta para
o espelho. §7, decisão 4.

O oráculo prova que a medição morde: com uma justificativa APROVADA de fixture para quem levou
1051, a linha vira `divergente=true, sentido='passivo'` com valor proporcional aos dias
cobertos.

### 1.c Falta justificada que NÃO foi descontada — o caminho certo

| Competência | Pessoas | Dias abonados | Descontado |
|---|---:|---:|---:|
| 08/2026 | 2 | 31 + 31 | R$ 0,00 |
| 09/2026 | 2 | 30 + 30 | R$ 0,00 |

São os dois afastamentos com atestado (CARLOS ALBERTO, CINTIA). O certo acontece — mas
**por outro caminho**: `coorte_ponto.SQL_NAO_AUSENTE_HOJE` tira o afastado da coorte de ponto,
então o espelho nunca marca falta para eles. Não há nenhuma linha de código que diga «não
desconte porque há atestado». É a coorte do ponto que salva, não a regra da folha.
`justified_absent_days` em `time_sheets` é **0 em todos os meses de 2026** — a coluna existe e
nunca foi preenchida.

### 1.d Os dois sentidos, somados

| Sentido | 08/2026 | 09/2026 | Total |
|---|---:|---:|---:|
| Atraso não descontado (empresa paga sem receber) | R$ 2.378,86 | R$ 698,71 | **R$ 3.077,57** |
| Falta justificada descontada (passivo do colaborador) | R$ 0,00 | R$ 0,00 | **R$ 0,00** |

O passivo é R$ 0,00 **hoje**, e é frágil: ele depende de que ninguém aprove justificativa.

---

## 2. O que o DGX tem

Na DGX, `atraso` e `falta justificada (abonada)` são dois dos eventos do mapa
evento→rubrica da «Configuração de Ponto» (`docs/dgx/lacunas/ponto.md` L27), com tolerância
por escopo e tipo de cálculo. A W5 já declarou os 15 eventos e semeou os 8 que o nosso motor
produz; `atraso` e `falta_justificada` estão lá marcados **«(o motor não produz)»**
(`DGX_W5_mapa_evento_rubrica.md` §7, itens 1 e 4). Esta frente é a medição de quanto custa
cada um desses dois buracos — **não** a construção da rubrica, que é decisão do dono.

---

## 3. O que foi feito

| Arquivo | O quê |
|---|---|
| `backend/modules/people_management/folha/services/atraso_falta_conferencia.py` (novo) | `DDL`, `_ensure`, `competencia_tupla/iso`, `valor_hora_do_holerite`, `atraso_por_pessoa` (importa a régua da frente 04), `falta_justificada_por_pessoa`, `apurar(db, competencia)`, `resumo`. `FRACAO_ENTRADA_AUSENTE = 0.5` |
| `backend/modules/operacional/controllers/redesign_builders/_dgx_x2_atraso_falta.py` (novo) | `telas(db, out)` → `atraso-conferencia`, `falta-justificada-conferencia`, `ponto-folha-apurar`; `router` com `POST /action/ponto-folha-apurar`; anexa as 3 abas ao fim do `g-folha` |
| `backend/scripts/orq/test_oraculo_x2_atraso_falta.py` (novo) | O oráculo (§4) |
| `.../redesign_builders/departamento_pessoal.py` | 2 linhas no topo (`router`) + 3 no FIM do `build()` (`telas`), comentário `# dgx x2` |
| `.../redesign_builders/_dp_grupos.py` | 3 tuplas no **FIM** do `g-folha` |

**Nada foi tocado** em `calculo_service.py`, `hr_payslips`, `time_sheets`, `alembic/`,
`frontend/`, `checar_regressao.py`.

### DDL que `_ensure` aplica em produção no 1º acesso (idempotente)

```sql
CREATE TABLE IF NOT EXISTS ponto_folha_conferencia (
  id serial PRIMARY KEY,
  competencia varchar(7) NOT NULL,                       -- 'AAAA-MM'
  tipo varchar(24) NOT NULL CHECK (tipo IN ('atraso','falta_justificada')),
  employee_id varchar(50) NOT NULL,
  employee_nome varchar(200) NOT NULL,
  ponto_qtd numeric(12,2) NOT NULL DEFAULT 0,            -- minutos (atraso) ou dias (falta)
  ponto_qtd_util numeric(12,2) NOT NULL DEFAULT 0,       -- minutos ALÉM da tolerância
  ponto_qtd_descartada numeric(12,2) NOT NULL DEFAULT 0, -- minutos de 'entrada ausente'
  unidade varchar(10) NOT NULL DEFAULT 'min',
  valor_hora numeric(12,4),                              -- do HOLERITE da pessoa
  valor_estimado numeric(12,2) NOT NULL DEFAULT 0,
  folha_qtd numeric(12,2) NOT NULL DEFAULT 0,
  folha_valor numeric(12,2) NOT NULL DEFAULT 0,
  divergente boolean NOT NULL DEFAULT false,
  sentido varchar(16) NOT NULL DEFAULT 'ok',             -- empresa_paga | passivo | ok
  observacao text,
  detalhe jsonb NOT NULL DEFAULT '[]'::jsonb,            -- dia a dia
  apurado_em timestamptz NOT NULL DEFAULT now());
CREATE UNIQUE INDEX IF NOT EXISTS ux_ponto_folha_conferencia
  ON ponto_folha_conferencia (competencia, tipo, employee_id);
CREATE INDEX IF NOT EXISTS ix_ponto_folha_conferencia_div
  ON ponto_folha_conferencia (competencia, tipo) WHERE divergente;
```

Idempotência pela chave única + `ON CONFLICT DO UPDATE`; quem sai da apuração é removido — e o
`DELETE` só alcança linhas desta tabela, que a frente criou. Nenhum DDL/DML fora dela.

### Telas (g-folha, deep-link `/redesign/departamento-pessoal?t=<id>`)

- **`atraso-conferencia`** (table, 51 linhas): Pessoa · Competência · Turnos · Atraso total ·
  Além da tolerância · Valor-hora · **R$ estimado** · **Descontado?** («NÃO — sem rubrica»,
  em vermelho, em todas) · Entrada ausente. Filtros Competência × Estado. Cada linha abre o
  **dia a dia** nos docs: `01/09 · 07:00–16:00 · Condomínio Ideal Flores` → «bateu 07:34 (app)
  — 34 min depois do início, 19 além da tolerância de 15 min».
- **`falta-justificada-conferencia`** (table, 23 linhas): Pessoa · Competência · Dia · Motivo
  da justificativa · Aprovada por · Descontou na folha? · Situação. As divergentes em
  **vermelho** («DESCONTOU MESMO ASSIM»); as certas em verde («não descontou»).
- **`ponto-folha-apurar`** (form, 1 campo): competência → `POST action/ponto-folha-apurar`,
  `showResult`, devolve a frase inteira com os dois sentidos e «Nenhum holerite foi tocado».

O subtítulo das duas tabelas diz, em letras claras, que **o R$ é ESTIMATIVA** (minutos além da
tolerância × valor-hora do holerite da própria pessoa) e que a tela não muda um centavo.

---

## 4. Oráculo — `backend/scripts/orq/test_oraculo_x2_atraso_falta.py`

```bash
WT=$(git rev-parse --show-toplevel)
ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' \
       | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\n' ' ')
docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" \
  --tmpfs /app/logs:rw,mode=1777 --tmpfs /app/uploads:rw,uid=999,gid=999 \
  -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env \
  -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \
  conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_x2_atraso_falta.py
```

Afirma **(a)** paralelo cego (Σ|Δ| = R$ 0,00 nos holerites, contagem de 1051/1053 intacta) ·
**(b)** apurar 2× não duplica · **(c)** os minutos de cada pessoa recontados por **SQL
próprio**, que reimplementa a régua da frente 04 (janela de presença, primeira batida,
check-in manual, geofence por haversine, tolerância) — tolerância R$ 0,00, o minuto tem de
bater · **(d)** `valor_hora` == `base_salary ÷ divisor` do holerite e `valor_estimado` ==
minutos além × valor-hora · **(e)** fixture de justificativa APROVADA para quem levou 1051
faz a linha virar `divergente/passivo` · **(f)** fiação.
Ele também **grita se a tolerância ganhar escopo** (`ponto_configuracoes` fora de `empresa`,
ou `geofence_zones.entry_tolerance_minutes`): aí o SQL de reconta deixa de ser fiel e precisa
acompanhar a cascata, em vez de mentir verde.

**VERMELHO** (antes do código, só o oráculo escrito):
```
FALHOU: 2026-09: a conferência gravou atraso de ANTONIO CARLOS CASTRO GAMA e o SQL não vê nenhum
FALHOU: 2026-09: a conferência gravou atraso de DANIEL VIDAL LARROQUE e o SQL não vê nenhum
FALHOU: 2026-09: VANDERLICE SANTOS DA SILVA — minutos descartados: SQL 0.00 × conferência 722.16
FALHOU: 2026-09: EDIWILSON CORREA MARQUES — minutos descartados: SQL 2637.00 × conferência 3359.19
FALHOU: 2026-09: KALEL SILVA DE JESUS R$ 48.01 ≠ 48.02 (min além da tolerância × valor-hora)
FALHOU: 2026-08: KALEL SILVA DE JESUS — minutos descartados: SQL 0.00 × conferência 300.00
FALHOU: 2026-08: VANDERLICE SANTOS DA SILVA — minutos descartados: SQL 0.00 × conferência 361.10
FALHOU: 2026-08: TELMA MARIA LAGES MEIRA — minutos descartados: SQL 0.00 × conferência 380.28
FALHOU: departamento_pessoal.py não chama a frente X2 — tela sem porta
FALHOU: a aba 'atraso-conferencia' não está em _dp_grupos.py — tela sem porta
FALHOU: a aba 'falta-justificada-conferencia' não está em _dp_grupos.py — tela sem porta
FALHOU: a aba 'ponto-folha-apurar' não está em _dp_grupos.py — tela sem porta
TOTAL desvios: 12
exit=1
```

**O vermelho pegou dois defeitos reais antes de qualquer tela existir:**
1. o SQL não conhecia o **check-in manual** (`shifts.actual_start_time`), que `classificar` usa
   quando não há batida na janela — quatro pessoas somem da reconta;
2. o serviço multiplicava os minutos **cheios** por valor-hora e gravava `ponto_qtd_util`
   arredondado: R$ 0,01 de diferença entre o número escrito na tela e o número cobrado.
   Arredondar antes de virar dinheiro.

**VERDE** (depois do serviço, das telas e da fiação):
```
09/2026: atraso 28 pessoa(s) · 7285 min (5425 além da tolerância, 12981 descartados) ≈ R$ 698.71 ·
         faltas descontadas R$ 4593.86 · passivo (descontado COM abono) R$ 0.00 em 0 pessoa(s) ·
         abonado e não descontado: 2 pessoa(s)
08/2026: atraso 23 pessoa(s) · 23036 min (17951 além da tolerância, 7457 descartados) ≈ R$ 2378.86 ·
         faltas descontadas R$ 0.00 · passivo (descontado COM abono) R$ 0.00 em 0 pessoa(s) ·
         abonado e não descontado: 2 pessoa(s)
TOTAL desvios: 0
OK conferência atraso/falta: paralelo cego (Σ|Δ| = R$ 0,00 nos holerites), apurar 2× não duplica,
minutos == régua da frente 04 recontada por SQL, R$ do valor-hora do holerite, falta descontada
com abono vira divergência
exit=0
```
(09/2026 é o mês corrente: os números movem entre corridas porque chegam batidas novas. O
oráculo compara serviço × SQL na MESMA corrida, então isso não o faz piscar.)

**Prova por HTTP** (`teste-dgx-x2`, porta 8262, parado ao fim):
```
GET /api/v1/redesign/data/departamento-pessoal → 200
g-folha tabs (últimas): [... 'folha-apontamentos-importar', 'atraso-conferencia',
                         'falta-justificada-conferencia', 'ponto-folha-apurar']
atraso-conferencia: table · 51 linhas · 9 colunas
  ['CELIANE GARCIA DE SOUSA','09/2026','17 turno(s)','20h49','16h34','R$ 7,59/h','R$ 125,83',
   'NÃO — sem rubrica','—']  docs: ['Como foi medido','01/09 · 07:00–16:00 · Condomínio Ideal…', …]
falta-justificada-conferencia: table · 23 linhas · 7 colunas
  ['CARLOS ALBERTO ASSIS DE LIMA','09/2026','01/09 +29d','Doenca com atestado medico',
   'SST · CID M51','não','não descontou']
ponto-folha-apurar: form · 1 campo · submit ponto-folha-apurar
POST apurar 09/2026 → 200 "49 linha(s) … Nenhum holerite foi tocado."
POST apurar 2026-09 → 200 (mesmo resultado)   POST 13/2026 → 400   POST 12/2099 → 400
QA_API=http://127.0.0.1:8262 checar_tela_sem_porta.py → TOTAL: 1 sem porta (crm/atividades, anterior)
```
Fixtures `'FIXTURE DGX X2'` apagadas (`count(*) = 0` em `gp_justifications`).

**Vizinhos, todos verdes depois da frente:**
`test_oraculo_mapa_de_ponto_5_estados` → OK · `test_oraculo_w5_mapa_evento_rubrica` → 0 desvios
(Σ|Δ| = R$ 0,00) · `test_oraculo_w3_he_classificada` → 0 falhas.

---

## 5. O que NÃO foi feito e por quê

- **Nenhuma linha em `ponto_evento_rubrica` (W5).** O brief mandava cadastrar a regra de atraso
  **se houvesse rubrica**. Não há: `rubricas_folha` tem 35 códigos e nenhum de atraso, abono ou
  ausência justificada (só 1051 Faltas e 1053 DSR sobre Faltas). Inventar `1052` seria fabricar
  o destino do dinheiro. Registrado em §7, decisão 1.
- **O motor continua sem ler nada disto.** `calculo_service.py` não foi aberto para escrita.
  É o que garante o Σ|Δ| = R$ 0,00.
- **Os dias exatos de falta não existem em lugar nenhum.** O motor desconta a partir de um
  **contador** (`time_sheets.unjustified_absent_days`), não de uma lista de dias. Por isso a
  tela de falta mostra o dia do **abono** (que se sabe) e o total descontado (que se sabe), e
  não consegue dizer «o dia 12 foi descontado e tinha atestado». Cruzar dia a dia exige o
  espelho diário, que é outra frente.
- **O dia da justificativa é inferido.** `gp_justifications` não tem campo de data do dia
  justificado — só `punch_id` e `created_at` (medido em 24/09). A frente usa a data da batida
  ligada e, sem ela, a da criação, e a tela marca «(data da criação)» quando é o caso. Acrescentar
  uma coluna `dia_referencia` é mexer numa tabela de outro módulo no dia em que outra frente
  pode estar nela.
- **A fração de 50 % é calibragem, não lei.** `FRACAO_ENTRADA_AUSENTE` é uma constante com
  nome e docstring, ajustável sem tocar em lógica. Não virou parâmetro de banco porque hoje
  ninguém a editaria, e coluna morta é pior que constante viva.
- **Nada de e-mail, alerta ou tarefa.** A frente mede e mostra. Quem decide o que fazer com
  R$ 3.077,57 de atraso e com 13 justificativas paradas é o dono.
- **Frontend**: nada. `table` + `docs` + `form` renderizam genericamente.
- **`checar_regressao.py`**: nada — `scripts/orq/test_*.py` é globado pela meia-noite e o
  orquestrador registra, conforme o contrato.

---

## 6. Como o Jordan testa amanhã

1. Depois do bake: **Departamento Pessoal → Folha de pagamento → «Apurar conferência ponto ×
   folha»** (`/redesign/departamento-pessoal?t=ponto-folha-apurar`). Escolha **09/2026** e
   clique **Apurar**. A resposta diz, na mesma frase, quantos minutos de atraso o ponto viu,
   quanto isso valeria, quanto a folha descontou de falta, e termina com «Nenhum holerite foi
   tocado». Clique de novo: o número é o mesmo (idempotente).
2. Aba **«Atraso: conferência»**. Corra o olho pela coluna **«Descontado?»**: diz «NÃO — sem
   rubrica» em **todas** as 51 linhas. Essa é a frente inteira numa coluna.
3. Clique numa linha de agosto (PAULO DA SILVA LAMEGO, 25 turnos). Abre o **dia a dia**: o
   posto, o turno, a hora exata da batida, os minutos e quantos passaram da tolerância de
   15 min. É daí que sai o R$ 297,15 — nada é média.
4. Ainda nessa aba, olhe **MAURICIO ALVES CHAGAS em 09/2026**: R$ 0,00 estimado e 3.519 min na
   coluna **«Entrada ausente»**. Não é atraso; é batida de entrada que não foi feita em cinco
   turnos. Compare com EDIWILSON em agosto (4.316 min). **Isso é conversa de supervisor, não
   de folha.**
5. Aba **«Falta justificada: conferência»**. Hoje são 23 linhas e **nenhuma vermelha** — nada de
   passivo. Procure **CARLOS ALBERTO** e **CINTIA**: verde, «não descontou» (atestado do SST).
   As outras dizem «sem abono»: desconto sem contestação conhecida.
6. **O teste que importa**, se quiser ver a trava morder: vá em **Ponto & Jornada → «Revisar
   justificativas»** e **aprove** a justificativa de **EDILENE SALES SOUSA** ou **TELMA MARIA
   LAGES MEIRA** (as duas levaram 1051 em 09/2026 e têm justificativa parada). Volte ao
   «Apurar», rode 09/2026 de novo e veja a linha delas ficar **vermelha** com o valor do
   passivo. E confira: **o holerite não muda**. É exatamente esse o buraco — aprovar não
   devolve o dinheiro.

---

## 7. Decisões que só o dono pode tomar

1. **Descontar atraso, ou não? E em que rubrica?**
   Não existe rubrica de atraso em `rubricas_folha` (35 códigos conferidos, 24/09/2026), e por
   isso a frente **não** cadastrou linha no `ponto_evento_rubrica` da W5. Para o atraso virar
   dinheiro faltam, nesta ordem: (a) a decisão de descontar; (b) uma rubrica nova (aba
   «Rubricas», F1); (c) a linha no mapa evento→rubrica (aba «Mapa evento → rubrica», W5); (d) o
   motor passar a produzir o evento — o que é código, e caminho de folha. **Nada disso é
   automático a partir desta frente.**
   **O que a CCT manda:** li `modules/cct` inteiro (`schedule.py`, `salary_table.py`,
   `benefits.py`, `holidays.py`, `cct_metadata.py`, os serviços e validadores) e as tabelas
   `cct_*` do banco. A CCT SINDECOMPRESTS AM000613/2025, como está modelada aqui, **não tem
   cláusula de tolerância de atraso nem de desconto por atraso** — ela fixa piso, jornadas
   (12x36 divisor 180, 44h divisor 220), hora noturna 52,5 min, adicionais (noturno 20 %, HE
   50 %, feriado 100 %, ronda 15/30 %, intrajornada 50 %) e benefícios. A única régua legal
   aplicável é a **CLT art. 58 §1º**: até 5 min por marcação e **10 min por dia** não contam
   nem como extra nem como atraso.
2. **A tolerância de 15 min é mais generosa que a lei.** A semente da F7 (15 min, herdada do
   quadro ao vivo) é uma tolerância **operacional**, não trabalhista — e ela vale 15 min/dia
   contra os 10 min/dia da CLT. Usá-la como régua de desconto é uma escolha, e custou
   **R$ 905,61** nas duas competências (R$ 3.983,18 pelo atraso inteiro × R$ 3.077,57 só além
   dos 15 min). Se a decisão for descontar, a tolerância de folha precisa ser uma linha
   própria — não a mesma que decide se o supervisor recebe alerta no celular.
3. **Batida de entrada faltando: 20.445 min em duas competências.** 64 % do «atraso» de
   setembro é gente que só bateu na saída. Isso é problema de operação (app travando, agente
   esquecendo, posto sem sinal) e tem de ser resolvido **antes** de qualquer desconto — descontar
   em cima desse dado é a mesma armadilha que a trava de cobertura de faltas já impediu uma vez.
4. **13 justificativas paradas, zero aprovadas, e a aprovação não volta para a folha.**
   A mais antiga espera desde 21/07. Duas delas são de pessoas que **levaram desconto de falta em
   09/2026**. E mesmo se forem aprovadas hoje, o motor não muda nada: ele lê
   `time_sheets.unjustified_absent_days` e **nunca** consulta `gp_justifications` nem
   `sst_afastamentos`. São duas decisões separadas: (a) quem revisa justificativa e em que prazo;
   (b) ligar a aprovação ao espelho, para que aprovar mova `unjustified` → `justified` — hoje
   `justified_absent_days` é **0 em todos os meses de 2026**.
5. **`incide_inss` de 1051/1053 = false** (herdado da F1): o motor não reduz o
   salário-de-contribuição pela falta e a lei diz o contrário. Fica registrado de novo aqui
   porque é a mesma rubrica.
6. **Quando o motor passar a produzir `atraso`**, este oráculo é a trava: ele afirma hoje que a
   folha desconta R$ 0,00 de atraso e que os minutos batem com a régua do ponto. No dia em que a
   primeira coisa mudar por decisão, a segunda tem de continuar verde — ou o commit não passa.
