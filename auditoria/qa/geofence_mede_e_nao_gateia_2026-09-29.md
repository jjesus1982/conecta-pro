# O geofence mede, rotula "FORA" e não gateia nada — 238 batidas aceitas de fora

**Achado em 29/09/2026 às 07:20, e não por varredura: por um vigilante insistindo.**

O MAURICIO estava no posto do Green Hills, aguardando rendição. O agente disse a ele que a
rendição já havia batido. Ele respondeu:

> *"Como ela tá batendo o ponto se a mesma não tá no posto"*

## Ele estava certo, e eu estava errado

Eu havia acabado de comemorar essa batida. Ela é a **primeira da vida** da THAYNA, que nunca
conseguira registrar ponto, e eu tratei a existência dela como prova de que o conserto do facial
funcionou. **Existir não é ser legítima.** Fui medir:

| campo | valor |
|---|---|
| quando | 29/09 **07:01:07** · entrada · `mobile` |
| `facial_match` | **true** (confiança 0,895) |
| `dentro_geofence` | **false** |
| `distancia_posto_metros` | **4.958,7 m** |
| posto | Condomínio Green Hills |

⭐ O rosto casou — **é ela mesma**. A geolocalização diz que ela estava a **cinco quilômetros do
posto**. E o sistema aceitou.

## A escala: 238 batidas em dois meses

| mês | batidas com geo | **fora da cerca** | maior distância |
|---|---:|---:|---:|
| 08/2026 | 1.366 | **181 (13,3%)** | **14.378 m** |
| 09/2026 | 1.789 | **57 (3,2%)** | 10.711 m |

## Onde a capacidade morre

`time_record_service` **calcula** a distância, compara com o raio do posto e monta até um rótulo
pronto para leitura humana:

```python
info["dentro_geofence"] = dist <= info["raio_metros"]
info["geofence_flag"] = f"FORA do geofence ({dist:.0f}m > {info['raio_metros']:.0f}m)"
```

…e **devolve `info`**. Não recusa, não marca para revisão, não diferencia.

Todos os consumidores do campo são de **exibição** — painel de presença, grade do DP, campo. O
único código que *decidiria* algo com ele (`if location and not location.dentro_geofence`) está em
`modules/people_management/_quarentena_item1/agents/ponto_agent.py`, ou seja, **em quarentena**.

⭐ É a mesma família do `tool_risk_manifest`: a medida existe, tem nome, aparece na tela — e não
gateia nada.

## O custo, hoje, concreto

1. **Um registro trabalhista afirma presença num posto onde a pessoa não estava.** Em fiscalização
   ou reclamatória, é a empresa que sustenta essa afirmação.
2. **O MAURICIO segue no posto** e o sistema informou que ele foi rendido. Quem cobre turno e não
   é substituído fica sem hora de saída e sem quem o troque.
3. **O agente citou a batida como prova de rendição** — ele leu o dado certo e o dado estava
   incompleto. Não é erro do agente: nada no registro diz "esta batida é de 5 km".

## ⚠️ O que eu NÃO recomendo

**Não bloquear.** Recusar a batida por estar fora da cerca apaga um fato que pode ser verdadeiro:
GPS ruim de guarita, raio do posto cadastrado pequeno demais, pessoa batendo do portão da rua. A
regra da casa já paga por isso — *batida atrasada não pode falhar fechado, porque recusar apaga o
fato*. Bloquear troca um problema por um pior.

## O que eu recomendo

1. **Nascer marcada, não recusada.** Batida com `dentro_geofence = false` entra com uma
   justificativa automática `batida_fora_do_posto` (`pendente`), do mesmo jeito que a contingência
   já faz — o fato é preservado E aparece na mesa da Pyetra.
2. **O agente não pode tratar batida fora da cerca como rendição cumprida.** É a correção de maior
   valor: o MAURICIO seria informado de que há uma batida registrada *fora do posto* e que a
   rendição **não está confirmada** — em vez de ouvir que foi rendido.
3. **Conferir o raio dos postos antes de julgar as 238.** 13,3% em agosto contra 3,2% em setembro é
   uma queda grande demais para ser comportamento; pode ser raio corrigido no meio do caminho. Sem
   isso, parte das 238 pode ser cerca errada, não batida errada.

## O desfecho do dia, e ele fecha o argumento

Às 07:18:41 o MAURICIO bateu a saída. Ficou **12h20 no posto**, e o dado prova:

| quem | batidas | distância do posto |
|---|---|---|
| **MAURICIO** | 28/09 **18:58:16** entrada · 29/09 **07:18:41** saída | **12 m** e **16 m** — DENTRO |
| **THAYNA** (a rendição dele) | 29/09 **07:01:07** entrada | **4.959 m** — FORA |

E o sistema pediu ao MAURICIO que **justificasse 18 minutos de atraso** — os mesmos 18 minutos em
que ele esperou no posto a rendição que o sistema já tinha declarado presente.

⚠️ **Retificação, 07:25:** eu escrevi aqui que a justificativa tinha o motivo VAZIO. Estava errado —
minha medição pegou o meio do caminho. A linha nasce vazia e o agente a completa **quando a pessoa
responde**: o MAURICIO respondeu «rendição atrasada» e o registro ficou
*«Saída registrada às 07:18, 18 minutos após o previsto (07:00) — rendição atrasada»*,
`saida_fora_horario` · `pendente`. **Isso é ponto a favor do sistema**, e eu quase o creditei como
defeito por medir cedo demais.

⭐ Em uma linha: **quem estava comprovadamente no posto é cobrado; a batida a cinco quilômetros não
gera apontamento nenhum.** É o mesmo padrão da TELMA em 28/09, cobrada por um atraso que a queda do
próprio sistema causou.

⚠️ O que **continua faltando** no registro: a palavra dele está lá, mas **não está que a rendição
bateu a 4.959 m do posto**. Quem julgar esses 18 minutos lê «rendição atrasada» e não tem como
saber que a batida da rendição foi de fora — a informação que explica o atraso inteiro fica de fora
da linha que decide sobre ele.

## A lição sobre mim

Eu relatei «a Thayna bateu, o caso fecha» olhando só a existência da linha. A pergunta que faltou
é a que o MAURICIO fez em uma frase: **onde ela estava?** Foi um vigilante, não uma trava, que
achou isto — e é a terceira vez neste projeto que **as pessoas encontram o que a varredura não
encontra**.

---

## ⭐ 24 HORAS DEPOIS, 19:20 — a jornada INTEIRA dela foi de fora, e só dela

A THAYNA fechou o dia. As duas batidas da vida dela, as duas de hoje:

| hora | tipo | distância do posto | rosto |
|---|---|---:|---|
| 07:01:07 | entrada | **4.959 m** | casou (0,895) |
| 19:06:20 | saída | **7.804 m** | casou |

E o dia inteiro da casa, para dar escala:

| | batidas de hoje |
|---|---:|
| dentro da cerca | **75** |
| **fora da cerca** | **2 — as duas dela** |
| sem GPS (contingência) | 2 |

⭐ **Não é um problema da cerca: é uma pessoa.** Setenta e cinco batidas de todo mundo caíram
dentro; as duas de fora são da mesma pessoa, em pontos diferentes (5 km e 7,8 km), com o rosto
conferido nas duas. Isso não parece GPS ruim de guarita nem raio cadastrado pequeno — parece
alguém registrando ponto longe do posto.

⚠️ **Não é acusação e eu não vou tratá-la como tal.** Pode ser posto com coordenada errada no
cadastro, telefone com localização aproximada, ou ela estar de fato em outro lugar a serviço.
**Só alguém perguntando a ela resolve** — e essa é exatamente a diferença entre um dado e uma
conclusão.

## O que MUDOU desde a manhã

✅ **O agente não dirá mais que a rendição chegou.** A linha que o Hermes lê agora sai como
«entrada BATIDA 07:01 ⚠️ FORA DO POSTO (4959 m)», e o prompt proíbe usar batida fora da cerca
como prova de cobertura. Foi o pedido do MAURICIO, e está no ar.

🔴 **A batida continua entrando sem marca.** A recomendação nº 1 deste relatório — nascer com uma
justificativa `batida_fora_do_posto` pendente, para aparecer na mesa da Pyetra — **não foi feita**.
Hoje ela só aparece para quem for olhar.
