"""Recomputa o estado da coleta de chave PIX a partir das MENSAGENS, não do que sobrou.

POR QUE EXISTE: em 25/09/2026 as 66 perguntas saíram e, no meio das respostas chegando, um bake
de outra sessão recriou o contêiner e apagou os `docker cp` que traziam três consertos da captura
— a conversa que não fecha na primeira mensagem, o "Não" seco, e a checagem de entrega. Durante
essa janela as respostas foram registradas pela lógica VELHA.

A saída não é confiar em quem foi gravado durante a janela ruim. As mensagens estão todas no
`cwi_message_log`; o registro é DERIVÁVEL delas. Este script reexecuta cada resposta, em ordem
cronológica, contra a lógica atual.

⭐ A regra que isso encarna: **o estado tem de ser recomputável da evidência, senão ele é só o
que sobrou.** Vale para qualquer coisa nesta casa que nasça de conversa.

⚠️ NÃO aplica chave nenhuma. Só recompõe `pix_confirmacoes`; `aplicar()` continua exigindo
aprovador humano. Quem já tem `aplicado_em` é intocado — não se reescreve o que já virou dinheiro.

Uso:
    docker exec -e PYTHONPATH=/app conecta-pro-backend \
        python3 /app/scripts/qa/reconciliar_pix_confirmacoes.py [--aplicar]

Sem `--aplicar` é ENSAIO: mostra o que mudaria e não escreve.
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database import async_session_factory  # noqa: E402
from modules.integrations.connectors.whatsapp import pix_confirma as px  # noqa: E402


def _ddd_e_final(fone: str | None) -> tuple[str, str]:
    """DDD + 8 últimos dígitos. É a única parte estável de um celular brasileiro.

    O mesmo número aparece com 8 e com 9 dígitos na base (mudança de 2016), com e sem o 55.
    Comparar a string inteira não casa — medido no Alan, cujo WhatsApp está gravado com 8 e a
    chave que ele mandou tem 9.
    """
    d = "".join(c for c in str(fone or "") if c.isdigit())
    if d.startswith("55") and len(d) >= 12:
        d = d[2:]
    return (d[:2], d[-8:]) if len(d) >= 10 else ("", "")


async def main() -> None:
    aplicar = "--aplicar" in sys.argv
    async with async_session_factory() as db:
        pessoas = (await db.execute(text("""
            SELECT employee_id::text AS eid, nome, telefone, status, chave_atual,
                   chave_informada, tipo_informado, pedido_em
            FROM pix_confirmacoes
            WHERE pedido_em IS NOT NULL AND aplicado_em IS NULL
            ORDER BY nome"""))).mappings().all()

        # todas as mensagens ENTRANDO desde o início da campanha, de uma vez
        msgs = (await db.execute(text("""
            SELECT phone_canonical, content, created_at
            FROM cwi_message_log
            WHERE direction = 'in' AND created_at >= (SELECT min(pedido_em) FROM pix_confirmacoes)
              AND coalesce(content,'') <> ''
              -- ⚠️ conversa de GRUPO não responde a esta pergunta. No ensaio de 25/09 uma menção
              -- do grupo Green Hills (`@83949732774058`) foi lida como CNPJ e virou "chave nova"
              -- para o Maurício. A pergunta foi no privado; a resposta também é.
              AND NOT EXISTS (SELECT 1 FROM wa_grupo_mensagens g
                              WHERE g.chatwoot_message_id = cwi_message_log.chatwoot_message_id)
              AND coalesce(content,'') !~ '@[0-9]{10,}'
            ORDER BY created_at"""))).mappings().all()

        por_fone: dict[tuple[str, str], list[dict]] = {}
        for m in msgs:
            k = _ddd_e_final(m["phone_canonical"])
            if k != ("", ""):
                por_fone.setdefault(k, []).append(dict(m))

        mudou, igual, sem_msg = [], 0, 0
        for p in pessoas:
            k = _ddd_e_final(p["telefone"])
            fila = [m for m in por_fone.get(k, []) if m["created_at"] >= p["pedido_em"]]
            if not fila:
                sem_msg += 1
                continue

            antes = (p["status"], p["chave_informada"], p["tipo_informado"])
            if aplicar:
                # reexecuta a conversa INTEIRA, em ordem: o último recado manda
                for m in fila:
                    if px.e_so_acuse(m["content"]):
                        continue
                    await px.registrar_resposta(
                        db, employee_id=p["eid"], texto=m["content"],
                        fone_remetente=m["phone_canonical"])
                d = (await db.execute(text(
                    "SELECT status, chave_informada, tipo_informado FROM pix_confirmacoes "
                    "WHERE employee_id = CAST(:e AS uuid)"), {"e": p["eid"]})).mappings().first()
                depois = (d["status"], d["chave_informada"], d["tipo_informado"])
            else:
                # ENSAIO: simula sem escrever — mesma ordem, mesma precedência
                st, kv, tp = p["status"], p["chave_informada"], p["tipo_informado"]
                for m in fila:
                    txt = m["content"]
                    if px.e_so_acuse(txt):
                        continue
                    if px.confirmou_o_atual(txt):
                        st, kv, tp = "confirmou_atual", kv, tp
                        continue
                    ch, ti = px.desambiguar_pelo_remetente(
                        *px.chave_do_texto(txt), m["phone_canonical"])
                    if ch:
                        st, kv, tp = "respondido", ch, ti
                    elif px._NEGA.search(px._sem_acento(txt)):
                        st, kv, tp = "aguardando", None, None
                depois = (st, kv, tp)

            if antes != depois:
                mudou.append((p["nome"], antes, depois, len(fila),
                              fila[-1]["content"][:38].replace("\n", " ")))
            else:
                igual += 1

        print(f"{'APLICANDO' if aplicar else 'ENSAIO (nada escrito)'} — "
              f"{len(pessoas)} pessoas na coleta, {len(msgs)} mensagens entrando")
        print(f"sem nenhuma mensagem: {sem_msg} · já corretas: {igual} · MUDAM: {len(mudou)}\n")
        for nome, a, d, n, ult in mudou:
            print(f"  {nome[:30]:32} {n} msg(s)")
            print(f"      antes : {a[0]:16} chave={a[1] or '—'} tipo={a[2] or '—'}")
            print(f"      depois: {d[0]:16} chave={d[1] or '—'} tipo={d[2] or '—'}   «{ult}»")
        if aplicar:
            await db.commit()
            print("\ncommit feito. Nenhuma chave foi APLICADA no cadastro — só o registro da coleta.")
        elif mudou:
            print("\nrode com --aplicar para gravar")


if __name__ == "__main__":
    asyncio.run(main())
