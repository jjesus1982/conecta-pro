"""Tasks de assinatura (09/09/2026) — o lote da empresa roda no CELERY, não no processo do backend.

Por que existe: o lote da empresa rodava em `asyncio.create_task` dentro do backend. Medido em 09/09 às 13:29 —
o Jordan confirmou o OTP e mandou assinar 24 documentos; o backend recarregou no meio (hot-copy de outra sessão)
e a tarefa morreu com 10 assinados e 14 pendentes, sem erro nenhum na tela. Uma assinatura ICP-Brasil leva ~4 s,
então um lote de 24 fica ~100 s no ar: tempo de sobra para pegar um reload.

No worker (fila `operacional`) o lote sobrevive a reload do backend e a task fica registrada, com retomada
idempotente — reprocessar só pega o que ainda está PENDING.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:
    from celery import shared_task
except ImportError:  # pragma: no cover — permite importar fora do celery
    def shared_task(*args, **kwargs):  # type: ignore[misc]
        def decorator(func):
            func.delay = lambda *a, **kw: func(*a, **kw)
            func.apply_async = lambda *a, **kw: func(*a, **kw)
            return func
        return decorator(args[0]) if args and callable(args[0]) else decorator


@shared_task(name="signatures.assinar_lote_empresa", bind=True, max_retries=0, queue="operacional")
def assinar_lote_empresa_task(self, request_ids: list[str], company_signer_id: str, signer_name: str | None = None,
                              evidence: dict | None = None) -> dict:
    """Assina, uma a uma, as solicitações da EMPRESA já autorizadas por OTP no endpoint.

    O OTP é validado ANTES (no endpoint); aqui só executa. Idempotente: o motor recusa request que não está
    pendente, e o resumo diz quantas passaram.
    """
    import asyncio

    async def _run() -> dict:
        import uuid as _uuid

        from core.database import get_db
        from modules.signatures.services.universal_signature_service import SignatureEvidence, UniversalSignatureService

        gen = get_db()
        db = await gen.__anext__()
        try:
            ev = SignatureEvidence(
                ip_address=(evidence or {}).get("ip_address"),
                user_agent=(evidence or {}).get("user_agent"),
                device=(evidence or {}).get("device") or "central-de-assinaturas",
                extra=(evidence or {}).get("extra") or {},
            )
            ids = [_uuid.UUID(str(r)) for r in request_ids]
            return await UniversalSignatureService(db).assinar_lote_empresa(
                company_signer_id=_uuid.UUID(str(company_signer_id)),
                signer_name=signer_name,
                request_ids=ids,
                limite=len(ids),
                evidence=ev,
            )
        finally:
            try:
                await gen.aclose()
            except Exception:  # noqa: BLE001
                pass

    res = asyncio.run(_run())
    logger.info("signatures.assinar_lote_empresa: %s assinados, %s falhas", res.get("assinados"), res.get("falhas"))
    return res
