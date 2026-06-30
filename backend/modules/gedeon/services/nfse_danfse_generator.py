"""GEDEON — Gera o DANFSe (PDF da NFS-e Nacional) a partir do XML do ADN.

Documento Auxiliar da NFS-e nacional (SPED/gov.br) — layout limpo e completo com
todos os dados legais (prestador, tomador, serviço, valores, chave de acesso).
Não é pixel-idêntico ao oficial, mas contém tudo + a chave p/ verificação no portal.
"""

from __future__ import annotations

import io
import re

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

_AZUL = colors.HexColor("#0a3d62")
_CINZA = colors.HexColor("#6b7280")
_CLARO = colors.HexColor("#eef1f4")


def _g(xml: str, tag: str, bloco: str | None = None) -> str:
    src = xml
    if bloco:
        m = re.search(rf"<{bloco}>(.*?)</{bloco}>", xml, re.S)
        src = m.group(1) if m else ""
    m = re.search(rf"<{tag}>([^<]*)</{tag}>", src)
    return m.group(1).strip() if m else ""


def _cnpj(d: str) -> str:
    d = re.sub(r"\D", "", d or "")
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}" if len(d) == 14 else d


def _money(v: str) -> str:
    try:
        return f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return v or "-"


def _data(d: str) -> str:
    if d and len(d) >= 10 and "-" in d:
        a, m, dia = d[:10].split("-")
        return f"{dia}/{m}/{a}"
    return d


def parse(xml: str) -> dict:
    chave = (re.search(r'Id="NFS([0-9]+)"', xml) or [None, ""])[1]
    return {
        "numero": _g(xml, "nNFSe"),
        "chave": chave,
        "competencia": _data(_g(xml, "dCompet")),
        "emissao": _data(_g(xml, "dhProc")),
        "local": _g(xml, "xLocEmi"),
        "emit_cnpj": _cnpj(_g(xml, "CNPJ", "emit")),
        "emit_im": _g(xml, "IM", "emit"),
        "emit_nome": _g(xml, "xNome", "emit"),
        "toma_cnpj": _cnpj(_g(xml, "CNPJ", "toma")),
        "toma_nome": _g(xml, "xNome", "toma"),
        "servico": _g(xml, "xTribNac"),
        "vserv": _money(_g(xml, "vServ")),
        "vbc": _money(_g(xml, "vBC")),
        "vliq": _money(_g(xml, "vLiq")),
        "viss": _money(_g(xml, "vISS")),
        "vinss": _money(_g(xml, "vISSQNRet") or _g(xml, "vRetCP") or "0"),
        "discr": (
            re.search(r"<xDescServ>([^<]+)</xDescServ>", xml)
            or re.search(r"<xInfComp>([^<]+)</xInfComp>", xml)
            or [None, ""]
        )[1][:600],
    }


def gerar_danfse_pdf(xml: str) -> bytes:
    d = parse(xml)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    x0, x1 = 18 * mm, W - 18 * mm

    c.setFillColor(_AZUL)
    c.rect(0, H - 30 * mm, W, 30 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(x0, H - 13 * mm, "NFS-e — Nota Fiscal de Serviço Eletrônica")
    c.setFont("Helvetica", 9)
    c.drawString(x0, H - 19 * mm, "DANFSe — Padrão Nacional · Prefeitura de Manaus / SEMEF")
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(x1, H - 13 * mm, f"Nº {d['numero']}")
    c.setFont("Helvetica", 8)
    c.drawRightString(x1, H - 19 * mm, f"Competência {d['competencia']}  ·  Emissão {d['emissao']}")

    y = H - 38 * mm

    def secao(titulo, linhas, altura):
        nonlocal y
        c.setFillColor(_AZUL)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x0, y, titulo)
        y -= 5 * mm
        c.setFillColor(_CLARO)
        c.rect(x0, y - altura + 4 * mm, x1 - x0, altura, fill=1, stroke=0)
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 9)
        for rot, val in linhas:
            c.setFillColor(_CINZA)
            c.drawString(x0 + 2 * mm, y, rot)
            c.setFillColor(colors.black)
            c.setFont("Helvetica-Bold", 9)
            c.drawString(x0 + 42 * mm, y, str(val)[:80])
            c.setFont("Helvetica", 9)
            y -= 5 * mm
        y -= 4 * mm

    secao(
        "PRESTADOR DO SERVIÇO",
        [
            ("Nome", d["emit_nome"]),
            ("CNPJ", d["emit_cnpj"]),
            ("Inscrição Municipal", d["emit_im"]),
            ("Local", d["local"]),
        ],
        22 * mm,
    )
    secao(
        "TOMADOR DO SERVIÇO",
        [
            ("Nome", d["toma_nome"]),
            ("CNPJ", d["toma_cnpj"]),
        ],
        12 * mm,
    )
    secao("SERVIÇO", [("Descrição", d["servico"][:80])], 8 * mm)

    # discriminação (texto)
    c.setFillColor(_AZUL)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x0, y, "DISCRIMINAÇÃO")
    y -= 5 * mm
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 8)
    import textwrap

    for ln in textwrap.wrap(re.sub(r"\s+", " ", d["discr"]), 110)[:6]:
        c.drawString(x0 + 2 * mm, y, ln)
        y -= 4.2 * mm
    y -= 4 * mm

    secao(
        "VALORES",
        [
            ("Valor do Serviço", d["vserv"]),
            ("Base de Cálculo", d["vbc"]),
            ("ISSQN", d["viss"]),
            ("Retenção INSS", d["vinss"]),
            ("Valor Líquido", d["vliq"]),
        ],
        27 * mm,
    )

    c.setStrokeColor(_CINZA)
    c.line(x0, 26 * mm, x1, 26 * mm)
    c.setFillColor(_CINZA)
    c.setFont("Helvetica", 7)
    c.drawString(x0, 21 * mm, "Chave de Acesso da NFS-e:")
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(colors.black)
    c.drawString(x0, 17 * mm, d["chave"])
    c.setFillColor(_CINZA)
    c.setFont("Helvetica", 7)
    c.drawString(
        x0, 12 * mm, "Verifique a autenticidade pela chave de acesso no portal nacional da NFS-e (www.nfse.gov.br)."
    )
    c.setFont("Helvetica-Oblique", 7)
    c.drawString(x0, 8 * mm, "GEDEON · Conecta PRO — DANFSe gerado a partir do XML oficial (ADN).")
    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()
