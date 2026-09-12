"""Procedência do custo — Bloco 3 do prompt de 11/09/2026.

⚠️ NÃO é catálogo de preço, e isso é decisão do Jordan: não existe e não deve existir tabela
fixa de preço de equipamento. Orçamento de eletrônica é montado por demanda — o fornecedor
cota, o projeto muda, o preço muda.

O que faltava é outra coisa. Na PROP-2026-00114 o custo entrou como estimativa de mercado e
a única marca disso era uma observação escrita à mão — que vazou para o PDF do cliente, com
a margem junto. A pergunta "esse preço é firme ou é chute?" tinha resposta em texto livre
que ora estava em `payment_terms`, ora em `notes`, ora no papel do cliente.

⭐ A pergunta passa a ter resposta em DADO consultável:

    origem_custo ∈ {cotacao_firme, estimativa_mercado, historico_compra}

Regras, todas do Bloco 3:
  · `origem_custo` é OBRIGATÓRIO quando há custo. Item de custo sem procedência não existe;
  · proposta com qualquer `estimativa_mercado` NÃO transita para `enviada` sem
    `aceito_com_estimativa` registrado — com quem aceitou e quando. O aviso vai para quem
    DECIDE, nunca para dentro do PDF do cliente;
  · cotação com `validade_cotacao` vencida na data do envio bloqueia com `COTACAO_VENCIDA`.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

ORIGENS = ("cotacao_firme", "estimativa_mercado", "historico_compra")

# ⚠️ Aceita `number` OU o id. Os resolvedores tolerantes do MCP devolvem o UUID, e consultar
# só por `number` fazia a proposta "não existir" tendo sido achada. É a terceira vez que
# este descasamento aparece em 11/09 — identificador certo para a consulta errada falha tão
# bem quanto identificador errado.
# o que cada origem significa para quem vai decidir. Sigla não decide nada.
O_QUE_SIGNIFICA = {
    "cotacao_firme": "fornecedor cotou por escrito e a cotação está dentro da validade",
    "estimativa_mercado": "PREÇO NÃO CONFIRMADO — estimativa de mercado, pode mudar",
    "historico_compra": "preço de uma compra anterior nossa; o mercado pode ter mudado",
}


class BloqueioDeEnvio(Exception):
    """Recusa de transitar para enviada. Carrega o código e o que falta resolver."""

    def __init__(self, codigo: str, mensagem: str, detalhes: list[dict],
                 dica: str = "") -> None:
        self.codigo, self.detalhes, self.dica = codigo, detalhes, dica
        super().__init__(mensagem)

    def envelope(self) -> dict:
        return {"ok": False, "codigo": self.codigo, "http": 409,
                "mensagem": str(self), "dica": self.dica, "itens": self.detalhes}


async def itens_com_procedencia(db: AsyncSession, numero: str) -> list[dict]:
    rs = (await db.execute(text(
        "SELECT i.name, i.custo_unitario::float AS custo_unitario, i.origem_custo, "
        "       i.fornecedor, i.data_cotacao::text AS data_cotacao, "
        "       i.validade_cotacao::text AS validade_cotacao, i.natureza_item "
        "  FROM proposal_items i "
        "  JOIN proposals p ON p.id = i.proposal_id "
        " WHERE (p.number = :n OR p.id::text = :n) AND coalesce(i.is_active, true) "
        " ORDER BY i.sort_order"), {"n": numero})).mappings().all()
    fora = []
    for r in rs:
        d = dict(r)
        d["origem_significa"] = O_QUE_SIGNIFICA.get(str(r["origem_custo"] or ""), None)
        fora.append(d)
    return fora


async def pode_enviar(db: AsyncSession, numero: str, *, hoje: date | None = None) -> dict:
    """Levanta `BloqueioDeEnvio` quando não pode. Devolve o diagnóstico quando pode.

    ⚠️ A ORDEM das checagens não é arbitrária. Cotação vencida vem ANTES da estimativa:
    uma cotação que expirou é um preço que já não existe, e aceitar estimativa não conserta
    isso. Aceitar primeiro e depois descobrir o vencimento seria pedir duas decisões ao dono
    quando uma já bastava para recusar.
    """
    hoje = hoje or date.today()
    cab = (await db.execute(text(
        "SELECT p.status, coalesce(p.aceito_com_estimativa,false) AS aceito, "
        "       p.aceito_com_estimativa_por AS por, "
        "       p.aceito_com_estimativa_em::text AS em "
        "  FROM proposals p WHERE (p.number = :n OR p.id::text = :n)"),
        {"n": numero})).mappings().first()
    if not cab:
        raise BloqueioDeEnvio("PROPOSTA_NAO_ENCONTRADA", f"Não achei a proposta {numero}.", [])

    itens = await itens_com_procedencia(db, numero)
    com_custo = [i for i in itens if i["custo_unitario"] is not None]

    sem_origem = [i for i in com_custo if not i["origem_custo"]]
    if sem_origem:
        raise BloqueioDeEnvio(
            "CUSTO_SEM_PROCEDENCIA",
            f"{len(sem_origem)} item(ns) têm custo e nenhuma procedência declarada.",
            sem_origem,
            dica="Informe `origem_custo` em cada item: " + " | ".join(ORIGENS))

    vencidas = [i for i in com_custo
                if i["validade_cotacao"] and i["validade_cotacao"][:10] < hoje.isoformat()]
    if vencidas:
        raise BloqueioDeEnvio(
            "COTACAO_VENCIDA",
            f"{len(vencidas)} cotação(ões) venceram antes de hoje ({hoje.isoformat()}).",
            vencidas,
            dica="Peça nova cotação ao fornecedor e atualize `validade_cotacao`. Preço "
                 "vencido é preço que já não existe.")

    estimativas = [i for i in com_custo if i["origem_custo"] == "estimativa_mercado"]
    if estimativas and not cab["aceito"]:
        raise BloqueioDeEnvio(
            "ESTIMATIVA_NAO_ACEITA",
            f"{len(estimativas)} item(ns) com custo de ESTIMATIVA DE MERCADO, não cotação "
            f"firme. Enviar assim é assumir o risco do preço mudar depois da assinatura.",
            estimativas,
            dica="Se for isso mesmo, registre a aceitação em "
                 "`aceitar_estimativa_da_proposta` — fica gravado quem aceitou e quando. "
                 "O aviso é para quem decide, e NUNCA entra no PDF do cliente.")

    return {
        "ok": True, "proposta": numero, "pode_enviar": True,
        "itens_com_custo": len(com_custo),
        "cotacoes_firmes": sum(1 for i in com_custo if i["origem_custo"] == "cotacao_firme"),
        "estimativas": len(estimativas),
        "aceite_registrado": ({"por": cab["por"], "em": cab["em"]}
                              if estimativas and cab["aceito"] else None),
    }


async def aceitar_estimativa(db: AsyncSession, numero: str, quem: str) -> dict:
    """Registra a aceitação. Quem e quando, porque decisão sem autor não é decisão."""
    if not (quem or "").strip():
        raise BloqueioDeEnvio("ACEITE_SEM_AUTOR",
                              "Aceitar estimativa exige dizer QUEM aceita.", [],
                              dica="Informe o nome de quem está assumindo o risco.")
    r = (await db.execute(text(
        "UPDATE proposals SET aceito_com_estimativa = true, "
        "  aceito_com_estimativa_por = :q, aceito_com_estimativa_em = now(), "
        "  updated_at = now() WHERE (number = :n OR id::text = :n) "
        "RETURNING aceito_com_estimativa_em::text"), {"q": quem.strip(), "n": numero}
    )).scalar()
    await db.commit()
    if not r:
        raise BloqueioDeEnvio("PROPOSTA_NAO_ENCONTRADA", f"Não achei a proposta {numero}.", [])
    return {"ok": True, "proposta": numero, "aceito_por": quem.strip(), "aceito_em": r,
            "aviso": "Registrado. Isto NÃO vai ao cliente — é trilha de decisão interna."}
