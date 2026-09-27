# 27/09/2026 — o anexo errado, o cronograma que nascia à mão, e o que falta decidir

> ## ⚠️ ANTES DE TUDO (1) — cinco tributos VENCIDOS sem guia no sistema
>
> O gate fiscal caiu de 9 para 7 condições, e uma delas é esta:
>
> | empresa | tributo | venceu |
> |---|---|---|
> | Eletrônica | ISS | **10/09** |
> | Eletrônica | FGTS · INSS · IRRF | **20/09** |
> | Patrimonial | **DAS** | **20/09** |
>
> É a transição da Portte em tempo real: setembro venceu e ninguém subiu guia.
>
> **Atualização da tarde — o que já tem valor no sistema, para pagar:**
>
> | empresa | tributo | venceu | valor |
> |---|---|---|---|
> | Eletronica | FGTS 7/2026 | 2026-08-20 (38 dias) | R$ 133,60 |
> | Patrimonial | DAS 7/2026 | 2026-08-20 (38 dias) | R$ 17.048,87 |
> | Patrimonial | FGTS 7/2026 | 2026-08-20 | ~~R$ 7.883,53~~ **pago 19/08 (Cora, PIX)** |
> | Eletronica | FGTS RESCISORIO 8/2026 | 2026-08-21 (37 dias) | R$ 1.078,01 |
> | Eletronica | FGTS RESCISORIO 8/2026 | 2026-08-28 | ~~R$ 97,29~~ **pago 28/08 (Cora, PIX)** |
> | Eletronica | FGTS 8/2026 | 2026-09-18 (9 dias) | R$ 133,60 |
> | Patrimonial | FGTS 8/2026 | 2026-09-18 (9 dias) | R$ 7.981,94 |
> | Patrimonial | DAS 8/2026 | 2026-09-21 (6 dias) | R$ 18.399,33 |
> | | **total sem rastro de pagamento no extrato** | | **R$ 44.775,35** |
>
> Cruzei as oito com o extrato (Cora e Inter): valor exato, débito no dia — duas estão pagas
> (riscadas acima). As **seis restantes não têm rastro em conta nenhuma do sistema**.
> Vieram dos PDFs que a Portte deixou no Onvio (código de barras dentro da obrigação) — agora
> também **julho** e as **duas GFD rescisórias** (Daniel, Keyson). O calendário **não tinha FGTS
> nem CPP da Patrimonial**: as GFD dela de julho e agosto nunca apareceram como vencidas. Se
> algum destes já foi pago pela Portte, me diga qual — não há comprovante no sistema. Os três
> da Eletrônica (ISS, INSS, IRRF) seguem sem valor: não há guia deles em lugar nenhum do
> sistema. Você **não pagou** nenhum — multa e juros correm por dia.
>
> **Onde subir:** os PDFs das guias e dos comprovantes vão na pasta do Drive
> `Documentos Temporários/Setembro/` — o puxador `fiscal.sync_guias_drive` roda às **09:30 e
> 15:30**, classifica pelo conteúdo (nunca pelo nome) e preenche `fiscal_obligations` com valor,
> vencimento e nº do recibo; é isso que a condição 3 do gate lê. Se quiser antes do horário, me
> avise que eu disparo a tarefa. O **extrato do PGDAS-D** pode ir na mesma pasta, mas o puxador
> só reconhece guias (DAS, FGTS, INSS, ISS, DCTFWeb) — o extrato vai aparecer como
> "não classificado", e eu leio o RBT12 dele à mão e preencho `empresas.rbt12`; a cotação já
> está ligada a esse campo (commit `c6c1d789a`) e fica certa sozinha. Do segundo mês em diante,
> com o primeiro extrato real na mão, eu ensino o puxador a ler o RBT12 sem mim. Multa e juros
> correm por dia. Se a Portte pagou, preciso dos comprovantes; se não pagou, é a primeira
> coisa a fazer na segunda-feira — o DAS da Patrimonial em atraso é exatamente o padrão que
> a PGFN já cobra da Eletrônica.

> ## ⚠️ ANTES DE TUDO (2) — 8 pares de nota duplicada VIVOS no fisco, e cancelar tem prazo
>
> A varredura desta manhã passou a ver o que a conciliação de 24/09 tinha escondido sob o
> rótulo errado de `homologacao`. São notas de **produção**, emitidas **duas vezes** para o
> mesmo tomador, mesmo mês, mesmo valor — cada par cobra o cliente duas vezes, recolhe ISS
> sobre faturamento que não existiu e infla o DRE:
>
> | mês | tomador | valor | notas | CNPJ |
> |---|---|---|---|---|
> | 06/2026 | Laranjeiras Village | R$ 42.544,50 **×4** (excedente R$ 127.633,50) | 1, 2, 3 (Patrimonial) + 109 (Eletrônica) | os dois |
> | 06/2026 | Villa dos Pássaros | R$ 33.538,33 ×2 | 7, 9 | Patrimonial |
> | 06/2026 | Mirante das Flores | R$ 28.694,30 ×2 | 6, 10 | Patrimonial |
> | 06/2026 | Mirante das Flores (limpeza) | R$ 13.561,50 ×2 | 5, 11 | Patrimonial |
> | 03/2026 | Ideal Flores | R$ 60.904,25 ×2 | 33, 34 | Eletrônica |
> | 07/2026 | Parque Gelati | R$ 6.000,00 ×2 | 112, 115 | Eletrônica |
> | 06/2026 | Prime Arena | R$ 3.879,60 ×2 | 98, 100 | Eletrônica |
> | 08/2026 | Prime Arena | R$ 3.879,60 ×2 | 22, 25 | Patrimonial |
>
> Os de junho da Patrimonial entraram em **dois lotes** (08:30 e 09:30 de 26/09) com números
> diferentes: duas emissões reais. Eu **não lancei** nenhuma cópia no razão — lançar dobraria
> a receita. **Cancelar no fisco é ato seu, e o prazo corre.** O par do Laranjeiras é a decisão
> D6 do plano.

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

## 4. A cotação do WhatsApp estava 9% acima — e não dizia

O `pricing_cct` é o motor que replica sua planilha e alimenta as três portas vivas de
preço: a tela do CRM, o `/pricing/simular` e **o agente de WhatsApp que o José Luís usa**.

Ele soma os encargos da tabela `crm_pricing_params`, que é **uma tabela só para as duas
empresas** e guarda o conjunto de Lucro Real. E cobra os tributos por fora: PIS 1,65% +
COFINS 7,60% + ISS 5% = 14,25%.

A Patrimonial, que emprega os agentes, é Simples Anexo IV: encargo 55,44% (os 5,8% de
terceiros não são devidos) e os tributos vêm num DAS só.

Num AGP de piso R$ 1.670, jornada 30, margem 15%:

| | encargo | tributos | custo | **preço** |
|---|---|---|---|---|
| hoje | 61,24% | 14,25% | 4.118,23 | **5.820,81** |
| parâmetros certos | 55,44% | 9,19% | 4.014,10 | **5.294,95** |
| | | | | **−525,86 (−9,0%)** |

**Precisando o que eu disse acima:** esses 9,0% têm duas metades com solidez muito
diferente, e misturá-las seria vender confiança que eu não tenho.

| | preço | efeito | quão firme |
|---|---|---|---|
| hoje | R$ 5.820,81 | | |
| só o **encargo** corrigido | R$ 5.673,64 | −2,5% | **provado** — 61,24% × 55,44% vem da guia |
| encargo **+ tributos** | R$ 5.294,95 | −9,0% | depende dos 9,19%, que é uma das duas taxas que não batem entre si |

Os 9,19% saem do DAS de 08/2026 dividido pela receita do mês. A guia de 07/2026 dá 5,10%
pela mesma conta — são as duas guias incompatíveis do item (a). Então a **direção** está
provada e a **magnitude** não: o preço está alto em pelo menos 2,5%, e provavelmente mais,
mas quanto mais só o PGDAS-D responde.

E o endpoint devolvia um rótulo dizendo *"encargos por regime da empresa (revisão
multi-CNPJ)"* — que era **falso**. Rótulo afirmando o que o código não faz é pior que
rótulo nenhum: quem lê para de conferir.

### Não corrigi o preço, e quero que você saiba por quê

A metade do encargo eu sei. A metade dos **tributos** depende do RBT12, que está nulo e
cujas duas guias discordam (item (a) abaixo). Consertar metade moveria o preço para um
lugar que também não é o certo. E derrubar a cotação com uma recusa tiraria do José Luís a
única ferramenta de preço que ele tem no WhatsApp.

**O que fiz:** a ficha passou a dizer em voz alta de que regime são os parâmetros na mão de
quem cota. Hoje, na API:

> *"parâmetros de Lucro Real: a tabela soma 61,24% de encargo e esta empresa é 55,44%; os
> tributos saem por fora (PIS+COFINS+ISS) quando no Simples vêm num DAS só. Preço
> indicativo — confirmar antes de fechar."*

Com o PGDAS-D na mão eu acerto o número e o aviso some sozinho.

---

## 5. O LALUR existe agora — e R$ 88.926,17 param de se perder

Primeiro uma correção ao que eu te disse: **o prejuízo fiscal não serve para a PGFN.** A
Portaria 6.757/2022 art. 37 veda usá-lo em transação por adesão, que é como a dívida da
Eletrônica foi feita; o art. 46 exige dívida acima de R$ 1 milhão e a nossa é R$ 582.262,83;
e nos anos de Simples não se apura prejuízo, então o estoque só começa em 2026.

Serve para outra coisa, real: **reduzir o IRPJ e a CSLL futuros em até 30% do lucro
ajustado, sem prazo de validade.** E o parágrafo único do art. 15 da Lei 9.065/95 decide
tudo: o direito *"somente se aplica às pessoas jurídicas que **mantiverem os livros**"*.
Prejuízo sem livro é prejuízo que a fiscalização glosa.

O que o razão da Eletrônica diz hoje:

| | lucro | IRPJ |
|---|---|---|
| T1/2026 | R$ 48.383,04 | R$ 7.257,46 |
| T2/2026 | −R$ 88.926,17 | — |
| T3/2026 | −R$ 13.474,16 | — |
| **ano** | **−R$ 54.017,29** | |

Repare nos dois últimos: a soma dos trimestres é R$ 102.400,33 e o anual é R$ 54.017,29.
A tela mostrava as **duas** respostas, uma ao lado da outra. E o prejuízo de T2 **não
desfaz** o imposto de T1 — cada trimestre é período fechado.

Construí o livro (Parte A e Parte B, espelhando o Bloco M da ECF) e provei a trava ponta a
ponta, numa transação que desfiz em seguida:

```
saldo da Parte B antes ............ 0,00
registra o prejuízo do T2 ......... 88.926,17
compensar R$ 200 mil em T3:
   teto de 30% ......... 60.000,00
   disponível .......... 88.926,17
   COMPENSÁVEL ......... 60.000,00   ← cortado pelo teto, não pelo saldo
desfeito .......................... 0,00
```

### Não deixei o prejuízo registrado, e quero explicar

Registrar agora gravaria o prejuízo **contábil**, não o fiscal — sem a Parte A decidida os
dois são iguais, e não deveriam ser. Três linhas do seu razão precisam de decisão humana
antes:

| conta | valor | o juízo |
|---|---|---|
| provisões de férias e 13º | R$ 84.285,15 | o art. 13, I **veda** provisões mas **excetua exatamente essas duas**. Um sistema que adicionasse por regra de conta erraria R$ 84 mil |
| despesas financeiras | R$ 10.370,40 | dentro, **oito saques em Banco24Horas** de R$ 500 a R$ 1.000. Tarifa é dedutível; saque sem documento é o caso-escola da adição A.069 |
| DAS/parcelamento | R$ 2.699,58 | **um lançamento que precisa virar três**: principal dedutível, multa no A.154, juros dedutíveis |

Nenhum dos 202 códigos de adição é derivável do plano de contas, porque a pergunta não é
contábil: `A.069` é *"despesas que não sejam consideradas **necessárias**"*, e "necessária"
não é campo. A ECF de 2026 vence em **julho/2027** — há tempo de decidir direito, e nenhum
motivo para eu gravar um número que vai mudar.

O campo `prejuizo_fiscal_compensavel` virou `prejuizo_contabil_do_periodo` — as duas
palavras estavam erradas — e o card agora mostra o estado do livro ao lado do número:

> Prejuízo contábil do período — R$ 54.017,29
> **Parte A do LALUR — não fechada: o número acima é do RAZÃO, não a base tributável**

**Ressalva:** os números de linha do Bloco M que gravei vêm do manual do Leiaute 10
(2023). São estáveis há anos, mas precisam de reconferência contra o manual de 2026 antes
da entrega da ECF.

---

## 6. Segunda rodada: a fila do LALUR, o preço com o encargo certo, e o balanço que estava vermelho desde 23/09

**A fila de revisão existe.** `fila_de_revisao` lista as despesas do período sem decisão,
por valor decrescente — no T3/2026 da Eletrônica são **746 linhas, R$ 166.563,74**, e o
topo são as notas da Sólides. `decidir` grava uma a uma e exige o código do Anexo para
adição/exclusão. O desenho central é um terceiro estado, *decidido dedutível*: sem ele,
"não revisado" e "revisado e dedutível" seriam a mesma coisa, e o não previsto falharia
aberto — que aqui significa subtributar.

Achei e corrigi três defeitos meus antes de assar: a fila incluía 13 lançamentos de ISS
(R$ 8.057,34) que a apuração exclui; o livro aceitava "ano inteiro" como período no Lucro
Real trimestral (a porta pela qual as duas respostas na mesma tela voltariam); e eu tinha
declarado o vínculo com o lançamento como UUID quando o id é inteiro.

**O encargo da cotação agora é o da empresa.** R$ 5.820,81 → **R$ 5.673,64** no AGP de
piso — a metade provada. O aviso encolheu para o que sobra (os tributos, que dependem do
RBT12). Junto, um defeito meu de algumas horas antes: eu tinha feito a rota de cotação
abrir ~20 conexões síncronas por requisição; agora é uma consulta assíncrona e função pura.

**O balanço.** Estava vermelho desde 23/09 e ninguém tinha olhado o motivo. Hoje eram 3
invariantes: junho e julho da Patrimonial "com resultado em aberto", e o DRE discordando
do PL em R$ 127.783,81 e R$ 6.038,62. Causa: os lançamentos que eu corrigi nesses meses
(fornecedor em dobro, receita pelas notas) não tinham sido encerrados contra o PL. O
preview da re-apuração devolveu as duas diferenças **centavo a centavo**. Apliquei a
complementar: **3 → 0, DRE = PL nos dois meses.**

---

## 7. A primeira varredura completa do dia, lida sem desconto

Rodei as 99 travas sobre o estado final. Cinco apontaram regressão. Lidas uma a uma:

| trava | de → para | o que é de verdade |
|---|---|---|
| `checar_nota_duplicada` | 0 → 8 | **notas reais, vivas no fisco**, que a conciliação de 24/09 tinha carimbado de `homologacao`; minha correção do `ambiente` as trouxe de volta. Não é regressão de código — é a trava finalmente enxergando. Tabela no topo deste relatório. **Cancelar tem prazo.** |
| `checar_receita_nao_lancada` | 4 → 15 | 9 "nunca lançadas" são **as cópias dos pares duplicados** — não lançar é o certo. 3 "competência diferente": 109 e 111 são a decisão da migração de 13/08 (serviço de junho) contra o razão de julho **congelado** da Eletrônica — permanente por desenho; a **32** eu corrigi (abaixo). 3 de homologação de jan/fev: antes do corte, registro e não pendência. |
| `checar_transitoria_aberta` | 6 → 11 | R$ 701,60 em PIX miúdos do extrato de hoje. Operacional, decidir por contraparte. |
| `checar_custo_recorrente_nao_mapeado` | 37 → 49 | fornecedores que cruzaram o limiar de recorrência com setembro. Operacional; cinco estão "parados" há 50–114 dias e são decisão sua (encerrar ou atraso). |
| `checar_batida_faltando` | 114 → 116 | ponto — outra sessão. |

**As outras vinte, lidas uma a uma.** Nenhuma é defeito de código meu. As de ponto, CRM,
WhatsApp, `chave_pix`, `capacidade_sem_botao`, `beat_engole_falha`, `varchar_teto`,
`id_tipo_divergente`, `irreversivel` (whatsapp:9136) são da outra sessão ou operacionais.
`uso_real +34` inclui as duas tabelas do LALUR, nascidas hoje e vazias **de propósito**
(registro pendente da Parte A). `data_do_banco_no_fuso` é um R$ −200 que cruza a virada de
julho/agosto — decisão sua de competência. `oraculo_externo` são as declarações Portte/Cora.

**Duas réguas que reprovavam o certo, consertadas:**
- o oráculo `v5_fiscal_relatorios` exigia `<cNBS>120032900</cNBS>` fixo no XML da NFS-e. A
  outra sessão removeu esse código em 24/09 com razão (era "instalação de maquinários" indo
  em nota de vigilância); meu bake de hoje foi o primeiro a levar a mudança ao container, e
  a régua velha gritou. Agora afirma a regra nova: sem NBS no cadastro, sem tag.
- o `checar_regressao` procurava `test_oraculo_x4/y1/y2` em `qa/` quando vivem em `orq/`:
  **três dias "NÃO VERIFICADO"** em silêncio (pareador único, espelho da régua, direção da
  batida). Caminho corrigido.

**Três oráculos que ninguém verificava há três dias** (`x4` pareador único, `y1` espelho
da régua, `y2` direção da batida): o executor procurava em `qa/` e depois os rodava no host
sem `core`. Rodados direto no container: `x4` 0, `y2` 0, **`y1` com 2 desvios** — é ponto,
da outra sessão; fica registrado aqui e passa a aparecer na varredura noturna.

**Uma terceira régua envelhecida:** `test_oraculo_periodo_fechado` julgava tudo pelo corte
global (01/08) e acusou 52 lançamentos "de período fechado alterados" — todos da
Patrimonial, cujo corte é 01/06, e nenhum anterior a ele. Agora julga pelo corte da empresa:
52 → 0.

**Uma quarta régua envelhecida, à tarde:** a condição 7 do gate acusava a busca de certidões
como "roda e não produz" medindo a data da última renovação — e renovar depende dos portais,
que hoje recusam este servidor. A task passou a gravar em `system_configs` a data da
**tentativa** e o motivo de cada portal (`ged.certidoes.ultima_tentativa`), e a régua lê
isso. Quem abrir a chave vê: *"Caixa RECUSOU (HTTP 403, WAF)… TST exige captcha…"* — sem
precisar de log de container, que cada bake zera.

**O gate fiscal 9 → 7.** Uma condição é o v5 acima. A outra é a tabela de tributos vencidos
sem guia no topo deste relatório — e essa é sua, urgente.

**A nota 32 (Ideal Flores, R$ 65.842,42).** Emitida em 02/09, o fisco carimba setembro. Mas
na Patrimonial o Ideal Flores tem junho (nº 4), julho (nº 21) e **nenhuma nota de agosto**:
a 32 é agosto, pela mesma prova aritmética que a migração usou nas 109/111. Corrigi a
competência para 08/2026 guardando o setembro do fisco em `competencia_origem_adn`. E fechei
o buraco que faria o conserto morrer às 05:30: o upsert da conciliação sobrescrevia a
competência corrigida com a do fisco — agora respeita o marcador da migração.

**As duas dicas do caçador mentiam:** diziam "corte 01/08/2026" fixo (o corte é por empresa
desde 26/09) e "sai sozinho no próximo fechamento" para linhas de jan/fev que estão antes
do corte e nunca sairão. Corrigidas.

---

## 8. O que está no ar às 11:30 de 27/09 — e como chegou

Nove commits, cada um assado com blue/green, md5 imagem × disco conferido e drift zero. O
último bake foi **morto pelo guarda de memória do harness** no passo 2 (blue + green + build
+ SOPHIA indexando + duas sessões Claude); a produção nunca saiu do ar, o green ficou órfão
já saudável na imagem nova, e retomar o script fechou em 7 minutos. Lição gravada.

| commit | o que | provado por |
|---|---|---|
| `e3cceab5b` | cronograma de notas nasce do contrato | out: 11 propostas, 0 divergências |
| `c85fad374` | anexo III→IV, typo 13,20%, 6ª faixa | guia sem 1006; posto R$ 3.059 → 3.472 |
| `08c6a4af4` | cotação diz de que regime são os parâmetros | aviso nos 2 endpoints |
| `31db3e5cc` | LALUR Parte A/B, trava dos 30% | R$ 200k → R$ 60k pelo teto |
| `f7335e237` | deploy para em conflito; M410 idempotente | abort nomeado; 3 chamadas = 1 |
| `5231e7052` | fila do LALUR (`D`, ISS fora, ano recusado); encargo da empresa | preço 5.820 → 5.673; balanço 3 → 0 |
| `8d6778848` | conciliação honra a competência corrigida; folha real na tela; card conta 3.010; réguas v5 e executor | receita 15 → 14; 6/7 contratos com folha real |
| `84ea13ec5`… | relatório e correções ao plano | — |

No ar e verificados de fora na imagem final: t3, v5, C10, C9, balanço, `receita_nao_lancada`
em 14, e a aba «Custo por contrato» com a folha real de 08/2026 em 6 dos 7 contratos.

A varredura noturna das 00:00 vai regravar a linha de base. O que ela vai absorver como
novo nível é o que está atribuído na §7 — nada disso é silêncio: a decisão de deixar
crescer está escrita nos commits `8d6778848` e neste relatório.

---

## 9. Tarde de 27/09 — pronto para receber o que você vai subir

**A cotação está ligada ao RBT12.** Quando o PGDAS-D chegar, eu leio o RBT12 e preencho
`empresas.rbt12`; a partir daí a cotação usa a alíquota efetiva do DAS **sozinha** — sem
mexer em código — e o aviso na ficha some. Provado: com 9,19% o AGP de piso dá R$ 5.294,95.

**Os comprovantes entram pelo Drive** (`Documentos Temporários/Setembro/`, puxador às 09:30
e 15:30) e a condição 3 do gate fecha pelo caminho normal.

**A tela «Revisão do LALUR» existe** — menu *Fiscal & Contábil*. O contador vê as 753
despesas do trimestre sem decisão, por valor, e decide linha a linha: dedutível, adição ou
exclusão, com o código do Anexo obrigatório para as duas últimas. A tela recusa o que não se
defende (sem código, sem histórico) e não sugere código — oferece. Cada decisão entra no
livro com quem decidiu e quando. Provada de fora, decisão por decisão, e vigiada pelo oráculo.

**O que o contador precisa saber para começar:** as três linhas que exigem juízo (§5 —
provisões, os saques em Banco24Horas, o DAS que vira três) estão na fila; ele começa pelo
topo, que é o dinheiro.

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

### e) Mirante das Flores: o aditivo da limpeza e um par duplicado a mais

Eu tinha escrito aqui que "a limpeza não está no contrato" — **errado**: ela existe como
contrato próprio, CTR-2026-00016, R$ 12.061,50. O que `checar_contrato_vs_nota` acusa
(contrato R$ 40.755,80 × nota R$ 52.817,30) é uma nota de limpeza **a mais** no mês — mais
um par duplicado, do mesmo lote de junho. E o valor da nota (R$ 13.561,50) é o reajustado,
enquanto o contrato ainda diz R$ 12.061,50: é o aditivo que você disse que falta assinar.
Com o valor do aditivo eu atualizo o CTR-00016 e o cronograma de outubro sai certo.

### f) O sino cortou os avisos de guia em 26/09 — porque ninguém lia

`checar_sino_surdo` mede: origem com ≥ 30 envios em 30 dias e menos de 2% lidos é "surda",
e depois de 14 medições seguidas o sistema **corta sozinho** (gatilho antes do INSERT — nenhum
produtor precisa saber). Em 26/09 ele cortou `fiscal_guia`, junto com `ged_kit_completo`,
`radar_fornecedores` e `triagem_ponto_hermes`. Os cinco tributos vencidos são de antes do
corte — mas **a partir de 26/09 nenhum aviso de guia chega a ninguém**, e o próximo
vencimento vai passar em silêncio de novo.

Religar é `--religar fiscal_guia` e é ato seu, não meu: religar um sino que você não abre só
recria o ruído que o cortou. A pergunta real é **por onde você quer ser avisado de guia
vencendo** — o sino do sistema (e então abri-lo) ou o WhatsApp, que você já lê. Com a
resposta eu ligo a origem no canal certo.

### g) O CRF/FGTS da Patrimonial vence em 04/10 e o robô não consegue renovar

Rodei a busca de certidões à mão: a Caixa **recusa o IP deste servidor** (HTTP 403, WAF) e a
CNDT do TST exige captcha de imagem. A certidão de FGTS da Patrimonial — a que o
contratante cobra para pagar a fatura e que a licitação exige — **vence em 7 dias**, e a
renovação automática está barrada. Renove pelo site da Caixa da sua máquina (ou de qualquer
IP que não seja o do servidor) e suba o PDF no Drive; o puxador reconhece pelo conteúdo.

Também vencida: a **certidão de falência** da Patrimonial (18/09) — a régua do gate não a
exige, mas edital de licitação costuma exigir. E três da Eletrônica (municipal 01/09, CRF
17/09, estadual 18/09), que ficam fora da régua **pela sua decisão de 19/08** (a Eletrônica
não presta mão de obra); registro, não pendência.

**Por que ninguém avisou:** a task de alerta de vencimento estava agendada para uma fila que
nenhum worker escuta — 68 disparos diários mofando no Redis desde julho. Corrigido (fila,
commit `e54cc8083`), purgado, e um disparo manual consumido. E a task lia uma tabela **vazia**
(o DMS genérico aposentado em 08/09) com casamento de dia exato — reescrita para ler
`ged_certidoes` pelos CNPJs do grupo: **seis alertas no sino agora** (CRF da Patrimonial em
7 dias, estadual em 21, quatro vencidas). Detalhe que quase escondeu a Patrimonial de novo:
todas as certidões dela estão com `alerta_ativo = false` — a flag não é régua.

### h) «O robô devia puxar tudo do governo» — ele não puxa, e é preciso dizer isso sem rodeio

Medi as integrações que você acredita que existem:

| integração | o que devolve hoje |
|---|---|
| `DCTFWebManager.consultar("2026-08")` | `"situacao": "consulta_pendente", "mensagem": "Implementar consulta via e-CAC"` |
| `SimplesNacionalManager.consultar_das_emitidos(...)` | `[]` |
| FGTS Digital / e-CAC | mesma casca: assinatura pronta, corpo por fazer |

São **esqueletos** — nome, parâmetros e docstring, sem nada que chegue ao governo. E os
portais bloqueiam servidor: a Caixa devolve 403 ao nosso IP, o TST exige captcha. O caminho
real para "puxar tudo" é a **API oficial do SERPRO (Integra Contador)** — paga, por
contrato, cobre DCTFWeb, PGDAS-D/DAS, e-CAC e procurações — ou um serviço tipo Infosimples.
Não é patch; é projeto, e precisa de decisão sua (custo mensal).

**Os certificados:** `certificado.pfx` abre (só em modo *legacy* do OpenSSL) e é o
**e-CPF de JORDAN SANTOS**, válido até **13/01/2027** — não é e-CNPJ. Para DCTFWeb, e-CAC e
FGTS Digital ele só vale com **procuração eletrônica** outorgada por cada CNPJ ao seu CPF
(no e-CAC). O `patrimonial.pfx` **não abre com a senha configurada** — a Patrimonial está
sem certificado utilizável no sistema; se a senha for outra, ela precisa entrar no `.env`
(`.env` é zona que eu não edito).

**O que dá para fazer hoje, sem governo:** os PDFs que a Portte deixou no Onvio já estão no
nosso disco. Estou ligando o parser (que hoje só olha o Drive) neles: o **DAS da Patrimonial
(R$ 18.399,33, venceu 21/09)** e as **duas GFD do FGTS (R$ 133,60 Eletrônica; R$ 7.981,94
Patrimonial, venceu 18/09)** entram em `fiscal_obligations` com valor, vencimento e código
de barras — para você pagar. Os DARFs de INSS/IRRF e o ISS da Eletrônica **não** têm valor em
lugar nenhum do sistema: precisam da guia (Portte/Onvio) ou do SERPRO.

**E o calendário estava cego para a Patrimonial:** não tinha linha de FGTS nem de CPP
(Anexo IV paga a patronal por DARF via DCTFWeb) — os vencidos dela nem apareciam como
vencidos.

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

### E isto não é curiosidade — o RAT está DENTRO do preço de hoje

Conferindo o meu próprio trabalho desta noite: os **55,44%** que passaram a precificar cada
posto são `Anexo III (32,44%) + CPP 20% + RAT 3%`. O RAT 3% está lá dentro. Se o nosso RAT
for 2%, o encargo certo é 54,44% e o custo por posto é R$ 3.454,14, não R$ 3.472,09 — uma
diferença de R$ 17,95/posto/mês que eu estaria embutindo sem base.

Não é erro do que fiz (3% é o valor de grau de risco 3, que é o de vigilância/portaria, e é
o que seis dos nove lugares do código dizem). Mas é uma **dependência que eu não tinha
declarado**, e declarar dependência é metade do trabalho.

Piora um pouco: o RAT efetivo é `RAT × FAP`, e o FAP varia de 0,5 a 2,0 por empresa. Mesmo
sabendo o grau de risco, sem o FAP o número não fecha. E não existe coluna de CNAE no
cadastro para eu nem começar a inferir.

**Uma pista que apareceu no fim do dia:** o texto de `fonte_regime` da Patrimonial (escrito
em 12/09 por outra sessão) cita **CNAE 8111-7/00** — serviços combinados de apoio a edifícios,
não vigilância. Se esse for o CNAE do cartão CNPJ, o grau de risco é **2**, o RAT é **2%**, e
os 55,44% que hoje precificam viram **54,44%**. É pista de texto livre, não documento: o
cartão CNPJ ou o S-1000 decide. (O mesmo texto dizia "Anexo III"; corrigi para não
contradizer o campo.)

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
