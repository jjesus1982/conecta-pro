# Quem cobriu levou a marca; a falta não deixou nenhuma

**29/09/2026, 18:50.** A TELMA explicou por WhatsApp o atraso dela na saída:

> *"Porque a minha parceira não veio e eu estava fazendo a parte que me cabe e a dela, então não
> deu para sair no horário usual."*

Fui conferir cada elo. A palavra dela se sustenta inteira — e o que o sistema registrou foi o
oposto do que aconteceu.

## O que de fato houve, no Mirante das Flores

| quem | turno | entrada | saída |
|---|---|---|---|
| ALEXANDRE | 07:00–19:00 | 07:02 | — |
| **TELMA** | 07:00–16:00 | 07:03 | **16:18** |
| **VANDERLICE** | 07:00–16:00 | **— não bateu** | — |
| PAULO | 09:00–18:00 | 09:01 | 18:01 |
| ANTONIO CARLOS | 10:00–22:00 | 10:00 | — |

## ✅ O que funcionou

A casa **perseguiu a VANDERLICE cinco vezes**: escala às 05:45, lembrete às 06:54, cobrança às
07:04, o José Luís pessoalmente às 07:24, e a confirmação de amanhã às 18:00. O elo individual
está de pé.

E o **Vigia dos postos rodou** às 07:30 e às 14:00. Ele apontou o Michelangelo — e está **certo
pela régua dele**: a pergunta é *«o posto está guarnecido?»* e a resposta era **sim**, porque a
TELMA cobriu por duas.

## 🔴 O que não existe em lugar nenhum

| o que deveria ter registro | existe? |
|---|---|
| a FALTA da Vanderlice (justificativa) | **não** |
| a falta como afastamento | **não** |
| a SUBSTITUIÇÃO / cobertura da Telma | **não** — `substitutions` tem **0 linhas na vida da tabela** |
| os 18 minutos a mais da Telma | **sim — como atraso dela** |

⭐ **A única marca que o dia deixou é contra quem cobriu.** A Telma fez o trabalho dela e o da
parceira por nove horas, saiu 18 minutos depois, e o artefato que o sistema produziu foi uma
cobrança de atraso no nome dela. A ausência que causou tudo não deixou rastro.

## ⚠️ E não é defeito do Vigia — é uma pergunta que ninguém faz

O verificador pergunta **«o posto está vazio?»**. Nunca pergunta **«o posto está com quantas
pessoas?»**. Falta de UMA pessoa num posto com várias é invisível por construção: não é
`descoberto`, não é `em_risco`, é `ok`.

Isso está escrito no próprio prompt dele, de propósito — *«um posto está GUARNECIDO se há alguém
nele agora, mesmo que seja outra pessoa que não a escalada»* — e essa regra existe porque o
contrário já acusou posto coberto. **A régua está certa para o que ela mede; falta uma segunda.**

## O que eu recomendo, e nada disso eu fiz

1. **Escalado que não bate e não justifica vira FALTA registrada**, automaticamente e como
   pendente — do mesmo jeito que a contingência já nasce. Hoje ela some.
2. **Quem cobre precisa aparecer.** `substitutions` existe, tem colunas para tudo isso
   (`original_employee_id`, `substitute_employee_id`, `reason`, `additional_cost`) e **nunca
   recebeu uma linha**. É capacidade desligada, não capacidade faltando.
3. **A cobrança de atraso devia saber da cobertura.** Perguntar a alguém por que saiu tarde no
   dia em que ela cobriu dois postos é o sistema pedindo explicação de algo que ele mesmo tinha
   como saber — o Alexandre e a Telma bateram, a Vanderlice não.

⚠️ Não registrei falta, não criei substituição, não apaguei a cobrança de atraso. Alocação e
cobertura são curadas à mão; isto é relatório.
