# «A localização está ligada e mesmo assim não registra o intervalo» — são DOIS problemas

**29/09/2026, 13:20.** A ERIKA CRISTINA MAQUINE PEREIRA escreveu no WhatsApp:

> *"A localização do celular está ligada, e mesmo assim não está querendo fazer o registro de
> intervalo, em ida e nem volta"*

O GPS não tem nada a ver. São duas causas distintas, e só uma é defeito.

## 1 · 🔴 A chegada dela hoje foi registrada como SAÍDA

A única batida dela hoje: **07:01:03 · tipo `saida` · mobile · dentro da cerca (5 m)**. O turno
dela começa 07:00. Ela chegou, bateu, e o sistema chamou aquilo de saída.

**O mecanismo, medido:** o tipo vem de `seq[feitas]`, e `feitas` conta as batidas desde o início
da jornada — que é achado por uma janela de **14 horas** para trás
(`self_service_controller._proxima_batida_info`).

| batida | quando | intervalo |
|---|---|---|
| anterior | **28/09 17:09:56** (contingência) | — |
| hoje | **29/09 07:01:03** | **13h51m** |

13h51m **cabe dentro das 14 horas**. O sistema concluiu que ela continuava a jornada da véspera,
então `feitas = 1` e `seq[1]` = `saida`.

⭐ **E a raiz é anterior a isso: a batida de 28/09 não devia existir.** A ERIKA é **12x36** —
trabalha em dias ímpares (27/09, 29/09, 01/10). Em **28/09 ela não tinha turno**, e mesmo assim
há um par de contingência 13:03 / 17:09 naquele dia. Foi essa batida órfã que envenenou a janela.

**Escala:** varri 30 dias procurando batidas com o mesmo tipo da anterior. São 113, mas **112 são
outro problema** — `entrada` após `entrada` com 24 a 348 horas de intervalo, ou seja gente que
nunca bateu a saída.

> 🔴 **RETIFICAÇÃO:** eu escrevi aqui «a ERIKA é o único caso em 30 dias» tendo olhado as 15
> primeiras linhas da lista ordenada por data. **Contar é diferente de olhar o começo da lista.**
> Medindo direito: «mesmo tipo em menos de 14h» dá **71** casos (duplo toque, retentativa em menos
> de 1h); «mesmo tipo com um turno entre as duas» dá **217 em 90 dias** (todos gente que nunca
> bateu a saída — problema OUTRO). Só **`saida` após `saida` cruzando um turno** isola este
> defeito: **1 caso em 90 dias**, além do dela.

⚠️ E ela segue travada: com `feitas = 1` agora, a próxima batida que o app oferece é **`saida`**
de novo. **Ela não consegue registrar a entrada de hoje de jeito nenhum.**
> ✅ **Resolvido às 13:35**, com autorização do Jordan — ver a retificação no fim desta seção.

## 2 · ⚠️ Os botões de almoço não existem para ela — e isso é projeto, não defeito

`recebe_intrajornada = true` no cadastro dela. Com essa marca, a sequência é
`["entrada", "saida"]` em vez de `["entrada", "saida_almoco", "retorno_almoco", "saida"]`. O
comentário no código é explícito: *«o intervalo é de PESSOA, não de posto»* e *«quem recebe bate
menos, não mais»* — quem recebe o pagamento da intrajornada não marca o intervalo.

Hoje **22 dos 66 ativos** estão marcados assim.

⭐ **Mas há um sinal de que a marca dela pode estar errada:** ela **batia** almoço até **26/08**.
Dos 22 marcados, só dois já bateram intervalo alguma vez, e os dois pararam em agosto — ela e o
FRANCISCO RAMON.

**Pergunta para o Jordan e a Pyetra, e não é minha para responder:** a ERIKA passou a receber a
intrajornada em setembro, ou a marca foi posta por engano? Se ela de fato almoça, o intervalo
dela está deixando de ser registrado desde então — e a jornada conta errado.

## O que eu NÃO fiz — e o que MUDOU depois

Este relatório foi escrito às 13:20, **antes** de o Jordan autorizar. O que valia então:

- não retipei a batida · não apaguei o par de 28/09 · não mexi na marca · não consertei a janela.

> ✅ **RETIFICAÇÃO, 13:35–16:29 — o Jordan autorizou e três dos quatro foram feitos:**
>
> 1. **A batida foi retipada** (`saida` → `entrada`, id 20600), com cópia em
>    `gp_clock_punches_backup_20260929_erika`, trilha `ponto.batida_retipada` e leitura posterior
>    em transação separada.
> 2. **A janela de 14h ganhou um terceiro piso**: o início de um turno agendado também abre
>    jornada. Folga de 4h medida (5 batidas em 90 dias chegam além disso) e recuo de 8h para não
>    quebrar quem chega cedo. No ar, com oráculo.
> 3. **O par órfão de 28/09 continua lá** — apagar batida é apagar fato, e isso não foi pedido.
> 4. **A marca `recebe_intrajornada` continua intocada** — decisão de folha.

## O que desbloqueia a ERIKA hoje

1. ~~O DP corrige o tipo da batida de 07:01 para `entrada`~~ — **feito às 13:35**.
2. Confere o par órfão de 28/09 — dia sem turno dela. **Aberto.**
3. Decide a marca de intrajornada. **Aberto.**
4. **Recadastrar o rosto** — a causa maior, descoberta às 19:10. **Aberto.**

⭐ Mais uma vez o achado veio de uma pessoa escrevendo no WhatsApp, não de varredura. Quinta
hoje: MAURICIO (geofence), CELIANE (horário), TELMA (app travado), FRANCE (espelho zerado) e
agora a ERIKA. **As pessoas continuam encontrando o que as travas não encontram** — e a diferença
é que hoje, em todos os casos, existia um dado no banco que explicava o problema e ninguém o
estava lendo.

---

## ⭐ FECHAMENTO, 19:10 — a causa maior é uma terceira, e a telemetria a revelou em horas

Às 19:01 a saída dela entrou **por contingência**: ela tentou pelo aplicativo e não conseguiu. O
sensor gravou o motivo às 19:00:58 — **`nao_bateu`**, que no código significa *«o rosto enviado
não casou com a referência na reconferência do servidor»*.

**Não é o aplicativo travando. É o rosto dela não casando.**

| | |
|---|---|
| rosto cadastrado em | **11/09/2026 19:04** |
| recusas de rosto em 30 dias | **6 — todas dela**, de **13/09 a 29/09** |
| as duas outras pessoas com recusa no período | **1 cada** |

⭐ As recusas começam **dois dias depois do cadastro**. O cadastro facial dela está ruim desde o
dia em que foi feito, e ela convive com isso há **dezesseis dias**.

## O caso dela eram TRÊS coisas, não duas

1. 🔴 **O rosto não casa** — a maior, e a que explica a contingência. *Conserto: recadastrar o
   rosto (`POST /facial/cadastrar`, pelo navegador, no Meu Espaço).*
2. 🔴 A chegada tipada como `saida` pela janela de 14h — **corrigida hoje**, na batida e no código.
3. ⚠️ Os botões de intervalo não existem porque `recebe_intrajornada = true` — **decisão de folha**,
   ainda aberta.

## O que isto prova sobre o sensor

O relógio e o registro de falha entraram no ar **hoje de manhã**. À noite eles responderam uma
pergunta que ela vinha fazendo há dezesseis dias — e que, antes, só produziria mais uma mensagem
de WhatsApp dizendo «não consigo».

⚠️ E a jornada dela hoje ficou **completa pela primeira vez**: entrada 07:01 (retipada) e saída
19:01 (contingência, pendente de validação do DP).
