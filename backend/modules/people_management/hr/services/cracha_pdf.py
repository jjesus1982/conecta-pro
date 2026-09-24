"""Crachás em lote — folha A4 com 8 crachás (85,6 × 54 mm, padrão CR-80) no timbrado da marca (DGX F6).

Frente simples: foto (moldura vazia quando não há), nome de guerra (ou primeiro nome), nome
completo, função, matrícula, CPF mascarado, CNV quando vigilante, empresa por CNPJ do vínculo.
Tudo vem de `pdf_branding` — mudar a marca lá muda aqui.
"""

from __future__ import annotations

import os
import re
from datetime import date
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as _canvas

from modules.crm.services import (
    pdf_branding as B,  # noqa: N812 — mesma grafia dos outros geradores (relatorio_diaristas_pdf)
)

CARD_W, CARD_H = 85.6 * mm, 54 * mm
POR_PAGINA = 8  # 2 colunas × 4 linhas
_GAP_X, _GAP_Y = 6 * mm, 4 * mm
_MARGEM = 16 * mm


def cpf_mascarado(cpf: str | None) -> str:
    d = re.sub(r"\D", "", cpf or "")
    return f"***.{d[3:6]}.{d[6:9]}-**" if len(d) == 11 else "—"


def foto_path(url: str | None) -> str | None:
    """Caminho local da foto, ou None (moldura vazia). `employees.foto_url` pode ser caminho
    absoluto, relativo a UPLOADS_DIR ou URL '/uploads/...'."""
    if not url or url.startswith("http"):
        return None
    up = os.getenv("UPLOADS_DIR", "/app/uploads")
    for cand in (url, os.path.join(up, url.lstrip("/")), os.path.join(up, re.sub(r"^/?uploads/", "", url))):
        if os.path.isfile(cand):
            return cand
    return None


def _cracha(c, x: float, y: float, p: dict) -> None:
    emp = B.empresa_branding(p.get("empresa_slug"))
    c.saveState()
    c.setStrokeColor(B.AZUL_ESCURO)
    c.setLineWidth(0.5)
    c.roundRect(x, y, CARD_W, CARD_H, 3 * mm, stroke=1, fill=0)
    # faixa superior com a empresa
    c.setFillColor(B.AZUL_ESCURO)
    c.roundRect(x, y + CARD_H - 8 * mm, CARD_W, 8 * mm, 3 * mm, stroke=0, fill=1)
    c.rect(x, y + CARD_H - 8 * mm, CARD_W, 4 * mm, stroke=0, fill=1)  # quina reta embaixo da faixa
    c.setFillColor(B.LARANJA)
    c.rect(x, y + CARD_H - 8.8 * mm, CARD_W, 0.8 * mm, stroke=0, fill=1)
    c.setFillColor("white")
    c.setFont(B.FONTE_B, 7.2)
    c.drawString(x + 3 * mm, y + CARD_H - 5.4 * mm, emp["nome"])
    c.setFont(B.FONTE, 5.6)
    c.drawRightString(x + CARD_W - 3 * mm, y + CARD_H - 5.4 * mm, f"CNPJ {emp['cnpj']}")
    # foto
    fx, fy, fw, fh = x + 3 * mm, y + 9 * mm, 22 * mm, 29 * mm
    c.setStrokeColor(B.AZUL_MEDIO)
    c.setFillColor(B.FUNDO_CLARO)
    c.rect(fx, fy, fw, fh, stroke=1, fill=1)
    fp = foto_path(p.get("foto_url"))
    if fp:
        try:
            c.drawImage(fp, fx, fy, fw, fh, preserveAspectRatio=True, anchor="c", mask="auto")
        except Exception:  # noqa: BLE001 — arquivo ilegível vira moldura vazia, não quebra o lote
            fp = None
    if not fp:
        c.setFillColor(B.AZUL_MEDIO)
        c.setFont(B.FONTE, 5.5)
        c.drawCentredString(fx + fw / 2, fy + fh / 2, "SEM FOTO")
    # textos
    tx = fx + fw + 3.5 * mm
    largura_txt = x + CARD_W - 3 * mm - tx
    nome = (p.get("nome") or "—").strip()
    guerra = (p.get("nome_de_guerra") or "").strip() or nome.split()[0]
    c.setFillColor(B.AZUL_ESCURO)
    tam = 12.5
    while tam > 8 and c.stringWidth(guerra.upper(), B.FONTE_B, tam) > largura_txt:
        tam -= 0.5
    c.setFont(B.FONTE_B, tam)
    c.drawString(tx, y + CARD_H - 15 * mm, guerra.upper())
    c.setFont(B.FONTE, 6.2)
    c.setFillColor(B.TEXTO)
    c.drawString(tx, y + CARD_H - 19 * mm, nome[:48])
    c.setFillColor(B.LARANJA)
    c.setFont(B.FONTE_B, 7.4)
    c.drawString(tx, y + CARD_H - 24 * mm, (p.get("cargo") or "—")[:34].upper())
    c.setFillColor(B.TEXTO)
    c.setFont(B.FONTE, 6.4)
    linhas = [f"Matrícula {p.get('matricula') or '—'}", f"CPF {cpf_mascarado(p.get('cpf'))}"]
    if p.get("cnv") and "vigil" in (p.get("cargo") or "").lower():
        linhas.append(f"CNV {p['cnv']}")
    for i, ln in enumerate(linhas):
        c.drawString(tx, y + CARD_H - (29 + i * 3.6) * mm, ln)
    B._desenha_logo_cheia(c, x + CARD_W - 21 * mm, y + 2.2 * mm, 18 * mm, 9 * mm)
    c.setFillColor(B.AZUL_MEDIO)
    c.setFont(B.FONTE, 4.8)
    c.drawString(x + 3 * mm, y + 3 * mm, f"{emp['fone']} · {emp['site']}")
    c.restoreState()


def montar_crachas(pessoas: list[dict], titulo: str = "Crachás funcionais") -> bytes:
    """Uma folha A4 timbrada a cada 8 crachás. `pessoas`: nome, nome_de_guerra, cargo,
    matricula, cpf, cnv, foto_url, empresa_slug."""
    buf = BytesIO()
    c = _canvas.Canvas(buf, pagesize=A4)
    emp = B.empresa_branding(pessoas[0].get("empresa_slug")) if pessoas else None
    paginas = max(1, (len(pessoas) + POR_PAGINA - 1) // POR_PAGINA)
    for pg in range(paginas):
        y_top = B.marca_canvas(
            c, titulo=titulo, subtitulo=f"{len(pessoas)} crachá(s) · {B.br_date(date.today())}", empresa=emp
        )
        lote = pessoas[pg * POR_PAGINA : (pg + 1) * POR_PAGINA]
        for i, p in enumerate(lote):
            col, lin = i % 2, i // 2
            x = _MARGEM + col * (CARD_W + _GAP_X)
            y = y_top - 2 * mm - (lin + 1) * CARD_H - lin * _GAP_Y
            _cracha(c, x, y, p)
        B.rodape_canvas(c, pagina=pg + 1, empresa=emp)
        c.showPage()
    c.save()
    return buf.getvalue()


def demo() -> None:
    pessoas = [
        {
            "nome": f"PESSOA {i} DA SILVA",
            "cargo": "VIGILANTE" if i % 2 else "AGENTE DE PORTARIA",
            "matricula": str(100 + i),
            "cpf": "52998224725",
            "cnv": "12345",
            "empresa_slug": "conecta_patrimonial",
        }
        for i in range(9)
    ]
    pdf = montar_crachas(pessoas)
    assert pdf.startswith(b"%PDF") and b"/Count 2" in pdf  # 9 crachás = 2 páginas
    assert cpf_mascarado("529.982.247-25") == "***.982.247-**" and cpf_mascarado(None) == "—"
    assert foto_path(None) is None and foto_path("http://x") is None
    print("ok cracha_pdf", len(pdf), "bytes")


if __name__ == "__main__":
    demo()
