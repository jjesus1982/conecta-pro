"""Espelho de Ponto — controller (DP).

Rotas sob /people-management/hr/ponto/espelho/*:
  GET  /ponto/espelho/{employee_id}/{mes}/{ano}/pdf   → PDF legal (Portaria 671)
  GET  /ponto/espelho/painel/{mes}/{ano}              → painel de fechamento (DP)
  POST /ponto/espelho/solicitar-homologacao/{mes}/{ano} → envia espelhos fechados p/ assinatura

LÊ o que o motor calculou em `time_sheets` (não recalcula). O gate module:dp é
aplicado automaticamente pelo _gatear_rotas_por_modulo do people_management.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.auth.dependencies import get_current_user
from core.database.session import get_sync_db_dependency

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ponto", tags=["Ponto — Espelho e Homologação"])


def _quem_fechou(current_user: Any) -> str | None:
    """Extrai um identificador legível de quem fechou (auditoria closed_by)."""
    if current_user is None:
        return None
    for attr in ("email", "username", "nome", "name", "id"):
        val = getattr(current_user, attr, None)
        if val:
            return str(val)
    if isinstance(current_user, dict):
        for k in ("email", "username", "nome", "name", "id", "sub"):
            if current_user.get(k):
                return str(current_user[k])
    return None


class FecharMesRequest(BaseModel):
    """Body de POST /ponto/fechar-mes."""

    mes: int
    ano: int
    employee_id: str | None = None
    # Se False, apenas CALCULA (dry-run) e devolve as anomalias — não fecha nada.
    fechar: bool = True
    # Recalcular por cima de um mês já fechado (uso administrativo).
    force: bool = False


# ==================== MOTOR: CÁLCULO / FECHAMENTO / STATUS ====================


@router.post(
    "/fechar-mes",
    summary="Calcular o espelho do mês e fechar os que não têm anomalia aberta",
)
def fechar_mes_ponto(
    body: FecharMesRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_sync_db_dependency),
) -> Any:
    """Calcula o(s) espelho(s) de ponto do mês a partir do dado REAL das batidas e
    grava em `time_sheets`.

    - `employee_id` ausente → processa TODOS os funcionários com batida no mês.
    - Aplica o fechamento DEFINITIVO (status='fechado') apenas nos espelhos SEM
      anomalia aberta. Os que têm anomalia voltam em `bloqueados` e NÃO são fechados.
    - `fechar=false` → só calcula e devolve o diagnóstico (sem fechar).
    """
    from modules.people_management.hr.services.espelho_service import fechar_mes

    try:
        return fechar_mes(
            db,
            body.mes,
            body.ano,
            employee_id=body.employee_id,
            fechar=body.fechar,
            closed_by=_quem_fechou(current_user),
            force=body.force,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/fechamento-status",
    summary="Status de fechamento do ponto por funcionário (calculado/anomalia/fechado/homologado)",
)
def fechamento_status_ponto(
    mes: int = Query(..., ge=1, le=12),
    ano: int = Query(..., ge=2020, le=2100),
    employee_id: str | None = Query(None),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_sync_db_dependency),
) -> Any:
    """Lê `time_sheets` do mês e devolve, por funcionário, se o espelho foi calculado,
    quantas anomalias abertas tem, se está fechado e se já foi homologado (assinado
    pelo funcionário no Meu Espaço)."""
    from modules.people_management.hr.services.espelho_service import fechamento_status

    return fechamento_status(db, mes, ano, employee_id=employee_id)


@router.post(
    "/calcular",
    summary="(Re)calcular o espelho de UM funcionário sem fechar o mês",
)
def calcular_espelho_endpoint(
    employee_id: str = Body(..., embed=True),
    mes: int = Body(..., embed=True),
    ano: int = Body(..., embed=True),
    force: bool = Body(False, embed=True),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_sync_db_dependency),
) -> Any:
    """Roda o motor para um único funcionário (status='calculado'), útil para o
    painel do DP recalcular antes de fechar. Não fecha o mês."""
    from modules.people_management.hr.services.espelho_service import calcular_espelho

    try:
        return calcular_espelho(db, employee_id, mes, ano, force=force)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/espelho/painel/{mes}/{ano}",
    summary="Painel de fechamento de ponto (status por funcionário)",
)
def painel_fechamento_ponto(
    mes: int,
    ano: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_sync_db_dependency),
) -> Any:
    """Status por funcionário do mês: calculado / anomalias / fechado / homologado."""
    from modules.people_management.hr.services.espelho_ponto_service import painel_fechamento

    return painel_fechamento(db, mes, ano)


@router.post(
    "/espelho/solicitar-homologacao/{mes}/{ano}",
    summary="Enviar espelhos fechados para homologação (assinatura do funcionário)",
)
def solicitar_homologacao(
    mes: int,
    ano: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_sync_db_dependency),
) -> Any:
    """Para cada funcionário com espelho FECHADO, cria a solicitação de assinatura
    (idempotente). O espelho passa a aparecer em 'Documentos a assinar' do Meu Espaço."""
    from modules.people_management.hr.services.espelho_ponto_service import (
        solicitar_homologacao_mes,
    )

    return solicitar_homologacao_mes(db, mes, ano)


@router.get(
    "/espelho/{employee_id}/{mes}/{ano}/pdf",
    summary="Baixar espelho de ponto em PDF (padrão-ouro, Portaria 671)",
)
def baixar_espelho_pdf(
    employee_id: str,
    mes: int,
    ano: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_sync_db_dependency),
):
    """Gera o espelho mensal legal a partir do time_sheets já calculado.

    Se o mês estiver FECHADO, garante (idempotente) a solicitação de homologação
    (assinatura do funcionário) e carimba o bloco de autenticidade quando já houver
    assinatura.
    """
    from modules.people_management.hr.services.espelho_ponto_pdf import (
        montar_espelho_ponto_pdf,
    )
    from modules.people_management.hr.services.espelho_ponto_service import (
        garantir_homologacao_espelho,
        ler_espelho,
    )

    esp = ler_espelho(db, employee_id, mes, ano)
    if not esp:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Espelho de ponto de {int(mes):02d}/{ano} ainda não foi calculado para este "
                "funcionário. Rode o cálculo do mês no ponto (motor) antes de emitir o espelho."
            ),
        )

    # Autenticidade: se já houver assinaturas, busca o status para carimbar o bloco.
    signatarios = None
    try:
        from modules.signatures.helpers import status_documento_sync

        stt = status_documento_sync("espelho_ponto", esp["time_sheet_id"])
        if stt:
            signatarios = stt.get("signatarios")
    except Exception:  # noqa: BLE001
        signatarios = None

    pdf = montar_espelho_ponto_pdf(esp, signatarios=signatarios)

    # Mês fechado → garante a solicitação de homologação (assinatura do funcionário).
    garantir_homologacao_espelho(db, esp=esp, pdf_bytes=pdf)

    nome = (esp.get("employee_name") or "colaborador").split()[0].lower()
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="espelho_ponto_{nome}_{int(mes):02d}_{ano}.pdf"'
        },
    )
