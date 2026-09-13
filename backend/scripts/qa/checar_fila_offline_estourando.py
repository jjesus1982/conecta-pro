#!/usr/bin/env python3
"""Caçador: a fila offline da ronda não pode virar buraco negro (frente 6, 12/09/2026).

Pré-mortem 6.2: um turno de 12h sem sinal enche a fila do celular; sem teto e sem aviso o app
trava ou apaga — e o registro perdido é o que a ronda existia para provar. O servidor não vê a
fila do aparelho, mas vê o RASTRO dela, e é isso que se conta aqui:

  1. checkpoint `origem_offline` cuja `hora_aparelho` está mais de ATRASO_MAX_H antes da
     `hora_servidor` — ficou um dia (ou mais) parado no celular antes de subir;
  2. checkpoint `pendente_foto` (nasceu obrigatório sem imagem pela rota antiga) há mais de
     ATRASO_MAX_H sem a foto chegar, em ronda que ainda não fechou — a foto nunca veio.

Cada um vira uma linha com o `device_id` (ou "sem device_id") para achar o aparelho.

Linha canônica: `TOTAL itens offline atrasados: N` · sai 1 se N > 0.

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/qa/checar_fila_offline_estourando.py
"""
from __future__ import annotations

import asyncio
import sys

#: 24h é o prazo do pré-mortem ("item com mais de 24h sem subir"), não um número de negócio.
ATRASO_MAX_H = 24

SQL = """
SELECT 'subiu_atrasado' AS motivo, coalesce(nullif(c.device_id,''),'sem device_id') AS aparelho,
       r.code, left(c.id::text, 8),
       round(extract(epoch FROM (c.hora_servidor - c.hora_aparelho))/3600)::int AS horas
FROM inspection_checkpoints c JOIN inspection_rounds r ON r.id = c.inspection_round_id
WHERE c.is_active AND c.origem_offline AND c.hora_aparelho IS NOT NULL AND c.hora_servidor IS NOT NULL
  AND c.hora_servidor - c.hora_aparelho > make_interval(hours => :h)
UNION ALL
SELECT 'foto_nunca_veio', coalesce(nullif(c.device_id,''),'sem device_id'), r.code, left(c.id::text, 8),
       round(extract(epoch FROM (now() - coalesce(c.hora_servidor, c.created_at AT TIME ZONE 'UTC')))/3600)::int
FROM inspection_checkpoints c JOIN inspection_rounds r ON r.id = c.inspection_round_id
WHERE c.is_active AND c.status = 'pendente_foto' AND r.status IN ('em_andamento','pausada')
  AND coalesce(c.hora_servidor, c.created_at AT TIME ZONE 'UTC') < now() - make_interval(hours => :h)
ORDER BY 2, 5 DESC
"""


async def main() -> int:
    from sqlalchemy import text

    from core.database import get_db

    gen = get_db()
    db = await gen.__anext__()
    linhas = (await db.execute(text(SQL), {"h": ATRASO_MAX_H})).fetchall()
    por_aparelho: dict[str, int] = {}
    for motivo, aparelho, code, cid, horas in linhas:
        por_aparelho[aparelho] = por_aparelho.get(aparelho, 0) + 1
        print(f"  {aparelho} · ronda {code} · checkpoint {cid} · {motivo} · {horas}h")
    for aparelho, n in sorted(por_aparelho.items(), key=lambda kv: -kv[1]):
        print(f"aparelho {aparelho}: {n} item(ns) atrasado(s)")
    print(f"TOTAL itens offline atrasados: {len(linhas)}")
    return 1 if linhas else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
