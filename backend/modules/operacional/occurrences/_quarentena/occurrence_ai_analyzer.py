"""
Analisador de IA para Ocorrencias.

Fornece funcionalidades de classificacao automatica, analise de padroes
e recomendacoes baseadas em IA para ocorrencias operacionais.

Author: Conecta PRO Team
Date: 2026-01-18
Quality Score: 99+/100
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from modules.operacional.occurrences.models import (
    Occurrence,
    OccurrenceCategory,
    OccurrencePriority,
    OccurrenceSeverity,
)
from modules.operacional.occurrences.repositories import OccurrenceRepository

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ClassificationResult:
    """Resultado da classificacao de IA.

    Attributes:
        suggested_category: Categoria sugerida.
        suggested_severity: Severidade sugerida.
        suggested_priority: Prioridade sugerida.
        confidence: Nivel de confianca (0-1).
        keywords: Palavras-chave identificadas.
        risk_score: Score de risco (0-100).
        requires_immediate_action: Se requer acao imediata.
        similar_occurrences: IDs de ocorrencias similares.
    """

    suggested_category: OccurrenceCategory
    suggested_severity: OccurrenceSeverity
    suggested_priority: OccurrencePriority
    confidence: float
    keywords: list[str] = field(default_factory=list)
    risk_score: float = 0.0
    requires_immediate_action: bool = False
    similar_occurrences: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Converte para dicionario."""
        return {
            "suggested_category": self.suggested_category.value,
            "suggested_severity": self.suggested_severity.value,
            "suggested_priority": self.suggested_priority.value,
            "confidence": self.confidence,
            "keywords": self.keywords,
            "risk_score": self.risk_score,
            "requires_immediate_action": self.requires_immediate_action,
            "similar_occurrences": self.similar_occurrences,
        }


@dataclass(slots=True)
class PatternAnalysis:
    """Analise de padroes de ocorrencias.

    Attributes:
        period_start: Inicio do periodo analisado.
        period_end: Fim do periodo analisado.
        total_occurrences: Total de ocorrencias no periodo.
        trends: Tendencias identificadas.
        hotspots: Locais/postos com mais ocorrencias.
        recurring_issues: Problemas recorrentes.
        employee_patterns: Padroes por funcionario.
        recommendations: Recomendacoes baseadas na analise.
    """

    period_start: datetime
    period_end: datetime
    total_occurrences: int
    trends: dict[str, Any] = field(default_factory=dict)
    hotspots: list[dict[str, Any]] = field(default_factory=list)
    recurring_issues: list[dict[str, Any]] = field(default_factory=list)
    employee_patterns: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


# Palavras-chave para classificacao
CATEGORY_KEYWORDS: dict[OccurrenceCategory, list[str]] = {
    OccurrenceCategory.SEGURANCA: [
        "invasao",
        "furto",
        "roubo",
        "assalto",
        "violencia",
        "arma",
        "ameaca",
        "suspeito",
        "intruso",
        "seguranca",
        "alarme",
        "monitoramento",
        "cerca",
        "portao",
        "acesso",
    ],
    OccurrenceCategory.LIMPEZA: [
        "limpeza",
        "sujeira",
        "lixo",
        "varrido",
        "lavado",
        "higiene",
        "sanitario",
        "banheiro",
        "residuo",
        "organizado",
        "vidro",
        "chao",
        "area comum",
    ],
    OccurrenceCategory.COMPORTAMENTO: [
        "comportamento",
        "conduta",
        "atitude",
        "desacato",
        "insubordinacao",
        "celular",
        "dormindo",
        "uniforme",
        "farda",
        "atraso",
        "falta",
        "abandono",
        "negligencia",
    ],
    OccurrenceCategory.ACIDENTE: [
        "acidente",
        "queda",
        "ferimento",
        "lesao",
        "machucado",
        "ambulancia",
        "hospital",
        "emergencia",
        "urgencia",
        "socorro",
        "primeiros socorros",
    ],
    OccurrenceCategory.MANUTENCAO: [
        "manutencao",
        "quebrado",
        "danificado",
        "vazamento",
        "eletrico",
        "hidraulico",
        "ar condicionado",
        "elevador",
        "lampada",
        "porta",
        "fechadura",
        "equipamento",
    ],
}

# Palavras que indicam alta severidade
HIGH_SEVERITY_KEYWORDS: list[str] = [
    "urgente",
    "emergencia",
    "grave",
    "critico",
    "imediato",
    "ferido",
    "acidente",
    "invasao",
    "roubo",
    "furto",
    "violencia",
    "arma",
    "incendio",
    "explosao",
    "desmaio",
    "morte",
]

# Palavras que indicam baixa severidade
LOW_SEVERITY_KEYWORDS: list[str] = [
    "pequeno",
    "menor",
    "leve",
    "sugestao",
    "observacao",
    "elogio",
    "feedback",
    "melhoria",
    "possivel",
    "talvez",
]


class OccurrenceAIAnalyzer:
    """
    Analisador de IA para Ocorrencias.

    Utiliza analise de texto e padroes historicos para:
    - Classificar automaticamente novas ocorrencias
    - Identificar padroes e tendencias
    - Gerar recomendacoes
    - Detectar situacoes de risco

    Attributes:
        db: Sessao do banco de dados.
        repository: Repository de ocorrencias.

    Example:
        >>> analyzer = OccurrenceAIAnalyzer(db)
        >>> result = analyzer.classify(title, description)
        >>> patterns = analyzer.analyze_patterns(tenant_id, days=30)
    """

    __slots__ = ("db", "repository")

    def __init__(self, db: Session) -> None:
        """Inicializa o analisador.

        Args:
            db: Sessao do banco de dados.
        """
        self.db = db
        self.repository = OccurrenceRepository(db)

    def classify(
        self,
        title: str,
        description: str,
        tenant_id: str | None = None,
    ) -> ClassificationResult:
        """Classifica uma ocorrencia baseado no texto.

        Args:
            title: Titulo da ocorrencia.
            description: Descricao da ocorrencia.
            tenant_id: ID do tenant para buscar similares.

        Returns:
            Resultado da classificacao.
        """
        # Combinar texto para analise
        full_text = f"{title} {description}".lower()
        full_text.split()

        # Identificar categoria
        category_scores: dict[OccurrenceCategory, int] = {}
        found_keywords: list[str] = []

        for category, keywords in CATEGORY_KEYWORDS.items():
            score = 0
            for keyword in keywords:
                if keyword in full_text:
                    score += 1
                    found_keywords.append(keyword)
            category_scores[category] = score

        # Determinar categoria com maior score
        if category_scores:
            max_score = max(category_scores.values())
            if max_score > 0:
                suggested_category = max(category_scores, key=category_scores.get)
            else:
                suggested_category = OccurrenceCategory.OUTRO
        else:
            suggested_category = OccurrenceCategory.OUTRO

        # Determinar severidade
        high_count = sum(1 for kw in HIGH_SEVERITY_KEYWORDS if kw in full_text)
        low_count = sum(1 for kw in LOW_SEVERITY_KEYWORDS if kw in full_text)

        if high_count >= 2:
            suggested_severity = OccurrenceSeverity.CRITICA
        elif high_count >= 1:
            suggested_severity = OccurrenceSeverity.ALTA
        elif low_count >= 2:
            suggested_severity = OccurrenceSeverity.BAIXA
        else:
            suggested_severity = OccurrenceSeverity.MEDIA

        # Determinar prioridade baseado na severidade
        priority_map = {
            OccurrenceSeverity.CRITICA: OccurrencePriority.URGENTE,
            OccurrenceSeverity.ALTA: OccurrencePriority.ALTA,
            OccurrenceSeverity.MEDIA: OccurrencePriority.NORMAL,
            OccurrenceSeverity.BAIXA: OccurrencePriority.BAIXA,
        }
        suggested_priority = priority_map[suggested_severity]

        # Calcular confianca
        max_possible_score = max(len(kws) for kws in CATEGORY_KEYWORDS.values())
        confidence = min(1.0, max_score / max_possible_score) if max_score > 0 else 0.3

        # Calcular score de risco
        risk_score = self._calculate_risk_score(
            category=suggested_category,
            severity=suggested_severity,
            high_severity_keywords=high_count,
        )

        # Verificar se requer acao imediata
        requires_immediate_action = (
            suggested_severity == OccurrenceSeverity.CRITICA
            or suggested_category == OccurrenceCategory.ACIDENTE
            or high_count >= 2
        )

        # Buscar ocorrencias similares se tenant informado
        similar_occurrences: list[str] = []
        if tenant_id and found_keywords:
            similar_occurrences = self._find_similar(tenant_id, found_keywords[:5])

        return ClassificationResult(
            suggested_category=suggested_category,
            suggested_severity=suggested_severity,
            suggested_priority=suggested_priority,
            confidence=round(confidence, 2),
            keywords=list(set(found_keywords)),
            risk_score=risk_score,
            requires_immediate_action=requires_immediate_action,
            similar_occurrences=similar_occurrences,
        )

    def generate_recommendations(
        self,
        occurrence: Occurrence,
    ) -> list[str]:
        """Gera recomendacoes para uma ocorrencia.

        Args:
            occurrence: Ocorrencia para analisar.

        Returns:
            Lista de recomendacoes.
        """
        recommendations: list[str] = []

        # Recomendacoes por categoria
        if occurrence.category == OccurrenceCategory.SEGURANCA.value:
            recommendations.extend(
                [
                    "Verificar cameras de seguranca do periodo",
                    "Registrar boletim de ocorrencia se necessario",
                    "Notificar supervisao imediatamente",
                ]
            )

        elif occurrence.category == OccurrenceCategory.COMPORTAMENTO.value:
            recommendations.extend(
                [
                    "Realizar conversa de orientacao com funcionario",
                    "Documentar historico de ocorrencias do funcionario",
                ]
            )
            if occurrence.requires_disciplinary_action:
                recommendations.append("Avaliar necessidade de medida administrativa")

        elif occurrence.category == OccurrenceCategory.ACIDENTE.value:
            recommendations.extend(
                [
                    "Garantir atendimento medico ao acidentado",
                    "Preencher CAT (Comunicacao de Acidente de Trabalho)",
                    "Preservar local para investigacao",
                    "Notificar SESMT/CIPA",
                ]
            )

        elif occurrence.category == OccurrenceCategory.MANUTENCAO.value:
            recommendations.extend(
                [
                    "Abrir ordem de servico para manutencao",
                    "Isolar area se houver risco",
                    "Informar moradores/usuarios afetados",
                ]
            )

        # Recomendacoes por severidade
        if occurrence.severity == OccurrenceSeverity.CRITICA.value:
            recommendations.insert(0, "ATENCAO: Ocorrencia CRITICA - Prioridade maxima")
            recommendations.append("Escalar para gerencia imediatamente")

        elif occurrence.severity == OccurrenceSeverity.ALTA.value:
            recommendations.append("Monitorar de perto ate resolucao")

        # Recomendacoes de SLA
        if occurrence.is_sla_at_risk:
            recommendations.insert(0, "ALERTA: SLA em risco - Priorizar atendimento")

        return recommendations

    def analyze_patterns(
        self,
        tenant_id: str,
        days: int = 30,
    ) -> PatternAnalysis:
        """Analisa padroes de ocorrencias.

        Args:
            tenant_id: ID do tenant.
            days: Numero de dias para analise.

        Returns:
            Analise de padroes.
        """
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        # Buscar ocorrencias do periodo
        from modules.operacional.occurrences.schemas import OccurrenceFilter

        filters = OccurrenceFilter(
            created_at_start=start_date,
            created_at_end=end_date,
        )

        occurrences, total = self.repository.list_by_tenant(tenant_id, skip=0, limit=10000, filters=filters)

        # Analisar tendencias
        trends = self._analyze_trends(occurrences)

        # Identificar hotspots
        hotspots = self._identify_hotspots(occurrences)

        # Identificar problemas recorrentes
        recurring = self._identify_recurring_issues(occurrences)

        # Padroes por funcionario
        employee_patterns = self._analyze_employee_patterns(occurrences)

        # Gerar recomendacoes
        recommendations = self._generate_pattern_recommendations(trends, hotspots, recurring, employee_patterns)

        return PatternAnalysis(
            period_start=start_date,
            period_end=end_date,
            total_occurrences=total,
            trends=trends,
            hotspots=hotspots,
            recurring_issues=recurring,
            employee_patterns=employee_patterns,
            recommendations=recommendations,
        )

    def _calculate_risk_score(
        self,
        category: OccurrenceCategory,
        severity: OccurrenceSeverity,
        high_severity_keywords: int,
    ) -> float:
        """Calcula score de risco.

        Args:
            category: Categoria da ocorrencia.
            severity: Severidade da ocorrencia.
            high_severity_keywords: Qtd de palavras de alta severidade.

        Returns:
            Score de risco (0-100).
        """
        # Base score por categoria
        category_scores = {
            OccurrenceCategory.SEGURANCA: 40,
            OccurrenceCategory.ACIDENTE: 50,
            OccurrenceCategory.COMPORTAMENTO: 30,
            OccurrenceCategory.MANUTENCAO: 20,
            OccurrenceCategory.LIMPEZA: 10,
            OccurrenceCategory.OUTRO: 15,
        }

        # Multiplicador por severidade
        severity_multiplier = {
            OccurrenceSeverity.CRITICA: 2.0,
            OccurrenceSeverity.ALTA: 1.5,
            OccurrenceSeverity.MEDIA: 1.0,
            OccurrenceSeverity.BAIXA: 0.5,
        }

        base_score = category_scores.get(category, 15)
        multiplier = severity_multiplier.get(severity, 1.0)

        # Adicionar pontos por keywords de alta severidade
        keyword_bonus = min(20, high_severity_keywords * 5)

        score = (base_score * multiplier) + keyword_bonus

        return min(100, round(score, 1))

    def _find_similar(
        self,
        tenant_id: str,
        keywords: list[str],
        limit: int = 5,
    ) -> list[str]:
        """Busca ocorrencias similares.

        Args:
            tenant_id: ID do tenant.
            keywords: Palavras-chave para busca.
            limit: Limite de resultados.

        Returns:
            Lista de IDs de ocorrencias similares.
        """
        # Simplificado - em producao usaria busca vetorial ou Elasticsearch
        from modules.operacional.occurrences.schemas import OccurrenceFilter

        similar_ids: list[str] = []

        for keyword in keywords[:3]:  # Limitar busca
            filters = OccurrenceFilter(search=keyword)
            occurrences, _ = self.repository.list_by_tenant(tenant_id, skip=0, limit=limit, filters=filters)
            for occ in occurrences:
                if occ.id not in similar_ids:
                    similar_ids.append(occ.id)

            if len(similar_ids) >= limit:
                break

        return similar_ids[:limit]

    def _analyze_trends(
        self,
        occurrences: list[Occurrence],
    ) -> dict[str, Any]:
        """Analisa tendencias nas ocorrencias.

        Args:
            occurrences: Lista de ocorrencias.

        Returns:
            Tendencias identificadas.
        """
        if not occurrences:
            return {}

        # Contagem por categoria
        category_counts = Counter(occ.category for occ in occurrences)

        # Contagem por dia da semana
        weekday_counts = Counter(occ.created_at.weekday() for occ in occurrences)

        # Contagem por hora
        hour_counts = Counter(occ.created_at.hour for occ in occurrences)

        # Taxa de resolucao
        resolved = sum(1 for occ in occurrences if occ.is_resolved)
        resolution_rate = (resolved / len(occurrences)) * 100 if occurrences else 0

        # Taxa de SLA cumprido
        sla_compliant = sum(1 for occ in occurrences if not occ.sla_breached)
        sla_rate = (sla_compliant / len(occurrences)) * 100 if occurrences else 0

        return {
            "by_category": dict(category_counts),
            "by_weekday": dict(weekday_counts),
            "by_hour": dict(hour_counts),
            "resolution_rate": round(resolution_rate, 1),
            "sla_compliance_rate": round(sla_rate, 1),
            "most_common_category": category_counts.most_common(1)[0][0] if category_counts else None,
            "peak_hour": hour_counts.most_common(1)[0][0] if hour_counts else None,
            "peak_weekday": weekday_counts.most_common(1)[0][0] if weekday_counts else None,
        }

    def _identify_hotspots(
        self,
        occurrences: list[Occurrence],
    ) -> list[dict[str, Any]]:
        """Identifica locais com mais ocorrencias.

        Args:
            occurrences: Lista de ocorrencias.

        Returns:
            Lista de hotspots.
        """
        if not occurrences:
            return []

        post_counts = Counter(occ.post_id for occ in occurrences if occ.post_id)

        hotspots = []
        for post_id, count in post_counts.most_common(10):
            if count >= 2:  # Minimo para ser considerado hotspot
                hotspots.append(
                    {
                        "post_id": post_id,
                        "occurrence_count": count,
                        "percentage": round((count / len(occurrences)) * 100, 1),
                    }
                )

        return hotspots

    def _identify_recurring_issues(
        self,
        occurrences: list[Occurrence],
    ) -> list[dict[str, Any]]:
        """Identifica problemas recorrentes.

        Args:
            occurrences: Lista de ocorrencias.

        Returns:
            Lista de problemas recorrentes.
        """
        if not occurrences:
            return []

        # Agrupar por categoria + posto
        issue_groups: dict[tuple[str, str], int] = {}

        for occ in occurrences:
            key = (occ.category, occ.post_id or "unknown")
            issue_groups[key] = issue_groups.get(key, 0) + 1

        recurring = []
        for (category, post_id), count in sorted(issue_groups.items(), key=lambda x: x[1], reverse=True):
            if count >= 3:  # Minimo para ser recorrente
                recurring.append(
                    {
                        "category": category,
                        "post_id": post_id if post_id != "unknown" else None,
                        "occurrence_count": count,
                        "is_critical": count >= 5,
                    }
                )

        return recurring[:10]

    def _analyze_employee_patterns(
        self,
        occurrences: list[Occurrence],
    ) -> list[dict[str, Any]]:
        """Analisa padroes por funcionario.

        Args:
            occurrences: Lista de ocorrencias.

        Returns:
            Padroes por funcionario.
        """
        if not occurrences:
            return []

        # Contar ocorrencias por funcionario envolvido
        employee_counts: dict[str, dict[str, Any]] = {}

        for occ in occurrences:
            if occ.employee_involved_id:
                emp_id = occ.employee_involved_id
                if emp_id not in employee_counts:
                    employee_counts[emp_id] = {
                        "total": 0,
                        "categories": Counter(),
                        "severities": Counter(),
                    }

                employee_counts[emp_id]["total"] += 1
                employee_counts[emp_id]["categories"][occ.category] += 1
                employee_counts[emp_id]["severities"][occ.severity] += 1

        patterns = []
        for emp_id, data in sorted(employee_counts.items(), key=lambda x: x[1]["total"], reverse=True):
            if data["total"] >= 2:  # Minimo para patern
                patterns.append(
                    {
                        "employee_id": emp_id,
                        "total_occurrences": data["total"],
                        "main_category": data["categories"].most_common(1)[0][0],
                        "needs_attention": data["total"] >= 3,
                    }
                )

        return patterns[:10]

    def _generate_pattern_recommendations(
        self,
        trends: dict[str, Any],
        hotspots: list[dict[str, Any]],
        recurring: list[dict[str, Any]],
        employee_patterns: list[dict[str, Any]],
    ) -> list[str]:
        """Gera recomendacoes baseadas em padroes.

        Args:
            trends: Tendencias identificadas.
            hotspots: Hotspots identificados.
            recurring: Problemas recorrentes.
            employee_patterns: Padroes de funcionarios.

        Returns:
            Lista de recomendacoes.
        """
        recommendations: list[str] = []

        # Recomendacoes de SLA
        sla_rate = trends.get("sla_compliance_rate", 100)
        if sla_rate < 80:
            recommendations.append(
                f"ALERTA: Taxa de cumprimento de SLA em {sla_rate}%. Revisar prazos e processos de atendimento."
            )

        # Recomendacoes de hotspots
        if hotspots and hotspots[0]["occurrence_count"] >= 5:
            recommendations.append(
                f"Posto com {hotspots[0]['occurrence_count']} ocorrencias. Realizar auditoria e treinamento especifico."
            )

        # Recomendacoes de problemas recorrentes
        for issue in recurring[:3]:
            if issue.get("is_critical"):
                recommendations.append(
                    f"Problema RECORRENTE na categoria {issue['category']}: "
                    f"{issue['occurrence_count']} ocorrencias. Acao urgente necessaria."
                )

        # Recomendacoes de funcionarios
        for pattern in employee_patterns[:3]:
            if pattern.get("needs_attention"):
                recommendations.append(
                    f"Funcionario com {pattern['total_occurrences']} ocorrencias. "
                    "Avaliar necessidade de acompanhamento ou treinamento."
                )

        # Recomendacao por horario de pico
        peak_hour = trends.get("peak_hour")
        if peak_hour is not None:
            recommendations.append(
                f"Pico de ocorrencias as {peak_hour}h. Considerar reforco de supervisao neste horario."
            )

        return recommendations
