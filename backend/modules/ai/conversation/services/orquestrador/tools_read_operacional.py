"""Tools READ do OPERACIONAL (Fase 6, balde VER) — módulo operacional, scope_kind="org".

No chat escopado, quem tem o módulo `operacional` CONSULTA a operação como faria
navegando as telas: postos, escalas, alocações, ocorrências, rondas, grade, presença
ao vivo e o dashboard operacional. Cada handler chama a COROUTINE do controller REAL
in-process, com a IDENTIDADE do usuário logado (`db`/`user` reais) — NUNCA a conta de
serviço, NUNCA HTTP.

Paredes (inegociáveis):
- RBAC na fonte: chamar o controller direto PULA o Depends(require_permission) dele,
  então TODO handler faz `_gate(user)` primeiro (re-checa user_has_module(user,"operacional")).
  O belt (tools_for_modules) já filtra por módulo; o _gate é o suspenders.
- SÓ LEITURA: o operacional é curado à mão pelo dono, read-only para agentes. Só coroutines
  de rota GET entram aqui. Nada cria/edita/apaga posto, escala, alocação ou ronda.
- Escopo por posto: os controllers que recebem OperationalScope (grade/ocorrências/presença)
  continuam escopados — líder vê só os postos que lidera; gestor vê tudo. Reusamos o mesmo
  get_operational_scope com a identidade real (o SQL deles já é parametrizado).
- Nunca fabricar: devolve o resultado REAL do banco; vazio real = vazio, não número inventado.
"""
from __future__ import annotations

from typing import Any

from core.auth.module_scope import user_has_module

from .read_dispatcher import registrar_read

_MOD = "operacional"


def _gate(user) -> None:
    # Suspenders: o GET normalmente gateia via Depends no mount do router; chamado direto
    # isso é pulado, então re-checamos o módulo aqui na fonte com a identidade real.
    if not user_has_module(user, _MOD):
        raise PermissionError(_MOD)


def _dump(res) -> Any:
    # Controllers ora devolvem Pydantic (response_model), ora dict cru (ex.: dashboard/grade,
    # cujo service já retorna dict). Normaliza p/ o engine serializar em JSON.
    return res.model_dump(mode="json") if hasattr(res, "model_dump") else res


async def _op_scope(db, user):
    # OperationalScope real (líder=só seus postos, gestor=all_posts) p/ os controllers
    # que o exigem — mesma identidade do usuário logado.
    from modules.operacional.scope import get_operational_scope
    return await get_operational_scope(current_user=user, db=db)


# ---- handlers (assinaturas heterogêneas dos controllers → handlers explícitos) ----

async def _postos(db, user, scope, *, status=None, search=None, post_type=None,
                  page=1, page_size=20, **_) -> dict[str, Any]:
    _gate(user)
    from modules.operacional.controllers.post_controller import list_posts
    res = await list_posts(current_user=user, db=db, page=page, page_size=page_size,
                           post_type=post_type, status_filter=status, shift_type=None,
                           contract_id=None, client_id=None, city=None, state=None,
                           requires_armed=None, requires_vehicle=None, has_vacancy=None,
                           search=search)
    return _dump(res)


async def _escalas(db, user, scope, *, status=None, post_id=None, month=None, year=None,
                   page=1, page_size=20, **_) -> dict[str, Any]:
    _gate(user)
    from modules.operacional.controllers.scale_controller import list_scales
    res = await list_scales(current_user=user, db=db, page=page, page_size=page_size,
                            post_id=post_id, scale_type=None, status_filter=status,
                            month=month, year=year, is_current_month=None, created_by=None)
    return _dump(res)


async def _alocacoes(db, user, scope, *, status=None, post_id=None, employee_id=None,
                     is_current=None, page=1, page_size=20, **_) -> dict[str, Any]:
    _gate(user)
    from modules.operacional.controllers.allocation_controller import list_allocations
    res = await list_allocations(current_user=user, db=db, page=page, page_size=page_size,
                                 post_id=post_id, employee_id=employee_id, status_filter=status,
                                 is_primary=None, is_temporary=None, is_current=is_current,
                                 start_date_from=None, start_date_to=None)
    return _dump(res)


async def _ocorrencias(db, user, scope, *, status=None, post_id=None, severity=None,
                       search=None, page=1, page_size=20, **_) -> dict[str, Any]:
    _gate(user)
    from modules.operacional.occurrences.controllers.occurrence_controller import list_occurrences
    op = await _op_scope(db, user)
    res = await list_occurrences(current_user=user, scope=op, db=db, page=page,
                                 page_size=page_size, occurrence_type=None, severity=severity,
                                 category=None, status_filter=status, employee_id=None,
                                 inspector_id=None, post_id=post_id, patrol_round_id=None,
                                 date_from=None, date_to=None, search=search)
    return _dump(res)


async def _rondas(db, user, scope, *, status=None, page=1, page_size=10, **_) -> dict[str, Any]:
    _gate(user)
    from modules.operacional.inspection_rounds.controllers.inspection_round_controller import (
        get_inspection_service,
        list_rounds,
    )
    res = await list_rounds(current_user=user, tenant_id=None, page=page, page_size=page_size,
                            skip=0, limit=100, inspector_id=None, inspector_role=None,
                            status_filter=status, start_date=None, end_date=None,
                            has_occurrences=None, has_disciplinary_actions=None,
                            service=get_inspection_service(db))
    return _dump(res)


async def _grade_postos(db, user, scope, **_) -> dict[str, Any]:
    _gate(user)
    from modules.operacional.controllers.grade_controller import grade_postos
    op = await _op_scope(db, user)
    return await grade_postos(scope=op, db=db)  # já retorna dict


async def _dashboard(db, user, scope, **_) -> dict[str, Any]:
    _gate(user)
    from modules.operacional.controllers.dashboard_controller import get_dashboard
    res = await get_dashboard(current_user=user, data=None, cliente_id=None, db=db)
    return _dump(res)


async def _presenca_ao_vivo(db, user, scope, **_) -> dict[str, Any]:
    _gate(user)
    from modules.operacional.presence.controllers.presence_controller import quadro_presenca_hoje
    op = await _op_scope(db, user)
    res = await quadro_presenca_hoje(data=None, scope=op, db=db)
    return _dump(res)


async def _grade_do_posto(db, user, scope, *, post_id=None, posto_id=None, mes=None, ano=None,
                          **_) -> dict[str, Any]:
    _gate(user)
    pid = post_id or posto_id
    if not pid:
        return {"status": "informe post_id (id do posto) para ver a grade por pessoa"}
    from modules.operacional.controllers.grade_controller import grade_do_posto
    op = await _op_scope(db, user)
    return await grade_do_posto(post_id=str(pid), mes=int(mes) if mes else None,
                                ano=int(ano) if ano else None, scope=op, db=db)


async def _alocacoes_vigentes(db, user, scope, *, post_id=None, **_) -> Any:
    _gate(user)
    from modules.operacional.controllers.allocation_controller import get_current_allocations
    return _dump(await get_current_allocations(current_user=user, db=db, post_id=post_id))


async def _substituicoes_pendentes(db, user, scope, *, post_id=None, **_) -> Any:
    _gate(user)
    from modules.operacional.controllers.substitution_controller import get_pending_substitutions
    return _dump(await get_pending_substitutions(current_user=user, db=db, post_id=post_id))


async def _relatorio_cobertura(db, user, scope, *, start_date=None, end_date=None, post_id=None,
                               **_) -> Any:
    _gate(user)
    from datetime import date
    from modules.operacional.controllers.reports_controller import coverage_report
    sd = date.fromisoformat(start_date) if start_date else None
    ed = date.fromisoformat(end_date) if end_date else None
    return _dump(await coverage_report(_user=user, db=db, start_date=sd, end_date=ed, post_id=post_id))


async def _colaboradores_sem_escala(db, user, scope, **_) -> Any:
    _gate(user)
    # controller síncrono (usa Session) — abre sessão sync própria; o db async não serve.
    from core.database.session import get_sync_db
    from modules.people_management.ponto.controllers.punch_controller import colaboradores_sem_escala
    with get_sync_db() as sdb:
        return _dump(await colaboradores_sem_escala(current_user=user, db=sdb))


async def _dashboard_campo(db, user, scope, **_) -> Any:
    _gate(user)
    from modules.campo.controllers.campo_service_controller import campo_dashboard
    return _dump(await campo_dashboard(current_user=user, session=db))


async def _visitas_campo(db, user, scope, *, status=None, busca=None, page=1, page_size=50,
                         **_) -> Any:
    _gate(user)
    from modules.campo.schemas.visita import VisitaFiltro
    from modules.campo.services.visita_service import VisitaService
    filtro = VisitaFiltro(status=status, busca=busca)
    return _dump(await VisitaService(db).listar_visitas(filtro, int(page), int(page_size)))


async def _panorama(db, user, scope, **_) -> Any:
    _gate(user)
    # Panorama COO — postos, cobertura, escalas, diaristas e vínculos (CLT×diária) que o
    # Consultor de Operações usa como âncora. Só leitura.
    from modules.operacional.services import consultor_coo_service
    return _dump(await consultor_coo_service.panorama(db))


# ---- registro das ops READ no dispatcher consultar_operacional (filtros vão em `filtros`) ----

registrar_read(_MOD, "postos",
               "Lista os postos de trabalho (com filtros). Filtros opcionais: status, "
               "post_type, search, page, page_size.", _postos)
registrar_read(_MOD, "escalas",
               "Lista as escalas do mês por posto. Filtros: status, post_id, month, year, "
               "page, page_size.", _escalas)
registrar_read(_MOD, "alocacoes",
               "Lista as alocações de colaboradores em postos. Filtros: status, post_id, "
               "employee_id, is_current, page, page_size.", _alocacoes)
registrar_read(_MOD, "ocorrencias",
               "Lista as ocorrências operacionais (escopadas por posto). Filtros: status, "
               "post_id, severity, search, page, page_size.", _ocorrencias)
registrar_read(_MOD, "rondas",
               "Lista as rondas de inspeção. Filtros: status, page, page_size.", _rondas)
registrar_read(_MOD, "grade_postos",
               "Grade do mês corrente: postos ativos do escopo com nº de pessoas na grade.",
               _grade_postos)
registrar_read(_MOD, "dashboard",
               "Dashboard operacional unificado do dia (postos, escalas, ocupação, diaristas, "
               "alertas).", _dashboard)
registrar_read(_MOD, "presenca_ao_vivo",
               "Quadro de presença do dia (esperados × presença real por posto, escopado).",
               _presenca_ao_vivo)
registrar_read(_MOD, "grade_do_posto",
               "Grade por PESSOA de um posto no mês (padrão derivado dos turnos reais). Filtros: "
               "post_id (obrigatório), mes, ano.", _grade_do_posto)
registrar_read(_MOD, "alocacoes_vigentes",
               "Alocações vigentes (ativas neste momento). Filtro opcional: post_id.",
               _alocacoes_vigentes)
registrar_read(_MOD, "substituicoes_pendentes",
               "Substituições pendentes (faltas aguardando confirmação de substituto). Filtro "
               "opcional: post_id.", _substituicoes_pendentes)
registrar_read(_MOD, "relatorio_cobertura",
               "Relatório de cobertura (postos × alocações, taxa de cobertura no período). Filtros: "
               "start_date, end_date ('AAAA-MM-DD'), post_id.", _relatorio_cobertura)
registrar_read(_MOD, "colaboradores_sem_escala",
               "Colaboradores ativos SEM escala definida (precisam de correção no DP). Sem filtros.",
               _colaboradores_sem_escala)
registrar_read(_MOD, "dashboard_campo",
               "Painel do módulo de CAMPO (agentes em campo, check-ins do dia, ocorrências, "
               "alertas). Sem filtros.", _dashboard_campo)
registrar_read(_MOD, "visitas_campo",
               "Lista visitas de campo (técnicas/comerciais). Filtros: status, busca, page, "
               "page_size.", _visitas_campo)
registrar_read(_MOD, "panorama",
               "Panorama COO consolidado (dados reais): postos e cobertura (postos descobertos), "
               "escalas, alocações, diaristas e vínculos (CLT×diária). Fotografia gerencial da "
               "operação agora. Sem filtros.", _panorama)


# ── COMUNICADOS NÃO LIDOS (7ª das 14 — leitura) ──────────────────────────────────────
# Rota real: GET /operacional/comunicados/nao-lidos · corrotina
# `operacional/communication/controllers/announcement_controller.py:179`.
# Reusa a corrotina da TELA, com a identidade real de quem pergunta — o "não lido" é POR
# PESSOA, então esta consulta só existe direito com identidade, e in-process ela já é real.
async def _comunicados_nao_lidos(db, user, scope, *, page=1, page_size=20, **_) -> Any:
    _gate(user)
    from modules.operacional.communication.controllers.announcement_controller import (
        list_unread_announcements,
    )
    return _dump(await list_unread_announcements(current_user=user, db=db,
                                                 page=int(page), page_size=int(page_size)))


registrar_read(_MOD, "comunicados_nao_lidos",
               "Comunicados internos que VOCÊ ainda não leu (o sino do ERP). Filtros: page, "
               "page_size. É por pessoa — mostra os seus, não os de todo mundo.",
               _comunicados_nao_lidos)


async def _comunicados(db, user, scope, *, status=None, categoria=None, busca=None,
                       limite=20, **_) -> Any:
    """Comunicados internos publicados/agendados. Rota GET /operacional/comunicados.

    ⚠️ MÓDULO: existem DOIS `comunicados` na casa — este é o de RH/operação
    (`operacional/communication`); o outro é o do portal do funcionário
    (`people_management/employee_portal`), que é self-only por LGPD e NÃO entra aqui.
    """
    _gate(user)
    from modules.operacional.communication.controllers.announcement_controller import (
        list_announcements,
    )

    res = await list_announcements(
        current_user=user, db=db, page=1, page_size=max(1, min(int(limite), 100)),
        status_filter=status, priority=None, category=categoria, target_type=None,
        requires_acknowledgment=None, search=busca)
    return res.model_dump(mode="json") if hasattr(res, "model_dump") else res


registrar_read(_MOD, "comunicados",
               "Comunicados internos (mural). Filtros: status, categoria, busca, limite "
               "(padrão 20).", _comunicados)


# ── DIÁRIAS / DIARISTAS (lacunas 21–24) ────────────────────────────────────────────────
# ⚠️ SÓ LEITURA. `lancar_diaria` e `gerar_lote_diarias_mes` são 🔴 (dinheiro que SAI) e NÃO
# entram aqui — quem lança é o Jordan pela tela, com OTP. Aqui ele só ENXERGA o que já foi
# lançado, que é a pergunta que ele faz todo dia 15 antes de pagar.
# ⚠️ MÓDULO: `operacional/diaristas/diarias_controller.py` — conferido pelo caminho.

def _periodo(mes, ano) -> tuple[int, int]:
    """Período do SERVIDOR quando o modelo não informa.

    O modelo não sabe que mês é hoje — ele chuta, e chutou errado antes (11 em vez de 1).
    Sem `mes`/`ano` explícitos, a data vem do relógio do servidor. Ver
    `scripts/qa/checar_periodo_do_servidor.py`.
    """
    from datetime import date

    h = date.today()
    return (int(mes) if mes else h.month, int(ano) if ano else h.year)


async def _diarias_cadastros(db, user, scope, **_) -> Any:
    _gate(user)
    from modules.operacional.diaristas.diarias_controller import cadastros

    return await cadastros(current_user=user, db=db)


async def _diarias_lancamentos(db, user, scope, *, mes=None, ano=None, data=None, **_) -> Any:
    _gate(user)
    from modules.operacional.diaristas.diarias_controller import lancamentos

    m, a = _periodo(mes, ano)
    # `data` filtra o dia exato e, quando vem, manda no controller — não misturamos os dois.
    return await lancamentos(mes=None if data else m, ano=None if data else a,
                             data=data, current_user=user, db=db)


async def _diarias_resumo_diarista(db, user, scope, *, mes=None, ano=None, **_) -> Any:
    _gate(user)
    from modules.operacional.diaristas.diarias_controller import resumo_diarista

    m, a = _periodo(mes, ano)
    return await resumo_diarista(mes=m, ano=a, current_user=user, db=db)


async def _diarias_resumo_gerencial(db, user, scope, *, mes=None, ano=None, **_) -> Any:
    _gate(user)
    from modules.operacional.diaristas.diarias_controller import resumo_gerencial

    m, a = _periodo(mes, ano)
    return await resumo_gerencial(mes=m, ano=a, current_user=user, db=db)


registrar_read(_MOD, "diarias_cadastros",
               "Cadastros das diárias: diaristas, funções, postos, turnos e a tabela de "
               "preços que dá o valor automático.", _diarias_cadastros)
registrar_read(_MOD, "diarias_lancamentos",
               "Diárias LANÇADAS. Filtros: mes, ano (padrão: mês do servidor) ou data "
               "(YYYY-MM-DD) para um dia exato.", _diarias_lancamentos)
registrar_read(_MOD, "diarias_por_diarista",
               "A lista de pagamento do dia 15: quanto cada diarista tem a receber no mês. "
               "Filtros: mes, ano (padrão: mês do servidor).", _diarias_resumo_diarista)
registrar_read(_MOD, "diarias_resumo_gerencial",
               "Diárias somadas por POSTO e por FUNÇÃO no mês. Filtros: mes, ano (padrão: "
               "mês do servidor).", _diarias_resumo_gerencial)
