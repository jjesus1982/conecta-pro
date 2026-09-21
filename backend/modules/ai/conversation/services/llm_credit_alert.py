"""Alerta de LLM indisponível/sem crédito — SEM CANAL DE ENVIO desde 11/08/2026.

Pedido do Jordan em 07/07/2026: *"preciso que os meus chats me informem todas as vezes que
estiverem sem crédito, pra eu recarregar"*. O canal era o Telegram; ele apagou e bloqueou os
bots em 11/08, e em 20/09/2026 o corpo morto que guardava a URL da API saiu daqui.

⚠️ HOJE O AVISO VIRA LOG, e é bom que fique escrito: quando um consultor fica sem crédito,
`alertar_llm_indisponivel()` grava em nível ERROR e ninguém é notificado. Os dumps do Hermes
de 15 e 16/09 mostraram HTTP 402 «Insufficient Balance» do DeepSeek — dois dias em que a
triagem não rodou e nada tocou. É exatamente o buraco que este módulo existia para tapar.

O canal da casa é o SINO (`communication_notifications`). Religar por lá é decisão do dono,
não conserto técnico — por isso ficou fora do commit que removeu o Telegram.

Chamado por 10 serviços de consultor no caminho de falha do provider; a função continua
existindo e devolvendo cedo, então apagá-la quebraria chamador que não tem nada a ver com o bot.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_ULTIMO_ALERTA: dict[str, float] = {}
_INTERVALO_MIN_S = 3600  # 1 alerta/hora por consultor

_PALAVRAS_CREDITO = ("credit", "quota", "billing", "insufficient", "429", "rate limit", "payment")


def _e_erro_de_credito(erro: str) -> bool:
    e = (erro or "").lower()
    return any(p in e for p in _PALAVRAS_CREDITO)


async def alertar_llm_indisponivel(origem: str, erro: str) -> None:
    """DESATIVADA (11/08/2026) — o Telegram saiu do Conecta PRO.

    Os dois bots foram apagados e bloqueados pelo Jordan. Este era o ÚNICO alerta puramente
    técnico do lote (consultor sem crédito de LLM); vira log em nível de erro, que é onde
    esse tipo de coisa deve viver mesmo. Se voltar a fazer falta, o canal é o SINO.
    """
    logger.error("[telegram removido] LLM indisponível em %s: %s", origem, (erro or "")[:200])
