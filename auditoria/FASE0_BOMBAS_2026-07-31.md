# Fase 0 — as 3 bombas, desarmadas (2026-07-31)

> Pré-requisito para qualquer trabalho de S-1010/S-1200. Não são features: são coisas que já
> estavam erradas em produção.

## Bomba #1 — CNPJ do transmissor eSocial hardcoded ✅

**Era:** `_build_soap_envelope` tinha `<nrInsc>35710481</nrInsc>` e `<nrInsc>35710481000103</nrInsc>`
**literais**. Qualquer evento da **Patrimonial** (66.014.833/0001-10) seria transmitido ao governo sob
o CNPJ da **Eletrônica** — evento legal declarado para a empresa errada.

**Agora:** vem de `event.employer_cnpj`. CNPJ ausente/inválido levanta `ValidationError` em vez de
transmitir sob outra empresa.

**Provado:** envelope da Patrimonial usa `66014833` e **não vaza** `35710481`; Eletrônica intacta;
`None`/`''`/`'123'` recusados.

## Bomba #2 — 3 semanas cegos + status mentindo ✅

Dois bugs em série faziam 5 ASOs aparecerem como **"transmitida"** quando o governo já os havia
**rejeitado**:

1. **A consulta nunca funcionou.** `_build_consulta_soap` usava serviço `v1_0_0` e schema no caminho
   errado → o governo respondia SOAP Fault `ActionNotSupported`. Nenhum recibo foi casado desde 09/07.
   O par correto (confirmado contra o webservice de **produção** — o próprio governo ditou o namespace
   na mensagem de erro): **serviço `v1_1_0`** + **schema `.../schema/lote/eventos/envio/consulta/retornoProcessamento/v1_0_0`**.
2. **`check_status` lia o `cdResposta` errado.** A resposta tem **dois**: o do **lote** (201 = recebido)
   e o do **evento**. O código lia só o do lote e marcava `ACCEPTED` — enquanto o evento trazia
   **`403 Leiaute do evento inválido`**. Agora lê o do evento e marca `REJECTED` com código e descrição
   reais do governo.

**Resultado medido:** o pull reclassificou os 5 ASOs para `rejeitada`. O banco (e a tela) passaram a
dizer a verdade.

**O que isso expôs:** o gerador de **S-2220 tem bug de leiaute** (403). Não era "esperando recibo" —
era rejeição. Vira trabalho da Fase 1. Resta 1 protocolo pendente honesto (S-2230 devolve `501
Solicitação de consulta incorreta` — formato de protocolo `1.2.` difere do `1.1.`, investigar).

## Bomba #3 — ponto do 12x36 noturno ✅

**Era:** a apuração agrupava por `punch_timestamp::date`. O 12x36 noturno entra ~19h do dia D e sai
~07h do dia D+1 — **a jornada era partida em dois "dias furados"**. Medido: só **9%** dos dias do
noturno apareciam pareados; a coluna Saída mostrava `--:--`.

**Agora:** pareamento por **jornada** (batidas alternadas 1ª→2ª, 3ª→4ª), que atravessa a meia-noite.

**Medido:**

| | Antes | Depois |
|---|--:|--:|
| Batidas "furadas" | ~840 | **29** |
| Tela sem saída | ~50% (noturno) | **7%** |
| Jornada do noturno | `--:--` | **12,0h** (21:01→09:01) |

**Consequência importante:** os "337 dias furados" que eu havia listado para ajuste manual **não
existiam** — eram artefato de agregação. Ninguém precisa ajustar 337 dias à mão.

## Correção de rumo (honestidade)

No relatório de aprovação do backlog eu classifiquei 840 batidas como "dias furados precisando de
ajuste humano". **Estava errado** — 811 delas eram jornadas noturnas legítimas partidas pela query.
As 2.321 batidas aprovadas seguem corretas (eram dias pareados). O saldo retido deve ser reavaliado
com o pareamento por jornada.

## O que continua verdadeiro e vira Fase 1

- Gerador **S-2220 com leiaute inválido** (403 confirmado pelo governo).
- **S-2230**: consulta devolve 501 — formato de protocolo a investigar.
- `INSS_PATRONAL_RAT_TERCEIROS = 0.288` fixo em 2 arquivos, ignora **FAP** — deve ser por empresa.
- **14 desligados sem data de desligamento** no cadastro.
