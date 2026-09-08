"""
API do GEDEON — endpoints para o frontend consultar
o contexto acumulado antes de montar um kit.
"""

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_db
from modules.gedeon.agents.hermes import hermes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/gedeon", tags=["GEDEON"])


@router.on_event("startup")
async def sophia_startup() -> None:
    """
    SOPHIA v2.0: auto-startup — verifica status do índice ao iniciar o app.
    """
    from modules.gedeon.agents.sophia import sophia

    try:
        s = sophia.status()
        logger.info(
            "SOPHIA v2.0 startup: %d documentos indexados, motor=%s",
            s.get("total_documentos", 0),
            s.get("motor_ativo", "unknown"),
        )
    except Exception as exc:
        logger.warning("SOPHIA v2.0 startup: status indisponível (%s)", exc)


@router.post("/hermes/classificar")
async def classificar_documento(
    nome_arquivo: str = Query(..., description="Nome do arquivo a classificar"),
    conteudo_preview: str = Query("", description="Trecho do conteudo (opcional)"),
    current_user=Depends(get_current_user),
):
    resultado = hermes.classificar_documento(nome_arquivo, conteudo_preview)
    return {"nome_arquivo": nome_arquivo, **resultado}


@router.post("/sophia/perguntar")
async def sophia_perguntar(
    q: str | None = None,
    pergunta: str | None = None,
    cliente_id: str | None = None,
    funcionario_id: str | None = None,
    modulo: str | None = None,
    competencia: str | None = None,
    current_user=Depends(get_current_user),
):
    """SOPHIA v2.0: pergunta em linguagem natural sobre o acervo."""
    from modules.gedeon.agents.sophia import sophia

    query_text = pergunta or q or ""
    if not query_text:
        return {"erro": "Parâmetro 'pergunta' ou 'q' obrigatório"}
    return sophia.perguntar(
        pergunta=query_text,
        cliente_id=cliente_id,
        funcionario_id=funcionario_id,
        modulo=modulo,
        competencia=competencia,
    )


@router.post("/sophia/reindexar")
async def sophia_reindexar(
    batch_size: int = 50,
    modulo: str | None = None,
    current_user=Depends(get_current_user),
):
    """SOPHIA v2.0: re-indexa acervo com embedding v2."""
    from modules.gedeon.agents.sophia import sophia

    resultado = sophia.reindexar_acervo(batch_size=batch_size, modulo_filter=modulo)
    return {"status": "ok", **resultado}


@router.post("/sophia/indexar")
async def sophia_indexar(
    current_user=Depends(get_current_user),
):
    """SOPHIA v2.0: indexar/re-indexar acervo completo."""
    from modules.gedeon.agents.sophia import sophia

    resultado = sophia.indexar_acervo_completo()
    return {"status": "ok", **resultado}


@router.get("/colaborador/{nome}/pagamentos")
async def colaborador_pagamentos(
    nome: str,
    mes_ref: str | None = Query(None, description="Filtro de mês — formato MM.YYYY ex: 03.2026"),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """G9.1 — Busca pagamentos do Banco Inter por nome do colaborador."""
    from modules.gedeon.services.inter_comprovante_service import InterComprovanteService

    svc = InterComprovanteService(db)
    return await svc.gerar_resumo_pagamentos(nome=nome, mes_ref=mes_ref)


def _gerar_checklist(ctx: dict) -> dict:
    return {
        "movimentacao": {
            "pre_preenchido": ctx["movimentacao_pessoal"],
            "confirmado": len(ctx["movimentacao_pessoal"]) > 0,
            "requer_input": True,
        },
        "certidoes": {
            "status": ctx["certidoes"],
            "critico": ctx["certidoes"].get("critico", 0) > 0,
            "confirmado": ctx["certidoes"].get("critico", 0) == 0,
        },
        "documentos": {
            "gerados": ctx["documentos_gerados"],
            "confirmado": bool(ctx["documentos_gerados"]),
        },
        "pendencias": {
            "itens": ctx["pendencias"],
            "tem_pendencias": len(ctx["pendencias"]) > 0,
            "requer_decisao": any(p.get("requer_decisao") for p in ctx["pendencias"]),
        },
        "score_geral": ctx["score_prontidao"],
    }
