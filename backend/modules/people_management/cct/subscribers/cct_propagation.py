"""Propagação bidirecional CCT/cargo entre módulos (ConectaEventBus).

Reage aos eventos de cargo/CCT e propaga a mudança para os módulos que guardam
cópias materializadas (postos/hazard_pay, caches de CCT/pricing), além de re-emitir
eventos para folha/GED reagirem. Assim a CCT (fonte única) flui em todos os módulos
sem cada um ter que ficar consultando — é a comunicação bidirecional.

Registrado no lifespan (main_production.py), ao lado do GEDEON.
Usa SEMPRE infrastructure.event_bus (ConectaEventBus, que É consumido).
"""

import logging

from infrastructure.event_bus import EventTypes, event_bus

logger = logging.getLogger(__name__)


async def _ressync_postos_do_funcionario(db, funcionario_id: str) -> int:
    """Ressincroniza hazard_pay dos postos onde o funcionário está alocado (CCT)."""
    from sqlalchemy import text

    from modules.operacional.repositories.post_repository import PostRepository

    repo = PostRepository(db)
    rows = (
        await db.execute(
            text(
                "SELECT DISTINCT CAST(post_id AS TEXT) FROM allocations "
                "WHERE CAST(employee_id AS TEXT) = :e AND COALESCE(status,'ativa') <> 'encerrada'"
            ),
            {"e": str(funcionario_id)},
        )
    ).fetchall()
    n = 0
    for (pid,) in rows:
        try:
            await repo.sincronizar_hazard_pay_cct(str(pid))
            n += 1
        except Exception:  # noqa: BLE001,S110
            pass
    return n


async def _on_cargo_alterado(event) -> None:
    """DP_CARGO_ALTERADO: funcionário mudou cargo/salário → propaga aos módulos."""
    p = getattr(event, "payload", None) or {}
    fid = p.get("funcionario_id")
    if not fid:
        return
    try:
        from core.database import async_session_factory

        async with async_session_factory() as db:
            n = await _ressync_postos_do_funcionario(db, fid)
            await db.commit()
        logger.info("Propagação cargo (%s): %s posto(s) ressincronizado(s)", p.get("cargo"), n)
    except Exception as e:  # noqa: BLE001
        logger.warning("Propagação cargo alterado falhou (%s): %s", fid, e)

    # Re-emite salário recalculado → folha/GED/GEDEON/pricing reagem
    try:
        await event_bus.emit(
            EventTypes.DP_SALARIO_RECALCULADO,
            {"funcionario_id": fid, "cargo": p.get("cargo"), "origem": "cargo_alterado"},
            source_module="cct_propagation",
        )
    except Exception:  # noqa: BLE001,S110
        pass


async def _on_cct_cargo_atualizado(event) -> None:
    """CCT_CARGO_ATUALIZADO: piso/adicional do cargo mudou → invalida caches + ressincroniza."""
    p = getattr(event, "payload", None) or {}
    cct_cargo_id = p.get("cct_cargo_id")
    try:
        from sqlalchemy import text

        from core.database import async_session_factory

        async with async_session_factory() as db:
            # Ressincroniza hazard_pay de todos os postos com funcionários deste cargo CCT
            emps = (
                await db.execute(
                    text("SELECT CAST(id AS TEXT) FROM employees WHERE CAST(cct_cargo_id AS TEXT) = :c"),
                    {"c": str(cct_cargo_id)},
                )
            ).fetchall()
            total = 0
            for (eid,) in emps:
                total += await _ressync_postos_do_funcionario(db, eid)
            await db.commit()
        logger.info("Propagação CCT cargo %s: %s posto(s) ressincronizado(s)", cct_cargo_id, total)
    except Exception as e:  # noqa: BLE001
        logger.warning("Propagação CCT cargo atualizado falhou (%s): %s", cct_cargo_id, e)

    # Invalida cache de pricing (piso mudou → recomputar custo/proposta)
    try:
        from core.cache.redis import cache_delete

        await cache_delete("cct:pricing:piso_min")
    except Exception:  # noqa: BLE001,S110
        pass

    # Re-emite reajuste → precificação/folha reagem
    try:
        await event_bus.emit(
            EventTypes.CCT_REAJUSTE_APLICADO,
            {"cct_cargo_id": cct_cargo_id, "campos": p.get("campos_alterados")},
            source_module="cct_propagation",
        )
    except Exception:  # noqa: BLE001,S110
        pass


def registrar_subscribers(bus=None) -> None:
    """Registra os subscribers de propagação CCT no event bus (chamar no lifespan)."""
    b = bus or event_bus
    b.subscribe(EventTypes.DP_CARGO_ALTERADO, _on_cargo_alterado)
    b.subscribe(EventTypes.CCT_CARGO_ATUALIZADO, _on_cct_cargo_atualizado)
    logger.info("CCT propagação: subscribers ativos (cargo/CCT → postos/folha/pricing bidirecional)")
