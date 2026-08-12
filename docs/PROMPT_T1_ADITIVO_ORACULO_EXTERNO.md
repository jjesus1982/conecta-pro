# ADITIVO ao prompt v2 — a ferramenta que você pediu existe

Cole no T1 que já está rodando. Não substitui nada do v2; acrescenta uma frente.

---

## A ferramenta que você pediu foi construída

Você escreveu na resposta 20:

> *"um `checar_oraculo_externo` — dado um número que a tela mostra, ele diz contra qual fonte
> de fora do sistema esse número foi provado, e quando."*

Está no ar, ligado na varredura da 00:00, e o Arsenal foi para **8 travas**.

```bash
python3 backend/scripts/qa/checar_oraculo_externo.py            # estado das âncoras
python3 backend/scripts/qa/checar_oraculo_externo.py --listar   # o que ESTÁ ancorado hoje
```

Sete âncoras: saldo do banco, extrato, pagamentos do Inter, certidões, eSocial, folha da
Portte, NFS-e. **Um achado real** — espelho do eSocial com beat diário às 09:10 e última
consulta em 08/07, 35 dias. É de governo, não seu; está mapeado, não é sua frente.

**O que a impede de virar mentira:** a data da última prova não é escrita à mão. Cada âncora
declara o SQL que a lê do próprio dado — se a sincronização parar, a idade cresce sozinha.
Registro mantido por humano envelhece e passa a afirmar prova que nunca houve.

## Ela nasceu com dois falsos positivos meus — leia antes de escrever a sua âncora

1. **Certidões**: usei `min(expiry_date)`, a certidão vencida mais antiga. Isso é vermelho
   para sempre, **impossível de calar** — a sua lição nº 3 batendo na minha ferramenta. A
   pergunta certa era quando um *emissor* falou conosco pela última vez (foi ontem).
2. **NFS-e**: apontei para `nfses` (27 linhas, legada, parada em 12/02) em vez de
   `nfse_emitidas_nacional` (99, até 31/07). Rendeu "181 dias sem nota" que não existia.

**Âncora errada mente com a mesma confiança de âncora certa.** Sete achados viraram um depois
de conferir cada um. Se eu tivesse reportado os sete, o Jordan teria ouvido três alarmes
falsos no primeiro uso e nunca mais confiaria nela.

## Sua frente nova: ancorar os números do financeiro

Hoje **nenhum número do financeiro que você citou tem âncora externa**. Pelas suas próprias
respostas, estes são os candidatos — e a pergunta em cada um é a mesma: *quem, fora daqui,
confirma isto?*

| Número | Quem poderia confirmar de fora |
|---|---|
| **transitória R$384.580,79** | ninguém hoje — e é justamente por isso que ela infla o prejuízo em silêncio |
| **resultado / DRE** | fechamento da Portte por competência (você disse que não confia: R$97.066,72 com dois CNPJs misturados) |
| **saldo de abertura no corte** | você provou o do caixa por dois caminhos (R$18.663,83). Os passivos não têm nenhum — a dívida de R$12.000 com a Denise o razão não sabe |
| **contas a pagar** | boleto/fatura do próprio fornecedor |
| **contas a receber** | NFS-e emitida + confirmação de recebimento no extrato |
| **conciliação** | extrato do banco (já é a âncora do extrato; falta a do *resultado* dela) |

Acrescente ao `ANCORAS` em `backend/scripts/qa/checar_oraculo_externo.py` as que fizerem
sentido **e que você conseguir medir a partir do dado**. Regras:

- o SQL tem que ler **quando a fonte externa falou**, não quando nós calculamos;
- se não existe fonte externa para aquele número, **não invente âncora** — deixe de fora e
  registre no relatório que aquele número não tem quem o confirme. Isso é achado, não lacuna
  a preencher;
- prazo de validade realista: alarme que toca sempre é alarme que ninguém lê.

⚠️ Esse arquivo é de outra sessão. **Acrescente âncoras; não reescreva as existentes.** Se
achar que uma está errada, diga qual e por quê — como eu disse das minhas duas.

## E a pergunta que o `--listar` existe para provocar

**Âncora ausente é o pior achado**: o número que ninguém de fora confirma não aparece na
lista, então não incomoda ninguém. Rode `--listar`, olhe o financeiro, e responda no
relatório: *o que deveria estar aqui e não está?*

O seu próprio diagnóstico já responde metade — *"qualquer DRE hoje é ficção plausível"*. Um
número que é ficção plausível e passa em todos os portões é exatamente o que esta trava
existe para nomear.
