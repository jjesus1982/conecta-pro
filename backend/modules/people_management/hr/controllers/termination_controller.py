"""
Controller de Rescisão — Departamento Pessoal.

Endpoints para o workflow de desligamento de colaboradores.
"""

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select, text as _sqltext
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.people_management.hr.models.termination import (
    TerminationStatus,
    TerminationType,
)
from modules.people_management.hr.publishers import publish_funcionario_demitido
from modules.people_management.hr.schemas.termination import (
    TerminationCalculation,
    TerminationCreate,
    TerminationResponse,
    TerminationUpdate,
)
from modules.people_management.hr.services.termination_service import (
    TerminationService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/terminations", tags=["DP - Rescisões"])


@router.get(
    "",
    summary="Listar Rescisões",
    description="Retorna lista paginada de processos de rescisão com filtro por status.",
)
async def list_terminations(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    status: TerminationStatus | None = Query(None, description="Filtro por status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Any:
    """Lista processos de rescisão com filtro e paginação."""
    service = TerminationService(db)
    result = await service.list_terminations(status=status, page=page, page_size=page_size)
    if isinstance(result, dict) and "items" in result:
        # Popula o NOME real do colaborador (JOIN por employee_id em employees.nome).
        from modules.operacional.models.employee import Employee

        emp_ids = [str(t.employee_id) for t in result["items"] if t.employee_id]
        name_by_id: dict[str, str] = {}
        if emp_ids:
            rows = await db.execute(select(Employee.id, Employee.nome).where(Employee.id.in_(emp_ids)))
            name_by_id = {str(r[0]): r[1] for r in rows.all()}
        serialized = []
        for t in result["items"]:
            serialized.append(
                {
                    "id": str(t.id),
                    "employee_id": str(t.employee_id),
                    "employee_name": name_by_id.get(str(t.employee_id)),
                    "type": t.type,
                    "reason": t.reason,
                    # Extrair notice_type do campo reason (formato "notice_type:<valor>")
                    "notice_type": (
                        t.reason.split("notice_type:")[1] if t.reason and t.reason.startswith("notice_type:") else None
                    ),
                    "notice_period_days": t.notice_period_days,
                    "notice_start_date": t.notice_start_date.isoformat() if t.notice_start_date else None,
                    "last_working_day": t.last_working_day.isoformat() if t.last_working_day else None,
                    "status": t.status,
                    "severance_amount": float(t.severance_amount) if t.severance_amount else None,
                    "vacation_balance_amount": float(t.vacation_balance_amount) if t.vacation_balance_amount else None,
                    "thirteenth_salary_amount": float(t.thirteenth_salary_amount)
                    if t.thirteenth_salary_amount
                    else None,
                    "fgts_amount": float(t.fgts_amount) if t.fgts_amount else None,
                    "total_amount": float(t.total_amount) if t.total_amount else None,
                    "exit_interview_done": t.exit_interview_done,
                    "exit_interview_notes": t.exit_interview_notes,
                    # [Achado 4] eSocial HONESTO: o módulo DP apenas GERA o XML (endpoint
                    # /esocial/s2299/gerar retorna XML p/ download); NÃO há transmissão ao
                    # webservice do eSocial aqui, logo não existe recibo/protocolo. Expomos
                    # os dois estados separados em vez de fingir "evento transmitido".
                    # - esocial_xml_gerado: XML/documento eSocial foi gerado (fato local)
                    # - esocial_transmitido: só True com nº de recibo real (hoje: nunca, externo)
                    "esocial_xml_gerado": bool(t.esocial_event_sent),
                    "esocial_transmitido": False,
                    "esocial_protocolo": None,
                    # Compat: mantém a chave antiga, mas seu SIGNIFICADO agora é "XML gerado"
                    # (não "transmitido"). Frontend rotula honestamente.
                    "esocial_event_sent": bool(t.esocial_event_sent),
                    "documents_generated": t.documents_generated or {},
                    "created_by_id": str(t.created_by_id) if t.created_by_id else None,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "updated_at": t.updated_at.isoformat() if t.updated_at else None,
                }
            )
        result["items"] = serialized
    return result


@router.post(
    "",
    summary="Iniciar Processo de Rescisão",
    response_model=TerminationResponse,
    status_code=201,
    description="Retorna lista paginada de processos de rescisão com filtro por status.",
)
async def create_termination(
    data: TerminationCreate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Cria um novo processo de rescisão."""
    service = TerminationService(db)
    termination = await service.create_termination(data.model_dump(), created_by_id=current_user.id)
    await db.commit()
    return termination


@router.get(
    "/{termination_id}",
    summary="Buscar Rescisão",
    response_model=TerminationResponse,
    description="Retorna lista paginada de processos de rescisão com filtro por status.",
)
async def get_termination(
    termination_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna detalhes de um processo de rescisão."""
    service = TerminationService(db)
    termination = await service.get_by_id(termination_id)
    if not termination:
        raise HTTPException(status_code=404, detail="Rescisão não encontrada")

    # Popula o NOME real do colaborador (JOIN por employee_id em employees.nome),
    # espelhando o endpoint de lista. Sem isso a tela de detalhe cai no fallback
    # "(colaborador removido)" mesmo quando o colaborador existe (ex.: demitido).
    from modules.operacional.models.employee import Employee

    employee_name: str | None = None
    if termination.employee_id:
        row = await db.execute(
            select(Employee.nome).where(Employee.id == str(termination.employee_id))
        )
        employee_name = row.scalar_one_or_none()

    data = TerminationResponse.model_validate(termination).model_dump(mode="json")
    data["employee_name"] = employee_name
    return data


@router.patch(
    "/{termination_id}",
    summary="Atualizar Rescisão",
    response_model=TerminationResponse,
    description="Retorna lista paginada de processos de rescisão com filtro por status.",
)
async def update_termination(
    termination_id: str,
    data: TerminationUpdate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Atualiza dados de um processo de rescisão."""
    service = TerminationService(db)
    termination = await service.get_by_id(termination_id)
    if not termination:
        raise HTTPException(status_code=404, detail="Rescisão não encontrada")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if hasattr(termination, key) and value is not None:
            setattr(termination, key, value)

    await db.flush()
    await db.refresh(termination)
    await db.commit()
    return termination


@router.post(
    "/{termination_id}/calculate",
    summary="Calcular Verbas Rescisórias",
    response_model=TerminationCalculation,
    status_code=201,
    description="Retorna lista paginada de processos de rescisão com filtro por status.",
)
async def calculate_severance(
    termination_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Calcula verbas rescisórias para um processo de rescisão."""
    service = TerminationService(db)
    termination = await service.get_by_id(termination_id)
    if not termination:
        raise HTTPException(status_code=404, detail="Rescisão não encontrada")

    if not termination.last_working_day:
        raise HTTPException(
            status_code=400,
            detail="Último dia de trabalho não informado",
        )

    try:
        calculation = await service.calculate_severance(
            termination.employee_id,
            TerminationType(termination.type),
            termination.last_working_day,
        )
        return calculation
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/{termination_id}/complete",
    summary="Concluir Rescisão",
    response_model=TerminationResponse,
    status_code=201,
    description="Retorna lista paginada de processos de rescisão com filtro por status.",
)
async def complete_termination(
    termination_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Conclui o processo de rescisão e desativa o funcionário."""
    service = TerminationService(db)
    termination = await service.complete_termination(termination_id)
    if not termination:
        raise HTTPException(status_code=404, detail="Rescisão não encontrada")
    await db.commit()
    # [Item −1/A1] resolve cliente_id do funcionário (backfill) → GEDEON monta o kit certo
    from sqlalchemy import text as _sqltext

    _term_cli = (
        await db.execute(
            _sqltext("SELECT cliente_id FROM employees WHERE CAST(id AS TEXT)=:i"),
            {"i": str(termination.employee_id)},
        )
    ).scalar()
    asyncio.create_task(
        publish_funcionario_demitido(
            funcionario_id=str(termination.employee_id),
            funcionario_nome=str(getattr(termination, "employee_name", "")),
            motivo=str(termination.type),
            data_desligamento=str(getattr(termination, "last_working_day", "") or ""),
            cliente_id=str(_term_cli) if _term_cli else None,
        )
    )
    return termination


async def _dados_funcionario(db: AsyncSession, employee_id: str) -> dict:
    """Busca cpf/cargo/data_admissao do funcionário (dado real, sem inventar)."""
    row = (
        await db.execute(
            _sqltext(
                "SELECT nome, cpf, cargo, data_admissao FROM employees "
                "WHERE CAST(id AS TEXT) = :i LIMIT 1"
            ),
            {"i": str(employee_id)},
        )
    ).first()
    if not row:
        return {}
    adm = row[3]
    return {
        "nome": row[0],
        "cpf": row[1],
        "cargo": row[2],
        "data_admissao": adm.isoformat() if hasattr(adm, "isoformat") else (adm or None),
    }


def _notice_type_from_reason(reason: str | None) -> str | None:
    """Extrai a modalidade do aviso ('trabalhado'/'indenizado') do campo reason."""
    if reason and reason.startswith("notice_type:"):
        return reason.split("notice_type:", 1)[1].strip() or None
    return None


@router.get(
    "/{termination_id}/aviso-previo/pdf",
    summary="Download PDF do Aviso Prévio",
    description=(
        "Gera e retorna o PDF do Aviso Prévio (Lei 12.506/2011) no padrão-ouro Conecta Mais. "
        "Plugado na assinatura universal (EMPLOYEE + COMPANY)."
    ),
)
async def download_aviso_previo_pdf(
    termination_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Gera o PDF do Aviso Prévio e garante a solicitação de assinatura (idempotente)."""
    service = TerminationService(db)
    termination = await service.get_by_id(termination_id)
    if not termination:
        raise HTTPException(status_code=404, detail="Rescisão não encontrada")

    func = await _dados_funcionario(db, termination.employee_id)
    nome = func.get("nome")

    # Status atual das assinaturas → alimenta o bloco de autenticidade se já assinado.
    assinaturas: list = []
    try:
        from modules.signatures.services.universal_signature_service import (
            UniversalSignatureService,
        )

        stt = await UniversalSignatureService(db).status(
            document_type="aviso_previo", document_id=termination_id
        )
        assinaturas = stt.get("signatarios") or stt.get("signers") or []
    except Exception:  # noqa: BLE001
        assinaturas = []

    from modules.people_management.hr.services.aviso_previo_pdf import montar_aviso_previo_pdf

    dados = {
        "termination_id": termination_id,
        "employee_nome": nome,
        "modalidade": _notice_type_from_reason(termination.reason),
        "notice_start_date": termination.notice_start_date,
        "notice_period_days": termination.notice_period_days,
        "last_working_day": termination.last_working_day,
        "assinaturas": assinaturas,
    }
    try:
        pdf_bytes = montar_aviso_previo_pdf(dados, func)
    except Exception as exc:  # noqa: BLE001
        logger.error("Erro ao gerar PDF do aviso prévio %s: %s", termination_id, exc)
        raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF: {exc}") from exc

    # Camada de assinatura universal: aviso_previo → EMPLOYEE + COMPANY (idempotente).
    try:
        from modules.signatures.helpers import (
            document_hash_sha256,
            garantir_solicitacao_assinatura,
        )

        await garantir_solicitacao_assinatura(
            db,
            document_type="aviso_previo",
            document_id=termination_id,
            title=f"Aviso Prévio - {nome or termination_id[:8]}",
            document_hash=document_hash_sha256(pdf_bytes),
            employee_id=str(termination.employee_id),
            employee_name=nome,
            employee_document=func.get("cpf"),
            requested_by=current_user.id,
        )
        await db.commit()
    except Exception as _sig_exc:  # noqa: BLE001
        logger.warning("Assinatura do aviso prévio %s não criada: %s", termination_id, _sig_exc)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="aviso_previo_{termination_id[:8]}.pdf"',
            "Cache-Control": "no-store",
        },
    )


@router.get(
    "/{termination_id}/trct/pdf",
    summary="Download PDF do TRCT",
    description=(
        "Gera e retorna o PDF do Termo de Rescisão do Contrato de Trabalho (TRCT) no padrão-ouro "
        "Conecta Mais, com as verbas JÁ calculadas pelo motor. Plugado na assinatura universal "
        "(EMPLOYEE + COMPANY)."
    ),
)
async def download_trct_pdf(
    termination_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Gera o PDF do TRCT (verbas do cálculo existente) e garante a assinatura (idempotente)."""
    service = TerminationService(db)
    termination = await service.get_by_id(termination_id)
    if not termination:
        raise HTTPException(status_code=404, detail="Rescisão não encontrada")
    if not termination.last_working_day:
        raise HTTPException(status_code=400, detail="Último dia de trabalho não informado")

    # Verbas: usa EXATAMENTE o cálculo existente (mesmo que a tela mostra).
    try:
        calc = await service.calculate_severance(
            termination.employee_id,
            TerminationType(termination.type),
            termination.last_working_day,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    func = await _dados_funcionario(db, termination.employee_id)
    nome = func.get("nome") or calc.get("employee_name")

    assinaturas: list = []
    try:
        from modules.signatures.services.universal_signature_service import (
            UniversalSignatureService,
        )

        stt = await UniversalSignatureService(db).status(
            document_type="rescisao", document_id=termination_id
        )
        assinaturas = stt.get("signatarios") or stt.get("signers") or []
    except Exception:  # noqa: BLE001
        assinaturas = []

    from modules.people_management.hr.services.trct_pdf import montar_trct_pdf

    try:
        pdf_bytes = montar_trct_pdf(
            calc,
            func,
            meta={
                "termination_id": termination_id,
                "notice_type": _notice_type_from_reason(termination.reason),
                "termination_type": termination.type,
                "assinaturas": assinaturas,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Erro ao gerar PDF do TRCT %s: %s", termination_id, exc)
        raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF: {exc}") from exc

    # Camada de assinatura universal: rescisao → EMPLOYEE + COMPANY (idempotente).
    try:
        from modules.signatures.helpers import (
            document_hash_sha256,
            garantir_solicitacao_assinatura,
        )

        await garantir_solicitacao_assinatura(
            db,
            document_type="rescisao",
            document_id=termination_id,
            title=f"TRCT - {nome or termination_id[:8]}",
            document_hash=document_hash_sha256(pdf_bytes),
            employee_id=str(termination.employee_id),
            employee_name=nome,
            employee_document=func.get("cpf"),
            requested_by=current_user.id,
        )
        await db.commit()
    except Exception as _sig_exc:  # noqa: BLE001
        logger.warning("Assinatura do TRCT %s não criada: %s", termination_id, _sig_exc)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="trct_{termination_id[:8]}.pdf"',
            "Cache-Control": "no-store",
        },
    )
