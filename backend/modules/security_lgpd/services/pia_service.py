"""
Service de Avaliacao de Impacto de Privacidade (PIA/DPIA) LGPD.

Persiste avaliacoes na tabela ``lgpd_pia_assessments`` via ``PIARepository``.
NAO usa mais armazenamento em memoria.
"""

import logging
import uuid
from datetime import datetime
from typing import Any
from uuid import UUID

from modules.security_lgpd.models.pia_assessment import (
    AssessmentStatus,
    PIAAssessment,
    RiskLevel,
)
from modules.security_lgpd.repositories.pia_repository import PIARepository

logger = logging.getLogger(__name__)


class PIAService:
    """Service para gerenciamento de avaliacoes de impacto.

    Encapsula a logica de avaliacao de impacto de privacidade conforme Art. 38
    da LGPD (RIPD), persistindo as avaliacoes no banco via ``PIARepository``.
    """

    # Categorias de dados sensiveis (Art. 5, II LGPD)
    SENSITIVE_CATEGORIES = [
        "racial_ethnic",
        "political_opinion",
        "religious_belief",
        "health_data",
        "sexual_data",
        "genetic_data",
        "biometric_data",
    ]

    def __init__(self, repository: PIARepository | None = None):
        """Inicializa o service.

        Args:
            repository: Repository de avaliacoes PIA (com sessao de banco).
                Pode ser ``None`` apenas para endpoints estaticos (listas de
                categorias) que nao tocam o banco.
        """
        self.repository = repository

    def _calculate_risk_level(
        self,
        data_categories: list[str],
        processing_purposes: list[str],
        data_subjects: list[str],
        risk_factors: list[str],
    ) -> str:
        """Calcula nivel de risco baseado nos fatores.

        Returns:
            Nivel de risco: low, medium, high, critical
        """
        score = 0

        # Dados sensiveis aumentam risco
        for cat in data_categories:
            if cat in self.SENSITIVE_CATEGORIES:
                score += 3

        # Grande volume de titulares
        if "mass" in data_subjects or "public" in data_subjects:
            score += 2

        # Fatores de risco identificados
        score += len(risk_factors)

        # Finalidades de alto risco
        high_risk_purposes = ["profiling", "automated_decision", "surveillance"]
        for purpose in processing_purposes:
            if purpose in high_risk_purposes:
                score += 3

        if score >= 10:
            return "critical"
        elif score >= 6:
            return "high"
        elif score >= 3:
            return "medium"
        else:
            return "low"

    def _generate_recommendations(
        self,
        risk_level: str,
        data_categories: list[str],
    ) -> list[str]:
        """Gera recomendacoes baseadas na avaliacao."""
        recommendations = []

        if risk_level in ("high", "critical"):
            recommendations.append("Realizar DPIA completo conforme Art. 38 LGPD")
            recommendations.append("Consultar Encarregado de Dados (DPO)")
            recommendations.append("Considerar consulta previa a ANPD")

        if any(cat in self.SENSITIVE_CATEGORIES for cat in data_categories):
            recommendations.append("Implementar medidas de seguranca reforçadas para dados sensiveis")
            recommendations.append("Obter consentimento especifico conforme Art. 11 LGPD")

        if risk_level in ("medium", "high", "critical"):
            recommendations.append("Documentar medidas de mitigacao implementadas")
            recommendations.append("Realizar revisao periodica da avaliacao")

        if not recommendations:
            recommendations.append("Manter documentacao do tratamento de dados")

        return recommendations

    def create_assessment(
        self,
        project_name: str,
        description: str,
        data_categories: list[str],
        processing_purposes: list[str],
        data_subjects: list[str] | None = None,
        risk_factors: list[str] | None = None,
    ) -> dict[str, Any]:
        """Cria avaliacao de impacto de privacidade (persistindo no banco).

        Args:
            project_name: Nome do projeto.
            description: Descricao do tratamento.
            data_categories: Categorias de dados tratados.
            processing_purposes: Finalidades do tratamento.
            data_subjects: Titulares afetados.
            risk_factors: Fatores de risco identificados.

        Returns:
            Dict com resultado da avaliacao.
        """
        data_subjects = data_subjects or ["funcionarios"]
        risk_factors = risk_factors or []

        now = datetime.utcnow()

        risk_level = self._calculate_risk_level(
            data_categories,
            processing_purposes,
            data_subjects,
            risk_factors,
        )

        recommendations = self._generate_recommendations(risk_level, data_categories)
        requires_dpia = risk_level in ("high", "critical")

        assessment = PIAAssessment(
            id=uuid.uuid4(),
            project_name=project_name,
            description=description,
            status=AssessmentStatus.APPROVED,
            risk_level=RiskLevel(risk_level),
            requires_dpia=requires_dpia,
            data_categories=data_categories,
            processing_purposes=processing_purposes,
            data_subjects=data_subjects,
            risk_factors=risk_factors,
            recommendations=recommendations,
            created_at=now,
            version="1.0",
        )

        saved = self.repository.create(assessment)

        logger.info(
            "PIA criado (persistido): projeto=%s, nivel de risco=%s",
            project_name,
            risk_level,
        )

        return {
            "assessment_id": str(saved.id),
            "project_name": saved.project_name,
            "risk_level": saved.risk_level.value if saved.risk_level else risk_level,
            "requires_dpia": saved.requires_dpia,
            "recommendations": saved.recommendations,
        }

    def get_assessment(self, assessment_id: str) -> dict[str, Any]:
        """Consulta avaliacao de impacto (lendo do banco).

        Args:
            assessment_id: ID da avaliacao.

        Returns:
            Dict com detalhes da avaliacao.

        Raises:
            ValueError: Se avaliacao nao encontrada.
        """
        assessment = self.repository.get_by_id(UUID(str(assessment_id)))
        if assessment is None:
            raise ValueError(f"Avaliacao nao encontrada: {assessment_id}")

        data = assessment.to_dict()
        # Enriquecimento com campos completos nao expostos no to_dict do model
        data["processing_purposes"] = assessment.processing_purposes
        data["data_subjects"] = assessment.data_subjects
        data["risk_factors"] = assessment.risk_factors
        return data

    def list_assessments(
        self,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Lista avaliacoes de impacto (lendo do banco).

        Args:
            status: Filtro por status.
            limit: Limite de resultados.
            offset: Offset para paginacao.

        Returns:
            Dict com lista de avaliacoes.
        """
        status_enum = None
        if status:
            try:
                status_enum = AssessmentStatus(status)
            except ValueError:
                status_enum = None

        assessments = self.repository.list(status=status_enum, limit=limit, offset=offset)

        return {
            "assessments": [a.to_dict() for a in assessments],
            "total": len(assessments),
            "limit": limit,
            "offset": offset,
        }

    def get_risk_categories(self) -> list[dict[str, str]]:
        """Lista categorias de risco disponiveis.

        Returns:
            Lista de categorias de risco.
        """
        return [
            {"id": "low", "description": "Baixo risco", "color": "green"},
            {"id": "medium", "description": "Risco medio", "color": "yellow"},
            {"id": "high", "description": "Alto risco", "color": "orange"},
            {"id": "critical", "description": "Risco critico", "color": "red"},
        ]

    def get_data_categories(self) -> list[dict[str, str]]:
        """Lista categorias de dados LGPD.

        Returns:
            Lista de categorias de dados.
        """
        return [
            {"id": "personal", "description": "Dados pessoais", "sensitive": False},
            {"id": "financial", "description": "Dados financeiros", "sensitive": False},
            {"id": "health_data", "description": "Dados de saude", "sensitive": True},
            {"id": "biometric_data", "description": "Dados biometricos", "sensitive": True},
            {"id": "genetic_data", "description": "Dados geneticos", "sensitive": True},
            {"id": "racial_ethnic", "description": "Origem racial/etnica", "sensitive": True},
            {"id": "political_opinion", "description": "Opiniao politica", "sensitive": True},
            {"id": "religious_belief", "description": "Crenca religiosa", "sensitive": True},
            {"id": "sexual_data", "description": "Vida sexual", "sensitive": True},
        ]
