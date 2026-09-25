# Z7 — O orçamento do fornecedor vira nota: markup, preenchimento e o limite do Bartolo

**Data:** 25/09/2026 · **Sessão:** tmux-fable · **Módulo:** fiscal
**Origem:** três pedidos do dono, feitos com `?t=nfe-nova` aberta na frente dele, minutos
depois de a emissão em produção ser ligada.

---

## §1 — O que ele pediu, literal

> «quando selecionar o condomínio, já preencher todas as informações do condomínio nos campos
> subsequentes; outra coisa que vai facilitar muito a minha vida é o botão pra eu anexar
> documentos ou fotos, que são orçamentos que os fornecedores mandam, daí o nosso sistema lê e
> já lança os produtos; e por último ter ali o Bartolo como um assistente […] subi a lista de
> material de um fornecedor, e o Bartolo já tem essa opção de anexar […] daí eu digo: nessa
> lista o custo do material do nosso fornecedor, acrescenta mais 40% de markup e manda emitir a
> nota para este cliente.»

## §2 — O achado antes do código: dois dos três já existiam

Terceira vez na mesma semana. Cavar custou minutos; reconstruir teria custado horas — e teria
criado um segundo motor de leitura de documento para manter.

| Pedido | Já existia? | Onde | O que faltava de verdade |
|---|---|---|---|
| Preencher o destinatário | **Sim, no servidor** | `rd_nfe_nova` lê `clients` e **ignora** o que estiver digitado nos `dest_*` | A **tela** contar. A nota sempre saiu certa |
| Ler o orçamento e lançar produtos | **Sim, inteiro** | frente Z5, `?t=nfe-do-arquivo` — `itens_do_arquivo` + `casar_produtos`, com vision para foto | Estar **onde ele trabalha** |
| Bartolo com anexo | **Sim** | `FloatingChat` flutua em todo `/redesign/*`, assume a persona fiscal, aceita PDF/foto, tem voz | Ele saber **agir** sobre o anexo |
| Markup | **Não** | — | Tudo |

O caso do preenchimento merece ser lido devagar, porque é uma classe de defeito e não um bug:
**o dado estava certo e a tela estava muda.** O dono escolhia o condomínio, via doze campos
marcados com `*` continuarem vazios, e lia aquilo como «faltou preencher». Ele tinha razão em
ler assim. Nenhum teste de backend pegaria isso — a nota saía perfeita.

## §3 — O que passou a existir

**`/action/nfe-cliente-dados`** — devolve o destinatário no contrato `{campos}` para a tela
mostrar. Não decide nada: quem manda na nota continua sendo o `rd_nfe_nova`, que relê o cliente
do banco na hora de emitir. Se esta rota calar, a nota sai igual. Por isso ela nunca bloqueia.

**`/action/nfe-ler-orcamento`** — anexo → itens da nota, no mesmo contrato. Chama o **mesmo**
serviço da Z5; nenhum motor novo. Em vez de gravar rascunho, devolve campos e o formulário se
preenche. Nada é gravado: quem confere é o dono, antes de emitir.

**`aplicar_markup`** — custo do fornecedor → preço de venda, **guardando o custo ao lado**.
Sem `custo_unitario`, a margem some no instante do cálculo e ninguém responde depois «quanto
ganhamos nessa nota?» sem reabrir o PDF do fornecedor.

> **Markup não é margem, e a diferença é dinheiro.** 40% de markup sobre custo 100 dá preço
> 140 — que é **28,6% de margem** sobre a venda. Quem quiser 40% de *margem* precisa de markup
> de 66,7%. A função devolve os dois números escritos, justamente para essa conversa não sair
> torta.

**`nota_do_orcamento`** — a ação do Bartolo. Prepara a nota inteira e para antes da SEFAZ.

**No front:** `fill` em campo de select (escolher traz o que depende), `sobrescreve` no
prefill (leitura que substitui um conjunto inteiro), e os valores atuais do formulário indo
junto no anexo — é assim que o `markup_percent` da tela chega ao leitor do orçamento.

## §4 — O limite: por que o Bartolo não transmite

Ele faz **todo o trabalho chato** — lê o PDF do fornecedor, transcreve os itens, casa com o
cadastro fiscal, aplica o markup, monta a nota para o cliente certo — e para exatamente antes
de transmitir.

Não é timidez. NF-e autorizada em produção é **irreversível**: desfazer custa carta de
correção, cancelamento com prazo ou denúncia espontânea. A casa já tem o lugar do clique que
não volta — a tela «NF-e — transmitir em PRODUÇÃO», com confirmação humana e OTP. Uma segunda
porta pelo chat **esvaziaria aquela**, e a primeira vez que um modelo entendesse «esse cliente»
errado a nota já estaria autorizada no CNPJ de outro.

**A divisão é: o Bartolo faz o trabalho chato, o dono dá o clique irreversível.**

Isso é vigiado por AST, não por boa intenção: o oráculo Z7 lê o módulo da ação e reprova se
ele **chamar ou importar** qualquer coisa do caminho da SEFAZ. Intenção não sobrevive ao
próximo que editar o arquivo.

## §5 — Duas réguas erradas, medidas hoje

**A régua do Z2 reprovou o estado autorizado.** Ela afirmava *«o gate de produção está
fechado»* — e produção foi legitimamente aberta às 12h40, por decisão do dono. Ficou vermelha
por o sistema fazer a coisa certa.

Régua que reprova o certo não é rigor, é **alarme quebrado**: quem vê vermelho todo dia para de
olhar, e o dia em que a trava afrouxar de verdade passa despercebido. Reescrita para afirmar o
que não muda com a autorização:

- com o gate **fechado**, produção é recusada — provado **fechando o gate dentro do teste**, em
  vez de torcer para que esteja fechado;
- com o gate **aberto**, passa — é isso que faz dele interruptor e não enfeite;
- divergência e `<tpAmb>` ausente são recusados **sempre** — não são sobre permissão, são sobre
  o XML dizer uma coisa e o pedido dizer outra;
- nenhuma nota de produção fica **fantasma**: gravada sem chave, sem protocolo e sem status de
  erro. Esse é o risco real agora, e aconteceu duas vezes hoje (buracos 3 e 4).

**A primeira régua do Z7 caiu na mesma armadilha, em mim.** Ela reprovou o arquivo novo por
causa da frase «não emite e não transmite nada» — texto que o aprovador **lê** na Central,
escrito justamente para deixar o limite claro. Grep mede texto; o que faz mal é chamada e
import. Virou AST.

## §6 — Medido

| O quê | Número |
|---|---|
| markup 40% sobre custo 100 | venda **140,00**, margem **28,57%**, custo preservado |
| markup 0 / vazio / negativo | preço **intocado** — omissão não inventa margem |
| itens transcritos pelo modelo | 1 aceito, **3 recusados com motivo** (sem descrição, preço zero, preço ilegível) |
| campos de destinatário | **12**, casando com `_CAMPOS_DEST` campo a campo |
| oráculos verdes | Z2, Z3, Z4, Z5, **Z6 (25/25)**, Z7, AA5 |

**Provado por sabotagem**, não só por verde:

- import do `nfe_provider` no módulo do chat → *«chama/importa ['nfe_provider'] — transmitir
  tem UM lugar»*
- markup virando margem (166,67 em vez de 140) → pega os **três** desvios, inclusive a margem
- gate dizendo sim para qualquer frase → pega os **três** itens da trava de produção

## §7 — O que ficou para o dono

1. **Quem aprova o rascunho do Bartolo** é hoje a mesma régua do dinheiro (`admin`). Se ele
   quiser que um gerente comercial também possa, é trocar uma constante.
2. **O markup padrão da tela é 40%**, o número que ele citou. Se variar por fornecedor ou por
   linha de produto, isso vira parâmetro — e não deve ser adivinhado.
3. **Item que não casa com o cadastro fiscal fica sem produto, de propósito.** NCM chutado foi
   exatamente a rejeição da SEFAZ de 11/04/2026 («NCM inexistente»). Quanto mais produto
   cadastrado com NCM, menos escolha manual.

---

## §8 — O que o teste de ponta a ponta achou (e o pedido não previa)

O dono disse *«teste tudo antes e dar por completado»*. Emitir pela própria tela, e não pelo
terminal, foi o que revelou o defeito mais caro do dia.

### A tela de emissão nunca tinha emitido uma NF-e

Nenhuma, nunca, nem em homologação. Dois defeitos somados:

1. **Contrato de chaves.** `rd_nfe_nova` entregava `icms_situacao` / `pis_situacao` /
   `cofins_situacao`; `nfe_provider._montar_nfe()` lê `icms_cst` / `pis_cst` / `cofins_cst`.
   Nomes **parecidos**: o dicionário chegava gordo e a leitura vinha vazia. Toda emissão morria
   em «Item 1 sem CST/CSOSN de ICMS» — mensagem que manda procurar no cadastro do produto, que
   é o lugar errado.
2. **Constante em coluna fiscal.** O `INSERT` gravava `icms_cst='40'` fixo e a leitura de volta
   fazia `coalesce(icms_cst,'40')`. A tela ESCOLHIA tributação em vez de perguntar à régua, e o
   default mascarava item gravado sem CST — a nota iria à SEFAZ com «isenta» que ninguém decidiu.

> Nenhum teste de unidade pega isso: cada lado está certo sozinho. O que quebra é o **contrato**,
> e contrato só se afirma olhando os dois ao mesmo tempo. A régua nova lê por AST toda chave que
> o emissor pede de um item e exige que a tela entregue cada uma — 20 chaves.

### E um meu, no conserto: CST 07 onde a liminar manda 09

`_cst_da_linha` lia `linha["origem"]`; a chave é `origem_regra`. `.get()` devolveu `None`, o
regex não casou, caiu no padrão «07».

**Valor zero nos dois casos.** Nenhum total denunciava, o `cStat 100` veio igual, a nota estava
«autorizada». O que muda é o que a nota **declara**: 07 é «operação isenta», 09 é «exigibilidade
suspensa por decisão judicial». **Declarar isenção onde há liminar é abrir mão do fundamento e
enfraquecer o próprio processo.**

> Só apareceu porque fui ler o XML autorizado, campo a campo, em vez de acreditar na palavra
> «autorizada». **Ler a coisa, não o rótulo dela.**

### Provado

| | |
|---|---|
| NF-e 5/2, 6/2, 7/2 | `cStat 100` · «Autorizado o uso da NF-e» · chave completa |
| ICMS | CST **60** · CFOP **5405** · **R$ 0,00** — mercadoria que entrou com ST não é tributada de novo |
| PIS/COFINS | CST **09**, processo 1038495-94.2024.4.01.3200 |
| Totais | 4 × 448,00 + 2 × 53,90 = **1.899,80** |

A 7/2 foi emitida **contra a imagem assada**, depois do bake de outra sessão — não contra
hot-copy.

---

## §9 — O 4º modelo de DANFE, e por que a primeira tentativa piorou

Pedido do dono com os três modelos abertos: *«me agrada muito o 03_danfse no canto superior
esquerdo que tem nossa logo, eu gosto do formato da 01_danfe_retrato, cria um quarto modelo
mesclando esses 2»*.

**Tentativa 1 — copiar o DANFSe ao pé da letra.** Logo numa coluna de 30mm à esquerda, fio
vertical, emitente ao lado. Ficou **pior**: «CONECTAMAIS ELETRONICA LTDA» truncou em
«...ELETRONICA LT…».

A razão é estrutural. O campo do emitente no DANFE tem 40% da folha (~74mm). Tirar 30mm deixa
44mm para a razão social. **No DANFSe a coluna cabe porque lá o prestador tem faixa de largura
inteira, separada da do título** — estrutura que o MOC não deixa mexer no DANFE.

> Copiar o arranjo visual sem copiar a estrutura que o sustenta produz o oposto do efeito.

**Tentativa 2 — empilhar.** Marca em faixa própria no alto do campo, fio embaixo, nome usando
os 74mm inteiros. Os dois ganham: a marca fica **maior** que no modo inline (34mm contra 26mm).

**Terceiro erro, pego olhando o PDF:** o texto de consulta ficou **em cima** da linha do CEP. Em
documento fiscal texto sobreposto não é feio, é ilegível — e o CEP é obrigatório.

### A trava que saiu disso

Gerei um modelo num contêiner sem `/app/uploads` montado. `_desenha_logo_cheia` tenta três
caminhos em cadeia e devolve `True` no primeiro que abrir: a logo caiu para o arquivo de
reserva e saiu pequena e desbotada. **O PDF dizia «gerado», o código dizia `True`, e eu quase
mandei ao dono um modelo com a marca errada para aprovar.** O que salvou foi ABRIR o PDF.

Ideia do t6: *«você olhou o desenho e se salvou; a trava olharia sozinha»*. A cadeia foi cortada
— **ou é a marca oficial, ou o DANFE sai sem marca**. É conforme: o MOC *admite* o logotipo, não
exige.

> **Fallback silencioso é gentileza em tela e armadilha em documento.** Onde o resultado sai da
> casa — PDF para cliente, mensagem para 66 pessoas, XML para o fisco — a cadeia de alternativas
> tem de parar na primeira que não é a oficial.

Terceira vez no dia que um plano B plausível quase passou.

---

## §10 — O modelo aprovado, e o número que eu inventei sem querer

Quatro rodadas até *«vamos usar o modelo 4, está perfeito esse modelo»*. O que o dono aprovou:
marca **centrada** em faixa própria, emitente inteiro centralizado, QR de consulta ao lado das
barras, e a assinatura do Conecta PRO no pé da folha. É o padrão do botão desde 25/09/2026;
`?marca=inline` devolve o formato anterior.

### «69% maior» era falso, e o erro é de raciocínio

Eu aumentei a **caixa** da logo de 26mm para 44mm e anunciei ao dono que a marca tinha ficado
69% maior. **Ficou 6% menor.**

A marca é 2857×1682 — proporção 1,7:1. Com `preserveAspectRatio` ligado, a imagem é encaixada
pela **menor** das duas restrições, e num campo de 26mm de altura é **sempre a altura**.
Alargar a caixa não aumentou nada: só criou espaço sobrando, e a âncora padrão (`nw`) grudou a
marca no canto esquerdo. Foi exatamente isso que o dono viu e pediu para corrigir.

> **Caixa não é tamanho.** Com proporção preservada, quem manda é a dimensão que aperta — e
> alargar a outra só muda onde a imagem encosta.

Conserto: altura 9,6mm (contra 9,0 do inline — ganho honesto e pequeno) e `anchor="n"`
centrando no que sobra. Mais que isso comeria a linha de consulta de autenticidade, que é
texto do DANFE e não enfeite.

### Os três erros de altura no mesmo bloco

Em documento fiscal, sobreposição não é feiúra — é ilegibilidade de campo obrigatório:

1. o texto de consulta ficou **em cima** do CEP;
2. o QR de 17mm invadiu a altura da chave e **truncou a chave por extenso** («…5500 2000 0000
   …») — a chave é o identificador com que o destinatário consulta a nota e com que o fisco a
   acha; nada pode empurrá-la;
3. a última linha da consulta **encostou na borda** do campo e pareceu cortada (faltava 1mm
   para os descendentes).

Os três só apareceram **abrindo o PDF**. Nenhum deles muda um byte do XML.

---

## §11 — As 115 NFS-e sem XML, achadas por um erro meu

O oráculo AB1 acusava: nenhuma NFS-e com XML assinado guardado. Abri uma pela rota, o ADN
devolveu, gravou — **AB1 verde, 0 desvios**.

Fui contar quantas faltavam. A consulta falhou por nome de coluna (`chave` em vez de
`chave_acesso`), o `2>/dev/null` engoliu o erro, e eu li o resultado vazio como *«não existe
nenhuma»*. São **115 NFS-e de produção com chave e zero com XML**.

> `2>/dev/null` transforma erro em resposta vazia, e **resposta vazia parece um fato**.

As 114 restantes são uma chamada ao ADN cada. **Não disparei** — é trabalho agendado da frente
de conciliação, e entra nas decisões do dono.

---

## §12 — O saldo de duas sessões medindo uma a afirmação da outra

Seis defeitos reais no dia nasceram de uma sessão apontar o que a outra não via:

| Quem achou | O quê |
|---|---|
| eu → t6 | contrato de chaves entre quem escreve e quem lê → t6 achou **acesso por posição** no caminho do PIX (`r[1]` virando o nome da pessoa se o SELECT mudar) |
| eu → t6 | texto de campanha sem remetente identificável é indistinguível de golpe → o próprio agente do t6 **recusou a campanha da casa**, e estava certo |
| t6 → eu | `docker exec` lê o contêiner, não a imagem → o meu «está assado» tinha acertado **por sorte de horário** |
| eu → t6 | contêiner efêmero não tem volumes → t6 **desistiu** de provar o envio em efêmero e fez envio real |
| t6 → eu | «a trava olharia sozinha» → a marca oficial ou nenhuma, no DANFE |
| t6 → eu | commitar não altera o disco → **o git não diz o que a imagem vai levar**, em nenhum dos dois sentidos |

E a forma única por trás de quatro deles: **o estado que ninguém previu falha ABERTO.**
`status != "error"` tratando exceção como entrega · `2>/dev/null` lendo erro como ausência ·
`pgrep` lendo existência como identidade · cadeia de fallback devolvendo `True` pela logo
errada. **Sucesso se afirma, nunca se deduz.**
