"""Controller de Ponto Eletronico — rotas FastAPI com persistencia no banco."""

import asyncio
import os
from datetime import date
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from core.auth.dependencies import CurrentActiveUser, get_current_user
from core.database.session import get_db, get_sync_db_dependency

from ..publishers import publish_batida_registrada, publish_espelho_fechado, publish_falta_confirmada
from ..schemas.dashboard_schemas import (
    AjusteRequest,
    BancoHorasResponse,
    ColaboradorSemEscalaResponse,
    DashboardPontoResponse,
    InconsistenciaResumoResponse,
    SyncSolidesRequest,
    SyncSolidesResponse,
)
from ..schemas.punch_schemas import (
    GeoLocationSchema,
    JustificationCreate,
    JustificationResponse,
    JustificationReview,
    MonthlyClosingResponse,
    PunchCreate,
    PunchResponse,
    PunchSyncRequest,
    PunchSyncResponse,
)
from ..services import dashboard_service
from ..services.folha_pdf_service import PontoFolhaPDFService
from ..services.punch_service import PunchService

router = APIRouter(prefix="/ponto", tags=["Ponto Eletronico"])


# ==================== BATIDA E ESPELHO (async, banco real) ====================


@router.post("/batida", response_model=PunchResponse, status_code=201)
async def registrar_batida(
    data: PunchCreate,
    db: AsyncSession = Depends(get_db),
) -> PunchResponse:
    """Registra uma batida de ponto (entrada, saida, almoco)."""
    service = PunchService(db)
    result = await service.registrar_batida(data)
    asyncio.create_task(
        publish_batida_registrada(
            punch_id=str(result["punch_id"]),
            employee_id=str(result["employee_id"]),
            funcionario_nome="",
            punch_type=result.get("punch_type") or "entrada",
            punch_timestamp=str(result.get("punch_timestamp") or ""),
            latitude=getattr(data, "latitude", None),
            longitude=getattr(data, "longitude", None),
        )
    )
    return PunchResponse(
        punch_id=result["punch_id"],
        employee_id=result["employee_id"],
        punch_type=result.get("punch_type"),
        punch_timestamp=result.get("punch_timestamp"),
        status=result.get("status"),
        facial_match=result.get("facial_match"),
        facial_confidence=result.get("facial_confidence"),
        dentro_geofence=result.get("dentro_geofence"),
        distancia_posto_metros=result.get("distancia_posto_metros"),
        is_offline=result.get("is_offline", False),
        message="Ponto registrado com sucesso",
    )


async def _resolve_employee_id(db: AsyncSession, current_user: Any) -> str:
    """Resolve o employee_id (UUID) do usuário autenticado pelo e-mail."""
    user_email = getattr(current_user, "email", None)
    if not user_email:
        raise HTTPException(status_code=400, detail="Usuário sem e-mail vinculado")
    row = (
        await db.execute(
            text("SELECT id FROM employees WHERE email = :email LIMIT 1"),
            {"email": user_email},
        )
    ).fetchone()
    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"Funcionário não encontrado para o e-mail {user_email}. Verifique se o cadastro do funcionário usa o mesmo e-mail do login.",
        )
    return str(row[0])


_PUNCH_SEQUENCE = ["entrada", "saida_almoco", "retorno_almoco", "saida"]


async def _next_punch_type(db: AsyncSession, employee_id: str) -> str:
    """Detecta o próximo tipo de batida com base nas batidas de hoje."""
    today = date.today()
    rows = (
        await db.execute(
            text(
                "SELECT punch_type FROM gp_clock_punches "
                "WHERE employee_id = :eid AND DATE((punch_timestamp)) = :today "
                "ORDER BY punch_timestamp ASC"
            ),
            {"eid": employee_id, "today": today},
        )
    ).fetchall()
    count = len(rows)
    if count >= len(_PUNCH_SEQUENCE):
        return "saida"
    return _PUNCH_SEQUENCE[count]


@router.post("/batida/me", response_model=PunchResponse, status_code=201)
async def registrar_batida_me(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    latitude: float | None = Query(None),
    longitude: float | None = Query(None),
    punch_type: str | None = Query(None, description="entrada|saida_almoco|retorno_almoco|saida"),
) -> PunchResponse:
    """Registra batida do funcionário autenticado — resolve employee e tipo automaticamente."""
    employee_id = await _resolve_employee_id(db, current_user)
    tipo = punch_type or await _next_punch_type(db, employee_id)

    location = None
    if latitude is not None and longitude is not None:
        location = GeoLocationSchema(latitude=latitude, longitude=longitude)

    data = PunchCreate(
        employee_id=str(employee_id),
        punch_type=tipo,
        location=location,
        device_type="web",
    )
    service = PunchService(db)
    result = await service.registrar_batida(data)
    await db.commit()
    return PunchResponse(
        punch_id=result["punch_id"],
        employee_id=result["employee_id"],
        punch_type=result.get("punch_type"),
        punch_timestamp=result.get("punch_timestamp"),
        status=result.get("status"),
        facial_match=result.get("facial_match"),
        facial_confidence=result.get("facial_confidence"),
        dentro_geofence=result.get("dentro_geofence"),
        distancia_posto_metros=result.get("distancia_posto_metros"),
        is_offline=False,
        message=f"Ponto registrado: {tipo}",
    )


@router.get("/batidas/me")
async def get_batidas_me(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retorna as batidas de hoje do funcionário autenticado."""
    try:
        employee_id = await _resolve_employee_id(db, current_user)
        today = date.today().isoformat()
        service = PunchService(db)
        batidas = await service.get_batidas_dia(employee_id, today)
        return {"employee_id": employee_id, "date": today, "batidas": batidas}
    except HTTPException:
        return {"employee_id": None, "date": date.today().isoformat(), "batidas": []}


@router.post("/sync", response_model=PunchSyncResponse, status_code=201)
async def sync_offline_punches(
    data: PunchSyncRequest,
    db: AsyncSession = Depends(get_db),
) -> PunchSyncResponse:
    """Sincroniza batidas feitas em modo offline."""
    service = PunchService(db)
    result = await service.sync_offline_punches(data.punches)
    return PunchSyncResponse(**result)


@router.get("/batidas/{employee_id}")
async def get_batidas_dia(
    employee_id: str,
    data: str = Query(..., description="Data no formato YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retorna batidas de um funcionario em um dia."""
    service = PunchService(db)
    batidas = await service.get_batidas_dia(employee_id, data)
    return {"employee_id": employee_id, "date": data, "punches": batidas}


@router.get("/espelho/{employee_id}")
async def get_espelho_mensal(
    employee_id: str,
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2020),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retorna espelho de ponto mensal."""
    service = PunchService(db)
    try:
        return await service.get_espelho_mensal(employee_id, month, year)
    except ValueError as e:
        # [Ponto Ciclo3 - Achado 3] Funcionário inexistente => 404, igual ao banco-horas
        # (antes devolvia 200 com espelho fantasma -180h).
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/justificativa", response_model=JustificationResponse, status_code=201)
async def criar_justificativa(
    data: JustificationCreate,
    db: AsyncSession = Depends(get_db),
) -> JustificationResponse:
    """Cria justificativa de atraso ou falta."""
    service = PunchService(db)
    result = await service.criar_justificativa(data)
    return JustificationResponse(
        justification_id=result["justification_id"],
        employee_id=result["employee_id"],
        type=result["type"],
        reason=result["reason"],
        category=result["category"],
        status=result["status"],
        created_at=result["created_at"],
    )


@router.put("/justificativa/{justification_id}/revisar")
async def revisar_justificativa(
    justification_id: str,
    data: JustificationReview,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Aprova ou rejeita uma justificativa."""
    service = PunchService(db)
    try:
        result = await service.revisar_justificativa(
            justification_id,
            data.action,
            data.reviewer_id,
            data.notes,
        )
        # P5: hook falta confirmada quando justificativa de falta é aprovada
        if data.action in ("aprovar", "approve") and result.get("type") in ("falta", "FALTA"):
            asyncio.create_task(
                publish_falta_confirmada(
                    employee_id=str(result.get("employee_id", "")),
                    funcionario_nome=result.get("funcionario_nome", ""),
                    data=str(result.get("data", "")),
                    justificada=True,
                    cliente_id=result.get("cliente_id"),
                )
            )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/justificativas/pendentes")
async def get_justificativas_pendentes(
    employee_id: int | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Lista justificativas pendentes de aprovacao."""
    service = PunchService(db)
    return await service.get_justificativas_pendentes(employee_id)


@router.post("/fechamento", response_model=MonthlyClosingResponse, status_code=201)
async def fechar_mes(
    employee_id: str,  # [Ponto loop] era int — employees têm UUID; gp_monthly_closings.employee_id migrado p/ String
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2020),
    fechado_por: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> MonthlyClosingResponse:
    """Fecha o ponto mensal de um funcionario."""
    service = PunchService(db)
    result = await service.fechar_mes(employee_id, month, year, fechado_por)
    asyncio.create_task(
        publish_espelho_fechado(
            employee_id=str(employee_id),
            funcionario_nome="",
            competencia=f"{year}-{month:02d}",
            total_horas=result.get("total_horas", 0),
            horas_extras=result.get("horas_extras", 0),
            faltas=result.get("faltas", 0),
        )
    )
    return MonthlyClosingResponse(**result)


@router.post("/fechamento-mes", status_code=201)
async def fechar_mes_todos(
    payload: dict,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Fecha o ponto mensal de TODOS os funcionários ativos (tela Fechamento Mensal).
    Recebe {mes, ano, fechado_por?}. Fecha cada um; retorna resumo (fechados/erros)."""
    from fastapi import HTTPException
    from sqlalchemy import text as _text

    _mes = payload.get("mes") or payload.get("month")
    _ano = payload.get("ano") or payload.get("year")
    if _mes is None or _ano is None:
        raise HTTPException(status_code=422, detail="Campos 'mes' e 'ano' são obrigatórios.")
    mes, ano = int(_mes), int(_ano)
    fechado_por = payload.get("fechado_por") or "sistema"
    rows = (await db.execute(_text("SELECT CAST(id AS text) FROM employees WHERE status='ativo'"))).fetchall()
    service = PunchService(db)
    fechados, erros = 0, []
    for (eid,) in rows:
        try:
            await service.fechar_mes(eid, mes, ano, fechado_por)
            fechados += 1
        except Exception as e:  # noqa: BLE001
            erros.append({"employee_id": eid, "erro": str(e)[:120]})
    return {"ok": True, "competencia": f"{ano}-{mes:02d}", "total": len(rows),
            "fechados": fechados, "erros": len(erros), "detalhe_erros": erros[:5]}


@router.get("/fechamento/status", summary="Status de fechamento por competência (estado REAL)")
async def fechamento_status(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2020),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Estado REAL de fechamento de uma competência a partir de gp_monthly_closings.

    Retorna quantos colaboradores estão com o ponto fechado no mês/ano e deriva
    o status da competência: 'fechado' se todos ativos fecharam, 'em_revisao' se
    parte fechou, 'aberto' se nenhum. NUNCA hardcoded.
    """
    total_ativos = (
        await db.execute(text("SELECT COUNT(*) FROM employees WHERE status='ativo'"))
    ).scalar() or 0
    # COUNT(DISTINCT employee_id): linhas duplicadas legadas (mesmo funcionário fechado
    # 2x) não podem estourar o total (>100%). fechados <= colaboradores sempre.
    row = (
        await db.execute(
            text(
                "SELECT COUNT(DISTINCT employee_id) FILTER (WHERE fechado IS TRUE) AS fechados, "
                "COUNT(*) AS registros "
                "FROM gp_monthly_closings WHERE month = :m AND year = :y"
            ),
            {"m": month, "y": year},
        )
    ).first()
    fechados = int(row[0]) if row else 0
    if total_ativos > 0 and fechados >= total_ativos:
        status = "fechado"
    elif fechados > 0:
        status = "em_revisao"
    else:
        status = "aberto"
    return {
        "month": month,
        "year": year,
        "status": status,
        "colaboradores": int(total_ativos),
        "fechados": fechados,
        "pendencias": max(0, int(total_ativos) - fechados),
    }


# ==================== DASHBOARD E RELATORIOS (sync, dados reais) ====================


@router.get(
    "/dashboard",
    response_model=DashboardPontoResponse,
    summary="Dashboard gerencial do ponto",
)
async def ponto_dashboard(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_sync_db_dependency),
) -> DashboardPontoResponse:
    """Visao gerencial com dados reais: presenca, inconsistencias, banco de horas."""
    data = dashboard_service.get_dashboard(db)
    return DashboardPontoResponse(**data)


@router.get(
    "/relatorio/inconsistencias",
    response_model=InconsistenciaResumoResponse,
    summary="Relatorio de inconsistencias CCT",
)
async def relatorio_inconsistencias(
    current_user=Depends(get_current_user),
    periodo_inicio: str | None = Query(None, description="YYYY-MM-DD"),
    periodo_fim: str | None = Query(None, description="YYYY-MM-DD"),
    db: Session = Depends(get_sync_db_dependency),
) -> InconsistenciaResumoResponse:
    """Analisa inconsistencias usando regras CCT 2026 SINDECOMPRESTS."""
    data = dashboard_service.get_inconsistencias(db, periodo_inicio, periodo_fim)
    return InconsistenciaResumoResponse(**data)


@router.get(
    "/banco-horas/{employee_id}",
    response_model=BancoHorasResponse,
    summary="Saldo banco de horas",
)
async def banco_horas(
    employee_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_sync_db_dependency),
) -> BancoHorasResponse:
    """Retorna saldo de banco de horas com prazo CCT (6 meses)."""
    data = dashboard_service.get_banco_horas(db, employee_id)
    if "error" in data:
        raise HTTPException(status_code=404, detail=data["error"])
    return BancoHorasResponse(**data)


@router.post(
    "/sincronizar-solides",
    response_model=SyncSolidesResponse,
    summary="Sincronizar ponto com Solides Tangerino",
    status_code=201,
)
async def sincronizar_solides(
    current_user=Depends(get_current_user),
    request: SyncSolidesRequest = Body(default=SyncSolidesRequest()),
    db: Session = Depends(get_sync_db_dependency),
) -> SyncSolidesResponse:
    """Importa registros de ponto do Solides Tangerino."""
    data = dashboard_service.sync_solides_ponto(db, request.periodo_inicio, request.periodo_fim)
    return SyncSolidesResponse(**data)


@router.post("/sync-escalas", summary="Sincronizar escalas de trabalho do Sólides", status_code=201)
async def sync_escalas(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_sync_db_dependency),
) -> dict[str, Any]:
    """Sincroniza escalas de trabalho do Sólides para employees.escala_padrao."""
    return dashboard_service.sync_escalas_from_solides(db)


@router.post("/ajuste", summary="Ajuste manual de ponto pelo DP", status_code=201)
async def ajuste_ponto(
    request: AjusteRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_sync_db_dependency),
) -> dict[str, Any]:
    """Registra ajuste manual de ponto (somente DP)."""
    return dashboard_service.registrar_ajuste(db, request.model_dump())


@router.get(
    "/colaboradores-sem-escala",
    response_model=list[ColaboradorSemEscalaResponse],
    summary="Colaboradores sem escala definida",
)
async def colaboradores_sem_escala(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_sync_db_dependency),
) -> list[ColaboradorSemEscalaResponse]:
    """Lista colaboradores ativos sem escala — necessitam correcao."""
    items = dashboard_service.get_colaboradores_sem_escala(db)
    return [ColaboradorSemEscalaResponse(**i) for i in items]


# ==================== FOLHA DE PONTO PDF ====================


@router.post(
    "/folha-pdf/{employee_id}",
    summary="Gerar folha de ponto HTML por funcionário/mês",
    status_code=201,
)
async def gerar_folha_pdf(
    employee_id: str,
    mes_ref: str = Query(..., description="Mês de referência no formato MM.YYYY"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_sync_db_dependency),
) -> dict[str, Any]:
    """Gera HTML de folha de ponto a partir das batidas em gp_clock_punches."""
    svc = PontoFolhaPDFService(db)
    try:
        return svc.gerar_folha_pdf(employee_id, mes_ref)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get(
    "/folha-pdf/{employee_id}/download",
    summary="Download da folha de ponto HTML",
)
async def download_folha_pdf(
    employee_id: str,
    mes_ref: str = Query(..., description="Mês de referência no formato MM.YYYY"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_sync_db_dependency),
) -> Any:
    """Serve o arquivo HTML da folha de ponto como download."""
    import re
    from pathlib import Path

    from fastapi.responses import FileResponse

    if not re.match(r"^(0[1-9]|1[0-2])\.\d{4}$", mes_ref):
        raise HTTPException(status_code=422, detail="mes_ref inválido. Formato: MM.YYYY")

    storage = Path("/app/uploads/ponto") / str(employee_id) / mes_ref
    arquivos = list(storage.glob("FolhaPonto_*.html")) if storage.exists() else []

    if not arquivos:
        # Gerar on-demand se ainda não existe
        svc = PontoFolhaPDFService(db)
        try:
            result = svc.gerar_folha_pdf(employee_id, mes_ref)
            filepath = Path(result["arquivo_path"])
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
    else:
        filepath = arquivos[0]

    return FileResponse(
        path=str(filepath),
        media_type="text/html",
        filename=filepath.name,
        headers={"Content-Disposition": f'attachment; filename="{filepath.name}"'},
    )


# ── Painel de completude do onboarding (DP) — rollout do ponto próprio 01/08 ──
_ONBOARDING_CAMPOS = {
    "telefone": "Telefone", "cep": "CEP", "logradouro": "Endereço", "bairro": "Bairro",
    "cidade": "Cidade", "nome_mae": "Nome da mãe", "naturalidade": "Naturalidade",
    "nacionalidade": "Nacionalidade", "rg": "RG", "estado_civil": "Estado civil", "pis": "PIS",
}


@router.get("/onboarding/completude", summary="Completude do cadastro (onboarding) por funcionário — painel do DP")
async def onboarding_completude(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Lista os funcionários ativos e quantos campos obrigatórios do onboarding já têm
    preenchidos (fonte: employees). Serve o painel do DP para acompanhar o rollout de
    01/08 — quem já completou e quem falta. Somente leitura."""
    cols = ", ".join(_ONBOARDING_CAMPOS.keys())
    rows = (
        await db.execute(
            text(
                f"SELECT id::text, nome, email, {cols} "
                "FROM employees WHERE status = 'ativo' ORDER BY nome"
            )
        )
    ).mappings().all()
    total_campos = len(_ONBOARDING_CAMPOS)
    itens = []
    completos = 0
    for r in rows:
        faltam = [lbl for c, lbl in _ONBOARDING_CAMPOS.items() if not str(r.get(c) or "").strip()]
        ok = total_campos - len(faltam)
        if not faltam:
            completos += 1
        itens.append({
            "employee_id": r["id"],
            "nome": r["nome"],
            "email": r["email"],
            "campos_ok": ok,
            "total_campos": total_campos,
            "pct": round(ok * 100 / total_campos),
            "completo": not faltam,
            "faltam": faltam,
        })
    return {
        "total_funcionarios": len(itens),
        "completos": completos,
        "pendentes": len(itens) - completos,
        "pct_medio": round(sum(i["pct"] for i in itens) / len(itens)) if itens else 0,
        "modo_transicao": os.getenv("PONTO_ONBOARDING_BLOQUEANTE", "false").lower() != "true",
        "funcionarios": itens,
    }
