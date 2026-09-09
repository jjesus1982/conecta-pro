"""PDF da escala mensal de UM funcionário (timbrado padrão-ouro) — 09/09/2026, kit de teste Conecta Village.

Nasceu porque o kit do banco tinha a vaga "Escala MM/AAAA" por funcionário e NENHUM gerador para ela: a vaga
ficava vazia para sempre. Lê os turnos já gerados (shifts) — não inventa horário.
"""
from __future__ import annotations

import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from modules.crm.services import pdf_branding as B

_MESES = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro",
          "Outubro", "Novembro", "Dezembro"]
_DIAS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]


def montar_escala_pdf(funcionario: dict, posto: str, mes: int, ano: int, turnos: list[dict]) -> bytes:
    """turnos: [{"data": date, "inicio": time|None, "fim": time|None, "folga": bool, "noturno": bool, "horas": float}]"""
    comp = f"{ano:04d}-{mes:02d}"
    empresa = B.empresa_branding_por_cpf(funcionario.get("cpf"), comp)
    st = B.styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=40 * mm, bottomMargin=16 * mm, leftMargin=16 * mm, rightMargin=16 * mm)
    W = A4[0] - 32 * mm
    p = st["corpo"]
    story: list = [
        Paragraph(f"<b>ESCALA DE TRABALHO — {_MESES[mes]}/{ano}</b>", p),
        Spacer(1, 3 * mm),
        Paragraph(f"<b>Funcionário:</b> {funcionario.get('nome', '—')} &nbsp;&nbsp; <b>Matrícula:</b> {funcionario.get('matricula') or '—'} "
                  f"&nbsp;&nbsp; <b>Cargo:</b> {funcionario.get('cargo') or '—'}", p),
        Paragraph(f"<b>Posto:</b> {posto} &nbsp;&nbsp; <b>Regime:</b> {funcionario.get('escala') or '—'}", p),
        Spacer(1, 4 * mm),
    ]
    linhas = [["Data", "Dia", "Entrada", "Saída", "Horas", "Observação"]]
    total_h = 0.0
    for t in sorted(turnos, key=lambda x: x["data"]):
        d: date = t["data"]
        if t.get("folga"):
            linhas.append([d.strftime("%d/%m"), _DIAS[d.weekday()], "—", "—", "", "Folga"])
            continue
        h = float(t.get("horas") or 0)
        total_h += h
        obs = "Noturno" if t.get("noturno") else ""
        linhas.append([d.strftime("%d/%m"), _DIAS[d.weekday()],
                       t["inicio"].strftime("%H:%M") if t.get("inicio") else "—",
                       t["fim"].strftime("%H:%M") if t.get("fim") else "—",
                       f"{h:.0f}h" if h else "", obs])
    linhas.append(["", "", "", "Total", f"{total_h:.0f}h", f"{sum(1 for t in turnos if not t.get('folga'))} turno(s)"])
    tb = Table(linhas, colWidths=[W * 0.12, W * 0.10, W * 0.15, W * 0.15, W * 0.12, W * 0.36], repeatRows=1)
    tb.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF5")), ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("ALIGN", (2, 1), (4, -1), "CENTER"), ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F7F9FB")]),
    ]))
    story.append(tb)
    story.append(Spacer(1, 8 * mm))
    story += B.campos_assinatura(st, funcionario_nome=funcionario.get("nome"), funcionario_cpf=funcionario.get("cpf"),
                                 responsavel_cargo="Supervisão operacional", empresa=empresa)
    hf = lambda cv, dc: B.header_footer(cv, dc, titulo="ESCALA DE TRABALHO", empresa=empresa)  # noqa: E731
    doc.build(story, onFirstPage=hf, onLaterPages=hf)
    return buf.getvalue()


if __name__ == "__main__":  # checagem mínima: gera um PDF com 3 turnos e uma folga
    from datetime import time
    pdf = montar_escala_pdf({"nome": "TESTE", "cpf": None}, "Portaria", 8, 2026, [
        {"data": date(2026, 8, 1), "inicio": time(7), "fim": time(19), "horas": 12},
        {"data": date(2026, 8, 2), "folga": True},
        {"data": date(2026, 8, 3), "inicio": time(19), "fim": time(7), "horas": 12, "noturno": True},
    ])
    assert pdf.startswith(b"%PDF-") and len(pdf) > 1000
    print("ok", len(pdf))
