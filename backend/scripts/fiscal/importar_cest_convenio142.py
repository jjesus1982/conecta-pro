#!/usr/bin/env python3
"""Popula `ncms.icms_cest` a partir do **Convênio ICMS 142/2018** (CONFAZ).

O CEST diz a que SEGMENTO da substituição tributária a mercadoria pertence. Ele é campo
OBRIGATÓRIO na NF-e sempre que a operação é de ST — emitir CST 60 sem CEST é campo faltando,
e a SEFAZ rejeita.

## Por que a fonte tem de ser o Convênio, e não a nota do fornecedor

Medido em 25/09/2026, cruzando os 14 CESTs que fornecedores declararam nas notas de compra
desta casa contra a tabela oficial: **11 conferem e 3 estão ERRADOS.**

  · um **controle remoto de portão** (NCM 8526.92.00) declarado como CEST 01.999.00 —
    «outras peças e acessórios para veículos automotores». Não é autopeça.
  · **naftalina** (2902.90.20) como CEST 28.043.00 — segmento 28 é «venda porta a porta»,
    e o NCM do item é 4202.92.00 (artefatos de plástico).
  · um **sensor magnético** (8543.70.99) como CEST 28.063.00 — «produtos de limpeza e
    conservação doméstica», também do segmento porta a porta.

Copiar o CEST do fornecedor para a nossa nota de saída propaga o erro dele com o nosso CNPJ
embaixo. Por isso: **Convênio manda; declaração de terceiro é indício.**

## Como o casamento é feito, e onde ele PARA

A coluna «NCM/SH» do Convênio tem três formas, e só duas são aproveitáveis aqui:

  · **NCM completo** («3925.10.00») → casa exato.
  · **posição/subposição** («3917», «3925.90») → casa por PREFIXO.
  · **lista de capítulos** («Capítulos 22, 27, 28…») → **IGNORADA**. É larga demais: casaria
    milhares de NCMs, e no Convênio ela aparece em segmentos cuja aplicação depende da
    MODALIDADE de venda (porta a porta), não da mercadoria. Casar por capítulo daria CEST a
    produto que não é ST — o oposto do que este script existe para fazer.

Quando um NCM casa com **mais de um CEST**, nada é gravado e a ambiguidade vai para o
relatório: escolher entre dois exige ler a descrição do produto, e isso é do contador.

## Uso

    # 1) baixar o HTML do Convênio (uma vez)
    curl -sL -A "Mozilla/5.0" \\
      https://www.confaz.fazenda.gov.br/legislacao/convenios/2018/CV142_18 -o /tmp/cv142.html

    # 2) conferir sem gravar
    python3 backend/scripts/fiscal/importar_cest_convenio142.py /tmp/cv142.html

    # 3) gravar
    python3 backend/scripts/fiscal/importar_cest_convenio142.py /tmp/cv142.html --aplicar

Linha canônica: `TOTAL: <n> NCM(s) com CEST gravado`.
"""

from __future__ import annotations

import asyncio
import re
import sys
from html import unescape

#: Segmentos do Convênio cuja aplicação depende da MODALIDADE de venda, não da mercadoria.
#: 28 = «venda de mercadorias pelo sistema porta a porta». Casar por eles daria CEST a produto
#: que, na venda normal, não é ST. Foi exatamente o erro de dois fornecedores desta casa.
SEGMENTOS_POR_MODALIDADE = {"28"}


def _limpa(s: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def ler_convenio(caminho: str) -> list[dict]:
    """HTML do Convênio → [{cest, ncms, descricao}]. Função pura: o oráculo bate nela."""
    html = open(caminho, encoding="utf-8", errors="ignore").read()
    vistos: set[str] = set()
    saida: list[dict] = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
        cols = [_limpa(t) for t in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
        if len(cols) < 3:
            continue
        i = next((k for k, c in enumerate(cols) if re.fullmatch(r"\d{2}\.\d{3}\.\d{2}", c)), None)
        if i is None:
            continue
        cest = cols[i].replace(".", "")
        if cest in vistos:
            continue
        vistos.add(cest)
        resto = cols[i + 1 :]
        if not resto:
            continue
        ncm_txt, desc = resto[0], " ".join(resto[1:]).strip()
        # «Capítulos 22, 27…» é lista de capítulos: não vira casamento (ver docstring).
        if "apítulo" in ncm_txt:
            ncms: list[str] = []
        else:
            ncms = [n.replace(".", "") for n in re.findall(r"\b\d{4}(?:\.\d{2}){0,2}\b", ncm_txt)]
        saida.append({"cest": cest, "ncms": ncms, "descricao": (desc or ncm_txt)[:300], "segmento": cest[:2]})
    return saida


def casar(tabela: list[dict], ncm: str) -> list[dict]:
    """CESTs cujo NCM/SH cobre este NCM de 8 dígitos. Prefixo, nunca capítulo."""
    fora = SEGMENTOS_POR_MODALIDADE
    return [
        r
        for r in tabela
        if r["segmento"] not in fora and any(len(p) >= 4 and ncm.startswith(p) for p in r["ncms"])
    ]


async def main() -> int:
    aplicar = "--aplicar" in sys.argv
    caminho = next((a for a in sys.argv[1:] if not a.startswith("--")), "")
    if not caminho:
        print("uso: importar_cest_convenio142.py <html-do-convenio> [--aplicar]")
        return 2
    try:
        from sqlalchemy import text  # noqa: PLC0415

        from core.database import async_session_factory  # noqa: PLC0415
    except ModuleNotFoundError:
        print("RECUSO: roda DENTRO do container (precisa do banco)")
        return 2

    tabela = ler_convenio(caminho)
    com_ncm = sum(1 for r in tabela if r["ncms"])
    por_modalidade = sum(1 for r in tabela if r["segmento"] in SEGMENTOS_POR_MODALIDADE)
    print(f"Convênio lido: {len(tabela)} CESTs · {com_ncm} com NCM aproveitável · {por_modalidade} de segmento por modalidade (ignorados)")

    gravados = ambiguos = sem_cest = 0
    exemplos_amb: list[str] = []
    async with async_session_factory() as db:
        ncms = (await db.execute(text("SELECT codigo FROM ncms WHERE length(codigo) = 8"))).scalars().all()
        print(f"NCMs de 8 dígitos na tabela oficial da casa: {len(ncms)}\n")
        for n in ncms:
            achados = casar(tabela, n)
            if not achados:
                sem_cest += 1
                continue
            if len({a["cest"] for a in achados}) > 1:
                ambiguos += 1
                if len(exemplos_amb) < 6:
                    exemplos_amb.append(f"  NCM {n} casa com {sorted({a['cest'] for a in achados})}")
                continue
            if aplicar:
                await db.execute(
                    text("UPDATE ncms SET icms_cest = CAST(:c AS VARCHAR), updated_at = now() WHERE codigo = CAST(:n AS VARCHAR)"),
                    {"c": achados[0]["cest"], "n": n},
                )
            gravados += 1
        if aplicar:
            await db.commit()

    if exemplos_amb:
        print("AMBÍGUOS (mais de um CEST para o mesmo NCM — precisa da descrição, é do contador):")
        print("\n".join(exemplos_amb))
    print(f"\n  sem CEST no Convênio (NÃO é ST em lugar nenhum): {sem_cest}")
    print(f"  ambíguos                                        : {ambiguos}")
    print(f"\nTOTAL: {gravados} NCM(s) com CEST {'gravado' if aplicar else 'a gravar'}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    raise SystemExit(asyncio.run(main()))
