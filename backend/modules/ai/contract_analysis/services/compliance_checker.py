"""
Compliance Checker Service - AI Contract Analysis

Verifica conformidade de contratos.
"""

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from modules.ai.contract_analysis.models.contract_analysis import (
    ContractAnalysis,
    ContractType,
)
from modules.ai.contract_analysis.models.extracted_clause import (
    ClauseType,
    ExtractedClause,
)
from modules.ai.contract_analysis.repositories.contract_repository import (
    ContractAnalysisRepository,
)

logger = logging.getLogger(__name__)


class ComplianceChecker:
    """
    Verificador de conformidade de contratos.

    Verifica se contratos possuem clausulas obrigatorias
    e atendem a requisitos legais.
    """

    # Clausulas obrigatorias por tipo de contrato
    REQUIRED_CLAUSES_BY_TYPE = {
        ContractType.SERVICE: {
            ClauseType.OBJECT: {"weight": 20, "description": "Objeto do contrato"},
            ClauseType.PAYMENT: {"weight": 20, "description": "Condicoes de pagamento"},
            ClauseType.TERMINATION: {"weight": 15, "description": "Condicoes de rescisao"},
            ClauseType.JURISDICTION: {"weight": 10, "description": "Foro competente"},
            ClauseType.LIABILITY: {"weight": 10, "description": "Responsabilidades"},
        },
        ContractType.SALES: {
            ClauseType.OBJECT: {"weight": 20, "description": "Objeto/produto"},
            ClauseType.PAYMENT: {"weight": 20, "description": "Condicoes de pagamento"},
            ClauseType.WARRANTY: {"weight": 15, "description": "Garantias"},
            ClauseType.JURISDICTION: {"weight": 10, "description": "Foro competente"},
        },
        ContractType.LEASE: {
            ClauseType.OBJECT: {"weight": 15, "description": "Objeto locado"},
            ClauseType.PAYMENT: {"weight": 20, "description": "Valor e pagamento"},
            ClauseType.TERMINATION: {"weight": 15, "description": "Condicoes de rescisao"},
            ClauseType.RENEWAL: {"weight": 15, "description": "Renovacao"},
            ClauseType.JURISDICTION: {"weight": 10, "description": "Foro competente"},
        },
        ContractType.EMPLOYMENT: {
            ClauseType.OBJECT: {"weight": 15, "description": "Funcao/cargo"},
            ClauseType.PAYMENT: {"weight": 20, "description": "Salario e beneficios"},
            ClauseType.TERMINATION: {"weight": 15, "description": "Rescisao"},
            ClauseType.CONFIDENTIALITY: {"weight": 10, "description": "Sigilo"},
        },
        ContractType.NDA: {
            ClauseType.CONFIDENTIALITY: {"weight": 30, "description": "Confidencialidade"},
            ClauseType.PENALTY: {"weight": 20, "description": "Penalidades"},
            ClauseType.TERMINATION: {"weight": 15, "description": "Vigencia/termino"},
        },
        ContractType.SLA: {
            ClauseType.SLA: {"weight": 25, "description": "Niveis de servico"},
            ClauseType.PENALTY: {"weight": 20, "description": "Penalidades por descumprimento"},
            ClauseType.WARRANTY: {"weight": 15, "description": "Garantias"},
        },
    }

    # Requisitos gerais
    GENERAL_REQUIREMENTS = [
        {
            "id": "parties_identified",
            "description": "Partes identificadas (nome e documento)",
            "weight": 15,
        },
        {
            "id": "dates_defined",
            "description": "Datas de inicio e fim definidas",
            "weight": 10,
        },
        {
            "id": "value_defined",
            "description": "Valores definidos",
            "weight": 10,
        },
        {
            "id": "jurisdiction_defined",
            "description": "Foro definido",
            "weight": 5,
        },
    ]

    # Requisitos LGPD (se aplicavel)
    LGPD_REQUIREMENTS = [
        {
            "id": "data_protection_clause",
            "description": "Clausula de protecao de dados",
            "weight": 15,
        },
        {
            "id": "data_purpose",
            "description": "Finalidade do tratamento de dados",
            "weight": 10,
        },
    ]

    def __init__(self, db: Session):
        """Inicializa checker."""
        self.db = db
        self.repository = ContractAnalysisRepository(db)

    def check_compliance(
        self,
        analysis: ContractAnalysis,
        clauses: list[ExtractedClause],
        check_lgpd: bool = True,
    ) -> dict:
        """
        Verifica conformidade do contrato.

        Args:
            analysis: Analise do contrato
            clauses: Clausulas extraidas
            check_lgpd: Verificar requisitos LGPD

        Returns:
            Dict com score, status e issues
        """
        logger.info(f"Verificando conformidade do contrato {analysis.id}")

        total_score = 0
        max_score = 0
        issues = []
        required_clauses = []
        missing_clauses = []

        # 1. Verificar clausulas obrigatorias por tipo
        type_requirements = self.REQUIRED_CLAUSES_BY_TYPE.get(analysis.contract_type, {})
        found_types = {c.clause_type for c in clauses}

        for clause_type, info in type_requirements.items():
            max_score += info["weight"]
            required_clauses.append(
                {
                    "type": clause_type.value,
                    "description": info["description"],
                    "required": True,
                }
            )

            if clause_type in found_types:
                total_score += info["weight"]
                required_clauses[-1]["status"] = "present"
                required_clauses[-1]["compliant"] = True
            else:
                missing_clauses.append(clause_type.value)
                required_clauses[-1]["status"] = "missing"
                required_clauses[-1]["compliant"] = False
                issues.append(
                    {
                        "severity": "high" if info["weight"] >= 15 else "medium",
                        "type": "missing_clause",
                        "description": f"Clausula obrigatoria ausente: {info['description']}",
                        "clause_type": clause_type.value,
                    }
                )

        # 2. Verificar requisitos gerais
        general_check = self._check_general_requirements(analysis)
        for req in self.GENERAL_REQUIREMENTS:
            max_score += req["weight"]
            if general_check.get(req["id"], False):
                total_score += req["weight"]
            else:
                issues.append(
                    {
                        "severity": "medium",
                        "type": "missing_requirement",
                        "description": f"Requisito ausente: {req['description']}",
                        "requirement_id": req["id"],
                    }
                )

        # 3. Verificar LGPD (se aplicavel)
        if check_lgpd and self._needs_lgpd_check(clauses):
            lgpd_check = self._check_lgpd_compliance(clauses)

            for req in self.LGPD_REQUIREMENTS:
                max_score += req["weight"]
                if lgpd_check.get(req["id"], False):
                    total_score += req["weight"]
                else:
                    issues.append(
                        {
                            "severity": "high",
                            "type": "lgpd_compliance",
                            "description": f"LGPD: {req['description']}",
                            "requirement_id": req["id"],
                        }
                    )

        # 4. Calcular score final
        compliance_score = (total_score / max_score * 100) if max_score > 0 else 0

        # 5. Determinar status
        status = self._determine_status(compliance_score, issues)

        # 6. Gerar recomendacoes
        recommendations = self._generate_recommendations(issues, missing_clauses)

        logger.info(f"Conformidade: {status} (score: {compliance_score:.1f})")

        return {
            "compliance_score": round(compliance_score, 1),
            "status": status,
            "required_clauses": required_clauses,
            "missing_clauses": missing_clauses,
            "issues": issues,
            "recommendations": recommendations,
        }

    def _check_general_requirements(self, analysis: ContractAnalysis) -> dict:
        """Verifica requisitos gerais."""
        return {
            "parties_identified": bool(analysis.contractor_name and analysis.contracted_name),
            "dates_defined": bool(analysis.start_date and analysis.end_date),
            "value_defined": bool(analysis.total_value or analysis.monthly_value),
            "jurisdiction_defined": True,  # Assumir presente se tiver clausula de foro
        }

    def _needs_lgpd_check(self, clauses: list[ExtractedClause]) -> bool:
        """Verifica se precisa verificar LGPD."""
        # Verificar se contrato menciona dados pessoais
        keywords = ["dados pessoais", "lgpd", "tratamento de dados", "privacidade"]

        for clause in clauses:
            text_lower = clause.original_text.lower()
            if any(kw in text_lower for kw in keywords):
                return True

        return False

    def _check_lgpd_compliance(self, clauses: list[ExtractedClause]) -> dict:
        """Verifica conformidade LGPD."""
        has_data_protection = any(c.clause_type == ClauseType.DATA_PROTECTION for c in clauses)

        # Verificar finalidade
        has_purpose = False
        for clause in clauses:
            if "finalidade" in clause.original_text.lower():
                has_purpose = True
                break

        return {
            "data_protection_clause": has_data_protection,
            "data_purpose": has_purpose,
        }

    def _determine_status(self, score: float, issues: list[dict]) -> str:
        """Determina status de conformidade."""
        high_issues = [i for i in issues if i.get("severity") == "high"]

        if score >= 90 and len(high_issues) == 0:
            return "compliant"
        elif score >= 70:
            return "partially_compliant"
        else:
            return "non_compliant"

    def _generate_recommendations(self, issues: list[dict], missing_clauses: list[str]) -> list[str]:
        """Gera recomendacoes de conformidade."""
        recommendations = []

        for clause in missing_clauses:
            recommendations.append(f"Adicionar clausula de {clause}")

        for issue in issues:
            if issue["type"] == "lgpd_compliance":
                recommendations.append("Incluir clausulas de protecao de dados (LGPD)")
            elif issue["type"] == "missing_requirement":
                if "partes" in issue["description"].lower():
                    recommendations.append("Identificar claramente as partes com nome e documento")
                elif "datas" in issue["description"].lower():
                    recommendations.append("Definir datas de inicio e termino da vigencia")

        return list(set(recommendations))[:10]

    def compare_with_template(
        self,
        analysis: ContractAnalysis,
        clauses: list[ExtractedClause],
        template_clauses: list[dict],
    ) -> dict:
        """
        Compara contrato com template padrao.

        Args:
            analysis: Analise do contrato
            clauses: Clausulas extraidas
            template_clauses: Clausulas do template

        Returns:
            Dict com score de match e desvios
        """
        if not template_clauses:
            return {
                "match_score": 0,
                "deviations": [],
                "error": "Template vazio",
            }

        matches = 0
        deviations = []

        for template_clause in template_clauses:
            template_type = template_clause.get("type")
            found = False

            for clause in clauses:
                if clause.clause_type.value == template_type:
                    found = True
                    break

            if found:
                matches += 1
            else:
                deviations.append(
                    {
                        "type": template_type,
                        "deviation": "missing",
                        "description": f"Clausula de {template_type} ausente no contrato",
                    }
                )

        match_score = (matches / len(template_clauses) * 100) if template_clauses else 0

        return {
            "match_score": round(match_score, 1),
            "deviations": deviations,
            "matched_clauses": matches,
            "total_template_clauses": len(template_clauses),
        }

    def get_compliance_report(self, analysis_id: UUID) -> dict:
        """Gera relatorio de conformidade."""
        analysis = self.repository.get_analysis(analysis_id, include_clauses=True)

        if not analysis:
            return {"error": "Analise nao encontrada"}

        return {
            "contract_id": str(analysis.contract_id),
            "contract_type": analysis.contract_type.value,
            "compliance_score": analysis.compliance_score,
            "status": self._determine_status(analysis.compliance_score, analysis.compliance_issues or []),
            "issues": analysis.compliance_issues or [],
            "missing_clauses": analysis.missing_clauses or [],
        }
