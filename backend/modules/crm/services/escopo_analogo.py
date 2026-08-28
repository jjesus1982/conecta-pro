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


# ── REVISÃO DO FUNIL: fazer o funil dizer a verdade ────────────────────────────────────
# Medido em 27/08/2026: 22 propostas em RASCUNHO, R$ 431.880, média de 46 dias. Parte já
# foi ganha ou perdida e ninguém registrou — então o alerta que dispara todo dia está
# PARCIALMENTE ERRADO, e alerta errado ensina a ignorar alerta. Foram 182 notificações em
# 5 dias e ZERO lidas. O Jordan não parou de ler por volume: parou porque o que chega não
# é verdade.
#
# ⭐ MEDIR SALVOU UMA MIGRAÇÃO. A análise dizia "não existe status de perdida" — porque
# olhou os valores EM USO (draft, sent, accepted). O enum `ProposalStatus` tem DEZ, e
# `rejected` está lá desde sempre. Não havia o que criar; havia o que USAR. E a coluna tem
# 42 consumidores literais: inventar valor novo ali era risco puro.
#
# O desenho tem uma regra dura: agrupa por CLIENTE, não lista proposta a proposta. O
# Jordan responde uma vez por cliente e resolve 9 de uma vez. Proposta a proposta seriam
# 20 perguntas — e uma tarde que não vai acontecer.

#: Abaixo disto a proposta é RECENTE e fica fora da revisão: está viva, não é dívida.
#: 7 dias porque é o mesmo corte do alerta de rascunho parado — dois números diferentes
#: para a mesma ideia é como um deles fica errado sem ninguém ver.
DIAS_VIVA = 7


async def revisar_funil(db, *, dias_minimo: int = DIAS_VIVA) -> dict[str, Any]:
    """Propostas em rascunho agrupadas por cliente, da maior para a menor.

    Uma linha por CLIENTE — é assim que a pergunta cabe numa conversa de WhatsApp.
    Devolve também as propostas de cada um, com número e valor, para a segunda pergunta
    ("quais fecharam?") não precisar de outra consulta.
    """
    linhas = (await db.execute(text("""
        SELECT coalesce(client_name, '(sem cliente)') AS cliente,
               p.number, coalesce(p.total, 0) AS total,
               coalesce(p.issue_date::text, p.created_at::date::text) AS data,
               ((now() AT TIME ZONE 'America/Manaus')::date - p.created_at::date) AS dias
        FROM proposals p
        WHERE p.status = 'draft'
        ORDER BY cliente, p.created_at
    """))).mappings().all()

    por_cliente: dict[str, dict[str, Any]] = {}
    for r in linhas:
        c = por_cliente.setdefault(r["cliente"], {"cliente": r["cliente"], "propostas": [],
                                                  "total": 0.0, "dias_max": 0})
        c["propostas"].append({"numero": r["number"], "valor": float(r["total"] or 0),
                               "data": r["data"], "dias": int(r["dias"])})
        c["total"] += float(r["total"] or 0)
        c["dias_max"] = max(c["dias_max"], int(r["dias"]))

    revisar = [c for c in por_cliente.values() if c["dias_max"] >= dias_minimo]
    vivas = [c for c in por_cliente.values() if c["dias_max"] < dias_minimo]
    revisar.sort(key=lambda c: -c["total"])

    # Valor ZERO é achado, não lixo: ou a proposta perdeu o valor, ou é resto de teste.
    # Apagar seria decidir sozinho; nomear deixa o Jordan decidir.
    zerados = [p["numero"] for c in revisar for p in c["propostas"] if p["valor"] == 0]

    return {
        "a_revisar": revisar,
        "clientes": len(revisar),
        "propostas": sum(len(c["propostas"]) for c in revisar),
        "valor_parado": round(sum(c["total"] for c in revisar), 2),
        "fora_por_serem_recentes": [
            {"cliente": c["cliente"], "propostas": len(c["propostas"]),
             "dias": c["dias_max"]} for c in vivas],
        "atencao_valor_zero": zerados or None,
        "como_perguntar": (
            "Pergunte por CLIENTE, do maior valor para o menor, uma pergunta por vez: "
            "'<CLIENTE> — N propostas de <data>, R$ X. O que rolou?'. Se ele disser que "
            "fechou algumas, liste as propostas com número e valor e pergunte QUAIS. "
            "Depois chame `resolver_propostas`. NÃO liste proposta a proposta de cara: "
            "são 20 perguntas e ele não tem a tarde."),
    }
