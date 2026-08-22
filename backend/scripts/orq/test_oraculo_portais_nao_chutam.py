"""Oráculo: cliente de portal não dá veredito sobre CNPJ que não consultou.

Em 11/08/2026 três clientes de certidão devolviam veredito sem terem consultado nada — eles
carregavam a PÁGINA DE SERVIÇO do órgão (a que explica o que é uma certidão) e casavam as
palavras dela:

  • `prefeitura_manaus_client` → "irregular" para TODO CNPJ, inclusive o do Banco do Brasil;
  • `sefaz_am_client`          → "regular" para TODO CNPJ, inclusive 11111111111111, que não
                                  existe — e sempre com a mesma validade, que era o fallback
                                  hoje+180 dias, não documento.

O segundo é o pior dos dois: fabrica REGULARIDADE. Foi com base nele que uma CND Estadual
inexistente entrou no banco naquele dia, e uma vencida apareceu renovada.

A prova é um CNPJ que não existe. Se o cliente afirma qualquer coisa sobre ele, está lendo
folheto e chamando de resposta. `requer_manual`/`indeterminado` é o veredito honesto.

Roda (rede real, mas só GET em página pública — nada é gravado):
    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_oraculo_portais_nao_chutam.py
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

#: Sintaticamente válido, inexistente na Receita. Nenhum órgão tem o que dizer sobre ele.
CNPJ_FANTASMA = "11111111111111"

#: Vereditos que afirmam algo. Sobre um CNPJ fantasma, qualquer um destes é chute.
AFIRMATIVOS = {"regular", "irregular", "negativa", "positiva", "positiva_com_efeito_negativa"}


async def _consultar(cls, cnpj: str) -> dict:
    """Chama o cliente aceitando as duas formas (context manager ou não)."""
    try:
        async with cls() as c:
            return await c.consultar_cnd(cnpj)
    except (AttributeError, TypeError):
        return await cls().consultar_cnd(cnpj)


async def main() -> None:
    from modules.bidding.integrations.receita_federal.prefeitura_manaus_client import (
        PrefeituraManausClient,
    )
    from modules.bidding.integrations.receita_federal.sefaz_am_client import SefazAMClient

    for nome, cls in (("Sefaz-AM", SefazAMClient), ("SEMEF/Manaus", PrefeituraManausClient)):
        r = await _consultar(cls, CNPJ_FANTASMA)
        sit = str(r.get("situacao") or "").lower()
        assert sit not in AFIRMATIVOS, (
            f"{nome} afirmou {sit!r} sobre um CNPJ que não existe — está lendo a página "
            f"informativa do órgão e chamando de resposta"
        )
        assert not r.get("data_validade"), (
            f"{nome} devolveu validade {r.get('data_validade')!r} para CNPJ inexistente — "
            f"o fallback que estima validade voltou"
        )
        assert r.get("regular") is not True, f"{nome} disse regular=True sobre CNPJ inexistente"
        print(f"OK {nome}: recusou opinar sobre CNPJ inexistente ({sit or 'sem situação'})")

    # Contraprova: se o portal responder de verdade um dia, o veredito NÃO pode ser bloqueado
    # por esta guarda. A checagem é "a resposta cita o CNPJ", não "nunca afirme nada".
    from modules.bidding.integrations.receita_federal.sefaz_am_client import SefazAMClient as S

    cli = S()
    html = "<html>Certidão Negativa emitida para 66.014.833/0001-10 — válida até 07/02/2027</html>"
    out = cli._parse_resultado_cnd(html, "66014833000110", "http://teste")
    assert out.get("situacao") == "regular", f"resposta legítima foi bloqueada: {out}"
    assert out.get("data_validade"), "resposta legítima perdeu a validade que estava no texto"
    print(f"OK contraprova: resposta que cita o CNPJ ainda vale ({out['data_validade'][:10]})")

    # Contraprova da SEMEF/Manaus. A correção de 22/08 fez "não achei certidão" deixar de
    # virar "irregular" — e uma trava assim tem o defeito espelhado: silenciar veredito
    # LEGÍTIMO. Estas duas provam os dois lados, porque um portal que nunca afirma nada é
    # tão inútil quanto um que inventa.
    from modules.bidding.integrations.receita_federal.prefeitura_manaus_client import (
        PrefeituraManausClient as PM,
    )

    pm = PM()
    neg = pm._parse_resultado_cnd(
        "<html>Certidão Negativa de Débitos Municipais — CNPJ 66.014.833/0001-10 — "
        "Número 2026/000123 — válida até 07/02/2027</html>", "66014833000110", "http://t")
    assert neg.get("situacao") == "regular", f"certidão negativa legítima foi bloqueada: {neg}"
    assert neg.get("data_validade"), "certidão legítima perdeu a validade"

    pos = pm._parse_resultado_cnd(
        "<html>Certidão Positiva de Débitos — existem pendências para o CNPJ "
        "66.014.833/0001-10 — Número 2026/000456 — válida até 07/02/2027</html>",
        "66014833000110", "http://t")
    assert pos.get("situacao") == "irregular", (
        f"certidão POSITIVA legítima deixou de acusar irregularidade: {pos} — a trava "
        f"não pode engolir o débito que existe de verdade")
    print("OK contraprova SEMEF: negativa vale regular, positiva vale irregular")

    print("TEST oraculo_portais_nao_chutam PASS")


if __name__ == "__main__":
    asyncio.run(main())
