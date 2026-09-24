# DGX F5 — Movimentações: alocar/remover de vaga com motivo tipado (24/09/2026)

**Branch:** `dgx/f5-movimentacoes` · **Módulo:** operacional · **Sandbox:** `conecta_pro_staging`, container `teste-dgx-f5` (8205, parado ao fim)

## 1. Estado antes (medido no staging, 23/09 23:30 Manaus)

- `employee_alocacoes`: **73 linhas, 8 colunas** (`employee_id, condominio_id, funcao, data_inicio, data_fim, ativo, created_at`), 51 ativas, 0 duplicadas.
  Sem motivo, sem quem pediu, sem origem/destino, sem aprovação. **Nenhum caminho do app escrevia nela** — só seed e importação
  (`scripts/qa/checar_alocacao_de_quem_saiu.py` documenta; a tela `alocacoes` do Operacional é só leitura, CTA "Nova alocação" sem ação).
- `allocations` (89 linhas, employee × post, `AllocationRepository`, `/allocations`) é **outra tabela**, do universo `posts`; não é a que o
  kit do GEDEON (`kit_builder_service`), o Hermes, a categorização do Inter, o "Sem alocação" do DP e o `financeiro.py` leem. Eles leem
  `employee_alocacoes`. Por isso a regra de duplicidade do repository **não se reaproveita** (tabela e chave diferentes).
- `posts.client_id` não aponta para `condominios.id` (0 de 15 casam) — o elo é `posts.client_id = condominios.client_id` (10 postos em 9 condomínios).
- Férias/afastamento vivos: `hr_vacation_requests` (APPROVED) e `sst_afastamentos` (ativo/em_andamento) — as mesmas fontes de `coorte_ponto.SQL_NAO_AUSENTE_HOJE`.
- Oráculo no nascimento: **VERMELHO** (2 falhas) — `(a) coluna tipo/motivo não existe: ProgrammingError` e `(c/d) serviço não importa: ImportError`.
  `(b)` 0 duplicadas e `(e)` 27 = 27 já eram verdes.

## 2. O que o DGX tem

`/Movimentacoes/IncluirMovimentacao` (23 campos): seção **Origem** (data, colaborador, admissão, cargo, cliente alocado, vaga, turno — tudo
preenchido automaticamente) e **Destino** (`TipoMovimentacao` = ALOCAR COLABORADOR EM NOVA VAGA · REMOVER O COLABORADOR DA VAGA ATUAL;
`Motivo` = A PEDIDO DO CLIENTE · A PEDIDO DO SUPERVISOR · ALOCAÇÃO DE VAGA · COBERTURA DE AFASTAMENTO · COBERTURA DE FALTA · COBERTURA DE
FÉRIAS · TREINAMENTO; contrato, vaga, sequência, observações). A movimentação alimenta o `GridPlanejamento`.

## 3. O que foi feito

| Arquivo | Papel |
|---|---|
| `backend/modules/operacional/services/movimentacao_service.py` | regra: `alocar()`, `remover()`, `_ensure()` (DDL), `MOTIVOS` (7), `SOLICITANTES`, `MovimentacaoErro(status)` |
| `backend/modules/operacional/controllers/redesign_builders/_dgx_f5_movimentacoes.py` | 3 telas + 2 ações (`router`) |
| `backend/modules/operacional/controllers/redesign_builders/operacional.py` | plug: import do `router` (1 linha) + `include_router` (1) + `await _telas_f5(db, out)` antes de `montar_grupos` (2) — `# dgx f5` |
| `backend/modules/operacional/controllers/redesign_builders/_op_grupos.py` | 3 abas no grupo **Escalas & Turnos** (`g-escalas`), ao lado de "Alocações" |
| `backend/scripts/orq/test_oraculo_movimentacao_com_motivo.py` | oráculo (a–e) |

**DDL que `_ensure` aplica em produção no 1º acesso** (idempotente; roda em `telas()` e em cada ação):
```sql
ALTER TABLE employee_alocacoes ADD COLUMN IF NOT EXISTS tipo varchar(10);              -- alocar | remover
ALTER TABLE employee_alocacoes ADD COLUMN IF NOT EXISTS motivo varchar(40);            -- 7 do DGX em snake_case
ALTER TABLE employee_alocacoes ADD COLUMN IF NOT EXISTS motivo_encerramento varchar(40);
ALTER TABLE employee_alocacoes ADD COLUMN IF NOT EXISTS posto_id uuid;                 -- posts.id (posto dentro do condomínio)
ALTER TABLE employee_alocacoes ADD COLUMN IF NOT EXISTS alocacao_origem_id uuid;       -- a alocação que esta encerrou
ALTER TABLE employee_alocacoes ADD COLUMN IF NOT EXISTS solicitado_por varchar(20);    -- cliente | supervisor | dp | sistema
ALTER TABLE employee_alocacoes ADD COLUMN IF NOT EXISTS solicitante_nome varchar(120);
ALTER TABLE employee_alocacoes ADD COLUMN IF NOT EXISTS aprovado_por uuid;
ALTER TABLE employee_alocacoes ADD COLUMN IF NOT EXISTS aprovado_em timestamp;         -- hora de Manaus
ALTER TABLE employee_alocacoes ADD COLUMN IF NOT EXISTS observacao text;
ALTER TABLE employee_alocacoes ADD COLUMN IF NOT EXISTS coberto_employee_id uuid;
ALTER TABLE employee_alocacoes ADD COLUMN IF NOT EXISTS created_by uuid;
UPDATE employee_alocacoes SET tipo='alocar', motivo='alocacao_de_vaga',
       observacao=coalesce(observacao,'retroativo: migrado em 24/09/2026 sem motivo declarado')
 WHERE tipo IS NULL AND motivo IS NULL;   -- só colunas novas nulas; as 8 antigas não mudam
```
Medido no sandbox após o 1º GET: 20 colunas, 73 retroativas, 0 ativas sem tipo.

**Regras do serviço** (`alocar`): função em maiúsculas; motivo ∈ 7; `data_inicio ≤ hoje + 60 dias` (422); cobertura de férias/afastamento
exige `coberto_employee_id` **e** o coberto com férias APROVADAS (`hr_vacation_requests`) / afastamento ativo (`sst_afastamentos`) na
data (422); posto tem que pertencer ao condomínio (422); alocação ativa igual (mesmo condomínio + função + posto) → 409; alocação ativa que
começa na data ou depois → 409; senão **encerra toda ativa anterior do colaborador em `data_inicio − 1`** e grava `alocacao_origem_id` =
a mais recente. Publica `alocacao_criada` (mesmo evento do `/allocations`). `remover`: 404/409/422 (já encerrada, fim antes do início),
`ativo=false, data_fim, tipo='remover', motivo_encerramento`, observação concatenada.

**Decisão de modelo — uma linha = uma alocação (estado), não um evento.** Remover NÃO insere linha: `financeiro.py` soma
`hr_payslips × employee_alocacoes` por competência sem filtrar `ativo`; uma linha-evento de remoção duplicaria a folha da pessoa naquele
mês. Por isso existe `motivo_encerramento` (1 coluna além do brief) e a tela pinta a remoção como segunda linha a partir da mesma alocação.

**Telas** (grupo Escalas & Turnos):
- `/redesign/operacional?t=movimentacoes` — ledger: Data · Tipo (Alocar/Remover) · Colaborador · De → Para (condomínio · posto · função) ·
  Motivo · Coberto · Solicitado por (nome) · Aprovado (quem · quando) · Situação. Filtros **Mês** e **Condomínio**; busca. Linha ativa tem
  ação **Encerrar** (último dia, motivo, observação). 73 linhas hoje, 51 ativas.
- `/redesign/operacional?t=movimentacao-nova` — form: colaborador (ativos, sem homologação), tipo, data, condomínio, posto (opcional,
  "Condomínio · Posto"), função (distintas da tabela ∪ cargos ativos), motivo, coberto, solicitado por, nome de quem pediu, observação;
  `confirm` + `showResult`. Tipo **remover** encerra a alocação ativa do colaborador na data (404 se não houver).
- `/redesign/operacional?t=movimentacao-encerrar` — form: alocação ativa (select), último dia, motivo, observação.
- Ações: `POST /api/v1/redesign/action/movimentacao-alocar` · `POST /api/v1/redesign/action/movimentacao-remover[?alocacao_id=]`.

**Nada quebrou onde já se lia a tabela:** `sem-escala` do DP ("Ativos sem alocação em posto", 2 linhas, sem FALHOU), `alocacoes` do
Operacional, `grid-real-contratual`/`mapa-de-ponto` (oráculo da frente 04 verde: "régua hoje: 27 turno(s) · mapa: 27 · OK grade/mapa").

**HTTP no container efêmero (8205), fixture ALAN VIEIRA (ativo, sem alocação), apagada ao fim (73 linhas antes e depois):**
```
1. alocar: 200 Alocado (não havia alocação anterior).
2. alocar igual: 409 Já existe alocação ativa igual (desde 23/09/2026).
3. cobertura sem coberto: 422 Cobertura de férias exige informar QUEM está sendo coberto.
4. > 60 dias: 422 Data de início mais de 60 dias no futuro (01/01/2030).
5. alocar por cima, mesma data: 409 Há alocação ativa que começa em 23/09/2026; a nova precisa começar depois.
6. alocar por cima amanhã: 200 Alocado. 1 alocação(ões) anterior(es) encerrada(s) no dia anterior.
7. remover (ação da linha): 200 Alocação encerrada em 25/09/2026.
8. remover de novo: 409 Essa alocação já está encerrada.
9. form nova com tipo=remover sem ativa: 404 Esse colaborador não tem alocação ativa para remover.
   posto de outro condomínio: 422 O posto informado não pertence a esse condomínio.
   tela: 25/09 Remover · GREEN HILLS · AGENTE DE PORTARIA → (sem vaga) · A pedido do supervisor · Jordan Jesus · 23/09/2026
         24/09 Alocar  · ESCRITÓRIO · AGENTE DE PORTARIA → GREEN HILLS · AGENTE DE PORTARIA · A pedido do cliente · Cliente (teste)
         23/09 Alocar  · — → ESCRITÓRIO · AGENTE DE PORTARIA · Alocação de vaga · Supervisor (teste) · encerrada 23/09/2026
```

## 4. Oráculo

```bash
WT=$(git rev-parse --show-toplevel)
ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\n' ' ')
docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 \
  --env-file /opt/conecta-pro/.env $ENVS conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_movimentacao_com_motivo.py
# em produção: docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_oraculo_movimentacao_com_motivo.py
```
ANTES (23/09 23:33):
```
  ✗ (a) coluna tipo/motivo não existe: ProgrammingError
  ✓ (b) colaboradores com 2 alocações ativas no mesmo condomínio+função: 0
  ✗ (c/d) serviço movimentacao_service não importa: ImportError: cannot import name 'movimentacao_service' ...
  ✓ (e) turnos de hoje 27 × com alocação ativa no condomínio do posto 27
TOTAL falhas movimentação com motivo: 2
```
DEPOIS (24/09 00:05):
```
  ✓ (a) alocações ativas sem tipo/motivo: 0
  ✓ (b) colaboradores com 2 alocações ativas no mesmo condomínio+função: 0
  ✓ (c) anterior encerrada no dia anterior: ativo=False data_fim=2026-09-22 (esperado 2026-09-22)
  ✓ (c) nova ativa e ligada à origem: ativo=True origem=5f538c66-...
  ✓ (c) alocação igual repetida recusada com 409: Já existe alocação ativa igual (desde 23/09/2026).
  ✓ (c) recontagem de duplicadas com a fixture no banco: 0
  ✓ (d) cobertura_de_ferias sem coberto recusada com 422 ...
  ✓ (d) cobertura_de_afastamento sem coberto recusada com 422 ...
  ✓ (d) coberto sem férias na data recusado com 422: O coberto não tem férias aprovadas em 23/09/2026.
  ✓ (c/d) fixture apagada ao fim: 0 sobrando
  ✓ (e) turnos de hoje 27 × com alocação ativa no condomínio do posto 27
TOTAL falhas movimentação com motivo: 0
```
Frente 04 (`test_oraculo_grid_bate_com_a_triagem.py`) rodado depois: exit 0, "OK grade/mapa".

## 5. O que NÃO foi feito e por quê

- **Grid de planejamento próprio** — não. O `grid-real-contratual` (frente 04) já é o grid por posto × dia; a movimentação alimenta o
  que ele já lê (`shifts` × alocação). O oráculo (e) é o elo: quem tem turno hoje tem alocação ativa no condomínio do posto (27 = 27).
- **Baixa automática na demissão** — não (fora do brief). `checar_alocacao_de_quem_saiu` continua sendo o instrumento; agora existe o
  botão Encerrar para o DP fechar a mão. Hoje há 1 demitido, 1 afastado INSS e 1 suspenso com alocação ativa (medido antes; não toquei).
- **`AllocationRepository` / `allocations`** — não reusado nem alterado: tabela paralela do universo `posts`, sem chave comum. Registrado
  em §1; a decisão de unificar as duas é do dono (§7).
- **Cobertura de falta** não exige coberto (o DGX também não); `coberto_employee_id` fica opcional para esse motivo.
- **Vaga como entidade** (`idModeloVaga`, `idSequencia`, `idContrato` do DGX) — não. Aqui a "vaga" é condomínio + posto + função; sem
  tabela de vagas por posto/turno não há o que selecionar. `posts.required_headcount` existe mas não é por função/turno.
- **Frontend** — nada editado; `table`/`form`/`filtros`/`actions` renderizam genericamente. Sem JSON de menu novo (as abas vêm de `_op_grupos`).
- **`checar_regressao.py`** — não registrado (é do orquestrador): oráculo órfão com dono até lá.
- **Cache** do builder da frente 04 (60 s) não foi tocado; uma movimentação feita agora aparece no grid em até 1 min.

## 6. Como o Jordan testa amanhã

1. Operacional → **Escalas & Turnos** → aba **Movimentações**: 73 linhas, filtre por Mês (ex.: 07/2026) e por Condomínio; as 73 antigas
   mostram motivo "Alocação de vaga" e, no Ver, a observação "retroativo…".
2. Aba **Nova movimentação**: escolha um colaborador que já está alocado, tipo *Alocar*, outro condomínio, data amanhã, motivo *A pedido do
   cliente*, solicitado por *Cliente* + nome do síndico → Confirmar. Volte em Movimentações: a nova aparece ativa, a antiga "encerrada"
   com data = ontem da nova, e a coluna De → Para mostra a troca.
3. Na linha ativa, **Encerrar** → último dia hoje, motivo *Treinamento* → a linha vira duas (Alocar + Remover) e a pessoa cai em
   DP → Visão → "Ativos sem alocação em posto".
4. Tente *Cobertura de férias* sem escolher o coberto → recusa com a mensagem; escolha alguém que NÃO está de férias → recusa também.
5. Tente data 3 meses à frente → recusa (60 dias).

## 7. Decisões que só o dono pode tomar

- **Unificar `allocations` (employee × post, 89) com `employee_alocacoes` (employee × condomínio, 73)?** Hoje são duas verdades; a
  nova coluna `posto_id` é a ponte para migrar a primeira para dentro da segunda e aposentar `/allocations`.
- **Os 3 com alocação ativa que não deviam** (1 demitido, 1 afastado INSS, 1 suspenso): encerrar pelo botão com que motivo/data? Suspenso
  volta ao mesmo posto (o caçador exclui de propósito).
- **Quem pode movimentar**: hoje qualquer usuário autenticado do redesign (mesmo gate das outras frentes). Restringir a DP/supervisão?
- **Aprovação em dois passos** (pedido do supervisor → aprova o DP): a tabela já tem `aprovado_por/aprovado_em`; hoje quem registra aprova.
