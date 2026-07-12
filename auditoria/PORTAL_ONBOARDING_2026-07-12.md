# Portal — Onboarding/adoção dos síndicos sem login — 2026-07-12

## Situação
11 clientes habilitados; 5 NUNCA logaram: Prime Arena, Green Hills, Parise Village,
Villa dos Pássaros, Villa Dei Fiori. Todos com senha no banco — conta existe, mas o
síndico nunca recebeu/usou.

## Bloqueador de dado (não técnico)
Só o PRIME ARENA tem e-mail REAL do síndico (Gmail). Os outros 4 apontam para alias
INTERNO @conectamais.pro — enviar credencial ali cairia na própria caixa da Conecta.
→ O serviço BLOQUEIA envio a alias interno e devolve as credenciais p/ entrega manual.

## Construído
- portal_onboarding_service: onboard_cliente (provisiona senha temp segura + entrega
  pelo canal certo) e onboard_nao_logados (lote). E-mail de boas-vindas com a isca de
  valor (equipe/presença, visitas com foto, kits, NFS-e) + user + senha + link + "troque
  no 1º acesso". Log em portal_access_logs (action=provision).
- Endpoints admin: POST /portal/access-management/{id}/onboard e /onboard/nao-logados
  (enviar_email, email_override p/ preview).

## Provado
- Lote gerou 5 credenciais; a do Villa Dei Fiori LOGOU no portal (token emitido).
- E-mail de boas-vindas renderizado e ENTREGUE (preview do Prime → inbox do Jordan).
- Roteamento de canal correto: Prime=e-mail; os 4 aliases=entrega manual com motivo.

## AÇÃO DO JORDAN (deliverable)
1. Os 4 sem e-mail real: ou informar o e-mail do síndico (aí re-onboard por e-mail) OU
   entregar as credenciais por WhatsApp (folha gerada, senhas na conversa desta sessão).
2. Prime Arena: aprovar o envio para PRIME.ARENAA@GMAIL.COM (hoje foi só preview p/ Jordan).
3. Reforço: o resumo mensal do dia 1º + o José Luís já dão motivo recorrente de retorno.

Obs: cada onboard RESETA a senha (gera nova temp) — rodar só quando for de fato entregar.
