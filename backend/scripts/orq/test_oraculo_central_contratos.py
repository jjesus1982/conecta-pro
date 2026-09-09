#!/usr/bin/env python3
"""A Central de contratos mostra o passo CERTO para cada negócio, e tem entrada no menu.

Existe porque a central é uma máquina de estados: cada linha diz onde o negócio travou e
oferece só o botão que destrava. Um estado que ofereça o botão errado é pior que estado
nenhum — manda o dono abrir assinatura de um contrato sem instrumento, ou pedir link de
quem já assinou.

Afirma a REGRA, não a fotografia: não fixa quantas linhas há nem quais contratos aparecem.
Fixa a COERÊNCIA — para cada situação, o passo e o botão que lhe correspondem. Contrato
novo entra na fila sozinho e não reprova nada.

⚠️ AFIRMA TAMBÉM O MENU. A tela que responde por HTTP e não tem entrada no `EXTRA_MENU`
existe e ninguém alcança — é o defeito mais comum desta casa, e foi por isso que a central
quase nasceu invisível.

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_oraculo_central_contratos.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TELA = "contratos-a-emitir"

# situação → (trecho que o passo tem de conter, rótulo do botão ou None quando o passo é
# humano). É o contrato da máquina de estados, e o que reprova quando alguém o quebra.
ESPERADO = {
    "Ganha, sem proposta":        ("proposta", None),
    "Aceita pelo cliente":        ("Gerar o contrato", "Gerar contrato"),
    "Rascunho, sem modelo":       ("modelo", None),
    "Instrumento pronto":         ("Abrir a assinatura", "Abrir assinatura"),
    # cancelada NÃO é pendência de assinatura: o link cancelado ainda serve o PDF pela
    # rota pública, então oferecer "mande o link" convida o cliente a assinar o que a
    # casa cancelou. Medido no CTR-2026-00019 em 09/09/2026.
    "Assinatura cancelada":       ("reabra", "Reabrir assinatura"),
    "Em assinatura":              ("assinatura(s)", "Enviar link"),
    "Assinado, fora de vigência": ("Ativar", "Ativar"),
}


async def main() -> None:
    # `main_production` PRIMEIRO, sempre — ver o oráculo do contrato eletrônico.
    import main_production  # noqa: F401,PLC0415,I001
    from core.database import async_session_factory  # noqa: PLC0415
    from modules.operacional.controllers.redesign_builders import crm as B  # noqa: PLC0415

    menu = {m["id"] for m in B.EXTRA_MENU}
    assert TELA in menu, (
        f"'{TELA}' não está no EXTRA_MENU do CRM — a tela responde e ninguém chega nela")
    print(f"OK '{TELA}' tem entrada no menu")

    async with async_session_factory() as db:
        screens = await B.build(db)
        assert TELA in screens, f"a tela '{TELA}' não montou (erro engolido pelo safe())"
        tela = screens[TELA]
        linhas = tela["rows"]
        print(f"OK tela montou · {len(linhas)} linha(s) na fila")

        vistos = set()
        for ln in linhas:
            cel = ln["cells"]
            situacao = cel[3]["v"]
            passo = cel[4]["v"]
            botoes = [a.get("btnLabel") for a in (ln.get("actions") or [])
                      if not a.get("readOnly")]

            assert situacao in ESPERADO, (
                f"situação desconhecida na central: {situacao!r} — estado novo sem passo "
                "definido deixa o dono sem saber o que fazer")
            trecho, botao = ESPERADO[situacao]
            assert trecho.lower() in passo.lower(), (
                f"'{situacao}' deveria orientar sobre {trecho!r}, e diz: {passo!r}")
            if botao:
                assert botao in botoes, (
                    f"'{situacao}' precisa do botão {botao!r}; tem {botoes}")
            else:
                assert not botoes, (
                    f"'{situacao}' é passo HUMANO e não pode oferecer botão; tem {botoes}")
            vistos.add(situacao)
            print(f"OK {situacao:28s} → {botao or 'sem botão (passo humano)'}")

        # o valor tem de declarar a natureza: contrato de serviço único mostrado como
        # mensalidade foi o defeito que motivou metade deste trabalho.
        for ln in linhas:
            v = ln["cells"][2]["v"]
            assert "R$" in v, f"valor sem moeda na central: {v!r}"

        assert vistos, "a fila veio vazia — sem nada para conferir, isto não é verde"

    print("TEST oraculo_central_contratos PASS")


if __name__ == "__main__":
    asyncio.run(main())
