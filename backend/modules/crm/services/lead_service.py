"""
Serviço de Lead com algoritmo de scoring baseado em IA.
"""

from datetime import datetime, timedelta

from core.logging import logger
from modules.crm.models.lead import Lead, LeadSource, LeadStatus


class LeadScoringEngine:  # pylint: disable=too-few-public-methods
    """
    Motor de scoring de leads usando algoritmo baseado em regras e heurísticas.

    O score é calculado considerando múltiplos fatores:
    - Completude dos dados (20%)
    - Fonte do lead (15%)
    - Tamanho da empresa (20%)
    - Setor de atuação (15%)
    - Engajamento (20%)
    - Tempo de resposta (10%)
    """

    # Pesos para cada fator
    WEIGHTS = {
        "completeness": 0.20,
        "source": 0.15,
        "company_size": 0.20,
        "industry": 0.15,
        "engagement": 0.20,
        "response_time": 0.10,
    }

    # Scores por fonte
    SOURCE_SCORES = {
        LeadSource.REFERRAL.value: 100,
        LeadSource.WEBSITE.value: 80,
        LeadSource.SOCIAL_MEDIA.value: 70,
        LeadSource.EMAIL_CAMPAIGN.value: 65,
        LeadSource.EVENT.value: 75,
        LeadSource.PARTNER.value: 90,
        LeadSource.COLD_CALL.value: 40,
        LeadSource.OTHER.value: 50,
    }

    # Scores por tamanho de empresa
    COMPANY_SIZE_SCORES = {
        "enterprise": 100,  # > 1000 funcionários
        "large": 85,  # 200-1000
        "medium": 70,  # 50-200
        "small": 55,  # 10-50
        "micro": 40,  # < 10
    }

    # Setores prioritários (mais alinhados ao produto)
    PRIORITY_INDUSTRIES = {
        "condominios": 100,
        "facilities": 95,
        "seguranca": 90,
        "limpeza": 85,
        "administracao": 80,
        "construcao": 75,
        "imobiliario": 70,
    }

    def calculate_score(self, lead: Lead) -> tuple[int, float]:
        """
        Calcula score e probabilidade de conversão do lead.

        Args:
            lead: Objeto Lead para scoring

        Returns:
            Tupla (score, probability)
        """
        scores = {
            "completeness": self._score_completeness(lead),
            "source": self._score_source(lead),
            "company_size": self._score_company_size(lead),
            "industry": self._score_industry(lead),
            "engagement": self._score_engagement(lead),
            "response_time": self._score_response_time(lead),
        }

        # Calcular score ponderado
        total_score = sum(scores[factor] * weight for factor, weight in self.WEIGHTS.items())

        # Converter para inteiro (0-100)
        final_score = min(100, max(0, int(total_score)))

        # Calcular probabilidade baseada no score e status
        probability = self._calculate_probability(final_score, lead.status)

        logger.debug(
            f"Lead {lead.id} scored: {final_score} (prob: {probability:.1f}%)",
            extra={"scores": scores},
        )

        return final_score, probability

    def _score_completeness(self, lead: Lead) -> float:
        """Pontua completude dos dados do lead."""
        fields = [
            (lead.name, 15),
            (lead.email, 15),
            (lead.phone, 15),
            (lead.company, 20),
            (lead.position, 10),
            (lead.company_size, 10),
            (lead.industry, 10),
            (lead.notes, 5),
        ]

        score = sum(weight for value, weight in fields if value)
        return score

    def _score_source(self, lead: Lead) -> float:
        """Pontua baseado na fonte do lead."""
        return self.SOURCE_SCORES.get(lead.source, 50)

    def _score_company_size(self, lead: Lead) -> float:
        """Pontua baseado no tamanho da empresa."""
        if not lead.company_size:
            return 50  # Score neutro se não informado

        size = lead.company_size.lower()
        return self.COMPANY_SIZE_SCORES.get(size, 50)

    def _score_industry(self, lead: Lead) -> float:
        """Pontua baseado no setor de atuação."""
        if not lead.industry:
            return 50

        industry = lead.industry.lower()

        # Buscar correspondência parcial
        for key, score in self.PRIORITY_INDUSTRIES.items():
            if key in industry:
                return score

        return 50  # Outros setores

    def _score_engagement(self, lead: Lead) -> float:
        """Pontua baseado no engajamento/status do lead."""
        status_scores = {
            LeadStatus.NEW.value: 30,
            LeadStatus.CONTACTED.value: 50,
            LeadStatus.QUALIFIED.value: 75,
            LeadStatus.PROPOSAL.value: 85,
            LeadStatus.NEGOTIATION.value: 95,
            LeadStatus.WON.value: 100,
            LeadStatus.LOST.value: 0,
        }

        return status_scores.get(lead.status, 30)

    def _score_response_time(  # pylint: disable=too-many-return-statements
        self, lead: Lead
    ) -> float:
        """Pontua baseado no tempo desde último contato."""
        if not lead.last_contact_at:
            # Novo lead, sem contato ainda. created_at pode ser None na CRIACAO
            # (default now() do banco so aplica no commit -> scoring roda antes).
            if not lead.created_at:
                return 100  # lead recem-criado
            days_since_creation = (datetime.now() - lead.created_at).days
            if days_since_creation < 1:
                return 100  # Lead muito recente
            if days_since_creation < 7:
                return 70
            return 40

        days_since_contact = (datetime.now() - lead.last_contact_at).days

        if days_since_contact < 1:
            return 100
        if days_since_contact < 3:
            return 85
        if days_since_contact < 7:
            return 70
        if days_since_contact < 14:
            return 50
        if days_since_contact < 30:
            return 30
        return 10

    def _calculate_probability(self, score: int, status: str) -> float:
        """
        Calcula probabilidade de conversão.

        Combina o score com fatores históricos do status.
        """
        # Base probability do score
        base_prob = score * 0.6

        # Ajuste por status
        status_multipliers = {
            LeadStatus.NEW.value: 0.5,
            LeadStatus.CONTACTED.value: 0.7,
            LeadStatus.QUALIFIED.value: 1.0,
            LeadStatus.PROPOSAL.value: 1.3,
            LeadStatus.NEGOTIATION.value: 1.5,
            LeadStatus.WON.value: 2.0,
            LeadStatus.LOST.value: 0.0,
        }

        multiplier = status_multipliers.get(status, 0.5)
        probability = base_prob * multiplier

        return min(100.0, max(0.0, probability))


class LeadService:
    """Serviço para operações de negócio com Leads."""

    def __init__(self) -> None:
        self.scoring_engine = LeadScoringEngine()

    def calculate_score(self, lead: Lead) -> tuple[int, float]:
        """
        Calcula score e probabilidade do lead.

        Args:
            lead: Lead para scoring

        Returns:
            Tupla (score, probability)
        """
        return self.scoring_engine.calculate_score(lead)

    def get_recommended_action(  # pylint: disable=too-many-return-statements
        self, lead: Lead
    ) -> str:
        """
        Retorna ação recomendada para o lead.

        Args:
            lead: Lead para análise

        Returns:
            String com ação recomendada
        """
        if lead.status == LeadStatus.LOST.value:
            return "Arquivar ou tentar reengajamento após 90 dias"

        if lead.status == LeadStatus.WON.value:
            return "Iniciar onboarding do cliente"

        if lead.score >= 80:
            if lead.status == LeadStatus.NEW.value:
                return "Contato imediato - Lead quente!"
            if lead.status in (LeadStatus.CONTACTED.value, LeadStatus.QUALIFIED.value):
                return "Enviar proposta comercial"
            return "Agendar reunião de fechamento"

        if lead.score >= 50:
            if not lead.last_contact_at:
                return "Realizar primeiro contato"
            days_since = (datetime.now() - lead.last_contact_at).days
            if days_since > 7:
                return "Fazer follow-up"
            return "Aguardar resposta ou enviar material informativo"

        # Score baixo
        if not lead.company:
            return "Qualificar - obter informações da empresa"
        return "Nutrir com conteúdo antes de contato direto"

    def get_next_contact_date(self, lead: Lead) -> datetime | None:
        """
        Sugere data para próximo contato.

        Args:
            lead: Lead para análise

        Returns:
            Datetime sugerido ou None
        """
        if lead.status in (LeadStatus.WON.value, LeadStatus.LOST.value):
            return None

        now = datetime.now()

        # Leads quentes: contato em 1 dia
        if lead.score >= 80:
            return now + timedelta(days=1)

        # Leads mornos: contato em 3 dias
        if lead.score >= 50:
            return now + timedelta(days=3)

        # Leads frios: contato em 7 dias
        return now + timedelta(days=7)


# Instância global
lead_service = LeadService()
