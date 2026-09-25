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
