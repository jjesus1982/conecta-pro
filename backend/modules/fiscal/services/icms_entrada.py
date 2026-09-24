"""AA5 — como a mercadoria ENTROU: o fato que decide o ICMS da SAÍDA (24/09/2026).

**O defeito.** Até hoje a régua de tributação (`fiscal/services/tributacao_nfe.py`) devolvia
CFOP 5102 / CST 00 / ICMS 20% para toda venda interna no Amazonas. Medido no container de
produção com os seis produtos da NF-e nº 10.026 da própria empresa: **5102 nos seis**. A nota
real — autorizada pela SEFAZ-AM em 17/09/2026, protocolo 113263811849419 — saiu com
**CFOP 5405 · CST 060 · BC ICMS 0,00 · V.ICMS 0,00** nos seis. CST 060 é *ICMS cobrado
anteriormente por substituição tributária*: o imposto foi pago na COMPRA. O sistema cobraria de
novo.

**Por que isso não é um caso isolado.** 209 itens lidos dos XMLs de NF-e de entrada
(`nfe_entradas.xml_raw`, 51 notas de fornecedores de Manaus), em 24/09/2026:

    CST de ICMS na entrada : 60 → 97 · 00 → 73 · 20 → 5 · 50 → 5 · 41 → 4
    CSOSN na entrada       : 102 → 13 · 500 → 9 · 400 → 1      (2 itens sem grupo de ICMS)
    com ICMS já retido por ST (CST 10/30/60/70 · CSOSN 201/202/203/500) : 106 de 209 = 50,7%
    CFOP de entrada desses 106 : 5929 → 61 · 5405 → 44 · 5403 → 1

Metade do que a casa compra já vem com o ICMS retido. Vender isso com CST 00 é pagar duas vezes.

**Onde o fato mora, e por quê.** Em duas colunas de `fin_produtos`, o catálogo fiscal que já
existe: `icms_entrada_cst` e `icms_entrada_fonte`. Três números decidiram:

1. `fin_produtos.codigo` **é** o `cProd` da nota de entrada — as 95 linhas nasceram de lá
   (`produto_fiscal.semear`). Casamento medido: **95 de 95**. Não precisa de tabela de ligação.
2. O fato é estável por PRODUTO: dos 147 `cProd` das notas de entrada, **zero** têm entradas com
   CST divergente entre si.
3. O fato **não** é do NCM: **5 NCMs** (34054000, 40151900, 94032090, 85365090, 34052000) têm
   entradas divergentes — o mesmo NCM entrando com e sem ST. Por isso não há busca por NCM aqui;
   seria chute com outro nome.

Tabela própria não se justificou (relação 1:1 com o produto, um fato por linha) e derivar na hora
também não: `calcular_puro` é puro e sem I/O de propósito — é o que o emissor chama por item.

**Nada é inferido.** Produto sem entrada conhecida fica com a coluna NULL e a régua **recusa** a
nota, com mensagem que ensina. Quem sabe o fato e não o tem em XML registra por
`registrar()` — e a fonte escrita por essa pessoa fica gravada ao lado do número.
"""

from __future__ import annotations

import logging

from sqlalchemy import text

from modules.fiscal.services.tributacao_nfe import (
    ICMS_ENTRADA_COM_ST,
    ICMS_ENTRADA_NORMAL,
    classificar_entrada,
)

logger = logging.getLogger(__name__)

#: rótulo dos três baldes, na ordem em que a tela e o relatório leem.
SITUACOES = {
    "st": "ICMS já retido por ST na entrada — sai CFOP 5405 / CST 060, sem ICMS",
    "normal": "entrou tributada — sai CFOP 5102 / CST 00, ICMS 20%",
    None: "não se sabe como entrou — a régua recusa a nota até alguém registrar",
}


async def _ensure(db) -> None:
    """DDL idempotente. As duas colunas ao lado do CEST, que veio do mesmo XML."""
    from modules.financial.services.produto_fiscal import _ensure as _ensure_catalogo

    await _ensure_catalogo(db)  # cria `fin_produtos` se ainda não existir (frente Z1)
    for ddl in (
        "ALTER TABLE fin_produtos ADD COLUMN IF NOT EXISTS icms_entrada_cst VARCHAR(4)",
        "ALTER TABLE fin_produtos ADD COLUMN IF NOT EXISTS icms_entrada_fonte TEXT",
    ):
        await db.execute(text(ddl))
    await db.commit()


# ──────────────────────────── ler o fato do XML da nota de entrada ────────────────────────────


async def sincronizar(db) -> dict:
    """Preenche as duas colunas a partir dos XMLs de NF-e de ENTRADA. Idempotente.

    Só grava onde `icms_entrada_cst` está NULL: o que uma pessoa registrou à mão nunca é
    sobrescrito por um XML que chegou depois. Se houver mais de uma entrada do mesmo `cProd`,
    vence a **mais recente** (maior `nfe_entradas.id`) — medido em 24/09/2026: nenhum dos 147
    códigos tem entradas divergentes, então a regra hoje não desempata nada; ela existe para o
    dia em que desempatar.
    """
    await _ensure(db)
    from modules.financial.services.produto_fiscal import _itens_do_xml

    rows = (
        await db.execute(
            text(
                "SELECT id, coalesce(chave_acesso,''), coalesce(numero,''), coalesce(emitente_nome,''), "
                "coalesce(to_char(data_emissao,'DD/MM/YYYY'),''), xml_raw FROM nfe_entradas "
                "WHERE xml_raw IS NOT NULL AND length(xml_raw) > 500 ORDER BY id"
            )
        )
    ).fetchall()
    mapa: dict[str, tuple[str, str]] = {}
    for _id, chave, numero, emitente, data, xml in rows:
        for cprod, campos in _itens_do_xml(xml).items():
            cst = (campos.get("icms_cst") or "").strip()
            if not cst:
                continue
            fonte = (
                f"NF-e de entrada nº {numero or '?'} de {emitente or 'fornecedor não identificado'}"
                + (f", emitida em {data}" if data else "")
                + (f", chave {chave}" if chave else "")
                + f" — item «{cprod}» com CST/CSOSN de ICMS {cst}"
                + (f", CFOP {campos.get('cfop')}" if campos.get("cfop") else "")
            )
            mapa[cprod] = (cst, fonte)  # ordem por id: a última entrada vence

    gravados = 0
    for cprod, (cst, fonte) in mapa.items():
        r = await db.execute(
            text(
                "UPDATE fin_produtos SET icms_entrada_cst = :cst, icms_entrada_fonte = :fonte, "
                "atualizado_em = now() WHERE codigo = :cod AND icms_entrada_cst IS NULL"
            ),
            {"cst": cst[:4], "fonte": fonte, "cod": cprod},
        )
        gravados += r.rowcount or 0
    await db.commit()
    return {"itens_com_cst_no_xml": len(mapa), "produtos_preenchidos": gravados}


# ─────────────────────────────────── ler / registrar o fato ───────────────────────────────────


async def do_produto(db, codigo: str) -> dict | None:
    """O fato de UM produto, pelo código. Sem busca por NCM: ver §3 do docstring do módulo."""
    cod = str(codigo or "").strip()
    if not cod:
        return None
    r = (
        await db.execute(
            text(
                "SELECT codigo, descricao, coalesce(ncm,''), icms_entrada_cst, icms_entrada_fonte "
                "FROM fin_produtos WHERE codigo = :cod"
            ),
            {"cod": cod},
        )
    ).first()
    if not r:
        return None
    return {
        "codigo": r[0],
        "descricao": r[1],
        "ncm": r[2],
        "icms_entrada_cst": r[3],
        "icms_entrada_fonte": r[4],
        "situacao": classificar_entrada(r[3]),
    }


async def enriquecer_itens(db, itens: list[dict]) -> list[dict]:
    """Põe `icms_entrada_cst`/`icms_entrada_fonte` em cada item da nota, vindo do CATÁLOGO.

    **De propósito o fato NÃO vem do payload da emissão.** Se viesse, qualquer chamada poderia
    declarar «entrou com ST» e ganhar ICMS zero sem nenhum documento por trás. Vem do catálogo,
    onde ou foi lido do XML da entrada ou foi registrado por uma pessoa com a fonte escrita.
    Item sem `codigo`, ou com código que não está no catálogo, sai sem o fato — e a régua recusa.
    """
    if not itens:
        return itens
    await _ensure(db)
    codigos = [str(i.get("codigo") or "").strip() for i in itens]
    if not any(codigos):
        for item in itens:
            item["icms_entrada_cst"] = None
            item["icms_entrada_fonte"] = None
        return itens
    conhecidos = {
        r[0]: (r[1], r[2])
        for r in (
            await db.execute(
                text("SELECT codigo, icms_entrada_cst, icms_entrada_fonte FROM fin_produtos WHERE codigo = ANY(:cods)"),
                {"cods": [c for c in codigos if c]},
            )
        ).fetchall()
    }
    for item, cod in zip(itens, codigos, strict=False):
        cst, fonte = conhecidos.get(cod, (None, None))
        item["icms_entrada_cst"] = cst
        item["icms_entrada_fonte"] = fonte
    return itens


async def registrar(db, *, codigo: str, cst: str, fonte: str, quem: str) -> dict:
    """A porta do humano: registrar como a mercadoria entrou, com a fonte escrita ao lado.

    `fonte` é obrigatória e vai inteira para o banco junto com quem registrou e quando. Um número
    fiscal sem de-onde-veio é exatamente o que esta casa não aceita.
    """
    await _ensure(db)
    cod = str(codigo or "").strip()
    c = str(cst or "").strip()
    f = str(fonte or "").strip()
    if not cod or not c or not f:
        raise ValueError("Informe o produto, o CST/CSOSN de ICMS da entrada e a fonte (o documento que prova).")
    if classificar_entrada(c) is None:
        raise ValueError(
            f"CST/CSOSN «{c}» não tem tratamento de saída com fonte neste repositório. Com fonte estão "
            f"{', '.join(sorted(ICMS_ENTRADA_COM_ST))} (ICMS já retido por ST) e "
            f"{', '.join(sorted(ICMS_ENTRADA_NORMAL))} (tributação normal). Redução de base, suspensão, "
            "diferimento e isenção ficam para decisão do contador — não invente aqui."
        )
    r = await db.execute(
        text(
            "UPDATE fin_produtos SET icms_entrada_cst = :cst, "
            "icms_entrada_fonte = :fonte || ' — registrado por ' || :quem || ' em ' || "
            "to_char(now(), 'DD/MM/YYYY HH24:MI'), atualizado_em = now() WHERE codigo = :cod"
        ),
        {"cst": c[:4], "fonte": f, "quem": quem or "(não identificado)", "cod": cod},
    )
    if not r.rowcount:
        raise ValueError(
            f"Produto «{cod}» não está em `fin_produtos`. Cadastre o produto antes de registrar a entrada."
        )
    await db.commit()
    return {"codigo": cod, "icms_entrada_cst": c, "situacao": classificar_entrada(c)}


async def resumo(db) -> dict:
    """Quantos produtos têm tratamento conhecido e quantos não — o número que o dono precisa ver."""
    await _ensure(db)
    linhas = (
        await db.execute(
            text(
                "SELECT codigo, descricao, coalesce(ncm,''), icms_entrada_cst, coalesce(icms_entrada_fonte,'') "
                "FROM fin_produtos ORDER BY codigo"
            )
        )
    ).fetchall()
    baldes = {"st": 0, "normal": 0, "sem_fonte": 0}
    por_cst: dict[str, int] = {}
    for _cod, _desc, _ncm, cst, _f in linhas:
        s = classificar_entrada(cst)
        baldes["sem_fonte" if s is None else s] += 1
        por_cst[cst or "(vazio)"] = por_cst.get(cst or "(vazio)", 0) + 1
    catalogo_bling = (await db.execute(text("SELECT count(*) FROM products"))).scalar() or 0
    bling_com_fato = (
        await db.execute(
            text(
                "SELECT count(*) FROM products p WHERE EXISTS (SELECT 1 FROM fin_produtos f "
                "WHERE f.codigo = p.code AND f.icms_entrada_cst IS NOT NULL)"
            )
        )
    ).scalar() or 0
    return {
        "fin_produtos": len(linhas),
        **baldes,
        "por_cst_de_entrada": por_cst,
        "products": catalogo_bling,
        "products_com_fato": bling_com_fato,
        "products_sem_fato": catalogo_bling - bling_com_fato,
        "linhas": [
            {
                "codigo": c,
                "descricao": d,
                "ncm": n,
                "cst": cst,
                "situacao": classificar_entrada(cst),
                "fonte": f,
            }
            for c, d, n, cst, f in linhas
        ],
    }
