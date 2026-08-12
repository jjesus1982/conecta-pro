---
name: plano-conecta
description: Escreve plano de implementação no Conecta PRO. Substitui superpowers:writing-plans aqui — a diferença que importa não é a decomposição em tarefas, é DECLARAR TERRITÓRIO, porque cinco sessões editam o mesmo repositório e o mesmo banco de produção ao mesmo tempo. Use antes de qualquer trabalho que passe de um commit ou toque arquivo que outra sessão possa estar mexendo.
---

# Plano — Conecta PRO

O `writing-plans` genérico assume um desenvolvedor num repositório seu. Aqui são **cinco
sessões no mesmo índice git, no mesmo banco de produção, com deploy que leva 15 minutos**.
Nesse cenário o plano tem uma função que a versão genérica não prevê: **dizer onde você vai
pisar, antes de pisar.**

## Passo 0 — território (não é opcional)

Antes de escrever qualquer tarefa:

```bash
cd /opt/conecta-pro
git log --since="1 day ago" --oneline -- <arquivos que você vai tocar>
git status --short -- <arquivos que você vai tocar>
```

Leia o resultado assim:

| O que aparece | O que significa |
|---|---|
| commits recentes de outra sessão | **território ativo** — leia os commits antes de decidir; pode já estar feito |
| ` M arquivo` (WIP não commitado) | outra sessão está **editando agora** |
| nada | livre |

**Se houver WIP alheio no arquivo:** `git add <arquivo>` leva o trabalho dela junto, e o
índice temporário **não protege** — ele isola arquivos, não trechos dentro do mesmo arquivo.
Em 12/08/2026 isso aconteceu duas vezes no mesmo dia. Escolha uma:
- esperar o arquivo ficar limpo (mais simples e quase sempre certo);
- ou combinar com a outra sessão antes.

## O que o plano DEVE conter, além das tarefas

```markdown
## Território
Vou tocar: caminho/a.py, caminho/b.py
NÃO vou tocar: modules/financial/services/**  (T1 está na cadeia do caixa)
Conferido em: <data/hora> — git log 1d e git status limpos nesses arquivos

## Decisões já tomadas que este plano respeita
- corte contábil 01/08/2026: jan–jul não se reconcilia (decisão do Jordan, 7e6eed09)
- operacional é curado à mão: divergência vira relatório, nunca correção
- money-out sempre com OTP humano; gov só leitura
```

Sem a seção **Território**, o plano é um roteiro pessoal — não coordena nada.

## Tarefas: o tamanho certo aqui

A regra genérica ("2-5 minutos por passo") produz plano longo demais para esta casa. Use:
**uma tarefa = um commit que fecha sozinho**, com o oráculo dentro dela. Se a tarefa não
termina com algo executável verde, ela não terminou.

Cada tarefa declara:
- arquivos exatos (criar / modificar / oráculo)
- o número que prova que funcionou — medido ANTES, para comparar depois
- como reverter, se mexer em dado de produção

## Quando NÃO planejar

Descoberta não se planeja. Se você ainda não mediu, o plano é ficção: em 11/08 o plano
previu `lider` como o papel de gestor e a medição mostrou `supervisor`; previu que a Task 5
era ajuste de teste e era falha de segurança. **Meça primeiro** (`raio-x-modulo`,
`veracity-sweep`, SQL direto), planeje depois.

Também não planeje conserto de uma linha. Plano para trabalho de 20 minutos é atrito.

## Onde salvar

`docs/superpowers/plans/AAAA-MM-DD-<assunto>.md`, com checkbox por passo. Ao fechar, marque
os passos E acrescente **o que a medição corrigiu no plano** — é o que ensina o próximo.

## Fechamento

O plano só fecha quando cada tarefa tem: oráculo verde, commit por pathspec, e a tela
servida pela rota real depois do bake. Ver [[entregue-de-verdade]].
