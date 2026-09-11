#!/usr/bin/env python3
"""A hora do turno gravada está 1h fora da hora REAL — corrige pelo que a pessoa bate.

Origem (11/09/2026). O Jordan: *"os horários dos pontos estão com o fuso de Brasília, não de
Manaus; o José Luís manda mensagem antes das 07:00 como se fosse 08:00"*. Ele está certo no
efeito e o diagnóstico ficou um passo adiante: **não há nada configurado em Brasília**. Os
containers rodam `TZ=America/Manaus`, o Postgres calcula com `AT TIME ZONE 'America/Manaus'` e
os três lembretes saíram nos minutos certos (06:44 · 06:59 · 07:09, para um turno de 07:00).

O que está errado é o DADO: `shifts.planned_start_time` está uma hora antes da hora real para
a maior parte da operação. A GRACIENE bate 08:00 todo dia — pelo Tangerino e pelo nosso app,
dois sistemas independentes — e a escala dela diz 07:00. Então o lembrete das 06:44 é correto
para uma escala errada, e chega uma hora antes da vida real.

A origem é a grade importada em 07-08/07/2026; desde então `auto_generate_monthly_scales_task`
COPIA o padrão do mês anterior (`mode() WITHIN GROUP`), e copiou o erro cinco vezes.

COMO A VERDADE É DERIVADA, e não adivinhada: mediana de (primeira batida − início planejado)
por (pessoa, posto, hora gravada), 28 dias, mínimo de 6 dias com batida. Só entra quem tem
desvio de 45 a 75 minutos — uma hora limpa — e cuja hora resultante é redonda. Quem tem desvio
torto (+223, −238) fica de FORA e vai nominalmente para o relatório: ali não é uma hora, é
outra coisa, e outra coisa precisa de gente.

SEGURANÇA:
  · mexe SÓ em turnos de HOJE para a frente. O passado é história e já foi apurado; reescrever
    silenciosamente a base de uma apuração fechada seria pior que o defeito.
  · desloca início E fim pelo mesmo delta — a duração não muda, então hora extra e adicional
    noturno não mudam de tamanho.
  · grava o ANTES em `/app/uploads/escala_hora_backup_<carimbo>.json` e imprime o SQL de volta.
  · `--aplicar` é obrigatório; o padrão é ensaio.

    python3 backend/scripts/corrigir_hora_escala.py
    python3 backend/scripts/corrigir_hora_escala.py --aplicar
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, "/app")

def main() -> int:
    import asyncio

    aplicar = "--aplicar" in sys.argv

    async def _rodar() -> dict:
        from sqlalchemy import text

        from core.database import async_session_factory
        from modules.people_management.ponto.hora_da_escala import (
            DIAS,
            MIN_DIAS,
            SQL_DESVIO,
            separar,
        )

        async with async_session_factory() as db:
            linhas = (await db.execute(text(SQL_DESVIO),
                                       {"dias": DIAS, "min_dias": MIN_DIAS})).mappings().all()
            # a MESMA régua do oráculo — ver `hora_da_escala.py` para o porquê de haver uma só
            limpos, crus = separar(linhas)
            planos = [{"employee_id": r["employee_id"], "post_id": r["post_id"],
                       "plan": r["promete"], "dias": int(r["dias"]), "desvio": int(r["desvio"]),
                       "delta_h": 1 if int(r["desvio"]) > 0 else -1} for r in limpos]
            tortos = [{"employee_id": r["employee_id"], "post_id": r["post_id"], "nome": r["nome"],
                       "plan": r["promete"], "dias": int(r["dias"]), "desvio": int(r["desvio"])}
                      for r in crus]

            rel: dict = {"aplicar": aplicar, "candidatos": len(planos), "tortos": tortos,
                         "turnos": 0, "detalhe": [], "backup": ""}
            antes = []
            for p in planos:
                alvo = (await db.execute(text(
                    "SELECT sh.id::text, e.nome, po.name AS posto, "
                    "       to_char(sh.planned_start_time,'HH24:MI') ini, "
                    "       to_char(sh.planned_end_time,'HH24:MI') fim, sh.shift_date "
                    "  FROM shifts sh JOIN employees e ON e.id=sh.employee_id "
                    "  JOIN posts po ON po.id=sh.post_id "
                    " WHERE sh.employee_id = CAST(:e AS uuid) AND sh.post_id = CAST(:p AS uuid) "
                    # comparar em TEXTO: com `CAST(:h AS time)` o asyncpg passa a exigir um
                    # objeto `time` de verdade e recusa a string (a mesma lição do §103 do kit)
                    "   AND to_char(sh.planned_start_time,'HH24:MI') = :h "
                    "   AND sh.shift_date >= current_date AND sh.is_active"),
                    {"e": p["employee_id"], "p": p["post_id"], "h": p["plan"]})).mappings().all()
                if not alvo:
                    continue
                nova = f"{(int(p['plan'][:2]) + p['delta_h']) % 24:02d}:{p['plan'][3:]}"
                rel["detalhe"].append(
                    f"{alvo[0]['nome'][:30]:32} {alvo[0]['posto'][:28]:30} "
                    f"{p['plan']} → {nova}  ({len(alvo)} turno(s) futuros · "
                    f"{p['dias']} dias observados · desvio {p['desvio']:+d} min)")
                antes += [{"shift_id": a["id"], "nome": a["nome"], "data": str(a["shift_date"]),
                           "ini": a["ini"], "fim": a["fim"]} for a in alvo]
                rel["turnos"] += len(alvo)
                if aplicar:
                    await db.execute(text(
                        "UPDATE shifts SET planned_start_time = planned_start_time + make_interval(hours => :d), "
                        "                  planned_end_time   = planned_end_time   + make_interval(hours => :d), "
                        "                  updated_at = now() "
                        # lista de verdade, não string "{...}": o asyncpg espera um container
                        # para parâmetro de array e recusa a forma literal do Postgres
                        " WHERE id::text = ANY(:ids)"),
                        {"d": p["delta_h"], "ids": [a["id"] for a in alvo]})
            if aplicar and antes:
                carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
                caminho = f"/app/uploads/escala_hora_backup_{carimbo}.json"
                os.makedirs("/app/uploads", exist_ok=True)
                with open(caminho, "w", encoding="utf-8") as f:
                    json.dump(antes, f, ensure_ascii=False, indent=1)
                rel["backup"] = caminho
                await db.commit()
            return rel

    rel = asyncio.run(_rodar())
    for linha in rel["detalhe"]:
        print("  " + linha)
    for t in rel["tortos"]:
        print(f"  ⚠️ FORA DA REGRA: {t['nome'][:30]} promete {t['plan']} e bate "
              f"{t['desvio']:+d} min em {t['dias']} dias — não é uma hora limpa; "
              f"precisa de gente olhando, não de script")
    print(f"\n{'APLICADO' if rel['aplicar'] else 'ENSAIO'}: {rel['candidatos']} padrão(ões) · "
          f"{rel['turnos']} turno(s) futuros")
    if rel["backup"]:
        print(f"reversão guardada em {rel['backup']}")
    elif not rel["aplicar"]:
        print("rode com --aplicar para gravar")
    return 0


if __name__ == "__main__":
    sys.exit(main())
