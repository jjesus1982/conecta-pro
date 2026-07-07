"""
Signature Service — Assinatura digital de documentos.

Gera, verifica e invalida assinaturas digitais usando SHA-256.
"""

import hashlib
import logging
import os
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.people_management.employee_portal.models.digital_signature import (
    DocumentType,
    PortalDigitalSignature,
)

logger = logging.getLogger(__name__)


# Salt/secret para geracao de hash — OBRIGATORIO em producao
def _get_signature_secret() -> str:
    secret = os.getenv("PORTAL_SIGNATURE_SECRET")
    if not secret:
        raise RuntimeError(
            "Variavel de ambiente PORTAL_SIGNATURE_SECRET nao definida. Defina em .env antes de iniciar o servidor."
        )
    return secret


class SignatureService:
    """Servico de assinatura digital de documentos.

    Gera hashes SHA-256 unicos para cada assinatura combinando
    document_id + employee_id + timestamp + secret.

    Attributes:
        db: Sessao async do banco de dados.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Inicializa o servico com sessao de banco.

        Args:
            db: Sessao async do SQLAlchemy.
        """
        self.db = db

    async def sign_document(
        self,
        document_id: str,
        document_type: str,
        employee_id: UUID,
        ip_address: str | None = None,
        user_agent: str | None = None,
        device_fingerprint: str | None = None,
        geolocation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Assina um documento digitalmente.

        Gera hash SHA-256 de document_id + employee_id + timestamp + secret
        e persiste no banco.

        Args:
            document_id: ID do documento a assinar.
            document_type: Tipo do documento.
            employee_id: UUID do funcionario signatario.
            ip_address: IP no momento da assinatura.
            user_agent: User agent do navegador.
            device_fingerprint: Fingerprint do dispositivo.
            geolocation: Dados de geolocalizacao.

        Returns:
            Dict com signature_hash e signed_at.

        Raises:
            ValueError: Se o tipo de documento for invalido ou ja assinado.
        """
        # Validar tipo de documento
        try:
            doc_type_enum = DocumentType(document_type)
        except ValueError:
            raise ValueError(
                f"Tipo de documento invalido: {document_type}. Valores aceitos: {[t.value for t in DocumentType]}"
            )

        # Verificar se ja existe assinatura valida
        existing = await self._get_existing_signature(document_id, employee_id)
        if existing and existing.is_valid:
            raise ValueError(f"Documento {document_id} ja possui assinatura valida do funcionario {employee_id}.")

        # Gerar hash da assinatura
        signed_at = datetime.utcnow()
        signature_hash = self._generate_hash(
            document_id=document_id,
            employee_id=employee_id,
            timestamp=signed_at,
        )

        # Persistir assinatura
        signature = PortalDigitalSignature(
            document_id=document_id,
            document_type=doc_type_enum,
            employee_id=employee_id,
            signature_hash=signature_hash,
            ip_address=ip_address,
            user_agent=user_agent,
            device_fingerprint=device_fingerprint,
            geolocation=geolocation,
            signed_at=signed_at,
            is_valid=True,
        )

        try:
            self.db.add(signature)
            await self.db.commit()
            await self.db.refresh(signature)

            logger.info(
                "Documento %s assinado por employee_id=%s hash=%s",
                document_id,
                employee_id,
                signature_hash[:16],
            )

            return {
                "signature_hash": signature_hash,
                "signed_at": signed_at,
            }

        except Exception as e:
            await self.db.rollback()
            logger.error("Erro ao salvar assinatura: %s", e, exc_info=True)
            raise

    async def verify_signature(
        self,
        signature_hash: str,
    ) -> dict[str, Any]:
        """Verifica a validade de uma assinatura digital.

        Args:
            signature_hash: Hash da assinatura a verificar.

        Returns:
            Dict com is_valid e dados do documento/signatario.
        """
        query = select(PortalDigitalSignature).where(PortalDigitalSignature.signature_hash == signature_hash)
        result = await self.db.execute(query)
        signature = result.scalar_one_or_none()

        if not signature:
            return {
                "is_valid": False,
                "document_id": None,
                "document_type": None,
                "employee_id": None,
                "signed_at": None,
                "invalidated_at": None,
                "invalidation_reason": "Assinatura nao encontrada.",
            }

        return {
            "is_valid": signature.is_valid,
            "document_id": signature.document_id,
            "document_type": signature.document_type.value if signature.document_type else None,
            "employee_id": str(signature.employee_id),
            "signed_at": signature.signed_at,
            "invalidated_at": signature.invalidated_at,
            "invalidation_reason": signature.invalidation_reason,
        }

    async def invalidate_signature(
        self,
        signature_hash: str,
        reason: str,
    ) -> bool:
        """Invalida uma assinatura digital existente.

        Args:
            signature_hash: Hash da assinatura a invalidar.
            reason: Motivo da invalidacao.

        Returns:
            True se invalidada com sucesso, False se nao encontrada.
        """
        query = select(PortalDigitalSignature).where(PortalDigitalSignature.signature_hash == signature_hash)
        result = await self.db.execute(query)
        signature = result.scalar_one_or_none()

        if not signature:
            return False

        signature.is_valid = False
        signature.invalidated_at = datetime.utcnow()
        signature.invalidation_reason = reason

        try:
            await self.db.commit()
            logger.info(
                "Assinatura invalidada: hash=%s motivo=%s",
                signature_hash[:16],
                reason,
            )
            return True
        except Exception as e:
            await self.db.rollback()
            logger.error("Erro ao invalidar assinatura: %s", e)
            return False

    def _generate_hash(
        self,
        document_id: str,
        employee_id: UUID,
        timestamp: datetime,
    ) -> str:
        """Gera hash SHA-256 da assinatura.

        Combina document_id + employee_id + timestamp ISO + secret
        para gerar um hash unico e verificavel.

        Args:
            document_id: ID do documento.
            employee_id: UUID do funcionario.
            timestamp: Data/hora da assinatura.

        Returns:
            String hex do hash SHA-256.
        """
        payload = f"{document_id}:{employee_id}:{timestamp.isoformat()}:{_get_signature_secret()}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    async def _get_existing_signature(
        self,
        document_id: str,
        employee_id: UUID,
    ) -> PortalDigitalSignature | None:
        """Busca assinatura existente para documento + funcionario.

        Args:
            document_id: ID do documento.
            employee_id: UUID do funcionario.

        Returns:
            PortalDigitalSignature se encontrada, None caso contrario.
        """
        query = select(PortalDigitalSignature).where(
            PortalDigitalSignature.document_id == document_id,
            PortalDigitalSignature.employee_id == employee_id,
            PortalDigitalSignature.is_valid.is_(True),
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
