"""
Self-Service do Funcionário (login Google / JWT principal).

Diferente do Portal do Funcionário clássico (login por CPF, audience
'employee_portal'), este router atende o funcionário que entra com a CONTA
GOOGLE — o MESMO fluxo dos gestores. A conta é um `User` (role='funcionario',
permissions=['self:portal']) vinculado a um `employees.id` via users.employee_id
(gravado na aprovação de perfil pelo Jordan).

Todos os endpoints resolvem o employee_id a partir de users.employee_id do
usuário autenticado (CurrentActiveUser). O funcionário só enxerga/baixa o que é
DELE — nunca documento/holerite de outro, nunca módulo de gestão.

Reusa integralmente a lógica já provada do portal clássico (payslips, ponto,
férias, benefícios): importa as funções dos controllers `my_*` e as chama com o
employee_id resolvido, sem duplicar regra de negócio.

Montado sob /portal (aggregator) → prefixo final /portal/self-service/*.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_active_user
from core.database import get_db
from core.models import User
from modules.people_management.employee_portal.controllers.my_data_controller import (
    UpdateMyDataRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/self-service", tags=["Self-Service do Funcionário"])


def _employee_id(current_user: User) -> str:
    """Resolve o employee_id vinculado à conta, ou 400 se não vinculada."""
    if not current_user.employee_id:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Sua conta não está vinculada a um funcionário (employee_id ausente). "
            "Peça a um administrador para aprovar seu acesso com o perfil 'Funcionário'.",
        )
    return str(current_user.employee_id)


@router.get(
    "/me",
    summary="Meu resumo (funcionário logado)",
    description="Dados básicos + dashboard do funcionário vinculado à conta Google.",
)
async def meu_resumo(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    emp = _employee_id(current_user)
    from modules.people_management.employee_portal.services.portal_service import (
        PortalService,
    )

    svc = PortalService(db)
    try:
        dashboard = await svc.get_dashboard(UUID(emp))
    except Exception as e:  # noqa: BLE001
        logger.warning("self-service dashboard indisponível p/ %s: %s", emp, e)
        dashboard = {}
    return {
        "employee_id": emp,
        "nome": current_user.name,
        "email": current_user.email,
        "dashboard": dashboard,
    }


@router.get(
    "/meus-holerites",
    summary="Meus holerites",
    description="Lista os holerites do funcionário logado (por ano).",
)
async def meus_holerites(
    year: int | None = Query(default=None, ge=2020, le=2030),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    emp = _employee_id(current_user)
    from modules.people_management.employee_portal.controllers.my_payslips_controller import (
        get_my_payslips,
    )

    return await get_my_payslips(employee_id=emp, year=year, db=db)


@router.get(
    "/meus-holerites/{month}/{year}",
    summary="Holerite por mês/ano",
)
async def meu_holerite_mes(
    month: int,
    year: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    emp = _employee_id(current_user)
    from modules.people_management.employee_portal.controllers.my_payslips_controller import (
        get_payslip_by_month,
    )

    return await get_payslip_by_month(employee_id=emp, month=month, year=year, db=db)


@router.get(
    "/meus-holerites/{month}/{year}/pdf",
    summary="Baixar PDF do holerite",
)
async def meu_holerite_pdf(
    month: int,
    year: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    emp = _employee_id(current_user)
    from modules.people_management.employee_portal.controllers.my_payslips_controller import (
        get_payslip_pdf,
    )

    return await get_payslip_pdf(employee_id=emp, month=month, year=year, db=db)


@router.get(
    "/minhas-ferias/saldo",
    summary="Meu saldo de férias",
)
async def minhas_ferias_saldo(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    emp = _employee_id(current_user)
    from modules.people_management.employee_portal.controllers.my_vacations_controller import (
        get_vacation_balance,
    )

    return await get_vacation_balance(employee_id=emp, db=db)


@router.get(
    "/minhas-ferias/solicitacoes",
    summary="Minhas solicitações de férias",
)
async def minhas_ferias_solicitacoes(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    emp = _employee_id(current_user)
    from modules.people_management.employee_portal.controllers.my_vacations_controller import (
        get_vacation_requests,
    )

    return await get_vacation_requests(employee_id=emp, db=db)


@router.get(
    "/meu-ponto",
    summary="Meu espelho de ponto",
)
async def meu_ponto(
    mes: int | None = Query(default=None, ge=1, le=12),
    ano: int | None = Query(default=None, ge=2020, le=2030),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    emp = _employee_id(current_user)
    from modules.people_management.employee_portal.controllers.my_ponto_controller import (
        get_ponto_historico,
    )

    return await get_ponto_historico(employee_id=emp, mes=mes, ano=ano, db=db)


@router.get(
    "/minha-escala",
    summary="Minha escala do mês",
    description="Turnos reais do funcionário logado (tabela shifts) para o mês/ano.",
)
async def minha_escala(
    mes: int | None = Query(default=None, ge=1, le=12),
    ano: int | None = Query(default=None, ge=2020, le=2030),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    emp = _employee_id(current_user)
    from modules.people_management.employee_portal.services.document_view_service import (
        DocumentViewService,
    )

    svc = DocumentViewService(db)
    return await svc.get_my_schedules(employee_id=UUID(emp), month=mes, year=ano)


@router.get(
    "/minha-escala/proximo-turno",
    summary="Meu próximo turno",
    description="Próximo turno futuro agendado do funcionário logado (ou vazio se não houver).",
)
async def meu_proximo_turno(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    emp = _employee_id(current_user)
    from datetime import date as _date

    from sqlalchemy import text as _sqltext

    row = (
        (
            await db.execute(
                _sqltext(
                    "SELECT s.shift_date, s.planned_start_time, s.planned_end_time, "
                    "s.status, p.name AS post_name "
                    "FROM shifts s LEFT JOIN posts p ON p.id = s.post_id "
                    "WHERE CAST(s.employee_id AS TEXT) = :e "
                    "AND s.shift_date >= :today "
                    "AND COALESCE(s.status, '') NOT IN ('cancelled', 'canceled') "
                    "AND COALESCE(s.is_off_day, false) = false "
                    "ORDER BY s.shift_date, s.planned_start_time LIMIT 1"
                ),
                {"e": emp, "today": _date.today()},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        return {"employee_id": emp, "proximo_turno": None}
    return {
        "employee_id": emp,
        "proximo_turno": {
            "date": str(row["shift_date"]),
            "start_time": str(row["planned_start_time"]) if row["planned_start_time"] else None,
            "end_time": str(row["planned_end_time"]) if row["planned_end_time"] else None,
            "workplace": row["post_name"],
            "status": row["status"] or "agendado",
        },
    }


@router.get(
    "/minhas-notificacoes",
    summary="Minhas notificações / comunicados",
    description="Notificações e comunicados do DP para o funcionário logado "
    "(mesma fonte de /portal/my-notifications e /portal/comunicados).",
)
async def minhas_notificacoes(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    emp = _employee_id(current_user)
    from sqlalchemy import select

    from modules.people_management.employee_portal.models.notification import (
        PortalNotification,
    )

    itens: list[dict[str, Any]] = []
    nao_lidas = 0
    try:
        result = await db.execute(
            select(PortalNotification)
            .where(PortalNotification.employee_id == str(emp))
            .order_by(PortalNotification.created_at.desc())
            .limit(100)
        )
        for n in result.scalars().all():
            lido = bool(n.is_read)
            if not lido:
                nao_lidas += 1
            itens.append(
                {
                    "id": n.id,
                    "titulo": n.title,
                    "mensagem": n.message,
                    "tipo": str(n.notification_type.value) if n.notification_type else None,
                    "lido": lido,
                    "data": str(n.created_at) if n.created_at else None,
                }
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("self-service notificações indisponíveis p/ %s: %s", emp, exc)

    return {
        "employee_id": emp,
        "total": len(itens),
        "nao_lidas": nao_lidas,
        "notificacoes": itens,
    }


@router.patch(
    "/minhas-notificacoes/{notification_id}/lida",
    summary="Marcar minha notificação como lida",
)
async def marcar_notificacao_lida(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    emp = _employee_id(current_user)
    from datetime import datetime as _dt

    from sqlalchemy import select

    from modules.people_management.employee_portal.models.notification import (
        PortalNotification,
    )

    result = await db.execute(
        select(PortalNotification).where(
            PortalNotification.id == notification_id,
            # Filtro de segurança: só a notificação DELE.
            PortalNotification.employee_id == str(emp),
        )
    )
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Notificação {notification_id} não encontrada.",
        )
    notif.is_read = True
    notif.read_at = _dt.utcnow()
    await db.commit()
    return {"id": notif.id, "lido": True}


@router.get(
    "/meus-beneficios",
    summary="Meus benefícios",
)
async def meus_beneficios(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    emp = _employee_id(current_user)
    from modules.people_management.employee_portal.controllers.my_benefits_controller import (
        get_my_benefits,
    )

    return await get_my_benefits(employee_id=emp, db=db)


@router.get(
    "/meus-documentos-a-assinar",
    summary="Meus documentos pendentes de assinatura",
    description="Atalho self-service para as assinaturas pendentes do funcionário "
    "logado (mesma fonte de GET /signatures/meus-pendentes).",
)
async def meus_documentos_a_assinar(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    emp = _employee_id(current_user)
    from modules.signatures.services.universal_signature_service import (
        UniversalSignatureService,
    )

    svc = UniversalSignatureService(db)
    pendentes = await svc.pendentes_do_funcionario(UUID(emp))
    return {"employee_id": emp, "total": len(pendentes), "pendentes": pendentes}


# =========================================================================== #
# Treinamentos / Dados pessoais / Documentos / CCT
# (self-service — reusa os my_*_controller com o employee_id do JWT Google)
# =========================================================================== #


@router.get(
    "/meus-treinamentos",
    summary="Meus treinamentos (matrículas)",
    description="Matrículas do funcionário logado em treinamentos (fonte: my-trainings).",
)
async def meus_treinamentos(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    emp = _employee_id(current_user)
    from modules.people_management.employee_portal.controllers.my_trainings_controller import (
        get_my_certificates,
        get_my_enrollments,
    )

    matriculas = await get_my_enrollments(employee_id=UUID(emp), db=db)
    certificados = await get_my_certificates(employee_id=UUID(emp), db=db)
    return {
        "employee_id": emp,
        "matriculas": [
            m.model_dump() if hasattr(m, "model_dump") else m for m in (matriculas or [])
        ],
        "certificados": [
            c.model_dump() if hasattr(c, "model_dump") else c for c in (certificados or [])
        ],
    }


@router.get(
    "/meus-dados",
    summary="Meus dados pessoais",
    description="Dados cadastrais do funcionário logado (leitura). CPF mascarado.",
)
async def meus_dados(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    emp = _employee_id(current_user)
    from modules.people_management.employee_portal.controllers.my_data_controller import (
        get_my_data,
    )

    return await get_my_data(employee_id=UUID(emp), db=db)


@router.get(
    "/onboarding-status",
    summary="Status do onboarding obrigatório (funcionário logado)",
    description="Indica se o funcionário precisa completar o cadastro no 1º acesso "
    "(campos obrigatórios do S-2200 eSocial faltando em employees). "
    "Se pendente=true, o Meu Espaço deve bloquear e exibir o formulário obrigatório.",
)
async def meu_onboarding_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    emp = _employee_id(current_user)
    from modules.people_management.employee_portal.controllers.my_data_controller import (
        get_onboarding_status,
    )

    return await get_onboarding_status(employee_id=UUID(emp), db=db)


@router.put(
    "/meus-dados",
    summary="Atualizar meus dados (dados pessoais/contato)",
    description="Grava DIRETO em employees (fonte única — o DP lê o mesmo registro). "
    "Aceita todos os campos do onboarding (telefone, endereço, nome_mae, "
    "naturalidade, nacionalidade, rg, estado_civil, pis...). "
    "Cargo/salário/status/matrícula/CPF NUNCA são editáveis pelo funcionário. "
    "Retorna os dados + o status de onboarding recomputado.",
)
async def atualizar_meus_dados(
    update_data: UpdateMyDataRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    emp = _employee_id(current_user)
    from modules.people_management.employee_portal.controllers.my_data_controller import (
        update_my_data,
    )

    return await update_my_data(update_data=update_data, employee_id=UUID(emp), db=db)


@router.get(
    "/meus-documentos",
    summary="Meus documentos",
    description="Lista os documentos REAIS do funcionário logado (holerite, contrato, "
    "ficha, kit...) com status de assinatura. Fonte: ged_kit_documents (só DELE).",
)
async def meus_documentos(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    emp = _employee_id(current_user)
    from modules.people_management.employee_portal.services.document_view_service import (
        DocumentViewService,
    )

    svc = DocumentViewService(db)
    documentos = await svc.get_my_documents(UUID(emp))
    return {"employee_id": emp, "total": len(documentos), "documentos": documentos}


@router.get(
    "/meus-documentos/{document_id}/download",
    summary="Baixar/ver um documento meu",
    description="Serve o arquivo do documento — SÓ se pertencer ao funcionário logado. "
    "Verifica ownership por employee_id antes de servir (path-traversal safe). "
    "Documentos gerados sob demanda (sem arquivo em disco) retornam 404 honesto.",
)
async def baixar_meu_documento(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    import os
    from pathlib import Path as _Path

    from fastapi.responses import FileResponse
    from sqlalchemy import text as _sqltext

    emp = _employee_id(current_user)

    # SEGURANÇA: só devolve o documento se employee_id == funcionário logado.
    row = (
        await db.execute(
            _sqltext(
                "SELECT document_name, file_path "
                "FROM ged_kit_documents "
                "WHERE CAST(id AS TEXT) = :did "
                "AND CAST(employee_id AS TEXT) = :e "
                "AND file_path IS NOT NULL"
            ),
            {"did": str(document_id), "e": emp},
        )
    ).mappings().first()

    if not row:
        # 404 tanto para inexistente quanto para documento de OUTRO funcionário
        # (não vaza a existência de documentos alheios).
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Documento não encontrado.",
        )

    file_path = row["file_path"]
    # Resolve base de storage (GED). Aceita path absoluto ou relativo.
    base = os.environ.get("GED_STORAGE_PATH", "/app/uploads")
    full = file_path if os.path.isabs(file_path) else os.path.join(base, file_path)

    # Path traversal protection: o alvo tem de ficar sob a base permitida.
    try:
        base_resolved = _Path(base).resolve()
        target = _Path(full).resolve()
        if not str(target).startswith(str(base_resolved)):
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="Caminho de arquivo inválido.",
            )
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001
        target = _Path(full)

    if not target.exists():
        # Vazio-real honesto: muitos documentos do DP são gerados sob demanda
        # (holerite via aba Holerite; kits pela GEDEON) e não têm arquivo salvo.
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Este documento é gerado sob demanda e não possui arquivo para download "
            "direto. Use a aba Holerite para baixar contracheques.",
        )

    filename = (row["document_name"] or target.name).replace("/", "_") + (
        "" if target.suffix else ".pdf"
    )
    return FileResponse(
        path=str(target),
        media_type="application/pdf",
        filename=filename,
    )


@router.get(
    "/minha-cct",
    summary="Minha CCT / meus direitos e piso",
    description="Direitos do trabalhador conforme a CCT vigente e o cargo do funcionário "
    "logado (piso, benefícios garantidos, adicionais, estabilidades).",
)
async def minha_cct(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    emp = _employee_id(current_user)
    from modules.people_management.employee_portal.controllers.my_cct_controller import (
        get_meus_direitos,
    )

    return await get_meus_direitos(employee_id=UUID(emp), db=db)
