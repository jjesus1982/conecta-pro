# DGX Y3 — O ciclo da justificativa fecha, e a batida que falta ganha nome

**Branch** `dgx/y3-justificativa-batida-faltante` · **Módulo** ponto (+ leitura de folha) ·
**Data** 24/09/2026 · **Sandbox** `conecta_pro_staging` · **Porta de teste** 8273
(`teste-dgx-y3`, parado ao fim)

> **Paralelo cego.** Deferir uma justificativa aqui **propõe** a devolução e não paga nada.
> O oráculo prova Σ|Δ| = R$ 0,00 em `total_earnings`, `total_deductions` e `net_salary` dos
> 51 holerites de 09/2026, antes e depois de deferir.

---

## 1. Estado antes — medido

### 1.a As 13 justificativas, nominais

13 na base, **13 `pendente`**, 0 `aprovada`, 0 `rejeitada`. A mais antiga espera **desde
21/07** (65 dias). Nove já passaram do prazo de 5 dias.

| # | Pessoa | Dia | Tipo | Parada há | Anexo | Motivo (resumo) |
|---|---|---|---|---:|---:|---|
| 1 | COLABORADOR TESTE HOMOLOGACAO | 21/07 (criação) | atestado_medico | **65 d** | 1 | Atestado médico do período 21/07, enviado pelo portal do funcionário |
| 2 | ERIKA CRISTINA MAQUINE PEREIRA | 11/09 | atraso | 13 d | 0 | Câmera do reconhecimento facial fica só carregando; a batida não registra (turno 07:00–19:00, Laranjeiras Village) |
| 3 | EDILENE SALES SOUSA | 11/09 | atraso | 13 d | 0 | Não conseguiu registrar a **saída**: app demora a abrir e a reconhecer; relatou jornada duplicada (Ideal Flores, 08:00–17:00) |
| 4 | TELMA MARIA LAGES MEIRA | 12/09 (criação) | atraso | 12 d | 0 | App trava e demora a abrir a folha de ponto; atraso no retorno do almoço |
| 5 | TELMA MARIA LAGES MEIRA | 12/09 (criação) | atraso | 12 d | 0 | **Duplicata do item 4** — mesmo texto, dois registros |
| 6 | MATHEUS HENRIQUE CABRAL DA SILVA | 13/09 | atraso | 11 d | 0 | Facial não reconhece o rosto na entrada; print às 7:01 (Laranjeiras Village) |
| 7 | ERIKA CRISTINA MAQUINE PEREIRA | 13/09 | atraso | 11 d | 0 | «Não reconheci seu rosto. Pode ser a luz» — segunda vez em três dias |
| 8 | ANILSON JOSE SEIXAS NEVES | 15/09 | atraso | 9 d | 0 | Não conseguiu bater a volta do intervalo, 00:27 (Laranjeiras Village) |
| 9 | ANTONIO CARLOS CASTRO GAMA | 17/09 (criação) | atraso | 7 d | 0 | **App logado no nome de outra pessoa** («Olá, GRACIENE», posto Prime Arena) |
| 10 | ANTONIO DINIZ ASSIS DOS SANTOS | 21/09 | atraso | 3 d | 0 | Facial não reconhece na saída — «sempre acontece e o DP sempre valida» |
| 11 | DANIEL VIDAL LARROQUE | 22/09 | atraso | 2 d | 0 | Tentou bater a saída e o app não abriu |
| 12 | MATHEUS HENRIQUE CABRAL DA SILVA | 23/09 | atraso | 1 d | 0 | Login do app devolve **«Request failed with status code 429»** (rate limit) |
| 13 | JONHATA DINIZ BENAION | 23/09 | atraso | 1 d | 0 | Troca de posto autorizada pelo Sr. Paiva; o app continua apontando o posto antigo |

**Onze das treze são o mesmo defeito**: o app não deixa bater. Reconhecimento facial (5),
app que não abre ou trava (3), login com 429 (1), sessão de outra pessoa (1), posto errado (1).
Isso não é indisciplina de colaborador — é a ferramenta. §7, decisão 3.

### 1.b A batida que falta — 121 dias-pessoa, com nome

Janela de 60 dias (26/07 → 24/09), turnos **encerrados**, pessoa que **trabalhou**:

| Recorte | Dias-pessoa |
|---|---:|
| Falta a **saída** | 105 |
| Falta a **entrada** | 12 |
| Faltam **as duas** | 4 |
| **Total (a dívida de operação)** | **121** em 34 pessoas |
| *Fora do total:* a batida existe, só que **fora do turno previsto** | 79 em 12 pessoas |

Os dias-pessoa, por nome:

| Pessoa | Dias | Falta entrada | Falta saída | Faltam as duas |
|---|---:|---:|---:|---:|
| GRACIENE PEREIRA DE CASTRO | 12 | 0 | 12 | 0 |
| JONHATA DINIZ BENAION | 10 | 9 | 1 | 0 |
| EDWARD JOSÉ ATENCIO DOMINGUEZ | 8 | 0 | 8 | 0 |
| ANTONIO DINIZ ASSIS DOS SANTOS | 7 | 0 | 7 | 0 |
| JONILSON MARTINS DE SOUZA | 7 | 0 | 7 | 0 |
| AILTON CÉSAR VASCONCELOS | 6 | 0 | 6 | 0 |
| MALAQUIAS PEREIRA FERREIRA | 6 | 0 | 5 | 1 |
| RENE RICARDO CRUZ GONÇALVES | 6 | 0 | 6 | 0 |
| CARLOS EDUARDO DA SILVA FAÇANHA | 5 | 2 | 3 | 0 |
| ERIKA CRISTINA MAQUINE PEREIRA | 5 | 0 | 5 | 0 |
| BIANCA HELLEM DA SILVA MEIRA | 4 | 0 | 4 | 0 |
| EDUARDO OLIVEIRA DE SOUZA | 4 | 0 | 4 | 0 |
| FERNANDO SOUZA SIMPLICIO JUNIOR | 4 | 0 | 4 | 0 |
| OSCAR SOARES DA COSTA FILHO | 4 | 0 | 4 | 0 |
| ANILSON JOSE SEIXAS NEVES | 3 | 0 | 3 | 0 |
| ANTONIO CARLOS CASTRO GAMA | 3 | 0 | 2 | 1 |
| DANIEL VIDAL LARROQUE | 3 | 1 | 2 | 0 |
| KALEL SILVA DE JESUS | 3 | 0 | 2 | 1 |
| TELMA MARIA LAGES MEIRA | 3 | 0 | 3 | 0 |
| ANTONIO CARLOS VIEIRA · MAIARA MUNIZ DE SANTOS · MATHEUS HENRIQUE CABRAL DA SILVA | 2 cada | 0 | 2 | 0 |
| ADEILSON DINIZ DEODATO · ADEMIR SALUSTIANO DE SOUZA FILHO · ANDREA GONÇALVES DOS SANTOS · ANTONIO WALCICLEY PEREIRA DA SILVA · EULER FELIPE FERNANDES DA COSTA · JAQUELINE CARLOS DOS SANTOS · JEOVANE DO NASCIMENTO · LIVIA CARISE PEREIRA CONSENTINE · MAURICIO ALVES CHAGAS · PAULO DA SILVA LAMEGO · RUAN RODRIGUES FIGUEIREDO | 1 cada | 0 | 1 | 0 |
| EDIWILSON CORREA MARQUES | 1 | 0 | 0 | 1 |

E os 79 dias **fora** do total — a batida existe, o turno lançado é que está errado:

| Pessoa | Dias |
|---|---:|
| MAURICIO ALVES CHAGAS | 17 |
| EDIWILSON CORREA MARQUES | 14 |
| PAULO DA SILVA LAMEGO | 14 |
| DANIEL VIDAL LARROQUE | 10 |
| JONHATA DINIZ BENAION | 8 |
| TELMA MARIA LAGES MEIRA · VANDERLICE SANTOS DA SILVA | 4 cada |
| CARLOS EDUARDO DA SILVA FAÇANHA · CELIANE GARCIA DE SOUSA · GRACIENE PEREIRA DE CASTRO | 2 cada |
| ADAILSON SERRA ALVES · EIDY CULIER DE CASTRO | 1 cada |

**O que esse segundo balde é.** MAURICIO tem turno lançado **07:00–19:00** e bate entrada
18:44 e saída 06:50 do dia seguinte: ele trabalha **19:00–07:00**. EDIWILSON, idem — em 04/09
o turno lançado é 10:00–22:00 e ele bateu 07:01 → 19:00. Cobrar deles a saída que bateram
seria cobrar o erro de quem lançou a escala; por isso saem do total e ganham dizer próprio na
tela. **É a mesma família do achado de 11/09** (a escala 1 h à frente da vida real) — agora com
nome e contagem.

### 1.c As três correções que o oráculo obrigou (e o que valiam)

| # | O que estava errado | Custo em falso-positivo |
|---|---|---:|
| 1 | Procurar a **saída** na janela de presença, que termina no fim planejado — a saída vem depois dele (16:02 num turno que acaba 16:00) | **706 de 737** turnos acusados à toa |
| 2 | Chamar de «batida faltando» a batida que existe **fora do turno previsto** | 64 dias |
| 3 | Tratar o **check-in manual do supervisor** como batida de entrada | 15 dias (EDIWILSON tem check-in manual às 19:02 num turno 07:00–19:00 — e a X2 descarta esse dia como `entrada_ausente`) |

737 → **121**. Sem a primeira correção, o caçador teria nascido gritando seis vezes mais alto
que a dívida real, e ninguém teria olhado para ele duas vezes.

---

## 2. O que o DGX tem

Na DGX o ciclo da justificativa é um fluxo com prazo e resposta: fila do analista, deferimento
com efeito na apuração, indeferimento com motivo que volta ao colaborador. Aqui existiam as
duas pontas (criar e revisar) e **faltava o meio**: a fila com prazo, e o efeito. A batida
faltando, na DGX, é «inconsistência de marcação» na conferência do espelho — o equivalente
aqui é a coluna `entrada_ausente` que a X2 criou e ninguém conseguia listar por pessoa.

---

## 3. O que foi feito

| Arquivo | O quê |
|---|---|
| `backend/modules/people_management/ponto/services/justificativa_batida.py` (novo, 260 l) | `_ensure` (semente do parâmetro), `prazo_dias`, `fila`, `revisar`, `batidas_faltando`, `resumo_batidas`. Constantes `PARAM_PRAZO`, `PRAZO_PADRAO=5`, `JANELA_DIAS_PADRAO=60`, `VOLTA_DO_TURNO=12 h` |
| `backend/modules/operacional/controllers/redesign_builders/_dgx_y3_justificativa_batida.py` (novo) | `telas(db, out)` → `justificativas-fila`, `batida-faltando`; `router` com `POST /action/y3-justificativa-revisar`; anexa as 2 abas ao fim do `g-ponto` |
| `backend/scripts/qa/checar_batida_faltando.py` (novo) | O caçador (§ abaixo) |
| `backend/scripts/orq/test_oraculo_y3_justificativa_batida.py` (novo) | O oráculo (§4) |
| `.../redesign_builders/departamento_pessoal.py` | 2 linhas no topo (`router`) + 3 no FIM do `build()` (`telas`), comentário `# dgx y3` |
| `.../redesign_builders/_dp_grupos.py` | 2 tuplas no **FIM** do `g-ponto` |
| `backend/modules/people_management/ponto/mapa_de_ponto.py` | **uma coluna** (`cp.punch_type`) no `_SQL_BATIDAS` — aditiva, ninguém a jeito de quebrar |
| `backend/modules/notifications/proativo/regras.py` | a regra `justificativa_parada`, que **já existia**, passou a ler o parâmetro (era 48 h chumbadas), a dizer **quem** está parado, e a apontar para a aba nova |

**Nada foi tocado** em `calculo_service.py`, `horas_service.py`, `espelho_service.py`,
`hr_payslips`, `time_sheets`, `alembic/`, `frontend/`, `checar_regressao.py`.

### A rota de revisar NÃO foi duplicada — e é isso que o brief pedia para dizer

`PUT /api/v1/people-management/ponto/justificativa/{id}/revisar` já existe, e a aba «Revisar
justificativas» já tem **Deferir** e **Indeferir**. Quem muda o estado da justificativa continua
sendo `PunchService.revisar_justificativa` — a Y3 **chama essa mesma função**, não escreve em
`gp_justifications` por conta própria. O que faltava e a Y3 acrescenta:

| | «Revisar justificativas» (existia) | «Fila de justificativas» (Y3) |
|---|---|---|
| Há quanto tempo está parada | não (só o dia de criação em DD/MM) | **dias parados**, em vermelho quando passa do prazo |
| Prazo | não existe | parâmetro `ponto.justificativa_prazo_dias` (5), mesmo número do alerta |
| Dia justificado | não | dia da batida ligada, ou o da criação, marcado «(criação)» |
| Anexo | não | contagem de anexos |
| Efeito na folha | não | «aquele mês descontou R$ X desta pessoa» por linha, e o passivo proposto |
| Recusar sem motivo | **aceita** | **422** — o motivo é a resposta que o colaborador vai ler |
| Ao deferir | nada acontece fora de `gp_justifications` | reapura a conferência da X2: o dia vira abono e a linha entra em «passivo a devolver» |

### DDL que `_ensure` aplica em produção no 1º acesso (idempotente)

Nenhuma tabela nova. Só a semente do parâmetro:

```sql
ALTER TABLE system_configs ADD COLUMN IF NOT EXISTS valor_por_empresa jsonb NOT NULL DEFAULT '{}'::jsonb;
INSERT INTO system_configs (id, chave, nome, valor, valor_padrao, tipo, valor_type, grupo,
                            descricao, metadata, is_editavel, scope)
VALUES (gen_random_uuid(), 'ponto.justificativa_prazo_dias',
        'Ponto: prazo para revisar justificativa (dias)', '5', '5',
        CAST('integer' AS setting_type), 'integer', 'ponto', '…', '{"frente":"dgx-y3"}'::jsonb,
        true, 'global')
ON CONFLICT (chave) DO NOTHING;
```

A fila lê `gp_justifications`; a pendência de batida é **derivada na hora** do mapa de ponto —
não há tabela de pendência para apodrecer fora de sincronia.

### Telas (g-ponto, deep-link `/redesign/departamento-pessoal?t=g-ponto&tab=<id>`)

- **`justificativas-fila`** (table, 13 linhas, 7 colunas): Pessoa · Dia · **Parada há** ·
  Tipo · Motivo · Anexo · **Mês descontou falta?**. Filtros Prazo × Tipo. Ações por linha:
  **Deferir** (observação opcional) e **Indeferir** (motivo obrigatório, textarea). Docs por
  linha: motivo declarado, de onde veio (canal, data, posto) e **«Se for deferida»**, que diz
  em português o que vai acontecer com o dinheiro daquela pessoa naquele mês.
- **`batida-faltando`** (table, 121 linhas, 7 colunas): Pessoa · Dia · Turno previsto · Posto ·
  **Falta (entrada/saída/as duas)** · Batidas do turno · **O mapa conclui**. Filtros Falta ×
  Posto. Ações por linha: **Lançar batida** (reusa `POST /action/ponto-ajuste?eid=&dia=`, com
  o tipo já pré-selecionado no que falta e a hora do turno como placeholder) e **Justificar**
  (reusa `POST /ponto/justificativa`, com o texto pré-escrito). Docs por linha: o que o mapa
  conclui e por quê, **«E a falta?»** (não vira falta automática, e o motivo), e as batidas.

### O caçador

`backend/scripts/qa/checar_batida_faltando.py` · linha canônica:

```
TOTAL dias com batida faltando: 121
```

**CONTADA, não binária** — é dívida de operação com dono. Zero é o alvo; o valor existe para
ser comparado com o de ontem, e acusa se **crescer**. Imprime os dez que mais devem, os cinco
mais recentes com as batidas que existem, e o balde de escala divergente em separado.
`QA_DIAS` muda a janela. **Não** foi registrado em `checar_regressao.py`, conforme o brief —
a linha acima é para o orquestrador registrar.

---

## 4. Oráculo — `backend/scripts/orq/test_oraculo_y3_justificativa_batida.py`

```bash
WT=$(git rev-parse --show-toplevel)
ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' \
       | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\n' ' ')
docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" \
  --tmpfs /app/logs:rw,mode=1777 --tmpfs /app/uploads:rw,mode=1777 \
  -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env \
  -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \
  conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_y3_justificativa_batida.py
```

Afirma **(a)** aprovar marca o dia como abonado em `ponto_folha_conferencia` e Σ|Δ| = R$ 0,00
nos holerites · **(b)** recusar sem motivo levanta `ValueError`, e com motivo grava
`review_notes` · **(c)** a lista de batida faltando recontada por **SQL próprio** (turno
esperado da coorte, janela de presença, cauda de 2 h para a saída, `punch_type`), e as duas
travas honestas: nenhum dia com entrada faltando vira dinheiro na conferência de atraso, e
todos têm ao menos uma batida — logo nenhum vira falta automática · **(d)** o caçador acha o
turno de fixture sem saída e **não** acusa o que está completo · **(e)** a fila é exatamente
o conjunto das pendentes · **(f)** fiação.

**VERMELHO** (com as correções 1 e 3 do §1.c revertidas — é o defeito que o oráculo pegou):
```
FALHOU: batida faltando: 552 dia(s) que o serviço vê e o SQL não — ex.: [('0137ab13-…', '2026-08-08'), …]
FALHOU: batida faltando: 15 dia(s) que o SQL vê e o serviço não — ex.: [('29c7e69f-…', '2026-07-30'), …]
FALHOU: batida faltando 2026-09-20 EDIWILSON CORREA MARQUES: SQL entrada=False/saída=False × serviço entrada=True/saída=False
FALHOU: batida faltando 2026-09-19 VANDERLICE SANTOS DA SILVA: SQL entrada=False/saída=False × serviço entrada=True/saída=False
FALHOU: batida faltando 2026-09-19 ANTONIO CARLOS CASTRO GAMA: SQL entrada=False/saída=False × serviço entrada=True/saída=False
FALHOU: batida faltando 2026-09-12 VANDERLICE SANTOS DA SILVA: SQL entrada=False/saída=False × serviço entrada=True/saída=False
FALHOU: batida faltando 2026-09-09 DANIEL VIDAL LARROQUE: SQL entrada=False/saída=False × serviço entrada=True/saída=False
FALHOU: batida faltando 2026-09-07 DANIEL VIDAL LARROQUE: … (mais 4)
FALHOU: caçador: o turno de fixture COMPLETO (ANTONIO DINIZ ASSIS DOS SANTOS, 2026-07-28) foi acusado à toa
batida faltando (2026-07-26 → 2026-09-24): 662 dia(s)-pessoa (+75 com a escala lançada divergente) …
TOTAL desvios: 13
exit=1
```

**VERDE** (com o serviço, as telas, o caçador e a fiação):
```
fila: 13 justificativa(s) pendente(s) — recontadas por SQL
batida faltando (2026-07-26 → 2026-09-24): 121 dia(s)-pessoa (+79 com a escala lançada divergente) ·
  falta entrada em 16 · nenhum vira falta automática (todos têm batida) · nenhum minuto de entrada
  ausente virou dinheiro
registro tardio (CONTADO, não trava): 15 dia(s) que a conferência da X2 descarta pelo tempo e esta
  tela não lista — a batida de entrada existe, só que lançada horas depois; ex.: 2026-08-20 com 361 min
aprovar ADAILSON SERRA ALVES (15/09): dia abonado na conferência, sentido=ok, passivo estimado 0.00
  — e nenhum holerite tocado
paralelo cego 09/2026: Σ|Δ| = R$ 0,00 em 51 holerite(s)
TOTAL desvios: 0
OK ciclo da justificativa e batida faltando: aprovar marca o dia como abonado e Σ|Δ| = R$ 0,00 nos
holerites, recusar exige motivo, dia com batida faltando não conta como atraso nem como falta
automática (recontado por SQL), o caçador acha a fixture e poupa quem está completo, a fila é o
conjunto das pendentes
exit=0
```

**A linha «registro tardio» é o que o oráculo aprendeu a NÃO travar.** A X2 descarta pelo
TEMPO, então ela também tira do dinheiro o dia em que a batida de entrada **existe** mas foi
lançada horas depois — JEOVANE, 20/09, turno 06:00–18:00, batida `entrada` às 17:25. Isso não
é batida faltando (e não entra na tela) nem é atraso de verdade (e a X2 acerta em descartar).
As duas réguas estão certas; travar por causa dessa diferença seria uma trava vermelha por
motivo nenhum. Fica **contado**, para o dono ver o tamanho do registro tardio: **15 dias**.

**Prova por HTTP** (`teste-dgx-y3`, porta 8273, parado ao fim):
```
GET /api/v1/redesign/data/departamento-pessoal → 200
g-ponto tabs (últimas): [… 'he-por-contrato', 'justificativas-fila', 'batida-faltando']
justificativas-fila: table · 13 linhas · 7 colunas
  sub: «13 pendente(s), a mais antiga parada há 65 dias. Prazo de revisão: 5 dia(s) … 9 passaram
        do prazo e aparecem no painel de alertas do sistema.»
  linha 1: ['COLABORADOR TESTE HOMOLOGACAO','21/07 (criação)','65 dia(s)','atestado medico',
            'Atestado médico …','1 anexo(s)','não']
  ações: Deferir → POST /action/y3-justificativa-revisar?jid=ATM-5BC706E8   Indeferir → idem
batida-faltando: table · 121 linhas · 7 colunas
  linha 1: ['TELMA MARIA LAGES MEIRA','23/09','07:00–16:00','Condomínio Mirante das F …',
            'falta saída','entrada 07:04, saida_almoco 12:00','ok']
  ações: Lançar batida → POST /action/ponto-ajuste?eid=…&dia=2026-09-23   Justificar → POST /ponto/justificativa
POST indeferir SEM motivo → 422 «Recusar exige motivo (ao menos 5 caracteres) — é a resposta que
                                 o colaborador vai ler.»
POST indeferir COM motivo → 200 · status=rejeitada · review_notes='Atestado ilegível; reenviar.'
POST deferir              → 200 «Deferida. O dia 15/09 entrou como abono na conferência 09/2026 …
                                 Nenhum holerite foi tocado.»
POST jid inexistente      → 404
QA_API=http://127.0.0.1:8273 checar_tela_sem_porta.py → TOTAL: 0 sem porta
```

**A prova que interessa — o passivo aparece** (fixture em quem levou 1051 em 09/2026):
```
TELMA MARIA LAGES MEIRA — antes:  ok      | divergente=false | R$ 0,00
DEFERIR → «Deferida. O dia 10/09 entrou como abono na conferência 09/2026: 1 pessoa(s) com
           passivo a devolver, R$ 111,34 no total estimado. Nenhum holerite foi tocado.»
TELMA MARIA LAGES MEIRA — depois: passivo | divergente=true  | R$ 111,34 | folha descontou R$ 222,68
holerites 09/2026  antes: 104617.95 / 53194.33 / 51423.62 / 51
holerites 09/2026 depois: 104617.95 / 53194.33 / 51423.62 / 51 → IGUAL (Σ|Δ| = R$ 0,00)
```

**A regra do painel de alertas** (`justificativa_parada`, que já existia e foi corrigida):
```
prazo: 5 dias · 9 achado(s) · action_url=/redesign/departamento-pessoal?t=g-ponto&tab=justificativas-fila
 - «Justificativa parada há 12 dias: Telma Maria Lages Meira»
   «A justificativa de atraso de Telma Maria Lages Meira está pendente há 12 dia(s) — o prazo é 5.
    Deferir ou indeferir na aba «Fila de justificativas» (Ponto & Jornada). Indeferir exige motivo.»
```
Antes: 48 h chumbadas, texto «Uma justificativa de ponto está pendente há 1533h (id 3). Revisar.»,
e `action_url` apontando para `/modulos/operacional/ponto/justificativas` — **uma página que não
existe**. O painel da T3 lê `proativo_alert_state` e não precisou de uma linha: a regra já estava
registrada, e melhorá-la não reescreveu nada.

Fixtures `'FIXTURE DGX Y3'` apagadas (`gp_justifications` de volta a **13 pendente / 0 aprovada /
0 rejeitada**; `shifts` e `gp_clock_punches` sem sobra).

**Vizinhos, todos verdes depois da frente:**
`test_oraculo_x2_atraso_falta` → 0 desvios (Σ|Δ| = R$ 0,00) ·
`test_oraculo_mapa_de_ponto_5_estados` → OK ·
`test_oraculo_t3_operacional_comercial` → 0 falhas (painel soma 393 == 393).

---

## 5. O que NÃO foi feito e por quê

- **A aba «Revisar justificativas» continua lá, intacta.** Não foi apagada nem substituída:
  ela é a porta antiga, funciona, e apagá-la seria mexer numa tela de outro dono no mesmo dia.
  Quem quiser a fila com prazo e efeito usa a aba nova. **Decisão do dono** aposentar a antiga
  (§7, 5).
- **O motor de folha continua sem ler nada disto.** `calculo_service.py` não foi aberto para
  escrita, e é isso que garante o Σ|Δ| = R$ 0,00. A devolução é **proposta**, escrita numa
  tabela de conferência. Quem paga é o dono.
- **`justified_absent_days` continua 0 em todos os meses de 2026.** Aprovar não move
  `unjustified` → `justified` em `time_sheets`: isso é caminho de espelho, e o espelho é de
  outra frente nesta onda. A Y3 escreve na conferência da X2, que é dela.
- **A duplicata da TELMA (itens 4 e 5) não foi apagada.** Duas justificativas idênticas, mesmo
  texto, mesma data. Apagar registro do colaborador sem ele pedir não é conserto — é decidir por
  ele. Fica na fila, visível, para o DP indeferir uma com motivo.
- **O balde «escala divergente» não vira ação.** A tela conta e nomeia (79 dias, 12 pessoas);
  corrigir a escala lançada é a tela de escalas, de outro módulo. §7, decisão 2.
- **A fração de 50 % da X2 não foi mexida.** É calibragem dela, e esta frente a usa como está —
  o oráculo cruza as duas réguas em vez de reescrever uma.
- **Nada de e-mail, WhatsApp ou Telegram.** O alerta que existe é o do painel, que já existia.
- **Frontend**: nada. `table` com `actions`/`docs`/`filtros` renderiza genericamente — provado
  por HTTP na porta 8273.
- **`checar_regressao.py`**: nada, conforme o brief. A linha canônica está no §3.

---

## 6. Como o Jordan testa amanhã

1. **Departamento Pessoal → Ponto & Jornada → «Fila de justificativas»**
   (`/redesign/departamento-pessoal?t=g-ponto&tab=justificativas-fila`). São **13**, e a
   primeira está parada **há 65 dias**. Corra o olho pela coluna «Parada há»: nove estão em
   vermelho.
2. Clique na linha da **TELMA MARIA LAGES MEIRA** e abra **«Se for deferida»**. A frase diz,
   em português, quanto a folha descontou dela naquele mês e que a linha dela vira «passivo a
   devolver» — e que **o holerite não muda**.
3. Clique em **Indeferir** e mande **sem escrever motivo**. O sistema recusa: indeferir sem
   dizer por quê não é resposta. Escreva o motivo e mande: a justificativa some da fila.
4. Agora **Deferir** a da TELMA. A resposta diz a competência, quantas pessoas ficaram com
   passivo e quanto. Vá em **Folha de pagamento → «Falta justificada: conferência»**: a linha
   dela está **vermelha**, «DESCONTOU MESMO ASSIM». Abra o holerite de 09/2026 dela: **não
   mudou um centavo**. É exatamente esse o buraco que a X2 apontou — e agora ele está visível
   e com valor.
5. Aba **«Batida faltando»**. 121 linhas. Olhe a **GRACIENE**: 12 dias em que ela trabalhou e
   não bateu a saída. Clique numa linha e leia **«E a falta?»**: aquele dia não vira falta,
   porque houve batida. Isso é conversa de supervisor.
6. Ainda nessa linha, clique **Lançar batida**: o tipo já vem marcado no que falta e a hora do
   turno aparece como sugestão. É a mesma ação de ajuste de sempre, com pessoa e dia da linha —
   você não digita UUID nenhum.
7. Leia o fim do subtítulo dessa aba: **79 dias em que a batida existe, só que fora do turno
   previsto**. MAURICIO tem 17. Ele trabalha 19:00–07:00 e a escala diz 07:00–19:00. Isso não é
   ponto, é escala — §7, decisão 2.
8. **Central de alertas** (Operacional → «Alertas do sistema»): a regra `justificativa parada`
   agora diz **o nome** de quem está esperando e leva para a fila com um clique.

---

## 7. Decisões que só o dono pode tomar

1. **O app não deixa bater — e é isso que 11 das 13 justificativas dizem.**
   Reconhecimento facial que não conclui (5), app que não abre ou trava (3), login com HTTP 429
   (1), sessão logada no nome de outra pessoa (1), posto errado depois de troca autorizada (1).
   Enquanto isso não for resolvido, a fila de justificativas vai encher de novo toda semana e os
   121 dias de batida faltando vão crescer. **Isto é a raiz; a fila é o sintoma.**
2. **79 dias com a escala lançada ao contrário — MAURICIO (17), EDIWILSON (14), PAULO
   LAMEGO (14), DANIEL (10), JONHATA (8).** Turno cadastrado 07:00–19:00 para quem trabalha
   19:00–07:00. Isso envenena três coisas ao mesmo tempo: o mapa de ponto («8 h de atraso»), a
   conferência da X2 (minutos descartados que parecem batida faltando) e esta tela. Corrigir é
   na escala, e é rápido — mas é decisão de quem manda no operacional.
3. **Quem revisa justificativa, e em que prazo?** O parâmetro nasce com **5 dias**
   (`ponto.justificativa_prazo_dias`, editável na tela de parâmetros). Hoje ninguém tem esse
   papel: 13 pendentes, **zero** aprovadas em toda a história da tabela. O prazo sem dono é só
   um número que vai ficar vermelho.
4. **O passivo, quando alguém aprovar, é dinheiro a devolver — em qual competência?**
   A conferência diz o valor (TELMA: R$ 111,34 dos R$ 222,68 descontados). Devolver exige
   decidir: rubrica de estorno, competência de destino, e se entra na folha do mês ou em
   pagamento avulso. **Nada disso é automático a partir desta frente** — e é de propósito.
5. **Aposentar a aba «Revisar justificativas»?** Ela faz menos que a fila nova e continua no
   menu. Ter duas portas para o mesmo ato é como o DP acaba deferindo pela tela cega. Um
   comando seu e ela sai do `_dp_grupos`.
6. **O caçador é contado, não binário.** `TOTAL dias com batida faltando: 121` — o orquestrador
   registra a linha. Se amanhã der 140, alguma coisa na operação piorou. Se der 90, melhorou.
   Zerar depende da decisão 1.
