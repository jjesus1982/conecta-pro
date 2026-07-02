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
    escala_padrao: str = ""
    turno_padrao: str = ""
    carga_horaria_semanal: int = 0
    jornada_trabalho: str = ""
    cargo: str = ""
    posto_atual_nome: str | None = None

    model_config = ConfigDict(from_attributes=True, extra="allow")
