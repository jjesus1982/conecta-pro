"""
Serviço de geração de PDF de Holerite/Contracheque (padrão-ouro Conecta Mais).

Reutiliza `montar_holerite_pdf` da folha oficial para que o holerite gerado por
/dp/payslips e /my-payslips saia EXATAMENTE no mesmo layout do holerite do DP.

Estratégia (espelha modules/hr/employee_portal/services/payslip_service.generate_pdf):
  1) Padrão-ouro: recalcula pelo motor da folha (`calcular_folha_colaborador`),
     idêntico ao holerite oficial, montando `fdad` da tabela employees.
  2) Fallback: monta o dict `holerite` a partir dos dados publicados no próprio
     contracheque (earnings/deductions JSONB, totais, bases, FGTS).
Retorna os BYTES do PDF (não path).
"""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def gerar_pdf_holerite(db: AsyncSession, payslip_id: UUID) -> bytes:
    """Gera o PDF do holerite/contracheque no PADRÃO-OURO Conecta Mais.

    Args:
        db: Sessão assíncrona do banco.
        payslip_id: UUID do contracheque.

    Returns:
        Bytes do PDF gerado.

    Raises:
        ValueError: Se contracheque não encontrado.
    """
    from modules.hr.employee_portal.models.payslip import PaySlip
    from modules.people_management.folha.services.holerite_pdf import montar_holerite_pdf

    # 1. Buscar holerite
    result = await db.execute(select(PaySlip).where(PaySlip.id == payslip_id))
    payslip = result.scalar_one_or_none()
    if not payslip:
        raise ValueError(f"Contracheque {payslip_id} não encontrado")

    emp_id = str(payslip.employee_id)
    mes = int(payslip.reference_month)
    ano = int(payslip.reference_year)

    data_pag = None
    if getattr(payslip, "payment_date", None):
        try:
            data_pag = payslip.payment_date.strftime("%d/%m/%Y")
        except Exception:
            data_pag = str(payslip.payment_date)

    holerite = None
    fdad: dict = {}

    # 1) Padrão-ouro: recalcula pelo motor da folha (idêntico ao holerite do DP)
    try:
        from sqlalchemy import text as _text

        from core.database.session import get_sync_db_dependency
        from modules.people_management.folha.services.calculo_service import (
            calcular_folha_colaborador,
        )

        sdb = next(get_sync_db_dependency())
        try:
            res = calcular_folha_colaborador(sdb, emp_id, mes, ano)
            if "error" not in res:
                holerite = res
                row = sdb.execute(
                    _text("SELECT cpf, pis, matricula, data_admissao FROM employees WHERE CAST(id AS TEXT) = :e"),
                    {"e": emp_id},
                ).first()
                if row:
                    adm = row[3]
                    fdad = {
                        "cpf": row[0],
                        "pis": row[1] or "—",
                        "matricula": row[2] or "—",
                        "data_admissao": adm.strftime("%d/%m/%Y") if hasattr(adm, "strftime") else (adm or "—"),
                        "posto": res.get("posto") or res.get("condominio") or "—",
                    }
        finally:
            sdb.close()
    except Exception:
        logger.exception(
            "Falha ao recalcular contracheque %s pelo motor; usando dados publicados",
            payslip_id,
        )
        holerite = None

    # 2) Fallback: monta a partir dos dados publicados no contracheque (JSONB)
    if holerite is None:

        def _map(items):
            mapped = []
            for it in items or []:
                if isinstance(it, dict):
                    mapped.append(
                        {
                            "descricao": it.get("description") or it.get("descricao") or "—",
                            "referencia": it.get("reference") or it.get("referencia") or "",
                            "valor": float(it.get("value") or it.get("valor") or 0),
                        }
                    )
            return mapped

        holerite = {
            "employee_nome": getattr(payslip, "employee_name", "") or "—",
            "cargo": getattr(payslip, "employee_cargo", "") or "—",
            "escala": getattr(payslip, "employee_escala", "") or "—",
            "mes": mes,
            "ano": ano,
            "proventos": _map(getattr(payslip, "earnings", [])),
            "descontos": _map(getattr(payslip, "deductions", [])),
            "total_proventos": float(payslip.total_earnings or 0),
            "total_descontos": float(payslip.total_deductions or 0),
            "liquido": float(payslip.net_salary or 0),
            "base_inss": float(payslip.inss_base or 0),
            "base_fgts": float(payslip.fgts_base or 0),
            "base_irrf": float(payslip.irrf_base or 0),
            "fgts_empresa": float(payslip.fgts_value or 0),
        }
        fdad = {
            "matricula": getattr(payslip, "employee_matricula", "") or "—",
            "posto": getattr(payslip, "employee_departamento", "") or "—",
        }

    if data_pag:
        holerite["data_pagamento"] = data_pag

    return montar_holerite_pdf(holerite, fdad)
