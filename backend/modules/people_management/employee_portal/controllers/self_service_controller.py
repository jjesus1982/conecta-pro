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
from datetime import date as _date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi import status as http_status
from pydantic import BaseModel, Field
from sqlalchemy import text as _sqltext
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
                "SELECT punch_id, punch_type, punch_timestamp, dentro_geofence, "
                "distancia_posto_metros, foto_capturada_url, posto_nome "
                "FROM gp_clock_punches "
                "WHERE employee_id::text = :e AND punch_timestamp::date = :today "
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

    # 1. Descobrir o posto atual (forçado ou pela alocação ativa).
    posto_id = payload.posto_id
    posto_nome = None
    if posto_id:
        prow = (
            await db.execute(
                _sqltext("SELECT name FROM posts WHERE id::text = :p LIMIT 1"),
                {"p": str(posto_id)},
            )
        ).first()
        posto_nome = prow[0] if prow else None
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

    proxima_acao = "saida" if estado["entrada_aberta"] else "entrada"
    if entrada and saida and not estado["entrada_aberta"]:
        proxima_acao = "concluido"

    return {
        "employee_id": emp,
        "data": str(_date.today()),
        "posto_atual": {"posto_id": posto_id, "posto_nome": posto_nome},
        "bateu_entrada": entrada is not None,
        "bateu_saida": saida is not None,
        "entrada": _fmt(entrada),
        "saida": _fmt(saida),
        "proxima_acao": proxima_acao,
        "total_batidas": len(estado["batidas"]),
    }
