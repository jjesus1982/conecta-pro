# «A Celiane é a única com cadastro errado?» — NÃO. São nove, e 3.292 minutos seguem vivos em setembro

> ## 🔴 RETIFICAÇÃO, 10:25 — a primeira resposta deste relatório estava ERRADA
>
> Eu publiquei **«sim, é só ela»**. Uma régua melhor devolveu **nove pessoas**. Dois defeitos na
> minha medição, e os dois são da mesma família — *a trava observa a coisa errada*:
>
> 1. **Misturei dois regimes.** Agrupei por pessoa, e o cadastro da Celiane mudou de 07:00 para
>    08:00 dentro da janela. A variância estourou e o filtro «variação baixa» a descartou —
>    junto com todos os outros. A suspeita é sobre **pessoa + horário cadastrado**, porque é o
>    par que define o regime.
> 2. **Pareei batida por DATA DE CALENDÁRIO.** Isso fez o MAURICIO aparecer com **3.518 minutos
>    em 5 dias** (703 por dia): ele é **noturno**, entra 18:58, e eu comparei com um cadastro de
>    07:00. A casa já documenta isto — *data da batida ≠ data da escala* — e eu caí. Pareando
>    pelo **instante previsto ±3h**, ele desaparece da lista, corretamente.
>
> ⚠️ Eu estava a um comando de corrigir este relatório usando os números do defeito nº 2. O que
> pegou foi o valor absurdo: 703 minutos por dia não é atraso de ninguém.
>
> O corpo abaixo está mantido — inclusive o método, que estava certo — com os números refeitos.

Pergunta que o Jordan deixou aberta em 29/09/2026, depois de eu consertar a recusa de batida
dela. Eu havia escrito: *"a tabela de vigência tem uma linha só, mas isso mede quem reclamou e
foi ouvido — não quem está errado."* Fui medir quem está errado.

## Como se separa «atraso» de «cadastro errado»

Sem opinião: pela **variação**. Quem se atrasa, atrasa diferente todo dia. Quem tem o cadastro
errado bate sempre na mesma hora, e a diferença é constante.

A régua certa é **por regime** (pessoa + horário cadastrado) e com a batida pareada ao **instante
previsto ±3h**, nunca por data de calendário. Setembro inteiro, com essa régua:

| quem | cadastro | dias | média | **variação** | além da tolerância |
|---|---|---:|---:|---:|---:|
| GRACIENE PEREIRA DE CASTRO | 07:00 | 8 | 64 min | 6 | 391 min |
| OSCAR SOARES DA COSTA FILHO | 07:00 | 7 | 62 | **1** | 327 |
| MALAQUIAS PEREIRA FERREIRA | 07:00 | 7 | 62 | 2 | 333 |
| EDILENE SALES SOUSA | 07:00 | 6 | 61 | **1** | 273 |
| GEILSON RODRIGUES DE ANDRADE | 07:00 | 8 | 60 | **0** | 360 |
| JAQUELINE CARLOS DOS SANTOS | 07:00 | 7 | 60 | **1** | 318 |
| KALEL SILVA DE JESUS | 07:00 | 8 | 60 | **1** | 365 |
| **CELIANE GARCIA DE SOUSA** | **08:00** | **14** | **59** | **2** | **622** |
| ANGELA LOPES MACEDO | 07:00 | 7 | 58 | 5 | 303 |

**Total: 9 pessoas · 72 turnos · 4.372 minutos fantasma · 3.292 além da tolerância.**

⭐ **Variação zero a seis minutos.** Ninguém se atrasa exatamente 60 minutos, com margem de um
minuto, oito dias seguidos. É o cadastro — e oito das nove tinham o mesmo valor errado, 07:00.

⚠️ **Hoje a régua está limpa** (janela corrente de 21 dias: zero pessoas). O erro foi corrigido na
origem para as oito, em 11/09; a Celiane foi coberta pela vigência em 24/09. O que sobra é o
resíduo dentro do mês aberto.

## O GEILSON prova o mecanismo, e já foi consertado

| dia | cadastro | bateu | acusado |
|---|---|---|---:|
| 01 a 10/09 | **07:00** | 08:00 | **60 min** × 8 dias |
| 11 e 12/09 | **08:00** | 08:00 | **0** |

**A batida dele nunca mudou** — sempre 08:00 em cheio. Em 11/09 o cadastro virou 08:00 e a
acusação foi a zero. Foram 19 pessoas com o horário de entrada alterado em setembro: houve uma
correção de escalas naquele dia, e ela funcionou.

⚠️ Sobraram os 8 dias anteriores dele (480 minutos) como acusação. E todas as batidas dele são
`tangerino` — o relógio que parou em 13/09 —, então ele não tem batida nenhuma depois de 12/09.

## A CELIANE é a que a correção de 11/09 não alcançou

A correção de 11/09 mudou o cadastro dela de **07:00 para 08:00**. Ela trabalha às **09:00**.
Consertaram uma hora das duas.

Setembro dela, inteiro, é uma acusação — **17 turnos, 1.249 minutos (20,8 horas), 994 além da
tolerância** de 15 minutos:

```
01/09  07:00–16:00  bateu 09:00  → 120 min
02–04  07:00–16:00  bateu 08:00  →  60 min  (tangerino)
08–10  07:00–16:00  bateu 08:59  → 119 min
11–19  08:00–17:00  bateu 08:51 a 09:02 → 51 a 62 min
```

E ela havia dito, por escrito: *"já falei várias vezes"* · *"eu entro 9:0h da manhã"* · *"eu
nunca bater pode atrasado"*.

## O que o conserto de hoje alcança, e o que NÃO alcança

✅ **De 24/09 em diante ela é pontual ao minuto**: 0,99 · 0,20 · **−0,12** (adiantada) · 0,17
minutos. A vigência escrita pelo Jordan em 24/09 agora manda em `punch_service` (recusa),
`lembrete_ponto` (o aviso) e `mapa_de_ponto` (a classificação — e por herança a conferência da
folha).

🔴 **De 11 a 23/09 ela segue acusada**: **622 minutos** além da tolerância. A vigência começa em
24/09 e **de propósito não reescreve para trás** — horário corrigido não pode mexer em mês
fechado, senão folha já paga muda sozinha.

⚠️ **Mas setembro NÃO está fechado.** Esses 767 minutos ainda vão descer para `minutos_alem`, que
é o número que sustenta desconto.

## A decisão é do Jordan, e agora é sobre NOVE pessoas

Setembro não está fechado, e **3.292 minutos além da tolerância** (54,9 horas) seguem descendo
para `minutos_alem`, que é o número que sustenta desconto. Distribuídos assim:

- **oito pessoas** com o cadastro 07:00 errado de 01 a 10/09 — corrigido na origem em 11/09, mas
  o resíduo dos dez primeiros dias continua lá (2.670 min além da tolerância)
- **a CELIANE**, de 11 a 23/09 (622 min), porque a vigência dela começa em 24/09

Duas saídas, e as duas são atos sobre folha:

1. **Retroagir** — a vigência da Celiane para 11/09 (ou 01/09), e registrar vigência para as oito
   cobrindo 01 a 10/09.
2. **Abonar na folha de setembro** — tratar os 3.292 minutos como abono explícito, com motivo.

⚠️ **Eu não fiz nenhuma das duas.** Mudar ou criar vigência é mexer no que decide desconto, e o
autor legítimo dessas linhas é quem tem autoridade sobre o horário — não eu. O que fiz foi medir
e deixar os nomes e os números.

## Por que a resposta importa além dela

A pergunta era «quem mais?». Minha primeira resposta foi «uma pessoa» e estava errada: são
**nove**, e sete delas nunca reclamaram — foram corrigidas por tabela, em 11/09, sem que ninguém
soubesse que havia um resíduo em folha. Mas o **método** agora existe: variação
baixa com diferença alta é cadastro errado, e isso se mede sem perguntar a ninguém. Antes de
hoje, o único jeito de descobrir era alguém insistir no WhatsApp até ser ouvido — foi assim que a
Celiane apareceu, e ela precisou falar «várias vezes».

⭐ Virou oráculo (`test_oraculo_cadastro_de_horario_suspeito`): **regime (pessoa + horário
cadastrado) com ≥5 dias, diferença média > 25 min e variação < 10 min é cadastro suspeito, não
pessoa atrasada.** Pareamento pelo instante previsto ±3h, senão o noturno inventa 700 minutos.

Hoje ela devolve **zero** na janela corrente — e devolveria **nove** na janela de setembro. É
assim que se sabe que ela tem dentes sem precisar que ninguém reclame.
