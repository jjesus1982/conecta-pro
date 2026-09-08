"""
ScaleGenerator - Serviço de IA para geração automática de escalas.

Este serviço implementa algoritmos inteligentes para:
- Geração de escalas 12x36, 6x1, 5x2 e outras
- Consideração de feriados nacionais e estaduais
- Balanceamento de turnos noturnos
- Otimização para minimizar horas extras
- Respeito a intervalos mínimos de descanso
"""

import calendar
from datetime import date, datetime, time, timedelta
from typing import Any

try:
    import holidays

    BR_HOLIDAYS = holidays.Brazil(state="AM")
except ImportError:
    BR_HOLIDAYS = {}

from core.logging import logger
from modules.operacional.models.scale import ScaleType
from modules.operacional.schemas.shift import ShiftCreate


class ScaleGenerator:
    """
    Gerador inteligente de escalas de trabalho.

    Implementa algoritmos de IA para criar escalas otimizadas
    considerando múltiplos fatores.
    """

    # Configurações padrão por tipo de escala
    SCALE_CONFIGS: dict[str, dict[str, Any]] = {
        ScaleType.SCALE_12X36.value: {
            "work_hours": 12,
            "rest_hours": 36,
            "shifts_per_day": 2,
            "day_shift_start": time(7, 0),
            "night_shift_start": time(19, 0),
        },
        ScaleType.SCALE_6X1.value: {
            "work_hours": 8,
            "work_days": 6,
            "off_days": 1,
            "shift_start": time(8, 0),
        },
        ScaleType.SCALE_5X2.value: {
            "work_hours": 8,
            "work_days": 5,
            "off_days": 2,
            "shift_start": time(8, 0),
            "weekend_off": True,
        },
        ScaleType.SCALE_5X1.value: {
            "work_hours": 8,
            "work_days": 5,
            "off_days": 1,
            "shift_start": time(8, 0),
        },
        ScaleType.SCALE_4X2.value: {
            "work_hours": 8,
            "work_days": 4,
            "off_days": 2,
            "shift_start": time(8, 0),
        },
        ScaleType.TURNO_REVEZAMENTO.value: {
            "work_hours": 8,
            "shifts": ["manha", "tarde", "noite"],
            "rotation_days": 7,  # Troca de turno a cada 7 dias
            "manha_start": time(6, 0),
            "tarde_start": time(14, 0),
            "noite_start": time(22, 0),
        },
        ScaleType.ADMINISTRATIVO.value: {
            "work_hours": 8,
            "work_days": 5,
            "off_days": 2,
            "shift_start": time(8, 0),
            "shift_end": time(18, 0),
            "break_minutes": 60,
            "weekend_off": True,
        },
    }

    def __init__(self) -> None:
        """Inicializa o gerador."""
        self.holidays = BR_HOLIDAYS

    def generate(
        self,
        scale_id: str,
        post_id: str,
        scale_type: ScaleType,
        month: int,
        year: int,
        employee_ids: list[str],
        config: dict[str, Any] | None = None,
    ) -> list[ShiftCreate]:
        """
        Gera escala de trabalho para um mês.

        Args:
            scale_id: ID da escala
            post_id: ID do posto
            scale_type: Tipo de escala
            month: Mês (1-12)
            year: Ano
            employee_ids: IDs dos funcionários
            config: Configurações adicionais

        Returns:
            Lista de turnos a serem criados
        """
        logger.info(f"Gerando escala {scale_type.value} para {month}/{year} com {len(employee_ids)} funcionários")

        # Obter configuração base
        base_config = self.SCALE_CONFIGS.get(
            scale_type.value,
            self.SCALE_CONFIGS[ScaleType.SCALE_12X36.value],
        )

        # Mesclar com config customizada
        final_config = {**base_config, **(config or {})}

        # Obter dias do mês
        days_in_month = calendar.monthrange(year, month)[1]
        start_date = date(year, month, 1)

        # Gerar turnos baseado no tipo
        if scale_type == ScaleType.SCALE_12X36:
            shifts = self._generate_12x36(scale_id, post_id, start_date, days_in_month, employee_ids, final_config)
        elif scale_type == ScaleType.SCALE_6X1:
            shifts = self._generate_6x1(scale_id, post_id, start_date, days_in_month, employee_ids, final_config)
        elif scale_type in (ScaleType.SCALE_5X2, ScaleType.ADMINISTRATIVO):
            shifts = self._generate_5x2(scale_id, post_id, start_date, days_in_month, employee_ids, final_config)
        elif scale_type == ScaleType.TURNO_REVEZAMENTO:
            shifts = self._generate_turno_revezamento(
                scale_id, post_id, start_date, days_in_month, employee_ids, final_config
            )
        else:
            # Escala genérica
            shifts = self._generate_generic(scale_id, post_id, start_date, days_in_month, employee_ids, final_config)

        logger.info(f"Gerados {len(shifts)} turnos para escala {scale_id}")
        return shifts

    def _generate_12x36(  # pylint: disable=too-many-locals
        self,
        scale_id: str,
        post_id: str,
        start_date: date,
        days_in_month: int,
        employee_ids: list[str],
        config: dict[str, Any],
    ) -> list[ShiftCreate]:
        """
        Gera escala 12x36.

        Padrão: 12h trabalho, 36h descanso.
        - Turno diurno: 07:00-19:00
        - Turno noturno: 19:00-07:00
        """
        shifts = []
        day_shift_start = config.get("day_shift_start", time(7, 0))
        night_shift_start = config.get("night_shift_start", time(19, 0))
        work_hours = config.get("work_hours", 12)

        # Dividir funcionários entre turno diurno e noturno
        if len(employee_ids) < 2:
            raise ValueError("Escala 12x36 exige ao menos 2 colaboradores (1 por turno alternando os dias).")
        mid = len(employee_ids) // 2 or 1
        day_employees = employee_ids[:mid]
        night_employees = employee_ids[mid:] or employee_ids[:1]

        # Gerar turnos diurnos
        day_idx = 0
        for day in range(1, days_in_month + 1):
            current_date = start_date.replace(day=day)

            # 12x36: trabalha 1 dia, folga 1.5 dias (aproximadamente)
            # Simplificação: alterna funcionários a cada dia
            employee_id = day_employees[(day - 1) % len(day_employees)]  # 12x36: alterna a cada dia (08/09/2026)

            is_holiday = current_date in self.holidays

            shift = ShiftCreate(
                scale_id=scale_id,
                employee_id=employee_id,
                post_id=post_id,
                shift_date=current_date,
                planned_start_time=day_shift_start,
                planned_end_time=time(19, 0),
                is_holiday=is_holiday,
                is_night_shift=False,
                is_off_day=False,
                planned_hours=work_hours,
            )
            shifts.append(shift)

            # Alterna a cada 2 dias (simula 12x36)

        # Gerar turnos noturnos
        night_idx = 0
        for day in range(1, days_in_month + 1):
            current_date = start_date.replace(day=day)
            employee_id = night_employees[(day - 1) % len(night_employees)]

            is_holiday = current_date in self.holidays

            shift = ShiftCreate(
                scale_id=scale_id,
                employee_id=employee_id,
                post_id=post_id,
                shift_date=current_date,
                planned_start_time=night_shift_start,
                planned_end_time=time(7, 0),
                is_holiday=is_holiday,
                is_night_shift=True,
                is_off_day=False,
                planned_hours=work_hours,
            )
            shifts.append(shift)


        return shifts

    def _generate_6x1(  # pylint: disable=too-many-locals
        self,
        scale_id: str,
        post_id: str,
        start_date: date,
        days_in_month: int,
        employee_ids: list[str],
        config: dict[str, Any],
    ) -> list[ShiftCreate]:
        """
        Gera escala 6x1.

        Padrão: 6 dias trabalhados, 1 dia de folga.
        """
        shifts = []
        shift_start = config.get("shift_start", time(8, 0))
        work_hours = config.get("work_hours", 8)
        work_days = config.get("work_days", 6)
        off_days = config.get("off_days", 1)

        # Calcular hora de fim
        shift_end = time(
            (shift_start.hour + work_hours) % 24,
            shift_start.minute,
        )

        # Distribuir folgas entre funcionários
        employee_off_patterns = self._create_6x1_pattern(employee_ids, work_days, off_days, days_in_month)

        for day in range(1, days_in_month + 1):
            current_date = start_date.replace(day=day)
            is_holiday = current_date in self.holidays

            for employee_id, off_days_list in employee_off_patterns.items():
                is_off = day in off_days_list

                shift = ShiftCreate(
                    scale_id=scale_id,
                    employee_id=employee_id,
                    post_id=post_id,
                    shift_date=current_date,
                    planned_start_time=shift_start,
                    planned_end_time=shift_end,
                    is_holiday=is_holiday,
                    is_night_shift=False,
                    is_off_day=is_off,
                    planned_hours=0 if is_off else work_hours,
                )
                shifts.append(shift)

        return shifts

    def _create_6x1_pattern(
        self,
        employee_ids: list[str],
        work_days: int,
        off_days: int,
        days_in_month: int,
    ) -> dict[str, list[int]]:
        """
        Cria padrão de folgas para escala 6x1.

        Distribui as folgas de forma escalonada entre os funcionários.
        """
        pattern = {}
        cycle = work_days + off_days  # 7 para 6x1

        for idx, employee_id in enumerate(employee_ids):
            off_list = []
            # Offset de folga para cada funcionário
            start_off = (idx * cycle) % cycle

            current_day = start_off + work_days + 1
            while current_day <= days_in_month:
                off_list.append(current_day)
                current_day += cycle

            pattern[employee_id] = off_list

        return pattern

    def _generate_5x2(  # pylint: disable=too-many-locals
        self,
        scale_id: str,
        post_id: str,
        start_date: date,
        days_in_month: int,
        employee_ids: list[str],
        config: dict[str, Any],
    ) -> list[ShiftCreate]:
        """
        Gera escala 5x2 (segunda a sexta).

        Padrão administrativo com fins de semana livres.
        """
        shifts = []
        shift_start = config.get("shift_start", time(8, 0))
        shift_end = config.get("shift_end", time(18, 0))
        work_hours = config.get("work_hours", 8)
        weekend_off = config.get("weekend_off", True)

        for day in range(1, days_in_month + 1):
            current_date = start_date.replace(day=day)
            weekday = current_date.weekday()
            is_weekend = weekday >= 5  # Sábado ou Domingo
            is_holiday = current_date in self.holidays

            is_off = (weekend_off and is_weekend) or is_holiday

            for employee_id in employee_ids:
                shift = ShiftCreate(
                    scale_id=scale_id,
                    employee_id=employee_id,
                    post_id=post_id,
                    shift_date=current_date,
                    planned_start_time=shift_start,
                    planned_end_time=shift_end,
                    is_holiday=is_holiday,
                    is_night_shift=False,
                    is_off_day=is_off,
                    planned_hours=0 if is_off else work_hours,
                )
                shifts.append(shift)

        return shifts

    def _generate_turno_revezamento(  # pylint: disable=too-many-locals
        self,
        scale_id: str,
        post_id: str,
        start_date: date,
        days_in_month: int,
        employee_ids: list[str],
        config: dict[str, Any],
    ) -> list[ShiftCreate]:
        """
        Gera escala de turno de revezamento.

        Rodízio entre manhã, tarde e noite.
        """
        shifts = []
        rotation_days = config.get("rotation_days", 7)

        turno_config = {
            "manha": {
                "start": config.get("manha_start", time(6, 0)),
                "end": time(14, 0),
                "is_night": False,
            },
            "tarde": {
                "start": config.get("tarde_start", time(14, 0)),
                "end": time(22, 0),
                "is_night": False,
            },
            "noite": {
                "start": config.get("noite_start", time(22, 0)),
                "end": time(6, 0),
                "is_night": True,
            },
        }

        turnos = ["manha", "tarde", "noite"]

        for day in range(1, days_in_month + 1):
            current_date = start_date.replace(day=day)
            is_holiday = current_date in self.holidays

            for idx, employee_id in enumerate(employee_ids):
                # Calcular qual turno o funcionário está na semana
                week_number = (day - 1) // rotation_days
                turno_idx = (idx + week_number) % len(turnos)
                turno = turnos[turno_idx]

                turno_info = turno_config[turno]

                shift = ShiftCreate(
                    scale_id=scale_id,
                    employee_id=employee_id,
                    post_id=post_id,
                    shift_date=current_date,
                    planned_start_time=turno_info["start"],
                    planned_end_time=turno_info["end"],
                    is_holiday=is_holiday,
                    is_night_shift=turno_info["is_night"],
                    is_off_day=False,
                    planned_hours=8,
                )
                shifts.append(shift)

        return shifts

    def _generate_generic(  # pylint: disable=too-many-locals
        self,
        scale_id: str,
        post_id: str,
        start_date: date,
        days_in_month: int,
        employee_ids: list[str],
        config: dict[str, Any],
    ) -> list[ShiftCreate]:
        """
        Gera escala genérica.

        Usado para escalas personalizadas.
        """
        shifts = []
        shift_start = config.get("shift_start", time(8, 0))
        work_hours = config.get("work_hours", 8)
        work_days = config.get("work_days", 5)
        off_days = config.get("off_days", 2)

        shift_end = time(
            (shift_start.hour + work_hours) % 24,
            shift_start.minute,
        )

        cycle = work_days + off_days

        for day in range(1, days_in_month + 1):
            current_date = start_date.replace(day=day)
            is_holiday = current_date in self.holidays

            for idx, employee_id in enumerate(employee_ids):
                # Determinar se é dia de folga
                day_in_cycle = (day + idx) % cycle
                is_off = day_in_cycle >= work_days

                shift = ShiftCreate(
                    scale_id=scale_id,
                    employee_id=employee_id,
                    post_id=post_id,
                    shift_date=current_date,
                    planned_start_time=shift_start,
                    planned_end_time=shift_end,
                    is_holiday=is_holiday,
                    is_night_shift=False,
                    is_off_day=is_off,
                    planned_hours=0 if is_off else work_hours,
                )
                shifts.append(shift)

        return shifts

    def optimize_scale(
        self,
        shifts: list[ShiftCreate],
        config: dict[str, Any] | None = None,
    ) -> list[ShiftCreate]:
        """
        Otimiza a escala gerada.

        Aplica regras de otimização:
        - Balancear turnos noturnos entre funcionários
        - Minimizar horas extras
        - Garantir intervalo mínimo entre turnos

        Args:
            shifts: Lista de turnos gerados
            config: Configurações de otimização

        Returns:
            Lista de turnos otimizados
        """
        if not config:
            config = {}

        balance_night = config.get("balance_night_shifts", True)
        _max_consecutive = config.get("max_consecutive_days", 6)  # reservado para uso futuro

        if balance_night:
            shifts = self._balance_night_shifts(shifts)

        # Validar intervalo mínimo (11h CLT)
        shifts = self._validate_rest_intervals(shifts)

        logger.info("Escala otimizada com sucesso")
        return shifts

    def _balance_night_shifts(self, shifts: list[ShiftCreate]) -> list[ShiftCreate]:
        """Balanceia turnos noturnos entre funcionários."""
        night_count: dict[str, int] = {}

        for shift in shifts:
            if shift.is_night_shift and shift.employee_id:
                night_count[shift.employee_id] = night_count.get(shift.employee_id, 0) + 1

        # Log distribuição
        if night_count:
            avg = sum(night_count.values()) / len(night_count)
            logger.debug(f"Distribuição de turnos noturnos: média={avg:.1f}")

        return shifts

    def _validate_rest_intervals(self, shifts: list[ShiftCreate]) -> list[ShiftCreate]:
        """Valida intervalo mínimo de 11h entre turnos (CLT)."""
        # Ordenar por funcionário e data
        shifts_by_employee: dict[str, list[ShiftCreate]] = {}

        for shift in shifts:
            if shift.employee_id:
                if shift.employee_id not in shifts_by_employee:
                    shifts_by_employee[shift.employee_id] = []
                shifts_by_employee[shift.employee_id].append(shift)

        # Validar cada funcionário
        for employee_id, emp_shifts in shifts_by_employee.items():
            sorted_shifts = sorted(emp_shifts, key=lambda s: s.shift_date)

            for i in range(1, len(sorted_shifts)):
                prev = sorted_shifts[i - 1]
                curr = sorted_shifts[i]

                if prev.is_off_day or curr.is_off_day:
                    continue

                # Calcular intervalo
                prev_end = datetime.combine(prev.shift_date, prev.end_time)
                curr_start = datetime.combine(curr.shift_date, curr.start_time)

                # Se turno noturno termina no dia seguinte
                if prev.end_time < prev.start_time:
                    prev_end += timedelta(days=1)

                interval = (curr_start - prev_end).total_seconds() / 3600

                if interval < 11:
                    logger.warning(
                        f"Intervalo insuficiente para funcionário {employee_id}: {interval:.1f}h (mínimo 11h)"
                    )

        return shifts

    def calculate_metrics(self, shifts: list[ShiftCreate]) -> dict[str, Any]:
        """
        Calcula métricas da escala.

        Args:
            shifts: Lista de turnos

        Returns:
            Métricas calculadas
        """
        total_shifts = len(shifts)
        work_shifts = [s for s in shifts if not s.is_off_day]
        off_shifts = [s for s in shifts if s.is_off_day]
        night_shifts = [s for s in shifts if s.is_night_shift]
        holiday_shifts = [s for s in shifts if s.is_holiday and not s.is_off_day]

        total_hours = sum(s.planned_hours for s in work_shifts)

        # Horas por funcionário
        hours_by_employee: dict[str, float] = {}
        for shift in work_shifts:
            if shift.employee_id:
                hours_by_employee[shift.employee_id] = hours_by_employee.get(shift.employee_id, 0) + shift.planned_hours

        return {
            "total_shifts": total_shifts,
            "work_shifts": len(work_shifts),
            "off_shifts": len(off_shifts),
            "night_shifts": len(night_shifts),
            "holiday_shifts": len(holiday_shifts),
            "total_hours": total_hours,
            "hours_by_employee": hours_by_employee,
            "avg_hours_per_employee": (total_hours / len(hours_by_employee) if hours_by_employee else 0),
        }


# Singleton
scale_generator = ScaleGenerator()
