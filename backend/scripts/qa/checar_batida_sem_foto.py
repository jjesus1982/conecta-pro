#!/usr/bin/env python3
"""Batida do app sem a selfie guardada — a evidência que o app tira e o servidor perdia.

Origem (14/09/2026). O Jordan pediu o que a Pyetra já tinha no Sólides: abrir a folha de
ponto e, PELA FOTO, ver se o funcionário está de farda, se o agente de portaria está
barbeado, se está mesmo no posto. Fui buscar as fotos e medi:

    829 batidas do app em setembro · 829 com facial conferido · 829 com GPS · 0 COM FOTO

O aparelho tirava a selfie, mandava em `facial.foto_base64`, o schema aceitava — e o
construtor de `GpClockPunch` em `PunchService.registrar_batida` NÃO passava o campo. A
foto era usada para validar o rosto e descartada logo depois. Mesmo defeito que já tinha
acontecido com `accuracy` no MESMO construtor, e o comentário dele estava lá, três linhas
acima: «a coluna existe, o schema aceita e o app manda — mas o model nunca recebia».

As fotos anteriores a 14/09/2026 estão PERDIDAS: nunca tocaram o disco.

O que este caçador mede: batida de origem MEDIDA (app/contingência) sem
`foto_capturada_url`. Só conta a partir do corte — cobrar foto de batida velha seria
dívida que ninguém pode pagar, e sino que toca sem ação é sino que se aprende a ignorar.

    docker exec -e PYTHONPATH=/app conecta-pro-backend \
        python3 /app/scripts/qa/checar_batida_sem_foto.py

Linha canônica: `TOTAL: <n> batida(s) sem foto`. Exit 1 quando há achado.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

#: Dia em que o servidor passou a guardar a selfie. Antes disso não há o que cobrar.
CORTE = "2026-09-14"

#: Origens que TIRAM foto. 'tangerino' e 'web' não têm câmera no fluxo — exigir foto delas
#: seria inventar requisito.
FONTES_COM_CAMERA = ("mobile", "facial", "app")


async def main() -> int:
    from sqlalchemy import text  # noqa: PLC0415

    from core.database import async_session_factory  # noqa: PLC0415

    if not Path("/app/scripts").is_dir():
        print("RECUSO: roda DENTRO do container (precisa do banco)")
        return 2

    lista = "(" + ",".join(f"'{f}'" for f in FONTES_COM_CAMERA) + ")"
    async with async_session_factory() as db:
        base = (
            f"FROM gp_clock_punches p WHERE p.device_type IN {lista} "
            f"AND p.punch_timestamp >= '{CORTE}'"
        )
        total = (await db.execute(text(f"SELECT count(*) {base}"))).scalar() or 0
        sem = (
            await db.execute(
                text(f"SELECT count(*) {base} AND coalesce(p.foto_capturada_url,'') = ''")
            )
        ).scalar() or 0
        # Arquivo no disco: URL gravada e arquivo ausente é pior que foto nenhuma —
        # a tela promete a evidência e entrega quadrado quebrado.
        urls = (
            await db.execute(
                text(
                    f"SELECT p.punch_id, p.foto_capturada_url {base} "
                    "AND coalesce(p.foto_capturada_url,'') <> '' LIMIT 500"
                )
            )
        ).all()
        # Antes do corte, para o relatório dizer o tamanho do que se perdeu.
        perdidas = (
            await db.execute(
                text(
                    f"SELECT count(*) FROM gp_clock_punches p WHERE p.device_type IN {lista} "
                    f"AND p.punch_timestamp < '{CORTE}' AND coalesce(p.foto_capturada_url,'') = ''"
                )
            )
        ).scalar() or 0

    sumidas = [pid for pid, u in urls if not Path("/app" + str(u)).exists()]

    print(f"   desde {CORTE}: {total} batida(s) com câmera · {total - sem} com foto · {sem} sem")
    if sumidas:
        print(f"   {len(sumidas)} com URL gravada e ARQUIVO AUSENTE no disco: {sumidas[:5]}")
    if perdidas:
        print(f"   ({perdidas} batida(s) ANTERIORES ao corte sem foto — perdidas, fora da conta)")

    achados = sem + len(sumidas)
    print(f"\nTOTAL: {achados} batida(s) sem foto")
    return 1 if achados else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
