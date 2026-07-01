"""
Models de Perfil Operacional.

Sistema de avaliacao comportamental para match de funcionarios com postos.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func, text

from core.database import Base
from core.models import TimestampMixin


class ProfileDimension(StrEnum):
    """Dimensoes do perfil operacional."""

    VIGILANCIA = "vigilancia"
    COMUNICACAO = "comunicacao"
    RESILIENCIA = "resiliencia"
    LIDERANCA = "lideranca"


class PostTypeProfile(StrEnum):
    """Tipos de posto com perfil ideal definido."""

    CFTV = "cftv"
    PORTARIA = "portaria"
    RECEPCAO = "recepcao"
    RONDA = "ronda"
    EVENTO = "evento"
    SUPERVISOR = "supervisor"
    SEGURANCA_ARMADA = "seguranca_armada"
    VIGILANTE = "vigilante"


# Questionario padrao - 20 perguntas, 5 por dimensao
QUESTIONARIO_PERFIL: list[dict[str, str]] = [
    # Vigilancia (5 perguntas) - Capacidade de observacao e atencao
    {
        "id": "v1",
        "texto": "Quando assisto TV, costumo notar detalhes que outros nao percebem",
        "dimensao": "vigilancia",
        "ordem": 1,
    },
    {
        "id": "v2",
        "texto": "Consigo manter atencao em uma tarefa por horas sem distracao",
        "dimensao": "vigilancia",
        "ordem": 2,
    },
    {
        "id": "v3",
        "texto": "Percebo rapidamente quando algo esta fora do lugar",
        "dimensao": "vigilancia",
        "ordem": 3,
    },
    {
        "id": "v4",
        "texto": "Prefiro trabalhos que exigem observacao cuidadosa",
        "dimensao": "vigilancia",
        "ordem": 4,
    },
    {
        "id": "v5",
        "texto": "Sou bom em encontrar erros em documentos ou imagens",
        "dimensao": "vigilancia",
        "ordem": 5,
    },
    # Comunicacao (5 perguntas) - Habilidades interpessoais
    {
        "id": "c1",
        "texto": "Me sinto confortavel conversando com desconhecidos",
        "dimensao": "comunicacao",
        "ordem": 6,
    },
    {
        "id": "c2",
        "texto": "Consigo explicar coisas complexas de forma simples",
        "dimensao": "comunicacao",
        "ordem": 7,
    },
    {
        "id": "c3",
        "texto": "As pessoas costumam me procurar para desabafar",
        "dimensao": "comunicacao",
        "ordem": 8,
    },
    {
        "id": "c4",
        "texto": "Gosto de trabalhar atendendo pessoas",
        "dimensao": "comunicacao",
        "ordem": 9,
    },
    {
        "id": "c5",
        "texto": "Consigo manter a calma mesmo com pessoas dificeis",
        "dimensao": "comunicacao",
        "ordem": 10,
    },
    # Resiliencia (5 perguntas) - Capacidade de lidar com pressao
    {
        "id": "r1",
        "texto": "Mantenho a calma em situacoes de emergencia",
        "dimensao": "resiliencia",
        "ordem": 11,
    },
    {
        "id": "r2",
        "texto": "Recupero-me rapidamente de situacoes estressantes",
        "dimensao": "resiliencia",
        "ordem": 12,
    },
    {
        "id": "r3",
        "texto": "Trabalho bem mesmo sob pressao de tempo",
        "dimensao": "resiliencia",
        "ordem": 13,
    },
    {
        "id": "r4",
        "texto": "Nao me abalo facilmente com criticas",
        "dimensao": "resiliencia",
        "ordem": 14,
    },
    {
        "id": "r5",
        "texto": "Consigo tomar decisoes dificeis sem hesitar muito",
        "dimensao": "resiliencia",
        "ordem": 15,
    },
    # Lideranca (5 perguntas) - Capacidade de liderar e orientar
    {
        "id": "l1",
        "texto": "Em grupos, naturalmente assumo a coordenacao",
        "dimensao": "lideranca",
        "ordem": 16,
    },
    {
        "id": "l2",
        "texto": "Gosto de ensinar e orientar outras pessoas",
        "dimensao": "lideranca",
        "ordem": 17,
    },
    {
        "id": "l3",
        "texto": "Tomo iniciativa mesmo sem ser solicitado",
        "dimensao": "lideranca",
        "ordem": 18,
    },
    {
        "id": "l4",
        "texto": "Consigo motivar pessoas a darem o melhor",
        "dimensao": "lideranca",
        "ordem": 19,
    },
    {
        "id": "l5",
        "texto": "Prefiro liderar do que ser liderado",
        "dimensao": "lideranca",
        "ordem": 20,
    },
]


# Perfis ideais por tipo de posto
PERFIL_IDEAL_POR_TIPO: dict[str, dict[str, int]] = {
    "cftv": {
        "vigilancia": 90,
        "comunicacao": 40,
        "resiliencia": 60,
        "lideranca": 30,
    },
    "portaria": {
        "vigilancia": 60,
        "comunicacao": 85,
        "resiliencia": 70,
        "lideranca": 40,
    },
    "recepcao": {
        "vigilancia": 50,
        "comunicacao": 95,
        "resiliencia": 60,
        "lideranca": 30,
    },
    "ronda": {
        "vigilancia": 85,
        "comunicacao": 50,
        "resiliencia": 80,
        "lideranca": 50,
    },
    "evento": {
        "vigilancia": 70,
        "comunicacao": 70,
        "resiliencia": 95,
        "lideranca": 60,
    },
    "supervisor": {
        "vigilancia": 70,
        "comunicacao": 80,
        "resiliencia": 85,
        "lideranca": 90,
    },
    "seguranca_armada": {
        "vigilancia": 85,
        "comunicacao": 60,
        "resiliencia": 90,
        "lideranca": 60,
    },
    "vigilante": {
        "vigilancia": 80,
        "comunicacao": 55,
        "resiliencia": 75,
        "lideranca": 40,
    },
}


class OperationalProfile(Base, TimestampMixin):
    """
    Perfil Operacional do Funcionario.

    Armazena os resultados da avaliacao comportamental com scores
    em 4 dimensoes: vigilancia, comunicacao, resiliencia e lideranca.

    Attributes:
        funcionario_id: UUID do funcionario avaliado
        data_avaliacao: Data/hora da avaliacao
        vigilancia: Score de vigilancia (0-100)
        comunicacao: Score de comunicacao (0-100)
        resiliencia: Score de resiliencia (0-100)
        lideranca: Score de lideranca (0-100)
        perfil_predominante: Dimensao com maior score
        respostas: Dict com respostas {pergunta_id: valor 1-4}
        versao_questionario: Versao do questionario utilizado
        tempo_resposta_segundos: Tempo total para responder
    """

    __tablename__ = "operational_profiles"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    # Relacionamento com funcionario
    funcionario_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        nullable=False,
        index=True,
    )

    # Data da avaliacao
    data_avaliacao: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Scores por dimensao (0-100)
    vigilancia: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    comunicacao: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    resiliencia: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    lideranca: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    # Perfil predominante (dimensao com maior score)
    perfil_predominante: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    # Respostas brutas do questionario {pergunta_id: valor 1-4}
    respostas: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    # Metadados da avaliacao
    versao_questionario: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="1.0.0",
    )
    tempo_resposta_segundos: Mapped[int] = mapped_column(
        Integer,
        nullable=True,
    )

    # Progresso para salvamento automatico
    progresso_respostas: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    em_andamento: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    ultima_pergunta_respondida: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    # Validez e controle
    is_valid: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    invalidation_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Condominio/Tenant
    condominium_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        nullable=True,
        index=True,
    )

    # Constraints
    __table_args__ = (
        CheckConstraint("vigilancia >= 0 AND vigilancia <= 100", name="ck_vigilancia_range"),
        CheckConstraint("comunicacao >= 0 AND comunicacao <= 100", name="ck_comunicacao_range"),
        CheckConstraint("resiliencia >= 0 AND resiliencia <= 100", name="ck_resiliencia_range"),
        CheckConstraint("lideranca >= 0 AND lideranca <= 100", name="ck_lideranca_range"),
        Index("ix_operational_profiles_funcionario_date", "funcionario_id", "data_avaliacao"),
    )

    def __repr__(self) -> str:
        return f"<OperationalProfile {self.funcionario_id} - {self.perfil_predominante}>"

    @property
    def scores(self) -> dict[str, int]:
        """Retorna todos os scores como dict."""
        return {
            "vigilancia": self.vigilancia,
            "comunicacao": self.comunicacao,
            "resiliencia": self.resiliencia,
            "lideranca": self.lideranca,
        }

    @property
    def score_medio(self) -> float:
        """Calcula score medio geral."""
        return (self.vigilancia + self.comunicacao + self.resiliencia + self.lideranca) / 4

    @property
    def dimensao_mais_fraca(self) -> str:
        """Retorna a dimensao com menor score."""
        scores = self.scores
        return min(scores, key=scores.get)

    def calcular_perfil_predominante(self) -> str:
        """Identifica a dimensao com maior score."""
        scores = self.scores
        return max(scores, key=scores.get)

    def get_percentil_dimensao(self, dimensao: str, media: float, desvio: float) -> int:
        """
        Calcula percentil de uma dimensao dado media e desvio padrao populacionais.

        Args:
            dimensao: Nome da dimensao
            media: Media populacional
            desvio: Desvio padrao populacional

        Returns:
            Percentil (0-100)
        """
        import math

        score = self.scores.get(dimensao, 0)
        if desvio == 0:
            return 50
        z = (score - media) / desvio
        # Aproximacao do percentil usando funcao erro
        percentil = 50 * (1 + math.erf(z / math.sqrt(2)))
        return int(min(100, max(0, percentil)))


class ProfileQuestion(Base, TimestampMixin):
    """
    Pergunta do Questionario de Perfil.

    Permite customizacao e versionamento do questionario.

    Attributes:
        texto: Texto da pergunta
        dimensao: Dimensao avaliada (vigilancia, comunicacao, etc)
        ordem: Ordem de exibicao
        ativo: Se a pergunta esta ativa
        versao: Versao do questionario
    """

    __tablename__ = "profile_questions"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    # Codigo unico da pergunta (v1, c2, etc)
    codigo: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        unique=True,
        index=True,
    )

    # Texto da pergunta
    texto: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Dimensao que a pergunta avalia
    dimensao: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    # Ordem de exibicao
    ordem: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    # Status
    ativo: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Versao do questionario
    versao: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="1.0.0",
    )

    # Peso da pergunta no calculo (default 1.0)
    peso: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=1.0,
    )

    # Condominio para customizacao (null = global)
    condominium_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        nullable=True,
        index=True,
    )

    __table_args__ = (Index("ix_profile_questions_ordem_versao", "ordem", "versao"),)

    def __repr__(self) -> str:
        return f"<ProfileQuestion {self.codigo} - {self.dimensao}>"


class PostMatch(Base, TimestampMixin):
    """
    Match entre Funcionario e Posto.

    Armazena o calculo de compatibilidade entre perfil do funcionario
    e requisitos do posto.

    Attributes:
        funcionario_id: UUID do funcionario
        posto_id: UUID do posto
        score_match: Score de compatibilidade (0-100)
        fatores_positivos: Lista de pontos fortes
        fatores_negativos: Lista de pontos a desenvolver
        recomendado: Se o match e recomendado
        calculado_em: Data/hora do calculo
    """

    __tablename__ = "post_matches"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    # Funcionario
    funcionario_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        nullable=False,
        index=True,
    )

    # Posto
    posto_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        nullable=False,
        index=True,
    )

    # Tipo do posto (para referencia rapida)
    posto_tipo: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    # Profile usado no calculo
    profile_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("operational_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Score de match (0-100)
    score_match: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )

    # Detalhamento do match
    fatores_positivos: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        nullable=False,
        default=list,
    )
    fatores_negativos: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        nullable=False,
        default=list,
    )

    # Scores detalhados por dimensao
    scores_detalhados: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Recomendacao
    recomendado: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # Nivel de match (baixo, medio, alto, excelente)
    nivel_match: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="medio",
    )

    # Data do calculo
    calculado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Validade do calculo (null = indefinido)
    valido_ate: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Condominio
    condominium_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        nullable=True,
        index=True,
    )

    # Relacionamento
    profile: Mapped[Optional["OperationalProfile"]] = relationship(
        "OperationalProfile",
        foreign_keys=[profile_id],
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_post_matches_funcionario_posto", "funcionario_id", "posto_id"),
        Index("ix_post_matches_score", "score_match"),
        CheckConstraint("score_match >= 0 AND score_match <= 100", name="ck_score_match_range"),
    )

    def __repr__(self) -> str:
        return f"<PostMatch {self.funcionario_id} -> {self.posto_id}: {self.score_match:.1f}>"

    @property
    def is_expired(self) -> bool:
        """Verifica se o calculo expirou."""
        if self.valido_ate is None:
            return False
        return datetime.now(self.valido_ate.tzinfo) > self.valido_ate

    def classificar_nivel(self) -> str:
        """Classifica nivel do match baseado no score."""
        if self.score_match >= 85:
            return "excelente"
        elif self.score_match >= 70:
            return "alto"
        elif self.score_match >= 50:
            return "medio"
        else:
            return "baixo"
