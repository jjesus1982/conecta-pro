"""Saga DP→Financeiro: reage a `dp.folha_fechada` propondo o lote de pagamento.

Por que este arquivo existe
---------------------------
O barramento `dp.*` está VIVO e o DP já grita: são 11 publishers reais, chamados de verdade.
O que nunca existiu foi a metade que REAGE — hoje só o GEDEON escuta, e ele reage montando
documento. Financeiro, operacional e fiscal publicam mas não assinam nada do DP.

Então a cadeia "folha fechada → pagar a folha" não estava adormecida: ela nunca teve o outro
lado. Construir a saga = ASSINAR, não reviver barramento.

Escolha do evento (registrada no ledger): assinei `folha_fechada`/`holerite_gerado` porque são
os que já NASCEM com frequência real — o GEDEON os consome hoje, então a cadeia se prova com
dado vivo. Os raros (demissão) usam o mesmo mecanismo e passam a valer quando a CAPTURA fizer
o evento nascer (é o buraco do caso Keyson).

A trava
-------
O subscriber NUNCA paga. Ele cria um RASCUNHO 🔴 na Central, com aprovação de diretoria e OTP
no momento da execução — money-out é do T1 e continua sendo. O que muda é que a Pyetra/diretoria
recebe o lote **já montado** em vez de montar à mão.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def _on_folha_fechada(event) -> None:
    """Folha fechada → PROPÕE o lote de pagamento (nunca paga)."""
    p = getattr(event, "payload", None) or {}
    competencia = p.get("competencia") or ""
    total = p.get("total_funcionarios") or 0
    liquido = p.get("total_liquido") or p.get("liquido")
    if not competencia:
        logger.info("[saga dp→fin] folha_fechada sem competência — ignorado (não fabrico)")
        return

    # import tardio: o subscriber é registrado no boot e não pode arrastar o mundo
    from core.database.session import async_session_factory
    from modules.ai.conversation.services.orquestrador.acoes.rascunho import criar_rascunho

    valor = f"R$ {float(liquido):,.2f}" if liquido not in (None, "") else "valor a apurar na tela"
    async with async_session_factory() as db:
        try:
            await criar_rascunho(
                db, None,
                tipo="pagar_folha_lote",
                modulo="financeiro",
                titulo=f"Folha {competencia} fechada — montar lote de pagamento",
                resumo=(f"A folha de {competencia} foi fechada ({total} colaborador(es), "
                        f"{valor}). O lote de pagamento pode ser montado. "
                        f"A execução do PIX continua exigindo OTP na tela de pagamentos."),
                payload={"competencia": competencia, "total_funcionarios": total,
                         "origem": "saga:dp.folha_fechada"},
                gate="🔴",
                requires_otp=True,
                roles_aprovador=("admin",),
                idempotency_key=f"saga:folha_fechada:{competencia}",
            )
            await db.commit()
            logger.info("[saga dp→fin] rascunho de lote criado p/ %s", competencia)
        except Exception as e:  # noqa: BLE001 — saga nunca derruba o publisher
            logger.warning("[saga dp→fin] falha ao criar rascunho (%s)", e)


def registrar_subscribers() -> None:
    """Assina os eventos do DP que já nascem com frequência real."""
    from infrastructure.event_bus import EventTypes, event_bus

    event_bus.subscribe(EventTypes.DP_FOLHA_FECHADA, _on_folha_fechada)
    logger.info("Saga DP→Financeiro: subscriber de folha_fechada ativo")
