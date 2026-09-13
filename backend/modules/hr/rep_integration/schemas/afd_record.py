"""Schemas Pydantic para AFDRecord."""

from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AFDRecordBase(BaseModel):
    """Schema base para AFDRecord."""

    nsr: int = Field(
        ...,
        ge=1,
        description="Número Sequencial de Registro",
    )
    record_type: str = Field(
        ...,
        min_length=1,
        max_length=1,
        pattern="^[1-49]$",
        description="Tipo de registro AFD (1-4, 9)",
    )
    afd_line: str = Field(
        ...,
        min_length=10,
        max_length=400,  # frente 01: tipo 2 tem 331 posições; 200 fazia /afd/records dar 500
        description="Linha AFD formatada",
    )


class AFDRecordCreate(AFDRecordBase):
    """Schema para criar AFDRecord."""

    device_id: UUID
    condominio_id: UUID
    record_date: date | None = None
    record_time: time | None = None
    pis_number: str | None = None
    cnpj: str | None = None
    cei: str | None = None
    company_name: str | None = None
    rep_serial: str | None = None
    rep_manufacturer: str | None = None
    rep_model: str | None = None
    generation_date: datetime | None = None
    start_date: date | None = None
    end_date: date | None = None
    original_date: date | None = None
    original_time: time | None = None
    adjusted_date: date | None = None
    adjusted_time: time | None = None
    event_id: UUID | None = None
    line_hash: str


class AFDRecordResponse(AFDRecordBase):
    """Schema de resposta para AFDRecord."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    device_id: UUID
    condominio_id: UUID
    record_date: date | None = None
    record_time: time | None = None
    pis_number: str | None = None
    event_id: UUID | None = None
    line_hash: str
    is_exported: bool
    exported_at: datetime | None = None
    is_valid: bool
    validation_error: str | None = None
    created_at: datetime


class AFDRecordList(BaseModel):
    """Schema para lista de registros AFD."""

    items: list[AFDRecordResponse]
    total: int
    page: int
    page_size: int
    pages: int


class AFDRecordFilter(BaseModel):
    """Filtros para busca de registros AFD."""

    device_id: UUID | None = None
    condominio_id: UUID | None = None
    record_type: str | None = None
    pis_number: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    is_exported: bool | None = None
    is_valid: bool | None = None
    nsr_from: int | None = None
    nsr_to: int | None = None


class AFDExportRequest(BaseModel):
    """Schema para exportar AFD."""

    device_id: UUID
    start_date: date = Field(
        ...,
        description="Data inicial do período",
    )
    end_date: date = Field(
        ...,
        description="Data final do período",
    )
    include_header: bool = Field(
        default=True,
        description="Incluir registro tipo 1 (cabeçalho)",
    )
    include_company: bool = Field(
        default=True,
        description="Incluir registro tipo 2 (empregador)",
    )
    include_trailer: bool = Field(
        default=True,
        description="Incluir registro tipo 9 (trailer)",
    )
    format: str = Field(
        default="txt",
        pattern="^(txt|csv)$",
        description="Formato de exportação",
    )


class AFDExportResponse(BaseModel):
    """Resposta da exportação AFD."""

    success: bool
    file_path: str | None = None
    file_name: str
    total_records: int
    period_start: date
    period_end: date
    generated_at: datetime
    file_size_bytes: int
    checksum: str
    download_url: str | None = None


class AFDValidationResult(BaseModel):
    """Resultado da validação de arquivo AFD."""

    is_valid: bool
    total_lines: int
    valid_lines: int
    invalid_lines: int
    errors: list[dict]
    warnings: list[dict]
    header_info: dict | None = None
    company_info: dict | None = None
    records_count: int
    date_range_start: date | None = None
    date_range_end: date | None = None


class AFDImportRequest(BaseModel):
    """Schema para importar arquivo AFD."""

    device_id: UUID
    file_content: str = Field(
        ...,
        description="Conteúdo do arquivo AFD",
    )
    validate_only: bool = Field(
        default=False,
        description="Apenas validar, não importar",
    )
    skip_duplicates: bool = Field(
        default=True,
        description="Ignorar registros já existentes",
    )


class AFDImportResponse(BaseModel):
    """Resposta da importação AFD."""

    success: bool
    total_lines: int
    imported_records: int
    skipped_records: int
    error_records: int
    errors: list[dict] | None = None
    validation_result: AFDValidationResult | None = None
