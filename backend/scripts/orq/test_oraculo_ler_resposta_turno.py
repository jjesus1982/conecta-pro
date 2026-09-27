"""«Tudo bem» não é compromisso; «estarei por lá» é. As duas pontas do mesmo defeito.

🔴 MEDIDO EM 27/09/2026, na mesma conversa. O GERNANES respondeu ao «boa noite» do José Luís com
**«Tudo bem»** e o sistema gravou `confirmado` — compromisso com um plantão que ele não tinha
mencionado. Minutos depois ele escreveu **«Amanhã se Deus quizer estarei por lá»**, que é
compromisso inequívoco, e `ler_resposta` devolveu `None`.

⭐ O vocabulário estava invertido nas duas direções: **aceitava a gentileza e recusava a
promessa.** `tudo (certo|ok|bem|tranquilo)` tratava «tudo bem» como sinônimo de «tudo certo», e em
português «tudo bem» sozinho é resposta a cumprimento. E `_CONFIRMA` é ancorado em `^`, então
qualquer compromisso que comece por outra palavra («amanhã…», «pode contar…») passava batido.

## Por que isto merece trava

`confirmado` falso é o pior desfecho do módulo: o relatório das 08:30 diz ao Jordan que a pessoa
se comprometeu, o lembrete de 1h antes PARA de cobrá-la, e se ela não aparecer o posto amanhece
descoberto com o painel verde. Um `None` a mais só custa uma cobrança repetida.

⚠️ A trava mais importante daqui é a da NEGAÇÃO: `_PROMETE` busca em qualquer posição, então
«não estarei por lá» casaria com `estarei` e viraria compromisso que a pessoa acabou de recusar —
defeito pior que o original. Estado ambíguo falha FECHADO.

⚠️ E «não estarei por lá» devolver `None` (não `recusado`) é DELIBERADO, não descuido: falta
anunciada tem caminho próprio em `supervisao.classificar_pedido`, que gera rascunho **com a lista
de quem pode cobrir**. Marcar `recusado` aqui arquivaria em silêncio e destruiria a ajuda que o
gerente operacional precisa. Régua que abraça demais rouba de outra.

Afirma a REGRA (o que cada classe de frase significa), nunca uma pessoa ou uma data.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/app")

from modules.integrations.connectors.whatsapp.troca_turno import ler_resposta  # noqa: E402

#: (frase, veredito esperado, por que este caso existe)
CASOS = [
    # ── gentileza NUNCA é compromisso (o defeito de 27/09)
    ("Tudo bem", None, "resposta ao «boa noite» — foi gravada como confirmado"),
    ("tudo bem?", None, "pergunta de cortesia"),
    ("Boa noite", None, "cumprimento"),
    ("Bom dia", None, "cumprimento"),
    # ── compromisso por extenso, fora do início da frase (o outro lado do defeito)
    ("Amanhã se Deus quizer estarei por lá", "confirmado", "a frase real do Gernanes"),
    ("estarei lá sim", "confirmado", "promessa direta"),
    ("vou estar no posto", "confirmado", "promessa direta"),
    ("pode contar comigo que estarei", "confirmado", "promessa que começa por outra palavra"),
    # ── ⚠️ NEGAÇÃO desliga a promessa. Sem isto o conserto criaria defeito pior.
    ("não estarei por lá", None, "recusa NÃO pode virar confirmado"),
    ("nao vou estar amanha", None, "recusa NÃO pode virar confirmado"),
    ("nao consigo, estarei ocupado", None, "«estarei» dentro de recusa"),
    # ── o núcleo curto que sempre valeu (não pode ser perdido no conserto)
    ("Sim", "confirmado", "núcleo"),
    ("Blz", "confirmado", "como a casa fala"),
    ("tudo certo", "confirmado", "responde ao «está tudo certo?» que a casa manda"),
    ("ok", "confirmado", "núcleo"),
    ("👍", "confirmado", "emoji de aceite"),
    # ── o «não» seco, e só ele
    ("nao", "recusado", "recusa explícita"),
    ("não", "recusado", "recusa explícita"),
]


def main() -> None:
    erros = []
    for frase, esperado, porque in CASOS:
        got = ler_resposta(frase)
        if got != esperado:
            erros.append(f"«{frase}» → {got}, esperado {esperado} ({porque})")

    assert not erros, "vocabulário de confirmação regrediu:\n  " + "\n  ".join(erros)

    confirmam = sum(1 for _, e, _ in CASOS if e == "confirmado")
    recusam = sum(1 for _, e, _ in CASOS if e == "recusado")
    print(f"OK {len(CASOS)} frases · {confirmam} confirmam · {recusam} recusam · "
          f"{len(CASOS) - confirmam - recusam} não são resposta de confirmação")

    # Suspenders: o defeito exato não pode voltar por outro caminho.
    assert ler_resposta("Tudo bem") is None, "«tudo bem» voltou a valer compromisso"
    assert ler_resposta("Amanhã estarei por lá") == "confirmado", "a promessa por extenso caiu"
    assert ler_resposta("nao estarei") is None, "a guarda de negação caiu — recusa viraria aceite"
    print("OK as três travas do incidente de 27/09 no lugar")

    print("TEST oraculo_ler_resposta_turno PASS")


if __name__ == "__main__":
    main()
