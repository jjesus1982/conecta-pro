"""
Controller de Kits Documentais — endpoints REST.

Gerencia o ciclo de vida dos kits documentais mensais:
criacao, montagem automatica, envio, aprovacao e exportacao.
"""

import logging
import os
from datetime import UTC, date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.people_management.ged.schemas.kit import (
    KitCreate,
    KitListResponse,
    KitResponse,
    KitSummary,
    KitUpdate,
)
from modules.people_management.ged.services.export_service import ExportService
from modules.people_management.ged.services.kit_builder_service import KitBuilderService
from modules.people_management.ged.services.kit_service import KitService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/kits", tags=["GED - Kits Documentais"])


class KitSendRequest(BaseModel):
    """Schema para marcar kit como enviado."""

    method: str = Field(..., description="Metodo de envio: email, google_drive, portal, impresso")
    sent_to: str | None = Field(None, max_length=500, description="Destinatario(s)")


class KitApproveRequest(BaseModel):
    """Schema para aprovar kit."""

    approved_by: str = Field(..., max_length=255, description="Nome de quem aprovou")


class KitBuildRequest(BaseModel):
    """Schema para solicitar montagem automatica de kit."""

    reference_month: date | None = Field(None, description="Mes de referencia (usa o do kit se nao informado)")


@router.get("", response_model=KitListResponse)
@router.get("", response_model=KitListResponse, include_in_schema=False)
async def list_kits(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    client_id: str | None = Query(None, description="Filtrar por cliente"),
    status: str | None = Query(None, description="Filtrar por status"),
    year: int | None = Query(None, ge=2020, le=2030, description="Filtrar por ano"),
    month: int | None = Query(None, ge=1, le=12, description="Filtrar por mes"),
    skip: int = Query(0, ge=0, description="Offset"),
    limit: int = Query(20, ge=1, le=100, description="Limite"),
) -> Any:
    """Lista kits documentais com filtros e paginacao."""
    service = KitService(db)
    return await service.list_kits(
        client_id=client_id,
        status=status,
        year=year,
        month=month,
        skip=skip,
        limit=limit,
    )


@router.get("/summary", response_model=KitSummary)
async def get_kit_summary(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    year: int | None = Query(None, ge=2020, le=2030, description="Ano de referencia"),
    month: int | None = Query(None, ge=1, le=12, description="Mes de referencia"),
) -> Any:
    """Retorna resumo geral dos kits para dashboard."""
    service = KitService(db)
    reference_month = None
    if year and month:
        reference_month = date(year, month, 1)
    return await service.get_kit_summary(reference_month=reference_month)


@router.get("/dashboard")
async def get_kit_dashboard(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    year: int | None = Query(None, ge=2020, le=2030),
    month: int | None = Query(None, ge=1, le=12),
) -> Any:
    """Dashboard completo dos kits documentais.

    Retorna resumo + proxima geracao + clientes sem kit.
    """
    from datetime import datetime

    from modules.people_management.ged.models.client import GedClient
    from modules.people_management.ged.models.document_kit import GedDocumentKit

    now = datetime.now()
    ref_year = year or now.year
    ref_month = month or now.month
    ref_date = date(ref_year, ref_month, 1)

    # Summary basico
    service = KitService(db)
    summary = await service.get_kit_summary(reference_month=ref_date)

    # Proxima geracao (dia 1 do proximo mes as 02:00)
    if ref_month == 12:
        next_month = date(ref_year + 1, 1, 1)
    else:
        next_month = date(ref_year, ref_month + 1, 1)
    proxima_geracao = f"{next_month.isoformat()}T02:00:00"

    # Clientes sem kit neste mes
    from sqlalchemy import select

    all_clients_q = select(GedClient.id, GedClient.name)
    all_clients = (await db.execute(all_clients_q)).all()

    clients_with_kit_q = select(GedDocumentKit.client_id).where(GedDocumentKit.reference_month == ref_date).distinct()
    clients_with_kit = {row[0] for row in (await db.execute(clients_with_kit_q)).all()}

    clientes_sem_kit = [{"id": str(cid), "name": cname} for cid, cname in all_clients if cid not in clients_with_kit]

    # Scheduler status
    try:
        from modules.document_kits import scheduler as kit_scheduler

        sched_status = kit_scheduler.get_scheduler_status()
    except Exception:
        sched_status = {"running": False, "message": "Scheduler indisponivel"}

    return {
        "reference_month": ref_date.isoformat(),
        "summary": summary,
        "proxima_geracao": proxima_geracao,
        "scheduler": sched_status,
        "clientes_sem_kit": clientes_sem_kit,
        "total_clientes_sem_kit": len(clientes_sem_kit),
    }


@router.post("", response_model=KitResponse, status_code=201)
async def create_kit(
    data: KitCreate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Cria um novo kit documental para um cliente/mes."""
    service = KitService(db)
    try:
        result = await service.create_kit(data)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{kit_id}", response_model=KitResponse)
async def get_kit(
    kit_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna detalhes de um kit com resumo de documentos."""
    service = KitService(db)
    try:
        return await service.get_kit(kit_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{kit_id}", response_model=KitResponse)
async def update_kit(
    kit_id: str,
    data: KitUpdate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Atualiza campos editaveis de um kit."""
    service = KitService(db)
    try:
        result = await service.update_kit(kit_id, data)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{kit_id}")
async def delete_kit(
    kit_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Remove um kit. Somente permitido se status = EM_MONTAGEM."""
    service = KitService(db)
    try:
        result = await service.delete_kit(kit_id)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{kit_id}/build", status_code=201)
async def build_kit(
    kit_id: str,
    data: KitBuildRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Dispara montagem automatica do kit.

    Coleta documentos de DP, Fiscal e Operacoes automaticamente.
    """
    kit_service = KitService(db)
    try:
        kit_resp = await kit_service.get_kit(kit_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    builder = KitBuilderService(db)
    try:
        ref_month = data.reference_month or kit_resp.reference_month
        result = await builder.build_kit_for_client(
            client_id=kit_resp.client_id,
            reference_month=ref_month,
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


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
    ref = reference_month or date.today().replace(day=1)
    builder = KitBuilderService(db)
    try:
        result = await builder.auto_build_all_kits(ref)
        await db.commit()
        return result
    except Exception as e:
        logger.error(f"Erro no auto-assemble: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{kit_id}/send", response_model=KitResponse, status_code=201)
async def send_kit(
    kit_id: str,
    data: KitSendRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Marca o kit como enviado com metodo e destinatario."""
    service = KitService(db)
    try:
        result = await service.mark_kit_sent(
            kit_id=kit_id,
            method=data.method,
            sent_to=data.sent_to,
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{kit_id}/send-email", status_code=201)
async def send_kit_email(
    kit_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Envia kit por email para o cliente via EmailKitService (HTML + link Drive).

    Valida completude (100%) antes de enviar. Marca kit como enviado se bem-sucedido.
    """
    from sqlalchemy import func, select

    from modules.people_management.ged.models.client import GedClient
    from modules.people_management.ged.models.document_kit import GedDocumentKit
    from modules.people_management.ged.models.kit_document import KitDocument

    # G3: buscar kit diretamente em ged_document_kits
    kit_result = await db.execute(select(GedDocumentKit).where(GedDocumentKit.id == kit_id))
    kit = kit_result.scalars().first()
    if not kit:
        raise HTTPException(status_code=404, detail="Kit nao encontrado")

    # INV-5: envio bloqueado se completude AO VIVO < 100
    # (COUNT real em ged_kit_documents; a coluna stored fica stale)
    _total = (
        await db.scalar(select(func.count()).select_from(KitDocument).where(KitDocument.kit_id == str(kit.id)))
    ) or 0
    _signed = (
        await db.scalar(
            select(func.count())
            .select_from(KitDocument)
            .where(KitDocument.kit_id == str(kit.id), KitDocument.is_signed.is_(True))
        )
    ) or 0
    pct = (_signed / _total) * 100 if _total else 0.0
    if pct < 100:
        raise HTTPException(
            status_code=400,
            detail=f"Kit incompleto. Completude atual: {pct:.1f}%. So e possivel enviar kits com 100% de documentos.",
        )

    # Buscar cliente para validar email cadastrado
    client_result = await db.execute(select(GedClient).where(GedClient.id == kit.client_id))
    client = client_result.scalars().first()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente nao encontrado")

    if not client.contact_email:
        return {
            "status": "sem_email",
            "kit_id": kit_id,
            "client_name": client.name,
            "message": "Cliente nao possui email cadastrado em ged_clients",
        }

    # G4: delegar para EmailKitService (HTML #1E3A5F + link Drive)
    competencia = kit.reference_month.strftime("%Y-%m") if kit.reference_month else ""
    from modules.gdrive.services.email_kit_service import email_kit_service as _email_svc

    resultado = _email_svc.enviar_kit_por_email(
        client_id=str(kit.client_id),
        competencia=competencia,
        destinatario_override=client.contact_email,
    )

    if resultado.get("sucesso"):
        service = KitService(db)
        await service.mark_kit_sent(
            kit_id=kit_id,
            method="email",
            sent_to=client.contact_email,
        )
        await db.commit()
        logger.info("Kit %s enviado por email para %s (%s)", kit_id, client.name, client.contact_email)
        return {
            "status": "enviado",
            "kit_id": kit_id,
            "client_name": client.name,
            "email": client.contact_email,
            "total_docs": resultado.get("total_docs", 0),
            "estrategia": resultado.get("estrategia", "email"),
        }

    return {
        "status": "erro",
        "kit_id": kit_id,
        "client_name": client.name,
        "email": client.contact_email,
        "error": resultado.get("erro", "Falha no envio"),
    }


@router.post("/{kit_id}/enviar")
async def enviar_kit(
    kit_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Envia kit via GDrive + Email (atômico).

    Fluxo: GDrive primeiro → email só se GDrive OK.
    Valida completion_percentage = 100 antes de enviar.
    Grava sent_at, sent_method='email+gdrive', sent_to.

    Returns:
        {sucesso, email_enviado, drive_link, sent_at, kit_id, documentos_drive}
    """
    from datetime import datetime

    from sqlalchemy import func, select

    from modules.gdrive.services.email_kit_service import email_kit_service as _email_svc
    from modules.people_management.ged.models.client import GedClient
    from modules.people_management.ged.models.document_kit import GedDocumentKit
    from modules.people_management.ged.models.kit_document import KitDocument
    from modules.people_management.ged.services.google_drive_service import GoogleDriveService

    # 1. Buscar kit
    kit_result = await db.execute(select(GedDocumentKit).where(GedDocumentKit.id == kit_id))
    kit = kit_result.scalar_one_or_none()
    if not kit:
        raise HTTPException(status_code=404, detail="Kit não encontrado")

    # 2. Validar completude AO VIVO (INV-5)
    # (COUNT real em ged_kit_documents; a coluna stored fica stale)
    _total = (
        await db.scalar(select(func.count()).select_from(KitDocument).where(KitDocument.kit_id == str(kit.id)))
    ) or 0
    _signed = (
        await db.scalar(
            select(func.count())
            .select_from(KitDocument)
            .where(KitDocument.kit_id == str(kit.id), KitDocument.is_signed.is_(True))
        )
    ) or 0
    pct = (_signed / _total) * 100 if _total else 0.0
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
    kit.sent_at = now_utc
    kit.sent_method = "email+gdrive"
    kit.sent_to = client.contact_email
    kit.status = "enviado"
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


@router.post("/{kit_id}/approve", response_model=KitResponse, status_code=201)
async def approve_kit(
    kit_id: str,
    data: KitApproveRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Aprova o kit documental."""
    service = KitService(db)
    try:
        result = await service.approve_kit(
            kit_id=kit_id,
            approved_by=data.approved_by,
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{kit_id}/export/zip")
async def export_zip(
    kit_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Gera e retorna o ZIP do kit para download."""
    export_svc = ExportService(db)
    try:
        result = await export_svc.generate_zip(kit_id)
        await db.commit()

        zip_path = result["zip_path"]
        if not os.path.exists(zip_path):
            raise HTTPException(status_code=500, detail="Arquivo ZIP nao foi gerado corretamente")

        # Registrar log de acesso
        await export_svc.log_access(
            kit_id=kit_id,
            action="downloaded",
            actor_type="internal",
            actor_id=str(current_user.id),
            actor_name=getattr(current_user, "full_name", None) or str(current_user.id),
            ip=None,
            user_agent=None,
            notes="Download ZIP via API",
        )
        await db.commit()

        return FileResponse(
            path=zip_path,
            filename=result["zip_filename"],
            media_type="application/zip",
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{kit_id}/export/pdf")
async def export_pdf(
    kit_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Gera e retorna o PDF consolidado do kit para download."""
    export_svc = ExportService(db)
    try:
        result = await export_svc.generate_consolidated_pdf(kit_id)
        await db.commit()

        pdf_path = result["pdf_path"]
        if not os.path.exists(pdf_path):
            raise HTTPException(status_code=500, detail="Arquivo PDF nao foi gerado corretamente")

        # Detectar tipo MIME pelo arquivo gerado
        media_type = "application/pdf"
        if pdf_path.endswith(".txt"):
            media_type = "text/plain"

        await export_svc.log_access(
            kit_id=kit_id,
            action="downloaded",
            actor_type="internal",
            actor_id=str(current_user.id),
            actor_name=getattr(current_user, "full_name", None) or str(current_user.id),
            ip=None,
            user_agent=None,
            notes="Download PDF consolidado via API",
        )
        await db.commit()

        return FileResponse(
            path=pdf_path,
            filename=result["pdf_filename"],
            media_type=media_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
