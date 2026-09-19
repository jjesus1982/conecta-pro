#!/usr/bin/env python3
"""O inventário do que está MORTO no DP — e o alarme para quando alguém mexer nele.

`ARSENAL_SKILLS.md` §6 lista, como a única lacuna que sobrou do arsenal, o **"mapa do
não-vigiado"**: cruzar a superfície (rotas, telas) com os oráculos e devolver o descoberto.
Este é o pedaço dele que cabe ao DP.

A afirmação 5 do fechamento é *"nenhuma superfície viva sem vigia; nenhuma superfície morta
fingindo estar viva"*. A segunda metade não se resolve apagando código: apagar remove a
superfície E a informação de que ela existiu. Resolve-se tirando o disfarce — declarando o
que está morto, com número, e **falhando quando o número mudar**.

Três asserções, e as duas primeiras existem para se contradizerem:

  (A) o que está declarado MORTO continua morto. Se uma tabela do inventário ganhar linhas,
      é boa notícia — e este oráculo reprova mesmo assim, porque o inventário virou mentira
      e alguém precisa reclassificar a superfície que a serve.
  (B) o que está declarado VIVO continua vivo. `time_sheets` entrou aqui porque eu quase a
      apaguei: ela tem 170 linhas e o diff que eu ia aplicar teria desmontado a superfície
      dela. Se zerar, a superfície correspondente passou a ser morta e ninguém viu.
  (C) nenhum prefixo duplicado NOVO no território do DP. Foram 107 (`time-tracking` 64 +
      `payroll` 43) corrigidos em 13/08; o padrão nasce sozinho toda vez que alguém inclui
      um sub-router que já traz o próprio prefixo, e nasce calado.

O que este oráculo NÃO faz: não decide o destino da superfície morta. Quarentenar, remontar
ou reescrever é decisão de quem conhece o negócio. Ele só garante que a decisão seja tomada
com o número na mão, e não descoberta seis meses depois.

Receita:
  docker exec -e PYTHONPATH=/app conecta-pro-backend \\
    python3 /app/scripts/orq/test_oraculo_superficie_morta.py
"""

from __future__ import annotations

import asyncio
import logging
import sys
from collections import Counter

sys.path.insert(0, "/app")
logging.disable(logging.CRITICAL)

from sqlalchemy import text  # noqa: E402

from core.database.session import async_session_factory  # noqa: E402

#: Tabelas do DP medidas VAZIAS em 13/08/2026, com a superfície que cada uma sustenta.
#: Entrar aqui não é sentença — é declaração. Sair daqui exige reclassificar a superfície.
MORTAS = {
    "ged_documents": "39 rotas + telas em app/modulos/documentos; o GED vivo é por KITS",
    "ged_document_shares": "23 rotas; componente DocumentShareDialog não é renderizado por página nenhuma",
    # ged_document_versions saiu daqui em 07/09/2026: foi para a quarentena (schema lixo_20260906)
    # no mapa de 06/09, junto das outras 🔴. Morta declarada que deixa de existir é dívida paga.
    "time_entries": "parte das 64 rotas de ponto; o ponto vivo é gp_clock_punches",
    "overtimes": "idem",
    "time_justifications": "idem",
    "work_schedules": "idem",
    "payroll_events": "parte das 43 rotas de folha; a folha viva é hr_payslips",
    "payroll_exports": "idem",
    "eventos_esocial": "o espelho vivo é esocial_eventos_espelho",
    "employee_documents": "sem superfície própria hoje",
}

#: Tabelas VIVAS cuja superfície eu quase classifiquei como morta. Duas afirmações por
#: tabela: `piso` guarda contra APAGAMENTO EM MASSA, e `dias` diz de quanto em quanto tempo
#: a fonte escreve — é este que responde «a fonte parou».
#:
#: ⚠️ 18/09/2026 — antes havia só o piso, e ele acusou `hr_payslips` por 796 contra 800. A
#: fonte não tinha parado: a última escrita era de 14/09, quatro dias antes. O que oscila
#: são os RASCUNHOS — a tabela guarda o holerite oficial (`published`, 360 linhas, registro
#: que não se mexe) e o cálculo da casa (`draft`, 380), e rascunho é substituído a cada
#: recálculo de folha, por desenho. Piso absoluto sobre população que muda de propósito é
#: régua que toca por meio por cento e ensina todo mundo a ignorar o sino.
#:
#: `dias=None` = tabela de REFERÊNCIA, que não recebe escrita regular (a `cct_cargos` é a
#: tabela da CCT: 51 cargos, última escrita em 30/03, e isso está certo).
VIVAS = {
    "time_sheets": (170, 45),
    "gp_clock_punches": (7800, 3),
    "ged_kit_documents": (2600, 15),
    # piso nos IMUTÁVEIS: 360 publicados hoje; 300 é margem contra apagamento, não contra
    # oscilação de rascunho. A folha é mensal — 45 dias cobre o mês fechado com folga.
    "hr_payslips": (300, 45),
    "cct_cargos": (51, None),
}

#: Para `hr_payslips` o piso vale sobre o que NÃO se reescreve. Sem isto, contar tudo
#: mistura registro entregue com rascunho de recálculo.
CONDICAO_DO_PISO = {"hr_payslips": "status = 'published'"}

#: Prefixos do território do DP. `fiscal` e financeiro têm os deles e não são meus.
MEUS = ("/hr/", "/dp/", "/ponto/", "/ged/", "/portal/", "/human-resources/", "/sst/")


async def main() -> int:
    falhas: list[str] = []

    async with async_session_factory() as db:
        # ── (A) o morto continua morto ───────────────────────────────────────
        ressuscitadas = []
        for tabela, superficie in MORTAS.items():
            try:
                n = (await db.execute(text(f"SELECT count(*) FROM {tabela}"))).scalar()  # noqa: S608
            except Exception:  # noqa: BLE001 — tabela removida também é mudança a declarar
                await db.rollback()
                falhas.append(f"(A) `{tabela}` não existe mais — o inventário precisa saber")
                continue
            if n:
                ressuscitadas.append((tabela, n, superficie))
        print(f"(A) tabelas declaradas mortas: {len(MORTAS)} · com linhas agora: {len(ressuscitadas)}")
        for tabela, n, sup in ressuscitadas:
            print(f"    ✗ {tabela}: {n} linha(s) — {sup}")
            falhas.append(
                f"(A) `{tabela}` tem {n} linha(s) e estava declarada MORTA. A superfície que "
                f"ela serve ({sup}) precisa ser reclassificada — pode ser que tenha "
                f"nascido um fluxo novo, e superfície viva sem vigia é dívida no dia em "
                f"que nasce"
            )

        # ── (B) o vivo continua vivo ─────────────────────────────────────────
        secas, paradas = [], []
        for tabela, (piso, dias) in VIVAS.items():
            onde = CONDICAO_DO_PISO.get(tabela)
            sql = f"SELECT count(*) FROM {tabela}" + (f" WHERE {onde}" if onde else "")  # noqa: S608
            n = (await db.execute(text(sql))).scalar()
            if n < piso:
                secas.append((tabela, n, piso, onde))
            if dias is not None:
                idade = (
                    await db.execute(
                        text(  # noqa: S608
                            f"SELECT (current_date - max(created_at)::date) FROM {tabela}"
                        )
                    )
                ).scalar()
                if idade is None or int(idade) > dias:
                    paradas.append((tabela, idade, dias))
        print(
            f"(B) tabelas declaradas vivas: {len(VIVAS)} · abaixo do piso: {len(secas)} · "
            f"sem escrita na janela: {len(paradas)}"
        )
        for tabela, n, piso, onde in secas:
            print(f"    ✗ {tabela}: {n} (piso {piso}{' em ' + onde if onde else ''})")
            falhas.append(
                f"(B) `{tabela}` caiu para {n}, abaixo do piso {piso}"
                + (f" (contando só {onde})" if onde else "")
                + " — some registro que não deveria sumir"
            )
        for tabela, idade, dias in paradas:
            print(f"    ✗ {tabela}: última escrita há {idade} dia(s) (janela {dias})")
            falhas.append(
                f"(B) `{tabela}` sem escrita há {idade} dia(s), acima da janela de {dias} — "
                f"a fonte que alimenta esta superfície parou"
            )

    # ── (C) prefixo duplicado novo no DP ─────────────────────────────────────
    from main_production import app  # noqa: PLC0415 — import caro, só quando roda

    dup: Counter = Counter()
    for rota in app.routes:
        p = getattr(rota, "path", "")
        if not any(m in p for m in MEUS):
            continue
        segs = [s for s in p.split("/") if s]
        for i in range(len(segs) - 1):
            if segs[i] == segs[i + 1]:
                dup[segs[i]] += 1
    print(f"(C) prefixos duplicados no território do DP: {sum(dup.values())}")
    for seg, n in dup.most_common():
        print(f"    ✗ /{seg}/{seg}/ — {n} rota(s)")
    if dup:
        falhas.append(
            f"(C) {sum(dup.values())} rota(s) do DP com prefixo duplicado. Foram 107 "
            f"corrigidas em 13/08; o padrão volta sozinho quando alguém inclui um "
            f"sub-router que já traz o próprio prefixo — e volta calado"
        )

    if falhas:
        for f in falhas:
            print(f"FALHA: {f}")
        print("TEST oraculo_superficie_morta FAIL")
        return 1
    print(
        "\nO inventário do morto está declarado e confere. Isto NÃO quer dizer que a "
        "superfície morta foi resolvida — quer dizer que ela parou de se passar por "
        "viva, e que o dia em que mudar alguém vai saber."
    )
    print("TEST oraculo_superficie_morta PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
