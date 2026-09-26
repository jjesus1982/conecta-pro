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

O total **não mudou** — continua −R$ 435.016,91 — e é essa a prova de que o conserto foi na
linha, não no número. O demonstrativo agora mostra as 16 contas de resultado, uma a uma.

### 2.3 Balancete, balanço e prova de caixa deixaram de discordar entre si

Três relatórios sobre a mesma tabela, cada um recortando de um jeito:

| | antes | agora |
|---|---|---|
| Balancete de agosto | R$ 6.775.023,46 (por data de lançamento) | **R$ 2.271.067,60** (por competência) |
| Receita no painel de PL | R$ 59.998,33 | **R$ 2.183.235,44** |
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

### 2.6 O DANFE da nota real estava cortando o código dos itens

A primeira NF-e de produção (Villa Dei Fiori, protocolo 113263822323573), que foi por
e-mail para você e para o condomínio, tem 6 itens. Quatro saíam com o código elidido:
`CABO-CAT5E-…`, `CX-SOBREPO…`, `ELETRODUT…`, `CABO-ELEV…`. Corrigido — o código agora
quebra em linhas como a descrição já fazia.

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
| Conciliação bancária de fato | 3,6% · 2.073 pendentes | operação |

### O que NÃO existe e é exigência legal

ECF (nem esboço), EFD Contribuições (mensal, dia 10), EFD ICMS/IPI (mensal, dia 15),
PGDAS-D, DCTF. E hoje quem transmite **eSocial S-1200, DCTFWeb e EFD-Reinf é a Portte** —
some no dia da rescisão. Exercícios 2022–2025 não são geráveis deste banco: 65 lançamentos
em 2025, 13 em 2024, 11 em 2023.

---

## 4. Uma decisão sua que está pronta para executar

Com o classificador corrigido, das 314 saídas hoje **sem categoria nenhuma**, 155 ganham
natureza — 142 delas são salário de CPF que casa com o cadastro de funcionários:

    salario 142  R$ 119.182,28   ·   imposto 6  R$ 26.939,54
    taxa_bancaria 6              ·   servico_sem_nf 1
    ficam em `outros` 159        R$ 200.275,77  (continuam pendentes, de propósito)

Aplicar isso faz o fechamento diário mover cerca de R$ 150 mil para fora de «Saídas a
Classificar». **Não apliquei.** Em três commits de hoje escrevi que reclassificar conta é
ato de contador, e não vou ser incoerente na véspera de você entregar os livros a alguém
novo — ele vai querer ver o antes e o depois. É um comando; diga e eu rodo.

---

## 5. Vigilância nova

Quatro oráculos (`backend/scripts/orq/`), todos com **vermelho provado** contra o código
anterior restaurado do git:

| | O que afirma | Vermelho antes |
|---|---|---|
| **C1** | CPF nunca é tributo; a contraparte manda | 4 desvios (R$ 52.852,71 de PF como tributo) |
| **C2** | Nada entra no total do DRE sem linha | 4 desvios (R$ 280.464,67 de custo sem linha) |
| **C3** | Balancete, balanço e caixa contam a mesma população | 4 desvios |
| **C4** | A ECD diz a verdade do razão | 12 desvios |

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
