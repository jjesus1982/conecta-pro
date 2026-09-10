"""
Modelo KitDocument — Documento individual dentro de um Kit.

Cada documento pode ser um contracheque, folha de ponto, certidão,
guia de recolhimento, ASO, etc. Pode ser gerado automaticamente
por outros módulos ou incluído manualmente.
"""

from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, String, Text, event, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class DocumentType(StrEnum):
    """Tipos de documento suportados pelo GED."""

    # Documentos do funcionário (mensais)
    CONTRACHEQUE = "contracheque"
    FOLHA_PONTO = "folha_ponto"
    COMPROVANTE_VT = "comprovante_vt"
    COMPROVANTE_VA = "comprovante_va"
    COMPROVANTE_VR = "comprovante_vr"

    # Documentos disciplinares
    ADVERTENCIA = "advertencia"
    SUSPENSAO = "suspensao"

    # Documentos de saúde
    ATESTADO_MEDICO = "atestado_medico"

    # Eventos trabalhistas
    FERIAS = "ferias"
    RESCISAO = "rescisao"

    # Certidões negativas da empresa
    CND_FEDERAL = "cnd_federal"
    CND_ESTADUAL = "cnd_estadual"
    CND_MUNICIPAL = "cnd_municipal"
    CRF_FGTS = "crf_fgts"
    CNDT_TRABALHISTA = "cndt_trabalhista"

    # Guias de recolhimento
    GFIP_SEFIP = "gfip_sefip"
    GRF_FGTS = "grf_fgts"
    GPS_INSS = "gps_inss"

    # Documentos admissionais/contratuais
    CONTRATO_TRABALHO = "contrato_trabalho"
    ASO_ADMISSIONAL = "aso_admissional"
    ASO_PERIODICO = "aso_periodico"
    ASO_DEMISSIONAL = "aso_demissional"

    # Documentos fiscais e operacionais
    NFS_SERVICO = "nfs_servico"
    BOLETO = "boleto"
    # 09/09/2026 (lista da Pyetra): o bloco de benefícios do kit real tem 5 documentos da EMPRESA além do recibo
    # do funcionário — a compra dos créditos, o pedido por colaborador e o comprovante de pagamento de cada um.
    BOLETO_VT_SINETRAM = "boleto_vt_sinetram"
    RELATORIO_VT_SINETRAM = "relatorio_vt_sinetram"
    RELATORIO_VA_SOLIDES = "relatorio_va_solides"
    COMPROVANTE_PAGTO_SINETRAM = "comprovante_pagto_sinetram"
    COMPROVANTE_PAGTO_SOLIDES = "comprovante_pagto_solides"
    RECIBO_ADIANTAMENTO = "recibo_adiantamento"  # 09/09: adiantamento salarial (40% no dia 20)
    COMPROVANTE_PAGAMENTO = "comprovante_pagamento"  # 09/09: comprovante PIX/TED do salário (40% e 60%)  # 09/09/2026: boleto da competência entra no kit (simulado em homologação; Inter no real)
    ESCALA_MES = "escala_mes"

    # Documentos fiscais — Simples Nacional / ISSQN / SEFAZ
    DAS_SIMPLES_NACIONAL = "das_simples_nacional"
    PARCELAMENTO_SIMPLES = "parcelamento_simples"
    GUIA_ISSQN = "guia_issqn"
    DAR_SEFAZ = "dar_sefaz"

    # DCTFWeb — variantes (resumos, créditos, débitos)
    DCTFWEB_RESUMO_CREDITOS = "dctfweb_resumo_creditos"
    DCTFWEB_RESUMO_DEBITOS = "dctfweb_resumo_debitos"
    DCTFWEB_CREDITOS = "dctfweb_creditos"
    DCTFWEB_DEBITOS = "dctfweb_debitos"

    # Folha — eventos especiais
    DECIMO_TERCEIRO = "decimo_terceiro"

    # Genérico
    OUTRO = "outro"


class SourceModule(StrEnum):
    """Módulo de origem do documento."""

    DP = "dp"
    RH = "rh"
    FISCAL = "fiscal"
    OPERACOES = "operacoes"
    MANUAL = "manual"


class KitDocument(Base):
    """Documento individual pertencente a um kit documental.

    Pode representar um documento por funcionário (ex: contracheque)
    ou um documento da empresa (ex: CND federal).
    """

    __tablename__ = "ged_kit_documents"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    kit_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="FK para ged_document_kits.id",
    )
    employee_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        comment="FK para employees.id (nulo para docs da empresa)",
    )

    # Tipo e identificação
    document_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
        comment="Tipo do documento (contracheque, folha_ponto, etc.)",
    )
    document_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Nome de exibição do documento",
    )

    # Arquivo
    file_path: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment="Caminho no storage (local ou S3)",
    )
    file_size_bytes: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Tamanho do arquivo em bytes",
    )
    mime_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        default="application/pdf",
        comment="MIME type do arquivo",
    )

    # Assinatura
    is_signed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Se o documento foi assinado digitalmente",
    )
    signed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    signed_by: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="FK para employees.id — quem assinou",
    )
    signature_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="Hash SHA-256 do arquivo assinado",
    )

    # Rastreabilidade de origem
    source_module: Mapped[str] = mapped_column(
        String(20),
        default=SourceModule.MANUAL,
        nullable=False,
        comment="Módulo que gerou o documento (dp, rh, fiscal, operacoes, manual)",
    )
    source_record_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="ID do registro de origem no módulo fonte",
    )
    auto_generated: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Se foi gerado automaticamente por integração entre módulos",
    )

    # Observações
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<KitDocument(id={self.id}, type={self.document_type}, "
            f"name={self.document_name}, signed={self.is_signed})>"
        )


# ── Assinado exige arquivo ────────────────────────────────────────────────────────────────────────
# 10/09/2026: vários coletores criam o SLOT do documento antes do arquivo existir ("a certidão já vem
# assinada pelo órgão", "a guia o contador emite no Onvio") e marcavam is_signed=True num slot vazio.
# Resultado medido: 231 linhas em 09/09 e mais 143 no dia seguinte dizendo "assinado" sem um PDF atrás,
# inflando a completude de todo kit. Corrigir call site por call site não segura: são doze, e o próximo
# coletor repete. A regra mora aqui, onde toda escrita passa.
@event.listens_for(KitDocument, "before_insert")
@event.listens_for(KitDocument, "before_update")
def _assinado_exige_arquivo(mapper, connection, target) -> None:  # noqa: ANN001, ARG001
    if target.is_signed and not target.file_path:
        target.is_signed = False
