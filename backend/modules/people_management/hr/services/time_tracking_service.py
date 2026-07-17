"""
Serviço de Controle de Ponto — Departamento Pessoal.

Re-exporta funcionalidades do módulo hr/time_tracking e adiciona
método para registro de ponto a partir de dados operacionais (turnos).
"""

import contextlib
import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Re-export do serviço existente
try:
    from modules.hr.time_tracking.services import TimeTrackingService as HRTimeTrackingService
except ImportError:
    HRTimeTrackingService = None  # type: ignore[assignment, misc]

try:
    from modules.hr.time_tracking.models import TimeEntry
except ImportError:
    TimeEntry = None  # type: ignore[assignment, misc]


class TimeTrackingService:
    """Serviço de Controle de Ponto — visão DP."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._hr_service = None
        if HRTimeTrackingService:
            with contextlib.suppress(Exception):
                self._hr_service = HRTimeTrackingService(db)

    async def register_from_operations(
        self,
        employee_id: str | UUID,
        shift_start: datetime,
        shift_end: datetime,
        location_id: str | UUID | None = None,
        notes: str | None = None,
    ) -> dict:
        """Registra ponto a partir de dados de turno operacional.

        Converte informações de turno (escala) em registros de ponto
        no sistema de time tracking.

        Args:
            employee_id: ID do funcionário.
            shift_start: Início do turno.
            shift_end: Fim do turno.
            location_id: ID do local de trabalho.
            notes: Observações adicionais.

        Returns:
            Dicionário com resultado do registro.
        """
        if not TimeEntry:
            logger.warning("Módulo time_tracking não disponível")
            return {
                "status": "unavailable",
                "message": "Módulo de ponto não disponível",
            }

        from uuid import uuid4

        entry = TimeEntry(
            id=uuid4(),
            employee_id=str(employee_id),
            entry_datetime=shift_start,
            entry_date=shift_start.date(),
            entry_time=shift_start.time(),
            entry_type="entrada",
            registration_method="operations",
            employee_name="",
            code=f"OPS-{uuid4().hex[:8]}",
            notes=notes,
        )
        self.db.add(entry)
        await self.db.flush()
        await self.db.refresh(entry)

        duration_hours = (shift_end - shift_start).total_seconds() / 3600

        logger.info(
            "Ponto registrado via operações: employee=%s, duração=%.1fh",
            employee_id,
            duration_hours,
        )
        return {
            "entry_id": str(entry.id),
            "employee_id": str(employee_id),
            "entry_datetime": shift_start.isoformat(),
            "shift_end": shift_end.isoformat(),
            "duration_hours": round(duration_hours, 2),
            "source": "operations",
            "status": "registered",
        }

    async def get_entries(
        self,
        employee_id: str | UUID,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list:
        """Busca registros de ponto de um funcionário.

        Args:
            employee_id: ID do funcionário.
            start_date: Data inicial do filtro.
            end_date: Data final do filtro.

        Returns:
            Lista de registros de ponto.
        """
        if not TimeEntry:
            return []

        try:
            from datetime import date as date_type
            from datetime import datetime as dt_type

            from sqlalchemy import text

            # Buscar de gp_clock_punches (fonte real: Tangerino + portal)
            params = {"emp_id": str(employee_id)}
            date_filter = ""
            if start_date:
                date_filter += " AND (punch_timestamp) >= :start"
                sd = (
                    start_date
                    if isinstance(start_date, (date_type, dt_type))
                    else dt_type.fromisoformat(str(start_date))
                )
                params["start"] = sd
            if end_date:
                date_filter += " AND (punch_timestamp) <= :end"
                ed = end_date if isinstance(end_date, (date_type, dt_type)) else dt_type.fromisoformat(str(end_date))
                if isinstance(ed, date_type) and not isinstance(ed, dt_type):
                    ed = dt_type.combine(ed, dt_type.max.time())
                params["end"] = ed

            sql = text(f"""
                SELECT
                    id,
                    employee_id,
                    (punch_timestamp)::date as date,
                    punch_timestamp::time as time,
                    punch_type as entry_type,
                    status,
                    CASE WHEN punch_id LIKE 'TNG%' THEN 'tangerino' ELSE 'portal' END as source
                FROM gp_clock_punches
                WHERE employee_id = :emp_id
                {date_filter}
                ORDER BY punch_timestamp DESC
                LIMIT 200
            """)
            result = await self.db.execute(sql, params)
            rows = [dict(r) for r in result.mappings().all()]

            # Ordenar por timestamp para emparelhar entrada/saida
            rows.sort(key=lambda r: str(r.get("date", "")) + str(r.get("time", "")))

            def _calc_hours(entrada_time, entrada_date, saida_time, saida_date):
                """Calcula horas reais entre entrada e saida."""
                if not entrada_time or not saida_time:
                    return "00:00", 0
                from datetime import timedelta

                ent = (
                    dt_type.combine(entrada_date, entrada_time)
                    if not isinstance(entrada_time, dt_type)
                    else entrada_time
                )
                sai = dt_type.combine(saida_date, saida_time) if not isinstance(saida_time, dt_type) else saida_time
                if sai < ent:
                    sai += timedelta(days=1)  # turno noturno
                diff = (sai - ent).total_seconds()
                if diff > 16 * 3600:
                    diff = 12 * 3600  # sanidade
                h = int(diff // 3600)
                m = int((diff % 3600) // 60)
                return f"{h:02d}:{m:02d}", diff

            # Emparelhar entrada + saida consecutiva
            entries = []
            i = 0
            while i < len(rows):
                r = rows[i]
                if r["entry_type"] == "entrada":
                    entrada = r
                    saida = None
                    if i + 1 < len(rows) and rows[i + 1]["entry_type"] == "saida":
                        saida = rows[i + 1]
                        i += 1
                    total_str, total_secs = _calc_hours(
                        entrada["time"],
                        entrada["date"],
                        saida["time"] if saida else None,
                        saida["date"] if saida else None,
                    )
                    entries.append(
                        {
                            "date": str(entrada["date"]),
                            "data": str(entrada["date"]),
                            "clock_in": str(entrada["time"])[:5],
                            "entrada": str(entrada["time"])[:5],
                            "clock_out": str(saida["time"])[:5] if saida else None,
                            "saida": str(saida["time"])[:5] if saida else None,
                            "total_hours": total_str,
                            "total": total_str,
                            "status": "normal",
                            "source": entrada.get("source", "tangerino"),
                        }
                    )
                else:
                    entries.append(
                        {
                            "date": str(r["date"]),
                            "data": str(r["date"]),
                            "clock_in": None,
                            "entrada": None,
                            "clock_out": str(r["time"])[:5],
                            "saida": str(r["time"])[:5],
                            "total_hours": "00:00",
                            "total": "00:00",
                            "status": "inconsistencia",
                            "source": r.get("source", "tangerino"),
                        }
                    )
                i += 1

            entries.sort(key=lambda e: e["date"], reverse=True)
            return entries
        except Exception as e:
            logger.warning("Erro ao buscar entries de ponto: %s", e)
            return []
