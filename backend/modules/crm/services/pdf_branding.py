"""
Identidade visual Conecta Mais para PDFs (proposta, contrato, relatório).
Centraliza cores, fontes, logos, selo, header/footer e helpers — para todos os documentos saírem
no MESMO padrão. Assets vêm do volume persistente /app/uploads/assets (trocáveis sem rebuild).
"""

from __future__ import annotations

import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Table, TableStyle

AZUL_ESCURO = colors.HexColor("#1E3A5F")
AZUL_MEDIO = colors.HexColor("#2D5F8B")
LARANJA = colors.HexColor("#F97316")
TEXTO = colors.HexColor("#1F2937")
FUNDO_CLARO = colors.HexColor("#F8FAFC")
FONTE = "Helvetica"
FONTE_B = "Helvetica-Bold"

EMPRESA = {
    "nome": "CONECTA MAIS - SEGURANÇA E TECNOLOGIA",
    "razao": "Jordan Santos de Jesus Ltda",
    "cnpj": "35.710.481/0001-03",
    "fone": "0800 880 4414",
    "site": "www.conectamaistech.com.br",
    "endereco": "Manaus/AM",
    "ceo": "Jordan Santos de Jesus",
    "ceo_cargo": "Diretor Executivo (CEO)",
}
MESES = [
    "",
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
]

_ASSETS = "/app/uploads/assets"
_CM = f"{_ASSETS}/conecta-mais"


def logo_path(kind: str = "cover") -> str | None:
    """cover=empilhada | header=horizontal | seal=selo circular. Volume persistente primeiro;
    ignora arquivo ilegível (os.access) p/ nunca quebrar a geração."""
    if kind == "header":
        cands = (
            os.getenv("PDF_LOGO_HEADER", ""),
            f"{_ASSETS}/pdf/header.png",
            f"{_CM}/sublogo-sem-fundo.2.png",
            f"{_CM}/conecta-mais.png",
            f"{_ASSETS}/logo-conecta-mais.png",
            "/app/assets/logo.png",
        )
    elif kind == "seal":
        cands = (
            os.getenv("PDF_LOGO_SELO", ""),
            f"{_ASSETS}/pdf/seal.png",
            f"{_CM}/lototipo-conecta.png",
            f"{_CM}/conecta-mais.png",
        )
    else:
        cands = (
            os.getenv("PDF_EMPRESA_LOGO", ""),
            f"{_ASSETS}/pdf/cover.png",
            f"{_ASSETS}/logo-conecta-mais.png",
            f"{_CM}/conecta-mais.png",
            "/app/assets/logo.png",
        )
    for c in cands:
        if c and os.path.exists(c) and os.access(c, os.R_OK):
            return c
    return None


def brl(v) -> str:
    s = f"{float(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def data_extenso(d) -> str:
    try:
        return f"Manaus/AM, {d.day} de {MESES[d.month]} de {d.year}"
    except Exception:  # noqa: BLE001
        return "Manaus/AM"


def br_date(d) -> str:
    try:
        return d.strftime("%d/%m/%Y") if d else "—"
    except Exception:  # noqa: BLE001
        return "—"


def header_footer(canvas, doc, *, seal_watermark: bool = False):
    """Header (logo horizontal) + footer (dados oficiais + página) nas páginas internas (não na capa).
    seal_watermark=True desenha o selo claro ao centro (contratos/relatórios)."""
    if doc.page == 1:
        return
    canvas.saveState()
    w, h = A4
    if seal_watermark:
        sp = logo_path("seal")
        if sp:
            try:
                canvas.saveState()
                canvas.setFillAlpha(0.05)
                canvas.drawImage(
                    sp,
                    w / 2 - 55 * mm,
                    h / 2 - 55 * mm,
                    width=110 * mm,
                    height=110 * mm,
                    preserveAspectRatio=True,
                    mask="auto",
                )
                canvas.restoreState()
            except Exception:  # noqa: BLE001
                pass
    lp = logo_path("header")
    drew = False
    if lp:
        try:
            canvas.drawImage(
                lp,
                16 * mm,
                h - 20.5 * mm,
                width=52 * mm,
                height=11 * mm,
                preserveAspectRatio=True,
                anchor="sw",
                mask="auto",
            )
            drew = True
        except Exception:  # noqa: BLE001
            pass
    if not drew:
        canvas.setFont(FONTE_B, 7)
        canvas.setFillColor(AZUL_ESCURO)
        canvas.drawString(16 * mm, h - 16 * mm, EMPRESA["nome"])
    canvas.setStrokeColor(AZUL_ESCURO)
    canvas.setLineWidth(0.8)
    canvas.line(16 * mm, h - 22 * mm, w - 16 * mm, h - 22 * mm)
    canvas.line(16 * mm, 16 * mm, w - 16 * mm, 16 * mm)
    canvas.setFont(FONTE, 6.5)
    canvas.setFillColor(AZUL_MEDIO)
    canvas.drawString(
        16 * mm, 12 * mm, f"{EMPRESA['nome']} | CNPJ: {EMPRESA['cnpj']} | {EMPRESA['fone']} | {EMPRESA['site']}"
    )
    canvas.drawRightString(w - 16 * mm, 12 * mm, f"Página {doc.page}")
    canvas.restoreState()


def styles() -> dict:
    ss = getSampleStyleSheet()
    return {
        "capa_titulo": ParagraphStyle(
            "ct",
            parent=ss["Normal"],
            fontName=FONTE_B,
            fontSize=32,
            leading=38,
            textColor=AZUL_ESCURO,
            alignment=TA_CENTER,
        ),
        "capa_sub": ParagraphStyle(
            "cs",
            parent=ss["Normal"],
            fontName=FONTE,
            fontSize=14,
            leading=19,
            textColor=AZUL_MEDIO,
            alignment=TA_CENTER,
        ),
        "capa_meta": ParagraphStyle(
            "cm", parent=ss["Normal"], fontName=FONTE, fontSize=10, leading=14, textColor=TEXTO, alignment=TA_CENTER
        ),
        "destaque": ParagraphStyle(
            "dq", parent=ss["Normal"], fontName=FONTE_B, fontSize=11, leading=15, textColor=LARANJA, alignment=TA_CENTER
        ),
        "h_sec": ParagraphStyle(
            "hs", parent=ss["Normal"], fontName=FONTE_B, fontSize=13, leading=17, textColor=AZUL_ESCURO, spaceAfter=3
        ),
        "corpo": ParagraphStyle(
            "co",
            parent=ss["Normal"],
            fontName=FONTE,
            fontSize=9.5,
            leading=14,
            textColor=TEXTO,
            alignment=TA_JUSTIFY,
            spaceAfter=5,
        ),
        "cell": ParagraphStyle("ce", parent=ss["Normal"], fontName=FONTE, fontSize=8.5, leading=11, textColor=TEXTO),
        "cellr": ParagraphStyle(
            "cer", parent=ss["Normal"], fontName=FONTE, fontSize=8.5, leading=11, textColor=TEXTO, alignment=TA_RIGHT
        ),
        "cellh": ParagraphStyle(
            "ch", parent=ss["Normal"], fontName=FONTE_B, fontSize=8.5, leading=11, textColor=colors.white
        ),
        "assina": ParagraphStyle(
            "as", parent=ss["Normal"], fontName=FONTE_B, fontSize=10, leading=14, textColor=AZUL_ESCURO
        ),
        "small": ParagraphStyle(
            "sm", parent=ss["Normal"], fontName=FONTE, fontSize=8.5, leading=12, textColor=AZUL_MEDIO
        ),
    }


def secao(titulo: str, st: dict) -> list:
    from reportlab.platypus import Spacer

    return [
        Paragraph(titulo, st["h_sec"]),
        Table([[""]], colWidths=[178 * mm], style=TableStyle([("LINEBELOW", (0, 0), (-1, -1), 1.5, LARANJA)])),
        Spacer(1, 3.5 * mm),
    ]
