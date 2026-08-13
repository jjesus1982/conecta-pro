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

---

# Adendo 2 — PL, apuração e DRE (13/08, autonomia total)

## O maior achado: o DRE lia um plano de contas que não existe mais

`_dre_simplificado` foi escrito para um plano antigo onde `4.1.1` era *pessoal*. No plano
atual **4.x é RECEITA e 5.x é DESPESA**. Julho aparecia com:

```
(−) Custos dos Serviços Prestados   R$ -378.286,98
```

…que é **exatamente a receita do mês**. Era o "DRE é ficção plausível" com nome e sobrenome
— e passava em todos os portões porque nenhum número era absurdo à primeira vista.

Reescrito sobre o razão. Agora bate com a apuração por **dois caminhos independentes**:

| competência | DRE | resultado levado ao PL |
|---|---|---|
| 2026-06 | −R$157.402,16 | −R$157.402,16 |
| 2026-07 | **+R$122.303,07** | +R$122.303,07 |

Também saíram duas fabricações: a **estimativa de receita por MRR** quando não havia NFS-e
(mês sem nota tem receita zero, e é isso que se diz), e o **IR sobre prejuízo** (a fórmula
aplicava o adicional de 10% sobre `ebitda − 20.000` mesmo com EBITDA negativo).

⭐ **Julho deu LUCRO de R$122.303,07.** O "prejuízo de R$242 mil" era o acumulado
contaminado pelo período arqueológico.

## PL: de zero lançamentos a balanço que fecha

| | antes | depois |
|---|---|---|
| lançamentos no grupo 3.x | **0** | 110 contas encerradas, 42 competências |
| balanço patrimonial | **501 honesto** | fecha, `dif R$0,00` |
| competências encerradas | 0 | todas as fechadas |

```
ATIVO              R$  27.629,39
PASSIVO            R$ 266.894,30
PL                 R$ -200.904,64
resultado em curso R$ -38.360,27
A − (P+PL+R) = R$ 0,00
```

O PL **não é derivado por diferença** — isso seria inventar. É escriturado: cada competência
encerra 4.x e 5.x contra `3.2.1.01`, via a conta de passagem `3.3.1.01`, que volta a zero.

O que continua **não sabido vem declarado** (`pl_completo: false`): capital social e lucros
acumulados até 31/12/2025 só existem no balanço do contador. A contrapartida já tem lugar
reservado — `3.9.9.01 Saldo de Abertura a Identificar`.

**Grupo 3 refeito.** `3.1.1 Portaria`, `3.1.2 Vigilância`, `3.1.3 Limpeza` e `3.2.1 ISS 5%`
estavam dentro do PL. ⚠️ **Desativei em vez de apagar**: a primeira versão fazia DELETE
conferindo `accounting_entries` e quebrou na FK `fk_line_account` — as contas são
referenciadas por `fin_journal_entry_lines`, o **outro** razão. Conferir um razão e apagar
com base nele é como se perde história em base com duas escrituras.

**Beat mensal** (dia 5, 09:00) encerra a competência anterior e **falha se a conta de
passagem não zerar** — apuração pela metade faz o balanço fechar mentindo.

## Transitória — resultado do ataque

| | início | fim |
|---|---|---|
| transitória do período aberto | R$9.157,43 | **R$2.923,67** (2% da despesa) |
| classificação das saídas | 83,6% | **87,4%** |

Três categorias criadas a pedido do Jordan: `aluguel` (5.2.1.03, já existia),
`comissao` (5.2.1.05, nova) e `equipamento` (**1.2.1.01, ATIVO**). "Parcelamento" não virou
categoria: é forma de pagamento, não natureza, e colidiria com `Parcelamento Simples`, que é
tributo. Criado o grupo 1.2 (imobilizado), que não existia.
⚠️ 1.2.1.01 **nasce sem depreciação** — dívida declarada, vai junto com a política contábil.

Dois bugs de normalização, ambos de família: **acento** (`Ângela` virava `" NGELA"` e todo
funcionário com acento escapava) e **`" SA"` dentro de `" SANTOS"`** (5 pessoas viraram
"fornecedor — razão social de empresa").

## Oráculos do financeiro: 0 → 2

`test_oraculo_extrato` (4 invariantes) e `test_oraculo_balanco` (5). Ambos provados em
vermelho. O do balanço nasceu com **42 falsos positivos** no invariante (c): a fórmula só
olhava `conta_debito LIKE '5%'` e não via o encerramento, que **credita** 5.x.

---

# Adendo 3 — o oráculo do extrato pegou dois erros que se cancelavam

O `test_oraculo_balanco` fica verde, mas o do extrato **falhou** na verificação final:
R$96,00 contra o saldo do próprio Inter em 11/08. Perseguir isso rendeu o achado mais
instrutivo do dia.

## Dois erros opostos, somando zero

Em 12/08 eu quase apaguei uma linha da Loide (07/08, R$32) achando que era duplicata; o
confronto com o saldo do banco disse que eu estava errado e eu **restaurei**. Estava errado
de novo — mas por sorte: eu **também** estava sem a linha do Thiago do mesmo dia e mesmo
valor. **Os dois erros se cancelavam**, e o saldo batia por compensação.

Inseridas as 4 linhas que o banco tinha e nós não, a duplicata apareceu sozinha e o saldo
fechou: **R$5.416,69 dos dois lados**.

⭐ **Saldo que bate não prova que as linhas estão certas** — prova que a SOMA está certa.
Só o confronto linha a linha (multiset por data+valor+descrição) separa os dois.

## 🔴 NÃO COBERTO — a constraint descarta gêmeo legítimo

Causa raiz das 3 linhas faltantes de 11/08: `uq_inter_transactions_dedup` é UNIQUE em
(data, tipo, valor, descrição). Dois PIX de R$32,00 para a **mesma pessoa** no **mesmo dia**
são indistinguíveis nessa chave, e o `ON CONFLICT` descarta o segundo **em silêncio**.

Não dá para usar o id do banco: `raw_payload->>'transaction_id'` está preenchido em 2.771
linhas com **um único valor distinto** (vazio) — o extrato do Inter não devolve `idTransacao`.

**Tentei trocar por dedup de contagem e REVERTI.** A implementação duplicou 49 linhas em
`inter_transactions` e 52 em `bank_transactions` antes de eu perceber. Revertido tudo
(migration, código e dados; backups `backup_intertx_dup_20260813` e
`backup_ponte_dup_20260813`), constraint restaurada, e as 4 linhas faltantes inseridas
manualmente contra o extrato do banco.

Fica como dívida **declarada**: o mecanismo certo é contagem, mas exige a ponte
`inter_transactions → bank_transactions` ser idempotente sob contagem também — e a minha
não era. Consertar as duas juntas, com teste, não no meio de uma verificação final.

⭐ A lição: **eu troquei um defeito conhecido e medido (R$96) por um risco maior** (duplicação
em massa) sem teste antes. O oráculo pegou, mas foi o oráculo, não eu.

---

# Adendo 4 — junho e julho não eram duplicata, eram um mês só

O Jordan viu o painel e disse: *"no faturamento de julho de 2026 está com R$378.286,98
acho que está errado... uma diferença de mais de 100 mil de junho para julho, não é
verdade."* Estava certo, e minha primeira leitura estava errada.

**O que eu concluí primeiro (errado).** Achei dois pares tomador+valor entre os dois CNPJs
e li como dupla emissão na transição. O Jordan confirmou que as notas da Eletrônica estavam
em cancelamento, e eu marquei `cancelada=TRUE` em n109 e n111. Julho caiu para
R$269.900,06 — mas junho ficou em R$163.529,67, ainda 100 mil abaixo. **O degrau não sumiu,
mudou de mês.** Isso já era o sinal de que a explicação estava errada: uma duplicata some,
não muda de lugar.

**O que o Jordan corrigiu.** *"em junho, as notas do Laranjeiras e Ideal saíram pela
Eletrônica, e julho deveria ter saído apenas pela Patrimonial. Não caiu para 169k, manteve
na mesma média dos meses anteriores."*

**A prova, no feed do ADN.** Puxei a distribuição dos dois CNPJs em leitura pura. O feed da
Eletrônica **não tem nenhuma nota do Laranjeiras ou do Ideal Flores em junho** — n96 a n107
cobrem 01/06 a 30/06 e nenhum dos dois aparece. As primeiras desde maio são n109 (09/07) e
n111 (14/07). São o faturamento de JUNHO, emitido com atraso. Julho saiu pela Patrimonial,
n13 e n21. Reverti o `cancelada` das duas: o ADN diz que estão vivas, e estão.

A aritmética fecha sozinha:

| competência | notas | faturamento |
|---|---|---|
| 2026-03 | 12 | R$ 268.886,96 |
| 2026-04 | 14 | R$ 271.971,46 |
| 2026-05 | 15 | R$ 262.604,96 |
| **2026-06** | **16** | **R$ 271.916,59** |
| **2026-07** | **14** | **R$ 269.900,06** |

**A causa real.** `dCompet`, o campo de competência que o ADN devolve, vem preenchido com a
**data de emissão** — não com o mês do serviço. Nota emitida com atraso cai no mês errado, e
como junho e julho foram os meses da transição de CNPJ, os dois viraram um só. O defeito
sempre esteve lá; só ficou visível quando duas notas grandes atrasaram no mesmo mês.

**O conserto.** `competencia_origem_adn` guarda o que o gov mandou e marca a linha como
corrigida por nós. O sync faz **recarga limpa diária** (DELETE + reinsert), então sem uma
cláusula a mais a correção morreria às 08:30 do dia seguinte — o DELETE agora preserva as
linhas corrigidas, e o `ON CONFLICT` não sobrescreve a competência delas. Provado rodando o
sync completo depois da correção: as duas continuaram em 2026-06.

**Dois invariantes novos** em `test_oraculo_fiscal_painel`: competência corrigida que ande
para o **futuro** ou que mude o **total do ano** quebra o oráculo — a correção pode
redistribuir entre meses, nunca criar receita. E pedido de cancelamento parado há 30+ dias
(`cancelamento_solicitado_em`, hoje com 0 linhas) — existe para que um cancelamento
REJEITADO no gov não tire receita do faturamento em silêncio.

**A lição.** Duas linhas com o mesmo cliente e o mesmo valor não são duplicata por serem
parecidas. A diferença entre "a mesma coisa cobrada duas vezes" e "duas competências
cobradas do mesmo jeito" não está nos dados da nota — está no calendário do serviço, que a
nota não carrega. Fui de padrão a conclusão sem consultar a fonte autoritativa; o feed do
ADN, que respondeu em uma consulta, tinha a resposta inteira. **O sinal de que eu estava
errado veio de graça e eu quase passei por ele: o buraco não fechou, andou de mês.**

## Os outros dois números da tela

**Recebíveis vencidos R$152.077,82** — não soma contas bancárias. São 7 títulos de contrato
vencidos em 10/08: Patrimonial R$141.577,82 (Ideal Flores, Prime Arena, Mirante ×2) +
Eletrônica R$10.500,00 (Parque Gelain, Hawk Eye, Green Hill).

**"A pagar nos próximos 7 dias R$0,00"** — está certo, e é o sintoma. Não existe **uma
única** conta a pagar com vencimento futuro. Das 76 pendentes, a mais recente venceu 10/08 e
a mais antiga 03/01; 46 delas (R$98.523,43) nem sabem de qual CNPJ são. É o retrato de pagar
pelo app do banco: o sistema só vê a conta depois que o dinheiro saiu.

## Planilha das lacunas

`auditoria/planilhas/lacunas_financeiro_20260813.xlsx` — 7 abas com as linhas REAIS do banco;
azul é o que o sistema sabe, laranja é o que só o Jordan sabe. Notas de julho (2), saídas de
agosto sem classificação (37), fornecedores PJ sem CNPJ (60), contas a pagar fixas, as 76
contas antigas em aberto, a carteira de recebíveis e o bloco de patrimônio que trava o
`pl_completo: false`.
