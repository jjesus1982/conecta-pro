"""Oráculo — a entrega de uniforme/EPI nunca abre num beco sem saída (28/09/2026).

Por que este oráculo existe: `sst_uniforme_entregas` ficou em **0 linhas desde 12/09/2026** com
escritor pronto, tela no menu e endpoint respondendo 200. Nada estava quebrado. O que havia era um
beco sem saída SILENCIOSO: a entrega é inteiramente a jusante de `sst_uniforme_grade`, o campo
`grade_id` ("SKU*") é o único obrigatório sem default, e com a grade vazia o select saía com
`options: []` e o subtítulo continuava falando de posto e CPF. Quem usa abre a tela, vê um
obrigatório mudo, não tem como descobrir que falta semear o catálogo, e sai. Zero linha não era
defeito de código — era a tela não dizendo o que falta.

A REGRA afirmada (não a fotografia: vale com a grade vazia HOJE e cheia amanhã):

    No formulário `uniforme-entrega-lote`, o select obrigatório `grade_id` está vazio
    SE E SOMENTE SE o subtítulo declara que a grade está vazia e diz onde cadastrar.

As duas metades são afirmadas de propósito. Um oráculo que só testasse a recusa ficaria verde
sobre uma tela que avisa "grade vazia" para sempre, inclusive depois de a grade ser semeada — é o
`feedback_oraculo_cumplice`: toda recusa exige a irmã de caminho feliz. Então:

  1. ESTADO REAL — o que o builder produz agora, com o banco como está, obedece o ⟺.
  2. CAMINHO FELIZ — com uma linha de grade semeada (na MESMA transação, desfeita no fim), o
     select carrega a opção E o aviso desaparece. Prova que o aviso é condicional, não fixo.
  3. LIMPEZA — a semente é desfeita por ROLLBACK e a ausência é reprovada por leitura nova.
     Estas tabelas vivem em 0; uma linha de teste esquecida viraria "a capacidade funciona"
     mentiroso para quem medir depois.

Mede o BUILDER de verdade (`_frente_10.telas`), não uma cópia da regra: se alguém trocar o
subtítulo por um texto fixo, ou devolver o select vazio sem aviso, cai aqui.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho.
"""
from __future__ import annotations

import asyncio
import sys

#: O subtítulo tem de dizer as DUAS coisas: que está vazio, e para onde ir. Um "sem dados" seco
#: deixa quem usa no mesmo beco, só com mais educação.
_DIZ_VAZIO = ("grade está vazia", "grade esta vazia")
_DIZ_ONDE = "Novo SKU"

_SEED_SKU = "ZZ ORACULO BECO"


def _sub_avisa(sub: str) -> bool:
    baixo = (sub or "").lower()
    return any(x in baixo for x in _DIZ_VAZIO) and _DIZ_ONDE.lower() in baixo


async def _tela_lote(db):
    """Constrói as telas de gestão-de-pessoas e devolve (options, sub) do formulário de entrega."""
    from modules.operacional.controllers.redesign_builders._frente_10 import telas

    t = (await telas(db, "gestao-de-pessoas")).get("uniforme-entrega-lote")
    if not isinstance(t, dict):
        raise AssertionError(
            "tela 'uniforme-entrega-lote' não foi construída — o formulário de entrega não existe "
            "para quem usa (builder quebrado ou removido)"
        )
    campos = {c.get("key"): c for c in t.get("fields", []) if isinstance(c, dict)}
    if "grade_id" not in campos:
        raise AssertionError("o formulário de entrega não tem o campo 'grade_id' — sem SKU não há entrega")
    return campos["grade_id"].get("options") or [], t.get("sub") or ""


async def main() -> int:
    from sqlalchemy import text

    from core.database import get_db

    falhas: list[str] = []
    gen = get_db()
    db = await gen.__anext__()
    try:
        if not (await db.execute(text("SELECT to_regclass('public.sst_uniforme_grade')"))).scalar():
            print("FALHOU: sst_uniforme_grade não existe — a grade que alimenta a entrega não tem mecanismo")
            raise AssertionError("mecanismo de grade ausente")

        # ── 1) estado real ────────────────────────────────────────────────────────────────────
        opts, sub = await _tela_lote(db)
        avisa = _sub_avisa(sub)
        n_grade = (await db.execute(text("SELECT count(*) FROM sst_uniforme_grade WHERE ativo"))).scalar() or 0
        print(f"estado real: grade ativa={n_grade} · options do SKU={len(opts)} · subtítulo avisa={avisa}")
        if not opts and not avisa:
            falhas.append(
                "BECO SEM SAÍDA: 'SKU*' é obrigatório, está com 0 opções e o subtítulo não diz que a "
                f"grade está vazia nem onde cadastrar. Subtítulo atual: {sub!r}"
            )
        if opts and avisa:
            falhas.append(
                f"a grade tem {len(opts)} SKU(s) e o subtítulo ainda avisa que está vazia — aviso fixo, "
                "não condicional; quem usa é mandado cadastrar o que já existe"
            )

        # ── 2) caminho feliz: com grade semeada, carrega e não avisa ─────────────────────────
        # Semeia na MESMA sessão/transação — o builder usa este `db`, então vê a linha, e o
        # ROLLBACK no fim não deixa nada. Sem commit em nenhum ponto.
        await db.execute(
            text(
                "INSERT INTO sst_uniforme_grade (item, tamanho, sku_norm, minimo, maximo, atual, ativo) "
                "VALUES (:i, 'M', :n, 1, 9, 5, true) ON CONFLICT (sku_norm) DO NOTHING"
            ),
            {"i": _SEED_SKU, "n": f"{_SEED_SKU} M"},
        )
        opts2, sub2 = await _tela_lote(db)
        rotulos = " | ".join(str(o.get("label", "")) for o in opts2)
        if not any(_SEED_SKU in str(o.get("label", "")) for o in opts2):
            falhas.append(
                f"com a grade semeada o select NÃO carregou o SKU '{_SEED_SKU}' — a tela não lê a grade "
                f"(options={rotulos!r})"
            )
        if _sub_avisa(sub2):
            falhas.append(
                f"com {len(opts2)} SKU(s) na grade o subtítulo ainda avisa 'grade vazia' — o aviso não é "
                f"condicional. Subtítulo: {sub2!r}"
            )
        else:
            print(f"caminho feliz: options={len(opts2)} (contém a semente) · aviso sumiu  OK")

        # ── 3) limpeza provada por leitura, não pela linha de saída ─────────────────────────
        await db.rollback()
        resto = (
            await db.execute(text("SELECT count(*) FROM sst_uniforme_grade WHERE sku_norm = :n"), {"n": f"{_SEED_SKU} M"})
        ).scalar() or 0
        if resto:
            falhas.append(f"LIMPEZA FALHOU: {resto} linha(s) da semente '{_SEED_SKU}' sobraram na grade — apague à mão")
        else:
            print("limpeza: semente desfeita por rollback e ausência confirmada por leitura nova  OK")
    finally:
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001 — sessão já fechada não é resultado do oráculo
            pass
        await gen.aclose()

    if falhas:
        for f in falhas:
            print(f"FALHOU: {f}")
        print(f"VERMELHO: {len(falhas)} desvio(s) — a entrega de uniforme/EPI abre sem dizer o que falta")
        return 1
    print("VERDE: o formulário de entrega nunca oferece 'SKU*' vazio sem dizer que a grade está vazia e onde cadastrar")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
