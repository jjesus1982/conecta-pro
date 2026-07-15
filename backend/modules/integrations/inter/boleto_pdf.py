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

    if not texto.strip():
        res["motivo"] = "PDF sem texto (boleto escaneado/imagem). Escaneie o código de barras ou digite a linha."
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

    # 3) fallback: qualquer sequência numérica (com . e espaço) que normalize p/ 47/48
    for token in re.findall(r"[\d][\d.\s]{40,60}\d", texto):
        d = _so_digitos(token)
        if len(d) in (47, 48):
            res.update(encontrado=True, linha_digitavel=d,
                       tipo="bancario" if len(d) == 47 else "arrecadacao",
                       valor=_valor_da_linha(d))
            return res

    res["motivo"] = "Não encontrei a linha digitável no PDF. Escaneie o código de barras ou digite."
    return res
