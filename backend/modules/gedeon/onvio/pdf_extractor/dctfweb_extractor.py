"""
DCTFWebExtractor — Extrai dados de docs DCTFWeb (8 subtipos).

Estratégia: campos comuns + específicos por subtipo.
PDFs são texto nativo (pdfplumber sem OCR) — confirmado em produção.

Scoring (max 1.0):
  competencia:      +0.30
  numero_recibo:    +0.20
  data_transmissao: +0.15
  cnpj_validado:    +0.15
  (se subtipo com valor) tem_valores +0.10, valor_extraido +0.10
  (se subtipo sem valor) bonus +0.20
"""

from __future__ import annotations

import re
from pathlib import Path

from .base import BaseExtractor, ExtractionResult


class DCTFWebExtractor(BaseExtractor):
    TIPO = "dctfweb"

    SUBTIPOS_VALIDOS = {
        "declaracao",
        "recibo",
        "debitos",
        "creditos",
        "resumo_debitos",
        "resumo_creditos",
        "extrato",
        "situacao",
    }

    # Subtipos esperados ter valores monetários (com linha TOTAL ou tabela de valores)
    SUBTIPOS_COM_VALOR = {"debitos", "creditos", "resumo_debitos", "resumo_creditos"}

    # --- Regexes comuns ---

    # Período: "Período de Apuração 01/2026", "Período apuração 2025", sem espaço antes do valor
    RE_PERIODO = re.compile(
        r"per[íi]odo\s+(?:de\s+)?apura[çc][ãa]o\s*[:\s]*"
        r"(\d{1,2}/\d{4}|\d{4})(?!\d)",
        re.IGNORECASE,
    )
    # Período em extrato: "EXTRATO DO PROCESSAMENTO : Geral - 01/2026"
    #                 ou "EXTRATO DO PROCESSAMENTO : 13º Salário - 2025"
    RE_PERIODO_EXTRATO = re.compile(
        r"EXTRATO DO PROCESSAMENTO\s*:.*?-\s*(\d{1,2}/\d{4}|\d{4})(?!\d)",
        re.IGNORECASE,
    )

    # Recibo: "Número do Recibo 0000050000443648449", "Número Recibo0000050000443648449",
    #         "Nº do recibo de entrega0000050000443648449" (recibo PDF — final do doc)
    RE_RECIBO = re.compile(
        r"(?:N[úu]mero\s+(?:do\s+)?[Rr]ecibo|N[°º]\s*do\s+recibo\s+de\s+entrega)"
        r"\s*([0-9]{8,})",
        re.IGNORECASE,
    )

    # Data transmissão: "Data/Hora da Transmissão 18/02/2026", "Data da Transmissão18/02/2026",
    #                   "SERPRO em18/02/2026" (recibo PDF)
    RE_DT_TRANSMISSAO = re.compile(
        r"(?:Data(?:/Hora)?\s+da\s+Transmiss[ãa]o|SERPRO\s+em)"
        r"\s*(\d{1,2}/\d{1,2}/\d{2,4})",
        re.IGNORECASE,
    )

    #: CNPJ do CONTRIBUINTE, capturado — não conferido contra um número cravado.
    #:
    #: Era `re.compile(r"35[\.\s]*710[\.\s]*481[/\s]*0001[-\s]*03")`: a Eletrônica, e só ela.
    #: Uma DCTFWeb da Patrimonial perderia os 0.20 de confiança por "não ter CNPJ" quando na
    #: verdade tem o CNPJ ERRADO para o regex — e pode cair abaixo do corte e ser descartada.
    #:
    #: Quarto lugar da casa com identificador de empresa cravado no código, e o último dos
    #: quatro a ser fechado (os outros: `sped_manager.py:681` — quarentenado —,
    #: `fgts_extractor.py:37` e o `_empresa_id` do ECD).
    #:
    #: Capturar em vez de conferir é o que permite ATRIBUIR o documento ao CNPJ certo lá na
    #: frente: `baixa_por_recibo_onvio` hoje tira o CNPJ do NOME do arquivo porque aqui só
    #: sobrava um booleano. Com o número em `detalhes["cnpj_contribuinte"]`, ele passa a
    #: preferir o que está DENTRO do documento.
    RE_CNPJ = re.compile(r"(?<!\d)(\d{2}[.\s]?\d{3}[.\s]?\d{3}[/\s]?\d{4}[-\s]?\d{2})(?!\d)")

    # Qualquer valor monetário (sinal de que o doc tem dados financeiros)
    RE_QUALQUER_VALOR = re.compile(r"R\$\s*[\d]+[.,][\d]+|[\d]+\.[\d]{3},[\d]{2}")

    # Linha TOTAL explícita (ex: "TOTAL R$ 32.277,82 R$ 14.604,94" no recibo)
    RE_VALOR_TOTAL = re.compile(
        r"(?:total\s+(?:geral|dos?\s+d[ée]bitos|apurado|a\s+pagar)?)"
        r"\s+R?\$?\s*([\d\.,]+)",
        re.IGNORECASE,
    )

    # Vencimento
    RE_VENCIMENTO = re.compile(r"vencimento[:\s]*(\d{1,2}/\d{1,2}/\d{2,4})", re.IGNORECASE)

    def __init__(self, subtipo: str = "declaracao") -> None:
        if subtipo not in self.SUBTIPOS_VALIDOS:
            raise ValueError(f"subtipo '{subtipo}' inválido. Válidos: {sorted(self.SUBTIPOS_VALIDOS)}")
        self.subtipo = subtipo
        self.TIPO = f"dctfweb_{subtipo}"

    def extract(self, pdf_path: Path) -> ExtractionResult:
        result = ExtractionResult(tipo=self.TIPO)

        try:
            texto = self._read_pdf_text(pdf_path)
            if not texto.strip():
                result.erro = "PDF vazio ou ilegível"
                return result

            result.detalhes["texto_len"] = len(texto)
            result.detalhes["subtipo"] = self.subtipo

            # --- Período de apuração ---
            m = self.RE_PERIODO.search(texto)
            if not m and self.subtipo == "extrato":
                m = self.RE_PERIODO_EXTRATO.search(texto)
            if m:
                result.competencia = m.group(1)

            # --- Número do recibo ---
            m = self.RE_RECIBO.search(texto)
            if m:
                result.detalhes["numero_recibo"] = m.group(1).lstrip("0") or m.group(1)

            # --- Data de transmissão ---
            m = self.RE_DT_TRANSMISSAO.search(texto)
            if m:
                result.detalhes["data_transmissao"] = m.group(1)

            # --- CNPJ do contribuinte ---
            # O primeiro CNPJ do documento é o do CONTRIBUINTE: a RFB imprime
            # "Nome do Contribuinte / CNPJ" no cabeçalho, antes do CNPJ do escritório que
            # transmitiu (PORTTE CONTABIL, 29.243.860/0001-38, aparece depois).
            m = self.RE_CNPJ.search(texto)
            cnpj = "".join(d for d in m.group(1) if d.isdigit()) if m else None
            if cnpj:
                result.detalhes["cnpj_contribuinte"] = cnpj
            tem_cnpj = bool(cnpj)
            result.detalhes["cnpj_validado"] = tem_cnpj

            # --- Vencimento (opcional) ---
            m = self.RE_VENCIMENTO.search(texto)
            if m:
                result.vencimento = self._safe_date(m.group(1))

            # --- Valores monetários ---
            tem_valores = bool(self.RE_QUALQUER_VALOR.search(texto))
            result.detalhes["tem_valores"] = tem_valores

            if self.subtipo in self.SUBTIPOS_COM_VALOR and tem_valores:
                m = self.RE_VALOR_TOTAL.search(texto)
                if m:
                    result.valor = self._safe_decimal(m.group(1))
                    result.detalhes["valor_raw"] = m.group(1)

            # --- Confiança ---
            score = 0.0
            if result.competencia:
                score += 0.30
            if result.detalhes.get("numero_recibo"):
                score += 0.20
            if result.detalhes.get("data_transmissao"):
                score += 0.15
            if tem_cnpj:
                score += 0.15

            if self.subtipo in self.SUBTIPOS_COM_VALOR:
                if tem_valores:
                    score += 0.10
                if result.valor and result.valor > 0:
                    score += 0.10
            else:
                score += 0.20  # bonus: doc não requer extração monetária

            result.confianca = round(min(score, 1.0), 2)
            result.metodo_extracao = "regex_v1"

        except Exception as e:
            result.erro = str(e)[:200]
            result.confianca = 0.0

        return result


# Mapeamento: padrão no filename → subtipo (para testes __main__)
_FILENAME_SUBTIPOS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"ResumoDebitos|Resumo.?Debitos", re.IGNORECASE), "resumo_debitos"),
    (re.compile(r"ResumoCreditos|Resumo.?Creditos", re.IGNORECASE), "resumo_creditos"),
    (re.compile(r"DeclaracaoCompleta|Declaracao.Completa", re.IGNORECASE), "declaracao"),
    (re.compile(r"RelatorioExtrato|Relatorio.Extrato", re.IGNORECASE), "extrato"),
    (re.compile(r"SituacaoFiscal|Situa[çc][ãa]oFiscal|Situa[çc][ãa]o", re.IGNORECASE), "situacao"),
    (re.compile(r"DCTFWEB\s+Recibo[_\s]", re.IGNORECASE), "recibo"),
    (re.compile(r"Debitos[_\s]", re.IGNORECASE), "debitos"),
    (re.compile(r"Creditos[^R]", re.IGNORECASE), "creditos"),
]


def _detectar_subtipo(nome: str) -> str | None:
    for padrao, subtipo in _FILENAME_SUBTIPOS:
        if padrao.search(nome):
            return subtipo
    return None


if __name__ == "__main__":
    from pathlib import Path

    # Coletar todos os PDFs DCTFWeb
    raiz = Path("/app/uploads/onvio")
    todos_pdfs = [p for p in raiz.rglob("*.pdf") if "dctf" in p.name.lower() or "DCTF" in p.name]

    por_subtipo: dict[str, list[Path]] = {}
    sem_subtipo: list[Path] = []
    for pdf in todos_pdfs:
        sub = _detectar_subtipo(pdf.name)
        if sub:
            por_subtipo.setdefault(sub, []).append(pdf)
        else:
            sem_subtipo.append(pdf)

    print(f"Total PDFs DCTFWeb: {len(todos_pdfs)}")
    for sub, pdfs in sorted(por_subtipo.items()):
        print(f"  {sub}: {len(pdfs)}")
    if sem_subtipo:
        print(f"  (sem_subtipo): {len(sem_subtipo)} — {[p.name for p in sem_subtipo]}")

    total = 0
    aceitaveis = 0

    for subtipo in sorted(SUBTIPOS_VALIDOS := DCTFWebExtractor.SUBTIPOS_VALIDOS):
        pdfs = por_subtipo.get(subtipo, [])
        print(f"\n{'=' * 60}")
        print(f"SUBTIPO: {subtipo} ({len(pdfs)} PDFs)")
        print("=" * 60)

        if not pdfs:
            print("  (sem PDFs)")
            continue

        extractor = DCTFWebExtractor(subtipo=subtipo)
        for pdf in sorted(pdfs):
            r = extractor.extract(pdf)
            d = r.to_dict()
            ok = "✅" if r.confianca >= 0.70 else ("⚠️" if r.confianca >= 0.50 else "❌")
            print(
                f"\n  {ok} {pdf.name[:55]}"
                f"\n     competência:     {d['competencia']}"
                f"\n     valor:           {d['valor']}"
                f"\n     recibo:          {d['detalhes'].get('numero_recibo')}"
                f"\n     data_transmissao:{d['detalhes'].get('data_transmissao')}"
                f"\n     cnpj_validado:   {d['detalhes'].get('cnpj_validado')}"
                f"\n     tem_valores:     {d['detalhes'].get('tem_valores')}"
                f"\n     confiança:       {d['confianca']}"
                + (f"\n     ERRO:            {d['erro']}" if d["erro"] else "")
            )
            if r.confianca >= 0.70:
                aceitaveis += 1
        total += len(pdfs)

    print(f"\n{'=' * 60}")
    print(f"RESUMO: {total} PDFs | Aceitáveis (>=0.70): {aceitaveis}")
    if total > 0:
        taxa = aceitaveis / total
        print(f"Taxa: {taxa:.0%} (meta: >=60%)")
        assert taxa >= 0.60, f"Taxa {taxa:.0%} abaixo da meta de 60%"
        print("\n✅ DCTFWebExtractor APROVADO")
    else:
        print("❌ NENHUM PDF encontrado")
