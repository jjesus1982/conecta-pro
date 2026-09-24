# DGX W5 — O elo que faltava: mapa evento do ponto → rubrica da folha (24/09/2026)

**Branch:** `dgx/w5-mapa-evento-rubrica` (base `98961d795`, fase5-hermes-camada-cognitiva)
**Módulo:** folha (cadastro `ponto_evento_rubrica`) + telas do redesign do DP · **Sessão:** agent-w5
**Paralelo cego.** `calculo_service.py` NÃO foi tocado — só LIDO. Nenhuma escrita em produção.
DDL idempotente aplicada só no sandbox (`_ensure`); em produção acontece no 1º acesso à aba.
**Container HTTP:** `teste-dgx-w5`, porta 8255 — **parado ao fim**.

---

## 1. Estado antes (medido) — os eventos que o motor produz e a rubrica de cada um hoje

A F1 trouxe a rubrica como dado (40 atributos do DGX) e a F7 trouxe a configuração de ponto em
cascata. O ELO continuava em código: quem decide em qual rubrica a ocorrência do ponto vira verba
é `calculo_service.py`. Levantado lendo o motor e **conferido nos holerites** (as duas últimas
competências do motor próprio — 09/2026, 51 holerites, e 08/2026, 53 holerites; 07/2026 é 100%
backfill do espelho da Portte e fica fora, §5):

| Evento do ponto | Rubrica que o motor emite | Fórmula que o motor usa | Linha | 09/2026 | 08/2026 |
|---|---|---|---|---|---|
| Falta injustificada | **1051** Faltas | `arred(salario_base ÷ 30) × dias` | L583-597 | 19 · R$ 2.575,28 | — |
| DSR perdido por falta | **1053** DSR sobre Faltas | `arred(salario_base ÷ 30) × dias` | L598-607 | 12 · R$ 2.018,58 | — |
| Hora extra 50% | **0040** Horas Extras 50% | `horas × valor_hora × 1,5` | L608-623 | — | 2 · R$ 208,94 |
| Adicional noturno | **0020** Adicional Noturno | `arred(horas × 60 ÷ 52,5) × valor_hora × 0,20` | L667-696 | 21 · R$ 3.641,45 | 19 · R$ 3.677,79 |
| Hora noturna reduzida (52'30") | **0021** Ad. Hora Noturna Reduzida | `horas × valor_hora × (1 + 0,20 + ronda) × 1,5` | L697-719 | 21 · R$ 4.347,92 | 19 · R$ 4.398,71 |
| Intrajornada não concedida — noturna | **0031** Intrajornada Noturna | `plantoes × valor_hora × (1 + 0,20 + ronda) × 1,5` | L720-746 | 9 · R$ 2.252,95 | 8 · R$ 2.167,33 |
| Intrajornada não concedida — diurna | **0030** Intrajornada Diurno | `plantoes × valor_hora × (1 + ronda) × 1,5` | L720-746 | 10 · R$ 2.001,13 | 11 · R$ 2.243,07 |
| DSR sobre verbas variáveis | **0090** DSR sobre HE | `valor_he × fator_dsr` | L748-775 | — | 2 · R$ 34,83 |

**São 8 eventos e 153 verbas de ponto nas duas competências.** Nenhum deles tinha uma linha de
cadastro; `ponto_evento_rubrica` não existia; `mapa_evento_rubrica` não importava. Nenhuma das 153
verbas era explicável por dado — só por leitura de Python.

Os 7 eventos que a DGX tem e o motor **não produz** (e por isso NÃO foram semeados — linha com
rubrica inventada seria ficção): falta justificada (abonada), atraso, HE 100%, feriado trabalhado,
sobreaviso, banco de horas crédito, banco de horas débito. Eles aparecem no combo da tela marcados
«(o motor não produz)», e no subtítulo da lista. §7.

## 2. O que o DGX tem

Na DGX o mapa evento→rubrica **e o tipo de cálculo** moram na «Configuração de Ponto»
(`/frontend/configuracoesponto`, `docs/dgx/lacunas/ponto.md` L27 e L50; `DGX_T2_ponto.md` L27),
uma linha por escopo (pessoa / contrato / vaga / colaborador / função / modelo de escala / escala),
campo vazio = herdado. O bloco **Eventos** carrega: tolerância, tipo de cálculo (ESCALA / BANCO DE
HORAS / ESCALA COMPENSAÇÃO / CARGA DIÁRIA / CARGA MENSAL / JORNADA POR ESCALA / CARGA MENSAL
PROPORCIONAL / FOLGA TRABALHADA) e o mapa **atraso, HE, HE100, falta automática, hora noturna,
noturna reduzida, HE noturna, hora trabalhada, falta dia compensado, adicional feriado**. É a
configuração que o motor LÊ — sem a linha, o cartão nem abre. O Evento em si tem 40 atributos
(`docs/dgx/01` §Eventos, `docs/dgx/09`), dos quais `somaAoEvento`, `somaAoPonto`, `tipoDia`,
`descontarBeneficio` e `bancoHoras` já viraram colunas de `rubricas_folha` na F1.

## 3. O que foi feito

| Arquivo | O quê |
|---|---|
| `backend/modules/people_management/folha/services/mapa_evento_rubrica.py` (novo) | `EVENTOS` (15, com `produzido` por evento), `ESCOPOS`, `BASES`, `DDL`, `SEMENTE` (8 linhas com `origem_regra` apontando arquivo e linha do motor), `_ensure(db)`, `carregar_regras`, `resolver` (puro), `mapa_evento_rubrica(db, evento, employee_id=…, condominio_id=…, funcao=…, escala=…, ref=…)`. Reusa `config_ponto._SQL_CTX_EMPREGADO` (F7) para a cascata resolver o MESMO escopo nas duas frentes |
| `backend/modules/operacional/controllers/redesign_builders/_dgx_w5_mapa_evento_rubrica.py` (novo) | `telas(db, out)` → `ponto-evento-rubrica` (table) e `ponto-evento-rubrica-nova` (form); `router` com `POST /action/evento-rubrica-salvar` e `evento-rubrica-inativar` |
| `backend/scripts/orq/test_oraculo_w5_mapa_evento_rubrica.py` (novo) | O oráculo (§4) |
| `.../redesign_builders/departamento_pessoal.py` | 2 linhas no topo (`router`) + 2 linhas logo após a F1 (`telas`, antes de `montar_grupos`), comentário `# dgx w5` |
| `.../redesign_builders/_dp_grupos.py` | 2 tuplas no g-folha, ao lado de «Rubricas» |

**Decisão de grupo: `g-folha`** (não `g-ponto`). O ponto produz a ocorrência; é a FOLHA que decide
em que rubrica ela vira dinheiro, e quem mexe nisto quando a CCT muda é o DP/folha. A aba fica
encostada em «Rubricas» (F1), que é a outra metade do mesmo assunto.

### DDL que `_ensure` aplica em produção no 1º acesso (idempotente)

```sql
CREATE TABLE IF NOT EXISTS ponto_evento_rubrica (
  id serial PRIMARY KEY,
  evento varchar(40) NOT NULL,
  rubrica_codigo varchar(10) NOT NULL,                    -- FK LÓGICA para rubricas_folha.codigo
  escopo varchar(20) NOT NULL DEFAULT 'empresa'
      CHECK (escopo IN ('empresa','condominio','funcao','escala','colaborador')),
  escopo_id text NOT NULL DEFAULT '',
  formula text NOT NULL,
  base varchar(20) NOT NULL CHECK (base IN ('salario_base','salario_minimo','valor_hora','piso_cct','evento')),
  percentual numeric(10,4),
  ativo boolean NOT NULL DEFAULT true,
  vigencia_inicio date, vigencia_fim date,
  origem_regra text NOT NULL,                             -- OBRIGATÓRIA, no banco
  criado_por varchar(120),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now());
CREATE INDEX IF NOT EXISTS ix_ponto_evento_rubrica ON ponto_evento_rubrica (evento, escopo, escopo_id) WHERE ativo;
-- semente: 8 INSERT ... WHERE NOT EXISTS (evento, escopo='empresa') — o que o dono editar nunca é sobrescrito
```

Não há CHECK no `evento`: a lista vive em Python (`EVENTOS`), e um evento novo não deve depender de
um `ALTER` que `IF NOT EXISTS` não reaplica. Nenhum DROP/DELETE/UPDATE em dado que a frente não criou.

### A cascata

`colaborador > escala > função > condomínio > empresa` — a MESMA da F7. Linha inativa ou fora da
vigência é ignorada; dentro do mesmo escopo, a mais recente vence. `resolver()` é puro (uma leitura,
nenhuma consulta dentro do laço). `mapa_evento_rubrica(db, evento, employee_id=…)` completa função,
escala e condomínio pelo cadastro do empregado. **`None` é resposta legítima**: significa que aquele
evento não vira verba nenhuma hoje — é o que acontece com os 7 eventos do §7.

### A fórmula é legível E recomponível

A `formula` é texto que se lê como se fala — `arred(salario_base ÷ 30) × dias` — e ao mesmo tempo é
avaliável: `×`→`*`, `÷`→`/`, vírgula decimal→ponto, `arred(x)` = o arredondamento do motor
(`_d`: 2 casas, meio para cima). **Nada em produção avalia fórmula** — o avaliador vive só no
oráculo, num escopo sem builtins. O motor segue com a regra em Python e a tela só exibe o texto.

Variáveis: `horas`/`dias`/`plantoes` (a quantidade que o motor gravou na `referencia` do holerite),
`valor_hora` = `arred(salario_base ÷ divisor da escala)`, `salario_base` (base cheia, pós-piso CCT),
`ronda` = `adicional_ronda_percentual ÷ 100`, `valor_he`, `fator_dsr`.

### Telas (g-folha, deep-link `/redesign/departamento-pessoal?t=<id>`)

- **`ponto-evento-rubrica`** (table, 8 linhas): Evento · Rubrica · Onde vale · Fórmula · Base·fator ·
  Origem da regra · **O motor usa?** · Na folha · Status. Por linha: **Editar** (modal com os 10
  campos, POST `evento-rubrica-salvar` com `id`) e **Inativar/Reativar**. Filtros Estado × Escopo.
  A coluna «O motor usa?» diz **«não — declaração»** em todas as linhas, e a coluna ao lado mostra
  o fato medido («emitida 21× (R$ 3.641,45) em 09/2026»). Honestidade na tela, como a F1 fez: o
  caminho existe em Python, não neste cadastro.
- **`ponto-evento-rubrica-nova`** (form, 10 campos): evento (com «(o motor não produz)» nos 7),
  rubrica (só ativas de `rubricas_folha`), escopo + id, base, percentual, fórmula, vigência
  início/fim, **origem da regra (obrigatória)**.

**Validações medidas** (§4): origem < 5 → 400 · rubrica inexistente em `rubricas_folha` → 400 ·
rubrica inativa → 409 · evento fora do enum → 400 com a lista · escopo ≠ empresa sem id → 400 ·
vigência invertida → 400 · fórmula < 3 → 400 · linha ativa duplicada (evento+escopo+id) → 409.
**`evento-rubrica-inativar`** alterna, **nunca apaga** (a linha é a explicação de holerites já
emitidos) e **recusa (409)** inativar a última linha ativa de evento que o motor produz — seria
deixar o oráculo vermelho de propósito.

## 4. Oráculo — `backend/scripts/orq/test_oraculo_w5_mapa_evento_rubrica.py`

Afirma, nas duas últimas competências do motor próprio: **(a)** o código que o mapa RESOLVE para
aquele evento e aquela pessoa == o que o motor emitiu; **(b)** o VALOR recomposto pela fórmula do
mapa == o do holerite, tolerância R$ 0,01 por linha e **Σ|Δ| = R$ 0,00**; **(c)** nenhum evento
produzido pelo motor sem linha; **(d)** `origem_regra` em todas; **(e)** a cascata resolve (fixture
de colaborador vence escopo de empresa, apagada ao fim mesmo em falha); **(f)** fiação (o build do
DP chama a frente e as abas estão em `_dp_grupos`). O mapa é lido por SQL próprio; o piso da CCT e
o `fator_dsr` são recontados no oráculo, não importados do motor.

```bash
WT=$(git rev-parse --show-toplevel)
ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' \
       | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\n' ' ')
docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" \
  --tmpfs /app/logs:rw,mode=1777 --tmpfs /app/uploads:rw,uid=999,gid=999 \
  -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env \
  -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \
  conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_w5_mapa_evento_rubrica.py
```

**VERMELHO** (antes de qualquer código):
```
FALHOU: mapa_evento_rubrica não importa: ModuleNotFoundError: No module named 'modules.people_management.folha.services.mapa_evento_rubrica'
TOTAL desvios: 1
exit=1
```

**VERDE** (depois do cadastro + fiação):
```
09/2026 e 08/2026 · mapa com 8 linha(s) · 8 evento(s) produzidos pelo motor · 153 verba(s) de ponto no holerite · divergentes: 0 · Σ|Δ| = R$ 0,00
por evento: adicional_noturno=40 · dsr_sobre_falta=12 · dsr_sobre_he=2 · falta=19 · he50=2 · hora_noturna_reduzida=40 · intrajornada=17 · intrajornada_diurna=21
TOTAL desvios: 0
OK mapa evento→rubrica: todo evento produzido tem linha, o código resolvido == o emitido, o valor recomposto pela fórmula == o do holerite (Σ|Δ| = R$ 0,00), cascata resolve, origem em todas
exit=0
```

**O oráculo morde.** Com uma fixture de escopo `funcao` mapeando `he50 → 0041` para AGENTE DE PORTARIA:
```
FALHOU: (a) GERNANES BINDA APARICIO 08/2026: motor emitiu 0040 e o mapa resolve 0041 para 'he50'
FALHOU: (a) JEOVANE DO NASCIMENTO 08/2026: motor emitiu 0040 e o mapa resolve 0041 para 'he50'
TOTAL desvios: 2
```

**Prova por HTTP** (`teste-dgx-w5`, porta 8255, parado ao fim):
```
GET /api/v1/redesign/data/departamento-pessoal → 200
g-folha tabs: [... 'folha-rubricas', 'folha-rubrica-nova', 'ponto-evento-rubrica', 'ponto-evento-rubrica-nova', ...]
ponto-evento-rubrica: table · 8 linhas · cols [Evento, Rubrica, Onde vale, Fórmula, Base · fator, Origem da regra, O motor usa?, Na folha, Status]
  ['Adicional noturno','0020 — Adicional Noturno','toda a empresa','arred(horas × 60 ÷ 52,5) × valor_hora × 0,20','valor hora · 0.2', …, 'não — declaração','emitida 21× (R$ 3.641,45) em 09/2026','ativa'] edit=True
ponto-evento-rubrica-nova: form · 10 campos · submit evento-rubrica-salvar
salvar [sem origem] → 400 · [rubrica inexistente] → 400 · [evento inválido] → 400 (com a lista dos 15)
salvar [escopo sem id] → 400 · [vigência invertida] → 400 · [ok] → 200 id 12
salvar [duplicado] → 409 "Já existe linha ativa de 'atraso' no escopo empresa (id 12). Edite-a."
salvar [escopo função he50→0041] → 200 id 13 · salvar [editar id 12] → 200 · inativar → 200 · reativar → 200
inativar he50 (única ativa) → 409 "'he50' é produzido pelo motor de folha e esta é a única linha ativa — o oráculo ficaria vermelho."
QA_API=http://127.0.0.1:8255 checar_tela_sem_porta.py → TOTAL: 1 sem porta (crm/atividades, anterior à W5)
```
Fixtures `'FIXTURE DGX W5'` apagadas do sandbox ao fim (`count(*) FILTER (origem_regra LIKE 'FIXTURE%') = 0`;
restam as 8 linhas da semente).

**Vizinhos, todos verdes** depois da frente:
`test_oraculo_rubricas_dizem_a_verdade` 0 · `test_oraculo_cct_como_dado` 0 vermelhos (6 avisos) ·
`test_oraculo_ponto_configuravel` 0 · `test_oraculo_beneficio_regra_e_dado` 0.
⚠️ O `beneficio_regra_e_dado` **piscou** duas vezes durante a frente (4 e depois 1 desvio de
previsão de VT/VR, empregados diferentes a cada corrida, verde nas quatro corridas seguintes com o
MESMO código). Ele compara o motor ao vivo contra a baseline guardada em
`folha_beneficio_conferencia` — e o sandbox estava sendo escrito por outras frentes em paralelo. Não
é a W5 (que não toca benefício nem coorte), mas é um oráculo sensível a corrida: fica registrado.

## 5. O que NÃO foi feito e por quê

- **O motor não lê o cadastro.** `calculo_service.py` segue com a regra em Python. Caminho de
  dinheiro: Σ|Δ| = 0 garantido por não tocar. Ligar o motor ao mapa (resolver a rubrica e o fator
  pela tabela em vez de pelo `if`) é o passo seguinte — o «F1-b» que a F1 deixou — e este oráculo já
  é a trava dele: o dia em que o motor ler daqui, ele continua verde ou o commit não passa.
- **07/2026 e anteriores ficaram fora.** São 100% backfill do espelho da Portte
  (`folha_verba_espelho`, referência «espelho Portte»): verba COPIADA, não calculada por evento.
  Lá o motor emite 0070 Horas Extras, 1052 Faltas Parcial, 1050, 0052, 0090 sem passar por nenhuma
  fórmula própria. Mapear isso seria mapear a folha de outra empresa. (07/2026 é, aliás, a última
  competência `published`; 08 e 09 estão em `draft` — «publicado» aqui = emitido pelo nosso motor.)
- **Os 7 eventos da DGX sem caminho** (atraso, HE 100%, falta justificada, feriado trabalhado,
  sobreaviso, banco de horas crédito/débito) **não foram semeados**. Não há rubrica que o motor
  emita para eles; inventar o código seria fabricar. Estão no combo e no subtítulo. §7.
- **`tipo de cálculo`** (ESCALA / BANCO DE HORAS / CARGA DIÁRIA / … — a outra metade da linha da
  DGX) não entrou. Aqui o «tipo de cálculo» efetivo está embutido na fórmula de cada evento
  (o divisor da escala e o `fator_dsr` saem do `escala_padrao` do empregado). Criar um enum que
  ninguém lê é coluna morta; quando o motor ler o mapa, o tipo de cálculo vira a próxima coluna.
- **`base = 'evento'`** é um 5º valor fora dos quatro do brief. O DSR sobre HE (0090) não tem base
  salarial: a base dele é o VALOR de outro evento — é o `somaAoEvento` da DGX. Preferi a enum dizer
  a verdade a forçar `valor_hora` num reflexo.
- **`percentual` guarda a parte CONSTANTE do fator** (1,5 · 0,20). Em 0021/0030/0031 o fator
  depende da pessoa (`ronda`), e é a fórmula que carrega a verdade inteira. A coluna existe porque
  o brief pede e porque serve de resumo na tela; quem recompõe é a fórmula.
- **`ponto_configuracoes` (F7) não ganhou o mapa dentro dela.** Na DGX é uma linha só; aqui são duas
  tabelas com a mesma cascata (`config_ponto` resolve tolerância/raio, `mapa_evento_rubrica` resolve
  evento→rubrica). Juntar significaria mexer na tabela e nas telas da F7 no mesmo dia em que ela
  nasceu. A cascata é literalmente a mesma função e o contexto do empregado é a MESMA consulta
  (importada, não copiada) — juntar depois é renomear, não reescrever.
- **Frontend**: nada. `table` + `edit`/`actions` + `form` renderizam genericamente; as abas vêm do
  `_dp_grupos`.
- **`checar_regressao.py`**: nada — `scripts/orq/test_*.py` é globado pela meia-noite (o orquestrador
  registra, conforme o contrato).

## 6. Como o Jordan testa amanhã

1. Depois do bake: **Departamento Pessoal → Folha de pagamento → aba «Mapa evento → rubrica»**
   (`/redesign/departamento-pessoal?t=ponto-evento-rubrica`). São 8 linhas. O subtítulo diz, em
   letras claras, que **o motor não lê este cadastro** e que o oráculo prova que ele diz a verdade.
2. Leia a coluna **Fórmula** de cima a baixo: é o que o motor faz, em português.
   `arred(salario_base ÷ 30) × dias` é a falta; `arred(horas × 60 ÷ 52,5) × valor_hora × 0,20` é o
   adicional noturno com a redução da hora noturna embutida.
3. Coluna **«O motor usa?»**: todas dizem «não — declaração». Ao lado, **«Na folha»** mostra o fato
   («emitida 21× (R$ 3.641,45) em 09/2026»). Se um dia a primeira coluna mudar, é porque o motor
   passou a ler daqui.
4. Clique **Editar** numa linha (ex.: Hora extra 50%) — abrem os 10 campos, inclusive a origem.
   Mude o fator para 2, salve: a tela muda, **o holerite não** (paralelo cego). Desfaça.
5. Tente **Inativar** a linha de Hora extra 50%: recusa com 409, explicando que é a única linha
   ativa de um evento que o motor produz.
6. Aba **«Nova linha do mapa»**: escolha o evento «Atraso (o motor não produz)», rubrica, escopo
   «função» e escreva a fórmula. Salve sem preencher a origem: recusa.

## 7. O que o cadastro NÃO conseguiu explicar — a dívida entre cadastro e motor

**Nas 153 verbas de ponto de 08 e 09/2026, zero.** Σ|Δ| = R$ 0,00, nenhuma linha divergente,
nenhum evento produzido sem linha. O cadastro explica hoje 100% do que o motor emitiu a partir do
ponto. A dívida real está noutro lugar, e é decisão do dono:

1. **Os 7 eventos da DGX que não existem aqui** — não é o cadastro que falha, é o motor que não os
   produz. Cada um é uma decisão de folha, não de código:
   | Evento | O que falta para existir |
   |---|---|
   | **Atraso** | O ponto MEDE atraso (tolerância da F7), a folha nunca desconta. Descontar minuto de atraso é decisão do dono — e, se for sim, precisa de rubrica nova e da mesma trava de cobertura de batidas que protege a falta. |
   | **HE 100%** | Não há rubrica 100% emitida por ninguém. Domingo/feriado trabalhado no 12x36 já está no piso; a CCT manda 100% no feriado não compensado. Hoje sai como HE 50% (0040) ou não sai. |
   | **Feriado trabalhado** | Os feriados ganharam escopo na F7 (`cct_feriados`), o espelho já marca HE 100% neles — mas o motor de folha não emite verba própria de adicional de feriado. |
   | **Falta justificada (abonada)** | `time_sheets` separa justificada de injustificada; só a injustificada vira 1051. A justificada não gera verba nenhuma (nem provento de abono). No espelho da Portte existia 0052 «Ausencia Justificada». |
   | **Sobreaviso** | Não existe registro de sobreaviso no ponto. Precisa do lançamento antes da rubrica. |
   | **Banco de horas crédito/débito** | O banco de horas está completo no Operacional (`time_bank_controller`), e **nunca conversa com a folha**: saldo não vira verba nem compensa HE. É o maior buraco desta lista. |
2. **A trava de cobertura de faltas é invisível no mapa.** A linha de `falta` diz a fórmula, mas
   não diz que o motor **só desconta** quando as batidas do Conecta PRO são a maioria do mês
   (`COBERTURA_MINIMA_FALTAS`, L548-582) — a regra que impediu tirar ~R$ 18 mil de quem trabalhou em
   julho. Está no texto da `origem_regra`, não num campo. Virar condição de dado exige uma coluna
   `condicao` que hoje ninguém leria.
3. **`incide_inss` de 1051/1053 = false** (herdado da F1): o motor não reduz o salário-de-contribuição
   pela falta; a lei diz o contrário. O mapa não muda isso — só registra a rubrica de destino.
4. **Quando o motor passar a LER o mapa** (F1-b/W5-b), estas três decisões viram uma só pergunta:
   a rubrica de destino e o fator passam a ser editáveis pelo DP sem deploy — inclusive por engano.
   A trava é este oráculo, e ele precisa entrar no `checar_regressao.py` nesse dia.
