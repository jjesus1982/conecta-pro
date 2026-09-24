# DGX Y4 — o colaborador sem cliente: um resolvedor, não 51 UPDATEs

**Data:** 24/09/2026 · **Branch:** `dgx/y4-vinculo-cliente` · **Módulo:** dp
**Origem:** `DGX_X3_feriado_he100.md` §7 item 5 — *«`employees.cliente_id` está órfão… feriado de
CLIENTE não alcança ninguém»*

---

## 1. O mapa do vínculo — de onde dá para derivar o cliente hoje

### 1.1 O número da chamada estava errado, e para pior

O brief herdou da X3 «47 de 63 órfãos». Medido hoje, sandbox **e** produção, idênticos:

| `employees.cliente_id` nos **63 ativos** | quantos |
|---|---|
| órfão (aponta para um `clients.id` que não existe) | **37** |
| nulo | **14** |
| FK válida | **12** |

Os **47** da X3 eram sobre os **104 empregados de todos os status** (44 nulos, 13 válidos lá).
Sobre os 63 ativos, quem **não tem cliente utilizável** não é 47 — é **51**. E os 12 que têm
apontam todos para o **mesmo** cliente (CONECTAMAIS ELETRONICA LTDA).

### 1.2 O campo é morto — isto não é opinião, é contagem

- **Sem `ForeignKey`**, no model (`operacional/models/employee.py:128`) e no banco.
- **Dois escritores vivos** no repositório inteiro: `candidatos_esteira_controller.py:788`
  (aprovação do candidato, que copia de `posts.client_id`) e o autocadastro de homologação.
  **A admissão não escreve** (`hr/services/admission_service.py` só resolve para o payload do
  evento), nem o PATCH de cadastro, nem o importador CSV, nem o sync da Sólides. Nenhum backfill.
- A casa **já tinha decidido** que o elo é outro: `operacional/services/restricao_cliente.py:9` diz
  *«O elo posto/condomínio → cliente é o da casa: `posts.client_id` e `condominios.client_id`»*, e
  `ged/services/kit_eventos.py` e `client_portal/services/portal_operacao_service.py` resolvem por
  alocação e **nunca** leem `employees.cliente_id`.

**Resposta ao que o brief mandou investigar: sim, `cliente_id` é campo morto e a verdade viva é a
alocação.** Esta frente resolve pelo caminho vivo e **não preenche os 51 cadastros**.

### 1.3 As fontes vivas, medidas nos 63 ativos

| Fonte | cobre | conflito interno |
|---|---|---|
| `allocations` vigente → `posts.client_id` | **60** | 0 |
| `employee_alocacoes` vigente → `condominios.client_id` | 48 | 0 |
| `shifts` (60 d) → `posts.client_id` | 56 | 2 |
| `employees.cliente_id` com FK válida | 12 | 0 |

`allocations.post_id` está 100% preenchido e os **17 postos** têm `client_id` válido; os **11
condomínios** têm `client_id` válido e são **1:1** com o cliente — então cliente → condomínio é
determinístico. `employee_alocacoes.posto_id` está vazio (0 de 73) e não serve de fonte.

### 1.4 O censo com a precedência da frente

| | quantos | quem |
|---|---|---|
| **uma fonte, sem conflito** | **58** | resolvidos por `alocacao_posto` |
| **mais de uma fonte, em conflito** | **2** | **MAURICIO ALVES CHAGAS** (posto diz Green Hills, condomínio diz Mirante das Flores) · **RILEM FERREIRA DE SOUZA** (posto diz Ideal Flores, condomínio diz Prime Arena) |
| **nenhuma fonte** | **3** | **ALAN VIEIRA DA SILVA** · **THIAGO DA SILVA MAQUINE** · **COLABORADOR TESTE HOMOLOGACAO** (fixture de homologação, não é gente) |

Um terceiro caso, **EULER FELIPE FERNANDES DA COSTA**, aparece com dois clientes se olharmos tudo
junto — mas a discordância é só no **turno** (cobriu um plantão no Mirante; as duas alocações dizem
Laranjeiras). A precedência resolve sem chamar de conflito: turno é log de evento, e cobertura é
normal. Ver §2.

---

## 2. O resolvedor único

**Antes de criar, cavei.** Já existiam `ged_client_do_funcionario` (alocação→posto→cliente, mas
devolve id do cliente **GED**, não do CRM), `hermes.resolver_colaborador` (só o ramo
`employee_alocacoes`) e os blocos de uma perna `client_do_posto`/`client_do_condominio` em
`restricao_cliente.py`. Nenhum era o resolvedor completo, e nenhum tinha precedência declarada.

`backend/modules/operacional/services/vinculo_cliente.py` — vizinho de `restricao_cliente.py`, que
é quem já declarava a regra da casa.

```python
cliente_do_colaborador(db, employee_id, ref=None) -> (cliente_id, fonte, confianca)
mapa_cliente(db, employee_ids=None, ref=None) -> {eid: {...}}   # a MESMA consulta, em lote
condominio_do_colaborador(db, employee_id, ref=None) -> condominio_id | None
definir_cliente(db, *, employee_id, client_id, motivo, ...)      # a exceção
```

`cliente_do_colaborador` é `mapa_cliente` de uma pessoa — **uma** implementação da regra, não duas.

### Precedência declarada

| # | fonte | de onde | confiança |
|---|---|---|---|
| 1 | `manual` | `dp_vinculo_cliente_manual` viva — o humano resolveu na tela | alta |
| 2 | `alocacao_posto` | `allocations` vigente em `ref` → `posts.client_id` | alta |
| 3 | `alocacao_condominio` | `employee_alocacoes` vigente em `ref` → `condominios.client_id` | alta |
| 4 | `turno` | `shifts` nos 60 dias até `ref` → `posts.client_id` | média |
| 5 | `cadastro` | `employees.cliente_id`, só com FK válida | baixa |

- **`conflito`** quando as duas fontes **de registro** (2 e 3) existem e discordam, ou quando uma
  fonte sozinha devolve mais de um cliente. Aí `cliente_id` volta **`None`** — conflito é
  sinalizado, nunca escolhido no escuro.
- **`turno` nunca gera conflito sozinho contra uma alocação**: é log de evento e registra cobertura
  e substituição (foi o caso do EULER). Só responde quando não há alocação nenhuma.
- **`cadastro` é o último de propósito.** Isso **não muda verdade**: para os 12 com FK válida o
  resolvedor devolve exatamente o mesmo cliente — **Σ divergências = 0** —, porque o escritor vivo
  daquela coluna copia de `posts.client_id`, a mesma fonte do nível 2. O oráculo afirma essa
  igualdade; se ficar vermelho, o cadastro passou a mentir contra a alocação viva.

### Os chamadores que passaram a usar o resolvedor — e os que **não** passaram

Regra seguida: **um por vez, e só os que eu provei que não mudam de comportamento.**

| Leitor | O que fiz | Prova |
|---|---|---|
| `folha/services/feriado_conferencia.py` (X3) | **trocado** — o condomínio vem do resolvedor, com `ref` = fim da competência (quem mudou de posto em outubro não reescreve setembro) | a cascata resolvia **0 das 61** pessoas; qualquer valor é acréscimo, nada muda para quem já tinha (ninguém tinha) |
| `ponto/config_ponto.py` (F7) | **linha morta deletada**, sem trocar pelo resolvedor | medido: quem resolve o condomínio lá é o `_SQL_CTX_POSTO` (`posto_atual_id → posts.client_id`), **48 dos 63**. A linha por `cliente_id` resolvia 0 ativos; no único registro do banco em que devolvia algo (um candidato), o caminho vivo devolve o **mesmo** condomínio. **Trocar pelo resolvedor TIRARIA o condomínio dos 2 em conflito** — seria mudar comportamento, e não fiz |
| `announcement_service.py:284` (comunicados por cliente) | **não tocado** | mudaria **quem recebe** comunicado. §5 |
| `vacation/termination/admission_controller` (payload GEDEON) | **não tocado** | mudaria o roteamento de kit. §5 |
| `ausencias.py`, `certification_service.py`, `cartao_lote.py`, `intelligent_operations_service.py` | **não tocados** | §5 |

### DDL que `_ensure` aplica em produção no 1º acesso (idempotente)

```sql
CREATE TABLE IF NOT EXISTS dp_vinculo_cliente_manual (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), employee_id uuid NOT NULL, client_id uuid NOT NULL,
  motivo text NOT NULL, definido_por varchar(120), ativo boolean NOT NULL DEFAULT true,
  definido_em timestamp NOT NULL DEFAULT (now() AT TIME ZONE 'America/Manaus'), definido_por_id uuid);
CREATE UNIQUE INDEX IF NOT EXISTS ux_dp_vinculo_cliente_manual_vivo
  ON dp_vinculo_cliente_manual (employee_id) WHERE ativo;
```

Nenhum DROP/DELETE/UPDATE em dado que a frente não criou. **Nenhum UPDATE em massa em
`employees`** — `definir_cliente` grava **uma** linha por vez, sempre com motivo.

---

## 3. A tela

`backend/modules/operacional/controllers/redesign_builders/_dgx_y4_vinculo.py`

**`vinculo-cliente`** — g-visao do DP · deep-link
`/redesign/departamento-pessoal?t=vinculo-cliente`

Colunas: Colaborador · Cargo · **Cliente resolvido** · **Fonte** · **Confiança** · Condomínio ·
Evidência. Conflito e sem-fonte saem **em vermelho e no topo** da lista. Filtros Situação × Fonte ×
Confiança. O subtítulo conta o estado e diz, com essas palavras, que definir à mão é a exceção.

Ação por linha **«Definir cliente»** → `POST /api/v1/redesign/action/vinculo-definir-cliente`
(cliente + motivo obrigatório ≥ 5 caracteres). Grava em `dp_vinculo_cliente_manual` **e** espelha
em `employees.cliente_id`/`cliente_nome`, que é onde os leitores antigos olham.

Plug: `departamento_pessoal.py` (2+2 linhas, `# dgx y4`), aba no `_dp_grupos.py` no fim do g-visao.

---

## 4. Oráculo e efeito medido

`backend/scripts/orq/test_oraculo_y4_vinculo_cliente.py`

```bash
docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" -e PYTHONPATH=/app \
  -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env -e SMTP_HOST= -e SMTP_USERNAME= \
  -e SMTP_PASSWORD= $ENVS conecta-pro-backend:latest \
  python3 /app/scripts/orq/test_oraculo_y4_vinculo_cliente.py
```

**VERMELHO** (antes do código — `vinculo_cliente` e `dp_vinculo_cliente_manual` não existiam;
depois de criar o serviço, sobrou a fiação):

```
alocacao_posto=58 · sem_fonte=3 · conflito=2 · condomínio resolvido=46/63 · Σ divergências vs cadastro válido=0/12 · Σ|Δ| na folha = R$ 0.00
DESVIO (h) a aba `vinculo-cliente` não está em `_dp_grupos.GRUPOS` — tela sem porta
DESVIO (h) `departamento_pessoal.py` não chama `_dgx_y4_vinculo`
DESVIO (h) config_ponto (F7) ainda não usa o resolvedor
DESVIO (h) config_ponto (F7) ainda tem a cascata morta `condominios.client_id = e.cliente_id`
DESVIO (h) feriado_conferencia (X3) ainda não usa o resolvedor
TOTAL desvios: 5
exit=1
```

**VERDE** (depois):

```
alocacao_posto=58 · sem_fonte=3 · conflito=2 · condomínio resolvido=46/63 · Σ divergências vs cadastro válido=0/12 · Σ|Δ| na folha = R$ 0.00
  conflito     MAURICIO ALVES CHAGAS — condomínio: CONDOMINIO MIRANTE DAS FLORES · posto: CONDOMINIO RESIDENCIAL GREEN HILLS · turno: …
  conflito     RILEM FERREIRA DE SOUZA — condomínio: CONDOMINIO PRIME ARENA · posto: CONDOMINIO IDEAL FLORES DA CIDADE · turno: …
  sem_fonte    ALAN VIEIRA DA SILVA — nenhuma fonte
  sem_fonte    COLABORADOR TESTE HOMOLOGACAO — nenhuma fonte
  sem_fonte    THIAGO DA SILVA MAQUINE — nenhuma fonte
TOTAL desvios: 0
OK vínculo cliente: … Σ divergências = 0 … conflito é sinalizado e nunca escolhido no escuro …
  nenhum feriado foi removido de ninguém e Σ|Δ| na folha = R$ 0,00
exit=0
```

Entre as afirmações, a que quase pegou um erro de dinheiro é a **(f)**: resolver o condomínio
**liga** o filtro de UF/cidade da régua de feriado, que hoje está desligado para todos (`co.estado
IS NULL` passa). O condomínio **ESCRITÓRIO** é `São Paulo/SP` e todos os feriados estaduais e
municipais do banco são **AM/Manaus** — se alguém caísse nele, perderia 4 feriados, e feriado
trabalhado se paga em dobro. Medido: **nenhum dos 63 ativos** resolve para o ESCRITÓRIO, e os
outros 10 condomínios têm UF/cidade vazias. O oráculo trava isso para o dia em que mudar.

**Vizinhos, os três verdes:** `x3_feriado_he100` (0 desvios, e com os **mesmos** 79 lançamentos e
o mesmo passivo R$ 5.399,01 de antes da frente) · `movimentacao_com_motivo` (0) ·
`grid_bate_com_a_triagem` (0).

### Efeito medido — quantas pessoas o feriado de CLIENTE passa a alcançar

`backend/scripts/orq/_y4_efeito_feriado_cliente.py` (medição, não oráculo): cria um feriado de
cliente `'FIXTURE DGX Y4'` num condomínio real, roda a apuração da X3 em **paralelo cego** e apaga
tudo no `finally`.

```
dia escolhido: 03/09/2026 (42 pessoa(s) bateram) · condomínio: IDEAL FLORES
ANTES (cascata por employees.cliente_id): 0/61 com condomínio → feriado de CLIENTE alcança 0 pessoa(s), por construção
DEPOIS (resolvedor pela alocação vigente): 28 pessoa(s) da apuração com condomínio
DEPOIS (condomínio resolvido pela alocação): alcance = 8 pessoa(s)
  ADEILSON DINIZ DEODATO · CELIANE GARCIA DE SOUSA · DANIEL VIDAL LARROQUE · EDILENE SALES SOUSA ·
  GEILSON RODRIGUES DE ANDRADE · JONHATA DINIZ BENAION · KELLY PATRICIA DA SILVA DE SOUZA · NAILSON GARCIA GOMES
vazou para outro condomínio: 0 (tem que ser 0)
fixture 'FIXTURE DGX Y4' restante: 0 (tem que ser 0)
Σ|Δ| em hr_payslips = R$ 0.00 (holerites: 844 → 844)
```

**0 → 8 pessoas** num condomínio; **0 → 46** dos 63 ativos passam a ter condomínio, e **28 de 28**
na apuração de 09/2026 (que antes mostrava «—» para todos). Nenhum centavo de folha mudou.

### Prova por HTTP (`teste-dgx-y4`, porta 8274, **parado ao fim**)

```
GET /api/v1/redesign/data/departamento-pessoal → 200
g-visao, abas: [… 'turnover-dashboard', 'vinculo-cliente', 'importacao-falhas']
vinculo-cliente: table · 63 linhas · cols [Colaborador, Cargo, Cliente resolvido, Fonte,
  Confiança, Condomínio, Evidência]
  linha 1 (vermelha, no topo): ALAN VIEIRA DA SILVA · AGENTE DE PORTARIA ·
    badge VERMELHO «— o dado não diz —» · «sem fonte nenhuma» · «nenhuma» · — · nenhuma fonte
  ação: «Definir cliente» → /api/v1/redesign/action/vinculo-definir-cliente?employee_id=…

POST …/vinculo-definir-cliente → 200
  {"fonte_antes": "sem_fonte", "fonte_depois": "manual", "mudou_cliente": true,
   "cliente_nome": "CONDOMINIO DO EDIFICIO MICHELANGELO"}
GET (de novo) → a linha do ALAN: CONDOMINIO DO EDIFICIO MICHELANGELO · «definido por pessoa» ·
  «alta» · MICHELANGELO   ·   subtítulo: 59 resolvidos (era 58) · 2 sem fonte (era 3)
```

Fixture desfeita ao fim. Conferido no sandbox: `FIXTURE DGX Y4` em `dp_vinculo_cliente_manual`,
`cct_feriados` e `folha_feriado_conferencia` = **0**, e `dp_vinculo_cliente_manual` vivo = **0**.

---

## 5. O que NÃO foi feito, e por quê

1. **Não preenchi os 51 cadastros.** Era o pedido explícito do brief e é a decisão certa: preencher
   por inferência é decisão do dono, e o resolvedor existe para não precisar. Nenhum UPDATE em
   massa em `employees`.
2. **Não troquei 4 dos 6 leitores de `employees.cliente_id`.** Todos mudariam comportamento, e a
   regra era trocar só o que eu provasse que não muda:
   - `announcement_service.py:284` — comunicados com `destinatarios_tipo='client'` filtram por
     `Employee.cliente_id.in_(...)`. Hoje alcançam só os 12; com o resolvedor alcançariam ~58.
     **Mudaria quem recebe comunicado** — é envio, e é decisão do dono (§7).
   - `vacation_controller.py:292`, `termination_controller.py:312`, `admission_controller.py:173`
     — passam `cliente_id` para o GEDEON montar o kit. Trocar muda **para qual cliente o kit vai**.
   - `certification_service.py:138` grava `hr_certifications.cliente_id`; `ausencias.py` agrupa
     faltas por nome de cliente; `cartao_lote.py:22` e `_dgx_f7_ponto.py:1104` filtram quem entra
     no PDF de cartão de ponto em lote — trocar **acrescenta gente** ao lote, que é mudança.
   - `intelligent_operations_service.py:318` usa `cliente_id` como **tenant_id** do otimizador de
     escala. Mexer ali é mexer em multi-tenancy, não em vínculo.
3. **Não consertei um bug que achei de passagem:** `hr/services/colaboradores_export.py:121` faz
   `LEFT JOIN condominios cd ON cd.id = e.cliente_id` — junta um id de **cliente** contra
   `condominios.id`. Está errado em duas camadas (coluna errada **e** campo morto) e o
   `condominio_nome` do export sai vazio. Fora do escopo da frente; fica registrado.
4. **Não pus `FOREIGN KEY` em `employees.cliente_id`.** Com 37 órfãos vivos, a constraint não sobe
   sem antes decidir o que fazer com eles — e isso é o §7.
5. **Não resolvi os 2 conflitos nem os 3 sem-fonte.** É exatamente o que a tela existe para o
   humano fazer; escolher no lugar dele seria inventar dado.
6. **`JANELA_TURNO_DIAS = 60` é corte de leitura, não regra de lei.** Separa «trabalha lá» de
   «cobriu um plantão em março». Está nomeado no módulo para ser achado e discutido.

---

## 6. Como o Jordan testa amanhã

1. DP → **Visão geral** → aba **Vínculo com o cliente**
   (`/redesign/departamento-pessoal?t=vinculo-cliente`).
2. No topo, em vermelho, os **5 casos que o dado não resolve**: MAURICIO e RILEM (conflito) e ALAN,
   THIAGO e o COLABORADOR TESTE (sem fonte). Na coluna **Evidência**, o que cada fonte diz.
3. Filtre **Situação = precisa de gente** — é a fila de trabalho.
4. No MAURICIO, clique **Definir cliente**: escolha Green Hills ou Mirante e escreva o porquê.
   Recarregue: a linha fica verde, a fonte vira **«definido por pessoa»**, confiança **alta**.
   *O caminho certo, porém, é corrigir a alocação* — aí ele sai do vermelho sozinho.
5. Confira o efeito: DP → **Folha** → **Feriado trabalhado e HE 100%**. A coluna do condomínio,
   que antes era «—» para todo mundo, agora traz o condomínio de **28 de 28** pessoas de 09/2026.
   Nenhum valor mudou (o passivo segue R$ 5.399,01).

---

## 7. Decisões que só o dono pode tomar

1. **O que fazer com os 51 cadastros órfãos/nulos.** Três caminhos: (a) deixar como está — o
   resolvedor cobre 58 dos 63 e ninguém precisa do campo; (b) backfill único a partir da alocação
   vigente, e depois **`FOREIGN KEY` + limpeza dos 37 órfãos**, para o campo parar de apodrecer;
   (c) **aposentar a coluna** e fazer os 6 leitores restantes usarem o resolvedor. A recomendação
   técnica é (c), mas ela muda quem recebe comunicado e para onde vai kit do GEDEON — por isso é sua.
2. **Os 2 conflitos são dado errado ou vida real?** MAURICIO está alocado em Green Hills pelo posto
   e em Mirante das Flores pelo condomínio; RILEM, em Ideal Flores e Prime Arena. Ou ele trabalha
   em dois lugares (e o sistema precisa suportar isso), ou uma das duas alocações não foi encerrada.
3. **ALAN VIEIRA DA SILVA e THIAGO DA SILVA MAQUINE não têm alocação nenhuma** e estão ativos. São
   escritório, afastados, ou é alocação que ninguém lançou?
4. **`COLABORADOR TESTE HOMOLOGACAO` está entre os 63 ativos.** É fixture do autocadastro de
   homologação contando como gente em toda medição de headcount desta casa. Apagar ou marcar?
5. **Comunicado por cliente alcança hoje 12 das 63 pessoas.** Se um comunicado «para o pessoal do
   Ideal Flores» foi disparado em algum momento, ele não chegou a quase ninguém. Vale conferir o
   histórico — e decidir se troco esse leitor para o resolvedor.
6. **Duas alocações discordando deveria ser impossível?** Se sim, é parede a pôr no lançamento da
   alocação (frente F5), não aqui.
