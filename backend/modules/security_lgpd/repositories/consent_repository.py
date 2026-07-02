"""
Repository de Consentimento LGPD.
"""

import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from modules.security_lgpd.models.consent import Consent, ConsentStatus

logger = logging.getLogger(__name__)


class ConsentRepository:
    """Repository para operacoes de persistencia de consentimentos.

    Encapsula o acesso ao banco de dados para a entidade Consent.
    """

    def __init__(self, db: Session):
        """Inicializa o repository.

        Args:
            db: Sessao do banco de dados.
        """
        self.db = db

    def create(self, consent: Consent) -> Consent:
        """Cria um novo consentimento.

        Args:
            consent: Instancia do consentimento.

        Returns:
            Consentimento criado.
        """
        self.db.add(consent)
        self.db.commit()
        self.db.refresh(consent)
        logger.info("Consentimento criado: %s", consent.id)
        return consent

    def get_by_id(self, consent_id: UUID) -> Consent | None:
        """Busca consentimento por ID.

        Args:
            consent_id: UUID do consentimento.

        Returns:
            Consentimento ou None.
        """
        return self.db.query(Consent).filter(Consent.id == consent_id).first()

    def get_by_titular(
        self,
        titular_id: UUID,
        status: ConsentStatus | None = None,
    ) -> list[Consent]:
        """Busca consentimentos de um titular.

        Args:
            titular_id: UUID do titular.
            status: Filtro por status (opcional).

        Returns:
            Lista de consentimentos.
        """
        query = self.db.query(Consent).filter(Consent.titular_id == titular_id)

        if status:
            query = query.filter(Consent.status == status)

        return query.order_by(Consent.created_at.desc()).all()

    def list_all(self, limit: int = 100, offset: int = 0) -> list[Consent]:
        """Lista todos os consentimentos paginados.

        Args:
            limit: Limite de resultados.
            offset: Offset para paginacao.

        Returns:
            Lista de consentimentos.
        """
        return (
            self.db.query(Consent)
            .order_by(Consent.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def count_all(self) -> int:
        """Conta o total de consentimentos.

        Returns:
            Total de consentimentos.
        """
        return self.db.query(Consent).count()

    def update(self, consent: Consent) -> Consent:
        """Atualiza um consentimento.

        Args:
            consent: Instancia do consentimento.

        Returns:
            Consentimento atualizado.
        """
        consent.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(consent)
        return consent

    def revoke(self, consent_id: UUID, reason: str) -> Consent | None:
        """Revoga um consentimento.

        Args:
            consent_id: UUID do consentimento.
            reason: Motivo da revogacao.

        Returns:
            Consentimento revogado ou None.
        """
        consent = self.get_by_id(consent_id)
        if consent:
            consent.status = ConsentStatus.REVOKED
            consent.revoked_at = datetime.utcnow()
            consent.revocation_reason = reason
            return self.update(consent)
        return None

    def list_expired(self, limit: int = 100) -> list[Consent]:
        """Lista consentimentos expirados.

        Args:
            limit: Limite de resultados.

        Returns:
            Lista de consentimentos expirados.
        """
        now = datetime.utcnow()
        return (
            self.db.query(Consent)
            .filter(Consent.status == ConsentStatus.ACTIVE)
            .filter(Consent.expires_at < now)
            .limit(limit)
            .all()
        )

    def count_by_status(self) -> dict:
        """Conta consentimentos por status.

        Returns:
            Dict com contagens por status.
        """
        from sqlalchemy import func

        result = self.db.query(Consent.status, func.count(Consent.id)).group_by(Consent.status).all()
        return {status.value: count for status, count in result}
