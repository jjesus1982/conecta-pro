# F-VISITA.2 pré — E-mail de confirmação da visita (READ-ONLY)

- **Data:** 2026-06-09
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Mapear como o agente enviaria e-mail de confirmação após criar a visita (reusando o `core/mailer` validado).
- **Veredito:** Mailer pronto e ponto de plug claro. **Gargalo:** a maioria das visitas é de **prospect sem e-mail na base** — a tool não coleta e-mail; cobrir o WhatsApp exige um novo arg `email_contato`. Para **cliente identificado**, `clients.email` (100%) resolve.

---

## 1. `clients.email` — 100% populado
- **11/11** clientes têm e-mail. Visita com `cliente_id` (resolvido por CNPJ) → dá pra `SELECT email FROM clients WHERE id = :cliente_id`.

## 2. Ponto de plug (em `_tool_agendar_visita`)
Logo após `visita = await VisitaService(db).criar_visita(...)` (~linha 282) e antes do `return {"ok": True, "numero": visita.numero, ...}` (283). Em escopo: `visita.numero`, `data_visita`, `horario_inicio`, `endereco/bairro/cidade`, `cliente_id`, `lead_id`, `is_prospect`, `args` (nome_contato, telefone_contato, objetivo, cnpj), e o `db`.

## 3. De onde vem o e-mail do destinatário (ponto crítico)
| Caso | E-mail? |
|------|---------|
| Cliente identificado (cliente_id via CNPJ) | ✅ `clients.email` (100%) |
| Prospect/lead de WhatsApp (cliente_id None — maioria) | 🔴 NÃO — tool sem arg de e-mail; leads de WhatsApp sem e-mail |

- Hoje a tool coleta `nome_contato`/`telefone_contato`, **não e-mail**. Para e-mailar o solicitante do WhatsApp (caso comum, `is_prospect=True`/`origem=LEAD`), é preciso **coletar o e-mail na conversa** → novo arg `email_contato` (o agente pergunta).

## 4. Mailer
`core/mailer.send_email(to_email, subject, html_body) -> bool` — **validado e funcional** (smoke test OK 2026-06-09, entrega confirmada). Chamar **best-effort** (try/except próprio): falha de e-mail **nunca** quebra a criação da visita nem o `{ok:true}` nem o webhook.

## 5. Teor (coerente com copiloto)
É **SOLICITAÇÃO** de visita, não confirmação. Assunto/corpo: *"recebemos sua solicitação de visita para [data] às [hora]; nossa equipe confirmará o horário"* — nunca "agendado/confirmado".

## 6. DECISÕES (suas — não decidi escopo)
1. E-mail só para **cliente identificado** (clients.email), ou **também coletar e-mail do prospect** (novo arg `email_contato`, cobre o caso comum do WhatsApp)?
2. Enviar **cópia interna** para a equipe/responsável (ex.: `comercial@`/`jjesus@`) avisando da solicitação, pra equipe confirmar? (recomendado).
3. Confirmar teor de **solicitação** (equipe confirma).
4. **Best-effort** (e-mail não quebra a visita) — confirmar (recomendado).

## 7. Esboço (quando fechar escopo) — PROPOSTA
- No ponto de plug: resolver `to_email` (cliente_id→clients.email; senão `args.email_contato`); se houver, `await send_email(to_email, assunto_solicitacao, corpo_html)` em try/except isolado; opcional cópia interna. Logar enviado/falha. `{ok:true}` independe do e-mail.
- Se adicionar `email_contato`: incluir no schema da tool + orientação no prompt (agente pede o e-mail ao conduzir o agendamento).

---
*Read-only: contagem de `clients.email`, leitura de `_tool_agendar_visita` (ponto de plug), assinatura de `send_email`. Nada implementado. Escopo aguardando sua definição.*
