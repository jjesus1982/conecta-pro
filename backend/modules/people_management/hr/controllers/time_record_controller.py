"""
Controller de Ponto Eletronico (Time Records) — Departamento Pessoal.

Endpoints completos para gestao de registros de ponto:
- Listagem com filtros e paginacao
- Clock-in / Clock-out
- Lancamento manual (admin/DP)
- Atualizacao e justificativa
- Resumo mensal por funcionario
- Registros diarios
"""

import asyncio
import logging
from datetime import date
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from core.permissions import requer_modulo
from modules.people_management.hr.publishers import publish_ponto_registrado
from modules.people_management.hr.schemas.time_record import (
    ClockOutRequest,
    DailyRecordsResponse,
    TimeRecordCreate,
    TimeRecordListResponse,
    TimeRecordResponse,
    TimeRecordUpdate,
)
from modules.people_management.hr.services.time_record_service import TimeRecordService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/time-records", tags=["DP - Ponto Eletrônico"])


@router.get(
    "",
    summary="Listar Registros de Ponto",
    response_model=TimeRecordListResponse,
    description="Retorna lista paginada de registros de ponto com filtros por funcionário, período e status.",
)
async def list_time_records(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    employee_id: str | None = Query(None, description="Filtro por funcionário"),
    date_from: date | None = Query(None, description="Data inicial (YYYY-MM-DD)"),
    date_to: date | None = Query(None, description="Data final (YYYY-MM-DD)"),
    status: str | None = Query(None, description="regular|falta|atestado|feriado|compensacao|inconsistencia"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Any:
    """Lista registros de ponto com filtros e paginação."""
    service = TimeRecordService(db)
    return await service.list_records(
        employee_id=employee_id,
        date_from=date_from,
        date_to=date_to,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    summary="Lançamento Manual de Ponto",
    response_model=TimeRecordResponse,
    status_code=201,
    description="Retorna lista paginada de registros de ponto com filtros por funcionário, período e status.",
)
async def create_manual_record(
    data: TimeRecordCreate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Cria lançamento manual de ponto (uso por admin/DP)."""
    service = TimeRecordService(db)
    try:
        result = await service.create_manual(
            data=data.model_dump(),
            created_by=str(current_user.id),
        )
    except ValueError as exc:  # dgx t2: competência fechada → 409, não 500
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.commit()
    asyncio.create_task(
        publish_ponto_registrado(
            employee_id=str(getattr(data, "employee_id", "")),
            tipo="manual",
            record_id=str(getattr(result, "id", "")),
        )
    )
    return result


@router.get(
    "/{record_id}",
    summary="Buscar Registro de Ponto",
    response_model=TimeRecordResponse,
    description="Retorna lista paginada de registros de ponto com filtros por funcionário, período e status.",
)
async def get_time_record(
    record_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna detalhes de um registro de ponto."""
    service = TimeRecordService(db)
    record = await service.get_by_id(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Registro de ponto não encontrado")
    return record


# ── Parede de DP no HANDLER: mexer em batida é ato de Departamento Pessoal ─────────────────
#
# ⚠️ P7 (28/09/2026). A leitura de partida era que o PATCH pedia só `CurrentActiveUser` e que
# por isso qualquer colaborador com senha aprovaria documento trabalhista. **Fui medir e não é
# verdade no HTTP**: `modules/people_management/__init__.py:_gatear_rotas_por_modulo` injeta
# `requer_modulo("dp")` em CADA rota do módulo depois do registro. Controle rodado nesta data,
# com token real de `celiane...@gmail.com` (`{self:portal}`):
#
#     GET /api/v1/people-management/hr/time-records  ->  403
#     {"detail":"Acesso negado ao módulo 'dp'. ..."}   (o mesmo token dá 200 em /auth/me)
#
# Então a parede JÁ existia — o arquivo é que não a mostrava, e o handler sozinho não a tinha.
# Declaro aqui de todo jeito, e não é zelo: aquele laço tem DOIS `continue` de isenção, e um
# deles é de ponto (`/people-management/ponto/offline`, o celular do porteiro). O dia em que
# alguém precisar isentar mais uma rota de ponto, a régua desta — que decide aprovação de
# documento trabalhista — não pode depender de um `startswith` num arquivo de registro.
#
# REUSO a MESMA dependency, não escrevo outra: `core.permissions.requer_modulo` passa CEO,
# `all` e `module:dp`; `core.auth.module_scope.user_has_module` (usada no gate de reembolso do
# redesign) passa também `role=='admin'` e `'*'`. São réguas DIFERENTES para a mesma parede, e
# duas réguas sempre acabam decididas pela mais frouxa. Uma fonte só.
_DEP_DP = requer_modulo("dp")


@router.patch(
    "/{record_id}",
    summary="Atualizar/Justificar/Aprovar Registro",
    dependencies=[_DEP_DP],
    response_model=TimeRecordResponse,
    description="Corrige, justifica ou APROVA/REPROVA uma batida. Restrito ao DP; tudo fica em gp_audit_logs.",
)
async def update_time_record(
    record_id: str,
    data: TimeRecordUpdate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Atualiza/justifica/decide um registro de ponto."""
    service = TimeRecordService(db)
    try:
        record = await service.update_record(
            record_id=record_id,
            data=data.model_dump(exclude_unset=True),
            updated_by=str(current_user.id),
        )
    except ValueError as e:  # tipo de batida inválido era 500
        raise HTTPException(status_code=400, detail=str(e))
    if not record:
        raise HTTPException(status_code=404, detail="Registro de ponto não encontrado")
    await db.commit()
    return record


@router.get(
    "/{record_id}/historico",
    summary="Histórico de Observação da Batida",
    dependencies=[_DEP_DP],
    description="Data | Observação | Tipo de toda decisão e correção já feita nesta batida (gp_audit_logs).",
)
async def get_time_record_historico(
    record_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """O «Histórico de Observação» do Sólides, sem tabela nova.

    ⚠️ P7 (28/09/2026): `gp_audit_logs` tinha 88 linhas sobre batida e **zero leitores** — a
    trilha era escrita e nunca lida, o que para quem trabalha é igual a não existir. Esta rota é
    o leitor. Não devolve 404 para batida sem histórico: lista vazia é a resposta honesta
    ("nenhuma observação ainda"), e 404 diria que a batida não existe.
    """
    return {"items": await TimeRecordService(db).get_historico(record_id)}


@router.post(
    "/dia/decidir",
    summary="Aprovar/Reprovar o DIA de um colaborador",
    dependencies=[_DEP_DP],
    description="Decisão do dono: a aprovação é por DIA — aprovar o dia aprova as batidas dele.",
)
async def decidir_dia_time_records(
    current_user: CurrentActiveUser,
    employee_id: str = Query(..., description="Colaborador"),
    dia: date = Query(..., description="Data da BATIDA (YYYY-MM-DD), não a da escala"),
    decisao: str = Query(..., description="approved | rejected | pending"),
    # A observação vem no BODY, não na query, porque é o ÚNICO campo digitado: o ModuleView do
    # redesign manda os campos do formulário em JSON no corpo e o resto na URL da ação (mesmo
    # molde de `rd_action_reembolso_rejeitar`). Declarar como Query faria o textarea chegar vazio
    # e a observação sumir sem erro nenhum — trilha vazia é pior que trilha ausente.
    payload: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Aprova/reprova o dia inteiro — a unidade de conferência que o DP usa.

    ⚠️ P7 (28/09/2026): a tela de ponto era `LIMIT 200 ORDER BY punch_timestamp DESC`, tudo
    misturado, contra **832 dias-pessoa pendentes desde 01/09** (medido). Sem unidade "dia",
    "aprovar cada dia" não é operável — é por isso que esta rota existe em vez de o front fazer
    N PATCHes.

    Não reimplementa nada: delega para `TimeRecordService.decidir_dia`, que chama `update_record`
    por batida — é lá que mora a exigência de autor real e a escrita da trilha. `pending`
    CONTINUA contando na folha; isto é trilha e estado visível, não porta de cálculo.
    """
    observacao = str(payload.get("observacao") or payload.get("motivo") or "").strip()
    # RECUSA em vez de truncar. O `max: 200` que o builder manda no campo é decorativo: o
    # ModuleView do redesign não tem `maxLength` (verificado no componente em 28/09/2026), então
    # o limite só existe aqui. Cortar em 200 em silêncio comeria o final da justificativa de quem
    # escreveu — e o pedaço que se perde é sempre o "porque", que vem no fim da frase.
    if len(observacao) > 200:
        raise HTTPException(
            status_code=400,
            detail=f"A observação tem {len(observacao)} caracteres; o limite é 200. "
            "Encurte o texto — nada é cortado sem você ver.",
        )
    if decisao == "rejected" and len(observacao) < 3:
        # Simetria com `rd_action_reembolso_rejeitar`: recusar sem motivo é a decisão que a pessoa
        # afetada mais vai contestar, e é a única que não se explica sozinha depois.
        raise HTTPException(status_code=400, detail="Informe o motivo da reprovação (mín. 3 caracteres).")
    try:
        r = await TimeRecordService(db).decidir_dia(
            employee_id=employee_id,
            dia=dia.isoformat(),
            decisao=decisao,
            observacao=observacao,
            updated_by=str(current_user.id),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    if not r["batidas"]:
        return {"ok": True, "message": "Nada a decidir neste dia (já decidido ou sem batida).", **r}
    return {"ok": True, "message": f"{r['batidas']} batida(s) do dia {dia:%d/%m} — {decisao}.", **r}
