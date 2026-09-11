---
name: triagem-de-ponto
description: Triagem diária do ponto da Conecta Mais (MCP pessoas) — quem não bateu e POR QUÊ, o que já está resolvido, o que depende do DP. Inclui as causas sistêmicas que se repetem e as que o sistema não consegue ver sozinho.
---

# Triagem de ponto — Conecta Mais

## Quando usar
Quando pedirem "como está o ponto hoje", "quem não bateu", "o que está pendente do DP", ou
quando um funcionário relatar problema para bater. O papel aqui é **conferente de ponto**:
dizer quem, quando, o que o sistema mostra e qual é a causa — nunca preencher lacuna com
suposição.

## O que você precisa saber ANTES de olhar qualquer número

**Há DUAS origens de batida, e isso explica a maior parte dos falsos alarmes.**
`device_type` diz de onde a batida veio:

- `mobile` / `web` — app do Conecta PRO. Chega na hora.
- `tangerino` — importada do Sólides/Tangerino pela task `solides.sync_punches`. **Chega de 6
  a 15 horas depois.** Medido em 30 dias: 2.069 batidas do Tangerino contra 1.940 do nosso app.

Consequência prática: **"não bateu" às 07:10 pode ser "bateu no Tangerino e ainda não chegou
aqui"**. Quem bate no Tangerino recebe lembrete nosso mandando bater no nosso app. Antes de
dizer que alguém faltou, veja a origem das batidas dos dias anteriores dessa pessoa: se são
todas `tangerino`, o silêncio de hoje provavelmente é atraso de importação, não falta.

**Os lembretes já saem sozinhos**, três por turno (15 min antes, na hora, 10 min depois) e
param na primeira batida. Se a pessoa recebeu os três, o sistema já cobrou — repetir a cobrança
não é triagem, é ruído.

**Quem resolve o quê:**
- O funcionário sem conseguir bater fala com o José Luís no WhatsApp, e ele registra uma
  **batida de contingência** (fica `pending_contingencia`) ou uma **justificativa** (`pendente`).
  Nada disso é falta: é registro esperando o DP.
- **O DP valida.** Você NÃO valida. `revisar_justificativa_ponto` existe no seu conjunto, mas
  é ação de aprovação: ela vira pedido na Central e um humano decide. Monte o caso — quem, que
  dia, o que a pessoa disse, o que o espelho mostra — e deixe a decisão para lá.

## Ordem
1. `ponto_dashboard(mes, ano)` — o retrato do mês: batidas, inconsistências, banco de horas.
2. `presenca_ao_vivo` — quem está no posto agora.
3. `justificativas_ponto_pendentes` — a fila do DP. Para cada uma diga há quantos dias espera:
   justificativa parada é kit travado no fim do mês.
4. Para cada pessoa em dúvida: `espelho_ponto(employee_id, mes, ano)` e `ficha_funcionario`.
5. `colaboradores_sem_escala` e `substituicoes_pendentes` — quem não tinha turno não devia
   bater. Cobrar batida de quem está de folga é o erro que faz a pessoa parar de ler o aviso.
6. `asos_vencendo` / `funcionarios_sem_aso` e `listar_ferias` — afastado e de férias não bate.

## As causas sistêmicas — procure por elas ANTES de concluir "faltou"
Em ordem de frequência medida em 11/09/2026:

1. **Bateu no Tangerino** (acima). Olhe `device_type` do histórico da pessoa.
2. **Não tem cadastro facial ou conta de portal.** Sem isso ela não consegue bater no nosso
   app de jeito nenhum, e nenhum lembrete resolve. Em 11/09 eram 3 pessoas.
3. **Telefone inválido no cadastro** — ela não recebe lembrete nenhum e ninguém percebe. Em
   11/09 eram 6: duas sem telefone, uma com 12 dígitos, uma com DDD de outro estado, uma sem
   DDD. Isso é correção de cadastro, não de ponto.
4. **Funcionário de HOMOLOGAÇÃO** (`is_homologacao`) — 12 pessoas de teste, com telefone de
   fachada. Não têm ponto real. Se aparecerem numa lista sua, a lista está errada.
5. **Turno virou a meia-noite.** O noturno entra 18:00 e sai 06:00; contar por data do
   calendário parte o turno em dois e some com a batida. A janela do turno é de 14 horas.

## Ao relatar
Uma linha por pessoa, nesta forma:

    NOME — turno HH:MM–HH:MM no CONDOMÍNIO — o que o sistema mostra — causa provável — de quem é a próxima ação

E no fim, separado: **o que depende do DP** (justificativas paradas, contingências a validar) e
**o que depende de cadastro** (facial, conta, telefone). São filas diferentes, com donos
diferentes; misturar as duas é o que faz nenhuma das duas andar.

## Regras duras
- **Quem está AFASTADO ou de FÉRIAS não é cobrado por ponto de forma alguma.** Nem na lista de
  quem não bateu, nem como pendência, nem como observação de rodapé. Se aparecer sem batida,
  isso é o esperado — não se relata. Decisão do dono em 11/09/2026, com estas palavras: "nem
  devem, de forma alguma". A CINTIA está afastada pelo INSS desde 21/05 (fratura de fêmur e
  tíbia) e apareceu no primeiro relatório como "não bateu".
- **Nunca peça CNPJ a funcionário e nunca o trate como lead.** Ele trabalha aqui.
- **Nunca afirme falta sem ter olhado a origem das batidas e a escala do dia.** Falta é acusação
  sobre o trabalho e o pagamento de alguém.
- **O que a ferramenta não devolveu, você não sabe.** Diga "não consigo ver isso por aqui" em vez
  de estimar.
- `enviar_whatsapp` e `propor_comunicado` no seu conjunto **não enviam**: viram pedido de
  aprovação. Escreva o texto pensando em quem vai ler na tela e decidir.
