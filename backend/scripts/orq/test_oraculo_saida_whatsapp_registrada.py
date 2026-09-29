"""O que a casa ENVIA fica registrado, e o registro nasce no ato — não no eco.

🔴 MEDIDO EM 29/09/2026. O aviso diário de assinatura saiu às 09:00 para dezenas de pessoas e
`cwi_message_log` guardou **23 linhas**. Conferi doze nomes que o monitor mostrou recebendo —
TELMA, CELIANE, KELLY, VANDERLICE, NAILSON, PAULO, RUAN, BIANCA, DANIEL, MATHEUS, EDIWILSON,
JONILSON — e **doze de doze não tinham linha nenhuma**. Rodei o controle oito minutos depois:
continuavam 23. Não era atraso do eco, era ausência.

## ⭐ A causa, e ela é da família mais cara desta casa

O registro estava pendurado no **EFEITO**, não no **ATO**: quem escrevia o log era o *webhook*,
a partir do eco que o Chatwoot devolve — `_send_message` não gravava nada. Eco que não volta =
a empresa falou com um funcionário e não tem prova do que disse. Em assunto de ponto, folha e
assinatura, "o que a casa afirmou a quem" é precisamente o que se precisa poder mostrar depois.

É a mesma forma de [registro de falha no lugar errado]: instrumentar o vizinho do fato e ler o
vazio como inocência.

## O que este oráculo trava

1. **O registrador existe e GRAVA** — exercitado de verdade contra o banco, com id sintético.
2. **É idempotente com o eco** (`ON CONFLICT` no `chatwoot_message_id`): quando o webhook
   chegar com a mesma mensagem, não nasce um segundo registro do mesmo fato. Sem isto o
   conserto trocaria "mensagem sem registro" por "mensagem registrada duas vezes", e qualquer
   contagem por pessoa passaria a mentir para o outro lado.
3. **Nunca bloqueia o envio**: entrada podre entra e a função NÃO levanta. Banco fora do ar não
   pode calar um WhatsApp — essa é a ordem de prioridade, e ela é deliberada.
4. **A canonização do telefone é UMA** (o `_normalize_phone` do controller é o MESMO objeto que
   `service.normalize_phone`). Dois normalizadores divergem na primeira mudança e aí o mesmo
   telefone existe em dois formatos no log.
5. **Coerência no banco** (regra, não fotografia): toda linha de saída com `phone_canonical`
   preenchido tem só dígitos. É o que permite contar por pessoa.

⚠️ Não envia nada. Mandar WhatsApp de verdade num teste é ato para fora — o que se exercita é o
REGISTRADOR, não o remetente.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database.session import async_session_factory  # noqa: E402
from modules.integrations.connectors.whatsapp import controller  # noqa: E402
from modules.integrations.connectors.whatsapp.service import (  # noqa: E402
    normalize_phone,
    whatsapp_service,
)

# Negativo de propósito: id do Chatwoot é sempre positivo, então não há como colidir com uma
# mensagem real nem apagar linha de produção na limpeza.
MSG_ID_SINTETICO = -987654321
FONE = "+559200000000"


async def main() -> None:
    # 4 — uma canonização só, e ela é a mesma dos dois lados
    assert controller._normalize_phone is normalize_phone, (
        "o controller voltou a ter a própria cópia da canonização: o mesmo telefone passará a "
        "existir em dois formatos no log e a contagem por pessoa mente"
    )
    for bruto, esperado in (("+559296053339", "9296053339"), ("92 98472-5613", "92984725613"), (None, None)):
        assert normalize_phone(bruto) == esperado, f"canonização mudou: {bruto!r}"

    # 3 — entrada podre não levanta (o envio não pode morrer por causa do registro)
    await whatsapp_service._registrar_saida(FONE, "controle", "nao-e-numero", "nem-isso")

    try:
        # 1 — grava de verdade
        await whatsapp_service._registrar_saida(FONE, "oráculo: registro no ato", 999_111, MSG_ID_SINTETICO)
        async with async_session_factory() as db:
            r = (
                await db.execute(
                    text(
                        "SELECT count(*) n, min(phone_canonical) fone, min(status) st "
                        "  FROM cwi_message_log WHERE chatwoot_message_id = :m"
                    ),
                    {"m": MSG_ID_SINTETICO},
                )
            ).mappings().first()
        assert r["n"] == 1, (
            f"o registro do ato não gravou ({r['n']} linhas). Sem ele, mensagem enviada cujo eco "
            "não volta deixa a empresa sem prova do que disse ao funcionário"
        )
        assert r["fone"] == normalize_phone(FONE), f"telefone gravado fora do formato: {r['fone']!r}"
        assert r["st"] == "sent", (
            "o registro do ato perdeu o status 'sent'. Ele existe para separar procedência — o eco "
            "grava status nulo — e é o que permite medir quantas mensagens só existem por causa "
            "deste conserto"
        )

        # 2 — idempotência: o eco do webhook chega com o mesmo id e NÃO duplica
        await whatsapp_service._registrar_saida(FONE, "oráculo: o eco chegando depois", 999_111, MSG_ID_SINTETICO)
        async with async_session_factory() as db:
            n2 = (
                await db.execute(
                    text("SELECT count(*) FROM cwi_message_log WHERE chatwoot_message_id = :m"),
                    {"m": MSG_ID_SINTETICO},
                )
            ).scalar()
        assert n2 == 1, (
            f"gravou {n2} linhas para a MESMA mensagem: o conserto trocou «sem registro» por "
            "«registrado em dobro», e contagem por pessoa passa a mentir para o outro lado"
        )

        # 5 — coerência: toda saída identificada por telefone tem só dígitos
        async with async_session_factory() as db:
            sujas = (
                await db.execute(
                    text(
                        "SELECT count(*) FROM cwi_message_log "
                        " WHERE direction='out' AND phone_canonical IS NOT NULL "
                        "   AND phone_canonical !~ '^[0-9]+$'"
                    )
                )
            ).scalar() or 0
        assert sujas == 0, (
            f"{sujas} mensagem(ns) de saída com telefone fora do formato de dígitos — some de "
            "qualquer contagem por pessoa sem dar sinal"
        )
        print("OK o registro nasce no ATO do envio (1 linha, telefone canônico, status 'sent')")
        print("OK idempotente com o eco do webhook — a mesma mensagem não vira dois registros")
        print("OK entrada podre não levanta: banco fora do ar não cala um envio")
        print("OK uma canonização só, compartilhada entre quem envia e quem recebe o webhook")
        print(f"OK {sujas} telefone(s) de saída fora do formato no banco")
    finally:
        # Limpa SEMPRE, inclusive se um assert estourar no meio: linha de teste deixada no log
        # de conversas aparece no histórico que o agente lê e vira contexto falso.
        async with async_session_factory() as db:
            await db.execute(
                text("DELETE FROM cwi_message_log WHERE chatwoot_message_id = :m"),
                {"m": MSG_ID_SINTETICO},
            )
            await db.execute(
                text(
                    "DELETE FROM cwi_message_log "
                    " WHERE chatwoot_message_id IS NULL AND direction='out' "
                    "   AND content IN ('controle') AND phone_canonical = :f"
                ),
                {"f": normalize_phone(FONE)},
            )
            await db.commit()

    print("TEST oraculo_saida_whatsapp_registrada PASS")


if __name__ == "__main__":
    asyncio.run(main())
