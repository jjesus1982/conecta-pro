# DGX Y2 — A direção da batida: 192 horas de diferença, medidas e explicadas (24/09/2026)

**Frente:** Y2, onda 7 · **Branch:** `dgx/y2-direcao-batida` · **Módulo:** ponto
**Origem:** `DGX_X4_pareador_unico.md` §7.1 — a divergência que SOBRA depois que a X4 fechou a
do DIA.

**O achado da X4:** duas réguas de pareamento discordam sobre **se o tipo da batida manda**.

| | Régua **A** — cronológica | Régua **B** — com direção |
|---|---|---|
| Onde vive | `ponto/services/horas_service.parear_batidas` | `hr/services/time_record_service._pair_punches` |
| Quem lê | **a FOLHA** e o fechamento de mês | a **TELA DE PONTO** do DP e o resumo mensal |
| A regra | ignora `punch_type`; pareia na ordem do relógio | «batida tipada `saida` **não ABRE** turno» |
| Por que nasceu | batida de noturno vem tipada errada e o turno inteiro sumia, levando o adicional noturno junto | commit 5e0bbc1f: `[saída de ontem, entrada de hoje]` viravam 12 h de trabalho **sobre o descanso** |

As duas nasceram de defeito real e **cada uma acerta em dias diferentes**. Escolher uma muda
`horas_trabalhadas`/`horas_noturnas` — de onde saem HE 50% e adicional noturno. É dinheiro.

**Esta frente NÃO escolhe. Mede, explica e prepara a escolha.** Nada muda em folha, espelho ou
ponto: `Σ|Δ| = R$ 0,00` provado no §4, item (e).

---

## 1. A medição que falta para decidir — 07, 08 e 09/2026, nominal

Sandbox (cópia de produção de 24/09/2026). Coorte: todo ativo não-homologação com ao menos uma
batida no mês — **155 pessoa×competência** (53 + 51 + 51), a mesma coorte da X4 §1b.

### 1a. O número

| Competência | pessoas com batida | pessoas divergentes | pessoa×dia | **Σ\|Δ\| horas** |
|---|---:|---:|---:|---:|
| 07/2026 | 53 | 2 | 2 | 7,98 |
| 08/2026 | 51 | 17 | 27 | 67,20 |
| 09/2026 | 51 | 18 | 30 | 58,09 |
| **total** | **155** | **28** | **59** | **133,27** |

### 1b. Reconciliação com as 192 h da X4 — a diferença NÃO é da direção da batida

A X4 §1b mediu **no MÊS**: Σ|Δ| de 192,51 h antes da correção dela e 192,45 h depois. Remedido
hoje, no mesmo jeito: **199,64 h** (31,04 + 107,26 + 61,34 — a diferença para 199,45 é dado novo
no sandbox desde então, não regressão). Por **DIA**, a divergência de PAR é **133,27 h**.

As 66 h de diferença são **borda de competência**, o assunto do §7.3 da X4, e foram medidas à
parte:

| Efeito | Σ\|Δ\| |
|---|---:|
| Régua A: hora do par conta no mês da **ENTRADA**, dia conta no mês do **PLANTÃO** | **63,19 h** |
| Régua B: `_calculate_summary_from_punches` filtra por `record_date` (o dia do plantão) | **31,65 h** |

Ou seja: **o Σ|Δ| de mês mistura duas perguntas.** A desta frente — o tipo da batida manda? —
vale **133,27 h**. O resto é a convenção de qual mês recebe o plantão da virada, que é a §7.3 e
continua aberta.

### 1c. As causas — 100 % classificadas, nenhuma `indeterminado`

| Causa | pessoa×dia | Σ\|Δ\| horas | % das horas |
|---|---:|---:|---:|
| `tipo_errado_no_aparelho` | **48** | **97,16** | 72,9 % |
| `batida_duplicada` | 8 | 23,52 | 17,6 % |
| `virada_de_meia_noite` | 1 | 12,53 | 9,4 % |
| `batida_faltando` | 2 | 0,06 | 0,05 % |
| `indeterminado` | **0** | 0,00 | — |
| **total** | **59** | **133,27** | |

A causa é lida do **mecanismo**, não de palpite: `tipo_errado_no_aparelho` é a batida que a
régua A usou para ABRIR par e a régua B recusou, com `punch_type` exatamente `saida`. (Tratar
`saida_almoco` como se disparasse a regra rotulava errado 12 dias de jornada partida — medido e
corrigido antes de fechar.)

### 1d. Qual das duas bate com a realidade

Árbitro: a **jornada planejada** do turno lançado em `shifts` naquele dia. Uma régua "bate" se
fica a menos de **2 h** dela (`TOL_REALIDADE_H`, calibragem declarada no serviço).

| Veredito | pessoa×dia |
|---|---:|
| **as DUAS erram** por mais de 2 h | **47** |
| régua A bate | 3 |
| régua B bate | 3 |
| as duas batem (empate) | 2 |
| sem turno lançado — não dá para saber | 4 |

E o desempate FRACO (só quem chegou mais perto, sem exigir que acerte): **régua A em 39,
régua B em 16**, dos 55 dias com turno lançado.

> **Ganhar por 3,9 h contra 6,9 h numa jornada de 12 h não é acertar.** Por isso as duas
> colunas existem separadas na tabela e na tela: `quem_acerta` e `mais_perto`.

### 1e. Os casos nominais que explicam tudo

**O arquétipo — ANILSON JOSE SEIXAS NEVES, 25/08/2026** (o caso de escola da X4 §7.1):

```
batidas: 19:02 entrada · 23:10 saída · 00:00 SAÍDA · 01:00 entrada · 06:59 saída   (plano 12h)
régua A  (00:00→01:00) = 1h00   +  (19:02→23:10) = 4h08   →  5,13 h   · 2 pares
régua B  (01:00→06:59) = 5h59   +  (19:02→23:10) = 4h08   →  10,12 h  · 2 pares
Δ = −4,99 h   causa: tipo_errado_no_aparelho   quem acerta: régua B (10,12 contra 12h)
```

**O contrário, no mesmo mês — ADAILSON SERRA ALVES, 01/09/2026:**

```
batidas: 19:00 entrada · 00:00 entrada · 01:04 SAÍDA · 07:00 saída                 (plano 12h)
régua A  (19:00→00:00) = 5h + (01:04→07:00) = 5h56    →  10,94 h  · 2 pares
régua B  (19:00→00:00) = 5h ; 01:04 recusada          →   5,00 h  · 1 par
Δ = +5,94 h   causa: tipo_errado_no_aparelho   quem acerta: régua A (10,94 contra 12h)
```

**Os dois piores, e os dois são de DADO, não de régua:**

| Pessoa | Dia | Régua A | Régua B | Δ | Plano | Causa | Quem acerta |
|---|---|---:|---:|---:|---:|---|---|
| ADEILSON DINIZ DEODATO | 13/09 | 18,89 h | 7,12 h | **11,77** | 12 h | batida_duplicada | as DUAS erram |
| ADEILSON DINIZ DEODATO | 31/08 | 12,53 h | 0,00 h | **12,53** | — | virada_de_meia_noite | sem turno |

**O padrão de volume — ANTONIO CARLOS VIEIRA, 11 dias em 08 e 09/2026**, sempre a mesma coisa:

```
07:30 entrada · 08:00 entrada · 12:00 saída almoço · 13:00 entrada · 16:30 SAÍDA · 17:00 saída
régua A 1,98 h (3 pares) × régua B 1,47 h (2 pares) — plano 9 h, as DUAS erram por 7 h
```

Aqui nenhuma das duas réguas está medindo o turno: está medindo os buracos entre batidas que o
aparelho gravou com o tipo trocado. Trocar de régua não salva este dia. **Corrigir o dado salva.**

---

## 2. O que o DGX tem

O DGX trata o **plantão** como a unidade do apontamento e assume que a folha de ponto chega com
entrada e saída **identificadas** — é o aparelho que garante a direção, não o software que a
adivinha depois. A frente não importa uma regra do DGX; importa a **exigência** dele: a direção
da batida é atributo do DADO. Daí a recomendação do §7 apontar para o aparelho e o app, não para
a escolha de uma das duas réguas.

---

## 3. O que foi feito (2 arquivos novos, 2 tocados)

### 3a. Serviço — `backend/modules/people_management/ponto/services/divergencia_regua.py` (novo)

`apurar(db, competencia)` — idempotente, chave `(competencia, employee_id, dia)`. Roda as **duas**
réguas sobre as **mesmas** batidas, na **mesma** ordem, agrupa pelo dia do plantão e grava só onde
a HORA diverge.

**As duas réguas são IMPORTADAS, não recriadas** — a X4 §7.2 catalogou OITO pareadores; um nono
seria o defeito, não a solução:

- **Régua B** roda como o DP a roda: `TimeRecordService._pair_punches(..., manter_origem=True)`
  com as mesmas janelas de turno; `_punch_ids` diz quais batidas cada registro consumiu.
- **Régua A** roda por **sondagem de prefixo** sobre a própria `parear_batidas`. A função é uma
  varredura da esquerda para a direita — acrescentar uma batida ao fim nunca muda decisão
  anterior — e um par dela é sempre de linhas **adjacentes** (`entrada, saida = rows[i],
  rows[i+1]`). Chamando-a sobre `rows[:k]` para k = 2..n e olhando onde `dias_com_par` sobe,
  recupera-se **cada par que ela formou**: o que fecha no prefixo k é (k−2, k−1). **Nenhuma linha
  da régua foi copiada** — se a frente Y1 mexer em `horas_service`, esta medição segue a mudança.

Por que a comparação é por HORA e não por dia: a X4 já unificou o dia (`dia_do_plantao`, Σ|Δ| de
dias caiu de 162 para 2). Diferença de número de PARES sem diferença de hora é a fusão de
intervalo da régua B (12x36 com 1 h de almoço = 1 registro de 11 h onde a régua A vê 7 h + 4 h) —
mesma hora, mesmo dia, nada a decidir: fica na coluna, não vira divergência.

**DDL idempotente** (`_ensure`, chamada por `telas()` e por cada ação — nada em `alembic/`):

```sql
CREATE TABLE IF NOT EXISTS ponto_divergencia_regua (
  id serial PRIMARY KEY, competencia varchar(7), employee_id varchar(50),
  employee_nome varchar(200), dia date,
  batidas jsonb, pares_a int, horas_a numeric(8,2), detalhe_a jsonb,
  pares_b int, horas_b numeric(8,2), detalhe_b jsonb, delta_h numeric(8,2),
  causa varchar(32), quem_acerta varchar(16), mais_perto varchar(1),
  horas_planejadas numeric(8,2), observacao text, apurado_em timestamptz);
CREATE UNIQUE INDEX IF NOT EXISTS ux_ponto_divergencia_regua ON … (competencia, employee_id, dia);
CREATE INDEX IF NOT EXISTS ix_ponto_divergencia_regua_causa ON … (competencia, causa);
```

Dois botões de calibragem, declarados como calibragem e não como lei: `DUPLICADA_MIN = 3` (min) e
`TOL_REALIDADE_H = 2.0` (h).

### 3b. Telas — `backend/modules/operacional/controllers/redesign_builders/_dgx_y2_direcao_batida.py` (novo)

Duas abas no **FIM do g-ponto** do Departamento Pessoal:

| Aba | Deep-link |
|---|---|
| **Direção da batida: A × B** | `/redesign/departamento-pessoal?t=ponto-divergencia-regua` |
| **Apurar direção da batida** | `/redesign/departamento-pessoal?t=ponto-divergencia-regua-apurar` |

Colunas: Pessoa · Dia · **Batidas cruas (hora · tipo)** · Régua A — folha · Régua B — tela · Δ ·
Planejado · Causa provável · Quem bate com a realidade. Na coluna das batidas, `+` marca a batida
do dia civil seguinte (plantão noturno) e `*` marca a batida que a régua A usou para abrir turno
e a régua B recusou — o mecanismo da divergência aparece na própria evidência. Três filtros
combináveis: Competência, Causa, Quem acerta. O subtítulo carrega o resumo por causa e o placar
de quem acerta.

Clicando na linha, quatro fichas: o que explica · os pares da régua A · os pares da régua B ·
quem chegou mais perto (com o aviso de que é desempate fraco).

### 3c. Plugues (2 arquivos tocados, 5 linhas)

- `redesign_builders/departamento_pessoal.py`: import do `router` no topo + `telas(db, out)` no
  fim do `build()`, comentário `# dgx y2`.
- `redesign_builders/_dp_grupos.py`: as duas abas no FIM do g-ponto.

`calculo_service.py`, `espelho_service.py`, `horas_service.py`, `time_record_service.py`,
`alembic/`, `frontend/`, `checar_regressao.py` — **nada tocado**. Produção, só leitura.

---

## 4. Oráculo — `backend/scripts/orq/test_oraculo_y2_direcao_batida.py`

```bash
ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\n' ' ')
docker run --rm --network conecta-staging-network -v "$PWD/backend:/app:ro" \
  --tmpfs /app/logs:rw,mode=1777 --tmpfs /app/uploads:rw,uid=999,gid=999 \
  -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env \
  -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \
  conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_y2_direcao_batida.py
```

**VERMELHO** (árvore-base — `divergencia_regua.py` fora da árvore, tabela derrubada):

```
FALHOU: (a-e) o serviço da frente Y2 não existe — cannot import name 'divergencia_regua' from 'modules.people_management.ponto.services' (/app/modules/people_management/ponto/services/__init__.py)
TOTAL desvios: 1
```

**VERDE** (com a frente):

```
(b) apurar 2× em 2026-09: 36 → 36 linha(s) · chaves 36 → 36 · Σ|Δ| 97.09 → 97.09 h
(a) fixture 1 (tipo_errado_no_aparelho): 3 dia(s) divergente(s) de 3 plantões · Δ [6.0] h · causa(s) ['tipo_errado_no_aparelho'] · quem acerta ['A']
(a) fixture 2 (batida_duplicada): 3 dia(s) divergente(s) de 3 plantões · Δ [7.0] h · causa(s) ['batida_duplicada'] · quem acerta ['ambas_erram']
(a) fixture «saída ao voltar»: régua A 11,00 h × régua B 5,00 h, Δ 6,00 h (a batida de 01:00 tipada «saída» abre turno numa e não na outra)
(c) 65 pessoa×dia divergentes · Σ|Δ| 172.27 h · por causa: tipo_errado_no_aparelho 51/115.16 h · batida_duplicada 11/44.52 h · virada_de_meia_noite 1/12.53 h · batida_faltando 2/0.06 h
(d) linhas «indeterminado»: 0 · sem as duas réguas terem rodado: 0
(e) paralelo cego: 793 holerite(s) e 285 espelho(s) fotografados antes e depois da apuração · Σ|Δ| R$ 0.00 · espelhos reescritos: 0
(§7) quem bate com a jornada planejada: ambas_erram 50 · A 6 · sem_turno 4 · B 3 · empate 2 · desempate fraco (só mais perto): régua A 45, régua B 16
TOTAL desvios: 0
OK direção da batida: as duas réguas medidas lado a lado, causa por causa, idempotente — e a folha intacta em R$ 0,00
```

(Os 65/172,27 h incluem as **6 linhas de fixture**; o dado REAL é 59 pessoa×dia / 133,27 h, e o
placar real é A 3 · B 3 · empate 2 · ambas_erram 47 · sem turno 4, mais_perto A 39 · B 16.)

**O que cada item afirma** — regra, não fotografia:

- **(a) fixture determinística.** Um 12x36 noturno em que a pessoa bateu «saída» ao VOLTAR do
  intervalo (19:00 entrada · 00:00 saída · **01:00 SAÍDA** · 07:00 saída). A régua A tem de dar
  11 h, a régua B 5 h, Δ **exatamente** 6,00 h, causa `tipo_errado_no_aparelho`. Uma segunda
  fixture (toque duplo a 1 min) tem de sair `batida_duplicada` — prova a ORDEM das causas.
- **(b) apurar 2× não duplica.** Mesma contagem, mesmas chaves, mesmo Σ|Δ|.
- **(c) a soma das horas por causa == o total**, recontado por **SQL próprio do oráculo** sobre a
  tabela, não pelo dicionário que `apurar` devolve. E toda causa gravada está na lista fechada.
- **(d) nenhum `indeterminado` cego.** Uma linha só pode confessar ignorância se houver batida
  crua registrada E pelo menos uma das réguas tiver produzido par naquele dia. `indeterminado`
  com `batidas` vazio é medição que não aconteceu, não ignorância honesta.
- **(e) paralelo cego.** Fotografia de proventos/descontos/líquido de **793 holerites** e de
  dias/horas de **285 espelhos** antes e depois de rodar `apurar` nas três competências:
  **Σ|Δ| = R$ 0,00**, 0 espelhos reescritos.

Fixtures `'FIXTURE DGX Y2'` apagadas ao fim — conferido no sandbox: `0|0|0|0` em `employees`,
`shifts`, `gp_clock_punches` e `ponto_divergencia_regua`.

### Vizinhos, verdes

| Oráculo | Resultado |
|---|---|
| `test_oraculo_x4_pareador_unico.py` | **verde** · (b) 0 fora do dia do plantão · (f) 0 / 2 · (d) 167 holerites, R$ 0,00 · (e) 8 declarados, 0 não declarados |
| `test_oraculo_w1_dias_trabalhados.py` | **verde** · (b) Σ\|Δ\| dias 0 · (c) 167 holerites, R$ 0,00, informativo mudou em 25 |

O item (e) da X4 continua dizendo **8 pareadores, 0 não declarados**: `divergencia_regua.py` não é
um nono — ele importa `horas_service`, que é justamente a cláusula que a X4 escreveu para premiar
quem reusa a régua em vez de copiá-la.

**Ruff:** limpo nos três arquivos novos e nos dois tocados.

**HTTP:** container `teste-dgx-y2` na porta 8272. `/health` **200**;
`GET /api/v1/redesign/data/departamento-pessoal` → **200 · 7.300.530 bytes**, aba
`ponto-divergencia-regua` no fim do g-ponto com **59 linhas** e o stub de deep-link em
`screens[ponto-divergencia-regua] = {"type":"redirect"}`;
`POST /api/v1/redesign/action/ponto-divergencia-regua-apurar {"competencia":"2026-09"}` → **200**
(«51 pessoa(s) com batida, 18 com divergência… Σ|Δ| 58.09 h… Nenhum holerite, espelho ou registro
de ponto foi tocado»); competência futura → **400** («01/2027 ainda não aconteceu»). Container
**parado e removido**.

---

## 5. O que NÃO foi feito e por quê

1. **Nenhuma régua foi escolhida.** É o que o brief manda e é o que o dado recomenda (§7.1).
   Nada em `horas_service.py`, `time_record_service.py`, `calculo_service.py` ou
   `espelho_service.py` foi tocado.
2. **Nenhum dado foi corrigido.** Nem batida com tipo errado, nem duplicata, nem escala faltando.
   Corrigir 59 dias de uma vez é exatamente o que o Ponytail manda parar e perguntar — e a
   pergunta está no §7.2.
3. **Geofence e cobertura não entraram no árbitro.** A jornada planejada de `shifts` é o único
   sinal presente em todos os dias medidos; `latitude`/`longitude` existem em parte das batidas e
   o raio do posto tem default de 150 m — um árbitro que só opina em metade dos casos teria
   produzido veredito enviesado. O campo está lido e guardado, mas não pesa. §7.4.
4. **A borda de competência (§7.3 da X4) continua aberta** — 63,19 h da régua A e 31,65 h da
   régua B, medidas no §1b desta frente. É outra pergunta e outra frente.
5. **`checar_regressao.py` não foi editado** — a linha sugerida está no §7.5, para o orquestrador
   registrar.
6. **Produção não foi tocada.** Toda medição foi no sandbox (`conecta_pro_staging`).

---

## 6. Como o Jordan testa amanhã

1. **Abra** `/redesign/departamento-pessoal` → **Ponto & Jornada** → aba
   **«Direção da batida: A × B»**. 59 linhas, o resumo por causa no subtítulo.
2. **Filtre por Causa = «tipo errado no aparelho»** — 48 linhas, 97 h. É a maior fatia e é sempre
   a mesma história: alguém bateu «saída» quando devia bater «entrada».
3. **Filtre por «Quem acerta» = «as DUAS erram»** — 47 linhas. É a leitura que importa: na
   maioria dos dias divergentes **nenhuma** das duas réguas chega perto do turno planejado.
   Trocar de régua não resolveria esses dias.
4. **Clique em ANILSON JOSE SEIXAS NEVES, 25/08** (o caso de escola da X4): as fichas mostram que
   a régua A pareou `00:00→01:00` = 1 h e a régua B pareou `01:00→06:59` = 5 h59. **Aqui a tela
   acerta e a folha erra.** Agora clique em **ADAILSON SERRA ALVES, 01/09**: é o contrário.
5. **Rode a aba «Apurar direção da batida»** duas vezes na mesma competência: o número tem de ser
   idêntico nas duas.
6. **O holerite não pode mudar.** Calcule 09/2026 de qualquer pessoa antes e depois de apurar:
   proventos, descontos e líquido idênticos. Se um centavo se mexer, o oráculo mentiu.

---

## 7. Decisões que só o dono pode tomar

### 7.1 — A recomendação, com o número que a sustenta

**Recomendação: não escolher régua agora. Corrigir o dado.**

O que sustenta:

- Em **47 dos 55** dias divergentes com turno lançado (85 %), **as duas réguas erram** por mais de
  2 h contra a jornada planejada. Só em **8** dias uma delas bate: régua A em 3, régua B em 3,
  empate em 2. **Escolher entre as duas resolveria 3 dias e deixaria 47 errados.**
- **48 dos 59** dias (72,9 % das horas — **97,16 h**) têm uma causa só e ela é de DADO:
  `tipo_errado_no_aparelho`. Mais **8** dias / 23,52 h de `batida_duplicada`, também de dado.
  **Corrigir tipo e duplicata faz as duas réguas convergirem em 56 dos 59 dias e em 120,68 das
  133,27 h (90,6 %)** — sem tocar uma linha de código de pareamento.
- Sobram 3 dias / 12,59 h: 1 `virada_de_meia_noite` e 2 `batida_faltando`, ambos sem turno
  lançado ou com ponta que ninguém fechou.

**Se ainda assim for preciso escolher UMA régua hoje**, o número aponta para a **régua A (a
cronológica, a que a folha já usa)**: ela chega mais perto do turno planejado em **39 dos 55**
dias com turno (71 %), contra 16 da régua B. E tem um argumento que não é de acerto e sim de
risco: a régua A **já é** a do caminho de dinheiro, então adotá-la também na tela custa
**R$ 0,00** de mudança de folha. Adotar a régua B mudaria `horas_trabalhadas` e
`horas_noturnas` — HE 50 % e adicional noturno — e exigiria um paralelo cego de dinheiro próprio,
com recálculo de 09/2026 verba a verba antes de qualquer publicação.

**O que precisa ser corrigido no DADO (não no código):**

| # | Correção | Resolve |
|---|---|---:|
| 1 | O app/relógio não pode registrar `saida` quando não há turno aberto para a pessoa — o tipo tem de vir da ordem do turno, não do botão que o dedo achou | **48 dias · 97,16 h** |
| 2 | Recusar (ou fundir) batida a menos de 3 min da anterior, no aparelho | **8 dias · 23,52 h** |
| 3 | Lançar escala nos dias sem turno (4 dias hoje sem árbitro possível) | não muda o Δ, mas torna o dia **arbitrável** |

### 7.2 — Corrigir os 59 dias já apurados: sim ou não?

A tabela de conferência sabe, dia a dia, qual batida está com o tipo errado e qual é duplicata.
Dá para escrever a correção — **e esta frente não escreveu**, de propósito: são batidas de ponto,
e 19 espelhos de 07/2026 já estão homologados pelo colaborador (X4 §1c). Reescrever batida de mês
homologado é assunto de dono, não de agente. Se o Jordan autorizar, a correção precisa de: mês
não fechado, trilha de auditoria por batida e o holerite recalculado em paralelo cego antes de
publicar.

### 7.3 — A tolerância de 2 h do árbitro

`TOL_REALIDADE_H = 2.0` é calibragem declarada, não lei. Apertando para 1 h, `ambas_erram` cresce;
afrouxando para 3 h, diminui. O número do §7.1 (85 % de `ambas_erram`) é robusto à escolha porque
a maioria dos dias erra por 5 h ou mais — mas quem manda na régua é o dono.

### 7.4 — Geofence como segundo árbitro

`gp_clock_punches` tem `latitude`/`longitude` e o posto tem raio (default 150 m). Uma batida fora
do geofence do posto é evidência forte de que ela não pertence àquele turno — e resolveria parte
dos 47 `ambas_erram`. Não entrou aqui porque a cobertura de coordenada é parcial e um árbitro que
só opina em metade dos casos enviesa o veredito. Ligar isso é uma frente própria, com medição de
cobertura primeiro.

### 7.5 — Linha para o `checar_regressao.py` (o orquestrador registra)

```python
    # As duas réguas de pareamento discordam em 133,27 h sobre 07+08+09/2026 (DGX Y2 §1), e 72,9%
    # dessas horas têm uma causa só, de DADO: batida tipada `saida` abrindo turno. O oráculo trava
    # a MEDIÇÃO — fixture determinística, idempotência, soma por causa fechando com o total,
    # nenhum `indeterminado` cego e R$ 0,00 contra os holerites. Fica vermelho no dia em que a
    # conferência parar de medir, ou no dia em que ela começar a mexer em dinheiro.
    "test_oraculo_y2_direcao_batida.py": lambda s: _n(r"^TOTAL desvios: (\d+)", s),
```
