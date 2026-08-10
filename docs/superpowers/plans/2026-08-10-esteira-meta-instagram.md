# Esteira Meta — CAPI e Instagram DM

> Criado 2026-08-10 (T5), a pedido do Jordan: *"quanto a conta meta, temos que colocar
> na esteira, temos que integrar também"*.
> **Não é uma integração, são duas** — com custo e bloqueio completamente diferentes.
> Tratá-las como um bloco só faria a barata esperar pela cara.

---

## Trilho 1 — Conversions API (CAPI) · **já construído, dormindo**

**Serve para:** dizer à Meta, server-side, toda vez que um lead nasce. É o que liga o
anúncio ao CRM e deixa a Meta otimizar a entrega por lead REAL, não por clique. Mais
confiável que pixel de navegador (não depende de cookie, adblock nem consentimento do
browser).

**Estado:** `backend/modules/integrations/connectors/meta/capi.py` existe, está **ligado
no fluxo** (`whatsapp/controller.py:283`, logo após o lead ser criado) e **dorme** porque
`META_CAPI_TOKEN` não está no ambiente. Best-effort: nunca quebra a criação do lead.

**O que falta — só isto:**

| passo | de quem |
|---|---|
| 1. Events Manager → conjunto de dados → gerar token da API de Conversões | **Jordan** |
| 2. `META_CAPI_TOKEN=<token>` no `.env` + recreate do backend | 1 comando |
| 3. Validar com `META_CAPI_TEST_EVENT_CODE` no Events Manager (evento aparece em tempo real) | T5 |
| 4. Tirar o test code e deixar em produção | T5 |

```bash
# depois de colar o token no .env:
docker compose -f docker-compose.yml -f docker-compose.celery.yml up -d --no-deps backend
```

**Sem App Review.** O token de CAPI sai do Events Manager de um dataset que a conta já tem
(`META_DATASET_ID` default `1646163319127517`, o pixel "Captura de leads"). Confirmar se é
esse mesmo o dataset em uso.

**Ganho imediato:** hoje a Meta não sabe quais anúncios viraram lead de verdade — só sabe
quem clicou. Com CAPI ligado, o lance passa a otimizar por lead no CRM. É o trilho de
**maior retorno por menor esforço** desta esteira.

> ⚠️ **LGPD:** o CAPI manda telefone/e-mail **hasheados (SHA-256)**, nunca em claro — o
> `capi.py` já faz isso. Ainda assim é transferência de dado pessoal a terceiro: precisa
> estar coberto na base legal e no aviso de privacidade. **Checar antes de ligar.**

---

## Trilho 2 — Instagram DM no José Luís · **bloqueado por App Review da Meta**

**Serve para:** o José Luís atender o direct do `@conectamaisoficial` com as mesmas 47
tools, o mesmo funil e a mesma cotação do WhatsApp.

**Por que não é "só configurar" — verificado em 2026-08-10:**

| verificação | resultado |
|---|---|
| inboxes no Chatwoot | **1 só**: `WhatsApp 0800 880 4414`, tipo `Channel::Api` |
| canais Meta nativos (`channel_facebook_pages`) | **0** |
| ponte de mensageria rodando | `baileys-api` — WhatsApp, não Instagram |
| canal de Instagram no sidecar Hermes | inexistente |

### Cadeia de pré-requisitos (nesta ordem, cada um trava o seguinte)

| # | passo | de quem | prazo típico |
|--:|---|---|---|
| 1 | Instagram **Profissional** (Business/Creator) vinculado a uma Página do Facebook | Jordan | minutos |
| 2 | Página e Instagram dentro de um **Meta Business Manager** | Jordan | minutos |
| 3 | App no Meta for Developers com `instagram_manage_messages` + `pages_messaging` | Jordan | horas |
| 4 | **App Review da Meta** — screencast do uso, política de privacidade pública, caso de uso descrito | Jordan | **dias a semanas** |
| 5 | Canal de Instagram criado no Chatwoot (OAuth com a conta aprovada) | Jordan + T5 | 1h |
| 6 | Ajuste de identidade sem telefone no webhook | **T5** | ~4h |
| 7 | QA E2E do papel SDR pelo canal novo | T5 | ~2h |

**O passo 4 é o gargalo real** e não é técnico — é fila da Meta.

### O que já está mapeado do lado do código (passo 6)

O webhook é **agnóstico de canal** (não filtra por inbox), mas a identidade é o telefone:

```python
# whatsapp/controller.py:831
if direction == "in" and phone_canonical:
    lead_id = await _match_or_create_lead(db, phone_canonical, name, content)
```

Um DM de Instagram **não tem telefone**. Hoje isso significaria: a mensagem é logada, o
agente responde — e **não nasce lead, não há funil, não há atribuição**. É uma linha de
guarda a resolver, com duas decisões que só dá para tomar com o payload real na mão:

1. **Chave de identidade** — o `sender.id` do Instagram é *scoped* por app (o mesmo humano
   tem id diferente em apps diferentes). O `username` é estável mas o usuário pode trocar.
2. **Dedup entre canais** — a mesma pessoa que fala no WhatsApp e no direct deve virar
   **um** lead. Hoje o `find_duplicate` casa por `match_key_br` (telefone). Sem telefone,
   não há chave comum — provavelmente vira lead separado até alguém informar o contato.

**Não escrevi esse código.** Seria adivinhar o formato do payload de um canal que não
existe — a versão em código de fabricar dado. Fica mapeado para o dia em que o passo 5 sair.

---

## Ordem recomendada

**Trilho 1 primeiro, e sozinho.** Ele destrava atribuição de anúncio hoje, custa um token e
não depende de review nenhum. O Trilho 2 pode andar em paralelo do lado do Jordan (passos
1-4), sem bloquear nada.

## Próximo passo concreto

Gerar o token de CAPI no Events Manager e me passar — ou colar direto no `.env` como
`META_CAPI_TOKEN=`. Eu valido com test event, confirmo que o lead aparece no Events Manager
em tempo real, tiro o test code e deixo em produção.
