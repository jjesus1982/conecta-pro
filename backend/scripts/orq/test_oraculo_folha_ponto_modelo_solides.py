#!/usr/bin/env python3
"""ORÁCULO — a folha de ponto impressa tem as colunas do modelo REAL, e campo sem fonte sai
TRACEJADO em vez de zero.

Por que existe (28/09/2026). O dono subiu o modelo que o DP usa no papel:
`auditoria/pyetra-prints/fp.pdf`, 53 páginas, período 26/07→25/08/2026. Lido com pymupdf, ele traz
por dia `DIA/MÊS | PONTOS (PERÍODO 1..6) | TRABALHADAS | PREVISTAS | ABONO | SALDO`, com a batida
lançada à mão marcada `(m)`, e no rodapé a declaração «Reconheço a exatidão…». O gerador desta casa
imprimia UMA coluna Entrada e UMA coluna Saída — então o plantão que o motor pareou como
`19:00→02:00` + `03:00→07:17` saía no papel como "19:00 … 07:17" e a parada de 1h da madrugada
não existia no documento que o colaborador ASSINA. Medido no banco: 691 dias com `segmentos`
publicados pelo motor e **388 deles com 2+ segmentos** — 56% dos plantões de 09/2026.

O outro defeito que este oráculo tranca é o inverso de faltar coluna: **coluna com zero que parece
dado**. ABONO não tem fonte preenchida nesta casa (`time_justifications`: 0 linhas;
`gp_justifications`, a que o ponto usa de verdade, não tem campo de duração) e Centro de Custo está
vazio em 93/93 ativos. Imprimir "00:00" nesses campos afirmaria "apurei e deu zero". A regra é
dash.

REGRAS afirmadas (regra, nunca fotografia — nenhum nome, id, data ou total está escrito aqui; o
sujeito do teste de ponta a ponta é DESCOBERTO no banco):

  R1  PERÍODO 1..6 — dia com N segmentos apurados imprime N pares `entrada saida |` na coluna
      PONTOS (até 6). Nenhum par do motor desaparece no papel.
  R2  `(m)` só onde o MOTOR marcou (`entrada_manual`/`saida_manual`); ponta não-manual sai sem a
      marca. A marca nunca é heurística do gerador.
  R3  ÓRFÃ NÃO VIRA HORA — segmento incompleto imprime `—` na ponta que o motor não achou, e a
      ponta que existe aparece. Nunca se chuta a hora que falta.
  R4  CAMPO SEM FONTE = DASH, NUNCA ZERO — dia sem abono lançado imprime "—" na coluna ABONO.
      (`_hm(0)` devolve "00:00": se alguém trocar a função, esta regra fica vermelha.)
  R5  ABONO FECHA O SALDO — é o mecanismo que a Pyetra pediu: no dia abonado de dia inteiro o
      ABONO vale as PREVISTAS e o SALDO do dia fecha em 00:00, mesmo com 0 min trabalhados.
  R6  MAIS DE 6 PERÍODOS NÃO SOME EM SILÊNCIO — a folha tem seis colunas; o 7º par é declarado
      ("+N períodos"), porque par perdido no documento assinado é hora que ninguém vê.
  R7  QUADRO DE HORÁRIOS FAIL-CLOSED — a escala publicada dá MAIS DE UMA janela planejada para a
      mesma pessoa no mesmo período em 48 de 63 pessoas (medido 26/07→25/08/2026). Com 2+ janelas
      o PDF diz o motivo em vez de escolher uma; com exatamente 1, imprime a janela. Rodado nos
      DOIS sentidos contra o banco (irmã de caminho feliz — senão a regra só provaria a recusa).
  R8  O PDF de ponta a ponta traz os blocos do modelo: PONTOS, ABONO, SALDO, PREVISTAS, CTPS/Série,
      Código, Centro de Custo, Quadro de Horários, Dias faltosos, Horas noturnas, Horas ficta e a
      declaração de reconhecimento. Sujeito descoberto no banco.

CONTROLE (por que este oráculo não é cúmplice): R1, R2, R3 e R6 são rodadas TAMBÉM contra o
comportamento ANTERIOR, reconstruído aqui em `_pontos_anterior` — literalmente as duas colunas
Entrada/Saída que o gerador tinha (`_horario(d,"entrada")` e `_horario(d,"saida")`). Se o controle
PASSAR, o oráculo está medindo o nada e sai VERMELHO por isso.

Read-only: só SELECT e PDF em memória. Nada é gravado.

Rodar:  docker exec conecta-pro-backend python /app/scripts/orq/test_oraculo_folha_ponto_modelo_solides.py
"""

from __future__ import annotations

import sys
from datetime import date, timedelta

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database.session import get_sync_db  # noqa: E402
from modules.people_management.hr.services.espelho_ponto_pdf import (  # noqa: E402
    _abono,
    _horario,
    _pontos,
    _saldo_dia,
)

falhas: list[str] = []


def ok(nome: str, cond: bool, detalhe: str = "") -> None:
    print(f"  {'✅' if cond else '❌'} {nome}{(' — ' + detalhe) if detalhe else ''}")
    if not cond:
        falhas.append(nome)


def _pontos_anterior(d: dict) -> str:
    """CONTROLE — o que o gerador imprimia antes de 28/09/2026: UMA entrada e UMA saída.

    Cópia fiel das duas células que existiam na tabela diária (espelho_ponto_pdf.py, colunas
    "Entrada" e "Saída"): a primeira entrada e a última saída do dia, sem nenhuma noção de par.
    """
    return (
        f'{_horario(d, "entrada", "clock_in", "entrada_1")} '
        f'{_horario(d, "saida", "saída", "clock_out", "saida_1")} |'
    )


def _abono_anterior(d: dict) -> str:
    """CONTROLE — não havia coluna ABONO. O jeito natural (e errado) de criá-la é somar 0 e
    formatar: dá "00:00", um zero que passa por apurado."""
    from modules.people_management.hr.services.espelho_ponto_pdf import _hm

    return _hm(d.get("abono") or 0)


# ── Dias SINTÉTICOS: o contrato de `daily_summary` que o motor publica, não dado de ninguém ──
DIA_2_SEG = {
    "date": "2026-01-02",
    "entrada": "19:00",
    "saida": "07:17",
    "worked": 677,
    "expected": 660,
    "segmentos": [
        {"entrada": "19:00", "saida": "02:00", "minutos": 420, "incompleto": False,
         "entrada_manual": False, "saida_manual": False},
        {"entrada": "03:00", "saida": "07:17", "minutos": 257, "incompleto": False,
         "entrada_manual": False, "saida_manual": False},
    ],
}
DIA_MANUAL = {
    **DIA_2_SEG,
    "segmentos": [
        {**DIA_2_SEG["segmentos"][0], "entrada_manual": True},
        {**DIA_2_SEG["segmentos"][1], "entrada_manual": True, "saida_manual": False},
    ],
}
DIA_ORFA = {
    "date": "2026-01-03",
    "entrada": "19:00",
    "saida": "19:00",
    "worked": 0,
    "expected": 660,
    "segmentos": [
        {"entrada": "19:00", "saida": None, "minutos": 0, "incompleto": True,
         "falta": "saida", "entrada_manual": False, "saida_manual": False},
    ],
}
DIA_7_SEG = {
    "date": "2026-01-04",
    "worked": 600,
    "expected": 660,
    "segmentos": [
        {"entrada": f"{6 + i:02d}:00", "saida": f"{6 + i:02d}:30", "minutos": 30,
         "incompleto": False, "entrada_manual": False, "saida_manual": False}
        for i in range(7)
    ],
}
DIA_ABONADO = {"date": "2026-01-05", "worked": 0, "expected": 660, "abono": -1}
DIA_SEM_ABONO = {"date": "2026-01-06", "worked": 660, "expected": 660}


def regras_puras(pontos, abono) -> dict[str, bool]:
    """As regras que dependem só de renderização, avaliadas contra UM par de funções.

    Recebe as funções para poder rodar as MESMAS regras contra o comportamento anterior (controle).
    """
    p2 = pontos(DIA_2_SEG)
    pm = pontos(DIA_MANUAL)
    po = pontos(DIA_ORFA)
    p7 = pontos(DIA_7_SEG)
    return {
        # R1 — os DOIS pares do plantão no papel, com as quatro horas do motor
        "R1": p2.count("|") == 2 and all(h in p2 for h in ("19:00", "02:00", "03:00", "07:17")),
        # R2 — (m) onde o motor marcou, e ausente onde não marcou
        "R2": pm.count("(m)") == 2 and "(m)19:00" in pm and "(m)07:17" not in pm and "(m)" not in p2,
        # R3 — órfã: a ponta que existe aparece, a que falta é dash (nunca hora chutada)
        "R3": "19:00" in po and "—" in po and po.count("|") == 1,
        # R6 — 6 períodos + declaração do que sobrou
        "R6": p7.count("|") == 6 and "+1" in p7,
        # R4 — dia sem abono lançado sai tracejado, jamais "00:00"
        "R4": abono(DIA_SEM_ABONO) == "—",
    }


print("ORÁCULO — folha de ponto no modelo do Solides (PONTOS 1..6 · ABONO · SALDO · dash≠zero)")
print("\n1) Renderização da linha do dia (código ATUAL)")
atual = regras_puras(_pontos, _abono)
ok("R1 PERÍODO 1..6 — os dois pares do plantão saem no papel", atual["R1"], _pontos(DIA_2_SEG))
ok("R2 `(m)` só onde o motor marcou manual", atual["R2"], _pontos(DIA_MANUAL))
ok("R3 órfã imprime dash na ponta que falta, nunca hora chutada", atual["R3"], _pontos(DIA_ORFA))
ok("R4 dia sem abono lançado = '—' (nunca '00:00')", atual["R4"], repr(_abono(DIA_SEM_ABONO)))
ok("R6 7º período declarado, não cortado em silêncio", atual["R6"], _pontos(DIA_7_SEG))

# R5 — ABONO fecha o saldo (o mecanismo que a Pyetra pediu)
saldo_ab = _saldo_dia(DIA_ABONADO)
saldo_sem = _saldo_dia({k: v for k, v in DIA_ABONADO.items() if k != "abono"})
ok(
    "R5 dia abonado (dia inteiro): ABONO = PREVISTAS e SALDO fecha 00:00",
    _abono(DIA_ABONADO) == "11:00" and saldo_ab == "00:00" and saldo_sem == "-11:00",
    f"abono={_abono(DIA_ABONADO)} saldo_com={saldo_ab} saldo_sem={saldo_sem}",
)

print("\n2) CONTROLE — as mesmas regras contra o comportamento ANTERIOR (2 colunas fixas)")
antes = regras_puras(_pontos_anterior, _abono_anterior)
for r in ("R1", "R2", "R3", "R4", "R6"):
    passou = antes[r]
    print(f"  {'❌' if passou else '✅'} {r} reprova no código anterior"
          f"{'' if not passou else ' — CONTROLE PASSOU: o oráculo não mede nada'}")
    if passou:
        falhas.append(f"controle-{r}")
print(f"     anterior imprimia: {_pontos_anterior(DIA_2_SEG)!r} · abono {_abono_anterior(DIA_SEM_ABONO)!r}")

# ── R7 + R8: contra o banco, sujeito DESCOBERTO ──
print("\n3) Quadro de horários (fail-closed por ambiguidade) e PDF de ponta a ponta")
with get_sync_db() as db:
    from modules.people_management.hr.services.espelho_ponto_pdf import montar_espelho_ponto_pdf
    from modules.people_management.hr.services.espelho_ponto_service import quadro_horarios
    from modules.people_management.ponto.dias_corridos import espelho_do_periodo

    # Janela de 31 dias mais recente em que a escala está publicada (sem data fixa aqui).
    fim = db.execute(text("SELECT max(shift_date) FROM shifts WHERE is_active")).scalar()
    if not fim:
        ok("R7/R8 escala publicada disponível", False, "nenhum shift ativo — oráculo sem sujeito")
    else:
        ini = fim - timedelta(days=30)
        cand = db.execute(
            text(
                "SELECT CAST(employee_id AS TEXT) e, "
                "       count(DISTINCT (planned_start_time, planned_end_time)) n "
                "FROM shifts WHERE is_active AND employee_id IS NOT NULL "
                "  AND shift_date BETWEEN :i AND :f GROUP BY 1"
            ),
            {"i": ini, "f": fim},
        ).mappings().all()
        um = [c["e"] for c in cand if c["n"] == 1]
        vario = [c["e"] for c in cand if c["n"] > 1]
        ok(
            "R7a escala AMBÍGUA (2+ janelas) → o PDF não escolhe: quadro = None",
            bool(vario) and quadro_horarios(db, vario[0], ini, fim) is None,
            f"{len(vario)} pessoas com 2+ janelas em {ini}..{fim}",
        )
        q_um = quadro_horarios(db, um[0], ini, fim) if um else None
        ok(
            "R7b escala ÚNICA → o quadro SAI preenchido (caminho feliz, senão a regra só recusa)",
            bool(q_um) and "às" in q_um,
            f"{len(um)} pessoas com janela única · exemplo: {q_um!r}",
        )

        # R8 — sujeito do PDF: quem tem MAIS dias com 2+ segmentos apurados (o caso que o
        # gerador antigo achatava). Sem isso o PDF provaria só o caminho de 1 par.
        alvo = db.execute(
            text(
                "SELECT CAST(ts.employee_id AS TEXT) e, ts.reference_month m, ts.reference_year y, "
                "       count(*) FILTER (WHERE jsonb_array_length("
                "           coalesce(d->'segmentos','[]'::jsonb)) > 1) multi "
                "FROM time_sheets ts, jsonb_array_elements(ts.daily_summary) d "
                "WHERE coalesce(ts.is_deleted,false) = false "
                "GROUP BY 1,2,3 ORDER BY multi DESC, y DESC, m DESC LIMIT 1"
            )
        ).mappings().first()
        if not alvo or not alvo["multi"]:
            ok("R8 há espelho com 2+ segmentos para imprimir", False, "motor sem segmentos apurados")
        else:
            f2 = date(int(alvo["y"]), int(alvo["m"]), 25)
            i2 = (f2.replace(day=26) - timedelta(days=31)).replace(day=26)
            esp = espelho_do_periodo(db, alvo["e"], i2, f2)
            ok("R8a espelho do período existe para o sujeito descoberto", bool(esp))
            if esp:
                import fitz

                pdf = montar_espelho_ponto_pdf(esp)
                with fitz.open(stream=pdf, filetype="pdf") as doc:
                    txt = "\n".join(p.get_text() for p in doc)
                blocos = [
                    "Pontos (períodos 1 a 6)", "Abono", "Saldo", "Previstas", "CTPS / Série",
                    "Código", "Centro de Custo", "Quadro de Horários", "Dias faltosos",
                    "Horas noturnas", "Horas ficta", "Reconheço a exatidão",
                ]
                faltando = [b for b in blocos if b not in txt]
                ok("R8b todos os blocos do modelo no PDF", not faltando, f"faltando: {faltando}")
                multi = [ln for ln in txt.splitlines() if ln.count("|") >= 2]
                ok(
                    "R8c o papel mostra linha com 2+ períodos (o que a coluna única achatava)",
                    bool(multi),
                    f"{len(multi)} linhas · ex.: {multi[0] if multi else '—'}",
                )
                ok(
                    "R8d ABONO sem fonte sai tracejado no PDF, não zerado",
                    "Abono lançado (dias" in txt and "\n—\n" in txt,
                    "coluna ABONO impressa com dash",
                )

print(f"\n{'❌ FALHAS: ' + ', '.join(falhas) if falhas else '✅ TODAS AS REGRAS VERDES'}")
sys.exit(1 if falhas else 0)
