#!/usr/bin/env python3
"""Cobra a assinatura de quem ainda não assinou — e SÓ de quem ainda não assinou.

Origem: 17/09/2026. O Jordan pediu que o José Luís cobrasse a assinatura dos recibos de VT/VR
"e não cobrasse de forma indevida quem já assinou". A segunda metade é a que importa: cobrança
que chega para quem já resolveu é a cobrança que a pessoa aprende a ignorar — e da próxima vez
ela ignora a que valia.

A fonte da verdade é `sig_signature_requests.status`: PENDING cobra, COMPLETED nunca. Não há
lista paralela, não há marcação de "já avisei" que possa divergir do fato — quem assinou some
da fila no mesmo instante em que assina.

O link leva direto para a aba de assinatura (`?t=assinar`), não para a home do Meu Espaço:
no celular, cair numa tela com 12 abas é onde a cobrança morre.

    # ensaio, não manda nada:
    python3 backend/modules/notifications/cobrar_assinatura.py --competencia 09/2026

    # cobra de verdade:
    python3 backend/modules/notifications/cobrar_assinatura.py --competencia 09/2026 \
        --enviar --confirmo "SIM, COBRAR"
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

#: Quantos dias de silêncio antes de cobrar de novo a mesma pessoa. Cobrar todo dia é
#: perseguir; nunca cobrar é deixar morrer. 3 dias é o intervalo em que o aviso ainda é
#: lembrete e não incômodo.
DIAS_ENTRE_COBRANCAS = int(os.getenv("COBRANCA_DIAS", "3"))

PORTAL = "https://erp.conectamais.pro/modulos/meu-espaco?t=assinar"


def _primeiro(nome: str) -> str:
    p = [x for x in str(nome or "").split() if len(x) > 2]
    return p[0].capitalize() if p else str(nome or "")


def _texto(nome: str, titulo: str, quantos: int) -> str:
    cab = f"Olá, {_primeiro(nome)}! 😊\n\nAqui é o José Luís, da Conecta Mais.\n\n"
    if quantos > 1:
        corpo = (
            f"Você tem *{quantos} documentos* esperando a sua assinatura no sistema (um deles é o *{titulo}*). ✍️\n\n"
        )
    else:
        corpo = f"O seu *{titulo}* está esperando a sua assinatura. ✍️\n\n"
    return (
        cab
        + corpo
        + f"É rápido, dá para fazer pelo celular:\n{PORTAL}\n\n"
        + "Entre com o seu login e confirme — se tiver mais de um documento, dá para "
        "assinar todos de uma vez.\n\n" + "Se tiver qualquer dúvida ou não conseguir entrar, me chama por aqui que eu "
        "ajudo. 💙\n\n_Conecta Mais — Segurança e Tecnologia_"
    )


async def main() -> int:
    ap = argparse.ArgumentParser()
    # Sem --tipo e sem --competencia, cobra TUDO que está pendente. É o caso normal: o
    # Jordan quer esta ferramenta para QUALQUER documento que a empresa mande ao funcionário,
    # não só o recibo de VT/VR.
    ap.add_argument("--competencia", default="", help="filtro opcional, ex.: 09/2026")
    ap.add_argument("--tipo", default="", help="filtro opcional, ex.: recibo_vt_vr")
    ap.add_argument("--enviar", action="store_true")
    ap.add_argument("--confirmo", default="")
    args = ap.parse_args()

    sys.path.insert(0, "/app")
    from sqlalchemy import text  # noqa: PLC0415

    from core.database.session import async_session_factory  # noqa: PLC0415

    async with async_session_factory() as db:
        # PENDING apenas. Quem assinou virou COMPLETED e não aparece aqui — é a mesma
        # consulta que a tela do funcionário usa, então não há como as duas discordarem.
        filtro = ["s.status = 'PENDING'", "s.signer_type = 'employee'"]
        par: dict = {}
        if args.tipo:
            filtro.append("s.document_type = :t")
            par["t"] = args.tipo
        if args.competencia:
            filtro.append("s.title LIKE :c")
            par["c"] = f"%{args.competencia}%"
        onde = " AND ".join(filtro)

        # UMA linha por PESSOA, com a contagem do que ela deve. Cobrar documento a documento
        # mandaria 3 mensagens para quem tem 3 pendentes — e a terceira já não é lembrete,
        # é incômodo. O botão "assinar todos" existe na tela, então uma mensagem basta.
        # `d.telefone` entra como último recurso: o cadastro de funcionário do ALAN estava sem
        # telefone e o de diarista tinha (medido em 16/09).
        linhas = (
            await db.execute(
                text(f"""
            SELECT s.signer_id, s.signer_name, count(*) AS quantos,
                   min(s.title) AS um_titulo,
                   coalesce(nullif(e.telefone,''), nullif(e.celular,''),
                            nullif(d.telefone,'')) AS fone
              FROM sig_signature_requests s
              LEFT JOIN employees e ON e.id = s.signer_id
              LEFT JOIN diaria_diaristas d
                     ON upper(btrim(d.nome)) = upper(btrim(s.signer_name))
             WHERE {onde}
             GROUP BY s.signer_id, s.signer_name, e.telefone, e.celular, d.telefone
             ORDER BY s.signer_name"""),
                par,
            )
        ).all()

        assinados = (
            await db.execute(
                text(
                    f"SELECT count(*) FROM sig_signature_requests s "
                    f"WHERE {onde.replace(chr(39) + 'PENDING' + chr(39), chr(39) + 'COMPLETED' + chr(39))}"
                ),
                par,
            )
        ).scalar() or 0

    pendentes = [x for x in linhas if x[4]]
    sem_fone = [x for x in linhas if not x[4]]
    total_docs = sum(int(x[2]) for x in linhas)

    print(f"   competência {args.competencia} · {args.tipo}")
    print(f"   já assinaram: {assinados}  (NÃO recebem cobrança)")
    print(f"   a cobrar: {len(pendentes)} pessoa(s) · {total_docs} documento(s) · sem telefone: {len(sem_fone)}")
    for x in sem_fone:
        print(f"      sem telefone: {x[1]} ({x[2]} doc)")

    if not args.enviar:
        print('\nENSAIO — nada enviado. Para cobrar: --enviar --confirmo "SIM, COBRAR"')
        for x in pendentes[:6]:
            print(f"      {x[1][:36]:36s} {x[2]} doc(s)")
        if len(pendentes) > 6:
            print(f"      (+{len(pendentes) - 6} não listados)")
        return 0

    if args.confirmo != "SIM, COBRAR":
        print('RECUSO: --enviar exige --confirmo "SIM, COBRAR"')
        return 2

    from modules.integrations.connectors.whatsapp.service import (  # noqa: PLC0415
        send_text_message,
    )

    ok = falhou = 0
    for _sid, nome, quantos, titulo, fone in pendentes:
        dig = "".join(c for c in str(fone) if c.isdigit())
        jid = dig if dig.startswith("55") else "55" + dig
        try:
            r = await send_text_message("+" + jid, _texto(nome, titulo, int(quantos)))
            bom = (r or {}).get("status") not in ("disabled", "error", "failed")
            ok += bom
            falhou += not bom
            print(f"      {'✓' if bom else '✗'} {nome[:34]:34s} {(r or {}).get('status')}")
        except Exception as e:  # noqa: BLE001
            falhou += 1
            print(f"      ✗ {nome[:34]:34s} {str(e)[:60]}")
        await asyncio.sleep(1.5)

    print(f"\nTOTAL: {ok} cobrança(s) enviada(s) · {falhou} falha(s)")
    return 1 if falhou else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
