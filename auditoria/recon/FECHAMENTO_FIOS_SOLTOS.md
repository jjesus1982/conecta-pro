# Fechamento dos fios soltos — o que ficou e por quê (2026-08-10)

Fecha o trabalho aberto em `ESTADO_FIOS_SOLTOS.md`. Aqui está o veredito de cada uma das
**167** rotas que valiam ligar, e o motivo de cada exclusão.

## Placar

```
inventário             197 candidatas
  ├─ órfão legítimo     23   webhook do Inter, /integration/* serviço-a-serviço, rota de dev
  ├─ gated               7   dinheiro que sai / transmissão ao governo
  └─ valia ligar       167
       ├─ LIGADAS      ~120  em 16 módulos
       └─ fora          ~47  por decisão, listadas abaixo
```

## O que destravou o bloqueio de arquitetura

O renderizador de formulário só mandava JSON no corpo. Isso deixava 43 rotas de query
param e todas as de anexo inalcançáveis. Ganhou **`submit.query`** (opt-in) e depois
suporte a **multipart + query** — o arquivo no corpo, os demais campos na URL.

Os dois commits foram feitos em **índice temporário** (`GIT_INDEX_FILE` + `read-tree` +
`update-index` + `commit-tree`), porque o `ModuleView.tsx` tinha trabalho não commitado de
outra sessão: `git add` teria publicado o inacabado deles sob o meu commit. A árvore
commitada é o HEAD anterior mais as minhas linhas, e nada do WIP alheio.

## 2ª rodada (autorizada pelo Jordan) — o que fechou depois

O que travava 8 delas era o renderizador não saber mandar **lista de objetos**. Ganhou o
tipo de campo **`json`**: textarea parseado antes do envio, opt-in, com a forma esperada no
placeholder. Destravou orçamento com itens, apresentação com slides, achados da visita,
signatários, holerites em lote, colaboradores do ciclo de avaliação, verbas do S-2299 e as
listas do otimizador.

Fecharam também: orçado do mês, faturamento de contrato ativado, pagáveis das NFS-e (com
tabela **própria** lendo `nfse_entrada`, que é a que o serviço consulta — a tela antiga lê
`nfse_tomadas_nacional`, tabela diferente), as 3 de justificativa, otimizador de escala
(entra porque **sugere**, não grava), alocar diarista, importar folha do Alterdata, eSocial
S-2299 **gerando o XML sem transmitir**, solicitar assinatura e onboard por cliente.

### O que segue fora, agora com o motivo verificado

| Rota | Por quê |
|---|---|
| `banking/ted/transfer` | **Sem OTP, sem teto, sem confirmação** — li o handler: vai direto ao adaptador do Inter. Botão ali é transferência de um clique para qualquer CPF/CNPJ. Precisa do gate antes. |
| `conciliar/auto`, `bank-reconciliations/auto` | já têm botão pela ação `conciliar-auto` |
| `payables/auto-criar/{nota_id}` | mesma operação da singular, que foi ligada |
| `scales/{id}/reject` | já exposto por `escala-rejeitar` |
| `desalocar-diarista/{id}` | já exposto por `diarista-assignment-cancelar` |
| `allocations/bulk`, `shifts/bulk` | editam em massa o território curado, e a interface seria colar JSON de alocação — botão que existe para satisfazer contador, não para ser usado |
| `det/ingest-robo` | o robô empurra com token; não há humano nesse fluxo |
| `portal/auth/reset-senha`, `self-service/bater-ponto` | fluxo de login e batida com GPS + selfie: pertencem ao portal, não ao ERP |
| `notifications/register-device` | registro de aparelho do app móvel |
| `discipline/from-occurrence/{id}` | fechado por outro caminho: o formulário de nova medida passou a aceitar `occurrence_id` |

## Fora por decisão — e a decisão é reversível

**Território curado à mão (8).** `allocations/bulk`, `shifts/bulk`, `alocar`/`desalocar
diarista`, `scales/reject`, `scale-optimizer`. Alocação e escala são curadas pelo Jordan e
read-only para agentes. Botão ali é o sistema discordando dele em silêncio.

**Dinheiro que sai (2).** `banking/ted/transfer` e o que move PIX. Fluxo com OTP, fora da
tela comum. `ted/transfer` estava classificado errado na minha triagem — a regra procurava
`transferencia`, não `transfer`.

**Governo (1).** `hr/esocial/s2299/gerar` — XML de desligamento. Gerar não é transmitir,
mas S-2299 é domínio da Portte; ligar aqui arrisca evento duplicado no eSocial.

**Limite do renderizador — lista de objetos (7).** `orcamento/pdf` (itens),
`visitas/achados`, `apresentacoes/gerar` (slides), `signatures/requests` (signatários),
`payslips/importar-lote` (items), `career/milestones`, `performance/review-cycle`
(employee_ids). O formulário só tem campo escalar. Form mentiroso é pior que form ausente.

**Não deveriam ter botão (6).** `portal/auth/reset-senha` e `self-service/bater-ponto` (o
primeiro é fluxo de login, o segundo precisa de GPS e selfie), `notifications/register-device`
×2 (app móvel), `crm/assets/upload` (infra), `crm/docs/expurgar-teste` (soft-delete em massa).

**Já exposto por outro caminho (4).** `conciliar/auto` e `bank-reconciliations/auto` têm
botão pela ação `conciliar-auto`; `auto-criar-payables` e `ai/billing/contrato-ativado` são
gatilhos de integração. Ligar de novo seria rota duplicada.

**Interno (2).** `det/ingest-robo` (o robô empurra com token) e `justificativa/*` (gate
próprio do financeiro).

## Três armadilhas que custaram caro — e como pegar

**Parâmetro chamado `request`.** O extrator de contrato ignorava qualquer parâmetro com
esse nome, presumindo o `Request` do FastAPI. Em várias rotas `request` **é** o modelo
Pydantic: elas apareciam como botão seco e teriam ido ao ar dando 422 em todo clique.
Pegas duas vezes, sempre por reconferir antes de escrever.

**`coalesce` em coluna ENUM.** `coalesce(status,'—')` faz o Postgres recusar o literal, e o
`safe()` engole o erro: a aba simplesmente não monta. Três tabelas quase foram ao ar
vazias. Precisa de `::text`. É a armadilha 3 do `DIVISAO_3T` — eu conhecia e repeti.

**Script que edita código por índice de string.** Errou três vezes: tela sem entrada de
menu (invisível), indentação quebrada, e parêntese cortado no lugar errado. Nas duas
últimas o Python acusou; na primeira, só a conferência **menu × tela nos dois sentidos**
pegou. Edição à mão é mais lenta e erra menos.

## Medição final (2026-08-10, com o instrumento já consertado)

```
4.192 rotas montadas · 4.032 expostas (96%) · 46 sem tela
```

Contra **197** no início do dia. E as 46 não são fila de trabalho:

| Natureza | Qtd | |
|---|---:|---|
| máquina-a-máquina | 19 | 10 `integration/*` (DP↔operacional↔RH), 6 webhooks (Inter/Cora), robô do DET, dev, MCP |
| dinheiro / governo | 11 | PIX da folha, chave PIX, refund, propor-pagamento, `transmitir-s1000` |
| já expostas por outro caminho | 9 | conciliar, escala-rejeitar, cancelar alocação, publicar holerite |
| portal / app, não ERP | 5 | login, reset de senha, bater ponto com GPS+selfie, registro de aparelho |
| edição em massa de território curado | 2 | `allocations/bulk`, `shifts/bulk` |

**O instrumento foi consertado antes desta medição** (v2.2): comentário e docstring deixaram
de entrar no índice. Antes do conserto ele dizia 36 — bajulando quem documenta exclusão.
Provado com 4 rotas citadas só em comentário: viraram órfãs, corretamente.

⚠️ **Sobra um problema que não é fio solto:** `integrations/banking/ted/transfer` não tem
OTP, nem teto, nem confirmação — vai direto ao adaptador do Inter. Não é falta de tela, é
falta de gate. Precisa de backend antes de qualquer botão.

## Como medir de novo (e por que o número engana)

O número confiável é o dos `submit.endpoint` colhidos do `build()` **em execução**, não do
`grep` nem do balde de órfãos da recon:

- a **recon superestima**: comentário citando um path conta como cobertura;
- o **grep subestima**: não enxerga endpoint montado por f-string;
- o **contador de rotas subestima ação por linha**: ela só existe quando há linha. As duas
  rotas de intercorrência do GEDEON estão ligadas e somem do placar porque a tabela está
  vazia. O mesmo vale para as ações disciplinares condicionais ao status.

## Infra que saiu junto

O deploy ganhou **verificação de drift** no fim (falha e não imprime "CONCLUÍDO" se algum
worker ficar para trás), o lock passou a cobrir o **build** (`com_lock.sh`,
`build_backend.sh`) e a imagem do deploy passou a ser **fixada por ID** nos 9 serviços, o
que mata a corrida por tag.

A verificação se pagou no mesmo dia: o pin quebrou a descoberta dos workers
(`svcs_da_imagem_backend` casava a string exata `image: conecta-pro-backend:latest`), e o
passo 7 anunciou **"recriando 0 worker(s)"**. O hook acusou os 8 em drift e barrou o
"CONCLUÍDO" na primeira execução depois da regressão.
