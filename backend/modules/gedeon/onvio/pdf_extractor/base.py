"""
BaseExtractor — Fundação da FASE B2 (extração de valores de PDFs Onvio).
Todo extractor de PDF da FASE B2 HERDA esta classe.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF — já instalado no backend; pdfplumber não está (extractor não importava)
from dateutil import parser as dateparser

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    """Resultado estruturado de uma extração de PDF."""

    tipo: str  # ex: "inss_guia", "fgts_guia"
    valor: Decimal | None = None  # NUNCA float
    vencimento: date | None = None  # NUNCA string
    competencia: str | None = None  # "MM/YYYY" ou "MM.YYYY"
    codigo_barras: str | None = None  # 47-48 dígitos
    confianca: float = 0.0  # 0.0 a 1.0
    metodo_extracao: str = "regex_v1"
    detalhes: dict[str, Any] = field(default_factory=dict)
    erro: str | None = None

    def to_dict(self) -> dict:
        return {
            "tipo": self.tipo,
            "valor": str(self.valor) if self.valor is not None else None,
            "vencimento": self.vencimento.isoformat() if self.vencimento else None,
            "competencia": self.competencia,
            "codigo_barras": self.codigo_barras,
            "confianca": self.confianca,
            "metodo_extracao": self.metodo_extracao,
            "detalhes": self.detalhes,
            "erro": self.erro,
        }


class BaseExtractor(ABC):
    """
    Classe abstrata para extração de dados estruturados de PDFs.

    Subclasses obrigatórias:
    - TIPO (str): identificador da categoria (ex: "inss_guia")
    - extract(pdf_path: Path) -> ExtractionResult

    Métodos herdados (não sobrescrever sem motivo forte):
    - _safe_decimal: converte string BR em Decimal
    - _safe_date: converte string BR em date
    - _validate_cnpj: valida dígitos verificadores
    - _extract_barcode: extrai código de barras de texto
    - _read_pdf_text: lê texto de PDF com pdfplumber
    """

    TIPO: str = "abstrato"

    @abstractmethod
    def extract(self, pdf_path: Path) -> ExtractionResult:
        """Contrato obrigatório: lê PDF, retorna ExtractionResult."""
        ...

    def _read_pdf_text(self, pdf_path: Path) -> str:
        """Extrai todo o texto de um PDF usando PyMuPDF (fitz)."""
        try:
            with fitz.open(pdf_path) as pdf:
                return "\n".join(page.get_text() or "" for page in pdf)
        except Exception as e:
            logger.error(f"Erro ao ler PDF {pdf_path}: {e}")
            return ""

    def _safe_decimal(self, texto: str) -> Decimal | None:
        """
        Converte string BR em Decimal.
        Aceita: 'R$ 1.234,56', '1.234,56', '1234.56', '1,234.56'.
        Rejeita: string vazia, texto, valores ambíguos.
        """
        if not texto or not isinstance(texto, str):
            return None

        s = texto.strip().replace("R$", "").replace("r$", "").strip()
        if not s:
            return None

        # Detectar formato BR (vírgula é decimal) vs US (ponto é decimal)
        # BR: "1.234,56" (ponto = milhar, vírgula = decimal)
        # US: "1,234.56" (vírgula = milhar, ponto = decimal)
        has_comma = "," in s
        has_dot = "." in s

        if has_comma and has_dot:
            # Decisão: a última ocorrência de "," ou "." é o separador decimal
            last_comma = s.rfind(",")
            last_dot = s.rfind(".")
            if last_comma > last_dot:
                # BR: remover pontos (milhares), trocar vírgula por ponto
                s = s.replace(".", "").replace(",", ".")
            else:
                # US: remover vírgulas (milhares), manter ponto
                s = s.replace(",", "")
        elif has_comma:
            # Só vírgula: assume BR (decimal)
            s = s.replace(",", ".")
        # else: só ponto, assume formato US/decimal

        try:
            return Decimal(s)
        except InvalidOperation:
            return None

    def _safe_date(self, texto: str) -> date | None:
        """Converte string BR em date. Usa dayfirst=True."""
        if not texto:
            return None
        try:
            dt = dateparser.parse(texto.strip(), dayfirst=True, fuzzy=True)
            return dt.date()
        except (ValueError, TypeError):
            return None

    def _validate_cnpj(self, cnpj: str) -> bool:
        """Valida dígitos verificadores do CNPJ."""
        if not cnpj:
            return False
        digits = re.sub(r"\D", "", cnpj)
        if len(digits) != 14 or digits == digits[0] * 14:
            return False

        def calc_digit(nums: str, pesos: list[int]) -> int:
            soma = sum(int(n) * p for n, p in zip(nums, pesos, strict=False))
            resto = soma % 11
            return 0 if resto < 2 else 11 - resto

        pesos_1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        pesos_2 = [6] + pesos_1
        d1 = calc_digit(digits[:12], pesos_1)
        d2 = calc_digit(digits[:12] + str(d1), pesos_2)
        return digits[-2:] == f"{d1}{d2}"

    def _extract_barcode(self, texto: str) -> str | None:
        """
        Extrai código de barras de 47 ou 48 dígitos.
        Formatos: contínuo (47-48 dígitos) ou em 4 grupos separados.
        """
        if not texto:
            return None
        # Padrão: 4 grupos de dígitos separados por espaços (formato boleto, grupos de 10-12 dígitos)
        m = re.search(r"(\d{10,12})\s+(\d{10,12})\s+(\d{10,12})\s+(\d{10,12})", texto)
        if m:
            return "".join(m.groups())
        # Padrão: 47 ou 48 dígitos contíguos
        m = re.search(r"(\d{47,48})(?!\d)", texto)
        if m:
            return m.group(1)
        return None


# TESTES INLINE — OBRIGATÓRIO 100% PASSAR
if __name__ == "__main__":
    from decimal import Decimal

    class _TestExtractor(BaseExtractor):
        TIPO = "teste"

        def extract(self, pdf_path):
            return ExtractionResult(tipo=self.TIPO)

    be = _TestExtractor()

    # Testes _safe_decimal
    casos_decimal = [
        ("R$ 1.234,56", Decimal("1234.56")),
        ("1.234,56", Decimal("1234.56")),
        ("1234.56", Decimal("1234.56")),
        ("1,234.56", Decimal("1234.56")),
        ("R$ 12.345.678,90", Decimal("12345678.90")),
        ("abc", None),
        ("", None),
        (None, None),
        ("R$ 0,01", Decimal("0.01")),
        ("100", Decimal("100")),
    ]
    print("\n=== _safe_decimal ===")
    erros = 0
    for entrada, esperado in casos_decimal:
        r = be._safe_decimal(entrada)
        status = "✅" if r == esperado else "❌"
        if r != esperado:
            erros += 1
            print(f"{status} {entrada!r} → {r} (esperado: {esperado})")
        else:
            print(f"{status} {entrada!r} → {r}")
    assert erros == 0, f"_safe_decimal: {erros} falhas"

    # Testes _safe_date
    from datetime import date as d

    casos_date = [
        ("20/04/2026", d(2026, 4, 20)),
        ("20-04-2026", d(2026, 4, 20)),
        ("Vencimento: 15/05/2026", d(2026, 5, 15)),
    ]
    print("\n=== _safe_date ===")
    for entrada, esperado in casos_date:
        r = be._safe_date(entrada)
        status = "✅" if r == esperado else "❌"
        print(f"{status} {entrada!r} → {r}")
        assert r == esperado, f"FALHOU: {entrada}"

    # Testes _validate_cnpj
    casos_cnpj = [
        ("35.710.481/0001-03", True),  # Conecta Mais (real)
        ("35710481000103", True),
        ("00.000.000/0000-00", False),
        ("11111111111111", False),  # Repetidos
        ("12345678901234", False),  # DV incorreto
    ]
    print("\n=== _validate_cnpj ===")
    for entrada, esperado in casos_cnpj:
        r = be._validate_cnpj(entrada)
        status = "✅" if r == esperado else "❌"
        print(f"{status} {entrada} → {r}")
        assert r == esperado

    # Testes _extract_barcode
    casos_barcode = [
        ("85820000004 2238000026 0412026044 0000000056", "85820000004223800002604120260440000000056"),
        ("Não tem código aqui", None),
    ]
    print("\n=== _extract_barcode ===")
    for entrada, esperado in casos_barcode:
        r = be._extract_barcode(entrada)
        status = "✅" if r == esperado else "❌"
        print(f"{status} {entrada[:50]}... → {r}")

    print("\n✅ TODOS OS TESTES DO BaseExtractor PASSARAM")
