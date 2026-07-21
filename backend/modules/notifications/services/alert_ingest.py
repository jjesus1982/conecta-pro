"""Fase 0 (Task 5): ingestão canônica de alertas — helper único `enqueue_alert`.

Todo produtor de alerta (RiskMonitor, jurídico, SST, GED, reconciliador) passa por
aqui. UPSERT idempotente contra o índice único (tenant_id, correlation_id): o mesmo
alerta atualiza a linha em vez de duplicar. Âncora de entidade obrigatória
(source_entity_*) — é o gancho do cruzamento futuro. Severidade normalizada numa
régua única (info/atencao/critico → priority do notification_queue).

Convenção de correlation_id: "{category}:{source_entity_type}:{source_entity_id}".
"""
from uuid import uuid4

from sqlalchemy import text

# Régua canônica de severidade a partir das 4 escalas legadas do sistema.
_SEV = {
    "info": "info", "warning": "atencao", "error": "critico", "critical": "critico",
    "green": "info", "yellow": "atencao", "orange": "atencao", "red": "critico",
    "amarelo": "atencao", "laranja": "atencao", "vermelho": "critico", "critico": "critico",
    "atencao": "atencao", "baixo": "info", "medio": "atencao", "alto": "critico",
}
# severidade canônica → priority (enum queuepriority: 1,2,5,8,10)
_SEV_TO_PRIORITY = {"info": "2", "atencao": "5", "critico": "8"}
_TENANT_DEFAULT = "00000000-0000-0000-0000-000000000001"


def normalize_severity(origem: str, valor) -> str:
    """Mapeia qualquer das 4 escalas legadas para info/atencao/critico."""
    return _SEV.get(str(valor).strip().lower(), "info")


async def enqueue_alert(
    db,
    *,
    category: str,
    source_entity_type: str,
    source_entity_id,
    severity,
    title: str,
    body: str = "",
    tenant_id=None,
    empresa_id=None,
    priority=None,
) -> str:
    """Insere/atualiza um alerta no notification_queue (idempotente por entidade).

    Retorna o id (uuid) da linha. `source_entity_id` deve ser um uuid (ou None).
    Não dispara ação nenhuma — só materializa a visibilidade no sino.
    """
    sev = normalize_severity("canon", severity)
    prio = str(priority) if priority is not None else _SEV_TO_PRIORITY.get(sev, "5")
    corr = f"{category}:{source_entity_type}:{source_entity_id}"
    tid = str(tenant_id) if tenant_id else _TENANT_DEFAULT
    sid = str(source_entity_id) if source_entity_id is not None else None
    row = await db.execute(
        text(
            """
            INSERT INTO notification_queue
              (id, tenant_id, notification_id, correlation_id, source_entity_type,
               source_entity_id, category, recipient_address, channel_type, status,
               priority, subject, body, enqueued_at, created_at, updated_at)
            VALUES
              (gen_random_uuid(), :tid, :nid, :corr, :set, CAST(:sid AS uuid), :cat,
               'push', 'push', 'pending', :prio, :subj, :body, now(), now(), now())
            ON CONFLICT (tenant_id, correlation_id) WHERE correlation_id IS NOT NULL
            DO UPDATE SET subject = EXCLUDED.subject, body = EXCLUDED.body,
                          priority = EXCLUDED.priority, status = 'pending', updated_at = now()
            RETURNING id;
            """
        ),
        {"tid": tid, "nid": f"alert-{uuid4().hex}", "corr": corr,
         "set": source_entity_type, "sid": sid, "cat": category, "prio": prio,
         "subj": title, "body": body},
    )
    return str(row.scalar())
