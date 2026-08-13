# Respostas ao Questionário T2 — Departamento Pessoal

Respondido em 13/08/2026. **Tudo aqui foi medido no banco ou lido no código de produção**, não
respondido de memória. Onde eu não verifiquei, está escrito "não verifiquei" — isso é resposta,
não lacuna disfarçada.

> **Leia primeiro a resposta 9.** Ela é o achado mais caro do módulo e nenhuma pergunta do
> questionário previa: existem holerites duplicados com valores diferentes para o mesmo
> funcionário no mesmo mês, e o portal escolhe qual mostrar sem critério.

---

## A. O que está em curso

### 1. Os três arquivos não commitados são meus, do rollout do ponto

São de hoje e de ontem, e **já estão em produção** (bakeados na imagem, verificados após
recreate). Estão fora do git porque não commitei — é dívida minha, não trabalho abandonado.

- `ponto/coorte_ponto.py` (novo) — define quem entra na coorte do ponto.
- `painel_ponto_controller.py` — passou a usar a coorte compartilhada e corrigiu a contagem de
  "ativado" (antes chamava de pendente quem tinha rosto cadastrado pelo DP).
- `primeiro_acesso_controller.py` — duas correções: não deixa refazer o cadastro inteiro (o link
  do WhatsApp era o único endereço que o pessoal tinha e eles repetiam o fluxo todo dia), e a
  ativação passou a mirar só a conta do e-mail do cadastro, em vez de todas as contas da pessoa.

Também mexi em `operacional/lembrete_ponto.py`, `operacional/services/notification_triggers.py`
e no frontend `redesign/RedesignGuard.tsx` + `types/modules.ts`.

### 2. `coorte_ponto.py` é peça de arquitetura, não script

É a **fonte única** de quem deve ponto. Antes a regra estava duplicada entre o painel e o
lembrete; com duas cópias, a primeira mudança em uma faz as duas contarem coisas diferentes sem
ninguém perceber. Hoje é importada por três consumidores: painel, lembrete de WhatsApp e a
escalada de cobertura (`check_late_employees`).

Ela exclui por **data, nunca por marcação manual**: férias aprovadas cobrindo hoje, afastamento
sem data de retorno, e desligamento na última semana. Quem volta de férias reentra sozinho.

### 3. O que outra sessão não deve tocar

- `users` — passei o dia normalizando acesso: 68 contas restritas a `self:portal`, 21
  corporativas desativadas, 15 órfãs excluídas, 4 contas criadas. Mexer sem contexto reabre
  buracos que acabei de fechar.
- `employees` — alocações e posto de 3 pessoas lançados hoje; há um índice novo
  `ux_employees_cpf_ativo` que **recusa** segundo cadastro com CPF ativo repetido.
- `ponto_lembrete_log` (tabela nova) — dedup dos lembretes; apagar linha faz reenviar.
- `termination_processes` — registro do Keyson criado hoje, incompleto de propósito
  (datas de verbas pendentes do DP).

---

## B. Dois mundos paralelos

### 4. `/hr` × `/human-resources` — não são dois mundos, são um só entrelaçado

**Não é resíduo de reorganização, e não dá para matar um dos lados sem quebrar o outro.**
A prova concreta: `people_management/employee_portal/services/payslip_portal_service.py`
importa o repositório de `modules/hr/employee_portal/repositories/payslip_repository.py`.
O serviço mora num mundo e o repositório no outro, no mesmo fluxo do holerite do portal.

No `main_production.py` só encontrei montagem explícita de `/people-management/hr`.

**Não verifiquei** as 221 × 134 rotas uma a uma — para responder "qual está viva" com honestidade
seria preciso medir chamada real (log de acesso), não montagem. Isso eu não fiz.

### 5. A verdade do ponto é `gp_clock_punches`, sem dúvida

| Tabela | Linhas | Última |
|---|---|---|
| `gp_clock_punches` | **7.806** | hoje, 13/08 |
| `time_entries` | 0 | — |

`time_entries` é engrenagem morta. O ponto vivo é `gp_*`, e é essa família que o rollout, o
painel, o lembrete e a escalada usam.

### 6. Mesma resposta, mesmo padrão: `time_*` morto, `gp_*` vivo

`overtime_records` = 0 e `time_justifications` = 0, mas **`gp_justifications` = 1**. É o mesmo
par duplicado da pergunta 5, com o prefixo denunciando a geração.

`time_sheets` = 168 é a exceção: tem conteúdo apesar do prefixo. **Não verifiquei** se esses 168
espelhos são gerados hoje ou são carga histórica — vale medir antes de confiar.

Hora extra hoje sai do cálculo da folha, não de `overtime_records`. **Não verifiquei** onde
exatamente, e não vou afirmar.

### 7. GED: `ged_documents` é fachada; o conteúdo está em outras quatro tabelas

| Tabela | Linhas |
|---|---|
| `ged_kit_documents` | **2.625** |
| `onvio_documents` | 901 |
| `gedeon_document_index` | 739 |
| `ged_document_kits` | 73 |
| `ged_documents` | **0** |

As telas do GED têm conteúdo porque leem os kits e o índice, não a tabela de nome óbvio.
Quem auditar `ged_documents` e concluir "GED vazio" erra por 4.338 linhas.

---

## C. A fronteira com dinheiro e com o governo

### 8. Gate entre folha calculada e pagamento — **não verifiquei**

Não rastreei o caminho `fechar_folha` → `propor_pagamento` → efetivação bancária, nem se existe
rota que paga sem aprovação humana. É pergunta de dinheiro saindo; responder por intuição seria
pior que não responder. **Fica como pendência de investigação**, e eu recomendo que seja a
próxima, antes de qualquer coisa cosmética.

### 9. Holerites: as duas fontes NÃO se revezaram — elas duplicam, com valores diferentes

Este é o achado mais grave do módulo.

**Nenhuma fonte "passou a mandar".** As duas cobrem exatamente o mesmo período, 2026-01 a 2026-07:

| Origem | Tipo | Qtd | Período |
|---|---|---|---|
| `CONECTA-*` (nosso) | `mensal` | 363 | 2026-01 a 2026-07 |
| sem prefixo (importado) | `monthly` | 365 | 2026-01 a 2026-07 |
| sem prefixo | 13º 1ª e 2ª parcela | 94 | 2026-11 e 2026-12 |

Cruzando por funcionário + mês, são 459 combinações:

- **363 têm holerite duplicado** (um nosso e um importado)
- **0 têm apenas o nosso**
- 96 têm apenas o importado

E o pior: comparando o líquido dos 363 pares,

- **353 pares têm valores DIFERENTES**
- 10 batem
- **maior divergência: R$ 3.628,08** no mesmo funcionário, no mesmo mês

Ou seja: para praticamente todo holerite que geramos, existe outro com valor diferente para a
mesma competência. Não é migração inacabada — é contradição ativa no banco.

### 10. eSocial: `eventos_esocial` = 0 é verdade, e a transmissão é quase inexistente

O que existe é **espelho**, que é dado puxado do governo, não enviado por nós:

- `esocial_espelho_janelas` = 367
- `esocial_eventos_espelho` = 36
- `eventos_esocial` = **0**

Sobre o S-2230 do SST ter rodado em produção: **rodou pela metade**. Em `sst_afastamentos`,
1 registro está `transmitida` e 7 `nao_transmitida` — e **nenhum tem recibo S-2230 gravado**
(`recibo_s2230` vazio nos 8). Sem recibo, não há prova de entrega. Eu trataria como
"não transmitido" até alguém exibir o protocolo.

### 11. Quais eventos são nossos × da Portte — **respondo parcialmente**

Pelo que medi: nós não transmitimos nada hoje (0 eventos próprios, 0 recibos). Os 822 holerites
importados e o espelho do eSocial indicam que a Portte é quem opera de fato. **Não verifiquei**
o contrato de divisão evento a evento, e não vou inventar essa lista.

### 12. LGPD no holerite: o escopo é self-only, mas há um risco pior que vazamento cruzado

O portal busca por `get_by_employee_month_year(employee_id, month, year)`, com o `employee_id`
vindo do contexto do funcionário — **não achei rota que devolva holerite de outro funcionário**.
Nesse sentido, o escopo se sustenta.

**O problema é outro, e nasce da resposta 9.** O serviço não filtra por origem — zero menções ao
prefixo do código — e a consulta do repositório não tem ordenação. Com duas linhas para o mesmo
mês, **qual holerite o funcionário vê é indefinido**, e pode mudar entre um acesso e outro.

Não é vazamento. É pior no dia a dia: é a pessoa ver um valor hoje e outro amanhã, sem que nada
tenha mudado, num documento que ela usa para conferir salário.

---

## D. Qualidade do que já existe

### 13. Correção ao questionário: **as 9 chamadas quebradas não existem hoje**

Testei uma a uma. O serviço chama 7 métodos, e **todos existem** no repositório que ele importa:

`get_by_employee_month_year`, `get_latest`, `get_unread_count`, `get_years_available`,
`list_by_employee`, `record_download`, `record_view`.

Conferi que o repositório medido é o mesmo que o serviço importa (`modules/hr/employee_portal/
repositories/payslip_repository.py`, importado de forma lazy na linha 45 para evitar import
circular) — o erro clássico nesse tipo de medição é comparar com o repositório errado.

Se a medição do T2 foi feita em outro momento, alguém corrigiu no meio do caminho. Hoje não
procede. **A rota do holerite do portal não está quebrada por método faltando** — ela está
comprometida pelo dado duplicado da resposta 9.

### 14. As 5 telas vazias — **não verifiquei**

Não abri as 163 telas. Sem isso, dizer "vazio honesto" ou "tela morta" seria chute.

### 15. Do que eu não confio hoje: a folha, e agora com prova

Antes de medir, minha desconfiança era genérica. Agora é específica: **não confio em nenhum
número de holerite exibido em tela**, porque 97% dos pares divergem e o sistema não sabe qual
dos dois é o certo. Qualquer relatório que some líquido está somando uma escolha arbitrária.

Também não confio no eSocial como "feito" — 1 transmissão sem recibo não é entrega.

### 16. Número exibido que está errado: sim, dois

**O holerite** (resposta 9), pelo motivo acima.

**O painel do ponto**, até hoje: ele contava como pendente quem tinha rosto cadastrado pelo DP
mas não passou pelo primeiro acesso. A Graciene aparecia como pendente **e já tinha batido ponto
pelo Conecta PRO**. Corrigido hoje — pendentes caíram de 7 para 4, e os 4 são reais.

---

## E. O que é "fechado"

### 17. O que estaria funcionando se o DP estivesse pronto

1. **Uma única fonte de holerite por competência**, com regra explícita de qual manda — hoje são
   duas em contradição.
2. **eSocial com recibo**: todo evento transmitido com protocolo gravado, e o que não foi
   transmitido visível como pendência, não como silêncio.
3. **Ponto fechando o mês sozinho**: escala × batida × justificativa gerando espelho sem ninguém
   conferir na mão. Hoje falta a ponta da justificativa (`gp_justifications` = 1 registro).
4. **Adesão em 100%**: hoje são 45 de 49, com 4 pendentes reais e 5 cadastros de telefone
   impedindo o lembrete automático.
5. **Fronteira com dinheiro auditável**: saber, sem investigar, qual humano aprovou cada
   pagamento — o que a resposta 8 diz que eu ainda não sei.

### 18. Alarme falso: sim, e eu criei um hoje sem querer

`dp_ponto_a_fechar` e a escalada de cobertura estavam cobrando **gente que não devia ponto** —
Francisco Ramon de férias e Keyson em aviso prévio tinham 45 turnos futuros gerando alerta
diário para o Gonzaga e o Paiva. Alerta que ninguém podia resolver, todo dia, é exatamente o
tipo que ensina a ignorar o sino. Corrigido hoje, com a coorte aplicada também na escalada.

O `vigia_ausencia` é o caso extremo: rodava 32 vezes por dia entregando num bot de Telegram
apagado — jogando o resultado fora. Foi tirado do beat em 11/08.

### 19. O que doeria mais caro quebrando em silêncio por um mês

**A folha.** E não é hipótese: já está quebrada em silêncio há meses. Se ninguém conferir, o
erro sai no pagamento, vira passivo trabalhista e só aparece na reclamação. Um mês de holerite
errado em ~50 pessoas não se conserta com deploy.

Segundo lugar: **o eSocial**. Silêncio ali não dá erro na tela — dá multa, meses depois.

---

## F. Sobre o Arsenal

### 20. Não usei `backend/scripts/qa/`

Não posso relatar achado falso porque não rodei. Trabalhei com consulta direta ao banco e leitura
de código.

### 21. O que o roteiro não cobriu e fiz na mão

- **Verificar em transação desfeita.** Antes de subir a correção que impedia ressuscitar contas
  desativadas, rodei o UPDATE dentro de uma transação e dei ROLLBACK, comparando o antes e o
  depois. Provou o comportamento sem tocar no banco.
- **Distinguir "código no container" de "código na imagem".** `docker cp` engana: o teste passa e
  some no próximo recreate. Passei a verificar depois do recreate, não antes.
- **Contar pessoas, não linhas.** Errei aqui: reportei "4 líderes" porque contei contas; eram 3
  pessoas com 6 contas. `JOIN` com duplicata infla contagem em silêncio.

---

## Bônus: dois erros meus de hoje, e como percebi

**Errei ao propor consertar o endpoint em vez do dado.** A Elen não conseguia logar; achei que o
`/concluir` devolvia o e-mail errado e ia mudar o endpoint. Errado: a regra da casa é que
funcionário usa e-mail pessoal, então quem estava errada era a conta dela, criada com
`@conectamais.pro`. Percebi porque o Jordan disse a regra — não porque o código denunciasse.
**Lição:** antes de corrigir o código que produz um dado, confirme qual é a regra de negócio que
o dado deveria obedecer. O código estava certo para a regra errada.

**Errei ao generalizar uma exclusão sem perguntar o critério.** Tirei da coorte todo mundo com
processo de desligamento aberto, e isso removeu o Adailson, que trabalha normalmente até 04/09.
A diferença entre ele e o Keyson não é ter aviso prévio — é a distância do último dia. Percebi
porque o Jordan corrigiu.
**Lição:** "está saindo" não é um estado binário. Quando uma regra depende de "quanto falta",
o corte é decisão de operação e precisa de número explícito — hoje são 7 dias, nomeado no código.

Um terceiro, menor, já listado em 21: contar linhas de `JOIN` como se fossem pessoas.
