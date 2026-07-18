"""Gerador genérico de relatório financeiro em PDF (marca Conecta).

Serve DRE, Balancete, Fluxo de Caixa e afins — recebe seções de (rótulo, valor) já
calculadas pelo endpoint JSON e renderiza uma folha branded. Não recalcula nada.
"""
from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from modules.crm.services import pdf_branding as B

_AZUL = B.AZUL_ESCURO
_LARANJA = B.LARANJA
_CINZA = B.TEXTO
_CLARO = B.FUNDO_CLARO


def _money(v) -> str:
    try:
        return f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:  # noqa: BLE001
        return str(v)


def gerar_relatorio_pdf(titulo: str, subtitulo: str, secoes: list[dict]) -> bytes:
    """secoes = [{'titulo': str, 'linhas': [(rotulo, valor, destaque_bool?)]}].
    valor numérico é formatado como R$; string é impressa como veio."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    x0, x1 = 18 * mm, W - 18 * mm
    TIT = titulo.upper()

    def cabecalho() -> float:
        yy = B.marca_canvas(c, titulo=TIT)
        c.setFillColor(_AZUL)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(x0, yy, subtitulo[:95])
        return yy - 10 * mm

    y = cabecalho()

    def linha(rot, val, destaque=False):
        nonlocal y
        if y < 34 * mm:
            B.rodape_canvas(c, pagina=1)
            c.showPage()
            y = cabecalho()
        c.setFillColor(_AZUL if destaque else colors.black)
        c.setFont("Helvetica-Bold" if destaque else "Helvetica", 10 if destaque else 9)
        c.drawString(x0 + 2 * mm, y, str(rot)[:72])
        val_s = _money(val) if isinstance(val, (int, float)) else str(val)
        c.drawRightString(x1 - 2 * mm, y, val_s)
        y -= 5.6 * mm

    for sec in secoes:
        y -= 2 * mm
        c.setFillColor(_LARANJA)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x0, y, str(sec.get("titulo", "")).upper())
        y -= 2.5 * mm
        c.setStrokeColor(_CLARO)
        c.setLineWidth(0.6)
        c.line(x0, y, x1, y)
        y -= 5 * mm
        for item in sec.get("linhas", []):
            rot, val = item[0], item[1]
            destaque = bool(item[2]) if len(item) > 2 else False
            linha(rot, val, destaque)

    B.rodape_canvas(c, pagina=1)
    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()
