"""Service da Ficha de EPI digital (NR-6 / NR-1).

Fluxo: entrega de EPI (gp_epi_deliveries) → gera FICHA (sst_fichas_epi,
snapshot imutável dos itens) → status 'pendente_assinatura' → funcionário
assina DIGITALMENTE reusando a infra do Portal (SignatureService, hash
SHA-256 em portal_digital_signatures) → status 'assinada' + hash real.

PRINCÍPIO: nunca marcar 'assinada' sem hash real; entregas sem ficha ficam
visíveis como pendência (NR-1 compliance).
"""

import logging
from datetime import UTC
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.people_management.sst.models.ficha_epi import FichaEPIModel

logger = logging.getLogger(__name__)


class FichaEPIService:
    """Gera, lista, assina e serve o PDF das fichas de EPI."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _carregar_funcionario(self, employee_id: str) -> dict[str, Any]:
        row = (
            await self.db.execute(
                text("SELECT id, nome, cpf, cargo FROM employees WHERE id = :eid"),
                {"eid": employee_id},
            )
        ).mappings().first()
        if not row:
            raise ValueError(f"Funcionário '{employee_id}' não encontrado em employees.")
        return dict(row)

    async def gerar_ficha(
        self, employee_id: str, delivery_ids: list[str] | None = None
    ) -> dict[str, Any]:
        """Gera uma ficha para as entregas SEM ficha do funcionário.

        delivery_ids: restringe a entregas específicas (delivery_id). Sem o
        parâmetro, consolida TODAS as entregas ainda sem ficha do funcionário.
        ValueError honesto quando não há entrega elegível — nada é fabricado.
        """
        func = await self._carregar_funcionario(employee_id)

        sql = (
            "SELECT delivery_id, epi_nome, epi_ca, quantidade, data_entrega, data_validade "
            "FROM gp_epi_deliveries WHERE employee_id = :eid AND ficha_epi_id IS NULL"
        )
        params: dict[str, Any] = {"eid": employee_id}
        if delivery_ids:
            sql += " AND delivery_id = ANY(:dids)"
            params["dids"] = [str(d) for d in delivery_ids]
        sql += " ORDER BY data_entrega"
        rows = (await self.db.execute(text(sql), params)).mappings().all()
        if not rows:
            raise ValueError(
                f"Nenhuma entrega de EPI sem ficha para o funcionário {func['nome']} "
                "(gp_epi_deliveries.ficha_epi_id IS NULL). Nada a gerar."
            )

        itens = [
            {
                "delivery_id": r["delivery_id"],
                "epi_nome": r["epi_nome"],
                "ca": r["epi_ca"],
                "quantidade": r["quantidade"],
                "data_entrega": str(r["data_entrega"]) if r["data_entrega"] else None,
                "data_validade": str(r["data_validade"]) if r["data_validade"] else None,
            }
            for r in rows
        ]
        ficha = FichaEPIModel(
            employee_id=employee_id,
            employee_nome=func["nome"],
            delivery_ids=[i["delivery_id"] for i in itens],
            itens=itens,
            status="pendente_assinatura",
        )
        self.db.add(ficha)
        await self.db.flush()

        await self.db.execute(
            text("UPDATE gp_epi_deliveries SET ficha_epi_id = :fid WHERE delivery_id = ANY(:dids)"),
            {"fid": str(ficha.id), "dids": [i["delivery_id"] for i in itens]},
        )
        await self.db.commit()
        logger.info("Ficha de EPI %s gerada: %s (%d itens)", ficha.id, func["nome"], len(itens))
        return ficha.to_dict()

    async def listar_fichas(
        self, status: str | None = None, employee_id: str | None = None
    ) -> list[dict[str, Any]]:
        query = select(FichaEPIModel).order_by(FichaEPIModel.created_at.desc())
        if status:
            query = query.where(FichaEPIModel.status == status)
        if employee_id:
            query = query.where(FichaEPIModel.employee_id == employee_id)
        result = await self.db.execute(query)
        return [f.to_dict() for f in result.scalars().all()]

    async def get_ficha(self, ficha_id: str) -> FichaEPIModel | None:
        result = await self.db.execute(select(FichaEPIModel).where(FichaEPIModel.id == ficha_id))
        return result.scalar_one_or_none()

    async def assinar_ficha(
        self,
        ficha_id: str,
        *,
        signer_employee_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        """Assina a ficha REUSANDO a infra de assinatura do Portal do Funcionário.

        signer_employee_id: quando informado (token do Portal), precisa bater
        com o dono da ficha — funcionário só assina a PRÓPRIA ficha.
        O hash SHA-256 vem de portal_digital_signatures — nunca fabricado.
        """
        ficha = await self.get_ficha(ficha_id)
        if not ficha:
            raise ValueError(f"Ficha de EPI '{ficha_id}' não encontrada.")
        if ficha.status == "assinada":
            raise ValueError(f"Ficha '{ficha_id}' já está assinada (hash {ficha.assinatura_hash}).")
        if signer_employee_id and str(signer_employee_id) != str(ficha.employee_id):
            raise PermissionError(
                "Assinatura negada: a ficha pertence a outro funcionário."
            )

        # Infra EXISTENTE do Portal (hash SHA-256 + rastreabilidade IP/UA)
        from modules.people_management.employee_portal.services.signature_service import (
            SignatureService,
        )

        signature_service = SignatureService(self.db)
        resultado = await signature_service.sign_document(
            document_id=str(ficha.id),
            document_type="ficha_epi",
            employee_id=UUID(str(ficha.employee_id)),
            ip_address=ip_address,
            user_agent=user_agent,
        )

        signed_at = resultado["signed_at"]
        if signed_at.tzinfo is None:  # timestamptz exige tz-aware no asyncpg
            signed_at = signed_at.replace(tzinfo=UTC)
        ficha.status = "assinada"
        ficha.assinatura_hash = resultado["signature_hash"]
        ficha.assinado_em = signed_at
        await self.db.commit()
        logger.info("Ficha de EPI %s ASSINADA por %s (hash %s)", ficha.id, ficha.employee_nome, ficha.assinatura_hash[:16])
        return ficha.to_dict()

    async def pdf_ficha(self, ficha_id: str) -> tuple[bytes, str]:
        """Gera o PDF padrão-ouro da ficha (com bloco de autenticidade se assinada)."""
        ficha = await self.get_ficha(ficha_id)
        if not ficha:
            raise ValueError(f"Ficha de EPI '{ficha_id}' não encontrada.")
        func = await self._carregar_funcionario(str(ficha.employee_id))

        from modules.people_management.sst.services.ficha_epi_pdf import montar_ficha_epi_pdf

        pdf = montar_ficha_epi_pdf(ficha.to_dict(), func)
        nome_arquivo = f"ficha_epi_{str(ficha.id)[:8]}_{(ficha.employee_nome or 'funcionario').replace(' ', '_')}.pdf"
        return pdf, nome_arquivo
