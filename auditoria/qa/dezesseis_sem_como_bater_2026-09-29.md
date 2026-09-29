# 16 de 66 ativos nunca tiveram UMA batida medida — e estão sendo chamados a assinar o espelho

**Medido em 29/09/2026.** Achado ao investigar por que o aviso diário de assinatura tinha
subido de 9 para 23 pessoas. E confirmado, no mesmo dia, pelas próprias pessoas no WhatsApp.

## O número

**16 dos 66 colaboradores ativos** (24%) não têm **uma única** batida de fonte medida
(`mobile`, `contingencia`, `facial`, `biometria`, `app`, `relogio`) em toda a vida no sistema.

E entre quem tem pedido de assinatura de espelho de agosto pendente:

| dias medidos em agosto | pessoas |
|---|---:|
| **ZERO** | **22** |
| 1 a 5 | 7 |
| 6 a 15 | 20 |
| mais de 15 | 15 |

**29 de 64 pessoas** estão sendo convidadas a assinar uma folha de ponto praticamente vazia.

## Os 12 do Conecta Village

Doze delas são um grupo só, e a história fecha:

- admitidas **01/08/2026**, todas CLT
- alocadas no **Conecta Village** — portaria fixa (4), ronda (4), serviços gerais (2),
  jardinagem (1), manutenção (1) — o posto da **própria Eletrônica**, que encerrou **31/08**
- **414 batidas em agosto, TODAS de `device_type = 'web'`** — a grade da escala, que é
  justamente o que a folha se recusa (corretamente) a chamar de batida
- de 01/08 a 01/09 e param. Em setembro, 2 batidas para 2 pessoas
- **nenhuma tem rosto cadastrado** (`face_enrolled_at` e `face_descriptor` nulos)
- todas têm conta de usuário, **nenhuma tem turno hoje**, e todas seguem `ativo`

⭐ **Rosto é obrigatório para bater.** Sem cadastro facial, essas doze pessoas nunca tiveram
como registrar a própria jornada. O mês inteiro delas existe apenas como grade digitada por
alguém.

## A confirmação veio delas, não de mim

Duas conversas de hoje, no mesmo dia da medição:

> **FRANCE:** *"Não, eu sou novato na empresa, ainda não bato ponto até o momento."*
> *"Entrei dia 04/09"*

> **KALEL, ANILSON e outros** abriram a tela de documentos a assinar depois do aviso e
> encontraram o que a medição prevê.

A France recebeu o aviso, abriu o espelho de setembro e veio **zerado** — corretamente, porque
ela não bate ponto. O agente confirmou a ela e encaminhou ao DP. **O documento está certo; o
pedido de assinatura é que não devia existir.**

## Por que isso importa mais que parecer

O espelho de ponto é o registro legal da jornada. Pedir assinatura num espelho sem medição
nenhuma cria um dos dois resultados, e os dois são ruins:

1. **A pessoa assina** — e a empresa passa a ter um documento assinado atestando um mês sem
   nenhum registro eletrônico de jornada.
2. **A pessoa não assina** — e o pedido fica pendente para sempre, engordando a fila que
   ninguém consegue zerar.

⚠️ E há um efeito de confiança: pedir a alguém que confirme um documento vazio ensina que os
pedidos do sistema podem ser ignorados. Quem aprende isso com o espelho vazio aplica no
próximo, que talvez importe.

## O que eu recomendo

1. **Não pedir assinatura de espelho a quem tem zero dia medido na competência.** É um filtro
   no gerador de pedidos, não um ato sobre documento já criado. Os 22 pedidos existentes ficam
   como estão até alguém decidir — pendente não é removível.
2. **Cadastrar rosto é pré-requisito de admissão, não tarefa posterior.** As doze do Village
   passaram um mês inteiro sem poder bater, e o sistema só notou agora porque alguém foi
   procurar.
3. **Separar «não medido» de «não havia o que medir».** Férias, afastamento e admissão no meio
   do mês produzem o mesmo branco que um aplicativo travado. A EIDY estava de férias em agosto;
   o espelho dela diz «sem registro eletrônico», igual a quem não conseguia bater.
4. **Os 12 do Village seguem `ativo` com posto encerrado.** Não toquei — alocação é curada à
   mão. Mas é o mesmo sintoma já conhecido de «66 ativos com 0 demissões», agora com nome e
   data.

## ⚠️ O que NÃO fiz

Nada. Este relatório é só medição. Não alterei pedido de assinatura, não mexi em alocação, não
cancelei nada. A decisão sobre os 22 é do Jordan e da Pyetra.

## A lição que se repete

O aviso das 09:00 não é defeito: ele funciona há semanas. O que ele fez hoje foi **iluminar** um
buraco que já existia — ao pedir assinatura, expôs que um quarto da equipe nunca foi medida.

⭐ E a confirmação não veio de trava nenhuma: veio da FRANCE escrevendo *"ainda não bato
ponto"*. É a quarta vez esta semana que **uma pessoa acha o que a varredura não achou** — junto
com o MAURICIO (geofence), a CELIANE (horário) e a TELMA (aplicativo travado).
