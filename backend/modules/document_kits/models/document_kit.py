"""Models de Kit Documental."""

from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship

from core.models.base import Base


class KitType(StrEnum):
    """Tipo de kit documental."""

    ADMISSAO = "ADMISSAO"
    DEMISSAO = "DEMISSAO"
    FERIAS = "FERIAS"
    AFASTAMENTO = "AFASTAMENTO"
    PROMOCAO = "PROMOCAO"
    TRANSFERENCIA = "TRANSFERENCIA"
    CONTRATO_CLIENTE = "CONTRATO_CLIENTE"
    ENCERRAMENTO_CONTRATO = "ENCERRAMENTO_CONTRATO"
    MENSAL = "MENSAL"  # Kit de documentos mensais (holerite, vale transporte, etc.)
    TREINAMENTO = "TREINAMENTO"
    CERTIFICACAO = "CERTIFICACAO"
    PORTARIA = "PORTARIA"
    EQUIPAMENTO = "EQUIPAMENTO"
    AUDITORIA = "AUDITORIA"
    LICITACAO = "LICITACAO"
    RENOVACAO = "RENOVACAO"
    OUTRO = "OUTRO"


class KitStatus(StrEnum):
    """Status do kit."""

    RASCUNHO = "RASCUNHO"
    ATIVO = "ATIVO"
    INATIVO = "INATIVO"
    ARQUIVADO = "ARQUIVADO"
    OBSOLETO = "OBSOLETO"


class ItemType(StrEnum):
    """Tipo de item do kit."""

    DOCUMENTO_PESSOAL = "DOCUMENTO_PESSOAL"
    CERTIFICADO = "CERTIFICADO"
    COMPROVANTE = "COMPROVANTE"
    DECLARACAO = "DECLARACAO"
    CONTRATO = "CONTRATO"
    TERMO = "TERMO"
    FORMULARIO = "FORMULARIO"
    FOTO = "FOTO"
    LAUDO = "LAUDO"
    ATESTADO = "ATESTADO"
    REGISTRO = "REGISTRO"
    AUTORIZACAO = "AUTORIZACAO"
    PROCURACAO = "PROCURACAO"
    OUTRO = "OUTRO"


class ItemPriority(StrEnum):
    """Prioridade do item."""

    OBRIGATORIO = "OBRIGATORIO"
    IMPORTANTE = "IMPORTANTE"
    DESEJAVEL = "DESEJAVEL"
    OPCIONAL = "OPCIONAL"


class AssignmentStatus(StrEnum):
    """Status da atribuicao do kit."""

    PENDENTE = "PENDENTE"
    EM_ANDAMENTO = "EM_ANDAMENTO"
    AGUARDANDO_DOCUMENTOS = "AGUARDANDO_DOCUMENTOS"
    EM_ANALISE = "EM_ANALISE"
    APROVADO = "APROVADO"
    REPROVADO = "REPROVADO"
    COMPLETO = "COMPLETO"
    INCOMPLETO = "INCOMPLETO"
    CANCELADO = "CANCELADO"
    EXPIRADO = "EXPIRADO"


class ItemStatusEnum(StrEnum):
    """Status do item na atribuicao."""

    PENDENTE = "PENDENTE"
    ENVIADO = "ENVIADO"
    EM_ANALISE = "EM_ANALISE"
    APROVADO = "APROVADO"
    REPROVADO = "REPROVADO"
    VENCIDO = "VENCIDO"
    NAO_APLICAVEL = "NAO_APLICAVEL"


class EntityType(StrEnum):
    """Tipo de entidade para atribuicao."""

    FUNCIONARIO = "FUNCIONARIO"
    CANDIDATO = "CANDIDATO"
    CONTRATO = "CONTRATO"
    CLIENTE = "CLIENTE"
    FORNECEDOR = "FORNECEDOR"
    EQUIPAMENTO = "EQUIPAMENTO"
    POSTO = "POSTO"
    TREINAMENTO = "TREINAMENTO"
    OUTRO = "OUTRO"


class DocumentKit(Base):
    """Kit de documentos."""

    __tablename__ = "document_kits"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    condominio_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("condominiums.id"),
        nullable=False,
        index=True,
    )

    # Identificacao
    codigo = Column(String(50), nullable=False, index=True)
    nome = Column(String(200), nullable=False)
    descricao = Column(Text)

    # Classificacao
    tipo = Column(
        SQLEnum(KitType, name="kit_type_enum"),
        default=KitType.OUTRO,
        nullable=False,
        index=True,
    )
    status = Column(
        SQLEnum(KitStatus, name="kit_status_enum"),
        default=KitStatus.RASCUNHO,
        nullable=False,
        index=True,
    )

    # Configuracao
    is_template = Column(Boolean, default=False, nullable=False)
    is_obrigatorio = Column(Boolean, default=True, nullable=False)
    prazo_dias = Column(Integer, default=30)
    permite_parcial = Column(Boolean, default=False)
    requer_aprovacao = Column(Boolean, default=True)

    # Aplicabilidade
    entity_types = Column(JSONB, default=list)
    departamentos = Column(JSONB, default=list)
    cargos = Column(JSONB, default=list)

    # Contadores
    total_itens = Column(Integer, default=0, nullable=False)
    itens_obrigatorios = Column(Integer, default=0, nullable=False)
    uso_count = Column(Integer, default=0, nullable=False)

    # Versao
    versao = Column(Integer, default=1, nullable=False)
    versao_anterior_id = Column(PGUUID(as_uuid=True), ForeignKey("document_kits.id"))

    # Metadados
    tags = Column(JSONB, default=list)
    extra_metadata = Column(JSONB, default=dict)

    # Auditoria
    created_by = Column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    updated_by = Column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    itens = relationship(
        "DocumentKitItem",
        back_populates="kit",
        cascade="all, delete-orphan",
        order_by="DocumentKitItem.ordem",
    )
    assignments = relationship(
        "DocumentKitAssignment",
        back_populates="kit",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        """Representacao do kit."""
        return f"<DocumentKit {self.codigo}: {self.nome}>"

    @property
    def is_ativo(self) -> bool:
        """Verifica se kit esta ativo."""
        return self.status == KitStatus.ATIVO

    @property
    def percentual_obrigatorio(self) -> float:
        """Percentual de itens obrigatorios."""
        if self.total_itens == 0:
            return 0.0
        return (self.itens_obrigatorios / self.total_itens) * 100

    def ativar(self) -> None:
        """Ativa o kit."""
        self.status = KitStatus.ATIVO

    def desativar(self) -> None:
        """Desativa o kit."""
        self.status = KitStatus.INATIVO

    def arquivar(self) -> None:
        """Arquiva o kit."""
        self.status = KitStatus.ARQUIVADO

    def incrementar_uso(self) -> None:
        """Incrementa contador de uso."""
        self.uso_count += 1

    def atualizar_contadores(self) -> None:
        """Atualiza contadores de itens."""
        if self.itens:
            self.total_itens = len(self.itens)
            self.itens_obrigatorios = sum(1 for item in self.itens if item.prioridade == ItemPriority.OBRIGATORIO)


class DocumentKitItem(Base):
    """Item de um kit de documentos."""

    __tablename__ = "document_kit_items"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    kit_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("document_kits.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    condominio_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("condominiums.id"),
        nullable=False,
        index=True,
    )

    # Identificacao
    codigo = Column(String(50), nullable=False)
    nome = Column(String(200), nullable=False)
    descricao = Column(Text)
    instrucoes = Column(Text)

    # Classificacao
    tipo = Column(
        SQLEnum(ItemType, name="item_type_enum"),
        default=ItemType.DOCUMENTO_PESSOAL,
        nullable=False,
    )
    prioridade = Column(
        SQLEnum(ItemPriority, name="item_priority_enum"),
        default=ItemPriority.OBRIGATORIO,
        nullable=False,
    )

    # Configuracao
    ordem = Column(Integer, default=0, nullable=False)
    is_ativo = Column(Boolean, default=True, nullable=False)

    # Validacao
    formatos_aceitos = Column(JSONB, default=list)
    tamanho_max_mb = Column(Integer, default=10)
    requer_validade = Column(Boolean, default=False)
    validade_minima_dias = Column(Integer)
    requer_autenticacao = Column(Boolean, default=False)

    # Template
    template_url = Column(String(500))
    exemplo_url = Column(String(500))

    # Dependencias
    depende_de = Column(PGUUID(as_uuid=True), ForeignKey("document_kit_items.id"))

    # Metadados
    tags = Column(JSONB, default=list)
    extra_metadata = Column(JSONB, default=dict)

    # Auditoria
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    kit = relationship("DocumentKit", back_populates="itens")

    def __repr__(self) -> str:
        """Representacao do item."""
        return f"<DocumentKitItem {self.codigo}: {self.nome}>"

    @property
    def is_obrigatorio(self) -> bool:
        """Verifica se item eh obrigatorio."""
        return self.prioridade == ItemPriority.OBRIGATORIO

    @property
    def formatos_display(self) -> str:
        """Retorna formatos aceitos para exibicao."""
        if not self.formatos_aceitos:
            return "Todos"
        return ", ".join(self.formatos_aceitos)


class DocumentKitAssignment(Base):
    """Atribuicao de kit a uma entidade."""

    __tablename__ = "document_kit_assignments"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    kit_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("document_kits.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    condominio_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("condominiums.id"),
        nullable=False,
        index=True,
    )

    # Entidade
    entity_type = Column(
        SQLEnum(EntityType, name="entity_type_enum"),
        nullable=False,
        index=True,
    )
    entity_id = Column(PGUUID(as_uuid=True), nullable=False, index=True)
    entity_nome = Column(String(200))

    # Status
    status = Column(
        SQLEnum(AssignmentStatus, name="assignment_status_enum"),
        default=AssignmentStatus.PENDENTE,
        nullable=False,
        index=True,
    )

    # Prazos
    data_inicio = Column(DateTime, default=datetime.utcnow, nullable=False)
    data_limite = Column(DateTime)
    data_conclusao = Column(DateTime)

    # Progresso
    total_itens = Column(Integer, default=0, nullable=False)
    itens_pendentes = Column(Integer, default=0, nullable=False)
    itens_aprovados = Column(Integer, default=0, nullable=False)
    itens_reprovados = Column(Integer, default=0, nullable=False)
    percentual_completo = Column(Integer, default=0, nullable=False)

    # Responsavel
    responsavel_id = Column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    aprovador_id = Column(PGUUID(as_uuid=True), ForeignKey("users.id"))

    # Observacoes
    observacoes = Column(Text)
    motivo_reprovacao = Column(Text)

    # Notificacoes
    notificacao_enviada = Column(Boolean, default=False)
    ultima_notificacao_at = Column(DateTime)
    notificacoes_count = Column(Integer, default=0)

    # Metadados
    extra_metadata = Column(JSONB, default=dict)

    # Auditoria
    created_by = Column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    approved_by = Column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    approved_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    kit = relationship("DocumentKit", back_populates="assignments")
    item_statuses = relationship(
        "DocumentKitItemStatus",
        back_populates="assignment",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        """Representacao da atribuicao."""
        return f"<DocumentKitAssignment {self.entity_type.value}: {self.entity_nome}>"

    @property
    def is_completo(self) -> bool:
        """Verifica se atribuicao esta completa."""
        return self.status == AssignmentStatus.COMPLETO

    @property
    def is_vencido(self) -> bool:
        """Verifica se atribuicao esta vencida."""
        if not self.data_limite:
            return False
        return datetime.utcnow() > self.data_limite and not self.is_completo

    @property
    def dias_restantes(self) -> int:
        """Dias restantes ate o prazo."""
        if not self.data_limite:
            return -1
        delta = self.data_limite - datetime.utcnow()
        return max(0, delta.days)

    def calcular_progresso(self) -> None:
        """Calcula progresso da atribuicao."""
        if self.total_itens == 0:
            self.percentual_completo = 0
            return
        self.percentual_completo = int((self.itens_aprovados / self.total_itens) * 100)

    def iniciar(self) -> None:
        """Inicia a atribuicao."""
        self.status = AssignmentStatus.EM_ANDAMENTO
        self.data_inicio = datetime.utcnow()

    def aprovar(self, aprovador_id: str) -> None:
        """Aprova a atribuicao."""
        self.status = AssignmentStatus.APROVADO
        self.approved_by = aprovador_id
        self.approved_at = datetime.utcnow()

    def reprovar(self, motivo: str) -> None:
        """Reprova a atribuicao."""
        self.status = AssignmentStatus.REPROVADO
        self.motivo_reprovacao = motivo

    def completar(self) -> None:
        """Marca como completo."""
        self.status = AssignmentStatus.COMPLETO
        self.data_conclusao = datetime.utcnow()
        self.percentual_completo = 100

    def cancelar(self) -> None:
        """Cancela a atribuicao."""
        self.status = AssignmentStatus.CANCELADO

    def registrar_notificacao(self) -> None:
        """Registra envio de notificacao."""
        self.notificacao_enviada = True
        self.ultima_notificacao_at = datetime.utcnow()
        self.notificacoes_count += 1


class DocumentKitItemStatus(Base):
    """Status de um item em uma atribuicao."""

    __tablename__ = "document_kit_item_statuses"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    assignment_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("document_kit_assignments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    item_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("document_kit_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    condominio_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("condominiums.id"),
        nullable=False,
        index=True,
    )

    # Status
    status = Column(
        SQLEnum(ItemStatusEnum, name="item_status_enum"),
        default=ItemStatusEnum.PENDENTE,
        nullable=False,
        index=True,
    )

    # Documento
    documento_id = Column(PGUUID(as_uuid=True))
    arquivo_url = Column(String(500))
    arquivo_nome = Column(String(255))
    arquivo_tamanho = Column(Integer)
    arquivo_tipo = Column(String(100))

    # Validade
    data_validade = Column(DateTime)
    is_vencido = Column(Boolean, default=False)

    # Analise
    analisado_por = Column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    analisado_at = Column(DateTime)
    observacoes_analise = Column(Text)
    motivo_reprovacao = Column(Text)

    # Historico
    tentativas = Column(Integer, default=0, nullable=False)
    historico = Column(JSONB, default=list)

    # Auditoria
    enviado_por = Column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    enviado_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    assignment = relationship("DocumentKitAssignment", back_populates="item_statuses")

    def __repr__(self) -> str:
        """Representacao do status."""
        return f"<DocumentKitItemStatus {self.item_id}: {self.status.value}>"

    @property
    def is_aprovado(self) -> bool:
        """Verifica se item esta aprovado."""
        return self.status == ItemStatusEnum.APROVADO

    @property
    def is_pendente(self) -> bool:
        """Verifica se item esta pendente."""
        return self.status == ItemStatusEnum.PENDENTE

    @property
    def precisa_reenvio(self) -> bool:
        """Verifica se precisa reenvio."""
        return self.status in (ItemStatusEnum.REPROVADO, ItemStatusEnum.VENCIDO)

    def enviar(self, arquivo_url: str, arquivo_nome: str, enviado_por: str) -> None:
        """Registra envio do documento."""
        self.status = ItemStatusEnum.ENVIADO
        self.arquivo_url = arquivo_url
        self.arquivo_nome = arquivo_nome
        self.enviado_por = enviado_por
        self.enviado_at = datetime.utcnow()
        self.tentativas += 1
        self._adicionar_historico("ENVIADO", f"Documento {arquivo_nome} enviado")

    def analisar(self) -> None:
        """Marca como em analise."""
        self.status = ItemStatusEnum.EM_ANALISE
        self._adicionar_historico("EM_ANALISE", "Documento em analise")

    def aprovar(self, analisado_por: str, observacoes: str = None) -> None:
        """Aprova o documento."""
        self.status = ItemStatusEnum.APROVADO
        self.analisado_por = analisado_por
        self.analisado_at = datetime.utcnow()
        self.observacoes_analise = observacoes
        self._adicionar_historico("APROVADO", observacoes or "Documento aprovado")

    def reprovar(self, analisado_por: str, motivo: str) -> None:
        """Reprova o documento."""
        self.status = ItemStatusEnum.REPROVADO
        self.analisado_por = analisado_por
        self.analisado_at = datetime.utcnow()
        self.motivo_reprovacao = motivo
        self._adicionar_historico("REPROVADO", motivo)

    def marcar_vencido(self) -> None:
        """Marca como vencido."""
        self.status = ItemStatusEnum.VENCIDO
        self.is_vencido = True
        self._adicionar_historico("VENCIDO", "Documento com validade expirada")

    def marcar_nao_aplicavel(self, motivo: str = None) -> None:
        """Marca como nao aplicavel."""
        self.status = ItemStatusEnum.NAO_APLICAVEL
        self._adicionar_historico("NAO_APLICAVEL", motivo or "Item nao aplicavel")

    def _adicionar_historico(self, acao: str, descricao: str) -> None:
        """Adiciona entrada ao historico."""
        if not self.historico:
            self.historico = []
        self.historico.append(
            {
                "acao": acao,
                "descricao": descricao,
                "data": datetime.utcnow().isoformat(),
            }
        )
