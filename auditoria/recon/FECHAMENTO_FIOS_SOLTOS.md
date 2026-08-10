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
