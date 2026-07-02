# RETOMAR — Auditoria E2E Fiscal & Financeiro (próxima sessão)

## Onde paramos (2026-06-28)
- Superfície de LEITURA (GET) de fiscal/financeiro: **49 erros 500 → 0** na raia. 205×200.
- Commitado: **`ada4a2a3`** (branch `fix/crm-qa-aprovado-20260614`, só `backend/modules/financial`).
- Âncora durável: imagem `conecta-pro-backend:finfiscal-fixed-20260628`.
- Relatório completo: `auditoria/T1_FINFISCAL_AUDITORIA_E2E_2026-06-28.md`.

## Próxima fase = WRITE E2E (criar/editar/excluir, função por função)
1. Para cada recurso CRUD de `backend/modules/financial` (suppliers, customers, bank-accounts, cost-centers, receivable-categories, billing-rules, payables, purchases, fiscal/obrigacao, inventory, widgets...): POST criar (marcador `ZZE2E_`) → GET verificar → PUT/PATCH editar → DELETE limpar. SEM efeito externo (NF-e/eSocial/e-mail/WhatsApp/pagamentos = pular).
2. Drifts latentes já sinalizados p/ atacar: POST `/fiscal/das` (cols legadas NOT-NULL), PATCH NFe/NFSe (models legados), POST inventory (enum PT vs nativo EN), POST widget (condominio_id/codigo).
3. Depois: 2 endpoints `/operacional/diaristas/fiscal/documentos` (bug `AsyncSession.query`, módulo operacional); rebuild canônico (B.3.3); check render frontend.

## Setup técnico (reusar)
- Token: `docker exec conecta-pro-backend python3 -c "from core.auth.jwt import create_access_token; from datetime import timedelta; print(create_access_token(subject='ad9abb59-55fb-444e-a04f-0e1f22541de3', expires_delta=timedelta(hours=8)))" > /tmp/finfiscal_token.txt`
- condominio_id real (com dados): `a1b2c3d4-e5f6-7890-abcd-ef1234567890`
- Deploy: editar host → `find /app/modules/financial -name __pycache__ -type d -exec rm -rf {} +` em backend+7 celery → `docker cp` → `docker restart conecta-pro-backend` (uvicorn não recarrega com HUP).
- Tabelas têm prefixo `fin_`. Subagentes: clusterizar por ARQUIVO (não dividir o mesmo arquivo entre 2).
