"""
Service de Consentimento LGPD.

Persiste consentimentos na tabela ``lgpd_consents`` via ``ConsentRepository``.
NAO usa mais armazenamento em memoria: os dados sobrevivem a restart e sao
compartilhados entre workers.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from modules.security_lgpd.models.consent import (
    Consent,
    ConsentPurpose,
    ConsentStatus,
    LegalBasis,
)
from modules.security_lgpd.repositories.consent_repository import ConsentRepository

logger = logging.getLogger(__name__)


class ConsentService:
    """Service para gerenciamento de consentimentos LGPD.

    Encapsula a logica de registro, consulta e revogacao de consentimentos de
    titulares de dados conforme Art. 7 LGPD, persistindo tudo no banco via
    ``ConsentRepository``.
    """

    def __init__(self, repository: ConsentRepository | None = None):
        """Inicializa o service.

        Args:
            repository: Repository de consentimentos (com sessao de banco).
                Pode ser ``None`` apenas para endpoints estaticos (listas de
                finalidades/bases legais) que nao tocam o banco.
        """
        self.repository = repository

    def register_consent(
        self,
        titular_id: str,
        titular_email: str,
        purpose: str,
        legal_basis: str,
        description: str,
        expiration_days: int = 365,
    ) -> dict[str, Any]:
        """Registra consentimento de titular (persistindo no banco).

        Args:
            titular_id: UUID do titular.
            titular_email: Email do titular.
            purpose: Finalidade do consentimento.
            legal_basis: Base legal LGPD.
            description: Descricao detalhada.
            expiration_days: Dias ate expirar.

        Returns:
            Dict com dados do consentimento registrado.
        """
        now = datetime.utcnow()
        expiration = now + timedelta(days=expiration_days)

        consent = Consent(
            id=uuid.uuid4(),
            titular_id=UUID(str(titular_id)),
            titular_email=titular_email,
            purpose=ConsentPurpose(purpose),
            legal_basis=LegalBasis(legal_basis),
            description=description,
            status=ConsentStatus.ACTIVE,
            created_at=now,
            expires_at=expiration,
            version="1.0",
        )

        saved = self.repository.create(consent)

        logger.info(
            "Consentimento registrado (persistido): titular=%s, finalidade=%s",
            titular_id,
            purpose,
        )

        return {
            "consent_id": str(saved.id),
            "titular_id": str(saved.titular_id),
            "purpose": saved.purpose.value if saved.purpose else purpose,
            "legal_basis": saved.legal_basis.value if saved.legal_basis else legal_basis,
            "status": saved.status.value if saved.status else "active",
            "expires_at": saved.expires_at.isoformat() if saved.expires_at else expiration.isoformat(),
        }

    def get_consents_by_titular(self, titular_id: str) -> dict[str, Any]:
        """Consulta consentimentos de um titular (lendo do banco).

        Args:
            titular_id: UUID do titular.

        Returns:
            Dict com lista de consentimentos.
        """
        consents = self.repository.get_by_titular(UUID(str(titular_id)))

        return {
            "titular_id": str(titular_id),
            "consents": [c.to_dict() for c in consents],
            "total": len(consents),
        }

    def list_all(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        """Lista todos os consentimentos registrados (lendo do banco).

        Args:
            limit: Limite de resultados.
            offset: Offset para paginacao.

        Returns:
            Dict paginado com os consentimentos.
        """
        all_consents = self.repository.list_all(limit=limit, offset=offset)
        total = self.repository.count_all()
        return {
            "consents": [c.to_dict() for c in all_consents],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def revoke_consent(self, consent_id: str, reason: str) -> dict[str, Any]:
        """Revoga um consentimento (persistindo no banco).

        Args:
            consent_id: ID do consentimento.
            reason: Motivo da revogacao.

        Returns:
            Dict com confirmacao da revogacao.

        Raises:
            ValueError: Se consentimento nao encontrado.
        """
        revoked = self.repository.revoke(UUID(str(consent_id)), reason)
        if revoked is None:
            raise ValueError(f"Consentimento nao encontrado: {consent_id}")

        logger.info("Consentimento revogado (persistido): %s", consent_id)

        return {
            "consent_id": str(revoked.id),
            "status": revoked.status.value if revoked.status else "revoked",
            "reason": reason,
            "revoked_at": revoked.revoked_at.isoformat() if revoked.revoked_at else None,
        }

    def list_purposes(self) -> list[dict[str, str]]:
        """Lista finalidades de consentimento disponiveis.

        Returns:
            Lista de finalidades conforme Art. 7 LGPD.
        """
        return [
            {"id": "marketing", "description": "Marketing e comunicacoes"},
            {"id": "analytics", "description": "Analise de dados e metricas"},
            {"id": "personalization", "description": "Personalizacao de conteudo"},
            {"id": "service_provision", "description": "Prestacao de servicos"},
            {"id": "legal_obligation", "description": "Obrigacao legal"},
            {"id": "vital_interest", "description": "Interesse vital"},
            {"id": "public_interest", "description": "Interesse publico"},
            {"id": "legitimate_interest", "description": "Interesse legitimo"},
        ]

    def list_legal_bases(self) -> list[dict[str, str]]:
        """Lista bases legais LGPD disponiveis.

        Returns:
            Lista de bases legais conforme Art. 7 LGPD.
        """
        return [
            {"id": "consent", "description": "Consentimento do titular", "article": "Art. 7, I"},
            {"id": "contract", "description": "Execucao de contrato", "article": "Art. 7, V"},
            {"id": "legal_obligation", "description": "Obrigacao legal", "article": "Art. 7, II"},
            {"id": "vital_interest", "description": "Protecao da vida", "article": "Art. 7, VII"},
            {"id": "public_policy", "description": "Politica publica", "article": "Art. 7, III"},
            {"id": "research", "description": "Pesquisa", "article": "Art. 7, IV"},
            {"id": "legitimate_interest", "description": "Interesse legitimo", "article": "Art. 7, IX"},
            {"id": "credit_protection", "description": "Protecao ao credito", "article": "Art. 7, X"},
        ]
