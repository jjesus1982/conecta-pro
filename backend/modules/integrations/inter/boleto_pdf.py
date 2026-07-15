"""Extrai a LINHA DIGITÁVEL de um boleto em PDF (texto selecionável).

A maioria dos boletos de fornecedor é PDF gerado digitalmente e traz a linha
digitável como texto — basta extrair e casar o padrão. Se o PDF for imagem
escaneada (sem camada de texto), devolve encontrado=False (aí o usuário escaneia/digita).

Não faz efeito externo: recebe bytes do PDF, devolve dict.
"""

from __future__ import annotations

import re
from typing import Any

# Linha digitável de BOLETO BANCÁRIO (47 díg): AAAAA.AAAAA BBBBB.BBBBBB CCCCC.CCCCCC D EEEEEEEEEEEEEE
_RE_BANCARIO = re.compile(
    r"(\d{5})[.\s]?(\d{5})[\s]+(\d{5})[.\s]?(\d{6})[\s]+(\d{5})[.\s]?(\d{6})[\s]+(\d)[\s]+(\d{14})"
)
# Arrecadação/concessionária (48 díg, começa com 8): 4 blocos de 11+DV
_RE_ARRECAD = re.compile(
    r"(8\d{10})[-\s]?\d?[\s]*(\d{11})[-\s]?\d?[\s]*(\d{11})[-\s]?\d?[\s]*(\d{11})[-\s]?\d?"
)


def _so_digitos(s: str) -> str:
    return "".join(c for c in s if c.isdigit())


def _valor_da_linha(linha: str) -> float | None:
    """Valor nominal a partir da linha digitável de boleto bancário (últimos 10 díg = centavos)."""
    d = _so_digitos(linha)
    if len(d) == 47:
        try:
            cents = int(d[37:47])
            return cents / 100 if cents > 0 else None
        except ValueError:
            return None
    return None


def _mod10(num: str) -> int:
    soma, peso = 0, 2
    for ch in reversed(num):
        p = int(ch) * peso
        soma += p if p < 10 else p - 9
        peso = 1 if peso == 2 else 2
    return (10 - (soma % 10)) % 10


def _barcode_para_linha(b: str) -> str | None:
    """Código de barras (44) → linha digitável (47), boleto bancário (não inicia com 8)."""
    if len(b) != 44 or b.startswith("8"):
        return b if len(b) == 44 else None  # arrecadação: o Inter aceita o próprio código
    c1, c2, c3 = b[0:4] + b[19:24], b[24:34], b[34:44]
    return f"{c1}{_mod10(c1)}{c2}{_mod10(c2)}{c3}{_mod10(c3)}{b[4]}{b[5:19]}"


def _decodificar_barcode_do_pdf(pdf_bytes: bytes) -> dict[str, Any] | None:
    """Fallback p/ boleto-IMAGEM: renderiza a página e decodifica o código de barras (ITF).

    Cobre boletos que não têm a linha digitável na camada de texto (dados são imagem)."""
    try:
        import fitz  # PyMuPDF
        import zxingcpp
        from PIL import Image
    except Exception:
        return None
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        return None
    try:
        for page in doc:
            for dpi in (300, 200, 400):
                pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72))
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                for r in zxingcpp.read_barcodes(img):
                    cod = _so_digitos(r.text)
                    if r.format.name == "ITF" and len(cod) == 44:
                        linha = _barcode_para_linha(cod)
                        if linha:
                            return {"linha_digitavel": linha,
                                    "valor": _valor_da_linha(linha),
                                    "tipo": "bancario" if not cod.startswith("8") else "arrecadacao"}
    finally:
        doc.close()
    return None


def extrair_linha_digitavel(pdf_bytes: bytes) -> dict[str, Any]:
    """Retorna {encontrado, linha_digitavel, valor, tipo, motivo}."""
    res: dict[str, Any] = {"encontrado": False, "linha_digitavel": None, "valor": None,
                           "tipo": None, "motivo": None}
    texto = ""
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page in doc:
            texto += page.get_text("text") + "\n"
        doc.close()
    except Exception as exc:  # noqa: BLE001
        res["motivo"] = f"Não consegui ler o PDF: {str(exc)[:120]}"
        return res

    # 1) boleto bancário (47)
    m = _RE_BANCARIO.search(texto)
    if m:
        linha = _so_digitos("".join(m.groups()))
        if len(linha) == 47:
            res.update(encontrado=True, linha_digitavel=linha, tipo="bancario",
                       valor=_valor_da_linha(linha))
            return res

    # 2) arrecadação (48) — junta os 4 blocos de 11 (sem os DV) = 44, mantém como está p/ o Inter
    m2 = _RE_ARRECAD.search(texto)
    if m2:
        linha = _so_digitos("".join(m2.groups()))
        if len(linha) in (44, 48):
            res.update(encontrado=True, linha_digitavel=linha, tipo="arrecadacao")
            return res

    # 3) fallback texto: qualquer sequência numérica (com . e espaço) que normalize p/ 47/48
    for token in re.findall(r"[\d][\d.\s]{40,60}\d", texto):
        d = _so_digitos(token)
        if len(d) in (47, 48):
            res.update(encontrado=True, linha_digitavel=d,
                       tipo="bancario" if len(d) == 47 else "arrecadacao",
                       valor=_valor_da_linha(d))
            return res

    # 4) fallback IMAGEM: boleto sem linha digitável em texto (dados são imagem) —
    #    renderiza a página e decodifica o código de barras (ITF). Cobre "todos os modelos".
    via_barcode = _decodificar_barcode_do_pdf(pdf_bytes)
    if via_barcode and via_barcode.get("linha_digitavel"):
        res.update(encontrado=True, **via_barcode)
        return res

    res["motivo"] = "Não encontrei a linha digitável no PDF. Escaneie o código de barras ou digite."
    return res
