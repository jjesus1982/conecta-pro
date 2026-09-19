#!/usr/bin/env python3
"""A data que gravamos do banco é a data que o BANCO enxerga — no fuso de Manaus.

Origem: 18/09/2026. O oráculo do extrato acusou «Cora SCD: LINHA FANTASMA — temos hoje
R$ -1.000,00 que o banco não reporta». Não era fantasma nem ordem de pagamento iniciada: era
um débito de **17/09 às 20:41** que nós lançamos em **18/09**.

A Cora devolve `createdAt` em **UTC**. Manaus é UTC−4, e o extrato DELA é recortado pela data
LOCAL. Tudo que acontece entre 20h e meia-noite de Manaus cai em 00h–04h UTC e ia para o dia
seguinte nos nossos livros. Medido em 60 dias: **77 de 486 lançamentos (15%) no dia errado,
R$ 110.057,03 envolvidos** — inclusive um débito de R$ 27.000 datado um dia à frente.

Isso não é detalhe de exibição: conciliação diária, fluxo de caixa por dia e o razão passam a
falar de dias diferentes do que o banco fala. E é a TERCEIRA vez que fuso morde nesta casa —
a escala do ponto ficou 1h fora desde julho pela mesma família de erro.

## A régua

Para cada transação nossa com `external_id` do banco, pergunta ao banco qual é o `createdAt`
e compara a data em **America/Manaus** com a que gravamos. Diferença é achado — não há
interpretação possível: a data é a do banco.

⚠️ Correção que CRUZA a virada do mês não se aplica sozinha e também não se esconde: ela muda
competência fechada, e isso é decisão do dono com a contabilidade. Sai em linha própria.

    python3 backend/scripts/qa/checar_data_do_banco_no_fuso.py

Linha canônica: `TOTAL: <n> lançamento(s) com data fora do fuso do banco`. Exit 1 com achado.
"""

from __future__ import annotations

import subprocess
import sys

DOCKER = "/usr/bin/docker"  # nosec B607 — ruff S607 recusa executável parcial
CONTAINER = "conecta-pro-backend"

#: Janela conferida. 90 dias cobre o trimestre e mantém a consulta barata; o defeito é
#: sistemático, então se existir aparece dentro disso.
_DIAS = 90

_SONDA = r"""
import sys, json, asyncio
sys.path.insert(0, "/app")
from datetime import date, timedelta, datetime
from zoneinfo import ZoneInfo
from sqlalchemy import text
from core.database.session import SyncSessionLocal
from modules.integrations.banking.adapters.cora import CoraAdapter
TZ = ZoneInfo("America/Manaus")

async def main():
    a = CoraAdapter(); await a.ensure_authenticated()
    fim = date.today(); ini = fim - timedelta(days=DIAS)
    ent, pg = [], 1
    async with a._client() as cli:
        while True:
            r = await cli.get("/bank-statement/statement", headers=a._auth_headers(),
                              params={"start": ini.isoformat(), "end": fim.isoformat(),
                                      "page": pg, "perPage": 200})
            lote = r.json().get("entries") or []
            ent += lote
            if len(lote) < 200: break
            pg += 1
    certo = {e.get("id"): datetime.fromisoformat(str(e.get("createdAt","")).replace("+00","+00:00"))
             .astimezone(TZ).date().isoformat() for e in ent}
    dentro, cruza, conferidas = [], [], 0
    with SyncSessionLocal() as db:
        for bid, ext, dt, val in db.execute(text(
            "SELECT id::text, external_id, transaction_date, amount FROM bank_transactions "
            " WHERE external_id LIKE 'ent_%' AND transaction_date >= :i"), {"i": ini}).all():
            real = certo.get(ext)
            if real is None: continue
            conferidas += 1
            if real == dt.isoformat(): continue
            item = {"valor": float(val), "nossa": dt.isoformat(), "banco": real}
            (cruza if real[:7] != dt.isoformat()[:7] else dentro).append(item)
    print("JSON " + json.dumps({"conferidas": conferidas, "dentro": dentro, "cruza": cruza}))

asyncio.run(main())
"""


def main() -> int:
    r = subprocess.run(  # noqa: S603  # nosec B603 - argv fixo, sem shell
        [DOCKER, "exec", "-e", "PYTHONPATH=/app", "-i", CONTAINER, "python3", "-"],
        input=_SONDA.replace("DIAS", str(_DIAS)),
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    linha = next((x for x in r.stdout.splitlines() if x.startswith("JSON ")), "")
    if not linha:
        # Banco fora do ar não é "tudo certo": é o terceiro estado, dito de frente.
        print(f"NÃO MEDIDO: não consegui falar com o banco — {(r.stderr or '').strip()[-180:]}")
        print("TOTAL: 0 lançamento(s) com data fora do fuso do banco")
        return 0
    import json

    d = json.loads(linha[5:])
    dentro, cruza = d["dentro"], d["cruza"]

    for x in dentro[:8]:
        print(f"  🕐 R$ {x['valor']:>10,.2f}  gravamos {x['nossa']} · banco diz {x['banco']}")
    if len(dentro) > 8:
        print(f"     (+{len(dentro) - 8} não listadas)")
    for x in cruza:
        print(
            f"  📅 R$ {x['valor']:>10,.2f}  gravamos {x['nossa']} · banco diz {x['banco']} "
            f"— CRUZA A VIRADA DO MÊS: muda competência, decisão do dono"
        )

    achados = len(dentro) + len(cruza)
    print(f"{d['conferidas']} lançamento(s) conferidos contra o banco · {d['conferidas'] - achados} com a data certa")
    print(f"TOTAL: {achados} lançamento(s) com data fora do fuso do banco")
    return 1 if achados else 0


if __name__ == "__main__":
    sys.exit(main())
