# Arrumar a casa para rescindir com a Portte — 25/09/2026

> Jordan: *"foco total na contabilidade então trabalhe em loop autônomo… arruma a casa que
> eu vou rescindir com a portte contábil."*

Tudo aqui foi **medido em produção**. Onde não consegui medir, está dito.

---

## 1. As duas coisas que precisam ser feitas ANTES de rescindir

Não são código, e são as únicas que ficam impossíveis depois.

### 1.1 Peça o saldo de abertura de 31/12/2025

As **89 contas do plano estão com saldo de abertura ZERO**. O razão nasce do nada em
01/01/2026, então o que ele chama de "saldo" é só o movimento do ano. Consequências medidas:

- O Ativo da Eletrônica fecha **credor em −R$ 244.547,72** — balanço impossível.
- Por isso o bloco J100 da ECD é **recusado de propósito** pelo sistema.
- A divergência de caixa entre o razão e o que os bancos informam, R$ 7.458,78, é
  praticamente isso: reconstruindo pelo encadeamento do extrato do Inter, a abertura em
  01/01/2026 seria **R$ 7.625,62**, e a divergência real cairia para a ordem de R$ 110.

Esse número está com a Portte. Depois da rescisão vira negociação.

### 1.2 Defina o contabilista com CRC ativo

A ECD e a ECF são assinadas por contabilista habilitado. Nenhum software substitui isso —
e hoje **não existe nem campo de CRC** no banco de dados. Rescindir não elimina a
exigência; muda quem produz o arquivo.

---

## 2. O que passou a funcionar hoje

### 2.1 A ECD sai do razão, por CNPJ

O gerador de 831 linhas já existia e já rodava. O que ele produzia é que não servia: a
natureza de cada conta era deduzida do **primeiro dígito do código**, com um mapa que
descrevia o plano de contas aposentado em 13/08/2026.

| | antes | agora |
|---|---|---|
| Receita do exercício no I350 | **R$ 0,00 D** | **R$ 1.581.873,06 C** |
| Registro 0000 | sem UF, IE, município, IM | AM · 054265746 · 1302603 · 45177801 |
| Encerrador do bloco I | `I990 = 10` (num bloco de 17.863) | `I990 = 17.862` |
| Saldos por conta | 27 × I150 sem código da conta | 1 × I150 + 27 × I155 com código |
| Bloco K | não existia | K001/K990 |
| ECD da Patrimonial | impossível (`empresa_id` fixo no código) | 3.142 registros, CNPJ próprio |
| Balanço e DRE (J100/J150) | zero registros | J150 sempre; J100 quando o balanço se sustenta |

Rota nova: **`POST /api/v1/government/sped-contabil/gerar`** (antes só existia `/status`).
Aceita `empresa_slug`; com `formato=txt` devolve o arquivo. Recusa com 422 se não houver
lançamento no período — gerar ECD vazia é pior que não gerar.

### 2.2 O DRE parou de esconder um quinto da despesa

O DRE batia ao centavo com o razão e mesmo assim mentia: as linhas visíveis somavam
**+R$ 89.571,41** e o EBITDA publicado era **−R$ 435.016,91**. A diferença de
R$ 524.588,32 — a conta transitória «Saídas a Classificar» — era subtraída do total **sem
nenhuma linha no demonstrativo**.

Junto com ela:

- **R$ 280.464,67** de custo (VR, férias/13º, diaristas, reembolsos, EPI) fora dos itens do
  próprio grupo, com rótulos citando contas de um plano morto.
- «Resultado Financeiro: 0,00» era literal no código, com R$ 10.415,30 de juros escondidos
  dentro de Despesas Operacionais.

O total **não mudou** com esse conserto — antes e depois, −R$ 435.016,91 — e é essa a prova
de que ele foi na linha, não no número. O demonstrativo agora mostra as 16 contas de
resultado, uma a uma. (O total só se moveu depois, para −R$ 436.516,91, quando tirei do
razão os R$ 1.500 de receita que eu mesmo tinha criado testando — §2.5.)

### 2.3 Balancete, balanço e prova de caixa deixaram de discordar entre si

Três relatórios sobre a mesma tabela, cada um recortando de um jeito:

| | antes | agora |
|---|---|---|
| Balancete de agosto | R$ 6.775.023,46 (por data de lançamento) | **R$ 2.271.067,60** (por competência) |
| Receita no painel de PL | R$ 59.998,33 | **R$ 2.181.735,44** |
| Prova de caixa | "bate ✓, divergência R$ 0,00" | divergência real **R$ 7.458,78**, com a causa escrita |
| Liquidez corrente | −0,29 · "posição apertada" | **não apurada**, com o motivo |

O balancete de agosto estava três vezes inflado porque as 168 apurações — de competências
2022-12 a 2026-08 — foram todas lançadas com data de agosto/2026. A "prova de caixa"
comparava o razão com a tabela **de onde o razão é escriturado**: batia por construção, ao
lado de um saldo bancário negativo de R$ 4.258,33 que é impossível.

### 2.4 Salário deixou de ser tributo

`2.1.2.09 Tributos a Recolher - a identificar` tinha **R$ 74.544,49 com 180 baixas e ZERO
provisões** — um passivo que só foi pago, nunca devido.

A causa era uma linha de leitura. O extrato do Inter escreve
`Pix enviado: "Cp :00360305-Fulano de Tal"`, e o `00360305` é o CNPJ da **Caixa Econômica
Federal** — o banco destino — não de quem recebeu. A tabela de regras casava isso com
"Recolhimento FGTS", então **todo funcionário com conta na Caixa teve o salário carimbado
como tributo**.

Medição que fecha o caso: sobre as 3.954 transações com esse padrão, o fragmento coincide
com o CNPJ da contraparte em **32**. Dos 13 CNPJs da tabela, **10 nunca aparecem como
contraparte** — são Nubank, Santander, Itaú, Banco do Brasil.

    antes:  imposto 170  R$ 65.806,30
    agora:  salario 125  R$ 43.176,57   (CPF que casa com o cadastro de funcionários)
            imposto  12  R$ 17.516,91   (os DARF de verdade)
            outros   43  R$ 13.851,01   (revisão manual — honesto)

### 2.5 Erro meu, corrigido

Duas notas de **homologação** que emiti testando em 24/09 (nº 8 e 9, R$ 1.500) estavam
lançadas como faturamento real de setembro. O escriturador não filtrava ambiente. A trava
criada no mesmo dia para esse incidente ficou verde porque mede a tabela de notas, e o
razão é outro lugar.

    receita de setembro no razão:  R$ 26.460,00 → R$ 24.960,00
    emitido em setembro:                         R$ 24.960,00   ← bate ao centavo

E o prejuízo de 2026 mudou junto, porque R$ 1.500 de receita que não existia saiu da conta:

    prejuízo acumulado 2026:  R$ 435.016,91 → **R$ 436.516,91**
    receita 2026:             R$ 2.183.235,44 → R$ 2.181.735,44

### 2.6 O DANFE da nota real estava cortando o código dos itens

A primeira NF-e de produção (Villa Dei Fiori, protocolo 113263822323573), que foi por
e-mail para você e para o condomínio, tem 6 itens. Quatro saíam com o código elidido:
`CABO-CAT5E-…`, `CX-SOBREPO…`, `ELETRODUT…`, `CABO-ELEV…`. Corrigido — o código agora
quebra em linhas como a descrição já fazia.

### 2.7 A apuração de agosto estava aberta — e nunca se fecharia sozinha

A task de encerramento roda dia 5 e fecha **a competência anterior**. Só isso deixa um
buraco permanente: competência já apurada que recebe lançamento depois nunca mais é
revisitada, porque no mês seguinte a task olha outro mês. O comentário do próprio
agendamento já dizia o preço — *"foi assim que 42 competências ficaram abertas desde 2022"*.

Aconteceu de novo: 2026-08 foi apurada em 07/09 e depois chegaram pelo ADN as NFS-e de
agosto que o fisco só publicou em setembro. Sobravam **R$ 15.139,00** abertos — a NFS-e 29
(R$ 33.538,33) e o DAS (R$ 18.399,33).

Rodei a apuração de agosto: a conta de passagem voltou a R$ 0,00 e todas as 43 competências
estão encerradas. E a task passou a varrer resíduo de competência anterior, não só o mês
passado — com trava por AST no oráculo do balanço, para que ninguém a remova sem o vermelho
aparecer no mesmo dia.

### 2.8 O painel de obrigações escondia justamente as que vão doer

`GET /empresas/obrigacoes/calendario/grupo?mes=9&ano=2026` devolvia
**`previstos_pelo_regime: 0`**. O motivo: bastava UMA obrigação cadastrada no mês para o
molde do regime ser descartado inteiro — e ECD, ECF, EFD Contribuições, EFD ICMS/IPI, DCTF
e PGDAS-D **nunca foram cadastradas**, porque quem as cuidava era a Portte.

| | antes | agora |
|---|---|---|
| 09/2026 Eletrônica | 7 cadastradas · **0 do regime** | 7 · **4** (DCTF, EFD Contribuições, EFD ICMS/IPI, IRPJ/CSLL) |
| 09/2026 Patrimonial | 1 cadastrada · **0 do regime** | 1 · **3** (FGTS, ISS, **PGDAS-D**) |
| 06/2026 Eletrônica | 7 cadastradas · **0 do regime** | 7 · **5** — inclusive a **ECD**, que vence em junho |

O código estava assim por um motivo legítimo: as duas fontes chamam a mesma obrigação por
nomes diferentes (`FGTS` no cadastro contra `FGTS_GUIA` no molde), e mesclar sem ponte
duplicaria tudo. Descartar o molde era o remédio errado para um problema real. Agora há a
ponte, e cada linha diz se é cadastrada ou apenas prevista pelo regime.

Isto **não gera** nenhuma dessas obrigações — ECF não existe nem como esboço, EFD
Contribuições e EFD ICMS/IPI têm gerador sem rota. Mas ver o prazo é o que faz alguém agir.

### 2.9 A folha estava contada DUAS vezes — R$ 189.870,59 de prejuízo que não existia

Você mandou tirar os R$ 150 mil de «Saídas a Classificar». Ao medir onde estavam, o número
era outro e a causa também — **e preciso corrigir o que eu tinha dito na §4 da versão
anterior deste relatório.** As 142 transações de salário que o classificador identificou
**já estavam lançadas certas**, em `2.1.1.01 Salários a Pagar`. Nunca estiveram na
transitória. Eu somei o valor das classificadas sem conferir em que conta o razão as tinha
posto. O efeito direto da classificação eram R$ 11.880,00.

Procurando o resto, apareceram três defeitos:

1. **`contrapartida_entrada` testa os CNPJs do grupo antes de tudo; `contrapartida_saida`
   não testava.** Dinheiro que a Patrimonial mandou para a Eletrônica saía como DESPESA —
   R$ 86.000 em 4 lançamentos, um deles categorizado `imposto`, que o teria mandado para
   «Tributos a Recolher - a identificar».

2. **A tabela de CNPJs conhecidos inteira apontava para bancos.** Ela nasceu do `Cp :` da
   descrição. Dos 13, dez nunca aparecem como contraparte. E um estava ativamente errado:
   `31680151` rotulado como SOLIDES, quando o CNPJ real da Solides é `10461302` — 93
   transações, R$ 55.570 presos na transitória.

3. **O reclassificador parava no corte contábil**, e isso prendia 637 lançamentos
   (R$ 308.149,66) na transitória para sempre. O corte existe contra lançamento NOVO em mês
   fechado — e o gatilho do banco diz isso textualmente: é `BEFORE INSERT`, com a dica
   *"Corrigir lancamento existente (UPDATE) e permitido."*

**E o item 3 não era cosmético.** Dentro daqueles 637 havia **R$ 64.739,46 de PAGAMENTO de
salário lançados como despesa**, em cima da provisão que a folha já tinha lançado. A mesma
despesa contada duas vezes. Mais R$ 18.333,39 de pagamento a fornecedor e R$ 16.230,00 de
transferência entre as empresas, na mesma situação.

| | antes | agora |
|---|---|---|
| linha «Saídas a Classificar» no DRE | −R$ 524.588,32 | **−R$ 272.395,49** |
| lançamentos na transitória | 863 | 633 |
| **resultado de 2026** | −R$ 436.516,91 | **−R$ 246.646,32** |
| contas com natureza invertida | 10 | 9 — saiu `2.1.1.01`, o pagamento voltou a baixar o passivo |

253 lançamentos reclassificados. Oito competências reabriram e foram encerradas pela
varredura de resíduo (R$ 113.870,59); a conta de passagem voltou a R$ 0,00. O balancete
continua fechando, e os oráculos do balanço, contábil, C1 a C5 e fin_visao estão verdes.

Conferido: `2.1.1.01` ficou **credor em R$ 20.427,60** — a provisão existia mesmo e absorve
os pagamentos. Se não existisse, a conta teria ficado devedora e a trava de natureza teria
acusado.

### 2.10 O resto da transitória virou fila, não mistério

Ficam **R$ 272.395,49 em 625 lançamentos**, e eles não saem por regra: são pagamentos a
empresas reais e PIX a pessoas fora do cadastro. Um pagamento a CNPJ pode ser serviço,
parcela de financiamento (parte passivo, parte juros), empréstimo ou gasto pessoal — a
descrição diz, a regra não. Chutar ali seria fabricar.

O que dava para fazer, e foi feito: `checar_transitoria_aberta.py` agrupa o que restou **por
contraparte**, ordenado por valor. São **218 contrapartes, 101 delas acima de R$ 300** —
decidir uma resolve várias de uma vez. Os maiores blocos:

    (sem nome, 170 PIX)  R$ 67.110,61      PJBANK PAGAMENTOS      R$ 11.873,46
    Sind. Transportes    R$  9.880,00      Denilson Silva Cardoso R$  9.623,68
    VB Odontológico      R$  9.250,00      Atlas Monitoramento    R$  9.106,37
    Gabriele Vitoria     R$  9.100,00      PORTTE CONTÁBIL        R$  6.580,22

A transitória de ENTRADAS ficou praticamente vazia: R$ 83,60.

### 2.11 A escrituração de ICMS declarava nota de serviço como mercadoria

O gerador de EFD ICMS/IPI existia e rodava. O que ele produzia era declaração falsa, e o
próprio código dizia o motivo: lia `nfse_emitidas_nacional` — **notas de serviço** — e as
declarava como NF-e modelo 55 com CFOP 5933, *"para não gerar arquivo oco"*.

| competência 09/2026 | antes | agora |
|---|---|---|
| documentos declarados | 9, **todos NFS-e** | 1, a NF-e real |
| chave declarada | começando em `1302603` (código IBGE de Manaus) | chave de NF-e de verdade |
| a NF-e do Villa Dei Fiori (R$ 2.581,00) | **fora do arquivo** | declarada, com 6 itens |
| C170 (item por item, exigido no perfil A) | **nunca emitido** | 6 |
| 0200 (cadastro de produto) | 0 | 6, com NCM |

Mais seis defeitos de leiaute no mesmo arquivo: o campo do **desconto** recebia o valor
cheio da nota (uma NF-e de R$ 2.581,00 declarava R$ 2.581,00 de desconto) e o campo de
mercadoria saía zerado; o C190 recebia o **valor** do ICMS no campo da **alíquota**, com CST
fixo "00" e um registro por documento; os encerradores contavam chaves e não linhas; o
participante saía com CNPJ `00000000000000`; e o CNPJ da empresa era constante no código.

Rota nova: **`POST /api/v1/government/sped-fiscal/gerar`**, que recusa com 422 se o CNPJ não
tiver inscrição estadual — a Patrimonial só tem inscrição municipal, e EFD ICMS/IPI é
obrigação de contribuinte do ICMS.

**Arquivo oco é honesto; arquivo que declara nota de serviço como mercadoria, não.** A EFD
de setembro vence em 15/10.

---

## 3. O que continua aberto, com valor

| O quê | Valor | Decisão de quem |
|---|---|---|
| `5.9.9.01 Saídas a Classificar` — 19% da despesa do ano | R$ 524.588,32 | ver §4 |
| `2.1.2.09` — origem corrigida, histórico não | R$ 74.544,49 | contador |
| `3.9.9.01 Abertura a Identificar` (plug contra o Capital Social) | R$ 600.000,00 | contador |
| 2 NFS-e de junho da Patrimonial, chegaram depois do corte | R$ 108.386,92 | reabrir período? |
| 2 NFS-e com competência corrigida na nota e não no razão | R$ 108.386,92 | contador |
| Recusados por período fechado **por rodada diária** (só Patrimonial) | R$ 569.878,54 | é correto recusar — agora é contado |
| **Encerramento que não sabe de qual CNPJ é** — 171 lançamentos | R$ 5.132.437,80 | contador (ver abaixo) |
| Conciliação bancária de fato | 3,6% · 2.073 pendentes | operação |

### O encerramento não separa as duas empresas

`apurar()` fecha 4.x e 5.x **por competência, sem filtrar empresa**, e grava `empresa_id`
nulo. São **171 lançamentos, R$ 5.132.437,80 — e os únicos 171 do razão inteiro sem
empresa**. Duas consequências diretas para a rescisão:

1. **A ECD de cada CNPJ sai sem o encerramento.** O gerador filtra `empresa_id`, então esses
   lançamentos ficam de fora do bloco I200/I250, que é o Livro Diário. Diário sem
   encerramento não é o diário do exercício.
2. **O resultado das duas pessoas jurídicas é somado num lançamento só.** O lucro de uma não
   encerra contra o patrimônio da outra.

O que cada encerramento deveria levar ao PL em 2026:

    CONECTAMAIS ELETRONICA    receita 1.584.579,69   despesa 1.842.082,34   →  −257.502,65
    CONECTAMAIS PATRIMONIAL     receita 597.155,75     despesa 776.170,01   →  −179.014,26

**Não consertei, e o motivo é concreto:** uma apuração filtrada por CNPJ **não enxergaria**
os 171 lançamentos existentes (que têm empresa nula) e recalcularia o resultado cheio —
fechando os meses em DOBRO. Corrigir exige decidir o destino desses 171, e isso é ato de
contador. Está contado pela trava `checar_apuracao_sem_empresa.py`.

### O que NÃO existe e é exigência legal

ECF (nem esboço), EFD Contribuições (mensal, dia 10), EFD ICMS/IPI (mensal, dia 15),
PGDAS-D, DCTF. E hoje quem transmite **eSocial S-1200, DCTFWeb e EFD-Reinf é a Portte** —
some no dia da rescisão. Exercícios 2022–2025 não são geráveis deste banco: 65 lançamentos
em 2025, 13 em 2024, 11 em 2023.

---

## 4. A decisão que você tomou, e o que ela rendeu

Você mandou aplicar. Está aplicado — e rendeu mais do que eu tinha estimado, por um motivo
diferente do que eu tinha dito. Veja §2.9: a classificação em si movia R$ 11.880,00; o que
tirou R$ 252.192,83 da transitória foram os três defeitos que apareceram ao procurar o
resto, sendo o maior deles a folha contada duas vezes.

Uma coisa eu **não** fiz e registro aqui: 18 transações da Solides foram justificadas por
você mesmo como "outro". Não sobrescrevi — a ponte por CNPJ entra na escrituração, que é
decisão do sistema, e não no campo de justificativa, que é seu.

## 5. Vigilância nova

Quatro oráculos (`backend/scripts/orq/`), todos com **vermelho provado** contra o código
anterior restaurado do git:

| | O que afirma | Vermelho antes |
|---|---|---|
| **C1** | CPF nunca é tributo; a contraparte manda | 4 desvios (R$ 52.852,71 de PF como tributo) |
| **C2** | Nada entra no total do DRE sem linha | 4 desvios (R$ 280.464,67 de custo sem linha) |
| **C3** | Balancete, balanço e caixa contam a mesma população | 4 desvios |
| **C4** | A ECD diz a verdade do razão | 12 desvios |
| **C5** | O calendário mostra a obrigação que o regime exige | 8 desvios |
| **C6** | A EFD declara a NF-e que existe, e não inventa documento | 14 desvios |

E um caçador diário: `checar_receita_nao_lancada.py` — NFS-e emitida que não virou receita,
lançamento em competência diferente da nota, e nota de teste contada como faturamento.
Hoje: **4 divergências**, todas de decisão de contador, todas contadas como dívida.

---

## 6. O que eu não consegui medir

- **Se o arquivo da ECD passa no PVA da Receita.** Não há PVA neste ambiente. As afirmações
  sobre leiaute vêm de comparar o gerador com a estrutura documentada dos registros.
- **Se o razão de 2026 está contabilmente correto.** Verifiquei que fecha em partida dobrada
  e que os relatórios concordam entre si. Auditar a reconstrução de jan–jul feita a partir
  do extrato bancário está fora do que dá para medir daqui.
- **A que empresa pertencem as 168 apurações** (R$ 5.065.361,14). Todas com `empresa_id`
  nulo. Presumi pelas contas envolvidas; o dado não prova.
- **O que é, juridicamente, a guia FGTS "CONSIGNADO"** — R$ 41.196,19 pagos de 12.2025 a
  06.2026 e nunca provisionados. Só sei o que o nome do arquivo diz.

---

# Continuação — 26/09/2026: a primeira nota do ERP

## O conflito de série, que não era conflito

Antes de emitir, duas tabelas discordavam sobre em que série a nota deveria sair:

    empresas.nfse_serie_rps                     = 901     (contador de produção em 0)
    nfse_parametros_empresa.serie_dps           = 70000   (último DPS no fisco: 125)

Parecia erro de cadastro. Não era: **são dois pontos de emissão diferentes, e a série é
exatamente o que os separa.** O `70000` é a série do portal que a contabilidade usa — foi
medida lendo DANFSe de verdade (`ultimo_dps_fonte`: «DANFSe nº 121 de 17/09/2026 — NÚMERO
DA DPS 125, SÉRIE DA DPS 70000»). O `901` é a série do ERP.

Emitir daqui na 70000 teria colidido com a numeração do portal e o fisco recusa isso com
**E0014** — o mesmo erro que já obrigou a separar sandbox de produção em séries distintas.
A linha do `SERIE_PADRAO` no código já dizia isso desde 24/09 («há um terceiro ponto: o
portal que a contabilidade usa, na série 70000»); as duas funções é que não diziam.
Corrigido nas duas docstrings: `nfse_emissao.serie_da` emite, `nfse_parametros.serie_de` lê.

## A prévia que não mostrava o que ia ser enviado

O `dry_run` retornava **antes** de reservar número e não passava série, então a simulação
saía com `<serie>900</serie>` e um `nDPS` de timestamp — os dois campos com maior chance de
erro apareciam certos no fisco e errados na prévia. Uma prévia que não mostra o que vai ser
enviado não é prévia: ela dá confiança sem dar informação.

`espiar_numero()` lê qual número *seria* reservado, sem reservar, e o `dry_run` passa
série e número de verdade. A prévia da nota do Hawk Eye passou a mostrar:

    <serie>901</serie>  <nDPS>1</nDPS>  <tpAmb>1</tpAmb>  <dCompet>2026-08-01</dCompet>
    <opSimpNac>1</opSimpNac>   (não optante — Lucro Real, correto)

## NFS-e 124 — Hawk Eye

    chave     13026032235710481000103000000000012426094625752532
    série 901 · DPS nº 1 · NFS-e nº 124 · cStat 100 · HTTP 201 · produção
    competência 2026-08 · R$ 1.000,00 · ISS R$ 50,00 · código 140601 (portaria remota)

O valor é decisão do dono, e é o que entrou: *«contabilize apenas o que entrou da hawkeye
na conta da eletrônica, não o que pagamos, pois eles são fornecedores nossos também, mas o
que eles pagaram como clientes»*. O contrato é de R$ 4.000/mês; no extrato do Inter há uma
única entrada dele no ano, R$ 1.000 em 13/08. O resto entrou na conta pessoa física do
dono, no Itaú, que o sistema não conhece.

O código 140601 não é escolha minha: é o que as outras notas de portaria remota desta mesma
empresa já usaram no fisco (Gelain, Villa dos Pássaros, Green Hills, Parise Village, Prime
Arena — todas 140601, ISS 5%).

No razão, depois do `fechar_grupo()`:

    D 1.1.2.01  /  C 4.1.1.01   R$ 1.000,00   Receita NFS-e 124 (2026-08)
    D 5.2.2.01  /  C 2.1.2.01   R$    50,00   ISS s/ NFS-e 124 (2026-08)

O dinheiro já estava lançado desde 13/08 (`D 1.1.1.01 / C 1.1.2.01`), então a conta de
clientes a receber fecha. Receita de 2026-08: R$ 274.461,56 → **R$ 275.461,56**.

## A régua que faltava: nota ←→ dinheiro

O Hawk Eye não foi achado por trava nenhuma — foi o dono que contou. As duas travas que
existiam partem do **contrato**, e quem recebe fora do contrato passa por baixo das duas.

`checar_recebimento_sem_nota.py` fecha o triângulo. Compara, por documento de contraparte,
**o que o cliente depositou** contra **o que foi faturado para ele**, em acumulado de 4
competências fechadas — acumulado porque nota de setembro se paga em outubro, e a
comparação mês a mês acusaria todo mundo por atraso de dias.

Prova contra o código anterior, na janela 2026-05 a 2026-08:

    HAWK EYE   recebido R$ 1.000,00   faturado (sem a nota 124) R$ 0,00   ← acusaria
    HAWK EYE   recebido R$ 1.000,00   faturado (com a nota 124) R$ 1.000,00 ← cala

E ela conta a própria população antes de dar o total, porque «TOTAL: 1» sobre uma
população cortada em silêncio é pior que nenhuma medida:

    entrou no período: R$ 1.111.425,32 em 112 créditos
       cliente cadastrado (é o que esta régua compara)    49x  R$ 822.680,52   74,0%
       entrada sem documento de contraparte               16x  R$ 150.065,98   13,5%
       documento preenchido, mas nenhum cliente com ele   35x  R$  69.734,42    6,3%
       transferência entre os nossos CNPJs                12x  R$  68.944,40    6,2%
    → esta régua alcança 74% do dinheiro. O resto não foi olhado por ela.

**Um achado real, e eu errei duas vezes antes de chegar nele.** CONDOMINIO RESIDENCIAL
PARQUE DOS FRANCESES depositou **R$ 2.508,00 em 27/08** — PIX de verdade, da conta
Bradesco do condomínio, com CNPJ na contraparte. Não há nota, não há título e nenhum
registro do sistema tem esse valor.

Puxando o fio apareceram duas decisões em sentidos opostos, e a leitura certa é a segunda:

    10/08 00:35  título de 08/2026 CANCELADO — «contrato só inicia em 09/2026
                 (confirmado pelo Jordan). start_date corrigido para 01/09.»

    14/08 18:17  o Jordan REVERTEU. Está por escrito em
                 `backend/scripts/corrigir_inicio_franceses.py`: «Decisão do Jordan em
                 14/08/2026 (...) o contrato está cadastrado com start_date = 2026-09-01
                 e ISSO ESTÁ ERRADO — ele entra em agosto, e é dele a PRIMEIRA NOTA e o
                 PRIMEIRO BOLETO da vida do cliente com a gente.»

**Minha primeira leitura foi que a correção de 10/08 «se perdeu». Não se perdeu: foi
revertida de propósito, e o estado atual (`start_date = 01/08`) é a decisão mais recente
do dono.** Ainda bem que não «consertei» a data.

E isso inverte a conclusão: **agosto ERA faturável, e a nota nunca foi emitida.** O
título de agosto foi cancelado em 10/08 sob uma premissa que caiu quatro dias depois, e
ninguém o recriou. A descrição do contrato afirma «1ª NFS-e emitida no fim de agosto» —
no fisco **não existe** nota de competência 08 para esse tomador; a primeira é a 121, de
17/09.

Ou seja: `checar_contrato_vs_faturado.py` estava **certo** ao acusar agosto como «SEM
NOTA», e eu é que descartei o alarme como defasagem de calendário. O caçador novo
(`checar_recebimento_sem_nota.py`) pegou o mesmo buraco pelo outro lado — o dinheiro —
e foi ele que me obrigou a olhar duas vezes.

## O que falta, e é uma pergunta só

Agosto precisa de nota. **Por qual valor?** O contrato diz R$ 1.800,00; o cliente pagou
R$ 2.508,00. A diferença de R$ 708,00 não está em lugar nenhum: a proposta aceita tem um
item só (manutenção preventiva + corretiva, R$ 1.800/mês), não há título com esse valor,
e juros de atraso não explicam (vencia 10/08, pago 27/08 — R$ 1.800 com 2% de multa e 1%
ao mês daria ~R$ 1.846).

Não emiti nota sobre o valor recebido: emitir sobre o recebido, quando ele não bate com o
contratado, é chute — pode ser duas competências juntas, serviço extra ou adiantamento.

## O que ficou provado que NÃO era problema

- **Notas 11 a 14 do Parque dos Franceses** («FIXTURE DGX Z7 — SEM VALOR FISCAL», «PROVA DE
  PRODUCAO EM HOMOLOGACAO», R$ 2.400 somadas) estão marcadas `ambiente = 'homologacao'` e o
  filtro de receita as exclui corretamente. Não entraram no DRE.
- **Duas notas canceladas no fisco** que o sync de hoje descobriu (nº 6 de 01/2026,
  R$ 35.737,39; nº 31 de 02/2026, R$ 5.850) **não têm receita correspondente no razão** —
  nada a estornar.
- **Parque dos Franceses não estava sem faturar** (ver PLANO_2027 §3.2).

---

# A transitória: R$ 67 mil que ninguém conseguia decidir

A conta **5.9.9.01 «Saídas a Classificar»** tem R$ 272.948,99 em 638 lançamentos. Ela é a
terceira maior linha de despesa do ano — depois de salários e terceiros — e é a que impede
saber o custo por posto, porque nada ali tem natureza.

Decidir transitória se faz **por contraparte**: uma decisão resolve várias (a Sólides eram
16 linhas com o mesmo destino). E o maior balde da lista era exatamente o que não dava para
decidir:

    ---- (sem nome)    170x   R$ 67.110,61   Pix enviado: "00019 61638862 ERIKA PEREIRA

**25% de toda a conta, num balde sem contraparte.** Só que a contraparte estava ali o tempo
todo — dentro da descrição. O extrato do Inter manda o mesmo fato em texto diferente
conforme a porta (API, CSV, boleto, convênio, cartão), e o extrator cobria **um** formato.

Cobrindo os seis, **170 de 170 ganham nome**, todos por padrão declarado e nenhum pelo
fallback genérico. O balde único virou ~110 contrapartes:

    ---- BANCO TOYOTA DO BRASIL SA     3x  R$ 8.380,33     ← financiamento, não despesa
    ---- WANDERSON DIAS                4x  R$ 3.923,79     ← ~R$ 1.000/mês, pessoa física
    ---- ERIKA PEREIRA                 6x  R$ 3.753,74     ← idem
    ---- JORDANA PIRES                 9x  R$ 3.689,63     ← idem
    ---- BANCO C6 S.A.                 3x  R$ 3.688,35     ← financiamento
    ---- RUAN FIGUEIREDO               7x  R$ 3.658,00     ← idem
    ---- ITAU UNIBANCO HOLDING S.A.    1x  R$ 3.630,17     ← financiamento
    ---- ECONDOS SISTEMAS LTDA         3x  R$ 3.320,15     ← fornecedor
    ---- PREFEITURA MUNICIPAL MANAUS  11x  R$ 3.151,66     ← tributo
    ---- RECEITA FEDERAL               2x  R$ 2.082,64     ← tributo

**Isto não classifica nada sozinho, e de propósito.** Só 46 dos 170 casam com o cadastro de
funcionários, e valem R$ 1.916 (são os PIX de R$ 32 de VA/VT). Os R$ 62 mil restantes são
de pessoas e empresas que o cadastro não conhece — e dizer que «ERIKA PEREIRA é folha»
porque o valor parece salário é adivinhação com consequência trabalhista.

O que mudou é que **agora há o que decidir**. Três grupos saltam da lista e cada um tem um
destino óbvio assim que alguém confirmar:

| grupo | o que parece ser | conta provável |
|---|---|---|
| BANCO TOYOTA, BANCO C6, ITAÚ | parcela de financiamento | amortização de passivo, **não despesa** |
| RECEITA FEDERAL, PREFEITURA | tributo | 5.2.2.xx / 2.1.2.xx |
| as ~8 pessoas de R$ 1.000–1.700/mês | cobertura ou prestação | folha (5.1.1.07) **ou** serviço com nota |

O terceiro é o que vale dinheiro e risco: se é cobertura, o lugar é folha e há exposição
trabalhista; se é prestador, precisa de nota. É a mesma pergunta da §3.1 do PLANO_2027, e
continua sendo do dono.

## A regressão que ia junto, e não foi

Nomear mais contrapartes faz o sistema consultar mais o cadastro de fornecedores — e essa
consulta casava pela **primeira palavra** com mais de 3 letras, pegando o primeiro
resultado. «BANCO TOYOTA DO BRASIL SA» virava `WHERE name ILIKE '%BANCO%' LIMIT 1`.

O CNPJ que sai dali é **gravado no extrato**, e é de lá que o classificador contábil decide
a natureza do lançamento. Documento errado não fica parado: vira conta errada no razão —
foi assim que salário virou FGTS, por outra porta, em setembro.

Agora o token precisa discriminar (BANCO, PREFEITURA e MUNICIPAL entraram na lista de
genéricos) e o candidato precisa ser único; no empate devolve vazio. **Sem documento é
melhor que o documento de outro.**

---

# Sair da Portte: a conta que ninguém estava contando

O que trava a rescisão não é a contabilidade — essa já fecha. É que **seis obrigações que
a Portte produz hoje o sistema não sabe produzir**, e no dia da rescisão cada uma vira
exposição legal com data marcada.

Isso estava escrito num arquivo de memória. Agora é um número medido todo dia:

    CONECTAMAIS ELETRONICA (Lucro Real) — 11 obrigações exigidas
       gera  EFD ICMS/IPI          POST /government/sped-fiscal/gerar
       gera  ECD                   POST /government/sped-contabil/gerar
       NÃO   EFD Contribuições     nenhuma rota
       NÃO   ECF                   nenhuma rota
       NÃO   DIRF                  nenhuma rota
       NÃO   RAIS                  nenhuma rota
       NÃO   DCTF                  só GET /dctfweb/status

    CONECTAMAIS PATRIMONIAL (Simples) — 4 obrigações exigidas
       NÃO   PGDAS-D               nenhuma rota

    TOTAL: 6 obrigação(ões) exigida(s) sem gerador no sistema

A DCTF quase escapou. A primeira versão da trava aceitava **qualquer** rota que contivesse
o nome da obrigação, e `GET /dctfweb/status` a fazia parecer coberta. **Consultar não é
produzir** — a régua passou a exigir rota produtora (POST, ou caminho com
gerar/transmitir/emitir). Foi o mesmo tipo de cegueira das outras réguas desta noite,
achado no meu próprio código antes de virar número no relatório.

As guias ficam de fora da conta **com motivo escrito**, não por omissão: DARF de IRPJ/CSLL,
GPS, ISS da SEMEF e DAS são pagas em banco ou emitidas em portal, e a DAE do FGTS nasce no
FGTS Digital a partir do eSocial — o dever do sistema ali é transmitir o evento, não gerar
a guia.

## Por que eu NÃO construí a EFD Contribuições hoje

Era o candidato natural: é mensal, é da Eletrônica no Lucro Real, e o padrão de construção
já existe (ECD e EFD ICMS/IPI seguem a mesma forma — `core/sped_*.py` + serviço + rota +
oráculo).

O que impede é o parâmetro central: **se o PIS/COFINS da Eletrônica é cumulativo ou
não-cumulativo**. Tentei medir e não dá, por três caminhos:

 · a NFS-e Padrão Nacional de Manaus **não devolve PIS/COFINS** — a tabela só tem ISS;
 · os DARF no extrato vêm como `PAGAMENTO DARF NUMERADO - DARF NUMERADO`, sem o código
   da receita, que é justamente o que distinguiria um regime do outro;
 · `nfse_parametros_empresa` tem `retem_pis_cofins = false` e código de retenção 8
   («PIS/COFINS Não Retidos, CSLL Retido») — isso é sobre RETENÇÃO do tomador, não sobre
   o regime de apuração do prestador.

Gerar uma escrituração de PIS/COFINS chutando o regime é produzir um arquivo legal errado
com aparência de certo. Fica como pergunta para o contador, com o custo já visível na
trava.

---

# R$ 5.069,00 de despesa que nunca aconteceu

O conserto do nome da contraparte acordou 61 achados que a trava de duplicata não via — ela
**exige favorecido preenchido**, e as cópias vinham sem nome. O próprio comentário dela já
avisava disso; faltava alguém preencher o campo para que ela pudesse falar.

    73 grupos · 77 linhas excedentes · R$ 9.864,13 · TODAS com lançamento no razão
    71 de `inter_api_backfill_20260811 + inter_api_sync`
    todas entre 2026-03 e 2026-07 — antes do corte, por isso o saldo seguia batendo

A causa é conhecida e está escrita no oráculo do extrato: a ponte deduplicava exigindo
**descrição idêntica**, e a mesma transação vinda do CSV e da API tem texto diferente
(`Pagamento efetuado: "FULL TELECOM LTDA` × `PAGAMENTO DE TITULO - FULL TELECOM LTDA`).
A limpeza de 11/08 removeu 321 transações por esse método e essas escaparam. Agravante:
**148 das 150 linhas têm `external_id` NULO**, e o índice único do banco é parcial —
nulo nunca colide com nulo.

## A adjudicação não precisou do banco — o banco já estava aqui

A regra da casa é conferir contra o extrato antes de apagar, e ela existe porque já se
apagou um pagamento achando que era duplicata e o saldo denunciou com a diferença exata
de R$ 32,00. Em 26/09 o `/banking/v2/extrato/completo` do Inter devolveu **503 em todos os
intervalos, inclusive recentes**.

Só que a conferência não dependia da API: **`inter_transactions` é a tabela crua da ponte
e guarda o payload que o banco mandou**, de 06/03/2026 em diante — e todos os grupos são
de 23/03 a 28/07.

    2026-03-23  R$ 152,13  FULL TELECOM      banco 1  ·  nós 2
    2026-04-08  R$  32,00  (VA/VT, 14 pessoas) banco 14 ·  nós 19

Nos 36 dias afetados, **em todos**, o nosso número excedia o do banco.

## A poda, com duas travas e backup

 · **contagem por valor no dia**, que é o método que o oráculo prescreve;
 · **teto por dia**: nunca remover mais do que `nosso − banco` naquele dia e valor.

Mantém-se a linha com `external_id` (a que o índice reconhece); no empate, a mais antiga.
Removidas **67 transações e 67 lançamentos, R$ 5.069,00**, com backup em
`backup_dup_multifonte_20260926` — mesmo padrão das tabelas de 11/08. **Seis grupos ficaram
de pé** porque o teto os protegeu: ali o banco confirma ter as duas linhas.

## E reapurar faz parte do mesmo trabalho

Remover lançamento de competência já apurada deixa resíduo aberto e o balanço passa a
mentir. As competências 04 a 07 foram reapuradas, e o resíduo somou **exatamente** o que
saiu:

    405,00 + 2.198,00 + 2.114,00 + 352,00 = R$ 5.069,00

`test_oraculo_balanco` e `test_oraculo_extrato` voltaram a passar; os saldos continuam
batendo com os que o próprio banco informa (Inter R$ 3.906,31 em 24/09, Cora R$ 580,18).

    resultado de 2026:  −R$ 208.231,49  →  −R$ 203.875,99

---

# As três duplicatas: provadas, e o fisco disse que o prazo passou

Jordan em 26/09, item 4: *«faz o que achar melhor»*. Fiz: provei cada uma, tentei cancelar,
e o fisco respondeu com precisão.

## A prova de cada par

| competência | notas | valor | como se prova |
|---|---|---|---|
| GELAIN 2026-07 | 112 e 115 | R$ 6.000,00 | o cliente tem **uma** nota de R$ 6.000 por mês o ano inteiro — 01, 02, 03, 04, 05, 06 e 08 têm uma cada. Julho tem duas. |
| PRIME ARENA 2026-06 | 98 e 100 | R$ 3.879,60 | paga uma vez por competência: R$ 3.414,06 em 10/06, R$ 3.414,06 em 09/07, R$ 3.452,85 em 11/08 (líquido de ~12% de retenção). |
| LARANJEIRAS 2026-06 | 2 e 3 | R$ 37.438,91 | paga uma vez por competência: R$ 35.741,39 em 09/07 e R$ 36.932,63 em 07/08. |

Excedente: **R$ 47.318,51**.

## O que o fisco respondeu

    GELAIN 115 · PRIME ARENA 100
        E0822 — «O prazo para o cancelamento da NFS-e expirou, conforme parametrização
        do município emissor da NFS-e.»

    LARANJEIRAS 3
        E0840 — «o evento de Solicitação de Análise Fiscal para Cancelamento já está
        vinculado à NFS-e» — o pedido dela JÁ ESTÁ ABERTO.

Passado o prazo, cancelar deixa de ser ato do contribuinte e vira **pedido ao município**.

## Duas coisas que só o fisco podia ensinar

**O código de justificativa que estava escrito no nosso código não existe.** A docstring
dizia «1=erro na emissão · 2=serviço não prestado · 3=erro de assinatura · 4=duplicidade;
para duplicata use 4». Sondando o esquema com uma chave estruturalmente válida e
inexistente, o tipo `TSCodJustCanc` aceita **1, 2 e 9, e só**. Para duplicata o código é
**1** — emitir duas vezes é erro na emissão. (O `xMotivo` também tem comprimento mínimo.)

**O evento e105102 não tem o corpo do e101101.** Tentei montá-lo reaproveitando
`xDesc`+`cMotivo`+`xMotivo` e o fisco recusou com E1235: o `xDesc` tem enumeração própria,
e nenhum dos cinco textos plausíveis passou — inclusive «Cancelamento de NFS-e», que é o
valor aceito dentro do e101101. **Falta o XSD do evento**, e descobri-lo por tentativa
contra um endpoint de governo não é método. Parei.

`solicitar_analise_fiscal_cancelamento()` existe e **recusa**, com tudo isso escrito, para
que ninguém repita a sondagem.

## O que fica para o dono

Abrir no portal do município a **Solicitação de Análise Fiscal para Cancelamento** de:

    NFS-e 115 · GELAIN · 29/07/2026 · R$ 6.000,00
    NFS-e 100 · PRIME ARENA · 23/06/2026 · R$ 3.879,60

A da Laranjeiras (nº 3, R$ 37.438,91) já tem o pedido aberto — é aguardar o município.
