"""
Schemas para consulta de escalas e turnos do funcionario.
"""

from datetime import date, time

from pydantic import BaseModel, ConfigDict


class MyShiftResponse(BaseModel):
    """Dados de um turno individual do funcionario.

    Attributes:
        date: Data do turno.
        start_time: Horario de inicio.
        end_time: Horario de termino.
        workplace: Nome do posto de trabalho.
        status: Status do turno (agendado, em_andamento, concluido, etc.).
    """

    date: date
    start_time: time
    end_time: time
    workplace: str | None = None
    status: str = "agendado"

    model_config = ConfigDict(from_attributes=True)


class MyScheduleResponse(BaseModel):
    """Resposta com a escala completa do funcionario.

    Attributes:
        employee_name: Nome do funcionario.
        month: Mes da escala.
        year: Ano da escala.
        shifts: Lista de turnos no periodo.
        total_hours: Total de horas escaladas.
    """

    employee_name: str = ""
    month: int = 0
    year: int = 0
    shifts: list[MyShiftResponse] = []
    total_hours: float = 0.0
    # Campos vindos do Employee podem ser NULL no banco -> aceitar None
    # (getattr(default=...) nao protege quando a coluna existe mas e None).
    escala_padrao: str | None = ""
    turno_padrao: str | None = ""
    carga_horaria_semanal: int | None = 0
    jornada_trabalho: str | None = ""
    cargo: str | None = ""
    posto_atual_nome: str | None = None

    model_config = ConfigDict(from_attributes=True, extra="allow")
