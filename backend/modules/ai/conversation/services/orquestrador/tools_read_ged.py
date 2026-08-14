"""Tools READ do GED (Fase 6, balde VER) — módulo ged, scope_kind="org".

No chat escopado, quem tem o módulo `ged` CONSULTA o acervo documental como faria navegando
as telas: lista de documentos, busca full-text, estatísticas consolidadas e o status de
coleta/prontidão dos kits mensais (GEDEON). Cada handler chama a COROUTINE do controller/serviço
REAL in-process, com a IDENTIDADE do usuário logado (`db`/`user` reais) — NUNCA a conta de
serviço, NUNCA HTTP.

Paredes (inegociáveis):
- RBAC na fonte: chamar o controller direto PULA o Depends(require_permission) dele, então
  TODO handler faz `_gate(user)` primeiro (re-checa user_has_module(user,"ged")). O belt
  (tools_for_modules) já filtra por módulo; o _gate é o suspenders.
- SÓ LEITURA: só coroutines de rota GET / list() de serviço entram aqui. Nada cria/edita/apaga.
- Nunca fabricar: devolve o resultado REAL do controller/banco; vazio real = vazio.
- Sem SQL f-string com input do usuário: os controllers usados (search_documents, kits_status)
  usam SQL parametrizado (:binds); nada aqui interpola texto do LLM em SQL.

NÃO inclui gera-doc de kit (kit_pdf/montar já existem como ação): aqui é só leitura.
`get_comunicados` foi DELIBERADAMENTE deixado de fora — devolve lista hardcoded (fabricação).
"""
from __future__ import annotations

from typing import Any

from core.auth.module_scope import user_has_module

from .read_dispatcher import registrar_read

_MOD = "ged"


def _gate(user) -> None:
    if not user_has_module(user, _MOD):
        raise PermissionError(_MOD)


def _dump(res) -> Any:
    return res.model_dump(mode="json") if hasattr(res, "model_dump") else res


# ---- handlers ----

async def _documentos(db, user, scope, *, busca=None, search=None, q=None,
                      folder_id=None, condominium_id=None, page=1, page_size=20, **_) -> Any:
    _gate(user)
    from modules.ged.schemas.document import DocumentFilter
    from modules.ged.services.document_service import DocumentService
    # só filtros str simples (enums exigiriam valor válido; deixa o repo tratar a busca)
    filtros = DocumentFilter(search=(busca or search or q), folder_id=folder_id,
                             condominium_id=condominium_id)
    return _dump(await DocumentService(db).list(filtros, int(page), int(page_size)))


async def _buscar_documento(db, user, scope, *, busca=None, q=None, search=None,
                            document_type=None, category=None, status=None, client_id=None,
                            limit=50, **_) -> Any:
    _gate(user)
    from modules.ged.controllers.document_controller import search_documents
    # search_documents faz SQL parametrizado (:q bound), nada de f-string com input
    return _dump(await search_documents(q=(busca or q or search or ""),
                                        document_type=document_type, category=category,
                                        status_filter=status, origin=None, signed=None,
                                        client_id=client_id, limit=int(limit), db=db,
                                        current_user=user))


async def _stats(db, user, scope, *, condominium_id=None, **_) -> Any:
    _gate(user)
    from modules.ged.controllers.ged_stats_controller import get_ged_stats
    return _dump(await get_ged_stats(condominium_id=condominium_id, db=db, current_user=user))


async def _kits_status(db, user, scope, *, competencia=None, **_) -> Any:
    _gate(user)
    from modules.gedeon.controllers.gedeon_controller import kits_status_mensal
    return _dump(await kits_status_mensal(competencia=competencia, current_user=user, db=db))


async def _kits_config(db, user, scope, **_) -> Any:
    _gate(user)
    from modules.gedeon.controllers.gedeon_controller import kits_config
    return _dump(await kits_config(current_user=user, db=db))


async def _kit_ficha(db, user, scope, *, condominio=None, competencia=None, **_) -> Any:
    _gate(user)
    if not condominio:
        return {"status": "informe condominio (nome do condomínio) para ver a ficha do kit"}
    from modules.gedeon.controllers.orquestrador_controller import ficha_kit
    # controller síncrono (lê o Drive, cacheado ~60s); não recebe db.
    return _dump(ficha_kit(condominio=str(condominio), competencia=competencia, refresh=False,
                           current_user=user))


async def _kit_cronograma(db, user, scope, *, competencia=None, **_) -> Any:
    _gate(user)
    from modules.gedeon.controllers.orquestrador_controller import cronograma
    return _dump(cronograma(competencia=competencia, current_user=user))


async def _intercorrencias(db, user, scope, *, condominio=None, competencia=None, status=None,
                           limit=200, **_) -> Any:
    _gate(user)
    # LISTAR intercorrências de kit (read). Registrar/tratar/excluir são ações, fora deste balde.
    from modules.gedeon.services.consultor_service import listar_intercorrencias
    itens = await listar_intercorrencias(db, condominio=condominio, competencia=competencia,
                                         status=status, limit=int(limit))
    return {"total": len(itens), "intercorrencias": _dump(itens)}


# ---- registro das ops READ (roteadas por consultar_ged(consulta, filtros)) ----

registrar_read(_MOD, "documentos",
               "Lista documentos do GED (paginado). Filtros opcionais: busca (texto), "
               "folder_id, condominium_id, page, page_size.", _documentos)
registrar_read(_MOD, "buscar_documento",
               "Busca documentos em ged_documents + kits (UNION, SQL parametrizado). Filtros: "
               "busca (texto), document_type, category, status, client_id, limit.", _buscar_documento)
registrar_read(_MOD, "stats",
               "Estatísticas consolidadas do GED (pastas, documentos, compartilhamentos, "
               "assinaturas, tags). Filtro opcional: condominium_id.", _stats)
registrar_read(_MOD, "kits_status",
               "Status de coleta/prontidão dos kits mensais (GEDEON): score por cliente, "
               "pendências, prontos/alertas/críticos. Filtro opcional: competencia ('AAAA-MM', "
               "default = mês atual).", _kits_status)
registrar_read(_MOD, "kits_config",
               "Configuração de kit por cliente ativo (tipo_kit e serviços) — qual checklist "
               "cada condomínio usa. Sem filtros.", _kits_config)
registrar_read(_MOD, "kit_ficha",
               "Ficha completa do kit de UM condomínio: completude, checklist (presente/falta), "
               "eventos do mês e arquivos no Drive. Filtros: condominio (obrigatório, nome), "
               "competencia ('MM.YYYY', default = mês anterior).", _kit_ficha)
registrar_read(_MOD, "kit_cronograma",
               "Cronograma do mês de entrega: quando cada documento deve estar pronto (salário 5º "
               "dia útil, VT/VR dia 16, prazos de assinatura 48h). Filtro opcional: competencia "
               "('MM.YYYY').", _kit_cronograma)
registrar_read(_MOD, "intercorrencias",
               "Lista intercorrências dos kits (eventos que impactam a folha/entrega: rescisão, "
               "afastamento, admissão etc.), com status e impacto. READ-ONLY: só lista — registrar/"
               "tratar é ação. Filtros: condominio, competencia ('AAAA-MM'), status, limit.",
               _intercorrencias)


# ── três consultas novas (F4 do fechamento GEDEON, 14/08/2026) ─────────────────
#
# O ALGORITMO NÃO MUDA AO TROCAR DE EMBALAGEM — é a regra do prompt e o oráculo
# `test_oraculo_tool_igual_classe` prova que cada uma devolve o mesmo que a classe já
# devolvia. Aqui não há uma linha de SQL nova: KRONOS e THEMIS já sabem responder, e a
# completude já tem dono em `services/completude_slots`. A tool orquestra, não recalcula.
#
# ⚠️ Por que estas três e não as doze do prompt: `comprovante_por_pagamento` chama a API do
# Cora (território a combinar com o T1), `comparar_portte` depende de itens de holerite que
# não existem (0 linhas em 07/2026), e as de ação (`kit_montar`, `kit_propor_envio`) são
# escrita — não entram num arquivo de LEITURA. Cada uma está registrada como não-coberta no
# relatório, com o motivo.


async def _certidoes_vencendo(db, user, scope, *, dias=None, **_) -> Any:  # noqa: ARG001
    """Certidões e ASOs com prazo — o ALGORITMO do KRONOS, sem reescrever a query."""
    _gate(user)
    from modules.gedeon.agents.kronos import Kronos

    k = Kronos()
    return {
        "certidoes": await k.verificar_certidoes(db),
        "asos": await k.verificar_asos_funcionarios(db),
    }


async def _assinaturas_pendentes(db, user, scope, **_) -> Any:  # noqa: ARG001
    """Quem falta assinar e há quantos dias — o ALGORITMO do THEMIS."""
    _gate(user)
    from modules.gedeon.agents.themis import Themis

    return await Themis().resumo(db)


async def _kit_completude(db, user, scope, *, competencia=None, **_) -> Any:  # noqa: ARG001
    """O que FALTA no kit, por TIPO de documento — não só um percentual.

    Usa `document_type`, a coluna tipada com 52 valores canônicos, e não o nome do arquivo.
    "Filtro por texto não é contagem — quem conta é o banco" é a regra que a F1 comprou com
    erro: o serviço que lê o Drive casa por nome porque arquivo de Drive não tem tipo; aqui,
    no banco, o tipo existe e é ele que manda.
    """
    _gate(user)
    from sqlalchemy import text as _t

    sql = _t(
        "SELECT to_char(k.reference_month,'YYYY-MM') AS competencia, "
        "       coalesce(gc.name,'—') AS cliente, "
        "       d.document_type AS tipo, "
        "       count(*) AS slots, "
        "       count(*) FILTER (WHERE d.file_path IS NOT NULL AND d.file_path <> '') AS entregues "
        "FROM ged_kit_documents d "
        "JOIN ged_document_kits k ON k.id = d.kit_id "
        "LEFT JOIN ged_clients gc ON gc.id = k.client_id "
        # CAST obrigatório: sem ele o asyncpg não infere o tipo de `:comp` num
        # `IS NULL OR ... = :comp` e estoura AmbiguousParameterError. Terceira vez que
        # parâmetro sem tipo morde nesta base — a primeira foi `current_date + :janela`.
        "WHERE (CAST(:comp AS text) IS NULL "
        "       OR to_char(k.reference_month,'YYYY-MM') = CAST(:comp AS text)) "
        "GROUP BY 1,2,3 HAVING count(*) > count(*) FILTER ("
        "  WHERE d.file_path IS NOT NULL AND d.file_path <> '') "
        "ORDER BY 1 DESC, 2, 3"
    )
    linhas = (await db.execute(sql, {"comp": competencia})).mappings().all()
    return {
        "competencia": competencia or "todas",
        "pendencias": [dict(r) for r in linhas],
        "total_tipos_incompletos": len(linhas),
    }

registrar_read(_MOD, "certidoes_vencendo",
               "Certidões e ASOs com prazo vencendo ou vencido (algoritmo do KRONOS). "
               "Devolve as duas listas com dias restantes e nível de alerta.", _certidoes_vencendo)
registrar_read(_MOD, "assinaturas_pendentes",
               "Documentos do GED aguardando assinatura: total, críticos e tempo de espera "
               "(algoritmo do THEMIS). Sem filtros.", _assinaturas_pendentes)
registrar_read(_MOD, "kit_completude",
               "O que FALTA no kit por TIPO de documento e por cliente — usa a coluna tipada "
               "`document_type` (52 tipos canônicos), não o nome do arquivo. Filtro opcional: "
               "competencia ('AAAA-MM'; sem ela, todas).", _kit_completude)
