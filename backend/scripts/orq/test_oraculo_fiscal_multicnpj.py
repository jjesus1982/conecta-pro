"""Oráculo multi-CNPJ do fiscal: cada empresa do grupo aparece, e o buraco dela também.

O grupo tem DOIS CNPJs desde 2026 — Eletrônica (Lucro Real) e Patrimonial (Simples Anexo
III) — e até 11/08/2026 nenhuma tela fiscal dizia de qual empresa era a linha. O painel
somava tudo, e a soma escondia o que importa: medido nesse dia, a Patrimonial faturava
R$ 443.381,11, tinha **1 das 8** certidões que a Eletrônica tem e **zero** obrigação fiscal
cadastrada — sendo Simples, que deve DAS todo mês.

Um número agregado não é errado; é cego. Este oráculo exige que o painel mostre POR EMPRESA
e que tipo de certidão FALTANDO apareça como falta, não como ausência silenciosa.

As empresas vêm de `empresas`, nunca de lista fixa: CNPJ novo entra coberto sozinho.

Roda:
    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_oraculo_fiscal_multicnpj.py
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _fixtures import tela  # noqa: E402
from sqlalchemy import text  # noqa: E402

from core.database import async_session_factory  # noqa: E402
from modules.operacional.controllers.redesign_builders.fiscal import build  # noqa: E402


def _texto(linha) -> str:
    """Achata uma linha da tabela do redesign em texto.

    A linha vem como `{"cells": [...]}` e cada célula é um dict (`{"v": ..., "w": 600, ...}`)
    ou um badge. Achatar é o suficiente: o oráculo pergunta se o número APARECE, não em qual
    coluna — assim uma troca de layout não reprova por motivo errado.
    """
    if isinstance(linha, dict):
        linha = linha.get("cells") or []

    def _v(c):
        if isinstance(c, dict):
            return " ".join(str(x) for x in c.values() if isinstance(x, (str, int, float)))
        return str(c)
    return " ".join(_v(c) for c in (linha or []))


async def main() -> None:
    async with async_session_factory() as db:
        telas = await build(db)

        empresas = (await db.execute(text(
            "SELECT id::text, coalesce(nome_fantasia, razao_social) AS nome, cnpj "
            "FROM empresas ORDER BY nome"
        ))).fetchall()
        assert len(empresas) >= 2, f"esperava os 2 CNPJs do grupo, achei {len(empresas)}"

        # ── 1. Painel por empresa: uma linha por CNPJ, com os números daquela empresa ──
        pe = tela(telas, "painel-por-empresa")
        assert pe, "tela 'painel-por-empresa' não existe — o fiscal continua cego a CNPJ"
        assert pe.get("type") == "table", f"painel-por-empresa deveria ser tabela: {pe.get('type')}"
        linhas = pe.get("rows") or []
        assert len(linhas) == len(empresas), \
            f"{len(empresas)} empresas no banco, {len(linhas)} linha(s) no painel"

        corpo = "\n".join(_texto(r) for r in linhas)
        for _id, nome, _cnpj in empresas:
            assert nome.split()[-1] in corpo or nome in corpo, \
                f"empresa {nome!r} não aparece no painel por empresa"

        for _id, nome, cnpj in empresas:
            alvo = next((r for r in linhas if nome.split()[-1] in _texto(r)), None)
            assert alvo, f"linha da {nome} sumiu"
            venc = (await db.execute(text(
                "SELECT count(*) FROM ged_certidoes "
                "WHERE regexp_replace(coalesce(cnpj,''), '[^0-9]', '', 'g') = "
                "      regexp_replace(:c, '[^0-9]', '', 'g') AND expiry_date < CURRENT_DATE"
            ), {"c": cnpj})).scalar()
            pend = (await db.execute(text(
                "SELECT count(*) FROM fiscal_obligations "
                "WHERE empresa_id::text = :e AND lower(coalesce(status::text,'')) = 'pendente'"
            ), {"e": _id})).scalar()
            txt = _texto(alvo)
            assert str(venc) in txt, f"{nome}: {venc} certidão(ões) vencida(s) não aparece(m) na linha"
            assert str(pend) in txt, f"{nome}: {pend} obrigação(ões) pendente(s) não aparece(m)"
        print(f"OK painel por empresa: {len(linhas)} linha(s), uma por CNPJ, com vencidas e pendentes")

        # ── 2. Cobertura de certidões: o que FALTA tem que aparecer ──
        cob = tela(telas, "certidoes-cobertura")
        assert cob, "tela 'certidoes-cobertura' não existe — falta de certidão continua invisível"
        corpo_cob = "\n".join(_texto(r) for r in (cob.get("rows") or []))

        tipos = [r[0] for r in (await db.execute(text(
            "SELECT DISTINCT name FROM ged_certidoes ORDER BY 1"))).fetchall()]
        assert tipos, "pré-condição: nenhuma certidão cadastrada"
        assert len(cob.get("rows") or []) == len(tipos), \
            f"{len(tipos)} tipos de certidão, {len(cob.get('rows') or [])} linha(s) na cobertura"

        faltas = 0
        for tipo in tipos:
            for _id, _nome, cnpj in empresas:
                tem = (await db.execute(text(
                    "SELECT count(*) FROM ged_certidoes WHERE name = :n AND "
                    "regexp_replace(coalesce(cnpj,''), '[^0-9]', '', 'g') = "
                    "regexp_replace(:c, '[^0-9]', '', 'g')"
                ), {"n": tipo, "c": cnpj})).scalar()
                if not tem:
                    faltas += 1
        assert faltas > 0, "esperava buraco de cobertura na base real (Patrimonial tem 1 de 8)"
        assert "FALTA" in corpo_cob.upper(), \
            f"{faltas} combinação(ões) tipo×empresa sem certidão e a tela não diz 'FALTA'"
        print(f"OK cobertura de certidões: {len(tipos)} tipos × {len(empresas)} empresas, "
              f"{faltas} falta(s) visível(is)")

        # ── 3. Empresa nas tabelas: a linha tem que dizer de quem é ──
        # `nfse` fica de fora de propósito: lista `nfse_manaus_historico`, que só tem o CNPJ do
        # TOMADOR e não sabe quem emitiu. Exigir Empresa ali empurraria alguém a carimbar
        # "Eletrônica" em 831 linhas por dedução — inventar dado para satisfazer teste.
        for slug in ("certidoes", "certidoes-cnd", "guias", "nfse-emitidas"):
            t = tela(telas, slug)
            assert t, f"tela {slug} não resolve"
            cols = [str(c) for c in (t.get("cols") or [])]
            assert any("empresa" in c.lower() for c in cols), \
                f"tela {slug!r} não tem coluna Empresa — não dá para saber de qual CNPJ é a linha: {cols}"
        print("OK certidoes/certidoes-cnd/guias/nfse-emitidas: todas dizem a empresa da linha")

        # A tela de arquivo tem que se DECLARAR arquivo: sem isso, 831 notas velhas passam
        # por faturamento corrente — e foi assim que o KPI de 12 meses errou por 8 meses.
        arq = tela(telas, "nfse")
        assert arq and "arquivo" in (arq.get("sub") or "").lower(), \
            f"tela 'nfse' não avisa que é arquivo anterior a 2026: {arq and arq.get('sub')!r}"
        print("OK nfse: declarada como arquivo, aponta para a tela das notas atuais")

        # As notas atuais precisam estar TODAS na tela nova (era só contagem no KPI).
        n_nac = (await db.execute(text("SELECT count(*) FROM nfse_emitidas_nacional"))).scalar()
        ne = tela(telas, "nfse-emitidas")
        assert len(ne.get("rows") or []) == min(n_nac, 200), \
            f"nfse-emitidas mostra {len(ne.get('rows') or [])} de {n_nac} notas"
        print(f"OK nfse-emitidas: {n_nac} notas de 2026 ganharam tela (antes só existiam como KPI)")

        # ── 4. Empresa que fatura e não tem obrigação = alerta, não zero calado ──
        sem_obr = (await db.execute(text(
            "SELECT coalesce(e.nome_fantasia, e.razao_social) FROM empresas e "
            "WHERE NOT EXISTS (SELECT 1 FROM fiscal_obligations o WHERE o.empresa_id = e.id) "
            "  AND EXISTS (SELECT 1 FROM nfse_emitidas_nacional n WHERE n.empresa_id = e.id)"
        ))).fetchall()
        if sem_obr:
            for (nome,) in sem_obr:
                alvo = next((r for r in linhas if nome.split()[-1] in _texto(r)), None)
                assert alvo and "sem obrigação" in _texto(alvo).lower(), \
                    (f"{nome} fatura e não tem NENHUMA obrigação fiscal cadastrada; a linha "
                     f"mostra zero em silêncio em vez de acusar o buraco")
            print(f"OK buraco denunciado: {len(sem_obr)} empresa(s) faturando sem obrigação cadastrada")
        else:
            print("OK nenhuma empresa fatura sem obrigação cadastrada")

    print("TEST oraculo_fiscal_multicnpj PASS")


if __name__ == "__main__":
    asyncio.run(main())
