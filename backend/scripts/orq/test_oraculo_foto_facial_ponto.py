"""Prova que batida aprovada na facial guarda a FOTO, e que a foto existe no disco.

POR QUE EXISTE — 25/09/2026. Medido: **2.216 batidas com `facial_match = true` e
`foto_capturada_url` NULO**, de julho a 14/09. Aprovação biométrica registrada sem a prova
guardada — o `true` estava lá, a evidência não.

E o defeito ficou CALADO por dois meses: julho 7/7 sem foto, agosto **1.380 de 1.380** (100%),
setembro 829 de 1.635. Ninguém notou porque nada ficava vermelho: a batida entrava, o ponto
fechava, e o campo vazio não impedia nada.

⭐ **Já estava consertado quando eu fui olhar.** A virada foi 14/09 (20 de 86 naquele dia) e de
15/09 em diante são **onze dias seguidos com 100%** — 786 batidas, zero sem foto. As 2.216 antigas
são irrecuperáveis: aquelas fotos nunca foram gravadas, não há de onde puxar.

Então o valor deste oráculo não é achar o defeito — é impedir que ele **volte em silêncio**,
que foi como ele viveu. Duas afirmações, e a segunda é a que o `true` sozinho não dá:

  1. batida recente aprovada na facial TEM `foto_capturada_url`
  2. a URL aponta para um arquivo que EXISTE no disco  ← senão é o verde que não prova nada

⚠️ Afirma a REGRA, não o retrato: a janela é MÓVEL (últimos 3 dias) e não fixa nenhum número.
Se eu olhasse o histórico, ele ficaria vermelho para sempre por causa das 2.216 antigas, e um
oráculo cronicamente vermelho é um oráculo que ninguém lê.
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database import async_session_factory  # noqa: E402

# 15/09/2026 é o dia em que o conserto passou a valer integralmente. Antes disso a ausência de
# foto é fato histórico, não defeito corrente — e cobrar o passado deixaria o teste vermelho
# eternamente, o que o mata na prática.
DESDE = "2026-09-15"
JANELA_DIAS = 3
RAIZ_FOTOS = Path("/app/uploads/ponto")


async def main() -> None:
    falhas: list[str] = []
    async with async_session_factory() as db:

        # 1 — batida recente aprovada na facial sem foto
        rows = (await db.execute(text(f"""
            SELECT date(punch_timestamp) AS dia,
                   count(*) AS aprovadas,
                   count(*) FILTER (WHERE foto_capturada_url IS NULL) AS sem_foto
            FROM gp_clock_punches
            WHERE facial_match IS TRUE
              AND punch_timestamp >= greatest(current_date - {JANELA_DIAS}, DATE '{DESDE}')
            GROUP BY 1 ORDER BY 1"""))).mappings().all()

        if not rows:
            # CONTROLE: sem batida na janela eu não sei se está tudo bem ou se o ponto parou.
            # Dizer "PASS" aqui seria o verde sobre tabela vazia.
            print("⚠️  nenhuma batida aprovada na facial nos últimos "
                  f"{JANELA_DIAS} dias — nada a afirmar, e isso já é sinal")
            print("TEST foto_facial_ponto INCONCLUSIVO")
            sys.exit(0)

        total = sum(r["aprovadas"] for r in rows)
        sem = sum(r["sem_foto"] for r in rows)
        if sem:
            for r in rows:
                if r["sem_foto"]:
                    falhas.append(f"{r['dia']}: {r['sem_foto']} de {r['aprovadas']} batidas "
                                  "aprovadas na facial SEM foto guardada")
        else:
            print(f"  ok  {total} batidas aprovadas na facial nos últimos {JANELA_DIAS} dias, "
                  "todas com foto")

        # 2 — a URL aponta para arquivo que EXISTE. `foto_capturada_url` preenchido não é prova
        #     de que a foto está lá: é prova de que alguém escreveu um caminho.
        urls = (await db.execute(text(f"""
            SELECT foto_capturada_url AS u FROM gp_clock_punches
            WHERE facial_match IS TRUE AND foto_capturada_url IS NOT NULL
              AND punch_timestamp >= greatest(current_date - {JANELA_DIAS}, DATE '{DESDE}')
            ORDER BY punch_timestamp DESC LIMIT 20"""))).mappings().all()
        mortas = [u["u"] for u in urls
                  if not (RAIZ_FOTOS / str(u["u"]).replace("/uploads/ponto/", "")).is_file()]
        if mortas:
            falhas.append(f"{len(mortas)} de {len(urls)} URLs de foto apontam para arquivo que "
                          f"NÃO existe no disco — ex.: {mortas[0]}")
        elif urls:
            print(f"  ok  {len(urls)} URLs conferidas contra o disco, todas existem")

    if falhas:
        for f in falhas:
            print(f"  ❌ {f}")
        print(f"TEST foto_facial_ponto FAIL ({len(falhas)})")
        sys.exit(1)
    print("\nTEST foto_facial_ponto PASS")


if __name__ == "__main__":
    asyncio.run(main())
