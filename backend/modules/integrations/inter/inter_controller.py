"""D6 — Controller Inter: saldo, extrato, transactions, conciliação, cobrancas, PIX."""

import logging
import os
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from core.auth.dependencies import get_current_user
from core.database import get_db
from core.database.session import get_sync_db_dependency

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/financeiro/inter", tags=["Financeiro - Banco Inter"])


def _get_adapter():
    from modules.integrations.banking.adapters.base import BankCredentials
    from modules.integrations.banking.adapters.inter import InterAdapter

    return InterAdapter(
        BankCredentials(
            client_id=os.getenv("INTER_CLIENT_ID", ""),
            client_secret=os.getenv("INTER_CLIENT_SECRET", ""),
            certificate_path=os.getenv("INTER_CERT_PATH"),
            private_key_path=os.getenv("INTER_KEY_PATH"),
            agency=os.getenv("INTER_AGENCY"),
            account=os.getenv("INTER_ACCOUNT"),
            environment=os.getenv("INTER_ENVIRONMENT", "production"),
        )
    )


# ── D6.0 — SALDO ─────────────────────────────────────────────────────────────


@router.get("/saldo")
async def get_saldo(current_user=Depends(get_current_user)):
    """Consulta saldo atual da conta Inter (token cacheado 50min, lock Redis 5s)."""
    # D6.0.4 — lock Redis para evitar 2 calls simultâneos
    try:
        from core.cache.redis import get_redis

        redis = await get_redis()
        lock_key = "inter:saldo:lock"
        acquired = await redis.set(lock_key, "1", nx=True, ex=5)
        if not acquired:
            # Tentar retornar cache de saldo se existir
            cached = await redis.get("inter:saldo:cache")
            if cached:
                import json

                return json.loads(cached)
    except Exception:
        redis = None
        acquired = True

    adapter = _get_adapter()
    try:
        balance = await adapter.get_balance()
        result = {
            "disponivel": float(balance.available),
            "bloqueado": float(balance.blocked),
            "total": float(balance.total),
            "conta": os.getenv("INTER_ACCOUNT", ""),
            "updated_at": balance.updated_at.isoformat() if balance.updated_at else datetime.now().isoformat(),
        }
        # Cachear saldo por 5 min
        try:
            if redis:
                import json

                await redis.set("inter:saldo:cache", json.dumps(result), ex=300)
        except Exception:
            pass
        return result
    finally:
        await adapter.close()
        try:
            if redis and acquired:
                await redis.delete("inter:saldo:lock")
        except Exception:
            pass


# ── D6.1 — EXTRATO + SYNC ────────────────────────────────────────────────────


@router.post("/sync-extrato", status_code=202)
async def sync_extrato(
    background_tasks: BackgroundTasks,
    dias: int = Query(default=7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Sincroniza extrato Inter dos últimos N dias em inter_transactions (background)."""

    async def _run():
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from core.config.settings import get_settings
        from modules.integrations.inter.inter_sync_service import InterSyncService

        settings = get_settings()
        engine = create_async_engine(settings.database_url)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as session:
            result = await InterSyncService(session).sincronizar_extrato(dias=dias)
            logger.info("D6.1 sync-extrato concluído: %s", result)

    background_tasks.add_task(_run)
    return {"status": "started", "dias": dias, "message": "Sincronização iniciada em background."}


@router.get("/transactions")
async def list_transactions(
    inicio: date | None = Query(default=None),
    fim: date | None = Query(default=None),
    tipo: str | None = Query(default=None, description="C ou D"),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Lista transações sincronizadas em inter_transactions."""
    from modules.integrations.inter.inter_sync_service import InterSyncService

    svc = InterSyncService(db)
    rows = await svc.listar_transactions(inicio=inicio, fim=fim, tipo_operacao=tipo, limit=limit)
    return {"total": len(rows), "transactions": rows}


@router.get("/extrato/resumo")
async def resumo_extrato(
    dias: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Totais crédito/débito por tipo nos últimos N dias."""
    from modules.integrations.inter.inter_sync_service import InterSyncService

    return await InterSyncService(db).resumo(dias=dias)


# ── D6.2 — CONCILIAÇÃO FOLHA ─────────────────────────────────────────────────


@router.post("/conciliar/{competencia}")
async def conciliar_folha(
    competencia: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Concilia transactions de débito da competência com folha de pagamento.

    competencia: '2026-04'
    """
    if len(competencia) != 7 or "-" not in competencia:
        raise HTTPException(status_code=400, detail="competencia deve ser 'YYYY-MM'")
    from modules.integrations.inter.conciliacao_service import ConciliacaoService

    svc = ConciliacaoService(db)
    await svc.preparar_competencia(competencia)
    return await svc.conciliar_folha(competencia)


@router.get("/payroll/pagamentos")
async def listar_pagamentos(
    competencia: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Lista conciliação de folha da competência."""
    from modules.integrations.inter.conciliacao_service import ConciliacaoService

    rows = await ConciliacaoService(db).listar_pagamentos(competencia)
    return {"competencia": competencia, "total": len(rows), "pagamentos": rows}


@router.get("/payroll/divergencias")
async def listar_divergencias(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Lista pagamentos em_conciliacao (ambíguos — requerem revisão manual)."""
    from modules.integrations.inter.conciliacao_service import ConciliacaoService

    rows = await ConciliacaoService(db).listar_divergencias()
    return {"total": len(rows), "divergencias": rows}


# ── D6.3 — COBRANÇA / BOLETOS ────────────────────────────────────────────────


class EmitirCobrancaRequest(BaseModel):
    valor: float
    vencimento: str  # YYYY-MM-DD
    payer_name: str
    payer_document: str
    descricao: str
    payer_address: str | None = None
    payer_city: str | None = "Manaus"
    payer_state: str | None = "AM"
    payer_zip: str | None = "69000000"
    payer_number: str | None = "S/N"
    payer_neighborhood: str | None = "Centro"


@router.post("/cobrancas", status_code=201)
async def emitir_cobranca(
    req: EmitirCobrancaRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Emite boleto/cobrança via Inter e persiste em inter_cobrancas."""
    from sqlalchemy import text

    adapter = _get_adapter()
    try:
        vencimento = date.fromisoformat(req.vencimento)
        result = await adapter.generate_boleto(
            amount=Decimal(str(req.valor)),
            due_date=vencimento,
            payer_name=req.payer_name,
            payer_document=req.payer_document,
            description=req.descricao,
            payer_address=req.payer_address,
            payer_city=req.payer_city,
            payer_state=req.payer_state,
            payer_zip=req.payer_zip,
            payer_number=req.payer_number,
            payer_neighborhood=req.payer_neighborhood,
        )
        # Inter gera o boleto de forma ASSÍNCRONA — o POST volta só com o código.
        # Busca os dados de pagamento reais (barcode/linha/PIX/PDF) antes de persistir.
        bid = result.get("boleto_id")
        if bid and not (result.get("barcode") or result.get("digitable_line")):
            import asyncio as _asyncio
            for _tent in range(4):
                await _asyncio.sleep(2)
                det = await adapter.get_boleto(bid)
                if det.get("barcode") or det.get("linha_digitavel") or det.get("pix_copy_paste"):
                    result["barcode"] = det.get("barcode") or result.get("barcode")
                    result["digitable_line"] = det.get("linha_digitavel") or result.get("digitable_line")
                    result["pix_qrcode"] = det.get("pix_copy_paste") or result.get("pix_qrcode")
                    result["pdf_url"] = det.get("pdf_url") or result.get("pdf_url")
                    break
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Erro Inter: {exc}") from exc
    finally:
        await adapter.close()

    await db.execute(
        text("""
            INSERT INTO inter_cobrancas
              (cobranca_id_inter, valor, vencimento, pagador, status,
               url_boleto, pix_copia_cola, barcode, linha_digitavel, descricao)
            VALUES
              (:cid, :valor, :venc, cast(:pagador as jsonb), 'A_RECEBER',
               :url, :pix, :barcode, :ld, :desc)
        """),
        {
            "cid": result.get("boleto_id"),
            "valor": req.valor,
            "venc": vencimento,
            "pagador": f'{{"nome": "{req.payer_name}", "cpfCnpj": "{req.payer_document}"}}',
            "url": result.get("pdf_url"),
            "pix": result.get("pix_qrcode"),
            "barcode": result.get("barcode"),
            "ld": result.get("digitable_line"),
            "desc": req.descricao,
        },
    )
    await db.commit()
    return {"ok": True, **result}


@router.get("/cobrancas")
async def listar_cobrancas(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Lista cobranças emitidas em inter_cobrancas."""
    from sqlalchemy import text

    where = "1=1"
    params: dict = {"limit": limit}
    if status:
        where = "status = :status"
        params["status"] = status.upper()

    rows = (
        (
            await db.execute(
                text(f"""
                SELECT id, cobranca_id_inter, valor, vencimento, status,
                       pagador, url_boleto, pix_copia_cola, barcode, descricao, created_at
                FROM inter_cobrancas
                WHERE {where}
                ORDER BY created_at DESC
                LIMIT :limit
            """),
                params,
            )
        )
        .mappings()
        .all()
    )
    return {"total": len(rows), "cobrancas": [dict(r) for r in rows]}


@router.get("/cobrancas/{cobranca_id}")
async def consultar_cobranca(
    cobranca_id: str,
    current_user=Depends(get_current_user),
):
    """Consulta cobrança diretamente na API Inter."""
    adapter = _get_adapter()
    try:
        return await adapter.get_boleto(cobranca_id)
    finally:
        await adapter.close()


@router.post("/cobrancas/{cobranca_id}/cancelar")
async def cancelar_cobranca(
    cobranca_id: str,
    motivo: str = "ACERTOS",
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Cancela cobrança e atualiza status no DB."""
    from sqlalchemy import text

    adapter = _get_adapter()
    try:
        result = await adapter.cancel_boleto(cobranca_id, motivo)
    finally:
        await adapter.close()

    if result.get("success"):
        await db.execute(
            text("UPDATE inter_cobrancas SET status='CANCELADO', updated_at=NOW() WHERE cobranca_id_inter=:cid"),
            {"cid": cobranca_id},
        )
        await db.commit()
    return result


# ── D6.4 — PIX RECEBIDOS ─────────────────────────────────────────────────────


@router.post("/pix/sync-recebidos", status_code=202)
async def sync_pix_recebidos(
    background_tasks: BackgroundTasks,
    dias: int = Query(default=30, ge=1, le=90),
    current_user=Depends(get_current_user),
):
    """Sincroniza PIX recebidos em inter_pix_recebidos (background)."""

    async def _run():
        import json
        from datetime import datetime

        from sqlalchemy import text as _text
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from core.config.settings import get_settings

        def _parse_dt(val: str | None):
            if not val:
                return None
            try:
                return datetime.fromisoformat(val.replace("Z", "+00:00"))
            except Exception:
                return None

        adapter = _get_adapter()
        try:
            result = await adapter.get_pix_received()
            pix_list = result.get("pix", []) if result.get("success") else []

            settings = get_settings()
            engine = create_async_engine(settings.database_url)
            factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            async with factory() as session:
                salvos = 0
                for p in pix_list:
                    e2e = p.get("endToEndId", p.get("e2eId", ""))
                    if not e2e:
                        continue
                    try:
                        await session.execute(
                            _text("""
                                INSERT INTO inter_pix_recebidos
                                  (end_to_end_id, txid, valor, pagador, data_horario, raw_payload)
                                VALUES (:e2e, :txid, :valor, cast(:pagador as jsonb), :dt, cast(:raw as jsonb))
                                ON CONFLICT (end_to_end_id) DO NOTHING
                            """),
                            {
                                "e2e": e2e,
                                "txid": p.get("txid"),
                                "valor": float(p.get("valor", 0)),
                                "pagador": json.dumps(p.get("pagador") or p.get("devedor") or {}),
                                "dt": _parse_dt(p.get("horario", p.get("dataHorario"))),
                                "raw": json.dumps(p),
                            },
                        )
                        salvos += 1
                    except Exception as exc:
                        logger.warning("D6.4 pix_recebidos insert erro: %s", exc)
                await session.commit()
                logger.info("D6.4 pix sync: %d salvos de %d", salvos, len(pix_list))
        finally:
            await adapter.close()

    background_tasks.add_task(_run)
    return {"status": "started", "message": "Sync PIX recebidos iniciado."}


@router.get("/pix/recebidos")
async def listar_pix_recebidos(
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Lista PIX recebidos persistidos em inter_pix_recebidos."""
    from sqlalchemy import text

    rows = (
        (
            await db.execute(
                text("""
                SELECT id, end_to_end_id, txid, valor, pagador,
                       data_horario, created_at
                FROM inter_pix_recebidos
                ORDER BY data_horario DESC NULLS LAST
                LIMIT :limit
            """),
                {"limit": limit},
            )
        )
        .mappings()
        .all()
    )
    return {"total": len(rows), "pix": [dict(r) for r in rows]}


# ── D6.3 extra — PDF do boleto + sincronizar status ──────────────────────────


@router.get("/cobrancas/{cobranca_id}/pdf")
async def baixar_boleto_pdf(
    cobranca_id: str,
    current_user=Depends(get_current_user),
):
    """Retorna URL do PDF do boleto consultando a API Inter."""
    adapter = _get_adapter()
    try:
        result = await adapter.get_boleto(cobranca_id)
        pdf_url = result.get("pdf_url") or result.get("linkPdf") or result.get("urlPdf")
        if not pdf_url:
            raise HTTPException(status_code=404, detail="PDF não disponível para esta cobrança")
        return {"cobranca_id": cobranca_id, "pdf_url": pdf_url}
    finally:
        await adapter.close()


@router.post("/cobrancas/sincronizar-status", status_code=202)
async def sincronizar_status_cobrancas(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Atualiza status de cobranças A_RECEBER consultando a API Inter (background)."""

    async def _run():
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from core.config.settings import get_settings
        from modules.integrations.inter.cobranca_service import CobrancaService

        settings = get_settings()
        engine = create_async_engine(settings.database_url)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as session:
            result = await CobrancaService(session).sincronizar_status()
            logger.info("D6.3 sincronizar_status concluído: %s", result)

    background_tasks.add_task(_run)
    return {"status": "started", "message": "Sincronização de status iniciada em background."}


# ── D6.4 extra — consultar PIX individual ────────────────────────────────────


@router.get("/pix/{e2e_id}")
async def consultar_pix(
    e2e_id: str,
    current_user=Depends(get_current_user),
):
    """Consulta PIX individual pelo end-to-end ID (API Inter + registro local)."""

    # Primeiro busca no banco local
    adapter = _get_adapter()
    try:
        result = await adapter.get_pix_received()
        pix_list = result.get("pix", []) if result.get("success") else []
        pix = next((p for p in pix_list if p.get("endToEndId") == e2e_id or p.get("e2eId") == e2e_id), None)
        if pix:
            return {"source": "inter_api", "pix": pix}
        raise HTTPException(status_code=404, detail=f"PIX {e2e_id} não encontrado")
    finally:
        await adapter.close()


# ── T-CATEGORIAS — Categorização de transações Inter ─────────────────────────


class CategorizarBody(BaseModel):
    categoria: str
    observacao: str | None = None


@router.post("/transacoes/{transaction_id}/categorizar")
def categorizar_transacao(
    transaction_id: str,
    body: CategorizarBody,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_sync_db_dependency),
):
    """Categoriza manualmente uma transação Inter (INV-6: sempre sobrescreve IA)."""
    from modules.integrations.inter.services.categorizacao_service import InterCategorizacaoService

    svc = InterCategorizacaoService(db)
    try:
        result = svc.categorizar(
            transaction_id=transaction_id,
            categoria=body.categoria,
            observacao=body.observacao,
            user_id=str(current_user.id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return result


@router.get("/colaborador/{nome}/categorias")
def listar_categorias_colaborador(
    nome: str,
    mes_ref: str = Query(..., description="Mês de referência — formato MM.YYYY"),
    apenas_kit: bool = Query(False),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_sync_db_dependency),
):
    """Lista transações de um colaborador no mês com categorização."""
    from modules.integrations.inter.services.categorizacao_service import InterCategorizacaoService

    svc = InterCategorizacaoService(db)
    return svc.listar_por_colaborador(nome, mes_ref, apenas_kit=apenas_kit)


@router.post("/colaborador/{nome}/auto-categorizar")
def auto_categorizar_colaborador(
    nome: str,
    mes_ref: str = Query(..., description="Mês de referência — formato MM.YYYY"),
    apenas_sem_categoria: bool = Query(True),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_sync_db_dependency),
):
    """Auto-categoriza transações de um colaborador no mês por heurísticas + histórico."""
    from modules.integrations.inter.services.categorizacao_service import InterCategorizacaoService

    svc = InterCategorizacaoService(db)
    return svc.auto_categorizar_colaborador(nome, mes_ref, apenas_sem_categoria)


@router.post("/categorias/auto-processar", status_code=200)
def auto_processar_categorias(
    mes_ref: str | None = Query(
        None, description="Mês opcional — formato YYYY-MM. Sem valor: todos os meses com confiança < 0.8"
    ),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_sync_db_dependency),
):
    """
    Auto-processa categorização de transações Inter com confiança < 0.8.
    Respeita INV-4: não toca em transações com confiança >= 0.8.
    """
    from modules.integrations.inter.services.categorizacao_service import InterCategorizacaoService

    svc = InterCategorizacaoService(db)
    return svc.auto_processar(mes_ref=mes_ref)


@router.post("/hermes/linkar", status_code=200)
def hermes_linkar_bulk(
    mes_ref: str | None = Query(None, description="Mês MM.YYYY — sem valor: todos os meses"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_sync_db_dependency),
):
    """
    HERMES bulk link — vincula inter_transactions ao slot ged_kit_documents correto.
    Para cada transação com categoria de kit (salario/VT/VA) e kit_document_id IS NULL:
    resolve employee → condomínio → kit → slot e atualiza ambas as tabelas.
    Idempotente: pula transações já vinculadas.
    """
    from modules.integrations.inter.services.categorizacao_service import InterCategorizacaoService

    svc = InterCategorizacaoService(db)
    return svc.processar_linkagem_bulk(mes_ref=mes_ref)


@router.get("/categorias/stats")
def stats_categorias(
    mes_ref: str = Query(..., description="Mês de referência — formato MM.YYYY"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_sync_db_dependency),
):
    """Estatísticas de categorização do mês."""
    from modules.integrations.inter.services.categorizacao_service import InterCategorizacaoService

    svc = InterCategorizacaoService(db)
    return svc.stats_mes(mes_ref)
