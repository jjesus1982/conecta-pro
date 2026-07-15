"""Serviço de processamento de folha de ponto."""

import logging
from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from modules.hr.time_tracking.models import (
    JustificationStatus,
    OvertimeStatus,
    TimeEntry,
    TimeJustification,
    TimeSheet,
    TimeSheetStatus,
    WorkSchedule,
)
from modules.hr.time_tracking.repositories import (
    OvertimeRepository,
    TimeEntryRepository,
    TimeJustificationRepository,
    TimeSheetRepository,
    WorkScheduleRepository,
)
from modules.hr.time_tracking.services.anomaly_detection_service import (
    AnomalyDetectionService,
)
from modules.hr.time_tracking.services.time_calculation_service import (
    TimeCalculationService,
)

logger = logging.getLogger(__name__)


class TimeSheetService:
    """Serviço para processamento de folhas de ponto mensais."""

    def __init__(self, db: AsyncSession):
        """Inicializa o serviço."""
        self.db = db
        self.sheet_repo = TimeSheetRepository(db)
        self.entry_repo = TimeEntryRepository(db)
        self.schedule_repo = WorkScheduleRepository(db)
        self.overtime_repo = OvertimeRepository(db)
        self.justification_repo = TimeJustificationRepository(db)
        self.calc_service = TimeCalculationService()
        self.anomaly_service = AnomalyDetectionService()

    async def generate_time_sheet(
        self,
        employee_id: str,
        employee_name: str,
        reference_month: int,
        reference_year: int,
        condominium_id: str = None,
        created_by_id: str = None,
    ) -> TimeSheet:
        """Gera ou atualiza folha de ponto do mês.

        Args:
            employee_id: ID do funcionário
            employee_name: Nome do funcionário
            reference_month: Mês de referência
            reference_year: Ano de referência
            condominium_id: ID do condomínio
            created_by_id: ID do criador

        Returns:
            TimeSheet gerado/atualizado
        """
        # Verifica se já existe
        existing = await self.sheet_repo.get_by_employee_month(employee_id, reference_month, reference_year)

        if existing:
            # Recalcula
            return await self.recalculate_time_sheet(existing)

        # Busca jornada do funcionário
        schedule = await self.schedule_repo.get_by_employee(employee_id)

        # Calcula período (variáveis usadas para referência futura)
        _ = date(reference_year, reference_month, 1)  # first_day
        _ = date(  # last_day
            reference_year, reference_month, monthrange(reference_year, reference_month)[1]
        )

        # Cria a folha
        # pylint: disable=import-outside-toplevel
        from modules.hr.time_tracking.schemas import TimeSheetCreate

        sheet_data = TimeSheetCreate(
            employee_id=employee_id,
            employee_name=employee_name,
            reference_month=reference_month,
            reference_year=reference_year,
            work_schedule_id=str(schedule.id) if schedule else None,
            work_schedule_name=schedule.name if schedule else None,
            condominium_id=condominium_id,
        )

        sheet = await self.sheet_repo.create(sheet_data, created_by_id)

        # Calcula totais
        return await self.recalculate_time_sheet(sheet)

    async def recalculate_time_sheet(  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
        self,
        sheet: TimeSheet,
        force: bool = False,
    ) -> TimeSheet:
        """Recalcula todos os totais da folha de ponto.

        Args:
            sheet: Folha de ponto
            force: Força recálculo mesmo se fechada

        Returns:
            TimeSheet atualizado
        """
        if sheet.status != TimeSheetStatus.ABERTO and not force:
            logger.warning(f"Folha {sheet.code} não está aberta para recálculo")
            return sheet

        # Busca registros do período
        entries = await self.entry_repo.get_by_employee_period(
            sheet.employee_id,
            sheet.period_start,
            sheet.period_end,
        )

        # Busca jornada
        schedule = None
        if sheet.work_schedule_id:
            from uuid import UUID  # pylint: disable=import-outside-toplevel

            schedule = await self.schedule_repo.get_by_id(UUID(sheet.work_schedule_id))

        # Busca horas extras
        overtimes = await self.overtime_repo.get_by_employee_period(
            sheet.employee_id,
            sheet.period_start,
            sheet.period_end,
        )

        # Busca justificativas
        justifications = await self.justification_repo.get_by_employee_period(
            sheet.employee_id,
            sheet.period_start,
            sheet.period_end,
        )

        # Processa dia a dia
        daily_summary = []
        total_worked = 0
        total_expected = 0
        total_overtime_50 = 0
        total_overtime_100 = 0
        total_night = 0
        total_late = 0
        total_early = 0
        total_break = 0
        late_count = 0
        early_count = 0
        absent_days = 0
        justified_absences = 0
        unjustified_absences = 0
        work_days_worked = 0
        anomaly_count = 0

        current_date = sheet.period_start
        while current_date <= sheet.period_end:
            day_entries = [e for e in entries if e.entry_date == current_date]

            day_summary = await self._process_day(
                current_date,
                day_entries,
                schedule,
                justifications,
            )

            daily_summary.append(day_summary)

            # Acumula totais
            total_worked += day_summary["worked"]
            total_expected += day_summary["expected"]
            total_night += day_summary["night"]
            total_late += day_summary["late"]
            total_early += day_summary["early"]
            total_break += day_summary.get("break", 0)

            if day_summary["late"] > 0:
                late_count += 1
            if day_summary["early"] > 0:
                early_count += 1
            if day_summary["is_absent"]:
                absent_days += 1
                if day_summary["is_justified"]:
                    justified_absences += 1
                else:
                    unjustified_absences += 1
            if day_summary["worked"] > 0:
                work_days_worked += 1
            if day_summary.get("has_anomaly"):
                anomaly_count += 1

            current_date += timedelta(days=1)

        # Processa horas extras aprovadas
        for ot in overtimes:
            if ot.status == OvertimeStatus.APROVADA:
                if ot.overtime_50_minutes:
                    total_overtime_50 += ot.overtime_50_minutes
                if ot.overtime_100_minutes:
                    total_overtime_100 += ot.overtime_100_minutes

        # Calcula valores
        hourly_rate = sheet.hourly_rate or Decimal("0")
        overtime_50_value, overtime_100_value = self.calc_service.calculate_overtime_value(
            total_overtime_50,
            total_overtime_100,
            hourly_rate,
        )
        night_value = self.calc_service.calculate_night_bonus(total_night, hourly_rate)

        # DSR
        work_days_expected = self._count_work_days(sheet.period_start, sheet.period_end, schedule)
        dsr_entitled, dsr_reason = self.calc_service.calculate_dsr(
            work_days_worked,
            work_days_expected,
            late_count,
            unjustified_absences,
        )

        # Banco de horas
        time_bank_credits = sum(
            ot.time_bank_minutes or 0
            for ot in overtimes
            if ot.status == OvertimeStatus.APROVADA and ot.time_bank_minutes
        )

        # Pendências
        pending_issues = []

        # Anomalias não resolvidas
        unresolved_entries = [e for e in entries if e.anomaly_type and not e.anomaly_resolved]
        if unresolved_entries:
            pending_issues.append(
                {
                    "type": "anomaly",
                    "date": unresolved_entries[0].entry_date.isoformat(),
                    "description": f"{len(unresolved_entries)} registros com anomalias não resolvidas",
                    "severity": "high",
                }
            )

        # Justificativas pendentes
        pending_just = [
            j for j in justifications if j.status in [JustificationStatus.PENDENTE, JustificationStatus.EM_ANALISE]
        ]
        if pending_just:
            pending_issues.append(
                {
                    "type": "justification",
                    "date": pending_just[0].start_date.isoformat(),
                    "description": f"{len(pending_just)} justificativas pendentes de aprovação",
                    "severity": "medium",
                }
            )

        # HE pendentes
        pending_ot = [ot for ot in overtimes if ot.status in [OvertimeStatus.PENDENTE, OvertimeStatus.EM_ANALISE]]
        if pending_ot:
            pending_issues.append(
                {
                    "type": "overtime",
                    "date": pending_ot[0].overtime_date.isoformat(),
                    "description": f"{len(pending_ot)} horas extras pendentes de aprovação",
                    "severity": "medium",
                }
            )

        # Atualiza folha
        sheet.hours_worked_minutes = total_worked
        sheet.hours_expected_minutes = total_expected
        sheet.hours_balance_minutes = total_worked - total_expected

        sheet.overtime_50_minutes = total_overtime_50
        sheet.overtime_100_minutes = total_overtime_100
        sheet.overtime_total_minutes = total_overtime_50 + total_overtime_100
        sheet.overtime_approved_minutes = total_overtime_50 + total_overtime_100

        sheet.night_hours_minutes = total_night

        sheet.late_minutes = total_late
        sheet.early_departure_minutes = total_early
        sheet.late_count = late_count
        sheet.early_departure_count = early_count

        sheet.break_actual_minutes = total_break

        sheet.work_days_expected = work_days_expected
        sheet.work_days_worked = work_days_worked
        sheet.absent_days = absent_days
        sheet.justified_absent_days = justified_absences
        sheet.unjustified_absent_days = unjustified_absences

        sheet.overtime_50_value = overtime_50_value
        sheet.overtime_100_value = overtime_100_value
        sheet.night_additional_value = night_value
        sheet.total_additional_value = overtime_50_value + overtime_100_value + night_value

        sheet.dsr_entitled = dsr_entitled
        if not dsr_entitled:
            sheet.dsr_lost_reason = dsr_reason

        sheet.time_bank_credits = time_bank_credits
        sheet.time_bank_current_balance = sheet.time_bank_previous_balance + time_bank_credits - sheet.time_bank_debits

        sheet.total_entries = len(entries)
        sheet.anomaly_count = anomaly_count
        sheet.justification_count = len(justifications)
        sheet.justification_approved_count = len(
            [j for j in justifications if j.status == JustificationStatus.APROVADA]
        )
        sheet.justification_pending_count = len(pending_just)

        sheet.daily_summary = daily_summary
        sheet.has_pending_issues = len(pending_issues) > 0
        sheet.pending_issues = pending_issues if pending_issues else None

        sheet.last_calculated_at = datetime.utcnow()

        await self.db.flush()
        await self.db.refresh(sheet)

        return sheet

    async def _process_day(  # pylint: disable=too-many-branches
        self,
        work_date: date,
        entries: list[TimeEntry],
        schedule: WorkSchedule = None,
        justifications: list[TimeJustification] = None,
    ) -> dict:
        """Processa um dia de trabalho."""
        result = {
            "date": work_date.isoformat(),
            "expected": 0,
            "worked": 0,
            "overtime": 0,
            "night": 0,
            "late": 0,
            "early": 0,
            "break": 0,
            "is_holiday": False,
            "is_absent": False,
            "is_justified": False,
            "has_anomaly": False,
            "notes": None,
        }

        # Verifica se é feriado
        if self._is_holiday(work_date):
            result["is_holiday"] = True
            return result

        # Verifica se é dia de trabalho
        is_work_day = True
        if schedule:
            is_work_day = schedule.is_work_day(work_date)
            if is_work_day:
                day_schedule = schedule.get_schedule_for_day(work_date)
                if day_schedule:
                    result["expected"] = day_schedule.get("daily_minutes", 0)

        if not is_work_day:
            return result

        # Verifica justificativas
        if justifications:
            day_justifications = [
                j
                for j in justifications
                if j.start_date <= work_date <= j.end_date and j.status == JustificationStatus.APROVADA
            ]
            if day_justifications:
                result["is_justified"] = True
                for j in day_justifications:
                    if j.is_full_day:
                        result["worked"] = result["expected"]
                        result["notes"] = f"Justificado: {j.justification_type.value}"
                        return result

        # Se não há registros
        if not entries:
            if result["expected"] > 0:
                result["is_absent"] = True
            return result

        # Calcula horas trabalhadas
        calc_result = self.calc_service.calculate_worked_hours(entries, schedule)

        result["worked"] = calc_result["worked_minutes"]
        result["night"] = calc_result["night_minutes"]
        result["late"] = calc_result["late_minutes"]
        result["early"] = calc_result["early_departure_minutes"]
        result["break"] = calc_result["break_minutes"]
        result["overtime"] = calc_result["overtime_minutes"]

        # Verifica anomalias
        for entry in entries:
            if entry.anomaly_type and not entry.anomaly_resolved:
                result["has_anomaly"] = True
                break

        return result

    def _count_work_days(
        self,
        start_date: date,
        end_date: date,
        schedule: WorkSchedule = None,
    ) -> int:
        """Conta dias úteis no período."""
        count = 0
        current = start_date

        while current <= end_date:
            if schedule:
                if schedule.is_work_day(current) and not self._is_holiday(current):
                    count += 1
            else:
                # Padrão: segunda a sexta
                if current.weekday() < 5 and not self._is_holiday(current):
                    count += 1
            current += timedelta(days=1)

        return count

    def _is_holiday(self, check_date: date) -> bool:
        """Verifica se é feriado."""
        fixed_holidays = [
            (1, 1),
            (4, 21),
            (5, 1),
            (9, 7),
            (10, 12),
            (11, 2),
            (11, 15),
            (12, 25),
        ]
        return (check_date.month, check_date.day) in fixed_holidays

    async def approve_by_employee(
        self,
        sheet: TimeSheet,
        notes: str = None,
    ) -> TimeSheet:
        """Aprovação do funcionário."""
        if sheet.approved_by_employee:
            raise ValueError("Folha já aprovada pelo funcionário")

        sheet.approved_by_employee = True
        sheet.employee_approved_at = datetime.utcnow()
        if notes:
            sheet.notes = notes

        await self.db.flush()
        await self.db.refresh(sheet)

        return sheet

    async def approve_by_manager(
        self,
        sheet: TimeSheet,
        manager_id: str,
        manager_name: str,
        notes: str = None,
    ) -> TimeSheet:
        """Aprovação do gestor."""
        if not sheet.approved_by_employee:
            raise ValueError("Aguardando aprovação do funcionário")
        if sheet.approved_by_manager:
            raise ValueError("Folha já aprovada pelo gestor")

        sheet.approved_by_manager = True
        sheet.manager_id = manager_id
        sheet.manager_name = manager_name
        sheet.manager_approved_at = datetime.utcnow()
        if notes:
            sheet.internal_notes = (sheet.internal_notes or "") + f"\nGestor: {notes}"

        await self.db.flush()
        await self.db.refresh(sheet)

        return sheet

    async def approve_by_hr(
        self,
        sheet: TimeSheet,
        hr_id: str,
        hr_name: str,
        notes: str = None,
    ) -> TimeSheet:
        """Aprovação do RH."""
        if not sheet.approved_by_manager:
            raise ValueError("Aguardando aprovação do gestor")
        if sheet.approved_by_hr:
            raise ValueError("Folha já aprovada pelo RH")

        sheet.approved_by_hr = True
        sheet.hr_approver_id = hr_id
        sheet.hr_approver_name = hr_name
        sheet.hr_approved_at = datetime.utcnow()
        if notes:
            sheet.internal_notes = (sheet.internal_notes or "") + f"\nRH: {notes}"

        await self.db.flush()
        await self.db.refresh(sheet)

        return sheet

    async def close_time_sheet(
        self,
        sheet: TimeSheet,
        closed_by_id: str,
        closed_by_name: str,
    ) -> TimeSheet:
        """Fecha a folha de ponto."""
        if not sheet.can_close:
            raise ValueError("Folha não pode ser fechada - verifique aprovações e pendências")

        sheet.status = TimeSheetStatus.FECHADO
        sheet.closed_at = datetime.utcnow()
        sheet.closed_by_id = closed_by_id
        sheet.closed_by_name = closed_by_name

        await self.db.flush()
        await self.db.refresh(sheet)

        return sheet

    async def send_to_payroll(
        self,
        sheet: TimeSheet,
        payroll_reference: str,
        batch_id: str = None,
    ) -> TimeSheet:
        """Envia para folha de pagamento."""
        if sheet.status != TimeSheetStatus.FECHADO:
            raise ValueError("Folha precisa estar fechada para envio")

        sheet.status = TimeSheetStatus.ENVIADO_FOLHA
        sheet.sent_to_payroll_at = datetime.utcnow()
        sheet.payroll_reference = payroll_reference
        sheet.payroll_batch_id = batch_id

        await self.db.flush()
        await self.db.refresh(sheet)

        return sheet

    async def reopen_time_sheet(  # pylint: disable=unused-argument
        self,
        sheet: TimeSheet,
        reason: str,
        reopened_by_id: str,
    ) -> TimeSheet:
        """Reabre uma folha fechada."""
        if sheet.status == TimeSheetStatus.ENVIADO_FOLHA:
            raise ValueError("Não é possível reabrir folha já enviada à folha de pagamento")

        sheet.status = TimeSheetStatus.ABERTO
        sheet.approved_by_employee = False
        sheet.approved_by_manager = False
        sheet.approved_by_hr = False
        sheet.closed_at = None
        sheet.internal_notes = (
            sheet.internal_notes or ""
        ) + f"\n[Reaberta em {datetime.utcnow().isoformat()}] Motivo: {reason}"

        await self.db.flush()
        await self.db.refresh(sheet)

        return sheet
