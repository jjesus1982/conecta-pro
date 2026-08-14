"""Documentos de diarista: lista de pagamento, extrato individual e recibo.

Três rotas porque são três perguntas diferentes: quanto pagar no total (lista),
por que esse valor (extrato) e a quitação assinada (recibo). Servir os três pela
mesma rota com um parâmetro de formato esconderia que o recibo é documento assinável
e os outros dois são conferência.

O gate de leitura é o mesmo do resto do financeiro — recibo traz CPF e chave PIX.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from core.database.session import get_sync_db_dependency
from core.auth.dependencies import get_current_user

router = APIRouter(prefix="/diaristas", tags=["Diaristas — documentos"])


def _periodo(inicio: date | None, fim: date | None) -> tuple[date, date]:
    """Sem período = mês corrente. Nunca 'tudo': relatório de pagamento sem recorte
    soma competências fechadas com a aberta e vira número que ninguém sabe pagar."""
    hoje = date.today()
    i = inicio or hoje.replace(day=1)
    f = fim or hoje
    if f < i:
        raise HTTPException(status_code=400, detail="Data final anterior à inicial.")
    return i, f


def _pdf(conteudo: bytes, nome: str) -> Response:
    return Response(content=conteudo, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{nome}"'})


@router.get("/relatorio/pdf", summary="Lista de pagamento das diárias (PDF paisagem)")
def relatorio_pdf(
    inicio: date | None = Query(None), fim: date | None = Query(None),
    db: Session = Depends(get_sync_db_dependency), _u: dict = Depends(get_current_user),
):
    from modules.financial.services.relatorio_diaristas_pdf import relatorio_diaristas

    i, f = _periodo(inicio, fim)
    pdf, _r = relatorio_diaristas(db, inicio=i, fim=f)
    return _pdf(pdf, f"diaristas_{i:%Y%m%d}_{f:%Y%m%d}.pdf")


@router.get("/{diarista_id}/extrato/pdf", summary="Extrato de diárias de um diarista")
def extrato_pdf(
    diarista_id: int, inicio: date | None = Query(None), fim: date | None = Query(None),
    db: Session = Depends(get_sync_db_dependency), _u: dict = Depends(get_current_user),
):
    from modules.financial.services.relatorio_diaristas_pdf import extrato_diarista

    i, f = _periodo(inicio, fim)
    try:
        pdf, r = extrato_diarista(db, diarista_id=diarista_id, inicio=i, fim=f)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return _pdf(pdf, f"extrato_{r['nome'].split()[0].lower()}_{i:%Y%m}.pdf")


@router.get("/{diarista_id}/recibo/pdf", summary="Recibo de pagamento para assinatura")
def recibo_pdf(
    diarista_id: int, inicio: date | None = Query(None), fim: date | None = Query(None),
    db: Session = Depends(get_sync_db_dependency), _u: dict = Depends(get_current_user),
):
    from modules.financial.services.relatorio_diaristas_pdf import recibo_diarista

    i, f = _periodo(inicio, fim)
    try:
        pdf, r = recibo_diarista(db, diarista_id=diarista_id, inicio=i, fim=f)
    except ValueError as e:
        # "sem diária no período" é 404 de propósito: recibo de valor zero é documento
        # que declara quitação de nada, e alguém assina.
        raise HTTPException(status_code=404, detail=str(e)) from e
    return _pdf(pdf, f"recibo_{r['nome'].split()[0].lower()}_{i:%Y%m}.pdf")
