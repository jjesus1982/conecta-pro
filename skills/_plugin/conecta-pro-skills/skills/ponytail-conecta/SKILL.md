---
name: ponytail-conecta
description: Camada local sobre ponytail para o Conecta PRO — onde a preguiça vale, onde ela é proibida, e a exceção da casa (mensagem de commit). Não substitui o ponytail; ajusta as três regras que colidem com esta realidade — dinheiro/fisco/governo, banco de produção vivo, e cinco sessões que só se comunicam por commit. Use junto com ponytail, sempre que ele estiver ativo.
---

# Ponytail — camada Conecta PRO

O ponytail está certo e fica ativo. Esta camada só resolve **três colisões** entre ele e a
realidade daqui. Fora delas, vale o original: escada, reuso, menor diff, deleção.

## 1. "Menor diff" não vale em dinheiro, fisco e governo

A escada do ponytail otimiza tamanho. Aqui, em caminho de dinheiro/tributo/gov, o critério é
outro: **o diff PROVÁVEL**, não o curto.

O menor diff possível para o balanço que não fechava seria trocar `"3"` por `"4"` no
classificador. Duas linhas, funcionaria hoje. O que se fez foi ler `account_type` do plano de
contas — mais código, e a diferença é que ele continua certo quando o plano mudar.

**Regra:** se o número toca R$, tributo ou órgão público, prefira ler a fonte a codificar a
convenção. Convenção codificada é a fábrica de defeito desta casa.

## 2. A checagem executável não é opcional aqui — e tem forma

Ponytail pede "uma checagem por lógica não-trivial". Nesta casa ela tem endereço e regra
própria: `backend/scripts/orq/`, afirmando a REGRA e não a fotografia, provada contra o
código anterior. Ver [[oraculo-conecta]].

E há um gatilho a mais que o ponytail não prevê: **toda superfície nova nasce vigiada.** KPI,
tela ou número sem oráculo é dívida no dia em que nasce — o Balanço exibiu PL de
+R$ 2,02 milhões por meses porque não havia oráculo contábil.

## 3. A exceção da casa: mensagem de commit é longa DE PROPÓSITO

Ponytail: *"no máximo três linhas curtas; se a explicação for maior que o código, apague a
explicação."* Vale para **código, comentário e conversa**. **Não vale para a mensagem de
commit** aqui, e a razão é estrutural:

Cinco sessões editam o mesmo repositório e **não conversam entre si**. O commit é o único
canal. Foi lendo o corpo de um commit do T1 que se descobriu o corte contábil de 01/08 —
*"decisão do Jordan: jan–jul foram vividos fora do Conecta PRO"*. Sem aquele parágrafo, a
reversão de 184 lançamentos não teria acontecido.

**O que a mensagem precisa carregar:** o número medido (antes → depois), a decisão de negócio
que ela respeita, e o que foi deliberadamente NÃO feito. A história longa vai no commit e no
relatório de auditoria; o comentário no código fica curto e explica só o que a linha não diz.

## O que continua igual (e é a maior parte)

- **Reuse antes de escrever.** O sino já existia (`task_falha`): a varredura diária não
  escreveu uma linha de notificação.
- **Deleção sobre adição.** Dois bots de Telegram e 8 tarefas mortas saíram; o sistema
  ficou melhor.
- **Nunca preguiçoso na compreensão.** Medir antes de corrigir é inegociável — o custo desta
  casa vem de código escrito sobre suposição, não sobre medição.
- **Sem abstração especulativa.** Um caçador de fabricação com 4 assinaturas medidas vale
  mais que um framework de linters.

## Sinal de que você saiu da escada

Se você está escrevendo o quinto script de rascunho na mesma tarefa, pare: provavelmente
está medindo o que já mediu. Se está prestes a "consertar" 184 registros de uma vez, pare:
provavelmente há uma regra que impede aquilo e você não a procurou.
