# Revisão bidding / licitações (agente só-leitura, 08/09/2026 ~14h)

88 rotas montadas + 10 nunca montadas · VIVA 0 · LIGAR 0 · INTERNA 0 · MORTA 88. Todas as tabelas bidding_* (exceto sync_jobs) só têm seed de 12/03/2026. Recomendação: desligar o módulo inteiro.

## Defeitos
1. [8+3] beat bidding-sync-pncp-2h roda 12×/dia há 26 dias e nunca trouxe nada: `integrations/pncp/client.py:22` usa BASE_URL inexistente (404 em toda rodada, também ComprasNet); `agents/scout_agent.py:262` trata falha como "acabaram as páginas" → 298 jobs "completed" com 0 registros; ~72 chamadas externas/dia a 6 portais.
2. [5+3] beat bidding-check-certidoes-6h monitora certidões fictícias (`_criar_documentos_padrao`, 11 docs sem data) → 108 notificações "Certidão CRÍTICA — Licitações (11)" no sino desde 14/08, todas não lidas. Nunca lê bidding_certificates nem ged_certidoes.
3. [2] botões do redesign "Sincronizar PNCP/preços": `controllers/sync_controller.py:112-114, 227-228` mandam kwargs que a task não aceita → TypeError no Celery; job fica pendente para sempre.
4. [5 perigoso] botões ERP do redesign (`erp_controller.py:157` → `erp_integration_service.py:361-500`) criam conta a receber, lead e postos REAIS a partir de contratos/oportunidades seed, sem idempotência.
5. [5] aprovar medição duas vezes soma duas vezes (`contract_repository.py:268-288`).
6. [5] "aplicar reajuste" não altera valor_contrato (`models/public_contract.py:212-217`).
7. [5] retenções nunca aplicadas na medição manual (`contract_repository.py:244`).
8. [2] GET /bidding/documents/habilitacao 500 (`document_service.py:107` itera tupla).
9. [3] GET /bidding/documents/tipo/{tipo} 500 MultipleResultsFound (`document_repository.py:40`); mesmo padrão em certificate_service.py:54.
10. [1] drift: bidding_price_history.metadata_extra, bidding_analyses.opportunity_id, bidding_pricing.assessment_id/raw_pricing, bidding_assessments.raw_assessment, bidding_disputes.updated_at não existem.
11. [4] certidão "vence" 4h antes (utcnow × data local) em `models/certificate.py:152,198`, `tender.py:163-178`.
12. [5] status de certidão congelado e errado (CNDT/CND_FEDERAL vencidas constam valid; certificado digital 2027 consta expired); tipos no banco fora do enum.
13. [6] pncp_service duplica o client; dispute (5), opportunity (4) e websocket nunca montados; bidding_proposals duplica proposals do CRM.
14. [3] scout na API reutiliza client fechado; portais "disponivel" hardcoded.

## Vereditos
certificate (11), sync (5), tender (15), document (11), proposal (13), contract (14), erp (6 — desligar já), agent (13): MORTA.
bidding_certificates duplica ged_certidoes (58 linhas vivas, com PDF e CNPJ) — a cópia pior. Ainda leem bidding_certificates: aba Certidões do redesign (redesign_data_controller.py:2206-2209), ged_config_controller.py:120-127, 363-370, ged/nfse_controller.py:509, agent_controller.py:306-345.
Beat: 3 entradas (celery_app.py:525-541) — desligar; perda zero.
