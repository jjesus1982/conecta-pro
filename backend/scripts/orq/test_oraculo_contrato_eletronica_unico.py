#!/usr/bin/env python3
"""O contrato de segurança eletrônica em SERVIÇO ÚNICO sai com as blindagens jurídicas.

Existe porque seis cláusulas deste modelo não são redação — são proteção, revisadas pela
Furtado Maia e aprovadas pelo Jordan em 09/09/2026. Um `render` que "simplifique" qualquer
uma delas produz um PDF bonito e um contrato pior, e ninguém percebe olhando a tela:

    2.2   exclui dificuldades comerciais de fornecimento do rol de força maior
    2.3   multa moratória da CONTRATADA por atraso, com teto
    3.2   parcela final RETIDA até o Termo de Entrega assinado sem ressalvas
    7.2   prazo de homologação para o cliente apontar defeitos por escrito
    9.3   vedada conversão automática da cortesia em contrato oneroso
    11.2  responsabilidade integral e REGRESSIVA por vazamento de biometria

Afirma a REGRA, não a fotografia: os valores saem do contrato de prova e são comparados com
o que está no banco, então reajuste ou parcela nova não reprovam. O que reprova é a cláusula
sumir, a contratada virar a Patrimonial, ou o instrumento contradizer a si mesmo sobre
testemunha.

⚠️ TRAVA DE REGRESSÃO junto: os dois modelos recorrentes (portaria e manutenção) NÃO podem
ganhar quadro de testemunha. Eles se apoiam na dispensa do art. 784 §4º do CPC, e um quadro
de testemunha em branco num contrato que declara a dispensa é o documento se contradizendo.

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_oraculo_contrato_eletronica_unico.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CTR = "CTR-2026-00022"
RECORRENTES = ("CTR-2026-00019", "CTR-2026-00020")
ELETRONICA_CNPJ = "35.710.481/0001-03"

# As seis blindagens, pela string exata. Trecho curto e sem número, para o oráculo não
# reprovar quando o Jordan renegociar teto ou prazo com um cliente específico.
BLINDAGENS = {
    "2.2 força maior não cobre falta de fornecedor":
        "excluindo-se deste rol dificuldades comerciais de fornecimento da CONTRATADA",
    "2.3 multa moratória da CONTRATADA": "multa moratória de",
    "2.3 com teto": "limitada ao teto de",
    "3.2 parcela retida até o Termo de Entrega":
        "retida, a ser paga no prazo de até 5 dias úteis contados da efetiva assinatura "
        "sem ressalvas do Termo de Entrega",
    "7.2 homologação por escrito":
        "para apontar por escrito eventuais defeitos, incompatibilidades ou pendências",
    "9.3 sem conversão automática":
        "vedada qualquer conversão automática em contrato oneroso",
    "11.2 responsabilidade regressiva": "responderá integral e regressivamente",
    "11.2 origem no Conecta Plus":
        "falha ou vulnerabilidade de segurança da própria plataforma Conecta Plus",
}


async def main() -> None:
    # `main_production` PRIMEIRO, sempre. Oráculo que importa depois mede um mundo que ele
    # mesmo montou pela metade; foi assim que 8/8 passou verde sobre capacidade morta.
    # O ruff reordenou isto uma vez e pôs o sqlalchemy na frente — daí o noqa: aqui a
    # ORDEM é o teste, não estilo.
    import main_production  # noqa: F401,PLC0415,I001
    from core.database import async_session_factory  # noqa: PLC0415
    from modules.crm.services.contract_render import renderizar_contrato  # noqa: PLC0415
    from sqlalchemy import text  # noqa: PLC0415

    async with async_session_factory() as db:
        res = await renderizar_contrato(db, CTR)
        txt = " ".join(res.texto.split())

        faltando = [rot for rot, frase in BLINDAGENS.items()
                    if " ".join(frase.split()) not in txt]
        assert not faltando, "blindagem jurídica sumiu do contrato: " + " · ".join(faltando)
        print(f"OK {len(BLINDAGENS)} blindagens presentes")

        # quem presta — errar o CNPJ num contrato assinado é problema fiscal, não estético
        assert res.contratada.cnpj == ELETRONICA_CNPJ, (
            f"contratada errada: {res.contratada.razao_social} ({res.contratada.cnpj}); "
            f"serviço eletrônico sai pela Eletrônica ({ELETRONICA_CNPJ})")
        print(f"OK contratada {res.contratada.razao_social} — {res.contratada.cnpj}")

        assert res.n_clausulas == 14, f"o modelo tem 14 cláusulas, renderizou {res.n_clausulas}"
        assert "{{" not in txt and "}}" not in txt, "variável não substituída foi para o PDF"

        # o VALOR não é fixado aqui: é comparado com o banco. Reajuste não reprova; o que
        # reprova é o instrumento anunciar um total que a composição não soma.
        r = (await db.execute(text(
            "SELECT c.total_value, "
            "  (SELECT sum(i.total_price) FROM contract_items i "
            "    WHERE i.contract_id = c.id AND coalesce(i.is_active,true)) AS soma "
            "FROM contracts c WHERE c.contract_number = :k"), {"k": CTR})).mappings().first()
        assert r and r["total_value"], f"{CTR} sem total_value"
        assert r["soma"] == r["total_value"], (
            f"a composição soma {r['soma']} e o contrato diz {r['total_value']}")
        from modules.crm.services.contract_render import brl  # noqa: PLC0415
        assert brl(r["total_value"]) in txt, (
            f"o total {brl(r['total_value'])} do banco não aparece no instrumento")
        print(f"OK total {brl(r['total_value'])} bate com a composição e sai no texto")

        # testemunhas: este modelo colhe (decisão do Jordan, 09/09) e por isso NÃO invoca a
        # dispensa. As duas coisas andam juntas — é a contradição que o oráculo caça.
        # (o quadro desenhado no PDF não é afirmável aqui: o texto do reportlab vai
        # comprimido no content stream. Quem confere o desenho é a lente TELA. Aqui se
        # afirma o que o texto declara — e é a contradição que interessa.)
        assert "igualmente o assinam por meio eletrônico" in txt, (
            "o fecho deixou de citar as testemunhas que assinam")
        assert "dispensada a assinatura de testemunhas" not in txt, (
            "o instrumento colhe testemunha E invoca a dispensa do art. 784 §4º — "
            "contradiz a si mesmo")
        print("OK fecho coerente: colhe testemunha e não invoca a dispensa")

        # REGRESSÃO: os recorrentes seguem sem quadro de testemunha e com a dispensa.
        for ctr in RECORRENTES:
            rr = await renderizar_contrato(db, ctr)
            t2 = " ".join(rr.texto.split())
            assert "dispensada a assinatura de testemunhas" in t2, (
                f"{ctr} deixou de invocar a dispensa do art. 784 §4º")
            assert "igualmente o assinam" not in t2, (
                f"{ctr} passou a colher testemunha — não era para mudar")
            print(f"OK {ctr} intacto ({rr.contratada.razao_social}, {rr.n_clausulas} cláusulas)")

    print("TEST oraculo_contrato_eletronica_unico PASS")


if __name__ == "__main__":
    asyncio.run(main())
