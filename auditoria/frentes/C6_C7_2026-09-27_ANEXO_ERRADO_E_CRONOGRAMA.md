# 27/09/2026 — o anexo errado, o cronograma que nascia à mão, e o que falta decidir

Jordan, três coisas fecharam hoje de madrugada e duas precisam de você. Começo pela que
custa dinheiro.

---

## 1. A margem de −11,1% tem nome

O cadastro da **Patrimonial** dizia Anexo III. A empresa é Anexo **IV**.

A prova não é minha opinião nem fonte de internet — é a guia que você pagou:

```
GUIA DAS CONECTAMAIS PATRIMONIAL 08 2026.pdf
composição:  IRPJ · CSLL · COFINS · PIS · ISS
códigos:     1001 · 1002 · 1004 · 1005 · 1010
NÃO TEM o código 1006 (CPP patronal)
folha do mês: R$ 126.689,72
```

A CPP patronal fica **dentro** do DAS no Anexo III e **fora** dele no Anexo IV. É a
definição dos dois. Se fosse III, aquela linha 1006 seria uns R$ 25 mil. Está zerada.

### O que o campo errado custava

O sistema calculava encargo de folha em **32,44%** quando o real é **55,44%**. Medido de
fora, no mesmo endpoint, antes e depois da correção:

| | antes | depois |
|---|---|---|
| encargo de folha | 32,44% | **55,44%** |
| custo all-in por posto | R$ 3.059,18 | **R$ 3.472,09** |
| margem global | −11,1% | −11,1% |

**A margem não mudou, e é exatamente esse o ponto.** O custo medido vem do extrato: a CPP
patronal sempre saiu em dinheiro de verdade. A constante errada não mudava o custo —
mudava o **preço**. Cada posto estava sendo precificado contra um piso R$ 412,91/mês
abaixo do custo real.

O −11,1% de margem global agora tem uma causa com nome, não é mistério.

### O que isso NÃO resolve

Se Anexo IV é a classificação **correta** para agentes de portaria continua sendo decisão
do tributarista. O que corrigi é outra coisa: nosso sistema discordava do que a
contabilidade **já declarou** ao fisco. Hoje eles concordam.

---

## 2. Um dígito na tabela do Simples

`crm/services/regime_tributario.py`, 3ª faixa do Anexo III: estava **13,20%**, é **13,50%**.
Nasceu assim no commit que criou o arquivo — erro de transcrição.

A prova está na própria tabela, e achei uma régua que vale para sempre: a parcela a deduzir
de cada faixa existe para a alíquota efetiva do piso de uma faixa bater **exatamente** com
a do teto da anterior. A curva é contínua por construção. O número errado produz dois
saltos, porque a faixa errada fica entre duas certas:

```
−0,30pp em R$ 360.000   (8,6000% → 8,3000%)
+0,30pp em R$ 720.000   (10,7500% → 11,0500%)
```

As outras três cópias da mesma tabela no sistema não têm salto nenhum.

Virou o **oráculo D1**, que afirma a propriedade e não os números: cinco tabelas cobertas,
zero alíquota fixada. Se a lei mudar, ele continua certo sozinho.

### E uma recusa minha que estava errada

Em 26/09 deixei a 6ª faixa do Anexo IV de fora escrevendo que a dedução de R$ 828.000
"faria a alíquota cair, e nenhuma tabela progressiva cai".

Cai. Acima de R$ 3,6 milhões o **ISS sai do DAS** e vai direto ao município: o DAS cobre
menos tributos, então a alíquota dele desce. A carga total não. A prova veio de dentro de
casa — as três cópias do Anexo III têm a mesma queda na mesma fronteira. Três transcrições
independentes não erram igual no mesmo lugar. Faixa incluída.

---

## 3. O cronograma de notas agora nasce do contrato

Antes, as propostas de nota vinham de uma lista digitada à mão a partir da sua planilha.
Três consequências:

- a **empresa emitente era adivinhada** lendo o texto da descrição atrás de dado bancário
- reajuste de contrato não chegava na nota (Prime Arena: R$ 33.479,60 no contrato,
  R$ 29.600,00 na lista)
- contrato novo só virava nota quando alguém lembrasse de digitar

Agora derivo de `contracts`: ativo, dentro da vigência, fora da carência. Apaguei outubro e
regerei: **11 propostas, R$ 262.100,06**, cada uma com o CNPJ do próprio contrato. O Green
Hills ficou corretamente de fora — 1ª nota a partir de 30/11, pelos 90 dias de carência que
você negociou.

A prova de que a inversão funciona está no contraste:

```
setembro (transcrito da planilha)  →  6 divergências
outubro  (gerado do contrato)      →  0
```

Também corrigi o piso da fila de DPS da Patrimonial (75 → 110): suas DANFSe mostram DPS 97,
106 e 110 emitidas pela Portte, e a fila nasceu curta e nunca chegou lá.

---

## PRECISO DE VOCÊ — 3 coisas

### a) O RBT12 não bate entre as duas guias

`empresas.rbt12` está vazio nas duas empresas, e o sistema **recusa** precificar sem ele —
o que está certo, chutar RBT12 escolhe a faixa, logo o imposto. Só que não consigo
preencher, porque retro-calculando a partir de cada guia eu chego em números incompatíveis:

| guia | DAS total | receita | efetiva | RBT12 implícito |
|---|---|---|---|---|
| 07/2026 | R$ 13.025,02 | R$ 255.400,06 | 5,10% | ~R$ 208 mil |
| 08/2026 | R$ 18.399,33 | R$ 200.198,74 | 9,19% | ~R$ 827 mil |

A receita caiu e o DAS subiu 41%. RBT12 não quadruplica em um mês. A guia de julho tem um
INSS de R$ 171,06 solto que cheira a complementar ou retificação.

**O que resolve:** o PGDAS-D dessas duas competências. Com ele eu preencho e a precificação
destrava.

### b) A tela de custo por contrato mostra R$ 0,00

Os 15 postos ativos têm `salario_base` **zerado** — ninguém preenche essa coluna. Então a
tela "Custo por contrato (pelas vagas)" exibe zero para os 7 contratos, enquanto a folha
real do mês é R$ 126.689,72.

Não mexi porque tem duas saídas e a escolha é sua: preencher a coluna posto a posto, ou eu
trocar a fonte para a folha real dos alocados (o dado existe, e deixa de depender de alguém
preencher). **Minha recomendação é a segunda** — ler o fato em vez de uma coluna de
planejamento.

### c) Os parâmetros de preço são de Lucro Real, aplicados às duas empresas

A tabela `crm_pricing_params` não tem empresa. Os sete encargos somam exatamente 61,24% —
o conjunto do Lucro Real, incluindo os **5,8% de terceiros que o Anexo IV não deve**. E
`pis`/`cofins` estão como 1,65%/7,60% (não-cumulativos) quando vigilância e limpeza são
0,65%/3,00% **cumulativos** por lei.

Hoje isso não custa dinheiro porque o único leitor que multiplica por dinheiro é a tela do
item (b), que está zerada. Mas o rótulo dela já exibe "61,24%" para contratos da
Patrimonial, que são 55,44%.

Não parametrizei por empresa porque `alembic/versions/` é zona proibida e isso pede
migração. **Proponho o caminho sem migração:** fazer os leitores consultarem
`encargo_pct_da_empresa()`, que já lê o cadastro certo — apagar a divergência em vez de
duplicar a tabela. Confirma?

### d) Qual é o nosso RAT: 2% ou 3%?

O número vive cravado em **nove lugares do código**. Seis dizem 3%, três dizem 2%:

| diz 3% | diz 2% |
|---|---|
| `encargos.py` (o que hoje precifica) | `fase5/cct_compliance/service.py:174` |
| `dctfweb_service.py` ("grau de risco vigilância/portaria") | `kit_preenchimento_service.py:948` (o DARF do kit) |
| `pricing_engine.py`, `pareamento_fiscal`, `simulador_regime` | `fgts_inss_manager.calcular_contribuicao_patronal(rat=2.0)` |

Tentei resolver pelo dado e **não consegue ser resolvido pelo dado**: não existe coluna de
RAT nem de FAP em lugar nenhum do banco, e as 7 guias de INSS importadas estão com a
competência nula, então não dá para dividir pela folha do mês e extrair a alíquota.

Não harmonizei por palpite — 1 ponto de RAT sobre a folha de R$ 126.689,72 é R$ 1.266,90/mês,
e cravar o número errado nos nove lugares é pior que a divergência, porque some a pista.

**O que resolve:** o RAT está no eSocial **S-1000** (campo `aliqRat`) e o FAP na carta anual
do INSS / consulta no e-CAC. Me manda qualquer um dos dois e eu unifico os nove lugares num
parâmetro só, com a fonte escrita.

Nota: o DARF com 2% está dentro de uma **guia simulada** do kit de teste, não de documento
real — menos grave, mas ainda ensina o número errado a quem lê o kit.

---

## O que ficou vigiando

| trava | o que pega | medido |
|---|---|---|
| `checar_anexo_vs_guia.py` | cadastro × guia, pela régua do código 1006 | 1 → 0 |
| `checar_cronograma_vs_contrato.py` | linha de nota que não bate com o contrato | set 6, out 0 |
| oráculo D1 | continuidade das 5 tabelas de faixa | 2 → 0 |
| oráculo C8 | simulador com a 6ª faixa | 0 |
| oráculo C9 | custo do posto acompanha o anexo | 0 |

O arsenal foi de 97 para **99 travas**.

Uma nota sobre o C9: a asserção dele dizia *"o custo muda com o anexo (hoje III; com IV
seria maior)"* — e **reprovou o estado certo** assim que corrigi o cadastro. Ela codificava
o estado, não a regra. Reescrevi para o que o autor queria: o custo acompanha o anexo, seja
ele qual for. Régua que envelhece com o dado não é régua.

---

**Nenhuma nota fiscal foi emitida.** Mirante e Ideal Flores continuam com você, e o
cronograma de outubro está pronto e conferido para sair pelo Conecta PRO.
