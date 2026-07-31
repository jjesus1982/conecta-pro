"""Tools GERA-DOC RH — HOLERITE no chat (Fase 6, Fatia 6) — LGPD.

Duas tools, uma regra RBAC inviolável (Jordan):
- `_meu_holerite_doc` (module="self", scope_kind="self"): o COLABORADOR recebe SÓ o
  próprio holerite. A identidade vem SEMPRE de `scope.employee_id` — o schema NÃO tem
  `employee_id` (o LLM nunca escolhe de quem é o holerite). Vazar o de outro = falha grave.
- `_gerar_holerite_funcionario_doc` (module="dp", scope_kind="org"): DP/diretoria recebe
  o de qualquer um, resolvido por nome/CPF/matrícula. Belt (módulo dp) + `_gate` (suspenders).

Paredes (inegociáveis):
- Números SÓ do hr_payslips PERSISTIDO (o que foi PAGO): totais + `earnings`/`deductions`
  JSONB. NUNCA recalcula (calcular_folha_colaborador diverge do pago — R$0,16-classe por
  colaborador). Sem holerite no período → RECUSA. Nunca fabrica, nunca recalcula.
- Doc só pelo gerador branded real (`montar_holerite_pdf`), que já escolhe a marca certa
  (CNPJ1/CNPJ2) por CPF+competência (empresa_branding_por_cpf) — não forçamos CNPJ.
- Read-only: só SELECT + render. Nada grava. Fail-closed.
"""
from __future__ import annotations

import asyncio
import base64
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import String, cast, func, or_, select

from core.auth.module_scope import user_has_module

from .tool_registry import ToolDef, register

_MESES = {1: "01", 2: "02", 3: "03", 4: "04", 5: "05", 6: "06",
          7: "07", 8: "08", 9: "09", 10: "10", 11: "11", 12: "12"}


def _gate(user) -> None:
    if not user_has_module(user, "dp"):
        raise PermissionError("dp")


def _recusa(motivo: str) -> dict[str, Any]:
    return {"status": "recusado", "motivo": motivo}


def _brl(v) -> str:
    try:
        return "R$ " + f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return str(v)


def _map_rubricas(items) -> list[dict[str, Any]]:
    """JSONB earnings/deductions -> lista {descricao, referencia, valor} (tolerante)."""
    out = []
    for it in items or []:
        if isinstance(it, dict):
            out.append({
                "descricao": it.get("description") or it.get("descricao") or "—",
                "referencia": it.get("reference") or it.get("referencia") or "",
                "valor": float(it.get("value") or it.get("valor") or 0),
            })
    return out


def _cpf_norm(col):
    return func.replace(func.replace(func.replace(col, ".", ""), "-", ""), "/", "")


def holerite_pdf_de_payslip(ps, emp) -> bytes:
    """Monta o PDF branded do holerite a partir do hr_payslips PERSISTIDO (Option A).

    `ps` = row PaySlip (ORM); `emp` = row Employee (ORM) ou None (só p/ identidade — nome,
    cargo, escala, cpf, pis, matrícula, admissão, que NÃO existem em hr_payslips). Os NÚMEROS
    são os PAGOS (totais + JSONB), NUNCA recalculados.
    """
    from modules.people_management.folha.services.holerite_pdf import montar_holerite_pdf

    adm = getattr(emp, "data_admissao", None)
    data_pag = None
    if getattr(ps, "payment_date", None):
        try:
            data_pag = ps.payment_date.strftime("%d/%m/%Y")
        except Exception:
            data_pag = str(ps.payment_date)

    holerite = {
        "mes": int(ps.reference_month),
        "ano": int(ps.reference_year),
        "employee_nome": getattr(emp, "nome", None) or "—",
        "cargo": getattr(emp, "cargo", None) or "—",
        "escala": getattr(emp, "escala_padrao", None) or "—",
        "proventos": _map_rubricas(ps.earnings),
        "descontos": _map_rubricas(ps.deductions),
        "total_proventos": float(ps.total_earnings or 0),
        "total_descontos": float(ps.total_deductions or 0),
        "liquido": float(ps.net_salary or 0),
        "base_inss": float(ps.inss_base or 0),
        "base_fgts": float(ps.fgts_base or 0),
        "base_irrf": float(ps.irrf_base or 0),
        "fgts_empresa": float(ps.fgts_value or 0),
    }
    if data_pag:
        holerite["data_pagamento"] = data_pag
    funcionario = {
        "cpf": getattr(emp, "cpf", None),
        "pis": getattr(emp, "pis", None) or "—",
        "matricula": getattr(emp, "matricula", None) or "—",
        "posto": getattr(emp, "posto_atual_nome", None) or getattr(emp, "departamento", None) or "—",
        "departamento": getattr(emp, "departamento", None) or "—",
        "data_admissao": adm.strftime("%d/%m/%Y") if hasattr(adm, "strftime") else (adm or "—"),
    }
    return montar_holerite_pdf(holerite, funcionario)


async def _resolve_payslip(db, employee_id: str, competencia: str | None):
    """O hr_payslips PAGO do colaborador (competência exata ou o mais recente). None se não há."""
    from modules.hr.employee_portal.models.payslip import PaySlip
    q = select(PaySlip).where(cast(PaySlip.employee_id, String) == str(employee_id))
    if competencia:
        q = q.where(PaySlip.reference_period == competencia)
    # LGPD/exatidão: SÓ a linha PAGA conta. Uma competência pode ter 2 linhas — a publicada/paga
    # (portte, fonte da verdade) e um espelho draft ('conecta') com net divergente, além de
    # 'contested' (disputado). Renderizar draft/contested rotulado "PAGO" = fabricação. Então
    # EXIGIMOS status pago; se só houver draft/contested (ocorre em ~5 competências), retorna None
    # → o handler recusa em vez de mostrar um número que não foi o pago.
    q = q.where(PaySlip.status.in_(("published", "rectified")))
    q = q.order_by(PaySlip.reference_year.desc(),
                   PaySlip.reference_month.desc(), PaySlip.id.desc()).limit(1)
    return (await db.execute(q)).scalars().first()


async def _resolve_emp(db, employee_id: str):
    from modules.operacional.models.employee import Employee
    return (await db.execute(
        select(Employee).where(cast(Employee.id, String) == str(employee_id))
    )).scalars().first()


async def _resolve_funcionario(db, termo: str):
    """Resolve o Employee REAL por matrícula/CPF/nome. (emp, None) ou (None, recusa)."""
    from modules.operacional.models.employee import Employee
    t = (termo or "").strip()
    if not t:
        return None, _recusa("diga de quem é o holerite (nome, CPF ou matrícula).")
    digits = "".join(c for c in t if c.isdigit())
    clauses = [Employee.matricula == t, Employee.nome.ilike(f"%{t}%")]
    if len(digits) >= 11:
        clauses.append(_cpf_norm(Employee.cpf) == digits)
    rows = (await db.execute(select(Employee).where(or_(*clauses)))).scalars().all()
    if not rows:
        return None, _recusa(f"não achei o colaborador '{termo}' no cadastro real; confira nome/CPF/matrícula.")
    if len(rows) > 1:
        nomes = ", ".join(r.nome for r in rows[:5])
        return None, _recusa(f"'{termo}' casou com mais de um colaborador ({nomes}); seja mais específico.")
    return rows[0], None


def _resumo(ps, emp, escopo: str) -> str:
    comp = f"{_MESES.get(int(ps.reference_month), ps.reference_month)}/{ps.reference_year}"
    nome = getattr(emp, "nome", None) or "colaborador"
    return (f"Holerite {comp} — {nome}: líquido {_brl(ps.net_salary)} "
            f"(valores PAGOS/persistidos, não recalculado){escopo}")


def _nome_arq(ps, emp) -> str:
    mat = getattr(emp, "matricula", None) or "colaborador"
    slug = "".join(c if c.isalnum() else "_" for c in str(mat))[:30].strip("_") or "colaborador"
    return f"holerite_{slug}_{ps.reference_period}.pdf"


async def _meu_holerite_doc(db, user, scope, *, competencia=None, **_) -> dict[str, Any]:
    # LGPD: a identidade é SEMPRE do escopo — NUNCA um argumento do LLM.
    emp_id = getattr(scope, "employee_id", None) if scope else None
    if not emp_id:
        return _recusa("você não tem vínculo de colaborador ativo; não há holerite pra mostrar.")
    ps = await _resolve_payslip(db, emp_id, (competencia or "").strip() or None)
    if ps is None:
        alvo = f" na competência {competencia}" if competencia else ""
        return _recusa(f"não encontrei holerite pago{alvo}; não recalculo nem invento — só mostro o que foi pago.")
    emp = await _resolve_emp(db, emp_id)
    pdf = holerite_pdf_de_payslip(ps, emp)
    return {
        "arquivo_base64": base64.b64encode(pdf).decode(),
        "nome": _nome_arq(ps, emp),
        "liquido": float(ps.net_salary or 0),
        "resumo": _resumo(ps, emp, ""),
    }


async def _gerar_holerite_funcionario_doc(db, user, scope, *, funcionario=None, competencia=None, **_) -> dict[str, Any]:  # noqa: ARG001
    _gate(user)
    if not (funcionario and str(funcionario).strip()):
        return _recusa("diga de quem é o holerite (nome, CPF ou matrícula do colaborador).")
    emp, recusa = await _resolve_funcionario(db, str(funcionario))
    if recusa:
        return recusa
    ps = await _resolve_payslip(db, str(emp.id), (competencia or "").strip() or None)
    if ps is None:
        alvo = f" na competência {competencia}" if competencia else ""
        return _recusa(f"{emp.nome} não tem holerite pago{alvo}; não recalculo nem invento.")
    pdf = holerite_pdf_de_payslip(ps, emp)
    return {
        "arquivo_base64": base64.b64encode(pdf).decode(),
        "nome": _nome_arq(ps, emp),
        "liquido": float(ps.net_salary or 0),
        "resumo": _resumo(ps, emp, " — doc de RH/DP (dado pessoal LGPD)"),
    }


# self: schema SEM employee_id (LGPD — a identidade vem só do scope, nunca do LLM).
_SCHEMA_SELF = {
    "type": "object",
    "properties": {"competencia": {"type": "string", "description": "Competência AAAA-MM (opcional; vazio = a mais recente)."}},
    "required": [],
}

_SCHEMA_DP = {
    "type": "object",
    "properties": {
        "funcionario": {"type": "string", "description": "Colaborador: nome, CPF ou matrícula (obrigatório)."},
        "competencia": {"type": "string", "description": "Competência AAAA-MM (opcional; vazio = a mais recente)."},
    },
    "required": ["funcionario"],
}

#: self tool exportada para o tier CLT/LÍDER (module="self" nunca sai de tools_for_modules).
RH_SELF_TOOLS: list[ToolDef] = [
    register(ToolDef(
        "meu_holerite_doc", "self",
        "Gera o MEU holerite/contracheque em PDF branded (só do próprio usuário logado), "
        "renderizado do que foi PAGO (contracheque persistido) — nunca recalculado. "
        "Sem holerite no período → recusa (não inventa).",
        _SCHEMA_SELF, _meu_holerite_doc, scope_kind="self")),
]

register(ToolDef(
    "gerar_holerite_funcionario_doc", "dp",
    "Gera o holerite/contracheque de UM COLABORADOR (por nome, CPF ou matrícula) em PDF branded, "
    "renderizado do que foi PAGO (contracheque persistido) — nunca recalculado. Dado pessoal (LGPD): "
    "só DP/diretoria. Colaborador inexistente/ambíguo ou sem holerite no período → recusa. Não grava.",
    _SCHEMA_DP, _gerar_holerite_funcionario_doc, scope_kind="org"))


# ─────────────────────────── ESPELHO DE PONTO (Fatia 7) ───────────────────────────
# Mesma regra LGPD do holerite: self (identidade só do scope) + DP (gated, por nome).
# Espelho = batidas REAIS do motor (time_sheets). Preferimos o FECHADO quando existe
# (o `fechado` flag do ler_espelho diz). NUNCA fabrica dias: sem time_sheet → recusa.

_TZ_MANAUS = ZoneInfo("America/Manaus")


def _norm_mes_ano(mes, ano) -> tuple[int, int]:
    """mes/ano do LLM (int/str/None) → ints; vazio = competência corrente em Manaus."""
    now = datetime.now(_TZ_MANAUS)
    m, a = now.month, now.year
    try:
        if mes not in (None, ""):
            m = int(mes)
        if ano not in (None, ""):
            a = int(ano)
    except (TypeError, ValueError):
        pass
    return m, a


def _espelho_render(employee_id: str, mes: int, ano: int) -> tuple[dict, bytes] | None:
    """(esp, pdf) do espelho REAL, ou None se não há time_sheet no período (anti-fabricação).

    Sessão SÍNCRONA própria: `ler_espelho`/`montar_espelho_ponto_pdf` são sync (o controller
    roda em rota `def`), mas o handler do chat é async — isolamos numa SyncSessionLocal.
    Read-only: só o SELECT do motor + render puro. NÃO chama garantir_homologacao_espelho
    (isso GRAVA a solicitação de assinatura; aqui é read-only).
    """
    from core.database.session import SyncSessionLocal
    from modules.people_management.hr.services.espelho_ponto_pdf import montar_espelho_ponto_pdf
    from modules.people_management.hr.services.espelho_ponto_service import ler_espelho

    with SyncSessionLocal() as s:
        esp = ler_espelho(s, str(employee_id), int(mes), int(ano))
    if not esp:  # sem time_sheet = sem espelho/batida real → o handler recusa
        return None
    return esp, montar_espelho_ponto_pdf(esp)


def _resposta_espelho(esp: dict, pdf: bytes, escopo: str) -> dict[str, Any]:
    mes = int(esp.get("mes") or 0)
    comp = f"{_MESES.get(mes, mes)}/{esp.get('ano')}"
    nome = esp.get("employee_name") or "colaborador"
    origem = "espelho FECHADO" if esp.get("fechado") else f"espelho em aberto (status {esp.get('status') or '—'})"
    mat = esp.get("employee_registration") or nome
    slug = "".join(c if c.isalnum() else "_" for c in str(mat))[:30].strip("_") or "colaborador"
    return {
        "arquivo_base64": base64.b64encode(pdf).decode(),
        "nome": f"espelho_ponto_{slug}_{mes:02d}_{esp.get('ano')}.pdf",
        "fechado": bool(esp.get("fechado")),
        "resumo": (f"Espelho de ponto {comp} — {nome}: {esp.get('horas_trabalhadas')} trabalhadas "
                   f"({origem}, batidas reais do motor){escopo}"),
    }


async def _meu_espelho_ponto_doc(db, user, scope, *, mes=None, ano=None, **_) -> dict[str, Any]:  # noqa: ARG001
    # LGPD: a identidade é SEMPRE do escopo — NUNCA um argumento do LLM (schema sem employee_id).
    emp_id = getattr(scope, "employee_id", None) if scope else None
    if not emp_id:
        return _recusa("você não tem vínculo de colaborador ativo; não há espelho de ponto pra mostrar.")
    m, a = _norm_mes_ano(mes, ano)
    res = await asyncio.to_thread(_espelho_render, str(emp_id), m, a)
    if res is None:
        return _recusa(f"não há registro de ponto (espelho) em {m:02d}/{a}; não invento batidas.")
    esp, pdf = res
    return _resposta_espelho(esp, pdf, "")


async def _gerar_espelho_ponto_funcionario_doc(db, user, scope, *, funcionario=None, mes=None, ano=None, **_) -> dict[str, Any]:  # noqa: ARG001
    _gate(user)
    if not (funcionario and str(funcionario).strip()):
        return _recusa("diga de quem é o espelho de ponto (nome, CPF ou matrícula do colaborador).")
    emp, recusa = await _resolve_funcionario(db, str(funcionario))
    if recusa:
        return recusa
    m, a = _norm_mes_ano(mes, ano)
    res = await asyncio.to_thread(_espelho_render, str(emp.id), m, a)
    if res is None:
        return _recusa(f"{emp.nome} não tem registro de ponto (espelho) em {m:02d}/{a}; não invento batidas.")
    esp, pdf = res
    return _resposta_espelho(esp, pdf, " — doc de RH/DP (dado pessoal LGPD)")


# self: schema SEM employee_id/funcionario (LGPD — identidade só do scope).
_SCHEMA_ESPELHO_SELF = {
    "type": "object",
    "properties": {
        "mes": {"type": "integer", "description": "Mês 1-12 (opcional; vazio = mês corrente)."},
        "ano": {"type": "integer", "description": "Ano AAAA (opcional; vazio = ano corrente)."},
    },
    "required": [],
}

_SCHEMA_ESPELHO_DP = {
    "type": "object",
    "properties": {
        "funcionario": {"type": "string", "description": "Colaborador: nome, CPF ou matrícula (obrigatório)."},
        "mes": {"type": "integer", "description": "Mês 1-12 (opcional; vazio = mês corrente)."},
        "ano": {"type": "integer", "description": "Ano AAAA (opcional; vazio = ano corrente)."},
    },
    "required": ["funcionario"],
}

RH_SELF_TOOLS.append(
    register(ToolDef(
        "meu_espelho_ponto_doc", "self",
        "Gera o MEU espelho de ponto do mês em PDF branded (Portaria 671) — só do próprio usuário logado, "
        "com as batidas REAIS apuradas pelo motor (prefere o espelho FECHADO quando existe). "
        "Nunca inventa dias/batidas. Sem registro de ponto no período → recusa.",
        _SCHEMA_ESPELHO_SELF, _meu_espelho_ponto_doc, scope_kind="self")))

register(ToolDef(
    "gerar_espelho_ponto_funcionario_doc", "dp",
    "Gera o espelho de ponto de UM COLABORADOR (por nome, CPF ou matrícula) em PDF branded (Portaria 671), "
    "com as batidas REAIS apuradas pelo motor (prefere o FECHADO quando existe). Dado pessoal (LGPD): "
    "só DP/diretoria. Colaborador inexistente/ambíguo ou sem registro de ponto no período → recusa. Não grava.",
    _SCHEMA_ESPELHO_DP, _gerar_espelho_ponto_funcionario_doc, scope_kind="org"))
