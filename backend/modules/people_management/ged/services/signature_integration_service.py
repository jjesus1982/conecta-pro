"""
Servico de Assinatura Digital de Documentos.

Gerencia o fluxo de assinatura digital de documentos em kits:
solicitacao, processamento, verificacao e consultas.
"""

import hashlib
import logging
import os
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.people_management.ged.models.document_kit import GedDocumentKit
from modules.people_management.ged.models.kit_document import KitDocument

logger = logging.getLogger(__name__)

GED_STORAGE_BASE = os.environ.get("GED_STORAGE_PATH", "/opt/conecta-pro/storage/ged")


class SignatureIntegrationService:
    """Servico de gestao de assinaturas digitais de documentos."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def request_signature(
        self,
        document_id: str,
        employee_id: str,
    ) -> dict:
        """Marca um documento como pendente de assinatura por um funcionario.

        Registra que o documento precisa ser assinado pelo funcionario indicado.
        O documento permanece com is_signed=False e signed_by recebe o ID
        do funcionario que deve assinar.

        Args:
            document_id: UUID do documento.
            employee_id: UUID do funcionario que deve assinar.

        Returns:
            Dicionario com status da solicitacao.

        Raises:
            ValueError: Se documento nao encontrado ou ja assinado.
        """
        doc = await self._get_document_or_raise(document_id)

        if doc.is_signed:
            raise ValueError(f"Documento '{doc.document_name}' ja esta assinado (assinado em {doc.signed_at})")

        doc.signed_by = employee_id
        doc.notes = (doc.notes or "") + f"\n[Assinatura solicitada para {employee_id}]"
        doc.notes = doc.notes.strip()

        await self.db.flush()
        await self.db.refresh(doc)

        logger.info("Assinatura solicitada: doc=%s, funcionario=%s", document_id, employee_id)

        return {
            "document_id": str(doc.id),
            "document_name": doc.document_name,
            "signer_id": employee_id,
            "status": "pending_signature",
            "message": "Assinatura solicitada com sucesso",
        }

    async def process_signature(
        self,
        document_id: str,
        employee_id: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict:
        """Processa a assinatura digital de um documento.

        Calcula o hash SHA-256 do arquivo, registra a assinatura com
        timestamp, IP e user-agent para auditoria completa.

        Args:
            document_id: UUID do documento.
            employee_id: UUID do funcionario que esta assinando.
            ip_address: IP do signatario.
            user_agent: User-Agent do navegador.

        Returns:
            Dicionario com dados da assinatura.

        Raises:
            ValueError: Se documento nao encontrado ou ja assinado.
        """
        doc = await self._get_document_or_raise(document_id)

        if doc.is_signed:
            raise ValueError(f"Documento '{doc.document_name}' ja esta assinado")

        # Calcular hash SHA-256 do arquivo REAL. Sem arquivo (placeholder) NÃO se assina —
        # senão o hash seria fabricado e a assinatura nunca fecharia na verificação.
        signature_hash = await self._calculate_file_hash(doc.file_path)
        if not signature_hash:
            raise ValueError(
                f"Documento '{doc.document_name}' não tem arquivo anexado — não pode ser assinado."
            )

        # Registrar assinatura
        now = datetime.utcnow()
        doc.is_signed = True
        doc.signed_at = now
        doc.signed_by = employee_id
        doc.signature_hash = signature_hash

        # Registrar metadados de auditoria nas notas
        audit_note = f"\n[Assinado em {now.strftime('%d/%m/%Y %H:%M:%S')} por {employee_id}"
        if ip_address:
            audit_note += f" IP:{ip_address}"
        if user_agent:
            audit_note += f" UA:{user_agent[:100]}"
        audit_note += "]"
        doc.notes = (doc.notes or "") + audit_note
        doc.notes = doc.notes.strip()

        await self.db.flush()
        await self.db.refresh(doc)

        # Atualizar completude do kit
        await self._update_kit_signed_count(str(doc.kit_id))

        logger.info(
            "Documento %s assinado por %s (hash=%s)",
            document_id,
            employee_id,
            signature_hash[:16] + "...",
        )

        return {
            "document_id": str(doc.id),
            "document_name": doc.document_name,
            "signer_id": employee_id,
            "signed_at": now.isoformat(),
            "signature_hash": signature_hash,
            "ip_address": ip_address,
            "status": "signed",
        }

    async def get_pending_signatures(self, employee_id: str) -> list[dict]:
        """Retorna documentos pendentes de assinatura para um funcionario.

        Busca documentos onde signed_by = employee_id e is_signed = False.

        Args:
            employee_id: UUID do funcionario.

        Returns:
            Lista de dicts com documentos pendentes.
        """
        result = await self.db.execute(
            select(KitDocument)
            .where(
                KitDocument.signed_by == employee_id,
                KitDocument.is_signed.is_(False),
            )
            .order_by(KitDocument.created_at)
        )
        documents = result.scalars().all()

        pending = []
        for doc in documents:
            pending.append(
                {
                    "document_id": str(doc.id),
                    "kit_id": str(doc.kit_id),
                    "document_name": doc.document_name,
                    "document_type": doc.document_type,
                    "file_path": doc.file_path,
                    "created_at": doc.created_at.isoformat() if doc.created_at else None,
                }
            )

        logger.debug("Funcionario %s tem %d documentos pendentes de assinatura", employee_id, len(pending))
        return pending

    async def get_signed_documents(self, kit_id: str) -> list[dict]:
        """Retorna todos os documentos assinados de um kit.

        Args:
            kit_id: UUID do kit.

        Returns:
            Lista de dicts com documentos assinados.
        """
        result = await self.db.execute(
            select(KitDocument)
            .where(
                KitDocument.kit_id == kit_id,
                KitDocument.is_signed.is_(True),
            )
            .order_by(KitDocument.signed_at)
        )
        documents = result.scalars().all()

        signed = []
        for doc in documents:
            signed.append(
                {
                    "document_id": str(doc.id),
                    "document_name": doc.document_name,
                    "document_type": doc.document_type,
                    "signed_at": doc.signed_at.isoformat() if doc.signed_at else None,
                    "signed_by": str(doc.signed_by) if doc.signed_by else None,
                    "signature_hash": doc.signature_hash,
                }
            )

        return signed

    async def verify_signature(self, document_id: str) -> dict:
        """Verifica a integridade da assinatura de um documento.

        Recalcula o hash SHA-256 do arquivo e compara com o hash
        armazenado no momento da assinatura.

        Args:
            document_id: UUID do documento.

        Returns:
            Dicionario com resultado da verificacao.

        Raises:
            ValueError: Se documento nao encontrado ou nao assinado.
        """
        doc = await self._get_document_or_raise(document_id)

        if not doc.is_signed:
            raise ValueError(f"Documento '{doc.document_name}' nao esta assinado")

        if not doc.signature_hash:
            return {
                "document_id": str(doc.id),
                "document_name": doc.document_name,
                "is_valid": False,
                "reason": "Hash de assinatura nao encontrado",
                "stored_hash": None,
                "current_hash": None,
            }

        current_hash = await self._calculate_file_hash(doc.file_path)
        if current_hash is None:
            # sem arquivo físico → integridade NÃO verificável (não é "inválido" fabricado,
            # e evita crash de None[:16] no log)
            return {
                "document_id": str(doc.id),
                "document_name": doc.document_name,
                "is_valid": False,
                "reason": "Documento sem arquivo físico — integridade não verificável.",
                "signed_at": doc.signed_at.isoformat() if doc.signed_at else None,
                "signed_by": str(doc.signed_by) if doc.signed_by else None,
                "stored_hash": doc.signature_hash,
                "current_hash": None,
            }
        is_valid = current_hash == doc.signature_hash

        if not is_valid:
            logger.warning(
                "Integridade comprometida para documento %s: hash_armazenado=%s, hash_atual=%s",
                document_id,
                doc.signature_hash[:16] + "...",
                current_hash[:16] + "...",
            )

        return {
            "document_id": str(doc.id),
            "document_name": doc.document_name,
            "is_valid": is_valid,
            "signed_at": doc.signed_at.isoformat() if doc.signed_at else None,
            "signed_by": str(doc.signed_by) if doc.signed_by else None,
            "stored_hash": doc.signature_hash,
            "current_hash": current_hash,
        }

    async def bulk_check_signatures(self, kit_id: str) -> dict:
        """Verifica integridade de todas as assinaturas de um kit.

        Para cada documento assinado, recalcula o hash e verifica
        se corresponde ao armazenado. Atualiza os contadores do kit.

        Args:
            kit_id: UUID do kit.

        Returns:
            Resumo da verificacao em lote.

        Raises:
            ValueError: Se kit nao encontrado.
        """
        kit_result = await self.db.execute(select(GedDocumentKit).where(GedDocumentKit.id == kit_id))
        kit = kit_result.scalar_one_or_none()
        if not kit:
            raise ValueError(f"Kit nao encontrado: {kit_id}")

        result = await self.db.execute(
            select(KitDocument).where(
                KitDocument.kit_id == kit_id,
                KitDocument.is_signed.is_(True),
            )
        )
        signed_docs = result.scalars().all()

        total_checked = 0
        valid_count = 0
        invalid_count = 0
        invalid_docs = []

        for doc in signed_docs:
            total_checked += 1

            if not doc.signature_hash:
                invalid_count += 1
                invalid_docs.append(
                    {
                        "document_id": str(doc.id),
                        "document_name": doc.document_name,
                        "reason": "Hash de assinatura ausente",
                    }
                )
                continue

            current_hash = await self._calculate_file_hash(doc.file_path)
            if current_hash is None:
                # documento assinado mas SEM arquivo físico → não verificável (honesto)
                invalid_count += 1
                invalid_docs.append(
                    {
                        "document_id": str(doc.id),
                        "document_name": doc.document_name,
                        "reason": "sem arquivo físico — integridade não verificável",
                    }
                )
                continue
            if current_hash == doc.signature_hash:
                valid_count += 1
            else:
                invalid_count += 1
                invalid_docs.append(
                    {
                        "document_id": str(doc.id),
                        "document_name": doc.document_name,
                        "reason": "Hash nao corresponde ao armazenado",
                    }
                )

        # Atualizar contadores do kit
        await self._update_kit_signed_count(kit_id)

        logger.info(
            "Verificacao em lote para kit %s: %d verificados, %d validos, %d invalidos",
            kit_id,
            total_checked,
            valid_count,
            invalid_count,
        )

        return {
            "kit_id": kit_id,
            "total_signed": total_checked,
            "valid": valid_count,
            "invalid": invalid_count,
            "invalid_documents": invalid_docs,
            "all_valid": invalid_count == 0,
        }

    # --- Metodos auxiliares ---

    async def _get_document_or_raise(self, document_id: str) -> KitDocument:
        """Busca documento por ID ou levanta ValueError."""
        result = await self.db.execute(select(KitDocument).where(KitDocument.id == document_id))
        doc = result.scalar_one_or_none()
        if not doc:
            raise ValueError(f"Documento nao encontrado: {document_id}")
        return doc

    async def _calculate_file_hash(self, file_path: str | None) -> str | None:
        """Calcula hash SHA-256 do ARQUIVO REAL. Retorna None se não houver arquivo.

        NUNCA fabrica hash a partir de path+timestamp (o fallback antigo gerava um hash
        de timestamp → a assinatura "colava" num placeholder e a verificação recomputava
        outro timestamp → NUNCA fechava). Sem arquivo = None; quem chama trata honesto.

        Args:
            file_path: Caminho relativo do arquivo.

        Returns:
            Hash SHA-256 (64 hex) ou None se o arquivo não existe.
        """
        if file_path:
            full_path = os.path.join(GED_STORAGE_BASE, file_path)
            if os.path.exists(full_path):
                sha256 = hashlib.sha256()
                with open(full_path, "rb") as f:
                    for chunk in iter(lambda: f.read(8192), b""):
                        sha256.update(chunk)
                return sha256.hexdigest()
        return None

    async def _update_kit_signed_count(self, kit_id: str) -> None:
        """Atualiza contadores de documentos assinados no kit."""
        total_result = await self.db.execute(
            select(func.count()).select_from(KitDocument).where(KitDocument.kit_id == kit_id)
        )
        total_docs = total_result.scalar() or 0

        signed_result = await self.db.execute(
            select(func.count())
            .select_from(KitDocument)
            .where(KitDocument.kit_id == kit_id, KitDocument.is_signed.is_(True))
        )
        signed_docs = signed_result.scalar() or 0

        kit_result = await self.db.execute(select(GedDocumentKit).where(GedDocumentKit.id == kit_id))
        kit = kit_result.scalar_one_or_none()
        if kit:
            kit.total_documents = total_docs
            kit.documents_signed = signed_docs
            kit.recalculate_completion()
            await self.db.flush()
