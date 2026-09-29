# A casa falou com dezenas de pessoas e registrou 23 — o log de saída estava pendurado no eco

**Medido em 29/09/2026, entre 09:00 e 09:10.** E achado por acidente: eu estava conferindo se o
aviso diário de assinatura era rotina ou se algo tinha disparado sozinho.

## O número

Às 09:00 o aviso diário de assinatura saiu. `cwi_message_log` registrou **23 mensagens para 23
pessoas**, entre 09:00:09 e 09:03:47 — com um salto suspeito de **09:01:47 para 09:03:22**.

O monitor de conversas, que lê mais perto do fio, mostrou muito mais gente nesse intervalo.
Escolhi doze nomes que ele exibiu recebendo e fui procurar no log:

| TELMA | CELIANE | KELLY | VANDERLICE | NAILSON | PAULO |
|---|---|---|---|---|---|
| RUAN | BIANCA | DANIEL | MATHEUS | EDIWILSON | JONILSON |

**Doze de doze sem uma linha.** Rodei o controle oito minutos depois: continuavam 23. Não era
atraso do eco — era ausência.

## A causa

`_send_message` (o ponto único por onde TODO envio passa: aviso de assinatura, alerta de
certidão, NFS-e, mensagem do agente) **não gravava nada**. Quem escrevia o log era o **webhook**,
em `controller.py:1100`, a partir do eco que o Chatwoot devolve:

```python
direction = "in" if mtype in ("incoming", "0") else "out"
```

⭐ **O registro estava pendurado no EFEITO, não no ATO.** Eco que não volta = a empresa falou com
um funcionário e não tem prova do que disse. É a mesma forma de
[registro de falha no lugar errado](../../.claude/projects/-root/memory/feedback_registro_de_falha_no_lugar_errado.md):
instrumentar o vizinho do fato e ler o vazio como inocência.

## Por que dói neste assunto especificamente

As mensagens que sumiram não eram propaganda. Eram **"você tem N documentos para assinar:
espelho de ponto, documento do kit"** — ponto, folha e assinatura. "O que a casa afirmou a quem,
e quando" é exatamente o que se precisa poder mostrar depois, em fiscalização ou reclamatória.
E é também o que o agente lê como histórico: mensagem fora do log é contexto que o José Luís
não tem quando a pessoa responde.

## O conserto

Registro no ato, dentro de `_send_message`, com duas propriedades deliberadas:

1. **Idempotente com o eco.** `chatwoot_message_id` tem UNIQUE; o `ON CONFLICT DO NOTHING` faz o
   webhook colidir em vez de duplicar. Sem isso o conserto trocaria "mensagem sem registro" por
   "mensagem registrada duas vezes" — mentira para o outro lado.
2. **`status='sent'` marca a procedência.** O eco grava status nulo. É o que permite medir depois
   quantas mensagens só existem porque este registro passou a ser feito.

**Best-effort de verdade:** banco fora do ar não pode calar um WhatsApp. A exceção morre no
registrador e o retorno de `_send_message` não muda.

### Um efeito colateral que virou conserto

A canonização do telefone **mudou de casa**: saiu do controller para `service.normalize_phone`.
Motivo: quem envia precisa canonizar, e importar um controller de FastAPI de dentro do caminho
de envio faria um worker de celery executar código de rota só para mandar uma mensagem. O
controller usa a mesma função por alias — **uma implementação, não duas** (duas divergem na
primeira mudança e o mesmo telefone passa a existir em dois formatos no log).

## Trava

`scripts/orq/test_oraculo_saida_whatsapp_registrada.py` — exercita o **registrador**, nunca o
remetente (mandar WhatsApp num teste é ato para fora). Cinco asserções: grava · não duplica no
eco · entrada podre não levanta · uma canonização só · telefones de saída só com dígitos.

Provado nos dois sentidos: verde com o conserto; **vermelho na asserção** com o registrador
neutralizado por monkeypatch — *"o registro do ato não gravou (0 linhas)"*.

## ⚠️ O que este conserto NÃO faz

Não recupera as mensagens já perdidas. O que saiu antes de hoje e não teve eco **não existe em
lugar nenhum** — não há de onde tirar. A partir do deploy, existe.

E fica uma pergunta que é do Jordan: **quanto do histórico já se perdeu assim?** O log tem 116
linhas de saída hoje; se a proporção de hoje valer para trás, o que a casa disse aos
funcionários está registrado pela metade desde que o canal existe.

## Erros meus nesta mesma investigação, porque eles são o mapa

Três afirmações que eu levantei e os controles derrubaram:

1. **"Pare tudo, pedidos de assinatura saindo sem autorização".** Era rotina — o aviso das 09:00
   roda desde 14/09. O que subiu foi o volume (23 pessoas contra 9 ontem), porque os kits que
   montei criaram pedidos que antes não existiam.
2. **"O destinatário virou um nome em vez de telefone"** (`Jair soares da rocha`). `cwi_message_log`
   tem **zero** linhas fora do formato: era rótulo do próprio monitor, que mostra o nome do
   contato do Chatwoot quando existe.
3. **"O aviso mente: disse 1 documento e a tela está vazia"** (caso do ANILSON). Ele **assinou às
   09:04:56**, três minutos depois do aviso. Aviso certo, assinatura feita, tela esvaziou
   corretamente, agente respondeu corretamente. **A cadeia inteira funcionou** e eu estava
   construindo um defeito em cima de um acerto.

⚠️ E um erro de método: `created_at`/`signed_at` dessas tabelas são **naive-Manaus**, como
`punch_timestamp`. Meu `AT TIME ZONE 'America/Manaus'` estava **somando 4 horas** em tudo. Só
percebi porque uma coluna apareceu como 04:27 onde eu já tinha lido 00:27 — a discrepância com
a minha própria leitura anterior foi o que denunciou.

## O que sobra de verdade, e é do Jordan

⭐ **22 pessoas estão sendo convidadas a assinar um espelho de ponto de agosto com ZERO dia
medido** — o documento delas é inteiro "Sem registro eletrônico". Mais 7 com 1 a 5 dias. São
**29 de 64** assinando uma folha praticamente vazia.

A opção 2 (dia não medido sai marcado, com a grade ao lado como referência) foi escolha sua e
está certa para quem tem o mês quase todo medido. Para quem tem **zero**, o que se está pedindo
é assinatura num documento sem conteúdo. Vale decidir se esses 29 entram no lote ou se esperam
a reconciliação do ponto.
