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
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

AZUL_ESCURO = colors.HexColor("#1E3A5F")
AZUL_MEDIO = colors.HexColor("#2D5F8B")
LARANJA = colors.HexColor("#F97316")
TEXTO = colors.HexColor("#1F2937")
FUNDO_CLARO = colors.HexColor("#F8FAFC")
FONTE = "Helvetica"
FONTE_B = "Helvetica-Bold"

EMPRESA = {
    "nome": "CONECTA MAIS ELETRÔNICA",
    "razao": "CONECTAMAIS ELETRONICA LTDA",
    "cnpj": "35.710.481/0001-03",
    "fone": "0800 880 4414",
    "site": "www.conectamais.pro",
    "email": "jjesus@conectamais.pro",
    "instagram": "@conectamaisoficial",
    "endereco": "Manaus/AM",
    "ceo": "JORDAN JESUS",
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


_LOGO_CHEIA = "/app/uploads/assets/conecta-mais/conecta-mais.png"


def _desenha_logo_cheia(canvas, x, y, largura=44 * mm, altura=24 * mm) -> bool:
    """Desenha a logo COMPLETA Conecta Mais (ícone + wordmark + tagline) sobre fundo claro."""
    for lp in (_LOGO_CHEIA, logo_path("cover"), logo_path("header")):
        if not lp:
            continue
        try:
            canvas.drawImage(
                lp,
                x,
                y,
                width=largura,
                height=altura,
                preserveAspectRatio=True,
                anchor="nw",
                mask="auto",
            )
            return True
        except Exception:  # noqa: BLE001
            continue
    return False


def _desenha_mini_icone(canvas, kind: str, x: float, y: float, s: float, cor) -> None:
    """Desenha um ícone vetorial minúsculo e discreto no rodapé (prédio/doc/telefone)."""
    canvas.saveState()
    canvas.setStrokeColor(cor)
    canvas.setFillColor(cor)
    canvas.setLineWidth(0.5)
    if kind == "bldg":  # prédio (empresa)
        canvas.rect(x, y, s * 0.7, s, stroke=1, fill=0)
        canvas.rect(x + s * 0.14, y + s * 0.58, s * 0.12, s * 0.16, fill=1, stroke=0)
        canvas.rect(x + s * 0.44, y + s * 0.58, s * 0.12, s * 0.16, fill=1, stroke=0)
        canvas.rect(x + s * 0.28, y, s * 0.16, s * 0.30, fill=1, stroke=0)  # porta
    elif kind == "doc":  # documento (CNPJ)
        canvas.rect(x + s * 0.05, y, s * 0.62, s, stroke=1, fill=0)
        for k in range(3):
            yy = y + s * (0.28 + 0.22 * k)
            canvas.line(x + s * 0.16, yy, x + s * 0.56, yy)
    elif kind == "phone":  # telefone (fone)
        canvas.roundRect(x + s * 0.16, y, s * 0.44, s, s * 0.09, stroke=1, fill=0)
        canvas.circle(x + s * 0.38, y + s * 0.13, s * 0.05, fill=1, stroke=0)
    canvas.restoreState()


def _rodape_linha_icones(canvas, w: float, y: float, fonte_sz: float, itens: list) -> None:
    """Desenha uma linha de rodapé CENTRALIZADA com um ícone discreto antes de cada item."""
    s = 2.5 * mm
    gap_icone = 1.0 * mm  # ícone → texto
    gap_grupo = 4.5 * mm  # grupo → grupo
    canvas.setFont(FONTE, fonte_sz)
    larguras = [s + gap_icone + canvas.stringWidth(txt, FONTE, fonte_sz) for _k, txt in itens]
    total = sum(larguras) + gap_grupo * (len(itens) - 1)
    x = (w - total) / 2
    for kind, txt in itens:
        _desenha_mini_icone(canvas, kind, x, y - 0.3 * mm, s, AZUL_MEDIO)
        x += s + gap_icone
        canvas.setFillColor(AZUL_MEDIO)
        canvas.drawString(x, y, txt)
        x += canvas.stringWidth(txt, FONTE, fonte_sz) + gap_grupo


def header_footer(
    canvas, doc, *, seal_watermark: bool = False, titulo: str | None = None, pular_primeira: bool = False
):
    """Cabeçalho limpo (logo COMPLETA à esquerda sobre branco + título/empresa à direita) + rodapé oficial.
    Desenha em TODAS as páginas. pular_primeira=True para docs com capa própria na pág. 1.
    seal_watermark=True desenha o selo claro ao centro (contratos/relatórios)."""
    if pular_primeira and doc.page == 1:
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
    # faixa laranja fina no topo
    canvas.setFillColor(LARANJA)
    canvas.rect(0, h - 2.5 * mm, w, 2.5 * mm, fill=1, stroke=0)
    # logo COMPLETA à esquerda (cores da marca sobre branco)
    if not _desenha_logo_cheia(canvas, 16 * mm, h - 33 * mm, 44 * mm, 25 * mm):
        canvas.setFont(FONTE_B, 12)
        canvas.setFillColor(AZUL_ESCURO)
        canvas.drawString(16 * mm, h - 18 * mm, EMPRESA["nome"])
    # título + empresa à direita (azul)
    if titulo:
        canvas.setFillColor(AZUL_ESCURO)
        canvas.setFont(FONTE_B, 15)
        canvas.drawRightString(w - 16 * mm, h - 15 * mm, titulo)
    canvas.setFillColor(AZUL_MEDIO)
    canvas.setFont(FONTE, 8)
    canvas.drawRightString(w - 16 * mm, h - (20 if titulo else 14) * mm, EMPRESA["nome"])
    canvas.drawRightString(w - 16 * mm, h - (24 if titulo else 18) * mm, f"CNPJ {EMPRESA['cnpj']}")
    # régua azul sob o cabeçalho + rodapé
    canvas.setStrokeColor(AZUL_ESCURO)
    canvas.setLineWidth(0.6)
    canvas.line(16 * mm, h - 36 * mm, w - 16 * mm, h - 36 * mm)
    canvas.line(16 * mm, 15 * mm, w - 16 * mm, 15 * mm)
    # linha 1: empresa + CNPJ + fone (CENTRALIZADA, com ícones discretos por item)
    _rodape_linha_icones(
        canvas,
        w,
        11 * mm,
        6.5,
        [("bldg", EMPRESA["nome"]), ("doc", f"CNPJ: {EMPRESA['cnpj']}"), ("phone", EMPRESA["fone"])],
    )
    canvas.setFont(FONTE, 6.5)
    canvas.setFillColor(AZUL_MEDIO)
    # linha 2: site + email + instagram (CENTRALIZADA)
    canvas.drawCentredString(
        w / 2, 7.5 * mm, f"{EMPRESA['site']}   ·   {EMPRESA['email']}   ·   {EMPRESA['instagram']}"
    )
    # paginação discreta no canto inferior direito (sem sobrepor o bloco centralizado)
    canvas.setFont(FONTE, 6)
    canvas.setFillColor(colors.HexColor("#9AA7B8"))
    canvas.drawRightString(w - 16 * mm, 4.5 * mm, f"Página {doc.page}")
    canvas.restoreState()


def marca_canvas(canvas, *, titulo: str | None = None, pagesize=A4, subtitulo: str | None = None) -> float:
    """Desenha o cabeçalho da marca (logo cheia + título + réguas) num canvas.Canvas direto.
    Para geradores que NÃO usam SimpleDocTemplate (comprovante, NF-e). Retorna o y abaixo do header."""
    w, h = pagesize
    canvas.saveState()
    canvas.setFillColor(LARANJA)
    canvas.rect(0, h - 2.5 * mm, w, 2.5 * mm, fill=1, stroke=0)
    if not _desenha_logo_cheia(canvas, 16 * mm, h - 33 * mm, 44 * mm, 25 * mm):
        canvas.setFont(FONTE_B, 12)
        canvas.setFillColor(AZUL_ESCURO)
        canvas.drawString(16 * mm, h - 18 * mm, EMPRESA["nome"])
    if titulo:
        canvas.setFillColor(AZUL_ESCURO)
        canvas.setFont(FONTE_B, 16)
        canvas.drawRightString(w - 16 * mm, h - 15 * mm, titulo)
    canvas.setFillColor(AZUL_MEDIO)
    canvas.setFont(FONTE, 8)
    canvas.drawRightString(w - 16 * mm, h - (20 if titulo else 14) * mm, EMPRESA["nome"])
    canvas.drawRightString(w - 16 * mm, h - (24 if titulo else 18) * mm, f"CNPJ {EMPRESA['cnpj']}")
    if subtitulo:
        canvas.drawRightString(w - 16 * mm, h - (28 if titulo else 22) * mm, subtitulo)
    canvas.setStrokeColor(AZUL_ESCURO)
    canvas.setLineWidth(0.6)
    canvas.line(16 * mm, h - 36 * mm, w - 16 * mm, h - 36 * mm)
    canvas.restoreState()
    return h - 44 * mm


def rodape_canvas(canvas, *, pagesize=A4, pagina: int | None = None) -> None:
    """Rodapé oficial da marca num canvas.Canvas direto."""
    w, _h = pagesize
    canvas.saveState()
    canvas.setStrokeColor(AZUL_ESCURO)
    canvas.setLineWidth(0.6)
    canvas.line(16 * mm, 16 * mm, w - 16 * mm, 16 * mm)
    canvas.setFont(FONTE, 6.5)
    canvas.setFillColor(AZUL_MEDIO)
    canvas.drawString(
        16 * mm,
        12 * mm,
        f"{EMPRESA['nome']} | CNPJ: {EMPRESA['cnpj']} | {EMPRESA['fone']} | "
        f"{EMPRESA['site']} | {EMPRESA['email']} | {EMPRESA['instagram']}",
    )
    if pagina:
        canvas.drawRightString(w - 16 * mm, 12 * mm, f"Página {pagina}")
    canvas.restoreState()


def campos_assinatura(
    st: dict | None = None,
    *,
    funcionario_nome: str | None = None,
    funcionario_cpf: str | None = None,
    responsavel_nome: str | None = None,
    responsavel_cargo: str | None = None,
    cidade: str = "Manaus/AM",
    data_str: str | None = None,
    espaco_antes: float = 16,
    data_prefixo: str = "",
    digital_funcionario: bool = False,
    digital_empresa: bool = False,
    data_empresa: str | None = None,
    funcionario_label: str | None = None,
    funcionario_doc_rotulo: str = "CPF",
    incluir_empresa: bool = True,
    incluir_funcionario: bool = True,
) -> list:
    """Flowables com campos de ASSINATURA (funcionário + responsável pela empresa).

    SELETIVO: use incluir_empresa=False para documentos que NÃO levam a assinatura da
    empresa/CEO (ex.: HOLERITE e recibos de recebimento — basta o funcionário atestar que
    recebeu). incluir_funcionario=False para documentos só da empresa (ex.: licitação,
    relatórios). Se apenas um lado for incluído, a coluna é centralizada.

    O Conecta PRO assina EXATAMENTE no campo de cada nome (âncora invisível
    ASSINAR::FUNCIONARIO / ASSINAR::EMPRESA que o motor de assinatura localiza para
    sobrepor a assinatura no ponto certo). Uso em holerite, contrato, recibo, etc.

    data_prefixo: rótulo antes da data (ex.: "Pago em ").
    digital_funcionario: quando True, o funcionário assina DIGITALMENTE pelo Portal do
    Funcionário (Conecta PRO) — o sub-rótulo reflete isso.
    """
    st = st or styles()
    resp = responsavel_nome or EMPRESA["ceo"]
    resp_cargo = responsavel_cargo or EMPRESA["ceo_cargo"]
    hoje = data_str or ""
    linha = "_" * 42
    cel = ParagraphStyle(
        "assina_cel",
        parent=st.get("small", getSampleStyleSheet()["Normal"]),
        alignment=TA_CENTER,
        fontName=FONTE,
        fontSize=9,
        leading=15,
    )
    func_ident = f"{funcionario_doc_rotulo} {funcionario_cpf}" if funcionario_cpf else ""
    # rótulo do signatário da esquerda: por padrão "Funcionário"; docs de cliente passam
    # funcionario_label="Assinatura do Cliente"/"Emitente". Se assina digital pelo Portal, reflete isso.
    if digital_funcionario:
        sub_func = "Assinatura digital · Portal do Funcionário"
    else:
        sub_func = funcionario_label or "Assinatura do Funcionário"
    # Empresa assina na DATA DO PAGAMENTO (o sistema coleta a data e a assinatura do CEO)
    if digital_empresa:
        sub_emp = f"Assinatura digital · {data_empresa}" if data_empresa else "Assinatura digital"
    else:
        sub_emp = EMPRESA["nome"]
    # espaço em branco ACIMA da linha (room pra caneta) via âncora invisível + linhas vazias
    col_func = Paragraph(
        f'<font size="7" color="#FFFFFF">ASSINAR::FUNCIONARIO</font><br/><br/><br/>{linha}<br/>'
        f"<b>{funcionario_nome or 'Funcionário'}</b><br/>{func_ident}<br/>"
        f'<font color="#2D5F8B">{sub_func}</font>',
        cel,
    )
    col_emp = Paragraph(
        f'<font size="7" color="#FFFFFF">ASSINAR::EMPRESA</font><br/><br/><br/>{linha}<br/>'
        f"<b>{resp}</b><br/>{resp_cargo}<br/>"
        f'<font color="#2D5F8B">{sub_emp}</font>',
        cel,
    )
    # Monta só as colunas pedidas (seletivo). Coluna única fica centralizada.
    cols = []
    if incluir_funcionario:
        cols.append(col_func)
    if incluir_empresa:
        cols.append(col_emp)
    if not cols:
        return [Spacer(1, espaco_antes * mm)]
    t = Table([cols], colWidths=[85 * mm] * len(cols), hAlign="CENTER")
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 2)]))
    out: list = [Spacer(1, espaco_antes * mm)]
    if hoje:
        out.append(
            Paragraph(
                f"{data_prefixo}{cidade}, {hoje}.", ParagraphStyle("loc", parent=cel, alignment=TA_CENTER, fontSize=9.5)
            )
        )
        out.append(Spacer(1, 14 * mm))
    out.append(t)
    return out


def bloco_autenticidade_assinaturas(st: dict | None = None, *, signatarios: list | None = None) -> list:
    """Bloco branded de AUTENTICIDADE das assinaturas eletrônicas (padrão-ouro).

    Mesmo padrão visual da ficha de EPI: para cada assinatura já coletada,
    imprime "ASSINADO ELETRONICAMENTE" com nome, papel, data/hora America/Manaus
    e o hash SHA-256. Deixa de imprimir os que ainda estão pendentes.

    Consome a lista `signatarios` do UniversalSignatureService.status():
      [{signer_name, signer_type, status, signed_at, signature_hash}, ...]

    Não altera o layout dos campos de assinatura — é um complemento branded que
    dá não-repúdio visual ao documento, alinhado à identidade Conecta Mais.
    """
    st = st or styles()
    assinados = [
        s for s in (signatarios or [])
        if (s.get("status") in ("signed", "completed") or s.get("signed_at"))
        and s.get("signature_hash")
    ]
    if not assinados:
        return []

    papel = {"employee": "Funcionário", "company": EMPRESA["nome"], "customer": "Cliente"}
    small = st.get("small", getSampleStyleSheet()["Normal"])
    out: list = [Spacer(1, 4 * mm)]
    out.append(
        Paragraph(
            '<font color="#1E3A5F"><b>AUTENTICIDADE DAS ASSINATURAS ELETRÔNICAS</b></font>',
            ParagraphStyle("aut_tit", parent=small, fontName=FONTE_B, fontSize=8.5),
        )
    )
    for s in assinados:
        nome = s.get("signer_name") or "—"
        pp = papel.get(str(s.get("signer_type")), str(s.get("signer_type") or ""))
        quando = _fmt_dt_manaus(s.get("signed_at"))
        h = s.get("signature_hash") or ""
        out.append(
            Paragraph(
                f"<b>ASSINADO ELETRONICAMENTE</b> por <b>{nome}</b> ({pp}) via Conecta PRO"
                + (f" em {quando}" if quando else "")
                + f' · Hash SHA-256: <font size="6.5">{h}</font>'
                + f'<br/><font color="#2D5F8B" size="7">Verifique em '
                + f"{EMPRESA['site']}/verificar · /signatures/verify/{h[:16]}…</font>",
                ParagraphStyle("aut_lin", parent=small, fontSize=7.5, leading=11),
            )
        )
    return out


def _fmt_dt_manaus(v) -> str:
    """Formata um datetime/ISO para dd/mm/aaaa HH:MM (já em horário de Manaus)."""
    if not v:
        return ""
    try:
        from datetime import datetime as _dt

        d = v if hasattr(v, "strftime") else _dt.fromisoformat(str(v).replace("Z", ""))
        return d.strftime("%d/%m/%Y %H:%M")
    except Exception:  # noqa: BLE001
        return str(v)


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
