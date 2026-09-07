"""Análise pura de contrato (5.6b) — reusa ClauseExtractor/RiskAnalyzer/ComplianceChecker.

Serviço FINO para a rota read-only da Central de Contratos jurídica. Não é CRUD, não
persiste nada, não chama LLM: só roda regex/scoring já existentes em cima do TEXTO real
do contrato (`contracts.content`/`description`).

As 3 classes reusadas (ClauseExtractor, RiskAnalyzer, ComplianceChecker) foram escritas
para operar com um `db: Session` porque instanciam um `ContractAnalysisRepository` — mas
os métodos usados aqui (extract_clauses, identify_contract_type, extract_parties,
analyze_risk, check_compliance) nunca tocam o repository, só regex sobre string e scoring
sobre objetos ORM em memória (nunca adicionados a nenhuma sessão/commit). Por isso é seguro
instanciá-las com db=None.

Nunca fabrica: cláusula/valor/parte que não está no texto simplesmente não aparece no
resultado (listas vazias / campos None), nunca é inventado.
"""

from __future__ import annotations

from modules.ai.contract_analysis.models.contract_analysis import ContractAnalysis
from modules.ai.contract_analysis.models.extracted_clause import ClauseType, ExtractedClause
from modules.ai.contract_analysis.services.clause_extractor import ClauseExtractor
from modules.ai.contract_analysis.services.compliance_checker import ComplianceChecker
from modules.ai.contract_analysis.services.risk_analyzer import RiskAnalyzer


async def analisar(texto: str) -> dict:
    """Extrai cláusulas + risco + conformidade do texto real de um contrato.

    Read-only e sem banco. `texto` vazio => resultado vazio honesto (nunca inventa).
    """
    texto = (texto or "").strip()
    if not texto:
        return {
            "clausulas": [],
            "risco": None,
            "compliance": None,
            "mensagem": "Sem texto para analisar (contrato sem `content`/`description`).",
        }

    extractor = ClauseExtractor(db=None)
    risk_analyzer = RiskAnalyzer(db=None)
    compliance_checker = ComplianceChecker(db=None)

    contract_type, type_confidence = extractor.identify_contract_type(texto)
    parties = extractor.extract_parties(texto)
    clause_dicts = await extractor.extract_clauses(texto, contract_type=contract_type)

    # Objetos ORM em memória (nunca adicionados a sessão/commitados) só para reusar o
    # scoring puro de risk_analyzer/compliance_checker, que espera esses tipos.
    clauses = [
        ExtractedClause(
            clause_number=c["clause_number"],
            clause_title=c["clause_title"],
            clause_type=c["clause_type"],
            clause_type_confidence=c["clause_type_confidence"],
            original_text=c["original_text"],
            is_risky=c["is_risky"],
            risk_score=c["risk_score"],
            risk_reasons=c["risk_reasons"],
        )
        for c in clause_dicts
    ]
    analysis = ContractAnalysis(
        contract_type=contract_type,
        contract_type_confidence=type_confidence,
        contractor_name=parties["contractor"],
        contractor_document=parties["contractor_document"],
        contracted_name=parties["contracted"],
        contracted_document=parties["contracted_document"],
        has_auto_renewal=any(c["clause_type"] == ClauseType.RENEWAL for c in clause_dicts),
        has_penalty_clause=any(c["clause_type"] == ClauseType.PENALTY for c in clause_dicts),
    )

    risco = risk_analyzer.analyze_risk(analysis, clauses)
    compliance = compliance_checker.check_compliance(analysis, clauses, check_lgpd=True)

    return {
        "contrato_tipo": contract_type.value,
        "contrato_tipo_confianca": type_confidence,
        "partes": parties,
        "clausulas": [
            {
                "numero": c["clause_number"],
                "titulo": c["clause_title"],
                "tipo": c["clause_type"].value,
                "resumo": c["summary"],
                "importancia": c["importance"].value,
                "arriscada": c["is_risky"],
                "risco_score": c["risk_score"],
                "risco_motivos": c["risk_reasons"],
                "datas": c["dates_found"],
                "valores": c["values_found"],
            }
            for c in clause_dicts
        ],
        "risco": {
            "nivel": risco["risk_level"].value,
            "score": risco["risk_score"],
            "fatores": risco["risk_factors"],
            "recomendacoes": risco["recommendations"],
        },
        "compliance": compliance,
    }
