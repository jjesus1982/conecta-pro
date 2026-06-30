"""
Motores das features de crescimento do CRM:
- scoring configurável (regras -> pontuação do lead)
- workflows/automação (evento -> condições -> ações)
- sequências/cadências (enrollment + processamento dos passos vencidos)
- segmentação dinâmica (filtros -> WHERE SQL seguro)

Tudo best-effort: nunca levanta exceção para o fluxo chamador.
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------------
# Avaliador de operadores (compartilhado por scoring, workflows e segmentos)
# ----------------------------------------------------------------------------
def match_operator(actual, operator: str, expected) -> bool:
    op = (operator or "eq").lower()
    a_str = "" if actual is None else str(actual).strip().lower()
    e_str = "" if expected is None else str(expected).strip().lower()
    try:
        if op in ("empty", "is_empty"):
            return actual is None or a_str == ""
        if op in ("not_empty", "is_not_empty", "exists"):
            return actual is not None and a_str != ""
        if op in ("eq", "equals", "="):
            return a_str == e_str
        if op in ("ne", "not_equals", "!="):
            return a_str != e_str
        if op in ("contains", "like"):
            return e_str in a_str
        if op in ("not_contains",):
            return e_str not in a_str
        if op in ("gt", ">"):
            return float(actual) > float(expected)
        if op in ("gte", ">="):
            return float(actual) >= float(expected)
        if op in ("lt", "<"):
            return float(actual) < float(expected)
        if op in ("lte", "<="):
            return float(actual) <= float(expected)
        if op in ("in",):
            vals = [v.strip().lower() for v in str(expected).split(",")]
            return a_str in vals
    except (ValueError, TypeError):
        return False
    return False


def _entity_value(entity: dict, field: str):
    """Lê field do dict; suporta custom_fields.<key>."""
    if field and field.startswith("custom_fields."):
        cf = entity.get("custom_fields") or {}
        return cf.get(field.split(".", 1)[1])
    return entity.get(field)


def eval_conditions(entity: dict, conditions: list) -> bool:
    """Todas as condições precisam bater (AND). Lista vazia = sempre verdadeiro."""
    if not conditions:
        return True
    for c in conditions:
        if not match_operator(_entity_value(entity, c.get("field")), c.get("operator", "eq"), c.get("value")):
            return False
    return True


# ----------------------------------------------------------------------------
# 8) Lead scoring configurável
# ----------------------------------------------------------------------------
async def recompute_lead_score(db: AsyncSession, lead_id: str) -> int | None:
    """Aplica as regras ativas de scoring a um lead e grava lead.score. Retorna o score."""
    try:
        row = (
            (
                await db.execute(
                    text("""
            SELECT name, email, phone, company, position, source, status, industry,
                   expected_value, COALESCE(custom_fields,'{}'::jsonb) custom_fields
            FROM leads WHERE id = :id
        """),
                    {"id": lead_id},
                )
            )
            .mappings()
            .first()
        )
        if not row:
            return None
        entity = dict(row)
        rules = (
            (
                await db.execute(
                    text("SELECT field, operator, value, points FROM crm_scoring_rules WHERE is_active = true")
                )
            )
            .mappings()
            .all()
        )
        score = 0
        for r in rules:
            if match_operator(_entity_value(entity, r["field"]), r["operator"], r["value"]):
                score += int(r["points"] or 0)
        score = max(0, min(100, score))
        await db.execute(text("UPDATE leads SET score = :s WHERE id = :id"), {"s": score, "id": lead_id})
        await db.commit()
        return score
    except Exception as exc:  # noqa: BLE001
        logger.warning("recompute_lead_score falhou (%s): %s", lead_id, exc)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None


async def recompute_all_lead_scores(db: AsyncSession) -> int:
    """Recalcula score de todos os leads. Retorna quantos foram atualizados."""
    ids = (await db.execute(text("SELECT id FROM leads"))).scalars().all()
    n = 0
    for lid in ids:
        if await recompute_lead_score(db, str(lid)) is not None:
            n += 1
    return n


# ----------------------------------------------------------------------------
# Ações (usadas por workflows e — algumas — por sequências)
# ----------------------------------------------------------------------------
async def _action_send_email(db, entity, params) -> str:
    from core.mailer import send_email

    to = entity.get("email") or params.get("to")
    if not to:
        return "skip: sem email"
    subj = _render(params.get("subject", "Conecta Mais"), entity)
    body = _render(params.get("body", ""), entity).replace("\n", "<br>")
    ok = await send_email(to, subj, f"<div style='font-family:Arial'>{body}</div>")
    return "email enviado" if ok else "email falhou"


async def _action_send_whatsapp(db, entity, params) -> str:
    phone = entity.get("phone") or params.get("phone")
    if not phone:
        return "skip: sem telefone"
    msg = _render(params.get("message", params.get("body", "")), entity)
    try:
        from modules.integrations.connectors.whatsapp.service import send_text_message  # type: ignore

        await send_text_message(phone, msg)
        return "whatsapp enviado"
    except Exception as exc:  # noqa: BLE001
        logger.info("whatsapp indisponível (%s) — registrado só log", exc)
        return f"whatsapp indisponível: {exc}"


async def _action_create_task(db, entity, params) -> str:
    from uuid import uuid4

    due = params.get("due_in_days")
    due_sql = "CURRENT_DATE + CAST(:d AS integer)" if due is not None else "NULL"
    await db.execute(
        text(f"""
        INSERT INTO crm_tasks (id, title, description, status, priority, due_date, lead_id, created_at, updated_at)
        VALUES (:id, :title, :desc, 'pending', :prio, {due_sql}, :lead, now(), now())
    """),
        {
            "id": str(uuid4()),
            "title": _render(params.get("title", "Tarefa automática"), entity)[:255],
            "desc": _render(params.get("description", ""), entity),
            "prio": params.get("priority", "medium"),
            "lead": entity.get("id"),
            **({"d": int(due)} if due is not None else {}),
        },
    )
    await db.commit()
    return "tarefa criada"


async def _action_assign_owner(db, entity, params) -> str:
    owner = params.get("user_id") or params.get("assigned_to_id")
    if not owner or not entity.get("id"):
        return "skip: sem owner"
    await db.execute(text("UPDATE leads SET assigned_to_id = :o WHERE id = :id"), {"o": owner, "id": entity.get("id")})
    await db.commit()
    return "responsável atribuído"


async def _action_enroll_sequence(db, entity, params) -> str:
    seq_id = params.get("sequence_id")
    if not seq_id or not entity.get("id"):
        return "skip: sem sequência/lead"
    seq = (
        (
            await db.execute(
                text("SELECT id, steps FROM crm_sequences WHERE id = :id AND is_active = true"), {"id": seq_id}
            )
        )
        .mappings()
        .first()
    )
    if not seq:
        return "skip: sequência inativa"
    await enroll_lead(db, seq, entity.get("id"))
    return "lead inscrito na sequência"


_ACTIONS = {
    "send_email": _action_send_email,
    "send_whatsapp": _action_send_whatsapp,
    "create_task": _action_create_task,
    "assign_owner": _action_assign_owner,
    "enroll_sequence": _action_enroll_sequence,
}


def _render(tpl: str, entity: dict) -> str:
    """Interpola {{campo}} com valores do entity (simples)."""
    out = tpl or ""
    for k, v in (entity or {}).items():
        if isinstance(v, (str, int, float)):
            out = out.replace("{{" + k + "}}", str(v))
    return out


# ----------------------------------------------------------------------------
# 2) Workflows / automação
# ----------------------------------------------------------------------------
async def run_workflows_for_event(db: AsyncSession, trigger_event: str, entity: dict, entity_type: str = "lead") -> int:
    """Roda os workflows ativos de um evento. Retorna quantos dispararam. Best-effort."""
    fired = 0
    try:
        wfs = (
            (
                await db.execute(
                    text(
                        "SELECT id, conditions, actions FROM crm_workflows WHERE is_active = true AND trigger_event = :e"
                    ),
                    {"e": trigger_event},
                )
            )
            .mappings()
            .all()
        )
        for wf in wfs:
            if not eval_conditions(entity, list(wf["conditions"] or [])):
                continue
            results = []
            for action in wf["actions"] or []:
                fn = _ACTIONS.get(action.get("type"))
                if not fn:
                    results.append({"type": action.get("type"), "result": "ação desconhecida"})
                    continue
                try:
                    res = await fn(db, entity, action.get("params", {}))
                except Exception as exc:  # noqa: BLE001
                    res = f"erro: {exc}"
                results.append({"type": action.get("type"), "result": res})
            await _log_workflow_run(db, wf["id"], entity_type, entity.get("id"), results)
            await db.execute(
                text("UPDATE crm_workflows SET run_count = run_count + 1, last_run_at = now() WHERE id = :id"),
                {"id": wf["id"]},
            )
            await db.commit()
            fired += 1
    except Exception as exc:  # noqa: BLE001
        logger.warning("run_workflows_for_event(%s) falhou: %s", trigger_event, exc)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
    return fired


async def _log_workflow_run(db, workflow_id, entity_type, entity_id, results):
    import json
    from uuid import uuid4

    try:
        await db.execute(
            text("""
            INSERT INTO crm_workflow_runs (id, workflow_id, entity_type, entity_id, status, detail, created_at)
            VALUES (:id, :wid, :et, :eid, 'ok', CAST(:detail AS jsonb), now())
        """),
            {
                "id": str(uuid4()),
                "wid": workflow_id,
                "et": entity_type,
                "eid": entity_id,
                "detail": json.dumps(results),
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("log_workflow_run ignorado: %s", exc)


# ----------------------------------------------------------------------------
# 1) Sequências/cadências
# ----------------------------------------------------------------------------
def _first_delay(steps: list) -> int:
    return int((steps[0] or {}).get("delay_days", 0)) if steps else 0


async def enroll_lead(db: AsyncSession, sequence: dict, lead_id: str) -> str | None:
    """Inscreve um lead numa sequência (idempotente: não duplica enrollment ativo)."""
    from uuid import uuid4

    try:
        dup = (
            await db.execute(
                text("SELECT id FROM crm_sequence_enrollments WHERE sequence_id=:s AND lead_id=:l AND status='active'"),
                {"s": sequence["id"], "l": lead_id},
            )
        ).first()
        if dup:
            return str(dup[0])
        steps = sequence.get("steps") or []
        delay = _first_delay(steps)
        eid = str(uuid4())
        await db.execute(
            text("""
            INSERT INTO crm_sequence_enrollments
                (id, sequence_id, lead_id, current_step, status, enrolled_at, next_run_at, created_at, updated_at)
            VALUES (:id, :s, :l, 0, 'active', now(), now() + make_interval(days => CAST(:d AS integer)), now(), now())
        """),
            {"id": eid, "s": sequence["id"], "l": lead_id, "d": delay},
        )
        await db.commit()
        return eid
    except Exception as exc:  # noqa: BLE001
        logger.warning("enroll_lead falhou: %s", exc)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None


async def process_due_enrollments(db: AsyncSession, limit: int = 100) -> dict:
    """Processa enrollments com next_run_at vencido: envia o passo atual e agenda o próximo.
    Retorna {processed, completed, sent}."""
    processed = completed = sent = 0
    try:
        rows = (
            (
                await db.execute(
                    text("""
            SELECT e.id, e.sequence_id, e.lead_id, e.current_step, s.steps, s.channel
            FROM crm_sequence_enrollments e JOIN crm_sequences s ON s.id = e.sequence_id
            WHERE e.status = 'active' AND e.next_run_at <= now() AND s.is_active = true
            ORDER BY e.next_run_at LIMIT :lim
        """),
                    {"lim": limit},
                )
            )
            .mappings()
            .all()
        )
        for e in rows:
            processed += 1
            steps = e["steps"] or []
            idx = e["current_step"]
            if idx >= len(steps):
                await db.execute(
                    text("UPDATE crm_sequence_enrollments SET status='completed', updated_at=now() WHERE id=:id"),
                    {"id": e["id"]},
                )
                completed += 1
                continue
            step = steps[idx] or {}
            lead = (
                (await db.execute(text("SELECT id, name, email, phone FROM leads WHERE id=:l"), {"l": e["lead_id"]}))
                .mappings()
                .first()
            )
            if lead:
                ch = step.get("channel") or e["channel"] or "email"
                params = {"subject": step.get("subject"), "body": step.get("body"), "message": step.get("body")}
                try:
                    if ch == "whatsapp":
                        await _action_send_whatsapp(db, dict(lead), params)
                    else:
                        await _action_send_email(db, dict(lead), params)
                    sent += 1
                except Exception as exc:  # noqa: BLE001
                    logger.info("envio passo seq falhou: %s", exc)
            nxt = idx + 1
            if nxt >= len(steps):
                await db.execute(
                    text("""
                    UPDATE crm_sequence_enrollments
                    SET status='completed', current_step=:n, last_step_at=now(), updated_at=now() WHERE id=:id
                """),
                    {"n": nxt, "id": e["id"]},
                )
                completed += 1
            else:
                delay = int((steps[nxt] or {}).get("delay_days", 1))
                await db.execute(
                    text("""
                    UPDATE crm_sequence_enrollments
                    SET current_step=:n, last_step_at=now(),
                        next_run_at=now() + make_interval(days => CAST(:d AS integer)), updated_at=now()
                    WHERE id=:id
                """),
                    {"n": nxt, "d": delay, "id": e["id"]},
                )
            await db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("process_due_enrollments falhou: %s", exc)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
    return {"processed": processed, "completed": completed, "sent": sent}


# ----------------------------------------------------------------------------
# 6) Segmentação dinâmica — constrói WHERE seguro a partir dos filtros
# ----------------------------------------------------------------------------
_SEGMENT_FIELDS = {
    "lead": {
        "table": "leads",
        "fields": {
            "name",
            "email",
            "phone",
            "company",
            "position",
            "source",
            "status",
            "industry",
            "score",
            "expected_value",
            "assigned_to_id",
            "created_at",
        },
        "select": "id, name, email, phone, company, source, status, score",
    },
    "opportunity": {
        "table": "opportunities",
        "fields": {"title", "stage", "value", "probability", "company_name", "created_at"},
        "select": "id, title, stage, value, probability, company_name",
    },
    "client": {
        "table": "clients",
        "fields": {"name", "document_number", "email", "phone", "mrr", "ativo", "created_at"},
        "select": "id, code, name, document_number, mrr",
    },
}
_SEG_OPS = {"eq": "=", "ne": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<=", "contains": "ILIKE"}


def build_segment_sql(entity: str, filters: list) -> tuple[str, dict] | None:
    """Monta SELECT seguro p/ um segmento. Só campos whitelisted. Retorna (sql, params) ou None."""
    cfg = _SEGMENT_FIELDS.get(entity)
    if not cfg:
        return None
    where, params = [], {}
    for i, f in enumerate(filters or []):
        field = f.get("field")
        if field not in cfg["fields"]:
            continue
        op = (f.get("operator") or "eq").lower()
        pkey = f"p{i}"
        if op in ("empty", "is_empty"):
            where.append(f"({field} IS NULL OR {field}::text = '')")
        elif op in ("not_empty", "exists"):
            where.append(f"({field} IS NOT NULL AND {field}::text <> '')")
        elif op == "days_since_gt":
            # ex.: created_at há mais de N dias
            where.append(f"{field} < now() - (:%s || ' days')::interval" % pkey)
            params[pkey] = str(f.get("value", 0))
        elif op in _SEG_OPS:
            sqlop = _SEG_OPS[op]
            val = f"%{f.get('value')}%" if op == "contains" else f.get("value")
            where.append(f"{field} {sqlop} :{pkey}")
            params[pkey] = val
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    sql = f"SELECT {cfg['select']} FROM {cfg['table']}{clause} ORDER BY created_at DESC LIMIT 500"
    return sql, params
