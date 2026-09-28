"""
Schemas Pydantic para Ponto Eletronico (Time Records) — Departamento Pessoal.
"""

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TimeRecordStatus(StrEnum):
    """Valores de `gp_clock_punches.status` que o PATCH aceita.

    ⚠️ P7 (28/09/2026): dos SETE valores que este enum tinha, o banco não tinha nenhum além de
    `regular` — e `regular` com 2 linhas. Medido na data:
    `SELECT status, count(*) FROM gp_clock_punches GROUP BY 1` = approved 7174, pending 4169,
    normal 421, fora_local 237, pending_contingencia 109, pendente_de_conferencia 2, regular 2;
    `falta`/`atestado`/`feriado`/`compensacao`/`inconsistencia`/`abono` somam ZERO. O contrato
    descrevia um vocabulário imaginado e **fechava a porta do código que funcionava**: o UPDATE de
    `status` já existia e estava no ar (`update_record`, ramo `if "status" in data`), e
    `PATCH /time-records/{id}` com `status=approved` morria em 422 no Pydantic, antes do handler.

    Os valores REGULAR..ABONO ficam: são vocabulário de classificação de dia que o espelho ainda
    pode usar, e remover valor de enum público quebra chamador que eu não meço daqui. O enum só
    CRESCE, e cresce para caber a coluna.
    """

    REGULAR = "regular"
    FALTA = "falta"
    ATESTADO = "atestado"
    FERIADO = "feriado"
    COMPENSACAO = "compensacao"
    INCONSISTENCIA = "inconsistencia"
    ABONO = "abono"
    #: Decisão do DP sobre o dia (P7). `pending` CONTINUA contando na folha — a aprovação é
    #: trilha e estado visível, não porta de cálculo (decisão do dono: virar essa chave
    #: excluiria 974 batidas do espelho de uma vez, retroativamente).
    APPROVED = "approved"
    PENDING = "pending"
    REJECTED = "rejected"
    #: Estados que o SISTEMA escreve. Estão aqui porque o enum é o vocabulário da COLUNA, e a
    #: única forma de o DP desfazer uma decisão devolvendo a batida ao estado anterior é poder
    #: nomear esse estado. O oráculo `test_oraculo_p7_aprovacao_dia` regra 1 derivou estes quatro
    #: do próprio banco (`SELECT DISTINCT status`) na primeira execução — eu tinha incluído só os
    #: três de decisão e ele reprovou com `['fora_local','normal','pendente_de_conferencia',
    #: 'pending_contingencia']`: 770 batidas cujo estado o contrato não sabia escrever.
    #:
    #: ⚠️ Aceitar o valor NÃO é autorizar o ato: o que conta como decisão auditada do DP é o
    #: conjunto menor em `TimeRecordService._DECISOES`, e `pendente_de_conferencia` continua
    #: intocável pela decisão por dia (`_NUNCA_DECIDIR`) — é a reconferência do rosto no
    #: servidor, não juízo de quem confere o ponto.
    NORMAL = "normal"
    FORA_LOCAL = "fora_local"
    PENDING_CONTINGENCIA = "pending_contingencia"
    PENDENTE_DE_CONFERENCIA = "pendente_de_conferencia"


class RegistrationMethod(StrEnum):
    SYSTEM = "system"
    MANUAL = "manual"
    APP = "app"
    REP = "rep"
    PORTAL = "portal"
    TANGERINO = "tangerino"
    OPERATIONS = "operations"


# --------------- Create / Update ---------------


class ClockInRequest(BaseModel):
    """Requisicao de registro de entrada."""

    employee_id: str = Field(..., description="UUID do funcionario")
    location_lat: float | None = Field(None, description="Latitude GPS")
    location_lng: float | None = Field(None, description="Longitude GPS")
    posto_id: str | None = Field(None, description="ID do posto (opcional)")
    device_type: str = Field("web", description="web|app|rep")
    notes: str | None = None


class ClockOutRequest(BaseModel):
    """Requisicao de registro de saida."""

    location_lat: float | None = Field(None, description="Latitude GPS")
    location_lng: float | None = Field(None, description="Longitude GPS")
    notes: str | None = None


class TimeRecordCreate(BaseModel):
    """Schema para lancamento manual de ponto (admin/DP)."""

    employee_id: str = Field(..., description="UUID do funcionario")
    record_date: date
    clock_in: datetime | None = None
    clock_out: datetime | None = None
    clock_in_lunch: datetime | None = None
    clock_out_lunch: datetime | None = None
    status: TimeRecordStatus = TimeRecordStatus.REGULAR
    justification: str | None = None
    location_lat: float | None = None
    location_lng: float | None = None
    registered_by: RegistrationMethod = RegistrationMethod.MANUAL
    notes: str | None = None


class TimeRecordUpdate(BaseModel):
    """Schema para atualizacao/justificativa de ponto."""

    clock_in: datetime | None = None
    clock_out: datetime | None = None
    clock_in_lunch: datetime | None = None
    clock_out_lunch: datetime | None = None
    status: TimeRecordStatus | None = None
    justification: str | None = None
    notes: str | None = None
    #: Correção do TIPO da batida — o DP conserta o que o app registrou errado.
    #: Só os 4 tipos válidos entram, e a alteração é sempre auditada com quem, de/para e
    #: motivo. O HORÁRIO não muda por aqui: para isso existe o caminho de nova batida com
    #: status ajustado. Ver `TimeRecordService.update_record`.
    punch_type: Literal["entrada", "saida", "saida_almoco", "retorno_almoco"] | None = None
    #: Por que a batida está sendo corrigida OU aprovada/reprovada. Vai para a auditoria — quem
    #: ler daqui a um ano precisa saber, e "corrigido" sozinho não explica nada. Campo ÚNICO de
    #: propósito (P7): é o mesmo slot semântico ("por que eu mexi nisto"), o mesmo destino
    #: (`gp_audit_logs.extra_data.motivo`) e a mesma leitura (`GET .../historico`). Um segundo
    #: campo `observacao` daria duas fontes para a mesma coluna e uma delas ficaria vazia.
    motivo: str | None = Field(None, max_length=300)


# --------------- Response ---------------


class TimeRecordResponse(BaseModel):
    """Resposta de um registro de ponto."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    employee_id: str
    employee_name: str | None = None
    record_date: str
    clock_in: str | None = None
    clock_out: str | None = None
    clock_in_lunch: str | None = None
    clock_out_lunch: str | None = None
    total_hours: str | None = None
    overtime_hours: str | None = None
    status: str = "regular"
    justification: str | None = None
    location_lat: float | None = None
    location_lng: float | None = None
    registered_by: str = "system"
    source: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class TimeRecordListResponse(BaseModel):
    """Resposta paginada de registros de ponto."""

    items: list[TimeRecordResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class MonthlySummaryResponse(BaseModel):
    """Resumo mensal de ponto de um funcionario."""

    employee_id: str
    employee_name: str | None = None
    month: int
    year: int
    total_work_days: int = 0
    total_worked_days: int = 0
    total_hours_worked: str = "00:00"
    total_hours_worked_minutes: int = 0
    total_overtime_minutes: int = 0
    total_overtime: str = "00:00"
    total_late_minutes: int = 0
    total_absences: int = 0
    total_justified_absences: int = 0
    total_unjustified_absences: int = 0
    total_medical_leaves: int = 0
    total_holidays: int = 0
    total_night_hours_minutes: int = 0
    records: list[TimeRecordResponse] = []


class DailyRecordsResponse(BaseModel):
    """Registros de ponto de um dia."""

    date: str
    total_employees: int
    records: list[TimeRecordResponse]
