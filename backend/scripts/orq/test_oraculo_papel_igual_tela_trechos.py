#!/usr/bin/env python3
"""ORÁCULO — o PAPEL imprime os MESMOS TRECHOS que a TELA, inclusive em espelho GRAVADO SEM eles.

🔴 O DEFEITO QUE ESTA REGRA GUARDA (medido em 28/09/2026, ADAILSON SERRA ALVES, folha 26/07→25/08):
a aba «Ponto do colaborador» mostrava 27/07 como 19:00→02:00 + 03:00→07:17 (duas linhas) e o PDF
da MESMA rota imprimia `19:00 07:17 |` — a parada de 1h da madrugada NÃO EXISTIA no documento que
o colaborador assina. Não era a coluna do PDF: a coluna PONTOS (períodos 1..6) já estava pronta.
Era o DADO. `daily_summary[].segmentos` só passou a ser GRAVADO em 28/09/2026 — ADAILSON tem
0 de 15 dias de 07/2026 e 0 de 6 de 08/2026 com a chave, contra 13 de 13 em 09/2026 — e mês
fechado/homologado nunca é recalculado, então esperar recálculo deixaria a folha achatada para
sempre. A TELA já derivava na leitura (`punch_controller.dias_com_segmentos`); o PDF não passava
por lá. Conserto: o mesmo `dias_com_segmentos` dentro de `ler_espelho`, o único ponto por onde
TODOS passam (PDF do mês e do período, cartão em lote, kit do GEDEON, portal, tools do chat).

AFIRMA A REGRA, NÃO A FOTOGRAFIA: nenhum id, nome, data ou hora escrito aqui. O sujeito é
DESCOBERTO no banco — um espelho cujo `daily_summary` NÃO tem a chave `segmentos` em dia nenhum
(a safra antiga, que é justamente a que o defeito atingia) e cujas batidas pareiam em 2+ trechos.
Quando toda a base for recalculada e não houver mais safra antiga, o oráculo RECUSA (exit 2) em
vez de passar em silêncio: regra sem sujeito não é regra verde.

PROVA DE QUE PEGA O CÓDIGO ANTERIOR: R1c roda `_pontos` sobre o dia CRU do `daily_summary`
gravado (sem derivação) — que é literalmente o que o PDF recebia antes — e exige UM par só.
Se o controle imprimisse dois pares, este oráculo estaria medindo o nada e sairia vermelho por
isso. R2 é a irmã de caminho feliz na direção oposta (anti-fabricação): dia que o motor pareou
em UM trecho continua imprimindo UM par — a regra não pode inventar período.

READ-ONLY: só SELECT. Não grava, não recalcula, não gera PDF em disco.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database.session import SyncSessionLocal  # noqa: E402
from modules.people_management.hr.services.espelho_ponto_pdf import _pontos  # noqa: E402
from modules.people_management.hr.services.espelho_ponto_service import ler_espelho  # noqa: E402
from modules.people_management.hr.services.espelho_service import segmentos_do_mes  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _dia_iso(d: dict) -> str:
    return str(d.get("date") or d.get("data") or "")[:10]


def _pares(txt: str) -> int:
    """Quantos períodos a coluna PONTOS do PDF imprimiu ('19:00 02:00 | 03:00 07:17 |' → 2)."""
    return len([p for p in txt.split("|") if p.strip() and ":" in p])


def main() -> int:
    falhas: list[str] = []
    with SyncSessionLocal() as db:
        # Sujeito: espelho da SAFRA ANTIGA — nenhum dia com a chave `segmentos` gravada.
        candidatos = db.execute(
            text(
                "SELECT CAST(employee_id AS TEXT), employee_name, reference_month, reference_year "
                "FROM time_sheets "
                "WHERE COALESCE(is_deleted,false)=false "
                "  AND CAST(daily_summary AS TEXT) NOT LIKE '%\"segmentos\"%' "
                "  AND jsonb_array_length(CAST(daily_summary AS jsonb)) > 0 "
                "ORDER BY reference_year DESC, reference_month DESC LIMIT 60"
            )
        ).fetchall()
        if not candidatos:
            print("RECUSO: não há mais espelho GRAVADO sem `segmentos` — a safra antiga acabou e")
            print("        esta regra ficou sem sujeito. Não é verde: é falta de caso para medir.")
            return 2

        alvo = None
        for eid, nome, mes, ano in candidatos:
            derivados = segmentos_do_mes(db, str(eid), int(mes), int(ano))
            multi = {k: v for k, v in derivados.items() if len(v) > 1}
            if multi:
                alvo = (str(eid), nome, int(mes), int(ano), multi)
                break
        if not alvo:
            print(f"RECUSO: {len(candidatos)} espelho(s) da safra antiga e nenhum com dia de 2+ trechos —")
            print("        sem plantão partido não há como provar que o papel deixou de achatar.")
            return 2

        eid, nome, mes, ano, multi = alvo
        print(f"sujeito descoberto: {nome} · {mes:02d}/{ano} · espelho gravado SEM `segmentos`")

        # ── R1 — o papel recebe os trechos e imprime um período por trecho ──
        esp = ler_espelho(db, eid, mes, ano)
        if not esp:
            print("RECUSO: ler_espelho devolveu None para o sujeito que o próprio SELECT achou")
            return 2
        por_dia = {_dia_iso(d): d for d in esp["dias"] if isinstance(d, dict)}
        dia_iso = next((k for k in multi if k in por_dia), None)
        if not dia_iso:
            falhas.append(
                "R1a o dia de 2+ trechos que as BATIDAS provam não chegou nos `dias` do espelho lido "
                f"(derivados={sorted(multi)[:3]} · dias={sorted(por_dia)[:3]})"
            )
        else:
            d = por_dia[dia_iso]
            n_seg = len(d.get("segmentos") or [])
            esperado = len(multi[dia_iso])
            if n_seg != esperado:
                falhas.append(
                    f"R1a ler_espelho entregou {n_seg} trecho(s) em {dia_iso} e as batidas pareiam "
                    f"{esperado} — o papel só imprime o que o dict traz; sem isto ele achata o plantão"
                )
            impresso = _pontos(d)
            if _pares(impresso) != esperado:
                falhas.append(
                    f"R1b a coluna PONTOS imprimiu {_pares(impresso)} período(s) em {dia_iso} "
                    f"({impresso!r}) e o dia tem {esperado} trecho(s) — hora que ninguém vê no "
                    "documento assinado"
                )
            else:
                print(f"  ✅ R1 papel == tela em {dia_iso}: {impresso}")

            # R1c — CONTROLE: o dia CRU do daily_summary gravado é o que o PDF recebia ANTES.
            cru = db.execute(
                text(
                    "SELECT CAST(daily_summary AS TEXT) FROM time_sheets "
                    "WHERE CAST(employee_id AS TEXT)=:e AND reference_month=:m AND reference_year=:y "
                    "  AND COALESCE(is_deleted,false)=false ORDER BY updated_at DESC NULLS LAST LIMIT 1"
                ),
                {"e": eid, "m": mes, "y": ano},
            ).scalar()
            antes = next((x for x in json.loads(cru or "[]") if _dia_iso(x) == dia_iso), None)
            if antes is None:
                falhas.append(f"R1c o dia {dia_iso} não está no daily_summary gravado — controle impossível")
            else:
                velho = _pontos(antes)
                if _pares(velho) >= esperado:
                    falhas.append(
                        f"R1c CONTROLE FALHOU: o dia CRU já imprimia {_pares(velho)} período(s) "
                        f"({velho!r}) — então este oráculo não está medindo o conserto"
                    )
                else:
                    print(f"  ✅ R1c controle: o dia CRU (código anterior) imprimia {velho} — achatado")

        # ── R2 — irmã de caminho feliz, direção oposta: não INVENTAR período ──
        um = next((k for k, v in segmentos_do_mes(db, eid, mes, ano).items() if len(v) == 1), None)
        if um is None:
            print("  ⚠️ R2 sem dia de trecho único neste sujeito — anti-fabricação não medida aqui")
        elif um in por_dia:
            txt = _pontos(por_dia[um])
            if _pares(txt) != 1:
                falhas.append(
                    f"R2 dia que o motor pareou em UM trecho imprimiu {_pares(txt)} período(s) "
                    f"({txt!r}) — a derivação passou a FABRICAR período"
                )
            else:
                print(f"  ✅ R2 trecho único continua um período só em {um}: {txt}")

    if falhas:
        print()
        for f in falhas:
            print(f"FALHOU: {f}")
        print(f"\nTOTAL: {len(falhas)} desvio(s)")
        return 1
    print("\nTODOS VERDES — o papel imprime os mesmos trechos da tela, e não inventa nenhum")
    return 0


if __name__ == "__main__":
    sys.exit(main())
