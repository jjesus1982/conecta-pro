#!/usr/bin/env python3
"""Libera o recadastro do rosto de quem falha em reconhecer — a referência é que está ruim.

🔴 A HISTÓRIA, toda medida (11/09/2026). O `gp_audit_logs` guarda 32 tentativas de bater que
falharam, TODAS por `rosto_nao_reconhecido`, de 4 pessoas. E o número que importa está no
`extra_data`: a **confiança da câmera** nessas tentativas é 0,93 a 0,99 — o celular vê o rosto
perfeitamente — enquanto a **distância até a referência** é 0,73 a 0,84, contra um limiar de
0,68. Não é luz, não é câmera, não é internet: é a foto de referência que não corresponde.

De onde veio a referência ruim está escrito no `self_service_controller`: até 14/08/2026 o app
pedia cadastro toda vez que `GET /facial/referencia` falhava, e o `catch` do cliente tratava
"não consegui perguntar" como "não tem rosto". 14 das 47 pessoas recadastraram — várias na
virada de turno, na guarita, no escuro. Cada recadastro trocou a referência boa por uma ruim.

O cliente foi corrigido e uma trava foi criada: `/facial/cadastrar` recusa com 409 se já existe
rosto. Certa para o próximo cliente mal-comportado — e é ela que hoje PRENDE quem ficou com a
referência ruim: o sistema responde "seu rosto já está cadastrado, use a contingência". Para
sempre. A LIVIA falha desde 23/08 e tentou 22 vezes.

O que este script faz: limpa a referência de quem tem falha REGISTRADA (evidência, nunca
pedido), guardando o descriptor antigo. Com a referência vazia o app volta a oferecer o
cadastro sozinho — e a pessoa refaz num lugar claro, com a mensagem explicando.

    python3 backend/scripts/liberar_recadastro_facial.py
    python3 backend/scripts/liberar_recadastro_facial.py --aplicar
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, "/app")

MIN_FALHAS = 3
DIAS = 45

_SQL = """
WITH falhas AS (
  SELECT lower(coalesce(a.actor_user_name,'')) AS email, count(*) AS n,
         round(min((a.extra_data->>'distance')::numeric),3) AS dist_min,
         round(avg((a.extra_data->>'confidence')::numeric),3) AS conf_media,
         max(a.timestamp)::date AS ultima
    FROM gp_audit_logs a
   WHERE a.action = 'ponto.tentativa_falhou'
     AND coalesce(a.extra_data->>'motivo','') = 'rosto_nao_reconhecido'
     AND a.timestamp > (now() AT TIME ZONE 'America/Manaus') - make_interval(days => :dias)
   GROUP BY 1 HAVING count(*) >= :min_falhas)
SELECT e.id::text AS eid, e.nome, f.n, f.dist_min, f.conf_media, f.ultima::text,
       to_char(e.face_enrolled_at,'DD/MM/YYYY HH24:MI') AS rosto_em,
       (e.face_descriptor IS NOT NULL) AS tem_referencia
  FROM falhas f JOIN users u ON lower(u.email) = f.email
  JOIN employees e ON e.id = u.employee_id
 ORDER BY f.n DESC
"""


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory

    aplicar = "--aplicar" in sys.argv
    async with async_session_factory() as db:
        linhas = (await db.execute(text(_SQL),
                                   {"dias": DIAS, "min_falhas": MIN_FALHAS})).mappings().all()
        if not linhas:
            print("ninguém com falha facial recorrente — nada a liberar")
            return 0
        backup = []
        for r in linhas:
            print(f"  {r['nome'][:32]:34} {r['n']:>2} falha(s) · distância mínima {r['dist_min']} "
                  f"(limiar 0.68) · confiança da câmera {r['conf_media']} · rosto cadastrado em "
                  f"{r['rosto_em'] or '—'} · última falha {r['ultima']}")
            if aplicar and r["tem_referencia"]:
                d = (await db.execute(text(
                    "SELECT face_descriptor::text FROM employees WHERE id = CAST(:e AS uuid)"),
                    {"e": r["eid"]})).scalar()
                backup.append({"employee_id": r["eid"], "nome": r["nome"], "descriptor": d,
                               "face_enrolled_at": r["rosto_em"]})
                await db.execute(text(
                    "UPDATE employees SET face_descriptor = NULL, biometria_facial = false, "
                    "  face_enrolled_at = NULL, updated_at = now() WHERE id = CAST(:e AS uuid)"),
                    {"e": r["eid"]})
        if aplicar:
            carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
            os.makedirs("/app/uploads", exist_ok=True)
            caminho = f"/app/uploads/facial_backup_{carimbo}.json"
            with open(caminho, "w", encoding="utf-8") as f:
                json.dump(backup, f, ensure_ascii=False)
            await db.commit()
            print(f"\nAPLICADO: {len(backup)} referência(s) limpa(s). O app volta a pedir o "
                  f"cadastro a essas pessoas no próximo acesso.\nreferência antiga guardada em {caminho}")
        else:
            print(f"\nENSAIO: {len(linhas)} pessoa(s) teriam a referência limpa. Rode com --aplicar.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
