# CRM Conecta PRO — o que já está ligado e o que falta ativar
## Raio-x de completude (2026-06-23)

**Para:** Jordan
**Base:** schema real extraído + diagnóstico do pipeline + a fiação que acabamos de construir.

---

## 1. ✅ O que JÁ está ligado (a jornada comercial)

Hoje o ciclo flui ponta a ponta, automático:

```
WhatsApp (José Luís) → Lead → [você qualifica] → DEAL no Kanban
   → Proposta (vinculada ao deal, avança o estágio)
   → Enviada (Negociação) → Aceita
       ├─ Deal vira GANHO (closed_won)
       ├─ CONTRATO criado automático (rascunho), ligado a cliente+deal+proposta
       └─ COMISSÃO gerada automática (se houver regra)
```

Além disso: proposta com itens + cálculo ao vivo, **PDF com logo**, campo de moeda BR, autopreencher
cliente, biblioteca de conteúdo (marketing), e o pipeline (Kanban) populado com deals reais.

---

## 2. 🟡 O que falta ATIVAR (já existe no sistema, mas está parado)

Estas são "peças prontas" no banco/código que nunca foram ligadas — ativar dá retorno rápido:

| # | Recurso | Estado | O que falta |
|---|---------|--------|-------------|
| 1 | **Atividades / Timeline** (`crm_activities`) | tabela existe, **0 registros** | Registrar automaticamente cada toque (lead criado, status mudou, proposta enviada/aceita) e ter uma linha do tempo por cliente/deal — o "histórico" que todo CRM tem. |
| 2 | **Lead Scoring por IA** (`lead_scores`) | tabela + serviço existem, **0** | Rodar o score nos leads (já há endpoint `recalculate-score`) e mostrar nota/qualidade/temperatura no lead e no card do deal. |
| 3 | **Modelos de Proposta** (`proposal_templates`) | tabela existe, **0** | Cadastrar modelos prontos (Portaria Remota, Cerca Elétrica, CFTV) pra gerar proposta em 1 clique. |
| 4 | **Alertas de Contrato** (renovação, reajuste, SLA) | `ContractService` tem a lógica, **não exposta** | Ligar os alertas de vencimento/reajuste (IGPM/IPCA) — o cálculo já existe, falta a tela/notificação. |
| 5 | **Assinatura eletrônica de proposta/contrato** | campos existem (`signature_*`) | Conectar um provedor (ex.: Clicksign/D4Sign/gov.br) e o fluxo "enviar para assinar". |
| 6 | **Tarefas / próximo contato** (`leads.next_contact_at`) | campo existe, nada age | Lembretes de follow-up com data + notificação no WhatsApp/Telegram do vendedor. |

---

## 3. 🟠 O que falta CONSTRUIR/AJUSTAR (lacunas reais)

| # | Item | Por quê | Esforço |
|---|------|---------|---------|
| 7 | **Ganho pelo Kanban também cria contrato** | hoje só a "proposta aceita" dispara o contrato; arrastar o card pra "Ganho" não | Pequeno (hook no estágio da oportunidade) |
| 8 | **Contrato → MRR/financeiro** | o MRR do funil lê `client_contracts` (outra tabela); o contrato novo (`contracts`) não atualiza o MRR | Médio (ponte contrato→faturamento) |
| 9 | **Criar cliente no Ganho quando não cadastrado** | hoje, se o cliente não existe, o contrato é pulado | Médio (cliente tem muitos campos/regras) |
| 10 | **Envio real da proposta por e-mail + rastreio "visualizada"** | há `sent_at/viewed_at` mas sem e-mail real nem tracking de abertura | Médio |
| 11 | **Dashboard de vendas com dados reais** | agora que o pipeline tem deals, ativar forecast ponderado, taxa de ganho, tempo de ciclo | Pequeno-médio (gráficos já existem) |
| 12 | **Conversão lead→cliente no Ganho** | quando ganha, o lead deveria virar cliente formal (evento existe, mas não cria o cliente) | Médio |

---

## 4. Recomendação de ordem (maior valor / menor esforço primeiro)

1. **Atividades/Timeline (#1)** — dá "alma" ao CRM (histórico por cliente). Alto valor, esforço médio.
2. **Ganho pelo Kanban cria contrato (#7)** — fecha o buraco do gatilho. Esforço pequeno.
3. **Tarefas/follow-up com lembrete (#6)** — o vendedor para de perder lead por esquecimento.
4. **Lead Scoring (#2)** — prioriza os leads quentes (já existe, só ligar).
5. **Contrato → MRR (#8)** + **alertas de contrato (#4)** — fecha o ciclo financeiro/renovação.
6. **Modelos de proposta (#3)** + **assinatura (#5)** — velocidade e profissionalismo no fechamento.

> Tudo isso transforma o "tem as telas" em "o CRM trabalha por você". A espinha dorsal (lead→deal→
> proposta→contrato) já está ligada; o que falta é o **histórico, os lembretes, o scoring e o
> fechamento financeiro/assinatura**.

---

## 5. Resumo em uma frase

A **trinca comercial está ligada e automática**. Para o CRM ficar "completo estilo HubSpot", os
próximos passos de maior impacto são, nesta ordem: **Timeline de atividades → Ganho-no-Kanban cria
contrato → Tarefas/lembretes → Lead scoring → Contrato no MRR + alertas → Modelos + assinatura.**

*Me diga por qual começar e eu ligo na sequência.*
