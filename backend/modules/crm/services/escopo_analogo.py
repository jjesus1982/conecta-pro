"""Escopo por ANALOGIA: o que o Jordan já vendeu num lugar parecido.

Numa visita técnica a pergunta útil não é "o que a norma manda" — é "o que eu fiz da
última vez num caso assim". O Jordan tem 16 propostas com 3+ itens, e elas são o
repertório real dele: poste antivandal com base de concreto, NVR 4 canais PoE, HD Purple,
DPS e aterramento POR RACK, fibra armada com vala, energia solar off-grid onde não chega
luz. Nada disso um modelo precisa inventar — está tudo escrito no histórico.

⭐ ANALOGIA, NUNCA REGRA INVENTADA. Este serviço não deduz "para 8 câmeras use 2 NVR": ele
DEVOLVE a proposta em que o Jordan usou 2 NVR para 8 câmeras, com número e data, para ele
conferir. A diferença importa porque escopo sugerido vira orçamento, orçamento vira
contrato — e um item que não saiu de proposta nenhuma é projeto de segurança inventado,
que sai bonito e diz coisa que ninguém especificou.

Similaridade por SOBREPOSIÇÃO DE TOKENS sobre o termo da busca (não Jaccard): a proposta
tem dezenas de itens e o termo tem poucas palavras; Jaccard puniria a proposta mais
completa, que é justamente a mais útil como ponto de partida.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from sqlalchemy import text

#: Palavras que não distinguem projeto nenhum e inflariam qualquer par.
_VAZIAS = frozenset({
    "com", "sem", "para", "por", "dos", "das", "que", "uma", "num", "nos", "nas",
    "tem", "nao", "sim", "mais", "menos", "ate", "onde", "como", "esta", "estao",
    "kit", "servico", "material", "materiais", "unidade", "unidades",
})

#: Abaixo disto não é parecido — é a proposta menos ruim, e devolver isso como analogia é
#: pior que não devolver nada: o Jordan levaria para a visita um escopo que não serve.
CORTE_PADRAO = 0.25


def _tokens(s: str) -> set[str]:
    t = unicodedata.normalize("NFKD", str(s or "").upper())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return {p for p in re.sub(r"[^A-Z0-9]", " ", t).split()
            if len(p) > 2 and p.lower() not in _VAZIAS}


async def buscar(db, termo: str, *, limite: int = 3,
                 corte: float = CORTE_PADRAO) -> dict[str, Any]:
    """Propostas passadas parecidas com o que foi levantado, com o escopo de cada uma."""
    alvo = _tokens(termo)
    if not alvo:
        return {"termo": termo, "corte": corte, "achados": [],
                "aviso": "informe o que você levantou (ex.: 'CFTV em torre, sem energia, "
                         "120 m do rack') — sem termo não há analogia."}

    linhas = (await db.execute(text("""
        SELECT p.number AS numero,
               coalesce(p.title, '') AS titulo,
               coalesce(p.issue_date::text, p.created_at::date::text) AS data,
               string_agg(i.name, ' | ' ORDER BY i.sort_order) AS blob
        FROM proposals p
        JOIN proposal_items i ON i.proposal_id = p.id
        GROUP BY 1, 2, 3
        HAVING count(i.id) >= 3
    """))).mappings().all()

    ranking = []
    for r in linhas:
        casou = alvo & _tokens(f"{r['titulo']} {r['blob']}")
        s = len(casou) / len(alvo)   # fração do TERMO coberta — ver o docstring
        if s >= corte:
            ranking.append((s, r, sorted(casou)))
    ranking.sort(key=lambda x: (-x[0], x[1]["numero"]))

    achados = []
    for s, r, casou in ranking[:max(1, min(int(limite), 5))]:
        itens = (await db.execute(text(
            "SELECT i.name AS nome, i.quantity AS qtd, i.unit AS unidade, i.code "
            "FROM proposal_items i JOIN proposals p ON p.id = i.proposal_id "
            "WHERE p.number = :n ORDER BY i.sort_order"), {"n": r["numero"]})).mappings().all()
        achados.append({
            "numero": r["numero"], "titulo": r["titulo"], "data": r["data"],
            "similaridade": round(s, 2),
            # ⭐ QUAIS palavras casaram, não só o placar. Medido em 27/08/2026: "controle
            # de acesso facial com catraca" trouxe "Portaria 24h + Limpeza" a 0,60 —
            # casando em PORTARIA e ACESSO, palavras genéricas. O número sozinho parecia
            # boa analogia; a lista de palavras denuncia que não é. Quem apresenta o
            # escopo (modelo ou humano) precisa ver isso, não só o placar.
            "casou_em": casou,
            "itens": [{"nome": x["nome"], "qtd": float(x["qtd"] or 0),
                       "unidade": x["unidade"], "code": x["code"]} for x in itens],
        })

    return {
        "termo": termo, "corte": corte, "achados": achados,
        # Vazio DITO é resultado; vazio silencioso parece sucesso.
        "aviso": (None if achados else
                  f"nenhuma proposta sua passou de {corte:.0%} de semelhança com "
                  f"{termo!r}. Isso é caso NOVO — monte o escopo item a item pelo "
                  f"catálogo, não por analogia."),
        "como_usar": ("Estes são escopos que VOCÊ já vendeu, com número e data para "
                      "conferir. Use como ponto de partida e ajuste — o preço continua "
                      "vindo do catálogo ou de você."),
    }
