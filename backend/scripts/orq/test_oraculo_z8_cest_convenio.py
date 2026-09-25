"""Z8 — o CEST importado do Convênio 142/18 diz a verdade, e o que falta é lacuna declarada.

Nasceu em 25/09/2026, do loop autônomo: o dono mandou popular o CEST dos produtos e a tabela
oficial foi importada do CONFAZ. Superfície nova nasce vigiada.

O QUE ELE AFIRMA

 (a) O **parser** do Convênio lê o que está escrito: NCM completo casa exato, posição/
     subposição casa por prefixo, e **lista de capítulos NÃO casa nada**. A terceira é a que
     importa — «Capítulos 22, 27, 28…» cobriria milhares de NCMs, e no Convênio ela aparece em
     segmento cuja sujeição depende da MODALIDADE de venda (porta a porta), não da mercadoria.

 (b) O **segmento 28** fica fora do casamento. Foi o erro de 2 dos 3 fornecedores que
     declararam CEST errado nas notas de compra desta casa: naftalina e um sensor magnético
     classificados como «venda porta a porta».

 (c) **Ambíguo não vira gravação.** NCM que casa com 2+ CESTs fica NULO, porque escolher entre
     dois exige ler a descrição do produto. Gravar um dos dois seria inventar classificação
     fiscal — e CEST errado vai DENTRO da nota.

 (d) O que está gravado em `ncms.icms_cest` **existe** no Convênio e **cobre** aquele NCM.
     Recontado aqui pelo parser, não lido do que o importador escreveu: a régua não pergunta
     ao medido se a medida está certa.

 (e) **A lacuna é declarada, não silenciosa.** Existe NCM sem CEST e isso é informação
     conclusiva («não é ST em lugar nenhum») — mas só quando o Convênio foi lido. Se o arquivo
     sumir, este oráculo RECUSA em vez de dizer que está tudo bem: `0 gravados` com o arquivo
     ausente é indistinguível de `0 gravados` porque nada casa.

VERMELHO ANTES: em 25/09, antes da frente, `ncms.icms_cest` tinha 0 linhas preenchidas e o
módulo do importador não existia — (a) a (d) davam ImportError.
"""

from __future__ import annotations

import asyncio
import pathlib
import sys

_FISCAL = "/app/scripts/fiscal"
if _FISCAL not in sys.path:
    sys.path.insert(0, _FISCAL)

#: O HTML do Convênio, baixado uma vez. Sem ele o oráculo não mede — e DIZ que não mediu.
CONVENIO = "/app/uploads/_entrada/convenio_icms_142_2018.html"


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory

    falhas: list[str] = []
    medidas: list[str] = []

    if not pathlib.Path(CONVENIO).exists():
        print(f"FALHOU: (e) o Convênio não está em {CONVENIO} — sem ele NÃO DÁ para afirmar nada")
        print("  Baixe: curl -sL -A 'Mozilla/5.0' \\")
        print("    https://www.confaz.fazenda.gov.br/legislacao/convenios/2018/CV142_18 \\")
        print(f"    -o {CONVENIO}")
        print("TOTAL desvios Z8: >0")
        raise SystemExit(1)

    from importar_cest_convenio142 import SEGMENTOS_POR_MODALIDADE, casar, ler_convenio

    tabela = ler_convenio(CONVENIO)
    if len(tabela) < 900:
        falhas.append(f"(a) o parser leu só {len(tabela)} CESTs — o Convênio tem ~1.051; leitura truncada")
    por_cest = {r["cest"]: r for r in tabela}

    # (a) as três formas da coluna NCM/SH
    com_capitulo = [r for r in tabela if not r["ncms"]]
    if not com_capitulo:
        falhas.append("(a) nenhuma linha com «Capítulos …» foi reconhecida — o parser mudou de comportamento")
    for r in com_capitulo[:40]:
        if casar([r], "85437099") or casar([r], "22030000"):
            falhas.append(f"(a) CEST {r['cest']} casa por CAPÍTULO — cobriria milhares de NCMs")
            break
    exato = next((r for r in tabela if any(len(n) == 8 for n in r["ncms"])), None)
    if exato:
        alvo = next(n for n in exato["ncms"] if len(n) == 8)
        if exato["cest"] not in {a["cest"] for a in casar(tabela, alvo)}:
            falhas.append(f"(a) NCM completo {alvo} não casa com o próprio CEST {exato['cest']}")
    medidas.append(f"Convênio: {len(tabela)} CESTs, {len(com_capitulo)} por capítulo (fora do casamento)")

    # (b) segmento 28 nunca casa
    for r in tabela:
        if r["segmento"] in SEGMENTOS_POR_MODALIDADE and r["ncms"]:
            n = next((x for x in r["ncms"] if len(x) == 8), None)
            if n and any(a["segmento"] in SEGMENTOS_POR_MODALIDADE for a in casar(tabela, n)):
                falhas.append(f"(b) o segmento {r['segmento']} (venda por modalidade) voltou a casar — CEST {r['cest']}")
            break
    medidas.append(f"segmentos por modalidade fora do casamento: {sorted(SEGMENTOS_POR_MODALIDADE)}")

    async with async_session_factory() as db:
        gravados = (
            await db.execute(text("SELECT codigo, icms_cest FROM ncms WHERE coalesce(icms_cest,'') <> ''"))
        ).all()
        if not gravados:
            falhas.append("(d) nenhum NCM com CEST gravado — o import não rodou ou foi desfeito")

        # (d) recontagem PRÓPRIA: o que está gravado existe e cobre o NCM
        ruins = 0
        for ncm, cest in gravados:
            reg = por_cest.get(cest)
            if not reg:
                ruins += 1
                if ruins <= 3:
                    falhas.append(f"(d) NCM {ncm} tem CEST {cest} que NÃO existe no Convênio")
                continue
            if not any(len(p) >= 4 and ncm.startswith(p) for p in reg["ncms"]):
                ruins += 1
                if ruins <= 3:
                    falhas.append(f"(d) NCM {ncm} tem CEST {cest}, mas o Convênio associa esse CEST a {reg['ncms'][:2]}")
        medidas.append(f"{len(gravados)} NCM(s) com CEST, {ruins} sem respaldo na recontagem")

        # (c) ambíguo continua NULO
        vazios = set(
            (await db.execute(text("SELECT codigo FROM ncms WHERE length(codigo)=8 AND coalesce(icms_cest,'')=''")))
            .scalars()
            .all()
        )
        amb_gravado = 0
        for ncm, _ in gravados[:4000]:
            if len({a["cest"] for a in casar(tabela, ncm)}) > 1:
                amb_gravado += 1
        if amb_gravado:
            falhas.append(f"(c) {amb_gravado} NCM(s) AMBÍGUO(s) foram gravados — escolher entre 2 CESTs é do contador")
        amb_vazios = sum(1 for n in list(vazios)[:4000] if len({a["cest"] for a in casar(tabela, n)}) > 1)
        medidas.append(f"ambíguos deixados em branco: {amb_vazios} (amostra)")

        # (e) a lacuna é conclusiva: NCM fora do Convênio não é ST
        fora = sum(1 for n in list(vazios)[:4000] if not casar(tabela, n))
        if not fora:
            falhas.append("(e) nenhum NCM ficou FORA do Convênio — suspeito: o casamento está largo demais")
        medidas.append(f"fora do Convênio (não é ST em lugar nenhum): {fora} (amostra)")

    print(" · ".join(medidas))
    for f in falhas:
        print("FALHOU:", f)
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) no CEST do Convênio")
    print(
        "OK CEST: o parser lê as três formas da coluna NCM/SH, capítulo não casa, segmento por "
        "modalidade fica fora, ambíguo não vira gravação, e o que está gravado tem respaldo"
    )
    print(f"TOTAL desvios Z8: {len(falhas)}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        print("TOTAL desvios Z8: >0")
        sys.exit(1)
