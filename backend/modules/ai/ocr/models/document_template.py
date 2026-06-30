"""DocumentTemplate Model - Templates para extracao de documentos.

Sprint 39 - Document OCR.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

from core.models.base import Base
from modules.ai.ocr.models.document_scan import DocumentScanType
from modules.ai.ocr.models.extracted_field import FieldType


class RuleType(StrEnum):
    """Tipo de regra de extracao."""

    REGEX = "regex"  # Expressao regular
    KEYWORD = "keyword"  # Palavra-chave + offset
    POSITION = "position"  # Posicao absoluta
    RELATIVE = "relative"  # Posicao relativa a outro campo
    KEY_VALUE = "key_value"  # Par chave-valor
    TABLE_CELL = "table_cell"  # Celula de tabela
    AFTER_LABEL = "after_label"  # Apos um label
    BETWEEN = "between"  # Entre dois marcadores
    ML_MODEL = "ml_model"  # Modelo de ML
    CUSTOM = "custom"  # Regra customizada


class DocumentTemplate(Base):
    """Modelo de template de documento para extracao."""

    __tablename__ = "ocr_document_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Identificacao
    template_id = Column(String(100), nullable=False, unique=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    version = Column(String(20), default="1.0.0")

    # Tipo de documento
    document_type = Column(Enum(DocumentScanType, values_callable=lambda x: [e.value for e in x]), nullable=False)
    document_subtype = Column(String(100))  # Subtipo especifico

    # Deteccao automatica
    detection_keywords = Column(ARRAY(String), default=[])
    detection_patterns = Column(JSONB, default=[])
    # Estrutura: [{"type": "regex", "pattern": "DANFE|NFe"}]
    detection_threshold = Column(Float, default=0.8)

    # Layouts suportados
    supported_layouts = Column(JSONB, default=[])
    # Estrutura: [{"name": "padrao", "orientation": "portrait", "regions": [...]}]

    # Regioes de interesse (ROI)
    regions = Column(JSONB, default=[])
    # Estrutura: [
    #   {
    #     "name": "header",
    #     "type": "header|body|footer|sidebar",
    #     "bounding_box": {"x": 0, "y": 0, "width": 100, "height": 20},
    #     "relative": true
    #   }
    # ]

    # Configuracoes de OCR
    ocr_settings = Column(JSONB, default={})
    # Estrutura: {
    #   "provider": "google_vision",
    #   "language": "por",
    #   "dpi": 300,
    #   "preprocessing": ["deskew", "enhance_contrast"]
    # }

    # Preprocessamento
    preprocessing_steps = Column(JSONB, default=[])
    # Estrutura: ["deskew", "rotate_auto", "enhance", "remove_noise", "binarize"]

    # Validacao
    validation_rules = Column(JSONB, default=[])
    # Estrutura: [
    #   {"field": "cnpj", "rule": "cnpj_valid"},
    #   {"field": "total", "rule": "sum_equals", "params": {"fields": ["item_*"]}}
    # ]

    # Mapeamento
    field_mapping = Column(JSONB, default={})
    # Estrutura: {
    #   "cnpj_emitente": {"entity": "supplier", "field": "cnpj"},
    #   "valor_total": {"entity": "invoice", "field": "total_amount"}
    # }

    # Metricas
    times_used = Column(Integer, default=0)
    success_rate = Column(Float)  # Taxa de sucesso
    avg_confidence = Column(Float)  # Confianca media
    avg_processing_time_ms = Column(Integer)
    last_used_at = Column(DateTime)

    # Controle de versao
    parent_version_id = Column(UUID(as_uuid=True))  # Versao anterior
    is_latest = Column(Boolean, default=True)
    published_at = Column(DateTime)
    published_by = Column(UUID(as_uuid=True))

    # Tags e categorias
    tags = Column(ARRAY(String), default=[])
    category = Column(String(100))

    # Metadata
    extra_data = Column(JSONB, default={})

    # Controle
    active = Column(Boolean, default=True, index=True)
    created_by = Column(UUID(as_uuid=True))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        """Representacao string."""
        return f"<DocumentTemplate {self.name} ({self.document_type.value})>"

    def matches_document(self, text: str) -> float:
        """Verifica se o texto corresponde ao template."""
        if not text or not self.detection_keywords:
            return 0.0

        text_lower = text.lower()
        matches = 0
        for keyword in self.detection_keywords:
            if keyword.lower() in text_lower:
                matches += 1

        if not self.detection_keywords:
            return 0.0

        score = matches / len(self.detection_keywords)
        return score

    def get_fields(self) -> list["TemplateField"]:
        """Retorna campos do template (deve ser carregado via relacionamento)."""
        return []


class TemplateField(Base):
    """Modelo de campo do template."""

    __tablename__ = "ocr_template_fields"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    template_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Identificacao
    field_id = Column(String(100), nullable=False)
    name = Column(String(100), nullable=False)
    label = Column(String(200))
    description = Column(Text)

    # Tipo
    field_type = Column(Enum(FieldType, values_callable=lambda x: [e.value for e in x]), nullable=False)
    field_group = Column(String(100))  # Agrupamento logico

    # Extracao
    extraction_rules = Column(JSONB, default=[])
    # Estrutura: [
    #   {"type": "regex", "pattern": "CNPJ[:\\s]*([\\d./-]+)", "group": 1},
    #   {"type": "keyword", "keyword": "CNPJ", "offset_x": 100, "width": 150}
    # ]

    # Posicao esperada
    expected_region = Column(String(100))  # Nome da regiao
    expected_position = Column(JSONB)  # Posicao absoluta/relativa
    position_tolerance = Column(Integer, default=20)  # Tolerancia em pixels

    # Alternativas
    alternative_labels = Column(ARRAY(String), default=[])
    alternative_patterns = Column(JSONB, default=[])

    # Validacao
    is_required = Column(Boolean, default=False)
    validation_rules = Column(JSONB, default=[])
    # Estrutura: [
    #   {"type": "format", "pattern": "\\d{2}\\.\\d{3}\\.\\d{3}/\\d{4}-\\d{2}"},
    #   {"type": "checksum", "algorithm": "cnpj"},
    #   {"type": "range", "min": 0, "max": 1000000}
    # ]

    # Transformacao
    transformations = Column(JSONB, default=[])
    # Estrutura: [
    #   {"type": "remove_chars", "chars": ".-/"},
    #   {"type": "uppercase"},
    #   {"type": "parse_date", "format": "DD/MM/YYYY"}
    # ]

    # Valor padrao
    default_value = Column(Text)
    default_if_empty = Column(Boolean, default=False)

    # Mapeamento
    target_entity = Column(String(100))
    target_field = Column(String(100))

    # Dependencias
    depends_on = Column(ARRAY(String), default=[])  # Campos que devem existir antes
    related_fields = Column(ARRAY(String), default=[])  # Campos relacionados

    # Ordem e prioridade
    extraction_order = Column(Integer, default=0)
    priority = Column(Integer, default=50)

    # Flags
    is_key_field = Column(Boolean, default=False)
    is_calculated = Column(Boolean, default=False)
    allow_multiple = Column(Boolean, default=False)  # Permite multiplos valores
    merge_strategy = Column(String(50))  # first, last, concat, highest_confidence

    # Metricas
    extraction_success_rate = Column(Float)
    avg_confidence = Column(Float)

    # Metadata
    extra_data = Column(JSONB, default={})

    # Controle
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        """Representacao string."""
        return f"<TemplateField {self.name} ({self.field_type.value})>"


class ExtractionRule(Base):
    """Modelo de regra de extracao (para reuso)."""

    __tablename__ = "ocr_extraction_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Identificacao
    rule_id = Column(String(100), nullable=False, unique=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)

    # Tipo e definicao
    rule_type = Column(Enum(RuleType, values_callable=lambda x: [e.value for e in x]), nullable=False)
    rule_definition = Column(JSONB, nullable=False)
    # Estrutura varia por tipo:
    # - regex: {"pattern": "...", "group": 1, "flags": "i"}
    # - keyword: {"keyword": "CNPJ", "offset_x": 100, "offset_y": 0, "width": 150}
    # - position: {"x": 100, "y": 200, "width": 200, "height": 20}
    # - key_value: {"key_patterns": ["CNPJ:", "CNPJ"], "value_offset": 50}

    # Aplicabilidade
    applicable_field_types = Column(ARRAY(String), default=[])
    applicable_document_types = Column(ARRAY(String), default=[])

    # Transformacao associada
    transformations = Column(JSONB, default=[])

    # Metricas
    times_used = Column(Integer, default=0)
    success_rate = Column(Float)
    avg_confidence = Column(Float)

    # Tags
    tags = Column(ARRAY(String), default=[])
    category = Column(String(100))

    # Controle
    active = Column(Boolean, default=True)
    is_system = Column(Boolean, default=False)  # Regra do sistema
    created_by = Column(UUID(as_uuid=True))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        """Representacao string."""
        return f"<ExtractionRule {self.name} ({self.rule_type.value})>"
