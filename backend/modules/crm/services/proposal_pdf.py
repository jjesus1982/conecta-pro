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

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
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

# Marca Conecta Mais centralizada (fonte única de verdade p/ logos, cores, header/footer).
from modules.crm.services import pdf_branding as B

# ---- Design tokens oficiais (delegados ao módulo de marca) ----
AZUL_ESCURO = B.AZUL_ESCURO
AZUL_MEDIO = B.AZUL_MEDIO
LARANJA = B.LARANJA
TEXTO = B.TEXTO
FUNDO_CLARO = B.FUNDO_CLARO
FONTE = B.FONTE
FONTE_B = B.FONTE_B

# Marca (nome, CNPJ, CEO, contatos) vem TODA de B.EMPRESA — sem strings hardcoded antigas.
EMPRESA = B.EMPRESA
_MESES = B.MESES


def _logo_path(kind: str = "cover") -> str | None:
    """Resolve o logo por uso — delega ao módulo de marca Conecta Mais."""
    return B.logo_path(kind)


def _brl(v) -> str:
    return B.brl(v)


def _data_extenso(d) -> str:
    return B.data_extenso(d)


def _mes_ano(d) -> str:
    try:
        return f"{_MESES[d.month].capitalize()}/{d.year}"
    except Exception:  # noqa: BLE001
        return ""


# ---------------------------------------------------------------- header/footer
def _header_footer(canvas, doc):
    """Header + footer oficiais Conecta Mais nas páginas internas (delega à marca).
    A proposta tem CAPA comercial própria na pág. 1 → pular_primeira=True."""
    B.header_footer(canvas, doc, seal_watermark=False, pular_primeira=True)


# ---------------------------------------------------------------- estilos
def _styles():
    """Estilos oficiais da marca (B.styles) + o extra 'capa_resumo' (destaque laranja centralizado)
    usado só na capa da proposta. Sem duplicar a paleta — tudo delega ao módulo de marca."""
    st = B.styles()
    st["capa_resumo"] = st["destaque"]
    return st


def _secao(titulo: str, st) -> list:
    return B.secao(titulo, st)


# ---------------------------------------------------------------- documento
def build_proposal_pdf(p) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=40 * mm,
        bottomMargin=16 * mm,
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
            f"É com grande satisfação que a <b>{EMPRESA['nome']}</b> apresenta esta "
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
    el.append(Paragraph(f"{EMPRESA['email']}  |  {EMPRESA['fone']}", st["small"]))
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

    # ---------------- Aceite (assinaturas) ----------------
    # O CLIENTE aceita/assina (manual ou pelo motor de assinatura do Conecta PRO) e a EMPRESA
    # assina digitalmente (CEO). Âncoras ASSINAR::FUNCIONARIO / ASSINAR::EMPRESA preservadas.
    el.append(Spacer(1, 6 * mm))
    el += _secao("Aceite da Proposta", st)
    el.append(
        Paragraph(
            "Manifestando concordância com os termos, valores e condições acima, as partes firmam o presente "
            "aceite, que servirá de base para a formalização do respectivo contrato de prestação de serviços.",
            st["corpo"],
        )
    )
    cliente_ident = f"CNPJ/CPF {doc_cli}" if doc_cli else None
    el += B.campos_assinatura(
        st,
        funcionario_nome=cliente,
        funcionario_cpf=cliente_ident,
        funcionario_label="Assinatura do Cliente",
        funcionario_doc_rotulo="CNPJ/CPF",
        digital_funcionario=False,
        digital_empresa=True,
        data_str=B.br_date(emitido),
        espaco_antes=6,
    )

    doc.build(el, onFirstPage=_header_footer, onLaterPages=_header_footer)
    return buf.getvalue()
