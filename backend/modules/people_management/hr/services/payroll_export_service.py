"""
Serviço de Exportação de Folha — Domínio Sistemas + PDF Contracheque.

Exporta folha de pagamento no formato texto para o sistema Domínio (TOTVS)
e gera contracheques em PDF usando reportlab.
"""

import io
import logging
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from modules.crm.services import pdf_branding as B

logger = logging.getLogger(__name__)


class PayrollExportService:
    """Exporta folha para Domínio Sistemas (TOTVS) e gera PDF contracheque."""

    # === EXPORT DOMÍNIO SISTEMAS (TOTVS) ===

    @staticmethod
    def export_dominio(folha_data: list[dict], competencia: str, empresa_cnpj: str = "35.710.481/0001-03") -> str:
        """Exporta folha no formato texto para Domínio Sistemas.

        Formato: pipe-delimited, encoding latin-1, campos fixos conforme layout Domínio.

        Args:
            folha_data: Lista de dicionários com dados da folha por funcionário.
            competencia: Mês/ano no formato MM/YYYY.
            empresa_cnpj: CNPJ da empresa.

        Returns:
            String com conteúdo do arquivo texto para importação.
        """
        lines = []
        # Header
        lines.append(f"DOMINIO|FOLHA|{competencia}|{empresa_cnpj}|{datetime.now().strftime('%d/%m/%Y %H:%M')}")

        for idx, emp in enumerate(folha_data, 1):
            # Linha do funcionário
            matricula = emp.get("matricula", str(idx).zfill(6))
            nome = emp.get("employee_name", "").upper()[:40].ljust(40)
            cpf = emp.get("cpf", "").replace(".", "").replace("-", "").ljust(11)
            cargo = emp.get("cargo", "").upper()[:30].ljust(30)
            salario_base = _fmt_valor(emp.get("salario_base", 0))
            total_proventos = _fmt_valor(emp.get("total_proventos", 0))
            total_descontos = _fmt_valor(emp.get("total_descontos", 0))
            liquido = _fmt_valor(emp.get("salario_liquido", 0))
            fgts = _fmt_valor(emp.get("fgts_8_pct", 0))
            base_inss = _fmt_valor(emp.get("base_inss", 0))
            base_irrf = _fmt_valor(emp.get("base_irrf", 0))

            lines.append(
                f"F|{matricula}|{cpf}|{nome}|{cargo}|{salario_base}|"
                f"{total_proventos}|{total_descontos}|{liquido}|{fgts}|{base_inss}|{base_irrf}"
            )

            # Linhas de proventos
            for prov in emp.get("proventos", []):
                lines.append(
                    f"P|{matricula}|{prov['codigo']}|{prov['descricao'][:30].ljust(30)}|"
                    f"{prov.get('ref', '').ljust(10)}|{_fmt_valor(prov['valor'])}"
                )

            # Linhas de descontos
            for desc in emp.get("descontos", []):
                lines.append(
                    f"D|{matricula}|{desc['codigo']}|{desc['descricao'][:30].ljust(30)}|"
                    f"{desc.get('ref', '').ljust(10)}|{_fmt_valor(desc['valor'])}"
                )

        # Footer
        total_geral_prov = sum(emp.get("total_proventos", 0) for emp in folha_data)
        total_geral_desc = sum(emp.get("total_descontos", 0) for emp in folha_data)
        total_geral_liq = sum(emp.get("salario_liquido", 0) for emp in folha_data)
        lines.append(
            f"T|{len(folha_data)}|{_fmt_valor(total_geral_prov)}|"
            f"{_fmt_valor(total_geral_desc)}|{_fmt_valor(total_geral_liq)}"
        )

        logger.info(
            "Exportação Domínio gerada: %d funcionários, competência %s",
            len(folha_data),
            competencia,
        )
        return "\n".join(lines)

    # === PDF CONTRACHEQUE (HOLERITE) ===

    @staticmethod
    def gerar_contracheque_pdf(
        folha_emp: dict,
        empresa_nome: str = "Conecta Mais Patrimonial",
        empresa_cnpj: str = "35.710.481/0001-03",
    ) -> bytes:
        """Gera PDF do contracheque (holerite) de um funcionário.

        Layout padrão trabalhista com:
        - Cabeçalho da empresa
        - Dados do funcionário
        - Tabela de proventos e descontos
        - Totais e FGTS informativo
        - Rodapé com assinatura

        Args:
            folha_emp: Dicionário com dados da folha do funcionário.
            empresa_nome: Nome da empresa.
            empresa_cnpj: CNPJ da empresa.

        Returns:
            Bytes do PDF gerado.
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=15 * mm,
            rightMargin=15 * mm,
            topMargin=42 * mm,
            bottomMargin=22 * mm,
        )

        styles = getSampleStyleSheet()
        styles.add(
            ParagraphStyle(
                name="Header",
                fontSize=14,
                leading=18,
                spaceAfter=6,
                fontName="Helvetica-Bold",
            )
        )
        styles.add(
            ParagraphStyle(
                name="SubHeader",
                fontSize=9,
                leading=12,
                textColor=colors.grey,
            )
        )
        styles.add(
            ParagraphStyle(
                name="SmallText",
                fontSize=8,
                leading=10,
            )
        )

        elements = []

        # (a marca e o título "CONTRACHEQUE" são desenhados no topo da página por B.header_footer)

        # === DADOS FUNCIONÁRIO ===
        ref = folha_emp.get("reference", "")
        emp_name = folha_emp.get("employee_name", "Funcionário")
        cargo = folha_emp.get("cargo", "")
        elements.append(Paragraph(f"<b>RECIBO DE PAGAMENTO — {ref}</b>", styles["Normal"]))
        elements.append(Spacer(1, 3 * mm))

        info_data = [
            ["Funcionário:", emp_name, "Cargo:", cargo],
            ["Referência:", ref, "Salário Base:", f"R$ {folha_emp.get('salario_base', 0):,.2f}"],
        ]
        info_table = Table(info_data, colWidths=[70, 200, 70, 120])
        info_table.setStyle(
            TableStyle(
                [
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        elements.append(info_table)
        elements.append(Spacer(1, 5 * mm))

        # === TABELA PROVENTOS/DESCONTOS ===
        header = ["Cód", "Descrição", "Ref", "Proventos (R$)", "Descontos (R$)"]
        table_data = [header]

        proventos = folha_emp.get("proventos", [])
        descontos = folha_emp.get("descontos", [])

        for p in proventos:
            table_data.append(
                [
                    p.get("codigo", ""),
                    p.get("descricao", ""),
                    p.get("ref", ""),
                    f"{p['valor']:,.2f}",
                    "",
                ]
            )

        for d in descontos:
            table_data.append(
                [
                    d.get("codigo", ""),
                    d.get("descricao", ""),
                    d.get("ref", ""),
                    "",
                    f"{d['valor']:,.2f}",
                ]
            )

        # Totals row
        table_data.append(
            [
                "",
                "TOTAIS",
                "",
                f"{folha_emp.get('total_proventos', 0):,.2f}",
                f"{folha_emp.get('total_descontos', 0):,.2f}",
            ]
        )

        t = Table(table_data, colWidths=[35, 180, 50, 85, 85])
        t.setStyle(
            TableStyle(
                [
                    # Header
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 8),
                    ("ALIGN", (3, 0), (4, -1), "RIGHT"),
                    # Body
                    ("FONTSIZE", (0, 1), (-1, -1), 7),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    # Totals row
                    ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f0f0f0")),
                    ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ]
            )
        )
        elements.append(t)
        elements.append(Spacer(1, 5 * mm))

        # === LÍQUIDO + FGTS ===
        liquido = folha_emp.get("salario_liquido", 0)
        fgts = folha_emp.get("fgts_8_pct", 0)
        base_inss = folha_emp.get("base_inss", 0)
        base_irrf = folha_emp.get("base_irrf", 0)

        summary_data = [
            ["SALÁRIO LÍQUIDO:", f"R$ {liquido:,.2f}", "FGTS (8%):", f"R$ {fgts:,.2f}"],
            ["Base INSS:", f"R$ {base_inss:,.2f}", "Base IRRF:", f"R$ {base_irrf:,.2f}"],
        ]
        summary = Table(summary_data, colWidths=[100, 120, 80, 120])
        summary.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (0, 0), "Helvetica-Bold"),
                    ("FONTNAME", (2, 0), (2, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("BACKGROUND", (0, 0), (1, 0), colors.HexColor("#e8f5e9")),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        elements.append(summary)
        elements.append(Spacer(1, 15 * mm))

        # === RODAPÉ ===
        elements.append(Paragraph("_" * 60, styles["SmallText"]))
        elements.append(Paragraph("Assinatura do Funcionário", styles["SmallText"]))
        elements.append(Spacer(1, 5 * mm))
        elements.append(
            Paragraph(
                f"Documento gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')} — Conecta PRO ERP",
                styles["SmallText"],
            )
        )

        doc.build(
            elements,
            onFirstPage=lambda cv, dc: B.header_footer(cv, dc, titulo="CONTRACHEQUE"),
            onLaterPages=lambda cv, dc: B.header_footer(cv, dc, titulo="CONTRACHEQUE"),
        )
        pdf_bytes = buffer.getvalue()
        buffer.close()

        logger.info(
            "Contracheque PDF gerado: %s, ref %s, %d bytes",
            emp_name,
            ref,
            len(pdf_bytes),
        )
        return pdf_bytes

    @staticmethod
    def gerar_contracheques_batch(
        folha_data: list[dict],
        empresa_nome: str = "Conecta Mais Patrimonial",
        empresa_cnpj: str = "35.710.481/0001-03",
    ) -> dict[str, bytes]:
        """Gera contracheques PDF para múltiplos funcionários.

        Args:
            folha_data: Lista de dicionários com dados da folha.
            empresa_nome: Nome da empresa.
            empresa_cnpj: CNPJ da empresa.

        Returns:
            Dicionário {employee_id: pdf_bytes}.
        """
        results: dict[str, bytes] = {}
        for emp in folha_data:
            emp_id = emp.get("employee_id", "unknown")
            try:
                pdf = PayrollExportService.gerar_contracheque_pdf(emp, empresa_nome, empresa_cnpj)
                results[emp_id] = pdf
            except Exception as e:
                logger.error("Erro ao gerar contracheque para %s: %s", emp_id, e)
        logger.info("Batch contracheques: %d/%d gerados", len(results), len(folha_data))
        return results


def _fmt_valor(valor: Any) -> str:
    """Formata valor numérico para string com 2 casas decimais."""
    try:
        return f"{float(valor):.2f}"
    except (TypeError, ValueError):
        return "0.00"
