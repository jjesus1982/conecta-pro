"""Saga DP→Operacional: admissão/demissão reagem na alocação de posto.

Mesma razão do irmão em `financial/subscribers/dp_saga_folha.py`: o `dp.*` está vivo e o DP
publica de verdade, mas operacional nunca assinou nada. Um funcionário admitido não gera
proposta de alocação; um demitido não gera baixa. Isso vira trabalho manual e, no caso da
baixa, vira posto contado como coberto por quem já saiu.

A trava: o subscriber PROPÕE, nunca escreve na escala. Operacional é curado à mão pelo Jordan
(regra do projeto), então o rascunho vai para a Central com gate 🟡 e a decisão continua humana.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def _propor(tipo: str, titulo: str, resumo: str, payload: dict, chave: str) -> None:
    from core.database.session import async_session_factory
    from modules.ai.conversation.services.orquestrador.acoes.rascunho import criar_rascunho

    async with async_session_factory() as db:
        try:
            await criar_rascunho(
                db, None, tipo=tipo, modulo="operacional", titulo=titulo, resumo=resumo,
                payload=payload, gate="🟡", requires_otp=False,
                roles_aprovador=("admin", "operacional"), idempotency_key=chave,
            )
            await db.commit()
            logger.info("[saga dp→ops] rascunho %s criado", tipo)
        except Exception as e:  # noqa: BLE001 — saga nunca derruba o publisher
            logger.warning("[saga dp→ops] falha ao criar rascunho (%s)", e)


async def _on_admitido(event) -> None:
    p = getattr(event, "payload", None) or {}
    eid, nome = p.get("employee_id"), p.get("nome") or "novo colaborador"
    if not eid:
        return
    await _propor(
        "alocar_em_posto", f"Alocar em posto: {nome}",
        f"{nome} foi admitido e ainda não tem posto. Defina a alocação para ele entrar "
        f"na escala e nos cálculos que dependem dela (VT/VR por escala, adicional noturno "
        f"por plantão).",
        {"employee_id": eid, "origem": "saga:dp.funcionario_admitido"},
        f"saga:alocar:{eid}",
    )


async def _on_demitido(event) -> None:
    p = getattr(event, "payload", None) or {}
    eid, nome = p.get("employee_id"), p.get("nome") or "colaborador"
    if not eid:
        return
    await _propor(
        "baixar_alocacao", f"Baixar alocação: {nome}",
        f"{nome} foi desligado e a alocação segue ativa. Sem a baixa o posto aparece "
        f"coberto por quem já saiu, e a escala continua lançando plantão para ele.",
        {"employee_id": eid, "origem": "saga:dp.funcionario_demitido"},
        f"saga:baixar_alocacao:{eid}",
    )


def registrar_subscribers() -> None:
    from infrastructure.event_bus import EventTypes, event_bus

    event_bus.subscribe(EventTypes.DP_FUNCIONARIO_ADMITIDO, _on_admitido)
    event_bus.subscribe(EventTypes.DP_FUNCIONARIO_DEMITIDO, _on_demitido)
    logger.info("Saga DP→Operacional: subscribers de admissão/demissão ativos")
