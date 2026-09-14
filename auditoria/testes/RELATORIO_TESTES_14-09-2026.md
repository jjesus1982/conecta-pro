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

**E onze coisas estavam quebradas** — três delas impediam a tela de funcionar, e uma fazia o
sistema mentir todo dia sem ninguém perceber.

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

*O detalhamento de cada achado, com o passo a passo, o traceback e a medição que o provou,
está em `auditoria/testes/ACHADOS.md`.*

