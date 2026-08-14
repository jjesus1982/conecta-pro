# Operacional — fechamento T4 · 13/08/2026

**Veredito: NÃO FECHADO — 4/7 condições.** Os 3 vermelhos que restam dependem de decisão
do Jordan, não de código meu. Rode o critério a qualquer momento:

```bash
python3 /opt/conecta-pro/backend/scripts/qa/fechado_operacional.py     # do host
```

Baseline no início desta ordem: **1/7**.

---

## As 7 condições

| # | condição | antes | agora |
|---|---|---|---|
| 1 | repositório: 0 chamada a método inexistente | ❌ 16 | ✅ **0** |
| 2 | vocabulário: 0 CRITICO em operacional/campo | ❌ 10 | ❌ **8** (2 eram falso-positivo) |
| 3 | rotas do front: 0 inexistente alcançável por tela | ❌ 7 | ✅ **0** |
| 4 | oráculos do operacional verdes | ✅ 7/7 | ✅ **7/7** |
| 5 | disciplinar: 0 medida aplicada >7d sem registro de ciência | ❌ 5 | ❌ **5** |
| 6 | apuração: nenhuma batida não-aprovada entra sem regra | ❌ 760 | ❌ **760** (agora **declarado na tela**) |
| 7 | tabela morta: nenhuma aba na fonte morta havendo viva | ❌ 3 pares | ✅ **0** |

---

## Antes de tudo: a primeira coisa medida estava errada — e era minha

A ordem avisava *"toda trava aqui já mentiu"*. Mentiu, mas não do jeito esperado: as travas
estavam certas e **o meu leitor delas estava errado**. Meu primeiro parser filtrava a saída
por substring genérica e imprimia **verde em 3 condições que tinham 33 achados**.

Se eu tivesse parado no primeiro verde, este relatório diria "módulo quase fechado" com
16 métodos inexistentes, 10 literais fora do vocabulário e 7 rotas mortas de pé.

Corrigido: cada condição agora parseia o formato real da trava. E `checar_vocabulario` roda
**no container** — do host ela quebra em `ModuleNotFoundError: core`, porque confronta a
coluna no banco e o host não alcança o Postgres. Ela vinha "passando" por não rodar.

---

## Lente CÓDIGO

### ✅ F5 · 7 rotas que o front chamava e o backend não tinha

Provado por HTTP — **404 = rota não existe, 401 = existe e pede auth**. Não precisou de
credencial para provar.

**(1) Medidas disciplinares — o achado mais grave da ordem.**

```
POST /api/v1/operacional/disciplinary/{id}/sign                              → 404
POST /api/v1/people-management/hr/discipline/medidas-administrativas/{id}/assinar → 401
```

O `services/disciplinary.ts` errava **tudo**: prefixo (`operacional/disciplinary` em vez de
`people-management/hr/discipline`), verbo (`/sign` `/approve` `/reject` `/submit` em inglês
onde o backend usa `/assinar` `/aprovar` `/rejeitar` `/submeter`), método (`PUT` onde o
backend expõe `PATCH`) e payload (`{comments}` onde o schema pede `{notes}`; `submit` ia sem
corpo obrigatório).

**Nenhuma ação disciplinar jamais saiu da tela.** E isso explica a condição 5 e metade da F8:
o banco tem **20 medidas — 15 em rascunho e 5 aplicadas, 0 assinadas**. Criar funcionava
(a ação do redesign chama o service direto); *avançar* não. Os 15 rascunhos são pessoas que
tentaram e o botão não fez nada.

O modal `DisciplinarySignatureModal` que o redesign chama em `row.sign` — o que eu mesmo
liguei — estava morto pelo mesmo motivo.

As duas rotas de IA (conformidade/proporcionalidade) **não são por id**: recebem o retrato da
medida. Passaram a receber a medida inteira, e os antecedentes vêm do **histórico real** do
funcionário, não de `0` fixo — a IA pesa antecedente, e zero fabricado mudaria o parecer.

**(2) Templates de escala.** `useScaleTemplates.ts` usava `/operacional/templates-escalas`
(404); o real é `/operacional/scales/templates/` (401). `update` PUT → PATCH. O `preview` foi
**removido**: o backend nunca expôs dry-run, só `/apply` — que cria a escala de verdade.
Manter o botão era prometer uma prévia que dá 404.

**(3) Campo (5 chamadas) — FALSO-POSITIVO, mas corrigido na fonte.** O `api-client.ts` já
reescrevia `/campo/guardian/campo/campo` → `/campo` num interceptor: em runtime nunca
quebraram. A trava é estática e não enxerga interceptor. Tirei o prefixo residual do cliente
gerado para pista e código coincidirem.

`tsc --noEmit`: 0 erro nos arquivos tocados.

### ✅ F4 · Camada de serviço de Ocorrências → quarentena

Os 16 achados da trava eram todos daqui. Levantei **18 chamadas a 14 métodos** que o
`OccurrenceRepository` (12 métodos reais) nunca teve — atingindo o miolo: `create()`,
`list()`, `add_comment()`, `get_dashboard_stats()`.

Mas o defeito é mais fundo: **os dois arquivos não importam.**

```
occurrence_service.py     → ImportError: cannot import name 'OccurrencePriority'
occurrence_ai_analyzer.py → ImportError: idem     (o nome certo é OccurrenceSeverity)
```

Como qualquer import estouraria na subida e o app sobe, **ninguém nunca importou**. E as
ocorrências *funcionam* — 16 rotas montadas, respondendo 401 — porque o
`occurrence_controller.py` usa o repositório **direto**. Funcionam **apesar** desta camada,
não através dela.

Por isso quarentena e não conserto: consertar seria implementar 8 métodos de repositório para
uma camada que ninguém chama. Seguindo a convenção de `financial/costing/_quarentena`, com
LEIA-ME registrando o caminho de volta. `models/`, `repositories/`, `schemas/` e
`controllers/` ficaram — tirar modelo do import faria o Alembic **propor DROP** das tabelas.

### ✅ F6 · Erro que se disfarça de resposta

Dois `except` em `campo_service_controller.py` devolviam vazio como se fosse a resposta:

- `/campo/technicians`: "nenhum técnico" e "a consulta explodiu" ficavam indistinguíveis.
- `/campo/dashboard`: devolvia o dict `vazio` — **zeros que se leem como "noite tranquila"**.
  Pior que erro, porque o gerente confia.

Ambos agora logam com traceback e levantam 500.

**O `datetime.utcnow()` do `ordem_servico.py:514` eu NÃO troquei, de propósito.** A coluna
`sla_vencimento` é `DateTime` **naive** e outros 187 pontos de campo/operacional usam o mesmo
estilo. Trocar só esta linha por timezone-aware **quebraria `is_atrasada()` na linha 366**,
que faz `datetime.utcnow() > self.sla_vencimento` — aware vs naive levanta `TypeError`. É
questão de convenção do repositório inteiro, não conserto de uma linha. E `ordens_servico`
tem **0 linhas**: o caminho existe e nunca foi exercido.

### ❌ F1 · Os 8 filtros inertes — BLOQUEADO no Jordan

```
gp_clock_punches.status  NOT IN ('cancelado', 'rejected')
vocabulário real: approved 6458 · pending 1275 · fora_local 103 · normal 5 · regular 2
'cancelado' e 'rejected': 0 linhas em 7843
```

8 pontos filtram por valores que a coluna nunca teve. O filtro é decorativo: **não exclui
nada**. Não consertei — a ordem proíbe, e com razão: trocar por `= 'approved'` descarta 29%
das batidas e pode virar falta onde houve trabalho.

**Cuidado que quase me pegou:** `'cancelado'` e `'rejected'` **existem** como enum — em
`time_bank`, `substitution`, `documento_fiscal`. Nenhum governa `gp_clock_punches`. Um teste
ingênuo de "esse literal existe em algum enum?" teria limpado o F1 por engano. A condição 2
agora ancora no **modelo da tabela**.

**Isso também revelou 2 falso-positivos que a ordem não citava e que eu abati:**
`tasks.py:552,565` filtram `occurrences.status IN ('aberta','em_analise')` — literais que a
trava acusou por não existirem *na coluna*. Mas `'aberta'` é o **default do próprio modelo** e
membro do `OccurrenceStatus`. A tabela tem 4 linhas, todas `cancelada`: a trava comparou com
valor **observado**, não com o domínio **declarado**. Código certo, tabela vazia.

⚠️ **Mas há um defeito real ali ao lado, este sim:** essas duas tasks alertam sobre ocorrência
aberta e **nunca dispararam nem dispararão**, porque não existe ocorrência aberta desde
09/07/2026. Não é bug de código — é função morta (ver F8).

---

## Lente DADO

### ✅ F3 · Diaristas — as abas liam um universo morto

O módulo tem **dois universos** de diarista, e o redesign operava o errado:

| morto | vivo |
|---|---|
| `diarist_schedules` **0** | `diaria_diaristas` **51** |
| `diarist_assignments` **0** | `diaria_lancamentos` **308** |
| `diarist_payments` **0** | `diaria_postos` **10** |
| `diarist_evaluations` **0** | `financial_pagamentos_diaristas` **251** |
| `diarists` **3** — ids UUID | ids **integer** |

Os 3 registros de `diarists` são teste: **o próprio Jordan, Gizely, e uma de julho** — contra
51 diaristas reais. Os 251 pagamentos têm `schedule_id` **NULL**: o fluxo real nunca passou
pelo universo morto. E os ids são de **espaços diferentes** (UUID vs integer) — nenhuma
daquelas ações jamais alcançaria uma pessoa real.

O que mudou:

- **`diaristas-fechamento`**: `diarist_payments` (0) → `financial_pagamentos_diaristas`.
  **251 pagamentos que estavam invisíveis** no redesign. `exibido==banco` conferido.
- **`diaristas-escala`: removida.** Lia `diarist_schedules`; o equivalente vivo
  (`diaria_lancamentos`) já é a aba `diarias` — duas abas para a mesma lista seria ruído.
- **7 ações saíram do menu** (endpoints seguem de pé, só não são oferecidos):
  `diarista-ativar/desativar/avaliar`, `-escala-criar`, `-fechamento`,
  `-assignment-criar/cancelar`.

Duas dessas mereciam destaque:

- **"Avaliar diarista" era impossível de concluir.** Exigia condomínio vindo de
  `diarist_schedules` (0 linhas) e caía **sempre** em `400 — Diarista sem condomínio
  vinculado`. `diarist_evaluations` = 0 confirma: ninguém nunca conseguiu.
- **"Gerar fechamento" era a pior.** Criava `DiaristPayment` em tabela que ninguém paga —
  **sensação de fechamento feito sobre dinheiro que não fecha.**

`g-diaristas`: 14 itens → **6**, todos sobre dado vivo.

### ⚠️ Um oráculo verde que não provava nada

Ao mexer nisso, o `test_oraculo_op_readfix2_redesign` ficou vermelho — e ao abrir, o vermelho
era o correto. Ele checava `diaristas-escala` vs `diarist_schedules` e `diaristas-fechamento`
vs `diarist_payments`. **Ambas com 0 linhas: passava com `0 == 0` sobre tabela morta.**

`exibido == banco` só tem força quando o banco tem linha. Agora bate nos 251 pagamentos reais.

Ficam dois `0 == 0` no mesmo oráculo (`substituicoes`, `avaliacao-equipe`) — mas ali a tabela
viva **está** vazia de verdade, que é diferente de ler a tabela errada.

---

## Lente TELA

### ✅ F2 · A apuração agora declara a própria procedência

A tela de banco de horas passou a dizer, medido em produção:

> ⚠️ Inclui **760** batida(s) NÃO aprovada(s) de **2654** (**29%**) — pendente/fora do local
> entram no cálculo porque ainda não há regra de apuração definida. Confira antes de lançar.

**Não mexi no cálculo.** Se `pending` deve contar é regra de negócio do Jordan, e errar aqui
tem consequência trabalhista. O defeito era entrar em **silêncio** num número que vira hora
paga. Enquanto a regra não vem, a tela conta.

---

## F7 · As 5 ações que o front não alcança — veredito de cada uma

`backend_recon`: 304 rotas, 288 expostas, **0 geradores de documento órfãos**. Paridade não é
o problema deste módulo.

| rota | veredito | motivo |
|---|---|---|
| `DELETE /operacional/allocations/bulk` | **órfã por desenho** | alocação é curada à mão pelo Jordan; agente não escreve. Dar tela contraria a regra. |
| `PATCH /operacional/allocations/bulk` | **órfã por desenho** | idem. |
| `PATCH /operacional/shifts/bulk` | **órfã por desenho** | escala é curada à mão; edição em massa de turno é exatamente o que a regra proíbe. |
| `POST /operacional/scales/{id}/reject` | **já tem tela** | o redesign expõe `escala-rejeitar` reusando `ScaleRepository.reject` **direto**. A rota HTTP fica órfã porque o redesign chama a função, não a rota — ponto cego conhecido do recon. |
| `POST /operacional/unificado/desalocar-diarista/{id}` | **quarentena** | opera `diarist_assignments` (0 linhas, universo morto — ver F3). Saiu do menu junto com as outras 7. |

---

## F8 · As 4 funções com uso ZERO — veredito de cada uma

Medido hoje, 13/08:

```
turnos (30d) 2831 · faltas formalizadas 0 · substituições 0 · banco de horas 0
medidas 20 (15 rascunho + 5 aplicada) · assinadas 0 · recusa formal 0
rondas 51 · avaliações de equipe 3
```

**1. Faltas formalizadas — 0 em 2831 turnos. Veredito: bloqueado, decisão do Jordan.**

A causa é estrutural e mede-se em uma linha: o status dos turnos é **só `scheduled` (2015) e
`cancelled` (1652)**. Não existe `completed`. **O ciclo de vida do turno nunca avança.** O
turno é criado, às vezes cancelado, e nunca fechado — então não há momento em que alguém
"faltou". O botão existe; o processo que o chamaria, não.

**2. Substituições — 0. Veredito: consequência da 1.** Substituição nasce de falta. Sem falta
formalizada, não há o que substituir. Não é tela faltando.

**3. Banco de horas — 0 lançamentos desde sempre. Veredito: entra na rotina, mas só depois da
regra de apuração.** A tela de apuração agora calcula e mostra o saldo (derivado do ponto).
Lançar antes de o Jordan decidir o que fazer com as 760 batidas não-aprovadas seria efetivar
hora paga sobre base indefinida. **Quem/quando: Pyetra, no fechamento mensal, assim que a
regra existir.**

**4. Medidas assinadas — 0 de 20. Veredito: DESBLOQUEADO por esta ordem.** Era 0 porque
assinar dava 404 (F5). Agora o caminho existe. Os 15 rascunhos são fila real esperando alguém
submeter.

---

## O que a condição 5 realmente diz (correção de rumo minha)

Escrevi a condição 5 como "medida aplicada sem ciência nem recusa" e ia reportá-la como
*"5 sanções que a empresa não prova ter comunicado"*. Fui olhar as 5 linhas:

```
ADV-TFM-20250710 · ADV-TFM-20260311 · SUS-TFM-20260427 · NOT-TFM-20260510  (THAIS)
NOT-FVM-20260503                                                          (FERNANDA)
```

Todas criadas em **02/07/2026, no mesmo dia**, com `approved_at` NULL e códigos de datas
antigas (2025-07 a 2026-05). É **carga histórica** — medidas reais digitadas retroativamente,
não sanções que passaram pelo fluxo.

A lacuna continua real (sem registro, a empresa não prova), mas **o remédio é outro**: anexar
o papel já assinado, não perseguir a colaboradora. A condição foi reescrita para dizer isso.

---

## NÃO COBERTO — e por quê

| item | por que não |
|---|---|
| **F1 · trocar os 8 filtros de status** | Decisão do Jordan. `pending` conta? `fora_local` conta? Entram com marcação? Trocar por `= 'approved'` descarta 29% das batidas e pode virar falta onde houve trabalho. |
| **Condição 5 · coletar as assinaturas** | Ação humana: anexar os papéis já assinados das 5 medidas históricas. |
| **Condição 6 · declarar a regra de apuração** | Decisão do Jordan. Criei o gancho (`operacional_apuracao_regra`) no critério, mas a regra é dele. |
| **F3 · rewire das ações de diarista para o mundo vivo** | Envolve dinheiro (fechamento → pagamento) e uma decisão de desenho: o universo `diarist_*` (com avaliação, alocação recorrente, folha própria) morre de vez, ou era ele que deveria estar em uso? Tirei do menu, que é reversível; não reimplementei. |
| **F3 · lado do financeiro** | `financeiro.py` é do T1. Recomendação abaixo. |
| **Responsivo/mobile e carga** | Fora do escopo desta ordem; segue não testado. |

### Para o T1 (não toquei em `financeiro.py`)

`financial_pagamentos_diaristas` tem 251 linhas com `schedule_id` **sempre NULL** e
`origem='diarias'` — ou seja, os pagamentos vêm de `diaria_lancamentos`, e a FK para
`diarist_schedules` é decorativa. Se houver tela ou conciliação no financeiro que faça `JOIN`
por `schedule_id`, ela retorna vazio hoje e retornará vazio sempre. Vale conferir e, se for o
caso, parear por `diarist_id` + `data_referencia`.

---

## Achado de infraestrutura (fora da ordem, mas real)

Durante o bake, `app.conectamais.pro/api` deu **502 por ~2 minutos** enquanto
`erp.conectamais.pro` ficou **200 o tempo todo**.

Motivo: o blue/green troca o `upstream backend` de `erp.conectamais.pro` (8080↔8081), mas
`app.conectamais.pro` tem `proxy_pass http://127.0.0.1:8080` **hardcoded** — fica fora do
switch e sofre queda real a cada deploy. Zero-downtime só vale para o `erp`.

Também confundi a mim mesmo aqui: dei o deploy como morto porque usei `pgrep` **sem `-f`**, e
o nome do processo é `bash`. O deploy estava vivo e terminou limpo — 8 workers, sem drift.

---

## Commits

```
9b685d9  fix(operacional): 7 rotas que o front chamava e o backend não tinha
e3761a2  fix(operacional): diaristas — abas e ações liam um universo morto
eaf1421  chore(operacional): quarentena da camada de serviço de Ocorrências (F4)
4c134be  fix(campo/operacional): erro que se disfarça de resposta + procedência da apuração
```

Deploy: blue/green concluído 23:06, backend + 8 workers na mesma imagem, sem drift.
Verificado em produção: rota velha de assinatura **404**, rota nova **401**, fechamento
exibindo 251, apuração exibindo o aviso.

---

## As 3 decisões que fecham o módulo

1. **Batida não-aprovada conta na apuração?** (`pending` 1275, `fora_local` 103) — sim, não,
   ou entra marcada? Sem isso o banco de horas não pode lançar.
2. **Turno vira `completed` por hábito ou por sistema?** Hoje nada fecha turno, e é por isso
   que falta e substituição são zero — não por falta de botão.
3. **O universo `diarist_*` morre?** Se sim, as 7 ações saem de vez. Se não, é ele que
   deveria estar sendo usado, e as diárias é que estão no lugar errado.
