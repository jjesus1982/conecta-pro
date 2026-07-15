"""Serviço de geração de relatórios de ponto."""

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from modules.hr.time_tracking.models import (
    OvertimeStatus,
    TimeEntry,
    TimeSheet,
    TimeSheetStatus,
)
from modules.hr.time_tracking.repositories import (
    OvertimeRepository,
    TimeEntryRepository,
    TimeJustificationRepository,
    TimeSheetRepository,
    WorkScheduleRepository,
)

logger = logging.getLogger(__name__)


class ReportService:
    """Serviço de geração de relatórios de ponto eletrônico."""

    def __init__(self, db: AsyncSession):
        """Inicializa o serviço."""
        self.db = db
        self.sheet_repo = TimeSheetRepository(db)
        self.entry_repo = TimeEntryRepository(db)
        self.schedule_repo = WorkScheduleRepository(db)
        self.overtime_repo = OvertimeRepository(db)
        self.justification_repo = TimeJustificationRepository(db)

    async def generate_employee_report(
        self,
        employee_id: str,
        reference_month: int,
        reference_year: int,
    ) -> dict[str, Any]:
        """Gera relatório mensal do funcionário.

        Args:
            employee_id: ID do funcionário
            reference_month: Mês de referência
            reference_year: Ano de referência

        Returns:
            Dict com relatório completo
        """
        # Busca folha de ponto
        sheet = await self.sheet_repo.get_by_employee_month(employee_id, reference_month, reference_year)

        if not sheet:
            return {"error": "Folha de ponto não encontrada"}

        # Busca registros
        entries = await self.entry_repo.get_by_employee_period(employee_id, sheet.period_start, sheet.period_end)

        # Busca horas extras
        overtimes = await self.overtime_repo.get_by_employee_period(employee_id, sheet.period_start, sheet.period_end)

        # Busca justificativas
        justifications = await self.justification_repo.get_by_employee_period(
            employee_id, sheet.period_start, sheet.period_end
        )

        # Monta relatório
        report = {
            "header": {
                "employee_id": employee_id,
                "employee_name": sheet.employee_name,
                "employee_registration": sheet.employee_registration,
                "department": sheet.department_name,
                "position": sheet.position_name,
                "reference_period": sheet.period_display,
                "work_schedule": sheet.work_schedule_name,
                "generated_at": datetime.utcnow().isoformat(),
            },
            "summary": {
                "hours_expected": sheet.hours_expected,
                "hours_worked": sheet.hours_worked,
                "hours_balance": sheet.hours_balance,
                "overtime_total": sheet.overtime_total_hours,
                "overtime_50_hours": round(sheet.overtime_50_minutes / 60, 2),
                "overtime_100_hours": round(sheet.overtime_100_minutes / 60, 2),
                "night_hours": round(sheet.night_hours_minutes / 60, 2),
                "late_count": sheet.late_count,
                "late_minutes_total": sheet.late_minutes,
                "early_departure_count": sheet.early_departure_count,
                "absent_days": sheet.absent_days,
                "justified_absences": sheet.justified_absent_days,
                "unjustified_absences": sheet.unjustified_absent_days,
            },
            "financial": {
                "hourly_rate": float(sheet.hourly_rate),
                "overtime_50_value": float(sheet.overtime_50_value),
                "overtime_100_value": float(sheet.overtime_100_value),
                "night_bonus_value": float(sheet.night_additional_value),
                "total_additional": float(sheet.total_additional_value),
                "total_deduction": float(sheet.total_deduction_value),
            },
            "time_bank": {
                "previous_balance": sheet.time_bank_previous_balance,
                "credits": sheet.time_bank_credits,
                "debits": sheet.time_bank_debits,
                "current_balance": sheet.time_bank_current_balance,
            },
            "dsr": {
                "entitled": sheet.dsr_entitled,
                "lost_reason": sheet.dsr_lost_reason,
            },
            "daily_details": sheet.daily_summary or [],
            "entries": [
                {
                    "date": e.entry_date.isoformat(),
                    "time": e.entry_time.isoformat(),
                    "type": e.entry_type.value,
                    "method": e.registration_method.value if e.registration_method else None,
                    "status": e.status.value,
                    "has_anomaly": e.anomaly_type is not None,
                }
                for e in entries
            ],
            "overtimes": [
                {
                    "date": ot.overtime_date.isoformat(),
                    "minutes": ot.total_minutes,
                    "type": ot.overtime_type.value,
                    "status": ot.status.value,
                    "reason": ot.reason,
                }
                for ot in overtimes
            ],
            "justifications": [
                {
                    "type": j.justification_type.value,
                    "start_date": j.start_date.isoformat(),
                    "end_date": j.end_date.isoformat(),
                    "days": j.days_count,
                    "status": j.status.value,
                }
                for j in justifications
            ],
            "approvals": {
                "employee_approved": sheet.approved_by_employee,
                "employee_approved_at": (
                    sheet.employee_approved_at.isoformat() if sheet.employee_approved_at else None
                ),
                "manager_approved": sheet.approved_by_manager,
                "manager_name": sheet.manager_name,
                "manager_approved_at": (sheet.manager_approved_at.isoformat() if sheet.manager_approved_at else None),
                "hr_approved": sheet.approved_by_hr,
                "hr_name": sheet.hr_approver_name,
                "hr_approved_at": (sheet.hr_approved_at.isoformat() if sheet.hr_approved_at else None),
            },
            "status": {
                "status": sheet.status.value,
                "closed_at": sheet.closed_at.isoformat() if sheet.closed_at else None,
                "sent_to_payroll_at": (sheet.sent_to_payroll_at.isoformat() if sheet.sent_to_payroll_at else None),
                "has_pending_issues": sheet.has_pending_issues,
                "pending_issues": sheet.pending_issues or [],
            },
        }

        return report

    async def generate_department_report(  # pylint: disable=too-many-locals
        self,
        department_id: str,
        reference_month: int,
        reference_year: int,
        condominium_id: str = None,
    ) -> dict[str, Any]:
        """Gera relatório consolidado do departamento."""
        # pylint: disable=import-outside-toplevel
        from modules.hr.time_tracking.schemas import TimeSheetFilter

        filters = TimeSheetFilter(
            department_id=department_id,
            reference_month=reference_month,
            reference_year=reference_year,
            condominium_id=condominium_id,
        )

        sheets, _total = await self.sheet_repo.list(filters, limit=1000)

        if not sheets:
            return {"error": "Nenhuma folha encontrada para o período"}

        # Consolida dados
        total_hours_worked = sum(s.hours_worked_minutes for s in sheets)
        total_hours_expected = sum(s.hours_expected_minutes for s in sheets)
        total_overtime = sum(s.overtime_total_minutes for s in sheets)
        total_overtime_value = sum(s.overtime_50_value + s.overtime_100_value for s in sheets)
        total_night_value = sum(s.night_additional_value for s in sheets)
        total_late_count = sum(s.late_count for s in sheets)
        total_absences = sum(s.absent_days for s in sheets)

        employees_summary = []
        for sheet in sheets:
            employees_summary.append(
                {
                    "employee_id": sheet.employee_id,
                    "employee_name": sheet.employee_name,
                    "hours_worked": sheet.hours_worked,
                    "hours_balance": sheet.hours_balance,
                    "overtime_hours": sheet.overtime_total_hours,
                    "late_count": sheet.late_count,
                    "absent_days": sheet.absent_days,
                    "status": sheet.status.value,
                    "approved": sheet.is_fully_approved,
                }
            )

        report = {
            "header": {
                "department_id": department_id,
                "reference_period": f"{reference_month:02d}/{reference_year}",
                "total_employees": len(sheets),
                "generated_at": datetime.utcnow().isoformat(),
            },
            "totals": {
                "hours_expected": round(total_hours_expected / 60, 2),
                "hours_worked": round(total_hours_worked / 60, 2),
                "overtime_hours": round(total_overtime / 60, 2),
                "overtime_value": float(total_overtime_value),
                "night_bonus_value": float(total_night_value),
                "late_occurrences": total_late_count,
                "absence_days": total_absences,
            },
            "employees": employees_summary,
            "statistics": {
                "avg_hours_worked": round(total_hours_worked / len(sheets) / 60, 2),
                "avg_overtime": round(total_overtime / len(sheets) / 60, 2),
                "sheets_pending": len([s for s in sheets if s.status == TimeSheetStatus.ABERTO]),
                "sheets_closed": len([s for s in sheets if s.status == TimeSheetStatus.FECHADO]),
                "sheets_sent": len([s for s in sheets if s.status == TimeSheetStatus.ENVIADO_FOLHA]),
            },
        }

        return report

    async def generate_anomaly_report(
        self,
        condominium_id: str = None,
        date_from: date = None,
        date_to: date = None,
    ) -> dict[str, Any]:
        """Gera relatório de anomalias."""
        entries = await self.entry_repo.get_with_anomalies(
            condominium_id=condominium_id,
            date_from=date_from,
            date_to=date_to,
            limit=500,
        )

        # Agrupa por tipo de anomalia
        by_type: dict[str, list] = {}
        by_employee: dict[str, int] = {}

        for entry in entries:
            anomaly_type = entry.anomaly_type.value if entry.anomaly_type else "unknown"

            if anomaly_type not in by_type:
                by_type[anomaly_type] = []

            by_type[anomaly_type].append(
                {
                    "employee_id": entry.employee_id,
                    "employee_name": entry.employee_name,
                    "date": entry.entry_date.isoformat(),
                    "time": entry.entry_time.isoformat(),
                    "entry_type": entry.entry_type.value,
                    "description": entry.anomaly_description,
                }
            )

            emp_key = entry.employee_id
            by_employee[emp_key] = by_employee.get(emp_key, 0) + 1

        # Top funcionários com anomalias
        top_employees = sorted(by_employee.items(), key=lambda x: x[1], reverse=True)[:10]

        date_from_str = date_from.isoformat() if date_from else "N/A"
        date_to_str = date_to.isoformat() if date_to else "N/A"
        report = {
            "header": {
                "period": f"{date_from_str} a {date_to_str}",
                "total_anomalies": len(entries),
                "generated_at": datetime.utcnow().isoformat(),
            },
            "by_type": {
                anomaly_type: {
                    "count": len(items),
                    "details": items[:20],  # Limita detalhes
                }
                for anomaly_type, items in by_type.items()
            },
            "top_employees_with_anomalies": [
                {"employee_id": emp_id, "count": count} for emp_id, count in top_employees
            ],
            "summary": {
                "total_unresolved": len(entries),
                "anomaly_types_count": len(by_type),
                "employees_affected": len(by_employee),
            },
        }

        return report

    async def generate_overtime_report(  # pylint: disable=too-many-locals
        self,
        condominium_id: str = None,
        date_from: date = None,
        date_to: date = None,
    ) -> dict[str, Any]:
        """Gera relatório de horas extras."""
        stats = await self.overtime_repo.get_stats(
            condominium_id=condominium_id,
            date_from=date_from,
            date_to=date_to,
        )

        # Busca detalhes
        # pylint: disable=import-outside-toplevel
        from modules.hr.time_tracking.schemas import OvertimeFilter

        filters = OvertimeFilter(
            condominium_id=condominium_id,
            date_from=date_from,
            date_to=date_to,
        )

        overtimes, _total = await self.overtime_repo.list(filters, limit=500)

        # Agrupa por funcionário
        by_employee: dict[str, dict] = {}
        for ot in overtimes:
            emp_id = ot.employee_id
            if emp_id not in by_employee:
                by_employee[emp_id] = {
                    "employee_name": ot.employee_name,
                    "total_minutes": 0,
                    "approved_minutes": 0,
                    "pending_minutes": 0,
                    "total_value": Decimal("0"),
                }

            by_employee[emp_id]["total_minutes"] += ot.total_minutes
            if ot.status == OvertimeStatus.APROVADA:
                by_employee[emp_id]["approved_minutes"] += ot.total_minutes
                by_employee[emp_id]["total_value"] += ot.calculated_value or Decimal("0")
            elif ot.status in [OvertimeStatus.PENDENTE, OvertimeStatus.EM_ANALISE]:
                by_employee[emp_id]["pending_minutes"] += ot.total_minutes

        date_from_str = date_from.isoformat() if date_from else "N/A"
        date_to_str = date_to.isoformat() if date_to else "N/A"
        report = {
            "header": {
                "period": f"{date_from_str} a {date_to_str}",
                "total_records": stats["total_records"],
                "generated_at": datetime.utcnow().isoformat(),
            },
            "summary": {
                "approved_hours": stats["approved_hours"],
                "approved_value": stats["total_value"],
                "pending_count": stats["pending_count"],
                "by_status": stats["by_status"],
                "by_type": stats["by_type"],
                "by_compensation": stats["by_compensation_type"],
            },
            "by_employee": [
                {
                    "employee_id": emp_id,
                    "employee_name": data["employee_name"],
                    "total_hours": round(data["total_minutes"] / 60, 2),
                    "approved_hours": round(data["approved_minutes"] / 60, 2),
                    "pending_hours": round(data["pending_minutes"] / 60, 2),
                    "total_value": float(data["total_value"]),
                }
                for emp_id, data in sorted(by_employee.items(), key=lambda x: x[1]["total_minutes"], reverse=True)
            ],
        }

        return report

    async def generate_afdt_export(
        self,
        condominium_id: str,
        date_from: date,
        date_to: date,
    ) -> str:
        """Gera arquivo AFDT (Arquivo Fonte de Dados Tratados).

        Formato exigido pela Portaria 671/2021 do MTE.
        """
        lines = []

        # Cabeçalho tipo 1
        lines.append(self._afdt_header(date_from, date_to))

        # Busca todas as entradas do período
        entries = await self._get_entries_for_export(condominium_id, date_from, date_to)

        # Agrupa por funcionário
        by_employee: dict[str, list] = {}
        for entry in entries:
            emp_id = entry.employee_id
            if emp_id not in by_employee:
                by_employee[emp_id] = []
            by_employee[emp_id].append(entry)

        # Gera linhas de detalhe (tipo 2)
        seq = 1
        for _emp_id, emp_entries in by_employee.items():
            for entry in sorted(emp_entries, key=lambda e: (e.entry_date, e.entry_time)):
                line = self._afdt_detail_line(entry, seq)
                lines.append(line)
                seq += 1

        # Trailer tipo 9
        lines.append(self._afdt_trailer(seq))

        return "\n".join(lines)

    async def generate_acjef_export(
        self,
        condominium_id: str,
        reference_month: int,
        reference_year: int,
    ) -> str:
        """Gera arquivo ACJEF (Arquivo de Controle de Jornada).

        Formato exigido pela Portaria 671/2021 do MTE.
        """
        lines = []

        # Busca folhas do período
        sheets = await self.sheet_repo.get_by_period(reference_month, reference_year, condominium_id)

        # Cabeçalho
        lines.append(self._acjef_header(reference_month, reference_year))

        # Detalhes por funcionário
        seq = 1
        for sheet in sheets:
            if sheet.daily_summary:
                for day in sheet.daily_summary:
                    line = self._acjef_detail_line(sheet, day, seq)
                    lines.append(line)
                    seq += 1

        # Trailer
        lines.append(self._acjef_trailer(seq))

        return "\n".join(lines)

    def _afdt_header(self, date_from: date, date_to: date) -> str:
        """Gera cabeçalho AFDT."""
        return (
            f"1"
            f"{date_from.strftime('%d%m%Y')}"
            f"{date_to.strftime('%d%m%Y')}"
            f"{'':>20}"  # CNPJ/CPF
            f"{'':>150}"  # Razão social
        )

    def _afdt_detail_line(self, entry: TimeEntry, seq: int) -> str:
        """Gera linha de detalhe AFDT."""
        return (
            f"2"
            f"{seq:09d}"
            f"{entry.employee_pis or '':>11}"
            f"{entry.entry_date.strftime('%d%m%Y')}"
            f"{entry.entry_time.strftime('%H%M')}"
            f"{'':>50}"  # NSR
        )

    def _afdt_trailer(self, total_records: int) -> str:
        """Gera trailer AFDT."""
        return f"9{total_records:09d}"

    def _acjef_header(self, month: int, year: int) -> str:
        """Gera cabeçalho ACJEF."""
        return (
            f"1"
            f"{month:02d}{year}"
            f"{'':>20}"  # CNPJ
            f"{'':>150}"  # Razão social
        )

    def _acjef_detail_line(
        self,
        sheet: TimeSheet,
        day: dict,
        seq: int,
    ) -> str:
        """Gera linha de detalhe ACJEF."""
        day_date = date.fromisoformat(day["date"])
        return (
            f"2"
            f"{seq:09d}"
            f"{sheet.employee_pis or '':>11}"
            f"{day_date.strftime('%d%m%Y')}"
            f"{day.get('worked', 0):04d}"
            f"{day.get('overtime', 0):04d}"
            f"{day.get('night', 0):04d}"
        )

    def _acjef_trailer(self, total_records: int) -> str:
        """Gera trailer ACJEF."""
        return f"9{total_records:09d}"

    async def _get_entries_for_export(
        self,
        condominium_id: str,
        date_from: date,
        date_to: date,
    ) -> list[TimeEntry]:
        """Busca entradas para exportação."""
        # pylint: disable=import-outside-toplevel
        from modules.hr.time_tracking.schemas import TimeEntryFilter

        filters = TimeEntryFilter(
            condominium_id=condominium_id,
            date_from=date_from,
            date_to=date_to,
        )

        entries, _ = await self.entry_repo.list(filters, limit=10000)
        return entries
