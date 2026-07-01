"""Servico da Certificacao Humana — CRUD + o hash que a torna inforjavel no tempo."""

import hashlib
import json
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.certification import CertificationStatus, HRCertification


def compute_content_hash(
    tipo_calculo: str,
    referencia_id: str | None,
    competencia: str | None,
    calculado_valor: float | None,
    payload: dict | None,
) -> str:
    """sha256 do conteudo certificavel, canonico (sort_keys) — muda o calculo, muda o hash.

    E o coracao anti-teatro: certifica-se um CONTEUDO. Se depois o calculo muda, o hash
    diverge e a certificacao expira (volta a pendente). A assinatura vale pro que foi assinado.
    """
    canonical = json.dumps(
        {
            "tipo": tipo_calculo,
            "ref": referencia_id or "",
            "comp": competencia or "",
            "calc": f"{calculado_valor:.2f}" if calculado_valor is not None else "",
            "payload": payload or {},
        },
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class CertificationService:
    """Fila de certificacao + assinatura rastreavel."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_pending(self, data: dict) -> HRCertification:
        """Cria uma certificacao PENDENTE com o hash do conteudo."""
        h = compute_content_hash(
            data["tipo_calculo"],
            data.get("referencia_id"),
            data.get("competencia"),
            data.get("calculado_valor"),
            data.get("payload"),
        )
        cert = HRCertification(
            id=str(uuid4()),
            tipo_calculo=data["tipo_calculo"],
            referencia_id=data.get("referencia_id"),
            referencia_tipo=data.get("referencia_tipo"),
            competencia=data.get("competencia"),
            employee_id=data.get("employee_id"),
            cliente_id=data.get("cliente_id"),
            calculado_valor=data.get("calculado_valor"),
            esperado_valor=data.get("esperado_valor"),
            divergencia=bool(data.get("divergencia", False)),
            divergencia_desc=data.get("divergencia_desc"),
            payload=data.get("payload"),
            hash_conteudo=h,
            status=CertificationStatus.PENDENTE.value,
        )
        self.db.add(cert)
        await self.db.commit()
        await self.db.refresh(cert)
        return cert

    async def list(self, status: str | None = None, limit: int = 100) -> list[HRCertification]:
        stmt = select(HRCertification).order_by(HRCertification.created_at.desc()).limit(limit)
        if status:
            stmt = stmt.where(HRCertification.status == status)
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def get(self, cert_id: str) -> HRCertification | None:
        res = await self.db.execute(select(HRCertification).where(HRCertification.id == cert_id))
        return res.scalar_one_or_none()

    async def certify(self, cert_id: str, user_id: str, observacao: str | None = None) -> HRCertification | None:
        """Assina. O trabalho humano de conferir vira fato: {quem, quando, hash}."""
        cert = await self.get(cert_id)
        if not cert:
            return None
        cert.status = CertificationStatus.CERTIFICADO.value
        cert.certificado_por = user_id
        cert.certificado_em = datetime.utcnow()
        if observacao:
            cert.observacao = observacao
        await self.db.commit()
        await self.db.refresh(cert)
        return cert

    async def reject(self, cert_id: str, user_id: str, observacao: str) -> HRCertification | None:
        cert = await self.get(cert_id)
        if not cert:
            return None
        cert.status = CertificationStatus.REJEITADO.value
        cert.certificado_por = user_id
        cert.certificado_em = datetime.utcnow()
        cert.observacao = observacao
        await self.db.commit()
        await self.db.refresh(cert)
        return cert

    @staticmethod
    def is_valid(cert: HRCertification) -> bool:
        """A certificacao ainda vale? (certificada E o hash bate com o conteudo atual).

        Recomputa o hash do conteudo gravado e compara com o hash assinado. Se o calculo
        foi alterado depois da assinatura, os hashes divergem -> expirou (nao vale mais).
        """
        if cert.status != CertificationStatus.CERTIFICADO.value:
            return False
        atual = compute_content_hash(
            cert.tipo_calculo,
            cert.referencia_id,
            cert.competencia,
            float(cert.calculado_valor) if cert.calculado_valor is not None else None,
            cert.payload,
        )
        return atual == cert.hash_conteudo
