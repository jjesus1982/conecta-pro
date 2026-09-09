"""PDFs SIMULADOS do kit de homologação (09/09/2026) — boleto PIX, DANFSe no layout da prefeitura e guias.

Só para cliente de HOMOLOGAÇÃO (todos os alocados is_homologacao). Nenhum destes documentos existe de verdade:
o boleto não tem registro bancário, a nota não foi emitida, as guias não foram geradas pelo governo. Cada um
carrega a marca "SIMULADO" visível. Em cliente real esses lugares são preenchidos pelo GEDEON (Inter/Cora, ADN
da NFS-e Nacional, Onvio).

Reuso: reportlab (código de barras I2of5 e QR já vêm com ele — não há dependência nova).
"""
from __future__ import annotations

import io
from datetime import date

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import qr
from reportlab.graphics.barcode.common import I2of5
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from modules.crm.services import pdf_branding as B  # noqa: N812

AZUL = B.AZUL_ESCURO
LARANJA = B.LARANJA
CINZA = colors.HexColor("#555555")


def _brl(v: float) -> str:
    return B.brl(v)


# ───────────────────────────── boleto PIX ─────────────────────────────
def _mod10(seq: str) -> int:
    soma, peso = 0, 2
    for ch in reversed(seq):
        p = int(ch) * peso
        soma += p if p < 10 else p - 9
        peso = 1 if peso == 2 else 2
    return (10 - soma % 10) % 10


def _mod11(seq: str) -> int:
    soma, peso = 0, 2
    for ch in reversed(seq):
        soma += int(ch) * peso
        peso = 2 if peso == 9 else peso + 1
    r = 11 - soma % 11
    return 1 if r in (0, 10, 11) else r


def codigo_barras_e_linha(banco: str, venc: date, valor: float, campo_livre: str) -> tuple[str, str]:
    """FEBRABAN: banco(3) moeda(1) DV(1) fator(4) valor(10) campo livre(25). Fator: base 22/02/2025 = 1000."""
    fator = 1000 + (venc - date(2025, 2, 22)).days
    val = f"{int(round(valor * 100)):010d}"
    campo_livre = (campo_livre + "0" * 25)[:25]
    sem_dv = f"{banco}9{fator:04d}{val}{campo_livre}"
    dv = _mod11(sem_dv)
    cb = f"{banco}9{dv}{fator:04d}{val}{campo_livre}"
    c1 = f"{banco}9{campo_livre[:5]}"
    c2 = campo_livre[5:15]
    c3 = campo_livre[15:25]
    linha = (f"{c1[:5]}.{c1[5:]}{_mod10(c1)} {c2[:5]}.{c2[5:]}{_mod10(c2)} {c3[:5]}.{c3[5:]}{_mod10(c3)} {dv} {fator:04d}{val}")
    return cb, linha


def _crc16(payload: str) -> str:
    crc = 0xFFFF
    for b in payload.encode():
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return f"{crc:04X}"


def pix_copia_e_cola(chave: str, nome: str, cidade: str, valor: float, txid: str) -> str:
    def f(i: str, v: str) -> str:
        return f"{i}{len(v):02d}{v}"
    mai = f("00", "BR.GOV.BCB.PIX") + f("01", chave)
    payload = (f("00", "01") + f("26", mai) + f("52", "0000") + f("53", "986") + f("54", f"{valor:.2f}")
               + f("58", "BR") + f("59", nome[:25]) + f("60", cidade[:15]) + f("62", f("05", txid[:25])) + "6304")
    return payload + _crc16(payload)


def _qr(c: canvas.Canvas, texto: str, x: float, y: float, lado: float) -> None:
    w = qr.QrCodeWidget(texto)
    b = w.getBounds()
    d = Drawing(lado, lado, transform=[lado / (b[2] - b[0]), 0, 0, lado / (b[3] - b[1]), 0, 0])
    d.add(w)
    renderPDF.draw(d, c, x, y)


def boleto_pix_pdf(*, beneficiario: dict, pagador: dict, valor: float, vencimento: date, descricao: str,
                   nosso_numero: str, banco_nome: str = "Banco Cora SCD", banco_codigo: str = "403",
                   chave_pix: str = "financeiro@conectamais.pro", simulado: bool = True) -> bytes:
    """Boleto híbrido (código de barras + QR PIX) no padrão dos bancos digitais, com a marca Conecta Mais."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    x0, x1 = 15 * mm, W - 15 * mm
    import re as _re

    nn_dig = _re.sub(r"\D", "", nosso_numero) or "0"  # código de barras só aceita dígitos
    cb, linha = codigo_barras_e_linha(banco_codigo, vencimento, valor, nn_dig.rjust(25, "0"))
    txid = ("SIM" if simulado else "CM") + nosso_numero[-20:]
    pix = pix_copia_e_cola(chave_pix, beneficiario["nome"], "MANAUS", valor, txid)

    # faixa da marca
    c.setFillColor(AZUL)
    c.rect(0, H - 22 * mm, W, 22 * mm, fill=1, stroke=0)
    c.setFillColor(LARANJA)
    c.rect(0, H - 23.2 * mm, W, 1.2 * mm, fill=1, stroke=0)
    for lg in (B.logo_path("header"), B.logo_path("cover")):
        if lg:
            try:
                c.drawImage(lg, x0, H - 19 * mm, width=42 * mm, height=16 * mm, preserveAspectRatio=True, mask="auto")
                break
            except Exception:  # noqa: BLE001, S112 — logo ausente/corrompido: tenta o próximo, boleto sai sem logo
                continue
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 15)
    c.drawRightString(x1, H - 11 * mm, "BOLETO DE COBRANÇA")
    c.setFont("Helvetica", 8.5)
    c.drawRightString(x1, H - 16 * mm, f"{banco_nome} · {banco_codigo}  |  Pague por código de barras ou PIX")

    y = H - 34 * mm
    if simulado:
        c.setFillColor(colors.HexColor("#B00020"))
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x0, y, "SIMULADO — homologação. Sem registro bancário: não pague este documento.")
        y -= 7 * mm

    # linha digitável em destaque
    c.setFillColor(colors.HexColor("#F3F6FA"))
    c.roundRect(x0, y - 14 * mm, x1 - x0, 13 * mm, 2 * mm, fill=1, stroke=0)
    c.setFillColor(CINZA)
    c.setFont("Helvetica", 7.5)
    c.drawString(x0 + 3 * mm, y - 4 * mm, "LINHA DIGITÁVEL")
    c.setFillColor(colors.black)
    c.setFont("Courier-Bold", 13)
    c.drawString(x0 + 3 * mm, y - 10.5 * mm, linha)
    y -= 20 * mm

    # quadro principal: valores à esquerda, QR à direita
    lado = 42 * mm
    _qr(c, pix, x1 - lado, y - lado, lado)
    c.setFillColor(CINZA)
    c.setFont("Helvetica", 7)
    c.drawCentredString(x1 - lado / 2, y - lado - 3.5 * mm, "PIX · aponte a câmera")

    def campo(lbl: str, val: str, yy: float, big: bool = False) -> None:
        c.setFillColor(CINZA)
        c.setFont("Helvetica", 7)
        c.drawString(x0, yy, lbl.upper())
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 14 if big else 9.5)
        c.drawString(x0, yy - (6 * mm if big else 4 * mm), val)

    campo("Valor do documento", _brl(valor), y - 2 * mm, big=True)
    campo("Vencimento", vencimento.strftime("%d/%m/%Y"), y - 14 * mm, big=True)
    campo("Beneficiário", f"{beneficiario['nome']} — CNPJ {beneficiario['cnpj']}", y - 26 * mm)
    campo("Pagador", f"{pagador['nome']} — CNPJ/CPF {pagador.get('documento') or '—'}", y - 33 * mm)
    campo("Nosso número", nosso_numero, y - 40 * mm)
    y -= 50 * mm

    # instruções
    c.setFillColor(colors.HexColor("#F3F6FA"))
    c.roundRect(x0, y - 22 * mm, x1 - x0, 22 * mm, 2 * mm, fill=1, stroke=0)
    c.setFillColor(CINZA)
    c.setFont("Helvetica", 7)
    c.drawString(x0 + 3 * mm, y - 4 * mm, "INSTRUÇÕES")
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 8.5)
    linhas = [descricao[:110], "Após o vencimento: multa de 2% e juros de 1% ao mês (pro rata).",
              "Não receber após 30 dias do vencimento. Dúvidas: financeiro@conectamais.pro · 0800 883 4414."]
    for i, t in enumerate(linhas):
        c.drawString(x0 + 3 * mm, y - 9.5 * mm - i * 4.5 * mm, t)
    y -= 30 * mm

    # PIX copia e cola
    c.setFillColor(CINZA)
    c.setFont("Helvetica", 7)
    c.drawString(x0, y, "PIX COPIA E COLA")
    c.setFillColor(colors.black)
    c.setFont("Courier", 6.8)
    for i in range(0, len(pix), 95):
        c.drawString(x0, y - 4 * mm - (i // 95) * 3.5 * mm, pix[i:i + 95])
    y -= 16 * mm

    # linha de corte + ficha de compensação
    c.setStrokeColor(CINZA)
    c.setDash(2, 2)
    c.line(x0, y, x1, y)
    c.setDash()
    c.setFillColor(CINZA)
    c.setFont("Helvetica", 6.5)
    c.drawRightString(x1, y + 1.5 * mm, "corte aqui")
    y -= 6 * mm
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x0, y, f"{banco_nome}  |  {banco_codigo}-0")
    c.setFont("Courier-Bold", 10)
    c.drawRightString(x1, y, linha)
    y -= 4 * mm
    c.setStrokeColor(colors.black)
    c.line(x0, y, x1, y)
    grade = [("Local de pagamento", "Pagável em qualquer banco ou via PIX até o vencimento"), ("Vencimento", vencimento.strftime("%d/%m/%Y")),
             ("Beneficiário", f"{beneficiario['nome']} — {beneficiario['cnpj']}"), ("Nosso número", nosso_numero),
             ("Espécie", "DM"), ("Valor do documento", _brl(valor)), ("Pagador", f"{pagador['nome']} — {pagador.get('documento') or '—'}")]
    yy = y - 5 * mm
    for lbl, val in grade:
        c.setFillColor(CINZA)
        c.setFont("Helvetica", 6.5)
        c.drawString(x0, yy, lbl.upper())
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 8.5)
        c.drawString(x0 + 40 * mm, yy, val)
        yy -= 5 * mm
    bc = I2of5(cb, barWidth=0.33 * mm, barHeight=13 * mm, bearers=0, quiet=0, checksum=0)
    bc.drawOn(c, x0, yy - 15 * mm)
    c.setFillColor(CINZA)
    c.setFont("Helvetica", 6.5)
    c.drawString(x0, yy - 18 * mm, "Autenticação mecânica — Ficha de compensação")
    if simulado:
        c.saveState()
        c.setFillColor(colors.Color(0.7, 0, 0, alpha=0.12))
        c.setFont("Helvetica-Bold", 60)
        c.translate(W / 2, H / 2)
        c.rotate(35)
        c.drawCentredString(0, 0, "SIMULADO")
        c.restoreState()
    c.showPage()
    c.save()
    return buf.getvalue()


# ───────────────────────────── DANFSe (layout da prefeitura, sem a nossa marca) ─────────────────────────────
def danfse_prefeitura_pdf(d: dict, *, simulada: bool = True) -> bytes:
    """Layout do DANFSe do Padrão Nacional (ADN) como a prefeitura entrega: cabeçalho institucional,
    chave de acesso, QR de consulta, prestador/tomador, serviço, tributos. Sem timbrado Conecta."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    x0, x1 = 15 * mm, W - 15 * mm
    y = H - 15 * mm
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.6)
    c.rect(x0, y - 26 * mm, x1 - x0, 26 * mm)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x0 + 3 * mm, y - 7 * mm, "PREFEITURA MUNICIPAL DE MANAUS")
    c.setFont("Helvetica", 8.5)
    c.drawString(x0 + 3 * mm, y - 11.5 * mm, "Secretaria Municipal de Finanças e Tecnologia da Informação — SEMEF")
    c.drawString(x0 + 3 * mm, y - 15.5 * mm, "NFS-e — Nota Fiscal de Serviço Eletrônica · Padrão Nacional")
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(x1 - 3 * mm, y - 7 * mm, "DANFSe")
    c.setFont("Helvetica", 7.5)
    c.drawRightString(x1 - 3 * mm, y - 11.5 * mm, "Documento Auxiliar da NFS-e")
    c.setFont("Helvetica-Bold", 9)
    c.drawRightString(x1 - 3 * mm, y - 17 * mm, f"Nº {d['numero']}   ·   Competência {d['competencia']}")
    c.setFont("Helvetica", 7.5)
    c.drawRightString(x1 - 3 * mm, y - 21.5 * mm, f"Emissão {d['emissao']}   ·   Local: {d.get('local', 'Manaus')}/AM")
    y -= 30 * mm

    # chave + QR
    chave = d.get("chave") or ""
    c.rect(x0, y - 26 * mm, x1 - x0, 26 * mm)
    c.setFont("Helvetica", 7)
    c.drawString(x0 + 3 * mm, y - 5 * mm, "CHAVE DE ACESSO")
    c.setFont("Courier-Bold", 9.5)
    c.drawString(x0 + 3 * mm, y - 10 * mm, " ".join(chave[i:i + 10] for i in range(0, len(chave), 10)) or "—")
    c.setFont("Helvetica", 7)
    c.drawString(x0 + 3 * mm, y - 15.5 * mm, "Consulte a autenticidade em https://www.nfse.gov.br/consultapublica (leia o QR)")
    c.drawString(x0 + 3 * mm, y - 20 * mm, f"Regime: {d.get('regime', 'Simples Nacional')}   ·   Emitida via ADN (Ambiente de Dados Nacional)")
    _qr(c, f"https://www.nfse.gov.br/consultapublica?chave={chave}", x1 - 25 * mm, y - 25 * mm, 23 * mm)
    y -= 30 * mm

    def bloco(titulo: str, linhas: list[tuple[str, str]], altura: float) -> None:
        nonlocal y
        c.rect(x0, y - altura, x1 - x0, altura)
        c.setFillColor(colors.HexColor("#E6E6E6"))
        c.rect(x0, y - 5 * mm, x1 - x0, 5 * mm, fill=1, stroke=1)
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(x0 + 2 * mm, y - 3.6 * mm, titulo)
        yy = y - 10 * mm
        for lbl, val in linhas:
            c.setFont("Helvetica", 7)
            c.drawString(x0 + 2 * mm, yy, lbl)
            c.setFont("Helvetica-Bold", 8.5)
            c.drawString(x0 + 42 * mm, yy, str(val)[:95])
            yy -= 5 * mm
        y -= altura + 3 * mm

    bloco("PRESTADOR DO SERVIÇO", [("Razão social", d["emit_nome"]), ("CNPJ", d["emit_cnpj"]), ("Inscrição municipal", d.get("emit_im") or "—"),
                                   ("Município", "Manaus/AM")], 30 * mm)
    bloco("TOMADOR DO SERVIÇO", [("Razão social", d["toma_nome"]), ("CNPJ/CPF", d["toma_cnpj"]), ("Endereço", d.get("toma_end") or "—"),
                                 ("Município", d.get("toma_mun") or "Manaus/AM")], 30 * mm)
    bloco("SERVIÇO PRESTADO", [("Código de tributação nacional", d.get("cod_servico") or "11.02.01 — Vigilância, segurança ou monitoramento"),
                               ("Descrição", d["servico"]), ("Local da prestação", "Manaus/AM")], 25 * mm)
    # discriminação
    c.rect(x0, y - 22 * mm, x1 - x0, 22 * mm)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(x0 + 2 * mm, y - 4 * mm, "DISCRIMINAÇÃO DOS SERVIÇOS")
    c.setFont("Helvetica", 8)
    disc = d.get("discr") or ""
    for i in range(0, min(len(disc), 400), 100):
        c.drawString(x0 + 2 * mm, y - 9 * mm - (i // 100) * 4 * mm, disc[i:i + 100])
    y -= 25 * mm
    # tributos e valores
    c.rect(x0, y - 34 * mm, x1 - x0, 34 * mm)
    c.setFillColor(colors.HexColor("#E6E6E6"))
    c.rect(x0, y - 5 * mm, x1 - x0, 5 * mm, fill=1, stroke=1)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(x0 + 2 * mm, y - 3.6 * mm, "TRIBUTAÇÃO MUNICIPAL (ISSQN) E VALORES")
    cols = [("Valor do serviço", d["vserv"]), ("Base de cálculo", d["vbc"]), ("Alíquota ISS", d.get("aliq", "—")), ("Valor ISS", d["viss"]),
            ("ISS retido", d.get("iss_retido", "Não")), ("Retenção INSS", d["vinss"]), ("Valor líquido", d["vliq"])]
    cx = x0 + 2 * mm
    for i, (lbl, val) in enumerate(cols):
        px = cx + (i % 4) * 44 * mm
        py = y - 11 * mm - (i // 4) * 12 * mm
        c.setFont("Helvetica", 7)
        c.drawString(px, py, lbl)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(px, py - 4.5 * mm, f"R$ {val}")
    y -= 38 * mm
    c.setFont("Helvetica", 7)
    c.drawString(x0, y, "Tributos federais (IRPJ, CSLL, PIS, COFINS) apurados no DAS — Simples Nacional. Documento gerado pelo Sistema Nacional NFS-e.")
    if simulada:
        c.saveState()
        c.setFillColor(colors.Color(0.7, 0, 0, alpha=0.14))
        c.setFont("Helvetica-Bold", 54)
        c.translate(W / 2, H / 2)
        c.rotate(35)
        c.drawCentredString(0, 0, "SIMULADA · NÃO EMITIDA")
        c.restoreState()
        c.setFillColor(colors.HexColor("#B00020"))
        c.setFont("Helvetica-Bold", 8)
        c.drawString(x0, 12 * mm, "SIMULAÇÃO de homologação: esta nota NÃO foi transmitida ao Sistema Nacional NFS-e e não tem valor fiscal.")
    c.showPage()
    c.save()
    return buf.getvalue()


# ───────────────────────────── guias (DARF / FGTS Digital / DAS) ─────────────────────────────
def guia_simulada_pdf(*, tipo: str, empresa: dict, competencia: str, vencimento: date, valor: float, linhas: list[tuple[str, str]],
                      codigo_barras_base: str, simulada: bool = True) -> bytes:
    """tipo: 'DARF' (DCTFWeb/INSS), 'FGTS' (FGTS Digital) ou 'DAS' (Simples Nacional). Layout de guia federal."""
    titulos = {"DARF": ("MINISTÉRIO DA FAZENDA — SECRETARIA ESPECIAL DA RECEITA FEDERAL DO BRASIL",
                        "DARF — Documento de Arrecadação de Receitas Federais (emitido pela DCTFWeb)"),
               "FGTS": ("MINISTÉRIO DO TRABALHO E EMPREGO — FGTS DIGITAL", "Guia do FGTS Digital — recolhimento mensal"),
               "DAS": ("RECEITA FEDERAL DO BRASIL — SIMPLES NACIONAL", "DAS — Documento de Arrecadação do Simples Nacional")}
    t1, t2 = titulos[tipo]
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    x0, x1 = 15 * mm, W - 15 * mm
    y = H - 15 * mm
    c.rect(x0, y - 18 * mm, x1 - x0, 18 * mm)
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(x0 + 3 * mm, y - 6 * mm, t1)
    c.setFont("Helvetica", 8.5)
    c.drawString(x0 + 3 * mm, y - 11 * mm, t2)
    c.setFont("Helvetica-Bold", 9)
    c.drawRightString(x1 - 3 * mm, y - 6 * mm, f"Período de apuração: {competencia}")
    c.drawRightString(x1 - 3 * mm, y - 11 * mm, f"Vencimento: {vencimento.strftime('%d/%m/%Y')}")
    y -= 22 * mm
    dados = [("Contribuinte", empresa["nome"]), ("CNPJ", empresa["cnpj"])] + linhas + [("Valor total a recolher", _brl(valor))]
    c.rect(x0, y - (len(dados) * 6 + 4) * mm, x1 - x0, (len(dados) * 6 + 4) * mm)
    yy = y - 6 * mm
    for lbl, val in dados:
        c.setFont("Helvetica", 7.5)
        c.drawString(x0 + 3 * mm, yy, lbl)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x0 + 60 * mm, yy, str(val))
        yy -= 6 * mm
    y = yy - 6 * mm
    cb = (codigo_barras_base + "0" * 48)[:48]
    linha = " ".join(f"{cb[i:i + 11]}-{_mod10(cb[i:i + 11])}" for i in range(0, 44, 11))
    c.setFont("Courier-Bold", 10.5)
    c.drawString(x0, y, linha)
    bc = I2of5(cb[:44], barWidth=0.33 * mm, barHeight=13 * mm, bearers=0, quiet=0, checksum=0)
    bc.drawOn(c, x0, y - 17 * mm)
    c.setFont("Helvetica", 7)
    c.drawString(x0, y - 21 * mm, "Pagável em bancos, internet banking e casas lotéricas até o vencimento.")
    if simulada:
        c.saveState()
        c.setFillColor(colors.Color(0.7, 0, 0, alpha=0.14))
        c.setFont("Helvetica-Bold", 54)
        c.translate(W / 2, H / 2)
        c.rotate(35)
        c.drawCentredString(0, 0, "SIMULADA")
        c.restoreState()
        c.setFillColor(colors.HexColor("#B00020"))
        c.setFont("Helvetica-Bold", 8)
        c.drawString(x0, 12 * mm, "SIMULAÇÃO de homologação: guia NÃO gerada pelo órgão arrecadador; valores calculados sobre a folha de teste.")
    c.showPage()
    c.save()
    return buf.getvalue()


if __name__ == "__main__":
    cb, ln = codigo_barras_e_linha("403", date(2026, 9, 10), 47681.28, "1234567890123456789012345")
    assert len(cb) == 44 and len(ln.replace(" ", "").replace(".", "")) == 47, (cb, ln)
    p = pix_copia_e_cola("x@y.com", "CONECTA", "MANAUS", 10.0, "TX1")
    assert p.startswith("000201") and len(p) > 60
    assert boleto_pix_pdf(beneficiario={"nome": "A", "cnpj": "1"}, pagador={"nome": "B"}, valor=10, vencimento=date(2026, 9, 10),
                          descricao="x", nosso_numero="1").startswith(b"%PDF-")
    print("ok")
