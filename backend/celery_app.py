"""
Aplicação Celery - Conecta Plus.

Ponto de entrada para os workers Celery de integrações governamentais.
"""

import os

from celery import Celery
from celery.schedules import crontab
from kombu import Exchange, Queue

# Broker e Backend (Redis)
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = os.getenv("REDIS_PORT", "6379")
REDIS_DB = os.getenv("REDIS_DB", "0")
BROKER_URL = os.getenv("CELERY_BROKER_URL", f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}")
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}")

# Criar aplicação Celery
app = Celery(
    "conecta_plus",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=[
        "modules.government_integrations.jobs.sync_tasks",
        "modules.government_integrations.jobs.monitoring_tasks",
        "modules.integrations.connectors.solides.tasks",
        "modules.operacional.tasks",
        "modules.bidding.tasks",
        "modules.people_management.sst.tasks",
        "modules.people_management.ged.tasks",
        "modules.health_occupational.tasks",
        "modules.gedeon.tasks.kronos_tasks",
        "modules.gedeon.tasks.orquestrador_tasks",
        "modules.client_portal.tasks",
        "modules.financial.tasks",
        "modules.fiscal_contabil.obrigacoes.tasks",
        "modules.crm.tasks",
        "modules.integrations.connectors.whatsapp.tasks",
        "modules.analytics.tasks",
    ],
)

# Exchanges
government_exchange = Exchange("government", type="direct")
government_priority_exchange = Exchange("government_priority", type="direct")
integrations_exchange = Exchange("integrations", type="direct")
operacional_exchange = Exchange("operacional", type="direct")

# Filas
app.conf.task_queues = [
    # Alta prioridade
    Queue("gov.esocial", government_priority_exchange, routing_key="esocial", queue_arguments={"x-max-priority": 10}),
    Queue("gov.fgts", government_priority_exchange, routing_key="fgts", queue_arguments={"x-max-priority": 10}),
    # Serviços SEFAZ
    Queue("gov.sefaz.nfe", government_exchange, routing_key="sefaz.nfe", queue_arguments={"x-max-priority": 10}),
    Queue("gov.sefaz.cte", government_exchange, routing_key="sefaz.cte", queue_arguments={"x-max-priority": 10}),
    Queue("gov.sefaz.mdfe", government_exchange, routing_key="sefaz.mdfe", queue_arguments={"x-max-priority": 10}),
    # NFS-e
    Queue("gov.nfse", government_exchange, routing_key="nfse", queue_arguments={"x-max-priority": 10}),
    # Batch/Sync/Monitoramento
    Queue("gov.batch", government_exchange, routing_key="batch", queue_arguments={"x-max-priority": 5}),
    # Integrações - Sólides
    Queue("integrations", integrations_exchange, routing_key="integrations", queue_arguments={"x-max-priority": 5}),
    Queue("webhooks", integrations_exchange, routing_key="webhooks", queue_arguments={"x-max-priority": 8}),
    Queue("maintenance", integrations_exchange, routing_key="maintenance", queue_arguments={"x-max-priority": 3}),
    # Operacional - Notificações Push
    Queue("operacional", operacional_exchange, routing_key="operacional", queue_arguments={"x-max-priority": 7}),
]

# Roteamento de tasks
app.conf.task_routes = {
    # Sync tasks
    "government_integrations.tasks.sync.*": {"queue": "gov.batch"},
    "government_integrations.tasks.sync.sincronizar_nfe": {"queue": "gov.sefaz.nfe"},
    "government_integrations.tasks.sync.sincronizar_esocial": {"queue": "gov.esocial"},
    "government_integrations.tasks.espelho.sincronizar_espelho_esocial": {"queue": "gov.esocial"},
    "government_integrations.tasks.sync.sincronizar_fgts": {"queue": "gov.fgts"},
    "government_integrations.tasks.sync.sincronizar_nfse": {"queue": "gov.nfse"},
    # Monitoring tasks
    "government_integrations.tasks.monitoring.*": {"queue": "gov.batch"},
    "government_integrations.tasks.reprocess.*": {"queue": "gov.batch"},
    "government_integrations.tasks.maintenance.*": {"queue": "gov.batch"},
    # Sólides Integration tasks
    "solides.full_sync": {"queue": "integrations"},
    "solides.incremental_sync": {"queue": "integrations"},
    "solides.sync_all_condominios_incremental": {"queue": "integrations"},
    "solides.sync_single_entity": {"queue": "integrations"},
    "solides.health_check": {"queue": "integrations"},
    "solides.health_check_all": {"queue": "integrations"},
    "solides.process_webhook_queue": {"queue": "webhooks"},
    "solides.retry_failed_webhooks": {"queue": "integrations"},
    "solides.cleanup_old_logs": {"queue": "maintenance"},
    "solides.cleanup_old_webhooks": {"queue": "maintenance"},
    # Bidding - Sync PNCP
    "bidding.sync_pncp_oportunidades": {"queue": "gov.batch"},
    "bidding.sync_pncp_precos": {"queue": "gov.batch"},
    "bidding.verificar_certidoes_vencimento": {"queue": "gov.batch"},
    "bidding.processar_pipeline_edital": {"queue": "gov.batch"},
    # Operacional - Notificações Push
    "operacional.check_late_employees": {"queue": "operacional"},
    "operacional.check_pending_approvals": {"queue": "operacional"},
    # Operacional - Banco de Horas / Relatórios
    "operacional.expire_time_bank_entries": {"queue": "operacional"},
    "operacional.send_shift_reminders": {"queue": "operacional"},
    "operacional.daily_coverage_report": {"queue": "operacional"},
    # SST - Afastamentos
    "sst.verificar_afastamentos_vencidos": {"queue": "operacional"},
    "sst.verificar_inss_pendente": {"queue": "operacional"},
    # SST - eSocial (transmissão S-2210/S-2220/S-2230 + pull de recibos) — fila gov
    "sst.transmit_cat_to_esocial": {"queue": "gov.esocial"},
    "sst.transmit_aso_to_esocial": {"queue": "gov.esocial"},
    "sst.transmit_afastamento_to_esocial": {"queue": "gov.esocial"},
    "sst.esocial_pull_recibos": {"queue": "gov.esocial"},
    # SST - Alertas internos no sino (notification_queue) — usuários admin
    "sst.alertas_diarios": {"queue": "operacional"},
    # SST - Saúde Ocupacional (health_occupational)
    "sst.verificar_asos_vencendo": {"queue": "operacional"},
    "sst.verificar_epis_vencendo": {"queue": "operacional"},
    "sst.verificar_exames_pendentes": {"queue": "operacional"},
    # GED - Kits e CNDs (roteadas para worker operacional)
    "ged.auto_collect_documents": {"queue": "operacional"},
    "ged.sync_cnds": {"queue": "operacional"},
    # People Management - Escalas Sólides
    "integrations.sync_work_schedules_from_solides": {"queue": "integrations"},
    # Analytics - Recálculo de KPIs
    "analytics.recalcular_kpis": {"queue": "gov.batch"},
}

# Configurações gerais
app.conf.update(
    # Timezone
    timezone="America/Manaus",
    enable_utc=True,
    # Serialização
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Comportamento
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    # Limites
    worker_prefetch_multiplier=1,
    task_soft_time_limit=300,  # 5 min
    task_time_limit=600,  # 10 min
    # Retry
    task_default_retry_delay=60,
    # Resultados
    result_expires=86400,  # 24h
    # Default queue
    task_default_queue="gov.batch",
)

# Beat Schedule (tarefas agendadas)
app.conf.beat_schedule = {
    # ── Financeiro — Conciliação bancária diária (extrato Inter → bridge → categoriza) ──
    "financeiro-conciliacao-inter-diaria": {
        "task": "financial.inter_reconciliacao_diaria",
        "schedule": crontab(hour=8, minute=0),
        "options": {"queue": "gov.batch"},
    },
    # ── Multi-CNPJ E4: extrato Cora (Patrimonial) + conciliação líquido×NFS-e ──
    "financeiro-extrato-cora-diario": {
        "task": "financial.cora_sync_extrato",
        "schedule": crontab(hour=8, minute=10),
        "options": {"queue": "gov.batch"},
    },
    # ── Financeiro — Monitor de pagamentos pendentes de aprovação (status vivo do Inter) ──
    "financeiro-monitor-pagamentos-pendentes": {
        "task": "financial.inter_monitorar_pendentes",
        "schedule": crontab(minute="*/5"),
        "options": {"queue": "gov.batch"},
    },
    # ── Fiscal — Guias do Drive (pacote Portte/Onvio → fiscal_obligations) ──────
    "fiscal-sync-guias-drive": {
        "task": "fiscal.sync_guias_drive",
        "schedule": crontab(hour="9,15", minute=30),
        "options": {"queue": "gov.batch"},
    },
    # ── GEDEON — Kronos/Themis ────────────────────────────────────────────────
    "gedeon-kronos-diario": {
        "task": "gedeon.kronos.verificacao_diaria",
        "schedule": crontab(hour=6, minute=0),
        "options": {"queue": "gov.batch"},
    },
    "gedeon-themis-assinaturas": {
        "task": "gedeon.themis.verificacao_assinaturas",
        "schedule": crontab(minute=0, hour="*/4"),
        "options": {"queue": "gov.batch"},
    },
    "gedeon-fiscal-verificar-certidoes": {
        "task": "gedeon.fiscal.verificar_certidoes",
        "schedule": crontab(hour=7, minute=0),
        "options": {"queue": "gov.batch"},
    },
    # Portal do Cliente — materializa os docs locais nos kits (catch-all diário 07:30)
    "portal-materializar-kits": {
        "task": "portal.materializar_kits",
        "schedule": crontab(hour=7, minute=30),
        "options": {"queue": "gov.batch"},
    },
    # ── Operacional — Briefing matinal via Telegram (seg-sex) ─────────────────
    # TZ do Celery = America/Sao_Paulo (BRT): 07:30 BRT = hour=7, minute=30 (sem
    # conversão para UTC — o beat agenda no timezone configurado acima).
    # Fila gov.batch: worker celery-batch tem TELEGRAM_* no env_file .env.
    # Portal do Cliente — resumo mensal de reengajamento (dia 1º, 08:00 Manaus)
    "portal-resumo-mensal": {
        "task": "portal.resumo_mensal_clientes",
        "schedule": crontab(minute=0, hour=9, day_of_month="1"),
        "options": {"queue": "gov.batch"},
    },
    "operacional-briefing-matinal": {
        "task": "operacional.briefing_operacional_matinal",
        "schedule": crontab(minute=30, hour=7, day_of_week="1-5"),
        "options": {"queue": "gov.batch"},
    },
    # Vigia de ausência: turno em andamento sem batida (30-60min do início) → Telegram.
    # Beat TZ = America/Sao_Paulo; turnos são hora de Manaus (SP-1h): hour 8-23 SP cobre 7-22 Manaus.
    "operacional-vigia-ausencia": {
        "task": "operacional.vigia_ausencia",
        "schedule": crontab(minute="0,30", hour="8-23"),
        "options": {"queue": "gov.batch"},
    },
    # Dia 25, 08:00 SP: gera em rascunho as escalas do mês seguinte (nunca publica sozinho)
    "operacional-escalas-proximo-mes": {
        "task": "operacional.gerar_escalas_proximo_mes",
        "schedule": crontab(minute=0, hour=8, day_of_month="25"),
        "options": {"queue": "gov.batch"},
    },
    # Verificação de disponibilidade a cada 5 minutos
    "check-endpoints-5min": {
        "task": "government_integrations.tasks.monitoring.verificar_disponibilidade",
        "schedule": 300.0,  # 5 minutos
        "options": {"queue": "gov.batch"},
    },
    # Verificação de certificados a cada 6 horas
    "check-certificates-6h": {
        "task": "government_integrations.tasks.monitoring.verificar_certificados",
        "schedule": 21600.0,  # 6 horas
        "options": {"queue": "gov.batch"},
    },
    # Reprocessamento de falhas a cada 15 minutos
    "reprocess-failures-15min": {
        "task": "government_integrations.tasks.reprocess.reprocessar_falhas",
        "schedule": 900.0,  # 15 minutos
        "options": {"queue": "gov.batch"},
    },
    # Relatório diário às 06:00
    "daily-report": {
        "task": "government_integrations.tasks.monitoring.gerar_relatorio_diario",
        "schedule": 86400.0,  # 24 horas
        "options": {"queue": "gov.batch"},
    },
    # Limpeza de cache diária
    "cleanup-cache-daily": {
        "task": "government_integrations.tasks.maintenance.limpar_cache",
        "schedule": 86400.0,  # 24 horas
        "options": {"queue": "gov.batch"},
    },
    # =========================================================================
    # FISCAL — NFS-e ENTRADA + NF-e ENTRADA (RECEBIMENTO AUTOMÁTICO)
    # =========================================================================
    # NFS-e recebidas (Portal Nacional) — diariamente às 06:30
    "fiscal-nfse-entrada-diario": {
        "task": "government_integrations.tasks.sync.sincronizar_nfse_entrada",
        "schedule": crontab(hour=6, minute=30),
        "options": {"queue": "gov.nfse"},
    },
    # NF-e recebidas (SEFAZ DistribuicaoDFe) — a cada 2 horas
    "fiscal-nfe-entrada-2h": {
        "task": "government_integrations.tasks.sync.sincronizar_nfe_entrada",
        "schedule": crontab(minute=0, hour="*/2"),
        "options": {"queue": "gov.sefaz.nfe"},
    },
    # NFS-e nacional (gov.br/ADN): receita emitidas + custo tomadas — diário 04:30.
    # Junho e futuros completam sozinhos quando o Ambiente Nacional recebe as notas.
    "financial-nfse-nacional-diario": {
        "task": "financial.sincronizar_nfse_nacional",
        "schedule": crontab(hour=4, minute=30),
    },
    # Contabilidade que fecha sozinha: folha + ISS no razão — diariamente às 05:00
    "financial-fechar-razao-diario": {
        "task": "financial.fechar_razao_auto",
        "schedule": crontab(hour=5, minute=0),
    },
    # =========================================================================
    # SÓLIDES - INTEGRAÇÃO RH/DP
    # =========================================================================
    # Sync incremental a cada 15 minutos
    "solides-incremental-sync-all": {
        "task": "solides.sync_all_condominios_incremental",
        "schedule": 900.0,  # 15 minutos
        "options": {"queue": "integrations"},
    },
    # Pull de batidas de ponto do Tangerino -> gp_clock_punches (de hora em hora)
    "solides-sync-punches": {
        "task": "solides.sync_punches",
        "schedule": 900.0,  # 15 min — presença ao vivo (era 1h; Jordan pediu quadro fiel, 2026-07-08)
        "kwargs": {"days_back": 2},
        "options": {"queue": "integrations"},
    },
    # Health check a cada 5 minutos
    "solides-health-check-all": {
        "task": "solides.health_check_all",
        "schedule": 300.0,  # 5 minutos
        "options": {"queue": "integrations"},
    },
    # Processar fila de webhooks a cada 30 segundos
    "solides-process-webhooks": {
        "task": "solides.process_webhook_queue",
        "schedule": 30.0,
        "options": {"queue": "webhooks"},
    },
    # Retry de webhooks falhos a cada hora
    "solides-retry-failed-webhooks": {
        "task": "solides.retry_failed_webhooks",
        "schedule": 3600.0,  # 1 hora
        "options": {"queue": "integrations"},
    },
    # Cleanup de logs de sync (diário às 4 AM via crontab)
    "solides-cleanup-sync-logs": {
        "task": "solides.cleanup_old_logs",
        "schedule": 86400.0,  # 24 horas
        "args": (30,),  # manter 30 dias
        "options": {"queue": "maintenance"},
    },
    # Cleanup de logs de webhook (diário às 4:30 AM via crontab)
    "solides-cleanup-webhook-logs": {
        "task": "solides.cleanup_old_webhooks",
        "schedule": 86400.0,  # 24 horas
        "args": (7,),  # manter 7 dias
        "options": {"queue": "maintenance"},
    },
    # =========================================================================
    # OPERACIONAL - NOTIFICAÇÕES PUSH
    # =========================================================================
    # Verifica colaboradores atrasados a cada 5 minutos
    "operacional-check-late-employees": {
        "task": "operacional.check_late_employees",
        "schedule": 300.0,  # 5 minutos
        "options": {"queue": "operacional"},
    },
    # Verifica aprovações pendentes a cada 1 hora
    "operacional-check-pending-approvals": {
        "task": "operacional.check_pending_approvals",
        "schedule": 3600.0,  # 1 hora
        "options": {"queue": "operacional"},
    },
    # Expira banco de horas vencidos todo dia às 00:30h
    "operacional-expire-time-bank-daily": {
        "task": "operacional.expire_time_bank_entries",
        "schedule": 86400.0,  # 24 horas (00:30 via crontab no deploy)
        "options": {"queue": "operacional"},
    },
    # Lembretes de turno a cada 30 minutos
    "operacional-shift-reminders-30min": {
        "task": "operacional.send_shift_reminders",
        "schedule": 1800.0,  # 30 minutos
        "options": {"queue": "operacional"},
    },
    # Relatório de cobertura diário às 23:55h
    "operacional-daily-coverage-report": {
        "task": "operacional.daily_coverage_report",
        "schedule": 86400.0,  # 24 horas
        "options": {"queue": "operacional"},
    },
    # =========================================================================
    # BIDDING - SYNC PNCP / CERTIDÕES
    # =========================================================================
    # Sync oportunidades PNCP a cada 2 horas
    "bidding-sync-pncp-2h": {
        "task": "bidding.sync_pncp_oportunidades",
        "schedule": 7200.0,  # 2 horas
        "options": {"queue": "gov.batch"},
    },
    # Verificação de certidões a cada 6 horas
    "bidding-check-certidoes-6h": {
        "task": "bidding.verificar_certidoes_vencimento",
        "schedule": 21600.0,  # 6 horas
        "options": {"queue": "gov.batch"},
    },
    # Sync preços de referência diário
    "bidding-sync-precos-daily": {
        "task": "bidding.sync_pncp_precos",
        "schedule": 86400.0,  # 24 horas
        "options": {"queue": "gov.batch"},
    },
    # =========================================================================
    # SST - SAÚDE E SEGURANÇA DO TRABALHO
    # =========================================================================
    # Encerra afastamentos vencidos (diário)
    "sst-check-expired-leaves-daily": {
        "task": "sst.verificar_afastamentos_vencidos",
        "schedule": 86400.0,  # 24 horas
        "options": {"queue": "operacional"},
    },
    # Alerta afastamentos > 15 dias sem INSS (diário)
    "sst-check-inss-pending-daily": {
        "task": "sst.verificar_inss_pendente",
        "schedule": 86400.0,  # 24 horas
        "options": {"queue": "operacional"},
    },
    # eSocial SST — pull de recibos a cada 2h: casa recibos REAIS dos protocolos
    # pendentes (esocial_status='transmitida' sem recibo) via WsConsultarLoteEventos
    "esocial-pull-recibos": {
        "task": "sst.esocial_pull_recibos",
        "schedule": crontab(minute=20, hour="*/2"),
        "options": {"queue": "gov.esocial"},
    },
    # eSocial ESPELHO OFICIAL — re-sync DIÁRIO 09:10 (baixa eventos JÁ
    # TRANSMITIDOS — read-only). O governo limita a 10 acessos/dia e bloqueia
    # os dias 1-7 do mês (a task respeita o orçamento e pula sozinha o bloqueio);
    # com esse teto, cadência semanal levaria ~1 ano p/ enumerar a fila — por
    # isso diário (usa até 8 acessos/dia, deixa 2 de margem p/ runs manuais).
    "esocial-espelho-sync": {
        "task": "government_integrations.tasks.espelho.sincronizar_espelho_esocial",
        "schedule": crontab(minute=10, hour=9),
        "options": {"queue": "gov.esocial"},
    },
    # =========================================================================
    # SST - SAÚDE OCUPACIONAL (health_occupational) — Alertas automáticos
    # =========================================================================
    # Verifica ASOs vencendo diariamente às 07:00
    "sst-verificar-asos-vencendo-daily": {
        "task": "sst.verificar_asos_vencendo",
        "schedule": crontab(hour="7", minute="0"),
        "options": {"queue": "operacional"},
    },
    # Verifica EPIs vencendo diariamente às 07:30
    "sst-verificar-epis-vencendo-daily": {
        "task": "sst.verificar_epis_vencendo",
        "schedule": crontab(hour="7", minute="30"),
        "options": {"queue": "operacional"},
    },
    # Verifica exames periódicos pendentes diariamente às 08:00
    "sst-verificar-exames-pendentes-daily": {
        "task": "sst.verificar_exames_pendentes",
        "schedule": crontab(hour="8", minute="0"),
        "options": {"queue": "operacional"},
    },
    # Alertas SST no sino INTERNO (notification_queue → GET /notifications/push)
    # diário 08:00 America/Manaus: ASOs vencendo 30d, ASOs vencidas (semanal,
    # segunda), CATs sem eSocial >4h (prazo legal 1 dia útil), fichas EPI 7+ dias
    "sst-alertas-diarios-0800": {
        "task": "sst.alertas_diarios",
        "schedule": crontab(hour="8", minute="0"),
        "options": {"queue": "operacional"},
    },
    # =========================================================================
    # GED - KITS DOCUMENTAIS E CERTIDÕES
    # =========================================================================
    # Sincronização diária de CNDs renovadas (06:00)
    "ged-sync-cnds-daily": {
        "task": "ged.sync_cnds",
        "schedule": 86400.0,  # 24 horas
        "options": {"queue": "operacional"},
    },
    # Busca ativa de certidões nos portais governamentais (06:30)
    # GAP 3: conecta ged_sync_cnds ao HTTP dos portais (CND, CNDT, CRF)
    "fiscal.certidoes.sync_diario": {
        "task": "ged.buscar_certidoes_portais",
        "schedule": crontab(hour=6, minute=30),
        "options": {"queue": "ged"},
    },
    # Coleta mensal D4 — dia 21 às 07:00 SP (= 06:00 Manaus UTC-4, tz global SP UTC-3)
    # INV-12: America/Manaus offset. Celery global tz = America/Sao_Paulo.
    # Manaus 06:00 = Sao Paulo 07:00 (horário padrão, sem DST em Manaus).
    "ged-auto-collect-monthly": {
        "task": "ged.auto_collect_documents",
        "schedule": crontab(day_of_month="21", hour="7", minute="0"),
        "args": [None],  # reference_month=None → usa mês atual
        "options": {"queue": "operacional"},
    },
    # Sincronização de escalas de trabalho do Sólides a cada 6 horas
    "sync-work-schedules-solides": {
        "task": "integrations.sync_work_schedules_from_solides",
        "schedule": crontab(hour="*/6"),
        "options": {"queue": "integrations"},
    },
    # ── FINANCIAL — Auto-sync cashflow_entries ────────────────────────────────
    "financial-sync-cashflow-hourly": {
        "task": "financial.sync_cashflow_entries",
        "schedule": crontab(minute=15),  # todo hora no minuto 15
        "options": {"queue": "gov.batch"},
    },
    # ── GEDEON LAYER 2 — Agentes financeiros automáticos ─────────────────────
    "gedeon-risk-monitor-5min": {
        "task": "gedeon.risk_monitor",
        "schedule": 300,  # cada 5 minutos
        "options": {"queue": "gov.batch"},
    },
    "gedeon-daily-all-0700": {
        "task": "gedeon.daily_all",
        "schedule": crontab(hour=7, minute=0),
        "options": {"queue": "gov.batch"},
    },
    "gedeon-cashflow-0715": {
        "task": "gedeon.cashflow_predictor",
        "schedule": crontab(hour=7, minute=15),
        "options": {"queue": "gov.batch"},
    },
    "gedeon-collection-0900": {
        "task": "gedeon.collection_negotiator",
        "schedule": crontab(hour=9, minute=0),
        "options": {"queue": "gov.batch"},
    },
    # Alerta kits GED 100% não enviados — 08:00 Manaus (12:00 UTC) — §79
    "gedeon-verificar-kits-completos-0800": {
        "task": "gedeon.verificar_kits_completos",
        "schedule": crontab(hour="8", minute="0"),
        "options": {"queue": "gov.batch"},
    },
    # HERMES: vincula onvio_documents → slots ged_kit_documents — dia 1 às 09:00 — §94
    "gedeon-hermes-vincular-docs-0900": {
        "task": "gedeon.hermes_vincular_docs_mes",
        "schedule": crontab(day_of_month="1", hour="9", minute="0"),
        "args": [None],  # None = mês corrente
        "options": {"queue": "gov.batch"},
    },
    # ORQUESTRADOR: monta o kit documental mensal de TODOS os condomínios —
    # dia 28 às 07:00 SP (06:00 Manaus). Competência = mês anterior (salário em arrears).
    # Idempotente (rodar de novo só completa o que faltava). Notifica o Jordan no fim.
    "gedeon-montar-kits-mensais-dia28": {
        "task": "gedeon.montar_kits_mensais",
        "schedule": crontab(day_of_month="28", hour="7", minute="0"),
        "options": {"queue": "gov.batch"},
    },
    # ── CRM — Follow-up de propostas: gera lista (disparo ao cliente DESLIGADO/gate LGPD) — diário 08:30 ──
    "crm-followup-proposals-0830": {
        "task": "crm.followup_proposals",
        "schedule": crontab(hour=8, minute=30),
        "options": {"queue": "gov.batch"},
    },
    # ── CRM Growth — processa passos vencidos das sequências/cadências — de hora em hora ──
    "crm-process-sequences-hourly": {
        "task": "crm.process_sequences",
        "schedule": crontab(minute=15),
        "options": {"queue": "gov.batch"},
    },
    # ── José Luís ↔ Jordan — lembra pendências sem resposta (1x/dia ~09h Manaus = 13h UTC) ──
    "crm-owner-pendentes-diario": {
        "task": "crm.owner_pendentes",
        "schedule": crontab(hour=13, minute=0),
        "options": {"queue": "gov.batch"},
    },
    # ── José Luís ↔ Jordan — resumo do dia (~18h Manaus = 22h UTC) ──
    "crm-owner-digest-diario": {
        "task": "crm.owner_digest",
        "schedule": crontab(hour=22, minute=0),
        "options": {"queue": "gov.batch"},
    },
    # ── José Luís ↔ Jordan — dispara lembretes agendados ("me lembra amanhã") — a cada 15 min ──
    "crm-owner-reminders-due-15min": {
        "task": "crm.owner_reminders_due",
        "schedule": crontab(minute="*/15"),
        "options": {"queue": "gov.batch"},
    },
    # ── Lembrete pré-reunião (reuniões confirmadas nas próximas 24h) — de hora em hora ──
    "crm-lembrete-reuniao-hourly": {
        "task": "crm.lembrete_reuniao",
        "schedule": crontab(minute=20),
        "options": {"queue": "gov.batch"},
    },
    # ── Heartbeat do ciclo (WhatsApp/agente/webhook) — de hora em hora ──
    "crm-heartbeat-ciclo-hourly": {
        "task": "crm.heartbeat_ciclo",
        "schedule": crontab(minute=50),
        "options": {"queue": "gov.batch"},
    },
    # ── Envia follow-ups agendados (pedidos fora do horário) — só age seg-sex 8-18h ──
    "crm-enviar-followups-agendados": {
        "task": "crm.enviar_followups_agendados",
        "schedule": crontab(minute=5),
        "options": {"queue": "gov.batch"},
    },
    # ── Auto-acompanhamento de proposta enviada — de hora em hora ──
    "crm-auto-acompanhar-hourly": {
        "task": "crm.auto_acompanhar",
        "schedule": crontab(minute=10),
        "options": {"queue": "gov.batch"},
    },
    # ── Scoring automático dos leads — de hora em hora ──
    "crm-score-leads-hourly": {
        "task": "crm.score_leads",
        "schedule": crontab(minute=40),
        "options": {"queue": "gov.batch"},
    },
    # ── Radar de leads frios → avisa o Jordan (sem auto-enviar ao cliente) — diário 12h UTC ──
    "crm-radar-frios-diario": {
        "task": "crm.radar_frios",
        "schedule": crontab(hour=12, minute=0),
        "options": {"queue": "gov.batch"},
    },
    # ── José Luís — conversas que esfriaram: lista + rascunho -> Telegram (aval humano; nada vai ao cliente) — diario 09:00 ──
    "whatsapp-followup-conversas-0900": {
        "task": "whatsapp.followup_conversas",
        "schedule": crontab(hour=9, minute=0),
        "options": {"queue": "gov.batch"},
    },
    # ── José Luís — auditoria de qualidade das conversas -> digest no Telegram — diario 20:00 ──
    "whatsapp-auditar-qualidade-2000": {
        "task": "whatsapp.auditar_qualidade",
        "schedule": crontab(hour=20, minute=0),
        "options": {"queue": "gov.batch"},
    },
    # ── José Luís — atualizações proativas de OS (status do Campo -> WhatsApp do cliente) — a cada 5 min ──
    "whatsapp-notificar-status-os-5min": {
        "task": "whatsapp.notificar_status_os",
        "schedule": 300.0,
        "options": {"queue": "gov.batch"},
    },
    # ── ANALYTICS — Recálculo de KPIs a partir do dado real ──────────────────
    # De hora em hora (minuto 25) para "descongelar" executive_kpis/financial_kpis.
    "analytics-recalcular-kpis-hourly": {
        "task": "analytics.recalcular_kpis",
        "schedule": crontab(minute=25),
        "options": {"queue": "gov.batch"},
    },
    # Recálculo diário garantido às 06:15 (SP).
    "analytics-recalcular-kpis-daily": {
        "task": "analytics.recalcular_kpis",
        "schedule": crontab(hour=6, minute=15),
        "options": {"queue": "gov.batch"},
    },
}


if __name__ == "__main__":
    app.start()
