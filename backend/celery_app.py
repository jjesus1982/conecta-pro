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
        # dgx aa4: conciliação da NFS-e com o fisco (roda DEPOIS da sincronia do ADN).
        "modules.fiscal.tasks",
        "modules.crm.tasks",
        # 09/09/2026: o lote de assinatura da empresa saiu do processo do backend (morria em qualquer reload)
        "modules.signatures.tasks",
        "modules.integrations.connectors.whatsapp.tasks",
        "modules.analytics.tasks",
        # Fase 0 (Task 7/8): sino canônico + reconciliação + GED expiry (era órfã).
        "modules.notifications.tasks",
        "modules.ged.tasks.expiry_alerts",
        # Fase 5.3: proativo por evento (avaliador de regras + digest).
        "modules.notifications.proativo.tasks",
        # Fase 5.6a (LT2): detector de anomalia de pagamento (beat + sino diretoria).
        "modules.ai.fraud_detection.tasks",
        # Vigia de AUSÊNCIA da varredura dos oráculos (a varredura em si roda por cron do
        # host; quem vigia não pode depender do mesmo mecanismo que vigia).
        "modules.notifications.tasks_vigia_oraculos",
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
    # Operacional - Notificações Push
    "operacional.check_late_employees": {"queue": "operacional"},
    "operacional.check_pending_approvals": {"queue": "operacional"},
    "operacional.lembrete_ponto_whatsapp": {"queue": "operacional"},
    # A RESPOSTA do José Luís ao Jordan/cliente: fila `webhooks` (prioridade 8, consumidor
    # MEDIDO vivo no worker `integrations`). Sem rota explícita ela cairia em `gov.batch`,
    # a fila dos lotes de governo — resposta de gente atrás de fila de lote é silêncio com
    # outro nome. 28/08/2026.
    "whatsapp.processar_incoming": {"queue": "webhooks"},
    "whatsapp.varrer_sem_resposta": {"queue": "webhooks"},
    # Troca de turno: tirar o Paiva do 05:30 (24/09/2026). Fila de webhooks porque são
    # mensagens de WhatsApp e a ordem importa (o lembrete não pode passar o relatório).
    "whatsapp.varrer_grupos_mencao": {"queue": "webhooks"},
    "whatsapp.expurgar_grupos": {"queue": "maintenance"},
    "whatsapp.turno_pedir_confirmacao": {"queue": "webhooks"},
    "whatsapp.turno_lembrar": {"queue": "webhooks"},
    "whatsapp.turno_fechar_cobertura": {"queue": "webhooks"},
    # Análise de foto/áudio/vídeo. Mesma fila da resposta: é o mesmo pedaço de conversa e
    # a ordem entre eles importa (a descrição precisa estar pronta antes do turno).
    "whatsapp.analisar_midia": {"queue": "webhooks"},
    "whatsapp.checar_saldo_llm": {"queue": "webhooks"},
    "whatsapp.checar_canal_surdo": {"queue": "webhooks"},
    # Operacional - Banco de Horas / Relatórios
    "operacional.expire_time_bank_entries": {"queue": "operacional"},
    "operacional.send_shift_reminders": {"queue": "operacional"},
    "operacional.daily_coverage_report": {"queue": "operacional"},
    "operacional.supervisao_planejada_gerar": {"queue": "operacional"},
    "operacional.ronda_alertas_avaliar": {"queue": "operacional"},
    "operacional.fechar_turnos_por_ponto": {"queue": "operacional"},
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

# Falha de tarefa agendada -> alerta no sino (uma por tarefa por dia).
# Import por EFEITO COLATERAL: o decorador @task_failure.connect registra o
# manipulador. Sem isto, tarefa que estoura todo dia so aparece no log do
# container — foi assim que o fechamento contabil parou em julho/2026.
from modules.notifications import task_falha  # noqa: E402,F401

# Beat Schedule (tarefas agendadas)
app.conf.beat_schedule = {
    # ── Fase 0: reconciliação do sino (espinha de completude, imune a evento perdido) ──
    "notificacoes-reconciliar-alertas": {
        "task": "notifications.reconciliar_alertas",
        "schedule": crontab(minute="*/15"),
    },
    # ── Fase 5.3: avaliador de regras proativas (transição → sino, dedup por estado) ──
    "proativo-avaliar-regras": {
        "task": "proativo.avaliar_regras",
        "schedule": crontab(minute="*/15"),
        "options": {"queue": "gov.batch"},
    },
    # ── Fase 5.3: digest matinal 07:00 America/Manaus — consolida em 1 notificação
    #    por destinatário o que PERSISTE (RBAC por regra.roles_destino). Verificado
    #    2026-07-25: app.conf.timezone (acima) == "America/Manaus" E o container
    #    celery-beat roda com TZ=America/Manaus — o crontab do celery interpreta a
    #    hora no timezone configurado, então hour=7 já É 07:00 Manaus (não 07:00 UTC).
    # ── Calendário fiscal: a obrigação existe por LEI, não porque o PDF da guia chegou.
    #    Dependia do sync do Drive; as guias pararam em dez/2025 e as competências 04, 05 e
    #    07/2026 nunca existiram — em 11/08 havia UMA obrigação vencendo nos 30 dias no
    #    sistema inteiro. Mensal, dia 1, e idempotente.
    "fiscal-calendario-obrigacoes": {
        "task": "fiscal.calendario_obrigacoes",
        "schedule": crontab(day_of_month="1", hour=6, minute=12),
        "options": {"queue": "gov.batch"},
    },
    # ── Alarme de AUSÊNCIA: se a varredura dos oráculos não rodou nas últimas 30h, o sino
    #    toca. Sem isto, silêncio significa "tudo verde" E "o cron nunca disparou" — a mesma
    #    ambiguidade que deixou 59 oráculos apodrecerem. 08:11, depois da janela das 05:00.
    "oraculos-vigia-ausencia": {
        "task": "orq.checar_varredura_ausente",
        "schedule": crontab(hour=8, minute=11),
        "options": {"queue": "gov.batch"},
    },
    # ── Os 59 oráculos NÃO rodam aqui: um oráculo tem pico de 894 MB (importa o app) e
    #    todo worker tem limite de 2 GB com 1,39 GB em uso — a varredura derrubaria por OOM
    #    o worker de gov/financeiro/integrações. Roda por cron do host no container do
    #    backend (6 GB), via modules/notifications/tasks_oraculos.py --varrer.
    # ── 11/09/2026 · TRIAGEM DE PONTO PELO HERMES. 08:30 Manaus, todo dia. O turno da manhã
    #    entra 07:00 e os três lembretes automáticos vão até 07:10 — olhar antes seria cobrar
    #    quem o próprio sistema ainda está cobrando. Roteada para `gov.batch` como as outras
    #    tarefas longas; o agente leva minutos (dezenas de chamadas de ferramenta por turno).
    "ponto-triagem-hermes": {
        "task": "ponto.triagem_hermes",
        "schedule": crontab(hour=8, minute=30),
        "options": {"queue": "gov.batch"},
    },
    "proativo-digest-diario": {
        "task": "proativo.digest_diario",
        "schedule": crontab(hour=7, minute=0),
        "options": {"queue": "gov.batch"},
    },
    # ── Fase 5.6a (LT2): detector de anomalia de pagamento — varre inter_payments
    #    (read-only) e avisa a diretoria no sino de suspeitas HIGH/CRITICAL ──
    "anomalia-varrer-pagamentos": {
        "task": "anomalia.varrer_pagamentos",
        "schedule": crontab(minute="*/30"),
        "options": {"queue": "gov.batch"},
    },
    # ── Fase 0: retenção leve do sino (expira não-alertas antigos; alertas retidos) ──
    "notificacoes-purgar": {
        "task": "notifications.purgar_notificacoes",
        "schedule": crontab(hour=3, minute=0),
    },
    # ── GED: alertas de vencimento de documento (task era órfã; agora agendada) ──
    "ged-check-document-expiry": {
        "task": "ged.check_document_expiry",
        "schedule": crontab(hour=8, minute=15),
    },
    # ── Financeiro — Conciliação bancária diária (extrato Inter → bridge → categoriza) ──
    "financeiro-conciliacao-inter-diaria": {
        "task": "financial.inter_reconciliacao_diaria",
        "schedule": crontab(hour=8, minute=0),
        "options": {"queue": "gov.batch"},
    },
    # Auto-baixa de contas a pagar por conciliação (SÓ match exato) — após o sync do extrato (08:00).
    "financeiro-auto-baixa-pagaveis": {
        "task": "financial.auto_baixa_pagaveis",
        "schedule": crontab(hour=8, minute=30),
        "options": {"queue": "gov.batch"},
    },
    # (financeiro-propor-baixa-pendentes vive abaixo do dict — está DESLIGADO)
    # Registra como pagável o que a empresa deve (NFS-e tomadas, folha, guias).
    # Roda ANTES da auto-baixa: primeiro a obrigação existe, depois o extrato a liquida.
    "financeiro-registrar-obrigacoes": {
        "task": "financial.registrar_obrigacoes",
        "schedule": crontab(hour=8, minute=15),
        "options": {"queue": "gov.batch"},
    },
    # Radar de fornecedor recorrente SEM título. Roda DEPOIS do registrar-obrigacoes:
    # senão avisaria sobre o que a rotina anterior acabou de criar. Telecom, energia e
    # água não emitem NFS-e, então escapam daquele motor — foi assim que um boleto da
    # Full Telecom venceu e custou juros. Só avisa; não cria pagável.
    "financeiro-radar-fornecedores": {
        "task": "financial.radar_fornecedores",
        "schedule": crontab(hour=8, minute=45),
        "options": {"queue": "gov.batch"},
    },
    # Boleto recebido por e-mail vira conta a pagar. Roda 3x ao dia porque boleto chega a
    # qualquer hora e o valor está no prazo: descobrir no dia seguinte já pode ser tarde.
    # Só registra código de barras VÁLIDO; NÃO paga.
    # "Ele lança, eu pago" — o passo de PROGRAMAR o VT+VR sai do caminho do Jordan.
    # De hora em hora entre 7h e 21h porque o VT/VR é pago no MESMO dia; rodar só à noite
    # o faria esperar o dia seguinte para pagar o que o Eliziel acabou de lançar.
    # Programar NÃO paga: cria a obrigação, o dinheiro sai pelo gate com OTP.
    # Aviso no WhatsApp quando o Eliziel/Orlailson lançam diária. 10 min: rápido o
    # bastante para ser útil, espaçado o bastante para não virar ruído — notificação que
    # cansa deixa de ser lida, e aí é o mesmo que não avisar.
    "financeiro-aviso-diarias-whatsapp": {
        "task": "financial.aviso_diarias_whatsapp",
        "schedule": crontab(minute="*/10"),
        "options": {"queue": "gov.batch"},
    },
    "financeiro-programar-vtvr-do-dia": {
        "task": "financial.programar_vtvr_do_dia",
        "schedule": crontab(hour="7-21", minute=5),
        "options": {"queue": "gov.batch"},
    },
    "financeiro-boletos-por-email": {
        "task": "financial.boletos_por_email",
        "schedule": crontab(hour="7,13,19", minute=10),
        "options": {"queue": "gov.batch"},
    },
    # Recebível por contrato/competência — dia 1 de cada mês. Sem isso o contas-a-receber
    # fica vazio e aging/inadimplência/régua de cobrança giram no vácuo.
    # NÃO emite cobrança ao cliente: boleto/PIX é ato separado, com decisão humana.
    "financeiro-gerar-recebiveis-mensal": {
        "task": "financial.gerar_recebiveis_mes",
        "schedule": crontab(hour=6, minute=0, day_of_month=1),
        "options": {"queue": "gov.batch"},
    },
    # Escritura o extrato no razão. 08:40 = DEPOIS de todo mundo que mexe no
    # extrato: Inter 08:00, Cora 08:10, obrigações 08:15, auto-baixa 08:30.
    # Estava às 05:20, ANTES dos syncs — cada movimentação esperava ~24h para
    # virar lançamento e o alarme `caixa_divergente` (que roda a cada 15 min e
    # conta movimentação sem lançamento) tocaria ~21h por dia, todo dia.
    "financeiro-escriturar-extrato": {
        "task": "financial.escriturar_extrato",
        "schedule": crontab(hour=8, minute=40),
        "options": {"queue": "gov.batch"},
    },
    # Encerra a competência anterior contra o PL. Dia 5 — depois de a NFS-e do mês
    # fechado ter entrado. Sem isto, 4.x e 5.x acumulam para sempre e o balanço
    # não fecha: foi assim que 42 competências ficaram abertas desde 2022.
    "financeiro-apurar-competencia": {
        "task": "financial.apurar_competencia",
        "schedule": crontab(hour=9, minute=0, day_of_month=5),
        "options": {"queue": "gov.batch"},
    },
    # ── Multi-CNPJ E4: extrato Cora (Patrimonial) + conciliação líquido×NFS-e ──
    "financeiro-extrato-cora-diario": {
        "task": "financial.cora_sync_extrato",
        "schedule": crontab(hour=8, minute=10),
        "options": {"queue": "gov.batch"},
    },
    # ── Saldos Inter+Cora frescos (bank_accounts) a cada 15 min, no worker ──
    # A tela "Saldos por conta" lê esse cache; o fetch ao vivo fica AQUI (worker),
    # nunca no render das telas (I/O externo no web derrubava o worker → 502).
    "financeiro-sync-saldos-15min": {
        "task": "financial.sync_bank_balances",
        "schedule": crontab(minute="*/15"),
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
    # Aviso por e-mail de documento a assinar. 09:00 é quando o pessoal do diurno já
    # entrou e o do noturno ainda não dormiu — a janela em que a mensagem é lida.
    # O serviço tem trava de reenvio própria (3 dias), então rodar diariamente não vira spam.
    "assinaturas-avisar-pendentes": {
        "task": "gedeon.assinaturas.avisar_pendentes",
        "schedule": crontab(hour=9, minute=0),
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
    # Portal do Cliente — resumo mensal de reengajamento (dia 1º, 08:00 Manaus)
    "portal-resumo-mensal": {
        "task": "portal.resumo_mensal_clientes",
        "schedule": crontab(minute=0, hour=9, day_of_month="1"),
        "options": {"queue": "gov.batch"},
    },
    # REMOVIDAS em 11/08/2026 — briefing matinal e vigia de ausência eram PURO Telegram:
    # faziam a consulta e entregavam a mensagem no bot. O Jordan apagou e bloqueou os dois
    # bots (Conecta PRO Monitor e Conecta PRO Alertas), então elas rodavam 33x por dia
    # (1 briefing + 32 vigias) para jogar o resultado fora.
    # As tarefas em si continuam no código; só saíram do beat. Se algum dia o aviso fizer
    # falta, o caminho é o SINO — que é o canal da casa e o que as tarefas do José Luís
    # já usam —, não um bot novo.
    # Dia 25, 08:00 SP: gera em rascunho as escalas do mês seguinte (nunca publica sozinho)
    "operacional-escalas-proximo-mes": {
        "task": "operacional.gerar_escalas_proximo_mes",
        "schedule": crontab(minute=0, hour=8, day_of_month="25"),
        "options": {"queue": "gov.batch"},
    },
    # =========================================================================
    # FISCAL — NF-e ENTRADA (RECEBIMENTO AUTOMÁTICO). 08/09/2026: saíram do beat check-endpoints (2.000 GETs/dia
    # às SEFAZ para empresa que não emite NF-e), check-certificates/reprocess/daily-report/cleanup (tasks vazias)
    # e fiscal-nfse-entrada (405 diário; as tomadas vêm de financial.sincronizar_nfse_nacional).
    # =========================================================================
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
    # dgx aa4 — conciliação por NÚMERO, depois da sincronia por NSU acima. Pergunta ao
    # fisco pelos números que a régua da numeração por CNPJ diz que faltam, e grava
    # também a resposta «não existe». Só GET: não emite, não cancela, não numera.
    "fiscal-conciliar-nfse-diario": {
        "task": "fiscal.conciliar_nfse_com_fisco",
        "schedule": crontab(hour=5, minute=30),
    },
    # Contabilidade que fecha sozinha: folha + ISS no razão — diariamente às 05:00
    "financial-fechar-razao-diario": {
        "task": "financial.fechar_razao_auto",
        "schedule": crontab(hour=5, minute=0),
    },
    # =========================================================================
    # SÓLIDES - INTEGRAÇÃO RH/DP
    # =========================================================================
    # DESLIGADO em 16/09/2026 por decisão do Jordan. O sync roda
    # `UPDATE employees SET nome = :nome, pis, data_nascimento, sexo, escala_padrao, status
    #  WHERE cpf = :cpf` (solides/tasks.py) e SOBRESCREVE o que se corrige à mão no
    # Conecta PRO. Medido no mesmo dia, duas vezes seguidas:
    #
    #     03:28  gravei  BIANCA HELLEM DA SILVA MEIRA  (grafia confirmada pelo banco no PIX)
    #     03:57  voltou  BIANCA HELEM DA SILVA MEIRA   (o sync desfez)
    #
    # O nome errado dela já custou uma mensagem de aviso não entregue e o recibo de VT/VR
    # sem solicitação de assinatura. Não é só o nome: PIS, escala e status vinham junto.
    # Enquanto a fonte for o Sólides, correção no Conecta PRO tem prazo de validade.
    #
    # A TASK CONTINUA EXISTINDO (`solides.sync_all_condominios_incremental`) para chamada
    # manual — só não roda mais sozinha. Para religar, devolva este bloco.
    # "solides-incremental-sync-all": {
    #     "task": "solides.sync_all_condominios_incremental",
    #     "schedule": 900.0,  # 15 minutos
    #     "options": {"queue": "integrations"},
    # },
    # DESLIGADO em 13/09/2026 por decisão do Jordan: "os pontos já estão sendo batidos
    # pelo Conecta PRO, já não temos mais necessidade de puxar as batidas do
    # Sólides/Tangerino". O que o pull trazia não era batida medida e sim a GRADE da
    # escala — em 09/2026 foram 422 registros com só 48 horários distintos, 382 em hora
    # cheia, contra 763 registros e 763 horários distintos do app. Nos 95 dias-pessoa em
    # que as duas fontes coexistiam, a grade (que vem ~1h adiantada) entrava junto e
    # quebrava o pareamento do espelho: 134 das 180 anomalias de setembro eram esse
    # defeito, e por causa dele o mês não fechava.
    #
    # A TASK CONTINUA EXISTINDO (`solides.sync_punches`) para chamada manual — só não
    # roda mais sozinha. Para religar, devolva este bloco.
    # "solides-sync-punches": {
    #     "task": "solides.sync_punches",
    #     "schedule": 900.0,
    #     "kwargs": {"days_back": 2},
    #     "options": {"queue": "integrations"},
    # },
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
    # Lembrete de ponto por WhatsApp — a cada 60s (as janelas são de 1 minuto).
    # Volume real baixo: só dispara nos minutos -15, 0 e +10 de cada turno, e para
    # na batida. Kill switch: PONTO_LEMBRETE_ENABLED (default false = só loga).
    "operacional-lembrete-ponto-whatsapp": {
        "task": "operacional.lembrete_ponto_whatsapp",
        "schedule": 60.0,
        "options": {"queue": "operacional"},
    },
    # Verifica aprovações pendentes a cada 1 hora
    "operacional-check-pending-approvals": {
        "task": "operacional.check_pending_approvals",
        "schedule": 3600.0,  # 1 hora
        "options": {"queue": "operacional"},
    },
    # Fecha por ponto os turnos que já acabaram (scheduled → completed/partial).
    # 05:40 é depois que a última saída do turno da noite (06:00) ainda não bateu —
    # por isso só olha de ONTEM pra trás; turno de hoje ainda recebe batida.
    # Não marca falta: turno sem batida fica scheduled e vira candidata para humano.
    "operacional-fechar-turnos-diario": {
        "task": "operacional.fechar_turnos_por_ponto",
        "schedule": crontab(hour=5, minute=40),
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
    # Alertas de ronda (DGX U4): ronda atrasada / ponto pulado / fora de sequência, a cada 5 min
    "operacional-ronda-alertas": {
        "task": "operacional.ronda_alertas_avaliar",
        "schedule": crontab(minute="*/5"),
        "options": {"queue": "operacional"},
    },
    # Supervisão planejada (DGX U1): gera as ocorrências do dia às 00:30 Manaus e fecha o passado
    "operacional-supervisao-planejada": {
        "task": "operacional.supervisao_planejada_gerar",
        "schedule": crontab(hour=0, minute=30),  # app.conf.timezone = America/Manaus
        "options": {"queue": "operacional"},
    },
    # Relatório de cobertura diário às 23:55h
    "operacional-daily-coverage-report": {
        "task": "operacional.daily_coverage_report",
        "schedule": 86400.0,  # 24 horas
        "options": {"queue": "operacional"},
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
    #
    # ⚠️ A fila era `ged` e NENHUM worker consumia `ged`. Medido em 17/08/2026:
    #
    #     fila ged          -> 101 mensagens acumuladas
    #     fila gov.esocial  -> 0
    #     fila gov.batch    -> 0
    #
    # Cento e uma execuções despachadas e nunca consumidas — o vigia de vencimento de
    # certidão nunca rodou por agendamento, desde sempre. E do jeito mais silencioso
    # possível: mensagem enfileirada não falha, não estoura, não vai para o sino. Fica.
    #
    # As filas que EXISTEM são as dos workers do compose: gov.esocial, gov.fgts,
    # operacional, integrations, webhooks, maintenance, gov.batch, gov.nfse e as três
    # gov.sefaz.*. `ged` nunca esteve entre elas. Vai para `gov.batch`, que é onde moram
    # as outras tarefas diárias de governo e tem consumidor (celery-batch).
    "fiscal.certidoes.sync_diario": {
        "task": "ged.buscar_certidoes_portais",
        "schedule": crontab(hour=6, minute=30),
        "options": {"queue": "gov.batch"},
    },
    # Coleta mensal D4 — dia 21 às 07:00 SP (= 06:00 Manaus UTC-4, tz global SP UTC-3)
    # INV-12: America/Manaus offset. Celery global tz = America/Sao_Paulo.
    # Manaus 06:00 = Sao Paulo 07:00 (horário padrão, sem DST em Manaus).
    # 09/09/2026: montagem incremental diária — o kit cresce à medida que cada processo termina (06:30 Manaus)
    "ged-kit-incremental-diario": {
        "task": "ged.kit_incremental_diario",
        "schedule": crontab(hour="7", minute="30"),
        "options": {"queue": "operacional"},
    },
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
    # ── José Luís — conversas que esfriaram: lista + rascunho -> SINO (aval humano; nada vai ao cliente) — diario 09:00 ──
    # Rede de segurança da resposta: a cada 2 min procura conversa cuja última mensagem é
    # do cliente e ficou sem resposta. Transforma "sumiu" em "atrasou" — ver
    # whatsapp.varrer_sem_resposta.
    # ── TROCA DE TURNO — os três tempos (Jordan, 24/09/2026) ───────────────────────────────
    # ⚠️ TODO `crontab` AQUI É UTC, e a operação é Manaus (UTC-4). Errar isso põe a pergunta da
    # véspera às 14h e o lembrete depois do turno já ter começado — o defeito seria invisível
    # para mim e óbvio para quem recebe a mensagem na hora errada.
    #   véspera 18:00 Manaus = 22:00 UTC
    "whatsapp-turno-pedir-confirmacao": {
        "task": "whatsapp.turno_pedir_confirmacao",
        "schedule": crontab(hour=22, minute=0),
    },
    #   lembrete: roda de 15 em 15 entre 04:00 e 07:00 UTC (00:00–03:00 Manaus)? NÃO —
    #   o turno é 06/07h MANAUS = 10/11h UTC, e o lembrete é 1h antes: 09:00–11:00 UTC.
    #   A própria task só age em quem está a ~1h de assumir, então rodar de 15 em 15 é barato
    #   e tolera atraso de fila sem perder ninguém.
    "whatsapp-turno-lembrar-15min": {
        "task": "whatsapp.turno_lembrar",
        "schedule": crontab(minute="*/15", hour="9-11"),
    },
    #   cobertura: 08:30 Manaus = 12:30 UTC — depois das duas trocas (06h e 07h), com folga
    #   para batida atrasada entrar na conta.
    "whatsapp-turno-cobertura": {
        "task": "whatsapp.turno_fechar_cobertura",
        "schedule": crontab(hour=12, minute=30),
    },
    # Rede de segurança PARA GRUPO: só menção ao José Luís que ficou sem resposta. A de
    # 2 minutos (`varrer_sem_resposta`) exclui grupo de propósito — ver a task.
    # Retenção: 07:10 UTC = 03:10 Manaus. Longe do pico e antes dos oráculos das 05:00.
    "whatsapp-expurgar-grupos-diario": {
        "task": "whatsapp.expurgar_grupos",
        "schedule": crontab(hour=7, minute=10),
    },
    "whatsapp-varrer-grupos-mencao-3min": {
        "task": "whatsapp.varrer_grupos_mencao",
        "schedule": crontab(minute="*/3"),
    },
    "whatsapp-varrer-sem-resposta-2min": {
        "task": "whatsapp.varrer_sem_resposta",
        "schedule": crontab(minute="*/2"),
    },
    # ── Saldo do provedor do LLM -> WhatsApp do dono — de hora em hora ──
    # Em 31/08 a conta zerou e o Jordan só descobriu levando "problema técnico" na cara
    # durante uma hora. De hora em hora basta: o gasto diário é de ordem US$ 1-3, então
    # entre duas checagens o saldo não despenca um patamar inteiro.
    # ── Canal do WhatsApp surdo (verde e mudo) — a cada 10 min ──
    # 10 min porque a falha de hoje durou 2h19 e ninguém viu: o valor está em avisar antes
    # de o Jordan reclamar. Duas sondas falhas = 20 min até o aviso, contra as 2h de hoje.
    "whatsapp-checar-canal-surdo-10min": {
        "task": "whatsapp.checar_canal_surdo",
        "schedule": 600.0,
    },
    "whatsapp-checar-saldo-llm-hourly": {
        "task": "whatsapp.checar_saldo_llm",
        "schedule": crontab(minute=7),
    },
    "whatsapp-followup-conversas-0900": {
        "task": "whatsapp.followup_conversas",
        "schedule": crontab(hour=9, minute=0),
        "options": {"queue": "gov.batch"},
    },
    # ── José Luís — auditoria de qualidade das conversas -> digest no SINO — diario 20:00 ──
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

# ── Propor baixa de pagáveis: DESLIGADO a pedido do Jordan (2026-08-09) ───────
# O beat varria pagáveis vencidos >30d e ≥R$500 e criava 1 rascunho de baixa por
# conta na Central (40/dia). Com o contas-a-pagar recém-reconstruído (69 → 297
# contas), isso viraria ~103 rascunhos de fila para contas cujo pagamento ainda
# não foi provado no extrato — ruído, não decisão. A ação manual "Dar baixa"
# (grupo Pagar) e a auto-baixa por conciliação seguem funcionando normalmente.
# Religar NÃO precisa de deploy: basta CONECTA_PROPOR_BAIXA=1 no .env da raiz e
# recriar os workers.
if os.getenv("CONECTA_PROPOR_BAIXA", "0").strip().lower() in ("1", "true", "sim"):
    app.conf.beat_schedule["financeiro-propor-baixa-pendentes"] = {
        "task": "financial.propor_baixa_pendentes",
        "schedule": crontab(hour=8, minute=45),
        "options": {"queue": "gov.batch"},
    }

# Enriquece o extrato do Inter com a contraparte: 08:20, DEPOIS do sync (08:00/08:10)
# e ANTES da conciliação (08:30) — que passa a casar por CPF em vez de valor e data.
app.conf.beat_schedule["financeiro-enriquecer-extrato-inter"] = {
    "task": "financial.enriquecer_extrato_inter",
    "schedule": crontab(hour=8, minute=20),
    "options": {"queue": "gov.batch"},
}

# Fecha ordem de pagamento contra o extrato: 08:40, DEPOIS do sync do extrato
# (08:00/08:10) e da conciliação (08:30). O pagamento foi feito no app do banco;
# aqui o sistema reconhece que saiu, sem ninguém voltar na tela.
app.conf.beat_schedule["financeiro-fechar-ordens-pagamento"] = {
    "task": "financial.fechar_ordens_pagamento",
    "schedule": crontab(hour=8, minute=40),
    "options": {"queue": "gov.batch"},
}

# Cobrança dos vencidos: 08:50, DEPOIS da conciliação das entradas (08:30 no
# auto_baixa_pagaveis) — cobrar quem já pagou é pior do que não cobrar. Fica
# LIGADO por padrão, ao contrário do propor-baixa: a fila é pequena porque só
# entra o que sobreviveu à conciliação, e inadimplência silenciosa custa caro.
# NÃO envia nada ao cliente; entrega o texto pronto na Central.
if os.getenv("CONECTA_PROPOR_COBRANCA", "1").strip().lower() in ("1", "true", "sim"):
    app.conf.beat_schedule["financeiro-propor-cobranca-vencidos"] = {
        "task": "financial.propor_cobranca_vencidos",
        "schedule": crontab(hour=8, minute=50),
        "options": {"queue": "gov.batch"},
    }


if __name__ == "__main__":
    app.start()
