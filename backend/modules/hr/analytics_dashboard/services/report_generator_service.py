"""Service para geração de relatórios."""

import csv
import io
import json
import logging
import random  # noqa: S311
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from modules.hr.analytics_dashboard.models import (
    ReportFormat,
    ReportType,
    ScheduledReport,
)
from modules.hr.analytics_dashboard.repositories import ReportRepository
from modules.hr.analytics_dashboard.schemas import (
    ReportRunResponse,
)

logger = logging.getLogger(__name__)


class ReportGeneratorService:
    """Service para geração de relatórios."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.report_repo = ReportRepository(db)

    async def generate_report(
        self,
        report: ScheduledReport,
        period_start: datetime = None,
        period_end: datetime = None,
        output_format: ReportFormat = None,
    ) -> ReportRunResponse:
        """Gera um relatório."""
        run_id = uuid4()
        started_at = datetime.utcnow()

        try:
            # Determinar período
            if not period_start or not period_end:
                period_start, period_end = self._calculate_period(report)

            # Usar formato especificado ou padrão do relatório
            format_to_use = output_format or ReportFormat(report.output_format)

            # Coletar dados
            data = await self._collect_report_data(
                report=report,
                period_start=period_start,
                period_end=period_end,
            )

            # Gerar arquivo
            file_content, file_size = await self._generate_file(
                report=report,
                data=data,
                output_format=format_to_use,
            )

            # Salvar arquivo
            file_path = await self._save_file(
                report_id=report.id,
                run_id=run_id,
                content=file_content,
                output_format=format_to_use,
            )

            completed_at = datetime.utcnow()
            generation_time = int((completed_at - started_at).total_seconds() * 1000)

            # Registrar execução
            await self.report_repo.record_run(
                report_id=report.id,
                success=True,
                file_path=file_path,
                file_size=file_size,
                duration_ms=generation_time,
            )

            return ReportRunResponse(
                report_id=report.id,
                run_id=run_id,
                status="success",
                file_path=file_path,
                file_size_bytes=file_size,
                download_url=f"/api/v1/analytics/reports/{report.id}/download/{run_id}",
                generation_time_ms=generation_time,
                started_at=started_at,
                completed_at=completed_at,
            )

        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as e:
            logger.error("Erro ao gerar relatório %s: %s", report.id, e)

            completed_at = datetime.utcnow()
            generation_time = int((completed_at - started_at).total_seconds() * 1000)

            await self.report_repo.record_run(
                report_id=report.id,
                success=False,
                error=str(e),
                duration_ms=generation_time,
            )

            return ReportRunResponse(
                report_id=report.id,
                run_id=run_id,
                status="failed",
                file_path=None,
                file_size_bytes=None,
                download_url=None,
                generation_time_ms=generation_time,
                started_at=started_at,
                completed_at=completed_at,
            )

    def _calculate_period(
        self,
        report: ScheduledReport,
    ) -> tuple:
        """Calcula período do relatório."""
        now = datetime.utcnow()

        if report.period_type == "previous_day":
            end = now.replace(hour=0, minute=0, second=0, microsecond=0)
            start = end - timedelta(days=1)

        elif report.period_type == "previous_week":
            # Início da semana passada
            days_since_monday = now.weekday()
            end = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_since_monday)
            start = end - timedelta(weeks=1)

        elif report.period_type == "previous_month":
            # Primeiro dia do mês atual
            end = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            # Primeiro dia do mês anterior
            start = (end - timedelta(days=1)).replace(day=1)

        elif report.period_type == "previous_quarter":
            current_quarter = (now.month - 1) // 3
            end_month = current_quarter * 3 + 1
            end = now.replace(month=end_month, day=1, hour=0, minute=0, second=0, microsecond=0)
            start = (end - timedelta(days=1)).replace(day=1)
            start = start.replace(month=((start.month - 1) // 3) * 3 + 1)

        elif report.period_type.startswith("rolling_"):
            days = int(report.period_type.split("_")[1])
            end = now
            start = now - timedelta(days=days)

        elif report.period_type == "custom":
            start = report.custom_period_start or now - timedelta(days=30)
            end = report.custom_period_end or now

        else:
            # Default: último mês
            end = now
            start = now - timedelta(days=30)

        return start, end

    async def _collect_report_data(
        self,
        report: ScheduledReport,
        period_start: datetime,
        period_end: datetime,
    ) -> dict[str, Any]:
        """Coleta dados para o relatório."""
        # Simulação de coleta de dados baseado no tipo de relatório
        data = {
            "report_name": report.name,
            "report_type": report.report_type,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "generated_at": datetime.utcnow().isoformat(),
        }

        if report.report_type == ReportType.ATTENDANCE.value:
            data["summary"] = {
                "total_employees": random.randint(80, 120),  # noqa: S311
                "present_days": random.randint(1800, 2200),  # noqa: S311
                "absent_days": random.randint(50, 100),  # noqa: S311
                "late_entries": random.randint(30, 80),  # noqa: S311
                "attendance_rate": round(random.uniform(94, 98), 2),  # noqa: S311
            }
            data["details"] = [
                {
                    "employee_id": f"emp_{i}",
                    "name": f"Funcionário {i}",
                    "department": random.choice(["TI", "RH", "Financeiro"]),  # noqa: S311
                    "present_days": random.randint(18, 22),  # noqa: S311
                    "absent_days": random.randint(0, 3),  # noqa: S311
                    "late_count": random.randint(0, 5),  # noqa: S311
                }
                for i in range(1, 21)
            ]

        elif report.report_type == ReportType.OVERTIME.value:
            data["summary"] = {
                "total_overtime_hours": round(random.uniform(200, 500), 1),  # noqa: S311
                "total_cost": round(random.uniform(15000, 35000), 2),  # noqa: S311
                "employees_with_overtime": random.randint(30, 60),  # noqa: S311
                "avg_overtime_per_employee": round(random.uniform(5, 15), 1),  # noqa: S311
            }
            data["by_department"] = [
                {
                    "department": dept,
                    "hours": round(random.uniform(30, 100), 1),  # noqa: S311
                    "cost": round(random.uniform(2000, 8000), 2),  # noqa: S311
                }
                for dept in ["TI", "RH", "Financeiro", "Operações"]
            ]

        elif report.report_type == ReportType.COMPLIANCE.value:
            data["summary"] = {
                "compliance_rate": round(random.uniform(95, 100), 2),  # noqa: S311
                "violations_count": random.randint(0, 10),  # noqa: S311
                "warnings_count": random.randint(5, 20),  # noqa: S311
            }
            data["violations"] = [
                {
                    "type": random.choice(["intervalo_minimo", "jornada_maxima", "descanso_semanal"]),  # noqa: S311
                    "employee_id": f"emp_{random.randint(1, 100)}",  # noqa: S311
                    "date": (period_start + timedelta(days=random.randint(0, 30))).isoformat(),  # noqa: S311
                    "description": "Violacao de regra CLT",
                }
                for _ in range(random.randint(0, 5))  # noqa: S311
            ]

        else:
            # Relatório genérico
            data["summary"] = {
                "records_count": random.randint(100, 500),  # noqa: S311
                "status": "completed",
            }

        return data

    async def _generate_file(
        self,
        report: ScheduledReport,
        data: dict[str, Any],
        output_format: ReportFormat,
    ) -> tuple:
        """Gera arquivo do relatório."""
        if output_format == ReportFormat.JSON:
            return self._generate_json(data)
        if output_format == ReportFormat.CSV:
            return self._generate_csv(data)
        if output_format == ReportFormat.EXCEL:
            return self._generate_excel(data, report.name)
        if output_format == ReportFormat.PDF:
            return self._generate_pdf(data, report)
        return self._generate_json(data)

    def _generate_json(self, data: dict[str, Any]) -> tuple:
        """Gera arquivo JSON."""
        content = json.dumps(data, indent=2, ensure_ascii=False)
        return content.encode("utf-8"), len(content)

    def _generate_csv(self, data: dict[str, Any]) -> tuple:
        """Gera arquivo CSV."""

        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        if "details" in data and data["details"]:
            headers = list(data["details"][0].keys())
            writer.writerow(headers)
            for row in data["details"]:
                writer.writerow([row.get(h, "") for h in headers])
        elif "summary" in data:
            writer.writerow(["Métrica", "Valor"])
            for key, value in data["summary"].items():
                writer.writerow([key, value])

        content = output.getvalue()
        return content.encode("utf-8"), len(content)

    def _generate_excel(self, data: dict[str, Any], report_name: str) -> tuple:
        """Gera arquivo Excel."""
        # Simulação - em produção usaria openpyxl ou xlsxwriter
        content = f"Excel file content for: {report_name}\n"
        content += f"Data: {data}\n"
        return content.encode("utf-8"), len(content)

    def _generate_pdf(self, data: dict[str, Any], report: ScheduledReport) -> tuple:
        """Gera arquivo PDF no padrão visual oficial Conecta Mais (header/footer + selo)."""
        try:
            content = self._render_pdf_branded(data, report)
        except Exception:  # noqa: BLE001 - nunca quebrar a geração de relatório
            logger.exception("Falha ao gerar PDF branded; usando fallback texto")
            fallback = f"PDF Report: {report.name}\n"
            fallback += f"Type: {report.report_type}\n"
            fallback += f"Generated: {datetime.utcnow().isoformat()}\n"
            fallback += f"Data Summary: {data.get('summary', {})}\n"
            content = fallback.encode("utf-8")
        return content, len(content)

    def _render_pdf_branded(self, data: dict[str, Any], report: ScheduledReport) -> bytes:
        """Monta o PDF com a marca Conecta Mais (capa institucional + resumo dos dados)."""
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Image,
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        from modules.crm.services import pdf_branding as B

        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=A4,
            leftMargin=16 * mm,
            rightMargin=16 * mm,
            topMargin=35 * mm,
            bottomMargin=20 * mm,
            title=f"Relatório {getattr(report, 'name', '')}",
        )
        st = B.styles()
        el: list = []

        gerado = datetime.utcnow()
        tipo = getattr(getattr(report, "report_type", None), "value", None) or str(
            getattr(report, "report_type", "") or ""
        )

        # ---------------- CAPA ----------------
        cover = B.logo_path("cover")
        el.append(Spacer(1, 26 * mm))
        if cover:
            try:
                img = Image(cover, width=58 * mm, height=40 * mm, kind="proportional")
                img.hAlign = "CENTER"
                el.append(img)
            except Exception:  # noqa: BLE001
                pass
        el.append(Spacer(1, 8 * mm))
        el.append(
            Table(
                [[""]],
                colWidths=[60 * mm],
                hAlign="CENTER",
                style=TableStyle([("LINEBELOW", (0, 0), (-1, -1), 2.5, B.LARANJA)]),
            )
        )
        el.append(Spacer(1, 10 * mm))
        el.append(Paragraph("RELATÓRIO", st["capa_titulo"]))
        el.append(Spacer(1, 3 * mm))
        el.append(Paragraph(getattr(report, "name", "") or "Relatório", st["capa_sub"]))
        el.append(Spacer(1, 12 * mm))
        el.append(Paragraph(B.data_extenso(gerado), st["capa_meta"]))
        if tipo:
            el.append(Paragraph(f"Tipo: {tipo}", st["capa_meta"]))
        el.append(Spacer(1, 14 * mm))
        el.append(Paragraph("— CONFIDENCIAL —", st["destaque"]))
        el.append(PageBreak())

        # ---------------- CONTEÚDO ----------------
        el += B.secao("Resumo do Relatório", st)
        if getattr(report, "description", None):
            el.append(Paragraph(str(report.description), st["corpo"]))
            el.append(Spacer(1, 3 * mm))

        summary = data.get("summary") if isinstance(data, dict) else None
        if isinstance(summary, dict) and summary:
            rows = [[Paragraph("Indicador", st["cellh"]), Paragraph("Valor", st["cellh"])]]
            for k, v in summary.items():
                rows.append([Paragraph(str(k), st["cell"]), Paragraph(str(v), st["cellr"])])
            tbl = Table(rows, colWidths=[120 * mm, 58 * mm], repeatRows=1)
            tbl.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), B.AZUL_ESCURO),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [B.colors.white, B.FUNDO_CLARO]),
                        ("GRID", (0, 0), (-1, -1), 0.4, B.AZUL_MEDIO),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ("LEFTPADDING", (0, 0), (-1, -1), 5),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ]
                )
            )
            el.append(tbl)
        else:
            el.append(Paragraph("Sem dados de resumo disponíveis para este período.", st["corpo"]))

        el.append(Spacer(1, 8 * mm))
        el.append(Paragraph(f"Gerado em {gerado.strftime('%d/%m/%Y %H:%M')} (UTC).", st["small"]))

        doc.build(
            el,
            onFirstPage=lambda cv, dc: B.header_footer(cv, dc, seal_watermark=True),
            onLaterPages=lambda cv, dc: B.header_footer(cv, dc, seal_watermark=True),
        )
        return buf.getvalue()

    async def _save_file(
        self,
        report_id: UUID,
        run_id: UUID,
        content: bytes,
        output_format: ReportFormat,
    ) -> str:
        """Salva arquivo do relatório."""
        # Em produção, salvaria em storage (S3, Azure Blob, etc.)
        extension = output_format.value
        file_path = f"/reports/{report_id}/{run_id}.{extension}"
        logger.info("Relatório salvo em: %s (%d bytes)", file_path, len(content))
        return file_path

    async def send_report(
        self,
        report: ScheduledReport,
    ) -> bool:
        """Envia relatório por email."""
        # Em produção, usaria serviço de email
        logger.info("Enviando relatório %s para: %s", report.name, report.recipients)
        return True

    async def process_due_reports(self) -> dict[str, Any]:
        """Processa relatórios pendentes."""
        reports = await self.report_repo.get_due_reports(limit=10)

        results = {
            "processed": 0,
            "success": 0,
            "failed": 0,
            "details": [],
        }

        for report in reports:
            try:
                result = await self.generate_report(report)

                if result.status == "success":
                    results["success"] += 1

                    # Enviar se configurado
                    if report.delivery_method == "email":
                        await self.send_report(report)
                else:
                    results["failed"] += 1

                results["details"].append(
                    {
                        "report_id": str(report.id),
                        "name": report.name,
                        "status": result.status,
                    }
                )

            except (OSError, ValueError, KeyError, TypeError, RuntimeError) as e:
                logger.error("Erro ao processar relatório %s: %s", report.id, e)
                results["failed"] += 1

            results["processed"] += 1

        return results
