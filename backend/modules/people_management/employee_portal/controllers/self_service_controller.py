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

import base64
import logging
from datetime import date as _date
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi import status as http_status
from pydantic import BaseModel, Field
from sqlalchemy import text as _sqltext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from core.auth.dependencies import get_current_active_user
from core.database import get_db
from core.database.session import get_sync_db_dependency
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
    "/meu-espelho/{mes}/{ano}/pdf",
    summary="Baixar o PDF do meu espelho de ponto (mês)",
)
def meu_espelho_pdf(
    mes: int,
    ano: int,
    current_user: User = Depends(get_current_active_user),
    db_sync: "Session" = Depends(get_sync_db_dependency),
) -> Any:
    """PDF do espelho de ponto do funcionário logado (lido de time_sheets)."""
    from fastapi.responses import Response

    from modules.people_management.hr.services.espelho_ponto_pdf import (
        montar_espelho_ponto_pdf,
    )
    from modules.people_management.hr.services.espelho_ponto_service import ler_espelho

    emp = _employee_id(current_user)
    esp = ler_espelho(db_sync, emp, mes, ano)
    if not esp:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Seu espelho de ponto de {int(mes):02d}/{ano} ainda não está disponível.",
        )
    signatarios = None
    try:
        from modules.signatures.helpers import status_documento_sync

        stt = status_documento_sync("espelho_ponto", esp["time_sheet_id"])
        if stt:
            signatarios = stt.get("signatarios")
    except Exception:  # noqa: BLE001
        signatarios = None
    pdf = montar_espelho_ponto_pdf(esp, signatarios=signatarios)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="meu_espelho_{int(mes):02d}_{ano}.pdf"'},
    )


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

    resultado = await get_my_benefits(employee_id=emp, db=db)
    # Não expor ao funcionário os mínimos garantidos pela CCT (decisão Jordan 2026-07-13):
    # comparar o "garantido pela CCT" com o holerite viraria prova de gap num contencioso.
    if isinstance(resultado, dict):
        resultado.pop("beneficios_cct", None)
    return resultado


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
    # DESATIVADO (decisão Jordan 2026-07-13): não expor ao funcionário o piso/adicionais
    # "que ele deveria receber" — comparado ao holerite, viraria prova de gap num contencioso
    # trabalhista. O dado da CCT segue disponível para o DP/gestão, não para o self-service.
    raise HTTPException(
        status_code=http_status.HTTP_404_NOT_FOUND,
        detail="Recurso indisponível.",
    )


# =========================================================================== #
# PONTO ANTI-FRAUDE (self-service): bater ponto + status do dia
# GPS geofence + selfie foto + timestamp (fase 1). Facial = fase 2.
# =========================================================================== #


class BaterPontoRequest(BaseModel):
    """Batida de ponto do funcionário (self-service)."""

    tipo: str = Field(
        default="auto",
        description="'entrada', 'saida' ou 'auto' (decide pelo estado do dia).",
    )
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    accuracy: float | None = Field(
        default=None, description="Precisão do GPS em metros (opcional)."
    )
    foto_base64: str | None = Field(
        default=None,
        description="Selfie da batida (base64 ou data-URI). Evidência anti-fraude.",
    )
    posto_id: str | None = Field(
        default=None,
        description="Opcional: força o posto. Se ausente, resolve pela alocação ativa.",
    )
    observacao: str | None = None


async def _posto_atual_do_funcionario(
    db: AsyncSession, employee_id: str
) -> tuple[str | None, str | None]:
    """Resolve o posto ATUAL do funcionário via alocação ativa (allocations→posts).

    Prefere a alocação primária ativa e vigente (start<=hoje, sem end ou end>=hoje).
    Retorna (posto_id, posto_nome) ou (None, None) se não houver alocação.
    """
    row = (
        await db.execute(
            _sqltext(
                "SELECT p.id::text AS posto_id, p.name AS posto_nome "
                "FROM allocations a JOIN posts p ON p.id = a.post_id "
                "WHERE a.employee_id::text = :e "
                "AND a.status = 'active' AND a.is_active = true "
                "AND a.start_date <= :today "
                "AND (a.end_date IS NULL OR a.end_date >= :today) "
                "ORDER BY a.is_primary DESC, a.start_date DESC LIMIT 1"
            ),
            {"e": employee_id, "today": _date.today()},
        )
    ).mappings().first()
    if not row:
        return None, None
    return row["posto_id"], row["posto_nome"]


async def _estado_ponto_hoje(db: AsyncSession, employee_id: str) -> dict[str, Any]:
    """Estado das batidas de HOJE: última batida e se há entrada aberta."""
    rows = (
        await db.execute(
            _sqltext(
                "SELECT punch_id, punch_type, (punch_timestamp) AS punch_timestamp, dentro_geofence, "
                "distancia_posto_metros, foto_capturada_url, posto_nome "
                "FROM gp_clock_punches "
                "WHERE employee_id::text = :e AND (punch_timestamp)::date = :today "
                "ORDER BY punch_timestamp"
            ),
            {"e": employee_id, "today": _date.today()},
        )
    ).mappings().all()
    batidas = [dict(r) for r in rows]
    ultima = batidas[-1] if batidas else None
    tem_entrada_aberta = bool(ultima and ultima["punch_type"] == "entrada")
    return {"batidas": batidas, "ultima": ultima, "entrada_aberta": tem_entrada_aberta}


@router.post(
    "/bater-ponto",
    summary="Bater ponto (funcionário) — GPS geofence + selfie",
    description="Registra a batida do funcionário logado. Resolve o posto ATUAL pela "
    "alocação ativa, calcula o geofence (haversine) contra as coordenadas reais do "
    "posto e salva a selfie como evidência anti-fraude. tipo='auto' alterna "
    "entrada/saída pelo estado do dia.",
)
async def bater_ponto(
    payload: BaterPontoRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    emp = _employee_id(current_user)
    from modules.people_management.hr.services.time_record_service import (
        TimeRecordService,
    )

    svc = TimeRecordService(db)

    # 1. Descobrir o posto atual. SEGURANÇA anti-fraude: um posto_id vindo do cliente só
    # é aceito se pertencer a uma ALOCAÇÃO ATIVA do próprio funcionário — senão o geofence
    # seria medido contra um posto escolhido por ele (marcaria dentro_geofence fora do posto
    # real). Posto não-pertencente é ignorado e cai na alocação real.
    posto_id = payload.posto_id
    posto_nome = None
    if posto_id:
        prow = (
            await db.execute(
                _sqltext(
                    "SELECT p.name FROM allocations a JOIN posts p ON p.id = a.post_id "
                    "WHERE a.employee_id::text = :e AND p.id::text = :p "
                    "AND a.status = 'active' AND a.is_active = true "
                    "AND (a.end_date IS NULL OR a.end_date >= :today) LIMIT 1"
                ),
                {"e": str(emp), "p": str(posto_id), "today": _date.today()},
            )
        ).first()
        if prow:
            posto_nome = prow[0]
        else:
            posto_id, posto_nome = await _posto_atual_do_funcionario(db, emp)
    else:
        posto_id, posto_nome = await _posto_atual_do_funcionario(db, emp)

    # 2. Decidir entrada x saída.
    estado = await _estado_ponto_hoje(db, emp)
    tipo = (payload.tipo or "auto").lower()
    if tipo == "auto":
        tipo = "saida" if estado["entrada_aberta"] else "entrada"

    # 3. Executar a batida (geofence + selfie são feitos no service).
    if tipo == "entrada":
        resultado = await svc.clock_in(
            employee_id=emp,
            location_lat=payload.latitude,
            location_lng=payload.longitude,
            posto_id=posto_id,
            device_type="conecta_pro_app",
            notes=payload.observacao,
            created_by=str(current_user.id),
            foto_base64=payload.foto_base64,
            accuracy=payload.accuracy,
        )
    elif tipo == "saida":
        if not estado["entrada_aberta"]:
            raise HTTPException(
                status_code=http_status.HTTP_409_CONFLICT,
                detail="Não há entrada aberta hoje para registrar saída.",
            )
        resultado = await svc.clock_out(
            record_id=str(estado["ultima"]["punch_id"]),
            location_lat=payload.latitude,
            location_lng=payload.longitude,
            notes=payload.observacao,
            created_by=str(current_user.id),
            foto_base64=payload.foto_base64,
            accuracy=payload.accuracy,
        )
    else:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="tipo inválido — use 'entrada', 'saida' ou 'auto'.",
        )

    await db.commit()
    resultado["tipo"] = tipo
    resultado["employee_id"] = emp
    if not resultado.get("posto_nome"):
        resultado["posto_nome"] = posto_nome
    return resultado


@router.get(
    "/ponto-hoje",
    summary="Meu ponto de hoje (funcionário)",
    description="Status do dia: se já bateu entrada/saída, últimas batidas com "
    "geofence e evidência, e qual a próxima ação (bater entrada ou saída).",
)
async def ponto_hoje(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    emp = _employee_id(current_user)
    estado = await _estado_ponto_hoje(db, emp)
    posto_id, posto_nome = await _posto_atual_do_funcionario(db, emp)

    entrada = next(
        (b for b in estado["batidas"] if b["punch_type"] == "entrada"), None
    )
    saida = next(
        (b for b in reversed(estado["batidas"]) if b["punch_type"] == "saida"), None
    )

    def _fmt(b: dict[str, Any] | None) -> dict[str, Any] | None:
        if not b:
            return None
        ts = b["punch_timestamp"]
        return {
            "hora": ts.strftime("%H:%M") if ts else None,
            "dentro_geofence": b["dentro_geofence"],
            "distancia_posto_metros": b["distancia_posto_metros"],
            "foto_capturada_url": b["foto_capturada_url"],
            "posto_nome": b["posto_nome"],
        }

    # Próxima batida considerando a intrajornada do posto (2 ou 4 batidas/dia).
    prox = await _proxima_batida_info(db, emp)
    proxima_acao = prox["tipo"]

    # Lista de batidas do dia (para a tela "Hoje" do Meu Espaço).
    batidas_lista = [
        {
            "tipo": b["punch_type"],
            "hora": b["punch_timestamp"].strftime("%H:%M") if b["punch_timestamp"] else None,
            "data_hora": str(b["punch_timestamp"]) if b["punch_timestamp"] else None,
            "posto": b["posto_nome"],
            "dentro_geofence": b["dentro_geofence"],
        }
        for b in estado["batidas"]
    ]

    return {
        "employee_id": emp,
        "data": str(_date.today()),
        "posto_atual": {"posto_id": posto_id, "posto_nome": posto_nome},
        "posto_nome": posto_nome,  # alias p/ a tela (hoje?.posto_nome)
        "bateu_entrada": entrada is not None,
        "bateu_saida": saida is not None,
        "entrada": _fmt(entrada),
        "saida": _fmt(saida),
        "proxima_acao": proxima_acao,
        # aliases de compatibilidade com o Meu Espaço (lê proxima_batida / batidas[])
        "proxima_batida": proxima_acao,
        "proxima_label": prox["label"],
        "num_batidas_dia": prox["num_batidas"],
        "jornada_concluida": prox["concluido"],
        "batidas": batidas_lista,
        "total_batidas": len(estado["batidas"]),
    }


# =========================================================================== #
# REEMBOLSO (self-service): solicitar reembolso + listar os meus
# O funcionário adianta a despesa a trabalho e a empresa devolve. A solicitação
# NASCE 'pendente' (aguardando aprovação do DP/financeiro) — o funcionário NÃO
# aprova nem paga. Grava na MESMA tabela reimbursement_requests que o DP lê.
# Segurança: requester_id = user do JWT (1:1 com o employee_id vinculado); a
# listagem filtra por requester_id → o funcionário só vê/cria os DELE, nunca de
# outro. O fluxo de aprovação/pagamento permanece do módulo reimbursement (DP).
# =========================================================================== #


class SolicitarReembolsoRequest(BaseModel):
    """Solicitação de reembolso do funcionário (self-service)."""

    categoria: str = Field(
        default="outros",
        description="Categoria da despesa (transporte, alimentacao, material, saude, ...).",
    )
    valor: Decimal = Field(..., gt=0, description="Valor gasto pelo funcionário (R$).")
    data_despesa: _date = Field(..., description="Data em que a despesa ocorreu.")
    descricao: str = Field(
        ..., min_length=3, max_length=500, description="Motivo/descrição da despesa."
    )
    comprovante_base64: str | None = Field(
        default=None,
        description="Foto/PDF do recibo (base64 ou data-URI). Evidência da despesa.",
    )
    comprovante_nome: str | None = Field(default=None, max_length=200)


async def _condominio_do_reembolso(
    db: AsyncSession, current_user: User
) -> UUID | None:
    """Resolve o condomínio para amarrar a solicitação.

    Usa o condominio do usuário; senão o primeiro condomínio ativo. A coluna é
    nullable — se nenhum for encontrado, retorna None (o DP/admin vê todos).
    """
    cid = getattr(current_user, "condominio_id", None)
    if cid:
        return cid if isinstance(cid, UUID) else UUID(str(cid))
    try:
        from modules.reimbursement.repositories import CondominioRepository

        return await CondominioRepository(db).get_first_active_condominio()
    except Exception:  # noqa: BLE001
        return None


@router.get(
    "/categorias-reembolso",
    summary="Categorias de reembolso disponíveis",
    description="Lista as categorias de despesa (enum) para o dropdown do formulário.",
)
async def categorias_reembolso(
    current_user: User = Depends(get_current_active_user),
) -> Any:
    from modules.reimbursement.models.reimbursement_item import (
        EXPENSE_CATEGORY_LABELS,
        ExpenseCategory,
    )

    return {
        "categorias": [
            {"value": e.value, "label": EXPENSE_CATEGORY_LABELS.get(e, e.value)}
            for e in ExpenseCategory
        ]
    }


@router.get(
    "/meus-reembolsos",
    summary="Meus reembolsos (funcionário logado)",
    description="Lista os reembolsos DO funcionário logado (por requester_id do JWT) "
    "com status, valor, categoria, data e motivo. Nunca mostra de outro funcionário.",
)
async def meus_reembolsos(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    emp = _employee_id(current_user)
    from modules.reimbursement.models.reimbursement_item import (
        EXPENSE_CATEGORY_LABELS,
        ExpenseCategory,
    )
    from modules.reimbursement.schemas import ReimbursementRequestFilter
    from modules.reimbursement.services import ReimbursementService

    svc = ReimbursementService(db)
    # condominio_id=None → não filtra por condomínio; requester_id garante que só
    # vêm os reembolsos DESTE funcionário.
    requests, total = await svc.list_my_requests(
        condominio_id=None,
        requester_id=current_user.id,
        filters=ReimbursementRequestFilter(),
        skip=0,
        limit=200,
    )

    itens: list[dict[str, Any]] = []
    for r in requests:
        ativos = [i for i in (r.items or []) if getattr(i, "is_active", True)]
        primeiro = ativos[0] if ativos else None
        categoria = primeiro.category_type if primeiro else None
        try:
            categoria_label = (
                EXPENSE_CATEGORY_LABELS.get(ExpenseCategory(categoria), categoria)
                if categoria
                else None
            )
        except ValueError:
            categoria_label = categoria
        itens.append(
            {
                "id": str(r.id),
                "code": r.code,
                "status": r.status,
                "valor": float(r.total_amount or 0),
                "valor_aprovado": float(r.approved_amount or 0),
                "valor_pago": float(r.paid_amount or 0),
                "categoria": categoria,
                "categoria_label": categoria_label,
                "data_despesa": str(r.expense_date_start) if r.expense_date_start else None,
                "motivo": r.description or r.title,
                "criado_em": str(r.created_at) if r.created_at else None,
                "rejeicao_motivo": r.rejection_reason,
                "anexos": len(getattr(r, "attachments", []) or []),
            }
        )

    return {"employee_id": emp, "total": total, "reembolsos": itens}


@router.post(
    "/solicitar-reembolso",
    summary="Solicitar reembolso (funcionário logado)",
    description="Cria uma solicitação de reembolso vinculada ao funcionário logado "
    "(requester_id do JWT). Nasce 'pendente' (aguardando DP/financeiro). Aceita o "
    "comprovante (foto/PDF) em base64. O funcionário NÃO aprova nem paga.",
)
async def solicitar_reembolso(
    payload: SolicitarReembolsoRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    emp = _employee_id(current_user)
    from modules.reimbursement.models import ExpenseCategory
    from modules.reimbursement.models.reimbursement_item import EXPENSE_CATEGORY_LABELS
    from modules.reimbursement.schemas import (
        ReimbursementAttachmentCreate,
        ReimbursementItemCreate,
        ReimbursementRequestCreate,
    )
    from modules.reimbursement.services import ReimbursementService

    # Categoria válida (fallback 'outros').
    try:
        categoria = ExpenseCategory(payload.categoria).value
    except ValueError:
        categoria = ExpenseCategory.OUTROS.value
    label = EXPENSE_CATEGORY_LABELS.get(ExpenseCategory(categoria), categoria.title())
    nome = (current_user.name or "Funcionário").strip()

    data = ReimbursementRequestCreate(
        title=f"Reembolso {label} — {nome}"[:200],
        description=payload.descricao,
        expense_date_start=payload.data_despesa,
        expense_date_end=payload.data_despesa,
        notes="Solicitado pelo funcionário via Meu Espaço.",
        items=[
            ReimbursementItemCreate(
                category_type=categoria,
                description=payload.descricao,
                expense_date=payload.data_despesa,
                amount=payload.valor,
                document_type="comprovante",
            )
        ],
    )

    svc = ReimbursementService(db)
    condominio_id = await _condominio_do_reembolso(db, current_user)

    try:
        request = await svc.create_request(condominio_id, current_user.id, data)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Falha ao criar reembolso do funcionário %s", emp)
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"Não foi possível criar o reembolso: {exc}",
        )

    # Comprovante (opcional): decodifica base64 / data-URI e anexa.
    anexado = False
    if payload.comprovante_base64:
        try:
            raw = payload.comprovante_base64
            mime = "image/jpeg"
            ext = ".jpg"
            if raw.startswith("data:"):
                header, _, b64 = raw.partition(",")
                if ":" in header:
                    mime = header.split(":", 1)[1].split(";", 1)[0] or mime
                raw = b64
                if "pdf" in mime:
                    ext = ".pdf"
                elif "png" in mime:
                    ext = ".png"
                elif "webp" in mime:
                    ext = ".webp"
            content = base64.b64decode(raw)
            filename = payload.comprovante_nome or f"comprovante_{request.code}{ext}"
            await svc.add_attachment(
                request_id=request.id,
                data=ReimbursementAttachmentCreate(
                    attachment_type="comprovante",
                    description="Comprovante da despesa (anexado pelo funcionário).",
                ),
                file_content=content,
                original_filename=filename,
                mime_type=mime,
                user_id=current_user.id,
            )
            anexado = True
        except Exception as exc:  # noqa: BLE001
            # Não bloqueia a solicitação: o comprovante pode ser reenviado depois.
            logger.warning(
                "Comprovante do reembolso %s não anexado: %s", request.code, exc
            )

    # Submete → 'pendente' (aguardando DP/financeiro). submit() valida que o
    # solicitante é o próprio funcionário e que há ao menos um item.
    try:
        await svc.submit_request(request.id, current_user.id)
    except ValueError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(exc)
        )

    fresh = await svc.get_request(request.id)
    return {
        "employee_id": emp,
        "id": str(fresh.id),
        "code": fresh.code,
        "status": fresh.status,
        "valor": float(fresh.total_amount or 0),
        "categoria": categoria,
        "categoria_label": label,
        "data_despesa": str(payload.data_despesa),
        "motivo": fresh.description,
        "comprovante_anexado": anexado,
        "mensagem": "Reembolso enviado. Aguardando aprovação do DP/financeiro.",
    }


# ==================== RECONHECIMENTO FACIAL (área do funcionário) ====================
#
# Arquitetura on-device (face-api.js): o NAVEGADOR calcula o descriptor de 128 floats do
# rosto (modelos em /public/models) e compara com a REFERÊNCIA cadastrada. Aqui no portal
# do funcionário (token normal, sem guard de módulo DP) o funcionário: (1) cadastra o rosto
# no onboarding — obrigatório; (2) bate ponto SÓ com match=true (gate rígido do Jordan).
import json as _facial_json


class _FacialEnrollBody(BaseModel):
    descriptor: list[float] = Field(..., min_length=64, max_length=512)
    foto_base64: str | None = None


class _FacialLocation(BaseModel):
    latitude: float
    longitude: float
    accuracy: float = 0.0


class _FacialBatidaBody(BaseModel):
    match: bool
    confidence: float = 0.0
    liveness_check: bool = True
    foto_base64: str | None = None
    location: _FacialLocation | None = None
    punch_type: str | None = None


_PUNCH_SEQ = ["entrada", "saida_almoco", "retorno_almoco", "saida"]
_PUNCH_SEQ_2 = ["entrada", "saida"]
_PUNCH_LABEL = {
    "entrada": "Entrada",
    "saida_almoco": "Saída para o almoço",
    "retorno_almoco": "Volta do almoço",
    "saida": "Saída",
    "concluido": "Jornada concluída",
}


async def _proxima_batida_info(db: AsyncSession, emp: str) -> dict:
    """Próxima batida do funcionário HOJE, considerando a INTRAJORNADA do posto.

    Nº de batidas: 44h (escala) → sempre 4 (entrada/saída-almoço/volta/saída);
    12x36 → 2 (entrada/saída) OU 4, conforme `posts.tem_intervalo_almoco` do posto
    onde ele trabalha. Ex.: Villa Dei Fiore=2, Ideal Flores=4 (decisão do Jordan).
    """
    row = (
        await db.execute(
            _sqltext(
                "SELECT lower(coalesce(e.escala_padrao,'')), "
                "       coalesce(p.tem_intervalo_almoco, false) "
                "FROM employees e LEFT JOIN posts p ON p.id = e.posto_atual_id "
                "WHERE e.id::text = :e"
            ),
            {"e": emp},
        )
    ).first()
    escala = (row[0] if row else "") or ""
    tem_intervalo = bool(row[1]) if row else False
    quatro = ("44" in escala) or tem_intervalo
    seq = _PUNCH_SEQ if quatro else _PUNCH_SEQ_2

    feitas = (
        await db.execute(
            _sqltext(
                "SELECT count(*) FROM gp_clock_punches WHERE employee_id::text = :e "
                "AND (punch_timestamp)::date = (now() AT TIME ZONE 'America/Manaus')::date"
            ),
            {"e": emp},
        )
    ).scalar() or 0
    concluido = feitas >= len(seq)
    tipo = "concluido" if concluido else seq[feitas]
    return {
        "tipo": tipo,
        "label": _PUNCH_LABEL.get(tipo, tipo),
        "concluido": concluido,
        "num_batidas": len(seq),
        "feitas": int(feitas),
    }


@router.post("/facial/cadastrar", status_code=201)
async def facial_cadastrar(
    body: _FacialEnrollBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Cadastra/atualiza o rosto de referência do funcionário (obrigatório no onboarding)."""
    emp = _employee_id(current_user)
    await db.execute(
        _sqltext(
            "UPDATE employees SET face_descriptor = :d, biometria_facial = true, "
            "face_enrolled_at = (now() AT TIME ZONE 'America/Manaus') WHERE id = :eid"
        ),
        {"d": _facial_json.dumps(body.descriptor), "eid": emp},
    )
    await db.commit()
    return {"success": True, "enrolled": True, "employee_id": emp, "dimensoes": len(body.descriptor)}


@router.get("/facial/referencia")
async def facial_referencia(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Descriptor de referência do funcionário (para o app comparar ao vivo)."""
    emp = _employee_id(current_user)
    row = (
        await db.execute(
            _sqltext("SELECT face_descriptor FROM employees WHERE id = :eid"), {"eid": emp}
        )
    ).fetchone()
    descriptor = None
    if row and row[0]:
        try:
            descriptor = _facial_json.loads(row[0])
        except (ValueError, TypeError):
            descriptor = None
    return {"enrolled": bool(descriptor), "employee_id": emp, "descriptor": descriptor}


@router.post("/facial/batida", status_code=201)
async def facial_batida(
    body: _FacialBatidaBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Batida com GATE RÍGIDO facial: só registra com match=true contra a referência."""
    from modules.people_management.ponto.schemas.punch_schemas import (
        FacialSchema,
        GeoLocationSchema,
        PunchCreate,
    )
    from modules.people_management.ponto.services.punch_service import PunchService

    emp = _employee_id(current_user)

    # precisa ter rosto cadastrado
    row = (
        await db.execute(
            _sqltext("SELECT face_descriptor FROM employees WHERE id = :eid"), {"eid": emp}
        )
    ).fetchone()
    if not row or not row[0]:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Rosto não cadastrado. Cadastre seu reconhecimento facial antes de bater o ponto.",
        )

    # GATE: sem match, não bate
    if body.match is not True:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Rosto não reconhecido. A batida só é confirmada com reconhecimento facial.",
        )

    # Tipo é AUTORIDADE do backend (intrajornada do posto → 2 ou 4 batidas/dia).
    # Não confia no punch_type do device p/ o rótulo — evita saída rotulada errado.
    prox = await _proxima_batida_info(db, emp)
    if prox["concluido"]:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="Jornada de hoje já concluída — todas as batidas do dia foram registradas.",
        )
    tipo = prox["tipo"]

    location = None
    if body.location is not None:
        location = GeoLocationSchema(
            latitude=body.location.latitude,
            longitude=body.location.longitude,
            accuracy=body.location.accuracy,
        )
    data = PunchCreate(
        employee_id=str(emp),
        punch_type=tipo,
        location=location,
        facial=FacialSchema(
            match=True, confidence=body.confidence,
            liveness_check=body.liveness_check, foto_base64=body.foto_base64,
        ),
        device_type="mobile",
    )
    result = await PunchService(db).registrar_batida(data)
    await db.commit()
    return {
        "success": True,
        "punch_id": result["punch_id"],
        "punch_type": result.get("punch_type"),
        "punch_timestamp": result.get("punch_timestamp"),
        "status": result.get("status"),
        "facial_match": result.get("facial_match"),
        "facial_confidence": result.get("facial_confidence"),
        "dentro_geofence": result.get("dentro_geofence"),
        "message": "Ponto registrado com reconhecimento facial",
    }
