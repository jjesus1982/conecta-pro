"""
Servico de Coleta de Documentos — integra com DP, Fiscal e Operacoes.

Responsavel por coletar documentos de outros modulos, adicionar manualmente,
remover e substituir documentos dentro de um kit documental.
"""

import logging
import os
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.people_management.ged.models.document_kit import GedDocumentKit, KitStatus
from modules.people_management.ged.models.kit_document import DocumentType, KitDocument, SourceModule

logger = logging.getLogger(__name__)

# Diretorio base para storage de documentos GED
GED_STORAGE_BASE = os.environ.get("GED_STORAGE_PATH", "/opt/conecta-pro/storage/ged")


class DocumentCollectorService:
    """Servico de coleta e gerenciamento de documentos em kits."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def collect_from_dp(
        self,
        kit_id: str,
        employee_id: str,
        reference_month: date,
    ) -> list[dict]:
        """Coleta todos os documentos do modulo DP para um funcionario.

        Busca contracheque, folha de ponto e comprovantes de beneficios
        do Departamento Pessoal para o mes de referencia.

        Args:
            kit_id: UUID do kit documental.
            employee_id: UUID do funcionario.
            reference_month: Mes de referencia.

        Returns:
            Lista de dicts com documentos coletados.
        """
        ref_str = reference_month.strftime("%Y-%m")
        collected = []

        dp_documents = [
            (
                DocumentType.CONTRACHEQUE,
                f"Contracheque {reference_month.strftime('%m/%Y')}",
                f"documents/dp/contracheques/{ref_str}/{employee_id}.pdf",
            ),
            (
                DocumentType.FOLHA_PONTO,
                f"Folha de Ponto {reference_month.strftime('%m/%Y')}",
                f"documents/dp/folhas_ponto/{ref_str}/{employee_id}.pdf",
            ),
            (
                DocumentType.COMPROVANTE_VT,
                f"Comprovante VT {reference_month.strftime('%m/%Y')}",
                f"documents/dp/beneficios/{ref_str}/vt/{employee_id}.pdf",
            ),
            (
                DocumentType.COMPROVANTE_VA,
                f"Comprovante VA {reference_month.strftime('%m/%Y')}",
                f"documents/dp/beneficios/{ref_str}/va/{employee_id}.pdf",
            ),
        ]

        for doc_type, doc_name, file_path in dp_documents:
            # Verificar duplicata
            existing = await self.db.execute(
                select(KitDocument).where(
                    KitDocument.kit_id == kit_id,
                    KitDocument.employee_id == employee_id,
                    KitDocument.document_type == doc_type,
                )
            )
            if existing.scalar_one_or_none():
                logger.debug("Documento %s ja existe para emp %s no kit %s", doc_type, employee_id, kit_id)
                continue

            doc = KitDocument(
                kit_id=kit_id,
                employee_id=employee_id,
                document_type=doc_type,
                document_name=doc_name,
                file_path=file_path,
                mime_type="application/pdf",
                source_module=SourceModule.DP,
                auto_generated=True,
                is_signed=False,
            )
            self.db.add(doc)
            collected.append(
                {
                    "document_type": doc_type,
                    "document_name": doc_name,
                    "file_path": file_path,
                }
            )

        if collected:
            await self.db.flush()
            logger.info("Coletados %d docs DP para emp %s no kit %s", len(collected), employee_id, kit_id)

        return collected

    async def collect_from_fiscal(self, kit_id: str) -> list[dict]:
        """Coleta certidoes negativas e documentos fiscais.

        Busca CNDs atualizadas, guias de recolhimento e documentos
        fiscais obrigatorios para inclusao no kit.

        Args:
            kit_id: UUID do kit documental.

        Returns:
            Lista de dicts com documentos coletados.
        """
        collected = []

        fiscal_documents = [
            (DocumentType.CND_FEDERAL, "CND Federal (PGFN/RFB)", "documents/fiscal/certidoes/cnd_federal.pdf"),
            (DocumentType.CND_ESTADUAL, "CND Estadual (SEFAZ)", "documents/fiscal/certidoes/cnd_estadual.pdf"),
            (DocumentType.CND_MUNICIPAL, "CND Municipal (ISS)", "documents/fiscal/certidoes/cnd_municipal.pdf"),
            (DocumentType.CRF_FGTS, "CRF FGTS (CEF)", "documents/fiscal/certidoes/crf_fgts.pdf"),
            (
                DocumentType.CNDT_TRABALHISTA,
                "CNDT Trabalhista (TST)",
                "documents/fiscal/certidoes/cndt_trabalhista.pdf",
            ),
            (DocumentType.GFIP_SEFIP, "GFIP/SEFIP", "documents/fiscal/guias/gfip_sefip.pdf"),
            (DocumentType.GRF_FGTS, "GRF FGTS", "documents/fiscal/guias/grf_fgts.pdf"),
            (DocumentType.GPS_INSS, "GPS INSS", "documents/fiscal/guias/gps_inss.pdf"),
        ]

        for doc_type, doc_name, file_path in fiscal_documents:
            existing = await self.db.execute(
                select(KitDocument).where(
                    KitDocument.kit_id == kit_id,
                    KitDocument.document_type == doc_type,
                    KitDocument.employee_id.is_(None),
                )
            )
            if existing.scalar_one_or_none():
                continue

            doc = KitDocument(
                kit_id=kit_id,
                employee_id=None,
                document_type=doc_type,
                document_name=doc_name,
                file_path=file_path,
                mime_type="application/pdf",
                source_module=SourceModule.FISCAL,
                auto_generated=True,
                is_signed=True,  # Certidoes/guias ja vem validadas
            )
            self.db.add(doc)
            collected.append(
                {
                    "document_type": doc_type,
                    "document_name": doc_name,
                    "file_path": file_path,
                }
            )

        if collected:
            await self.db.flush()
            logger.info("Coletados %d docs fiscais para kit %s", len(collected), kit_id)

        return collected

    async def collect_from_operations(
        self,
        kit_id: str,
        employee_id: str,
        reference_month: date,
    ) -> list[dict]:
        """Coleta escalas e documentos operacionais.

        Busca escalas mensais e outros documentos do modulo de operacoes
        para o funcionario no mes de referencia.

        Args:
            kit_id: UUID do kit documental.
            employee_id: UUID do funcionario.
            reference_month: Mes de referencia.

        Returns:
            Lista de dicts com documentos coletados.
        """
        ref_str = reference_month.strftime("%Y-%m")
        collected = []

        # ESCALA APOSENTADA — decisão do Jordan, 09/09/2026: "a escala não vai no kit, pode excluir
        # inclusive este documento. A gente não precisa e nem envia documento referente a escala de
        # trabalho de funcionários, somente a folha de ponto basta."
        #
        # Este bloco criava a vaga com um `file_path` INVENTADO
        # ("documents/operacoes/escalas/<mês>/<id>.pdf") que nunca existiu em disco — 369 slots de
        # escala nos kits, e o caminho apontando para lugar nenhum. Nem o documento era pedido, nem
        # o arquivo existia.
        _ = ref_str  # mantido: o resto do método usa a competência formatada

        if collected:
            await self.db.flush()
            logger.info("Coletados %d docs operacionais para emp %s no kit %s", len(collected), employee_id, kit_id)

        return collected

    async def add_manual_document(
        self,
        kit_id: str,
        file_path: str,
        document_type: str,
        document_name: str,
        employee_id: str | None = None,
        notes: str | None = None,
        file_size_bytes: int | None = None,
        mime_type: str = "application/pdf",
    ) -> dict:
        """Adiciona um documento manualmente a um kit.

        Usado quando o operador faz upload de um documento que nao
        foi coletado automaticamente (advertencias, atestados, etc.).

        Args:
            kit_id: UUID do kit documental.
            file_path: Caminho do arquivo no storage.
            document_type: Tipo do documento (DocumentType).
            document_name: Nome de exibicao do documento.
            employee_id: UUID do funcionario (opcional para docs da empresa).
            notes: Observacoes.
            file_size_bytes: Tamanho do arquivo em bytes.
            mime_type: Tipo MIME do arquivo.

        Returns:
            Dicionario com dados do documento criado.

        Raises:
            ValueError: Se kit nao encontrado ou status nao permite adicao.
        """
        kit = await self._get_kit_or_raise(kit_id)

        if kit.status not in [KitStatus.EM_MONTAGEM, KitStatus.COMPLETO]:
            raise ValueError(
                f"Nao e possivel adicionar documentos a kit com status '{kit.status}'. "
                "Somente kits em montagem ou completos aceitam novos documentos."
            )

        # Detectar tamanho do arquivo se nao informado
        if file_size_bytes is None and file_path:
            full_path = os.path.join(GED_STORAGE_BASE, file_path)
            if os.path.exists(full_path):
                file_size_bytes = os.path.getsize(full_path)

        doc = KitDocument(
            kit_id=kit_id,
            employee_id=employee_id,
            document_type=document_type,
            document_name=document_name,
            file_path=file_path,
            file_size_bytes=file_size_bytes,
            mime_type=mime_type,
            source_module=SourceModule.MANUAL,
            auto_generated=False,
            is_signed=False,
            notes=notes,
        )
        self.db.add(doc)
        await self.db.flush()
        await self.db.refresh(doc)

        # Atualizar contadores do kit
        await self._update_kit_counters(kit_id)

        logger.info("Documento manual adicionado ao kit %s: %s (%s)", kit_id, document_name, document_type)

        return {
            "id": str(doc.id),
            "kit_id": kit_id,
            "document_type": doc.document_type,
            "document_name": doc.document_name,
            "file_path": doc.file_path,
            "source_module": doc.source_module,
        }

    async def remove_document(self, document_id: str) -> dict:
        """Remove um documento de um kit.

        Args:
            document_id: UUID do documento.

        Returns:
            Confirmacao da remocao.

        Raises:
            ValueError: Se documento nao encontrado ou kit nao permite remocao.
        """
        doc = await self._get_document_or_raise(document_id)
        kit = await self._get_kit_or_raise(str(doc.kit_id))

        if kit.status not in [KitStatus.EM_MONTAGEM, KitStatus.COMPLETO]:
            raise ValueError(f"Nao e possivel remover documentos de kit com status '{kit.status}'.")

        kit_id = str(doc.kit_id)
        doc_name = doc.document_name

        await self.db.delete(doc)
        await self.db.flush()

        # Atualizar contadores do kit
        await self._update_kit_counters(kit_id)

        logger.info("Documento '%s' removido do kit %s", doc_name, kit_id)
        return {
            "message": f"Documento '{doc_name}' removido com sucesso",
            "id": document_id,
            "kit_id": kit_id,
        }

    async def replace_document(
        self,
        document_id: str,
        new_file_path: str,
        new_file_size: int | None = None,
        new_mime_type: str | None = None,
    ) -> dict:
        """Substitui o arquivo de um documento existente.

        Mantém os metadados (tipo, nome, funcionário) mas atualiza
        o arquivo e reseta a assinatura se existia.

        Args:
            document_id: UUID do documento.
            new_file_path: Novo caminho do arquivo.
            new_file_size: Tamanho do novo arquivo em bytes.
            new_mime_type: Novo tipo MIME (se diferente).

        Returns:
            Dicionario com dados atualizados.

        Raises:
            ValueError: Se documento nao encontrado ou kit nao permite edicao.
        """
        doc = await self._get_document_or_raise(document_id)
        kit = await self._get_kit_or_raise(str(doc.kit_id))

        if kit.status not in [KitStatus.EM_MONTAGEM, KitStatus.COMPLETO]:
            raise ValueError(f"Nao e possivel substituir documentos em kit com status '{kit.status}'.")

        old_path = doc.file_path

        doc.file_path = new_file_path
        if new_file_size is not None:
            doc.file_size_bytes = new_file_size
        if new_mime_type:
            doc.mime_type = new_mime_type

        # Resetar assinatura ao substituir arquivo
        if doc.is_signed:
            doc.is_signed = False
            doc.signed_at = None
            doc.signed_by = None
            doc.signature_hash = None
            logger.info("Assinatura resetada para documento %s apos substituicao", document_id)

        await self.db.flush()
        await self.db.refresh(doc)

        # Atualizar contadores
        await self._update_kit_counters(str(doc.kit_id))

        logger.info(
            "Documento %s substituido: %s -> %s",
            document_id,
            old_path,
            new_file_path,
        )

        return {
            "id": str(doc.id),
            "document_name": doc.document_name,
            "old_file_path": old_path,
            "new_file_path": doc.file_path,
            "is_signed": doc.is_signed,
        }

    # --- Metodos auxiliares ---

    async def _get_kit_or_raise(self, kit_id: str) -> GedDocumentKit:
        """Busca kit por ID ou levanta ValueError."""
        result = await self.db.execute(select(GedDocumentKit).where(GedDocumentKit.id == kit_id))
        kit = result.scalar_one_or_none()
        if not kit:
            raise ValueError(f"Kit documental nao encontrado: {kit_id}")
        return kit

    async def _get_document_or_raise(self, document_id: str) -> KitDocument:
        """Busca documento por ID ou levanta ValueError."""
        result = await self.db.execute(select(KitDocument).where(KitDocument.id == document_id))
        doc = result.scalar_one_or_none()
        if not doc:
            raise ValueError(f"Documento nao encontrado: {document_id}")
        return doc

    async def _update_kit_counters(self, kit_id: str) -> None:
        """Recalcula contadores de documentos do kit."""
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
