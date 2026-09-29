# Duas pessoas com turno amanhã e praticamente nenhum registro de ponto

**29/09/2026, 18:40.** Achado ao conferir uma pergunta do agente ao JAIR — *«teu acesso já foi
liberado pra bater o ponto?»*. O Jair está bem; a varredura dos escalados é que trouxe dois nomes.

## 1 · EIDY CULIER DE CASTRO — o último órfão do Tangerino

| | |
|---|---|
| última batida | **11/09 06:00** |
| origem de TODAS as 138 batidas da vida | **`tangerino`** (+44 `web` em março) |
| batidas desde 13/09 | **zero** |
| rosto cadastrado | **não** |
| turnos sem registro desde 13/09 | **8** |
| turnos agendados nos próximos 14 dias | **7** — o primeiro **30/09 às 18:00**, Villa Dei Fiori, 12x36 noturno |

⭐ **O Tangerino foi desligado em 13/09 e ela nunca teve outro caminho.** Sem rosto cadastrado, o
aplicativo não funciona para ela. Ela batia normalmente até 11/09 — não é alguém que não bate, é
alguém de quem tiraram o meio de bater.

Ela é a **única** ativa nessa situação: o desligamento deixou cinco pessoas sem como bater, quatro
foram resolvidas, e ela ficou. **Dezoito dias.**

**O conserto é dela e leva minutos:** `POST /facial/cadastrar` existe — ela entra no Meu Espaço
pelo navegador e cadastra o rosto (permissões → rosto → batida).

⚠️ **Mas confira antes:** ela tem **DUAS contas de usuário**. Se o rosto for cadastrado numa e a
batida tentada na outra, nada funciona — e isso pode ser a razão de nunca ter sido resolvido.

## 2 · THAYNA RHANNELE CANCIO NEVES — rosto cadastrado e uma batida na vida

| | |
|---|---|
| rosto cadastrado | **sim** |
| batidas na vida | **1** — 29/09 07:01 |
| turnos nos últimos 30 dias | **17** |
| turnos agendados nos próximos 14 dias | **7** |

⚠️ E a única batida dela é justamente a que o MAURICIO contestou: **4.958,7 m do posto**, rosto
conferido (0,895), aceita pelo sistema. Ou seja, o único registro da vida dela é o que gerou o
relatório do geofence.

O problema dela é **diferente do da EIDY**: o caminho existe (rosto cadastrado) e mesmo assim não
produz batida. Não medi por quê — vale perguntar a ela antes de supor.

## ⚠️ Um número que eu NÃO vou usar

Montei um ranking de «muito turno e pouca batida» e ele não se sustenta: **turno e batida não são
a mesma unidade**. Um turno gera duas ou quatro batidas, então subtrair uma coluna da outra não
mede nada. Os dois casos acima se sustentam pelo caso individual — última batida, origem, rosto —
não pela diferença de colunas.

## 3 · De passagem: a marca de intrajornada não bate com a prática em 17 de 66

O JAIR escreveu que no Prime Arena **não há intervalo**, e o agente respondeu *«você já tinha
pedido isso»* — pedido anterior que não foi aplicado.

| situação | pessoas |
|---|---:|
| coerente (não recebe, bate almoço) | 29 |
| coerente (recebe, não bate) | 20 |
| ⚠️ marcado «não recebe» e **nunca** bate almoço | **15** |
| 🔴 marcado «recebe» mas **bate** almoço | **2** |

⚠️ **Isto NÃO está bloqueando ninguém** — o JAIR e o ALAN batem entrada e saída normalmente, então
a sequência de dois passos chega a eles por outra regra. É inconsistência de **cadastro**, não
defeito de batida. Mas `recebe_intrajornada` decide pagamento, e 17 de 66 fora do lugar é matéria
de folha, não de tela.

Os 2 marcados «recebe» que batem almoço são a **ERIKA** (que reclamou hoje de não conseguir
registrar intervalo) e o **FRANCISCO RAMON** — já reportados.

## O que eu não fiz

Não cadastrei rosto de ninguém, não mexi em marca de intrajornada, não criei batida. Tudo aqui é
medição; os três consertos são humanos.
