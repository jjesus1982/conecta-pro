"""Avisa o Jordan no WhatsApp quando o Eliziel ou o Orlailson lançam diárias.

Pedido dele: "tem como me mandar uma notificação toda vez que o Eliziel ou Orlailson
lançarem as diárias, eu recebo no WhatsApp pelo José Luís?".

⚠️ **Não toca no Operacional.** O módulo é curado à mão e é read-only para agentes — então
isto NÃO é gancho no endpoint de lançar. É leitura periódica de `diaria_lancamentos`,
comparando com a última vista. Se a rotina morrer, ninguém deixa de lançar; só o aviso
falha, e o lançamento continua visível no financeiro como sempre.

⚠️ **Marca d'água persistida em `crm_system_state` (chave/valor), não em memória.** Reusa
a tabela que já existe para isso — criar uma nova só para guardar um número seria mais uma
tabela para alguém manter. Guardar o "último
visto" numa variável faria o worker reiniciar e reavisar tudo de novo — 326 lançamentos
do Eliziel no WhatsApp do dono.

⚠️ **Só avisa o que é NOVO e de QUEM interessa.** Lançamento do próprio Jordan não gera
aviso — ele não precisa ser notificado do que acabou de fazer.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

from sqlalchemy import text

logger = logging.getLogger(__name__)

#: Quem, ao lançar, gera aviso. UUID em vez de nome: nome muda, id não.
LANCADORES = {
    "f9e7e74b-2fa2-4120-924e-18b9c4ca5297": "Eliziel",
    "9dbb2bdd-df95-4bb6-87c1-d0ab43a7522f": "Orlailson",
}

#: Marca d'água: id do último lançamento já avisado.
CHAVE_MARCA = "aviso_diarias.ultimo_id"

#: Destino. No .env dá para trocar sem mexer no código.
DESTINO_PADRAO = "+5592986465328"

#: Teto por rodada — se algo represar, é melhor avisar "e mais N" que despejar 300
#: mensagens no WhatsApp de alguém.
MAX_DETALHE = 8


def _marca(db) -> int:
    r = db.execute(text("SELECT valor FROM crm_system_state WHERE chave = :k"),
                   {"k": CHAVE_MARCA}).scalar()
    try:
        return int(str(r or 0))
    except (TypeError, ValueError):
        return 0


def _gravar_marca(db, valor: int) -> None:
    db.execute(text("""
        INSERT INTO crm_system_state (chave, valor, updated_at)
        VALUES (:k, :v, NOW())
        ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor, updated_at = NOW()
    """), {"k": CHAVE_MARCA, "v": str(valor)})
    db.commit()


def montar_mensagem(linhas: list[dict], total_extra: int = 0) -> str:
    """O texto que chega no WhatsApp. Curto: é notificação, não relatório."""
    por_quem: dict[str, list[dict]] = {}
    for ln in linhas:
        por_quem.setdefault(ln["quem"], []).append(ln)

    partes = []
    for quem, itens in por_quem.items():
        soma = sum(float(i["valor"] or 0) for i in itens)
        dias = sorted({str(i["data"]) for i in itens})
        quando = dias[0] if len(dias) == 1 else f"{dias[0]} a {dias[-1]}"
        cab = (f"*{quem}* lançou {len(itens)} diária(s) — {quando}\n"
               f"Total: R$ {soma:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        nomes = [f"• {i['diarista']} — R$ {float(i['valor'] or 0):,.2f}".replace(
            ",", "X").replace(".", ",").replace("X", ".") for i in itens[:MAX_DETALHE]]
        if len(itens) > MAX_DETALHE:
            nomes.append(f"• …e mais {len(itens) - MAX_DETALHE}")
        partes.append(cab + "\n" + "\n".join(nomes))

    txt = "\n\n".join(partes)
    if total_extra:
        txt += f"\n\n(+{total_extra} lançamento(s) além do detalhado)"
    txt += "\n\nPagar: erp.conectamais.pro/redesign/financeiro?t=g-pagar-pessoas"
    return txt


def varrer_e_avisar(db, enviar=None) -> dict:
    """Procura lançamentos novos do Eliziel/Orlailson e avisa. `enviar` injetável p/ teste."""
    ultimo = _marca(db)
    linhas = db.execute(text("""
        SELECT l.id, l.data, l.valor, l.created_by,
               COALESCE(d.nome, '(sem cadastro)') AS diarista
          FROM diaria_lancamentos l
          LEFT JOIN diaria_diaristas d ON d.id = l.diarista_id
         WHERE l.id > :ultimo
           AND l.created_by = ANY(:autores)
           AND l.status = 'lancado'
         ORDER BY l.id
    """), {"ultimo": ultimo, "autores": list(LANCADORES)}).mappings().all()

    if not linhas:
        return {"novos": 0, "enviado": False, "ultimo": ultimo}

    itens = [{"quem": LANCADORES.get(str(x["created_by"]), "Operacional"),
              "data": x["data"], "valor": x["valor"], "diarista": x["diarista"]}
             for x in linhas]
    msg = montar_mensagem(itens)
    destino = os.getenv("AVISO_DIARIAS_WHATSAPP", DESTINO_PADRAO)

    if enviar is None:
        import asyncio

        from modules.integrations.connectors.whatsapp.agent_service import (
            _enviar_whatsapp_direto,
        )
        ok = asyncio.run(_enviar_whatsapp_direto(destino, msg))
    else:
        ok = enviar(destino, msg)

    # ⚠️ A marca só avança se o envio DEU CERTO. Avançar antes faria o aviso sumir de vez
    # quando o WhatsApp estivesse fora do ar — e ninguém saberia que perdeu.
    novo_ultimo = max(int(x["id"]) for x in linhas)
    if ok:
        _gravar_marca(db, novo_ultimo)
    else:
        logger.warning("aviso_diarias: envio falhou, marca mantida em %s (tenta de novo)", ultimo)

    return {"novos": len(linhas), "enviado": bool(ok),
            "ultimo": novo_ultimo if ok else ultimo, "destino": destino,
            "mensagem": msg if not ok else None}
