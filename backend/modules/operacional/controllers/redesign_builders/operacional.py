"""Operacional (T1) — delega ao _build_operacional e ESTENDE com telas de LEITURA
(presença ao vivo, escalas, turnos, reembolsos). Operacional é curado pelo Jordan →
SÓ visibilidade, NUNCA escreve/altera escala/alocação. Reembolso é read-only (sem aprovar/pagar)."""
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text as _sqltext

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.operacional.controllers.redesign_data_controller import (
    IC, S, _build_operacional, _fmtdate, _helpers, _scalar, b, brl, doc, initials, t,
)

SLUG = "operacional"

router = APIRouter()


def _usuario_e_admin(current_user) -> bool:
    role = (getattr(current_user, "role", "") or "").lower()
    perms = getattr(current_user, "permissions", None) or []
    return role in ("admin", "super_admin", "administrador") or "*" in perms or "all" in perms


async def _exige_escopo_operacional(db, current_user, employee_id: str, acao: str) -> None:
    """Parede de EQUIPE: supervisor/gerente operacional só age sobre a força operacional
    (colaborador alocado a posto ativo). Admin (Jordan/Pyetra) age sobre todos."""
    if _usuario_e_admin(current_user):
        return
    op = (await db.execute(_sqltext(
        "SELECT 1 FROM allocations a JOIN posts p ON p.id=a.post_id "
        "WHERE a.employee_id::text=:e AND coalesce(a.is_active,true) AND coalesce(p.is_active,true) LIMIT 1"),
        {"e": employee_id})).first()
    if not op:
        raise HTTPException(status_code=403,
                            detail=f"Fora do seu escopo operacional — só é possível {acao} (colaborador alocado a posto ativo).")


@router.post("/action/medida-administrativa")
async def rd_action_medida_administrativa(current_user: CurrentActiveUser, payload: dict = Body(...),
                                          db=Depends(get_db)) -> dict:
    """Cria medida disciplinar REAL via DisciplinaryService (reuso; validação CLT no service).
    Humano-operado (CurrentActiveUser). Nome/CPF resolvidos do employee_id — nunca fabricados.
    Escrita operacional → passa pelo op_write (idempotência)."""
    from datetime import date as _date

    from core.auth import get_tenant_id
    from modules.operacional.controllers.redesign_write_gate import GateError, op_write
    from modules.operacional.disciplinary.schemas.disciplinary_schemas import DisciplinaryActionCreate
    from modules.operacional.disciplinary.services import get_disciplinary_service

    emp_id = (payload.get("employee_id") or "").strip()
    if not emp_id:
        raise HTTPException(status_code=400, detail="Selecione o colaborador.")
    desc = (payload.get("reason_description") or "").strip()
    if len(desc) < 10:
        raise HTTPException(status_code=400, detail="A descrição do motivo precisa de ao menos 10 caracteres.")
    emp = (await db.execute(_sqltext(
        "SELECT nome, coalesce(cpf,'') FROM employees WHERE id::text=:i"), {"i": emp_id})).first()
    if not emp:
        raise HTTPException(status_code=400, detail="Colaborador não encontrado.")
    await _exige_escopo_operacional(db, current_user, emp_id,
                                    "aplicar medida a colaborador da sua equipe operacional")
    cpf_digits = "".join(ch for ch in (emp[1] or "") if ch.isdigit())
    if len(cpf_digits) < 11:
        raise HTTPException(status_code=400, detail=f"Colaborador '{emp[0]}' sem CPF cadastrado — regularize antes de aplicar medida.")
    try:
        data = DisciplinaryActionCreate(
            action_type=payload.get("action_type") or "advertencia_escrita",
            employee_id=emp_id,
            employee_name=emp[0] or "—",
            employee_cpf=cpf_digits,
            reason_category=payload.get("reason_category") or "outros",
            reason_description=desc,
            incident_date=payload.get("incident_date") or _date.today().isoformat(),
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Dados inválidos: {e}")
    svc = get_disciplinary_service(db)
    tenant_id = get_tenant_id(current_user)

    async def _write():
        return await svc.create(data=data, tenant_id=str(tenant_id), created_by=str(current_user.id))

    try:
        action = await op_write(db, real_write=_write,
                                idempotency_key=f"medida:{emp_id}:{data.incident_date}:{data.reason_category}")
    except GateError as ge:
        raise HTTPException(status_code=400, detail=str(ge))
    return {"ok": True, "id": str(action.id), "code": getattr(action, "code", None),
            "message": "Medida disciplinar registrada (rascunho)"}


async def _medida_gate(db, action_id, coro_factory, ok_status):
    """Choke-point das ações de fluxo da medida: valida id, roteia pelo op_write, devolve status REAL."""
    from fastapi import HTTPException

    from modules.operacional.controllers.redesign_write_gate import GateError, op_write
    if not (action_id or "").strip():
        raise HTTPException(status_code=400, detail="Selecione a medida.")
    try:
        res = await op_write(db, real_write=coro_factory)
    except GateError as ge:
        raise HTTPException(status_code=400, detail=str(ge))
    return {"ok": True, "id": str(getattr(res, "id", action_id)),
            "status": str(getattr(res, "status", ok_status)), "message": f"Medida {ok_status}"}


@router.post("/action/medida-submeter")
async def rd_action_medida_submeter(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    from core.auth import get_tenant_id
    from modules.operacional.disciplinary.services import get_disciplinary_service
    aid = (payload.get("action_id") or "").strip()
    svc = get_disciplinary_service(db)
    tid = get_tenant_id(current_user)
    return await _medida_gate(db, aid,
        lambda: svc.submit_for_approval(action_id=aid, tenant_id=str(tid), submitted_by=str(current_user.id),
                                        notes=(payload.get("notes") or None)), "pendente_aprovacao")


@router.post("/action/medida-aprovar")
async def rd_action_medida_aprovar(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    from core.auth import get_tenant_id
    from modules.operacional.disciplinary.schemas.disciplinary_schemas import ApproveRequest
    from modules.operacional.disciplinary.services import get_disciplinary_service
    aid = (payload.get("action_id") or "").strip()
    svc = get_disciplinary_service(db)
    tid = get_tenant_id(current_user)
    req = ApproveRequest(notes=(payload.get("notes") or None), application_date=None)
    return await _medida_gate(db, aid,
        lambda: svc.approve(action_id=aid, tenant_id=str(tid), approved_by=str(current_user.id), request=req), "aprovada")


@router.post("/action/medida-rejeitar")
async def rd_action_medida_rejeitar(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    from fastapi import HTTPException

    from core.auth import get_tenant_id
    from modules.operacional.disciplinary.schemas.disciplinary_schemas import RejectRequest
    from modules.operacional.disciplinary.services import get_disciplinary_service
    aid = (payload.get("action_id") or "").strip()
    reason = (payload.get("reason") or "").strip()
    if len(reason) < 10:
        raise HTTPException(status_code=400, detail="O motivo da rejeição precisa de ao menos 10 caracteres.")
    svc = get_disciplinary_service(db)
    tid = get_tenant_id(current_user)
    req = RejectRequest(reason=reason)
    return await _medida_gate(db, aid,
        lambda: svc.reject(action_id=aid, tenant_id=str(tid), rejected_by=str(current_user.id), request=req), "rejeitada")


@router.post("/action/medida-documento")
async def rd_action_medida_documento(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    from fastapi import HTTPException

    from core.auth import get_tenant_id
    from modules.operacional.disciplinary.services import get_disciplinary_service
    aid = (payload.get("action_id") or "").strip()
    if not aid:
        raise HTTPException(status_code=400, detail="Selecione a medida.")
    svc = get_disciplinary_service(db)
    try:
        res = await svc.generate_document(action_id=aid, tenant_id=str(get_tenant_id(current_user)), request=None)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Falha ao gerar documento: {e}")
    body = res if isinstance(res, dict) else {"document_text": getattr(res, "document_text", None) or str(res)}
    return {"ok": True, "message": "Documento gerado", **body}


async def _scale_action(db, scale_id, coro_factory, ok_status):
    """Choke-point do ciclo de escala. Reflete status REAL; None do repo = estado inválido."""
    from fastapi import HTTPException

    from modules.operacional.controllers.redesign_write_gate import GateError, op_write
    if not (scale_id or "").strip():
        raise HTTPException(status_code=400, detail="Selecione a escala.")
    try:
        res = await op_write(db, real_write=coro_factory)
    except GateError as ge:
        raise HTTPException(status_code=400, detail=str(ge))
    if res is None:
        raise HTTPException(status_code=400, detail="Escala não encontrada ou em estado inválido para esta ação.")
    return {"ok": True, "id": str(getattr(res, "id", scale_id)),
            "status": str(getattr(res, "status", ok_status)), "message": f"Escala {ok_status}"}


@router.post("/action/escala-submeter")
async def rd_action_escala_submeter(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    import uuid as _uuid

    from fastapi import HTTPException

    from modules.operacional.controllers.scale_controller import submit_scale_for_approval
    aid = (payload.get("scale_id") or "").strip()
    try:
        _sid = _uuid.UUID(aid)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Selecione a escala.")
    return await _scale_action(db, aid,
        lambda: submit_scale_for_approval(scale_id=_sid, current_user=current_user, db=db), "enviada para aprovação")


@router.post("/action/escala-aprovar")
async def rd_action_escala_aprovar(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    from modules.operacional.repositories.scale_repository import ScaleRepository
    aid = (payload.get("scale_id") or "").strip()
    repo = ScaleRepository(db)
    return await _scale_action(db, aid,
        lambda: repo.approve(aid, str(current_user.id), (payload.get("notes") or None)), "aprovada")


@router.post("/action/escala-rejeitar")
async def rd_action_escala_rejeitar(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    from fastapi import HTTPException

    from modules.operacional.repositories.scale_repository import ScaleRepository
    aid = (payload.get("scale_id") or "").strip()
    reason = (payload.get("reason") or "").strip()
    if len(reason) < 10:
        raise HTTPException(status_code=400, detail="O motivo da rejeição precisa de ao menos 10 caracteres.")
    repo = ScaleRepository(db)
    return await _scale_action(db, aid,
        lambda: repo.reject(aid, str(current_user.id), reason, (payload.get("notes") or None)), "rejeitada")


@router.post("/action/escala-publicar")
async def rd_action_escala_publicar(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    from modules.operacional.repositories.scale_repository import ScaleRepository
    aid = (payload.get("scale_id") or "").strip()
    repo = ScaleRepository(db)
    return await _scale_action(db, aid,
        lambda: repo.publish(aid, str(current_user.id)), "publicada")


async def _entry_gate(db, entry_id, coro_factory, ok_status, noun="registro"):
    """Choke-point genérico de ação sobre um registro por id. Reflete status REAL."""
    from fastapi import HTTPException

    from modules.operacional.controllers.redesign_write_gate import GateError, op_write
    if not (entry_id or "").strip():
        raise HTTPException(status_code=400, detail=f"Selecione o {noun}.")
    try:
        res = await op_write(db, real_write=coro_factory)
    except GateError as ge:
        raise HTTPException(status_code=400, detail=str(ge))
    if res is None:
        raise HTTPException(status_code=400, detail=f"{noun.capitalize()} não encontrado ou em estado inválido.")
    return {"ok": True, "id": str(getattr(res, "id", entry_id)),
            "status": str(getattr(res, "status", ok_status)), "message": f"Lançamento {ok_status}"}


@router.post("/action/banco-horas-aprovar")
async def rd_action_banco_horas_aprovar(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    from modules.operacional.repositories.time_bank_repository import TimeBankRepository
    eid = (payload.get("entry_id") or "").strip()
    repo = TimeBankRepository(db)
    return await _entry_gate(db, eid,
        lambda: repo.approve(eid, str(current_user.id), (payload.get("notes") or None)), "approved", "lançamento")


@router.post("/action/banco-horas-rejeitar")
async def rd_action_banco_horas_rejeitar(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    from fastapi import HTTPException

    from modules.operacional.repositories.time_bank_repository import TimeBankRepository
    eid = (payload.get("entry_id") or "").strip()
    reason = (payload.get("reason") or "").strip()
    if len(reason) < 5:
        raise HTTPException(status_code=400, detail="Informe o motivo da rejeição (mín. 5 caracteres).")
    repo = TimeBankRepository(db)
    return await _entry_gate(db, eid,
        lambda: repo.reject(eid, reason, str(current_user.id)), "rejected", "lançamento")


@router.post("/action/substituicao-confirmar")
async def rd_action_substituicao_confirmar(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    from fastapi import HTTPException

    from modules.operacional.repositories.substitution_repository import SubstitutionRepository
    sid = (payload.get("substitution_id") or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="Selecione a substituição.")
    row = (await db.execute(_sqltext(
        "SELECT substitute_employee_id FROM substitutions WHERE id::text=:i"), {"i": sid})).first()
    if not row or not row[0]:
        raise HTTPException(status_code=400, detail="Substituição sem substituto definido — defina o substituto primeiro.")
    repo = SubstitutionRepository(db)
    return await _entry_gate(db, sid,
        lambda: repo.confirm(sid, str(row[0]), str(current_user.id), (payload.get("notes") or None)), "confirmed", "substituição")


@router.post("/action/substituicao-rejeitar")
async def rd_action_substituicao_rejeitar(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    from fastapi import HTTPException

    from modules.operacional.repositories.substitution_repository import SubstitutionRepository
    sid = (payload.get("substitution_id") or "").strip()
    reason = (payload.get("reason") or "").strip()
    if len(reason) < 5:
        raise HTTPException(status_code=400, detail="Informe o motivo da rejeição (mín. 5 caracteres).")
    repo = SubstitutionRepository(db)
    return await _entry_gate(db, sid,
        lambda: repo.reject(sid, reason), "cancelled", "substituição")


@router.post("/action/comunicado-publicar")
async def rd_action_comunicado_publicar(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    import uuid as _uuid

    from fastapi import HTTPException

    from modules.operacional.communication.controllers.announcement_controller import publish_announcement
    from modules.operacional.communication.schemas.communication_schemas import AnnouncementPublishRequest
    cid = (payload.get("announcement_id") or "").strip()
    try:
        _cid = _uuid.UUID(cid)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Selecione o comunicado.")
    return await _entry_gate(db, cid,
        lambda: publish_announcement(announcement_id=_cid, request_data=AnnouncementPublishRequest(),
                                     current_user=current_user, db=db), "publicado", "comunicado")


@router.post("/action/comunicado-criar")
async def rd_action_comunicado_criar(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    from fastapi import HTTPException

    from modules.operacional.communication.controllers.announcement_controller import create_announcement
    from modules.operacional.communication.schemas.communication_schemas import AnnouncementCreate
    titulo = (payload.get("title") or "").strip()
    conteudo = (payload.get("content") or "").strip()
    if len(titulo) < 3 or len(conteudo) < 10:
        raise HTTPException(status_code=400, detail="Título (mín. 3) e conteúdo (mín. 10) são obrigatórios.")
    data = AnnouncementCreate(title=titulo, content=conteudo,
                              priority=(payload.get("priority") or "normal"),
                              category=(payload.get("category") or "informativo"))
    res = await create_announcement(data=data, current_user=current_user, db=db)
    return {"ok": True, "msg": "Comunicado criado (rascunho). Publique para enviar.", "id": str(getattr(res, "id", "") or "")}


@router.post("/action/comunicado-editar")
async def rd_action_comunicado_editar(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    import uuid as _uuid

    from fastapi import HTTPException

    from modules.operacional.communication.controllers.announcement_controller import update_announcement
    from modules.operacional.communication.schemas.communication_schemas import AnnouncementUpdate
    cid = (payload.get("announcement_id") or "").strip()
    try:
        _cid = _uuid.UUID(cid)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Selecione o comunicado.")
    upd = {k: (payload.get(k) or "").strip() for k in ("title", "content") if (payload.get(k) or "").strip()}
    for k in ("priority", "category"):
        if payload.get(k):
            upd[k] = payload[k]
    if not upd:
        raise HTTPException(status_code=400, detail="Nada para atualizar.")
    await update_announcement(announcement_id=_cid, data=AnnouncementUpdate(**upd), current_user=current_user, db=db)
    return {"ok": True, "msg": "Comunicado atualizado (só rascunho/agendado é editável)."}


@router.post("/action/comunicado-excluir")
async def rd_action_comunicado_excluir(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    import uuid as _uuid

    from fastapi import HTTPException

    from modules.operacional.communication.controllers.announcement_controller import delete_announcement
    cid = (payload.get("announcement_id") or "").strip()
    try:
        _cid = _uuid.UUID(cid)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Selecione o comunicado.")
    await delete_announcement(announcement_id=_cid, current_user=current_user, db=db)
    return {"ok": True, "msg": "Comunicado excluído."}


@router.post("/action/alerta-ack")
async def rd_action_alerta_ack(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    from fastapi import HTTPException

    from modules.operacional.communication.controllers.notification_controller import acknowledge_alert
    aid = (payload.get("alert_id") or "").strip()
    if not aid:
        raise HTTPException(status_code=400, detail="Selecione o alerta.")
    return await _entry_gate(db, aid,
        lambda: acknowledge_alert(alert_id=aid, current_user=current_user, db=db), "reconhecido", "alerta")


@router.post("/action/diarista-ativar")
async def rd_action_diarista_ativar(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    import uuid as _uuid

    from fastapi import HTTPException

    from modules.operacional.diaristas.services.diarist_service import DiaristService
    did = (payload.get("diarist_id") or "").strip()
    try:
        _did = _uuid.UUID(did)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Selecione o diarista.")
    return await _entry_gate(db, did, lambda: DiaristService(db).activate_diarist(_did), "ativado", "diarista")


@router.post("/action/diarista-desativar")
async def rd_action_diarista_desativar(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    import uuid as _uuid

    from fastapi import HTTPException

    from modules.operacional.diaristas.services.diarist_service import DiaristService
    did = (payload.get("diarist_id") or "").strip()
    try:
        _did = _uuid.UUID(did)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Selecione o diarista.")
    return await _entry_gate(db, did, lambda: DiaristService(db).deactivate_diarist(_did), "desativado", "diarista")


@router.post("/action/diarista-avaliar")
async def rd_action_diarista_avaliar(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    from fastapi import HTTPException

    from modules.operacional.diaristas.schemas.diarist_schemas import DiaristEvaluationCreate
    from modules.operacional.diaristas.services.diarist_service import DiaristService
    did = (payload.get("diarist_id") or "").strip()
    if not did:
        raise HTTPException(status_code=400, detail="Selecione o diarista.")
    try:
        nota = int(payload.get("nota_geral") or 0)
    except (ValueError, TypeError):
        nota = 0
    if not 1 <= nota <= 5:
        raise HTTPException(status_code=400, detail="Nota geral deve ser de 1 a 5.")
    cond = (await db.execute(_sqltext(
        "SELECT condominio_id FROM diarist_schedules WHERE diarist_id::text=:d AND condominio_id IS NOT NULL "
        "ORDER BY created_at DESC LIMIT 1"), {"d": did})).scalar()
    if not cond:
        raise HTTPException(status_code=400, detail="Diarista sem condomínio vinculado — não há contexto para avaliar.")
    try:
        data = DiaristEvaluationCreate(diarist_id=did, condominio_id=str(cond), avaliador_id=str(current_user.id),
                                       avaliador_nome=(getattr(current_user, "name", "") or "—"),
                                       nota_geral=nota, comentario=(payload.get("comentario") or None))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Dados inválidos: {e}")
    try:
        ev = await DiaristService(db).create_evaluation(data)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Falha ao avaliar: {e}")
    return {"ok": True, "id": str(getattr(ev, "id", None)), "message": "Avaliação registrada"}


@router.post("/action/diarista-fechamento")
async def rd_action_diarista_fechamento(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Gera o FECHAMENTO de diaristas do mês = cria os registros DiaristPayment PENDENTE (op_write,
    SEM dinheiro). O pagamento em si é gated OTP no financeiro (/action/pagar-diaristas). Reuso do
    serviço; nunca move dinheiro aqui."""
    from fastapi import HTTPException

    from modules.operacional.controllers.redesign_write_gate import GateError, op_write
    from modules.operacional.diaristas.schemas.diarist_schemas import PayrollGenerateRequest
    from modules.operacional.diaristas.services.diarist_service import DiaristService
    cond = (payload.get("condominio_id") or "").strip()
    comp = (payload.get("competencia") or "").strip()
    if not cond:
        raise HTTPException(status_code=400, detail="Selecione o condomínio.")
    if len(comp) != 7 or comp[4] != "-":
        raise HTTPException(status_code=400, detail="Informe a competência no formato AAAA-MM.")
    try:
        data = PayrollGenerateRequest(condominio_id=cond, competencia=comp)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Dados inválidos: {e}")

    try:
        res = await op_write(db, real_write=lambda: DiaristService(db).generate_payroll_payments(data),
                             idempotency_key=f"diar-fech:{cond}:{comp}")
    except GateError as ge:
        raise HTTPException(status_code=400, detail=str(ge))
    tot = res.get("total_gerados", 0) if isinstance(res, dict) else 0
    return {"ok": True, "total_gerados": tot,
            "message": f"Fechamento gerado: {tot} pagamento(s) pendente(s). Pagamento é gated (OTP) no financeiro."}


def _mgr_scope(current_user):
    """Scope de GESTOR p/ ações do redesign (mesmo padrão do quadro de presença).
    Humano-operado: a parede real é o RBAC do módulo no redesign + auth da rota."""
    from modules.operacional.scope import OperationalScope
    return OperationalScope(all_posts=True, post_ids=[], employee_id=None,
                            user_id=str(current_user.id),
                            user_name=(getattr(current_user, "name", "") or "redesign"),
                            is_manager=True)


# Drill-down dos dashboards: KPI (por label) → tela de destino. O ModuleView torna o KPI
# clicável (mostra "›" e navega) quando o KPI tem `to`. Tira os dashboards de "beco sem
# saída" — clicar num número abre OS registros por trás dele.
_KPI_DRILL = {
    "Postos ativos": "postos", "Postos": "postos", "Descobertos": "cobertura-risco",
    "Colaboradores": "colaboradores", "Colaboradores ativos": "colaboradores",
    "Efetivo ativo": "colaboradores", "Total de agentes": "colaboradores",
    "Alocações ativas": "alocacoes",
    "Ocorrências abertas": "ocorrencias", "Ocorrências (7d)": "ocorrencias",
    "Ocorrências (mês)": "ocorrencias", "Nível de risco": "ocorrencias",
    "Rondas (mês)": "rondas", "Substituições (mês)": "substituicoes",
    "Cobertos": "presenca", "Taxa de cobertura": "presenca", "Cobertura": "presenca",
    "Presentes": "presenca", "Presentes hoje": "presenca", "Ausentes": "presenca",
    "Medidas (mês)": "medidas-administrativas", "Passagens (mês)": "passagem-turno",
    "Avaliações (semana)": "avaliacao-equipe",
    "Postos sem escala vigente": "postos-sem-escala", "Escalas em rascunho": "escalas-rascunho",
}


def _aplicar_drill(out: dict) -> None:
    """Seta `to` em cada KPI de dashboard (por label → tela). Só drilla p/ tela que EXISTE
    em out (senão o clique levaria a nada — honesto). DEVE rodar ANTES de montar_grupos,
    enquanto os dashboards ainda estão no topo de out (depois viram .screen das abas)."""
    for scr in out.values():
        if isinstance(scr, dict) and scr.get("type") == "dash":
            for kpi in scr.get("kpis", []):
                tgt = _KPI_DRILL.get(kpi.get("l"))
                if tgt and tgt in out:
                    kpi["to"] = tgt


def _ver_todas(out: dict) -> None:
    """Clique-na-linha em TODA tabela: adiciona uma ação 'Ver' (modal read-only com os campos
    da linha) onde ainda não há ver/editar. Uniforme, sem escrita — mata o 'clico e não abre
    nada'. Detalhe rico/edição por tabela vem depois, por cima disto."""
    for scr in out.values():
        if not isinstance(scr, dict) or scr.get("type") != "table":
            continue
        cols = scr.get("cols", []) or []
        titulo = scr.get("title", "Detalhe")
        for row in scr.get("rows", []):
            if row.get("edit") or any((a or {}).get("btnLabel") == "Ver" for a in (row.get("actions") or [])):
                continue
            campos = []
            for c, cell in zip(cols, row.get("cells", []) or []):
                val = cell.get("v") if isinstance(cell, dict) else cell
                campos.append({"label": c, "value": (val if (val not in (None, "")) else "—")})
            if campos:
                row.setdefault("actions", []).insert(
                    0, {"btnLabel": "Ver", "readOnly": True, "title": f"{titulo} — detalhe", "fields": campos})


@router.post("/action/passagem-turno")
async def rd_action_passagem_turno(current_user: CurrentActiveUser, payload: dict = Body(...),
                                   db=Depends(get_db)) -> dict:
    """Registra passagem de turno REAL via controller existente (reuso). Humano-operado."""
    from modules.operacional.controllers.redesign_write_gate import GateError, op_write
    from modules.operacional.shift_handover.controllers.shift_handover_controller import create_passagem_turno
    from modules.operacional.shift_handover.schemas import PassagemTurnoCreate

    post_id = (payload.get("post_id") or "").strip() or None
    resumo = (payload.get("resumo") or "").strip()
    if len(resumo) < 5:
        raise HTTPException(status_code=400, detail="O resumo precisa de ao menos 5 caracteres.")
    try:
        data = PassagemTurnoCreate(
            post_id=post_id, turno=(payload.get("turno") or "diurno").strip(),
            resumo=resumo, pendencias=(payload.get("pendencias") or None),
            data_turno=payload.get("data_turno") or None)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Dados inválidos: {e}")
    scope = _mgr_scope(current_user)

    async def _write():
        return await create_passagem_turno(data=data, scope=scope, db=db)

    try:
        res = await op_write(db, real_write=_write)
    except GateError as ge:
        raise HTTPException(status_code=400, detail=str(ge))
    rid = getattr(res, "id", None) or (res.get("id") if isinstance(res, dict) else None)
    return {"ok": True, "id": str(rid) if rid else None, "message": "Passagem de turno registrada"}


@router.post("/action/instrucao-posto")
async def rd_action_instrucao_posto(current_user: CurrentActiveUser, payload: dict = Body(...),
                                    db=Depends(get_db)) -> dict:
    """Upsert versionado das instruções do posto REAL via controller (reuso). Só gestor."""
    from modules.operacional.controllers.redesign_write_gate import GateError, op_write
    from modules.operacional.post_orders.controllers.post_orders_controller import atualizar_instrucoes_posto
    from modules.operacional.post_orders.schemas import InstrucoesPostoUpdate

    post_id = (payload.get("post_id") or "").strip()
    if not post_id:
        raise HTTPException(status_code=400, detail="Selecione o posto.")
    conteudo = (payload.get("conteudo") or "").strip()
    if len(conteudo) < 10:
        raise HTTPException(status_code=400, detail="O conteúdo precisa de ao menos 10 caracteres.")
    try:
        body = InstrucoesPostoUpdate(titulo=(payload.get("titulo") or None), conteudo=conteudo)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Dados inválidos: {e}")
    scope = _mgr_scope(current_user)

    async def _write():
        return await atualizar_instrucoes_posto(post_id=post_id, body=body, scope=scope, db=db)

    try:
        res = await op_write(db, real_write=_write)
    except GateError as ge:
        raise HTTPException(status_code=400, detail=str(ge))
    ver = getattr(res, "versao", None) or (res.get("versao") if isinstance(res, dict) else None)
    return {"ok": True, "versao": ver, "message": f"Instruções do posto salvas (v{ver})" if ver else "Instruções salvas"}


@router.post("/action/banco-horas")
async def rd_action_banco_horas(current_user: CurrentActiveUser, payload: dict = Body(...),
                                db=Depends(get_db)) -> dict:
    """Cria lançamento no banco de horas REAL via controller (reuso; expiração+repo). Humano-operado."""
    from datetime import date as _date

    from modules.operacional.controllers.redesign_write_gate import GateError, op_write
    from modules.operacional.controllers.time_bank_controller import create_entry as _tb_create
    from modules.operacional.schemas.time_bank import TimeBankCreate

    emp_id = (payload.get("employee_id") or "").strip()
    if not emp_id:
        raise HTTPException(status_code=400, detail="Selecione o colaborador.")
    try:
        hours = float(str(payload.get("hours") or "0").replace(",", "."))
    except ValueError:
        raise HTTPException(status_code=400, detail="Horas inválidas.")
    if hours == 0:
        raise HTTPException(status_code=400, detail="Horas não pode ser zero (use + crédito / - débito).")
    try:
        data = TimeBankCreate(
            employee_id=emp_id, entry_type=payload.get("entry_type") or "credit",
            hours=hours, reference_date=payload.get("reference_date") or _date.today().isoformat(),
            description=(payload.get("description") or None), reason=(payload.get("reason") or None))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Dados inválidos: {e}")

    async def _write():
        return await _tb_create(data=data, current_user=current_user, db=db)

    try:
        res = await op_write(db, real_write=_write,
                             idempotency_key=f"bh:{emp_id}:{data.reference_date}:{data.entry_type}:{hours}")
    except GateError as ge:
        raise HTTPException(status_code=400, detail=str(ge))
    rid = getattr(res, "id", None) or (res.get("id") if isinstance(res, dict) else None)
    return {"ok": True, "id": str(rid) if rid else None, "message": "Lançamento no banco de horas criado"}


@router.post("/action/nova-ronda")
async def rd_action_nova_ronda(current_user: CurrentActiveUser, payload: dict = Body(...),
                               db=Depends(get_db)) -> dict:
    """Cria (agenda) ronda de inspeção REAL via InspectionRoundService (reuso). Humano-operado.
    O ciclo de campo (iniciar/checkpoints/fotos) fica no fluxo mobile (ronda-mobile)."""
    from core.auth import get_tenant_id
    from modules.operacional.controllers.redesign_write_gate import GateError, op_write
    from modules.operacional.inspection_rounds.schemas.inspection_round_schemas import InspectionRoundCreate
    from modules.operacional.inspection_rounds.services.inspection_round_service import InspectionRoundService

    insp_id = (payload.get("inspector_id") or "").strip()
    if not insp_id:
        raise HTTPException(status_code=400, detail="Selecione o inspetor.")
    emp = (await db.execute(_sqltext("SELECT nome FROM employees WHERE id::text=:i"), {"i": insp_id})).first()
    if not emp:
        raise HTTPException(status_code=400, detail="Inspetor não encontrado.")
    try:
        data = InspectionRoundCreate(
            tenant_id=get_tenant_id(current_user), inspector_id=insp_id, inspector_name=emp[0] or "—",
            scheduled_date=payload.get("scheduled_date") or None,
            observations=(payload.get("observations") or None))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Dados inválidos: {e}")

    async def _write():
        return await InspectionRoundService(db).create(data)

    try:
        r = await op_write(db, real_write=_write, idempotency_key=f"ronda:{insp_id}:{data.scheduled_date}")
    except GateError as ge:
        raise HTTPException(status_code=400, detail=str(ge))
    rid = getattr(r, "id", None)
    return {"ok": True, "id": str(rid) if rid else None, "code": getattr(r, "code", None), "message": "Ronda criada"}


@router.post("/action/ronda-transicao")
async def rd_action_ronda_transicao(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Ciclo de vida da ronda pelo gestor (iniciar/pausar/retomar/concluir/cancelar).
    Reusa os controllers reais do inspection_round (mantém o publish de evento no concluir).
    O serviço valida o estado — transição inválida devolve 400."""
    import uuid as _uuid

    from fastapi import HTTPException

    from modules.operacional.inspection_rounds.controllers.inspection_round_controller import (
        cancel_round, complete_round, pause_round, resume_round, start_round)
    from modules.operacional.inspection_rounds.services.inspection_round_service import InspectionRoundService
    rid = (payload.get("round_id") or "").strip()
    acao = (payload.get("acao") or "").strip()
    try:
        _rid = _uuid.UUID(rid)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Selecione a ronda.")
    svc = InspectionRoundService(db)
    ops = {
        "iniciar": lambda: start_round(round_id=_rid, current_user=current_user, data=None, service=svc),
        "pausar": lambda: pause_round(round_id=_rid, current_user=current_user, service=svc),
        "retomar": lambda: resume_round(round_id=_rid, current_user=current_user, service=svc),
        "concluir": lambda: complete_round(round_id=_rid, current_user=current_user, data=None, service=svc),
        "cancelar": lambda: cancel_round(round_id=_rid, current_user=current_user,
                                         reason=(payload.get("motivo") or None), service=svc),
    }
    fn = ops.get(acao)
    if not fn:
        raise HTTPException(status_code=400, detail="Ação inválida (iniciar/pausar/retomar/concluir/cancelar).")
    await fn()
    return {"ok": True, "msg": f"Ronda: '{acao}' aplicado."}


@router.post("/action/notificacoes-marcar-todas")
async def rd_action_notif_marcar_todas(current_user: CurrentActiveUser, payload: dict = Body(default={}),
                                       db=Depends(get_db)) -> dict:
    """Marca TODAS as notificações do usuário como lidas (reuso do controller real)."""
    from modules.operacional.communication.controllers.notification_controller import mark_all_notifications_read
    from modules.operacional.communication.schemas.communication_schemas import MarkNotificationReadRequest
    res = await mark_all_notifications_read(
        request_data=MarkNotificationReadRequest(notification_ids=None), current_user=current_user, db=db)
    n = res.get("count") if isinstance(res, dict) else None
    return {"ok": True, "message": "Notificações marcadas como lidas." + (f" ({n})" if n is not None else "")}


@router.post("/action/checkin-manual")
async def rd_action_checkin_manual(current_user: CurrentActiveUser, payload: dict = Body(...),
                                   db=Depends(get_db)) -> dict:
    """Check-in manual de presença (quando o facial falha) — reuso do controller real via gate."""
    from modules.operacional.controllers.redesign_write_gate import GateError, op_write
    from modules.operacional.presence.controllers.presence_controller import checkin_manual
    from modules.operacional.presence.schemas import CheckinManualBody
    shift_id = (payload.get("shift_id") or "").strip()
    if not shift_id:
        raise HTTPException(status_code=400, detail="Selecione o turno de hoje.")
    body = CheckinManualBody(observacao=(payload.get("observacao") or None))
    scope = _mgr_scope(current_user)

    async def _write():
        return await checkin_manual(shift_id=shift_id, payload=body, scope=scope, db=db)
    try:
        await op_write(db, real_write=_write)
    except GateError as ge:
        raise HTTPException(status_code=400, detail=str(ge))
    return {"ok": True, "message": "Check-in manual registrado."}


@router.post("/action/posto-localizacao")
async def rd_action_posto_localizacao(current_user: CurrentActiveUser, payload: dict = Body(...),
                                      db=Depends(get_db)) -> dict:
    """Define a localização GPS REAL do posto (reuso do controller). Só gestão."""
    from uuid import UUID
    from modules.operacional.controllers.post_controller import DefinirLocalizacaoRequest, definir_localizacao_posto
    from modules.operacional.controllers.redesign_write_gate import GateError, op_write
    post_id = (payload.get("post_id") or "").strip()
    if not post_id:
        raise HTTPException(status_code=400, detail="Selecione o posto.")
    try:
        _pid = UUID(post_id)
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Posto inválido.")
    try:
        req = DefinirLocalizacaoRequest(
            lat=float(payload.get("lat")), lng=float(payload.get("lng")),
            raio_metros=(float(payload["raio_metros"]) if payload.get("raio_metros") else None))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Latitude/longitude inválidas: {e}")

    async def _write():
        return await definir_localizacao_posto(post_id=_pid, current_user=current_user, payload=req, db=db)
    try:
        await op_write(db, real_write=_write)
    except GateError as ge:
        raise HTTPException(status_code=400, detail=str(ge))
    return {"ok": True, "message": "Localização do posto definida."}


@router.post("/action/posto-editar")
async def rd_action_posto_editar(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Edita dados cadastrais do posto (nome/endereço/cidade/UF/CEP) — reuso do update_post real."""
    from uuid import UUID

    from modules.operacional.controllers.post_controller import update_post
    from modules.operacional.schemas.post import PostUpdate
    post_id = (payload.get("post_id") or "").strip()
    try:
        _pid = UUID(post_id)
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Selecione o posto.")
    upd = {k: (payload.get(k) or "").strip() for k in ("name", "address", "city", "zip_code") if (payload.get(k) or "").strip()}
    uf = (payload.get("state") or "").strip().upper()
    if uf:
        upd["state"] = uf[:2]
    if not upd:
        raise HTTPException(status_code=400, detail="Nada para atualizar.")
    await update_post(post_id=_pid, data=PostUpdate(**upd), current_user=current_user, db=db)
    return {"ok": True, "message": "Posto atualizado."}


@router.post("/action/alerta-criar")
async def rd_action_alerta_criar(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Cria um alerta operacional (reuso do create_alert real). Par do 'Reconhecer alerta'."""
    from fastapi import HTTPException

    from modules.operacional.communication.controllers.notification_controller import create_alert
    from modules.operacional.communication.schemas.communication_schemas import AlertCreate
    titulo = (payload.get("title") or "").strip()
    msg = (payload.get("message") or "").strip()
    if len(titulo) < 3 or len(msg) < 3:
        raise HTTPException(status_code=400, detail="Título e mensagem (mín. 3) são obrigatórios.")
    data = AlertCreate(title=titulo, message=msg,
                       alert_type=(payload.get("alert_type") or "posto_descoberto"),
                       severity=(payload.get("severity") or "warning"))
    await create_alert(data=data, current_user=current_user, db=db)
    return {"ok": True, "msg": "Alerta criado."}


@router.post("/action/banco-horas-compensar")
async def rd_action_banco_horas_compensar(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Lança compensação de banco de horas de um colaborador (reuso do compensate_hours real)."""
    import uuid as _uuid

    from fastapi import HTTPException

    from modules.operacional.controllers.time_bank_controller import compensate_hours
    from modules.operacional.schemas.time_bank import TimeBankCompensate
    eid = (payload.get("employee_id") or "").strip()
    try:
        _eid = _uuid.UUID(eid)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Selecione o colaborador.")
    try:
        data = TimeBankCompensate(hours=float(payload.get("hours")),
                                  compensation_date=(payload.get("compensation_date") or None),
                                  notes=(payload.get("notes") or None))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Dados inválidos (horas/data): {e}")
    await compensate_hours(employee_id=_eid, data=data, current_user=current_user, db=db)
    return {"ok": True, "msg": "Compensação de horas lançada."}


@router.post("/action/avaliacao-criar")
async def rd_action_avaliacao_criar(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Registra avaliação de um colaborador (nota 1-5) — reuso do criar_avaliacao real.
    Dá create-path à tabela operacional_avaliacoes_equipe (antes só-leitura no redesign)."""
    from fastapi import HTTPException

    from modules.operacional.team_evaluations.controllers.team_evaluation_controller import criar_avaliacao
    from modules.operacional.team_evaluations.schemas import AvaliacaoCreate
    eid = (payload.get("employee_id") or "").strip()
    if not eid:
        raise HTTPException(status_code=400, detail="Selecione o colaborador.")
    try:
        nota = int(payload.get("nota"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Nota (1 a 5) é obrigatória.")
    data = AvaliacaoCreate(employee_id=eid, nota=nota,
                           observacao=(payload.get("observacao") or None),
                           competencia=(payload.get("competencia") or None))
    await criar_avaliacao(data=data, scope=_mgr_scope(current_user), db=db)
    return {"ok": True, "msg": "Avaliação registrada."}


@router.post("/action/substituicao-concluir")
async def rd_action_substituicao_concluir(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Conclui uma substituição confirmada (reuso do complete_substitution real)."""
    from fastapi import HTTPException

    from modules.operacional.controllers.substitution_controller import complete_substitution
    sid = (payload.get("substitution_id") or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="Selecione a substituição.")
    try:
        oh = float(payload.get("overtime_hours") or 0)
    except (TypeError, ValueError):
        oh = 0.0
    await complete_substitution(substitution_id=sid, current_user=current_user, db=db, overtime_hours=oh, additional_cost=0)
    return {"ok": True, "msg": "Substituição concluída."}


@router.post("/action/diarista-escala-criar")
async def rd_action_diarista_escala_criar(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Agenda um diarista (diarist_schedules) — reuso do DiaristService.create_schedule.
    Dá create-path à tabela diarist_schedules (antes só-leitura no redesign). valor_previsto ≠ pagamento (OTP fica no financeiro)."""
    import uuid as _uuid

    from fastapi import HTTPException

    from modules.operacional.diaristas.schemas.diarist_schemas import DiaristScheduleCreate
    from modules.operacional.diaristas.services.diarist_service import DiaristService
    try:
        did = _uuid.UUID((payload.get("diarist_id") or "").strip())
        cond = _uuid.UUID((payload.get("condominio_id") or "").strip())
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Selecione diarista e condomínio.")
    if not (payload.get("data_trabalho") or "").strip():
        raise HTTPException(status_code=400, detail="Informe a data de trabalho.")
    kw = {"diarist_id": did, "condominio_id": cond, "data_trabalho": payload["data_trabalho"].strip()}
    for k in ("hora_inicio", "hora_fim", "valor_previsto", "observacoes"):
        if payload.get(k):
            kw[k] = payload[k]
    try:
        data = DiaristScheduleCreate(**kw)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Dados inválidos: {e}")
    r = await DiaristService(db).create_schedule(data)
    return {"ok": True, "msg": "Escala de diarista criada.", "id": str(getattr(r, "id", "") or "")}


@router.post("/action/banco-horas-editar")
async def rd_action_bh_editar(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Edita um lançamento de banco de horas PENDENTE (horas/motivo/descrição) — reuso do update_entry."""
    from fastapi import HTTPException

    from modules.operacional.controllers.time_bank_controller import update_entry
    from modules.operacional.schemas.time_bank import TimeBankUpdate
    eid = (payload.get("entry_id") or "").strip()
    if not eid:
        raise HTTPException(status_code=400, detail="Selecione o lançamento.")
    upd = {}
    if payload.get("hours"):
        try:
            upd["hours"] = float(payload["hours"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Horas inválidas.")
    for k in ("reason", "description"):
        if (payload.get(k) or "").strip():
            upd[k] = payload[k].strip()
    if not upd:
        raise HTTPException(status_code=400, detail="Nada para atualizar.")
    await update_entry(entry_id=eid, data=TimeBankUpdate(**upd), current_user=current_user, db=db)
    return {"ok": True, "msg": "Lançamento atualizado."}


@router.post("/action/banco-horas-excluir")
async def rd_action_bh_excluir(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Exclui um lançamento de banco de horas — reuso do delete_entry."""
    from fastapi import HTTPException

    from modules.operacional.controllers.time_bank_controller import delete_entry
    eid = (payload.get("entry_id") or "").strip()
    if not eid:
        raise HTTPException(status_code=400, detail="Selecione o lançamento.")
    await delete_entry(entry_id=eid, current_user=current_user, db=db)
    return {"ok": True, "msg": "Lançamento excluído."}


@router.post("/action/diaria-excluir")
async def rd_action_diaria_excluir(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Exclui um lançamento de diária (status 'lancado') — reuso do excluir_lancamento."""
    from fastapi import HTTPException

    from modules.operacional.diaristas.diarias_service import excluir_lancamento
    try:
        _lid = int(payload.get("lancamento_id"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Selecione o lançamento.")
    res = await excluir_lancamento(db, _lid)
    await db.commit()
    return {"ok": True, "msg": (res.get("message") if isinstance(res, dict) else None) or "Lançamento de diária excluído."}


@router.post("/action/diarista-assignment-criar")
async def rd_action_assignment_criar(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Cria uma alocação recorrente de diarista (diarist_assignments — tabela própria, NÃO allocations).
    Reuso do DiaristService.create_assignment."""
    import uuid as _uuid

    from fastapi import HTTPException

    from modules.operacional.diaristas.schemas.diarist_schemas import DiaristAssignmentCreate
    from modules.operacional.diaristas.services.diarist_service import DiaristService
    try:
        did = _uuid.UUID((payload.get("diarist_id") or "").strip())
        cond = _uuid.UUID((payload.get("condominio_id") or "").strip())
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Selecione diarista e condomínio.")
    if not (payload.get("data_inicio") or "").strip():
        raise HTTPException(status_code=400, detail="Informe a data de início.")
    kw = {"diarist_id": did, "condominio_id": cond,
          "servico_tipo": (payload.get("servico_tipo") or "portaria").strip(),
          "data_inicio": payload["data_inicio"].strip()}
    for k in ("data_fim", "servico_descricao", "local_servico"):
        if payload.get(k):
            kw[k] = payload[k]
    try:
        data = DiaristAssignmentCreate(**kw)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Dados inválidos: {e}")
    r = await DiaristService(db).create_assignment(data)
    return {"ok": True, "msg": "Alocação de diarista criada.", "id": str(getattr(r, "id", "") or "")}


@router.post("/action/diarista-assignment-cancelar")
async def rd_action_assignment_cancelar(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Cancela uma alocação recorrente de diarista — reuso do DiaristService.cancel_assignment."""
    import uuid as _uuid

    from fastapi import HTTPException

    from modules.operacional.diaristas.services.diarist_service import DiaristService
    try:
        _aid = _uuid.UUID((payload.get("assignment_id") or "").strip())
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Selecione a alocação.")
    ok = await DiaristService(db).cancel_assignment(_aid)
    if not ok:
        raise HTTPException(status_code=404, detail="Alocação não encontrada.")
    return {"ok": True, "msg": "Alocação cancelada."}


# F0: menu extra ZERADO — as antigas entradas de ação viram ABAS dos 8 grupos (_op_grupos.py),
# igual ao financeiro. A navegação agrupada evita a sidebar com 60+ itens soltos.
EXTRA_MENU: list[dict] = [
    {"id": "consultor-op", "label": "Consultor operacional", "icon": "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20M12 8v4M12 16h.01"},
    {"id": "consultor-op-arquivo", "label": "Consultor operacional — com anexo", "icon": "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20M12 8v4M12 16h.01"},
]


async def build(db) -> dict:
    out = await _build_operacional(db)
    _, _safe, tbl = _helpers(db)

    # Presença Hoje — QUADRO por posto/condomínio (FIDELIDADE: reusa o MESMO serviço do
    # clássico, quadro_presenca_hoje → os números batem). Composite: tabela + resumo do dia.
    try:
        from modules.operacional.presence.controllers.presence_controller import quadro_presenca_hoje
        from modules.operacional.scope import OperationalScope
        _scope = OperationalScope(all_posts=True, post_ids=[], employee_id=None,
                                  user_id="redesign", user_name="redesign", is_manager=True)
        q = await quadro_presenca_hoje(data=None, scope=_scope, db=db)
        qd = q.model_dump() if hasattr(q, "model_dump") else (q.dict() if hasattr(q, "dict") else q)
        res = qd.get("resumo", {}) or {}
        postos = qd.get("postos", []) or []

        def _cnt(v, tone):
            return b(str(v or 0), tone if (v or 0) > 0 else "mut")
        out["presenca"] = {
            "title": "Presença Hoje",
            "sub": (f"Quadro do dia por posto/condomínio (Manaus) · {res.get('presentes', 0)} presente(s) · "
                    f"{res.get('atrasados', 0)} atrasado(s) · {res.get('ausentes', 0)} ausente(s) de "
                    f"{res.get('esperados', 0)} esperado(s)"),
            "cta": "—", "type": "table", "searchHint": "Buscar posto…",
            "grid": "2fr 0.9fr 0.9fr 0.9fr 0.9fr",
            "cols": ["Posto / Condomínio", "Esperados", "Presentes", "Atrasados", "Ausentes"],
            "rows": [{"cells": [
                t(p.get("post_nome") or "—", 600, "#0F1B3A"),
                t(str(p.get("esperados", 0))),
                _cnt(p.get("presentes"), "ok"), _cnt(p.get("atrasados"), "warn"), _cnt(p.get("ausentes"), "bad"),
            ]} for p in postos],
            "panelGrid": "1fr",
            "panels": [{"title": "Resumo do dia", "rows": [
                {"left": "Esperados", "right": str(res.get("esperados", 0)), **S["info"]},
                {"left": "Presentes", "right": str(res.get("presentes", 0)), **S["ok"]},
                {"left": "Atrasados", "right": str(res.get("atrasados", 0)), **S["warn"]},
                {"left": "Ausentes", "right": str(res.get("ausentes", 0)), **S["bad"]},
                {"left": "Aguardando", "right": str(res.get("aguardando", 0)), **S["mut"]},
            ]}],
        }
    except Exception:  # noqa: BLE001 — presença não derruba o resto do módulo
        pass

    # Escalas — solides_work_schedules (curado; leitura)
    try:
        out["escalas"] = await tbl(
            "Escalas", "Escalas de trabalho (Sólides)", "—",
            ["Escala", "Código", "Tipo", "Carga/sem", "Status"], "1.8fr 1fr 1fr 0.9fr 0.9fr",
            "SELECT coalesce(nome,'—'), coalesce(codigo,'—'), coalesce(tipo::text,'—'), carga_horaria_semanal, coalesce(is_active,true) "
            "FROM solides_work_schedules ORDER BY nome LIMIT 200",
            lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t((r[2] or '—').replace('_', ' ')),
                       t(f"{r[3]}h" if r[3] is not None else '—'), b("Ativa", "ok") if r[4] else b("Inativa", "mut")])
    except Exception:  # noqa: BLE001
        pass

    # Turnos — shifts (instâncias de turno planejadas/realizadas; leitura)
    _tt = {"scheduled": "info", "planejado": "info", "completed": "ok", "concluido": "ok", "absent": "bad", "falta": "bad", "in_progress": "warn", "em_andamento": "warn"}
    try:
        out["turnos"] = await tbl(
            "Turnos", "Turnos planejados/realizados", "—",
            ["Colaborador", "Data", "Início", "Fim", "Horas", "Status"], "1.6fr 0.9fr 0.8fr 0.8fr 0.7fr 0.9fr",
            "SELECT coalesce(e.nome,'—'), s.shift_date, s.planned_start_time, s.planned_end_time, s.planned_hours, coalesce(s.status::text,'—'), "
            "s.planned_break_minutes, s.actual_start_time, s.actual_end_time, s.actual_hours, s.overtime_hours, s.night_hours, coalesce(s.notes,'—') "
            "FROM shifts s LEFT JOIN employees e ON e.id=s.employee_id ORDER BY s.shift_date DESC NULLS LAST LIMIT 200",
            lambda r: [t(r[0], 600, "#0F1B3A"), t(_fmtdate(r[1])), t(str(r[2])[:5] if r[2] else '—'), t(str(r[3])[:5] if r[3] else '—'),
                       t(f"{float(r[4]):.0f}h" if r[4] is not None else '—'), b((r[5] or '—').replace('_', ' ').capitalize(), _tt.get((r[5] or '').lower(), "info"))],
            editfn=lambda r: {
                "btnLabel": "Ver turno", "readOnly": True, "title": f"Turno — {r[0]}",
                "fields": [
                    {"label": "Colaborador", "value": r[0], "span": "span 2"},
                    {"label": "Data", "value": _fmtdate(r[1])}, {"label": "Status", "value": (r[5] or "—").replace("_", " ").capitalize()},
                    {"label": "Início previsto", "value": str(r[2])[:5] if r[2] else "—"}, {"label": "Fim previsto", "value": str(r[3])[:5] if r[3] else "—"},
                    {"label": "Início real", "value": str(r[7])[:5] if r[7] else "—"}, {"label": "Fim real", "value": str(r[8])[:5] if r[8] else "—"},
                    {"label": "Horas previstas", "value": (f"{float(r[4]):.1f}h" if r[4] is not None else "—")},
                    {"label": "Horas realizadas", "value": (f"{float(r[9]):.1f}h" if r[9] is not None else "—")},
                    {"label": "Intervalo (min)", "value": (str(r[6]) if r[6] is not None else "—")},
                    {"label": "Horas extras", "value": (f"{float(r[10]):.1f}h" if r[10] is not None else "—")},
                    {"label": "Horas noturnas", "value": (f"{float(r[11]):.1f}h" if r[11] is not None else "—")},
                    {"label": "Notas", "value": r[12], "span": "span 2"},
                ],
            })
    except Exception:  # noqa: BLE001
        pass

    # Reembolsos — reimbursement_requests (READ-ONLY: sem aprovar/pagar aqui)
    _rt = {"aprovado": "ok", "pago": "ok", "reembolsado": "ok", "pendente": "warn", "em_analise": "warn", "submetido": "warn", "rejeitado": "bad", "negado": "bad"}
    try:
        out["reembolsos"] = await tbl(
            "Reembolsos", "Solicitações de reembolso (visibilidade)", "—",
            ["Código", "Descrição", "Valor", "Status"], "1fr 2fr 1fr 0.9fr",
            "SELECT coalesce(code,'—'), coalesce(title,'—'), total_amount, coalesce(status::text,'—'), "
            "coalesce(description,'—'), approved_amount, submitted_at, approved_at, coalesce(bank_code,'—') "
            "FROM reimbursement_requests ORDER BY submitted_at DESC NULLS LAST LIMIT 200",
            lambda r: [t(r[0], 600, "#0F1B3A"), t((r[1] or '—')[:60]), t(brl(r[2]) if r[2] is not None else '—', 600),
                       b((r[3] or '—').replace('_', ' ').capitalize(), _rt.get((r[3] or '').lower(), "info"))],
            editfn=lambda r: {
                "btnLabel": "Ver reembolso", "readOnly": True, "title": f"Reembolso — {r[0]}",
                "fields": [
                    {"label": "Código", "value": r[0]}, {"label": "Status", "value": (r[3] or "—").replace("_", " ").capitalize()},
                    {"label": "Título", "value": r[1], "span": "span 2"},
                    {"label": "Descrição", "value": r[4], "span": "span 2"},
                    {"label": "Valor solicitado", "value": brl(r[2]) if r[2] is not None else "—"},
                    {"label": "Valor aprovado", "value": brl(r[5]) if r[5] is not None else "—"},
                    {"label": "Submetido em", "value": _fmtdate(r[6])}, {"label": "Aprovado em", "value": _fmtdate(r[7])},
                    {"label": "Banco", "value": r[8]},
                ],
            })
    except Exception:  # noqa: BLE001
        pass

    # Colaboradores — ENRIQUECIDO (fidelidade: Email/Matrícula/Departamento/Admissão + KPIs)
    try:
        _tot = await _scalar(db, "SELECT count(*) FROM employees")
        _atv = await _scalar(db, "SELECT count(*) FROM employees WHERE status='ativo'")
        _colab = await tbl(
            "Colaboradores", f"{_tot or 0} colaboradores · {_atv or 0} ativos", "—",
            ["Colaborador", "Email", "Matrícula", "Cargo", "Departamento", "Admissão", "Status"],
            "1.6fr 1.8fr 0.8fr 1.3fr 1.1fr 0.9fr 0.8fr",
            "SELECT coalesce(nome,'—'), coalesce(email,'—'), coalesce(matricula,'—'), coalesce(cargo,'—'), "
            "coalesce(departamento, setor, '—'), data_admissao, coalesce(status,'—'), "
            "coalesce(cpf,'—'), coalesce(telefone,'—'), coalesce(rg,'—'), data_nascimento, "
            "coalesce(posto_atual_nome,'—'), coalesce(cliente_nome,'—'), coalesce(pix_key, pix, '—'), "
            "coalesce(gestor_nome,'—'), CAST(id AS TEXT) "
            "FROM employees ORDER BY nome LIMIT 300",
            lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t(r[2]), t(r[3]), t(r[4]), t(_fmtdate(r[5])),
                       b((r[6] or '—').capitalize(), "ok" if (r[6] or '') == "ativo" else "mut")],
            editfn=lambda r: {
                "btnLabel": "Ver ficha", "readOnly": True, "title": f"Ficha — {r[0]}",
                "fields": [
                    {"label": "Nome", "value": r[0], "span": "span 2"},
                    {"label": "CPF", "value": r[7]}, {"label": "RG", "value": r[9]},
                    {"label": "Nascimento", "value": _fmtdate(r[10])}, {"label": "Matrícula", "value": r[2]},
                    {"label": "Cargo", "value": r[3]}, {"label": "Departamento", "value": r[4]},
                    {"label": "Admissão", "value": _fmtdate(r[5])},
                    {"label": "Status", "value": (r[6] or "—").capitalize()},
                    {"label": "E-mail", "value": r[1], "span": "span 2"},
                    {"label": "Telefone", "value": r[8]}, {"label": "Gestor", "value": r[14]},
                    {"label": "Posto atual", "value": r[11]}, {"label": "Cliente", "value": r[12]},
                    {"label": "Chave PIX", "value": r[13], "span": "span 2"},
                ],
            },
            actionsfn=lambda r: [{
                "btnLabel": "Editar contato", "title": f"Editar contato — {r[0]}",
                "endpoint": f"/api/v1/people-management/hr/employees/{r[15]}", "method": "PATCH",
                "okMsg": "Contato atualizado. Recarregue a tela.",
                "fields": [
                    {"key": "celular", "label": "Telefone / Celular", "type": "text", "span": "span 2",
                     "value": (r[8] if r[8] and r[8] != "—" else "")},
                    {"key": "email", "label": "E-mail", "type": "text", "span": "span 2",
                     "value": (r[1] if r[1] and r[1] != "—" else "")},
                ],
            }])
        # Afastados: MESMA definição do clássico (colaboradores page filtra status LIKE 'afastado%'
        # → afastado_inss), NÃO o afastados_ativos do SSTService (que conta afastamentos-registro).
        _afast = await _scalar(db, "SELECT count(*) FROM employees WHERE lower(coalesce(status,'')) LIKE 'afastado%'")
        _colab["panelGrid"] = "1fr"
        _colab["panels"] = [{"title": "Resumo", "rows": [
            {"left": "Total", "right": str(_tot or 0), **S["info"]},
            {"left": "Ativos", "right": str(_atv or 0), **S["ok"]},
            {"left": "Afastados", "right": str(_afast), **S["warn"]},
        ]}]
        out["colaboradores"] = _colab
    except Exception:  # noqa: BLE001
        pass

    # Rondas — inspection_rounds (leitura) com Relatório PDF por-linha. Rota curl-provada:
    # GET /api/v1/operacional/rondas/{id}/relatorio/pdf → 200 application/pdf ~267KB.
    _ron_tone = {"concluida": "ok", "concluída": "ok", "finalizada": "ok", "em_andamento": "warn",
                 "iniciada": "warn", "pausada": "warn", "cancelada": "bad", "agendada": "info"}
    try:
        n_ron = await _scalar(db, "SELECT count(*) FROM inspection_rounds") or 0
        out["rondas"] = await tbl(
            "Rondas", f"{n_ron} ronda(s)", "—",
            ["Código", "Inspetor", "Data", "Duração", "Ocorrências", "Status"],
            "1.1fr 1.6fr 1fr 0.8fr 0.9fr 0.9fr",
            "SELECT id, coalesce(code,'—'), coalesce(inspector_name,'—'), coalesce(scheduled_date, started_at), "
            "duration_minutes, coalesce(total_occurrences,0), coalesce(status::text,'—'), "
            "coalesce(inspector_role,'—'), started_at, coalesce(total_checkpoints,0), "
            "coalesce(total_disciplinary_actions,0), coalesce(observations,'—') "
            "FROM inspection_rounds ORDER BY coalesce(scheduled_date, started_at, created_at) DESC NULLS LAST LIMIT 200",
            lambda r: [t(r[1], 600, "#0F1B3A"), t(r[2]), t(_fmtdate(r[3])),
                       t(f"{int(r[4])} min" if r[4] is not None else '—'), t(str(int(r[5] or 0))),
                       b((r[6] or '—').replace('_', ' ').capitalize(), _ron_tone.get((r[6] or '').lower(), "info"))],
            docsfn=lambda r: [doc("Relatório (PDF)", f"/api/v1/operacional/rondas/{r[0]}/relatorio/pdf", fmt="pdf")],
            editfn=lambda r: {
                "btnLabel": "Ver ronda", "readOnly": True, "title": f"Ronda — {r[1]}",
                "fields": [
                    {"label": "Código", "value": r[1]}, {"label": "Status", "value": (r[6] or "—").replace("_", " ").capitalize()},
                    {"label": "Inspetor", "value": r[2]}, {"label": "Função", "value": (r[7] or "—").replace("_", " ").capitalize()},
                    {"label": "Agendada", "value": _fmtdate(r[3])}, {"label": "Iniciada", "value": _fmtdate(r[8])},
                    {"label": "Duração", "value": (f"{int(r[4])} min" if r[4] is not None else "—")},
                    {"label": "Checkpoints", "value": str(int(r[9] or 0))},
                    {"label": "Ocorrências", "value": str(int(r[5] or 0))},
                    {"label": "Medidas disciplinares", "value": str(int(r[10] or 0))},
                    {"label": "Observações", "value": r[11], "span": "span 2"},
                ],
            })
    except Exception:  # noqa: BLE001
        pass

    # Medidas administrativas — disciplinary_actions (LEITURA real; mata a casca fabricada).
    _med_tone = {"aplicada": "ok", "aprovada": "ok", "assinada": "ok",
                 "pendente_aprovacao": "warn", "pendente_assinatura": "warn", "rascunho": "info",
                 "rejeitada": "bad", "recusada_assinatura": "bad", "cancelada": "mut"}
    try:
        n_med = await _scalar(db, "SELECT count(*) FROM disciplinary_actions WHERE coalesce(is_active,true)") or 0
        out["medidas-administrativas"] = await tbl(
            "Medidas administrativas", f"{n_med} medida(s) · fonte: disciplinary_actions", "—",
            ["Colaborador", "Tipo", "Motivo", "Data", "Status"], "1.8fr 1.2fr 1.6fr 0.9fr 1fr",
            "SELECT id, coalesce(employee_name,'—'), coalesce(action_type::text,'—'), "
            "coalesce(reason_description, reason_category::text, '—'), incident_date, coalesce(status::text,'—'), "
            "coalesce(code,'—'), coalesce(reason_category::text,'—'), coalesce(witness_1_name,'—'), "
            "coalesce(witness_2_name,'—'), created_at, coalesce(rejection_reason,'—'), "
            "(employee_signature_id IS NOT NULL), (supervisor_signature_id IS NOT NULL), (hr_signature_id IS NOT NULL) "
            "FROM disciplinary_actions WHERE coalesce(is_active,true) "
            "ORDER BY coalesce(incident_date, created_at) DESC NULLS LAST LIMIT 200",
            lambda r: [t(r[1], 600, "#0F1B3A"), t((r[2] or '—').replace('_', ' ').capitalize()),
                       t((r[3] or '—')[:60]), t(_fmtdate(r[4])),
                       b((r[5] or '—').replace('_', ' ').capitalize(), _med_tone.get((r[5] or '').lower(), "info"))],
            editfn=lambda r: {
                "btnLabel": "Ver medida", "readOnly": True, "title": f"Medida — {r[1]}",
                "fields": [
                    {"label": "Código", "value": r[6]}, {"label": "Status", "value": (r[5] or "—").replace("_", " ").capitalize()},
                    {"label": "Colaborador", "value": r[1], "span": "span 2"},
                    {"label": "Tipo", "value": (r[2] or "—").replace("_", " ").capitalize()},
                    {"label": "Categoria", "value": (r[7] or "—").replace("_", " ").capitalize()},
                    {"label": "Data do incidente", "value": _fmtdate(r[4])}, {"label": "Registrada em", "value": _fmtdate(r[10])},
                    {"label": "Motivo / descrição", "value": r[3], "span": "span 2"},
                    {"label": "Testemunha 1", "value": r[8]}, {"label": "Testemunha 2", "value": r[9]},
                    {"label": "Assinaturas", "span": "span 2",
                     "value": f"Colaborador: {'sim' if r[12] else 'não'} · Supervisor: {'sim' if r[13] else 'não'} · RH: {'sim' if r[14] else 'não'}"},
                    {"label": "Motivo da rejeição", "value": r[11], "span": "span 2"},
                ],
            })
    except Exception:  # noqa: BLE001 — nunca derruba o módulo
        pass

    # Form "Nova medida" (ESCRITA real → /action/medida-administrativa). Nome/CPF resolvidos no server.
    try:
        _emp = (await db.execute(_sqltext(
            "SELECT id, nome FROM employees WHERE coalesce(status,'')='ativo' ORDER BY nome LIMIT 500"))).fetchall()
        _tipos = [("advertencia_verbal", "Advertência verbal"), ("advertencia_escrita", "Advertência escrita"),
                  ("suspensao", "Suspensão"), ("demissao_justa_causa", "Demissão por justa causa")]
        _cats = [("falta", "Falta"), ("atraso", "Atraso"), ("insubordinacao", "Insubordinação"),
                 ("indisciplina", "Indisciplina"), ("dano_patrimonio", "Dano ao patrimônio"),
                 ("negligencia", "Negligência"), ("abandono_emprego", "Abandono de emprego"),
                 ("ofensa_moral", "Ofensa moral"), ("ofensa_fisica", "Ofensa física"), ("outros", "Outros")]
        out["disciplinar"] = {
            "title": "Nova medida disciplinar", "sub": "Cria a medida (rascunho) — validação CLT no motor real",
            "cta": "Registrar medida", "type": "form",
            "submit": {"endpoint": "/api/v1/redesign/action/medida-administrativa", "okMsg": "Medida registrada (rascunho)"},
            "fields": [
                {"key": "employee_id", "label": "Colaborador*", "type": "select", "span": "span 2", "ph": "Selecione o colaborador",
                 "options": [{"value": str(i), "label": (n or '—')} for i, n in _emp]},
                {"key": "action_type", "label": "Tipo*", "type": "select", "span": "span 1", "ph": "Tipo",
                 "options": [{"value": v, "label": l} for v, l in _tipos]},
                {"key": "reason_category", "label": "Motivo (CLT)*", "type": "select", "span": "span 1", "ph": "Categoria",
                 "options": [{"value": v, "label": l} for v, l in _cats]},
                {"key": "incident_date", "label": "Data do incidente*", "type": "date", "span": "span 1"},
                {"key": "reason_description", "label": "Descrição do incidente*", "type": "textarea", "span": "span 2", "ph": "Descreva o ocorrido (mín. 10 caracteres)…"},
            ],
        }
    except Exception:  # noqa: BLE001
        pass

    # Banco de horas — time_bank (LEITURA real; mata "João da Silva/+12h"). Vazio→honesto.
    _bh_tone = {"aprovado": "ok", "aprovada": "ok", "compensado": "ok",
                "pendente": "warn", "em_analise": "warn", "rejeitado": "bad", "rejeitada": "bad"}
    try:
        n_bh = await _scalar(db, "SELECT count(*) FROM time_bank WHERE coalesce(is_active,true)") or 0
        out["banco-horas"] = await tbl(
            "Banco de horas", f"{n_bh} lançamento(s) · fonte: time_bank", "—",
            ["Colaborador", "Tipo", "Horas", "Saldo", "Data", "Status"], "1.8fr 1fr 0.8fr 0.8fr 0.9fr 1fr",
            "SELECT coalesce(e.nome,'—'), coalesce(tb.entry_type,'—'), tb.hours, tb.balance_after, "
            "tb.reference_date, coalesce(tb.status,'—') "
            "FROM time_bank tb LEFT JOIN employees e ON e.id=tb.employee_id "
            "WHERE coalesce(tb.is_active,true) ORDER BY tb.reference_date DESC NULLS LAST LIMIT 200",
            lambda r: [t(r[0], 600, "#0F1B3A"), t((r[1] or '—').replace('_', ' ').capitalize()),
                       t(f"{float(r[2]):+.1f}h" if r[2] is not None else '—', 600,
                         "#16A34A" if (r[2] or 0) >= 0 else "#DC2626"),
                       t(f"{float(r[3]):+.1f}h" if r[3] is not None else '—', 600),
                       t(_fmtdate(r[4])), b((r[5] or '—').replace('_', ' ').capitalize(), _bh_tone.get((r[5] or '').lower(), "info"))])
    except Exception:  # noqa: BLE001
        pass

    # Passagem de turno — operacional_passagens_turno (LEITURA real).
    try:
        n_pt = await _scalar(db, "SELECT count(*) FROM operacional_passagens_turno WHERE coalesce(is_active,true)") or 0
        out["passagem-turno"] = await tbl(
            "Passagem de turno", f"{n_pt} passagem(ns) · fonte: operacional_passagens_turno", "—",
            ["Posto", "Turno", "Autor", "Data", "Resumo"], "1.6fr 1fr 1.3fr 0.9fr 2fr",
            "SELECT coalesce(p.name,'—'), coalesce(pt.turno,'—'), coalesce(pt.author_nome,'—'), pt.data_turno, coalesce(pt.resumo,'—') "
            "FROM operacional_passagens_turno pt LEFT JOIN posts p ON p.id=pt.post_id "
            "WHERE coalesce(pt.is_active,true) ORDER BY pt.criada_em DESC NULLS LAST LIMIT 200",
            lambda r: [t(r[0], 600, "#0F1B3A"), t((r[1] or '—').capitalize()), t(r[2]), t(_fmtdate(r[3])), t((r[4] or '—')[:80])])
    except Exception:  # noqa: BLE001
        pass

    # Instruções de posto — operacional_post_orders × posts (LEITURA real; cobertura por posto).
    try:
        out["instrucoes-posto"] = await tbl(
            "Instruções de posto", "Procedimentos por posto · fonte: operacional_post_orders", "—",
            ["Posto", "Documento", "Versão", "Situação"], "2fr 2fr 0.8fr 1fr",
            "SELECT p.name, coalesce(po.titulo,'—'), coalesce(po.versao,0), "
            "(po.conteudo IS NOT NULL AND coalesce(po.conteudo,'') <> '') "
            "FROM posts p LEFT JOIN operacional_post_orders po ON po.post_id=p.id "
            "WHERE coalesce(p.is_active,true) ORDER BY p.name LIMIT 300",
            lambda r: [t(r[0] or '—', 600, "#0F1B3A"), t(r[1]), t(f"v{int(r[2] or 0)}" if r[2] else '—'),
                       b("Com instrução", "ok") if r[3] else b("Sem instrução", "mut")])
    except Exception:  # noqa: BLE001
        pass

    # Forms de ESCRITA (humano-operado; reusam controllers via gate). Opções vêm do banco.
    try:
        _posts = (await db.execute(_sqltext(
            "SELECT id, name FROM posts WHERE coalesce(is_active,true) ORDER BY name LIMIT 500"))).fetchall()
        _post_opts = [{"value": str(i), "label": (n or '—')} for i, n in _posts]
        _emp2 = (await db.execute(_sqltext(
            "SELECT id, nome FROM employees WHERE coalesce(status,'')='ativo' ORDER BY nome LIMIT 500"))).fetchall()
        _emp_opts = [{"value": str(i), "label": (n or '—')} for i, n in _emp2]

        out["passagem-turno-nova"] = {
            "title": "Nova passagem de turno", "sub": "Registro de troca entre plantões", "cta": "Registrar passagem",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/passagem-turno", "okMsg": "Passagem registrada"},
            "fields": [
                {"key": "post_id", "label": "Posto*", "type": "select", "span": "span 2", "ph": "Selecione o posto", "options": _post_opts},
                {"key": "turno", "label": "Turno*", "type": "select", "span": "span 1", "ph": "Turno",
                 "options": [{"value": v, "label": l} for v, l in [("diurno", "Diurno"), ("noturno", "Noturno"), ("madrugada", "Madrugada")]]},
                {"key": "data_turno", "label": "Data do turno", "type": "date", "span": "span 1"},
                {"key": "resumo", "label": "Resumo do turno*", "type": "textarea", "span": "span 2", "ph": "Como foi o turno (mín. 5 caracteres)…"},
                {"key": "pendencias", "label": "Pendências p/ o próximo", "type": "textarea", "span": "span 2", "ph": "Opcional…"},
            ],
        }
        out["instrucao-posto-editar"] = {
            "title": "Editar instruções do posto", "sub": "Upsert versionado — só gestão", "cta": "Salvar instruções",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/instrucao-posto", "okMsg": "Instruções salvas"},
            "fields": [
                {"key": "post_id", "label": "Posto*", "type": "select", "span": "span 2", "ph": "Selecione o posto", "options": _post_opts},
                {"key": "titulo", "label": "Título", "type": "text", "span": "span 2", "ph": "Ex.: POP Portaria v4"},
                {"key": "conteudo", "label": "Conteúdo*", "type": "textarea", "span": "span 2", "ph": "Procedimento operacional (mín. 10 caracteres)…"},
            ],
        }
        out["banco-horas-lancar"] = {
            "title": "Lançar banco de horas", "sub": "Crédito/débito de horas (requer aprovação p/ efetivar)", "cta": "Lançar",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/banco-horas", "okMsg": "Lançamento criado"},
            "fields": [
                {"key": "employee_id", "label": "Colaborador*", "type": "select", "span": "span 2", "ph": "Selecione o colaborador", "options": _emp_opts},
                {"key": "entry_type", "label": "Tipo*", "type": "select", "span": "span 1", "ph": "Tipo",
                 "options": [{"value": v, "label": l} for v, l in [("credit", "Crédito (a favor do empregador)"), ("debit", "Débito (a favor do empregado)"), ("adjustment", "Ajuste manual")]]},
                {"key": "hours", "label": "Horas*", "type": "text", "span": "span 1", "ph": "Ex.: 8 ou 2.5"},
                {"key": "reference_date", "label": "Data de referência*", "type": "date", "span": "span 1"},
                {"key": "reason", "label": "Motivo", "type": "text", "span": "span 1", "ph": "Opcional"},
                {"key": "description", "label": "Descrição", "type": "textarea", "span": "span 2", "ph": "Opcional…"},
            ],
        }
        out["banco-horas-compensar"] = {
            "title": "Compensar horas", "sub": "Registra a compensação (folga) contra o saldo do colaborador", "cta": "Compensar",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/banco-horas-compensar", "okMsg": "Compensação lançada"},
            "fields": [
                {"key": "employee_id", "label": "Colaborador*", "type": "select", "span": "span 2", "ph": "Selecione o colaborador", "options": _emp_opts},
                {"key": "hours", "label": "Horas a compensar*", "type": "text", "span": "span 1", "ph": "Ex.: 8 ou 2.5"},
                {"key": "compensation_date", "label": "Data da compensação*", "type": "date", "span": "span 1"},
                {"key": "notes", "label": "Observações", "type": "textarea", "span": "span 2", "ph": "Opcional…"},
            ],
        }
        out["avaliacao-criar"] = {
            "title": "Avaliar colaborador", "sub": "Registra avaliação de desempenho (nota 1 a 5) — alimenta o histórico da equipe", "cta": "Registrar avaliação",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/avaliacao-criar", "okMsg": "Avaliação registrada"},
            "fields": [
                {"key": "employee_id", "label": "Colaborador*", "type": "select", "span": "span 2", "ph": "Selecione o colaborador", "options": _emp_opts},
                {"key": "nota", "label": "Nota (1-5)*", "type": "select", "span": "span 1", "ph": "Selecione",
                 "options": [{"value": str(n), "label": f"{n} — {l}"} for n, l in [(5, "Excelente"), (4, "Bom"), (3, "Regular"), (2, "Abaixo"), (1, "Ruim")]]},
                {"key": "competencia", "label": "Competência", "type": "date", "span": "span 1"},
                {"key": "observacao", "label": "Observação", "type": "textarea", "span": "span 2", "ph": "Opcional…"},
            ],
        }
        out["nova-ronda"] = {
            "title": "Nova ronda", "sub": "Agenda uma ronda de inspeção (ciclo de campo é no mobile)", "cta": "Criar ronda",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/nova-ronda", "okMsg": "Ronda criada"},
            "fields": [
                {"key": "inspector_id", "label": "Inspetor*", "type": "select", "span": "span 2", "ph": "Selecione o inspetor", "options": _emp_opts},
                {"key": "scheduled_date", "label": "Data agendada", "type": "date", "span": "span 1"},
                {"key": "observations", "label": "Observações", "type": "textarea", "span": "span 2", "ph": "Opcional…"},
            ],
        }
        _ron_ativas = (await db.execute(_sqltext(
            "SELECT id, coalesce(code,'—'), coalesce(status::text,'—'), scheduled_date FROM inspection_rounds "
            "WHERE coalesce(status::text,'') NOT IN ('concluida','cancelada','concluída') "
            "ORDER BY coalesce(scheduled_date, created_at) DESC LIMIT 200"))).fetchall()
        out["ronda-transicao"] = {
            "title": "Andamento da ronda", "sub": "Iniciar, pausar, retomar, concluir ou cancelar uma ronda (gestor)", "cta": "Aplicar",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/ronda-transicao", "okMsg": "Transição aplicada"},
            "fields": [
                {"key": "round_id", "label": "Ronda*", "type": "select", "span": "span 2", "ph": "Selecione a ronda",
                 "options": [{"value": str(i), "label": f"{c} · {st}" + (f" · {dt.strftime('%d/%m')}" if dt else "")} for i, c, st, dt in _ron_ativas]},
                {"key": "acao", "label": "Ação*", "type": "select", "span": "span 1", "ph": "Selecione",
                 "options": [{"value": v, "label": l} for v, l in [("iniciar", "Iniciar"), ("pausar", "Pausar"), ("retomar", "Retomar"), ("concluir", "Concluir"), ("cancelar", "Cancelar")]]},
                {"key": "motivo", "label": "Motivo (se cancelar)", "type": "text", "span": "span 1", "ph": "Opcional"},
            ],
        }
        # ── 3 edge-actions ligadas 2026-08-04 (marcar-todas notif · checkin manual · localização posto) ──
        out["notificacoes-marcar-todas"] = {
            "title": "Marcar notificações como lidas", "sub": "Marca TODAS as suas notificações como lidas", "cta": "Marcar todas",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/notificacoes-marcar-todas", "okMsg": "Notificações marcadas como lidas"},
            "fields": [],
        }
        _shifts_hoje = (await db.execute(_sqltext(
            "SELECT s.id, coalesce(e.nome,'—') || coalesce(' · '||to_char(s.planned_start_time,'HH24:MI'),'') "
            "FROM shifts s LEFT JOIN employees e ON e.id=s.employee_id "
            "WHERE s.shift_date = CURRENT_DATE AND coalesce(s.is_active,true) ORDER BY e.nome LIMIT 300"))).fetchall()
        _shift_opts = [{"value": str(i), "label": (n or '—')} for i, n in _shifts_hoje]
        out["checkin-manual"] = {
            "title": "Check-in manual", "sub": "Registra presença quando o facial falha (turno de HOJE)", "cta": "Registrar check-in",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/checkin-manual", "okMsg": "Check-in registrado"},
            "fields": [
                {"key": "shift_id", "label": "Turno de hoje*", "type": "select", "span": "span 2", "ph": "Selecione o turno", "options": _shift_opts},
                {"key": "observacao", "label": "Observação", "type": "textarea", "span": "span 2", "ph": "Opcional (motivo do check-in manual)…"},
            ],
        }
        out["posto-localizacao"] = {
            "title": "Definir localização do posto", "sub": "GPS capturado no local (latitude/longitude reais)", "cta": "Salvar localização",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/posto-localizacao", "okMsg": "Localização definida"},
            "fields": [
                {"key": "post_id", "label": "Posto*", "type": "select", "span": "span 2", "ph": "Selecione o posto", "options": _post_opts},
                {"key": "lat", "label": "Latitude*", "type": "text", "span": "span 1", "ph": "Ex.: -3.10194"},
                {"key": "lng", "label": "Longitude*", "type": "text", "span": "span 1", "ph": "Ex.: -60.02510"},
                {"key": "raio_metros", "label": "Raio (metros)", "type": "text", "span": "span 1", "ph": "Opcional, ex.: 100"},
            ],
        }
        out["posto-editar"] = {
            "title": "Editar posto", "sub": "Atualiza dados cadastrais do posto (nome/endereço/cidade/UF/CEP)", "cta": "Salvar posto",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/posto-editar", "okMsg": "Posto atualizado"},
            "fields": [
                {"key": "post_id", "label": "Posto*", "type": "select", "span": "span 2", "ph": "Selecione o posto", "options": _post_opts},
                {"key": "name", "label": "Novo nome", "type": "text", "span": "span 2", "ph": "Deixe vazio p/ manter"},
                {"key": "address", "label": "Endereço", "type": "text", "span": "span 2", "ph": "Deixe vazio p/ manter"},
                {"key": "city", "label": "Cidade", "type": "text", "span": "span 1", "ph": "Manter"},
                {"key": "state", "label": "UF", "type": "text", "span": "span 1", "ph": "Ex.: AM"},
                {"key": "zip_code", "label": "CEP", "type": "text", "span": "span 1", "ph": "Manter"},
            ],
        }
    except Exception:  # noqa: BLE001
        pass

    # ── Read-fixes: telas que caíam na casca estática → tabela real (vazio→honesto) ──
    _sub_tone = {"confirmada": "ok", "concluida": "ok", "aprovada": "ok", "pendente": "warn",
                 "solicitada": "warn", "rejeitada": "bad", "cancelada": "mut"}
    try:  # Substituições — substitutions
        n = await _scalar(db, "SELECT count(*) FROM substitutions WHERE coalesce(is_active,true)") or 0
        out["substituicoes"] = await tbl(
            "Substituições", f"{n} substituição(ões) · fonte: substitutions", "—",
            ["Data", "Ausente", "Substituto", "Posto", "Status"], "0.9fr 1.6fr 1.6fr 1.4fr 1fr",
            "SELECT s.substitution_date, coalesce(eo.nome,'—'), coalesce(es.nome,'—'), coalesce(p.name,'—'), coalesce(s.status::text,'—') "
            "FROM substitutions s LEFT JOIN employees eo ON eo.id=s.original_employee_id "
            "LEFT JOIN employees es ON es.id=s.substitute_employee_id LEFT JOIN posts p ON p.id=s.post_id "
            "WHERE coalesce(s.is_active,true) ORDER BY s.substitution_date DESC NULLS LAST LIMIT 200",
            lambda r: [t(_fmtdate(r[0])), t(r[1], 600, "#0F1B3A"), t(r[2]), t(r[3]),
                       b((r[4] or '—').replace('_', ' ').capitalize(), _sub_tone.get((r[4] or '').lower(), "info"))])
    except Exception:  # noqa: BLE001
        pass
    try:  # Escalas · Templates — scale_templates
        out["escalas-templates"] = await tbl(
            "Templates de escala", "Modelos reutilizáveis · fonte: scale_templates", "—",
            ["Template", "Descrição", "Usos", "Último uso"], "1.6fr 2fr 0.7fr 1fr",
            "SELECT name, coalesce(description,'—'), coalesce(times_used,0), last_used "
            "FROM scale_templates WHERE coalesce(is_active,true) ORDER BY name LIMIT 200",
            lambda r: [t(r[0], 600, "#0F1B3A"), t((r[1] or '—')[:70]), t(str(int(r[2] or 0))), t(_fmtdate(r[3]))])
    except Exception:  # noqa: BLE001
        pass
    try:  # Escalas · Grade por pessoa — shifts agregado
        out["escalas-grade"] = await tbl(
            "Grade por pessoa", "Turnos por colaborador · fonte: shifts", "—",
            ["Colaborador", "Turnos", "De", "Até"], "2fr 0.8fr 1fr 1fr",
            "SELECT coalesce(e.nome,'—'), count(*), min(s.shift_date), max(s.shift_date) "
            "FROM shifts s LEFT JOIN employees e ON e.id=s.employee_id WHERE coalesce(s.is_active,true) "
            "GROUP BY e.nome ORDER BY count(*) DESC LIMIT 300",
            lambda r: [t(r[0], 600, "#0F1B3A"), t(str(int(r[1] or 0))), t(_fmtdate(r[2])), t(_fmtdate(r[3]))])
    except Exception:  # noqa: BLE001
        pass
    try:  # Avaliação de equipe — operacional_avaliacoes_equipe
        n = await _scalar(db, "SELECT count(*) FROM operacional_avaliacoes_equipe WHERE coalesce(is_active,true)") or 0
        out["avaliacao-equipe"] = await tbl(
            "Avaliação de equipe", f"{n} avaliação(ões) · fonte: operacional_avaliacoes_equipe", "—",
            ["Colaborador", "Avaliador", "Nota", "Competência", "Data"], "1.8fr 1.6fr 0.7fr 1.2fr 0.9fr",
            "SELECT coalesce(e.nome,'—'), coalesce(a.avaliador_nome,'—'), a.nota, coalesce(a.competencia::text,'—'), a.criada_em "
            "FROM operacional_avaliacoes_equipe a LEFT JOIN employees e ON e.id=a.employee_id "
            "WHERE coalesce(a.is_active,true) ORDER BY a.criada_em DESC NULLS LAST LIMIT 200",
            lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]),
                       b(str(r[2]) if r[2] is not None else '—', "ok" if (r[2] or 0) >= 7 else ("warn" if (r[2] or 0) >= 5 else "bad")),
                       t((r[3] or '—').capitalize()), t(_fmtdate(r[4]))])
    except Exception:  # noqa: BLE001
        pass
    try:  # Diaristas · Escala — diarist_schedules (sem join: n=0, colunas seguras)
        n = await _scalar(db, "SELECT count(*) FROM diarist_schedules WHERE coalesce(ativo,true)") or 0
        out["diaristas-escala"] = await tbl(
            "Escala de diaristas", f"{n} agendamento(s) · fonte: diarist_schedules", "—",
            ["Data", "Início", "Fim", "Status", "Valor previsto"], "1fr 0.8fr 0.8fr 1fr 1.1fr",
            "SELECT data_trabalho, hora_inicio, hora_fim, coalesce(status::text,'—'), valor_previsto "
            "FROM diarist_schedules WHERE coalesce(ativo,true) ORDER BY data_trabalho DESC NULLS LAST LIMIT 200",
            lambda r: [t(_fmtdate(r[0]), 600, "#0F1B3A"), t(str(r[1])[:5] if r[1] else '—'), t(str(r[2])[:5] if r[2] else '—'),
                       t((r[3] or '—').capitalize()), t(brl(r[4]) if r[4] is not None else '—', 600)])
    except Exception:  # noqa: BLE001
        pass
    try:  # Diaristas · Fechamento — diarist_payments
        n = await _scalar(db, "SELECT count(*) FROM diarist_payments WHERE coalesce(ativo,true)") or 0
        out["diaristas-fechamento"] = await tbl(
            "Fechamento de diaristas", f"{n} fechamento(s) · fonte: diarist_payments", "—",
            ["Referência", "Bruto", "Líquido", "Status", "Pagamento"], "1fr 1fr 1fr 1fr 1fr",
            "SELECT data_referencia, valor_bruto, valor_liquido, coalesce(status::text,'—'), data_pagamento "
            "FROM diarist_payments WHERE coalesce(ativo,true) ORDER BY data_referencia DESC NULLS LAST LIMIT 200",
            lambda r: [t(_fmtdate(r[0]), 600, "#0F1B3A"), t(brl(r[1]) if r[1] is not None else '—'),
                       t(brl(r[2]) if r[2] is not None else '—', 600), t((r[3] or '—').capitalize()), t(_fmtdate(r[4]))])
    except Exception:  # noqa: BLE001
        pass

    # ── Balde A: dashboards com backend REAL (cobertura via repo; kpi/relatorios via counts) ──
    try:  # Cobertura — reusa ReportsRepository.get_coverage (fidelidade com o clássico)
        from datetime import date as _date

        from modules.operacional.repositories.reports_repository import ReportsRepository
        _end = _date.today()
        _start = _end.replace(day=1)
        items = await ReportsRepository(db).get_coverage(_start, _end)
        total = len(items)
        covered = sum(1 for it in items if (it.get("coverage_rate") or 0) >= 100)
        descob = total - covered
        rate = round(covered / total * 100, 1) if total else 100.0
        piores = sorted(items, key=lambda x: x.get("coverage_rate") or 0)[:10]
        out["cobertura"] = {
            "title": "Cobertura de postos", "sub": f"Mês corrente · fonte: allocations × postos · {total} posto(s)",
            "type": "dash", "panelGrid": "1fr",
            "kpis": [
                {"v": str(total), "l": "Postos", "icon": IC["shield"], "color": "#0F1B3A"},
                {"v": str(covered), "l": "Cobertos", "icon": IC["shield"], "color": "#16A34A"},
                {"v": f"{rate}%", "l": "Taxa de cobertura", "icon": IC["shield"], "color": "#16A34A" if rate >= 90 else "#C2410C"},
                {"v": str(descob), "l": "Descobertos", "icon": IC["alert"], "color": "#DC2626" if descob else "#0F1B3A"},
            ],
            "panels": [{"title": "Postos com menor cobertura", "rows": [
                {"left": it.get("post_name") or "—", "right": f"{(it.get('coverage_rate') or 0):.0f}%",
                 **(S["bad"] if (it.get("coverage_rate") or 0) < 50 else S["warn"] if (it.get("coverage_rate") or 0) < 100 else S["ok"])}
                for it in piores] or [{"left": "Sem postos cadastrados", "right": "—", **S["mut"]}]}],
        }
        # Preditor de cobertura REAL (substitui o stub CoveragePredictorAgent que devolvia {}):
        # lista os postos em risco de descobrir = cobertura < 100% (dado real, sem ML/fabricação).
        _risco = sorted((it for it in items if (it.get("coverage_rate") or 0) < 100),
                        key=lambda x: x.get("coverage_rate") or 0)
        out["cobertura-risco"] = {
            "title": "Cobertura em risco",
            "sub": f"{len(_risco)} posto(s) abaixo de 100% · aja antes de descobrir",
            "type": "table", "searchHint": "Buscar posto…", "grid": "2.4fr 1fr 1fr",
            "cols": ["Posto", "Cobertura", "Risco"],
            "rows": [{"cells": [
                t(it.get("post_name") or "—", 600, "#0F1B3A"),
                t(f"{(it.get('coverage_rate') or 0):.0f}%", 600),
                b("Crítico", "bad") if (it.get("coverage_rate") or 0) < 50 else b("Atenção", "warn"),
            ]} for it in _risco]
            or [{"cells": [t("Todos os postos 100% cobertos ✓", 500, "#16A34A"), t("100%"), b("OK", "ok")]}],
        }
    except Exception:  # noqa: BLE001
        pass

    try:  # KPIs operacionais — estado atual (contagens reais)
        _post = await _scalar(db, "SELECT count(*) FROM posts WHERE coalesce(is_active,true)") or 0
        _occ_ab = await _scalar(db, "SELECT count(*) FROM occurrences WHERE lower(coalesce(status::text,''))='aberta'") or 0
        _ron_mes = await _scalar(db, "SELECT count(*) FROM inspection_rounds WHERE coalesce(scheduled_date, created_at) >= date_trunc('month', now())") or 0
        _sub_mes = await _scalar(db, "SELECT count(*) FROM substitutions WHERE coalesce(is_active,true) AND coalesce(substitution_date, created_at::date) >= date_trunc('month', now())::date") or 0
        out["kpi"] = {
            "title": "KPIs operacionais", "sub": "Indicadores reais (estado atual)", "type": "dash", "panelGrid": "1fr",
            "kpis": [
                {"v": str(_post), "l": "Postos ativos", "icon": IC["shield"], "color": "#0F1B3A"},
                {"v": str(_occ_ab), "l": "Ocorrências abertas", "icon": IC["alert"], "color": "#C2410C" if _occ_ab else "#0F1B3A"},
                {"v": str(_ron_mes), "l": "Rondas (mês)", "icon": IC["shield"], "color": "#0F1B3A"},
                {"v": str(_sub_mes), "l": "Substituições (mês)", "icon": IC["users"], "color": "#0F1B3A"},
            ],
            "panels": [{"title": "Resumo", "rows": [
                {"left": "Postos ativos", "right": str(_post), **S["info"]},
                {"left": "Ocorrências abertas", "right": str(_occ_ab), **(S["warn"] if _occ_ab else S["ok"])},
                {"left": "Rondas no mês", "right": str(_ron_mes), **S["info"]},
                {"left": "Substituições no mês", "right": str(_sub_mes), **S["info"]},
            ]}],
        }
    except Exception:  # noqa: BLE001
        pass

    try:  # Relatórios — resumo mensal real (totais do mês)
        _med_mes = await _scalar(db, "SELECT count(*) FROM disciplinary_actions WHERE coalesce(is_active,true) AND coalesce(incident_date, created_at::date) >= date_trunc('month', now())::date") or 0
        _occ_mes = await _scalar(db, "SELECT count(*) FROM occurrences WHERE coalesce(occurred_at, created_at) >= date_trunc('month', now())") or 0
        _pass_mes = await _scalar(db, "SELECT count(*) FROM operacional_passagens_turno WHERE coalesce(is_active,true) AND coalesce(data_turno, criada_em::date) >= date_trunc('month', now())::date") or 0
        _col = await _scalar(db, "SELECT count(*) FROM employees WHERE coalesce(status,'')='ativo'") or 0
        out["relatorios"] = {
            "title": "Relatórios operacionais", "sub": "Resumo do mês corrente (dados reais)", "type": "dash", "panelGrid": "1fr",
            "kpis": [
                {"v": str(_occ_mes), "l": "Ocorrências (mês)", "icon": IC["alert"], "color": "#C2410C" if _occ_mes else "#0F1B3A"},
                {"v": str(_med_mes), "l": "Medidas (mês)", "icon": IC["shield"], "color": "#0F1B3A"},
                {"v": str(_pass_mes), "l": "Passagens (mês)", "icon": IC["shield"], "color": "#0F1B3A"},
                {"v": str(_col), "l": "Colaboradores ativos", "icon": IC["users"], "color": "#0F1B3A"},
            ],
            "panels": [{"title": "Totais do mês", "rows": [
                {"left": "Ocorrências registradas", "right": str(_occ_mes), **S["info"]},
                {"left": "Medidas administrativas", "right": str(_med_mes), **S["info"]},
                {"left": "Passagens de turno", "right": str(_pass_mes), **S["info"]},
                {"left": "Colaboradores ativos", "right": str(_col), **S["ok"]},
            ]}],
        }
    except Exception:  # noqa: BLE001
        pass

    # ── Balde B: camada cognitiva (Fase 5/6) — reusa funções REAIS (command_center/panorama) ──
    try:
        from modules.operacional.ai.controller import command_center as _cc
        cc = await _cc(None, db)
    except Exception:  # noqa: BLE001
        cc = {}
        await db.rollback()
    if cc:
        ov = cc.get("overview", {}) or {}
        ag = cc.get("agents_status", {}) or {}
        cov = cc.get("coverage_prediction", {}) or {}
        _risk = str(cov.get("nivel_risco", "—")).capitalize()
        _cob_atual = ov.get("cobertura_atual") or 0
        out["ai-command-center"] = {
            "title": "AI Command Center", "sub": "Centro de comando operacional · dado real", "type": "dash", "panelGrid": "1fr",
            "kpis": [
                {"v": str(ov.get("agentes_ativos", 0)), "l": "Efetivo ativo", "icon": IC["users"], "color": "#0F1B3A"},
                {"v": str(ov.get("agentes_presentes", 0)), "l": "Presentes hoje", "icon": IC["users"], "color": "#16A34A"},
                {"v": f"{_cob_atual}%", "l": "Cobertura", "icon": IC["shield"], "color": "#16A34A" if _cob_atual >= 90 else "#C2410C"},
                {"v": _risk, "l": "Nível de risco", "icon": IC["alert"], "color": "#DC2626" if _risk in ("Alto", "Critico", "Crítico") else ("#C2410C" if _risk in ("Medio", "Médio") else "#16A34A")},
            ],
            "panels": [{"title": "Situação do efetivo", "rows": [
                {"left": "Efetivo ativo", "right": str(ov.get("agentes_ativos", 0)), **S["info"]},
                {"left": "Presentes hoje", "right": str(ov.get("agentes_presentes", 0)), **S["ok"]},
                {"left": "Ausentes", "right": str(ov.get("agentes_ausentes", 0)), **(S["bad"] if (ov.get("agentes_ausentes") or 0) else S["ok"])},
                {"left": "Postos", "right": str(ov.get("total_postos", 0)), **S["info"]},
            ]}],
        }
        out["agentes"] = {
            "title": "Agentes em operação", "sub": "Situação do efetivo (agentes de portaria) · dado real", "type": "dash", "panelGrid": "1fr",
            "kpis": [
                {"v": str(ag.get("total", 0)), "l": "Total de agentes", "icon": IC["users"], "color": "#0F1B3A"},
                {"v": str(ag.get("presentes", 0)), "l": "Presentes", "icon": IC["users"], "color": "#16A34A"},
                {"v": str(ag.get("ausentes", 0)), "l": "Ausentes", "icon": IC["alert"], "color": "#DC2626" if (ag.get("ausentes") or 0) else "#0F1B3A"},
            ],
            "panels": [{"title": "Efetivo", "rows": [
                {"left": "Total de agentes ativos", "right": str(ag.get("total", 0)), **S["info"]},
                {"left": "Presentes hoje", "right": str(ag.get("presentes", 0)), **S["ok"]},
                {"left": "Ausentes", "right": str(ag.get("ausentes", 0)), **(S["bad"] if (ag.get("ausentes") or 0) else S["ok"])},
            ]}],
        }

    # Consultor Operacional (COO) — chat ancorado na operação real, roteado ao chat CENTRAL
    # (mesma engine do chat flutuante: run_engine agent-first; ações sensíveis viram rascunho).
    # Antes era um dash estático (dados já duplicados em KPIs/Cobertura/Presença) → virou chat de verdade.
    out["consultor"] = {
        "title": "Consultor Operacional (COO)",
        "sub": "Chat ancorado na operação real — postos, escalas, cobertura, ocorrências",
        "type": "chat",
        "chat": {
            "endpoint": "/api/v1/consultores/chat/executar",
            "field": "pergunta",
            "persona": "operacional",
            "placeholder": "Ex.: Quais postos estão descobertos hoje?",
            "suggestions": [
                "Quais postos estão descobertos hoje?",
                "Onde a cobertura está em risco?",
                "Resumo das ocorrências abertas da semana",
                "Quais escalas vencem nos próximos dias?",
            ],
            "disclaimer": "Respostas ancoradas nos dados reais da operação. Ações sensíveis viram rascunho para aprovação.",
        },
    }

    # ── Balde C: campo/geo — tabela real (mapa/ronda-mobile/escalas-visual/campo) + triagem derivada ──
    try:  # Mapa — georreferenciamento real dos postos
        _geo = await _scalar(db, "SELECT count(*) FROM posts WHERE latitude IS NOT NULL AND longitude IS NOT NULL AND coalesce(is_active,true)") or 0
        _tp = await _scalar(db, "SELECT count(*) FROM posts WHERE coalesce(is_active,true)") or 0
        out["mapa"] = await tbl(
            "Mapa de postos", f"{_geo}/{_tp} georreferenciados · fonte: posts", "—",
            ["Posto", "Latitude", "Longitude", "Situação"], "2fr 1fr 1fr 1.1fr",
            "SELECT name, latitude, longitude FROM posts WHERE coalesce(is_active,true) ORDER BY name LIMIT 300",
            lambda r: [t(r[0] or '—', 600, "#0F1B3A"), t(f"{r[1]:.5f}" if r[1] is not None else '—'),
                       t(f"{r[2]:.5f}" if r[2] is not None else '—'),
                       b("Georreferenciado", "ok") if (r[1] is not None and r[2] is not None) else b("Sem localização", "mut")])
    except Exception:  # noqa: BLE001
        await db.rollback()
    try:  # Ronda mobile — rondas em andamento (fluxo de campo)
        out["ronda-mobile"] = await tbl(
            "Ronda mobile", "Rondas em andamento · fonte: inspection_rounds", "—",
            ["Código", "Inspetor", "Status", "Ocorrências", "Início"], "1.1fr 1.6fr 1fr 0.9fr 1fr",
            "SELECT coalesce(code,'—'), coalesce(inspector_name,'—'), coalesce(status::text,'—'), coalesce(total_occurrences,0), coalesce(started_at, scheduled_date) "
            "FROM inspection_rounds WHERE lower(coalesce(status::text,'')) IN ('em_andamento','iniciada','pausada','iniciado') "
            "ORDER BY coalesce(started_at, scheduled_date) DESC NULLS LAST LIMIT 100",
            lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), b((r[2] or '—').replace('_', ' ').capitalize(), "warn"),
                       t(str(int(r[3] or 0))), t(_fmtdate(r[4]))])
    except Exception:  # noqa: BLE001
        await db.rollback()
    try:  # Escalas · Editor visual — scales real com preenchimento
        out["escalas-visual"] = await tbl(
            "Editor de escalas", "Escalas e preenchimento · fonte: scales", "—",
            ["Escala", "Tipo", "Período", "Turnos", "Preenchidos", "Status"], "1.6fr 1fr 0.9fr 0.8fr 0.9fr 1fr",
            "SELECT coalesce(name,'—'), coalesce(scale_type::text,'—'), month, year, coalesce(total_shifts,0), coalesce(filled_shifts,0), coalesce(status::text,'—') "
            "FROM scales WHERE coalesce(is_active,true) ORDER BY year DESC NULLS LAST, month DESC NULLS LAST LIMIT 200",
            lambda r: [t(r[0], 600, "#0F1B3A"), t((r[1] or '—').replace('_', ' ')),
                       t(f"{int(r[2]):02d}/{int(r[3])}" if r[2] and r[3] else '—'), t(str(int(r[4] or 0))),
                       t(f"{int(r[5] or 0)}/{int(r[4] or 0)}"), b((r[6] or '—').capitalize(), "ok" if (r[6] or '') == 'published' else "info")])
    except Exception:  # noqa: BLE001
        await db.rollback()
    try:  # Campo — visitas de campo reais
        out["campo"] = await tbl(
            "Campo — visitas", "Visitas de campo · fonte: visitas", "—",
            ["Nº", "Tipo", "Responsável", "Cidade", "Data", "Status"], "0.9fr 1.1fr 1.6fr 1.2fr 0.9fr 1fr",
            "SELECT coalesce(numero,'—'), coalesce(tipo::text,'—'), coalesce(responsavel_nome,'—'), coalesce(cidade,'—'), data_visita, coalesce(status::text,'—') "
            "FROM visitas WHERE coalesce(is_active,true) ORDER BY data_visita DESC NULLS LAST LIMIT 200",
            lambda r: [t(r[0], 600, "#0F1B3A"), t((r[1] or '—').replace('_', ' ').capitalize()), t(r[2]), t(r[3]),
                       t(_fmtdate(r[4])), b((r[5] or '—').replace('_', ' ').capitalize(), "info")])
    except Exception:  # noqa: BLE001
        await db.rollback()
    try:  # Triagem — sinais consolidados via sub-funções reais do triage_controller
        from modules.operacional.triage.controllers.triage_controller import (
            _avaliacoes_semana, _escalas, _ocorrencias,
        )
        _to = await _ocorrencias(db)
        _te = await _escalas(db)
        _ta = await _avaliacoes_semana(db)
        _sv = len(getattr(_te, "sem_vigencia", []) or [])
        _dr = len(getattr(_te, "drafts", []) or [])
        _ab = int(getattr(_to, "abertas_total", 0) or 0)
        _mg = getattr(_ta, "media_geral", None)
        out["triagem"] = {
            "title": "Triagem operacional", "sub": "Sinais consolidados (dado real derivado)", "type": "dash", "panelGrid": "1fr",
            "kpis": [
                {"v": str(_ab), "l": "Ocorrências abertas", "icon": IC["alert"], "color": "#C2410C" if _ab else "#0F1B3A"},
                {"v": str(_sv), "l": "Postos sem escala vigente", "icon": IC["alert"], "color": "#DC2626" if _sv else "#16A34A"},
                {"v": str(_dr), "l": "Escalas em rascunho", "icon": IC["shield"], "color": "#0F1B3A"},
                {"v": str(int(getattr(_ta, "total", 0) or 0)), "l": "Avaliações (semana)", "icon": IC["users"], "color": "#0F1B3A"},
            ],
            "panels": [{"title": "Prioridades", "rows": [
                {"left": "Ocorrências abertas", "right": str(_ab), **(S["warn"] if _ab else S["ok"])},
                {"left": "Postos sem escala vigente", "right": str(_sv), **(S["bad"] if _sv else S["ok"])},
                {"left": "Escalas em rascunho", "right": str(_dr), **S["info"]},
                {"left": "Média de avaliação (semana)", "right": (f"{_mg:.1f}" if _mg is not None else "—"), **S["info"]},
            ]}],
        }
        # DRILL-DOWN real: telas filtradas p/ os KPIs de alerta da triagem (clicar → ver OS records).
        out["postos-sem-escala"] = {
            "title": "Postos sem escala vigente", "sub": f"{_sv} posto(s) sem escala publicada em vigência",
            "type": "table", "cols": ["Posto"], "grid": "1fr",
            "rows": [{"cells": [t(p.post_nome or "—", 600, "#0F1B3A", initials(p.post_nome or ""))]}
                     for p in (getattr(_te, "sem_vigencia", []) or [])]
            or [{"cells": [t("Todos os postos têm escala vigente ✓", 500, "#16A34A")]}],
        }
        out["escalas-rascunho"] = {
            "title": "Escalas em rascunho", "sub": f"{_dr} escala(s) não publicada(s)",
            "type": "table", "cols": ["Escala", "Posto", "Competência", "Status"], "grid": "1.4fr 1.4fr 1fr 0.9fr",
            "rows": [{"cells": [t(d.name or "—", 600, "#0F1B3A"), t(d.post_nome or "—"),
                                t(f"{d.month:02d}/{d.year}" if d.month else "—"), b((d.status or "—").capitalize(), "warn")]}
                     for d in (getattr(_te, "drafts", []) or [])]
            or [{"cells": [t("Sem escalas em rascunho ✓", 500, "#16A34A"), t("—"), t("—"), b("—", "mut")]}],
        }
    except Exception:  # noqa: BLE001
        await db.rollback()

    # Forms do fluxo de aprovação de medidas (selects por status real — nunca id livre)
    try:
        _q = ("SELECT id, coalesce(code,'—'), coalesce(employee_name,'—') FROM disciplinary_actions "
              "WHERE coalesce(is_active,true) AND status::text=:st ORDER BY created_at DESC LIMIT 200")
        _rasc = (await db.execute(_sqltext(_q), {"st": "rascunho"})).fetchall()
        _pend = (await db.execute(_sqltext(_q), {"st": "pendente_aprovacao"})).fetchall()
        _apro = (await db.execute(_sqltext(
            "SELECT id, coalesce(code,'—'), coalesce(employee_name,'—') FROM disciplinary_actions "
            "WHERE coalesce(is_active,true) AND status::text IN ('aprovada','aplicada','assinada') ORDER BY created_at DESC LIMIT 200"))).fetchall()
        def _opt(rows):
            return [{"value": str(i), "label": f"{c} · {n}"} for i, c, n in rows]
        out["medida-submeter"] = {
            "title": "Submeter medida", "sub": "Envia um rascunho para aprovação", "cta": "Submeter",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/medida-submeter", "okMsg": "Medida submetida"},
            "fields": [{"key": "action_id", "label": "Medida (rascunho)*", "type": "select", "span": "span 2", "ph": "Selecione", "options": _opt(_rasc)},
                       {"key": "notes", "label": "Observação", "type": "textarea", "span": "span 2", "ph": "Opcional…"}]}
        out["medida-aprovar"] = {
            "title": "Aprovar medida", "sub": "Aprova uma medida pendente de aprovação", "cta": "Aprovar",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/medida-aprovar", "okMsg": "Medida aprovada"},
            "fields": [{"key": "action_id", "label": "Medida (pendente)*", "type": "select", "span": "span 2", "ph": "Selecione", "options": _opt(_pend)},
                       {"key": "notes", "label": "Notas da aprovação", "type": "textarea", "span": "span 2", "ph": "Opcional…"}]}
        out["medida-rejeitar"] = {
            "title": "Rejeitar medida", "sub": "Rejeita uma medida pendente com justificativa", "cta": "Rejeitar",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/medida-rejeitar", "okMsg": "Medida rejeitada"},
            "fields": [{"key": "action_id", "label": "Medida (pendente)*", "type": "select", "span": "span 2", "ph": "Selecione", "options": _opt(_pend)},
                       {"key": "reason", "label": "Motivo da rejeição*", "type": "textarea", "span": "span 2", "ph": "Mín. 10 caracteres…"}]}
        out["medida-documento"] = {
            "title": "Documento da medida", "sub": "Gera o documento da medida (aprovada/aplicada)", "cta": "Gerar documento",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/medida-documento", "okMsg": "Documento gerado"},
            "fields": [{"key": "action_id", "label": "Medida*", "type": "select", "span": "span 2", "ph": "Selecione", "options": _opt(_apro)}]}
    except Exception:  # noqa: BLE001
        await db.rollback()

    # Forms do ciclo de escala (submeter/aprovar/rejeitar/publicar) — selects por status real.
    # Sólides é fonte da verdade; aqui só o CICLO das nossas escalas, sem gerar/sobrescrever cego.
    try:
        _sq = ("SELECT id, coalesce(name,'—'), month, year FROM scales "
               "WHERE coalesce(is_active,true) AND status::text=:st ORDER BY year DESC NULLS LAST, month DESC NULLS LAST LIMIT 200")
        _s_draft = (await db.execute(_sqltext(_sq), {"st": "draft"})).fetchall()
        _s_pend = (await db.execute(_sqltext(_sq), {"st": "pending_approval"})).fetchall()
        _s_appr = (await db.execute(_sqltext(_sq), {"st": "approved"})).fetchall()
        def _sopt(rows):
            return [{"value": str(i), "label": f"{n} · {int(m):02d}/{int(y)}" if m and y else (n or '—')} for i, n, m, y in rows]
        out["escala-submeter"] = {
            "title": "Submeter escala", "sub": "Envia um rascunho de escala para aprovação", "cta": "Submeter",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/escala-submeter", "okMsg": "Escala enviada para aprovação"},
            "fields": [{"key": "scale_id", "label": "Escala (rascunho)*", "type": "select", "span": "span 2", "ph": "Selecione", "options": _sopt(_s_draft)}]}
        out["escala-aprovar"] = {
            "title": "Aprovar escala", "sub": "Aprova uma escala pendente", "cta": "Aprovar",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/escala-aprovar", "okMsg": "Escala aprovada"},
            "fields": [{"key": "scale_id", "label": "Escala (pendente)*", "type": "select", "span": "span 2", "ph": "Selecione", "options": _sopt(_s_pend)},
                       {"key": "notes", "label": "Notas da aprovação", "type": "textarea", "span": "span 2", "ph": "Opcional…"}]}
        out["escala-rejeitar"] = {
            "title": "Rejeitar escala", "sub": "Rejeita uma escala pendente com justificativa", "cta": "Rejeitar",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/escala-rejeitar", "okMsg": "Escala rejeitada"},
            "fields": [{"key": "scale_id", "label": "Escala (pendente)*", "type": "select", "span": "span 2", "ph": "Selecione", "options": _sopt(_s_pend)},
                       {"key": "reason", "label": "Motivo da rejeição*", "type": "textarea", "span": "span 2", "ph": "Mín. 10 caracteres…"}]}
        out["escala-publicar"] = {
            "title": "Publicar escala", "sub": "Publica uma escala aprovada (envia aos funcionários)", "cta": "Publicar",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/escala-publicar", "okMsg": "Escala publicada"},
            "fields": [{"key": "scale_id", "label": "Escala (aprovada)*", "type": "select", "span": "span 2", "ph": "Selecione", "options": _sopt(_s_appr)}]}
    except Exception:  # noqa: BLE001
        await db.rollback()

    # Forms de aprovação de banco de horas (select lançamentos pendentes)
    try:
        _tbp = (await db.execute(_sqltext(
            "SELECT tb.id, coalesce(e.nome,'—'), tb.hours, tb.reference_date FROM time_bank tb "
            "LEFT JOIN employees e ON e.id=tb.employee_id WHERE coalesce(tb.is_active,true) AND tb.status='pending' "
            "ORDER BY tb.reference_date DESC NULLS LAST LIMIT 200"))).fetchall()
        _tbopt = [{"value": str(i), "label": f"{n} · {(('+' if (h or 0) >= 0 else ''))}{h}h · {_fmtdate(d)}"} for i, n, h, d in _tbp]
        out["banco-horas-aprovar"] = {
            "title": "Aprovar banco de horas", "sub": "Aprova um lançamento pendente", "cta": "Aprovar",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/banco-horas-aprovar", "okMsg": "Lançamento aprovado"},
            "fields": [{"key": "entry_id", "label": "Lançamento (pendente)*", "type": "select", "span": "span 2", "ph": "Selecione", "options": _tbopt},
                       {"key": "notes", "label": "Observação", "type": "textarea", "span": "span 2", "ph": "Opcional…"}]}
        out["banco-horas-rejeitar"] = {
            "title": "Rejeitar banco de horas", "sub": "Rejeita um lançamento pendente", "cta": "Rejeitar",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/banco-horas-rejeitar", "okMsg": "Lançamento rejeitado"},
            "fields": [{"key": "entry_id", "label": "Lançamento (pendente)*", "type": "select", "span": "span 2", "ph": "Selecione", "options": _tbopt},
                       {"key": "reason", "label": "Motivo da rejeição*", "type": "text", "span": "span 2", "ph": "Mín. 5 caracteres"}]}
        out["banco-horas-editar"] = {
            "title": "Editar banco de horas", "sub": "Corrige horas/motivo de um lançamento pendente", "cta": "Salvar",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/banco-horas-editar", "okMsg": "Lançamento atualizado"},
            "fields": [{"key": "entry_id", "label": "Lançamento (pendente)*", "type": "select", "span": "span 2", "ph": "Selecione", "options": _tbopt},
                       {"key": "hours", "label": "Novas horas", "type": "text", "span": "span 1", "ph": "Deixe vazio p/ manter"},
                       {"key": "reason", "label": "Motivo", "type": "text", "span": "span 1", "ph": "Opcional"},
                       {"key": "description", "label": "Descrição", "type": "textarea", "span": "span 2", "ph": "Opcional…"}]}
        out["banco-horas-excluir"] = {
            "title": "Excluir banco de horas", "sub": "Remove um lançamento pendente", "cta": "Excluir",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/banco-horas-excluir", "okMsg": "Lançamento excluído"},
            "fields": [{"key": "entry_id", "label": "Lançamento (pendente)*", "type": "select", "span": "span 2", "ph": "Selecione", "options": _tbopt}]}
    except Exception:  # noqa: BLE001
        await db.rollback()

    # Forms substitutions / comunicação / diaristas (gestão) — selects por estado real
    try:
        _sub_p = (await db.execute(_sqltext(
            "SELECT s.id, coalesce(p.name,'—'), coalesce(eo.nome,'—') FROM substitutions s "
            "LEFT JOIN posts p ON p.id=s.post_id LEFT JOIN employees eo ON eo.id=s.original_employee_id "
            "WHERE coalesce(s.is_active,true) AND s.status::text='pending' ORDER BY s.requested_at DESC NULLS LAST LIMIT 200"))).fetchall()
        _sub_opt = [{"value": str(i), "label": f"{p} · falta {n}"} for i, p, n in _sub_p]
        out["substituicao-confirmar"] = {
            "title": "Confirmar substituição", "sub": "Confirma o substituto de uma substituição pendente", "cta": "Confirmar",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/substituicao-confirmar", "okMsg": "Substituição confirmada"},
            "fields": [{"key": "substitution_id", "label": "Substituição (pendente)*", "type": "select", "span": "span 2", "ph": "Selecione", "options": _sub_opt},
                       {"key": "notes", "label": "Observação", "type": "textarea", "span": "span 2", "ph": "Opcional…"}]}
        out["substituicao-rejeitar"] = {
            "title": "Rejeitar substituição", "sub": "Rejeita uma substituição pendente", "cta": "Rejeitar",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/substituicao-rejeitar", "okMsg": "Substituição rejeitada"},
            "fields": [{"key": "substitution_id", "label": "Substituição (pendente)*", "type": "select", "span": "span 2", "ph": "Selecione", "options": _sub_opt},
                       {"key": "reason", "label": "Motivo*", "type": "text", "span": "span 2", "ph": "Mín. 5 caracteres"}]}
        _sub_c = (await db.execute(_sqltext(
            "SELECT s.id, coalesce(p.name,'—'), coalesce(eo.nome,'—') FROM substitutions s "
            "LEFT JOIN posts p ON p.id=s.post_id LEFT JOIN employees eo ON eo.id=s.original_employee_id "
            "WHERE coalesce(s.is_active,true) AND s.status::text='confirmed' ORDER BY s.requested_at DESC NULLS LAST LIMIT 200"))).fetchall()
        out["substituicao-concluir"] = {
            "title": "Concluir substituição", "sub": "Marca como concluída uma substituição já confirmada", "cta": "Concluir",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/substituicao-concluir", "okMsg": "Substituição concluída"},
            "fields": [{"key": "substitution_id", "label": "Substituição (confirmada)*", "type": "select", "span": "span 2", "ph": "Selecione",
                        "options": [{"value": str(i), "label": f"{p} · falta {n}"} for i, p, n in _sub_c]},
                       {"key": "overtime_hours", "label": "Horas extras", "type": "text", "span": "span 1", "ph": "Opcional, ex.: 2"}]}
        _ann = (await db.execute(_sqltext(
            "SELECT id, coalesce(titulo,'—') FROM communication_announcements WHERE coalesce(is_active,true) "
            "AND status::text NOT IN ('publicado','published') ORDER BY created_at DESC LIMIT 200"))).fetchall()
        out["comunicado-publicar"] = {
            "title": "Publicar comunicado", "sub": "Publica um comunicado em rascunho", "cta": "Publicar",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/comunicado-publicar", "okMsg": "Comunicado publicado"},
            "fields": [{"key": "announcement_id", "label": "Comunicado (rascunho)*", "type": "select", "span": "span 2", "ph": "Selecione",
                        "options": [{"value": str(i), "label": tt} for i, tt in _ann]}]}
        _prio_opt = [{"value": v, "label": l} for v, l in [("normal", "Normal"), ("baixa", "Baixa"), ("alta", "Alta"), ("urgente", "Urgente")]]
        _cat_opt = [{"value": v, "label": l} for v, l in [("informativo", "Informativo"), ("procedimento", "Procedimento"), ("alerta", "Alerta"), ("treinamento", "Treinamento"), ("politica", "Política")]]
        _ann_opt = [{"value": str(i), "label": tt} for i, tt in _ann]
        out["comunicado-novo"] = {
            "title": "Novo comunicado", "sub": "Cria um comunicado (nasce como rascunho — publique depois)", "cta": "Criar comunicado",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/comunicado-criar", "okMsg": "Comunicado criado (rascunho)"},
            "fields": [{"key": "title", "label": "Título*", "type": "text", "span": "span 2", "ph": "Mín. 3 caracteres"},
                       {"key": "content", "label": "Conteúdo*", "type": "textarea", "span": "span 2", "ph": "Mín. 10 caracteres"},
                       {"key": "priority", "label": "Prioridade", "type": "select", "span": "span 1", "options": _prio_opt},
                       {"key": "category", "label": "Categoria", "type": "select", "span": "span 1", "options": _cat_opt}]}
        out["comunicado-editar"] = {
            "title": "Editar comunicado", "sub": "Edita título/conteúdo/prioridade (só rascunho ou agendado)", "cta": "Salvar alterações",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/comunicado-editar", "okMsg": "Comunicado atualizado"},
            "fields": [{"key": "announcement_id", "label": "Comunicado (rascunho)*", "type": "select", "span": "span 2", "ph": "Selecione", "options": _ann_opt},
                       {"key": "title", "label": "Novo título", "type": "text", "span": "span 2", "ph": "Deixe vazio p/ manter"},
                       {"key": "content", "label": "Novo conteúdo", "type": "textarea", "span": "span 2", "ph": "Deixe vazio p/ manter"},
                       {"key": "priority", "label": "Prioridade", "type": "select", "span": "span 1", "ph": "Manter", "options": _prio_opt},
                       {"key": "category", "label": "Categoria", "type": "select", "span": "span 1", "ph": "Manter", "options": _cat_opt}]}
        out["comunicado-excluir"] = {
            "title": "Excluir comunicado", "sub": "Remove um comunicado em rascunho", "cta": "Excluir",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/comunicado-excluir", "okMsg": "Comunicado excluído"},
            "fields": [{"key": "announcement_id", "label": "Comunicado*", "type": "select", "span": "span 2", "ph": "Selecione", "options": _ann_opt}]}
        _alr = (await db.execute(_sqltext(
            "SELECT id, coalesce(title,'—'), coalesce(severity::text,'—') FROM communication_alerts "
            "WHERE coalesce(is_active,true) AND acknowledged_by IS NULL ORDER BY created_at DESC LIMIT 200"))).fetchall()
        out["alerta-ack"] = {
            "title": "Reconhecer alerta", "sub": "Marca um alerta como reconhecido", "cta": "Reconhecer",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/alerta-ack", "okMsg": "Alerta reconhecido"},
            "fields": [{"key": "alert_id", "label": "Alerta ativo*", "type": "select", "span": "span 2", "ph": "Selecione",
                        "options": [{"value": str(i), "label": f"[{sv}] {tt}"} for i, tt, sv in _alr]}]}
        out["alerta-criar"] = {
            "title": "Novo alerta", "sub": "Emite um alerta operacional para a equipe", "cta": "Criar alerta",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/alerta-criar", "okMsg": "Alerta criado"},
            "fields": [
                {"key": "title", "label": "Título*", "type": "text", "span": "span 2", "ph": "Mín. 3 caracteres"},
                {"key": "message", "label": "Mensagem*", "type": "textarea", "span": "span 2", "ph": "Mín. 3 caracteres"},
                {"key": "alert_type", "label": "Tipo", "type": "select", "span": "span 1", "options": [{"value": v, "label": l} for v, l in [
                    ("posto_descoberto", "Posto descoberto"), ("falta_detectada", "Falta detectada"),
                    ("sla_vencendo", "SLA vencendo"), ("ocorrencia_critica", "Ocorrência crítica")]]},
                {"key": "severity", "label": "Severidade", "type": "select", "span": "span 1", "options": [{"value": v, "label": l} for v, l in [
                    ("warning", "Aviso"), ("info", "Informativo"), ("error", "Erro"), ("critical", "Crítico")]]},
            ]}
        _di_on = (await db.execute(_sqltext("SELECT id, coalesce(nome,'—') FROM diarists WHERE coalesce(ativo,true) ORDER BY nome LIMIT 300"))).fetchall()
        _di_off = (await db.execute(_sqltext("SELECT id, coalesce(nome,'—') FROM diarists WHERE NOT coalesce(ativo,true) ORDER BY nome LIMIT 300"))).fetchall()
        _di_all = (await db.execute(_sqltext("SELECT id, coalesce(nome,'—') FROM diarists ORDER BY nome LIMIT 300"))).fetchall()
        _diopt = lambda rows: [{"value": str(i), "label": n} for i, n in rows]
        out["diarista-ativar"] = {
            "title": "Ativar diarista", "sub": "Reativa um diarista inativo", "cta": "Ativar",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/diarista-ativar", "okMsg": "Diarista ativado"},
            "fields": [{"key": "diarist_id", "label": "Diarista (inativo)*", "type": "select", "span": "span 2", "ph": "Selecione", "options": _diopt(_di_off)}]}
        out["diarista-desativar"] = {
            "title": "Desativar diarista", "sub": "Desativa um diarista ativo", "cta": "Desativar",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/diarista-desativar", "okMsg": "Diarista desativado"},
            "fields": [{"key": "diarist_id", "label": "Diarista (ativo)*", "type": "select", "span": "span 2", "ph": "Selecione", "options": _diopt(_di_on)}]}
        out["diarista-avaliar"] = {
            "title": "Avaliar diarista", "sub": "Registra avaliação (nota 1–5) de um diarista", "cta": "Avaliar",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/diarista-avaliar", "okMsg": "Avaliação registrada"},
            "fields": [{"key": "diarist_id", "label": "Diarista*", "type": "select", "span": "span 2", "ph": "Selecione", "options": _diopt(_di_all)},
                       {"key": "nota_geral", "label": "Nota geral (1–5)*", "type": "select", "span": "span 1", "ph": "Nota",
                        "options": [{"value": str(k), "label": str(k)} for k in (1, 2, 3, 4, 5)]},
                       {"key": "comentario", "label": "Comentário", "type": "textarea", "span": "span 2", "ph": "Opcional…"}]}
        _conds = (await db.execute(_sqltext("SELECT id, coalesce(nome,'—') FROM condominios WHERE coalesce(ativo,true) ORDER BY nome LIMIT 300"))).fetchall()
        out["diarista-fechamento"] = {
            "title": "Gerar fechamento de diaristas", "sub": "Cria os pagamentos PENDENTES do mês · pagamento é gated (OTP) no financeiro", "cta": "Gerar fechamento",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/diarista-fechamento", "okMsg": "Fechamento gerado"},
            "fields": [{"key": "condominio_id", "label": "Condomínio*", "type": "select", "span": "span 2", "ph": "Selecione",
                        "options": [{"value": str(i), "label": n} for i, n in _conds]},
                       {"key": "competencia", "label": "Competência (AAAA-MM)*", "type": "text", "span": "span 1", "ph": "2026-07"}]}
        out["diarista-escala-criar"] = {
            "title": "Escalar diarista (agenda)", "sub": "Agenda um diarista para um dia num condomínio (valor previsto ≠ pagamento)", "cta": "Escalar",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/diarista-escala-criar", "okMsg": "Escala criada"},
            "fields": [
                {"key": "diarist_id", "label": "Diarista*", "type": "select", "span": "span 2", "ph": "Selecione", "options": _diopt(_di_on)},
                {"key": "condominio_id", "label": "Condomínio*", "type": "select", "span": "span 2", "ph": "Selecione",
                 "options": [{"value": str(i), "label": n} for i, n in _conds]},
                {"key": "data_trabalho", "label": "Data*", "type": "date", "span": "span 1"},
                {"key": "hora_inicio", "label": "Início", "type": "text", "span": "span 1", "ph": "HH:MM (pad 08:00)"},
                {"key": "hora_fim", "label": "Fim", "type": "text", "span": "span 1", "ph": "HH:MM (pad 17:00)"},
                {"key": "valor_previsto", "label": "Valor previsto (R$)", "type": "text", "span": "span 1", "ph": "Opcional"},
                {"key": "observacoes", "label": "Observações", "type": "textarea", "span": "span 2", "ph": "Opcional…"},
            ]}
        out["diarista-assignment-criar"] = {
            "title": "Alocar diarista (recorrente)", "sub": "Vincula um diarista a um condomínio por um período", "cta": "Alocar",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/diarista-assignment-criar", "okMsg": "Alocação criada"},
            "fields": [
                {"key": "diarist_id", "label": "Diarista*", "type": "select", "span": "span 2", "ph": "Selecione", "options": _diopt(_di_on)},
                {"key": "condominio_id", "label": "Condomínio*", "type": "select", "span": "span 2", "ph": "Selecione",
                 "options": [{"value": str(i), "label": n} for i, n in _conds]},
                {"key": "servico_tipo", "label": "Tipo de serviço", "type": "text", "span": "span 1", "ph": "Ex.: portaria"},
                {"key": "data_inicio", "label": "Início*", "type": "date", "span": "span 1"},
                {"key": "data_fim", "label": "Fim", "type": "date", "span": "span 1"},
                {"key": "servico_descricao", "label": "Descrição", "type": "textarea", "span": "span 2", "ph": "Opcional…"},
            ]}
        _asg = (await db.execute(_sqltext(
            "SELECT a.id, coalesce(d.nome,'—'), a.data_inicio FROM diarist_assignments a "
            "LEFT JOIN diarists d ON d.id=a.diarist_id WHERE coalesce(a.ativo,true) "
            "ORDER BY a.data_inicio DESC NULLS LAST LIMIT 200"))).fetchall()
        out["diarista-assignment-cancelar"] = {
            "title": "Cancelar alocação de diarista", "sub": "Encerra uma alocação recorrente ativa", "cta": "Cancelar",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/diarista-assignment-cancelar", "okMsg": "Alocação cancelada"},
            "fields": [{"key": "assignment_id", "label": "Alocação ativa*", "type": "select", "span": "span 2", "ph": "Selecione",
                        "options": [{"value": str(i), "label": f"{n} · desde {_fmtdate(dt)}"} for i, n, dt in _asg]}]}
        _dl = (await db.execute(_sqltext(
            "SELECT l.id, coalesce(l.posto,'—'), l.data, coalesce(l.funcao,'—') FROM diaria_lancamentos l "
            "WHERE l.status='lancado' ORDER BY l.data DESC NULLS LAST LIMIT 300"))).fetchall()
        out["diaria-excluir"] = {
            "title": "Excluir lançamento de diária", "sub": "Remove um lançamento de diária (status 'lançado')", "cta": "Excluir",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/diaria-excluir", "okMsg": "Lançamento excluído"},
            "fields": [{"key": "lancamento_id", "label": "Lançamento*", "type": "select", "span": "span 2", "ph": "Selecione",
                        "options": [{"value": str(i), "label": f"{po} · {fn} · {_fmtdate(dt)}"} for i, po, dt, fn in _dl]}]}
    except Exception:  # noqa: BLE001
        await db.rollback()

    # ── Apuração ponto → saldo (o "motor de acúmulo" que nunca existiu) ─────────────────
    # DERIVADO, nunca gravado automaticamente: pareia entrada→saída em SEQUÊNCIA (o intervalo
    # de almoço fica de fora naturalmente) e compara com planned_hours da escala. Pares com
    # gap >16h são descartados (batida órfã) e o dia entra na coluna "Pendências" — sem isso
    # min(entrada)/max(saída) contaria o almoço como trabalhado e inflaria a HE.
    # Lançar no banco de horas continua ATO HUMANO (aba "Lançar horas"), nunca automático.
    try:
        _sql_apur = """
        WITH b AS (
          SELECT employee_id, punch_timestamp AS ts, punch_type,
                 lead(punch_timestamp) OVER (PARTITION BY employee_id ORDER BY punch_timestamp) AS prox_ts,
                 lead(punch_type)      OVER (PARTITION BY employee_id ORDER BY punch_timestamp) AS prox_tp
          FROM gp_clock_punches WHERE punch_timestamp > now() - interval '30 days'),
        par AS (SELECT employee_id, ts::date AS d, EXTRACT(EPOCH FROM (prox_ts-ts))/3600.0 AS h
                FROM b WHERE punch_type='entrada' AND prox_tp='saida' AND prox_ts>ts
                  AND prox_ts-ts < interval '16 hours'),
        orf AS (SELECT DISTINCT employee_id, ts::date AS d FROM b
                WHERE punch_type='entrada' AND (prox_tp IS DISTINCT FROM 'saida' OR prox_ts-ts >= interval '16 hours')),
        realiz AS (SELECT employee_id, d, sum(h) AS h_real FROM par GROUP BY 1,2),
        -- previsto agregado POR PESSOA-DIA (senão o JOIN multiplica o realizado: há até 4
        -- registros de turno no mesmo dia) e SEM turno cancelado (as versões antigas da escala
        -- ficam como 'cancelled' na mesma data — somá-las inflava o previsto p/ 48h/dia).
        prev AS (SELECT s.employee_id, s.shift_date AS d, sum(coalesce(s.planned_hours,8)) AS h_prev
                 FROM shifts s WHERE s.shift_date > current_date-30 AND coalesce(s.is_active,true)
                   AND s.employee_id IS NOT NULL
                   AND coalesce(s.status::text,'') NOT IN ('cancelled','canceled','cancelada')
                 GROUP BY 1,2)
        SELECT e.nome, round(sum(r.h_real)::numeric,1), round(sum(p.h_prev)::numeric,1),
               round(sum(r.h_real-p.h_prev)::numeric,1),
               (SELECT count(*) FROM orf o WHERE o.employee_id=r.employee_id),
               count(*) AS dias
        FROM realiz r JOIN prev p ON p.employee_id=r.employee_id AND p.d=r.d
        JOIN employees e ON e.id=r.employee_id
        GROUP BY e.nome, r.employee_id ORDER BY 4 DESC LIMIT 300
        """

        def _saldo_cell(v):
            v = float(v or 0)
            if v > 0.5:
                return b(f"+{v:.1f}h", "warn")
            if v < -0.5:
                return b(f"{v:.1f}h", "bad")
            return b(f"{v:+.1f}h", "ok")

        out["banco-horas-apuracao"] = await tbl(
            "Apuração de horas (ponto × escala)",
            "Últimos 30 dias · compara só os dias COM batida: realizado = pares entrada→saída reais "
            "(intervalo já descontado) vs previsto na escala vigente (turno cancelado não conta). "
            "Cálculo derivado — não lança nada: use 'Lançar horas' para efetivar.",
            "—", ["Colaborador", "Dias", "Realizado", "Previsto", "Saldo", "Pendências"],
            "2fr 0.6fr 0.9fr 0.9fr 0.9fr 1.1fr", _sql_apur,
            lambda r: [t(r[0] or "—", 600, "#0F1B3A"), t(f"{r[5]}d"), t(f"{r[1] or 0}h"), t(f"{r[2] or 0}h"),
                       _saldo_cell(r[3]),
                       b(f"{r[4]} dia(s) c/ batida solta", "warn") if (r[4] or 0) else b("Consistente", "ok")])
    except Exception:  # noqa: BLE001
        await db.rollback()

    # ── Ausentes hoje: fecha o elo quadro-de-presença → Registrar falta (1 clique) ──────
    # O fluxo existia mas ninguém achava: o form pedia escolher o turno num dropdown. Aqui a
    # ação nasce NA LINHA do ausente, com shift_id já preenchido → vira 1 clique.
    try:
        out["ausentes-hoje"] = await tbl(
            "Ausentes hoje", "Turnos de hoje sem check-in e sem batida de ponto · registre a falta na linha "
            "(abre a substituição automaticamente)", "—",
            ["Colaborador", "Posto", "Turno previsto", "Cargo"], "1.6fr 1.6fr 1fr 1.2fr",
            "SELECT e.nome, p.name, to_char(s.planned_start_time,'HH24:MI'), coalesce(e.cargo,'—'), s.id::text "
            "FROM shifts s JOIN posts p ON p.id=s.post_id JOIN employees e ON e.id=s.employee_id "
            "WHERE s.shift_date=current_date AND coalesce(s.is_active,true) AND s.actual_start_time IS NULL "
            "  AND coalesce(s.status::text,'') NOT IN ('cancelled','completed','missed') "
            "  AND NOT EXISTS (SELECT 1 FROM gp_clock_punches gp WHERE gp.employee_id=s.employee_id "
            "                  AND gp.punch_timestamp::date=s.shift_date) "
            "ORDER BY p.name, e.nome LIMIT 200",
            lambda r: [t(r[0] or "—", 600, "#0F1B3A"), t(r[1] or "—"), t(r[2] or "—"), t(r[3] or "—")],
            actionsfn=lambda r: [{
                "btnLabel": "Registrar falta", "btnStyle": "primary",
                "title": f"Registrar falta — {r[0]}",
                "endpoint": "/api/v1/redesign/action/falta", "method": "POST",
                "okMsg": "Falta registrada — substituição aberta.",
                "fields": [
                    {"key": "shift_id", "label": "Turno", "type": "text", "span": "span 2", "value": r[4]},
                    {"key": "motivo", "label": "Motivo*", "type": "select", "span": "span 1", "ph": "Motivo",
                     "options": [{"value": v, "label": lb} for v, lb in [
                         ("falta", "Falta (sem aviso)"), ("atestado", "Atestado"),
                         ("emergencia", "Emergência"), ("pessoal", "Pessoal"), ("outro", "Outro")]]},
                    {"key": "detalhes", "label": "Detalhes", "type": "textarea", "span": "span 2", "ph": "Opcional…"},
                ],
            }])
    except Exception:  # noqa: BLE001
        await db.rollback()

    # ── Checkpoints de ronda: a parte do trabalho de CAMPO que o gestor precisa VER ────
    # Registrar checkpoint/foto é do app mobile; conferir o que foi feito é do desktop.
    try:
        out["ronda-checkpoints"] = await tbl(
            "Checkpoints de ronda", "O que foi verificado em campo (registro vem do app mobile)", "—",
            ["Ronda", "Posto", "Checkpoint", "Colaborador", "Situação", "Data"],
            "1fr 1.4fr 1.6fr 1.4fr 1fr 0.9fr",
            "SELECT coalesce(r.code,'—'), coalesce(c.post_name,'—'), coalesce(c.title,'—'), "
            "       coalesce(c.employee_name,'—'), coalesce(c.status::text,'—'), c.created_at, "
            "       coalesce(c.infraction_severity::text,'') "
            "FROM inspection_checkpoints c LEFT JOIN inspection_rounds r ON r.id=c.inspection_round_id "
            "WHERE coalesce(c.is_active,true) ORDER BY c.created_at DESC NULLS LAST LIMIT 300",
            lambda r: [t(r[0] or "—", 600, "#0F1B3A"), t(r[1] or "—"), t(r[2] or "—"), t(r[3] or "—"),
                       b((r[4] or "—").replace("_", " ").capitalize(),
                         "bad" if (r[6] or "").lower() in ("grave", "gravissima") else
                         ("warn" if r[6] else "ok")),
                       t(_fmtdate(r[5]))])
    except Exception:  # noqa: BLE001
        await db.rollback()

    # ── Assinatura de medida disciplinar: PORTA o fluxo já provado do clássico ─────────
    # Não é form declarativo (o backend exige signature_data = base64 do traço, ≥100 chars,
    # + geolocalização): a linha entrega o payload e o front abre o SignaturePad já existente
    # (components/operacional/disciplinary-signature-modal), mesmo padrão do ScannerPagamento.
    # Cobre os dois lados: ciência do FUNCIONÁRIO e assinatura da EMPRESA (gestor/diretoria),
    # e a recusa com 2 testemunhas (Art. 477 CLT) vem junto no componente.
    try:
        _med = (await db.execute(_sqltext(
            "SELECT id::text, coalesce(code,'—'), coalesce(action_type::text,'—'), coalesce(status::text,'—'), "
            "       coalesce(employee_name,'—'), coalesce(employee_cpf,''), incident_date, "
            "       coalesce(reason_description,'') "
            "FROM disciplinary_actions WHERE coalesce(is_active,true) "
            "  AND coalesce(status::text,'') NOT IN ('rascunho','draft','cancelada','cancelled') "
            "ORDER BY incident_date DESC NULLS LAST LIMIT 200"))).fetchall()
        out["medida-assinar"] = {
            "title": "Assinar medida disciplinar",
            "sub": f"{len(_med)} medida(s) aplicada(s) · assinatura por traço com geolocalização · "
                   "recusa do funcionário registra 2 testemunhas (Art. 477 CLT)",
            "cta": "—", "type": "table", "searchHint": "Buscar colaborador…",
            "grid": "1fr 1.6fr 1.2fr 1fr 1fr",
            "cols": ["Código", "Colaborador", "Tipo", "Situação", "Incidente"],
            "rows": [{
                "cells": [t(m[1], 600, "#0F1B3A"), t(m[4]), t((m[2] or "—").replace("_", " ").capitalize()),
                          b((m[3] or "—").capitalize(), "ok" if (m[3] or "") == "assinada" else "warn"),
                          t(_fmtdate(m[6]))],
                # payload consumido pelo DisciplinarySignatureModal (shape DisciplinaryAction)
                "sign": {"id": m[0], "code": m[1], "action_type": m[2], "status": m[3],
                         "employee_name": m[4], "employee_cpf": m[5],
                         "incident_date": (m[6].isoformat() if m[6] else None),
                         "reason_description": m[7]},
            } for m in _med],
        }
    except Exception:  # noqa: BLE001
        await db.rollback()

    # F0 — agrupa as ~62 telas/ações em 8 grupos (fundação tabs, igual ao financeiro).
    # Chamado por ÚLTIMO: precisa de TODAS as telas/ações já montadas em out.
    try:
        from modules.operacional.controllers.redesign_builders._op_grupos import montar_grupos
        _aplicar_drill(out)   # KPIs clicáveis ANTES de agrupar (dashboards viram abas depois)
        _ver_todas(out)       # clique-na-linha (Ver) em toda tabela
        montar_grupos(out)
    except Exception:  # noqa: BLE001 — nunca derruba o módulo por causa da navegação
        pass

    # ── Consultor operacional (2026-08-10) ─────────────────────────────────────────
    # SÓ os dois consultores. As outras 8 rotas órfãs deste módulo (allocations/bulk,
    # shifts/bulk, alocar/desalocar diarista, scales/reject, scale-optimizer) mexem em
    # ALOCAÇÃO e ESCALA — território curado à mão pelo Jordan, read-only para agentes.
    # Ligar botão ali seria o sistema discordando dele em silêncio. Divergência vira
    # relatório, não ação.
    out["consultor-op"] = {
        "title": "Consultor operacional",
        "sub": "Pergunta ancorada em postos, escalas e presença reais. É consulta — não "
               "cria posto, não move alocação.",
        "cta": "Perguntar", "type": "form",
        "submit": {"endpoint": "/api/v1/operacional/consultor/perguntar",
                   "okMsg": "Consulta respondida", "showResult": True},
        "fields": [
            {"key": "area", "label": "Área*", "type": "text", "span": "span 1",
             "ph": "Ex.: cobertura, faltas, escala"},
            {"key": "posto", "label": "Posto", "type": "text", "span": "span 1"},
            {"key": "pergunta", "label": "Pergunta*", "type": "textarea", "span": "span 2"},
        ],
    }
    out["consultor-op-arquivo"] = {
        "title": "Consultor operacional — analisando um anexo",
        "sub": "Anexe uma escala, um relatório de ronda ou uma foto de ocorrência e pergunte.",
        "cta": "Analisar", "type": "form",
        "submit": {"endpoint": "/api/v1/operacional/consultor/perguntar-arquivo",
                   "multipart": True, "query": True,
                   "okMsg": "Análise concluída", "showResult": True},
        "fields": [
            {"key": "arquivo", "label": "Arquivo*", "type": "file", "span": "span 2"},
            {"key": "area", "label": "Área", "type": "text", "span": "span 1"},
            {"key": "posto", "label": "Posto", "type": "text", "span": "span 1"},
            {"key": "pergunta", "label": "Pergunta*", "type": "textarea", "span": "span 2"},
        ],
    }

    return out
