"""Fase 5.6a (LT2) — Beat task que liga o detector de anomalia de pagamento
(LT1, `services/anomalia_pagamentos.py`) ao ciclo periódico + sino da diretoria.

`anomalia.varrer_pagamentos` (*/30min, fila gov.batch, mesmo padrão de
`modules/notifications/proativo/tasks.py`):
  1) roda o detector — READ-ONLY sobre `inter_payments`, só INSERT em
     `fraud_alerts` (ver invariantes no docstring de anomalia_pagamentos.py);
  2) para cada alerta severity HIGH/CRITICAL recém-criado nesta rodada, avisa
     a diretoria (role admin, via `resolver_usuarios_por_roles`) no sino —
     SEMPRE rotulado como SUSPEITA pendente de revisão humana, nunca como
     fraude confirmada. Dedup por `idempotency_key` (1 aviso por alerta,
     mesmo se a task rodar de novo).

Isolado do resto do beat: falha aqui nunca propaga (try/except + retry
curto, mesmo padrão de `proativo.avaliar_regras`). NUNCA age sobre o
pagamento — só lê `inter_payments` e escreve em `fraud_alerts`/sino.
"""
from __future__ import annotations

import logging

from celery_app import app

logger = logging.getLogger(__name__)

# severidades que acordam a diretoria no sino (low/medium só ficam na fila de revisão)
_SEVERIDADES_SINO = ("high", "critical")


def _run_async(coro):
    import asyncio
    import os

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    url = os.getenv("DATABASE_URL", "").replace("postgresql://", "postgresql+asyncpg://")

    async def _inner():
        eng = create_async_engine(url, echo=False)
        session = sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
        async with session() as s:
            return await coro(s)

    return asyncio.run(_inner())


async def _varrer(
    db,
    *,
    janela_horas: int = 24,
    apenas_pagamento_ids: list[str] | None = None,
) -> dict:
    """Coração testável (sem celery). Roda o detector + avisa a diretoria dos
    alertas HIGH/CRITICAL desta rodada. Retorna contadores para log/teste."""
    from modules.ai.fraud_detection.services.anomalia_pagamentos import (
        detectar_anomalias_pagamentos,
    )
    from modules.notifications.proativo.entrega import (
        enviar_individual,
        resolver_usuarios_por_roles,
    )

    alertas = await detectar_anomalias_pagamentos(
        db, janela_horas=janela_horas, apenas_pagamento_ids=apenas_pagamento_ids,
    )

    avisados = 0
    for alerta in alertas:
        if alerta.get("severity") not in _SEVERIDADES_SINO:
            continue
        try:
            destinatarios = await resolver_usuarios_por_roles(db, ("admin",))
            if not destinatarios:
                logger.warning(
                    "anomalia.varrer_pagamentos: sem destinatário admin resolvido "
                    "p/ alerta %s", alerta.get("alert_number"))
                continue
            sinais = ", ".join(alerta.get("sinais_disparados") or []) or "n/d"
            valor = alerta.get("valor")
            valor_fmt = f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") \
                if valor is not None else "valor não disponível"
            title = "⚠️ Suspeita de anomalia em pagamento (revisar)"
            body = (
                f"SUSPEITA pendente de revisão — NÃO é fraude confirmada. "
                f"Alerta {alerta.get('alert_number')} · beneficiário: "
                f"{alerta.get('beneficiario') or 'não identificado'} · valor: {valor_fmt} · "
                f"severidade: {alerta.get('severity')} · sinais: {sinais}."
            )
            correlation_id = f"anomalia:{alerta['alert_id']}"
            criados = await enviar_individual(
                db, user_ids=destinatarios, title=title, body=body,
                familia="financeiro", severidade=alerta.get("severity") or "high",
                correlation_id=correlation_id, action_url="/ai/fraud/anomalias/pendentes",
                reference_type="anomalia_pagamento", reference_id=alerta.get("alert_id"),
                idempotency_key=correlation_id,
            )
            await db.commit()
            if criados:
                avisados += 1
        except Exception as exc:  # noqa: BLE001 — 1 aviso falho não derruba os outros
            logger.error(
                "anomalia.varrer_pagamentos: falha ao avisar diretoria do alerta %s: %s",
                alerta.get("alert_number"), exc)
            await db.rollback()

    return {"alertas_criados": len(alertas), "avisados_sino": avisados}


@app.task(name="anomalia.varrer_pagamentos", bind=True, max_retries=1)
def varrer_pagamentos_task(self):
    try:
        res = _run_async(_varrer)
        logger.info("[anomalia_pagamentos] varrer_pagamentos: %s", res)
        return res
    except Exception as exc:
        logger.error("[anomalia_pagamentos] varrer_pagamentos erro: %s", exc)
        raise self.retry(exc=exc, countdown=120)
