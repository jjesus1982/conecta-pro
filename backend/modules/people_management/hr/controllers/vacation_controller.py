"""
Controller de Férias — Departamento Pessoal.

Re-exporta endpoints de férias do operacional e adiciona endpoints DP:
cálculo de saldo, detalhes e aprovação.
"""

import asyncio
import io
import logging
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import text as _sqltext
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.operacional.vacations.schemas import VacationRequestResponse
from modules.people_management.hr.publishers import publish_ferias_aprovadas
from modules.people_management.hr.services.vacation_service import VacationService

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/vacations", tags=["DP - Férias"])


# Mapa de sinônimos EN↔PT para o filtro de status (causa-raiz nº1: pt×EN).
# O banco grava PT minúsculo (aprovado/pendente/rejeitado/cancelado); telas/integrações
# antigas mandam EN maiúsculo (APPROVED/PENDING/...). Normaliza ANTES da query.
_VAC_STATUS_SYNONYMS = {
    "approved": "aprovado",
    "aprovado": "aprovado",
    "pending": "pendente",
    "pendente": "pendente",
    "rejected": "rejeitado",
    "rejeitado": "rejeitado",
    "cancelled": "cancelado",
    "canceled": "cancelado",
    "cancelado": "cancelado",
}


def _normalize_vacation_status(raw: str | None) -> str | None:
    """Normaliza o parâmetro ?status= para o vocabulário do banco (PT minúsculo),
    aceitando sinônimos EN↔PT e case-insensitive. Retorna None p/ 'todos'/vazio."""
    if not raw:
        return None
    key = str(raw).strip().lower()
    if key in ("", "todos", "all"):
        return None
    return _VAC_STATUS_SYNONYMS.get(key, key)


def _normalize_days(raw: Any) -> str | None:
    """[Achado 6] Normaliza o campo `days` para inteiro puro em string ('30').

    Dados legados foram gravados com sufixo ('30 dias', '15 dias'); a criação (POST) grava
    número puro. Aqui extraímos apenas o inteiro para exibição consistente na tela,
    independente do formato armazenado. Retorna None se não houver número.
    """
    if raw is None:
        return None
    import re as _re

    m = _re.search(r"\d+", str(raw))
    return m.group(0) if m else None

# FIX 2026-04-16: include_router(_vacation_ops_router) REMOVIDO.
# O ops router tem prefix="/vacations" — incluí-lo aqui gerava prefix duplo
# /hr/vacations/vacations/... Rotas DP definidas diretamente abaixo.


@router.get(
    "",
    summary="Listar Solicitações de Férias",
    description="Retorna lista paginada de solicitações de férias de todos os funcionários.",
)
async def list_vacations(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, description="Filtrar por status: pendente, aprovado, rejeitado, cancelado"),
) -> Any:
    """Lista solicitações de férias (FONTE DA VERDADE: hr_vacation_requests).

    O banco grava status EN maiúsculo (SUBMITTED/APPROVED/...); a tela e os cards
    trabalham em PT minúsculo. O mapa PT↔EN é aplicado ANTES do filtro e nos buckets.
    """
    try:
        from sqlalchemy import text as _text

        from modules.people_management.hr.services.vacation_service import (
            _HVR_BASE_SELECT,
            _hvr_row_to_ns,
            _hvr_status_to_pt,
        )

        # [Causa-raiz nº1] normaliza o filtro (?status=) para PT (bucket do front)
        norm_status = _normalize_vacation_status(status)

        # Contagem por status (buckets do banco → PT) para os CARDS — SEMPRE global,
        # independente do filtro, para o card não zerar ao filtrar.
        counts_rows = (
            await db.execute(_text("SELECT status, COUNT(*) FROM hr_vacation_requests GROUP BY status"))
        ).all()
        by_status: dict[str, int] = {}
        for raw_st, cnt in counts_rows:
            bucket = _hvr_status_to_pt(raw_st)
            by_status[bucket] = by_status.get(bucket, 0) + int(cnt or 0)
        total_all = sum(by_status.values())

        # Lista completa (filtro de status aplicado em PT, sobre o bucket mapeado)
        rows = (await db.execute(_text(_HVR_BASE_SELECT + " ORDER BY h.created_at DESC"))).fetchall()
        all_items = [_hvr_row_to_ns(r) for r in rows]
        if norm_status:
            all_items = [v for v in all_items if v.status == norm_status]

        total = len(all_items)
        page_items = all_items[(page - 1) * page_size : (page - 1) * page_size + page_size]

        return {
            "pendente": by_status.get("pendente", 0),
            "aprovado": by_status.get("aprovado", 0),
            "rejeitado": by_status.get("rejeitado", 0),
            "cancelado": by_status.get("cancelado", 0),
            "counts": by_status,
            "total_all": total_all,
            "items": [
                {
                    "id": str(v.id),
                    "employee_id": str(v.employee_id) if v.employee_id else None,
                    "employee_name": v.employee_name,
                    "type": v.type,
                    "status": v.status,
                    "start_date": str(v.start_date) if v.start_date else None,
                    "end_date": str(v.end_date) if v.end_date else None,
                    "days": _normalize_days(v.days),
                    "reason": v.reason,
                    "notes": v.notes,
                    "created_at": v.created_at.isoformat() if v.created_at else None,
                }
                for v in page_items
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        }
    except Exception:
        # NÃO mascarar como "0 pendentes" (obrigação legal escondida como all-clear).
        # Loga e propaga → 500 honesto ("não carregou" é melhor que "0 pendentes").
        logger.exception("list_vacations falhou — propagando erro em vez de retornar zeros")
        raise


@router.get(
    "/employee/{employee_id}",
    summary="Férias por Funcionário",
    response_model=None,
    description="Retorna lista paginada de solicitações de férias de todos os funcionários.",
)
async def list_vacations_by_employee(
    employee_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Any:
    """Lista solicitações de férias de um funcionário específico."""
    service = VacationService(db)
    result = await service.list_by_employee(employee_id, page=page, page_size=page_size)
    # Serialize items using the response schema
    serialized_items = []
    for item in result["items"]:
        try:
            serialized_items.append(VacationRequestResponse.model_validate(item).model_dump())
        except Exception:
            serialized_items.append(
                {
                    "id": str(item.id),
                    "employee_id": str(item.employee_id),
                    "employee_name": item.employee_name,
                    "type": item.type,
                    "status": item.status,
                    "start_date": str(item.start_date) if item.start_date else None,
                    "end_date": str(item.end_date) if item.end_date else None,
                    "days": _normalize_days(item.days),
                    "reason": item.reason,
                    "notes": item.notes,
                    "approved_by": str(item.approved_by) if item.approved_by else None,
                    "approved_at": item.approved_at.isoformat() if item.approved_at else None,
                    "rejected_reason": item.rejected_reason,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                    "updated_at": item.updated_at.isoformat() if item.updated_at else None,
                }
            )
    return {
        "items": serialized_items,
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
        "total_pages": result["total_pages"],
    }


@router.get(
    "/employee/{employee_id}/balance",
    summary="Saldo de Férias",
    description="Retorna lista paginada de solicitações de férias de todos os funcionários.",
)
async def get_vacation_balance(
    employee_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Calcula o saldo de férias do funcionário."""
    service = VacationService(db)
    try:
        return await service.calculate_vacation_balance(employee_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/{vacation_id}",
    summary="Buscar Solicitação de Férias",
    response_model=VacationRequestResponse,
    description="Retorna lista paginada de solicitações de férias de todos os funcionários.",
)
async def get_vacation(
    vacation_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna detalhes de uma solicitação de férias."""
    service = VacationService(db)
    vacation = await service.get_by_id(vacation_id)
    if not vacation:
        raise HTTPException(status_code=404, detail="Solicitação de férias não encontrada")
    return vacation


@router.post(
    "/sync-solides",
    summary="Sincronizar Férias do Sólides",
    status_code=201,
    description="Retorna lista paginada de solicitações de férias de todos os funcionários.",
)
async def sync_ferias_solides(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    periodo_inicio: str | None = Query(None, description="YYYY-MM-DD"),
    periodo_fim: str | None = Query(None, description="YYYY-MM-DD"),
) -> Any:
    """Sincroniza férias do Sólides Tangerino para o módulo de férias do DP."""
    service = VacationService(db)
    try:
        result = await service.sync_vacations_from_solides(
            periodo_inicio=periodo_inicio,
            periodo_fim=periodo_fim,
        )
        if result.get("success"):
            await db.commit()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/{vacation_id}/approve",
    summary="Aprovar Férias",
    status_code=201,
    description="Retorna lista paginada de solicitações de férias de todos os funcionários.",
)
async def approve_vacation(
    vacation_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Aprova uma solicitação de férias."""
    service = VacationService(db)
    try:
        result = await service.approve_vacation(vacation_id, approved_by_id=current_user.id)
        await db.commit()
        # [Item −1/A1] resolve cliente_id do funcionário (backfill) → GEDEON monta o kit certo
        _vac_emp = str(result.get("employee_id", "")) if isinstance(result, dict) else ""
        _vac_cli = (
            (
                await db.execute(
                    _sqltext("SELECT cliente_id FROM employees WHERE CAST(id AS TEXT)=:i"), {"i": _vac_emp}
                )
            ).scalar()
            if _vac_emp
            else None
        )
        asyncio.create_task(
            publish_ferias_aprovadas(
                funcionario_id=str(result.get("employee_id", vacation_id)) if isinstance(result, dict) else vacation_id,
                funcionario_nome=str(result.get("employee_name", "")) if isinstance(result, dict) else "",
                inicio=str(result.get("start_date", "")) if isinstance(result, dict) else "",
                fim=str(result.get("end_date", "")) if isinstance(result, dict) else "",
                aprovado_por=str(current_user.id),
                cliente_id=str(_vac_cli) if _vac_cli else None,
            )
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/{vacation_id}/aviso-previo",
    summary="Gerar Aviso Prévio de Férias (PDF)",
    description=(
        "Gera o Aviso Prévio de Férias em PDF via reportlab. Conforme art. 135 CLT e CCT SINDECOMPRESTS 2026."
    ),
)
async def gerar_aviso_previo_ferias(
    vacation_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Gera PDF do Aviso Prévio de Férias."""
    service = VacationService(db)
    vacation = await service.get_by_id(vacation_id)
    if not vacation:
        raise HTTPException(status_code=404, detail="Solicitação de férias não encontrada")

    employee_name = getattr(vacation, "employee_name", None) or "Funcionário"
    cargo = "Agente de Segurança"
    admission_date = "Não informada"

    try:
        from sqlalchemy import select as sa_select

        from modules.operacional.models.employee import Employee

        emp_result = await db.execute(sa_select(Employee).where(Employee.id == vacation.employee_id))
        emp = emp_result.scalar_one_or_none()
        if emp:
            employee_name = emp.nome or employee_name
            cargo = emp.cargo or cargo
            if emp.data_admissao:
                admission_date = emp.data_admissao.strftime("%d/%m/%Y")
    except Exception:
        pass

    start_date = getattr(vacation, "start_date", None)
    end_date = getattr(vacation, "end_date", None)
    days = getattr(vacation, "days", None)

    vacation_start = start_date.strftime("%d/%m/%Y") if start_date else "—"
    vacation_end = end_date.strftime("%d/%m/%Y") if end_date else "—"
    vacation_days = days or (str((end_date - start_date).days + 1) if start_date and end_date else "30")

    if start_date:
        period_end_dt = start_date - timedelta(days=1)
        period_start_dt = period_end_dt.replace(year=period_end_dt.year - 1) + timedelta(days=1)
        period_start = period_start_dt.strftime("%d/%m/%Y")
        period_end = period_end_dt.strftime("%d/%m/%Y")
    else:
        period_start = "—"
        period_end = "—"

    return_date = (end_date + timedelta(days=1)).strftime("%d/%m/%Y") if end_date else "—"
    notice_date = date.today().strftime("%d/%m/%Y")

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        from modules.crm.services import pdf_branding as B

        st = B.styles()
        body_style = st["corpo"]
        label_style = st["cell"]

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=16 * mm,
            leftMargin=16 * mm,
            topMargin=40 * mm,
            bottomMargin=16 * mm,
        )

        story = []
        story += B.secao("DADOS DO EMPREGADO", st)

        box_data = [
            [Paragraph(f"<b>Empregado(a):</b> {employee_name}", label_style)],
            [Paragraph(f"<b>Cargo:</b> {cargo}", label_style)],
            [Paragraph(f"<b>Data de Admissão:</b> {admission_date}", label_style)],
            [Paragraph(f"<b>Período Aquisitivo:</b> {period_start} a {period_end}", label_style)],
        ]
        box = Table(box_data, colWidths=[178 * mm])
        box.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.6, B.AZUL_ESCURO),
                    ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D9E1F2")),
                    ("BACKGROUND", (0, 0), (-1, -1), B.FUNDO_CLARO),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(box)
        story.append(Spacer(1, 5 * mm))

        story += B.secao("COMUNICADO", st)
        story.append(Paragraph(f"Prezado(a) <b>{employee_name}</b>,", body_style))
        story.append(
            Paragraph(
                f"Comunicamos que suas férias estão programadas para o período de "
                f"<b>{vacation_start}</b> a <b>{vacation_end}</b> "
                f"({vacation_days} dias), conforme artigo 135 da CLT e CCT SINDECOMPRESTS 2026.",
                body_style,
            )
        )
        story.append(
            Paragraph(
                "O pagamento das férias será efetuado com antecedência mínima de "
                "2 (dois) dias, conforme determina o artigo 145 da CLT.",
                body_style,
            )
        )
        story.append(Paragraph(f"Retorno previsto: <b>{return_date}</b>.", body_style))

        # Assinaturas (padrão-ouro: funcionário assina digital pelo Portal; empresa = CEO Jordan)
        story += B.campos_assinatura(
            st,
            funcionario_nome=employee_name,
            data_str=notice_date,
            digital_funcionario=True,
            digital_empresa=True,
            data_empresa=notice_date,
            espaco_antes=14,
        )

        doc.build(
            story,
            onFirstPage=lambda cv, dc: B.header_footer(cv, dc, titulo="AVISO DE FÉRIAS"),
            onLaterPages=lambda cv, dc: B.header_footer(cv, dc, titulo="AVISO DE FÉRIAS"),
        )
        pdf_bytes = buffer.getvalue()
        buffer.close()

        safe_name = employee_name.replace(" ", "_")[:30]
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="aviso_previo_ferias_{safe_name}_{vacation_id[:8]}.pdf"'
                ),
                "Cache-Control": "no-store",
            },
        )
    except ImportError:
        raise HTTPException(status_code=500, detail="reportlab não instalado")
    except Exception as exc:
        logger.error("Erro ao gerar aviso prévio férias %s: %s", vacation_id, exc)
        raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF: {exc}")


@router.post("", status_code=201, summary="Criar solicitação de férias")
@router.post("/", include_in_schema=False, status_code=201)
async def criar_vacation(data: dict, current_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)) -> Any:
    """Cria solicitação de férias na FONTE DA VERDADE (hr_vacation_requests).

    Gera request_code único por condomínio e preenche os campos NOT NULL exigidos
    (condominio_id, request_code, return_date, days_requested, status EN 'SUBMITTED').
    NUNCA perde uma solicitação: grava direto no superset canônico.
    """
    import uuid as _uuid
    from datetime import date as _date
    from datetime import timedelta as _td

    from modules.people_management.hr.services.vacation_service import (
        _HVR_DEFAULT_CONDOMINIO_ID,
    )

    emp = str(data.get("employee_id") or "").strip()
    if not emp:
        raise HTTPException(status_code=422, detail="employee_id é obrigatório")

    def _d(v):
        try:
            return _date.fromisoformat(str(v)[:10]) if v else None
        except Exception:  # noqa: BLE001
            return None

    sd, ed = _d(data.get("start_date")), _d(data.get("end_date"))
    if not sd or not ed:
        raise HTTPException(status_code=422, detail="start_date e end_date são obrigatórios")
    if ed < sd:
        raise HTTPException(status_code=422, detail="A data de término não pode ser anterior à data de início.")
    # Teto legal: férias nunca excedem 30 dias corridos (CLT art. 130). Este endpoint recebe
    # dict cru (sem schema Pydantic) — a tela do DP posta DIRETO nesta rota, então a
    # validação precisa estar aqui (a guarda no schema de /operacional/vacations não a cobre).
    _dias_corridos = (ed - sd).days + 1
    if _dias_corridos > 30:
        raise HTTPException(
            status_code=422,
            detail=f"Férias não podem exceder 30 dias corridos (CLT art. 130); o período informado tem {_dias_corridos} dias.",
        )

    days = data.get("days")
    if days is None:
        days = (ed - sd).days + 1
    try:
        days_int = int(str(days).split()[0]) if days is not None else (ed - sd).days + 1
    except (ValueError, IndexError):
        days_int = (ed - sd).days + 1
    return_date = ed + _td(days=1)

    # condominio_id é NOT NULL na fonte canônica; employees não tem esse vínculo,
    # e todas as 18 solicitações existentes usam o condomínio canônico. Usa-o.
    condominio_id = _HVR_DEFAULT_CONDOMINIO_ID

    # request_code único por condomínio (uq_hr_vacation_requests_code)
    request_code = f"FER-DP-{_uuid.uuid4().hex[:8].upper()}"

    vid = str(_uuid.uuid4())
    await db.execute(
        _sqltext(
            "INSERT INTO hr_vacation_requests "
            "(id, condominio_id, employee_id, status, request_code, start_date, end_date, "
            " return_date, days_requested, sell_days, advance_13th, employee_notes, hr_notes, "
            " created_by, created_at, updated_at) VALUES "
            "(CAST(:id AS uuid), CAST(:cond AS uuid), CAST(:emp AS uuid), 'SUBMITTED', :code, "
            " :sd, :ed, :rd, :days, 0, false, :reason, :notes, CAST(:cby AS uuid), NOW(), NOW())"
        ),
        {
            "id": vid,
            "cond": condominio_id,
            "emp": emp,
            "code": request_code,
            "sd": sd,
            "ed": ed,
            "rd": return_date,
            "days": days_int,
            "reason": data.get("reason"),
            "notes": data.get("notes"),
            "cby": str(current_user.id) if getattr(current_user, "id", None) else None,
        },
    )
    await db.commit()
    return {"id": vid, "request_code": request_code, "message": "Solicitação de férias criada", "status": "pendente"}


@router.post("/{vacation_id}/reject", status_code=201, summary="Rejeitar solicitação de férias")
async def rejeitar_vacation(
    vacation_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    reason: str | None = Query(None, description="Motivo da rejeição"),
) -> Any:
    """Rejeita uma solicitação de férias (status EN 'REJECTED' na fonte canônica)."""
    service = VacationService(db)
    try:
        result = await service.reject_vacation(vacation_id, rejected_by_id=current_user.id, reason=reason)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{vacation_id}", summary="Cancelar solicitação de férias")
@router.delete("/{vacation_id}/", include_in_schema=False)
async def deletar_vacation(
    vacation_id: str, current_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)
) -> Any:
    """Cancela (soft-delete) a solicitação na fonte canônica — NUNCA hard-delete.

    A solicitação passa a contar no bucket 'cancelado' (status EN 'CANCELLED') e sai
    da lista ativa da tela. Preserva o dado trabalhista (NUNCA perde uma solicitação).
    """
    service = VacationService(db)
    try:
        result = await service.cancel_vacation(vacation_id, cancelled_by_id=current_user.id)
        await db.commit()
        return {"message": "Solicitação removida", "deleted": 1, **result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
