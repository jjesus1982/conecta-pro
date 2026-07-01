"""Servico da Certificacao Humana — CRUD + o hash que a torna inforjavel no tempo."""

import hashlib
import json
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select, text
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

    async def gerar_da_folha(self, competencia: str) -> dict:
        """Gera certificacoes PENDENTES da folha de uma competencia, a partir do golden set Dominio.

        Modo 1 do loop DP/Folha: para cada holerite importado (hr_payslips) da competencia,
        cria 1 certificacao pra DP/Contabil revisar e assinar. Idempotente (nao duplica se ja
        existe pra aquele holerite). calculado=esperado=valor Dominio (M1 le Dominio); quando o
        item -0.5 (tabelas 2026) entrar, calculado vira recalculo independente e divergencia
        passa a ser real.
        `competencia`: 'YYYY-MM'.
        """
        ano, mes = competencia.split("-")
        rows = (
            await self.db.execute(
                text(
                    """
                    SELECT p.id, p.employee_id, p.net_salary, p.inss_value, p.irrf_value,
                           p.fgts_value, p.base_salary, p.total_earnings, p.total_deductions,
                           e.cliente_id, e.nome
                    FROM hr_payslips p
                    LEFT JOIN employees e ON e.id = p.employee_id
                    WHERE p.reference_year = :ano AND p.reference_month = :mes
                      AND p.net_salary IS NOT NULL
                    """
                ),
                {"ano": int(ano), "mes": int(mes)},
            )
        ).fetchall()

        criadas, ja_existiam = 0, 0
        for r in rows:
            ref_id = str(r[0])
            existe = (
                await self.db.execute(
                    text(
                        "SELECT 1 FROM hr_certifications WHERE referencia_id = :r AND tipo_calculo = 'folha_mensal' LIMIT 1"
                    ),
                    {"r": ref_id},
                )
            ).fetchone()
            if existe:
                ja_existiam += 1
                continue
            net = float(r[2]) if r[2] is not None else None
            payload = {
                "inss": float(r[3]) if r[3] is not None else None,
                "irrf": float(r[4]) if r[4] is not None else None,
                "fgts": float(r[5]) if r[5] is not None else None,
                "base_salary": float(r[6]) if r[6] is not None else None,
                "total_earnings": float(r[7]) if r[7] is not None else None,
                "total_deductions": float(r[8]) if r[8] is not None else None,
                "fonte": "dominio_sistemas",
                "funcionario": r[10],
            }
            cert = HRCertification(
                id=str(uuid4()),
                tipo_calculo="folha_mensal",
                referencia_id=ref_id,
                referencia_tipo="hr_payslip",
                competencia=competencia,
                employee_id=str(r[1]) if r[1] else None,
                cliente_id=str(r[9]) if r[9] else None,
                calculado_valor=net,  # M1 le Dominio -> calculado = valor Dominio
                esperado_valor=net,  # golden set Dominio
                divergencia=False,  # sem recalculo independente ainda (item -0.5)
                payload=payload,
                hash_conteudo=compute_content_hash("folha_mensal", ref_id, competencia, net, payload),
                status=CertificationStatus.PENDENTE.value,
            )
            self.db.add(cert)
            criadas += 1
        await self.db.commit()
        return {"competencia": competencia, "criadas": criadas, "ja_existiam": ja_existiam, "total_holerites": len(rows)}

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
