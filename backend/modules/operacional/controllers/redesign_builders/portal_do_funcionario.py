"""Redesign builder — Portal do Funcionário.

Estende `_build_portal_funcionario` (base: dashboard, contracheque, ferias,
documentos) e liga as 5 telas sem wiring, lendo tabelas REAIS (visão admin/
preview; o portal real é escopado por colaborador logado).
Telas novas: ponto · beneficios · escalas · treinamentos · dados-pessoais.
"""

import uuid

from sqlalchemy import text

from modules.operacional.controllers.redesign_builders import _dgx_y5_portal as _y5  # dgx y5
from modules.operacional.controllers.redesign_data_controller import (
    _ICF,
    IC,
    S,
    _helpers,
    _scalar,
    b,
    brl,
    doc,
    initials,
    t,
)

SLUG = "portal-do-funcionario"
EXTRA_MENU: list[dict] = [
    *_y5.EXTRA_MENU,  # dgx y5 — Minhas justificativas
    {"id": "meus-direitos-cct", "label": "Meus direitos (CCT)", "icon": "M3 3v18h18"},
    {"id": "calculadora-rescisao", "label": "Simulador de rescisão", "icon": "M3 3v18h18"},
    {"id": "contracheques-ged", "label": "Contracheques (GED)", "icon": "M3 3v18h18"},
    {"id": "comunicados", "label": "Comunicados", "icon": "M3 3v18h18"},
    {"id": "bater-ponto", "label": "Bater ponto", "icon": "M3 3v18h18"},
    {"id": "assinaturas-pendentes", "label": "Assinaturas pendentes", "icon": "M3 3v18h18"},
    {
        "id": "ouvidoria",
        "label": "Ouvidoria",
        "icon": "M9 11l3 3L22 4M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11",
    },
]
_ND = "#0F1B3A"


def _d(v, fmt="%d/%m/%Y"):
    try:
        return v.strftime(fmt) if v else "—"
    except Exception:
        return "—"


def _bs(v):
    s = (v or "").lower()
    if s in ("ativo", "active", "concluido", "concluida", "presente", "trabalhado", "aprovado", "completed", "gozada"):
        return b(v or "—", "ok")
    if s in ("pendente", "agendado", "planned", "scheduled", "em_andamento", "andamento", "solicitada"):
        return b(v or "—", "warn")
    if s in ("falta", "ausente", "cancelado", "rejeitado", "off", "folga"):
        return b(v or "—", "bad")
    return b(v or "—", "info")


# Status em PT — espelha os label maps do clássico (meu-espaco): benefícios/escala/treinamento
_PF_ST = {
    "active": ("Ativo", "ok"),
    "ativo": ("Ativo", "ok"),
    "inactive": ("Inativo", "mut"),
    "inativo": ("Inativo", "mut"),
    "cancelled": ("Cancelado", "bad"),
    "canceled": ("Cancelado", "bad"),
    "cancelado": ("Cancelado", "bad"),
    "scheduled": ("Agendado", "warn"),
    "agendado": ("Agendado", "warn"),
    "completed": ("Concluído", "ok"),
    "concluido": ("Concluído", "ok"),
    "in_progress": ("Em andamento", "warn"),
    "confirmed": ("Confirmado", "ok"),
    "absent": ("Falta", "bad"),
    "suspended": ("Suspenso", "warn"),
    "approved": ("Aprovado", "ok"),
    "aprovado": ("Aprovado", "ok"),
    "submitted": ("Pendente", "warn"),
    "pending": ("Pendente", "warn"),
    "rejected": ("Rejeitado", "bad"),
    "rejeitado": ("Rejeitado", "bad"),
}


def _pf_status(v):
    lbl, tone = _PF_ST.get((v or "").lower(), (v or "—", "info"))
    return b(lbl, tone)


def _cpf(v):
    d = "".join(c for c in (v or "") if c.isdigit())
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:11]}" if len(d) == 11 else (v or "—")


_PUNCH = {"entrada": "Entrada", "saida": "Saída", "saída": "Saída", "intervalo": "Intervalo", "retorno": "Retorno"}


async def _resolve_me(db, current_user) -> str | None:
    """employee_id do usuário logado: users.employee_id → fallback e-mail. None se não vinculado.
    É a PAREDE self-only do portal: sem employee resolvido, nenhuma tela mostra dado de terceiro."""
    if current_user is None:
        return None
    me = None
    uid = getattr(current_user, "id", None)
    if uid is not None:
        row = (
            await db.execute(text("SELECT CAST(employee_id AS TEXT) FROM users WHERE id::text=:i"), {"i": str(uid)})
        ).first()
        if row and row[0]:
            me = row[0]
    if not me:
        em = getattr(current_user, "email", None)
        if em:
            r2 = (
                await db.execute(
                    text("SELECT CAST(id AS TEXT) FROM employees WHERE lower(email)=lower(:e) LIMIT 1"), {"e": em}
                )
            ).first()
            if r2 and r2[0]:
                me = r2[0]
    if me:
        try:
            uuid.UUID(str(me))  # valida antes de in-linar no SQL (defesa em profundidade)
        except Exception:
            me = None
    return me


async def build(db, current_user=None) -> dict:
    """Portal PESSOAL — escopado ao colaborador logado (parede self-only / LGPD).

    NÃO chama a base `_build_portal_funcionario` (visão admin agregada: vazaria holerite/
    ponto/benefícios de TODOS). Toda tela filtra por `employee_id = <usuário logado>`. Sem
    vínculo employee → telas vazias com aviso, NUNCA dado de terceiro. `me` é UUID validado,
    vindo do nosso banco (users/employees), não do request → in-lining seguro."""
    out, safe, tbl = _helpers(db)
    me = await _resolve_me(db, current_user)
    _vinc = me is not None
    # sem vínculo → literal que não casa nada → todas as queries voltam vazias
    me_lit = f"'{me}'" if _vinc else "'00000000-0000-0000-0000-000000000000'"
    _nota = "" if _vinc else " — vincule seu cadastro de colaborador ao usuário"

    # dashboard PESSOAL (substitui o dash agregado da base, que vazava totais da empresa)
    async def _dash():
        comp = (
            await db.execute(
                text(
                    f"SELECT reference_year, reference_month, net_salary FROM hr_payslips "
                    f"WHERE employee_id={me_lit} AND payslip_code NOT LIKE '13O-%' AND make_date(reference_year, reference_month, 1) <= date_trunc('month', current_date) "
                    f"ORDER BY reference_year DESC, reference_month DESC LIMIT 1"
                )
            )
        ).fetchone()
        comp_lbl = f"{comp[1]:02d}/{comp[0]}" if comp and comp[1] else "—"
        meu_liq = brl(comp[2]) if comp and comp[2] is not None else "—"
        n_pay = await _scalar(db, f"SELECT count(*) FROM hr_payslips WHERE employee_id={me_lit}")
        # hr_vacation_requests é a AUTORITATIVA (test_oraculo_ferias_autoritativa, 13/08); a cópia
        # employee_vacation_requests parou em 01/04 com 14 pedidos presos em SUBMITTED — o portal
        # mostrava ao colaborador um pedido "enviado" que o DP já tinha aprovado (achado 07/09).
        n_fer = await _scalar(db, f"SELECT count(*) FROM hr_vacation_requests WHERE employee_id={me_lit}")
        n_ben = await _scalar(db, f"SELECT count(*) FROM employee_benefits WHERE employee_id={me_lit}")
        n_doc = await _scalar(db, f"SELECT count(*) FROM ged_kit_documents WHERE employee_id={me_lit}")
        fr = (
            await db.execute(
                text(
                    f"SELECT coalesce(status::text,'—'), count(*) FROM hr_vacation_requests "
                    f"WHERE employee_id={me_lit} GROUP BY 1 ORDER BY 2 DESC LIMIT 5"
                )
            )
        ).fetchall()
        return {
            "title": "Início",
            "sub": "Meu portal — dados pessoais" + _nota,
            "cta": "Atualizar",
            "type": "dash",
            "panelGrid": "1fr 1fr",
            "kpis": [
                {"v": str(n_pay), "l": "Meus holerites", "icon": _ICF["money"], "color": "#0F1B3A"},
                {"v": str(n_fer), "l": "Minhas férias", "icon": IC["cal"], "color": "#0F1B3A"},
                {"v": str(n_ben), "l": "Benefícios", "icon": _ICF["hand"], "color": "#0F1B3A"},
                {"v": str(n_doc), "l": "Documentos", "icon": IC["users"], "color": "#0F1B3A"},
            ],
            "panels": [
                {"title": f"Meu holerite — {comp_lbl}", "rows": [{"left": "Líquido", "right": meu_liq, **S["ok"]}]},
                {
                    "title": "Minhas férias por status",
                    "rows": [{"left": (s or "—").capitalize(), "right": str(c), **S["info"]} for s, c in fr]
                    or [{"left": "Sem férias", "right": "0", **S["mut"]}],
                },
            ],
        }

    await safe("dashboard", _dash())

    # Contracheque — só MEUS holerites + botão Holerite PDF por-linha
    await safe(
        "contracheque",
        tbl(
            "Contracheque",
            "Meus holerites" + _nota,
            "—",
            ["Competência", "Líquido", "Status"],
            "1.4fr 1fr 0.9fr",
            f"SELECT p.reference_month, p.reference_year, p.net_salary, "
            f"coalesce(p.status::text,'—'), CAST(p.id AS TEXT) "
            f"FROM hr_payslips p WHERE p.employee_id={me_lit} "
            f"ORDER BY p.reference_year DESC, p.reference_month DESC LIMIT 200",
            lambda r: [
                t(f"{r[0]:02d}/{r[1]}" if r[0] else "—"),
                t(brl(r[2]) if r[2] is not None else "—"),
                b((r[3] or "—").capitalize(), "info"),
            ],
            docsfn=lambda r: [
                doc("Holerite", f"/api/v1/people-management/dp/payslips/{r[4]}/pdf", fmt="pdf", gate="financeiro")
            ],
        ),
    )

    # Minhas férias
    await safe(
        "ferias",
        tbl(
            "Minhas férias",
            "Minhas solicitações" + _nota,
            "—",
            ["Início", "Fim", "Dias", "Status"],
            "1fr 1fr 0.7fr 0.9fr",
            f"SELECT v.start_date, v.end_date, v.days_requested, coalesce(v.status::text,'—') "
            f"FROM hr_vacation_requests v WHERE v.employee_id={me_lit} "
            f"ORDER BY v.start_date DESC NULLS LAST LIMIT 200",
            lambda r: [t(_d(r[0])), t(_d(r[1])), t(str(r[2] or "—")), _pf_status(r[3])],
        ),
    )

    # Meu ponto
    await safe(
        "ponto",
        tbl(
            "Meu ponto",
            "Minhas batidas" + _nota,
            "—",
            ["Tipo", "Data/hora", "Posto", "Facial"],
            "1fr 1.2fr 1.4fr 0.8fr",
            f"SELECT coalesce(p.punch_type,'—'), p.punch_timestamp, coalesce(p.posto_nome,'—'), p.facial_match "
            f"FROM gp_clock_punches p WHERE p.employee_id={me_lit} "
            f"ORDER BY p.punch_timestamp DESC LIMIT 300",
            lambda r: [
                t(_PUNCH.get((r[0] or "").lower(), (r[0] or "—").capitalize())),
                t(_d(r[1], "%d/%m/%Y %H:%M")),
                t(r[2]),
                (b("OK", "ok") if r[3] else b("—", "mut")),
            ],
        ),
    )

    # Meus benefícios
    await safe(
        "beneficios",
        tbl(
            "Benefícios",
            "Meus benefícios" + _nota,
            "—",
            ["Tipo", "Provedor", "Plano", "Status"],
            "1fr 1.2fr 1.2fr 0.9fr",
            f"SELECT coalesce(x.type::text,'—'), coalesce(x.provider,'—'), "
            f"coalesce(x.plan_name,'—'), coalesce(x.status::text,'—') "
            f"FROM employee_benefits x WHERE x.employee_id={me_lit} "
            f"ORDER BY x.created_at DESC LIMIT 200",
            lambda r: [t((r[0] or "—").replace("_", " ").capitalize()), t(r[1]), t(r[2]), _pf_status(r[3])],
        ),
    )

    # Minha escala
    await safe(
        "escalas",
        tbl(
            "Minha escala",
            "Meus turnos" + _nota,
            "—",
            ["Data", "Início", "Fim", "Status"],
            "1fr 0.8fr 0.8fr 0.9fr",
            f"SELECT s.shift_date, to_char(s.planned_start_time,'HH24:MI'), "
            f"to_char(s.planned_end_time,'HH24:MI'), coalesce(s.status::text,'—') "
            f"FROM shifts s WHERE s.employee_id::text={me_lit} "
            f"ORDER BY s.shift_date DESC NULLS LAST LIMIT 300",
            lambda r: [t(_d(r[0])), t(r[1] or "—"), t(r[2] or "—"), _pf_status(r[3])],
        ),
    )

    # Meus documentos (base vazava TODOS → aqui só os meus)
    await safe(
        "documentos",
        tbl(
            "Meus documentos",
            "Meus documentos" + _nota,
            "—",
            ["Documento", "Tipo", "Assinado"],
            "2fr 1.4fr 0.9fr",
            f"SELECT coalesce(g.document_name,'—'), coalesce(g.document_type::text,'—'), g.is_signed "
            f"FROM ged_kit_documents g WHERE g.employee_id={me_lit} "
            f"ORDER BY g.created_at DESC NULLS LAST LIMIT 200",
            lambda r: [
                t(r[0] or "—", 600, _ND),
                t((r[1] or "—").replace("_", " ")),
                b("Assinado", "ok") if r[2] else b("Pendente", "warn"),
            ],
        ),
    )

    # Meus treinamentos (via matrícula training_enrollments)
    await safe(
        "treinamentos",
        tbl(
            "Treinamentos",
            "Meus treinamentos" + _nota,
            "—",
            ["Treinamento", "Início", "Fim", "Status"],
            "2fr 1fr 1fr 0.9fr",
            f"SELECT coalesce(title,'—'), start_date, end_date, coalesce(status::text,'—') "
            f"FROM trainings WHERE id IN (SELECT training_id FROM training_enrollments WHERE employee_id={me_lit}) "
            f"ORDER BY start_date DESC NULLS LAST LIMIT 200",
            lambda r: [t(r[0] or "—", 600, _ND), t(_d(r[1])), t(_d(r[2])), _pf_status(r[3])],
        ),
    )

    # Meus dados pessoais (só o MEU cadastro)
    await safe(
        "dados-pessoais",
        tbl(
            "Dados pessoais",
            "Meu cadastro" + _nota,
            "—",
            ["Nome", "CPF", "RG", "Nascimento", "Estado civil", "Cargo", "Telefone"],
            "1.8fr 1.1fr 1fr 1fr 1fr 1.3fr 1.1fr",
            f"SELECT coalesce(nome,'—'), coalesce(cpf,'—'), coalesce(rg,'—'), data_nascimento, "
            f"coalesce(estado_civil::text,'—'), coalesce(cargo,'—'), coalesce(telefone,'—') "
            f"FROM employees WHERE id::text={me_lit} LIMIT 1",
            lambda r: [
                t(r[0] or "—", 600, _ND, initials(r[0] or "")),
                t(_cpf(r[1])),
                t(r[2]),
                t(_d(r[3])),
                t((r[4] or "—").replace("_", " ")),
                t(r[5]),
                t(r[6]),
            ],
        ),
    )

    # Ouvidoria (2026-08-10): responder leva {manifestacao_id} no caminho -> acao por LINHA.
    # A mensagem do colaborador aparece; a resposta fica visivel a ele.
    await safe(
        "ouvidoria",
        tbl(
            "Ouvidoria",
            "Manifestações dos colaboradores",
            "—",
            ["Protocolo", "Categoria", "Mensagem", "Anônima", "Status"],
            "1fr 1.1fr 2.2fr 0.8fr 0.9fr",
            "SELECT id, coalesce(protocolo,'—'), coalesce(categoria::text,'—'), coalesce(mensagem,'—'), "
            "coalesce(anonimo,false), coalesce(status::text,'aberta') "
            "FROM ouvidoria_manifestacoes ORDER BY created_at DESC NULLS LAST LIMIT 200",
            lambda r: [
                t(r[1], 600, "#0F1B3A"),
                t((r[2] or "—").capitalize()),
                t((r[3] or "—")[:90]),
                b("Sim", "warn") if r[4] else b("Não", "mut"),
                b((r[5] or "—").capitalize(), "ok" if (r[5] or "").lower() in ("respondida", "encerrada") else "warn"),
            ],
            actionsfn=lambda r: [
                {
                    "title": f"Responder a manifestação {r[1]}",
                    "sub": "A resposta fica VISÍVEL ao autor. Se for anônima, você responde sem saber quem é.",
                    "endpoint": f"/api/v1/people-management/portal/ouvidoria-admin/{r[0]}/responder",
                    "method": "POST",
                    "btnLabel": "Responder",
                    "submitLabel": "Enviar resposta",
                    "btnStyle": "primary",
                    "okMsg": "Resposta registrada. Recarregue a tela.",
                    "fields": [
                        {
                            "key": "resposta",
                            "label": "Resposta ao colaborador*",
                            "type": "textarea",
                            "span": "span 2",
                            "value": "",
                        },
                        {
                            "key": "status",
                            "label": "Novo status",
                            "type": "select",
                            "span": "span 2",
                            "value": "",
                            "options": [
                                {"value": "respondida", "label": "Respondida"},
                                {"value": "encerrada", "label": "Encerrada"},
                            ],
                        },
                    ],
                },
            ],
        ),
    )

    await _ligar_lote3_20260908(db, out, me if _vinc else None, current_user)
    await _ligar_lote4_20260908(db, out, me if _vinc else None)
    await _ligar_lote5_20260908(db, out, me if _vinc else None)
    await _y5.telas(db, out, me if _vinc else None)  # dgx y5
    return out


async def _ligar_lote3_20260908(db, out: dict, me, current_user) -> None:
    """LIGAR lote 3 (08/09/2026): comunicados (confirmar leitura), bater ponto, assinaturas pendentes — sempre do usuário logado."""
    import logging as _lg

    from sqlalchemy import text as _T  # noqa: N812 — alias curto do builder

    from modules.operacional.controllers.redesign_data_controller import _helpers, b, t

    _log = _lg.getLogger(__name__)
    _, _safe, tbl = _helpers(db)
    uid = str(getattr(current_user, "id", "") or "")
    me_lit = f"'{me}'" if me else "'00000000-0000-0000-0000-000000000000'"

    try:  # POST /operacional/comunicados/{id}/confirmar
        out["comunicados"] = await tbl(
            "Comunicados",
            "Comunicados publicados · confirme a leitura quando o comunicado pedir · fonte: communication_announcements",
            "—",
            ["Título", "Tipo", "Prioridade", "Publicado", "Situação"],
            "2.2fr 0.9fr 0.9fr 0.9fr 1fr",
            f"SELECT a.id::text, coalesce(a.titulo,'—'), coalesce(a.tipo,'—'), coalesce(a.prioridade,'—'), a.data_publicacao, coalesce(a.requer_confirmacao,false), "
            f"(SELECT max(r.confirmed_at) FROM communication_announcement_reads r WHERE r.announcement_id=a.id AND r.user_id::text='{uid}') "
            # status aceita as DUAS grafias: as 10 linhas antigas gravaram 'publicado' e a ação
            # de publicar de hoje grava 'published'. Com o filtro só em 'publicado', todo
            # comunicado publicado a partir de agora ficava INVISÍVEL para o colaborador —
            # medido em 14/09/2026 publicando um e não achando no portal.
            "FROM communication_announcements a WHERE coalesce(a.is_active,true) AND a.status IN ('publicado','published') AND (a.data_expiracao IS NULL OR a.data_expiracao >= now()) "
            "ORDER BY a.data_publicacao DESC NULLS LAST LIMIT 100",
            lambda r: [
                t(r[1][:70], 600, "#0F1B3A"),
                t(r[2]),
                t(r[3]),
                t(_d(r[4])),
                b(
                    "Confirmado" if r[6] else ("Confirmar leitura" if r[5] else "Informativo"),
                    "ok" if r[6] else ("warn" if r[5] else "mut"),
                ),
            ],
            actionsfn=lambda r: (
                [
                    {
                        "title": f"Confirmar leitura — {r[1][:50]}",
                        "endpoint": f"/api/v1/operacional/comunicados/{r[0]}/confirmar",
                        "method": "POST",
                        "btnLabel": "Confirmar leitura",
                        "btnStyle": "primary",
                        "submitLabel": "Confirmo que li",
                        "okMsg": "Leitura confirmada.",
                        "fields": [],
                    }
                ]
                if (r[5] and not r[6])
                else []
            ),
        )
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        _log.warning("portal comunicados: %s", exc)

    try:  # POST /people-management/ponto/batida/me?punch_type=…
        ult = None
        if me:
            ult = (
                await db.execute(
                    _T(
                        f"SELECT punch_type, punch_timestamp FROM gp_clock_punches WHERE employee_id={me_lit} ORDER BY punch_timestamp DESC LIMIT 1"
                    )
                )
            ).first()
        tipos = [
            ("entrada", "Entrada"),
            ("saida_almoco", "Saída para almoço"),
            ("retorno_almoco", "Retorno do almoço"),
            ("saida", "Saída"),
        ]
        sub = (
            "Registra a batida do usuário logado, hora do servidor (sem foto/GPS por aqui — o painel de ponto continua sendo o caminho com reconhecimento facial)."
            + (
                f" Última batida: {str(ult[0]).replace('_', ' ')} em {_d(ult[1], '%d/%m %H:%M')}."
                if ult
                else " Nenhuma batida registrada ainda."
            )
        )
        out["bater-ponto"] = {
            "title": "Bater ponto",
            "sub": sub if me else "Seu usuário não está vinculado a um colaborador — nada a registrar.",
            "cta": "—",
            "type": "table",
            "searchHint": "",
            "grid": "1.4fr 1fr",
            "cols": ["Batida", "Quando"],
            "rows": [
                {
                    "cells": [t(lbl, 600, "#0F1B3A"), t("agora")],
                    "actions": [
                        {
                            "title": f"Bater ponto — {lbl}",
                            "endpoint": f"/api/v1/people-management/ponto/batida/me?punch_type={k}",
                            "method": "POST",
                            "btnLabel": lbl,
                            "btnStyle": "primary",
                            "submitLabel": "Registrar batida",
                            "okMsg": "Batida registrada.",
                            "fields": [],
                        }
                    ],
                }
                for k, lbl in tipos
            ]
            if me
            else [],
        }
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        _log.warning("portal bater-ponto: %s", exc)

    try:  # GET /signatures/meus-pendentes (por SQL) + POST /signatures/assinar-lote
        out["assinaturas-pendentes"] = await tbl(
            "Assinaturas pendentes",
            "Documentos esperando a sua assinatura · fonte: sig_signature_requests",
            "—",
            ["Documento", "Tipo", "Finalidade", "Pedido em", "Vence em"],
            "2.2fr 1fr 1fr 0.9fr 0.9fr",
            f"SELECT id::text, coalesce(title, document_name, '—'), coalesce(document_type,'—'), coalesce(purpose,'—'), created_at, due_date "
            f"FROM sig_signature_requests WHERE upper(status)='PENDING' AND (signer_id::text='{uid}' OR signer_id::text={me_lit}) ORDER BY created_at DESC LIMIT 100",
            lambda r: [t(r[1][:70], 600, "#0F1B3A"), t(r[2]), t(r[3]), t(_d(r[4])), t(_d(r[5]))],
            actionsfn=lambda r: [
                {
                    "title": f"Assinar — {r[1][:50]}",
                    "endpoint": "/api/v1/signatures/assinar-lote",
                    "method": "POST",
                    "btnLabel": "Assinar",
                    "btnStyle": "primary",
                    "submitLabel": "Assinar agora",
                    "okMsg": "Assinado.",
                    "fields": [
                        {
                            "key": "request_ids",
                            "label": "Pedido(s)",
                            "type": "json",
                            "span": "span 2",
                            "value": f'["{r[0]}"]',
                        }
                    ],
                }
            ],
        )
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        _log.warning("portal assinaturas: %s", exc)


async def _ligar_lote4_20260908(db, out: dict, me) -> None:
    """LIGAR lote 4 (08/09/2026): GET /ged/ged-integration/contracheques/{employee_id} — por SQL, do logado."""
    import logging as _lg

    from modules.operacional.controllers.redesign_data_controller import _helpers, t

    _log = _lg.getLogger(__name__)
    _, _safe, tbl = _helpers(db)
    me_lit = f"'{me}'" if me else "'00000000-0000-0000-0000-000000000000'"
    try:
        out["contracheques-ged"] = await tbl(
            "Meus contracheques (GED)",
            "Contracheques arquivados no GED para você · fonte: ged_contracheques",
            "—",
            ["Competência", "Arquivo", "Tamanho", "Arquivado em"],
            "1fr 2.4fr 0.8fr 1fr",
            f"SELECT coalesce(competencia, lpad(mes::text,2,'0') || '/' || ano), coalesce(path,'—'), tamanho_bytes, created_at FROM ged_contracheques WHERE employee_id={me_lit} ORDER BY ano DESC, mes DESC LIMIT 100",
            lambda r: [
                t(r[0], 600, "#0F1B3A"),
                t(r[1].rsplit("/", 1)[-1][:60]),
                t(f"{(r[2] or 0) // 1024} KB"),
                t(_d(r[3])),
            ],
        )
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        _log.warning("contracheques-ged: %s", exc)


async def _ligar_lote5_20260908(db, out: dict, me=None) -> None:
    """LIGAR lote 5 (08/09/2026): rotas do people-management/users/SST que só existiam por API. Blocos independentes."""
    import logging as _lg

    from sqlalchemy import text as _T  # noqa: N812 — alias curto do builder

    from modules.operacional.controllers.redesign_builders._ligar_generico import (
        chamar,
        painel_de_dict,
        selecionar,
    )
    from modules.operacional.controllers.redesign_data_controller import _helpers

    _log = _lg.getLogger(__name__)
    _, _safe, tbl = _helpers(db)
    _SN = [{"value": "true", "label": "Sim"}, {"value": "false", "label": "Não"}]

    def _fd(v, fmt="%d/%m/%Y"):
        try:
            return v.strftime(fmt) if v else "—"
        except Exception:  # noqa: BLE001
            return str(v or "—")

    async def _n(sql):
        try:
            return (await db.execute(_T(sql))).scalar() or 0
        except Exception:  # noqa: BLE001
            await db.rollback()
            return 0

    async def _emps():
        try:
            return [
                {"value": str(i), "label": n}
                for i, n in (
                    await db.execute(_T("SELECT id, nome FROM employees WHERE status='ativo' ORDER BY nome LIMIT 400"))
                ).fetchall()
            ]
        except Exception:  # noqa: BLE001
            await db.rollback()
            return []

    def _consulta(key, titulo, sub, endpoint, fields, method="GET"):
        out[key] = {
            "title": titulo,
            "sub": sub,
            "cta": "Consultar",
            "type": "form",
            "submit": {
                "endpoint": endpoint,
                "method": method,
                "query": True,
                "okMsg": "Consulta feita — veja o resultado.",
                "showResult": True,
            },
            "fields": fields,
        }

    try:  # GET /people-management/portal/cct/direitos — do logado
        if me:
            from modules.people_management.employee_portal.controllers import (  # noqa: N812
                my_cct_controller as Mc,
            )

            res = await chamar(Mc.get_meus_direitos, db, employee_id=str(me))
            out["meus-direitos-cct"] = painel_de_dict(
                "Meus direitos pela CCT",
                "Piso do seu cargo, adicionais e benefícios obrigatórios da convenção SINDECOMPRESTS 2026.",
                res,
            )
        else:
            out["meus-direitos-cct"] = painel_de_dict(
                "Meus direitos pela CCT", "Seu usuário não está vinculado a um colaborador.", {"vinculo": "ausente"}
            )
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        _log.warning("meus-direitos-cct: %s", exc)
    out["calculadora-rescisao"] = {  # POST /people-management/portal/cct/calculadora?motivo=
        "title": "Simulador de rescisão (CCT)",
        "sub": "Estima as verbas rescisórias do seu contrato pelo motivo escolhido. Só simula — nada é registrado.",
        "cta": "Simular",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/people-management/portal/cct/calculadora",
            "query": True,
            "okMsg": "Simulado — veja o resultado.",
            "showResult": True,
        },
        "fields": [
            selecionar(
                "motivo",
                "Motivo",
                [
                    {"value": v, "label": l}
                    for v, l in (
                        ("sem_justa_causa", "Dispensa sem justa causa"),
                        ("justa_causa", "Justa causa"),
                        ("pedido_demissao", "Pedido de demissão"),
                        ("acordo", "Acordo"),
                    )
                ],
                "span 1",
            )
        ],
    }
