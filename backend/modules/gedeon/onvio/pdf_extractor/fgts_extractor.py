"""
FGTSExtractor — Extrai dados de guias e relatórios FGTS (GFD - Guia do FGTS Digital).
Suporta 4 subtipos: guia, consignado, relatorio, consignado_relatorio.
"""

from __future__ import annotations

import re
from pathlib import Path

from .base import BaseExtractor, ExtractionResult


class FGTSExtractor(BaseExtractor):
    TIPO = "fgts"
    SUBTIPOS_VALIDOS = {"guia", "consignado", "relatorio", "consignado_relatorio"}

    # "Total da Guia: 6.009,93" / "Total da Guia (FGTS): 5.803,72" / "Total da Guia (Consignado): 5.222,96"
    RE_VALOR = re.compile(r"Total\s+da\s+Guia[^:\n]*:\s*([\d\.\,]+)", re.IGNORECASE)

    # Guia: "Razão Social do Empregador 20/03/2026" | Relatório: "Vencimento da Guia: 20/10/2025"
    RE_VENCIMENTO = re.compile(
        r"(?:Vencimento\s+da\s+Guia:\s*|Razão\s+Social\s+do\s+Empregador\s+)(\d{1,2}/\d{1,2}/\d{2,4})",
        re.IGNORECASE,
    )

    # MM/YYYY: mês válido (01-12) + lookbehind bloqueia padrão embarcado em CNPJ ("860/0001")
    # ou dentro de DD/MM/YYYY ("13/03/2026" → bloqueia ao ver "/" antes de "03")
    RE_COMPETENCIA = re.compile(r"(?<![/\d])((?:0[1-9]|1[0-2])/\d{4})\b")

    # Marcador que identifica documento GFD (diferencia de INSS, DAR, etc.)
    RE_GFD = re.compile(
        r"(?:GFD\b|Guia\s+do\s+FGTS\s+Digital|Detalhe\s+da\s+Guia\s+Emitida)",
        re.IGNORECASE,
    )

    #: CNPJ do EMPREGADOR, capturado — não conferido contra um número cravado.
    #:
    #: Era `re.compile(r"35[\.\s]*710[\.\s]*481")`: a Eletrônica, e só ela. Uma guia da
    #: Patrimonial perdia os 0.10 de confiança por "não ter CNPJ", quando na verdade tinha
    #: o CNPJ ERRADO para o regex — e podia cair abaixo do corte e ser descartada. Medido em
    #: 14/08/2026, é o quarto lugar da casa com identificador de empresa cravado no código
    #: (os outros: `sped_manager.py:681`, `dctfweb_extractor.py:73` e o `_empresa_id` do ECD).
    #:
    #: Capturar em vez de conferir também é o que torna possível ATRIBUIR a guia ao CNPJ
    #: certo lá na frente: hoje `fgts_guias` não tem coluna de CNPJ e ninguém sabe de quem é
    #: a guia sem abrir o PDF de novo. O número vai para `detalhes["cnpj_empregador"]`.
    #:
    #: A GFD imprime o empregador sem os 6 dígitos finais ("35.710.481"), então aceita-se a
    #: raiz de 8 dígitos; quando o documento traz o CNPJ inteiro, guarda-se inteiro.
    RE_CNPJ = re.compile(r"\b(\d{2}[.\s]?\d{3}[.\s]?\d{3})(?:[/\s]?(\d{4})[-\s]?(\d{2}))?\b")

    def __init__(self, subtipo: str = "guia"):
        if subtipo not in self.SUBTIPOS_VALIDOS:
            raise ValueError(f"subtipo '{subtipo}' inválido. Válidos: {self.SUBTIPOS_VALIDOS}")
        self.subtipo = subtipo
        self.TIPO = f"fgts_{subtipo}"

    def extract(self, pdf_path: Path) -> ExtractionResult:
        result = ExtractionResult(tipo=self.TIPO)
        try:
            texto = self._read_pdf_text(pdf_path)
            if not texto:
                result.erro = "PDF vazio"
                return result

            result.detalhes["texto_len"] = len(texto)
            result.detalhes["subtipo"] = self.subtipo

            # Marcador GFD — principal diferenciador vs. INSS/DAR/outros
            is_gfd = bool(self.RE_GFD.search(texto))
            result.detalhes["is_gfd"] = is_gfd

            # Valor: padrão unificado para os 4 subtipos
            m = self.RE_VALOR.search(texto)
            if m:
                result.valor = self._safe_decimal(m.group(1))
                result.detalhes["valor_raw"] = m.group(1)

            # Vencimento
            m = self.RE_VENCIMENTO.search(texto)
            if m:
                result.vencimento = self._safe_date(m.group(1))
                result.detalhes["vencimento_raw"] = m.group(1)

            # Competência (MM/YYYY) — lookbehind evita capturar parte de DD/MM/YYYY
            m = self.RE_COMPETENCIA.search(texto)
            if m:
                result.competencia = m.group(1)

            # O CNPJ do EMPREGADOR é o primeiro do documento: a GFD imprime
            # "CPF/CNPJ do Empregador" antes de qualquer outro (o da Caixa e o do escritório
            # de contabilidade que emitiu vêm depois).
            m = self.RE_CNPJ.search(texto)
            cnpj = None
            if m:
                cnpj = "".join(d for d in "".join(g or "" for g in m.groups()) if d.isdigit())
                result.detalhes["cnpj_empregador"] = cnpj
            tem_cnpj = bool(cnpj)

            # GFD usa PIX — código de barras de boleto geralmente ausente, mas tentamos
            result.codigo_barras = self._extract_barcode(texto)
            # Boleto de arrecadação FGTS começa com 8 — alertar se diferente
            if result.codigo_barras and not result.codigo_barras.startswith("8"):
                result.detalhes["barcode_alerta"] = "não começa com 8 (esperado para FGTS)"

            # Confiança
            score = 0.0
            if is_gfd:
                score += 0.20
            if result.valor and result.valor > 0:
                score += 0.40
            if result.vencimento:
                score += 0.20
            if result.competencia:
                score += 0.10
            if tem_cnpj:
                score += 0.10
            result.confianca = round(min(score, 1.0), 2)
            result.metodo_extracao = "regex_v1"

        except Exception as e:
            result.erro = str(e)[:200]
            result.confianca = 0.0

        return result


# TESTES INLINE — rodar com: python3 -m modules.gedeon.onvio.pdf_extractor.fgts_extractor
if __name__ == "__main__":
    import asyncio

    from sqlalchemy import text

    from core.database.session import async_session_factory

    MAPA_SUBTIPO = {
        "fgts_guia": "guia",
        "fgts_consignado": "consignado",
        "fgts_relatorio": "relatorio",
        "fgts_consignado_relatorio": "consignado_relatorio",
    }

    async def main() -> None:
        async with async_session_factory() as session:
            total_pdfs = 0
            total_utilizaveis = 0

            for categoria, subtipo in MAPA_SUBTIPO.items():
                result = await session.execute(
                    text(
                        "SELECT caminho_local, nome_arquivo FROM onvio_documents WHERE categoria = :cat ORDER BY nome_arquivo"
                    ),
                    {"cat": categoria},
                )
                rows = result.fetchall()
                print(f"\n{'=' * 60}")
                print(f"SUBTIPO: {subtipo} ({len(rows)} PDFs)")
                print("=" * 60)

                extractor = FGTSExtractor(subtipo=subtipo)
                sucessos = 0
                aceitaveis = 0

                for caminho_local, nome_arquivo in rows:
                    p = Path(caminho_local)
                    r = extractor.extract(p)
                    d = r.to_dict()

                    existe = p.exists()
                    icon = "✅" if d["confianca"] >= 0.90 else ("⚠️ " if d["confianca"] >= 0.70 else "❌")
                    print(f"\n{icon} {nome_arquivo[:55]}")
                    print(f"   existe:        {existe}")
                    print(f"   valor:         {d['valor']}")
                    print(f"   vencimento:    {d['vencimento']}")
                    print(f"   competência:   {d['competencia']}")
                    print(f"   confiança:     {d['confianca']}")
                    if d["erro"]:
                        print(f"   ❌ erro:       {d['erro']}")
                    if d["confianca"] >= 0.90:
                        sucessos += 1
                        aceitaveis += 1
                    elif d["confianca"] >= 0.70:
                        aceitaveis += 1

                total_pdfs += len(rows)
                total_utilizaveis += aceitaveis
                print(f"\n  Sucessos (≥0.90): {sucessos}/{len(rows)} | Aceitáveis (≥0.70): {aceitaveis}/{len(rows)}")

            print(f"\n\n{'=' * 60}")
            print("RESUMO GERAL")
            print("=" * 60)
            print(f"Total PDFs:           {total_pdfs}")
            print(f"Utilizáveis (≥0.70):  {total_utilizaveis}")
            taxa = total_utilizaveis / total_pdfs if total_pdfs else 0
            print(f"Taxa:                 {taxa:.0%} (meta: ≥70%)")
            assert taxa >= 0.70, f"Taxa {taxa:.0%} abaixo de 70% — NÃO commitar"
            print("\n✅ FGTSExtractor APROVADO")

    asyncio.run(main())
