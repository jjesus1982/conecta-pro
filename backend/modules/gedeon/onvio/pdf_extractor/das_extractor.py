"""
DASExtractor — Extrai dados de guias DAS do Simples Nacional (inclui PARCSN/parcelamento).
Herda de BaseExtractor. Espelha o INSSExtractor; o marcador "do Simples Nacional"
diferencia do DARF INSS ("de Receitas Federais").

Estrutura do DAS (validada em PDF real 2026-01):
  - Header: "Documento de Arrecadação\ndo Simples Nacional"
  - Competência: "Período de Apuração" → nome do mês PT-BR + ano (ex: "Janeiro/2026")
  - Vencimento: "Pagar este documento até\nDD/MM/AAAA"
  - Valor: "Valor Total do Documento\nX.XXX,XX"
  - Composição por tributo (IRPJ/CSLL/COFINS/INSS/ICMS/ISS - SIMPLES NACIONAL)
"""

from __future__ import annotations

import re
from pathlib import Path

from .base import BaseExtractor, ExtractionResult

_MESES_PT: dict[str, str] = {
    "janeiro": "01", "fevereiro": "02", "março": "03", "abril": "04",
    "maio": "05", "junho": "06", "julho": "07", "agosto": "08",
    "setembro": "09", "outubro": "10", "novembro": "11", "dezembro": "12",
}


class DASExtractor(BaseExtractor):
    TIPO = "das_simples_nacional"

    # Marcador exclusivo do DAS (≠ DARF INSS "de Receitas Federais")
    RE_TIPO_DOC = re.compile(r"Documento de Arrecada[çc][ãa]o\s+do Simples Nacional", re.IGNORECASE)

    RE_VALOR = re.compile(r"Valor Total do Documento\s*\n\s*([\d.]+,\d{2})", re.IGNORECASE)
    RE_VENCIMENTO = re.compile(r"Pagar este documento at[eé]\s*\n\s*(\d{2}/\d{2}/\d{4})", re.IGNORECASE)
    RE_COMPETENCIA = re.compile(
        r"(janeiro|fevereiro|mar[çc]o|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)/(\d{4})",
        re.IGNORECASE,
    )
    # Barcode arrecadação: 4 grupos (formato guia) — reaproveita o helper da base
    RE_CNPJ = re.compile(r"\d{2}[\.\s]*\d{3}[\.\s]*\d{3}[/\s]*\d{4}[-\s]*\d{2}")

    def extract(self, pdf_path: Path) -> ExtractionResult:
        result = ExtractionResult(tipo=self.TIPO)
        try:
            texto = self._read_pdf_text(pdf_path)
            if not texto:
                result.erro = "PDF vazio ou não legível"
                return result
            result.detalhes["texto_len"] = len(texto)

            is_das = bool(self.RE_TIPO_DOC.search(texto))
            result.detalhes["is_das"] = is_das

            m = self.RE_VALOR.search(texto)
            if m:
                result.valor = self._safe_decimal(m.group(1))
                result.detalhes["valor_raw"] = m.group(1)

            m = self.RE_VENCIMENTO.search(texto)
            if m:
                result.vencimento = self._safe_date(m.group(1))
                result.detalhes["vencimento_raw"] = m.group(1)

            m = self.RE_COMPETENCIA.search(texto)
            if m:
                mes = _MESES_PT.get(m.group(1).lower().replace("marco", "março"))
                if mes:
                    result.competencia = f"{mes}/{m.group(2)}"
                result.detalhes["competencia_raw"] = m.group(0)

            result.codigo_barras = self._extract_barcode(texto)
            tem_cnpj = bool(self.RE_CNPJ.search(texto))
            result.detalhes["cnpj_validado"] = tem_cnpj

            score = 0.0
            if is_das:
                score += 0.30
            if result.valor and result.valor > 0:
                score += 0.30
            if result.vencimento:
                score += 0.20
            if result.competencia:
                score += 0.15
            if tem_cnpj:
                score += 0.05
            # Sem o marcador DAS nunca vira final (evita casar DARF/outros)
            result.confianca = round(min(score, 0.65) if not is_das else min(score, 1.0), 2)
            result.metodo_extracao = "regex_v1"
        except Exception as e:
            result.erro = str(e)[:200]
            result.confianca = 0.0
        return result


# TESTE INLINE — python3 -m modules.gedeon.onvio.pdf_extractor.das_extractor
if __name__ == "__main__":
    pdfs = sorted(Path("/app/uploads/onvio/das_simples_nacional").rglob("*.pdf"))
    print(f"=== DASExtractor ({len(pdfs)} PDFs) ===")
    ext = DASExtractor()
    ok = 0
    for p in pdfs:
        r = ext.extract(p)
        d = r.to_dict()
        print(f"{'✅' if d['confianca'] >= 0.70 else '❌'} {p.name[:50]:50} valor={d['valor']} venc={d['vencimento']} comp={d['competencia']} conf={d['confianca']}")
        if d["confianca"] >= 0.70:
            ok += 1
    taxa = ok / len(pdfs) if pdfs else 0
    print(f"\nUtilizáveis (≥0.70): {ok}/{len(pdfs)} = {taxa:.0%}")
    assert not pdfs or taxa >= 0.7, f"taxa {taxa:.0%} < 70%"
    print("✅ DASExtractor OK")
