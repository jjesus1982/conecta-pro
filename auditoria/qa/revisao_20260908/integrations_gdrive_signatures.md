# Revisão integrations + gdrive + signatures (agente só-leitura, 08/09/2026 ~10h)

126 rotas · VIVA 45 · LIGAR 9 · INTERNA 9 · MORTA 63. Por bloco: banking 31 (11/1/7/12) · whatsapp 7 (5/2/0/0) · gateway 35 (0/0/0/35) · connectors 12 (0/0/0/12) · solides 18 (13/4/1/0) · gdrive 12 (7/1/0/4) · signatures 11 (9/1/1/0).

## Defeitos (mais grave primeiro)
### Banking
1. [5/8 grave] Dinheiro sai sem OTP, sem teto e sem trilha: `banking/controllers/payment_controller.py:71-113` (/banking/payment/barcode), `:115-142` (/darf), `:145-156` (/batch) vão direto ao adapter (`adapters/inter.py:945`), sem INSERT em inter_payments. Chamado pelo clássico (payable-detail-modal.tsx:74, banking/page.tsx:186,210).
2. [5 grave] Webhooks Inter sem autenticação/assinatura alteram recebíveis: `webhook_controller.py:22-30` aceita tudo sem INTER_WEBHOOK_CA_PATH (não definido); /inter/boleto (:303), /pagamento-pix (:398), /pagamento-boleto (:448), /cobranca-recorrente (:515) nem chamam o validador.
3. [5 grave] Evento de boleto sem codigoSolicitacao marca TODOS os pendentes: `webhook_controller.py:222-236` (`boleto_number ILIKE '%%'`).
4. [5 grave] Status gravado que o sistema não reconhece: Inter grava 'recebido' (:162,183,239,537); Cora grava 'pago' (cora_webhook_controller.py:87); canônico 'paga'.
5. [5] Conciliação por valor casa o recebível errado (`webhook_controller.py:178-203`).
6. [5] Boleto emitido nunca é conciliado: banking_controller salva em boleto_id; webhook procura boleto_number/pix_txid.
7. [7/5] sync_single_transaction antes do commit (`webhook_controller.py:140-146`).
8. [7] asyncio.create_task sem referência com psycopg2 síncrono (`banking_controller.py:527,642`).
9. [5] POST /webhooks/inter/configurar e GET /status sem auth (:358, :384).
10. [3] Erro interno vira 200 (:296-298, 322-324, 440-442, 490-492).
11. [2] /inter/pix quebra se vier lista (:287). 12. [4] NOW()/CURRENT_DATE em UTC (:120,161,181). 13. Cora/Asaas nunca conciliaram nada. 14. Asaas status re-consultado não casa o mapa (asaas_webhook_controller.py:41-49,110). 15. /banking/status só conhece o Inter (banking_controller.py:434-436,392).
### WhatsApp
16. [3/5 alto] Botão NFS-e do redesign sempre 422: `redesign_builders/integracoes.py:137-143` manda só user_id na query; `connectors/whatsapp/controller.py:55-61` exige JSON.
17. [5 alto] BAILEYS_API_KEY hardcoded como default em `connectors/whatsapp/service.py:133`.
18. [8] Reentrega do Chatwoot reenfileira mídia e agente (`controller.py:1120-1128, 1171, 1216`).
19. [5] Vídeo entra como documento (:1244 testa 🎬, transcrição devolve 🎥). 20. [4] Dashboard do agente corta o dia em UTC (:793-800). 21. [3/7] except silencioso no advisory lock (:214-217); commit no meio de _match_or_create_lead (:265).
### GDrive + Assinaturas
22. [5 grave] E-mail do kit pode ir a contato de OUTRO cliente: `gdrive/services/email_kit_service.py:85-90` JOIN cartesiano quando contact_email vazio.
23. [5 grave] PIN de 6 dígitos sem limite de tentativas: `signatures/controllers/signature_controller.py:544-590` não chama _limite_ok.
24. [5 grave] POST /signatures/requests sem auth (:81-87, 611-637).
25. [5] Pasta do Drive com holerites pública (kit_drive_service.py:218 tornar_publico=True).
26. [5] Shell injection com socket docker (email_kit_service.py:51-58,81,86-88).
27. [5] 180 solicitações PENDING vencidas listadas como "a assinar" (universal_signature_service.py:1093-1105).
28. [5] Redesign manda destinatario no body, rota lê query (area_do_cliente.py:171-179 vs gdrive_controller.py:288-295).
29. [4] Fuso misto na assinatura (naive Manaus × utcnow). 30. [3] Falha de envio vira 200 sucesso:false. 31. [4/5] OAuth callback ignora state (gdrive_controller.py:445-500). 32. [6] POST /gdrive/autorizar aponta para rota inexistente. 33. handlers async com smtplib/subprocess; código após return em aviso_assinatura_service.py:240-267; GET /signatures/document sem auth; public_send_code manda PIN para CANCELLED/EXPIRED.
### Gateway / Connectors / Sólides
34. [1 grave] Tabelas movidas para lixo_20260906 (solides_sync_state, sync_runs, sync_states, id_maps…): `solides_controller.py:565-585` GET /solides/status 500 (chamado pelo clássico); :1035,1081,1143 conflicts 500; connector_controller sync/run 500.
35. [5 grave] Tenant errado: users.condominio_id do admin = placeholder; dados Sólides em 615bbcf6… (`solides_controller.py:67-73`).
36. [5] Secret HMAC devolvido em todo GET (integration_schemas.py:361,371). 37. Token Sólides em texto plano (:943,950). 38. [6] GET /connectors/{name} engole /connectors/accounts. 39. [2] current_user.get em objeto User (connector_controller.py:434,553). 40. str(e) no detail; /integrations/health sem auth.

## Vereditos
- webhooks Inter: /pix e /boleto VIVA (entregas reais); /configurar INTERNA; /status LIGAR (após auth); pagamento-pix/boleto/recorrencia/cobranca-recorrente INTERNA. Cora/Asaas: POST VIVA/INTERNA; aliases com barra MORTA.
- banking_controller: VIVA balances, status, boleto/generate, pix/generate, boleto/list, statement/full, boleto/{id}; MORTA statement, /boleto (alias), DELETE boleto, ted/gerar-otp, ted/transfer, pix/received, pix/refund.
- payment_controller: barcode e darf VIVA (clássico, sem OTP — defeito 1); batch, list, cancel MORTA.
- whatsapp: status, kit-notification, certificate-alert, custom, webhook VIVA; nfse-notification LIGAR (corrigir form); agent/dashboard LIGAR.
- integration_controller (35): todas MORTA (tabelas vazias). connector_controller (12): todas MORTA.
- solides: status/config/employees/logs/sync/trigger/conflicts/health VIVA no clássico (quebradas pelo lixo/tenant); sync full/incremental/entity LIGAR; webhook INTERNA; beneficios/vincular-kits VIVA (redesign); beneficios/sync LIGAR.
- gdrive: status/autorizar GET/oauth callback/desconectar VIVA; POST autorizar MORTA; montar-e-enviar, enviar-email, montar VIVA; kits, ingestao/status, link MORTA; portal/{c}/kits LIGAR.
- signatures: requests, document, meus-pendentes, assinar-lote, {id}/sign, public/* VIVA; empresa/assinar-lote LIGAR (51 espelhos company vencidos); verify INTERNA.
