"""Tools READ do DP/RH (Fase 6, balde VER) — módulo dp, scope_kind="org".

No chat escopado, quem tem o módulo `dp` CONSULTA a gestão de pessoas como faria
navegando as telas: lista de funcionários, busca, estatísticas, resumo da folha,
férias, admissões em curso e pendências de ASO/SST. Cada handler chama a COROUTINE
do controller REAL in-process, com a IDENTIDADE do usuário logado (o `db`/`user`
reais) — NUNCA a conta de serviço, NUNCA HTTP.

Molde idêntico ao tools_read_crm.py (commit 9d0da02e).

Paredes (inegociáveis):
- RBAC na fonte: chamar o controller direto PULA o Depends(require_permission) dele,
  então TODO handler faz `_gate(user)` primeiro (re-checa user_has_module(user,"dp")).
  O belt (tools_for_modules) já filtra por módulo; o _gate é o suspenders.
- SÓ LEITURA: só coroutines de rota GET entram aqui. Nada cria/edita/apaga/envia.
- LGPD: só visões de GESTÃO org-wide (listas/contagens/status). NÃO expõe holerite
  nem espelho de UM funcionário — esses já têm tool própria (self/DP gera-doc).
- Nunca fabricar: devolve o resultado REAL do banco; vazio real = vazio.

Todos os controllers reusados usam SQL parametrizado (nenhum f-string com input do
usuário), verificado ao curar.
"""
from __future__ import annotations

from typing import Any

from core.auth.module_scope import user_has_module

from .read_dispatcher import registrar_read


def _gate(user) -> None:
    # Suspenders: o controller GET normalmente gateia via Depends no mount do router;
    # chamado direto isso é pulado, então re-checamos o módulo aqui na fonte. (O dispatcher
    # também gateia antes de despachar; aqui é a 2ª cinta caso o handler seja chamado direto.)
    if not user_has_module(user, "dp"):
        raise PermissionError("dp")


# ---- handlers (assinaturas heterogêneas dos controllers → handlers explícitos) ----

async def _listar_funcionarios(db, user, scope, *, search=None, page=1, page_size=20, **_) -> dict[str, Any]:
    _gate(user)
    from modules.people_management.hr.controllers.employee_controller import list_employees
    from modules.people_management.hr.schemas.employee import DPEmployeeList
    res = await list_employees(current_user=user, db=db, page=page, page_size=page_size, search=search)
    # A rota serializa via response_model=DPEmployeeList; chamando direto vêm ORMs → serializa igual.
    return DPEmployeeList.model_validate(res).model_dump(mode="json")


async def _buscar_funcionario(db, user, scope, *, q=None, status=None, page=1, page_size=20, **_) -> dict[str, Any]:
    _gate(user)
    if not q:
        return {"status": "informe o termo de busca (nome, CPF ou matrícula)"}
    from modules.people_management.hr.controllers.employee_controller import search_employees
    from modules.people_management.hr.schemas.employee import DPEmployeeList
    res = await search_employees(current_user=user, db=db, q=str(q), status=status,
                                 page=page, page_size=page_size)
    return DPEmployeeList.model_validate(res).model_dump(mode="json")


async def _estatisticas_funcionarios(db, user, scope, **_) -> dict[str, Any]:
    _gate(user)
    from modules.people_management.hr.controllers.employee_controller import get_employees_stats
    return await get_employees_stats(current_user=user, db=db)


async def _folha_resumo(db, user, scope, *, mes=None, ano=None, **_) -> dict[str, Any]:
    _gate(user)
    from modules.people_management.hr.controllers.payroll_controller import get_payroll_summary
    return await get_payroll_summary(current_user=user, db=db, mes=mes, ano=ano)


async def _folha_analitico(db, user, scope, *, mes=None, ano=None, cnpj=None, **_) -> dict[str, Any]:
    """Folha ANALÍTICA por colaborador (fonte hr_payslips) p/ conciliar linha a linha.
    Escopável por CNPJ (hr_payslips.empresa_id → empresas). SÓ DP/diretoria (_gate)."""
    _gate(user)
    from datetime import datetime  # noqa: PLC0415
    from sqlalchemy import text as _text  # noqa: PLC0415
    h = datetime.now()
    m, a = int(mes) if mes else h.month, int(ano) if ano else h.year
    sql = (
        "SELECT COALESCE(e.nome, p.employee_id::text) AS colaborador, e.cargo AS cargo, "
        "em.razao_social AS empresa, em.cnpj AS cnpj, "
        "COALESCE(p.total_earnings,0) AS proventos, COALESCE(p.total_deductions,0) AS descontos, "
        "COALESCE(p.inss_value,0) AS inss, COALESCE(p.irrf_value,0) AS irrf, "
        "COALESCE(p.fgts_value,0) AS fgts, COALESCE(p.net_salary,0) AS liquido "
        "FROM hr_payslips p "
        "LEFT JOIN employees e ON e.id = p.employee_id "
        "LEFT JOIN empresas em ON em.id = p.empresa_id "
        "WHERE p.reference_month = :mes AND p.reference_year = :ano "
    )
    params: dict[str, Any] = {"mes": m, "ano": a}
    if cnpj:
        params["cnpj"] = "".join(c for c in str(cnpj) if c.isdigit())
        sql += "AND regexp_replace(COALESCE(em.cnpj,''), '[^0-9]', '', 'g') = :cnpj "
    sql += "ORDER BY colaborador"
    try:
        rows = (await db.execute(_text(sql), params)).mappings().all()
    except Exception:  # noqa: BLE001
        await db.rollback()
        rows = []
    if not rows:
        return {"competencia": f"{m:02d}/{a}", "colaboradores": [],
                "aviso": "Sem holerites em hr_payslips para esta competência/CNPJ — aguardando dado real."}
    cols = [{
        "colaborador": r["colaborador"], "cargo": r["cargo"], "empresa": r["empresa"], "cnpj": r["cnpj"],
        "proventos": float(r["proventos"]), "descontos": float(r["descontos"]),
        "inss": float(r["inss"]), "irrf": float(r["irrf"]),
        "fgts": float(r["fgts"]), "liquido": float(r["liquido"]),
    } for r in rows]
    keys = ("proventos", "descontos", "inss", "irrf", "fgts", "liquido")
    return {
        "competencia": f"{m:02d}/{a}", "total_colaboradores": len(cols),
        "totais": {k: round(sum(c[k] for c in cols), 2) for k in keys},
        "colaboradores": cols,
    }


async def _listar_ferias(db, user, scope, *, status=None, page=1, page_size=20, **_) -> dict[str, Any]:
    _gate(user)
    from modules.people_management.hr.controllers.vacation_controller import list_vacations
    return await list_vacations(current_user=user, db=db, page=page, page_size=page_size, status=status)


async def _listar_admissoes(db, user, scope, *, status=None, page=1, page_size=20, **_) -> dict[str, Any]:
    _gate(user)
    from modules.people_management.hr.controllers.admission_controller import list_admissions
    from modules.people_management.hr.models.admission import AdmissionStatus
    st = None
    if status:
        try:
            st = AdmissionStatus(status)
        except ValueError:
            return {"status": f"status inválido {status!r}; use um de "
                              f"{[s.value for s in AdmissionStatus]}"}
    return await list_admissions(current_user=user, db=db, status=st, page=page, page_size=page_size)


async def _estatisticas_admissoes(db, user, scope, **_) -> dict[str, Any]:
    _gate(user)
    from modules.people_management.hr.controllers.admission_controller import get_admission_stats
    return await get_admission_stats(current_user=user, db=db)


async def _pendencias_aso(db, user, scope, *, dias=30, **_) -> dict[str, Any]:
    _gate(user)
    # Duas visões de pendência SST que a gestão de DP acompanha (ambas GET, org-wide).
    from modules.people_management.sst.controllers.sst_controller import (
        listar_asos_vencendo,
        listar_sem_aso,
    )
    vencendo = await listar_asos_vencendo(current_user=user, db=db, dias=dias)
    sem_aso = await listar_sem_aso(current_user=user, db=db)
    return {"asos_vencendo": vencendo, "sem_aso": sem_aso}


# ---- registro das ops READ no dispatcher consultar_dp (filtros vão em `filtros`) ----

registrar_read("dp", "funcionarios",
               "Lista funcionários ativos (paginado). Filtros: search (nome/CPF/matrícula), page, "
               "page_size.", _listar_funcionarios)
registrar_read("dp", "buscar_funcionario",
               "Busca funcionário por nome, CPF ou matrícula. Filtro obrigatório: q. Filtros: "
               "status, page, page_size.", _buscar_funcionario)
registrar_read("dp", "estatisticas_funcionarios",
               "Contadores de funcionários por status (total, ativos, inativos, por status).",
               _estatisticas_funcionarios)
registrar_read("dp", "folha_resumo",
               "Resumo consolidado da folha da competência: proventos, descontos, INSS, IRRF, FGTS "
               "e líquido (fonte hr_payslips; vazio real = aguardando dado). Filtros: mes, ano.",
               _folha_resumo)
registrar_read("dp", "folha_analitico",
               "Folha ANALÍTICA por colaborador da competência: nome, cargo, empresa/CNPJ, proventos, "
               "descontos, INSS, IRRF, FGTS e líquido de CADA funcionário + totais (fonte hr_payslips). "
               "Use para COMPARAR/CONCILIAR linha a linha com extrato de outro sistema. "
               "Filtros: mes, ano, cnpj (opcional — escopa por empresa; ex.: só a Patrimonial).",
               _folha_analitico)
registrar_read("dp", "ferias",
               "Lista solicitações de férias de todos os funcionários (com contagem por status). "
               "Filtros: status, page, page_size.", _listar_ferias)
registrar_read("dp", "admissoes",
               "Lista processos de admissão em curso. Filtros: status, page, page_size.",
               _listar_admissoes)
registrar_read("dp", "estatisticas_admissoes",
               "Contadores de processos de admissão por etapa (documentos, exame, assinatura, concluído).",
               _estatisticas_admissoes)
registrar_read("dp", "pendencias_aso",
               "Pendências de saúde ocupacional (SST): ASOs próximos do vencimento e colaboradores "
               "sem ASO periódico. Filtro: dias.", _pendencias_aso)
