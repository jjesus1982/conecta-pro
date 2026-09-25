"""Ação FAZER do fiscal — orçamento do fornecedor vira RASCUNHO de nota, com markup.

O dono, em 25/09/2026, com a tela de emissão aberta na frente:

    «subi a lista de material de um fornecedor, e o Bartolo já tem essa opção de anexar […]
     daí eu digo: nessa lista o custo do material do nosso fornecedor, acrescenta mais 40% de
     markup e manda emitir a nota para este cliente… algo do tipo.»

**Até onde esta ação vai, e por quê.** Ela prepara a nota INTEIRA — cliente, itens, preço de
venda com markup — e para exatamente antes de transmitir. Não é timidez: NF-e autorizada em
produção é irreversível, e desfazer custa carta de correção, cancelamento com prazo ou
denúncia espontânea. A casa já tem o lugar certo do clique irreversível — a tela
«NF-e — transmitir em PRODUÇÃO», com confirmação humana e OTP. Uma segunda porta que
transmitisse a partir do chat esvaziaria aquela, e a primeira vez que um modelo entendesse
«esse cliente» errado a nota já estaria na SEFAZ no CNPJ de outro.

Então a divisão é: **o Bartolo faz todo o trabalho chato, o dono dá o clique que não volta.**

**Por que 🔵 e não 🟡.** Rascunho de nota não muda status compartilhado, não move dinheiro e
não sai do prédio — vive em `fiscal_nota_rascunho`, é listado em «Rascunhos de nota» e tem
cancelamento próprio. O risco de um rascunho errado é alguém perder um minuto apagando. Isso
é 🔵. O que é 🔴 nesta história continua 🔴, na tela de transmissão.

**O markup sai daqui calculado, e com o custo ao lado.** `aplicar_markup` guarda
`custo_unitario` junto do preço — sem isso a margem some no instante do cálculo e ninguém
responde depois «quanto ganhamos nessa nota?». E markup não é margem: 40% sobre custo 100 dá
preço 140, que é 28,6% de margem sobre a venda. A resposta devolve os dois números, escritos,
justamente para essa conversa não sair torta com o dono.

**Os itens vêm do que o modelo LEU no anexo.** O chat já entrega PDF e foto ao modelo
(`anexos.py`: texto por PyMuPDF, foto por vision). O modelo transcreve os itens e chama esta
ação. Nenhum item é inventado aqui: item sem descrição ou sem preço é RECUSADO, nunca
completado — chutar preço de material é o começo de uma nota errada. O casamento com o
cadastro fiscal é o mesmo `casar_produtos` da frente Z5, e item que não casa fica SEM produto,
com o motivo escrito, para uma pessoa escolher. NCM chutado foi exatamente a rejeição da
SEFAZ de 11/04/2026 («NCM inexistente»).
"""

from __future__ import annotations

from typing import Any

from .acoes.base import ROLES_MONEY
from .acoes.rascunho import criar_rascunho, registrar_executor
from .agir_dispatcher import registrar_acao

#: Preparar rascunho de nota é decisão comercial/fiscal da casa — mesma régua de quem aprova
#: proposta. Não é o gate do dinheiro, mas também não é de qualquer um: o rascunho já carrega
#: preço de venda e vai virar documento fiscal na tela seguinte.
_ROLES = ROLES_MONEY


def _itens_limpos(itens: Any) -> tuple[list[dict], list[str]]:
    """Valida os itens transcritos pelo modelo. Devolve (aceitos, recusas explicadas).

    Função pura de propósito: o oráculo bate nela sem banco e sem LLM. Ela é a parede entre
    «o modelo leu» e «virou preço de nota».
    """
    aceitos: list[dict] = []
    recusas: list[str] = []
    if not isinstance(itens, list) or not itens:
        return [], ["A lista de itens veio vazia. Transcreva os itens do orçamento antes de chamar esta ação."]
    for n, bruto in enumerate(itens, 1):
        if not isinstance(bruto, dict):
            recusas.append(f"item {n}: formato inválido")
            continue
        desc = str(bruto.get("descricao") or "").strip()
        if not desc:
            recusas.append(f"item {n}: sem descrição — não se emite nota de item sem nome")
            continue
        try:
            unit = float(str(bruto.get("valor_unitario") or "0").replace(",", "."))
        except ValueError:
            unit = 0.0
        if unit <= 0:
            recusas.append(f"«{desc[:40]}»: sem preço legível no orçamento — não se chuta preço de material")
            continue
        try:
            qtd = float(str(bruto.get("quantidade") or "1").replace(",", "."))
        except ValueError:
            qtd = 1.0
        aceitos.append(
            {
                "codigo": str(bruto.get("codigo") or "").strip()[:60],
                "descricao": desc[:200],
                "unidade": str(bruto.get("unidade") or "UN").strip()[:6] or "UN",
                "quantidade": qtd if qtd > 0 else 1.0,
                "valor_unitario": unit,
                "desconto_percent": 0,
                "valor_total": round(qtd * unit, 2) if qtd > 0 else unit,
                "confianca": 0.9,  # transcrito pelo modelo com o documento à vista
                "trecho_origem": str(bruto.get("trecho_origem") or desc)[:400],
            }
        )
    return aceitos, recusas


async def _propor_nota_do_orcamento(
    db,
    user,
    scope,
    *,
    cliente: str = "",
    cliente_documento: str = "",
    itens: Any = None,
    markup_percent: Any = 0,
    observacao: str = "",
    **_,
) -> dict[str, Any]:
    from decimal import Decimal  # noqa: PLC0415

    from modules.fiscal.services import orcamento_para_nota as z5  # noqa: PLC0415

    nome_cliente = str(cliente or "").strip()
    if not nome_cliente:
        return {
            "erro": "cliente é obrigatório. Pergunte para QUEM é a nota antes de preparar — "
            "nota emitida para o destinatário errado é irreversível."
        }

    aceitos, recusas = _itens_limpos(itens)
    if not aceitos:
        return {"erro": "Nenhum item aproveitável. " + " · ".join(recusas[:5])}

    casados = await z5.casar_produtos(db, [dict(i) for i in aceitos])
    # `aplicar_markup` opera sobre Decimal; os valores vieram do modelo como float.
    for i in casados:
        i["quantidade"] = Decimal(str(i["quantidade"]))
        i["valor_unitario"] = Decimal(str(i["valor_unitario"]))
        i["desconto_percent"] = Decimal("0")
    com_preco = z5.aplicar_markup(casados, markup_percent)

    m = z5.para_decimal(markup_percent, 4)
    custo = sum(float(i.get("custo_unitario") or i["valor_unitario"]) * float(i["quantidade"]) for i in com_preco)
    venda = sum(float(i["valor_total"]) for i in com_preco)
    sem_produto = [i for i in com_preco if not i.get("produto_id")]
    margem = ((venda - custo) / venda * 100) if venda else 0.0

    linhas = "\n".join(
        f"  · {i['descricao'][:44]} — {float(i['quantidade']):g} {i['unidade']} × "
        f"R$ {float(i['valor_unitario']):.2f} = R$ {float(i['valor_total']):.2f}"
        + ("" if i.get("produto_id") else "  ⚠️ SEM produto no cadastro fiscal")
        for i in com_preco
    )

    return await criar_rascunho(
        db,
        user,
        tipo="nota_do_orcamento",
        modulo="fiscal",
        gate="🔵",
        requires_otp=False,
        roles_aprovador=_ROLES,
        idempotency_key=f"nota_orc:{nome_cliente[:30]}:{len(com_preco)}:{venda:.2f}",
        titulo="Preparar rascunho de nota a partir de um orçamento",
        resumo=(
            f"Rascunho de nota para **{nome_cliente}**, {len(com_preco)} item(ns).\n{linhas}\n\n"
            + (
                f"Custo do fornecedor R$ {custo:,.2f} · markup {m}% · "
                f"venda R$ {venda:,.2f} · margem {margem:.1f}% sobre a venda."
                if m > 0
                else f"Total R$ {venda:,.2f} — SEM markup, preço igual ao do orçamento."
            )
            .replace(",", "·")
            .replace(".", ",")
            .replace("·", ".")
            + (
                f"\n\n⚠️ {len(sem_produto)} item(ns) sem produto no cadastro fiscal — escolha antes de emitir."
                if sem_produto
                else ""
            )
            + (f"\n\nRecusados na leitura: {' · '.join(recusas[:3])}" if recusas else "")
            + (f"\n\nObservação: “{observacao[:140]}”." if observacao else "")
            + "\n\nAprovar cria o RASCUNHO em «Rascunhos de nota». **Não emite e não transmite nada** — "
            "a nota só vai à SEFAZ na tela «NF-e — transmitir em PRODUÇÃO», com OTP."
        ),
        payload={
            "cliente": nome_cliente,
            "cliente_documento": str(cliente_documento or "").strip(),
            "markup_percent": str(m),
            "itens": [
                {
                    "codigo": i.get("codigo") or "",
                    "descricao": i["descricao"],
                    "unidade": i["unidade"],
                    "quantidade": str(i["quantidade"]),
                    "valor_unitario": str(i["valor_unitario"]),
                    "valor_total": str(i["valor_total"]),
                    "custo_unitario": str(i.get("custo_unitario") or i["valor_unitario"]),
                    "produto_id": i.get("produto_id"),
                    "produto_codigo": i.get("produto_codigo"),
                    "produto_descricao": i.get("produto_descricao"),
                    "ncm": i.get("ncm"),
                    "ncm_sugerido": i.get("ncm_sugerido"),
                    "casamento": i.get("casamento"),
                    "motivo": i.get("motivo"),
                    "confianca": i.get("confianca"),
                    "trecho_origem": i.get("trecho_origem"),
                }
                for i in com_preco
            ],
        },
    )


async def _exec_nota_do_orcamento(db, aprovador_user, payload: dict) -> str:
    """Grava o rascunho. Roda SÓ pela Central, depois do aprovador — nunca pelo LLM."""
    from decimal import Decimal  # noqa: PLC0415

    from modules.fiscal.services import orcamento_para_nota as z5  # noqa: PLC0415

    itens = []
    for i in payload.get("itens") or []:
        d = dict(i)
        for k in ("quantidade", "valor_unitario", "valor_total", "custo_unitario"):
            if d.get(k) is not None:
                d[k] = Decimal(str(d[k]))
        d["desconto_percent"] = Decimal("0")
        itens.append(d)
    r = await z5.preparar_rascunho(
        db,
        "chat",
        itens=itens,
        cliente_nome=payload.get("cliente") or "—",
        cliente_documento=payload.get("cliente_documento") or "",
        usuario=str(getattr(aprovador_user, "email", "") or getattr(aprovador_user, "id", "?")),
    )
    return str(r["id"])


registrar_executor("nota_do_orcamento", _exec_nota_do_orcamento)

registrar_acao(
    "fiscal",
    "nota_do_orcamento",
    "Transformar um orçamento de FORNECEDOR (que o usuário anexou no chat) em RASCUNHO de nota "
    "para um cliente, aplicando markup sobre o custo. dados: cliente (obrig., para quem é a "
    "nota), cliente_documento (CNPJ/CPF, se souber), itens (obrig., lista de "
    "{descricao, quantidade, unidade, valor_unitario, codigo} transcritos do anexo — o "
    "valor_unitario é o CUSTO do fornecedor, como está no documento), markup_percent (ex.: 40 "
    "para acrescentar 40% sobre o custo; 0 = preço igual ao do orçamento), observacao. "
    "Item sem descrição ou sem preço legível é RECUSADO — nunca complete nem chute preço, "
    "quantidade ou NCM. NÃO emite, NÃO assina e NÃO transmite nota: cria um rascunho em "
    "«Rascunhos de nota», e transmitir continua sendo na tela «NF-e — transmitir em "
    "PRODUÇÃO», com OTP humano.",
    _propor_nota_do_orcamento,
)
