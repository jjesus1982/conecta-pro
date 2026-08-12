# Financeiro — auditoria e fechamento parcial · 12/08/2026 (T1)

**Veredito curto:** a **cadeia do caixa** fechou e agora tem oráculo. O **módulo não**.
São coisas diferentes e misturá-las seria mentira: em `serviços` o contrato fechou e o
produto continuou casca.

---

## Números antes → depois

| | antes | depois |
|---|---|---|
| razão × extrato | não conferido | **Δ R$0,00**, com oráculo |
| oráculos do financeiro | 0 | **1** (`test_oraculo_extrato`) |
| âncoras externas no financeiro | 0 | **1** (contas a pagar ← NFS-e tomada) |
| vocabulário fantasma (financial) | 5 ocorrências | **0** |
| duplicata real no extrato | 1 (criada por mim ontem) | 0 |
| travas — regressão | — | **sem regressão** nas 8 |

Travas, medido antes de tocar em nada: `checar_repositorio` 61 (financial 19),
`checar_rotas_frontend` 657 (financeiro 2), `cacar_fabricacao` 27, `checar_vocabulario` 20,
`checar_oraculo_externo` 1.

---

## DADO

**Extrato ↔ razão ↔ banco fecha.** Razão contas 1.1.1.x = extrato, Δ R$0,00. E o extrato do
Inter foi confrontado com o saldo que o **próprio banco** informa para 10/08
(`/banking/v2/saldo?dataSaldo=`): R$9.875,35 dos dois lados.

🔴 **O oráculo me pegou apagando uma transação legítima.** Eu tinha "adjudicado" três grupos
suspeitos consultando o extrato do Inter **por nome na descrição**; o filtro não contou o par
da Loide (07/08, R$32,00) e eu apaguei uma linha real. A checagem contra o saldo do banco
acusou a diferença **exata de R$32,00**. Restaurada. O banco tem dois pagamentos de R$32 para
a mesma pessoa naquele dia — gêmeo legítimo, como Sólides 17/06 e Alan 09/08.

Isto é o achado mais importante do dia: **a mesma lição que eu escrevi ontem me pegou hoje**.
Filtro por texto não é contagem; quem conta é o banco.

**NÃO COBERTO:** o Cora não tem saldo histórico na API (só o Inter tem `dataSaldo`), então o
extrato dele não tem confronto externo — R$7.175,36 sem quem confirme.

## CÓDIGO

**Oráculo do extrato** (`backend/scripts/orq/test_oraculo_extrato.py`), provado em vermelho
nos 4 caminhos. Provar em vermelho pagou três vezes:

1. o INSERT duplicado foi **recusado**: já existe `idx_bank_tx_external_id` UNIQUE;
2. o UPDATE de sinal foi **recusado**: já existe `ck_bank_tx_sinal_coerente`;
   → os dois invariantes que eu ia afirmar eram **decoração**. Viraram outra coisa: o oráculo
   agora afirma que a **garantia continua de pé**. Constraint some em migration distraída e
   o defeito volta calado.
3. a checagem contra o banco pegou o meu erro (acima).

A chave de duplicata inclui o **favorecido** de propósito: sem ele, 21 pagamentos de R$32,00
do mesmo dia para pessoas **diferentes** viram falso positivo só por terem sido importados
metade por uma fonte, metade por outra. Alcance declarado: 9% das linhas têm favorecido.

**Vocabulário fantasma corrigido** — `status='aprovado'` em `pagamentos_diaristas_service`:
a coluna só tem `a_revisar/sem_pix/pago/cancelado` e `aprovado` nunca é escrito. A trava
apontou 1; a **família eram 5** (2 filtros SQL, 2 filtros Python, comentário do schema,
docstring).

## TELA

**As 6 rotas 404 de pagamento não existem.** A trava deu pista, o HTTP deu prova:

| chamada | HTTP real |
|---|---|
| `/api/v1/banking/payment/barcode` | **405** (existe, é POST) |
| `/api/v1/integrations/banking/pix/generate` | **405** (existe, é POST) |
| `/api/v1/integrations/banking/boleto/generate` | **200** |

19 rotas de banking estão montadas. `/modulos/financeiro/inter`, `pagamentos-diaristas` e
`pagamentos-pj` são **páginas do frontend**, não API — nunca foram 404 de rota.

**Os 3 arquivos órfãos: mapeados, não tocados.** Os 7 endpoints que eles chamam devolvem
**200** — o backend está completo para essas telas. Não editei, não commitei, não descartei.

---

## Dinheiro que sai — com as palavras certas

> **O Cora não oferece PIX de saída na API.** Nem por chave, nem copia-e-cola. Só TED por
> dados bancários completos, e a TED sai como `INITIATED` para aprovar no app. E **89% do
> dinheiro sai pelo Cora** (R$136.426,78 de R$153.259 em agosto).
>
> Portanto "pagar tudo pelo sistema" alcança **11%** hoje — e isso é **limite da API do
> banco, não defeito nosso**. O Inter transmite de verdade: 26 pagamentos confirmados,
> R$35.813,99, entre 03/07 e 11/08.

**Não exercitei nenhum fluxo de pagamento.** Verificação foi por leitura de código e registro
no banco. **NÃO VERIFICADO:** se o gate de OTP cobre todos os caminhos — não auditei, e
declarar "passou" sem evidência seria pior que declarar não verificado.

---

## Âncoras externas — a pergunta que o `--listar` provoca

**Acrescentei 1** (nenhuma existente tocada): `contas a pagar ← NFS-e tomada`, prefeitura do
**fornecedor**. Distinta da âncora `notas fiscais de serviço`, que lê as **emitidas** (nossa
receita); esta lê o documento que **lastreia um pagável**. 303 notas, cadência mensal estável
(24/24/27/28) — a fonte avança sozinha. Validade 45d.

### O que deveria estar na lista e NÃO está

Isto é achado, não lacuna a preencher. Em nenhum destes existe fonte externa que fale
sozinha, e inventar âncora seria fabricar:

| número | por que não tem âncora |
|---|---|
| **transitória R$384.580,79** | ninguém de fora sabe o que é. É exatamente por isso que ela infla o prejuízo em silêncio — e é o mais grave da lista |
| **resultado / DRE** | só o fechamento da Portte confirmaria, e não temos ingestão dele por competência. **Enquanto isso, qualquer DRE é ficção plausível** — e passa em todos os portões |
| **saldo de abertura no corte** | provei o do **caixa** (R$18.663,83, dois caminhos independentes), mas é prova de **uma vez**: a data não avança sozinha, então virar âncora seria alarme condenado a ficar vermelho (o erro das certidões) |
| **passivos de abertura** | **nenhum**. A empresa devia R$12.000 à Denise em 31/07 e o razão não sabe — a conta 2.1.6.01 está com saldo **devedor** de R$12.300 |
| **nota fiscal dos 9 PJ** | zero notas numa base de 135. Âncora aqui nasceria vermelha e ficaria — está no alarme `pj_sem_nota_fiscal`, que é o lugar certo |

### Sobre as âncoras existentes
Conferi as sete e **não encontrei erro**. A observação do eSocial (35 dias, beat às 09:10)
confere com o dado e é de governo — fora da minha frente.

---

## NÃO COBERTO (e por quê)

1. **`costing_controller.py` — 19 chamadas a método inexistente, 1.085 linhas.** Não é
   renomeação: o controller inteiro foi escrito contra uma interface CRUD genérica
   (`get_multi`, `get`, `soft_delete`, `get_statistics`) que **nunca existiu** — os
   repositórios reais têm `list_all`, `get_by_id`, `delete`, `get_stats`. E `create`/`update`
   existem pelo nome mas recebem **modelo, não schema**: é o segundo olho da trava.
   **As 50 rotas dele não são alcançáveis** — provado por HTTP: `/api/v1/financial/costing/*`
   → **404**. `financial_router` não é montado pelo `main_production`.
   **Por que parei:** consertar ou apagar 1.085 linhas inalcançáveis é decisão com
   consequência (o trabalho é de alguém), e a resposta muda o que eu faria. É a única
   pergunta que deixei aberta.
2. **Cora sem confronto externo** — a API não tem saldo histórico.
3. **Gate de OTP** — não auditado (ver acima).
4. **Grupo 3.x / PL** — as contas estão corrompidas (`3.1.1 Portaria`, `3.1.2 Vigilância`
   dentro de *Capital Social*; `3.2.1 ISS 5%` dentro de *Lucros Acumulados*) e não há
   lançamento nenhum em 3.x. Refazer é do meu escopo, mas **altera número que o Jordan lê** e
   a nomenclatura é decisão dele. Não mexi.

---

## Dois falsos positivos das travas (para o Arsenal)

Ambos da **mesma raiz**: a trava liga a coluna à tabela errada quando o SQL é fragmento ou
quando a função tem mais de uma query.

1. `checar_vocabulario` → `classificacao_saidas_service.py:178,180` [CRITICO]:
   leu `c.status NOT IN ('pj_ativo','pj_pendente')` como `bank_transactions.status`. O alias
   `c` é de **employees** — o SQL é montado pelo helper `_casa_nome()` e ela só vê o pedaço.
2. `checar_vocabulario` → `financial_dashboard_controller.py:92` [CRITICO]:
   a query é sobre **`payable_accounts`** (que tem `pago`), não `bank_transactions`. A query
   anterior na mesma função é que era de `bank_transactions`.

Sugestão: quando o texto SQL não contiver um `FROM` resolvível, marcar como **indeterminado**
em vez de CRITICO. Falso positivo em CRITICO gasta a confiança que a trava precisa ter.

---

## Fora do financeiro, mas encontrado e consertado

**O script de deploy estava quebrado desde 10/08.** A fixação por ID passava `sha256:abc…`
ao compose, que lia como **nome de repositório** e tentava baixar
(`pull access denied for sha256`). O passo 7 falhava em quase todos os workers e eles seguiam
com **código antigo** — o oposto do que a fixação existe para evitar. Dois deploys hoje
deixaram 5 workers para trás, incluindo o **celery-beat**: nenhum beat novo estava valendo.
Corrigido (hex sem prefixo), provado, e os 8 workers voltaram sem drift.

---

## Três portões — onde cada entrega parou

| entrega | servido após bake | oráculo que pega | vigia |
|---|---|---|---|
| oráculo do extrato | ✅ | ✅ provado em vermelho ×4 | varredura 00:00 |
| âncora contas a pagar | ✅ | ✅ (a própria trava) | varredura 00:00 |
| vocabulário dos diaristas | ✅ | ✅ `checar_vocabulario` | regressão |
| trigger do período fechado | ✅ (verificado por T2) | ✅ 3 casos | banco |

**ENTREGUE.** O que ficou de fora está na seção NÃO COBERTO, com o motivo.

---

# Adendo — ataque à transitória (mesmo dia)

## O achado que mudou a estratégia

**97% da transitória está no período FECHADO:** R$308.149,66 de jan–jul contra R$9.157,43
em agosto. Reclassificar 637 lançamentos de um período que o Jordan decidiu fechar seria
exatamente a arqueologia que combinamos não fazer.

**E o "prejuízo" tem outra causa, não a transitória.** No período aberto a receita é
**R$0,00** — porque receita se reconhece quando a NFS-e é emitida (dia 2 a 31 do mês) e a
folha sai no dia 7. Em 12/08 o DRE do mês em curso mostra −R$152.005,25 e isso é
**artefato de competência, não defeito**: os R$160.284,29 que entraram em agosto são
recebimento de notas de JULHO, cuja receita já foi reconhecida lá.

⭐ **Consequência prática: DRE de mês em curso não significa nada.** Só competência fechada.

## O que foi feito (período aberto)

| | antes | depois |
|---|---|---|
| transitória do mês | R$9.157,43 | **R$7.348,67** (5% da despesa) |
| classificação das saídas | 83,6% | **85,8%** |

Dois defeitos de normalização corrigidos, ambos de **família**:

1. **Acento.** O cadastro tem `ANGELA LOPES MACEDO`, o banco `Ângela Lopes Macêdo`. O
   normalizador aplicava `[^A-Z0-9 ]` **antes** de `unaccent`, virando `" NGELA LOPES MAC DO"`
   — e o outro lado procurava `ANGELA`/`MACEDO`. **Todo funcionário com acento no nome
   escapava.** (Errei a ordem uma vez, pondo `unaccent` por fora do `regexp`: o `Â` já tinha
   sido removido junto com a letra.)
2. **`" SA"` dentro de palavra.** Casava em `" SANTOS"` — Gabriel Santos Machado e mais 4
   pessoas viraram "Fornecedor — razão social de empresa". Mesmo defeito do `ISS` dentro de
   `COMISSAO`. Sufixo curto foi para `_EMPRESA_SUFIXO`, testado só no fim do nome.

## O que resta na transitória do mês — R$7.348,67

**Precisa do Jordan (R$5.725,00 — 78% do que sobrou):**

| valor | quem | memo |
|---|---|---|
| R$1.725,00 | Eric de Souza Cardoso | "Parcela 2/4 TVs" |
| R$1.700,00 | Railton da Costa Rodrigues | "Aluguel escritório" |
| R$1.500,00 | CICERO SOUZA DE PAIVA | (sem memo) |
| R$1.000,00 | GABRIEL SANTOS MACHADO | "Comissão Vanessa" |
| R$500,00 | Raimundo Almeida Trindade | (sem memo, 2×) |
| R$300,00 | — | (dentro dos R$500 acima) |
| R$200,00 | BRUNO FRANCISCO | "Emprestimo Bruno" |

Três deles pedem **categoria nova** na lista fechada — aluguel, comissão e parcelamento de
equipamento não existem hoje, e por isso caem na transitória mesmo com memo claro.

**Miudezas de fornecedor (R$1.623,67):** JK HORT FRUT (7×), Yasmin (8×), RC Conveniência,
Manaus Farma, AT E SM Veneza. Nenhuma casa com `_EMPRESA` porque são nomes de comércio
pequeno. **Não adicionei tokens**: cada token novo é risco de falso positivo, e a lição de
hoje (`" SA"` dentro de `" SANTOS"`) foi cara.

## Quarentena do `costing_controller`

Movido por decisão do Jordan. Verificado: app importa, **4.197 rotas inalteradas**,
`/api/v1/financial` **592 inalterado**, modelos ABC importáveis.
`checar_repositorio`: **financial 19 → 0**, TOTAL 61 → 42.

⚠️ Meus números de referência divergem dos do Arsenal (3.338 / 493). Não investiguei —
provavelmente rota×método vs caminho único. Usei o invariante **"não muda"**, não o
absoluto.
