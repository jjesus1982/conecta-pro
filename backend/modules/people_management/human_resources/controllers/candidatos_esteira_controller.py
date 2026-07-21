"""Esteira de aprovação de CANDIDATOS (Funil de candidato — Fase 3).

O RH vê os candidatos que se autocadastraram (employees.status='candidato'), revisa os
dados/selfie e decide: APROVAR ou REPROVAR. A decisão muda o status para 'aprovado' /
'reprovado' (ambos ainda ISOLADOS da produção — só 'ativo' é produção). A ATIVAÇÃO e a
propagação pelos módulos (DP/RH/financeiro/operacional) + notificação + acesso ao portal
são a Fase 4/5.

Montado sob /human-resources (gate de módulo DP + login). Perfis admin (Jordan/Pyetra)
e quem tem o módulo dp acessam.
"""

import calendar
import hashlib
import os
import re
import uuid as _uuid
from datetime import date, datetime, time as _time, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from core.auth.dependencies import get_current_active_user, get_current_user
from core.auth.security import hash_password
from core.database import get_db
from core.database.session import get_sync_db_dependency
from core.models import User

router = APIRouter(prefix="/candidatos", tags=["RH - Candidatos (esteira)"])

_STATUS_VALIDOS = {"candidato", "aprovado", "reprovado"}
_LABEL = {"candidato": "Em análise", "aprovado": "Aprovado", "reprovado": "Não aprovado", "ativo": "Em admissão"}


class DecisaoBody(BaseModel):
    decisao: str  # 'aprovado' | 'reprovado'
    motivo: str | None = None


def _uid(user: User) -> str:
    return str(getattr(user, "id", "") or "")


@router.get("")
def listar_candidatos(
    status_filtro: str = Query("todos", description="todos | candidato | aprovado | reprovado"),
    db: Session = Depends(get_sync_db_dependency),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """Lista os candidatos da esteira, com dados e completude p/ o RH decidir."""
    # 'em_admissao' = já ativado e com checklist de admissão (mesmo já concluído — NÃO some da
    # esteira ao marcar tudo; o RH continua acessando dossiê + certidões permanentes do admitido).
    if status_filtro == "em_admissao":
        where = ("status = 'ativo' AND id IN "
                 "(SELECT employee_id FROM admission_checklists)")
        params: dict[str, Any] = {}
    elif status_filtro in ("aprovado", "reprovado", "candidato"):
        where = "status = :st"
        params = {"st": status_filtro}
    else:  # 'todos' na esteira = em análise (candidato)
        where = "status = 'candidato'"
        params = {}
    rows = db.execute(
        text(
            f"""
            SELECT id::text, matricula, nome, cargo, status, email, telefone, cpf,
                   cidade, uf, pix_key, pix_key_type,
                   coalesce(biometria_facial, false) AS facial,
                   created_at,
                   (CASE WHEN nullif(trim(coalesce(telefone,'')),'') IS NOT NULL THEN 1 ELSE 0 END
                  + CASE WHEN nullif(trim(coalesce(cep,'')),'') IS NOT NULL THEN 1 ELSE 0 END
                  + CASE WHEN nullif(trim(coalesce(nome_mae,'')),'') IS NOT NULL THEN 1 ELSE 0 END
                  + CASE WHEN nullif(trim(coalesce(rg,'')),'') IS NOT NULL THEN 1 ELSE 0 END
                  + CASE WHEN nullif(trim(coalesce(pis,'')),'') IS NOT NULL THEN 1 ELSE 0 END
                  + CASE WHEN nullif(trim(coalesce(naturalidade,'')),'') IS NOT NULL THEN 1 ELSE 0 END
                  + CASE WHEN nullif(trim(coalesce(pix_key,'')),'') IS NOT NULL THEN 1 ELSE 0 END) AS dados_ok,
                   (SELECT total_score FROM candidate_scores cs WHERE cs.employee_id = employees.id) AS score,
                   (SELECT nivel FROM candidate_scores cs WHERE cs.employee_id = employees.id) AS nivel_score,
                   (SELECT recomendacao FROM candidate_scores cs WHERE cs.employee_id = employees.id) AS recomendacao
            FROM employees
            WHERE {where} AND coalesce(is_homologacao, false) = false
            ORDER BY created_at DESC
            """
        ),
        params,
    ).mappings().all()
    candidatos = [
        {
            "id": r["id"], "protocolo": r["matricula"], "nome": r["nome"],
            "cargo_pleiteado": r["cargo"], "status": r["status"], "status_label": _LABEL.get(r["status"], r["status"]),
            "email": r["email"], "telefone": r["telefone"], "cpf": r["cpf"],
            "cidade": r["cidade"], "uf": r["uf"],
            "pix_key": r["pix_key"], "pix_key_type": r["pix_key_type"],
            "facial_cadastrada": bool(r["facial"]),
            "dados_ok": int(r["dados_ok"] or 0), "dados_total": 7,
            "score": round(float(r["score"]), 1) if r["score"] is not None else None,
            "nivel_score": r["nivel_score"], "recomendacao": r["recomendacao"],
            "criado_em": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]
    # contadores da esteira (independe do filtro)
    tot = db.execute(
        text(
            "SELECT status, count(*) FROM employees "
            "WHERE status IN ('candidato','aprovado','reprovado') AND coalesce(is_homologacao,false)=false "
            "GROUP BY status"
        )
    ).fetchall()
    contadores = {k: 0 for k in _STATUS_VALIDOS}
    for st, n in tot:
        contadores[st] = int(n)
    contadores["em_admissao"] = int(db.execute(
        text("SELECT count(DISTINCT employee_id) FROM admission_checklists c "
             "JOIN employees e ON e.id = c.employee_id "
             "WHERE e.status='ativo' AND coalesce(e.is_homologacao,false)=false")
    ).scalar() or 0)
    return {"candidatos": candidatos, "contadores": contadores, "total": len(candidatos)}


@router.get("/postos")
def postos_para_alocar(
    db: Session = Depends(get_sync_db_dependency),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """Postos ativos para o RH escolher ao aprovar (com vaga em destaque).
    Definido ANTES de /{candidato_id} para não colidir na resolução de rota."""
    rows = db.execute(
        text(
            "SELECT p.id::text, p.name, p.code, p.shift_type, "
            "       coalesce(p.required_headcount,0) AS req, coalesce(p.current_headcount,0) AS cur, "
            "       c.name AS cliente "
            "FROM posts p LEFT JOIN clients c ON c.id = p.client_id "
            "WHERE p.is_active AND coalesce(p.code,'') <> 'CONECTA-BASE' "
            "ORDER BY (coalesce(p.required_headcount,0) - coalesce(p.current_headcount,0)) DESC, p.name"
        )
    ).mappings().all()
    return {
        "postos": [
            {
                "id": r["id"], "nome": r["name"], "code": r["code"], "shift_type": r["shift_type"],
                "cliente": r["cliente"], "required": int(r["req"]), "current": int(r["cur"]),
                "vagas": max(0, int(r["req"]) - int(r["cur"])),
            }
            for r in rows
        ]
    }


@router.get("/{candidato_id}")
def detalhe_candidato(
    candidato_id: str,
    db: Session = Depends(get_sync_db_dependency),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """Ficha completa do candidato para revisão do RH."""
    r = db.execute(
        text(
            "SELECT id::text, matricula, nome, cargo, status, email, telefone, cpf, rg, pis, "
            " data_nascimento, estado_civil, nacionalidade, naturalidade, nome_mae, "
            " cep, logradouro, numero, complemento, bairro, cidade, uf, "
            " pix_key, pix_key_type, coalesce(biometria_facial,false) AS facial, created_at "
            "FROM employees WHERE id::text = :id AND status IN ('candidato','aprovado','reprovado')"
        ),
        {"id": candidato_id},
    ).mappings().first()
    if not r:
        raise HTTPException(status_code=404, detail="Candidato não encontrado.")
    d = dict(r)
    d["status_label"] = _LABEL.get(d["status"], d["status"])
    d["facial_cadastrada"] = bool(d.pop("facial"))
    if d.get("created_at"):
        d["created_at"] = d["created_at"].isoformat()
    if d.get("data_nascimento"):
        d["data_nascimento"] = str(d["data_nascimento"])
    return d


@router.post("/{candidato_id}/decisao")
def decidir_candidato(
    candidato_id: str,
    body: DecisaoBody,
    db: Session = Depends(get_sync_db_dependency),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """RH aprova ou reprova o candidato. NÃO ativa nem propaga (isso é a Fase 4)."""
    decisao = (body.decisao or "").strip().lower()
    if decisao not in ("aprovado", "reprovado"):
        raise HTTPException(status_code=422, detail="Decisão deve ser 'aprovado' ou 'reprovado'.")
    atual = db.execute(
        text("SELECT status, nome FROM employees WHERE id::text = :id"), {"id": candidato_id}
    ).mappings().first()
    if not atual:
        raise HTTPException(status_code=404, detail="Candidato não encontrado.")
    if atual["status"] not in ("candidato", "aprovado", "reprovado"):
        raise HTTPException(status_code=409, detail="Este registro não é um candidato em esteira.")

    nota = (
        f"[{datetime.now():%Y-%m-%d %H:%M}] Candidatura {decisao} por {_uid(current_user)}"
        + (f" — {body.motivo.strip()}" if body.motivo else "")
    )
    db.execute(
        text(
            "UPDATE employees SET status = :st, updated_at = now(), updated_by = :by, "
            " observacoes = trim(coalesce(observacoes,'') || E'\\n' || :nota) "
            "WHERE id::text = :id"
        ),
        {"st": decisao, "by": _uid(current_user), "nota": nota, "id": candidato_id},
    )
    db.commit()
    return {
        "success": True,
        "candidato_id": candidato_id,
        "nome": atual["nome"],
        "status": decisao,
        "status_label": _LABEL.get(decisao, decisao),
        "message": f"Candidato {decisao}." + (
            " A ativação e a liberação de acesso acontecem na etapa de propagação." if decisao == "aprovado" else ""
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# CHECKLIST DE ADMISSÃO (pós-aprovação) — com gate humano no que a lei exige
# ─────────────────────────────────────────────────────────────────────────────

class ChecklistItemBody(BaseModel):
    status: str  # 'ok' | 'pendente' | 'nao_aplicavel'
    observacao: str | None = None


@router.get("/{candidato_id}/admissao")
def checklist_admissao(
    candidato_id: str,
    db: Session = Depends(get_sync_db_dependency),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """Checklist de admissão do colaborador aprovado + resumo (bloqueios legais)."""
    from modules.people_management.hr.services import admission_checklist_service as _chk
    rows = db.execute(
        text("SELECT item_key, label, categoria, obrigatorio_legal, gate_humano, status, "
             " observacao, done_at, ordem FROM admission_checklists "
             "WHERE employee_id::text = :id ORDER BY ordem"),
        {"id": candidato_id},
    ).mappings().all()
    itens = [
        {"item_key": r["item_key"], "label": r["label"], "categoria": r["categoria"],
         "obrigatorio_legal": r["obrigatorio_legal"], "gate_humano": r["gate_humano"],
         "status": r["status"], "observacao": r["observacao"],
         "done_at": r["done_at"].isoformat() if r["done_at"] else None}
        for r in rows
    ]
    emp = db.execute(text("SELECT nome, matricula, cargo FROM employees WHERE id::text=:id"),
                     {"id": candidato_id}).mappings().first()
    return {
        "employee": dict(emp) if emp else None,
        "itens": itens,
        "resumo": _chk.resumo(itens),
    }


@router.post("/{candidato_id}/admissao/{item_key}")
def atualizar_item_admissao(
    candidato_id: str,
    item_key: str,
    body: ChecklistItemBody,
    db: Session = Depends(get_sync_db_dependency),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """Marca um item do checklist. Itens com gate humano (ASO, eSocial S-2200) só
    ficam 'ok' aqui, com registro de QUEM e QUANDO confirmou — a lógica de
    'irreversível/legal = confirmação humana'."""
    status_novo = (body.status or "").strip().lower()
    if status_novo not in ("ok", "pendente", "nao_aplicavel"):
        raise HTTPException(status_code=422, detail="Status deve ser ok, pendente ou nao_aplicavel.")
    uid = str(getattr(current_user, "id", "") or "") or None
    r = db.execute(
        text("UPDATE admission_checklists SET status=:st, observacao=coalesce(:obs, observacao), "
             " done_at = CASE WHEN :st='ok' THEN now() ELSE NULL END, "
             " done_by = CASE WHEN :st='ok' THEN CAST(:by AS uuid) ELSE NULL END "
             "WHERE employee_id::text=:id AND item_key=:k RETURNING gate_humano, label"),
        {"st": status_novo, "obs": body.observacao, "by": uid, "id": candidato_id, "k": item_key},
    ).mappings().first()
    if not r:
        raise HTTPException(status_code=404, detail="Item de checklist não encontrado.")
    db.commit()
    return {"success": True, "item_key": item_key, "status": status_novo,
            "gate_humano": r["gate_humano"], "label": r["label"]}


# ─────────────────────────────────────────────────────────────────────────────
# FASE 6.2 — Dossiê + score do candidato (verificação por CPF)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{candidato_id}/verificar")
def verificar_candidato(
    candidato_id: str,
    db: Session = Depends(get_sync_db_dependency),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """Roda as verificações reais por CPF e devolve o dossiê + score."""
    from modules.people_management.hr.services import background_check_service as _bg
    try:
        return _bg.verificar(db, candidato_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Candidato não encontrado.")


@router.get("/{candidato_id}/dossie")
def dossie_candidato(
    candidato_id: str,
    db: Session = Depends(get_sync_db_dependency),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, Any]:
    """Dossiê armazenado (checks + score). Se ainda não foi verificado, score None."""
    checks = db.execute(
        text("SELECT check_type, provider, status, severidade, resumo, resultado, checked_at "
             "FROM candidate_background_checks WHERE employee_id::text=:id ORDER BY checked_at DESC NULLS LAST"),
        {"id": candidato_id},
    ).mappings().all()
    sc = db.execute(
        text("SELECT total_score, nivel, recomendacao, checks_ok, checks_total, fatores, calculated_at "
             "FROM candidate_scores WHERE employee_id::text=:id"),
        {"id": candidato_id},
    ).mappings().first()
    docs = db.execute(
        text("SELECT id::text AS id, tipo, original_name, mime_type, created_at "
             "FROM candidate_documents WHERE employee_id::text=:id AND file_path IS NOT NULL "
             "ORDER BY created_at DESC NULLS LAST"),
        {"id": candidato_id},
    ).mappings().all()
    return {
        "score": (dict(sc) | {"calculated_at": sc["calculated_at"].isoformat() if sc["calculated_at"] else None}) if sc else None,
        "checks": [
            {"check_type": c["check_type"], "provider": c["provider"], "status": c["status"],
             "severidade": c["severidade"], "resumo": c["resumo"]}
            for c in checks
        ],
        "documentos": [
            {"id": d["id"], "tipo": d["tipo"], "nome": d["original_name"] or f"{d['tipo']}.pdf",
             "mime": d["mime_type"], "is_pdf": (d["mime_type"] or "").endswith("pdf"),
             "url": f"/human-resources/candidatos/{candidato_id}/documento/{d['id']}"}
            for d in docs
        ],
    }


@router.get("/{candidato_id}/documento/{doc_id}")
def baixar_documento_candidato(
    candidato_id: str,
    doc_id: str,
    db: Session = Depends(get_sync_db_dependency),
    current_user: User = Depends(get_current_active_user),
):
    """Serve o PDF/imagem de um documento do candidato (certidão do robô ou anexo) — RH autenticado."""
    row = db.execute(
        text("SELECT file_path, mime_type, original_name FROM candidate_documents "
             "WHERE id::text=:d AND employee_id::text=:c"),
        {"d": doc_id, "c": candidato_id},
    ).mappings().first()
    if not row or not row["file_path"] or not os.path.exists(row["file_path"]):
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    return FileResponse(
        row["file_path"],
        media_type=row["mime_type"] or "application/pdf",
        filename=row["original_name"] or f"documento_{doc_id}.pdf",
    )


# ─────────────────────────────────────────────────────────────────────────────
# FASE 4 — Aprovação com PROPAGAÇÃO (RH → DP → operacional → ponto → financeiro)
# ─────────────────────────────────────────────────────────────────────────────

class AprovarBody(BaseModel):
    posto_id: str
    turno: str | None = None          # 12x36 → 'diurno'|'noturno' (default: do posto)
    paridade: str | None = None       # 12x36 → 'pares'|'impares' (default: impares)
    salario_base: float | None = None  # override; default = piso da CCT do cargo


async def _ensure_scale(db: AsyncSession, post_id: str, mes: int, ano: int, scale_type: str, user_id: str | None) -> str:
    sid = (
        await db.execute(
            text("SELECT id::text FROM scales WHERE post_id=CAST(:p AS uuid) AND month=:m AND year=:y AND is_active "
                 "ORDER BY created_at DESC LIMIT 1"),
            {"p": post_id, "m": mes, "y": ano},
        )
    ).scalar()
    if sid:
        return sid
    sid = str(_uuid.uuid4())
    await db.execute(
        text(
            "INSERT INTO scales (id, post_id, scale_type, status, month, year, name, is_active, created_by, created_at, updated_at) "
            "VALUES (CAST(:id AS uuid), CAST(:p AS uuid), :st, 'published', :m, :y, :nm, true, "
            "        CAST(:u AS uuid), now(), now())"
        ),
        {"id": sid, "p": post_id, "st": scale_type, "m": mes, "y": ano, "nm": f"Escala {mes:02d}/{ano}", "u": user_id},
    )
    return sid


async def _gerar_escala(db: AsyncSession, employee_id: str, post_id: str, padrao: str, turno: str,
                        paridade_alvo: int, desde: date, ate: date, user_id: str | None) -> int:
    """Gera scale (se faltar) + shifts do novo colaborador, de `desde` a `ate`.
    12x36 = dias com a paridade escolhida (diurno 07-19 / noturno 19-07); comercial 44h
    = seg-sex 8h (span 9h) + sábado 4h. Mesma matemática do editor de grade (Jordan)."""
    scale_type = "12x36" if padrao == "12x36" else "5x2"
    criados = 0
    y, m = desde.year, desde.month
    while (y, m) <= (ate.year, ate.month):
        sid = await _ensure_scale(db, post_id, m, y, scale_type, user_id)
        for d in range(1, calendar.monthrange(y, m)[1] + 1):
            dia = date(y, m, d)
            if dia < desde or dia > ate:
                continue
            if padrao == "12x36":
                if d % 2 != paridade_alvo:
                    continue
                if turno == "noturno":
                    ini, fim, isn, h, pausa = _time(19, 0), _time(7, 0), True, 12.0, 60
                else:
                    ini, fim, isn, h, pausa = _time(7, 0), _time(19, 0), False, 12.0, 60
            else:  # comercial 44h
                dow = dia.weekday()
                if dow < 5:
                    ini = _time(8, 0); fim = (datetime.combine(dia, ini) + timedelta(hours=9)).time()
                    isn, h, pausa = False, 8.0, 60
                elif dow == 5:  # sábado 4h
                    ini = _time(8, 0); fim = (datetime.combine(dia, ini) + timedelta(hours=4)).time()
                    isn, h, pausa = False, 4.0, 0
                else:
                    continue
            await db.execute(
                text(
                    "INSERT INTO shifts (id, scale_id, employee_id, post_id, shift_date, "
                    " planned_start_time, planned_end_time, planned_break_minutes, status, "
                    " is_holiday, is_night_shift, is_overtime, is_off_day, needs_substitution, "
                    " planned_hours, actual_hours, overtime_hours, night_hours, base_pay, "
                    " overtime_pay, night_bonus, holiday_bonus, total_pay, notes, is_active, created_at, updated_at) "
                    "VALUES (CAST(:id AS uuid), CAST(:sc AS uuid), CAST(:emp AS uuid), CAST(:post AS uuid), :dia, "
                    " :ini, :fim, :pausa, 'scheduled', false, :noturno, false, false, false, "
                    " :h, 0,0,0,0,0,0,0,0, :nota, true, now(), now())"
                ),
                {"id": str(_uuid.uuid4()), "sc": sid, "emp": employee_id, "post": post_id, "dia": dia,
                 "ini": ini, "fim": fim, "pausa": pausa, "noturno": isn, "h": h,
                 "nota": "Escala inicial (ativação do candidato aprovado)"},
            )
            criados += 1
        await db.execute(
            text("UPDATE scales s SET total_shifts=q.n, filled_shifts=q.n, total_hours=q.h, updated_at=now() "
                 "FROM (SELECT count(*) n, COALESCE(sum(planned_hours),0) h FROM shifts "
                 "      WHERE scale_id=CAST(:sc AS uuid) AND is_active) q WHERE s.id=CAST(:sc AS uuid)"),
            {"sc": sid},
        )
        m += 1
        if m > 12:
            m = 1; y += 1
    return criados


@router.post("/{candidato_id}/aprovar")
async def aprovar_e_ativar(
    candidato_id: str,
    body: AprovarBody,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict[str, Any]:
    """APROVA o candidato e PROPAGA pela cadeia: DP (ativa, matrícula, CCT/salário,
    admissão) → operacional (aloca no posto + gera escala) → ponto (facial já pronta) →
    financeiro (PIX já registrado) → contrato de trabalho p/ assinar no portal →
    login + notificação. Tudo numa transação."""
    uid = str(getattr(current_user, "id", "") or "") if not isinstance(current_user, dict) else str(current_user.get("id") or "")

    cand = (
        await db.execute(
            text("SELECT id::text, nome, cpf, cargo, status, email, dependentes FROM employees WHERE id::text = :id"),
            {"id": candidato_id},
        )
    ).mappings().first()
    if not cand:
        raise HTTPException(status_code=404, detail="Candidato não encontrado.")
    if cand["status"] not in ("candidato", "aprovado"):
        raise HTTPException(status_code=409, detail="Este registro não é um candidato em esteira.")

    # GATE DE IDENTIDADE — o sistema NÃO aceita CPF/nome/documento que não confere.
    # Só aprova com a identidade validada (CPF dígito válido + confirmada na Receita).
    # Enquanto não resolver, fica pendente (regra Jordan 2026-07-20).
    ident = (
        await db.execute(
            text("SELECT check_type, status FROM candidate_background_checks "
                 "WHERE employee_id::text=:id AND check_type IN ('cpf_valido','receita_situacao')"),
            {"id": candidato_id},
        )
    ).mappings().all()
    by = {r["check_type"]: r["status"] for r in ident}
    pend = []
    if by.get("cpf_valido") != "ok":
        pend.append("CPF inválido ou ainda não verificado")
    if by.get("receita_situacao") != "ok":
        pend.append("identidade não confirmada na Receita (CPF × nome × data de nascimento)")
    if pend:
        raise HTTPException(
            status_code=422,
            detail="Pendência de identidade — resolva antes de aprovar: " + "; ".join(pend)
            + ". Rode 'Verificar' novamente (ou confira os dados do candidato).",
        )

    posto = (
        await db.execute(
            text("SELECT p.id::text, p.name, p.shift_type, p.client_id::text AS client_id, c.name AS cliente "
                 "FROM posts p LEFT JOIN clients c ON c.id = p.client_id "
                 "WHERE p.id::text = :pid AND p.is_active AND coalesce(p.code,'') <> 'CONECTA-BASE'"),
            {"pid": body.posto_id},
        )
    ).mappings().first()
    if not posto:
        raise HTTPException(status_code=404, detail="Posto não encontrado ou inativo.")

    cargo = cand["cargo"] or ""
    # Mapeia a função → cct_cargo pelo que os funcionários REAIS já usam (as nossas
    # funções não casam por nome com a CCT; o vínculo verdadeiro é via cct_cargo_id).
    cct = (
        await db.execute(
            text("SELECT cc.id::text, cc.piso_salarial "
                 "FROM employees e JOIN cct_cargos cc ON cc.id = e.cct_cargo_id "
                 "WHERE e.status='ativo' AND coalesce(e.is_homologacao,false)=false "
                 "  AND upper(e.cargo)=upper(:c) "
                 "GROUP BY cc.id, cc.piso_salarial ORDER BY count(*) DESC LIMIT 1"),
            {"c": cargo},
        )
    ).mappings().first()
    # fallback: nome direto na CCT (caso a função não exista ainda no quadro)
    if not cct:
        cct = (
            await db.execute(
                text("SELECT id::text, piso_salarial FROM cct_cargos WHERE upper(cargo_nome)=upper(:c) "
                     "AND coalesce(is_active,true) ORDER BY created_at LIMIT 1"),
                {"c": cargo},
            )
        ).mappings().first()
    salario = body.salario_base if body.salario_base else (float(cct["piso_salarial"]) if cct and cct["piso_salarial"] else 0.0)
    cct_id = cct["id"] if cct else None

    # Salário-família: calcula do valor OFICIAL (Portaria 2026) sobre os dependentes que
    # o candidato entregou (certidão de nascimento fotografada → dependentes). Zero trabalho manual.
    from modules.people_management.hr.services import salario_familia_service as _sf
    _deps = cand["dependentes"] if isinstance(cand["dependentes"], list) else []
    salfam = _sf.calcular(salario, _deps)

    matricula = str((await db.execute(
        text("SELECT coalesce(max(matricula::int),0)+1 FROM employees WHERE matricula ~ '^[0-9]+$'")
    )).scalar() or 1)

    eh_portaria = "PORTARIA" in cargo.upper()
    padrao = "12x36" if eh_portaria else "comercial"
    if padrao == "12x36":
        turno = (body.turno or ("noturno" if (posto["shift_type"] or "").lower() == "noturno" else "diurno")).lower()
        escala_padrao = "12x36"
    else:
        turno = "diurno"
        escala_padrao = "44h"
    paridade_alvo = 1 if (body.paridade or "impares").lower() == "impares" else 0
    setor = "PORTARIA" if eh_portaria else "SERVICOS GERAIS"
    hoje = date.today()

    # Admissão como CONTRATO DE EXPERIÊNCIA 45+45 (decisão do Jordan): 1º período 45 dias,
    # prorrogável por mais 45 (total 90). Datas guardadas na ficha (employees só tem tipo_contrato).
    contrato_exp = {
        "tipo": "experiencia", "periodo": "45+45",
        "inicio": hoje.isoformat(),
        "fim_1o_periodo": (hoje + timedelta(days=45)).isoformat(),
        "fim_com_prorrogacao": (hoje + timedelta(days=90)).isoformat(),
    }

    # ── 1) DP: vira colaborador ATIVO com ficha completa ──
    uid_param = uid or None
    await db.execute(
        text(
            "UPDATE employees SET status='ativo', matricula=:mat, cargo=:cargo, "
            " cct_cargo_id=CAST(:cct AS uuid), "
            " salario_base=:sal, data_admissao=:hoje, data_inicio_posto=:hoje, "
            " posto_atual_id=CAST(:pid AS uuid), posto_atual_nome=:pnome, "
            " cliente_id=CAST(:cli AS uuid), cliente_nome=:clinome, "
            " escala_padrao=:esc, turno_padrao=:turno, setor=:setor, carga_horaria_semanal=44, "
            " tipo_contrato='experiencia', regime_trabalho=coalesce(nullif(regime_trabalho,''),'mensalista'), "
            " updated_by=CAST(:by AS uuid), updated_at=now(), "
            " observacoes=trim(coalesce(observacoes,'') || E'\\n' || CAST(:nota AS text)) "
            "WHERE id::text = :id"
        ),
        {"mat": matricula, "cargo": cargo, "cct": cct_id, "sal": salario, "hoje": hoje,
         "pid": posto["id"], "pnome": posto["name"], "cli": posto["client_id"], "clinome": posto["cliente"],
         "esc": escala_padrao, "turno": turno, "setor": setor, "by": uid_param,
         "nota": f"[{datetime.now():%Y-%m-%d %H:%M}] Aprovado e ativado por {uid} — posto {posto['name']}, "
                 f"matrícula {matricula}, salário R${salario:.2f}", "id": candidato_id},
    )

    # ── 1b) Financeiro/DP: salário-família + contrato de experiência gravam na ficha ──
    import json as _json
    await db.execute(
        text("UPDATE employees SET dados_adicionais = coalesce(dados_adicionais, '{}'::jsonb) "
             " || jsonb_build_object('salario_familia', CAST(:sf AS jsonb)) "
             " || jsonb_build_object('contrato_experiencia', CAST(:ce AS jsonb)) "
             "WHERE id::text = :id"),
        {"sf": _json.dumps(salfam), "ce": _json.dumps(contrato_exp), "id": candidato_id},
    )

    # ── 2) Operacional: alocação ativa + escala (até o fim do mês seguinte) ──
    prox = (hoje.replace(day=1) + timedelta(days=32)).replace(day=1)
    ate = (prox + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    await db.execute(
        text(
            "INSERT INTO allocations (id, post_id, employee_id, status, start_date, is_primary, is_temporary, "
            " hourly_rate, monthly_salary, additional_benefits, setor, notes, is_active, created_at, updated_at, created_by) "
            "VALUES (CAST(:id AS uuid), CAST(:p AS uuid), CAST(:e AS uuid), 'active', :ini, true, false, "
            " 0, :sal, 0, :setor, :nota, true, now(), now(), CAST(:u AS uuid))"
        ),
        {"id": str(_uuid.uuid4()), "p": posto["id"], "e": candidato_id, "ini": hoje, "sal": salario,
         "setor": setor, "nota": "Alocação automática na aprovação do candidato", "u": uid_param},
    )
    await db.execute(
        text("UPDATE posts SET current_headcount = (SELECT count(*) FROM allocations WHERE post_id=CAST(:p AS uuid) "
             "AND status='active' AND is_active), updated_at=now() WHERE id=CAST(:p AS uuid)"),
        {"p": posto["id"]},
    )
    turnos = await _gerar_escala(db, candidato_id, posto["id"], padrao, turno, paridade_alvo, hoje, ate, uid or None)

    # ── 3) Acesso: login (senha = CPF) se ainda não existir ──
    email = (cand["email"] or "").strip().lower()
    login_criado = False
    if email:
        ja = (await db.execute(text("SELECT 1 FROM users WHERE lower(email)=:e"), {"e": email})).first()
        if not ja:
            cpf_digits = re.sub(r"\D", "", cand["cpf"] or "")
            await db.execute(
                text("INSERT INTO users (id, email, password_hash, name, role, is_active, employee_id, created_at) "
                     "VALUES (gen_random_uuid(), :email, :ph, :name, 'funcionario', true, CAST(:eid AS uuid), now())"),
                {"email": email, "ph": hash_password(cpf_digits or matricula), "name": cand["nome"], "eid": candidato_id},
            )
            login_criado = True

    # ── 4) DP dispara o CONTRATO DE TRABALHO p/ assinar no portal (best-effort) ──
    contrato_ok = False
    try:
        from modules.people_management.hr.services.contract_generator_service import ContractGeneratorService
        from modules.signatures.helpers.solicitar_assinatura_documento import garantir_solicitacao_assinatura
        contrato = await ContractGeneratorService(db).gerar_contrato_trabalho_html(candidato_id)
        try:
            with open(contrato.file_path, "rb") as _f:
                dhash = hashlib.sha256(_f.read()).hexdigest()
        except OSError:
            dhash = None
        res = await garantir_solicitacao_assinatura(
            db, document_type="contract", document_id=candidato_id,
            title=f"Contrato de Trabalho — {cand['nome']}",
            document_hash=dhash, document_path=contrato.file_path,
            employee_id=candidato_id, employee_name=cand["nome"],
            employee_document=re.sub(r"\D", "", cand["cpf"] or ""), requested_by=uid or None,
        )
        contrato_ok = bool(res)
    except Exception:
        contrato_ok = False  # nunca quebra a ativação

    # ── 5) Notificação no sino do portal ──
    try:
        await db.execute(
            text("INSERT INTO portal_notifications (employee_id, notification_type, title, message, is_read, created_at) "
                 "VALUES (CAST(:e AS uuid), 'general', :t, :m, false, now())"),
            {"e": candidato_id, "t": "Você foi aprovado! 🎉",
             "m": f"Parabéns! Você foi aprovado para {cargo}. Seu acesso está liberado — "
                  f"assine o contrato de trabalho no app e comece a bater o ponto."},
        )
    except Exception:
        pass

    # ── 6) Checklist de admissão: o que falta entre "aprovado" e "legalmente trabalhando" ──
    from modules.people_management.hr.services import admission_checklist_service as _chk
    tem_docs = bool((await db.execute(
        text("SELECT 1 FROM candidate_documents WHERE employee_id::text = :id LIMIT 1"), {"id": candidato_id}
    )).first())
    ctx_chk = {"tem_docs": tem_docs, "tem_pis": bool(cand.get("cpf") and salario),
               "tem_pix": True, "tem_contrato": contrato_ok, "salfam_avaliado": True,
               "contrato_experiencia": True}
    # pis do próprio employee (mais confiável que o cand)
    _pis = (await db.execute(text("SELECT nullif(trim(coalesce(pis,'')),'') FROM employees WHERE id::text=:id"),
                             {"id": candidato_id})).scalar()
    ctx_chk["tem_pis"] = bool(_pis)
    for it in _chk.montar_itens(ctx_chk):
        await db.execute(
            text("INSERT INTO admission_checklists (employee_id, item_key, label, categoria, "
                 " obrigatorio_legal, gate_humano, status, ordem) "
                 "VALUES (CAST(:e AS uuid), :k, :l, :c, :ol, :gh, :st, :o) "
                 "ON CONFLICT (employee_id, item_key) DO NOTHING"),
            {"e": candidato_id, "k": it["key"], "l": it["label"], "c": it["categoria"],
             "ol": it["obrigatorio_legal"], "gh": it["gate_humano"], "st": it["status"], "o": it["ordem"]},
        )

    await db.commit()

    return {
        "success": True,
        "candidato_id": candidato_id,
        "nome": cand["nome"],
        "message": f"{cand['nome']} aprovado e ativado como colaborador.",
        "propagacao": {
            "dp": {"status": "ativo", "matricula": matricula, "cargo": cargo,
                   "salario_base": salario, "cct_vinculada": bool(cct_id), "admissao": hoje.isoformat()},
            "operacional": {"posto": posto["name"], "escala": escala_padrao, "turno": turno,
                            "turnos_gerados": turnos, "setor": setor},
            "ponto": {"facial": "já cadastrada no autocadastro", "pode_bater": True},
            "financeiro": {
                "pix": "registrado (pagamento segue com gate OTP)",
                "salario_familia": (
                    {"elegivel": True, "dependentes": salfam["quantidade_elegivel"],
                     "valor_mensal": salfam["valor_total"], "base": salfam["base_legal"]}
                    if salfam["elegivel"] else
                    {"elegivel": False, "motivo": salfam["motivo"]}
                ),
            },
            "contrato": {"disparado_para_assinatura": contrato_ok},
            "acesso": {"login_criado": login_criado, "portal_liberado": True},
        },
    }
