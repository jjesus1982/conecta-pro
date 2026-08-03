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

from .tool_registry import ToolDef, register


def _gate(user) -> None:
    # Suspenders: o controller GET normalmente gateia via Depends no mount do router;
    # chamado direto isso é pulado, então re-checamos o módulo aqui na fonte.
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


# ---- schemas (SÓ filtros de negócio; nunca db/user/scope — o registry proíbe) ----

_NO_ARGS = {"type": "object", "properties": {}}

_S_FUNCS = {"type": "object", "properties": {
    "search": {"type": "string", "description": "Busca por nome, CPF ou matrícula."},
    "page": {"type": "integer"}, "page_size": {"type": "integer"},
}}

_S_BUSCA = {"type": "object", "properties": {
    "q": {"type": "string", "description": "Termo de busca (nome, CPF ou matrícula)."},
    "status": {"type": "string", "description": "Filtrar por status (ativo/inativo)."},
    "page": {"type": "integer"}, "page_size": {"type": "integer"},
}, "required": ["q"]}

_S_FOLHA = {"type": "object", "properties": {
    "mes": {"type": "integer", "description": "Mês 1-12 (padrão: última competência com folha)."},
    "ano": {"type": "integer", "description": "Ano (padrão: última competência com folha)."},
}}

_S_FERIAS = {"type": "object", "properties": {
    "status": {"type": "string", "description": "Status: pendente, aprovado, rejeitado, cancelado."},
    "page": {"type": "integer"}, "page_size": {"type": "integer"},
}}

_S_ADMISSOES = {"type": "object", "properties": {
    "status": {"type": "string", "description": "Status: documents_pending, medical_exam, "
               "contract_signing, completed, cancelled."},
    "page": {"type": "integer"}, "page_size": {"type": "integer"},
}}

_S_ASO = {"type": "object", "properties": {
    "dias": {"type": "integer", "description": "Antecedência em dias para ASO vencendo (1-90)."},
}}


register(ToolDef("dp_listar_funcionarios", "dp",
                 "Lista funcionários ativos (paginado), com busca opcional por nome, CPF ou matrícula.",
                 _S_FUNCS, _listar_funcionarios, scope_kind="org"))
register(ToolDef("dp_buscar_funcionario", "dp",
                 "Busca funcionário por nome, CPF ou matrícula (visão de cadastro/DP).",
                 _S_BUSCA, _buscar_funcionario, scope_kind="org"))
register(ToolDef("dp_estatisticas_funcionarios", "dp",
                 "Contadores de funcionários por status (total, ativos, inativos, por status).",
                 _NO_ARGS, _estatisticas_funcionarios, scope_kind="org"))
register(ToolDef("dp_folha_resumo", "dp",
                 "Resumo consolidado da folha da competência: proventos, descontos, INSS, IRRF, FGTS "
                 "e líquido (fonte hr_payslips; vazio real = aguardando dado).",
                 _S_FOLHA, _folha_resumo, scope_kind="org"))
register(ToolDef("dp_listar_ferias", "dp",
                 "Lista solicitações de férias de todos os funcionários (com contagem por status).",
                 _S_FERIAS, _listar_ferias, scope_kind="org"))
register(ToolDef("dp_listar_admissoes", "dp",
                 "Lista processos de admissão em curso, com filtro opcional por status.",
                 _S_ADMISSOES, _listar_admissoes, scope_kind="org"))
register(ToolDef("dp_estatisticas_admissoes", "dp",
                 "Contadores de processos de admissão por etapa (documentos, exame, assinatura, concluído).",
                 _NO_ARGS, _estatisticas_admissoes, scope_kind="org"))
register(ToolDef("dp_pendencias_aso", "dp",
                 "Pendências de saúde ocupacional (SST): ASOs próximos do vencimento e colaboradores "
                 "sem ASO periódico.", _S_ASO, _pendencias_aso, scope_kind="org"))
