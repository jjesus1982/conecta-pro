"""
API v1 - Router principal (dev/complete).

Imports organizados em 2 seções:
1. Via 9 módulos agregadores (mesma estrutura que main_production.py)
2. Módulos dev-only (AI sub-modules, HR, Campo legacy, etc.)

Reorganização backend: 2026-03-11
"""

from fastapi import APIRouter

from .endpoints.auth import router as auth_router

router = APIRouter(prefix="/api/v1")

# =============================================================================
# HEALTH CHECK
# =============================================================================
from core.controllers.health_controller import router as health_router  # noqa: E402

router.include_router(health_router)
router.include_router(auth_router)

# =============================================================================
# 1. COMERCIAL (via agregador)
# =============================================================================
from modules.comercial import (  # noqa: E402
    bidding_contract_router,
    bidding_document_router,
    bidding_erp_router,
    bidding_proposal_router,
    bidding_tender_router,
    client_router,
    crm_commission_router,
    crm_contract_router,
    crm_dashboard_router,
    crm_lead_router,
    crm_opportunity_router,
    crm_proposal_router,
    service_router,
)

router.include_router(crm_lead_router, prefix="/crm", tags=["CRM - Leads"])
router.include_router(crm_opportunity_router, prefix="/crm", tags=["CRM - Oportunidades"])
router.include_router(crm_proposal_router, prefix="/crm", tags=["CRM - Propostas"])
router.include_router(crm_commission_router, prefix="/crm", tags=["CRM - Comissões"])
router.include_router(crm_dashboard_router, prefix="/crm", tags=["CRM - Dashboard"])
router.include_router(crm_contract_router, prefix="/crm", tags=["CRM - Contratos"])
router.include_router(client_router, prefix="/clients", tags=["Clients - Cadastro"])
router.include_router(client_router, prefix="/crm/clients", tags=["CRM - Clientes"])
router.include_router(service_router, prefix="/services", tags=["Services - Gestão de Serviços"])
router.include_router(bidding_tender_router, prefix="/bidding", tags=["Bidding - Editais"])
router.include_router(bidding_document_router, prefix="/bidding", tags=["Bidding - Documentos"])
router.include_router(bidding_proposal_router, prefix="/bidding", tags=["Bidding - Propostas"])
router.include_router(bidding_contract_router, prefix="/bidding", tags=["Bidding - Contratos"])
router.include_router(bidding_erp_router, prefix="/bidding", tags=["Bidding - Integracao ERP"])

# =============================================================================
# 2. OPERAÇÕES (via agregador)
# =============================================================================
from modules.operacoes import (  # noqa: E402
    allocation_router,
    checklist_router,
    communication_router,
    diarist_fiscal_router,
    diarist_router,
    disciplinary_router,
    employee_router,
    inspection_round_router,
    kpi_trends_router,
    occurrence_router,
    operacional_ai_router,
    operacional_ws_router,
    ordem_servico_router,
    post_router,
    presence_router,
    reports_router,
    scale_router,
    scale_template_router,
    shift_handover_router,
    shift_router,
    substitution_router,
    team_evaluation_router,
    time_bank_router,
    triage_router,
    vacation_router,
    visita_router,
)

router.include_router(post_router, prefix="/operacional/postos", tags=["Operacional - Postos"])
router.include_router(scale_router, prefix="/operacional/escalas", tags=["Operacional - Escalas"])
router.include_router(
    scale_template_router, prefix="/operacional/scales/templates", tags=["Operacional - Templates de Escalas"]
)
router.include_router(shift_router, prefix="/operacional/turnos", tags=["Operacional - Turnos"])
router.include_router(allocation_router, prefix="/operacional/alocacoes", tags=["Operacional - Alocações"])
router.include_router(employee_router, prefix="/operacional", tags=["Operacional - Funcionarios"])
router.include_router(occurrence_router, prefix="/operacional", tags=["Operacional - Ocorrências"])
router.include_router(substitution_router, prefix="/operacional/substituicoes", tags=["Operacional - Substituições"])
router.include_router(time_bank_router, prefix="/operacional/banco-horas", tags=["Operacional - Banco de Horas"])
router.include_router(reports_router, prefix="/operacional", tags=["Operacional - Relatorios"])
router.include_router(kpi_trends_router, prefix="/operacional", tags=["Operacional - KPI Trends"])
router.include_router(disciplinary_router, prefix="/operacional", tags=["Operacional - Medidas Administrativas"])
router.include_router(communication_router, prefix="/operacional", tags=["Operacional - Comunicacao"])
router.include_router(inspection_round_router, prefix="/operacional/rondas", tags=["Operacional - Rondas de Inspecao"])
router.include_router(vacation_router, prefix="/operacional", tags=["Operacional - Férias e Afastamentos"])
router.include_router(shift_handover_router, prefix="/operacional", tags=["Operacional - Passagem de Turno"])
router.include_router(team_evaluation_router, prefix="/operacional", tags=["Operacional - Avaliação de Equipe"])
router.include_router(triage_router, prefix="/operacional", tags=["Operacional - Triagem"])
router.include_router(presence_router, prefix="/operacional", tags=["Operacional - Presença"])
router.include_router(diarist_router, prefix="/operacional/diaristas", tags=["Operacional - Diaristas"])
router.include_router(
    diarist_fiscal_router, prefix="/operacional/diaristas/fiscal", tags=["Operacional - Diaristas Fiscal"]
)
router.include_router(operacional_ai_router, prefix="/operacional/ai", tags=["Operacional - IA"])
router.include_router(operacional_ws_router, prefix="/operacional", tags=["Operacional - WebSocket"])
router.include_router(ordem_servico_router, prefix="/campo/os", tags=["Campo - Ordens de Serviço"])
router.include_router(visita_router, prefix="/campo/visitas", tags=["Campo - Visitas"])
router.include_router(checklist_router, prefix="/campo/checklists", tags=["Campo - Checklists"])

# =============================================================================
# 3. TÉCNICO (via agregador)
# =============================================================================
from modules.tecnico import (  # noqa: E402
    comodato_router,
    document_kit_router,
    equipment_maintenance_router,
    equipment_router,
    installation_router,
)

router.include_router(equipment_router, prefix="/equipment", tags=["Equipment - Equipamentos"])
router.include_router(installation_router, prefix="/equipment/installations", tags=["Equipment - Instalações"])
router.include_router(equipment_maintenance_router, prefix="/equipment/maintenance", tags=["Equipment - Manutenção"])
router.include_router(comodato_router, prefix="/equipment/comodato", tags=["Equipment - Comodato"])
router.include_router(document_kit_router, prefix="/document-kits", tags=["Document Kits"])

# =============================================================================
# 4. PESSOAS (via agregador)
# =============================================================================
from modules.pessoas import (  # noqa: E402
    climate_router,
    ged_document_router,
    ged_folder_router,
    ged_share_router,
    ged_signature_router,
    ged_stats_router,
    ged_tag_router,
    ged_version_router,
    onboarding_router,
    profile_router,
    recruitment_router,
    reimbursement_router,
    turnover_router,
)

router.include_router(recruitment_router, prefix="", tags=["Recruitment"])
router.include_router(onboarding_router, prefix="/retention/onboarding", tags=["Retention - Onboarding"])
router.include_router(profile_router, prefix="/retention/profile", tags=["Retention - Operational Profile"])
router.include_router(climate_router, prefix="/retention/climate", tags=["Retention - Climate Survey"])
router.include_router(turnover_router, prefix="/retention/turnover", tags=["Retention - Turnover Prediction"])
router.include_router(reimbursement_router, prefix="/reimbursements", tags=["Reimbursement - Reembolsos"])
router.include_router(ged_folder_router, prefix="/ged/folders", tags=["GED - Pastas"])
router.include_router(ged_document_router, prefix="/ged/documents", tags=["GED - Documentos"])
router.include_router(ged_version_router, prefix="/ged/versions", tags=["GED - Versões"])
router.include_router(ged_share_router, prefix="/ged/shares", tags=["GED - Compartilhamentos"])
router.include_router(ged_tag_router, prefix="/ged/tags", tags=["GED - Tags"])
router.include_router(ged_signature_router, prefix="/ged/signatures", tags=["GED - Assinaturas"])
router.include_router(ged_stats_router, prefix="/ged", tags=["GED - Estatísticas"])

# =============================================================================
# 4b. GESTÃO DE PESSOAS (people_management: DP + RH + Operations + Portal + GED)
# =============================================================================
try:
    from modules.people_management import router as people_management_router  # noqa: E402

    router.include_router(people_management_router)
except ImportError:
    pass

# =============================================================================
# 5. FINANCEIRO (via agregador)
# =============================================================================
from modules.financeiro import (  # noqa: E402
    accounting_router,
    bank_account_router,
    bank_reconciliation_router,
    bank_transaction_router,
    billing_rule_router,
    cashflow_router,
    customer_router,
    financial_ai_router,
    fiscal_router,
    inventory_router,
    payable_router,
    purchase_router,
    receivable_category_router,
    receivable_router,
    supplier_router,
)

router.include_router(accounting_router, prefix="/financial/accounting", tags=["Financial - Contabilidade"])
router.include_router(supplier_router, prefix="/financial/suppliers", tags=["Financial - Fornecedores"])
router.include_router(payable_router, prefix="/financial/payables", tags=["Financial - Contas a Pagar"])
router.include_router(customer_router, prefix="/financial/customers", tags=["Financial - Clientes"])
router.include_router(
    receivable_category_router, prefix="/financial/receivable-categories", tags=["Financial - Categorias Recebíveis"]
)
router.include_router(receivable_router, prefix="/financial/receivables", tags=["Financial - Contas a Receber"])
router.include_router(billing_rule_router, prefix="/financial/billing-rules", tags=["Financial - Regras de Cobrança"])
router.include_router(bank_account_router, prefix="/financial/bank-accounts", tags=["Financial - Contas Bancárias"])
router.include_router(
    bank_transaction_router, prefix="/financial/bank-transactions", tags=["Financial - Transações Bancárias"]
)
router.include_router(
    bank_reconciliation_router, prefix="/financial/bank-reconciliation", tags=["Financial - Conciliação Bancária"]
)
router.include_router(cashflow_router, prefix="/financial/cashflow", tags=["Financial - Fluxo de Caixa"])
router.include_router(purchase_router, prefix="/financial/purchases", tags=["Financial - Compras"])
router.include_router(inventory_router, prefix="/financial/inventory", tags=["Financial - Estoque"])
router.include_router(fiscal_router, prefix="/financial/fiscal", tags=["Financial - Fiscal/Tributário"])
router.include_router(financial_ai_router, prefix="/financial", tags=["Financial AI"])

# =============================================================================
# 6. FISCAL/CONTÁBIL (via agregador)
# =============================================================================
from modules.fiscal_contabil import (  # noqa: E402
    bidding_certificate_router,
    empresas_router,
)

router.include_router(empresas_router, tags=["Empresas - Multi-CNPJ"])
router.include_router(bidding_certificate_router, prefix="/bidding", tags=["Certidões - CNDs"])

# =============================================================================
# 7. INTELIGÊNCIA (via agregador)
# =============================================================================
from modules.inteligencia import (  # noqa: E402
    analytics_router,
    executive_dashboard_router,
    monitoring_router,
    report_router,
)

router.include_router(executive_dashboard_router, prefix="/analytics", tags=["Analytics - Executive Dashboard"])
router.include_router(analytics_router, tags=["Analytics - Predictive"])
router.include_router(report_router, prefix="/reports", tags=["Reports - Relatórios Gerenciais"])
router.include_router(monitoring_router, tags=["Monitoring - Early Warning System"])

# =============================================================================
# 8. GESTÃO (via agregador)
# =============================================================================
from modules.gestao import (  # noqa: E402
    audit_router,
    config_router,
    integration_router,
    intelligent_notification_router,
    mobile_router,
    notification_compliance_router,
    notification_router,
    push_notification_router,
    workflow_router,
)

router.include_router(config_router, prefix="/config", tags=["Config - Configurações"])
router.include_router(audit_router, prefix="/audit", tags=["Audit - Auditoria e Compliance"])
router.include_router(notification_router, prefix="", tags=["Notifications - Hub"])
router.include_router(intelligent_notification_router, prefix="/notifications", tags=["Notifications - Intelligent"])
router.include_router(notification_compliance_router, prefix="/notifications", tags=["Notifications - LGPD Compliance"])
router.include_router(push_notification_router, prefix="/notifications", tags=["Notifications - Push"])
router.include_router(mobile_router, prefix="/mobile", tags=["Mobile API"])
router.include_router(workflow_router, prefix="/workflows", tags=["Automation - Workflows"])
router.include_router(integration_router, tags=["Integrations - API Gateway"])

# =============================================================================
# DEV-ONLY: Módulos não cobertos pelos 9 agregadores
# Estes módulos só existem em api/v1, não em main_production.py
# =============================================================================

# --- AI Sub-Modules (13 módulos especializados) ---
from modules.ai.contract_analysis.controllers import router as ai_contract_router  # noqa: E402
from modules.ai.data_quality.controllers import data_quality_router as ai_data_quality_router  # noqa: E402
from modules.ai.email_assistant.controllers import router as ai_email_router  # noqa: E402
from modules.ai.fraud_detection.controllers import router as ai_fraud_router  # noqa: E402
from modules.ai.intelligence_hub.controllers import intelligence_hub_router  # noqa: E402
from modules.ai.inventory_forecast.controllers import router as ai_forecast_router  # noqa: E402
from modules.ai.knowledge_base.controllers import kb_router as ai_kb_router  # noqa: E402
from modules.ai.meeting_assistant.controllers import meeting_assistant_router as ai_meeting_router  # noqa: E402
from modules.ai.ocr.controllers import ocr_router as ai_ocr_router  # noqa: E402
from modules.ai.report_generator.controllers import report_router as ai_report_router  # noqa: E402
from modules.ai.sentiment_analysis.controllers import router as ai_sentiment_router  # noqa: E402
from modules.ai.signature.controllers import signature_router as ai_signature_router  # noqa: E402
from modules.ai.voice_recognition.controllers import voice_router as ai_voice_router  # noqa: E402
from modules.ai.workflow_optimizer.controllers import router as ai_workflow_router  # noqa: E402

router.include_router(ai_contract_router, prefix="/ai/contracts", tags=["AI - Análise de Contratos"])
router.include_router(ai_data_quality_router, prefix="/ai/data-quality", tags=["AI - Qualidade de Dados"])
router.include_router(ai_email_router, prefix="/ai/email", tags=["AI - Assistente de Email"])
router.include_router(ai_fraud_router, prefix="/ai/fraud", tags=["AI - Detecção de Fraude"])
router.include_router(ai_forecast_router, prefix="/ai/forecast", tags=["AI - Previsão de Inventário"])
router.include_router(ai_kb_router, prefix="/ai/knowledge-base", tags=["AI - Base de Conhecimento"])
router.include_router(ai_meeting_router, prefix="/ai/meetings", tags=["AI - Assistente de Reuniões"])
router.include_router(ai_ocr_router, prefix="/ai/ocr", tags=["AI - OCR"])
router.include_router(ai_report_router, prefix="/ai/reports", tags=["AI - Gerador de Relatórios"])
router.include_router(ai_sentiment_router, prefix="/ai/sentiment", tags=["AI - Análise de Sentimento"])
router.include_router(ai_signature_router, prefix="/ai/signatures", tags=["AI - Reconhecimento de Assinatura"])
router.include_router(ai_voice_router, prefix="/ai/voice", tags=["AI - Reconhecimento de Voz"])
router.include_router(ai_workflow_router, prefix="/ai/workflows", tags=["AI - Otimizador de Workflows"])
router.include_router(intelligence_hub_router, prefix="/ai", tags=["Intelligence Hub - Central IA"])

# --- HR (Recursos Humanos) ---
from modules.hr.analytics_dashboard import router as hr_analytics_router  # noqa: E402
from modules.hr.employee_portal.controllers import router as hr_portal_router  # noqa: E402
from modules.hr.mobile_time_clock import checkin_router as mobile_checkin_router  # noqa: E402
from modules.hr.mobile_time_clock import device_router as mobile_device_router  # noqa: E402
from modules.hr.mobile_time_clock import geofence_router as mobile_geofence_router  # noqa: E402
from modules.hr.mobile_time_clock import offline_router as mobile_offline_router  # noqa: E402
from modules.hr.payroll_integration import router as hr_payroll_router  # noqa: E402
from modules.hr.rep_integration.controllers import router as hr_rep_router  # noqa: E402
from modules.hr.time_tracking.controllers import router as hr_time_tracking_router  # noqa: E402

router.include_router(hr_analytics_router, prefix="/hr", tags=["HR - Analytics"])
router.include_router(hr_portal_router, prefix="/hr", tags=["HR - Portal"])
router.include_router(mobile_device_router, prefix="/hr/mobile", tags=["HR - Mobile Devices"])
router.include_router(mobile_checkin_router, prefix="/hr/mobile", tags=["HR - Mobile Check-in"])
router.include_router(mobile_geofence_router, prefix="/hr/mobile", tags=["HR - Geofencing"])
router.include_router(mobile_offline_router, prefix="/hr/mobile", tags=["HR - Offline Sync"])
router.include_router(hr_payroll_router, prefix="/hr", tags=["HR - Payroll"])
router.include_router(hr_rep_router, prefix="/hr", tags=["HR - REP"])
router.include_router(hr_time_tracking_router, prefix="/hr", tags=["HR - Time Tracking"])

# --- Documents (Document Intelligence OCR/IA) ---
from modules.documents.controllers import router as documents_router  # noqa: E402

router.include_router(documents_router, prefix="", tags=["Documents - Document Intelligence"])

# --- Fase 3: Security, Health, Government ---
from modules.government_integrations import government_integrations_router  # noqa: E402
from modules.health_occupational import health_occupational_router  # noqa: E402
from modules.security_lgpd import security_lgpd_router  # noqa: E402

router.include_router(security_lgpd_router, prefix="/security")
router.include_router(health_occupational_router, tags=["Health - Saude Ocupacional"])
router.include_router(government_integrations_router, tags=["Government - Integracoes Governamentais"])

# --- Fase 5 (DEPRECATED) ---
from modules.fase5.controllers import fase5_router  # noqa: E402

router.include_router(fase5_router, tags=["Fase 5 - Grand Finale (DEPRECATED)"])

# --- Campo Legacy (routers não cobertos pelo agregador operações) ---
from modules.campo import access_log_router as campo_access_router  # noqa: E402
from modules.campo import campo_service_router, estoque_router, roteirizacao_router  # noqa: E402
from modules.campo import equipment_status_router as campo_equipment_router  # noqa: E402

router.include_router(campo_service_router, prefix="/campo", tags=["Campo - Serviços e OS"])
router.include_router(campo_access_router, prefix="/campo/acessos", tags=["Campo - Logs de Acesso"])
router.include_router(campo_equipment_router, prefix="/campo/equipamentos", tags=["Campo - Equipamentos"])
router.include_router(roteirizacao_router, prefix="/campo/rotas", tags=["Campo - Roteirização"])
router.include_router(estoque_router, prefix="/campo/estoque", tags=["Campo - Estoque"])

# --- Scheduler ---
from modules.scheduler.controllers import router as scheduler_router  # noqa: E402

router.include_router(scheduler_router, prefix="/scheduler", tags=["Scheduler - Agendamento de Tarefas"])
