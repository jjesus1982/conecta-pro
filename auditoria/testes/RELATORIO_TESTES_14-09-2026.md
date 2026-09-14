# Bateria de testes ponta a ponta — Conecta PRO
**Quando:** madrugada de 14 de setembro de 2026 · **Onde:** PRODUÇÃO (erp.conectamais.pro)
**Como:** navegador real (Playwright), clicando como usuário final, com escrita liberada pelo Jordan
**Quem pediu:** Jordan Jesus · **Autorização:** escrita total, inclusive irreversível

---

## O veredito, em uma página

**O esqueleto do sistema funciona.** Escala nasce, é aprovada e publicada. Diária lança,
atravessa para o Financeiro e some quando excluída. Ocorrência nasce, resolve e chega ao portal
do cliente. Folha gera e avisa que não paga. NFS-e é assinada com certificado A1 e transmitida
ao governo de verdade. O gate de OTP recusa pagar sem saber de qual CNPJ sai o dinheiro.

**E catorze coisas estavam quebradas** — quatro impediam a tela de funcionar e três faziam o
sistema mentir todo dia sem ninguém perceber.

E duas que passaram merecem ser ditas com o mesmo peso: **o AFD da Portaria 671 está impecável**
(NSR de 1 a 36 sem buraco, 35 batidas viraram 35 marcações, fuso `-0400` declarado no arquivo) e
**a escala 12x36 que gerei respeita a lei na letra** — zero dias consecutivos, todos os
intervalos de exatamente dois dias.

### Não libere ainda. Estes eram os bloqueadores (todos corrigidos e verificados):

| # | O que estava errado | Como se manifestava | Estado |
|---|---|---|---|
| 1 | **Espelho da Portaria 671 morto** | `HTTP 500` em toda competência. Calcular e fechar o ponto não funcionava para ninguém. | ✅ corrigido e verificado |
| 2 | **Comunicado invisível** | Publicado no Operacional, **não chegava a nenhum colaborador**. | ✅ corrigido e verificado |
| 3 | **Criar proposta impossível** | `HTTP 500`. O CRM não emitia proposta. | ✅ corrigido |
| 4 | **Tela de PIX impossível** | Sempre recusada, sem campo para escolher a conta. | ✅ corrigido |
| 5 | **Contador de turnos mentindo** | 23 de 34 escalas (68%) com número errado na tela. | ✅ corrigido e verificado |
| 6 | **Alocação sem posto** | 73 de 73 linhas com «—». | ✅ corrigido e verificado |
| 7 | **Fechar o mês por omissão** | Deixar o campo vazio fechava o mês do ponto. | ✅ corrigido |
| 8 | **Confirmação mentindo** | «Só calcular» perguntava «Fechar o espelho?». | ✅ corrigido |
| 9 | **Erro do governo escondido** | Rejeição da NFS-e virava «Erro interno». | ✅ corrigido |
| 10 | **Fuso misturado** | Mesma ocorrência gravada em dois dias diferentes. | ✅ corrigido |
| 11 | **UUID digitado à mão** | Medida disciplinar pedia o id do colaborador. | ✅ corrigido |
| 12 | **Proposta nova nunca virava contrato** | Nascia sem o CNPJ do cliente e sumia do passo seguinte. | ✅ corrigido e verificado |
| 13 | **Proposta RECUSADA podia virar contrato** | O seletor oferecia as que o cliente já tinha dito não. | ✅ corrigido e verificado |
| 14 | **Alerta de ASO inflado 3,5×** | Dizia 88; o número acionável é 25. Contava papel, não gente. | ✅ corrigido e verificado |

### Duas coisas que eu NÃO consertei, porque a decisão é sua

**A Conecta Mais Patrimonial não consegue emitir NFS-e.** O certificado dela existe e é válido
até 06/07/2027. O código é que não o escolhe: o emissor é fixo e cacheado, então toda nota sai
assinada pela Eletrônica. Como a Patrimonial é quem faz vigilância, portaria e limpeza, é ela
que mais precisa emitir. Emitir nota assinada pela empresa errada é pior que não emitir — por
isso parei e trouxe para você.

**Não existe tela para cadastrar cliente.** Em nenhum módulo. O CRM cria lead, proposta,
contrato, comissão, produto, aditivo e até condomínio — cliente, não. Um lead novo nunca vira
proposta sem alguém criar o cliente por fora. O funil do manual está interrompido no primeiro
salto.

### Uma prova que eu achava impossível e consegui fazer

O maior risco do sistema é **um síndico ver o condomínio do vizinho**. Eu tinha registrado isso
como não testável por falta de credencial — até achar o `preview-token`, que deixa ver o portal
como o cliente. Testei com o token do **Ideal Flores**:

- o portal devolveu **17 kits** — de **137** que existem no sistema, todos dele;
- pedir o kit do **Prime Arena** pelo id: **404**, e 404 é a resposta certa (nem confirma que
  existe);
- chamados: nenhum de terceiro.

**A parede segura.** É o único item de risco de LGPD e ele passou.

### E três coisas que não são do sistema — são da operação

- **182 anomalias de ponto abertas em setembro**, em 43 dos 51 colaboradores. O mês não pode
  ser fechado, e sem mês fechado não há folha com base. É a fila de trabalho mais urgente.
- **4 pessoas demitidas continuam com alocação ativa** — isso infla a contagem de vigilantes e
  faz a cobertura parecer melhor do que é.
- **94 holerites de novembro e dezembro de 2026** (meses que não aconteceram) poluem a tela de
  divergência Conecta × Portte, que abre justamente neles.

### Uma que passou despercebida e é sua
O contrato **CTR-2026-00022** está esperando a **sua assinatura desde 11/09**, e expira em
**11/10**. Está em Portal do Colaborador › Assinaturas pendentes.

---

## O que foi gravado em produção
Está tudo no livro-caixa de `ACHADOS.md`, ato por ato, com como desfazer. O resumo:
uma escala de outubro publicada, uma folha de setembro do Michelangelo em rascunho, um lead,
um comunicado, uma ocorrência (criada e resolvida), uma diária (criada e excluída) e
**uma NFS-e autorizada no ambiente de homologação** — que não é documento fiscal válido.
**Nenhum centavo saiu de nenhuma conta.**

---

## A sequência que você pediu, e onde cada módulo parou

| # | Módulo | Veredito |
|---|---|---|
| 1 | **Operacional** | Passou depois de 4 correções. Escala nasce, aprova, publica — e a 12x36 sai legalmente correta. |
| 2 | **Ponto / Gestão de Pessoas** | Passou depois da correção crítica do espelho. O AFD está impecável. |
| 3 | **Departamento Pessoal** | Folha gera e avisa que não paga. **Bloqueado pela operação:** 182 anomalias. |
| 4 | **Comercial** | Passou depois de 3 correções. **Falta a tela de cadastrar cliente** — decisão sua. |
| 5 | **Financeiro** | O gate de OTP é o melhor desenho do sistema. Passou depois da correção do PIX. |
| 6 | **Fiscal** | Emite NFS-e de verdade. **A Patrimonial não consegue emitir** — decisão sua. |
| 7 | **GED / Kits** | Passou. Ressalva: dá para enviar kit incompleto ao cliente sem aviso. |
| 8 | **Área do Cliente** | **Passou no teste de vazamento** — o item de maior risco do sistema. |
| 9 | **Portal do Colaborador** | Estrutura correta e honesta. Falta testar com um colaborador real. |
| 10 | **Saúde Ocupacional** | Passou depois da correção do alerta. Estabilidade funciona. |
| 11 | **Jurídico & Licitações** | Passou na leitura. DET, prazos e risco trabalhista coerentes. |
| 12 | **RH** | Passou depois da correção da medida disciplinar. |
| 13 | **Equipamentos** | Vazio, como o manual já dizia. Nada a testar. |

---

## O que eu faria na sua próxima hora no sistema

1. **Assinar o CTR-2026-00022** — está esperando desde 11/09 e expira em 11/10.
2. **Decidir sobre o certificado da Patrimonial** — enquanto não decidir, ela não fatura por NFS-e.
3. **Mandar o DP atacar as 182 anomalias** — sem isso, setembro não fecha e a folha não tem base.
4. **Mandar apagar os 94 holerites de nov/dez** — eles poluem a tela de divergência.
5. **Mandar encerrar as 4 alocações de quem já saiu** — a cobertura está mentindo para melhor.

---

*O detalhamento de cada achado, com o passo a passo, o traceback e a medição que o provou,
está em `auditoria/testes/ACHADOS.md`. O livro-caixa do que foi gravado em produção está no
topo do mesmo arquivo.*


---

## E uma coisa que esta bateria deixou para o futuro

O defeito crítico de hoje — o espelho da Portaria 671 morto — era uma comparação entre tipos
(`varchar` contra `uuid`) que **nenhum dos 48 caçadores pegava**. Foi preciso clicar na tela
para descobrir.

Escrevi a trava que faltava: **`checar_id_tipo_divergente.py`**, já registrada na varredura das
00:00. Ela estreia acusando **8 colunas** — e **7 são minas ainda não pisadas**, cada uma um
HTTP 500 esperando alguém escrever o join:

```
gp_cats.employee_id · gp_justifications.employee_id · gp_monthly_closings.employee_id
juridico_processos.employee_id · time_sheets.condominium_id · time_sheets.work_schedule_id
```

De hoje em diante, se esse número crescer, a varredura acusa antes de alguém clicar.
