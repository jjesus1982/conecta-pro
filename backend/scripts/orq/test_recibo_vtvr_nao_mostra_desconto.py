"""Oráculo — o recibo de VT/VR mostra o CONCEDIDO, nunca o desconto nem o líquido (28/09/2026).

Por que existe: a co-participação do VT/VR já é descontada no CONTRACHEQUE. O recibo também
trazia as colunas «Co-part.» e «Líquido» e o rodapé laranja «Total líquido recebido em
benefícios». Quem confere lia a mesma dedução em dois documentos e concluía que descontaram em
dobro. Medido no modelo do print da Pyetra: R$ 16,70 (VR) + R$ 66,80 (VT) = R$ 83,50 repetidos,
e o rodapé fechava R$ 660,50 em vez dos R$ 744,00 efetivamente concedidos.

A regra afirmada (não a fotografia): gerando o PDF de verdade e LENDO o texto de volta,

  1. nenhum rótulo de desconto/líquido aparece: «Co-part.», «Líquido», «Total líquido recebido»;
  2. nenhum VALOR de desconto ou de líquido vaza, mesmo que o holerite traga desconto_vr /
     desconto_vt preenchidos — o recibo recebe os números e escolhe não imprimi-los;
  3. o que a Pyetra pediu continua lá: Valor unit., Qtd e Total, com os números certos;
  4. «Total» É o total da linha (unitário × qtd) — se um dia virarem valores diferentes,
     isto quebra e alguém decide de novo se cabe uma coluna «Total» separada.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho.
"""

from __future__ import annotations

import sys

# `python /app/scripts/orq/este.py` põe /app/scripts/orq no sys.path, NÃO /app: a varredura das
# 05:00 (tasks_oraculos.varrer) injeta PYTHONPATH=/app e passa, mas rodado à mão sem -e PYTHONPATH
# o import estourava `ModuleNotFoundError: No module named 'modules'` — vermelho que não é defeito
# do recibo. Os dois oráculos irmãos desta onda já traziam esta linha; este ficou sem.
sys.path.insert(0, "/app")

# números do print da Pyetra (28/09/2026) — desconto e líquido entram de propósito
HOLERITE = {
    "mes": 8,
    "ano": 2026,
    "employee_nome": "ORACULO VTVR",
    "cargo": "Agente de Portaria",
    "vr_dia": 22.0,
    "dias_vr": 22,
    "vr_concedido": 484.0,
    "desconto_vr": 16.70,
    "vt_dia": 10.0,
    "dias_vt": 26,
    "vt_concedido": 260.0,
    "desconto_vt": 66.80,
}
PROIBIDO_ROTULO = ("Co-part", "Líquido", "Total líquido recebido")
PROIBIDO_VALOR = ("16,70", "66,80", "467,30", "193,20", "660,50", "83,50")
OBRIGATORIO = ("Valor unit.", "Qtd", "Total", "22,00", "22", "484,00", "10,00", "26", "260,00")


def main() -> int:
    import pymupdf

    from modules.people_management.folha.services.recibo_vt_vr_pdf import montar_recibo_vt_vr_pdf

    falhas: list[str] = []

    pdf = montar_recibo_vt_vr_pdf(dict(HOLERITE), {"cpf": "01613230222", "posto": "Posto Oráculo"})
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    txt = "\n".join(p.get_text() for p in doc)

    for w in PROIBIDO_ROTULO:
        if w in txt:
            falhas.append(f"rótulo de desconto/líquido voltou ao recibo: {w!r} (já está no contracheque)")
    for v in PROIBIDO_VALOR:
        if v in txt:
            falhas.append(f"valor de co-participação/líquido vazou no recibo: {v!r}")
    for w in OBRIGATORIO:
        if w not in txt:
            falhas.append(f"o recibo perdeu o que a Pyetra pediu para manter: {w!r}")

    # 4) «Total» é o total da linha — unitário × qtd. O rótulo era «Concedido» até o
    #    Jordan confirmar em 28/09 que a Pyetra usa a palavra «Total».
    esperado = HOLERITE["vr_dia"] * HOLERITE["dias_vr"]
    if abs(esperado - HOLERITE["vr_concedido"]) > 0.005:
        falhas.append(
            f"«Concedido» deixou de ser unitário × qtd ({HOLERITE['vr_dia']} × {HOLERITE['dias_vr']} "
            f"= {esperado:.2f} ≠ {HOLERITE['vr_concedido']:.2f}) — reavaliar se cabe coluna «Total» separada"
        )

    if falhas:
        print("VERMELHO — recibo VT/VR:")
        for f in falhas:
            print(f"  · {f}")
        return 1
    print("VERDE — recibo VT/VR mostra unitário/qtd/concedido e nenhum desconto ou líquido.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
