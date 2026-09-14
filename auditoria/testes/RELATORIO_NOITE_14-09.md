# O que foi feito esta noite — 13 para 14 de setembro de 2026

Para Jordan Jesus. Em português claro, na ordem que você pediu.

---

## RESUMO EM SEIS LINHAS

1. **A Patrimonial emite nota fiscal pelo Conecta PRO.** Eram quatro defeitos empilhados, não um. Um deles derrubava a emissão das **duas** empresas.
2. **Setembro voltou a poder fechar.** As pendências de "o sistema não casa entrada com saída" caíram de **134 para 48** — eram defeito nosso, não erro de funcionário.
3. **Desliguei o puxador do Sólides/Tangerino**, como você mandou. Os 7 que ficam de fora estão listados e vigiados.
4. **As 4 alocações de demitidos e os 94 holerites fantasma sumiram.**
5. **Os "25 exames vencidos" não existem** como você pensava — explico abaixo, e é mais sério.
6. **Comecei a esteira dos botões que faltam.** Medi **326**; liguei os primeiros e já achei bug que nunca tinha funcionado.

---

## ITEM 1 — Assinar o contrato ❌ TRAVADO (e a trava é boa)

Tentei assinar o **CTR-2026-00022** e o próprio sistema me barrou:

> `assinar_contrato_empresa` não é executada por mim. Se eu rodar isto, SAI DA EMPRESA: a assinatura da empresa no instrumento, com o certificado ICP-Brasil — é ato jurídico, não rascunho.

O pedido ficou registrado na **Central de Aprovações** e exige o seu código (OTP). Não dá para eu contornar, e nem deveria: é a sua assinatura com certificado digital, vinculando a empresa.

**Mas eu descobri uma coisa tentando:** não existia botão nenhum para assinar contrato na tela. Nem para você. **Agora existe** — o CTR-2026-00022 tem o botão "Assinar" na própria linha, pedindo que você digite ASSINAR para confirmar.

> **Contrato:** Chácaras Maiápolis, controle de acesso, **R$ 46.320,00** · entrada de R$ 23.160 + 2 parcelas de R$ 7.720 + 1 retida contra o Termo de Entrega · assinatura pendente desde **11/09**, vence **11/10**.
> **Atenção:** você já assinou uma versão anterior em 10/09 às 00:11, mas o documento mudou depois — a assinatura antiga não cobre o texto atual. E o pedido enviado à síndica **Mayana** foi cancelado; o link que ela recebeu não funciona mais.

---

## ITEM 2 — Nota fiscal da Patrimonial ✅ RESOLVIDO

**Funciona.** Emiti de verdade e o governo autorizou:

```
chave de acesso 13026032266014833000110000000000000326093644058546
                          ^^^^^^^^^^^^^^ o CNPJ da Patrimonial na própria chave
```

Não era "o certificado está vencido". Eram **quatro defeitos empilhados**, e só apareciam um de cada vez, porque o governo recusa um erro por vez:

| # | O que estava errado | Quem sofria |
|---|---|---|
| 1 | O sistema tinha **um único emissor fixo**. Qualquer nota saía com o CNPJ e o certificado da Eletrônica. | Só a Patrimonial |
| 2 | Quando a inscrição municipal vinha vazia, o código caía num **valor fixo: a inscrição da Eletrônica**. Outra empresa emitiria com a inscrição alheia. | Qualquer empresa nova |
| 3 | O **código do serviço** enviado ao governo era de outra tabela. O governo respondia «este código não existe» em **toda** emissão. | **As duas empresas** |
| 4 | Empresa do Simples Nacional precisa declarar o regime de apuração. Faltava. | Só a Patrimonial |

**O nº 3 é o mais grave:** nenhuma emissão funcionava, nem da Eletrônica, se alguém usasse o padrão do sistema. Só passava quem soubesse digitar o código certo à mão.

**Trava nova, e é a que mais importa:** agora o sistema confere que **o CNPJ do certificado é o CNPJ que assina**. Se alguém pedir uma nota da Patrimonial escrevendo o CNPJ da Eletrônica, a emissão para com o motivo na tela. Nota assinada pela empresa errada não sai daqui.

**Decisão que deixei para você:** as duas empresas continuam no **ambiente de testes** do governo. Emitir em produção cria documento fiscal de serviço que não foi prestado — isso é decisão sua, e é um campo só na tabela de empresas. Quando quiser faturar de verdade, me avise.

---

## ITEM 3 — As 182 pendências de ponto ✅ MAIORIA ERA DEFEITO NOSSO

As 180 eram de dois tipos bem diferentes, e misturá-los confunde:

- **134 eram de "pareamento"** — o sistema não conseguia casar entrada com saída. **Essas eram defeito nosso, e caíram para 48.**
- **46 eram "dia sem batida"** — dia de escala em que ninguém bateu. Esse número **não depende de conserto: ele cresce todo dia** até alguém tratar, e hoje está em 80 (o dia virou durante a noite, e os 7 que não usam o app agora aparecem aqui porque o Tangerino não os cobre mais).

Nenhuma das 134 era erro de funcionário. Foram três defeitos:

**Defeito 1 — duas fontes no mesmo dia.** O que o Tangerino trazia não era batida: era a **grade da escala**. A prova: 422 registros dele com apenas **48 horários distintos** e 382 em hora cheia, contra 763 registros do app com **763 horários distintos**. Nos dias em que as duas fontes existiam, a grade (que vem 1h adiantada) entrava junto e quebrava o pareamento.

**Defeito 2 — turno em andamento virava pendência.** Quem entrou às 19:00 de hoje sai às 07:00 de amanhã. O sistema cobrava a saída no mesmo instante.

**Defeito 3 — uma fresta de 1 segundo.** Quem trabalha 08:00–18:00 tem **exatamente 14 horas** entre a saída e a entrada seguinte. A janela de contagem do app abria em "14 horas e 1 segundo" — a saída da véspera vazava para dentro, e o app rotulava a **entrada da manhã como "saída para o almoço"**. O Nailson teve 4 dias assim em setembro.

### O que sobrou, e de quem é (medido às 00:50 de 14/09)

| | Quantidade | O que fazer |
|---|---|---|
| **Fila real do DP** | **120** em 39 pessoas | Corrigir na tela (veja abaixo) |
| Gente que ainda não bate pelo app | 14 | Supervisor Paiva / instalar o app |

Dos 120, **48 são de pareamento** (batida com rótulo errado — conserto rápido, um clique cada) e **72 são dias sem batida** (falta de verdade ou ponto não registrado — exige conferir com a pessoa).

> **Atenção ao número que sobe:** "dia sem batida" cresce sozinho todo dia enquanto ninguém trata. Recalculei setembro depois do conserto — **sem fechar nada** — para o painel do DP mostrar a fila real e não a de ontem.

**E agora existe botão para corrigir.** A tela *Gestão de Pessoas › Ponto eletrônico* ganhou "**Corrigir**" em cada linha: troca o tipo da batida com motivo obrigatório, que vai para a auditoria. O horário não muda — horário é registro de fato. Isso também nunca teve botão: o DP via a batida errada e ia ao banco.

---

## SOBRE DESLIGAR O SÓLIDES/TANGERINO ✅ FEITO

Desliguei o `solides-sync-punches`, que rodava de 15 em 15 minutos. A rotina continua existindo para chamada manual; só não roda mais sozinha.

**Os 7 que você conferiu:** os 4 sem app e os 3 que pararam. Criei uma verificação diária que os mostra separados por "nunca usou" e "usava e parou" — porque a ação é diferente.

> **Achado sobre o Geilson:** você disse que ele está afastado. **O sistema não sabe disso.** Não há afastamento nem férias registrados para ele. Consequência: o painel cobra ponto dele, o lembrete manda mensagem, o espelho marca falta todo dia e **o eSocial não tem o S-2230**. Não registrei o afastamento por conta própria — sem data de início, tipo, CID e atestado, eu estaria inventando um fato trabalhista.

---

## ITEM 4 — Alocações de quem saiu ✅ FEITO

4 encerradas, com a data de término igual à data de demissão de cada um (não a data de hoje — a alocação acabou quando a pessoa saiu):

Fernando Miguel (Michelangelo), Jonathan Mendes (Laranjeiras), Keyson Pinto (Prime Arena), Daniel Souza (Ideal Flores).

**Não mexi no Aryelton Braga** (Prime Arena): ele está **suspenso**, não demitido. Suspensão é temporária e a pessoa volta ao mesmo posto.

Criei uma verificação diária para isso não voltar a acontecer — ninguém errou ao não encerrar, porque a demissão entra por importação e nenhum caminho do sistema escreve nessa tabela.

---

## ITEM 5 — Os 94 holerites fantasma ✅ FEITO

94 apagados (47 de novembro + 47 de dezembro de 2026, R$ 66.274,80 somados, criados todos em 03/08).

Antes de apagar, provei que eram órfãos: **nunca abertos, nunca baixados, sem pagamento ligado, sem itens**. Guardei uma cópia completa em CSV.

A verificação diária que criei já pegou uma **terceira família** que ninguém tinha visto: 12 holerites de agosto **sem origem declarada** — não entram em nenhum lado da tela Conecta × Portte. São os funcionários de teste do kit Conecta Village (09/09), então os deixei de fora do alarme.

---

## ITEM 6 — Os 25 exames vencidos ⚠️ O PROBLEMA É OUTRO, E É PIOR

Fui montar a fila de renovação e os 25 tinham **a mesma data de validade** (01/06/2026) e o mesmo tipo. Olhando a tabela inteira:

```
96 dos 97 exames assinados por "Dr. Carlos Mendes, CRM-AM 4521"
3 datas de realização distintas para 96 exames
0 com clínica preenchida
0 com documento anexado
96 criados no mesmo dia: 16/03/2026
```

**Não são 25 exames que venceram. É uma carga de março com datas de enfeite — e ninguém na empresa tem ASO comprovado no sistema.**

O alarme estava certo por acaso e errado por construção: "renovar 25" é uma tarefa que não existe. A tarefa real é **carregar os ASOs de verdade**.

Isso pesa além da tela: o ASO autoriza a pessoa a trabalhar, alimenta o S-2220 do eSocial e é dos primeiros documentos que a fiscalização pede.

**Não apaguei a carga.** Apagar deixaria a tela em zero, que parece "tudo certo" — o pior resultado possível. E é decisão sua.

---

## A ESTEIRA QUE VOCÊ PEDIU — botões que faltam

Você disse: *"percebi vários botões, funções e recursos que deveriam ter... tanto que todas as vezes tive que recorrer ao terminal"*.

Primeiro medi. Escrevi um instrumento que pergunta **"existe alguma coisa que o sistema sabe fazer e nenhuma tela oferece?"**. Começou dizendo 350; hoje diz **262**, e a diferença toda foi eu descobrindo falsos positivos **indo ligar o botão e achando o botão já lá**:

- ação que só aparece em certa condição (o botão "Ativar cliente" só existe se houver cliente inativo);
- o mesmo recurso montado em dois endereços (15 do disciplinar eram o mesmo recurso);
- o redesign tendo porta própria para a mesma ação;
- plural contra singular (`/vigilante/cursos` × ação `vigilante-curso`) — sozinho isso escondia **5 telas do vigilante que já existiam**.

Conto isso porque é a diferença entre um número e um número confiável: os 262 que sobraram são buraco de verdade.

### O que já liguei esta noite

**Contratos — 7 ações que só existiam no terminal:**
Aditivo · Incluir item · Calcular reajuste · **Assinar pela empresa** · Excluir rascunho · Editar contrato · (e Cancelar férias, abaixo)

> **E o botão revelou um bug:** "Incluir item num contrato" **devolvia erro sempre, desde sempre**. Ninguém tinha visto porque não havia botão — a capacidade existia no papel e quebrava na primeira chamada.

**Ponto:** botão "Corrigir batida" (a fila de 95 do DP).

**AFD — o arquivo que a fiscalização pede primeiro:** ele existia no banco (39 linhas, numeração contínua) e **não aparecia em tela nenhuma**. Agora tem aba própria em *DP › Ponto & Jornada*, com a lista das linhas e dois botões de download: **AFD do mês** e **AEJ da competência**. O CNPJ vem da tabela de empresas — ninguém digita.

> ⚠️ **E a tela avisa em vermelho:** o arquivo sai com o nome `AFDSEM_INPI...` porque **o instrumento legal do REP-P não está registrado** — faltam o **INPI**, o **atestado técnico** e o **termo de responsabilidade**. Um AFD sem INPI é recusado numa fiscalização. Gerar arquivo que não vale é pior do que não gerar, então está escrito na tela.

**Justificar falta/atraso:** existia o botão de APROVAR uma justificativa, mas não o de CRIAR. Agora existe.

**Cancelar férias:** inclusive férias já aprovada que o colaborador não vai tirar. Cancelar não apaga — marca como cancelada e a trilha fica.

**Descontos recorrentes:** existem **97 descontos ativos** no banco — consignados, pensões alimentícias e empréstimos que entram na folha todo mês — e **nenhuma tela**. Corrigir o valor de um consignado ou encerrar uma pensão exigia o banco. Agora tem aba própria em *DP › Folha de pagamento*: lista, editar na linha, encerrar e "Novo desconto".

> **E o teste achou uma falha no encerramento:** ele marcava o desconto como inativo e **deixava a data de fim vazia**. Daqui a um ano ninguém saberia se o consignado parou em setembro ou em março — e em pensão alimentícia essa data tem consequência judicial. Agora grava a data em que parou (sem sobrescrever uma data de fim já programada).

---

## O QUE FICA PARA VOCÊ DECIDIR

1. **Assinar o CTR-2026-00022** — agora tem botão na tela, e vence em 11/10. Conferir a cláusula antes: o documento mudou depois da sua assinatura de 10/09.
2. **Reabrir a assinatura da síndica Mayana** — o link dela foi cancelado e não funciona mais.
3. **Nota fiscal em produção?** Está tudo pronto; falta você dizer quando sair do ambiente de teste.
4. **Registrar o afastamento do Geilson** — preciso da data de início, tipo, CID e atestado. Sem isso o sistema continua cobrando ponto dele e o eSocial fica sem o S-2230.
5. **O instrumento legal do REP-P** (INPI + atestado + termo) — enquanto não existir, o AFD não vale em fiscalização.
6. **Os ASOs de verdade** — a carga de março não é exame. Ninguém tem ASO comprovado.
7. **Cadastrar cliente** ainda não tem tela. Continua na fila da esteira.

---

## O QUE CONTINUA NA ESTEIRA

Das 326 ações sem botão, liguei as primeiras. As maiores famílias que faltam:

| Quantas | Onde | Exemplos |
|---|---|---|
| 16 | Recursos Humanos | aprovar candidato, avaliação de desempenho, plano de carreira, treinamento |
| 14 | Departamento Pessoal | benefícios da folha, contrato de trabalho, admissão |
| 12 | Rondas | criar, iniciar, pausar, concluir e cancelar ronda pela tela do supervisor |
| 12 | GED | criar/aprovar/enviar kit, assinar documento |
| 10 | Escalas | — |
| 8 | Contas a receber | — |

Sigo por elas.

---

## VERIFICAÇÃO FINAL — medido de fora, depois da última publicação

Tudo abaixo foi conferido pela **mesma porta que a tela usa**, não por dentro do código:

| O quê | Resultado |
|---|---|
| Os 34 módulos do sistema | Todos respondem com conteúdo |
| NFS-e da Patrimonial | CNPJ 66014833000110 · inscrição 721042001 · Simples declarado |
| NFS-e da Eletrônica | CNPJ 35710481000103 · inscrição 45177801 · sem Simples (correto, é Lucro Real) |
| Baixar AFD | 200 · 6.087 bytes |
| Baixar AEJ | 200 · 60.456 bytes |
| Painel de fechamento do ponto | 200 · 51 pessoas · recalculado |
| Telas novas no DP | AFD, Justificar ponto, Descontos e Novo desconto — as quatro no ar |

**Dois erros meus que a verificação pegou:**

1. Eu conferi as telas pelo endereço `dp` e concluí que **nenhuma** tinha nascido. O endereço certo é `departamento-pessoal`; `dp` é nome do sistema antigo. As quatro estavam lá o tempo todo.
2. Consequência do mesmo engano: o teste de "os 14 módulos respondem" que venho rodando **media respostas vazias como sucesso** — alguns daqueles nomes não são módulos do sistema novo. Refiz com os 34 nomes reais, e todos respondem com conteúdo (dois deles são de chat e vêm prontos do próprio site, o que é o esperado).

## COMO EU TRABALHEI (e o que deu errado no meio)

Publiquei **5 vezes** durante a noite, sem tirar o sistema do ar, e conferi os 32 módulos depois de cada mudança.

Três erros meus, que conto porque explicam o método:

1. **Medi a coisa errada e quase relatei "zero pendências"** — meu script procurava a chave `anomalies` e o sistema usa `anomalias`.
2. **Uma tela que eu criei não aparecia e não havia nada no log.** O código de montagem engole a exceção e mantém a tela antiga no ar. Só descobri comparando as colunas que apareciam com as que eu tinha escrito.
3. **Deixei rastro num teste** — um item de teste somou R$ 10 no valor de um contrato, e uma linha de auditoria de ponto ficou com autor "0". Restaurei os dois. O segundo virou uma trava nova: agora o sistema **recusa** corrigir ponto se quem está corrigindo não for um usuário de verdade. Trilha com autor inexistente não é trilha.

---

*Relatório de 14 de setembro de 2026, madrugada. A versão técnica de cada item está nas mensagens dos commits — cada uma traz o número medido antes e depois, e o que foi deliberadamente NÃO feito.*
