"""
Controller standalone para auto-assemble de kits documentais.

Isolado do aggregator para evitar import circular via people_management.__init__.
Registrado diretamente no main_production.py.
"""

import logging
from datetime import UTC, date
from typing import Any
from uuid import UUID  # [GED] tipar kit_id -> /kits/dashboard 500 (uuid cast) vira 422

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["GED - Auto-Assemble"])


@router.post("/auto-assemble", status_code=201)
async def auto_assemble_kits(
    reference_month: date | None = Query(None, description="Mes de referencia (default: mes atual)"),
    current_user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Monta kits automaticamente para todos os clientes ativos.

    Coleta documentos de DP, Fiscal e Operacoes automaticamente
    para cada cliente que tem funcionarios alocados.
    """
    from modules.people_management.ged.services.kit_builder_service import KitBuilderService

    ref = reference_month or date.today().replace(day=1)
    builder = KitBuilderService(db)
    try:
        result = await builder.auto_build_all_kits(ref)
        await db.commit()
        return result
    except Exception as e:
        logger.error("Erro no auto-assemble: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/kits")
@router.get("/kits/", include_in_schema=False)
async def list_kits(
    client_id: str | None = Query(None),
    status: str | None = Query(None),
    month: int | None = Query(None, ge=1, le=12),
    year: int | None = Query(None, ge=2020),
    reference_month: str | None = Query(None, description="YYYY-MM formato do filtro frontend"),
    current_user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Lista kits documentais com filtros."""
    from sqlalchemy import text

    conditions = []
    params: dict[str, Any] = {}

    if client_id:
        conditions.append("gk.client_id = :client_id")
        params["client_id"] = client_id
    if status:
        conditions.append("gk.status = :status")
        params["status"] = status

    # Aceitar tanto month+year quanto reference_month (YYYY-MM)
    if reference_month and len(reference_month) >= 7:
        try:
            parts = reference_month.split("-")
            _year = int(parts[0])
            _month = int(parts[1])
            conditions.append("EXTRACT(MONTH FROM gk.reference_month) = :month")
            conditions.append("EXTRACT(YEAR FROM gk.reference_month) = :year")
            params["month"] = _month
            params["year"] = _year
        except (ValueError, IndexError):
            pass
    elif month and year:
        conditions.append("EXTRACT(MONTH FROM gk.reference_month) = :month")
        conditions.append("EXTRACT(YEAR FROM gk.reference_month) = :year")
        params["month"] = month
        params["year"] = year

    where = " AND ".join(conditions) if conditions else "1=1"
    # Subqueries contam documentos reais de ged_kit_documents (fonte de verdade)
    # Fallback para coluna stored quando ged_kit_documents estiver vazio mas stored > 0
    query = text(
        "SELECT gk.*, gc.name as client_name, "
        "  GREATEST("
        "    (SELECT COUNT(*) FROM ged_kit_documents gkd WHERE gkd.kit_id = gk.id),"
        "    COALESCE(gk.total_documents, 0)"
        "  ) as real_total_documents, "
        "  GREATEST("
        "    (SELECT COUNT(*) FROM ged_kit_documents gkd WHERE gkd.kit_id = gk.id AND gkd.is_signed = true),"
        "    COALESCE(gk.documents_signed, 0)"
        "  ) as real_documents_signed "
        "FROM ged_document_kits gk "
        "LEFT JOIN ged_clients gc ON gk.client_id = gc.id "
        "WHERE " + where + " ORDER BY gk.reference_month DESC, gk.created_at DESC LIMIT 50"
    )
    result = await db.execute(query, params)
    rows = result.mappings().all()
    return {
        "total": len(rows),
        "items": [
            {
                "id": str(r["id"]),
                "client_id": str(r["client_id"]) if r["client_id"] else None,
                "client_name": r.get("client_name") or None,
                "reference_month": r["reference_month"].isoformat() if r["reference_month"] else None,
                "status": r["status"],
                "total_employees": r["total_employees"],
                "total_documents": int(r["real_total_documents"] or 0),
                "documents_signed": int(r["real_documents_signed"] or 0),
                "completion_percentage": (
                    round(int(r["real_documents_signed"] or 0) / int(r["real_total_documents"]) * 100)
                    if int(r["real_total_documents"] or 0) > 0
                    else float(r["completion_percentage"])
                    if r["completion_percentage"]
                    else 0
                ),
                "sent_at": r["sent_at"].isoformat() if r["sent_at"] else None,
                "sent_method": r["sent_method"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ],
    }


@router.get("/kits/summary")
async def kits_summary(
    current_user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Resumo dos kits do mês atual."""
    from sqlalchemy import text

    latest_result = await db.execute(text("SELECT MAX(reference_month) FROM ged_document_kits"))
    latest_month = latest_result.scalar()
    if not latest_month:
        return {
            "total_kits": 0,
            "kits_pending_send": 0,
            "kits_pending_approval": 0,
            "average_completion": 0,
        }
    result = await db.execute(
        text("""
        SELECT
            COUNT(*) as total_kits,
            COUNT(*) FILTER (WHERE status = 'em_montagem') as kits_pending_send,
            COUNT(*) FILTER (WHERE status IN ('enviado','aprovado')) as kits_pending_approval,
            COALESCE(AVG(completion_percentage), 0) as average_completion
        FROM ged_document_kits
        WHERE DATE_TRUNC('month', reference_month) = DATE_TRUNC('month', CAST(:latest_month AS date))
        """),
        {"latest_month": latest_month},
    )
    r = result.mappings().first()
    return {
        "total_kits": r["total_kits"] if r else 0,
        "kits_pending_send": r["kits_pending_send"] if r else 0,
        "kits_pending_approval": r["kits_pending_approval"] if r else 0,
        "average_completion": round(float(r["average_completion"]), 1) if r else 0,
    }


@router.get("/kits/{kit_id}")
async def get_kit_detail(
    kit_id: UUID,
    current_user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna detalhes de um kit documental."""
    from sqlalchemy import text

    result = await db.execute(
        text("""
        SELECT gk.*, gc.name as client_name
        FROM ged_document_kits gk
        LEFT JOIN ged_clients gc ON gk.client_id = gc.id
        WHERE gk.id = :kit_id
        """),
        {"kit_id": kit_id},
    )
    r = result.mappings().first()
    if not r:
        raise HTTPException(status_code=404, detail="Kit nao encontrado")

    # Buscar documentos do kit com nome do funcionario
    docs_result = await db.execute(
        text("""
        SELECT gkd.id, gkd.employee_id, gkd.document_type, gkd.document_name,
               gkd.file_path, gkd.is_signed, gkd.source_module, gkd.created_at,
               e.nome as employee_name
        FROM ged_kit_documents gkd
        LEFT JOIN employees e ON e.id = gkd.employee_id
        WHERE gkd.kit_id = :kit_id
        ORDER BY e.nome NULLS LAST, gkd.document_type, gkd.created_at
        """),
        {"kit_id": kit_id},
    )
    docs = docs_result.mappings().all()

    return {
        "id": str(r["id"]),
        "client_id": str(r["client_id"]) if r["client_id"] else None,
        "client_name": r.get("client_name"),
        "reference_month": r["reference_month"].isoformat() if r["reference_month"] else None,
        "status": r["status"],
        "total_employees": r["total_employees"],
        "total_documents": r["total_documents"],
        "documents_signed": r["documents_signed"],
        "completion_percentage": float(r["completion_percentage"]) if r["completion_percentage"] else 0,
        "sent_at": r["sent_at"].isoformat() if r["sent_at"] else None,
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        "documents": [
            {
                "id": str(d["id"]),
                "document_type": d["document_type"],
                "name": d["document_name"],
                "file_path": d["file_path"],
                "signed": d["is_signed"],
                "origin": d["source_module"],
                "category": "employee" if d["employee_id"] is not None else "company",
                "employee_name": d["employee_name"],
                "created_at": d["created_at"].isoformat() if d["created_at"] else None,
            }
            for d in docs
        ],
    }


@router.post("/kits", status_code=201)
async def create_kit(
    data: dict[str, Any],
    current_user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Cria um novo kit documental."""
    import uuid

    from sqlalchemy import text

    client_id = data.get("client_id")
    reference_month_str = data.get("reference_month")

    if not client_id:
        raise HTTPException(status_code=422, detail="client_id obrigatorio")
    if not reference_month_str:
        raise HTTPException(status_code=422, detail="reference_month obrigatorio (YYYY-MM-DD)")

    # Converter string para date
    try:
        ref_date = date.fromisoformat(reference_month_str[:10])
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="reference_month formato invalido (YYYY-MM-DD)")

    # Verificar duplicata
    existing = await db.execute(
        text("SELECT id FROM ged_document_kits WHERE client_id = :cid AND reference_month = :rm"),
        {"cid": client_id, "rm": ref_date},
    )
    if existing.first():
        raise HTTPException(status_code=409, detail="Kit ja existe para este cliente/mes")

    kit_id = str(uuid.uuid4())
    await db.execute(
        text("""
        INSERT INTO ged_document_kits (id, client_id, reference_month, status,
            total_employees, total_documents, documents_signed, completion_percentage,
            created_at, updated_at)
        VALUES (:id, :cid, :rm, 'em_montagem', 0, 0, 0, 0, NOW(), NOW())
        """),
        {"id": kit_id, "cid": client_id, "rm": ref_date},
    )
    await db.commit()

    return {"id": kit_id, "client_id": client_id, "reference_month": ref_date.isoformat(), "status": "em_montagem"}


@router.post("/kits/{kit_id}/send", status_code=201)
async def send_kit(
    kit_id: str,
    current_user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Envia kit ao cliente (muda status para 'enviado')."""
    import uuid

    from sqlalchemy import text

    try:
        uuid.UUID(kit_id)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_UUID", "message": f"ID de kit inválido: '{kit_id}'"},
        )

    result = await db.execute(
        text("SELECT id, status FROM ged_document_kits WHERE id = :id"),
        {"id": kit_id},
    )
    kit = result.mappings().first()
    if not kit:
        raise HTTPException(status_code=404, detail="Kit nao encontrado")

    await db.execute(
        text("UPDATE ged_document_kits SET status = 'enviado', sent_at = NOW(), updated_at = NOW() WHERE id = :id"),
        {"id": kit_id},
    )
    await db.commit()
    return {"success": True, "kit_id": kit_id, "novo_status": "enviado"}


@router.post("/kits/{kit_id}/enviar")
async def enviar_kit(
    kit_id: str,
    current_user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Envia kit via GDrive + Email (atômico).

    Fluxo: GDrive primeiro → email só se GDrive OK.
    Valida completion_percentage = 100 antes de enviar.
    Grava sent_at, sent_method='email+gdrive', sent_to, status='enviado'.

    Returns:
        {sucesso, email_enviado, drive_link, sent_at, kit_id, documentos_drive}
    """
    import uuid
    from datetime import datetime

    from sqlalchemy import select, text

    try:
        uuid.UUID(kit_id)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_UUID", "message": f"ID de kit inválido: '{kit_id}'"},
        )

    from modules.gdrive.services.email_kit_service import email_kit_service as _email_svc
    from modules.people_management.ged.models.client import GedClient
    from modules.people_management.ged.models.document_kit import GedDocumentKit
    from modules.people_management.ged.services.google_drive_service import GoogleDriveService

    # 1. Buscar kit
    kit_result = await db.execute(select(GedDocumentKit).where(GedDocumentKit.id == kit_id))
    kit = kit_result.scalar_one_or_none()
    if not kit:
        raise HTTPException(status_code=404, detail="Kit não encontrado")

    # 2. Validar completude (INV-5)
    pct = float(kit.completion_percentage or 0)
    if pct < 100:
        raise HTTPException(
            status_code=400,
            detail=f"Kit incompleto. Completude atual: {pct:.1f}%. Só é possível enviar kits com 100% de documentos.",
        )

    # 3. Buscar cliente e validar email
    client_result = await db.execute(select(GedClient).where(GedClient.id == kit.client_id))
    client = client_result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    if not client.contact_email:
        raise HTTPException(status_code=422, detail="Cliente não possui email cadastrado em ged_clients")

    # 4. GDrive (atômico: se falhar, não envia email)
    drive_svc = GoogleDriveService(db)
    try:
        sync = await drive_svc.sync_kit_to_drive(str(kit.id))
    except Exception as exc:
        logger.error("Falha GDrive ao enviar kit %s: %s", kit_id, exc)
        raise HTTPException(status_code=502, detail=f"Falha GDrive: {str(exc)}")

    if not sync.get("configured"):
        raise HTTPException(
            status_code=502,
            detail=f"GDrive não configurado: {sync.get('message', 'Google Drive não conectado')}",
        )

    drive_link = sync.get("drive_link") or getattr(kit, "google_drive_link", None)

    # 5. Email (só se GDrive OK)
    competencia = kit.reference_month.strftime("%Y-%m") if kit.reference_month else ""
    resultado_email = _email_svc.enviar_kit_por_email(
        client_id=str(kit.client_id),
        competencia=competencia,
        share_link=drive_link,
        destinatario_override=client.contact_email,
    )

    if not resultado_email.get("sucesso"):
        raise HTTPException(
            status_code=502,
            detail=f"Drive OK mas email falhou: {resultado_email.get('erro', 'Falha no envio')}",
        )

    # 6. Gravar sent_at, sent_method='email+gdrive', sent_to, status='enviado'
    now_utc = datetime.now(UTC)
    await db.execute(
        text(
            "UPDATE ged_document_kits "
            "SET sent_at = :now, sent_method = 'email+gdrive', sent_to = :email, "
            "    status = 'enviado', updated_at = NOW() "
            "WHERE id = :kit_id"
        ),
        {"kit_id": kit_id, "email": client.contact_email, "now": now_utc},
    )
    await db.commit()

    logger.info("Kit %s enviado via email+gdrive para %s (%s)", kit_id, client.name, client.contact_email)

    return {
        "sucesso": True,
        "email_enviado": client.contact_email,
        "drive_link": drive_link,
        "sent_at": now_utc.isoformat(),
        "kit_id": kit_id,
        "documentos_drive": sync.get("uploaded", 0),
    }


@router.post("/kits/{kit_id}/approve", status_code=201)
async def approve_kit(
    kit_id: str,
    current_user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Aprova kit (muda status para 'aprovado')."""
    import uuid

    from sqlalchemy import text

    try:
        uuid.UUID(kit_id)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_UUID", "message": f"ID de kit inválido: '{kit_id}'"},
        )

    result = await db.execute(
        text("SELECT id, status FROM ged_document_kits WHERE id = :id"),
        {"id": kit_id},
    )
    kit = result.mappings().first()
    if not kit:
        raise HTTPException(status_code=404, detail="Kit nao encontrado")

    await db.execute(
        text(
            "UPDATE ged_document_kits SET status = 'aprovado', approved_at = NOW(), updated_at = NOW() WHERE id = :id"
        ),
        {"id": kit_id},
    )
    await db.commit()
    return {"success": True, "kit_id": kit_id, "novo_status": "aprovado"}


@router.post("/kits/montar", status_code=201)
async def montar_kits(
    current_user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Monta kits para todos os clientes ativos que nao tem kit no mes atual."""
    import uuid

    from sqlalchemy import text

    hoje = date.today()
    mes_ref = hoje.replace(day=1)

    result = await db.execute(
        text("""
        SELECT gc.id, gc.name
        FROM ged_clients gc
        WHERE gc.is_active = true
        AND gc.id NOT IN (
            SELECT client_id FROM ged_document_kits
            WHERE reference_month = :mes
        )
        """),
        {"mes": mes_ref},
    )
    clientes = result.mappings().all()

    criados = 0
    detalhes = []
    for c in clientes:
        kit_id = str(uuid.uuid4())
        await db.execute(
            text("""
            INSERT INTO ged_document_kits (id, client_id, reference_month, status,
                total_employees, total_documents, documents_signed, completion_percentage,
                created_at, updated_at)
            VALUES (:id, :cid, :mes, 'em_montagem', 0, 0, 0, 0, NOW(), NOW())
            """),
            {"id": kit_id, "cid": str(c["id"]), "mes": mes_ref},
        )
        criados += 1
        detalhes.append({"kit_id": kit_id, "client": c["name"]})

    await db.commit()
    return {"kits_criados": criados, "detalhes": detalhes}


@router.get("/dashboard")
async def ged_dashboard(
    current_user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Dashboard consolidado do GED com metricas operacionais."""
    from sqlalchemy import text

    # Total de documentos por status
    docs_result = await db.execute(
        text("""
        SELECT
            count(*) as total,
            count(*) FILTER (WHERE status = 'ativo' OR status = 'rascunho') as ativos,
            count(*) FILTER (WHERE status = 'assinado') as assinados,
            count(*) FILTER (WHERE status = 'expirado') as expirados
        FROM ged_documents
    """)
    )
    docs = docs_result.mappings().first()

    # Kits do mes atual
    kits_result = await db.execute(
        text("""
        SELECT
            count(*) as total,
            count(*) FILTER (WHERE status = 'EM_MONTAGEM') as em_montagem,
            count(*) FILTER (WHERE status = 'COMPLETO') as completos,
            count(*) FILTER (WHERE status = 'ENVIADO') as enviados,
            count(*) FILTER (WHERE status = 'APROVADO') as aprovados,
            COALESCE(AVG(completion_percentage), 0) as media_completude
        FROM ged_document_kits
        WHERE EXTRACT(MONTH FROM reference_month) = EXTRACT(MONTH FROM CURRENT_DATE)
          AND EXTRACT(YEAR FROM reference_month) = EXTRACT(YEAR FROM CURRENT_DATE)
    """)
    )
    kits = kits_result.mappings().first()

    # Pastas
    folders_result = await db.execute(
        text("""
        SELECT count(*) as total FROM ged_folders WHERE status = 'ativa'
    """)
    )
    folders = folders_result.mappings().first()

    # Tags
    tags_result = await db.execute(
        text("""
        SELECT count(*) as total FROM ged_document_tags WHERE is_active = true
    """)
    )
    tags = tags_result.mappings().first()

    # Clientes GED
    clients_result = await db.execute(
        text("""
        SELECT
            count(*) as total,
            count(*) FILTER (WHERE portal_access_enabled = true) as com_portal
        FROM ged_clients
    """)
    )
    clients = clients_result.mappings().first()

    return {
        "documentos": {
            "total": docs["total"] if docs else 0,
            "ativos": docs["ativos"] if docs else 0,
            "assinados": docs["assinados"] if docs else 0,
            "expirados": docs["expirados"] if docs else 0,
        },
        "kits_mes_atual": {
            "total": kits["total"] if kits else 0,
            "em_montagem": kits["em_montagem"] if kits else 0,
            "completos": kits["completos"] if kits else 0,
            "enviados": kits["enviados"] if kits else 0,
            "aprovados": kits["aprovados"] if kits else 0,
            "media_completude": round(float(kits["media_completude"]), 1) if kits else 0,
        },
        "pastas": folders["total"] if folders else 0,
        "tags": tags["total"] if tags else 0,
        "clientes": {
            "total": clients["total"] if clients else 0,
            "com_portal": clients["com_portal"] if clients else 0,
        },
    }
