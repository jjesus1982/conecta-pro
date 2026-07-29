"""Operacional (T1) — delega ao _build_operacional e ESTENDE com telas de LEITURA
(presença ao vivo, escalas, turnos, reembolsos). Operacional é curado pelo Jordan →
SÓ visibilidade, NUNCA escreve/altera escala/alocação. Reembolso é read-only (sem aprovar/pagar)."""
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text as _sqltext

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.operacional.controllers.redesign_data_controller import (
    S, _build_operacional, _fmtdate, _helpers, _scalar, b, brl, doc, t,
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
EXTRA_MENU: list[dict] = [
    {"id": "rondas", "label": "Rondas",
     "icon": "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"},
    {"id": "passagem-turno-nova", "label": "Nova passagem", "icon": "M12 5v14M5 12h14"},
    {"id": "instrucao-posto-editar", "label": "Editar instrução", "icon": "M12 5v14M5 12h14"},
    {"id": "banco-horas-lancar", "label": "Lançar horas", "icon": "M12 5v14M5 12h14"},
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
    except Exception:  # noqa: BLE001
        pass

    return out
