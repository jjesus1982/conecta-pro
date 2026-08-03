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
