"""
Redesign — dados reais por módulo (READ-ONLY).

Devolve patches de tela na MESMA forma que os *.dc.html (kpis/panels/cols/rows/items),
para o renderizador genérico do /redesign trocar os exemplos do pacote por dado real.

Oráculo: todo valor exibido == fato no banco. Vazio-real = 0/"aguardando dado".
NUNCA fabricar. Este controller é somente leitura.
"""

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser, require_permission
from core.database import get_db
from modules.operacional.scope import OperationalScope, get_operational_scope

router = APIRouter()

# Paleta de status (idêntica ao pacote)
S = {
    "ok": {"color": "#16A34A", "bg": "#E7F7ED"},
    "warn": {"color": "#B45309", "bg": "#FFFBEB"},
    "bad": {"color": "#B91C1C", "bg": "#FEF2F2"},
    "info": {"color": "#2563EB", "bg": "#EAF0FF"},
    "mut": {"color": "#64748B", "bg": "#F1F4FA"},
}
IC = {
    "shield": "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z",
    "users": "M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M9 3a4 4 0 1 1 0 8 4 4 0 0 1 0-8",
    "cal": "M3 4h18v18H3zM16 2v4M8 2v4M3 10h18",
    "alert": "M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h16.9a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01",
}


def t(v: Any, w: int = 500, tc: str = "#334155", ini: str = "") -> dict:
    return {"isText": True, "v": str(v) if v is not None else "—", "w": w, "tc": tc, "ini": ini}


def b(v: str, s: str) -> dict:
    p = S.get(s, S["mut"])
    return {"isBadge": True, "v": v, "color": p["color"], "bg": p["bg"]}


def initials(nome: str) -> str:
    parts = [p for p in (nome or "").split() if p]
    if not parts:
        return "--"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


async def _scalar(db: AsyncSession, sql: str) -> Any:
    r = await db.execute(text(sql))
    return r.scalar()


async def _build_operacional(db: AsyncSession) -> dict:
    postos_ativos = await _scalar(db, "SELECT count(*) FROM posts WHERE status='active'")
    colaboradores = await _scalar(db, "SELECT count(*) FROM employees WHERE status='ativo'")
    aloc_ativas = await _scalar(db, "SELECT count(*) FROM employee_alocacoes WHERE ativo=true")
    occ_7d = await _scalar(db, "SELECT count(*) FROM occurrences WHERE occurred_at >= now()-interval '7 days'")

    # Cobertura: postos ativos + headcount
    cov = (await db.execute(text(
        "SELECT p.name, p.current_headcount, p.required_headcount "
        "FROM posts p WHERE p.status='active' ORDER BY p.name LIMIT 8"
    ))).fetchall()
    cov_rows = []
    for name, hc, req in cov:
        hc = hc or 0
        req = req or 0
        if req and hc >= req:
            cov_rows.append({"left": name, "right": "100% coberto", **S["ok"]})
        elif hc > 0:
            cov_rows.append({"left": name, "right": f"{hc} em campo", **S["warn"]})
        else:
            cov_rows.append({"left": name, "right": "sem headcount", **S["mut"]})
    if not cov_rows:
        cov_rows = [{"left": "Nenhum posto ativo", "right": "aguardando dado", **S["mut"]}]

    # Últimas ocorrências
    occ = (await db.execute(text(
        "SELECT o.title, p.name, o.severity, o.occurred_at "
        "FROM occurrences o LEFT JOIN posts p ON p.id=o.post_id "
        "ORDER BY o.occurred_at DESC NULLS LAST LIMIT 5"
    ))).fetchall()

    def sev_tone(sev: str) -> tuple:
        s = (sev or "").lower()
        if s in ("critical", "high", "grave", "alta", "critica"):
            return ("Grave", "bad")
        if s in ("medium", "media", "moderada"):
            return ("Média", "warn")
        if s in ("low", "baixa"):
            return ("Baixa", "info")
        return (sev or "Info", "info")

    occ_rows = []
    for title, pname, sev, _ in occ:
        lbl, tone = sev_tone(sev)
        occ_rows.append({"left": f"{title} · {pname or 's/ posto'}", "right": lbl, **S[tone]})
    if not occ_rows:
        occ_rows = [{"left": "Sem ocorrências nos últimos 7 dias", "right": "0", **S["ok"]}]

    visao = {
        "title": "Visão geral", "sub": f"{postos_ativos} postos ativos · {colaboradores} colaboradores",
        "cta": "Nova ação", "type": "dash", "panelGrid": "1.6fr 1fr",
        "kpis": [
            {"v": str(postos_ativos), "l": "Postos ativos", "icon": IC["shield"], "color": "#0F1B3A"},
            {"v": str(colaboradores), "l": "Colaboradores", "icon": IC["users"], "color": "#0F1B3A"},
            {"v": str(aloc_ativas), "l": "Alocações ativas", "icon": IC["cal"], "color": "#0F1B3A"},
            {"v": str(occ_7d), "l": "Ocorrências (7d)", "icon": IC["alert"], "color": "#C2410C" if occ_7d else "#0F1B3A"},
        ],
        "panels": [
            {"title": "Cobertura dos postos hoje", "rows": cov_rows},
            {"title": "Últimas ocorrências", "rows": occ_rows},
        ],
    }

    # Postos (tabela)
    prows = (await db.execute(text(
        "SELECT p.name, c.name, p.shift_type, p.current_headcount, p.status "
        "FROM posts p LEFT JOIN clients c ON c.id=p.client_id "
        "ORDER BY (p.status='active') DESC, p.name"
    ))).fetchall()
    postos = {
        "title": "Postos", "sub": f"{postos_ativos} postos ativos", "cta": "Novo posto",
        "type": "table", "searchHint": "Buscar posto ou cliente…",
        "grid": "2fr 1.6fr 1fr 1fr 0.9fr", "cols": ["Posto", "Cliente", "Turno", "Vigilantes", "Status"],
        "rows": [{"cells": [
            t(name, 600, "#0F1B3A"), t(cli or "—"), t(shift or "—"),
            t(hc if hc is not None else 0),
            b("Ativo", "ok") if st == "active" else b("Inativo", "mut"),
        ]} for name, cli, shift, hc, st in prows],
    }

    # Colaboradores (tabela)
    erows = (await db.execute(text(
        "SELECT nome, cargo, posto_atual_nome, status FROM employees "
        "WHERE status='ativo' ORDER BY nome LIMIT 300"
    ))).fetchall()
    st_tone = {"ativo": ("Ativo", "ok"), "afastado_inss": ("Afastado", "warn"),
               "suspenso": ("Suspenso", "warn"), "inativo": ("Inativo", "mut"),
               "demitido": ("Demitido", "bad")}
    colaboradores_scr = {
        "title": "Colaboradores", "sub": f"{len(erows)} colaboradores ativos", "cta": "Novo colaborador",
        "type": "table", "searchHint": "Buscar colaborador…",
        "grid": "2fr 1.4fr 1.6fr 0.9fr", "cols": ["Colaborador", "Cargo", "Posto", "Status"],
        "rows": [{"cells": [
            t(nome, 600, "#0F1B3A", initials(nome)), t(cargo or "—"), t(posto or "—"),
            b(*st_tone.get(status, (status or "—", "mut"))),
        ]} for nome, cargo, posto, status in erows],
    }

    # Alocações (tabela)
    arows = (await db.execute(text(
        "SELECT e.nome, c.name, al.funcao, al.ativo "
        "FROM employee_alocacoes al LEFT JOIN employees e ON e.id=al.employee_id "
        "LEFT JOIN clients c ON c.id=al.condominio_id "
        "ORDER BY al.ativo DESC, e.nome LIMIT 300"
    ))).fetchall()
    alocacoes = {
        "title": "Alocações", "sub": f"{aloc_ativas} alocações ativas", "cta": "Nova alocação",
        "type": "table", "searchHint": "Buscar alocação…",
        "grid": "2fr 1.6fr 1.2fr 0.9fr", "cols": ["Colaborador", "Cliente / Posto", "Função", "Status"],
        "rows": [{"cells": [
            t(nome or "—", 600, "#0F1B3A", initials(nome or "")), t(cli or "—"), t(funcao or "—"),
            b("Ativa", "ok") if ativo else b("Encerrada", "mut"),
        ]} for nome, cli, funcao, ativo in arows],
    }

    # Ocorrências (lista)
    olist = (await db.execute(text(
        "SELECT o.title, p.name, o.severity, o.occurred_at "
        "FROM occurrences o LEFT JOIN posts p ON p.id=o.post_id "
        "ORDER BY o.occurred_at DESC NULLS LAST LIMIT 30"
    ))).fetchall()
    dotmap = {"bad": "#EF4444", "warn": "#F5A524", "info": "#2563EB", "ok": "#16A34A"}
    ocorrencias = {
        "title": "Ocorrências", "sub": "Registro de eventos nos postos", "cta": "Registrar ocorrência",
        "type": "list",
        "items": [(lambda lbl, tone: {
            "title": title, "meta": f"{pname or 's/ posto'} · {occ_at.strftime('%d/%m %H:%M') if occ_at else 's/ data'}",
            "dot": dotmap.get(tone, "#64748B"), "badge": lbl, **S[tone],
        })(*sev_tone(sev)) for title, pname, sev, occ_at in olist],
    }
    if not ocorrencias["items"]:
        ocorrencias["items"] = [{"title": "Sem ocorrências registradas", "meta": "aguardando dado",
                                 "dot": "#16A34A", "badge": "OK", **S["ok"]}]

    # Ocorrência rápida (FORM com ESCRITA real → POST /redesign/action/occurrence)
    post_opts = (await db.execute(text(
        "SELECT id, name FROM posts WHERE status='active' ORDER BY name"))).fetchall()
    ocorrencia_rapida = {
        "title": "Ocorrência rápida", "sub": "Registro ágil de evento em campo", "cta": "Registrar",
        "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/occurrence", "okMsg": "Ocorrência registrada com sucesso"},
        "fields": [
            {"key": "post_id", "label": "Posto", "type": "select", "span": "span 1",
             "ph": "Selecione o posto", "options": [{"value": str(i), "label": n} for i, n in post_opts]},
            {"key": "occurrence_type", "label": "Tipo", "type": "select", "span": "span 1", "ph": "Tipo",
             "options": [{"value": v, "label": l} for v, l in [
                 ("incidente", "Incidente"), ("nao_conformidade_documental", "Não conformidade"),
                 ("abandono_posto", "Abandono de posto"), ("atraso", "Atraso"), ("falta_epi", "Falta de EPI"),
                 ("uso_celular", "Uso de celular"), ("elogio", "Elogio"), ("outros", "Outros")]]},
            {"key": "severity", "label": "Gravidade", "type": "select", "span": "span 1", "ph": "Gravidade",
             "options": [{"value": v, "label": l} for v, l in [
                 ("leve", "Leve"), ("moderada", "Moderada"), ("grave", "Grave"), ("gravissima", "Gravíssima")]]},
            {"key": "title", "label": "Título", "type": "text", "span": "span 1", "ph": "Resumo curto"},
            {"key": "description", "label": "Descrição", "type": "textarea", "span": "span 2", "ph": "Descreva o ocorrido…"},
        ],
    }

    # Resolver ocorrência (FORM com ESCRITA real → POST /redesign/action/occurrence-resolve)
    open_occ = (await db.execute(text(
        "SELECT id, code, title FROM occurrences WHERE status='aberta' ORDER BY occurred_at DESC NULLS LAST LIMIT 50"))).fetchall()
    resolver_ocorrencia = {
        "title": "Resolver ocorrência", "sub": "Encerrar uma ocorrência aberta com a ação tomada", "cta": "Resolver",
        "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/occurrence-resolve", "okMsg": "Ocorrência resolvida"},
        "fields": [
            {"key": "occurrence_id", "label": "Ocorrência aberta*", "type": "select", "span": "span 2", "ph": "Selecione a ocorrência",
             "options": [{"value": str(i), "label": f"{c or '—'} · {(ti or '')[:50]}"} for i, c, ti in open_occ]},
            {"key": "corrective_action", "label": "Ação corretiva*", "type": "textarea", "span": "span 2", "ph": "O que foi feito para resolver…"},
            {"key": "resolution_notes", "label": "Observações", "type": "textarea", "span": "span 2", "ph": "Notas adicionais (opcional)…"},
        ],
    }

    # Comentar ocorrência (FORM com ESCRITA real → POST /redesign/action/occurrence-comment)
    recent_occ = (await db.execute(text(
        "SELECT id, code, title FROM occurrences ORDER BY occurred_at DESC NULLS LAST LIMIT 50"))).fetchall()
    comentar_ocorrencia = {
        "title": "Comentar ocorrência", "sub": "Adicionar um comentário a uma ocorrência", "cta": "Comentar",
        "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/occurrence-comment", "okMsg": "Comentário adicionado"},
        "fields": [
            {"key": "occurrence_id", "label": "Ocorrência*", "type": "select", "span": "span 2", "ph": "Selecione a ocorrência",
             "options": [{"value": str(i), "label": f"{c or '—'} · {(ti or '')[:50]}"} for i, c, ti in recent_occ]},
            {"key": "content", "label": "Comentário*", "type": "textarea", "span": "span 2", "ph": "Escreva o comentário…"},
        ],
    }

    # Diaristas — opções (referência) + LEITURA + FORM Lançar diária
    d_diaristas = (await db.execute(text("SELECT id, nome FROM diaria_diaristas WHERE ativo ORDER BY nome"))).fetchall()
    d_postos = (await db.execute(text("SELECT nome FROM diaria_postos WHERE ativo ORDER BY nome"))).fetchall()
    d_funcoes = (await db.execute(text("SELECT nome FROM diaria_funcoes WHERE ativo ORDER BY nome"))).fetchall()
    d_turnos = (await db.execute(text("SELECT nome FROM diaria_turnos WHERE ativo ORDER BY nome"))).fetchall()
    lancar_diaria = {
        "title": "Lançar diária", "sub": "Registrar a diária de um diarista (o valor é automático pela função/turno)",
        "cta": "Lançar diária", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/diaria", "okMsg": "Diária lançada"},
        "fields": [
            {"key": "diarista_id", "label": "Diarista*", "type": "select", "span": "span 1", "ph": "Selecione o diarista",
             "options": [{"value": str(i), "label": n} for i, n in d_diaristas]},
            {"key": "data", "label": "Data*", "type": "date", "span": "span 1"},
            {"key": "posto", "label": "Posto*", "type": "select", "span": "span 1", "ph": "Posto",
             "options": [{"value": n, "label": n} for (n,) in d_postos]},
            {"key": "funcao", "label": "Função*", "type": "select", "span": "span 1", "ph": "Função",
             "options": [{"value": n, "label": n} for (n,) in d_funcoes]},
            {"key": "turno", "label": "Turno", "type": "select", "span": "span 1", "ph": "Turno (só p/ Agente de Portaria)",
             "options": [{"value": n, "label": n} for (n,) in d_turnos]},
            {"key": "observacao", "label": "Observação", "type": "textarea", "span": "span 2", "ph": "Opcional…"},
        ],
    }
    # Leitura: Diaristas
    drows = (await db.execute(text("SELECT nome, cpf, coalesce(pix,'—') FROM diaria_diaristas WHERE ativo ORDER BY nome LIMIT 200"))).fetchall()
    diaristas_scr = {"title": "Diaristas", "sub": f"{len(drows)} diaristas ativos", "cta": "Novo diarista",
        "type": "table", "searchHint": "Buscar diarista…", "grid": "2fr 1.2fr 1.6fr", "cols": ["Diarista", "CPF", "PIX"],
        "rows": [{"cells": [t(n, 600, "#0F1B3A", initials(n)), t(c or "—"), t(px)]} for n, c, px in drows]}
    # Leitura: Diárias (lançamentos recentes)
    lrows = (await db.execute(text(
        "SELECT l.data, coalesce(d.nome,'—'), l.funcao, l.posto, l.valor, l.status "
        "FROM diaria_lancamentos l LEFT JOIN diaria_diaristas d ON d.id=l.diarista_id "
        "ORDER BY l.data DESC, l.id DESC LIMIT 200"))).fetchall()
    diarias_scr = {"title": "Lançamento de diárias", "sub": f"{len(lrows)} lançamentos", "cta": "Lançar diária",
        "type": "table", "searchHint": "Buscar…", "grid": "1fr 1.8fr 1.4fr 1.2fr 1fr 0.9fr",
        "cols": ["Data", "Diarista", "Função", "Posto", "Valor", "Status"],
        "rows": [{"cells": [t(dt.strftime('%d/%m/%Y') if dt else '—'), t(nm, 600, "#0F1B3A"), t(fu or '—'),
                  t(po or '—'), t(brl(vl), 600), b("Lançado", "info") if (stt or '').lower() == 'lancado' else b(stt or '—', 'mut')]}
                 for dt, nm, fu, po, vl, stt in lrows]}

    cadastrar_diarista = {
        "title": "Cadastrar diarista", "sub": "Adicionar um diarista à lista (CPF e PIX obrigatórios — nunca inventar)",
        "cta": "Cadastrar", "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/diarista", "okMsg": "Diarista cadastrado"},
        "fields": [
            {"key": "nome", "label": "Nome completo*", "type": "text", "span": "span 2", "ph": "Nome do diarista"},
            {"key": "cpf", "label": "CPF*", "type": "text", "span": "span 1", "ph": "000.000.000-00"},
            {"key": "pix", "label": "Chave PIX*", "type": "text", "span": "span 1", "ph": "CPF, telefone, e-mail ou aleatória"},
            {"key": "telefone", "label": "Telefone", "type": "text", "span": "span 1", "ph": "(92) 90000-0000"},
            {"key": "email", "label": "E-mail", "type": "text", "span": "span 1", "ph": "email@exemplo.com"},
        ],
    }

    # Falta → substituto (fluxo ativo, curado). Registrar falta:
    turnos_hoje = (await db.execute(text(
        "SELECT s.id, coalesce(e.nome,'—'), coalesce(p.name,'—'), s.planned_start_time "
        "FROM shifts s LEFT JOIN employees e ON e.id=s.employee_id LEFT JOIN posts p ON p.id=s.post_id "
        "WHERE s.employee_id IS NOT NULL AND s.is_active "
        "AND s.shift_date BETWEEN (now() AT TIME ZONE 'America/Manaus')::date - 1 AND (now() AT TIME ZONE 'America/Manaus')::date "
        "AND s.status IN ('scheduled','in_progress') ORDER BY p.name, e.nome LIMIT 300"))).fetchall()

    def _tno(hhmm):
        try:
            return "Noturno" if hhmm and hhmm.hour >= 15 else "Diurno"
        except Exception:
            return ""
    registrar_falta_scr = {
        "title": "Registrar falta", "sub": "Marcar a falta de um turno de hoje/ontem (abre a substituição)",
        "cta": "Registrar falta", "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/falta", "okMsg": "Falta registrada"},
        "fields": [
            {"key": "shift_id", "label": "Turno faltoso*", "type": "select", "span": "span 2", "ph": "Selecione o turno de hoje/ontem",
             "options": [{"value": str(i), "label": f"{n} · {po} ({_tno(hh)})"} for i, n, po, hh in turnos_hoje]},
            {"key": "motivo", "label": "Motivo", "type": "select", "span": "span 1", "ph": "Motivo",
             "options": [{"value": v, "label": l} for v, l in [("falta", "Falta (sem aviso)"), ("atestado", "Atestado"), ("emergencia", "Emergência"), ("pessoal", "Pessoal"), ("outro", "Outro")]]},
            {"key": "detalhes", "label": "Detalhes", "type": "textarea", "span": "span 2", "ph": "Opcional…"},
        ],
    }
    # Escalar substituto (diarista) numa substituição aberta:
    subs_abertas = (await db.execute(text(
        "SELECT sub.id, coalesce(e.nome,'—'), coalesce(p.name,'—'), sub.substitution_date "
        "FROM substitutions sub LEFT JOIN employees e ON e.id=sub.original_employee_id LEFT JOIN posts p ON p.id=sub.post_id "
        "WHERE sub.is_active AND sub.status='pending' ORDER BY sub.substitution_date DESC LIMIT 100"))).fetchall()
    escalar_substituto_scr = {
        "title": "Escalar substituto (diarista)", "sub": "Cobrir uma falta aberta com um diarista (gera a diária automática)",
        "cta": "Escalar diarista", "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/substituir-diarista", "okMsg": "Diarista escalado"},
        "fields": [
            {"key": "substitution_id", "label": "Falta aberta*", "type": "select", "span": "span 2", "ph": "Selecione a substituição aberta",
             "options": [{"value": str(i), "label": f"{n} · {po} · {dt.strftime('%d/%m') if dt else '—'}"} for i, n, po, dt in subs_abertas]},
            {"key": "diarista_id", "label": "Diarista*", "type": "select", "span": "span 1", "ph": "Selecione o diarista",
             "options": [{"value": str(i), "label": n} for i, n in d_diaristas]},
            {"key": "funcao", "label": "Função", "type": "select", "span": "span 1", "ph": "Auto pelo cargo do faltoso",
             "options": [{"value": n, "label": n} for (n,) in d_funcoes]},
            {"key": "turno", "label": "Turno", "type": "select", "span": "span 1", "ph": "Auto pelo horário",
             "options": [{"value": n, "label": n} for (n,) in d_turnos]},
            {"key": "observacao", "label": "Observação", "type": "textarea", "span": "span 2", "ph": "Opcional…"},
        ],
    }

    # Comunicados — leitura real de communication_announcements (menu já existia vazio)
    crows = (await db.execute(text(
        "SELECT titulo, coalesce(tipo::text,'—'), coalesce(prioridade::text,'—'), data_publicacao, "
        "coalesce(total_destinatarios,0), coalesce(total_visualizacoes,0), coalesce(status::text,'—') "
        "FROM communication_announcements WHERE coalesce(is_active,true)=true ORDER BY data_publicacao DESC NULLS LAST LIMIT 200"))).fetchall()
    _prio_tone = {"alta": "bad", "urgente": "bad", "media": "warn", "normal": "info", "baixa": "mut"}
    comunicados_scr = {"title": "Comunicados", "sub": f"{len(crows)} comunicados", "cta": "Novo comunicado",
        "type": "table", "searchHint": "Buscar comunicado…", "grid": "2.2fr 1fr 0.9fr 1fr 0.9fr 0.7fr 0.9fr",
        "cols": ["Título", "Tipo", "Prioridade", "Publicação", "Destinatários", "Views", "Status"],
        "rows": [{"cells": [t(ti, 600, "#0F1B3A"), t((tp or '—').replace('_', ' ')), b((pr or '—').capitalize(), _prio_tone.get((pr or '').lower(), 'info')),
                  t(dp.strftime('%d/%m/%Y') if dp else '—'), t(str(dest)), t(str(views)), b((st or '—').capitalize(), 'ok' if (st or '').lower() == 'publicado' else 'mut')]}
                 for ti, tp, pr, dp, dest, views, st in crows]}

    return {
        "visao": visao, "postos": postos, "colaboradores": colaboradores_scr,
        "alocacoes": alocacoes, "ocorrencias": ocorrencias, "ocorrencia-rapida": ocorrencia_rapida,
        "resolver-ocorrencia": resolver_ocorrencia, "comentar-ocorrencia": comentar_ocorrencia,
        "lancar-diaria": lancar_diaria, "cadastrar-diarista": cadastrar_diarista,
        "registrar-falta": registrar_falta_scr, "escalar-substituto": escalar_substituto_scr,
        "diaristas": diaristas_scr, "diarias": diarias_scr, "comunicados": comunicados_scr,
    }


def brl(v: Any) -> str:
    try:
        v = float(v or 0)
    except Exception:
        v = 0.0
    s = f"{v:,.2f}"
    return "R$ " + s.replace(",", "§").replace(".", ",").replace("§", ".")


_ICF = {
    "money": "M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6",
    "chart": "M3 3v18h18M7 14l3-3 3 3 5-6",
    "users": "M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M9 3a4 4 0 1 1 0 8 4 4 0 0 1 0-8",
    "hand": "M8 13V5a2 2 0 1 1 4 0v6M12 11V4a2 2 0 1 1 4 0v7M16 11V6a2 2 0 1 1 4 0v8a7 7 0 0 1-7 7h-2a7 7 0 0 1-5-2l-3-3",
}

_PAY_TONE = {"pendente": ("Pendente", "warn"), "pago": ("Pago", "ok"), "paga": ("Paga", "ok"),
             "parcial": ("Parcial", "info"), "cancelada": ("Cancelada", "mut"), "agendada": ("Agendada", "info")}


async def _build_financeiro(db: AsyncSession) -> dict:
    out: dict = {}

    async def safe(key: str, coro):
        try:
            out[key] = await coro
        except Exception:
            await db.rollback()

    async def _dashboard():
        fat = await _scalar(db, "SELECT coalesce(sum(valor_servicos),0) FROM nfse_manaus_historico "
                                "WHERE data_emissao >= (SELECT max(data_emissao) FROM nfse_manaus_historico) - interval '12 months'")
        receber = await _scalar(db, "SELECT coalesce(sum(net_value),0) FROM receivable_accounts WHERE status IN ('pendente','parcial')")
        pagar = await _scalar(db, "SELECT coalesce(sum(net_value),0) FROM payable_accounts WHERE status IN ('pendente','parcial')")
        clientes = await _scalar(db, "SELECT count(*) FROM clients WHERE status='active'")
        pay_top = (await db.execute(text(
            "SELECT coalesce(nullif(supplier_name,''), fornecedor_nome, '—'), net_value FROM payable_accounts "
            "WHERE status IN ('pendente','parcial') ORDER BY net_value DESC LIMIT 6"))).fetchall()
        nfse_recent = (await db.execute(text(
            "SELECT tomador_nome, valor_servicos FROM nfse_manaus_historico ORDER BY data_emissao DESC LIMIT 6"))).fetchall()
        return {
            "title": "Dashboard", "sub": "Financeiro — dados reais", "cta": "Atualizar", "type": "dash", "panelGrid": "1fr 1fr",
            "kpis": [
                {"v": brl(fat), "l": "Faturamento (12m NFS-e)", "icon": _ICF["money"], "color": "#0F1B3A"},
                {"v": brl(receber), "l": "A receber (aberto)", "icon": _ICF["chart"], "color": "#16A34A"},
                {"v": brl(pagar), "l": "A pagar (aberto)", "icon": _ICF["money"], "color": "#C2410C"},
                {"v": str(clientes), "l": "Clientes ativos", "icon": _ICF["users"], "color": "#0F1B3A"},
            ],
            "panels": [
                {"title": "Contas a pagar em aberto", "rows": [{"left": n, "right": brl(v), **S["warn"]} for n, v in pay_top]
                 or [{"left": "Nada em aberto", "right": brl(0), **S["ok"]}]},
                {"title": "Últimas NFS-e emitidas", "rows": [{"left": nm or "—", "right": brl(v), **S["info"]} for nm, v in nfse_recent]
                 or [{"left": "Sem NFS-e", "right": "—", **S["mut"]}]},
            ],
        }

    async def _tbl(title, sub, cta, cols, grid, sql, rowfn, hint="Buscar…"):
        rows = (await db.execute(text(sql))).fetchall()
        return {"title": title, "sub": sub, "cta": cta, "type": "table", "searchHint": hint,
                "grid": grid, "cols": cols, "rows": [{"cells": rowfn(r)} for r in rows]}

    def paytone(st):
        return _PAY_TONE.get((st or "").lower(), ((st or "—"), "mut"))

    await safe("dashboard", _dashboard())
    await safe("contas-pagar", _tbl(
        "Contas a pagar", "A pagar em aberto e recentes", "Nova conta",
        ["Fornecedor", "Descrição", "Valor", "Vencimento", "Status"], "1.5fr 2fr 1fr 1fr 0.9fr",
        "SELECT coalesce(nullif(supplier_name,''),fornecedor_nome,'—'), coalesce(description,'—'), net_value, due_date, status "
        "FROM payable_accounts ORDER BY (status IN ('pendente','parcial')) DESC, due_date NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t(brl(r[2]), 600), t(r[3].strftime('%d/%m/%Y') if r[3] else '—'), b(*paytone(r[4]))]))
    await safe("contas-receber", _tbl(
        "Contas a receber", "A receber em aberto e recentes", "Nova cobrança",
        ["Cliente", "Descrição", "Valor", "Vencimento", "Status"], "1.5fr 2fr 1fr 1fr 0.9fr",
        "SELECT coalesce(customer_name,'—'), coalesce(description,'—'), net_value, due_date, status "
        "FROM receivable_accounts ORDER BY (status IN ('pendente','parcial')) DESC, due_date NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t(brl(r[2]), 600), t(r[3].strftime('%d/%m/%Y') if r[3] else '—'), b(*paytone(r[4]))]))
    await safe("clientes", _tbl(
        "Clientes", f"{await _scalar(db, 'SELECT count(*) FROM clients')} clientes", "Novo cliente",
        ["Cliente", "Segmento", "MRR", "Status"], "2fr 1.4fr 1fr 0.9fr",
        "SELECT name, coalesce(segment::text,'—'), coalesce(mrr,0), status::text FROM clients ORDER BY name LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0])), t(r[1]), t(brl(r[2]), 600), b("Ativo", "ok") if r[3] == "active" else b(r[3] or "—", "mut")]))
    await safe("fornecedores", _tbl(
        "Fornecedores", f"{await _scalar(db, 'SELECT count(*) FROM suppliers')} fornecedores", "Novo fornecedor",
        ["Fornecedor", "Categoria", "Cidade", "Status"], "2fr 1.4fr 1.2fr 0.9fr",
        "SELECT name, coalesce(category,'—'), coalesce(address_city,'—'), status FROM suppliers ORDER BY name LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t(r[2]), b("Ativo", "ok") if (r[3] or "").lower() in ("active", "ativo") else b(r[3] or "—", "mut")]))
    await safe("pagamentos-diaristas", _tbl(
        "Pagamentos diaristas", f"{await _scalar(db, 'SELECT count(*) FROM financial_pagamentos_diaristas')} lançamentos", "Novo pagamento",
        ["Beneficiário", "Valor", "Competência", "Status"], "2fr 1fr 1.2fr 0.9fr",
        "SELECT coalesce(beneficiario,'—'), valor, coalesce(competencia, to_char(data_referencia,'MM/YYYY')), status "
        "FROM financial_pagamentos_diaristas ORDER BY data_referencia DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0])), t(brl(r[1]), 600), t(r[2]), b(*paytone(r[3]))]))
    # Pagamentos Inter — VISIBILIDADE da fila (dinheiro que SAI = SEMPRE gate OTP humano; esta tela NÃO paga).
    _pay_tone = {"confirmado": "ok", "executado": "ok", "preparado": "warn", "aguardando_otp": "warn", "erro": "bad", "cancelado": "mut"}
    await safe("inter-pagamentos", _tbl(
        "Pagamentos Inter", f"{await _scalar(db, 'SELECT count(*) FROM inter_payments')} pagamentos — dinheiro que sai é SEMPRE com gate OTP humano (esta tela só mostra)", "—",
        ["Tipo", "Destinatário", "Valor", "Data", "Status", "OTP"], "1fr 2fr 1fr 1fr 1fr 0.7fr",
        "SELECT coalesce(payment_type,'—'), "
        "coalesce(destinatario->>'nome_recebedor', destinatario->>'condominio', destinatario->>'chave', left(destinatario->>'codigo_barras',18), '—'), "
        "valor, data_pagamento, coalesce(status::text,'—'), coalesce(approval_otp_used::text,'') "
        "FROM inter_payments ORDER BY created_at DESC NULLS LAST LIMIT 200",
        lambda r: [t((r[0] or '—').upper()), t(r[1], 600, "#0F1B3A"), t(brl(r[2]) if r[2] is not None else '—', 600),
                   t(_fmtdate(r[3])), b((r[4] or '—').capitalize(), _pay_tone.get((r[4] or '').lower(), "info")),
                   b("OTP ✓", "ok") if (r[5] and str(r[5]).lower() not in ('', 'false', 'nao', 'no', '0', 'none')) else b("—", "mut")]))
    # Registrar conta a pagar (FORM com ESCRITA real → POST /redesign/action/payable) — REGISTRO, não pagamento
    out["registrar-conta-pagar"] = {
        "title": "Registrar conta a pagar", "sub": "Lançar uma conta a pagar (registro — o pagamento é sempre com OTP)",
        "cta": "Registrar", "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/payable", "okMsg": "Conta a pagar registrada"},
        "fields": [
            {"key": "description", "label": "Descrição*", "type": "text", "span": "span 2", "ph": "Ex.: Energia — Posto Centro"},
            {"key": "supplier_name", "label": "Fornecedor", "type": "text", "span": "span 1", "ph": "Nome do fornecedor"},
            {"key": "valor", "label": "Valor (R$)*", "type": "text", "span": "span 1", "ph": "0,00"},
            {"key": "due_date", "label": "Vencimento*", "type": "date", "span": "span 1"},
            {"key": "notes", "label": "Observações", "type": "textarea", "span": "span 2", "ph": "Opcional…"},
        ],
    }
    # Registrar conta a receber (ESCRITA real → POST /redesign/action/receivable) — REGISTRO, não recebimento
    out["registrar-conta-receber"] = {
        "title": "Registrar conta a receber", "sub": "Lançar uma conta a receber (registro — não gera boleto/PIX)",
        "cta": "Registrar", "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/receivable", "okMsg": "Conta a receber registrada"},
        "fields": [
            {"key": "description", "label": "Descrição*", "type": "text", "span": "span 2", "ph": "Ex.: Vigilância — Condomínio Green"},
            {"key": "customer_name", "label": "Cliente/Sacado", "type": "text", "span": "span 1", "ph": "Nome do cliente"},
            {"key": "valor", "label": "Valor (R$)*", "type": "text", "span": "span 1", "ph": "0,00"},
            {"key": "due_date", "label": "Vencimento*", "type": "date", "span": "span 1"},
            {"key": "notes", "label": "Observações", "type": "textarea", "span": "span 2", "ph": "Opcional…"},
        ],
    }

    return out


async def _build_dp(db: AsyncSession) -> dict:
    out: dict = {}

    async def safe(key: str, coro):
        try:
            out[key] = await coro
        except Exception:
            await db.rollback()

    async def _tbl(title, sub, cta, cols, grid, sql, rowfn, hint="Buscar…"):
        rows = (await db.execute(text(sql))).fetchall()
        return {"title": title, "sub": sub, "cta": cta, "type": "table", "searchHint": hint,
                "grid": grid, "cols": cols, "rows": [{"cells": rowfn(r)} for r in rows]}

    ic_users = IC["users"]
    ic_money = _ICF["money"]
    ic_cal = IC["cal"]

    async def _visao():
        ativos = await _scalar(db, "SELECT count(*) FROM employees WHERE status='ativo'")
        comp = (await db.execute(text("SELECT reference_year, reference_month FROM hr_payslips ORDER BY reference_year DESC, reference_month DESC LIMIT 1"))).fetchone()
        liq = await _scalar(db, "SELECT coalesce(sum(net_salary),0) FROM hr_payslips WHERE (reference_year,reference_month)=(SELECT reference_year,reference_month FROM hr_payslips ORDER BY reference_year DESC, reference_month DESC LIMIT 1)")
        ferias_req = await _scalar(db, "SELECT count(*) FROM employee_vacation_requests")
        admissoes = await _scalar(db, "SELECT count(*) FROM admission_processes")
        comp_lbl = f"{comp[1]:02d}/{comp[0]}" if comp else "—"
        # quadro por status
        st_rows = (await db.execute(text("SELECT status, count(*) FROM employees GROUP BY status ORDER BY count(*) DESC"))).fetchall()
        st_tone = {"ativo": "ok", "afastado_inss": "warn", "suspenso": "warn", "inativo": "mut", "demitido": "bad"}
        quadro = [{"left": (s or "—").replace("_", " ").capitalize(), "right": str(c), **S[st_tone.get(s, "mut")]} for s, c in st_rows]
        # férias por status
        fr_rows = (await db.execute(text("SELECT status, count(*) FROM employee_vacation_requests GROUP BY status ORDER BY count(*) DESC"))).fetchall()
        fer = [{"left": (s or "—").replace("_", " ").capitalize(), "right": str(c), **S["info"]} for s, c in fr_rows] or [{"left": "Sem solicitações", "right": "0", **S["mut"]}]
        return {
            "title": "Visão geral", "sub": f"{ativos} colaboradores ativos · folha {comp_lbl}", "cta": "Nova admissão",
            "type": "dash", "panelGrid": "1fr 1fr",
            "kpis": [
                {"v": str(ativos), "l": "Colaboradores ativos", "icon": ic_users, "color": "#0F1B3A"},
                {"v": brl(liq), "l": f"Folha líquida ({comp_lbl})", "icon": ic_money, "color": "#0F1B3A"},
                {"v": str(ferias_req), "l": "Solicitações de férias", "icon": ic_cal, "color": "#0F1B3A"},
                {"v": str(admissoes), "l": "Admissões em processo", "icon": ic_users, "color": "#0F1B3A"},
            ],
            "panels": [
                {"title": "Quadro por situação", "rows": quadro},
                {"title": "Férias por status", "rows": fer},
            ],
        }

    st_emp = {"ativo": ("Ativo", "ok"), "afastado_inss": ("Afastado", "warn"), "suspenso": ("Suspenso", "warn"),
              "inativo": ("Inativo", "mut"), "demitido": ("Demitido", "bad")}
    n_ativos = await _scalar(db, "SELECT count(*) FROM employees WHERE status='ativo'")
    n_demit = await _scalar(db, "SELECT count(*) FROM employees WHERE status='demitido'")
    n_ferias = await _scalar(db, "SELECT count(*) FROM employee_vacation_requests")
    n_benef = await _scalar(db, "SELECT count(*) FROM employee_benefits")

    await safe("visao", _visao())
    await safe("funcionarios", _tbl(
        "Funcionários", f"{n_ativos} ativos", "Nova admissão",
        ["Colaborador", "Cargo", "Admissão", "Status"], "2fr 1.5fr 1fr 0.9fr",
        "SELECT nome, coalesce(cargo,'—'), data_admissao, status::text FROM employees WHERE status='ativo' ORDER BY nome LIMIT 300",
        lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0])), t(r[1]), t(r[2].strftime('%d/%m/%Y') if r[2] else '—'), b(*st_emp.get(r[3], (r[3] or '—', 'mut')))]))
    await safe("folha", _tbl(
        "Folha de pagamento", "Última competência", "Fechar folha",
        ["Colaborador", "Competência", "Salário base", "Líquido", "Status"], "2fr 1fr 1fr 1fr 0.9fr",
        "SELECT e.nome, p.reference_month, p.reference_year, p.base_salary, p.net_salary, p.status::text "
        "FROM hr_payslips p LEFT JOIN employees e ON e.id=p.employee_id "
        "WHERE (p.reference_year,p.reference_month)=(SELECT reference_year,reference_month FROM hr_payslips ORDER BY reference_year DESC, reference_month DESC LIMIT 1) "
        "ORDER BY e.nome LIMIT 300",
        lambda r: [t(r[0] or '—', 600, "#0F1B3A", initials(r[0] or '')), t(f"{(r[1] or 0):02d}/{r[2] or ''}"), t(brl(r[3])), t(brl(r[4]), 600), b("Processada", "ok") if (r[5] or '').lower() in ("processed", "processada", "fechada", "paga") else b(r[5] or "—", "info")]))
    # Folha · Rubricas — breakdown de proventos/descontos por rubrica (unnest do JSON earnings/deductions da última competência)
    await safe("folha-rubricas", _tbl(
        "Folha · Rubricas", "Proventos e descontos linha-a-linha (última competência)", "—",
        ["Colaborador", "Competência", "Rubrica", "Tipo", "Valor"], "1.8fr 1fr 2fr 0.9fr 1fr",
        "SELECT e.nome, p.reference_month, p.reference_year, elem->>'description', 'Provento', (elem->>'value')::numeric "
        "FROM hr_payslips p LEFT JOIN employees e ON e.id=p.employee_id "
        "CROSS JOIN LATERAL jsonb_array_elements(p.earnings::jsonb) elem "
        "WHERE p.earnings IS NOT NULL AND (p.reference_year,p.reference_month)=(SELECT reference_year,reference_month FROM hr_payslips ORDER BY reference_year DESC, reference_month DESC LIMIT 1) "
        "UNION ALL "
        "SELECT e.nome, p.reference_month, p.reference_year, elem->>'description', 'Desconto', (elem->>'value')::numeric "
        "FROM hr_payslips p LEFT JOIN employees e ON e.id=p.employee_id "
        "CROSS JOIN LATERAL jsonb_array_elements(p.deductions::jsonb) elem "
        "WHERE p.deductions IS NOT NULL AND (p.reference_year,p.reference_month)=(SELECT reference_year,reference_month FROM hr_payslips ORDER BY reference_year DESC, reference_month DESC LIMIT 1) "
        "ORDER BY 1, 5 DESC LIMIT 400",
        lambda r: [t(r[0] or '—', 600, "#0F1B3A", initials(r[0] or '')), t(f"{(r[1] or 0):02d}/{r[2] or ''}"), t(r[3] or '—'),
                   b(r[4], "ok" if r[4] == "Provento" else "bad"), t(brl(r[5]) if r[5] is not None else '—', 600)]))
    # Benefícios CCT — configuração legal dos benefícios obrigatórios/opcionais (cct_beneficios)
    await safe("beneficios-cct", _tbl(
        "Benefícios CCT", "Benefícios da convenção — valores e obrigatoriedade (CCT SINDECOMPRESTS)", "—",
        ["Benefício", "Valor mínimo", "Valor empresa", "Desconto máx.", "Obrigatoriedade"], "2fr 1.1fr 1.1fr 1.1fr 1.1fr",
        "SELECT tipo_beneficio, valor_minimo, valor_empresa, desconto_maximo_percentual, coalesce(obrigatorio,false) "
        "FROM cct_beneficios WHERE coalesce(is_active,true)=true ORDER BY obrigatorio DESC NULLS LAST, tipo_beneficio LIMIT 60",
        lambda r: [t((r[0] or '—').replace('_', ' ').capitalize(), 600, "#0F1B3A"), t(brl(r[1]) if r[1] is not None else '—'),
                   t(brl(r[2]) if r[2] is not None else '—'), t(f"{float(r[3]):.0f}%" if r[3] is not None else '—'),
                   b("Obrigatório", "bad") if r[4] else b("Opcional", "mut")]))
    await safe("ferias", _tbl(
        "Férias", f"{n_ferias} solicitações", "Solicitar férias",
        ["Colaborador", "Início", "Fim", "Dias", "Status"], "2fr 1fr 1fr 0.7fr 0.9fr",
        "SELECT e.nome, v.start_date, v.end_date, v.days_requested, v.status::text "
        "FROM employee_vacation_requests v LEFT JOIN employees e ON e.id=v.employee_id ORDER BY v.start_date DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0] or '—', 600, "#0F1B3A", initials(r[0] or '')), t(r[1].strftime('%d/%m/%Y') if r[1] else '—'), t(r[2].strftime('%d/%m/%Y') if r[2] else '—'), t(r[3] if r[3] is not None else '—'), b(r[4] or "—", "info")]))
    await safe("beneficios", _tbl(
        "Benefícios", f"{n_benef} benefícios", "Novo benefício",
        ["Colaborador", "Tipo", "Fornecedor", "Status"], "2fr 1.2fr 1.4fr 0.9fr",
        "SELECT e.nome, coalesce(b.type::text,'—'), coalesce(b.provider,'—'), b.status::text "
        "FROM employee_benefits b LEFT JOIN employees e ON e.id=b.employee_id ORDER BY e.nome LIMIT 200",
        lambda r: [t(r[0] or '—', 600, "#0F1B3A", initials(r[0] or '')), t(r[1]), t(r[2]), b("Ativo", "ok") if (r[3] or '').lower() in ("active", "ativo") else b(r[3] or "—", "mut")]))
    await safe("rescisao", _tbl(
        "Rescisão", f"{n_demit} desligados", "Nova rescisão",
        ["Colaborador", "Cargo", "Desligamento", "Motivo"], "2fr 1.4fr 1fr 1.4fr",
        "SELECT nome, coalesce(cargo,'—'), coalesce(data_demissao,data_desligamento), coalesce(motivo_desligamento,motivo_inatividade,'—') "
        "FROM employees WHERE status='demitido' ORDER BY coalesce(data_demissao,data_desligamento) DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0])), t(r[1]), t(r[2].strftime('%d/%m/%Y') if r[2] else '—'), t(r[3])]))
    # Registrar reembolso (ESCRITA real → POST /redesign/action/reembolso) — nasce em RASCUNHO, sem mover dinheiro
    _cat_lbl = {"transporte": "Transporte", "alimentacao": "Alimentação", "hospedagem": "Hospedagem",
                "material": "Material", "comunicacao": "Comunicação", "viagem": "Viagem",
                "estacionamento": "Estacionamento", "pedagio": "Pedágio", "saude": "Saúde",
                "cursos": "Cursos", "outros": "Outros"}
    out["registrar-reembolso"] = {
        "title": "Registrar reembolso", "sub": "Solicitar reembolso de despesa (rascunho — aprovação e pagamento seguem o fluxo)",
        "cta": "Registrar", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/reembolso", "okMsg": "Reembolso registrado"},
        "fields": [
            {"key": "title", "label": "Título/motivo*", "type": "text", "span": "span 2", "ph": "Ex.: Táxi para visita ao posto Centro"},
            {"key": "category_type", "label": "Categoria*", "type": "select", "span": "span 1", "ph": "Selecione a categoria",
             "options": [{"value": k, "label": v} for k, v in _cat_lbl.items()]},
            {"key": "valor", "label": "Valor (R$)*", "type": "text", "span": "span 1", "ph": "0,00"},
            {"key": "merchant", "label": "Estabelecimento", "type": "text", "span": "span 1", "ph": "Onde foi a despesa"},
            {"key": "expense_date", "label": "Data da despesa*", "type": "date", "span": "span 1"},
            {"key": "description", "label": "Detalhe da despesa", "type": "textarea", "span": "span 2", "ph": "Opcional…"},
        ],
    }
    # Solicitar férias (ESCRITA real → POST /redesign/action/vacation-request) — sobre SALDO REAL, nasce RASCUNHO
    try:
        fer_rows = (await db.execute(text(
            "SELECT p.employee_id, e.nome, sum(p.days_remaining) d FROM employee_vacation_periods p "
            "JOIN employees e ON e.id=p.employee_id "
            "WHERE p.is_expired=false AND p.is_fully_used=false "
            "GROUP BY 1,2 HAVING sum(p.days_remaining)>=5 ORDER BY e.nome LIMIT 400"))).fetchall()
        fer_opts = [{"value": str(eid), "label": f"{nm} · saldo {int(d)}d"} for eid, nm, d in fer_rows]
    except Exception:
        await db.rollback()
        fer_opts = []
    out["solicitar-ferias"] = {
        "title": "Solicitar férias", "sub": "Pedir férias sobre o saldo disponível (rascunho — segue para aprovação)",
        "cta": "Solicitar", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/vacation-request", "okMsg": "Férias solicitadas"},
        "fields": [
            {"key": "employee_id", "label": "Colaborador (com saldo)*", "type": "select", "span": "span 2", "ph": "Selecione o colaborador", "options": fer_opts},
            {"key": "vacation_type", "label": "Tipo", "type": "select", "span": "span 1", "ph": "Tipo",
             "options": [{"value": v, "label": l} for v, l in [
                 ("full", "Integral"), ("split", "Fracionada"), ("sell", "Com venda (abono)"), ("collective", "Coletiva")]]},
            {"key": "start_date", "label": "Início*", "type": "date", "span": "span 1"},
            {"key": "end_date", "label": "Fim*", "type": "date", "span": "span 1"},
            {"key": "employee_notes", "label": "Observações", "type": "textarea", "span": "span 2", "ph": "Opcional… (5 a 30 dias corridos)"},
        ],
    }
    # Calcular rescisão (calculadora CLT — cálculo PURO; não gera rescisão nem transmite/paga)
    try:
        _resc_rows = (await db.execute(text("SELECT id, nome FROM employees WHERE status='ativo' AND salario_base IS NOT NULL AND data_admissao IS NOT NULL ORDER BY nome LIMIT 400"))).fetchall()
        _resc_opts = [{"value": str(eid), "label": nm} for eid, nm in _resc_rows]
    except Exception:
        await db.rollback()
        _resc_opts = []
    out["calcular-rescisao"] = {
        "title": "Calcular rescisão (CLT)", "sub": "Calculadora de verbas rescisórias — cálculo, NÃO gera rescisão nem transmite/paga",
        "cta": "Calcular", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/rescisao-calc", "okMsg": "Rescisão calculada"},
        "fields": [
            {"key": "employee_id", "label": "Colaborador*", "type": "select", "span": "span 2", "ph": "Selecione o colaborador", "options": _resc_opts},
            {"key": "tipo_rescisao", "label": "Motivo*", "type": "select", "span": "span 1", "ph": "Motivo",
             "options": [{"value": v, "label": l} for v, l in [
                 ("sem_justa_causa", "Sem justa causa"), ("pedido_demissao", "Pedido de demissão"),
                 ("acordo", "Acordo (art. 484-A)"), ("justa_causa", "Justa causa")]]},
            {"key": "data_desligamento", "label": "Data de desligamento*", "type": "date", "span": "span 1"},
            {"key": "dias_trabalhados_mes", "label": "Dias trabalhados no mês", "type": "text", "span": "span 1", "ph": "0"},
            {"key": "ferias_vencidas_dias", "label": "Dias de férias vencidas", "type": "text", "span": "span 1", "ph": "0"},
            {"key": "saldo_fgts", "label": "Saldo FGTS (R$)", "type": "text", "span": "span 1", "ph": "0,00 (p/ multa 40%)"},
        ],
    }

    return out


def _helpers(db: AsyncSession):
    out: dict = {}

    async def safe(key: str, coro):
        try:
            out[key] = await coro
        except Exception:
            await db.rollback()

    async def tbl(title, sub, cta, cols, grid, sql, rowfn, hint="Buscar…"):
        rows = (await db.execute(text(sql))).fetchall()
        return {"title": title, "sub": sub, "cta": cta, "type": "table", "searchHint": hint,
                "grid": grid, "cols": cols, "rows": [{"cells": rowfn(r)} for r in rows]}

    return out, safe, tbl


def _fmtdate(d, fmt="%d/%m/%Y"):
    return d.strftime(fmt) if d else "—"


async def _build_crm(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)
    n_leads = await _scalar(db, "SELECT count(*) FROM leads")
    n_prop = await _scalar(db, "SELECT count(*) FROM proposals")
    n_contr = await _scalar(db, "SELECT count(*) FROM contracts")
    com_pend = await _scalar(db, "SELECT coalesce(sum(final_commission),0) FROM commissions WHERE status::text NOT IN ('paid','pago','cancelled','cancelada')")

    async def _dash():
        lead_st = (await db.execute(text("SELECT status::text, count(*) FROM leads GROUP BY status ORDER BY count(*) DESC"))).fetchall()
        prop_st = (await db.execute(text("SELECT status::text, count(*) FROM proposals GROUP BY status ORDER BY count(*) DESC"))).fetchall()
        return {"title": "Dashboard", "sub": "Comercial — dados reais", "cta": "Novo lead", "type": "dash", "panelGrid": "1fr 1fr",
                "kpis": [
                    {"v": str(n_leads), "l": "Leads", "icon": _ICF["users"], "color": "#0F1B3A"},
                    {"v": str(n_prop), "l": "Propostas", "icon": _ICF["hand"], "color": "#0F1B3A"},
                    {"v": str(n_contr), "l": "Contratos", "icon": IC["cal"], "color": "#0F1B3A"},
                    {"v": brl(com_pend), "l": "Comissões a pagar", "icon": _ICF["money"], "color": "#C2410C"},
                ],
                "panels": [
                    {"title": "Leads por status", "rows": [{"left": (s or "—").capitalize(), "right": str(c), **S["info"]} for s, c in lead_st] or [{"left": "Sem leads", "right": "0", **S["mut"]}]},
                    {"title": "Propostas por status", "rows": [{"left": (s or "—").capitalize(), "right": str(c), **S["warn"]} for s, c in prop_st] or [{"left": "Sem propostas", "right": "0", **S["mut"]}]},
                ]}

    await safe("dashboard", _dash())
    await safe("leads", tbl("Leads", f"{n_leads} leads", "Novo lead",
        ["Lead", "Empresa", "Valor estimado", "Status"], "2fr 1.6fr 1fr 0.9fr",
        "SELECT name, coalesce(company,'—'), coalesce(expected_value,0), status::text FROM leads ORDER BY created_at DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0])), t(r[1]), t(brl(r[2])), b("Qualificado", "ok") if r[3] == "qualified" else b("Novo" if r[3] == "new" else (r[3] or "—"), "info")]))
    await safe("propostas", tbl("Propostas", f"{n_prop} propostas", "Nova proposta",
        ["Número", "Cliente", "Título", "Valor", "Status"], "1fr 1.6fr 1.6fr 1fr 0.9fr",
        "SELECT coalesce(number,'—'), coalesce(client_name,'—'), coalesce(title,'—'), coalesce(total,subtotal,0), status::text FROM proposals ORDER BY created_at DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t(r[2]), t(brl(r[3]), 600), b(r[4] or "—", "info")]))
    await safe("contratos", tbl("Contratos", f"{n_contr} contratos", "Novo contrato",
        ["Contrato", "Cliente", "Mensal", "Total", "Status"], "1.2fr 1.6fr 1fr 1fr 0.9fr",
        "SELECT coalesce(ct.contract_number,'—'), coalesce(cl.name, ct.name, '—'), coalesce(ct.monthly_value,0), coalesce(ct.total_value,0), ct.status::text "
        "FROM contracts ct LEFT JOIN clients cl ON cl.id=ct.client_id ORDER BY ct.start_date DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t(brl(r[2])), t(brl(r[3]), 600), b("Ativo", "ok") if (r[4] or "").lower() in ("active", "ativo", "vigente") else b(r[4] or "—", "mut")]))
    await safe("comissoes", tbl("Comissões", f"{await _scalar(db, 'SELECT count(*) FROM commissions')} comissões", "Nova comissão",
        ["Referência", "Venda", "Comissão", "Status"], "1.4fr 1fr 1fr 0.9fr",
        "SELECT coalesce(reference_number,'—'), coalesce(sale_value,0), coalesce(final_commission,0), status::text FROM commissions ORDER BY created_at DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(brl(r[1])), t(brl(r[2]), 600), b("Paga", "ok") if (r[3] or "").lower() in ("paid", "pago") else b(r[3] or "—", "warn")]))
    await safe("contatos", tbl("Contatos", f"{await _scalar(db, 'SELECT count(*) FROM crm_contacts')} contatos", "Novo contato",
        ["Contato", "Cliente", "Cargo", "Telefone"], "1.6fr 1.6fr 1.2fr 1fr",
        "SELECT ct.name, coalesce(cl.name,'—'), coalesce(ct.role,'—'), coalesce(ct.phone, ct.whatsapp, '—') FROM crm_contacts ct LEFT JOIN clients cl ON cl.id=ct.client_id ORDER BY ct.name LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0])), t(r[1]), t(r[2]), t(r[3])]))
    # Precificação — Tabela de referência CCT 2026 por função (base legal da folha; era P0 no audit)
    await safe("precificacao", tbl(
        "Precificação — Tabela CCT 2026", f"{await _scalar(db, 'SELECT count(*) FROM crm_pricing_funcoes')} funções (piso + adicionais CCT SINDECOMPRESTS)", "—",
        ["Função", "Salário base", "Jornada", "Noturno", "Ronda", "Periculosidade", "Insalubridade"], "2fr 1.1fr 0.9fr 0.9fr 0.9fr 1fr 1fr",
        "SELECT nome, coalesce(salario_base,0), coalesce(jornada_dias::text,'—'), coalesce(noturno::text,'—'), "
        "coalesce(ronda::text,'—'), coalesce(periculosidade::text,'—'), coalesce(insalubridade::text,'—') "
        "FROM crm_pricing_funcoes WHERE coalesce(ativo,true)=true ORDER BY ordem NULLS LAST LIMIT 60",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(brl(r[1]), 600), t(f"{r[2]} dias" if r[2] not in (None, '—') else '—'),
                   *[b("Sim", "ok") if str(v).lower() in ("true", "t", "1", "sim") else t("—") for v in (r[3], r[4], r[5], r[6])]]))
    # Atividades — timeline real do CRM (crm_activities; menu já existia)
    await safe("atividades", tbl(
        "Atividades", f"{await _scalar(db, 'SELECT count(*) FROM crm_activities')} atividades", "Nova atividade",
        ["Assunto", "Tipo", "Cliente", "Agendada", "Concluída", "Resultado"], "2fr 1fr 1.6fr 1fr 1fr 1.2fr",
        "SELECT coalesce(a.subject,'—'), coalesce(a.type::text,'—'), coalesce(cl.name,'—'), a.scheduled_at, a.completed_at, coalesce(a.outcome,'—') "
        "FROM crm_activities a LEFT JOIN clients cl ON cl.id=a.client_id ORDER BY coalesce(a.scheduled_at, a.created_at) DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), b((r[1] or '—').replace('_', ' ').capitalize(), "info"), t(r[2]),
                   t(_fmtdate(r[3], '%d/%m/%Y %H:%M') if r[3] else '—'), b("Concluída", "ok") if r[4] else b("Aberta", "warn"), t(r[5])]))
    # Novo lead (FORM com ESCRITA real → POST /redesign/action/lead)
    out["novo-lead"] = {
        "title": "Novo lead", "sub": "Cadastrar um novo lead comercial", "cta": "Cadastrar lead",
        "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/lead", "okMsg": "Lead criado com sucesso"},
        "fields": [
            {"key": "name", "label": "Nome*", "type": "text", "span": "span 1", "ph": "Nome do contato"},
            {"key": "company", "label": "Empresa", "type": "text", "span": "span 1", "ph": "Empresa / condomínio"},
            {"key": "email", "label": "E-mail", "type": "text", "span": "span 1", "ph": "email@empresa.com"},
            {"key": "phone", "label": "Telefone", "type": "text", "span": "span 1", "ph": "(92) 90000-0000"},
            {"key": "source", "label": "Origem", "type": "select", "span": "span 1", "ph": "Origem",
             "options": [{"value": v, "label": l} for v, l in [
                 ("whatsapp", "WhatsApp"), ("referral", "Indicação"), ("website", "Site"),
                 ("social_media", "Redes sociais"), ("cold_call", "Prospecção ativa"),
                 ("event", "Evento"), ("partner", "Parceiro"), ("email_campaign", "E-mail mkt"), ("other", "Outro")]]},
            {"key": "expected_value", "label": "Valor estimado (R$)", "type": "text", "span": "span 1", "ph": "0,00"},
            {"key": "notes", "label": "Observações", "type": "textarea", "span": "span 2", "ph": "Notas sobre o lead…"},
        ],
    }
    # Nova tarefa (FORM com ESCRITA real → POST /redesign/action/task)
    cli_opts = (await db.execute(text("SELECT id, name FROM clients WHERE status='active' ORDER BY name LIMIT 100"))).fetchall()
    out["nova-tarefa"] = {
        "title": "Nova tarefa", "sub": "Criar um follow-up / lembrete comercial", "cta": "Criar tarefa",
        "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/task", "okMsg": "Tarefa criada com sucesso"},
        "fields": [
            {"key": "title", "label": "Título*", "type": "text", "span": "span 2", "ph": "Ex.: Ligar para o cliente sobre proposta"},
            {"key": "priority", "label": "Prioridade", "type": "select", "span": "span 1", "ph": "Prioridade",
             "options": [{"value": v, "label": l} for v, l in [("low", "Baixa"), ("medium", "Média"), ("high", "Alta")]]},
            {"key": "due_date", "label": "Vencimento", "type": "date", "span": "span 1"},
            {"key": "client_id", "label": "Cliente (opcional)", "type": "select", "span": "span 2", "ph": "Vincular a um cliente",
             "options": [{"value": str(i), "label": n} for i, n in cli_opts]},
            {"key": "description", "label": "Descrição", "type": "textarea", "span": "span 2", "ph": "Detalhes da tarefa…"},
        ],
    }
    # Oportunidades (LEITURA real) + Mover no funil (ESCRITA)
    _STG = {"qualification": ("Qualificação", "mut"), "needs_analysis": ("Análise", "info"),
            "proposal": ("Proposta", "info"), "negotiation": ("Negociação", "warn"),
            "closed_won": ("Ganho", "ok"), "closed_lost": ("Perdido", "bad")}
    opp_rows = (await db.execute(text(
        "SELECT id, title, coalesce(company_name, contact_name, '—'), coalesce(value,0), stage::text "
        "FROM opportunities ORDER BY updated_at DESC NULLS LAST LIMIT 200"))).fetchall()
    await safe("oportunidades", tbl(
        "Oportunidades", f"{len(opp_rows)} no funil", "Mover no funil",
        ["Oportunidade", "Cliente", "Valor", "Estágio"], "2.4fr 1.4fr 1fr 1fr",
        "SELECT id, title, coalesce(company_name, contact_name, '—'), coalesce(value,0), stage::text "
        "FROM opportunities ORDER BY updated_at DESC NULLS LAST LIMIT 200",
        lambda r: [t((r[1] or '—')[:70], 600, "#0F1B3A"), t(r[2]), t(brl(r[3]), 600),
                   b(*_STG.get(r[4], (r[4] or '—', 'mut')))]))
    out["mover-oportunidade"] = {
        "title": "Mover no funil", "sub": "Atualizar o estágio de uma oportunidade", "cta": "Mover",
        "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/opportunity-stage", "okMsg": "Oportunidade movida"},
        "fields": [
            {"key": "opportunity_id", "label": "Oportunidade*", "type": "select", "span": "span 2", "ph": "Selecione a oportunidade",
             "options": [{"value": str(i), "label": f"{(ti or '—')[:55]} · {_STG.get(st,(st,''))[0]}"} for i, ti, _cn, _v, st in opp_rows]},
            {"key": "stage", "label": "Novo estágio*", "type": "select", "span": "span 1", "ph": "Estágio",
             "options": [{"value": v, "label": l} for v, (l, _tone) in _STG.items()]},
            {"key": "notes", "label": "Observação", "type": "textarea", "span": "span 2", "ph": "Motivo/nota da mudança (opcional)…"},
        ],
    }
    # Nova proposta (FORM com ESCRITA real → POST /redesign/action/proposal)
    out["nova-proposta"] = {
        "title": "Nova proposta", "sub": "Criar uma proposta comercial", "cta": "Criar proposta",
        "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/proposal", "okMsg": "Proposta criada com sucesso"},
        "fields": [
            {"key": "client_id", "label": "Cliente*", "type": "select", "span": "span 2", "ph": "Selecione o cliente",
             "options": [{"value": str(i), "label": n} for i, n in cli_opts]},
            {"key": "title", "label": "Título*", "type": "text", "span": "span 2", "ph": "Ex.: Proposta de portaria — Cond. X"},
            {"key": "item_name", "label": "Serviço/Item", "type": "text", "span": "span 1", "ph": "Ex.: Portaria 24h"},
            {"key": "valor", "label": "Valor (R$)", "type": "text", "span": "span 1", "ph": "0,00"},
            {"key": "description", "label": "Descrição", "type": "textarea", "span": "span 2", "ph": "Detalhes da proposta…"},
        ],
    }
    # Anotar cliente (FORM com ESCRITA real → POST /redesign/action/client-note)
    out["anotar-cliente"] = {
        "title": "Anotar cliente", "sub": "Registrar uma anotação na ficha do cliente", "cta": "Salvar anotação",
        "type": "form", "submit": {"endpoint": "/api/v1/redesign/action/client-note", "okMsg": "Anotação salva"},
        "fields": [
            {"key": "client_id", "label": "Cliente*", "type": "select", "span": "span 2", "ph": "Selecione o cliente",
             "options": [{"value": str(i), "label": n} for i, n in cli_opts]},
            {"key": "nota", "label": "Anotação*", "type": "textarea", "span": "span 2", "ph": "Escreva a anotação sobre o cliente…"},
        ],
    }
    return out


async def _build_fiscal(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)
    n_nfse = await _scalar(db, "SELECT count(*) FROM nfse_manaus_historico")
    fat12 = await _scalar(db, "SELECT coalesce(sum(valor_servicos),0) FROM nfse_manaus_historico WHERE data_emissao >= (SELECT max(data_emissao) FROM nfse_manaus_historico) - interval '12 months'")
    obr_pend = await _scalar(db, "SELECT count(*) FROM fiscal_obligations WHERE status::text NOT IN ('pago','paga','concluido','concluida')")
    obr_val = await _scalar(db, "SELECT coalesce(sum(valor_devido),0) FROM fiscal_obligations WHERE status::text NOT IN ('pago','paga','concluido','concluida')")

    async def _painel():
        obr = (await db.execute(text("SELECT nome, valor_devido, data_vencimento, status::text FROM fiscal_obligations ORDER BY data_vencimento NULLS LAST LIMIT 6"))).fetchall()
        nf = (await db.execute(text("SELECT tomador_nome, valor_servicos FROM nfse_manaus_historico ORDER BY data_emissao DESC LIMIT 6"))).fetchall()
        return {"title": "Painel fiscal", "sub": "Fiscal & Contábil — dados reais", "cta": "Atualizar", "type": "dash", "panelGrid": "1fr 1fr",
                "kpis": [
                    {"v": str(n_nfse), "l": "NFS-e (histórico)", "icon": _ICF["chart"], "color": "#0F1B3A"},
                    {"v": brl(fat12), "l": "Faturamento (12m)", "icon": _ICF["money"], "color": "#0F1B3A"},
                    {"v": str(obr_pend), "l": "Obrigações em aberto", "icon": IC["alert"], "color": "#C2410C" if obr_pend else "#0F1B3A"},
                    {"v": brl(obr_val), "l": "Valor em aberto", "icon": _ICF["money"], "color": "#0F1B3A"},
                ],
                "panels": [
                    {"title": "Obrigações", "rows": [{"left": f"{n or '—'}", "right": brl(v), **(S["bad"] if False else S["warn"])} for n, v, dv, st in obr] or [{"left": "Sem obrigações", "right": brl(0), **S["ok"]}]},
                    {"title": "Últimas NFS-e", "rows": [{"left": nm or "—", "right": brl(v), **S["info"]} for nm, v in nf] or [{"left": "Sem NFS-e", "right": "—", **S["mut"]}]},
                ]}

    await safe("painel", _painel())
    await safe("nfse", tbl("NFS-e", f"{n_nfse} notas (histórico)", "Emitir NFS-e",
        ["Número", "Tomador", "Valor", "Emissão", "Status"], "1fr 2fr 1fr 1fr 0.9fr",
        "SELECT coalesce(numero::text,'—'), coalesce(tomador_nome,'—'), coalesce(valor_servicos,0), data_emissao, coalesce(status::text,'—') FROM nfse_manaus_historico ORDER BY data_emissao DESC LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t(brl(r[2]), 600), t(_fmtdate(r[3])), b("Autorizada", "ok") if "autoriz" in (r[4] or "").lower() or (r[4] or "").lower() in ("normal", "emitida") else b(r[4] or "—", "info")]))
    await safe("guias", tbl("Guias / Obrigações", f"{await _scalar(db, 'SELECT count(*) FROM fiscal_obligations')} obrigações", "Nova guia",
        ["Obrigação", "Competência", "Valor", "Vencimento", "Status"], "1.8fr 1fr 1fr 1fr 0.9fr",
        "SELECT coalesce(nome,'—'), coalesce(to_char(make_date(competencia_ano, greatest(competencia_mes,1), 1),'MM/YYYY'),'—'), coalesce(valor_devido,0), data_vencimento, status::text "
        "FROM fiscal_obligations ORDER BY data_vencimento DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t(brl(r[2]), 600), t(_fmtdate(r[3])), b("Pago", "ok") if (r[4] or "").lower() in ("pago", "paga") else b(r[4] or "Pendente", "warn")]))

    # DCTFWeb / EFD-Reinf — status de obrigação (compliance legal, leitura de fiscal_obligations por tipo)
    def _obrig(tipo, label):
        return tbl(label, f"{label} — obrigações, prazos e status (fiscal_obligations)", "—",
            ["Obrigação", "Competência", "Valor devido", "Valor pago", "Vencimento", "Status"], "1.6fr 1fr 1fr 1fr 1fr 0.9fr",
            "SELECT coalesce(nome, tipo, '—'), coalesce(to_char(make_date(competencia_ano, greatest(competencia_mes,1), 1),'MM/YYYY'),'—'), "
            "coalesce(valor_devido,0), coalesce(valor_pago,0), data_vencimento, coalesce(status::text,'—') "
            f"FROM fiscal_obligations WHERE tipo='{tipo}' ORDER BY data_vencimento DESC NULLS LAST LIMIT 200",
            lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t(brl(r[2]), 600), t(brl(r[3])), t(_fmtdate(r[4])),
                       b("Cumprida", "ok") if (r[5] or "").lower() in ("cumprida", "pago", "paga") else b((r[5] or "Pendente").capitalize(), "warn")])
    await safe("dctfweb", _obrig("DCTFWEB", "DCTFWeb"))
    await safe("reinf", _obrig("EFD_REINF", "EFD-Reinf"))
    return out


async def _build_gp(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)
    n_ged = await _scalar(db, "SELECT count(*) FROM ged_kit_documents")
    n_aso = await _scalar(db, "SELECT count(*) FROM gp_asos")
    n_epi = await _scalar(db, "SELECT count(*) FROM gp_epi_deliveries")
    n_punch = await _scalar(db, "SELECT count(*) FROM gp_clock_punches")

    async def _visao():
        aso_st = (await db.execute(text("SELECT status::text, count(*) FROM gp_asos GROUP BY status ORDER BY count(*) DESC LIMIT 6"))).fetchall()
        ged_ty = (await db.execute(text("SELECT document_type::text, count(*) FROM ged_kit_documents GROUP BY document_type ORDER BY count(*) DESC LIMIT 6"))).fetchall()
        return {"title": "Visão geral", "sub": "Gestão de Pessoas — dados reais", "cta": "Nova ação", "type": "dash", "panelGrid": "1fr 1fr",
                "kpis": [
                    {"v": f"{n_ged:,}".replace(",", "."), "l": "Documentos GED", "icon": IC["cal"], "color": "#0F1B3A"},
                    {"v": str(n_aso), "l": "ASOs", "icon": _ICF["hand"], "color": "#0F1B3A"},
                    {"v": str(n_epi), "l": "EPIs entregues", "icon": IC["shield"], "color": "#0F1B3A"},
                    {"v": f"{n_punch:,}".replace(",", "."), "l": "Batidas de ponto", "icon": IC["cal"], "color": "#0F1B3A"},
                ],
                "panels": [
                    {"title": "ASO por status", "rows": [{"left": (s or "—").capitalize(), "right": str(c), **S["info"]} for s, c in aso_st] or [{"left": "Sem ASO", "right": "0", **S["mut"]}]},
                    {"title": "GED por tipo", "rows": [{"left": (s or "—").replace("_", " ").capitalize(), "right": str(c), **S["ok"]} for s, c in ged_ty] or [{"left": "Sem documentos", "right": "0", **S["mut"]}]},
                ]}

    await safe("visao", _visao())
    await safe("ged", tbl("GED — Documentos", f"{n_ged} documentos", "Enviar documento",
        ["Documento", "Tipo", "Colaborador", "Assinado"], "2fr 1.4fr 1.6fr 0.9fr",
        "SELECT coalesce(g.document_name,'—'), coalesce(g.document_type::text,'—'), coalesce(e.nome,'—'), g.is_signed "
        "FROM ged_kit_documents g LEFT JOIN employees e ON e.id=g.employee_id ORDER BY g.created_at DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t((r[1] or "—").replace("_", " ")), t(r[2]), b("Assinado", "ok") if r[3] else b("Pendente", "warn")]))
    await safe("ponto", tbl("Ponto eletrônico", f"{n_punch} batidas", "Registrar",
        ["Colaborador", "Data/Hora", "Tipo", "Status"], "2fr 1.2fr 1fr 0.9fr",
        "SELECT coalesce(e.nome,'—'), to_char(p.punch_timestamp AT TIME ZONE 'America/Manaus','DD/MM HH24:MI'), coalesce(p.punch_type::text,'—'), coalesce(p.status::text,'—') "
        "FROM gp_clock_punches p LEFT JOIN employees e ON e.id=p.employee_id ORDER BY p.punch_timestamp DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0])), t(r[1]), t((r[2] or "—").replace("_", " ")), b("OK", "ok") if (r[3] or "").lower() in ("valid", "aprovado", "ok", "approved") else b(r[3] or "—", "info")]))
    # Fechamento de ponto / espelho (Portaria 671) — leitura real de gp_monthly_closings (controle legal)
    await safe("ponto-espelho", tbl(
        "Fechamento de ponto (Portaria 671)", f"{await _scalar(db, 'SELECT count(*) FROM gp_monthly_closings')} fechamentos", "Fechar mês",
        ["Colaborador", "Competência", "Dias", "Horas trab.", "HE 50%", "Faltas", "Atraso (min)", "Status"], "1.8fr 1fr 0.6fr 1fr 0.8fr 0.7fr 0.9fr 0.9fr",
        "SELECT coalesce(e.nome, m.employee_id, '—'), m.month, m.year, coalesce(m.total_dias_trabalhados,0), "
        "coalesce(m.total_horas_trabalhadas,0), coalesce(m.total_horas_extras_50,0), coalesce(m.total_faltas,0), "
        "coalesce(m.total_atrasos_minutos,0), coalesce(m.fechado,false) "
        "FROM gp_monthly_closings m LEFT JOIN employees e ON e.id::text=m.employee_id::text "
        "ORDER BY m.year DESC NULLS LAST, m.month DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0])), t(f"{r[1]:02d}/{r[2]}" if r[1] else "—"), t(str(r[3])),
                   t(f"{float(r[4]):.0f}h" if r[4] is not None else "—"), t(f"{float(r[5]):.0f}h" if r[5] else "—"),
                   b(str(r[6]), "bad" if (r[6] or 0) > 0 else "ok"), t(str(r[7])),
                   b("Fechado", "ok") if r[8] else b("Aberto", "warn")]))
    await safe("saude-exames", tbl("Saúde · Exames (ASO)", f"{n_aso} ASOs", "Agendar exame",
        ["Colaborador", "Tipo", "Validade", "Situação"], "2fr 1.2fr 1fr 0.9fr",
        "SELECT coalesce(e.nome,'—'), coalesce(a.tipo::text,'—'), a.data_validade, a.apto "
        "FROM gp_asos a LEFT JOIN employees e ON e.id=a.employee_id ORDER BY a.data_validade DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0])), t((r[1] or "—").replace("_", " ")), t(_fmtdate(r[2])), b("Apto", "ok") if r[3] else b("Inapto/Pendente", "warn")]))
    await safe("sst", tbl("SST — Entrega de EPI", f"{n_epi} entregas", "Registrar entrega",
        ["Colaborador", "EPI", "CA", "Entrega"], "2fr 1.4fr 0.9fr 1fr",
        "SELECT coalesce(e.nome,'—'), coalesce(d.epi_nome,'—'), coalesce(d.epi_ca,'—'), d.data_entrega "
        "FROM gp_epi_deliveries d LEFT JOIN employees e ON e.id=d.employee_id ORDER BY d.data_entrega DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0])), t(r[1]), t(r[2]), t(_fmtdate(r[3]))]))
    # Registrar entrega de EPI (ESCRITA real → POST /redesign/action/epi-delivery) — log operacional NR-6
    try:
        emp_rows = (await db.execute(text(
            "SELECT id, nome FROM employees WHERE status='ativo' ORDER BY nome LIMIT 400"))).fetchall()
        emp_opts = [{"value": str(eid), "label": nm} for eid, nm in emp_rows]
    except Exception:
        await db.rollback()
        emp_opts = []
    out["registrar-entrega-epi"] = {
        "title": "Registrar entrega de EPI", "sub": "Registrar a entrega de um EPI ao colaborador (NR-6)",
        "cta": "Registrar entrega", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/epi-delivery", "okMsg": "Entrega de EPI registrada"},
        "fields": [
            {"key": "employee_id", "label": "Colaborador*", "type": "select", "span": "span 2", "ph": "Selecione o colaborador", "options": emp_opts},
            {"key": "epi_nome", "label": "EPI*", "type": "text", "span": "span 1", "ph": "Ex.: Colete Refletivo"},
            {"key": "epi_ca", "label": "CA", "type": "text", "span": "span 1", "ph": "Ex.: CA-40123"},
            {"key": "quantidade", "label": "Quantidade", "type": "text", "span": "span 1", "ph": "1"},
            {"key": "nr", "label": "Norma (NR)", "type": "text", "span": "span 1", "ph": "NR-6"},
            {"key": "data_entrega", "label": "Data de entrega*", "type": "date", "span": "span 1"},
            {"key": "data_validade", "label": "Validade", "type": "date", "span": "span 1"},
        ],
    }
    # Registrar justificativa de ponto (ESCRITA real → POST /redesign/action/justificativa-ponto) — nasce PENDENTE
    out["registrar-justificativa-ponto"] = {
        "title": "Registrar justificativa de ponto", "sub": "Justificar atraso/falta (pendente — o gestor revisa depois)",
        "cta": "Registrar", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/justificativa-ponto", "okMsg": "Justificativa registrada"},
        "fields": [
            {"key": "employee_id", "label": "Colaborador*", "type": "select", "span": "span 2", "ph": "Selecione o colaborador", "options": emp_opts},
            {"key": "justification_type", "label": "Tipo*", "type": "select", "span": "span 1", "ph": "Atraso ou falta",
             "options": [{"value": "atraso", "label": "Atraso"}, {"value": "falta", "label": "Falta"}]},
            {"key": "category", "label": "Motivo*", "type": "select", "span": "span 1", "ph": "Selecione o motivo",
             "options": [{"value": v, "label": l} for v, l in [
                 ("transito", "Trânsito"), ("saude", "Saúde"), ("familiar", "Familiar"),
                 ("transporte_publico", "Transporte público"), ("acidente", "Acidente"), ("outro", "Outro")]]},
            {"key": "reason", "label": "Justificativa*", "type": "textarea", "span": "span 2", "ph": "Descreva o ocorrido (mínimo 5 caracteres)"},
        ],
    }
    return out


async def _candidatos_screen(db, tbl):
    n = await _scalar(db, "SELECT count(*) FROM candidates")
    return await tbl("Candidatos", f"{n} candidatos", "Novo candidato",
        ["Candidato", "Cargo pretendido", "Cidade", "Empresa atual"], "1.8fr 1.4fr 1fr 1.4fr",
        "SELECT name, coalesce(current_position,'—'), coalesce(nullif(concat_ws('/', city, state),''),'—'), coalesce(current_company,'—') FROM candidates ORDER BY name LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0])), t(r[1]), t(r[2]), t(r[3])])


async def _entrevistas_screen(db):
    rows = (await db.execute(text(
        "SELECT interview_type::text, format::text, scheduled_at, status::text FROM interviews ORDER BY scheduled_at DESC NULLS LAST LIMIT 100"))).fetchall()
    tone = {"scheduled": "info", "completed": "ok", "cancelled": "mut", "agendada": "info", "realizada": "ok"}
    items = [{"title": (it or "Entrevista").replace("_", " ").capitalize(),
              "meta": f"{(fmt or '—')} · {_fmtdate(sa, '%d/%m/%Y %H:%M')}",
              "dot": "#2563EB", "badge": (st or "—").capitalize(), **S[tone.get((st or "").lower(), "info")]}
             for it, fmt, sa, st in rows]
    if not items:
        items = [{"title": "Sem entrevistas", "meta": "aguardando dado", "dot": "#16A34A", "badge": "OK", **S["ok"]}]
    return {"title": "Entrevistas", "sub": "Agenda de entrevistas", "cta": "Agendar", "type": "list", "items": items}


async def _build_recrutamento(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)
    n_cand = await _scalar(db, "SELECT count(*) FROM candidates")
    n_int = await _scalar(db, "SELECT count(*) FROM interviews")
    n_adm = await _scalar(db, "SELECT count(*) FROM admission_processes")
    n_vagas = await _scalar(db, "SELECT count(*) FROM job_positions")
    n_vagas_abertas = await _scalar(db, "SELECT count(*) FROM job_positions WHERE status='aberta'")

    async def _visao():
        return {"title": "Visão geral", "sub": "Recrutamento & Seleção — dados reais", "cta": "Nova vaga", "type": "dash", "panelGrid": "1fr 1fr",
                "kpis": [
                    {"v": str(n_cand), "l": "Candidatos", "icon": IC["users"], "color": "#0F1B3A"},
                    {"v": str(n_int), "l": "Entrevistas", "icon": IC["cal"], "color": "#0F1B3A"},
                    {"v": str(n_adm), "l": "Admissões em processo", "icon": _ICF["hand"], "color": "#0F1B3A"},
                    {"v": str(n_vagas_abertas), "l": "Vagas abertas", "icon": IC["shield"], "color": "#0F1B3A"},
                ],
                "panels": [
                    {"title": "Candidatos por cidade", "rows": [{"left": (c or "—"), "right": str(n), **S["info"]} for c, n in (await db.execute(text("SELECT coalesce(city,'—'), count(*) FROM candidates GROUP BY city ORDER BY count(*) DESC LIMIT 6"))).fetchall()] or [{"left": "Sem candidatos", "right": "0", **S["mut"]}]},
                    {"title": "Entrevistas por status", "rows": [{"left": (s or "—").capitalize(), "right": str(n), **S["warn"]} for s, n in (await db.execute(text("SELECT status::text, count(*) FROM interviews GROUP BY status ORDER BY count(*) DESC"))).fetchall()] or [{"left": "Sem entrevistas", "right": "0", **S["mut"]}]},
                ]}

    _vaga_tone = {"aberta": "ok", "rascunho": "mut", "pausada": "warn", "encerrada": "bad", "preenchida": "info"}
    await safe("visao", _visao())
    await safe("vagas", tbl(
        "Vagas", f"{n_vagas} vagas", "Abrir vaga",
        ["Vaga", "Departamento", "Local", "Nº", "Status"], "2fr 1.4fr 1.4fr 0.6fr 0.9fr",
        "SELECT title, coalesce(department,'—'), coalesce(nullif(concat_ws('/', city, state),''),'—'), coalesce(vacancies,1), coalesce(status,'—') "
        "FROM job_positions ORDER BY created_at DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t(r[2]), t(str(r[3])), b(*(( (r[4] or '—').capitalize()), _vaga_tone.get((r[4] or '').lower(), "mut")))]))
    await safe("candidatos", _candidatos_screen(db, tbl))
    await safe("entrevistas", _entrevistas_screen(db))
    # Abrir vaga (ESCRITA real → POST /redesign/action/job-position) — nasce em RASCUNHO
    out["abrir-vaga"] = {
        "title": "Abrir vaga", "sub": "Cadastrar uma nova vaga (rascunho — publique quando quiser divulgar)",
        "cta": "Abrir vaga", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/job-position", "okMsg": "Vaga aberta"},
        "fields": [
            {"key": "title", "label": "Título da vaga*", "type": "text", "span": "span 2", "ph": "Ex.: Agente de Portaria 12x36"},
            {"key": "department", "label": "Departamento", "type": "text", "span": "span 1", "ph": "Ex.: Operacional"},
            {"key": "position_type", "label": "Contratação", "type": "select", "span": "span 1", "ph": "Tipo",
             "options": [{"value": v, "label": l} for v, l in [
                 ("clt", "CLT"), ("pj", "PJ"), ("temporario", "Temporário"), ("estagio", "Estágio"), ("aprendiz", "Aprendiz")]]},
            {"key": "work_model", "label": "Modelo", "type": "select", "span": "span 1", "ph": "Modelo",
             "options": [{"value": v, "label": l} for v, l in [
                 ("presencial", "Presencial"), ("hibrido", "Híbrido"), ("remoto", "Remoto")]]},
            {"key": "vacancies", "label": "Nº de vagas", "type": "text", "span": "span 1", "ph": "1"},
            {"key": "city", "label": "Cidade", "type": "text", "span": "span 1", "ph": "Ex.: Manaus"},
            {"key": "state", "label": "UF", "type": "text", "span": "span 1", "ph": "AM"},
            {"key": "salary_min", "label": "Salário mín. (R$)", "type": "text", "span": "span 1", "ph": "0,00"},
            {"key": "salary_max", "label": "Salário máx. (R$)", "type": "text", "span": "span 1", "ph": "0,00"},
            {"key": "requirements", "label": "Requisitos", "type": "textarea", "span": "span 2", "ph": "Opcional…"},
            {"key": "description", "label": "Descrição", "type": "textarea", "span": "span 2", "ph": "Opcional…"},
        ],
    }
    return out


async def _build_rh(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)
    ativos = await _scalar(db, "SELECT count(*) FROM employees WHERE status='ativo'")
    n_cand = await _scalar(db, "SELECT count(*) FROM candidates")
    n_int = await _scalar(db, "SELECT count(*) FROM interviews")
    n_cert = await _scalar(db, "SELECT count(*) FROM hr_certifications")

    async def _dash():
        st_rows = (await db.execute(text("SELECT status::text, count(*) FROM employees GROUP BY status ORDER BY count(*) DESC"))).fetchall()
        st_tone = {"ativo": "ok", "afastado_inss": "warn", "suspenso": "warn", "inativo": "mut", "demitido": "bad"}
        return {"title": "RH", "sub": "Recursos Humanos — dados reais", "cta": "Nova ação", "type": "dash", "panelGrid": "1fr 1fr",
                "kpis": [
                    {"v": str(ativos), "l": "Colaboradores ativos", "icon": IC["users"], "color": "#0F1B3A"},
                    {"v": str(n_cand), "l": "Candidatos", "icon": _ICF["hand"], "color": "#0F1B3A"},
                    {"v": str(n_int), "l": "Entrevistas", "icon": IC["cal"], "color": "#0F1B3A"},
                    {"v": str(n_cert), "l": "Certificações", "icon": IC["shield"], "color": "#0F1B3A"},
                ],
                "panels": [
                    {"title": "Quadro por situação", "rows": [{"left": (s or "—").replace("_", " ").capitalize(), "right": str(c), **S[st_tone.get(s, "mut")]} for s, c in st_rows]},
                    {"title": "Certificações (competência)", "rows": [{"left": (c or "—"), "right": str(n), **S["info"]} for c, n in (await db.execute(text("SELECT competencia::text, count(*) FROM hr_certifications GROUP BY competencia ORDER BY competencia DESC LIMIT 6"))).fetchall()] or [{"left": "Sem certificações", "right": "0", **S["mut"]}]},
                ]}

    await safe("dashboard", _dash())
    await safe("candidatos", _candidatos_screen(db, tbl))
    await safe("entrevistas", _entrevistas_screen(db))
    await safe("certificados", tbl("Certificados", f"{n_cert} certificações", "Nova certificação",
        ["Colaborador", "Competência", "Tipo", "Status"], "1.8fr 1fr 1.2fr 0.9fr",
        "SELECT coalesce(e.nome,'—'), coalesce(c.competencia::text,'—'), coalesce(c.tipo_calculo::text,'—'), c.status::text "
        "FROM hr_certifications c LEFT JOIN employees e ON e.id=c.employee_id ORDER BY c.competencia DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0] or '')), t(r[1]), t((r[2] or '—').replace('_', ' ')), b("OK", "ok") if (r[3] or '').lower() in ('ok', 'certificado', 'valido') else b(r[3] or '—', 'info')]))
    return out


async def _build_juridico(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)
    n_proc = await _scalar(db, "SELECT count(*) FROM juridico_processos")

    async def _visao():
        st = (await db.execute(text("SELECT status::text, count(*) FROM juridico_processos GROUP BY status ORDER BY count(*) DESC"))).fetchall()
        tp = (await db.execute(text("SELECT tipo::text, count(*) FROM juridico_processos GROUP BY tipo ORDER BY count(*) DESC LIMIT 6"))).fetchall()
        return {"title": "Visão geral", "sub": "Jurídico — dados reais", "cta": "Novo processo", "type": "dash", "panelGrid": "1fr 1fr",
                "kpis": [
                    {"v": str(n_proc), "l": "Processos", "icon": _ICF["chart"], "color": "#0F1B3A"},
                    {"v": str(await _scalar(db, "SELECT count(*) FROM juridico_processos WHERE escalonar=true") or 0), "l": "Escalonados", "icon": IC["alert"], "color": "#C2410C"},
                    {"v": "—", "l": "Pareceres", "icon": IC["cal"], "color": "#64748B"},
                    {"v": "—", "l": "Contratos", "icon": _ICF["hand"], "color": "#64748B"},
                ],
                "panels": [
                    {"title": "Processos por status", "rows": [{"left": (s or "—").capitalize(), "right": str(c), **S["info"]} for s, c in st] or [{"left": "Sem processos", "right": "0", **S["mut"]}]},
                    {"title": "Processos por tipo", "rows": [{"left": (s or "—").capitalize(), "right": str(c), **S["warn"]} for s, c in tp] or [{"left": "—", "right": "0", **S["mut"]}]},
                ]}

    await safe("visao", _visao())
    await safe("processos", tbl("Processos", f"{n_proc} processos", "Novo processo",
        ["Número", "Tipo", "Reclamante", "Status"], "1.4fr 1.2fr 1.8fr 0.9fr",
        "SELECT coalesce(numero,'—'), coalesce(tipo::text,'—'), coalesce(reclamante,'—'), status::text FROM juridico_processos ORDER BY created_at DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t((r[1] or '—').replace('_', ' ')), t(r[2]), b(r[3] or "—", "info")]))
    return out


async def _build_empresas(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)
    n_emp = await _scalar(db, "SELECT count(*) FROM empresas")
    obr_pend = await _scalar(db, "SELECT count(*) FROM fiscal_obligations WHERE status::text NOT IN ('pago','paga','concluido','concluida')")

    async def _visao():
        emps = (await db.execute(text("SELECT razao_social, coalesce(regime_tributario::text,'—') FROM empresas ORDER BY razao_social LIMIT 10"))).fetchall()
        return {"title": "Visão geral", "sub": "Empresas — dados reais", "cta": "Nova empresa", "type": "dash", "panelGrid": "1.4fr 1fr",
                "kpis": [
                    {"v": str(n_emp), "l": "Empresas", "icon": IC["shield"], "color": "#0F1B3A"},
                    {"v": str(obr_pend), "l": "Obrigações em aberto", "icon": IC["alert"], "color": "#C2410C" if obr_pend else "#0F1B3A"},
                    {"v": str(await _scalar(db, "SELECT count(*) FROM clients WHERE status='active'") or 0), "l": "Clientes", "icon": IC["users"], "color": "#0F1B3A"},
                    {"v": str(await _scalar(db, "SELECT count(*) FROM nfse_manaus_historico") or 0), "l": "NFS-e (histórico)", "icon": _ICF["chart"], "color": "#0F1B3A"},
                ],
                "panels": [
                    {"title": "Empresas do grupo", "rows": [{"left": rs, "right": (rg or "—"), **S["info"]} for rs, rg in emps] or [{"left": "Sem empresas", "right": "—", **S["mut"]}]},
                    {"title": "Obrigações", "rows": [{"left": (n or "—"), "right": brl(v), **S["warn"]} for n, v in (await db.execute(text("SELECT nome, valor_devido FROM fiscal_obligations ORDER BY data_vencimento NULLS LAST LIMIT 6"))).fetchall()] or [{"left": "Sem obrigações", "right": brl(0), **S["ok"]}]},
                ]}

    await safe("visao", _visao())
    await safe("dashboard", _visao())
    await safe("obrigacoes", tbl("Obrigações", f"{await _scalar(db, 'SELECT count(*) FROM fiscal_obligations')} obrigações", "Nova obrigação",
        ["Obrigação", "Competência", "Valor", "Vencimento", "Status"], "1.8fr 1fr 1fr 1fr 0.9fr",
        "SELECT coalesce(nome,'—'), coalesce(to_char(make_date(competencia_ano, greatest(competencia_mes,1), 1),'MM/YYYY'),'—'), coalesce(valor_devido,0), data_vencimento, status::text "
        "FROM fiscal_obligations ORDER BY data_vencimento DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t(brl(r[2]), 600), t(_fmtdate(r[3])), b("Pago", "ok") if (r[4] or "").lower() in ("pago", "paga") else b(r[4] or "Pendente", "warn")]))
    return out


async def _asos_screen(db, tbl):
    n = await _scalar(db, "SELECT count(*) FROM gp_asos")
    return await tbl("Exames (ASO)", f"{n} ASOs", "Agendar exame",
        ["Colaborador", "Tipo", "Validade", "Situação"], "2fr 1.2fr 1fr 0.9fr",
        "SELECT coalesce(e.nome,'—'), coalesce(a.tipo::text,'—'), a.data_validade, a.apto FROM gp_asos a LEFT JOIN employees e ON e.id=a.employee_id ORDER BY a.data_validade DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0] or '')), t((r[1] or '—').replace('_', ' ')), t(_fmtdate(r[2])), b("Apto", "ok") if r[3] else b("Inapto/Pendente", "warn")])


async def _epi_screen(db, tbl):
    n = await _scalar(db, "SELECT count(*) FROM gp_epi_deliveries")
    return await tbl("EPI — Entregas", f"{n} entregas", "Registrar entrega",
        ["Colaborador", "EPI", "CA", "Entrega"], "2fr 1.4fr 0.9fr 1fr",
        "SELECT coalesce(e.nome,'—'), coalesce(d.epi_nome,'—'), coalesce(d.epi_ca,'—'), d.data_entrega FROM gp_epi_deliveries d LEFT JOIN employees e ON e.id=d.employee_id ORDER BY d.data_entrega DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0] or '')), t(r[1]), t(r[2]), t(_fmtdate(r[3]))])


async def _ged_screen(db, tbl):
    n = await _scalar(db, "SELECT count(*) FROM ged_kit_documents")
    return await tbl("Arquivos", f"{n} documentos", "Enviar documento",
        ["Documento", "Tipo", "Colaborador", "Assinado"], "2fr 1.4fr 1.6fr 0.9fr",
        "SELECT coalesce(g.document_name,'—'), coalesce(g.document_type::text,'—'), coalesce(e.nome,'—'), g.is_signed FROM ged_kit_documents g LEFT JOIN employees e ON e.id=g.employee_id ORDER BY g.created_at DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t((r[1] or '—').replace('_', ' ')), t(r[2]), b("Assinado", "ok") if r[3] else b("Pendente", "warn")])


async def _build_saude(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)
    n_aso = await _scalar(db, "SELECT count(*) FROM gp_asos")
    n_risk = await _scalar(db, "SELECT count(*) FROM gp_risks")
    n_epi = await _scalar(db, "SELECT count(*) FROM gp_epi_deliveries")
    aptos = await _scalar(db, "SELECT count(*) FROM gp_asos WHERE apto=true")

    async def _visao():
        aso_st = (await db.execute(text("SELECT status::text, count(*) FROM gp_asos GROUP BY status ORDER BY count(*) DESC LIMIT 6"))).fetchall()
        risk_lv = (await db.execute(text("SELECT nivel::text, count(*) FROM gp_risks GROUP BY nivel ORDER BY count(*) DESC LIMIT 6"))).fetchall()
        return {"title": "Visão geral", "sub": "Saúde Ocupacional — dados reais", "cta": "Nova ação", "type": "dash", "panelGrid": "1fr 1fr",
                "kpis": [
                    {"v": str(n_aso), "l": "ASOs", "icon": _ICF["hand"], "color": "#0F1B3A"},
                    {"v": str(aptos), "l": "Aptos", "icon": IC["shield"], "color": "#16A34A"},
                    {"v": str(n_risk), "l": "Riscos mapeados", "icon": IC["alert"], "color": "#0F1B3A"},
                    {"v": str(n_epi), "l": "EPIs entregues", "icon": IC["shield"], "color": "#0F1B3A"},
                ],
                "panels": [
                    {"title": "ASO por status", "rows": [{"left": (s or "—").capitalize(), "right": str(c), **S["info"]} for s, c in aso_st] or [{"left": "Sem ASO", "right": "0", **S["mut"]}]},
                    {"title": "Riscos por nível", "rows": [{"left": (s or "—").capitalize(), "right": str(c), **S["warn"]} for s, c in risk_lv] or [{"left": "Sem riscos", "right": "0", **S["mut"]}]},
                ]}

    risk_tone = {"alto": "bad", "high": "bad", "critico": "bad", "medio": "warn", "moderado": "warn", "baixo": "info", "low": "info"}
    await safe("visao", _visao())
    await safe("exames", _asos_screen(db, tbl))
    await safe("epi", _epi_screen(db, tbl))
    await safe("riscos", tbl("Riscos ocupacionais", f"{n_risk} riscos", "Novo risco",
        ["Categoria", "Descrição", "Nível", "Status"], "1.2fr 2.2fr 0.9fr 0.9fr",
        "SELECT coalesce(categoria::text,'—'), coalesce(descricao,'—'), coalesce(nivel::text,'—'), status::text FROM gp_risks ORDER BY nivel DESC NULLS LAST LIMIT 200",
        lambda r: [t((r[0] or '—').replace('_', ' '), 600, "#0F1B3A"), t(r[1]), b((r[2] or '—').capitalize(), risk_tone.get((r[2] or '').lower(), "mut")), b(r[3] or "—", "info")]))

    # eSocial · Transmissão (VISIBILIDADE real, READ-ONLY) — reusa o acompanhamento do clássico.
    # Protocolo/recibo SEMPRE do governo; transmitir em lote continua no fluxo gated (não aqui).
    async def _esocial_screen():
        from modules.people_management.sst.services.transmissao_central_service import acompanhamento
        ac = await acompanhamento(db, 200)
        cont = ac.get("contagem", {})
        st_tone = {"recibo_casado": "ok", "aguardando_recibo": "warn", "rejeitado_ou_erro": "bad"}
        rows = [{"cells": [
            t(ev.get("tipo", "—"), 600, "#0F1B3A"),
            t(ev.get("funcionario") or "—"),
            b((ev.get("esocial_status") or "—").capitalize(), st_tone.get(ev.get("grupo"), "info")),
            t(ev.get("esocial_protocolo") or "—"),
            t(ev.get("recibo") or "—"),
        ]} for ev in ac.get("eventos", [])]
        sub = (f"Aguardando recibo {cont.get('aguardando_recibo', 0)} · Casados {cont.get('recibo_casado', 0)} · "
               f"Rejeitados {cont.get('rejeitado_ou_erro', 0)} — protocolo/recibo SEMPRE do governo (nada fabricado)")
        return {"title": "eSocial · Transmissão", "sub": sub, "type": "table", "searchHint": "Buscar evento…",
                "grid": "0.8fr 2fr 1fr 1.4fr 1.4fr", "cols": ["Evento", "Funcionário", "Status", "Protocolo", "Recibo"],
                "rows": rows or [{"cells": [t("—"), t("Sem eventos transmitidos"), b("—", "mut"), t("—"), t("—")]}]}

    await safe("esocial", _esocial_screen())
    # CAT (S-2210) — leitura real de gp_cats
    _cat_tone = {"grave": "bad", "fatal": "bad", "moderada": "warn", "leve": "info", "tipica": "info"}
    await safe("cat", tbl(
        "CAT — Comunicação de Acidente", f"{await _scalar(db, 'SELECT count(*) FROM gp_cats')} CATs (S-2210)", "Nova CAT",
        ["Colaborador", "Tipo", "Data", "Gravidade", "Nº CAT INSS", "eSocial"], "1.8fr 1.2fr 1fr 0.9fr 1.1fr 0.9fr",
        "SELECT coalesce(e.nome, c.employee_id::text, '—'), coalesce(c.tipo_acidente,'—'), c.data_acidente, "
        "coalesce(c.gravidade,'—'), coalesce(c.numero_cat_inss,'—'), coalesce(c.esocial_status::text,'nao_transmitida') "
        "FROM gp_cats c LEFT JOIN employees e ON e.id::text=c.employee_id::text ORDER BY c.data_acidente DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0])), t((r[1] or '—').replace('_', ' ')), t(_fmtdate(r[2])),
                   b((r[3] or '—').capitalize(), _cat_tone.get((r[3] or '').lower(), "info")), t(r[4]),
                   b((r[5] or '—').replace('_', ' ').capitalize(), "ok" if (r[5] or '').startswith('aceit') else "warn")]))
    # Afastamentos (S-2230) — leitura real de sst_afastamentos
    await safe("afastamentos", tbl(
        "Afastamentos", f"{await _scalar(db, 'SELECT count(*) FROM sst_afastamentos')} afastamentos (S-2230)", "Novo afastamento",
        ["Colaborador", "Tipo", "Início", "Fim previsto", "Retorno", "CID", "Estabilidade", "Status"], "1.6fr 1fr 0.9fr 1fr 0.9fr 0.7fr 1fr 0.9fr",
        "SELECT coalesce(employee_nome,'—'), coalesce(tipo::text,'—'), data_inicio, data_fim_prevista, data_retorno, "
        "coalesce(cid,'—'), gera_estabilidade, estabilidade_ate, coalesce(status::text,'—') FROM sst_afastamentos ORDER BY data_inicio DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0])), t((r[1] or '—').replace('_', ' ')), t(_fmtdate(r[2])), t(_fmtdate(r[3])),
                   t(_fmtdate(r[4]) if r[4] else 'em curso'), t(r[5]),
                   b(f"até {_fmtdate(r[7])}", "warn") if r[6] else b("não", "mut"), b((r[8] or '—').capitalize(), "info")]))
    return out


async def _build_documentos(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)
    n_ged = await _scalar(db, "SELECT count(*) FROM ged_kit_documents")
    n_signed = await _scalar(db, "SELECT count(*) FROM ged_kit_documents WHERE is_signed=true")

    async def _visao():
        ty = (await db.execute(text("SELECT document_type::text, count(*) FROM ged_kit_documents GROUP BY document_type ORDER BY count(*) DESC LIMIT 8"))).fetchall()
        return {"title": "Visão geral", "sub": "Documentos (GED) — dados reais", "cta": "Enviar documento", "type": "dash", "panelGrid": "1fr 1fr",
                "kpis": [
                    {"v": f"{n_ged:,}".replace(",", "."), "l": "Documentos", "icon": IC["cal"], "color": "#0F1B3A"},
                    {"v": f"{n_signed:,}".replace(",", "."), "l": "Assinados", "icon": IC["shield"], "color": "#16A34A"},
                    {"v": str(await _scalar(db, "SELECT count(DISTINCT employee_id) FROM ged_kit_documents") or 0), "l": "Colaboradores", "icon": IC["users"], "color": "#0F1B3A"},
                    {"v": str(await _scalar(db, "SELECT count(DISTINCT document_type) FROM ged_kit_documents") or 0), "l": "Tipos", "icon": IC["cal"], "color": "#0F1B3A"},
                ],
                "panels": [
                    {"title": "Documentos por tipo", "rows": [{"left": (s or "—").replace("_", " ").capitalize(), "right": str(c), **S["ok"]} for s, c in ty] or [{"left": "Sem documentos", "right": "0", **S["mut"]}]},
                    {"title": "Assinatura", "rows": [{"left": "Assinados", "right": str(n_signed), **S["ok"]}, {"left": "Pendentes", "right": str((n_ged or 0) - (n_signed or 0)), **S["warn"]}]},
                ]}

    await safe("visao", _visao())
    await safe("arquivos", _ged_screen(db, tbl))
    return out


async def _build_campo(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)
    n_vis = await _scalar(db, "SELECT count(*) FROM visitas")
    n_os = await _scalar(db, "SELECT count(*) FROM ordens_servico")

    async def _visao():
        return {"title": "Visão geral", "sub": "Campo — dados reais", "cta": "Nova visita", "type": "dash", "panelGrid": "1fr 1fr",
                "kpis": [
                    {"v": str(n_vis), "l": "Visitas", "icon": IC["shield"], "color": "#0F1B3A"},
                    {"v": str(n_os), "l": "Ordens de serviço", "icon": _ICF["hand"], "color": "#0F1B3A"},
                    {"v": str(await _scalar(db, "SELECT count(*) FROM posts WHERE status='active'") or 0), "l": "Postos ativos", "icon": IC["shield"], "color": "#0F1B3A"},
                    {"v": str(await _scalar(db, "SELECT count(*) FROM occurrences") or 0), "l": "Ocorrências", "icon": IC["alert"], "color": "#0F1B3A"},
                ],
                "panels": [
                    {"title": "Visitas por status", "rows": [{"left": (s or "—").capitalize(), "right": str(c), **S["info"]} for s, c in (await db.execute(text("SELECT status::text, count(*) FROM visitas GROUP BY status ORDER BY count(*) DESC"))).fetchall()] or [{"left": "Sem visitas", "right": "0", **S["mut"]}]},
                    {"title": "OS por status", "rows": [{"left": (s or "—").capitalize(), "right": str(c), **S["warn"]} for s, c in (await db.execute(text("SELECT status::text, count(*) FROM ordens_servico GROUP BY status ORDER BY count(*) DESC"))).fetchall()] or [{"left": "Sem OS", "right": "0", **S["mut"]}]},
                ]}

    await safe("visao", _visao())
    await safe("checkin", tbl("Visitas de campo", f"{n_vis} visitas", "Nova visita",
        ["Número", "Tipo", "Responsável", "Status"], "1fr 1.2fr 1.8fr 0.9fr",
        "SELECT coalesce(numero,'—'), coalesce(tipo::text,'—'), coalesce(responsavel_nome, prospect_nome, '—'), status::text FROM visitas ORDER BY id DESC LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t((r[1] or '—').replace('_', ' ')), t(r[2]), b(r[3] or "—", "info")]))
    await safe("ordens-servico", tbl("Ordens de serviço", f"{n_os} OS", "Nova OS",
        ["Número", "Tipo", "Cliente", "Prioridade", "Status"], "1fr 1.2fr 1.6fr 0.9fr 0.9fr",
        "SELECT coalesce(numero,'—'), coalesce(tipo::text,'—'), coalesce(cliente_nome,'—'), coalesce(prioridade::text,'—'), status::text FROM ordens_servico ORDER BY id DESC LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t((r[1] or '—').replace('_', ' ')), t(r[2]), b((r[3] or '—').capitalize(), "warn" if (r[3] or '').lower() in ("alta", "urgente", "high") else "info"), b(r[4] or "—", "info")]))
    return out


async def _build_servicos(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)
    n_os = await _scalar(db, "SELECT count(*) FROM ordens_servico")

    async def _visao():
        return {"title": "Visão geral", "sub": "Serviços — dados reais", "cta": "Nova OS", "type": "dash", "panelGrid": "1fr 1fr",
                "kpis": [
                    {"v": str(n_os), "l": "Ordens de serviço", "icon": _ICF["hand"], "color": "#0F1B3A"},
                    {"v": str(await _scalar(db, "SELECT count(*) FROM service_catalog") or 0), "l": "Catálogo", "icon": IC["cal"], "color": "#0F1B3A"},
                    {"v": str(await _scalar(db, "SELECT count(*) FROM clients WHERE status='active'") or 0), "l": "Clientes", "icon": IC["users"], "color": "#0F1B3A"},
                    {"v": str(await _scalar(db, "SELECT count(*) FROM ordens_servico WHERE status::text NOT IN ('concluida','concluido','cancelada')") or 0), "l": "Em aberto", "icon": IC["alert"], "color": "#0F1B3A"},
                ],
                "panels": [
                    {"title": "OS por status", "rows": [{"left": (s or "—").capitalize(), "right": str(c), **S["info"]} for s, c in (await db.execute(text("SELECT status::text, count(*) FROM ordens_servico GROUP BY status ORDER BY count(*) DESC"))).fetchall()] or [{"left": "Sem OS", "right": "0", **S["mut"]}]},
                    {"title": "OS por tipo", "rows": [{"left": (s or "—").capitalize(), "right": str(c), **S["warn"]} for s, c in (await db.execute(text("SELECT tipo::text, count(*) FROM ordens_servico GROUP BY tipo ORDER BY count(*) DESC LIMIT 6"))).fetchall()] or [{"left": "—", "right": "0", **S["mut"]}]},
                ]}

    await safe("visao", _visao())
    await safe("ordens", tbl("Ordens", f"{n_os} OS", "Nova OS",
        ["Número", "Tipo", "Cliente", "Status"], "1fr 1.2fr 1.8fr 0.9fr",
        "SELECT coalesce(numero,'—'), coalesce(tipo::text,'—'), coalesce(cliente_nome,'—'), status::text FROM ordens_servico ORDER BY id DESC LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t((r[1] or '—').replace('_', ' ')), t(r[2]), b(r[3] or "—", "info")]))
    return out


def _kv(val, unit):
    v = float(val or 0)
    if unit == "BRL":
        return brl(v)
    if unit == "%":
        return f"{v:.1f}".replace(".", ",") + "%"
    return str(int(v)) if v == int(v) else f"{v:.1f}".replace(".", ",")


async def _build_bi(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)

    async def _dash():
        rows = (await db.execute(text("SELECT name, current_value, unit, category::text, direction::text FROM executive_kpis WHERE status::text!='inactive' ORDER BY category"))).fetchall()
        by_name = {r[0]: r for r in rows}

        def kpi(nm, label, icon, color="#0F1B3A"):
            r = by_name.get(nm)
            return {"v": _kv(r[1], r[2]) if r else "—", "l": label, "icon": icon, "color": color}

        cats: dict = {}
        for nm, val, unit, cat, direc in rows:
            cats.setdefault(cat or "—", []).append((nm, _kv(val, unit)))
        # dois painéis: FINANCIAL e COMMERCIAL/OPERATIONAL
        def panel(title, catkey):
            return {"title": title, "rows": [{"left": nm, "right": v, **S["info"]} for nm, v in cats.get(catkey, [])] or [{"left": "—", "right": "—", **S["mut"]}]}

        return {"title": "Dashboard", "sub": "Business Intelligence — KPIs reais", "cta": "Atualizar", "type": "dash", "panelGrid": "1fr 1fr",
                "kpis": [
                    kpi("Funcionarios Ativos", "Funcionários ativos", IC["users"]),
                    kpi("Clientes Ativos", "Clientes ativos", _ICF["hand"]),
                    kpi("Receita Recorrente Mensal", "MRR", _ICF["money"], "#16A34A"),
                    kpi("Margem Bruta", "Margem bruta", _ICF["chart"]),
                ],
                "panels": [panel("Financeiro", "FINANCIAL"), panel("Comercial", "COMMERCIAL")]}

    await safe("dashboard", _dash())
    return out


async def _build_analytics(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)

    async def _visao():
        async def sc(sql):
            return await _scalar(db, sql) or 0
        punches = await sc("SELECT count(*) FROM gp_clock_punches")
        ged = await sc("SELECT count(*) FROM ged_kit_documents")
        nfse = await sc("SELECT count(*) FROM nfse_manaus_historico") + await sc("SELECT count(*) FROM nfse_emitidas_nacional")
        prop = await sc("SELECT count(*) FROM proposals")
        emp = await sc("SELECT count(*) FROM employees")
        inter = await sc("SELECT count(*) FROM inter_transactions")
        return {"title": "Visão geral", "sub": "Analytics — métricas de uso reais", "cta": "Exportar", "type": "dash", "panelGrid": "1fr 1fr",
                "kpis": [
                    {"v": f"{punches:,}".replace(",", "."), "l": "Batidas de ponto", "icon": IC["cal"], "color": "#0F1B3A"},
                    {"v": f"{ged:,}".replace(",", "."), "l": "Documentos GED", "icon": IC["cal"], "color": "#0F1B3A"},
                    {"v": f"{nfse:,}".replace(",", "."), "l": "NFS-e", "icon": _ICF["chart"], "color": "#0F1B3A"},
                    {"v": f"{inter:,}".replace(",", "."), "l": "Transações bancárias", "icon": _ICF["money"], "color": "#0F1B3A"},
                ],
                "panels": [
                    {"title": "Volume por módulo", "rows": [
                        {"left": "Colaboradores", "right": str(emp), **S["info"]},
                        {"left": "Propostas comerciais", "right": str(prop), **S["info"]},
                        {"left": "Documentos GED", "right": f"{ged:,}".replace(",", "."), **S["info"]},
                        {"left": "Batidas de ponto", "right": f"{punches:,}".replace(",", "."), **S["info"]},
                    ]},
                    {"title": "Fiscal", "rows": [
                        {"left": "NFS-e (histórico)", "right": str(await sc("SELECT count(*) FROM nfse_manaus_historico")), **S["ok"]},
                        {"left": "NFS-e nacional", "right": str(await sc("SELECT count(*) FROM nfse_emitidas_nacional")), **S["ok"]},
                        {"left": "NFS-e tomadas", "right": str(await sc("SELECT count(*) FROM nfse_tomadas_nacional")), **S["ok"]},
                    ]},
                ]}

    await safe("visao", _visao())
    return out


async def _build_relatorios(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)

    async def sc(sql):
        return await _scalar(db, sql) or 0

    async def _central():
        postos = await sc("SELECT count(*) FROM posts WHERE status='active'")
        colab = await sc("SELECT count(*) FROM employees WHERE status='ativo'")
        pagar = await sc("SELECT coalesce(sum(net_value),0) FROM payable_accounts WHERE status IN ('pendente','parcial')")
        receber = await sc("SELECT coalesce(sum(net_value),0) FROM receivable_accounts WHERE status IN ('pendente','parcial')")
        leads = await sc("SELECT count(*) FROM leads")
        prop = await sc("SELECT count(*) FROM proposals")
        contr = await sc("SELECT count(*) FROM contracts")
        holerites = await sc("SELECT count(*) FROM hr_payslips")
        return {"title": "Central de relatórios", "sub": "Indicadores reais por área", "cta": "Novo relatório", "type": "cards",
                "cards": [
                    {"title": "Operacional", "sub": "Postos e escalas", "badge": "Ativo", **S["ok"], "hasStats": True,
                     "stats": [{"v": str(postos), "l": "Postos"}, {"v": str(colab), "l": "Colab."}, {"v": str(await sc("SELECT count(*) FROM occurrences")), "l": "Ocorr."}]},
                    {"title": "Financeiro", "sub": "Contas e caixa", "badge": "Ativo", **S["info"], "hasStats": True,
                     "stats": [{"v": brl(pagar), "l": "A pagar", "color": "#C2410C"}, {"v": brl(receber), "l": "A receber", "color": "#16A34A"}]},
                    {"title": "Comercial", "sub": "Funil e vendas", "badge": "Ativo", **S["info"], "hasStats": True,
                     "stats": [{"v": str(leads), "l": "Leads"}, {"v": str(prop), "l": "Propostas"}, {"v": str(contr), "l": "Contratos"}]},
                    {"title": "Departamento Pessoal", "sub": "Folha e benefícios", "badge": "Ativo", **S["ok"], "hasStats": True,
                     "stats": [{"v": str(holerites), "l": "Holerites"}, {"v": brl(await sc("SELECT coalesce(sum(net_salary),0) FROM hr_payslips WHERE (reference_year,reference_month)=(SELECT reference_year,reference_month FROM hr_payslips ORDER BY reference_year DESC, reference_month DESC LIMIT 1)")), "l": "Folha líq."}]},
                ]}

    await safe("central", _central())
    await safe("operacional", tbl("Relatório operacional", "Indicadores reais", "Exportar",
        ["Indicador", "Valor"], "2fr 1fr",
        "SELECT * FROM (VALUES "
        "('Postos ativos', (SELECT count(*)::text FROM posts WHERE status='active')), "
        "('Postos inativos', (SELECT count(*)::text FROM posts WHERE status='inactive')), "
        "('Colaboradores ativos', (SELECT count(*)::text FROM employees WHERE status='ativo')), "
        "('Alocações ativas', (SELECT count(*)::text FROM employee_alocacoes WHERE ativo=true)), "
        "('Ocorrências (total)', (SELECT count(*)::text FROM occurrences))) v(k,val)",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1], 700)]))
    await safe("financeiro", tbl("Relatório financeiro", "Indicadores reais", "Exportar",
        ["Indicador", "Valor"], "2fr 1fr",
        "SELECT * FROM (VALUES "
        "('Contas a pagar (aberto)','money', (SELECT coalesce(sum(net_value),0) FROM payable_accounts WHERE status IN ('pendente','parcial'))::text), "
        "('Contas a receber (aberto)','money', (SELECT coalesce(sum(net_value),0) FROM receivable_accounts WHERE status IN ('pendente','parcial'))::text), "
        "('Diaristas pagos (total)','money', (SELECT coalesce(sum(valor),0) FROM financial_pagamentos_diaristas)::text), "
        "('Clientes ativos','int', (SELECT count(*) FROM clients WHERE status='active')::text)) v(k,kind,val)",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(brl(r[2]) if r[1] == "money" else r[2], 700)]))
    await safe("comercial", tbl("Relatório comercial", "Indicadores reais", "Exportar",
        ["Indicador", "Valor"], "2fr 1fr",
        "SELECT * FROM (VALUES "
        "('Leads', (SELECT count(*)::text FROM leads)), "
        "('Propostas', (SELECT count(*)::text FROM proposals)), "
        "('Contratos', (SELECT count(*)::text FROM contracts)), "
        "('Comissões (registros)', (SELECT count(*)::text FROM commissions))) v(k,val)",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1], 700)]))
    return out


async def _build_configuracoes(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)
    n_users = await _scalar(db, "SELECT count(*) FROM users")
    n_active = await _scalar(db, "SELECT count(*) FROM users WHERE is_active=true")

    async def _visao():
        by_role = (await db.execute(text("SELECT coalesce(role::text,'—'), count(*) FROM users GROUP BY role ORDER BY count(*) DESC LIMIT 6"))).fetchall()
        return {"title": "Visão geral", "sub": "Configurações — dados reais", "cta": "Novo usuário", "type": "dash", "panelGrid": "1fr 1fr",
                "kpis": [
                    {"v": str(n_users), "l": "Usuários", "icon": IC["users"], "color": "#0F1B3A"},
                    {"v": str(n_active), "l": "Ativos", "icon": IC["shield"], "color": "#16A34A"},
                    {"v": str(await _scalar(db, "SELECT count(DISTINCT role) FROM users") or 0), "l": "Perfis", "icon": IC["cal"], "color": "#0F1B3A"},
                    {"v": str((n_users or 0) - (n_active or 0)), "l": "Inativos", "icon": IC["alert"], "color": "#0F1B3A"},
                ],
                "panels": [
                    {"title": "Usuários por perfil", "rows": [{"left": (r or "—"), "right": str(c), **S["info"]} for r, c in by_role] or [{"left": "Sem usuários", "right": "0", **S["mut"]}]},
                    {"title": "Situação", "rows": [{"left": "Ativos", "right": str(n_active), **S["ok"]}, {"left": "Inativos", "right": str((n_users or 0) - (n_active or 0)), **S["mut"]}]},
                ]}

    await safe("visao", _visao())
    await safe("usuarios", tbl("Usuários", f"{n_users} usuários · {n_active} ativos", "Novo usuário",
        ["Usuário", "E-mail", "Perfil", "Status"], "1.6fr 1.8fr 1fr 0.9fr",
        "SELECT coalesce(name,'—'), coalesce(email,'—'), coalesce(role::text,'—'), is_active FROM users ORDER BY name LIMIT 300",
        lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0] or '')), t(r[1]), t(r[2]), b("Ativo", "ok") if r[3] else b("Inativo", "mut")]))
    return out


async def _build_seguranca(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)
    n_audit = await _scalar(db, "SELECT count(*) FROM turnover_audit_logs")

    async def _visao():
        return {"title": "Visão geral", "sub": "Segurança & LGPD — dados reais", "cta": "Ver auditoria", "type": "dash", "panelGrid": "1fr 1fr",
                "kpis": [
                    {"v": str(n_audit), "l": "Eventos de auditoria", "icon": IC["shield"], "color": "#0F1B3A"},
                    {"v": str(await _scalar(db, "SELECT count(*) FROM users WHERE is_active=true") or 0), "l": "Usuários ativos", "icon": IC["users"], "color": "#0F1B3A"},
                    {"v": str(await _scalar(db, "SELECT count(*) FROM employees WHERE face_enrolled_at IS NOT NULL") or 0), "l": "Biometria facial", "icon": IC["shield"], "color": "#0F1B3A"},
                    {"v": "—", "l": "Solicitações LGPD", "icon": IC["alert"], "color": "#64748B"},
                ],
                "panels": [
                    {"title": "Auditoria por ação", "rows": [{"left": (a or "—").replace("_", " ").capitalize(), "right": str(c), **S["info"]} for a, c in (await db.execute(text("SELECT acao::text, count(*) FROM turnover_audit_logs GROUP BY acao ORDER BY count(*) DESC LIMIT 6"))).fetchall()] or [{"left": "Sem eventos", "right": "0", **S["mut"]}]},
                    {"title": "Recursos auditados", "rows": [{"left": (r or "—"), "right": str(c), **S["warn"]} for r, c in (await db.execute(text("SELECT recurso::text, count(*) FROM turnover_audit_logs GROUP BY recurso ORDER BY count(*) DESC LIMIT 6"))).fetchall()] or [{"left": "—", "right": "0", **S["mut"]}]},
                ]}

    await safe("visao", _visao())
    audit = (await db.execute(text(
        "SELECT a.acao::text, a.recurso::text, u.name, a.created_at FROM turnover_audit_logs a LEFT JOIN users u ON u.id=a.usuario_id ORDER BY a.created_at DESC NULLS LAST LIMIT 100"))).fetchall()
    out["auditoria"] = {"title": "Auditoria", "sub": f"{n_audit} eventos", "cta": "Exportar", "type": "list",
        "items": [{"title": f"{(ac or '—').replace('_', ' ').capitalize()} · {rec or '—'}",
                   "meta": f"{nm or 'sistema'} · {_fmtdate(dt, '%d/%m/%Y %H:%M')}",
                   "dot": "#2563EB", "badge": "Auditoria", **S["info"]} for ac, rec, nm, dt in audit]
        or [{"title": "Sem eventos de auditoria", "meta": "aguardando dado", "dot": "#16A34A", "badge": "OK", **S["ok"]}]}
    return out


async def _build_licitacoes(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)
    n_opp = await _scalar(db, "SELECT count(*) FROM bidding_opportunities")
    n_ten = await _scalar(db, "SELECT count(*) FROM bidding_tenders")
    n_part = await _scalar(db, "SELECT count(*) FROM bidding_tenders WHERE participando=true")
    n_prop = await _scalar(db, "SELECT count(*) FROM bidding_proposals")

    async def _visao():
        opp_st = (await db.execute(text("SELECT coalesce(status,'—'), count(*) FROM bidding_opportunities GROUP BY 1 ORDER BY 2 DESC LIMIT 6"))).fetchall()
        mod = (await db.execute(text("SELECT coalesce(modalidade,'—'), count(*) FROM bidding_tenders GROUP BY 1 ORDER BY 2 DESC LIMIT 6"))).fetchall()
        val_ctr = await _scalar(db, "SELECT coalesce(sum(valor_contrato),0) FROM bidding_public_contracts WHERE coalesce(ativo,true)=true")
        return {"title": "Visão geral", "sub": "Licitações — dados reais", "cta": "Atualizar", "type": "dash", "panelGrid": "1fr 1fr",
                "kpis": [
                    {"v": str(n_opp), "l": "Oportunidades", "icon": IC["shield"], "color": "#0F1B3A"},
                    {"v": f"{n_part}/{n_ten}", "l": "Editais (participando)", "icon": IC["cal"], "color": "#0F1B3A"},
                    {"v": str(n_prop), "l": "Propostas", "icon": _ICF["hand"], "color": "#0F1B3A"},
                    {"v": brl(val_ctr), "l": "Contratos públicos", "icon": _ICF["money"], "color": "#16A34A"},
                ],
                "panels": [
                    {"title": "Oportunidades por status", "rows": [{"left": (s or "—").capitalize(), "right": str(c), **S["info"]} for s, c in opp_st] or [{"left": "Sem oportunidades", "right": "0", **S["mut"]}]},
                    {"title": "Editais por modalidade", "rows": [{"left": (m or "—"), "right": str(c), **S["ok"]} for m, c in mod] or [{"left": "Sem editais", "right": "0", **S["mut"]}]},
                ]}

    await safe("visao", _visao())
    await safe("oportunidades", tbl(
        "Oportunidades", f"{n_opp} captadas", "Atualizar",
        ["Objeto", "Órgão", "UF", "Valor estimado", "Encerra", "Status"], "2.2fr 1.6fr 0.5fr 1fr 1fr 0.9fr",
        "SELECT objeto, coalesce(orgao_nome,'—'), coalesce(uf,'—'), valor_estimado, data_encerramento, coalesce(status,'—') "
        "FROM bidding_opportunities ORDER BY data_encerramento DESC NULLS LAST LIMIT 200",
        lambda r: [t((r[0] or '—')[:80], 600, "#0F1B3A"), t((r[1] or '—')[:40]), t(r[2]), t(brl(r[3]) if r[3] is not None else '—'), t(_fmtdate(r[4])), b((r[5] or '—').capitalize(), "info")]))
    await safe("editais", tbl(
        "Editais", f"{n_ten} editais ({n_part} participando)", "Novo edital",
        ["Nº / Objeto", "Órgão", "Modalidade", "Valor estimado", "Status", "Participa"], "2fr 1.6fr 1.1fr 1fr 0.9fr 0.8fr",
        "SELECT coalesce(objeto_resumido, objeto, numero, '—'), coalesce(orgao_nome,'—'), coalesce(modalidade,'—'), valor_estimado, coalesce(status,'—'), coalesce(participando,false) "
        "FROM bidding_tenders ORDER BY data_abertura DESC NULLS LAST LIMIT 200",
        lambda r: [t((r[0] or '—')[:70], 600, "#0F1B3A"), t((r[1] or '—')[:40]), t(r[2]), t(brl(r[3]) if r[3] is not None else '—'), b((r[4] or '—').capitalize(), "info"), b("Sim", "ok") if r[5] else b("Não", "mut")]))
    await safe("propostas", tbl(
        "Propostas", f"{n_prop} propostas", "Nova proposta",
        ["Nº", "Edital", "Valor total", "Classificação", "Status"], "0.8fr 2.2fr 1fr 1fr 0.9fr",
        "SELECT coalesce(p.numero,'—'), coalesce(t.objeto_resumido, t.objeto, '—'), p.valor_total, p.posicao_classificacao, coalesce(p.status,'—') "
        "FROM bidding_proposals p LEFT JOIN bidding_tenders t ON t.id=p.tender_id ORDER BY p.created_at DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t((r[1] or '—')[:70]), t(brl(r[2]) if r[2] is not None else '—'), t(f"{r[3]}º" if r[3] else '—'), b((r[4] or '—').capitalize(), "info")]))
    await safe("contratos", tbl(
        "Contratos públicos", f"{await _scalar(db, 'SELECT count(*) FROM bidding_public_contracts')} contratos", "Novo contrato",
        ["Contrato", "Objeto", "Órgão", "Valor", "Vigência", "Status"], "1fr 1.8fr 1.4fr 1fr 1.1fr 0.9fr",
        "SELECT coalesce(numero_contrato,'—'), coalesce(objeto_resumido, objeto, '—'), coalesce(orgao_nome,'—'), valor_contrato, data_vigencia_fim, coalesce(status,'—') "
        "FROM bidding_public_contracts ORDER BY data_assinatura DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t((r[1] or '—')[:55]), t((r[2] or '—')[:35]), t(brl(r[3]) if r[3] is not None else '—'), t(_fmtdate(r[4])), b((r[5] or '—').capitalize(), "ok")]))
    await safe("certidoes", tbl(
        "Certidões", f"{await _scalar(db, 'SELECT count(*) FROM bidding_certificates')} certidões", "Nova certidão",
        ["Certidão", "Tipo", "Órgão", "Validade", "Situação"], "1.8fr 1.2fr 1.4fr 1fr 0.9fr",
        "SELECT coalesce(nome,'—'), coalesce(tipo,'—'), coalesce(orgao_emissor,'—'), data_validade, coalesce(situacao, status, '—') "
        "FROM bidding_certificates ORDER BY data_validade ASC NULLS LAST LIMIT 200",
        lambda r: [t((r[0] or '—')[:45], 600, "#0F1B3A"), t(r[1]), t((r[2] or '—')[:35]), t(_fmtdate(r[3])), b((r[4] or '—').capitalize(), "info")]))
    # disputas (list)
    drows = (await db.execute(text(
        "SELECT coalesce(d.status,'—'), coalesce(d.resultado,'—'), d.posicao_final, coalesce(t.objeto_resumido, t.objeto, '—'), d.finished_at "
        "FROM bidding_disputes d LEFT JOIN bidding_tenders t ON t.id=d.tender_id ORDER BY d.started_at DESC NULLS LAST LIMIT 100"))).fetchall()
    res_tone = {"vencedor": "ok", "ganhou": "ok", "perdedor": "bad", "perdeu": "bad", "desclassificado": "bad"}
    ditems = [{"title": (obj or "Disputa")[:70],
               "meta": f"Resultado: {(resu or '—')} · {(f'{pos}º' if pos else '—')} · {_fmtdate(fin, '%d/%m/%Y %H:%M')}",
               "dot": "#2563EB", "badge": (st or "—").capitalize(), **S[res_tone.get((resu or "").lower(), "info")]}
              for st, resu, pos, obj, fin in drows]
    if not ditems:
        ditems = [{"title": "Sem disputas", "meta": "aguardando dado", "dot": "#16A34A", "badge": "OK", **S["ok"]}]
    out["disputas"] = {"title": "Disputas", "sub": f"{len(drows)} disputas", "cta": "Ver", "type": "list", "items": ditems}
    return out


async def _build_portal_funcionario(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)
    ativos = await _scalar(db, "SELECT count(*) FROM employees WHERE status='ativo'")
    n_pay = await _scalar(db, "SELECT count(*) FROM hr_payslips")
    n_fer = await _scalar(db, "SELECT count(*) FROM employee_vacation_requests")
    n_reemb = await _scalar(db, "SELECT count(*) FROM reimbursement_requests")

    async def _dash():
        comp = (await db.execute(text("SELECT reference_year, reference_month FROM hr_payslips ORDER BY reference_year DESC, reference_month DESC LIMIT 1"))).fetchone()
        comp_lbl = f"{comp[1]:02d}/{comp[0]}" if comp else "—"
        liq = await _scalar(db, "SELECT coalesce(sum(net_salary),0) FROM hr_payslips WHERE (reference_year,reference_month)=(SELECT reference_year,reference_month FROM hr_payslips ORDER BY reference_year DESC, reference_month DESC LIMIT 1)")
        fr = (await db.execute(text("SELECT coalesce(status::text,'—'), count(*) FROM employee_vacation_requests GROUP BY 1 ORDER BY 2 DESC LIMIT 5"))).fetchall()
        return {"title": "Início", "sub": "Portal do Funcionário — dados reais", "cta": "Atualizar", "type": "dash", "panelGrid": "1fr 1fr",
                "kpis": [
                    {"v": str(ativos), "l": "Colaboradores", "icon": IC["users"], "color": "#0F1B3A"},
                    {"v": str(n_pay), "l": "Holerites", "icon": _ICF["money"], "color": "#0F1B3A"},
                    {"v": str(n_fer), "l": "Férias solicitadas", "icon": IC["cal"], "color": "#0F1B3A"},
                    {"v": str(n_reemb), "l": "Reembolsos", "icon": _ICF["hand"], "color": "#0F1B3A"},
                ],
                "panels": [
                    {"title": f"Folha — competência {comp_lbl}", "rows": [{"left": "Líquido total", "right": brl(liq), **S["ok"]}]},
                    {"title": "Férias por status", "rows": [{"left": (s or "—").capitalize(), "right": str(c), **S["info"]} for s, c in fr] or [{"left": "Sem férias", "right": "0", **S["mut"]}]},
                ]}

    await safe("dashboard", _dash())
    await safe("contracheque", tbl(
        "Contracheque", f"{n_pay} holerites", "Ver",
        ["Colaborador", "Competência", "Líquido", "Status"], "2fr 1fr 1fr 0.9fr",
        "SELECT coalesce(e.nome,'—'), p.reference_month, p.reference_year, p.net_salary, coalesce(p.status::text,'—') "
        "FROM hr_payslips p LEFT JOIN employees e ON e.id=p.employee_id ORDER BY p.reference_year DESC, p.reference_month DESC LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0])), t(f"{r[1]:02d}/{r[2]}" if r[1] else "—"), t(brl(r[3]) if r[3] is not None else "—"), b((r[4] or "—").capitalize(), "info")]))
    await safe("ferias", tbl(
        "Minhas férias", f"{n_fer} solicitações", "Solicitar",
        ["Colaborador", "Início", "Fim", "Dias", "Status"], "2fr 1fr 1fr 0.7fr 0.9fr",
        "SELECT coalesce(e.nome,'—'), v.start_date, v.end_date, v.days_requested, coalesce(v.status::text,'—') "
        "FROM employee_vacation_requests v LEFT JOIN employees e ON e.id=v.employee_id ORDER BY v.start_date DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0])), t(_fmtdate(r[1])), t(_fmtdate(r[2])), t(str(r[3]) if r[3] is not None else "—"), b((r[4] or "—").capitalize(), "info")]))
    await safe("documentos", tbl(
        "Meus documentos", f"{await _scalar(db, 'SELECT count(*) FROM ged_kit_documents')} documentos", "Enviar",
        ["Documento", "Tipo", "Colaborador", "Assinado"], "2fr 1.4fr 1.6fr 0.9fr",
        "SELECT coalesce(g.document_name,'—'), coalesce(g.document_type::text,'—'), coalesce(e.nome,'—'), g.is_signed "
        "FROM ged_kit_documents g LEFT JOIN employees e ON e.id=g.employee_id ORDER BY g.created_at DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t((r[1] or "—").replace("_", " ")), t(r[2]), b("Assinado", "ok") if r[3] else b("Pendente", "warn")]))
    return out


async def _build_meu_espaco(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)
    n_not = await _scalar(db, "SELECT count(*) FROM portal_notifications")
    n_task = await _scalar(db, "SELECT count(*) FROM crm_tasks")

    async def _visao():
        nlidas = await _scalar(db, "SELECT count(*) FROM portal_notifications WHERE coalesce(is_read,false)=false")
        n_reemb = await _scalar(db, "SELECT count(*) FROM reimbursement_requests")
        ty = (await db.execute(text("SELECT coalesce(notification_type::text,'—'), count(*) FROM portal_notifications GROUP BY 1 ORDER BY 2 DESC LIMIT 6"))).fetchall()
        return {"title": "Meu espaço", "sub": "Área pessoal — dados reais", "cta": "Atualizar", "type": "dash", "panelGrid": "1fr 1fr",
                "kpis": [
                    {"v": str(n_not), "l": "Notificações", "icon": IC["cal"], "color": "#0F1B3A"},
                    {"v": str(nlidas), "l": "Não lidas", "icon": IC["shield"], "color": "#C2410C"},
                    {"v": str(n_task), "l": "Tarefas", "icon": _ICF["hand"], "color": "#0F1B3A"},
                    {"v": str(n_reemb), "l": "Reembolsos", "icon": _ICF["money"], "color": "#0F1B3A"},
                ],
                "panels": [
                    {"title": "Notificações por tipo", "rows": [{"left": (x or "—").replace("_", " ").capitalize(), "right": str(c), **S["info"]} for x, c in ty] or [{"left": "Sem notificações", "right": "0", **S["mut"]}]},
                    {"title": "Tarefas", "rows": [{"left": "Tarefas abertas", "right": str(n_task), **(S["ok"] if n_task == 0 else S["warn"])}]},
                ]}

    await safe("visao", _visao())
    await safe("tarefas", tbl(
        "Minhas tarefas", f"{n_task} tarefas", "Nova tarefa",
        ["Tarefa", "Prioridade", "Vencimento", "Status"], "2fr 1fr 1fr 0.9fr",
        "SELECT coalesce(title,'—'), coalesce(priority::text,'—'), due_date, coalesce(status::text,'—') FROM crm_tasks ORDER BY due_date NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), b((r[1] or "—").capitalize(), "info"), t(_fmtdate(r[2])), b((r[3] or "—").capitalize(), "info")]))
    nrows = (await db.execute(text(
        "SELECT coalesce(n.title,'—'), coalesce(n.message,''), coalesce(n.is_read,false), n.created_at, coalesce(e.nome,'—') "
        "FROM portal_notifications n LEFT JOIN employees e ON e.id=n.employee_id ORDER BY n.created_at DESC NULLS LAST LIMIT 100"))).fetchall()
    nitems = [{"title": (ti or "—"), "meta": f"{(msg or '')[:70]} · {nm} · {_fmtdate(dt, '%d/%m/%Y %H:%M')}",
               "dot": "#16A34A" if rd else "#C2410C", "badge": "Lida" if rd else "Nova", **(S["ok"] if rd else S["warn"])}
              for ti, msg, rd, dt, nm in nrows]
    if not nitems:
        nitems = [{"title": "Sem notificações", "meta": "aguardando dado", "dot": "#16A34A", "badge": "OK", **S["ok"]}]
    out["notificacoes"] = {"title": "Notificações", "sub": f"{len(nrows)} notificações", "cta": "Marcar lidas", "type": "list", "items": nitems}
    return out


async def _build_suprimentos(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)
    n_est = await _scalar(db, "SELECT count(*) FROM nfe_compras_estoque")
    n_req = await _scalar(db, "SELECT count(*) FROM purchase_requisitions")

    async def _visao():
        val = await _scalar(db, "SELECT coalesce(sum(qty_on_hand*coalesce(avg_cost,unit_cost,0)),0) FROM nfe_compras_estoque")
        n_fin = await _scalar(db, "SELECT count(*) FROM fin_stock_items")
        top = (await db.execute(text("SELECT descricao, qty_on_hand, coalesce(avg_cost,unit_cost,0) FROM nfe_compras_estoque ORDER BY qty_on_hand*coalesce(avg_cost,unit_cost,0) DESC NULLS LAST LIMIT 6"))).fetchall()
        return {"title": "Visão geral", "sub": "Suprimentos — dados reais", "cta": "Atualizar", "type": "dash", "panelGrid": "1fr 1fr",
                "kpis": [
                    {"v": str(n_est), "l": "Itens no estoque (NF-e)", "icon": IC["shield"], "color": "#0F1B3A"},
                    {"v": brl(val), "l": "Valor em estoque", "icon": _ICF["money"], "color": "#16A34A"},
                    {"v": str(n_req), "l": "Requisições", "icon": IC["cal"], "color": "#0F1B3A"},
                    {"v": str(n_fin), "l": "Itens financeiros", "icon": _ICF["hand"], "color": "#0F1B3A"},
                ],
                "panels": [
                    {"title": "Itens de maior valor", "rows": [{"left": (d or "—")[:40], "right": brl((q or 0) * (cst or 0)), **S["info"]} for d, q, cst in top] or [{"left": "Sem estoque", "right": brl(0), **S["mut"]}]},
                    {"title": "Requisições", "rows": [{"left": "Requisições de compra", "right": str(n_req), **(S["ok"] if n_req == 0 else S["warn"])}]},
                ]}

    await safe("visao", _visao())
    await safe("almoxarifado", tbl(
        "Almoxarifado", f"{n_est} itens (NF-e)", "Atualizar",
        ["Item", "NCM", "Un", "Qtd", "Custo médio", "Última compra"], "2.4fr 1fr 0.5fr 0.7fr 1fr 1fr",
        "SELECT coalesce(descricao, item_code, '—'), coalesce(ncm,'—'), coalesce(unidade,'—'), qty_on_hand, coalesce(avg_cost,unit_cost,0), last_purchase_date "
        "FROM nfe_compras_estoque ORDER BY last_purchase_date DESC NULLS LAST LIMIT 200",
        lambda r: [t((r[0] or "—")[:55], 600, "#0F1B3A"), t(r[1]), t(r[2]), t(str(r[3]) if r[3] is not None else "—"), t(brl(r[4]) if r[4] is not None else "—"), t(_fmtdate(r[5]))]))
    return out


async def _build_integracoes(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)
    n_sol = await _scalar(db, "SELECT count(*) FROM solides_employees")
    n_esc = await _scalar(db, "SELECT count(*) FROM solides_work_schedules")

    async def _visao():
        n_cpf = await _scalar(db, "SELECT count(DISTINCT cpf) FROM solides_employees WHERE cpf IS NOT NULL")
        return {"title": "Visão geral", "sub": "Integrações — dados reais", "cta": "Atualizar", "type": "dash", "panelGrid": "1fr 1fr",
                "kpis": [
                    {"v": str(n_sol), "l": "Colaboradores Sólides", "icon": IC["users"], "color": "#0F1B3A"},
                    {"v": str(n_esc), "l": "Escalas Sólides", "icon": IC["cal"], "color": "#0F1B3A"},
                    {"v": str(n_cpf), "l": "CPFs sincronizados", "icon": IC["shield"], "color": "#16A34A"},
                    {"v": "Ativo", "l": "Conector Sólides", "icon": _ICF["hand"], "color": "#16A34A"},
                ],
                "panels": [
                    {"title": "Conectores ativos", "rows": [{"left": "Sólides (RH/ponto)", "right": "Ativo", **S["ok"]}, {"left": "Banco Inter (financeiro)", "right": "Ativo", **S["ok"]}]},
                    {"title": "Sólides — escopo do sync", "rows": [{"left": "Identidade (nome/email/CPF)", "right": f"{n_sol}", **S["ok"]}, {"left": "Escalas de trabalho", "right": f"{n_esc}", **S["info"]}]},
                ]}

    await safe("visao", _visao())
    await safe("solides", tbl(
        "Sólides · Colaboradores sincronizados", f"{n_sol} colaboradores · {n_esc} escalas (sync RH/ponto)", "Sincronizar",
        ["Colaborador", "Email", "CPF"], "1.8fr 2fr 1.2fr",
        "SELECT coalesce(nome,'—'), coalesce(email,'—'), coalesce(cpf,'—') FROM solides_employees ORDER BY nome LIMIT 300",
        lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0])), t(r[1]), t(r[2])]))
    return out


BUILDERS = {
    "operacional": _build_operacional,
    "financeiro": _build_financeiro,
    "departamento-pessoal": _build_dp,
    "crm": _build_crm,
    "fiscal": _build_fiscal,
    "gestao-de-pessoas": _build_gp,
    "recrutamento": _build_recrutamento,
    "rh": _build_rh,
    "juridico": _build_juridico,
    "empresas": _build_empresas,
    "saude-ocupacional": _build_saude,
    "documentos": _build_documentos,
    "campo": _build_campo,
    "servicos": _build_servicos,
    "bi": _build_bi,
    "analytics": _build_analytics,
    "relatorios": _build_relatorios,
    "configuracoes": _build_configuracoes,
    "seguranca": _build_seguranca,
    "licitacoes": _build_licitacoes,
    "portal-do-funcionario": _build_portal_funcionario,
    "meu-espaco": _build_meu_espaco,
    "suprimentos": _build_suprimentos,
    "integracoes": _build_integracoes,
}


# =============================================================================
# ESCRITA (mutações) — Onda 1: ocorrência (baixo risco, sem dinheiro/legal).
# Import LAZY dentro da função: não arrisca o boot do backend; no pior caso
# só este endpoint falha, nunca derruba o app. Dinheiro/folha/fiscal NÃO
# passam por aqui — esses seguem o fluxo comprovado com gate OTP.
# =============================================================================
@router.post("/action/occurrence")
async def rd_action_occurrence(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    import uuid as _uuid

    import modules.operacional.occurrences.controllers.occurrence_controller as _OC
    from modules.operacional.occurrences.repositories.occurrence_repository import OccurrenceRepository

    desc = (payload.get("description") or "").strip()
    post_id = payload.get("post_id")
    if not post_id:
        raise HTTPException(status_code=400, detail="Selecione o posto da ocorrência.")
    if len(desc) < 10:
        raise HTTPException(status_code=400, detail="A descrição precisa de ao menos 10 caracteres.")
    title = (payload.get("title") or desc).strip()[:120]
    if len(title) < 5:
        title = (title + " · ocorrência")[:120]
    try:
        data = _OC.OccurrenceCreate(
            tenant_id=getattr(current_user, "condominio_id", None) or _uuid.uuid4(),
            reported_by_id=current_user.id,
            post_id=str(post_id),
            title=title,
            description=desc,
            occurrence_type=payload.get("occurrence_type") or "incidente",
            severity=payload.get("severity") or "moderada",
            category=payload.get("category") or "operacional",
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Dados inválidos: {e}")
    occ = await OccurrenceRepository(db).create(data, inspector_id=str(current_user.id))
    return {"ok": True, "id": str(occ.id), "code": getattr(occ, "code", None), "message": "Ocorrência registrada"}


@router.post("/action/lead")
async def rd_action_lead(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from modules.crm.repositories.lead_repository import LeadRepository
    from modules.crm.schemas.lead import LeadCreate

    name = (payload.get("name") or "").strip()
    if len(name) < 2:
        raise HTTPException(status_code=400, detail="Informe o nome do lead (mínimo 2 caracteres).")
    kwargs: dict = {"name": name, "source": payload.get("source") or "other"}
    for k in ("email", "company", "position", "notes"):
        v = (payload.get(k) or "").strip()
        if v:
            kwargs[k] = v
    phone = "".join(c for c in (payload.get("phone") or "") if c.isdigit())
    if 10 <= len(phone) <= 15:
        kwargs["phone"] = phone
    ev = payload.get("expected_value")
    if ev not in (None, ""):
        try:
            kwargs["expected_value"] = float(str(ev).replace(".", "").replace(",", "."))
        except (ValueError, TypeError):
            pass
    try:
        data = LeadCreate(**kwargs)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Dados inválidos: {e}")
    repo = LeadRepository(db)
    if data.email and await repo.get_by_email(data.email):
        raise HTTPException(status_code=400, detail="Já existe um lead com este e-mail.")
    lead = await repo.create(data)
    return {"ok": True, "id": str(lead.id), "message": "Lead criado com sucesso"}


@router.post("/action/task")
async def rd_action_task(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from datetime import date as _date

    from modules.crm.models.activity_task import CrmTask

    title = (payload.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Informe o título da tarefa.")
    due = None
    dd = (payload.get("due_date") or "").strip()
    if dd:
        try:
            due = _date.fromisoformat(dd)
        except ValueError:
            raise HTTPException(status_code=400, detail="Data de vencimento inválida.")
    task = CrmTask(
        title=title[:255],
        description=(payload.get("description") or "").strip() or None,
        due_date=due,
        priority=payload.get("priority") or "medium",
        assigned_to_id=str(current_user.id),
        created_by_id=str(current_user.id),
        client_id=payload.get("client_id") or None,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return {"ok": True, "id": str(task.id), "message": "Tarefa criada com sucesso"}


@router.post("/action/occurrence-resolve")
async def rd_action_occ_resolve(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    import modules.operacional.occurrences.controllers.occurrence_controller as _OC
    from modules.operacional.occurrences.repositories.occurrence_repository import OccurrenceRepository

    occ_id = payload.get("occurrence_id")
    if not occ_id:
        raise HTTPException(status_code=400, detail="Selecione a ocorrência.")
    action = (payload.get("corrective_action") or "").strip()
    if len(action) < 5:
        raise HTTPException(status_code=400, detail="Descreva a ação corretiva (mínimo 5 caracteres).")
    data = _OC.OccurrenceResolve(
        corrective_action=action,
        resolution_notes=(payload.get("resolution_notes") or "").strip() or None,
    )
    occ = await OccurrenceRepository(db).resolve(str(occ_id), data, resolved_by_id=current_user.id)
    if not occ:
        raise HTTPException(status_code=404, detail="Ocorrência não encontrada ou já resolvida.")
    return {"ok": True, "id": str(occ.id), "message": "Ocorrência resolvida com sucesso"}


@router.post("/action/occurrence-comment")
async def rd_action_occ_comment(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    import uuid as _uuid
    from datetime import datetime as _dt

    occ_id = payload.get("occurrence_id")
    content = (payload.get("content") or "").strip()
    if not occ_id:
        raise HTTPException(status_code=400, detail="Selecione a ocorrência.")
    if len(content) < 2:
        raise HTTPException(status_code=400, detail="Escreva o comentário.")
    await db.execute(text(
        "INSERT INTO occurrence_comments (id, occurrence_id, author_id, author_name, content, is_internal, created_at, is_active) "
        "VALUES (:id, :oid, :aid, :an, :c, FALSE, :ts, TRUE)"),
        {"id": str(_uuid.uuid4()), "oid": str(occ_id), "aid": str(current_user.id),
         "an": getattr(current_user, "name", None), "c": content, "ts": _dt.utcnow()})
    await db.commit()
    return {"ok": True, "message": "Comentário adicionado"}


@router.post("/action/client-note")
async def rd_action_client_note(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    import uuid as _uuid
    from datetime import datetime as _dt

    cid = payload.get("client_id")
    nota = (payload.get("nota") or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="Selecione o cliente.")
    if len(nota) < 3:
        raise HTTPException(status_code=400, detail="Escreva a anotação (mínimo 3 caracteres).")
    row = (await db.execute(text("SELECT name FROM clients WHERE id=:i"), {"i": cid})).first()
    cliente_nome = row[0] if row else None
    await db.execute(text(
        "INSERT INTO crm_client_notes (id, cliente_id, cliente_nome, nota, autor, created_at) "
        "VALUES (:id, :cid, :nome, :nota, :autor, :ts)"),
        {"id": str(_uuid.uuid4()), "cid": str(cid), "nome": cliente_nome, "nota": nota,
         "autor": getattr(current_user, "email", None), "ts": _dt.utcnow()})
    await db.commit()
    return {"ok": True, "message": "Anotação salva"}


@router.post("/action/proposal")
async def rd_action_proposal(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from modules.crm.repositories.proposal_repository import ProposalRepository
    from modules.crm.schemas.proposal import ProposalCreate, ProposalItemCreate

    title = (payload.get("title") or "").strip()
    if len(title) < 2:
        raise HTTPException(status_code=400, detail="Informe o título da proposta.")
    client_name = (payload.get("client_name") or "").strip()
    client_id = payload.get("client_id")
    if client_id and not client_name:
        row = (await db.execute(text("SELECT name FROM clients WHERE id=:i"), {"i": client_id})).first()
        if row:
            client_name = row[0]
    if not client_name:
        raise HTTPException(status_code=400, detail="Selecione o cliente da proposta.")
    try:
        valor = float(str(payload.get("valor") or "0").replace(".", "").replace(",", "."))
    except (ValueError, TypeError):
        valor = 0.0
    item_name = (payload.get("item_name") or title).strip()[:255]
    items = [ProposalItemCreate(name=item_name, quantity=1, unit_price=valor)] if (valor > 0 or payload.get("item_name")) else []
    try:
        data = ProposalCreate(
            title=title[:255],
            client_name=client_name[:255],
            description=(payload.get("description") or "").strip() or None,
            items=items,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Dados inválidos: {e}")
    proposal = await ProposalRepository(db).create(data, created_by_id=str(current_user.id))
    return {"ok": True, "id": str(proposal.id), "number": getattr(proposal, "number", None), "message": "Proposta criada com sucesso"}


@router.post("/action/opportunity-stage")
async def rd_action_opp_stage(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from modules.crm.models.opportunity import OpportunityStage
    from modules.crm.repositories.opportunity_repository import OpportunityRepository

    opp_id = payload.get("opportunity_id")
    stage = payload.get("stage")
    if not opp_id:
        raise HTTPException(status_code=400, detail="Selecione a oportunidade.")
    if not stage:
        raise HTTPException(status_code=400, detail="Selecione o estágio.")
    try:
        st = OpportunityStage(stage)
    except ValueError:
        raise HTTPException(status_code=400, detail="Estágio inválido.")
    opp = await OpportunityRepository(db).update_stage(str(opp_id), st, (payload.get("notes") or "").strip() or None)
    if not opp:
        raise HTTPException(status_code=404, detail="Oportunidade não encontrada.")
    return {"ok": True, "id": str(opp.id), "message": f"Oportunidade movida para “{st.value}”"}


@router.post("/action/diaria")
async def rd_action_diaria(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from modules.operacional.diaristas import diarias_service as _ds

    diarista_id = payload.get("diarista_id")
    data_str = (payload.get("data") or "").strip()
    posto = (payload.get("posto") or "").strip()
    funcao = (payload.get("funcao") or "").strip()
    turno = (payload.get("turno") or "").strip() or None
    if not diarista_id:
        raise HTTPException(status_code=400, detail="Selecione o diarista.")
    if not data_str:
        raise HTTPException(status_code=400, detail="Informe a data.")
    if not posto:
        raise HTTPException(status_code=400, detail="Selecione o posto.")
    if not funcao:
        raise HTTPException(status_code=400, detail="Selecione a função.")
    try:
        did = int(diarista_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Diarista inválido.")
    res = await _ds.lancar(db, data=data_str, diarista_id=did, funcao=funcao, posto=posto,
                           turno=turno, observacao=(payload.get("observacao") or "").strip() or None,
                           user_id=str(current_user.id))
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("mensagem") or "Não foi possível lançar a diária.")
    vtvr = " · VT+VR no Financeiro" if res.get("vt_vr_enviado_financeiro") else ""
    return {"ok": True, "id": res.get("id"), "message": f"Diária lançada — R$ {float(res.get('valor', 0)):.2f}{vtvr}"}


@router.post("/action/diarista")
async def rd_action_diarista(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from modules.operacional.diaristas import diarias_service as _ds

    res = await _ds.criar_diarista(
        db,
        nome=(payload.get("nome") or "").strip(),
        cpf=(payload.get("cpf") or "").strip() or None,
        pix=(payload.get("pix") or "").strip() or None,
        telefone=(payload.get("telefone") or "").strip() or None,
        email=(payload.get("email") or "").strip() or None,
    )
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("mensagem") or "Não foi possível cadastrar.")
    return {"ok": True, "id": res.get("id"),
            "message": "Diarista já estava cadastrado." if res.get("ja_existia") else "Diarista cadastrado com sucesso."}


@router.post("/action/falta")
async def rd_action_falta(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    scope: OperationalScope = Depends(get_operational_scope),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # REUSA o endpoint comprovado (toda validação: hoje/ontem, sem presença/batida, escopo por posto)
    from modules.operacional.controllers.falta_substituto_controller import FaltaBody, registrar_falta

    shift_id = payload.get("shift_id")
    if not shift_id:
        raise HTTPException(status_code=400, detail="Selecione o turno faltoso.")
    body = FaltaBody(motivo=payload.get("motivo") or "falta", detalhes=(payload.get("detalhes") or "").strip() or None)
    res = await registrar_falta(shift_id, body, scope, db)
    return {"ok": True, "substitution_id": res.get("substitution_id"),
            "message": f"Falta de {res.get('faltoso')} registrada em {res.get('posto')} — substituição aberta"}


@router.post("/action/substituir-diarista")
async def rd_action_substituir(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    scope: OperationalScope = Depends(get_operational_scope),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from modules.operacional.controllers.falta_substituto_controller import SubstituirBody, escalar_substituto

    sub_id = payload.get("substitution_id")
    if not sub_id:
        raise HTTPException(status_code=400, detail="Selecione a substituição aberta.")
    if not payload.get("diarista_id"):
        raise HTTPException(status_code=400, detail="Selecione o diarista.")
    try:
        did = int(payload.get("diarista_id"))
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Diarista inválido.")
    body = SubstituirBody(tipo="diarista", diarista_id=did,
                          funcao=(payload.get("funcao") or "").strip() or None,
                          turno=(payload.get("turno") or "").strip() or None,
                          observacao=(payload.get("observacao") or "").strip() or None)
    res = await escalar_substituto(sub_id, body, scope, db)
    return {"ok": True, "lancamento_id": res.get("lancamento_id"),
            "message": f"Diarista {res.get('substituto')} escalado — diária R$ {float(res.get('valor_diaria', 0)):.2f}"}


@router.post("/action/payable", dependencies=[Depends(require_permission("module:financeiro"))])
async def rd_action_payable(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # REGISTRO de conta a pagar (NÃO paga — dinheiro que sai só via fluxo OTP). Gate financeiro.
    from datetime import date as _date
    from decimal import Decimal, InvalidOperation

    from modules.financial.schemas.payable import PayableAccountCreate
    from modules.financial.services.payable_service import PayableService

    desc = (payload.get("description") or "").strip()
    if len(desc) < 3:
        raise HTTPException(status_code=400, detail="Descrição (mínimo 3 caracteres).")
    try:
        valor = Decimal(str(payload.get("valor") or "0").replace(".", "").replace(",", "."))
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=400, detail="Valor inválido.")
    if valor <= 0:
        raise HTTPException(status_code=400, detail="O valor deve ser maior que zero.")
    dd = (payload.get("due_date") or "").strip()
    try:
        due = _date.fromisoformat(dd)
    except ValueError:
        raise HTTPException(status_code=400, detail="Vencimento inválido.")
    import uuid as _uuid
    # condominio_id "empresa" (todas as 71 contas existentes usam este mesmo tenant default)
    _COND_EMPRESA = _uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
    try:
        data = PayableAccountCreate(
            condominio_id=_COND_EMPRESA,
            description=desc, gross_value=valor, due_date=due,
            supplier_name=(payload.get("supplier_name") or "").strip() or None,
            notes=(payload.get("notes") or "").strip() or None,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Dados inválidos: {e}")
    account = await PayableService(db).create_account(data, current_user.id)
    return {"ok": True, "id": str(account.id), "message": "Conta a pagar registrada (não paga — pagamento é com OTP)"}


@router.post("/action/receivable", dependencies=[Depends(require_permission("module:financeiro"))])
async def rd_action_receivable(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # REGISTRO de conta a receber (não gera boleto/PIX). Gate financeiro.
    import uuid as _uuid
    from datetime import date as _date
    from decimal import Decimal, InvalidOperation

    from modules.financial.schemas.receivable import ReceivableAccountCreate
    from modules.financial.services.receivable_service import ReceivableService

    desc = (payload.get("description") or "").strip()
    if len(desc) < 3:
        raise HTTPException(status_code=400, detail="Descrição (mínimo 3 caracteres).")
    try:
        valor = Decimal(str(payload.get("valor") or "0").replace(".", "").replace(",", "."))
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=400, detail="Valor inválido.")
    if valor <= 0:
        raise HTTPException(status_code=400, detail="O valor deve ser maior que zero.")
    try:
        due = _date.fromisoformat((payload.get("due_date") or "").strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="Vencimento inválido.")
    # customer_name é texto livre (todos os receivables usam assim; customer_id FK→customers, não clients)
    try:
        data = ReceivableAccountCreate(
            condominio_id=_uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890"),
            description=desc, gross_value=valor, due_date=due,
            customer_name=(payload.get("customer_name") or "").strip() or None,
            notes=(payload.get("notes") or "").strip() or None,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Dados inválidos: {e}")
    account = await ReceivableService(db).create_account(data, current_user.id)
    return {"ok": True, "id": str(account.id), "message": "Conta a receber registrada"}


@router.post("/action/epi-delivery")
async def rd_action_epi_delivery(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Registro de entrega de EPI (log operacional NR-6). Alimenta a ficha (ficha_epi_id NULL = pendente).
    # INSERT cru: a coluna employee_id é uuid no banco (o modelo ORM está como String → asyncpg recusa).
    import uuid as _uuid
    from datetime import date as _date

    try:
        emp_uuid = _uuid.UUID((payload.get("employee_id") or "").strip())
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Selecione o colaborador.")
    row = (await db.execute(text("SELECT nome FROM employees WHERE id=:i"), {"i": emp_uuid})).first()
    if not row:
        raise HTTPException(status_code=400, detail="Colaborador não encontrado.")
    nome = (payload.get("epi_nome") or "").strip()
    if len(nome) < 2:
        raise HTTPException(status_code=400, detail="Informe o nome do EPI.")
    try:
        d_ent = _date.fromisoformat((payload.get("data_entrega") or "").strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="Data de entrega inválida.")
    d_val = None
    dv = (payload.get("data_validade") or "").strip()
    if dv:
        try:
            d_val = _date.fromisoformat(dv)
        except ValueError:
            raise HTTPException(status_code=400, detail="Data de validade inválida.")
    try:
        qtd = int(payload.get("quantidade") or 1)
    except (ValueError, TypeError):
        qtd = 1
    qtd = max(qtd, 1)
    nr = (payload.get("nr") or "").strip() or "NR-6"
    ca = (payload.get("epi_ca") or "").strip() or None
    delivery_id = str(_uuid.uuid4())
    await db.execute(text(
        "INSERT INTO gp_epi_deliveries "
        "(delivery_id, employee_id, epi_nome, epi_ca, quantidade, nr, data_entrega, data_validade, created_at) "
        "VALUES (:did, :eid, :nome, :ca, :qtd, :nr, :de, :dv, now())"),
        {"did": delivery_id, "eid": emp_uuid, "nome": nome, "ca": ca,
         "qtd": qtd, "nr": nr, "de": d_ent, "dv": d_val})
    await db.commit()
    return {"ok": True, "id": delivery_id, "message": f"Entrega de EPI registrada para {row[0]}"}


_REEMBOLSO_CATS = {"transporte", "alimentacao", "hospedagem", "material", "comunicacao",
                   "viagem", "estacionamento", "pedagio", "saude", "cursos", "outros"}


@router.post("/action/reembolso")
async def rd_action_reembolso(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Solicitação de reembolso → nasce em RASCUNHO (aprovação e pagamento seguem o fluxo, sem mover dinheiro aqui).
    from datetime import date as _date
    from decimal import Decimal, InvalidOperation

    from modules.reimbursement.repositories import CondominioRepository
    from modules.reimbursement.schemas.reimbursement_item import ReimbursementItemCreate
    from modules.reimbursement.schemas.reimbursement_request import ReimbursementRequestCreate
    from modules.reimbursement.services.reimbursement_service import ReimbursementService

    title = (payload.get("title") or "").strip()
    if len(title) < 3:
        raise HTTPException(status_code=400, detail="Título (mínimo 3 caracteres).")
    cat = (payload.get("category_type") or "").strip()
    if cat not in _REEMBOLSO_CATS:
        raise HTTPException(status_code=400, detail="Selecione a categoria da despesa.")
    try:
        valor = Decimal(str(payload.get("valor") or "0").replace(".", "").replace(",", "."))
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=400, detail="Valor inválido.")
    if valor <= 0:
        raise HTTPException(status_code=400, detail="O valor deve ser maior que zero.")
    try:
        exp = _date.fromisoformat((payload.get("expense_date") or "").strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="Data da despesa inválida.")
    desc = (payload.get("description") or "").strip()
    if len(desc) < 3:
        desc = title
    merchant = (payload.get("merchant") or "").strip() or None
    notes = (payload.get("notes") or "").strip() or None

    cond_id = await CondominioRepository(db).get_first_active_condominio()
    if not cond_id:
        raise HTTPException(status_code=400, detail="Nenhum condomínio disponível para o reembolso.")
    try:
        data = ReimbursementRequestCreate(
            title=title, expense_date_start=exp, expense_date_end=exp, notes=notes,
            items=[ReimbursementItemCreate(
                category_type=cat, description=desc, merchant=merchant, expense_date=exp, amount=valor)],
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Dados inválidos: {e}")
    req = await ReimbursementService(db).create_request(cond_id, current_user.id, data)
    return {"ok": True, "id": str(req.id), "code": req.code,
            "message": f"Reembolso {req.code} criado (rascunho — aprovação e pagamento seguem o fluxo)"}


_JUSTIF_TYPES = {"atraso", "falta"}
_JUSTIF_CATS = {"transito", "saude", "familiar", "transporte_publico", "acidente", "outro"}


@router.post("/action/justificativa-ponto")
async def rd_action_justificativa_ponto(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Justificativa de atraso/falta → nasce PENDENTE (gestor revisa depois). Sem efeito na folha aqui.
    import uuid as _uuid

    from modules.people_management.ponto.schemas.punch_schemas import JustificationCreate
    from modules.people_management.ponto.services.punch_service import PunchService

    try:
        emp_uuid = _uuid.UUID((payload.get("employee_id") or "").strip())
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Selecione o colaborador.")
    row = (await db.execute(text("SELECT nome FROM employees WHERE id=:i"), {"i": emp_uuid})).first()
    if not row:
        raise HTTPException(status_code=400, detail="Colaborador não encontrado.")
    jtype = (payload.get("justification_type") or "").strip()
    if jtype not in _JUSTIF_TYPES:
        raise HTTPException(status_code=400, detail="Selecione o tipo (atraso ou falta).")
    cat = (payload.get("category") or "").strip()
    if cat not in _JUSTIF_CATS:
        raise HTTPException(status_code=400, detail="Selecione o motivo.")
    reason = (payload.get("reason") or "").strip()
    if len(reason) < 5:
        raise HTTPException(status_code=400, detail="Descreva a justificativa (mínimo 5 caracteres).")
    data = JustificationCreate(
        employee_id=str(emp_uuid), justification_type=jtype, reason=reason, category=cat)
    result = await PunchService(db).criar_justificativa(data)
    await db.commit()
    return {"ok": True, "id": result.get("justification_id"),
            "message": f"Justificativa de {jtype} registrada para {row[0]} (pendente de revisão)"}


@router.post("/action/job-position")
async def rd_action_job_position(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Abrir vaga → nasce em RASCUNHO (o recrutador publica depois). Sem impacto em folha/operacional.
    from decimal import Decimal, InvalidOperation

    from modules.recruitment.schemas.job_position import JobPositionCreate
    from modules.recruitment.services.job_position_service import JobPositionService

    title = (payload.get("title") or "").strip()
    if len(title) < 3:
        raise HTTPException(status_code=400, detail="Título da vaga (mínimo 3 caracteres).")

    def _money(key):
        raw = (payload.get(key) or "").strip()
        if not raw:
            return None
        try:
            return Decimal(raw.replace(".", "").replace(",", "."))
        except (InvalidOperation, ValueError):
            raise HTTPException(status_code=400, detail=f"Valor de salário inválido ({key}).")

    try:
        vagas = int(payload.get("vacancies") or 1)
    except (ValueError, TypeError):
        vagas = 1
    vagas = max(vagas, 1)
    sal_min, sal_max = _money("salary_min"), _money("salary_max")
    try:
        data = JobPositionCreate(
            title=title,
            department=(payload.get("department") or "").strip() or None,
            position_type=(payload.get("position_type") or "").strip() or "clt",
            work_model=(payload.get("work_model") or "").strip() or None,
            city=(payload.get("city") or "").strip() or None,
            state=((payload.get("state") or "").strip()[:2].upper() or None),
            vacancies=vagas,
            salary_min=sal_min, salary_max=sal_max,
            show_salary=bool(sal_min or sal_max),
            description=(payload.get("description") or "").strip() or None,
            requirements=(payload.get("requirements") or "").strip() or None,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Dados inválidos: {e}")
    position = await JobPositionService(db).create(data)
    return {"ok": True, "id": str(position.id), "code": getattr(position, "code", None),
            "message": f"Vaga '{title}' aberta (rascunho — publique quando quiser divulgar)"}


@router.post("/action/vacation-request")
async def rd_action_vacation_request(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Solicitação de férias (auto-serviço) → nasce RASCUNHO/DRAFT sobre SALDO REAL. Sem mover folha/dinheiro.
    import uuid as _uuid
    from datetime import date as _date

    from modules.hr.employee_portal.schemas.vacation import VacationRequestCreate, VacationType
    from modules.hr.employee_portal.services.vacation_service import VacationService

    try:
        emp_uuid = _uuid.UUID((payload.get("employee_id") or "").strip())
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Selecione o colaborador.")
    row = (await db.execute(text("SELECT nome FROM employees WHERE id=:i"), {"i": emp_uuid})).first()
    if not row:
        raise HTTPException(status_code=400, detail="Colaborador não encontrado.")
    vtype = (payload.get("vacation_type") or "full").strip()
    if vtype not in {v.value for v in VacationType}:
        vtype = "full"
    try:
        sd = _date.fromisoformat((payload.get("start_date") or "").strip())
        ed = _date.fromisoformat((payload.get("end_date") or "").strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="Datas de início/fim inválidas.")
    if sd < _date.today():
        raise HTTPException(status_code=400, detail="A data de início não pode ser no passado.")
    dias = (ed - sd).days + 1
    if dias < 5 or dias > 30:
        raise HTTPException(status_code=400, detail="O período deve ter de 5 a 30 dias corridos.")
    # condomínio vem do período de férias do colaborador (fallback: empresa)
    crow = (await db.execute(text(
        "SELECT condominio_id FROM employee_vacation_periods WHERE employee_id=:e AND condominio_id IS NOT NULL LIMIT 1"),
        {"e": emp_uuid})).first()
    cond_id = crow[0] if crow else _uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
    try:
        data = VacationRequestCreate(
            vacation_type=VacationType(vtype), start_date=sd, end_date=ed, days_requested=dias,
            employee_notes=(payload.get("employee_notes") or "").strip() or None)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Dados inválidos: {e}")
    try:
        req = await VacationService(db).create_vacation_request(data, cond_id, emp_uuid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "id": str(req.id), "code": getattr(req, "request_code", None),
            "message": f"Férias solicitadas para {row[0]} — {dias} dias (rascunho, pendente de aprovação)"}


@router.post("/action/rescisao-calc")
async def rd_action_rescisao_calc(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Calculadora de rescisão (CLT) — cálculo PURO, sem gravar/transmitir/pagar. Reusa clt_calculator.
    import uuid as _uuid
    from datetime import date as _date
    from decimal import Decimal, InvalidOperation

    from modules.people_management.common.utils.clt_calculator import calcular_rescisao

    try:
        emp_uuid = _uuid.UUID((payload.get("employee_id") or "").strip())
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Selecione o colaborador.")
    row = (await db.execute(text("SELECT nome, salario_base, data_admissao FROM employees WHERE id=:i"), {"i": emp_uuid})).first()
    if not row:
        raise HTTPException(status_code=400, detail="Colaborador não encontrado.")
    nome, sal, adm = row
    if not sal or not adm:
        raise HTTPException(status_code=400, detail="Colaborador sem salário base ou data de admissão cadastrados.")
    tipo = (payload.get("tipo_rescisao") or "sem_justa_causa").strip()
    try:
        demissao = _date.fromisoformat((payload.get("data_desligamento") or "").strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="Data de desligamento inválida.")
    if demissao < adm:
        raise HTTPException(status_code=400, detail="Desligamento não pode ser antes da admissão.")

    def _int(k):
        try:
            return max(int(payload.get(k) or 0), 0)
        except (ValueError, TypeError):
            return 0

    def _money(k):
        raw = (payload.get(k) or "").strip()
        if not raw:
            return Decimal("0")
        try:
            return Decimal(raw.replace(".", "").replace(",", "."))
        except (InvalidOperation, ValueError):
            return Decimal("0")

    try:
        r = calcular_rescisao(Decimal(str(sal)), tipo, adm, demissao,
                              _money("saldo_fgts"), _int("ferias_vencidas_dias"), _int("dias_trabalhados_mes"))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Não foi possível calcular: {e}")
    ferias_tot = (r["ferias_proporcionais"] + r["terco_ferias_proporcionais"]
                  + r["ferias_vencidas"] + r["terco_ferias_vencidas"])
    msg = (f"Rescisão de {nome} ({tipo.replace('_', ' ')}) — LÍQUIDO {brl(r['total_liquido'])} | "
           f"Saldo salário {brl(r['saldo_salario'])} · Aviso {brl(r['aviso_previo_indenizado'])} ({r['aviso_previo_dias']}d) · "
           f"Férias+1/3 {brl(ferias_tot)} · 13º {brl(r['decimo_terceiro_proporcional'])} · "
           f"Multa FGTS {brl(r['multa_fgts'])} · INSS −{brl(r['inss'])} · IRRF −{brl(r['irrf'])} "
           f"({r['anos_servico']} anos de serviço). Cálculo — não gera rescisão.")
    return {"ok": True, "message": msg}


# Itens de menu extras (telas de ação/escrita) que o ModuleView anexa à nav.
EXTRA_MENU = {
    "financeiro": [
        {"id": "registrar-conta-pagar", "label": "Registrar conta a pagar", "icon": "M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"},
        {"id": "registrar-conta-receber", "label": "Registrar conta a receber", "icon": "M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"},
    ],
    "operacional": [
        {"id": "lancar-diaria", "label": "Lançar diária", "icon": "M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"},
        {"id": "cadastrar-diarista", "label": "Cadastrar diarista", "icon": "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 3a4 4 0 1 1 0 8 4 4 0 0 1 0-8M20 8v6M23 11h-6"},
        {"id": "registrar-falta", "label": "Registrar falta", "icon": "M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h16.9a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01"},
        {"id": "escalar-substituto", "label": "Escalar substituto", "icon": "M17 2l4 4-4 4M3 11V9a4 4 0 0 1 4-4h14M7 22l-4-4 4-4M21 13v2a4 4 0 0 1-4 4H3"},
        {"id": "resolver-ocorrencia", "label": "Resolver ocorrência", "icon": "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10zM9 12l2 2 4-4"},
        {"id": "comentar-ocorrencia", "label": "Comentar ocorrência", "icon": "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"},
    ],
    "crm": [
        {"id": "novo-lead", "label": "Novo lead", "icon": "M12 5v14M5 12h14"},
        {"id": "nova-proposta", "label": "Nova proposta", "icon": "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M9 13h6M9 17h3"},
        {"id": "mover-oportunidade", "label": "Mover no funil", "icon": "M3 3v18h18M7 14l3-3 3 3 5-6"},
        {"id": "nova-tarefa", "label": "Nova tarefa", "icon": "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18M12 7v5l3 2"},
        {"id": "anotar-cliente", "label": "Anotar cliente", "icon": "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M8 13h8M8 17h5"},
    ],
    "gestao-de-pessoas": [
        {"id": "registrar-entrega-epi", "label": "Registrar entrega de EPI", "icon": "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"},
        {"id": "registrar-justificativa-ponto", "label": "Justificar ponto", "icon": "M12 8v4l3 2M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z"},
    ],
    "departamento-pessoal": [
        {"id": "calcular-rescisao", "label": "Calcular rescisão", "icon": "M9 7h6M9 11h6M9 15h4M5 3h14a1 1 0 0 1 1 1v16l-3-2-2 2-2-2-2 2-2-2-3 2V4a1 1 0 0 1 1-1z"},
        {"id": "beneficios-cct", "label": "Benefícios CCT", "icon": "M20 12v10H4V12M2 7h20v5H2zM12 22V7M12 7H7.5a2.5 2.5 0 0 1 0-5C11 2 12 7 12 7zM12 7h4.5a2.5 2.5 0 0 0 0-5C13 2 12 7 12 7z"},
        {"id": "registrar-reembolso", "label": "Registrar reembolso", "icon": "M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"},
        {"id": "solicitar-ferias", "label": "Solicitar férias", "icon": "M17 8C8 10 5.9 16.2 3.8 21.7c-.3.7.3 1.3 1 1L8 21c9-2 11-8 13-13M12 2v4M20 6l-2 2"},
    ],
    "recrutamento": [
        {"id": "abrir-vaga", "label": "Abrir vaga", "icon": "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 3a4 4 0 1 1 0 8 4 4 0 0 1 0-8M19 8v6M22 11h-6"},
    ],
    "saude-ocupacional": [
        {"id": "esocial", "label": "eSocial · Transmissão", "icon": "M22 2 11 13M22 2l-7 20-4-9-9-4 20-7z"},
    ],
}


@router.get("/home")
async def redesign_home(current_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)) -> dict:
    """KPIs e pendências REAIS da Home (launcher). Substitui os exemplos chumbados."""
    from datetime import date as _date

    async def _sc(q: str):
        try:
            return await _scalar(db, q)
        except Exception:  # noqa: BLE001
            await db.rollback()
            return 0

    colaboradores = await _sc("SELECT count(*) FROM employees WHERE status='ativo'")
    postos = await _sc("SELECT count(*) FROM posts WHERE coalesce(is_active,true)=true")
    clientes = await _sc("SELECT count(*) FROM clients WHERE status='active'")
    escalas = await _sc("SELECT count(*) FROM solides_work_schedules")

    kpis = [
        {"v": str(colaboradores), "l": "Colaboradores"},
        {"v": str(postos), "l": "Postos ativos"},
        {"v": str(clientes), "l": "Clientes"},
        {"v": str(escalas), "l": "Escalas"},
    ]

    # Pendências REAIS: certidões com vencimento (vencidas ou vencendo em ≤45 dias)
    alerts: list[dict] = []
    try:
        hoje = _date.today()
        rows = (await db.execute(text(
            "SELECT name, expiry_date FROM ged_certidoes "
            "WHERE expiry_date IS NOT NULL ORDER BY expiry_date ASC LIMIT 20"))).fetchall()
        for name, exp in rows:
            dias = (exp - hoje).days
            if dias < 0:
                meta, level, action = f"Vencido há {abs(dias)} dias", "var(--error)", "Regularizar"
            elif dias <= 45:
                meta, level, action = f"Vence em {dias} dias", "var(--warning)", "Ver"
            else:
                continue
            alerts.append({"title": name, "meta": meta, "action": action, "dot": level})
        alerts = alerts[:4]
    except Exception:  # noqa: BLE001
        await db.rollback()
        alerts = []

    return {"kpis": kpis, "alerts": alerts}


@router.get("/data/{slug}")
async def redesign_data(slug: str, current_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)) -> dict:
    """Patches de tela com dado real para o módulo <slug>. Telas não cobertas ficam de fora."""
    builder = BUILDERS.get(slug)
    if not builder:
        return {"slug": slug, "screens": {}, "wired": [], "extraMenu": []}
    screens = await builder(db)
    return {"slug": slug, "screens": screens, "wired": list(screens.keys()), "extraMenu": EXTRA_MENU.get(slug, [])}
