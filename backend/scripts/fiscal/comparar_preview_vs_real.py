#!/usr/bin/env python3
"""O XML do PREVIEW diz o mesmo que o XML que a SEFAZ autorizou?

`nfe-preview` («Conferir antes de transmitir») monta o XML com `xml.etree` da stdlib;
a emissão real monta com a PyNFe, por dentro do `nfe_provider`. **São duas implementações da
mesma regra** — e a razão é legítima (o preview roda sem certificado e sem rede).

Mas duas implementações divergem, e a divergência aqui é perigosa numa direção específica:
**um preview limpo autoriza o clique irreversível.** Foi o que quase aconteceu em 25/09/2026,
quando três chaves trocadas entre a tela e o emissor faziam a nota ser recusada — e nenhuma
delas apareceria no preview, porque ele lê `cab`/`itens` direto e não passa pelo dicionário
que o emissor consome.

Este script compara campo a campo o preview com o XML **autorizado** de notas que já
existem. Divergência aqui não é bug do preview nem do emissor: é a distância entre os dois,
e ela é a medida do risco de confiar na conferência.

Uso (dentro do container):
    python3 backend/scripts/fiscal/comparar_preview_vs_real.py

Linha canônica: `TOTAL: <n> campo(s) em que o preview difere do XML autorizado`.
"""

from __future__ import annotations

import asyncio
import re
import sys

sys.path.insert(0, "/app")

#: Campos que a SEFAZ lê e que quem confere precisa ver iguais. `Id`/chave e assinatura ficam
#: de fora de propósito: a chave só existe depois da emissão e a assinatura nunca está no
#: preview — divergir neles é esperado e não informa nada.
CAMPOS = (
    "tpAmb", "natOp", "mod", "serie", "nNF", "tpNF", "idDest", "cMunFG", "finNFe",
    "CNPJ", "xNome", "IE", "CRT", "xLgr", "nro", "xBairro", "xMun", "UF", "CEP",
    "indIEDest", "email", "NCM", "CFOP", "CST", "CSOSN", "orig", "vUnCom", "vProd",
    "qCom", "uCom", "vBC", "vICMS", "vPIS", "vCOFINS", "vNF", "infCpl",
)


#: Diferenças ESPERADAS, que não são defeito e só fariam ruído. Cada uma tem razão escrita:
#: ler «67 campos diferentes» quando 60 são estruturais é o mesmo que não medir.
_ESPERADO = {
    # o XML autorizado é `nfeProc` = NFe + protNFe; o preview é só a NFe. O protocolo repete
    # tpAmb e chave, então as listas ficam com um item a mais.
    "tpAmb",
    # a PyNFe acrescenta `infRespTec` (responsável técnico) com CNPJ e e-mail próprios — bloco
    # que o preview não monta e que não é conferido por ninguém na tela.
    "email",
    # em HOMOLOGAÇÃO a SEFAZ exige que o destinatário vire «NF-E EMITIDA EM AMBIENTE DE
    # HOMOLOGACAO - SEM VALOR FISCAL» e o CNPJ vire 99999999000191. O preview mostra o
    # destinatário REAL, que é o que quem confere quer ver.
    "xNome",
    "CNPJ",
}

#: Tags de número: comparar «3.0000» com «3.0» como texto acusa diferença que não existe.
_NUMERICAS = {"vUnCom", "qCom", "vProd", "vBC", "vICMS", "vPIS", "vCOFINS", "vNF"}


def _norm_num(v: str) -> str:
    try:
        return f"{float(v):.4f}"
    except ValueError:
        return v


def _tags(xml: str, tag: str) -> list[str]:
    """Valores de uma tag, ignorando prefixo de namespace (`ns0:` etc.)."""
    vals = re.findall(rf"<(?:\w+:)?{tag}>([^<]*)</(?:\w+:)?{tag}>", xml)
    return [_norm_num(v) for v in vals] if tag in _NUMERICAS else vals


async def main() -> int:
    try:
        from sqlalchemy import text  # noqa: PLC0415

        from core.database import async_session_factory  # noqa: PLC0415

        from modules.operacional.controllers.redesign_builders._dgx_z3_tela_nfe import (  # noqa: PLC0415
            carregar_nota,
            xml_preview,
        )
    except ModuleNotFoundError as e:
        print(f"RECUSO: roda DENTRO do container ({e})")
        return 2

    divergencias = 0
    async with async_session_factory() as db:
        notas = (
            await db.execute(
                text(
                    "SELECT id::text, numero, serie, tp_amb FROM nfes"
                    " WHERE coalesce(xml_autorizado,'') <> '' ORDER BY tp_amb DESC, numero DESC LIMIT 6"
                )
            )
        ).all()
        if not notas:
            print("nenhuma nota autorizada com XML para comparar")
            return 0
        for nid, numero, serie, tp_amb in notas:
            cab, itens = await carregar_nota(db, nid)
            real = cab.get("xml_autorizado") or ""
            prev = xml_preview(cab, itens)
            amb = "PRODUCAO" if tp_amb == "1" else "homologacao"
            difs, ruido = [], 0
            for tag in CAMPOS:
                a, b = _tags(prev, tag), _tags(real, tag)
                if a == b:
                    continue
                if tag in _ESPERADO:
                    ruido += 1
                    continue
                # o real repete valores por item + total; o preview pode agrupar. Compara
                # como CONJUNTO quando a diferença é só repetição.
                if set(a) == set(b):
                    ruido += 1
                    continue
                difs.append((tag, a[:4], b[:4]))
            print(f"── nota {numero}/{serie} ({amb}): {len(difs)} divergência(s) reais · {ruido} diferença(s) esperada(s)")
            for tag, a, b in difs:
                print(f"     {tag:<10} preview={a}")
                print(f"     {'':<10} real   ={b}")
            divergencias += len(difs)

    print(f"\nTOTAL: {divergencias} divergencia(s) reais entre o preview e o XML autorizado")
    if divergencias:
        print("  Cada linha acima é algo que quem confere VÊ diferente do que a SEFAZ recebeu.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
