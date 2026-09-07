"""
Clause Extractor Service - AI Contract Analysis

Extrai clausulas de contratos usando NLP.
"""

import logging
import re

from sqlalchemy.orm import Session

from modules.ai.contract_analysis.models.contract_analysis import ContractType
from modules.ai.contract_analysis.models.extracted_clause import (
    ClauseImportance,
    ClauseType,
)
from modules.ai.contract_analysis.repositories.contract_repository import (
    ContractAnalysisRepository,
)

logger = logging.getLogger(__name__)


class ClauseExtractor:
    """
    Extrator de clausulas usando NLP.

    Identifica e classifica clausulas em contratos.
    """

    # Padroes regex para identificar clausulas
    CLAUSE_PATTERNS = [
        r"(?:CLÁUSULA|CLAUSULA|Cláusula|Clausula)\s+(\w+)[:\.\s-]+(.+?)(?=(?:CLÁUSULA|CLAUSULA|Cláusula|Clausula)\s+\w+|$)",
        r"(?:ARTIGO|Artigo|Art\.?)\s+(\d+)[:\.\s-]+(.+?)(?=(?:ARTIGO|Artigo|Art\.?)\s+\d+|$)",
        r"(\d+[\.\d]*)\s*[-–]\s*(.+?)(?=\d+[\.\d]*\s*[-–]|$)",
    ]

    # Mapeamento de palavras-chave para tipos de clausula
    CLAUSE_KEYWORDS = {
        ClauseType.OBJECT: ["objeto", "finalidade", "escopo", "propósito", "serviços prestados"],
        ClauseType.PAYMENT: [
            "pagamento",
            "remuneração",
            "preço",
            "valor",
            "honorários",
            "faturamento",
            "cobrança",
            "vencimento",
        ],
        ClauseType.PENALTY: [
            "multa",
            "penalidade",
            "sanção",
            "inadimplemento",
            "mora",
            "indenização",
            "perdas e danos",
        ],
        ClauseType.TERMINATION: ["rescisão", "resolução", "resilição", "término", "extinção", "denúncia", "distrato"],
        ClauseType.RENEWAL: ["renovação", "prorrogação", "vigência", "prazo", "duração"],
        ClauseType.CONFIDENTIALITY: [
            "confidencialidade",
            "sigilo",
            "segredo",
            "não divulgação",
            "informações confidenciais",
        ],
        ClauseType.NON_COMPETE: ["não concorrência", "exclusividade", "não competição", "restrição", "vedação"],
        ClauseType.WARRANTY: ["garantia", "responsabilidade", "qualidade", "defeito", "vício"],
        ClauseType.LIABILITY: ["responsabilidade civil", "limitação de responsabilidade", "danos", "indenizar"],
        ClauseType.FORCE_MAJEURE: ["força maior", "caso fortuito", "eventos extraordinários", "imprevisível"],
        ClauseType.DISPUTE: ["resolução de conflitos", "mediação", "arbitragem", "litígio", "controvérsia"],
        ClauseType.JURISDICTION: ["foro", "jurisdição", "comarca", "competência"],
        ClauseType.DATA_PROTECTION: [
            "lgpd",
            "proteção de dados",
            "dados pessoais",
            "privacidade",
            "tratamento de dados",
        ],
        ClauseType.SLA: ["nível de serviço", "sla", "disponibilidade", "uptime", "tempo de resposta"],
        ClauseType.PRICE_ADJUSTMENT: ["reajuste", "correção monetária", "índice", "igpm", "ipca", "atualização"],
        ClauseType.OBLIGATION: ["obrigação", "dever", "compromisso", "responsável por"],
    }

    # Padroes para extrair entidades
    DATE_PATTERN = r"\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}"
    MONEY_PATTERN = r"R\$\s*[\d.,]+|[\d.,]+\s*(?:reais|real)"
    PERCENTAGE_PATTERN = r"\d+[,.]?\d*\s*%"
    CNPJ_PATTERN = r"\d{2}\.\d{3}\.\d{3}\/\d{4}-\d{2}"
    CPF_PATTERN = r"\d{3}\.\d{3}\.\d{3}-\d{2}"

    def __init__(self, db: Session):
        """Inicializa extractor."""
        self.db = db
        self.repository = ContractAnalysisRepository(db)

    async def extract_clauses(
        self,
        text: str,
        contract_type: ContractType = ContractType.OTHER,
    ) -> list[dict]:
        """
        Extrai clausulas do texto do contrato.

        Args:
            text: Texto do contrato
            contract_type: Tipo de contrato

        Returns:
            Lista de clausulas extraidas
        """
        logger.info("Iniciando extracao de clausulas")

        clauses = []

        # Normalizar texto
        normalized_text = self._normalize_text(text)

        # Dividir em secoes/clausulas
        sections = self._split_into_sections(normalized_text)

        for i, section in enumerate(sections):
            clause_data = self._analyze_section(section, i + 1)
            if clause_data:
                clauses.append(clause_data)

        logger.info(f"Extraidas {len(clauses)} clausulas")
        return clauses

    def _normalize_text(self, text: str) -> str:
        """Normaliza texto do contrato."""
        # Remover multiplos espacos
        text = re.sub(r"\s+", " ", text)
        # Remover quebras de linha excessivas
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _split_into_sections(self, text: str) -> list[dict]:
        """Divide texto em secoes."""
        sections = []

        # Tentar diferentes padroes
        for pattern in self.CLAUSE_PATTERNS:
            matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
            if matches:
                for match in matches:
                    if isinstance(match, tuple) and len(match) >= 2:
                        sections.append(
                            {
                                "number": match[0].strip(),
                                "content": match[1].strip(),
                            }
                        )
                break

        # Se nao encontrou padroes, dividir por paragrafos
        if not sections:
            paragraphs = text.split("\n\n")
            for i, para in enumerate(paragraphs):
                if len(para.strip()) > 50:  # Ignorar paragrafos muito curtos
                    sections.append(
                        {
                            "number": str(i + 1),
                            "content": para.strip(),
                        }
                    )

        return sections

    def _analyze_section(self, section: dict, index: int) -> dict | None:
        """Analisa uma secao e extrai informacoes."""
        content = section.get("content", "")
        if not content or len(content) < 20:
            return None

        # Classificar tipo da clausula
        clause_type, confidence = self._classify_clause(content)

        # Extrair entidades
        entities = self._extract_entities(content)

        # Determinar importancia
        importance = self._determine_importance(clause_type, content)

        # Detectar risco
        is_risky, risk_score, risk_reasons = self._detect_risk(content, clause_type)

        # Extrair obrigacoes
        obligations = self._extract_obligations(content)

        # Gerar resumo
        summary = self._generate_summary(content)

        return {
            "clause_number": section.get("number", str(index)),
            "clause_title": self._extract_title(content),
            "clause_type": clause_type,
            "clause_type_confidence": confidence,
            "original_text": content,
            "normalized_text": self._normalize_text(content),
            "summary": summary,
            "importance": importance,
            "is_standard": confidence >= 70,
            "is_custom": confidence < 50,
            "is_risky": is_risky,
            "entities": entities,
            "dates_found": self._extract_dates(content),
            "values_found": self._extract_values(content),
            "risk_score": risk_score,
            "risk_reasons": risk_reasons,
            "obligations": obligations,
            "has_deadline": bool(re.search(r"prazo|dias|meses|até", content, re.I)),
            "has_monetary_value": bool(re.search(self.MONEY_PATTERN, content, re.I)),
            "has_percentage": bool(re.search(self.PERCENTAGE_PATTERN, content)),
            "requires_action": bool(re.search(r"deverá|deve|obriga|compromete", content, re.I)),
        }

    def _classify_clause(self, content: str) -> tuple[ClauseType, float]:
        """Classifica tipo da clausula."""
        content_lower = content.lower()
        best_type = ClauseType.OTHER
        best_score = 0

        for clause_type, keywords in self.CLAUSE_KEYWORDS.items():
            score = 0
            for keyword in keywords:
                if keyword.lower() in content_lower:
                    score += 1

            # Normalizar score
            if keywords:
                normalized_score = (score / len(keywords)) * 100

                if normalized_score > best_score:
                    best_score = normalized_score
                    best_type = clause_type

        # Ajustar confianca
        confidence = min(95, best_score * 2) if best_score > 0 else 30

        return best_type, confidence

    def _extract_entities(self, content: str) -> list[dict]:
        """Extrai entidades do texto."""
        entities = []

        # Datas
        dates = re.findall(self.DATE_PATTERN, content)
        for d in dates:
            entities.append({"type": "date", "value": d})

        # Valores monetarios
        values = re.findall(self.MONEY_PATTERN, content, re.I)
        for v in values:
            entities.append({"type": "monetary", "value": v})

        # Percentuais
        percentages = re.findall(self.PERCENTAGE_PATTERN, content)
        for p in percentages:
            entities.append({"type": "percentage", "value": p})

        # CNPJ
        cnpjs = re.findall(self.CNPJ_PATTERN, content)
        for c in cnpjs:
            entities.append({"type": "cnpj", "value": c})

        # CPF
        cpfs = re.findall(self.CPF_PATTERN, content)
        for c in cpfs:
            entities.append({"type": "cpf", "value": c})

        return entities

    def _extract_dates(self, content: str) -> list[dict]:
        """Extrai datas com contexto."""
        dates = []
        patterns = [
            (r"vigência.*?(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})", "vigencia"),
            (r"vencimento.*?(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})", "vencimento"),
            (r"início.*?(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})", "inicio"),
            (r"término.*?(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})", "termino"),
            (r"renovação.*?(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})", "renovacao"),
        ]

        for pattern, label in patterns:
            matches = re.findall(pattern, content, re.I)
            for m in matches:
                dates.append({"date": m, "context": label})

        return dates

    def _extract_values(self, content: str) -> list[dict]:
        """Extrai valores monetarios com contexto."""
        values = []
        patterns = [
            (r"(?:valor|preço|remuneração)[^R$]*?(R\$\s*[\d.,]+)", "valor_principal"),
            (r"multa[^R$]*?(R\$\s*[\d.,]+)", "multa"),
            (r"(?:mensal|mensalmente)[^R$]*?(R\$\s*[\d.,]+)", "valor_mensal"),
        ]

        for pattern, label in patterns:
            matches = re.findall(pattern, content, re.I)
            for m in matches:
                values.append({"value": m, "context": label})

        return values

    def _determine_importance(self, clause_type: ClauseType, content: str) -> ClauseImportance:
        """Determina importancia da clausula."""
        critical_types = {
            ClauseType.PAYMENT,
            ClauseType.PENALTY,
            ClauseType.TERMINATION,
            ClauseType.LIABILITY,
        }

        high_types = {
            ClauseType.CONFIDENTIALITY,
            ClauseType.NON_COMPETE,
            ClauseType.WARRANTY,
            ClauseType.DATA_PROTECTION,
        }

        if clause_type in critical_types:
            return ClauseImportance.CRITICAL

        if clause_type in high_types:
            return ClauseImportance.HIGH

        # Verificar palavras indicativas de importancia
        critical_words = ["irrevogável", "irretratável", "definitivo", "imediato"]
        if any(word in content.lower() for word in critical_words):
            return ClauseImportance.HIGH

        return ClauseImportance.MEDIUM

    def _detect_risk(self, content: str, clause_type: ClauseType) -> tuple[bool, float, list[str]]:
        """Detecta riscos na clausula."""
        risk_score = 0
        risk_reasons = []

        content_lower = content.lower()

        # Indicadores de risco
        risk_indicators = {
            "renúncia": ("Renuncia de direitos", 20),
            "irrevogável": ("Clausula irrevogavel", 15),
            "exclusivamente": ("Exclusividade total", 15),
            "sob pena de": ("Penalidade severa", 20),
            "rescisão imediata": ("Rescisao imediata", 25),
            "sem aviso prévio": ("Sem aviso previo", 20),
            "ilimitada": ("Responsabilidade ilimitada", 25),
            "todas as despesas": ("Assuncao total de despesas", 15),
            "integral": ("Responsabilidade integral", 15),
        }

        for indicator, (reason, points) in risk_indicators.items():
            if indicator in content_lower:
                risk_score += points
                risk_reasons.append(reason)

        # Tipos de clausula mais arriscados
        if clause_type in (ClauseType.PENALTY, ClauseType.LIABILITY):
            risk_score += 10

        is_risky = risk_score >= 30

        return is_risky, min(100, risk_score), risk_reasons

    def _extract_obligations(self, content: str) -> list[dict]:
        """Extrai obrigacoes da clausula."""
        obligations = []

        # Padroes de obrigacao
        patterns = [
            r"(?:contratante|contratado)\s+(?:deverá|deve|se obriga a)\s+([^.]+)",
            r"(?:é obrigação|cabe a)\s+(?:da |do )?(\w+)\s+([^.]+)",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content, re.I)
            for match in matches:
                if isinstance(match, tuple):
                    obligations.append(
                        {
                            "party": match[0] if len(match) > 1 else "parte",
                            "action": match[-1].strip(),
                        }
                    )
                else:
                    obligations.append({"action": match.strip()})

        return obligations[:5]  # Limitar a 5

    def _extract_title(self, content: str) -> str | None:
        """Extrai titulo da clausula."""
        # Primeira linha ate 100 caracteres
        first_line = content.split("\n")[0].strip()
        if len(first_line) <= 100:
            return first_line
        return first_line[:100] + "..."

    def _generate_summary(self, content: str) -> str:
        """Gera resumo da clausula."""
        # Primeiras 200 palavras
        words = content.split()
        if len(words) <= 50:
            return content

        summary = " ".join(words[:50]) + "..."
        return summary

    def identify_contract_type(self, text: str) -> tuple[ContractType, float]:
        """Identifica tipo do contrato pelo texto."""
        text_lower = text.lower()

        type_indicators = {
            ContractType.SERVICE: ["prestação de serviços", "serviços", "consultoria"],
            ContractType.SALES: ["compra e venda", "venda", "aquisição"],
            ContractType.LEASE: ["locação", "aluguel", "arrendamento"],
            ContractType.EMPLOYMENT: ["trabalho", "emprego", "clt", "contratação"],
            ContractType.NDA: ["confidencialidade", "sigilo", "nda", "não divulgação"],
            ContractType.SLA: ["nível de serviço", "sla", "disponibilidade"],
            ContractType.MAINTENANCE: ["manutenção", "suporte", "assistência técnica"],
            ContractType.SUPPLY: ["fornecimento", "entrega", "abastecimento"],
        }

        best_type = ContractType.OTHER
        best_score = 0

        for contract_type, indicators in type_indicators.items():
            score = sum(1 for ind in indicators if ind in text_lower)
            if score > best_score:
                best_score = score
                best_type = contract_type

        confidence = min(90, best_score * 30) if best_score > 0 else 20

        return best_type, confidence

    def extract_parties(self, text: str) -> dict:
        """Extrai partes do contrato."""
        parties = {
            "contractor": None,
            "contractor_document": None,
            "contracted": None,
            "contracted_document": None,
        }

        # Buscar CNPJ/CPF
        cnpjs = re.findall(self.CNPJ_PATTERN, text)
        cpfs = re.findall(self.CPF_PATTERN, text)

        documents = cnpjs + cpfs

        if len(documents) >= 2:
            parties["contractor_document"] = documents[0]
            parties["contracted_document"] = documents[1]
        elif len(documents) == 1:
            parties["contractor_document"] = documents[0]

        # Buscar nomes (simplificado)
        name_patterns = [
            r"CONTRATANTE[:\s]+([A-Z][A-Za-zÀ-ÿ\s]+)",
            r"CONTRATADO[:\s]+([A-Z][A-Za-zÀ-ÿ\s]+)",
        ]

        for i, pattern in enumerate(name_patterns):
            match = re.search(pattern, text)
            if match:
                name = match.group(1).strip()[:100]
                if i == 0:
                    parties["contractor"] = name
                else:
                    parties["contracted"] = name

        return parties
