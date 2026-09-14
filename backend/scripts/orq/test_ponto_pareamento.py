#!/usr/bin/env python3
"""As três regras do pareamento de ponto que quebraram em 09/2026 — e o que cada uma custou.

Setembro tinha **180 anomalias em 43 das 51 pessoas** e não fechava. Nenhuma era erro de
funcionário. Eram três defeitos nossos:

  1. **Duas fontes no mesmo dia (67 anomalias).** O pull do Sólides/Tangerino trazia a
     GRADE da escala, não batida medida: 422 registros com 48 horários distintos, 382 em
     hora cheia, contra 763 registros e 763 horários distintos do app. Nos 95 dias-pessoa
     em que as duas coexistiam, a grade (~1h adiantada) entrava no pareamento e produzia
     `entrada(08:00 grade) → entrada(09:01 app)` + `saida(18:01 app)` órfã: exatamente um
     `par_incompleto` e um `saida_sem_entrada` por dia.

  2. **Turno em andamento virava anomalia (8).** Quem entrou às 19:00 de hoje sai às 07:00
     de amanhã. O espelho cobrava a saída no mesmo instante — e o DP não tinha o que
     corrigir, porque não havia nada errado.

  3. **A fresta de 1 segundo.** `_proxima_batida_info` abria a janela de contagem em 14h
     **e 1 segundo**. Quem trabalha 08:00–18:00 tem exatos 14h entre a saída e a entrada
     seguinte: a saída da véspera vazava, `feitas` valia 1, e o app rotulava a ENTRADA DA
     MANHÃ como «saída para o almoço». O NAILSON teve 4 dias assim em setembro, cada um
     gerando 2 anomalias.

    docker exec -e PYTHONPATH=/app conecta-pro-backend \
        python3 /app/scripts/orq/test_ponto_pareamento.py

Linha canônica: `TOTAL: <n> regra(s) de pareamento violada(s)`. Exit 1 se houver.
"""
from __future__ import annotations

import re as _re
import sys
from datetime import datetime, timedelta


def main() -> int:
    from modules.people_management.hr.services.espelho_service import (  # noqa: PLC0415
        FONTES_MEDIDAS,
        _parear,
        _uma_fonte_por_dia,
    )

    falhas: list[str] = []

    def b(dia: str, hora: str, tipo: str, dev: str = "mobile") -> dict:
        return {
            "punch_timestamp": datetime.fromisoformat(f"{dia}T{hora}"),
            "punch_type": tipo,
            "device_type": dev,
            "punch_id": f"{dia}{hora}{tipo}",
        }

    # REGRA 1 — no dia com batida medida, a grade importada sai; no dia sem, ela fica.
    dia_misto = [
        b("2026-09-02", "08:00:00", "entrada", "tangerino"),
        b("2026-09-02", "09:01:00", "entrada"),
        b("2026-09-02", "12:01:00", "saida_almoco"),
        b("2026-09-02", "13:03:00", "retorno_almoco"),
        b("2026-09-02", "17:00:00", "saida", "tangerino"),
        b("2026-09-02", "18:01:00", "saida"),
        # 03/09 é só grade: gente que ainda não está no app, e o dia é real.
        b("2026-09-03", "08:00:00", "entrada", "tangerino"),
        b("2026-09-03", "17:00:00", "saida", "tangerino"),
    ]
    filtrado = _uma_fonte_por_dia(dia_misto)
    tang_02 = [
        x for x in filtrado
        if x["device_type"] == "tangerino" and x["punch_timestamp"].day == 2
    ]
    tang_03 = [
        x for x in filtrado
        if x["device_type"] == "tangerino" and x["punch_timestamp"].day == 3
    ]
    if tang_02:
        falhas.append(f"dia com batida medida ainda carrega {len(tang_02)} registro(s) da grade")
    if len(tang_03) != 2:
        falhas.append("dia SEM batida medida perdeu a grade — gente fora do app fica sem ponto")

    _, anomalias = _parear(filtrado)
    if anomalias:
        falhas.append(
            f"dia de fonte dupla ainda gera {len(anomalias)} anomalia(s): "
            + "; ".join(a["type"] for a in anomalias)
        )

    # REGRA 2 — turno aberto AGORA não é anomalia; turno aberto há dias é.
    agora = datetime.now()
    em_curso = [b(agora.strftime("%Y-%m-%d"), (agora - timedelta(hours=2)).strftime("%H:%M:%S"), "entrada")]
    _, anom_curso = _parear(em_curso)
    if anom_curso:
        falhas.append("turno em andamento (entrou há 2h) foi contado como anomalia")

    velho = agora - timedelta(days=4)
    _, anom_velho = _parear([b(velho.strftime("%Y-%m-%d"), "19:00:00", "entrada")])
    if not anom_velho:
        falhas.append("entrada de 4 dias atrás SEM saída não acusou — a guarda comeu o achado real")

    # REGRA 3 — a fresta de 1 segundo não pode voltar ao SQL de `_proxima_batida_info`.
    # Lê o ARQUIVO, não `inspect.getsource` da função: getsource segue o objeto em memória
    # e um monkeypatch de teste o deixa sem fonte. O que se afirma aqui é sobre o código
    # que está no disco — que é o que roda em produção.
    from pathlib import Path as _P  # noqa: PLC0415

    alvo = _P("/app/modules/people_management/employee_portal/controllers/self_service_controller.py")
    if not alvo.exists():
        alvo = _P(__file__).resolve().parents[1] / (
            "modules/people_management/employee_portal/controllers/self_service_controller.py"
        )
    if not alvo.exists():
        falhas.append(f"não achei {alvo} para conferir a janela de contagem")
    else:
        texto = alvo.read_text()
        i = texto.find("async def _proxima_batida_info")
        corpo = texto[i : texto.find("\nasync def ", i + 10)] if i >= 0 else ""
        if not corpo:
            falhas.append("_proxima_batida_info sumiu do controller — a regra 3 ficou sem alvo")
        # A forma correta fecha o subselect e JÁ aplica o -1s ali dentro do coalesce.
        # Compara com o espaçamento colapsado: o que importa é a ordem dos termos no SQL,
        # não quantos espaços o formatador deixou entre as aspas e o parêntese.
        elif ") - interval '1 second' , (now(" not in _re.sub(
            r"\s+", " ", corpo.replace('"', " ").replace(",", " , ")
        ):
            falhas.append(
                "o -1s saiu de dentro do GREATEST em _proxima_batida_info: a janela volta a "
                "abrir em 14h+1s e a entrada da manhã de quem faz 08:00–18:00 vira "
                "'saída para o almoço' (caso NAILSON, 4 dias em 09/2026)"
            )

    # Sanidade do vocabulário: se alguém renomear as fontes medidas, a regra 1 morre calada.
    if "mobile" not in FONTES_MEDIDAS or "tangerino" in FONTES_MEDIDAS:
        falhas.append(f"FONTES_MEDIDAS inconsistente: {FONTES_MEDIDAS}")

    for f in falhas:
        print(f"   ✗ {f}")
    if not falhas:
        print("   ✓ fonte dupla separada por dia, turno em andamento fora, fresta de 1s fechada")
    print(f"\nTOTAL: {len(falhas)} regra(s) de pareamento violada(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
