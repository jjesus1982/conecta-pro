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

---------------------------------------------------------------------------------------------
## 🔴 ACRÉSCIMO DE 28/09/2026 — ELE OBSERVAVA A COISA ERRADA

As duas afirmações acima olham só `facial_match IS TRUE`. **Batida de contingência não tem
`facial_match`** (a facial falhou, é por isso que ela existe): as 90 batidas de contingência da
casa eram INVISÍVEIS para este arquivo. Medido no dia: desde 15/09, `mobile` tem foto em
**889 de 889**, e `contingencia` em **0 de 90** — o buraco estava justamente onde o DP é o gate
humano, e o oráculo dizia PASS.

⭐ É a família mais cara desta casa: a lógica estava certa e a OBSERVAÇÃO estava errada. Corrigir
só o gravador sem corrigir o observador deixaria o conserto regredir pelo mesmo mecanismo que
escondeu as fotos — em silêncio, com verde na tela.

A terceira afirmação, então, **não pergunta pela facial: pergunta pelo DISPOSITIVO**, e é uma
regra de regressão, não uma nota de corte inventada:

  3. **dispositivo que guardava foto não para de guardar.** Integral que deixou de ser integral,
     ou parcial que virou zero, reprova. Quem nunca cobriu sai NOMEADO no relatório (é buraco
     conhecido, não regressão) — o que não pode é sumir do radar como sumiram as 90.

⚠️ `contingencia` vai ficar em 0% até o app passar a enviar a selfie da tentativa que falhou. Isso
é buraco DECLARADO e não reprova: um oráculo que fica vermelho esperando deploy de terceiro é um
oráculo que ninguém lê. O que reprova é ela cobrir e parar.

    python3 backend/scripts/orq/test_oraculo_foto_facial_ponto.py --autoteste
        confere a REGRA 3 contra casos sintéticos, sem tocar no banco.
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

#: Quantos dias ANTES da janela servem de referência para a regra 3. Não é nota de corte: é a
#: comparação de um dispositivo com ele mesmo.
JANELA_REFERENCIA_DIAS = 18


def perdeu_cobertura(dispositivo: str, antes: tuple[int, int], agora: tuple[int, int]) -> str | None:
    """REGRA 3 — dispositivo que guardava foto e parou de guardar. `(com_foto, total)`.

    Pura de propósito: a regra é o que precisa de teste, e testá-la não pode depender de ter o
    banco num estado específico. Ver `--autoteste`.

    Devolve None quando não há o que afirmar:
      · sem batida em um dos lados  → nada a comparar (não é verde, é silêncio honesto)
      · nunca guardou foto          → buraco conhecido, sai nomeado no relatório, não reprova
    """
    a_com, a_tot = antes
    b_com, b_tot = agora
    if a_tot == 0 or b_tot == 0:
        return None
    if a_com == 0:
        return None
    if a_com == a_tot and b_com < b_tot:
        return (f"{dispositivo}: guardava foto em TODAS as batidas ({a_com}/{a_tot}) e agora "
                f"{b_tot - b_com} de {b_tot} vieram sem foto")
    if b_com == 0:
        return (f"{dispositivo}: guardava foto em {a_com} de {a_tot} batidas e agora em "
                f"ZERO de {b_tot} — parou de guardar")
    return None


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

        # 3 — POR DISPOSITIVO, sem filtrar pela facial. É esta pergunta que enxerga a
        #     contingência: ela não tem `facial_match`, então as duas checagens acima nunca
        #     olharam para ela. Duas janelas do MESMO dispositivo — referência e agora.
        por_dev = (await db.execute(text(f"""
            SELECT device_type AS dev,
                   count(*) FILTER (WHERE punch_timestamp <  current_date - {JANELA_DIAS}) AS ref_tot,
                   count(foto_capturada_url) FILTER (WHERE punch_timestamp <  current_date - {JANELA_DIAS}) AS ref_com,
                   count(*) FILTER (WHERE punch_timestamp >= current_date - {JANELA_DIAS}) AS ago_tot,
                   count(foto_capturada_url) FILTER (WHERE punch_timestamp >= current_date - {JANELA_DIAS}) AS ago_com
            FROM gp_clock_punches
            WHERE punch_timestamp >= greatest(current_date - {JANELA_DIAS + JANELA_REFERENCIA_DIAS},
                                              DATE '{DESDE}')
            GROUP BY 1 ORDER BY 1"""))).mappings().all()

        for r in por_dev:
            achado = perdeu_cobertura(r["dev"], (r["ref_com"], r["ref_tot"]), (r["ago_com"], r["ago_tot"]))
            if achado:
                falhas.append(achado)
                continue
            # Quem nunca guardou foto sai NOMEADO. Era exatamente o que faltava: as 90 batidas
            # de contingência não reprovavam nada porque ninguém as mencionava.
            if not r["ago_tot"]:
                continue
            # ⚠️ «ok» SÓ com cobertura integral. A primeira versão desta linha imprimiu
            # «ok contingencia: 1 de 30 com foto» — 29 sem evidência com carimbo de verde, que é
            # o defeito que este arquivo existe para não cometer.
            marca = "  ok " if r["ago_com"] == r["ago_tot"] else "  ⚠️ "
            print(f"{marca}{r['dev']}: {r['ago_com']} de {r['ago_tot']} com foto nos últimos "
                  f"{JANELA_DIAS} dias (referência antes: {r['ref_com']}/{r['ref_tot']})")

    if falhas:
        for f in falhas:
            print(f"  ❌ {f}")
        print(f"TEST foto_facial_ponto FAIL ({len(falhas)})")
        sys.exit(1)
    print("\nTEST foto_facial_ponto PASS")


def _autoteste() -> None:
    """A REGRA 3 pega? Casos sintéticos, banco nenhum. Rode antes de confiar no verde."""
    # o defeito que este acréscimo existe para pegar: cobria tudo e parou
    assert perdeu_cobertura("mobile", (889, 889), (0, 40))
    # cobria tudo e passou a falhar em parte — mesmo mecanismo, escala menor
    assert perdeu_cobertura("mobile", (889, 889), (39, 40))
    # cobria em parte e parou de vez
    assert perdeu_cobertura("mobile", (500, 889), (0, 40))
    # continua cobrindo integralmente
    assert perdeu_cobertura("mobile", (889, 889), (40, 40)) is None
    # nunca cobriu: é a contingência de hoje (0 de 90). Buraco declarado, não regressão —
    # se isto reprovasse, o oráculo nasceria vermelho esperando deploy de terceiro.
    assert perdeu_cobertura("contingencia", (0, 90), (0, 12)) is None
    # e o dia em que a contingência começar a guardar foto, ela entra na regra como as outras
    assert perdeu_cobertura("contingencia", (12, 12), (0, 5))
    # sem amostra em um dos lados não se afirma nada (dispositivo novo, ou casa parada)
    assert perdeu_cobertura("offline", (0, 0), (5, 5)) is None
    assert perdeu_cobertura("offline", (5, 5), (0, 0)) is None
    print("autoteste da regra 3: 8 casos OK (inclui o defeito medido de 28/09)")


if __name__ == "__main__":
    if "--autoteste" in sys.argv:
        _autoteste()
    else:
        asyncio.run(main())
