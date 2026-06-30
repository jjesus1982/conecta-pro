"""
Models de Checklist - Modulo Campo
==================================

Sistema de Checklist Dinamico para Ordens de Servico.
Templates reutilizaveis com diferentes tipos de perguntas.
"""

from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from core.models.base import Base

# =============================================================================
# ENUMS
# =============================================================================


class TipoServico(StrEnum):
    """Tipo de servico ao qual o checklist se aplica."""

    INSTALACAO = "instalacao"
    MANUTENCAO_PREVENTIVA = "manutencao_preventiva"
    MANUTENCAO_CORRETIVA = "manutencao_corretiva"
    VISITA_TECNICA = "visita_tecnica"
    VISTORIA = "vistoria"
    RETIRADA = "retirada"
    TROCA = "troca"
    SUPORTE = "suporte"
    GERAL = "geral"


class TipoResposta(StrEnum):
    """Tipo de resposta esperada para o item."""

    TEXTO = "texto"
    TEXTO_LONGO = "texto_longo"
    NUMERO = "numero"
    DECIMAL = "decimal"
    SIM_NAO = "sim_nao"
    CONFORME_NAO_CONFORME = "conforme_nao_conforme"
    FOTO = "foto"
    FOTOS_MULTIPLAS = "fotos_multiplas"
    ASSINATURA = "assinatura"
    MULTIPLA_ESCOLHA = "multipla_escolha"
    SELECAO_UNICA = "selecao_unica"
    DATA = "data"
    HORA = "hora"
    DATA_HORA = "data_hora"
    GEOLOCALIZACAO = "geolocalizacao"
    ARQUIVO = "arquivo"


class CategoriaItem(StrEnum):
    """Categoria do item do checklist."""

    VERIFICACAO = "verificacao"
    MEDICAO = "medicao"
    DOCUMENTACAO = "documentacao"
    SEGURANCA = "seguranca"
    QUALIDADE = "qualidade"
    LIMPEZA = "limpeza"
    EQUIPAMENTO = "equipamento"
    MATERIAL = "material"
    CONCLUSAO = "conclusao"


# =============================================================================
# MODEL - TEMPLATE
# =============================================================================


class ChecklistTemplate(Base):
    """
    Template de Checklist Reutilizavel.

    Define a estrutura de um checklist que pode ser aplicado
    a diferentes Ordens de Servico do mesmo tipo.
    """

    __tablename__ = "checklist_templates"
    __table_args__ = (Index("ix_checklist_template_tipo", "tipo_servico"), {})

    # =========================================================================
    # Identificacao
    # =========================================================================
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    codigo = Column(String(50), unique=True, nullable=False, index=True)
    # Formato: CHK-INST-001

    nome = Column(String(200), nullable=False)
    descricao = Column(Text)

    # =========================================================================
    # Classificacao
    # =========================================================================
    tipo_servico = Column(
        Enum(TipoServico, values_callable=lambda x: [e.value for e in x]), nullable=False, default=TipoServico.GERAL
    )
    categoria_equipamento = Column(String(100))  # "cameras", "alarmes", "portaria", etc.
    versao = Column(String(20), default="1.0")

    # =========================================================================
    # Configuracao
    # =========================================================================
    is_obrigatorio = Column(Boolean, default=False)
    # Se True, tecnico deve preencher para concluir OS

    permite_itens_adicionais = Column(Boolean, default=False)
    # Se True, tecnico pode adicionar itens durante execucao

    tempo_estimado_minutos = Column(Integer, default=15)
    pontuacao_maxima = Column(Integer)
    # Para checklists com scoring

    # =========================================================================
    # Visibilidade
    # =========================================================================
    is_ativo = Column(Boolean, default=True, nullable=False)
    visivel_cliente = Column(Boolean, default=False)
    # Se True, cliente pode ver o checklist preenchido

    # =========================================================================
    # Metadata
    # =========================================================================
    tags = Column(JSONB, default=list)
    extra_metadata = Column(JSONB, default=dict)

    # Auditoria
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # =========================================================================
    # Relacionamentos
    # =========================================================================
    itens = relationship(
        "ChecklistItem", back_populates="template", cascade="all, delete-orphan", order_by="ChecklistItem.ordem"
    )

    # =========================================================================
    # Propriedades
    # =========================================================================
    @property
    def total_itens(self) -> int:
        """Total de itens no template."""
        return len(self.itens) if self.itens else 0

    @property
    def itens_obrigatorios(self) -> int:
        """Total de itens obrigatorios."""
        if not self.itens:
            return 0
        return sum(1 for item in self.itens if item.obrigatorio)

    # =========================================================================
    # Metodos
    # =========================================================================
    def gerar_codigo(self, tipo_abrev: str, sequencial: int) -> str:
        """Gera codigo do template."""
        self.codigo = f"CHK-{tipo_abrev.upper()}-{sequencial:03d}"
        return self.codigo

    def adicionar_item(self, pergunta: str, tipo_resposta: TipoResposta, **kwargs) -> "ChecklistItem":
        """Adiciona item ao template."""
        ordem = len(self.itens) + 1 if self.itens else 1
        item = ChecklistItem(template_id=self.id, ordem=ordem, pergunta=pergunta, tipo_resposta=tipo_resposta, **kwargs)
        if not self.itens:
            self.itens = []
        self.itens.append(item)
        return item

    def reordenar_itens(self, nova_ordem: list[str]):
        """Reordena itens conforme lista de IDs."""
        if not self.itens:
            return
        item_dict = {str(item.id): item for item in self.itens}
        for idx, item_id in enumerate(nova_ordem, 1):
            if item_id in item_dict:
                item_dict[item_id].ordem = idx

    def clonar(self, novo_nome: str) -> "ChecklistTemplate":
        """Cria copia do template."""
        novo = ChecklistTemplate(
            nome=novo_nome,
            descricao=self.descricao,
            tipo_servico=self.tipo_servico,
            categoria_equipamento=self.categoria_equipamento,
            is_obrigatorio=self.is_obrigatorio,
            permite_itens_adicionais=self.permite_itens_adicionais,
            tempo_estimado_minutos=self.tempo_estimado_minutos,
            tags=self.tags.copy() if self.tags else [],
        )
        return novo

    def __repr__(self) -> str:
        return f"<ChecklistTemplate {self.codigo} - {self.nome}>"


# =============================================================================
# MODEL - ITEM
# =============================================================================


class ChecklistItem(Base):
    """
    Item do Checklist (pergunta/verificacao).

    Define uma pergunta ou verificacao dentro do template.
    """

    __tablename__ = "checklist_itens"
    __table_args__ = (Index("ix_checklist_item_template", "template_id"), {})

    # =========================================================================
    # Identificacao
    # =========================================================================
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    template_id = Column(UUID(as_uuid=True), ForeignKey("checklist_templates.id"), nullable=False)

    # =========================================================================
    # Ordem e Agrupamento
    # =========================================================================
    ordem = Column(Integer, nullable=False, default=1)
    secao = Column(String(100))  # Agrupamento visual
    secao_ordem = Column(Integer, default=1)

    # =========================================================================
    # Pergunta
    # =========================================================================
    pergunta = Column(String(500), nullable=False)
    descricao = Column(Text)  # Instrucoes adicionais
    categoria = Column(
        Enum(CategoriaItem, values_callable=lambda x: [e.value for e in x]), default=CategoriaItem.VERIFICACAO
    )

    # =========================================================================
    # Tipo de Resposta
    # =========================================================================
    tipo_resposta = Column(
        Enum(TipoResposta, values_callable=lambda x: [e.value for e in x]), nullable=False, default=TipoResposta.SIM_NAO
    )

    # Opcoes para multipla escolha/selecao unica
    opcoes = Column(JSONB, default=list)
    # [{"valor": "ok", "label": "OK"}, {"valor": "nok", "label": "Nao OK"}]

    # Validacao para tipos numericos
    valor_minimo = Column(Numeric(10, 2))
    valor_maximo = Column(Numeric(10, 2))
    unidade_medida = Column(String(20))  # "mm", "V", "A", "°C", etc.

    # Valor padrao
    valor_padrao = Column(String(500))

    # =========================================================================
    # Obrigatoriedade
    # =========================================================================
    obrigatorio = Column(Boolean, default=True)

    # Condicional - item so aparece se outro item tiver certa resposta
    condicional_item_id = Column(UUID(as_uuid=True), ForeignKey("checklist_itens.id"), nullable=True)
    condicional_valor = Column(String(100))
    # Ex: Se item X = "sim", mostrar este item

    # =========================================================================
    # Scoring
    # =========================================================================
    pontos = Column(Integer, default=0)
    # Pontuacao do item para checklists com scoring

    peso = Column(Numeric(3, 2), default=1.0)
    # Peso para calculo de conformidade

    # =========================================================================
    # Alerta
    # =========================================================================
    gera_alerta = Column(Boolean, default=False)
    alerta_condicao = Column(String(100))
    # Ex: "valor < 10" ou "resposta = nao"
    alerta_mensagem = Column(String(300))
    alerta_severidade = Column(String(20), default="warning")
    # "info", "warning", "critical"

    # =========================================================================
    # Metadata
    # =========================================================================
    extra_metadata = Column(JSONB, default=dict)

    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # =========================================================================
    # Relacionamentos
    # =========================================================================
    template = relationship("ChecklistTemplate", back_populates="itens")

    # =========================================================================
    # Propriedades
    # =========================================================================
    @property
    def tem_condicional(self) -> bool:
        """Verifica se item tem condicao de exibicao."""
        return self.condicional_item_id is not None

    @property
    def requer_foto(self) -> bool:
        """Verifica se item requer foto."""
        return self.tipo_resposta in [TipoResposta.FOTO, TipoResposta.FOTOS_MULTIPLAS]

    @property
    def requer_assinatura(self) -> bool:
        """Verifica se item requer assinatura."""
        return self.tipo_resposta == TipoResposta.ASSINATURA

    # =========================================================================
    # Metodos
    # =========================================================================
    def validar_resposta(self, valor) -> tuple[bool, str | None]:
        """Valida resposta conforme tipo e restricoes."""
        if self.obrigatorio and valor is None:
            return False, "Resposta obrigatoria"

        if valor is None:
            return True, None

        # Validacao numerica
        if self.tipo_resposta in [TipoResposta.NUMERO, TipoResposta.DECIMAL]:
            try:
                num = float(valor)
                if self.valor_minimo is not None and num < float(self.valor_minimo):
                    return False, f"Valor minimo: {self.valor_minimo}"
                if self.valor_maximo is not None and num > float(self.valor_maximo):
                    return False, f"Valor maximo: {self.valor_maximo}"
            except ValueError:
                return False, "Valor numerico invalido"

        # Validacao multipla escolha
        if self.tipo_resposta in [TipoResposta.SELECAO_UNICA, TipoResposta.MULTIPLA_ESCOLHA]:
            valores_validos = [op.get("valor") for op in (self.opcoes or [])]
            if self.tipo_resposta == TipoResposta.SELECAO_UNICA:
                if valor not in valores_validos:
                    return False, "Opcao invalida"
            else:
                if not isinstance(valor, list):
                    return False, "Esperado lista de valores"
                for v in valor:
                    if v not in valores_validos:
                        return False, f"Opcao invalida: {v}"

        return True, None

    def verificar_alerta(self, valor) -> dict | None:
        """Verifica se resposta gera alerta."""
        if not self.gera_alerta or not self.alerta_condicao:
            return None

        # Avaliar condicao simples
        condicao = self.alerta_condicao.lower()

        if "=" in condicao and "<" not in condicao and ">" not in condicao:
            # Igualdade
            esperado = condicao.split("=")[1].strip()
            if str(valor).lower() == esperado:
                return {
                    "item_id": str(self.id),
                    "pergunta": self.pergunta,
                    "mensagem": self.alerta_mensagem,
                    "severidade": self.alerta_severidade,
                    "valor": valor,
                }

        elif "<" in condicao:
            # Menor que
            try:
                limite = float(condicao.split("<")[1].strip())
                if float(valor) < limite:
                    return {
                        "item_id": str(self.id),
                        "pergunta": self.pergunta,
                        "mensagem": self.alerta_mensagem,
                        "severidade": self.alerta_severidade,
                        "valor": valor,
                    }
            except (ValueError, TypeError):
                pass

        elif ">" in condicao:
            # Maior que
            try:
                limite = float(condicao.split(">")[1].strip())
                if float(valor) > limite:
                    return {
                        "item_id": str(self.id),
                        "pergunta": self.pergunta,
                        "mensagem": self.alerta_mensagem,
                        "severidade": self.alerta_severidade,
                        "valor": valor,
                    }
            except (ValueError, TypeError):
                pass

        return None

    def __repr__(self) -> str:
        return f"<ChecklistItem {self.ordem}. {self.pergunta[:50]}>"


# =============================================================================
# MODEL - RESPOSTA
# =============================================================================


class ChecklistResposta(Base):
    """
    Resposta de um Checklist Preenchido.

    Armazena as respostas dadas pelo tecnico durante a OS.
    """

    __tablename__ = "checklist_respostas"
    __table_args__ = (
        Index("ix_checklist_resposta_os", "ordem_servico_id"),
        Index("ix_checklist_resposta_item", "item_id"),
        {},
    )

    # =========================================================================
    # Identificacao
    # =========================================================================
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Vinculo com OS e Item
    ordem_servico_id = Column(UUID(as_uuid=True), ForeignKey("ordens_servico.id"), nullable=False)
    template_id = Column(UUID(as_uuid=True), ForeignKey("checklist_templates.id"), nullable=False)
    item_id = Column(UUID(as_uuid=True), ForeignKey("checklist_itens.id"), nullable=False)

    # =========================================================================
    # Resposta
    # =========================================================================
    # Diferentes campos para diferentes tipos de resposta
    resposta_texto = Column(Text)
    resposta_numero = Column(Numeric(15, 4))
    resposta_boolean = Column(Boolean)
    resposta_data = Column(DateTime)
    resposta_json = Column(JSONB)
    # Para multipla escolha, geolocalizacao, etc.

    # Arquivos
    resposta_foto_url = Column(String(500))
    resposta_fotos_urls = Column(JSONB, default=list)
    resposta_assinatura_url = Column(String(500))
    resposta_arquivo_url = Column(String(500))

    # =========================================================================
    # Validacao
    # =========================================================================
    is_valida = Column(Boolean, default=True)
    mensagem_validacao = Column(String(300))

    # =========================================================================
    # Alerta
    # =========================================================================
    gerou_alerta = Column(Boolean, default=False)
    alerta_data = Column(JSONB)
    # Dados do alerta gerado

    # =========================================================================
    # Metadata
    # =========================================================================
    respondido_por = Column(UUID(as_uuid=True), nullable=True)
    respondido_at = Column(DateTime, default=datetime.utcnow)

    # Geolocalizacao no momento da resposta
    latitude = Column(Numeric(10, 8))
    longitude = Column(Numeric(11, 8))

    observacao = Column(Text)
    # Observacao adicional do tecnico

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # =========================================================================
    # Relacionamentos
    # =========================================================================
    # ordem_servico = relationship("OrdemServico", back_populates="checklist_respostas")
    # item = relationship("ChecklistItem")
    # template = relationship("ChecklistTemplate")

    # =========================================================================
    # Propriedades
    # =========================================================================
    @property
    def valor(self):
        """Retorna valor da resposta independente do tipo."""
        if self.resposta_boolean is not None:
            return self.resposta_boolean
        if self.resposta_numero is not None:
            return self.resposta_numero
        if self.resposta_texto is not None:
            return self.resposta_texto
        if self.resposta_data is not None:
            return self.resposta_data
        if self.resposta_json is not None:
            return self.resposta_json
        if self.resposta_foto_url:
            return self.resposta_foto_url
        if self.resposta_fotos_urls:
            return self.resposta_fotos_urls
        if self.resposta_assinatura_url:
            return self.resposta_assinatura_url
        return None

    @property
    def tem_foto(self) -> bool:
        """Verifica se resposta tem foto."""
        return bool(self.resposta_foto_url or self.resposta_fotos_urls)

    @property
    def tem_assinatura(self) -> bool:
        """Verifica se resposta tem assinatura."""
        return bool(self.resposta_assinatura_url)

    # =========================================================================
    # Metodos
    # =========================================================================
    def set_valor(self, tipo_resposta: TipoResposta, valor):
        """Define valor conforme tipo de resposta."""
        if tipo_resposta in [TipoResposta.TEXTO, TipoResposta.TEXTO_LONGO]:
            self.resposta_texto = str(valor) if valor else None

        elif tipo_resposta == TipoResposta.NUMERO:
            self.resposta_numero = int(valor) if valor else None

        elif tipo_resposta == TipoResposta.DECIMAL:
            self.resposta_numero = float(valor) if valor else None

        elif tipo_resposta in [TipoResposta.SIM_NAO, TipoResposta.CONFORME_NAO_CONFORME]:
            if isinstance(valor, bool):
                self.resposta_boolean = valor
            elif isinstance(valor, str):
                self.resposta_boolean = valor.lower() in ["sim", "yes", "true", "1", "conforme"]
            else:
                self.resposta_boolean = bool(valor)

        elif tipo_resposta == TipoResposta.FOTO:
            self.resposta_foto_url = valor

        elif tipo_resposta == TipoResposta.FOTOS_MULTIPLAS:
            self.resposta_fotos_urls = valor if isinstance(valor, list) else [valor]

        elif tipo_resposta == TipoResposta.ASSINATURA:
            self.resposta_assinatura_url = valor

        elif tipo_resposta in [TipoResposta.MULTIPLA_ESCOLHA, TipoResposta.SELECAO_UNICA, TipoResposta.GEOLOCALIZACAO]:
            self.resposta_json = valor

        elif tipo_resposta in [TipoResposta.DATA, TipoResposta.HORA, TipoResposta.DATA_HORA]:
            if isinstance(valor, datetime):
                self.resposta_data = valor
            elif isinstance(valor, str):
                # Tentar parse
                try:
                    self.resposta_data = datetime.fromisoformat(valor.replace("Z", "+00:00"))
                except ValueError:
                    self.resposta_texto = valor

        elif tipo_resposta == TipoResposta.ARQUIVO:
            self.resposta_arquivo_url = valor

    def __repr__(self) -> str:
        return f"<ChecklistResposta OS:{self.ordem_servico_id} Item:{self.item_id}>"


# =============================================================================
# MODEL - CHECKLIST PREENCHIDO (Agregador)
# =============================================================================


class ChecklistPreenchido(Base):
    """
    Checklist Preenchido (agregador de respostas).

    Representa uma instancia de checklist aplicada a uma OS,
    com metadados de preenchimento e status.
    """

    __tablename__ = "checklists_preenchidos"
    __table_args__ = (Index("ix_checklist_preenchido_os", "ordem_servico_id"), {})

    # =========================================================================
    # Identificacao
    # =========================================================================
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    ordem_servico_id = Column(UUID(as_uuid=True), ForeignKey("ordens_servico.id"), nullable=False, unique=True)
    template_id = Column(UUID(as_uuid=True), ForeignKey("checklist_templates.id"), nullable=False)

    # =========================================================================
    # Status
    # =========================================================================
    iniciado = Column(Boolean, default=False)
    iniciado_at = Column(DateTime)

    concluido = Column(Boolean, default=False)
    concluido_at = Column(DateTime)

    # =========================================================================
    # Progresso
    # =========================================================================
    total_itens = Column(Integer, default=0)
    itens_respondidos = Column(Integer, default=0)
    itens_obrigatorios = Column(Integer, default=0)
    itens_obrigatorios_respondidos = Column(Integer, default=0)

    # Percentual de conclusao
    percentual_conclusao = Column(Numeric(5, 2), default=0)

    # =========================================================================
    # Scoring
    # =========================================================================
    pontuacao_obtida = Column(Integer, default=0)
    pontuacao_maxima = Column(Integer, default=0)
    percentual_conformidade = Column(Numeric(5, 2))

    # =========================================================================
    # Alertas
    # =========================================================================
    total_alertas = Column(Integer, default=0)
    alertas = Column(JSONB, default=list)
    # Lista de alertas gerados

    # =========================================================================
    # Metadata
    # =========================================================================
    preenchido_por = Column(UUID(as_uuid=True), nullable=True)
    preenchido_offline = Column(Boolean, default=False)
    sincronizado_at = Column(DateTime)

    observacoes_finais = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # =========================================================================
    # Relacionamentos
    # =========================================================================
    # ordem_servico = relationship("OrdemServico", back_populates="checklist_preenchido")
    # template = relationship("ChecklistTemplate")

    # =========================================================================
    # Propriedades
    # =========================================================================
    @property
    def pode_concluir(self) -> bool:
        """Verifica se todos itens obrigatorios foram respondidos."""
        return self.itens_obrigatorios_respondidos >= self.itens_obrigatorios

    @property
    def tem_alertas_criticos(self) -> bool:
        """Verifica se ha alertas criticos."""
        if not self.alertas:
            return False
        return any(a.get("severidade") == "critical" for a in self.alertas)

    # =========================================================================
    # Metodos
    # =========================================================================
    def iniciar(self, preenchido_por: str = None):
        """Marca checklist como iniciado."""
        self.iniciado = True
        self.iniciado_at = datetime.utcnow()
        if preenchido_por:
            self.preenchido_por = preenchido_por

    def atualizar_progresso(self, respondidos: int, obrigatorios_respondidos: int):
        """Atualiza progresso do preenchimento."""
        self.itens_respondidos = respondidos
        self.itens_obrigatorios_respondidos = obrigatorios_respondidos

        if self.total_itens > 0:
            self.percentual_conclusao = (respondidos / self.total_itens) * 100

    def adicionar_alerta(self, alerta: dict):
        """Adiciona alerta gerado."""
        if not self.alertas:
            self.alertas = []
        self.alertas.append(alerta)
        self.total_alertas = len(self.alertas)

    def concluir(self, observacoes: str = None):
        """Marca checklist como concluido."""
        if not self.pode_concluir:
            raise ValueError("Itens obrigatorios pendentes")

        self.concluido = True
        self.concluido_at = datetime.utcnow()
        if observacoes:
            self.observacoes_finais = observacoes

        # Calcular conformidade
        if self.pontuacao_maxima > 0:
            self.percentual_conformidade = (self.pontuacao_obtida / self.pontuacao_maxima) * 100

    def __repr__(self) -> str:
        return f"<ChecklistPreenchido OS:{self.ordem_servico_id} {self.percentual_conclusao}%>"
