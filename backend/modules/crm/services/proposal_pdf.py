"""
Gerador de PDF de proposta no PADRÃO VISUAL OFICIAL Conecta Mais (ReportLab).

Estrutura (espelha o template canônico da skill conecta-mais-templates):
  1) Capa — logo, linha laranja, "PROPOSTA COMERCIAL", cliente, nº + mês/ano, confidencial
  2) Carta de Apresentação — institucional + assinatura CEO
  3) Escopo + Investimento — tabela de itens + financeiro (bruto → retenções 2,5% → líquido → anual)
  4) Condições Gerais + Diferenciais

Design tokens (NÃO alterar): #1E3A5F títulos | #2D5F8B subtítulos/bordas | #F97316 destaques |
#1F2937 texto | #F8FAFC fundo claro. Fonte Arial (Helvetica no ReportLab). A4.
Header/footer oficiais em todas as páginas internas (a capa não tem).
"""

from __future__ import annotations

import io
import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ---- Design tokens oficiais ----
AZUL_ESCURO = colors.HexColor("#1E3A5F")
AZUL_MEDIO = colors.HexColor("#2D5F8B")
LARANJA = colors.HexColor("#F97316")
TEXTO = colors.HexColor("#1F2937")
FUNDO_CLARO = colors.HexColor("#F8FAFC")
FONTE = "Helvetica"
FONTE_B = "Helvetica-Bold"

EMPRESA = {
    "nome": "CONECTA MAIS - SEGURANÇA E TECNOLOGIA",
    "cnpj": "35.710.481/0001-03",
    "fone": "0800 880 4414",
    "site": "www.conectamaistech.com.br",
    "ceo": "Jordan Santos de Jesus",
    "ceo_cargo": "Diretor Executivo (CEO)",
    "ceo_contato": "jjesus@conectamais.pro | (92) 98646-5328",
}
_MESES = [
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


def _logo_path(kind: str = "cover") -> str | None:
    """Resolve o logo por uso (cover = empilhada / header = horizontal). Volume PERSISTENTE primeiro
    (troca sem rebuild). Ignora arquivo ILEGÍVEL (os.access) p/ um upload com permissão errada NUNCA
    quebrar a geração — cai no próximo candidato / logo do ERP."""
    if kind == "header":
        cands = (
            os.getenv("PDF_LOGO_HEADER", ""),
            f"{_ASSETS}/pdf/header.png",
            f"{_CM}/sublogo-sem-fundo.2.png",
            f"{_CM}/conecta-mais.png",
            f"{_ASSETS}/logo-conecta-mais.png",
            "/app/assets/logo.png",
        )
    else:  # cover
        cands = (
            os.getenv("PDF_EMPRESA_LOGO", ""),
            f"{_ASSETS}/pdf/cover.png",
            f"{_ASSETS}/logo-conecta-mais.png",
            f"{_CM}/conecta-mais.png",
            "/app/assets/logo.png",
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "assets", "logo.png"),
        )
    for c in cands:
        if c and os.path.exists(c) and os.access(c, os.R_OK):
            return c
    return None


def _brl(v) -> str:
    s = f"{float(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def _data_extenso(d) -> str:
    try:
        return f"Manaus/AM, {d.day} de {_MESES[d.month]} de {d.year}"
    except Exception:  # noqa: BLE001
        return "Manaus/AM"


def _mes_ano(d) -> str:
    try:
        return f"{_MESES[d.month].capitalize()}/{d.year}"
    except Exception:  # noqa: BLE001
        return ""


# ---------------------------------------------------------------- header/footer
def _header_footer(canvas, doc):
    """Desenha header + footer oficiais nas páginas internas (não na capa)."""
    if doc.page == 1:
        return
    canvas.saveState()
    w, h = A4
    # Header: logo HORIZONTAL (já contém o nome) + borda inferior azul
    lp = _logo_path("header")
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
    if not drew:  # fallback: sem logo legível -> escreve o nome (nunca header vazio)
        canvas.setFont(FONTE_B, 7)
        canvas.setFillColor(AZUL_ESCURO)
        canvas.drawString(16 * mm, h - 16 * mm, EMPRESA["nome"])
    canvas.setStrokeColor(AZUL_ESCURO)
    canvas.setLineWidth(0.8)
    canvas.line(16 * mm, h - 22 * mm, w - 16 * mm, h - 22 * mm)
    # Footer: dados oficiais + página, borda superior azul
    canvas.line(16 * mm, 16 * mm, w - 16 * mm, 16 * mm)
    canvas.setFont(FONTE, 6.5)
    canvas.setFillColor(AZUL_MEDIO)
    canvas.drawString(
        16 * mm, 12 * mm, f"{EMPRESA['nome']} | CNPJ: {EMPRESA['cnpj']} | {EMPRESA['fone']} | {EMPRESA['site']}"
    )
    canvas.drawRightString(w - 16 * mm, 12 * mm, f"Página {doc.page}")
    canvas.restoreState()


# ---------------------------------------------------------------- estilos
def _styles():
    ss = getSampleStyleSheet()
    return {
        "capa_titulo": ParagraphStyle(
            "ct",
            parent=ss["Normal"],
            fontName=FONTE_B,
            fontSize=34,
            leading=40,
            textColor=AZUL_ESCURO,
            alignment=TA_CENTER,
        ),
        "capa_sub": ParagraphStyle(
            "cs",
            parent=ss["Normal"],
            fontName=FONTE,
            fontSize=15,
            leading=20,
            textColor=AZUL_MEDIO,
            alignment=TA_CENTER,
        ),
        "capa_resumo": ParagraphStyle(
            "cr", parent=ss["Normal"], fontName=FONTE_B, fontSize=11, leading=15, textColor=LARANJA, alignment=TA_CENTER
        ),
        "capa_meta": ParagraphStyle(
            "cm", parent=ss["Normal"], fontName=FONTE, fontSize=10, leading=14, textColor=TEXTO, alignment=TA_CENTER
        ),
        "h_sec": ParagraphStyle(
            "hs", parent=ss["Normal"], fontName=FONTE_B, fontSize=15, leading=19, textColor=AZUL_ESCURO, spaceAfter=4
        ),
        "corpo": ParagraphStyle(
            "co",
            parent=ss["Normal"],
            fontName=FONTE,
            fontSize=10,
            leading=15,
            textColor=TEXTO,
            alignment=TA_JUSTIFY,
            spaceAfter=6,
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


def _secao(titulo: str, st) -> list:
    return [
        Paragraph(titulo, st["h_sec"]),
        Table([[""]], colWidths=[178 * mm], style=TableStyle([("LINEBELOW", (0, 0), (-1, -1), 1.5, LARANJA)])),
        Spacer(1, 4 * mm),
    ]


# ---------------------------------------------------------------- documento
def build_proposal_pdf(p) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=26 * mm,
        bottomMargin=20 * mm,
        title=f"Proposta {getattr(p, 'number', '')}",
    )
    st = _styles()
    el: list = []

    numero = getattr(p, "number", "—")
    cliente = getattr(p, "client_name", "") or "Cliente"
    doc_cli = getattr(p, "client_document", "") or ""
    endereco = getattr(p, "client_address", "") or ""
    titulo_serv = getattr(p, "title", "") or "Serviços de Segurança Patrimonial"
    emitido = getattr(p, "issue_date", None) or getattr(p, "created_at", None)
    total = float(getattr(p, "total", 0) or 0)

    # ---------------- 1) CAPA ----------------
    lp = _logo_path("cover")
    el.append(Spacer(1, 22 * mm))
    if lp:
        try:
            img = Image(lp, width=58 * mm, height=40 * mm, kind="proportional")
            img.hAlign = "CENTER"
            el.append(img)
        except Exception:  # noqa: BLE001
            pass
    el.append(Spacer(1, 8 * mm))
    el.append(
        Table(
            [[""]],
            colWidths=[60 * mm],
            hAlign="CENTER",
            style=TableStyle([("LINEBELOW", (0, 0), (-1, -1), 2.5, LARANJA)]),
        )
    )
    el.append(Spacer(1, 10 * mm))
    el.append(Paragraph("PROPOSTA COMERCIAL", st["capa_titulo"]))
    el.append(Spacer(1, 3 * mm))
    el.append(Paragraph(titulo_serv, st["capa_sub"]))
    el.append(Spacer(1, 14 * mm))
    # bloco cliente
    cli_rows = [[Paragraph(f"<b>CLIENTE:</b> {cliente}", st["capa_meta"])]]
    if doc_cli:
        cli_rows.append([Paragraph(f"CNPJ/CPF: {doc_cli}", st["capa_meta"])])
    if endereco:
        cli_rows.append([Paragraph(endereco, st["capa_meta"])])
    box = Table(cli_rows, colWidths=[150 * mm], hAlign="CENTER")
    box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), FUNDO_CLARO),
                ("BOX", (0, 0), (-1, -1), 0.8, AZUL_MEDIO),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    el.append(box)
    el.append(Spacer(1, 12 * mm))
    el.append(Paragraph(f"Proposta <b>{numero}</b>", st["capa_meta"]))
    el.append(Paragraph(_mes_ano(emitido), st["capa_meta"]))
    el.append(Spacer(1, 16 * mm))
    el.append(Paragraph("— CONFIDENCIAL —", st["capa_resumo"]))
    el.append(PageBreak())

    # ---------------- 2) CARTA DE APRESENTAÇÃO ----------------
    el += _secao("Carta de Apresentação", st)
    el.append(Paragraph(_data_extenso(emitido), st["corpo"]))
    el.append(Paragraph(f"<b>À {cliente}</b>", st["corpo"]))
    el.append(Paragraph("Prezados Senhores,", st["corpo"]))
    el.append(
        Paragraph(
            "É com grande satisfação que a <b>Conecta Mais — Segurança e Tecnologia</b> apresenta esta "
            "proposta comercial. Somos uma empresa especializada em segurança patrimonial, com soluções "
            "humanizadas e tecnológicas (vigilância, portaria remota e presencial, controle de acesso, "
            "CFTV e monitoramento 24 horas), comprometida com a proteção do seu patrimônio e a "
            "tranquilidade de quem você cuida.",
            st["corpo"],
        )
    )
    el.append(
        Paragraph(
            "Nossa atuação combina equipe treinada, processos auditáveis e tecnologia própria de gestão "
            "(ERP Conecta PRO), garantindo transparência, agilidade no atendimento e qualidade contínua "
            "no serviço prestado.",
            st["corpo"],
        )
    )
    el.append(
        Paragraph(
            "Colocamo-nos à disposição para detalhar qualquer ponto desta proposta e seguimos honrados "
            "com a oportunidade de atendê-los.",
            st["corpo"],
        )
    )
    el.append(Spacer(1, 10 * mm))
    el.append(Paragraph("Atenciosamente,", st["corpo"]))
    el.append(Spacer(1, 6 * mm))
    el.append(Paragraph(EMPRESA["ceo"], st["assina"]))
    el.append(Paragraph(EMPRESA["ceo_cargo"], st["small"]))
    el.append(Paragraph(EMPRESA["ceo_contato"], st["small"]))
    el.append(PageBreak())

    # ---------------- 3) ESCOPO + INVESTIMENTO ----------------
    el += _secao("Escopo e Investimento", st)
    if getattr(p, "description", None):
        el.append(Paragraph(p.description, st["corpo"]))
        el.append(Spacer(1, 2 * mm))

    head = ["Item", "Descrição", "Qtd", "Un", "Valor Unit.", "Total"]
    rows = [[Paragraph(h, st["cellh"]) for h in head]]
    itens = sorted(getattr(p, "items", []) or [], key=lambda i: getattr(i, "sort_order", 0))
    for idx, it in enumerate(itens, 1):
        qtd = float(getattr(it, "quantity", 0) or 0)
        qtd_s = str(int(qtd)) if qtd.is_integer() else f"{qtd:g}"
        rows.append(
            [
                Paragraph(str(idx), st["cell"]),
                Paragraph(
                    (getattr(it, "name", "") or "")
                    + (f" — {it.description}" if getattr(it, "description", None) else ""),
                    st["cell"],
                ),
                Paragraph(qtd_s, st["cellr"]),
                Paragraph(getattr(it, "unit", "un") or "un", st["cell"]),
                Paragraph(_brl(getattr(it, "unit_price", 0)), st["cellr"]),
                Paragraph(_brl(getattr(it, "total", 0)), st["cellr"]),
            ]
        )
    tbl = Table(rows, colWidths=[12 * mm, 84 * mm, 14 * mm, 12 * mm, 28 * mm, 28 * mm], repeatRows=1)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), AZUL_ESCURO),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, FUNDO_CLARO]),
                ("GRID", (0, 0), (-1, -1), 0.4, AZUL_MEDIO),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    el.append(tbl)
    el.append(Spacer(1, 6 * mm))

    # Resumo financeiro: bruto -> retenções 2,5% -> líquido -> anual (x12)
    retencoes = round(total * 0.025, 2)
    liquido = round(total - retencoes, 2)
    anual = round(total * 12, 2)
    fin_rows = [
        ["Valor mensal (bruto)", _brl(total)],
        ["(-) Retenções (2,5% — IRRF 1,5% + PIS/COFINS/CSLL 1%)", "- " + _brl(retencoes)],
        ["(=) Valor líquido mensal", _brl(liquido)],
        ["Estimativa anual (12x)", _brl(anual)],
    ]
    fin = Table([[a, b] for a, b in fin_rows], colWidths=[130 * mm, 48 * mm])
    fin.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), FONTE),
                ("FONTNAME", (1, 0), (1, -1), FONTE_B),
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("TEXTCOLOR", (0, 0), (-1, -1), TEXTO),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BACKGROUND", (0, 0), (-1, 0), FUNDO_CLARO),
                ("LINEABOVE", (0, 2), (-1, 2), 0.8, AZUL_MEDIO),
                ("BACKGROUND", (0, 2), (-1, 2), FUNDO_CLARO),
                ("BACKGROUND", (0, 3), (-1, 3), AZUL_ESCURO),
                ("TEXTCOLOR", (0, 3), (-1, 3), colors.white),
                ("FONTNAME", (0, 3), (-1, 3), FONTE_B),
                ("FONTSIZE", (0, 2), (-1, 3), 10.5),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E5E7EB")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    el.append(fin)
    el.append(PageBreak())

    # ---------------- 4) CONDIÇÕES GERAIS + DIFERENCIAIS ----------------
    el += _secao("Condições Gerais", st)
    cond = getattr(p, "payment_terms", None)
    parc = getattr(p, "installments", 1) or 1
    validade = getattr(p, "valid_until", None)
    cond_txt = cond or "A combinar com o cliente."
    if parc and parc > 1:
        cond_txt += f"  •  Parcelamento: {parc}x."
    el.append(Paragraph(f"<b>Pagamento:</b> {cond_txt}", st["corpo"]))
    if validade:
        try:
            el.append(Paragraph(f"<b>Validade da proposta:</b> {validade.strftime('%d/%m/%Y')}.", st["corpo"]))
        except Exception:  # noqa: BLE001
            pass
    el.append(
        Paragraph(
            "<b>Reajuste:</b> anual, pelo índice acordado em contrato.  "
            "<b>Vigência:</b> conforme contrato de prestação de serviços.  "
            "<b>Tributos:</b> conforme legislação vigente.",
            st["corpo"],
        )
    )
    if getattr(p, "notes", None):
        el.append(Spacer(1, 2 * mm))
        el.append(Paragraph(f"<b>Observações:</b> {p.notes}", st["corpo"]))

    el.append(Spacer(1, 6 * mm))
    el += _secao("Por que a Conecta Mais", st)
    for dif in (
        "Equipe própria, treinada e uniformizada, com supervisão ativa.",
        "Tecnologia proprietária de gestão (ERP Conecta PRO) — transparência e rastreabilidade.",
        "Atendimento 0800 880 4414 e central de monitoramento 24 horas.",
        "Conformidade fiscal e trabalhista; processos auditáveis.",
        "Soluções integradas: segurança humana + eletrônica (CFTV, controle de acesso, alarme).",
    ):
        el.append(Paragraph(f"•  {dif}", st["corpo"]))

    doc.build(el, onFirstPage=_header_footer, onLaterPages=_header_footer)
    return buf.getvalue()
