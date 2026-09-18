#!/usr/bin/env python3
"""A triagem do Hermes sabe o que o dono DESLIGOU — e não reporta decisão como defeito.

Origem: 18/09/2026. A triagem daquele dia abriu assim, para o dono ler de manhã:

    «Último sync do Sólides/Tangerino: 17/09 às 03:57. São ~29 horas sem importação.
     E nenhum dos 8 espelhos que abri tem dia lançado depois de 13/09.»

Nada disso é defeito: o Jordan DESLIGOU o pull em 13/09 — *"os pontos já estão sendo batidos
pelo conecta pro, já não temos mais necessidade de puxar as batidas do solides/tangerino"*. O
que o pull trazia não era batida medida, era a GRADE da escala, ~1h adiantada, quebrando o
pareamento do espelho.

É a mesma falha do caso da CINTIA, que apareceu como "não bateu" estando afastada pelo INSS há
quatro meses: o agente lê o DADO e não conhece a DECISÃO. Dado não diz por que é assim, e um
relatório que gasta o primeiro parágrafo num não-problema ensina o dono a não ler o resto.

## As regras afirmadas

1. O bloco de fatos decididos CHEGA ao pedido que vai ao Hermes — não basta a função existir.
2. Ele é LIDO DO BEAT, não escrito à mão: com a rotina agendada, a linha some. Se alguém
   religar o pull do Sólides e o aviso continuar, o prompt passa a mentir na direção oposta.
3. A regra dos afastados continua junto: as duas nasceram do mesmo defeito e some uma, some
   o cuidado com a pessoa.

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \
        /app/scripts/orq/test_oraculo_triagem_sabe_o_que_foi_desligado.py

Linha canônica: `TOTAL: <n> falha(s) no que a triagem sabe`. Exit 1 quando há achado.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "/app")

#: A task cujo desligamento gerou o falso alarme de 18/09.
_PULL_DO_SOLIDES = "solides.sync_punches"


def main() -> int:
    from modules.people_management.ponto import triagem_hermes as t

    falhas: list[str] = []

    # 1 · o bloco chega ao pedido de verdade. Medir a função isolada não prova nada: ela pode
    #     existir perfeita e ninguém chamá-la — foi assim que 4 travas ficaram órfãs nesta casa.
    import inspect

    fonte = inspect.getsource(t.rodar)
    if "_fatos_decididos()" not in fonte:
        falhas.append(
            "`rodar` não monta os fatos decididos no pedido — o Hermes volta a "
            "reportar o pull desligado do Sólides como se fosse falha"
        )
    if "_REGRA_AUSENTES" not in fonte:
        falhas.append("sumiu a regra dos afastados do pedido — alguém em licença médica volta a ser cobrado por ponto")

    # 2 · o texto sai do BEAT, não de um literal. Com a task agendada, a linha tem de sumir.
    try:
        import celery_app as ca

        app = getattr(ca, "app", None) or getattr(ca, "celery", None)
        agendadas = {str(v.get("task", "")) for v in (app.conf.beat_schedule or {}).values()}
    except Exception as exc:  # noqa: BLE001
        print(f"BLOQUEADO: não consegui ler o beat ({exc})")
        print("TOTAL: 0 falha(s) no que a triagem sabe")
        return 3

    texto = t._fatos_decididos()  # noqa: SLF001
    cita_solides = "Sólides" in texto or "Tangerino" in texto
    if _PULL_DO_SOLIDES in agendadas and cita_solides:
        falhas.append(
            f"`{_PULL_DO_SOLIDES}` VOLTOU ao beat e o aviso continua dizendo que está "
            "desligado — agora o prompt mente na direção oposta, e importação parada "
            "de verdade passaria batida"
        )
    if _PULL_DO_SOLIDES not in agendadas and not cita_solides:
        falhas.append(
            f"`{_PULL_DO_SOLIDES}` está fora do beat e o aviso NÃO fala dele — o "
            "relato volta a abrir com «X horas sem importação» sobre uma decisão"
        )

    # 3 · o mapa não pode ficar vazio sem que alguém perceba: sem chave nenhuma, a função
    #     devolve "" para sempre e o oráculo acima passa a concordar com o silêncio.
    if not t._DESLIGADO_DE_PROPOSITO:  # noqa: SLF001
        falhas.append(
            "_DESLIGADO_DE_PROPOSITO ficou vazio — a triagem perdeu a memória das "
            "decisões e nenhuma trava daqui acusaria isso"
        )

    for f in falhas:
        print(f"FALHOU: {f}")
    estado = "agendado" if _PULL_DO_SOLIDES in agendadas else "desligado"
    print(
        f"pull do Sólides: {estado} · aviso no pedido: {'sim' if cita_solides else 'não'} · "
        f"{len(t._DESLIGADO_DE_PROPOSITO)} decisão(ões) no mapa"
    )  # noqa: SLF001
    print(f"TOTAL: {len(falhas)} falha(s) no que a triagem sabe")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
