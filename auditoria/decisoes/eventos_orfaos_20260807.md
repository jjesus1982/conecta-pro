# Fila de decisão — eventos que disparam e ninguém reage (2026-08-07)

Medido com `python3 backend/scripts/orquestra_eventos.py` (READ-ONLY).

**Contexto:** o barramento tem 102 eventos declarados, 281 gravados no Redis (db 1).
Destes, **15 tipos disparam de verdade sem nenhum handler reagindo**. O evento **não se
perde** — fica no stream, replayável. O que falta é alguém agir.

**Por que isto é fila de decisão e não trabalho:** cada handler é **comportamento novo em
produção**. "O que deve acontecer quando este evento chega" é decisão de negócio, não de
engenharia — e três dos casos caem em território que suas regras marcam como seu
(operacional curado à mão, dinheiro com OTP).

Responda uma frase por linha. Com a frase, vira execução.

---

## Os que mais disparam

### 1 · `crm.cliente.ativo` — 14 disparos · publica: crm
Cliente passou a ativo.
- **(a)** operacional cria/reativa os postos do contrato → ⚠️ postos são curados à mão
- **(b)** financeiro abre a régua de faturamento
- **(c)** GED inicia o kit documental do cliente
- **(d)** nada — o evento fica só como trilha
**Recomendo (c):** é o que o GEDEON já faz para outros eventos, e não toca seu território.

### 2 · `dp.funcionario.transferido` — 12 · publica: people_management
Funcionário mudou de posto/lotação.
- **(a)** operacional move a alocação automaticamente → ⚠️ alocação é sua
- **(b)** operacional só **registra divergência** para você revisar
- **(c)** eSocial S-1020/S-2205 entra na fila de transmissão → ⚠️ gov
**Recomendo (b):** respeita a curadoria e ainda te avisa.

### 3 · `gedeon.cliente.espelhar` — 10 · publica: gedeon
Não está no catálogo `EventTypes` — evento ad-hoc criado fora da convenção.
- **(a)** formalizar no catálogo e dar handler
- **(b)** remover se for resíduo
**Decisão prévia:** alguém sabe o que ele faz? Se ninguém souber, é candidato a (b).

### 4 · `ponto.batida.registrada` — 8 · publica: people_management
Bateu ponto.
- **(a)** operacional atualiza presença ao vivo na tela
- **(b)** dispara verificação de cobertura do posto (alguém faltou?)
- **(c)** nada — o ponto já é lido direto do banco pelas telas
**Recomendo (c) por ora:** as telas já leem `gp_clock_punches`. (a) duplicaria caminho.

### 5 · `dp.beneficio.adicionado` — 6 · publica: people_management
Benefício adicionado ao funcionário.
- **(a)** folha recalcula a competência aberta
- **(b)** financeiro provisiona o custo
- **(c)** nada
⚠️ (a) mexe em cálculo de folha — **precisa da sua palavra**, é dinheiro do trabalhador.

### 6 · `dp.contrato.criado` — 5 · publica: people_management
Contrato de trabalho criado.
- **(a)** GED monta o kit admissional
- **(b)** assinatura ICP é solicitada automaticamente
- **(c)** eSocial S-2200 → ⚠️ gov, e hoje é a Portte quem transmite
**Recomendo (a).** (b) só se você quiser assinatura disparando sozinha.

### 7 · `dp.esocial.gerado` — 5 · publica: people_management 🏛️
Evento eSocial gerado.
- **(a)** transmitir ao governo → ⚠️ **irreversível**, e a folha hoje é da Portte
- **(b)** só registrar no espelho e alertar o DP
**Recomendo (b) com força.** (a) não deve ser automático em hipótese nenhuma.

### 8 · `crm.contrato.assinado` — 5 · publica: crm
Contrato comercial assinado.
- **(a)** operacional cria os postos previstos → ⚠️ seu território
- **(b)** financeiro cria a régua de faturamento
- **(c)** jurídico inicia o ciclo de vida (vencimento, reajuste)
**Recomendo (c) + (b).** (a) fica como alerta, não como criação.

### 9 · `dp.ponto.registrado` — 3 · publica: people_management
Parece **duplicata semântica** de `ponto.batida.registrada` (item 4).
**Decisão:** manter os dois ou consolidar? Dois eventos para o mesmo fato é dívida.

### 10 · `saude.ppra.atualizado` — 3 · publica: health_occupational
PPRA atualizado.
- **(a)** GED refaz o kit de SST
- **(b)** alerta quem tem ASO vinculado ao risco alterado
**Recomendo (a).**

### 11 · `operacional.diarista.criada` — 2 · publica: operacional
- **(a)** financeiro provisiona o custo da diária
- **(b)** nada
**Recomendo (b) por ora** — o fluxo de diarista já tem tela própria.

### 12 · `rh.avaliacao_desempenho.criada` — 2 · publica: people_management
- **(a)** notificar avaliador e avaliado
- **(b)** nada
**Recomendo (a)** — é notificação, risco baixo, valor direto.

### 13 · `financeiro.pagamento.recebido` — 2 · publica: financial 💰
- **(a)** baixa automática do contas a receber
- **(b)** CRM atualiza status de inadimplência
- **(c)** só alerta
⚠️ **Dinheiro.** (a) altera registro financeiro sem humano. Sua decisão.

### 14 e 15 · `rh.onboarding.item_concluido` · `rh.milestone.concluido` — 2 e 1
- **(a)** avançar o funil de onboarding
- **(b)** nada
**Recomendo (a)** — é fluxo interno de RH, reversível.

---

## Os 22 que NUNCA dispararam

Declarados e publicados no código, mas sem nenhuma ocorrência no stream:
`financeiro.pagamento.realizado`, `financeiro.inadimplencia.detectada`,
`crm.lead.convertido`, `operacional.turno.iniciado`/`.encerrado`,
`operacional.alocacao.criada`, `operacional.banco_horas.criado`,
`operacional.diarista.pagamento_processado`, `saude.afastamento.iniciado`, entre outros.

**Recomendação: não escrever handler para nenhum.** É código especulativo para fluxo que
não acontece. Se um dia disparar, o leitor mostra e aí se decide.

Vale investigar **por que não disparam**: a função `publish_*` existe e é chamada, mas o
caminho de código pode estar morto. É sintoma de funcionalidade desligada, não do bus.

---

## Resumo para decidir rápido

| Risco | Eventos | O que fazer |
|---|---|---|
| 🟢 baixo, recomendo ligar | 3, 6, 10, 12, 14, 15 | GED/notificação — reversível |
| 🟡 precisa da sua frase | 1, 2, 4, 8, 9, 11 | tocam operacional ou duplicam caminho |
| 🔴 não automatizar | 5, 7, 13 | folha, gov e dinheiro |
