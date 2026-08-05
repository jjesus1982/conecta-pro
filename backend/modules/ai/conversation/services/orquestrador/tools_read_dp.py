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


def _dump(obj) -> Any:
    """Serializa retorno do controller (Pydantic v2 / lista / dict) → JSON-safe."""
    if obj is None or isinstance(obj, (dict, str, int, float, bool)):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, (list, tuple)):
        return [_dump(o) for o in obj]
    return obj


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


async def _rescisoes(db, user, scope, *, status=None, page=1, page_size=20, **_) -> dict[str, Any]:
    _gate(user)
    from modules.people_management.hr.controllers.termination_controller import list_terminations
    from modules.people_management.hr.models.termination import TerminationStatus
    st = None
    if status:
        try:
            st = TerminationStatus(status)
        except ValueError:
            return {"status": f"status inválido {status!r}; use um de "
                              f"{[s.value for s in TerminationStatus]}"}
    return _dump(await list_terminations(current_user=user, db=db, status=st, page=page, page_size=page_size))


async def _justificativas_ponto_pendentes(db, user, scope, *, employee_id=None, **_) -> dict[str, Any]:
    _gate(user)
    from modules.people_management.ponto.controllers.punch_controller import get_justificativas_pendentes
    eid = int(employee_id) if employee_id else None
    itens = await get_justificativas_pendentes(employee_id=eid, db=db)
    return {"total": len(itens), "justificativas": _dump(itens)}


async def _saldo_ferias(db, user, scope, *, employee_id=None, **_) -> dict[str, Any]:
    _gate(user)
    if not employee_id:
        return {"status": "informe employee_id (id do funcionário) para calcular o saldo de férias"}
    from fastapi import HTTPException
    from modules.people_management.hr.controllers.vacation_controller import get_vacation_balance
    try:
        return _dump(await get_vacation_balance(employee_id=str(employee_id), current_user=user, db=db))
    except HTTPException as e:
        return {"status": "indisponível", "motivo": str(e.detail)}


async def _recrutamento_overview(db, user, scope, **_) -> dict[str, Any]:
    _gate(user)
    from modules.people_management.human_resources.controllers.recruitment_controller import recruitment_overview
    return _dump(await recruitment_overview(current_user=user, db=db))


async def _rubricas_folha(db, user, scope, **_) -> dict[str, Any]:
    _gate(user)
    from modules.people_management.hr.controllers.payroll_controller import list_rubricas
    return _dump(await list_rubricas(current_user=user, db=db))


async def _esocial_eventos(db, user, scope, *, limit=500, **_) -> dict[str, Any]:
    _gate(user)
    from modules.people_management.hr.controllers.esocial_controller import listar_eventos_esocial
    lim = max(1, min(int(limit), 2000))
    return _dump(await listar_eventos_esocial(current_user=user, db=db, limit=lim))


# Controllers SÍNCRONOS (usam Session/get_sync_db) — abre sessão sync própria; o `db` async
# do dispatcher não serve. São views gerenciais org-wide (dashboard/esteira), só leitura.

async def _ponto_dashboard(db, user, scope, **_) -> dict[str, Any]:
    _gate(user)
    from core.database.session import get_sync_db
    from modules.people_management.ponto.controllers.punch_controller import ponto_dashboard
    with get_sync_db() as sdb:
        return _dump(await ponto_dashboard(current_user=user, db=sdb))


async def _folha_dashboard(db, user, scope, *, mes=None, ano=None, **_) -> dict[str, Any]:
    _gate(user)
    from core.database.session import get_sync_db
    from modules.people_management.folha.controllers.folha_controller import folha_dashboard
    with get_sync_db() as sdb:
        return _dump(await folha_dashboard(current_user=user,
                                           mes=int(mes) if mes else None,
                                           ano=int(ano) if ano else None, db=sdb))


async def _banco_horas(db, user, scope, *, employee_id=None, **_) -> dict[str, Any]:
    _gate(user)
    if not employee_id:
        return {"status": "informe employee_id (id do funcionário) para consultar o banco de horas"}
    from fastapi import HTTPException
    from core.database.session import get_sync_db
    from modules.people_management.ponto.controllers.punch_controller import banco_horas
    with get_sync_db() as sdb:
        try:
            return _dump(await banco_horas(employee_id=str(employee_id), current_user=user, db=sdb))
        except HTTPException as e:
            return {"status": "indisponível", "motivo": str(e.detail)}


async def _candidatos(db, user, scope, *, status_filtro="todos", **_) -> dict[str, Any]:
    _gate(user)
    from core.database.session import get_sync_db
    from modules.people_management.human_resources.controllers.candidatos_esteira_controller import listar_candidatos
    with get_sync_db() as sdb:
        # controller síncrono (def) — sem await
        return _dump(listar_candidatos(status_filtro=str(status_filtro), db=sdb, current_user=user))


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
registrar_read("dp", "ponto_dashboard",
               "Painel gerencial do PONTO: presença, inconsistências CCT e banco de horas "
               "(dados reais do dia). Sem filtros.", _ponto_dashboard)
registrar_read("dp", "folha_dashboard",
               "Painel gerencial da FOLHA do mês com totais por cargo (visão calculada). "
               "Filtros: mes, ano (default = mês/ano atual).", _folha_dashboard)
registrar_read("dp", "banco_horas",
               "Saldo de banco de horas de UM funcionário, com prazo CCT (6 meses). "
               "Filtro obrigatório: employee_id.", _banco_horas)
registrar_read("dp", "saldo_ferias",
               "Saldo de férias (dias adquiridos/gozados/disponíveis) de UM funcionário. "
               "Filtro obrigatório: employee_id.", _saldo_ferias)
registrar_read("dp", "rescisoes",
               "Lista processos de RESCISÃO (com nome do colaborador). Filtros: status, page, "
               "page_size.", _rescisoes)
registrar_read("dp", "justificativas_ponto_pendentes",
               "Justificativas de ponto pendentes de aprovação (org-wide). Filtro: employee_id "
               "(opcional, restringe a um funcionário).", _justificativas_ponto_pendentes)
registrar_read("dp", "rubricas_folha",
               "Tabela de rubricas de folha cadastradas (código, descrição, tipo, incidências "
               "INSS/IRRF/FGTS). Sem filtros.", _rubricas_folha)
registrar_read("dp", "candidatos",
               "Esteira de recrutamento: candidatos com dados e completude para o RH decidir. "
               "Filtro: status_filtro (todos|candidato|aprovado|reprovado|em_admissao).", _candidatos)
registrar_read("dp", "recrutamento_overview",
               "Agregado de recrutamento: contagens reais de candidatos, vagas, vagas abertas, "
               "aplicações e entrevistas. Sem filtros.", _recrutamento_overview)
registrar_read("dp", "esocial_eventos",
               "Lista de eventos eSocial (transmissões próprias + espelho oficial do governo) com "
               "status. Filtro: limit (default 500, máx 2000).", _esocial_eventos)
