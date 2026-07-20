"""
GEDEON — Gerador de Comprovante de Pagamento (produção interna no Conecta PRO).

Gera um PDF limpo de "Comprovante de Pagamento" a partir dos dados reais de uma
transação PIX do Banco Inter (data, valor, favorecido, CPF, idTransacao). É o
documento que o Conecta PRO PRODUZ internamente — em paralelo (sombra) ao extrato
oficial do Inter, pro agente ATLAS comparar e aprender até ficarem idênticos.

Determinístico (sem efeito externo): recebe dados, devolve bytes PDF.
"""

from __future__ import annotations

import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from modules.crm.services import pdf_branding as B

# Empresa pagadora (CNPJ 1 — matriz)
EMPRESA_NOME = "CONECTAMAIS ELETRONICA LTDA"
EMPRESA_CNPJ = "35.710.481/0001-03"
BANCO_ORIGEM = "Banco Inter S.A. (077)"

# Marca Conecta Mais — este comprovante vai para o CLIENTE/favorecido
_AZUL = B.AZUL_ESCURO
_LARANJA = B.LARANJA
_CINZA = colors.HexColor("#6b7280")
_CINZA_CLARO = colors.HexColor("#f1f3f5")


def _fmt_valor(v) -> str:
    try:
        return f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return f"R$ {v}"


def _fmt_cpf(doc) -> str:
    if not doc:
        return "-"
    d = "".join(ch for ch in str(doc) if ch.isdigit())
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return str(doc)


def _fmt_data(d) -> str:
    if isinstance(d, str):
        # aceita "2026-06-05" ou "05/06/2026"
        if "-" in d and len(d) >= 10:
            a, m, dia = d[:10].split("-")
            return f"{dia}/{m}/{a}"
        return d
    if isinstance(d, date):
        return d.strftime("%d/%m/%Y")
    return str(d)


def gerar_comprovante_pdf(
    favorecido: str,
    cpf: str | None,
    valor,
    data_pagamento,
    descricao: str | None = None,
    id_transacao: str | None = None,
    competencia: str | None = None,
    condominio: str | None = None,
    tipo: str = "PIX",
    emitido_em: str | None = None,
    empresa_nome: str | None = None,
    empresa_cnpj: str | None = None,
    banco_origem: str | None = None,
) -> bytes:
    """Gera o PDF do comprovante e retorna os bytes.

    Multi-CNPJ E4: empresa_nome/cnpj/banco_origem parametrizáveis — default
    (None) mantém CNPJ1/Inter (comportamento atual). Pagamento da Patrimonial
    passa a Patrimonial/Cora sem tocar os comprovantes históricos do Inter."""
    _emp_nome = empresa_nome or EMPRESA_NOME
    _emp_cnpj = empresa_cnpj or EMPRESA_CNPJ
    _banco = banco_origem or BANCO_ORIGEM
    _banco_label = _banco.replace("Banco ", "").split(" S.A")[0].split(" (")[0].strip()
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    x0, x1 = 20 * mm, W - 20 * mm

    # ── Cabeçalho (marca Conecta Mais — logo cheia sobre fundo branco) ──
    # faixa laranja fina no topo
    c.setFillColor(_LARANJA)
    c.rect(0, H - 2.5 * mm, W, 2.5 * mm, fill=1, stroke=0)
    # logo COMPLETA Conecta Mais (canto esquerdo, cores da marca sobre branco)
    for _lg in ("/app/uploads/assets/conecta-mais/conecta-mais.png", B.logo_path("cover"), B.logo_path("header")):
        if not _lg:
            continue
        try:
            c.drawImage(
                _lg,
                x0,
                H - 34 * mm,
                width=46 * mm,
                height=26 * mm,
                preserveAspectRatio=True,
                anchor="nw",
                mask="auto",
            )
            break
        except Exception:
            continue
    # título e dados da empresa à direita, em azul
    c.setFillColor(_AZUL)
    c.setFont("Helvetica-Bold", 17)
    c.drawRightString(x1, H - 15 * mm, "COMPROVANTE DE PAGAMENTO")
    c.setFillColor(_CINZA)
    c.setFont("Helvetica", 8.5)
    c.drawRightString(x1, H - 20 * mm, _emp_nome)
    c.drawRightString(x1, H - 24 * mm, f"CNPJ {_emp_cnpj}")
    c.drawRightString(x1, H - 28 * mm, _banco)
    # régua fina azul separando o cabeçalho
    c.setStrokeColor(_AZUL)
    c.setLineWidth(0.6)
    c.line(x0, H - 37 * mm, x1, H - 37 * mm)

    # ── Valor em destaque ──
    y = H - 50 * mm
    c.setFillColor(_CINZA)
    c.setFont("Helvetica", 10)
    c.drawString(x0, y + 8 * mm, "Valor do pagamento")
    c.setFillColor(_AZUL)
    c.setFont("Helvetica-Bold", 26)
    c.drawString(x0, y - 2 * mm, _fmt_valor(valor))
    c.setFillColor(_CINZA)
    c.setFont("Helvetica", 11)
    c.drawRightString(x1, y - 2 * mm, _fmt_data(data_pagamento))
    c.setFont("Helvetica", 9)
    c.drawRightString(x1, y + 8 * mm, "Data do pagamento")

    # ── Linhas de dados ──
    linhas = [
        ("Favorecido", favorecido or "-"),
        ("CPF/CNPJ", _fmt_cpf(cpf)),
        ("Forma de pagamento", tipo or "PIX"),
        ("Descrição", descricao or "-"),
        ("Competência (folha)", competencia or "-"),
        ("Condomínio / Posto", condominio or "-"),
        (f"ID da transação ({_banco_label})", id_transacao or "-"),
    ]
    yy = y - 14 * mm
    c.setFont("Helvetica", 10)
    for i, (rot, val) in enumerate(linhas):
        if i % 2 == 0:
            c.setFillColor(_CINZA_CLARO)
            c.rect(x0, yy - 2.5 * mm, x1 - x0, 9 * mm, fill=1, stroke=0)
        c.setFillColor(_CINZA)
        c.drawString(x0 + 3 * mm, yy, rot)
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(x0 + 65 * mm, yy, str(val)[:70])
        c.setFont("Helvetica", 10)
        yy -= 9 * mm

    # ── Rodapé (dados oficiais Conecta Mais) ──
    c.setStrokeColor(_LARANJA)
    c.setLineWidth(0.8)
    c.line(x0, 32 * mm, x1, 32 * mm)
    c.setFillColor(_CINZA)
    c.setFont("Helvetica", 8)
    c.drawString(x0, 26 * mm, f"Documento gerado pelo Conecta PRO a partir do registro de pagamento ({_banco}).")
    c.drawString(
        x0, 22 * mm, "Comprovante de quitação de pagamento — confira o valor e o favorecido com a folha de competência."
    )
    if emitido_em:
        c.drawRightString(x1, 26 * mm, f"Emitido em {emitido_em}")
    c.setFillColor(_AZUL)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(
        x0,
        16 * mm,
        f"{B.EMPRESA['nome']} | CNPJ: {B.EMPRESA['cnpj']} | {B.EMPRESA['fone']} | {B.EMPRESA['site']}",
    )
    c.setFillColor(_CINZA)
    c.setFont("Helvetica-Oblique", 7)
    c.drawString(x0, 12 * mm, "GEDEON • Conecta Mais — Gestão Documental")

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()
