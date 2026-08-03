# DP — Afastamentos: registro × realidade (2026-08-03)

> READ-ONLY. Nada foi alterado. Afastamento tem peso legal (estabilidade art. 118 da Lei 8.213),
> então a correção é decisão humana — aqui está a evidência para decidir.

## Problema 1 — o registro cobre 24% da realidade

| | Pessoas | Valor pago |
|---|--:|--:|
| Afastamento **pago na folha** (fonte validada, Δ=0 vs Portte) | **29** | R$ 24.926 |
| Registrado em `sst_afastamentos` | 7 | R$ 15.042 |
| **Só na folha — nunca registrado no DP** | **22** | R$ 9.884 |

Ou seja: 22 pessoas tiveram afastamento pago e o módulo de DP não sabe que existiram.
Isso quebra qualquer coisa que dependa do registro — cálculo de folha nativo, eSocial S-2230,
controle de estabilidade, escala.

## Problema 2 — 4 dos 5 "afastados ativos" estão trabalhando

Cruzei os afastamentos abertos com as batidas de ponto posteriores ao início do afastamento:

| Colaborador | Status no sistema | Afastado desde | 1ª batida depois | Batidas depois | Veredito |
|---|---|---|---|--:|---|
| ADAILSON SERRA ALVES | ativo | 25/03 | 03/06 | **116** | voltou — registro parado |
| CINTIA BEZERRA OLIVEIRA | em_andamento | 21/05 | 03/06 | **56** | voltou |
| ARYELTON BRAGA FIGUEIRA | ativo | 02/02 | 02/03 | **44** | voltou |
| FERNANDA VINHOTE MACIEL | ativo | 22/02 | 02/03 | **39** | voltou |
| CARLOS ALBERTO ASSIS DE LIMA | ativo | 02/03 | — | **0** | ✅ consistente: segue afastado |

ADAILSON tem folha até julho **e** 116 batidas — está trabalhando há meses com o sistema
achando que está afastado desde março.

## Por que isso importa além do cadastro

- **eSocial S-2230**: afastamento aberto sem evento de retorno fica pendente no governo.
- **Folha nativa**: o motor não modela afastamento; medi antes que os "não-ativos" carregam
  ~R$12.250 do delta da folha paralela. Sem registro correto, isso não fecha.
- **Estabilidade**: se algum for acidentário (art. 118), a data de retorno define os 12 meses
  de estabilidade. Fechar com data errada tem consequência trabalhista.

## O que NÃO fiz (e por quê)

Não fechei nenhum afastamento automaticamente. A data de retorno tem efeito legal, e "primeira
batida após o início" é um **candidato**, não uma certeza — a pessoa pode ter batido ponto num
dia isolado, ou o retorno pode ter sido formalizado em data diferente.

## Sugestão de encaminhamento

1. **Confirmar os 4 retornos** usando a 1ª batida como data candidata (o DP valida).
2. **Investigar por que 22 afastamentos nunca foram registrados** — provavelmente o fluxo real
   acontece fora do sistema (atestado entregue no papel / lançado direto na Portte).
3. Só depois disso faz sentido construir o cálculo de afastamento (15 dias empregador × INSS),
   porque cálculo sobre registro furado não resolve nada.

---

## Execução (2026-08-03, autorizado pelo Jordan: "confirma os 4 retornos usando a primeira batida")

Ao abrir os registros para executar, apareceu informação que **não estava no relatório acima**
(tipo e motivo do afastamento) e que muda a decisão em 2 dos 4 casos. Fechei só os limpos.

### ✅ Encerrados (2)

| Colaborador | Tipo | Afastado | Fim previsto | **Retorno** |
|---|---|---|---|---|
| ADAILSON SERRA ALVES | doença (dengue, atestado 7d) | 25/03 | 02/06 | **03/06** |
| FERNANDA VINHOTE MACIEL | doença c/ atestado | 22/02 | 01/03 | **02/03** |

Ambos doença comum — **sem estabilidade** envolvida. Retorno = 1ª batida após o afastamento.

### ⏸️ NÃO encerrados (2) — precisam da sua decisão

**CINTIA BEZERRA OLIVEIRA — acidente de trajeto.** Dois motivos para não automatizar:
1. **Estabilidade art. 118**: `estabilidade_ate` está gravada como 2027-05-21 (início + 12 meses).
   Mas na acidentária a estabilidade conta **do RETORNO**, não do início. Se ela voltou em 03/06,
   a proteção vai até **03/06/2027** — fechar sem recalcular **encurta a estabilidade dela em
   ~2 semanas**, o que é exposição trabalhista.
2. **Plausibilidade médica**: fratura de fêmur/tíbia com cirurgia e internação em 21/05, e a 1ª
   batida é 03/06 — **13 dias depois**. Para agente de portaria isso não fecha. Ou as batidas são
   de outro contexto, ou a data/gravidade do registro está errada. Confirmar antes de assinar
   qualquer data de retorno.

**ARYELTON BRAGA FIGUEIRA — suspensão contratual.** Não é afastamento médico: é suspensão por
**ajuizamento de rescisão indireta** (eSocial motivo 44, recibo 1.1.0000000037643). Encerrar isso
tem efeito jurídico no processo, e "voltou a bater ponto" não equivale a "a suspensão acabou".
É decisão jurídica, não de DP.

### Reversão

Backup do estado anterior: `auditoria/sst_afastamentos_pre_retorno_2026-08-03.json` (os 5 registros
antes da alteração). Para desfazer, restaurar `status`/`data_retorno`/`data_fim_prevista` dos 2 IDs.
