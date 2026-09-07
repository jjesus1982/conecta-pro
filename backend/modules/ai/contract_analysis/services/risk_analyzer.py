"""
Risk Analyzer Service - AI Contract Analysis

Analisa riscos em contratos.
"""

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from modules.ai.contract_analysis.models.contract_analysis import (
    ContractAnalysis,
    ContractType,
    RiskLevel,
)
from modules.ai.contract_analysis.models.extracted_clause import (
    ClauseType,
    ExtractedClause,
)
from modules.ai.contract_analysis.repositories.contract_repository import (
    ContractAnalysisRepository,
)

logger = logging.getLogger(__name__)


class RiskAnalyzer:
    """
    Analisador de riscos de contratos.

    Avalia riscos baseado em clausulas, tipo de contrato
    e padroes identificados.
    """

    # Fatores de risco por tipo de clausula
    CLAUSE_RISK_WEIGHTS = {
        ClauseType.PENALTY: 15,
        ClauseType.LIABILITY: 15,
        ClauseType.TERMINATION: 10,
        ClauseType.NON_COMPETE: 10,
        ClauseType.EXCLUSIVITY: 10,
        ClauseType.CONFIDENTIALITY: 5,
        ClauseType.FORCE_MAJEURE: 5,
    }

    # Indicadores de risco em texto
    HIGH_RISK_INDICATORS = {
        "responsabilidade ilimitada": 20,
        "renúncia de direitos": 20,
        "irrevogável e irretratável": 15,
        "rescisão imediata": 15,
        "multa de 100%": 20,
        "sem aviso prévio": 15,
        "assumir todos os custos": 15,
        "indenização integral": 15,
        "exclusividade total": 10,
        "vedado": 10,
        "proibido": 10,
    }

    # Clausulas obrigatorias por tipo de contrato
    REQUIRED_CLAUSES = {
        ContractType.SERVICE: [
            ClauseType.OBJECT,
            ClauseType.PAYMENT,
            ClauseType.TERMINATION,
        ],
        ContractType.SALES: [
            ClauseType.OBJECT,
            ClauseType.PAYMENT,
            ClauseType.WARRANTY,
        ],
        ContractType.LEASE: [
            ClauseType.OBJECT,
            ClauseType.PAYMENT,
            ClauseType.TERMINATION,
            ClauseType.RENEWAL,
        ],
        ContractType.NDA: [
            ClauseType.CONFIDENTIALITY,
            ClauseType.PENALTY,
        ],
    }

    def __init__(self, db: Session):
        """Inicializa analyzer."""
        self.db = db
        self.repository = ContractAnalysisRepository(db)

    def analyze_risk(
        self,
        analysis: ContractAnalysis,
        clauses: list[ExtractedClause],
    ) -> dict:
        """
        Analisa riscos do contrato.

        Args:
            analysis: Analise do contrato
            clauses: Clausulas extraidas

        Returns:
            Dict com nivel de risco, score e fatores
        """
        logger.info(f"Analisando riscos do contrato {analysis.id}")

        risk_score = 0
        risk_factors = []

        # 1. Analisar clausulas arriscadas
        clause_risk, clause_factors = self._analyze_clause_risks(clauses)
        risk_score += clause_risk
        risk_factors.extend(clause_factors)

        # 2. Verificar clausulas faltantes
        missing_risk, missing_factors = self._check_missing_clauses(analysis.contract_type, clauses)
        risk_score += missing_risk
        risk_factors.extend(missing_factors)

        # 3. Analisar texto geral
        text_risk, text_factors = self._analyze_text_risks(analysis, clauses)
        risk_score += text_risk
        risk_factors.extend(text_factors)

        # 4. Verificar valores e prazos
        value_risk, value_factors = self._analyze_value_risks(analysis)
        risk_score += value_risk
        risk_factors.extend(value_factors)

        # 5. Verificar renovacao automatica
        if analysis.has_auto_renewal:
            risk_score += 10
            risk_factors.append(
                {
                    "factor": "auto_renewal",
                    "impact": "medium",
                    "score": 10,
                    "description": "Contrato possui renovacao automatica",
                }
            )

        # Normalizar score
        risk_score = min(100, risk_score)

        # Determinar nivel
        risk_level = self._determine_risk_level(risk_score)

        logger.info(f"Risco: {risk_level.value} (score: {risk_score})")

        return {
            "risk_level": risk_level,
            "risk_score": risk_score,
            "risk_factors": risk_factors,
            "recommendations": self._generate_recommendations(risk_factors),
        }

    def _analyze_clause_risks(self, clauses: list[ExtractedClause]) -> tuple[float, list[dict]]:
        """Analisa riscos das clausulas."""
        total_risk = 0
        factors = []

        for clause in clauses:
            if clause.is_risky:
                weight = self.CLAUSE_RISK_WEIGHTS.get(clause.clause_type, 5)
                adjusted_risk = (clause.risk_score / 100) * weight

                total_risk += adjusted_risk

                factors.append(
                    {
                        "factor": f"risky_clause_{clause.clause_type.value}",
                        "impact": "high" if clause.risk_score >= 50 else "medium",
                        "score": round(adjusted_risk, 1),
                        "description": f"Clausula {clause.clause_number} apresenta risco",
                        "clause_id": str(clause.id),
                        "reasons": clause.risk_reasons,
                    }
                )

        return total_risk, factors

    def _check_missing_clauses(
        self, contract_type: ContractType, clauses: list[ExtractedClause]
    ) -> tuple[float, list[dict]]:
        """Verifica clausulas faltantes."""
        total_risk = 0
        factors = []

        required = self.REQUIRED_CLAUSES.get(contract_type, [])
        found_types = {c.clause_type for c in clauses}

        for clause_type in required:
            if clause_type not in found_types:
                risk = 15 if clause_type in (ClauseType.PENALTY, ClauseType.TERMINATION) else 10
                total_risk += risk

                factors.append(
                    {
                        "factor": f"missing_clause_{clause_type.value}",
                        "impact": "high" if risk >= 15 else "medium",
                        "score": risk,
                        "description": f"Clausula de {clause_type.value} nao encontrada",
                    }
                )

        return total_risk, factors

    def _analyze_text_risks(
        self, analysis: ContractAnalysis, clauses: list[ExtractedClause]
    ) -> tuple[float, list[dict]]:
        """Analisa riscos no texto."""
        total_risk = 0
        factors = []

        # Juntar texto de todas as clausulas
        full_text = " ".join(c.original_text.lower() for c in clauses if c.original_text)

        for indicator, risk_points in self.HIGH_RISK_INDICATORS.items():
            if indicator.lower() in full_text:
                total_risk += risk_points
                factors.append(
                    {
                        "factor": f"text_risk_{indicator.replace(' ', '_')}",
                        "impact": "high" if risk_points >= 15 else "medium",
                        "score": risk_points,
                        "description": f"Termo de risco encontrado: '{indicator}'",
                    }
                )

        return min(40, total_risk), factors  # Cap em 40

    def _analyze_value_risks(self, analysis: ContractAnalysis) -> tuple[float, list[dict]]:
        """Analisa riscos de valores."""
        total_risk = 0
        factors = []

        # Valor muito alto sem garantias
        if analysis.total_value and analysis.total_value > 100000:
            if not analysis.has_penalty_clause:
                total_risk += 15
                factors.append(
                    {
                        "factor": "high_value_no_penalty",
                        "impact": "high",
                        "score": 15,
                        "description": "Alto valor sem clausula de penalidade",
                    }
                )

        # Prazo muito longo
        if analysis.notice_period_days and analysis.notice_period_days < 30:
            total_risk += 10
            factors.append(
                {
                    "factor": "short_notice_period",
                    "impact": "medium",
                    "score": 10,
                    "description": f"Aviso previo curto ({analysis.notice_period_days} dias)",
                }
            )

        return total_risk, factors

    def _determine_risk_level(self, score: float) -> RiskLevel:
        """Determina nivel de risco baseado no score."""
        if score >= 70:
            return RiskLevel.CRITICAL
        elif score >= 50:
            return RiskLevel.HIGH
        elif score >= 30:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW

    def _generate_recommendations(self, factors: list[dict]) -> list[str]:
        """Gera recomendacoes baseadas nos fatores de risco."""
        recommendations = []

        for factor in factors:
            factor_name = factor.get("factor", "")

            if "missing_clause" in factor_name:
                clause_type = factor_name.replace("missing_clause_", "")
                recommendations.append(f"Adicionar clausula de {clause_type} ao contrato")

            elif "risky_clause" in factor_name:
                recommendations.append(f"Revisar clausula {factor.get('clause_id', '')} - apresenta risco")

            elif "high_value_no_penalty" in factor_name:
                recommendations.append("Incluir clausula de penalidade devido ao alto valor")

            elif "short_notice_period" in factor_name:
                recommendations.append("Negociar prazo de aviso previo maior")

            elif "auto_renewal" in factor_name:
                recommendations.append("Agendar revisao antes da renovacao automatica")

            elif "text_risk" in factor_name:
                recommendations.append(f"Revisar termo: {factor.get('description', '')}")

        return list(set(recommendations))[:10]  # Remover duplicatas, max 10

    def get_risk_summary(self, analysis_id: UUID) -> dict:
        """Retorna resumo de riscos de uma analise."""
        analysis = self.repository.get_analysis(analysis_id, include_clauses=True)

        if not analysis:
            return {"error": "Analise nao encontrada"}

        risky_clauses = [c for c in analysis.clauses if c.is_risky]

        return {
            "contract_id": str(analysis.contract_id),
            "risk_level": analysis.risk_level.value,
            "risk_score": analysis.risk_score,
            "risk_factors": analysis.risk_factors or [],
            "risky_clauses_count": len(risky_clauses),
            "risky_clauses": [
                {
                    "clause_number": c.clause_number,
                    "clause_type": c.clause_type.value,
                    "risk_score": c.risk_score,
                    "reasons": c.risk_reasons,
                }
                for c in risky_clauses[:5]
            ],
        }
