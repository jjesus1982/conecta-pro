"""Operacional (T1) — delega ao _build_operacional e ESTENDE com telas de LEITURA
(presença ao vivo, escalas, turnos, reembolsos). Operacional é curado pelo Jordan →
SÓ visibilidade, NUNCA escreve/altera escala/alocação. Reembolso é read-only (sem aprovar/pagar)."""
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text as _sqltext

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.operacional.controllers.redesign_data_controller import (
    IC, S, _build_operacional, _fmtdate, _helpers, _scalar, b, brl, doc, t,
)

SLUG = "operacional"

router = APIRouter()


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
EXTRA_MENU: list[dict] = [
    {"id": "rondas", "label": "Rondas",
     "icon": "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"},
    {"id": "passagem-turno-nova", "label": "Nova passagem", "icon": "M12 5v14M5 12h14"},
    {"id": "instrucao-posto-editar", "label": "Editar instrução", "icon": "M12 5v14M5 12h14"},
    {"id": "banco-horas-lancar", "label": "Lançar horas", "icon": "M12 5v14M5 12h14"},
    {"id": "nova-ronda", "label": "Nova ronda", "icon": "M12 5v14M5 12h14"},
    {"id": "medida-submeter", "label": "Submeter medida", "icon": "M12 5v14M5 12h14"},
    {"id": "medida-aprovar", "label": "Aprovar medida", "icon": "M20 6L9 17l-5-5"},
    {"id": "medida-rejeitar", "label": "Rejeitar medida", "icon": "M18 6L6 18M6 6l12 12"},
    {"id": "medida-documento", "label": "Documento da medida", "icon": "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"},
    {"id": "escala-submeter", "label": "Submeter escala", "icon": "M12 5v14M5 12h14"},
    {"id": "escala-aprovar", "label": "Aprovar escala", "icon": "M20 6L9 17l-5-5"},
    {"id": "escala-rejeitar", "label": "Rejeitar escala", "icon": "M18 6L6 18M6 6l12 12"},
    {"id": "escala-publicar", "label": "Publicar escala", "icon": "M22 2L11 13M22 2l-7 20-4-9-9-4z"},
    {"id": "banco-horas-aprovar", "label": "Aprovar horas", "icon": "M20 6L9 17l-5-5"},
    {"id": "banco-horas-rejeitar", "label": "Rejeitar horas", "icon": "M18 6L6 18M6 6l12 12"},
    {"id": "substituicao-confirmar", "label": "Confirmar substituição", "icon": "M20 6L9 17l-5-5"},
    {"id": "substituicao-rejeitar", "label": "Rejeitar substituição", "icon": "M18 6L6 18M6 6l12 12"},
    {"id": "comunicado-publicar", "label": "Publicar comunicado", "icon": "M22 2L11 13M22 2l-7 20-4-9-9-4z"},
    {"id": "alerta-ack", "label": "Reconhecer alerta", "icon": "M20 6L9 17l-5-5"},
    {"id": "diarista-ativar", "label": "Ativar diarista", "icon": "M20 6L9 17l-5-5"},
    {"id": "diarista-desativar", "label": "Desativar diarista", "icon": "M18 6L6 18M6 6l12 12"},
    {"id": "diarista-avaliar", "label": "Avaliar diarista", "icon": "M11.5 2l2.6 6.9 7.4.3-5.8 4.6 2 7.1-6.2-4-6.2 4 2-7.1-5.8-4.6 7.4-.3z"},
    {"id": "diarista-fechamento", "label": "Gerar fechamento diaristas", "icon": "M9 11l3 3L22 4M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"},
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
            "SELECT coalesce(e.nome,'—'), s.shift_date, s.planned_start_time, s.planned_end_time, s.planned_hours, coalesce(s.status::text,'—') "
            "FROM shifts s LEFT JOIN employees e ON e.id=s.employee_id ORDER BY s.shift_date DESC NULLS LAST LIMIT 200",
            lambda r: [t(r[0], 600, "#0F1B3A"), t(_fmtdate(r[1])), t(str(r[2])[:5] if r[2] else '—'), t(str(r[3])[:5] if r[3] else '—'),
                       t(f"{float(r[4]):.0f}h" if r[4] is not None else '—'), b((r[5] or '—').replace('_', ' ').capitalize(), _tt.get((r[5] or '').lower(), "info"))])
    except Exception:  # noqa: BLE001
        pass

    # Reembolsos — reimbursement_requests (READ-ONLY: sem aprovar/pagar aqui)
    _rt = {"aprovado": "ok", "pago": "ok", "reembolsado": "ok", "pendente": "warn", "em_analise": "warn", "submetido": "warn", "rejeitado": "bad", "negado": "bad"}
    try:
        out["reembolsos"] = await tbl(
            "Reembolsos", "Solicitações de reembolso (visibilidade)", "—",
            ["Código", "Descrição", "Valor", "Status"], "1fr 2fr 1fr 0.9fr",
            "SELECT coalesce(code,'—'), coalesce(title,'—'), total_amount, coalesce(status::text,'—') "
            "FROM reimbursement_requests ORDER BY submitted_at DESC NULLS LAST LIMIT 200",
            lambda r: [t(r[0], 600, "#0F1B3A"), t((r[1] or '—')[:60]), t(brl(r[2]) if r[2] is not None else '—', 600),
                       b((r[3] or '—').replace('_', ' ').capitalize(), _rt.get((r[3] or '').lower(), "info"))])
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
            "coalesce(departamento, setor, '—'), data_admissao, coalesce(status,'—') "
            "FROM employees ORDER BY nome LIMIT 300",
            lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t(r[2]), t(r[3]), t(r[4]), t(_fmtdate(r[5])),
                       b((r[6] or '—').capitalize(), "ok" if (r[6] or '') == "ativo" else "mut")])
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
            "duration_minutes, coalesce(total_occurrences,0), coalesce(status::text,'—') "
            "FROM inspection_rounds ORDER BY coalesce(scheduled_date, started_at, created_at) DESC NULLS LAST LIMIT 200",
            lambda r: [t(r[1], 600, "#0F1B3A"), t(r[2]), t(_fmtdate(r[3])),
                       t(f"{int(r[4])} min" if r[4] is not None else '—'), t(str(int(r[5] or 0))),
                       b((r[6] or '—').replace('_', ' ').capitalize(), _ron_tone.get((r[6] or '').lower(), "info"))],
            docsfn=lambda r: [doc("Relatório (PDF)", f"/api/v1/operacional/rondas/{r[0]}/relatorio/pdf", fmt="pdf")])
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
            "coalesce(reason_description, reason_category::text, '—'), incident_date, coalesce(status::text,'—') "
            "FROM disciplinary_actions WHERE coalesce(is_active,true) "
            "ORDER BY coalesce(incident_date, created_at) DESC NULLS LAST LIMIT 200",
            lambda r: [t(r[1], 600, "#0F1B3A"), t((r[2] or '—').replace('_', ' ').capitalize()),
                       t((r[3] or '—')[:60]), t(_fmtdate(r[4])),
                       b((r[5] or '—').replace('_', ' ').capitalize(), _med_tone.get((r[5] or '').lower(), "info"))])
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
        out["nova-ronda"] = {
            "title": "Nova ronda", "sub": "Agenda uma ronda de inspeção (ciclo de campo é no mobile)", "cta": "Criar ronda",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/nova-ronda", "okMsg": "Ronda criada"},
            "fields": [
                {"key": "inspector_id", "label": "Inspetor*", "type": "select", "span": "span 2", "ph": "Selecione o inspetor", "options": _emp_opts},
                {"key": "scheduled_date", "label": "Data agendada", "type": "date", "span": "span 1"},
                {"key": "observations", "label": "Observações", "type": "textarea", "span": "span 2", "ph": "Opcional…"},
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

    try:  # Consultor Operacional (COO) — reusa panorama (fotografia real da operação)
        from modules.operacional.services import consultor_coo_service as _coo
        pan = await _coo.panorama(db)
        _cob = pan.get("cobertura", {}) or {}
        _oc = pan.get("ocorrencias", {}) or {}
        _fn = pan.get("funcionarios", {}) or {}
        _es = pan.get("escalas", {}) or {}
        _pct = _cob.get("percentual")
        out["consultor"] = {
            "title": "Consultor Operacional (COO)", "sub": "Fotografia real da operação — perguntas analíticas no chat interno", "type": "dash", "panelGrid": "1fr",
            "kpis": [
                {"v": str(pan.get("postos", {}).get("ativos", 0)), "l": "Postos ativos", "icon": IC["shield"], "color": "#0F1B3A"},
                {"v": str(pan.get("alocacoes_ativas", 0)), "l": "Alocações ativas", "icon": IC["users"], "color": "#0F1B3A"},
                {"v": str(_oc.get("abertas", 0)), "l": "Ocorrências abertas", "icon": IC["alert"], "color": "#C2410C" if (_oc.get("abertas") or 0) else "#0F1B3A"},
                {"v": (f"{_pct}%" if _pct is not None else "—"), "l": "Cobertura", "icon": IC["shield"], "color": "#0F1B3A"},
            ],
            "panels": [{"title": "Panorama da operação", "rows": [
                {"left": "Colaboradores ativos", "right": str(_fn.get("ativos", 0)), **S["ok"]},
                {"left": "Afastados INSS", "right": str(_fn.get("afastados_inss", 0)), **(S["warn"] if (_fn.get("afastados_inss") or 0) else S["mut"])},
                {"left": "Diaristas ativos", "right": str(pan.get("diaristas", {}).get("ativos", 0)), **S["info"]},
                {"left": "Escalas vigentes hoje", "right": str(_es.get("vigentes_hoje", 0)), **S["info"]},
                {"left": "Postos descobertos", "right": str(len(_cob.get("postos_descobertos", []) or [])), **(S["bad"] if _cob.get("postos_descobertos") else S["ok"])},
            ]}],
        }
    except Exception:  # noqa: BLE001
        await db.rollback()

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
        _ann = (await db.execute(_sqltext(
            "SELECT id, coalesce(titulo,'—') FROM communication_announcements WHERE coalesce(is_active,true) "
            "AND status::text NOT IN ('publicado','published') ORDER BY created_at DESC LIMIT 200"))).fetchall()
        out["comunicado-publicar"] = {
            "title": "Publicar comunicado", "sub": "Publica um comunicado em rascunho", "cta": "Publicar",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/comunicado-publicar", "okMsg": "Comunicado publicado"},
            "fields": [{"key": "announcement_id", "label": "Comunicado (rascunho)*", "type": "select", "span": "span 2", "ph": "Selecione",
                        "options": [{"value": str(i), "label": tt} for i, tt in _ann]}]}
        _alr = (await db.execute(_sqltext(
            "SELECT id, coalesce(title,'—'), coalesce(severity::text,'—') FROM communication_alerts "
            "WHERE coalesce(is_active,true) AND acknowledged_by IS NULL ORDER BY created_at DESC LIMIT 200"))).fetchall()
        out["alerta-ack"] = {
            "title": "Reconhecer alerta", "sub": "Marca um alerta como reconhecido", "cta": "Reconhecer",
            "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/alerta-ack", "okMsg": "Alerta reconhecido"},
            "fields": [{"key": "alert_id", "label": "Alerta ativo*", "type": "select", "span": "span 2", "ph": "Selecione",
                        "options": [{"value": str(i), "label": f"[{sv}] {tt}"} for i, tt, sv in _alr]}]}
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
    except Exception:  # noqa: BLE001
        await db.rollback()

    return out
