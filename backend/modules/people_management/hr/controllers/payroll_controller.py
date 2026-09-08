"""
Controller de Folha de Pagamento — Departamento Pessoal.

Re-exporta endpoints de folha do módulo HR e adiciona endpoints
para cálculo individual, fechamento mensal e contracheque PDF.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payroll", tags=["DP - Folha de Pagamento"])

# O re-export do router de `hr/payroll_integration` saiu daqui em 13/08/2026, pelo mesmo
# motivo do de ponto: este router já tem `prefix="/payroll"` e o sub-router também, então as
# 43 rotas nasciam em `/hr/payroll/payroll/...`. Agora o sub-router é montado direto no
# aggregator, onde o `/hr` sozinho produz `/hr/payroll/...`.
#
# 💰 É caminho de folha, então medi antes em vez de confiar na simetria com o ponto:
#   · 15 dias de access log, 99.841 chamadas de API: **0** ao caminho duplicado;
#   · colisão com as 8 rotas próprias deste controller (`/summary`, `/close`, `/benefits`,
#     `/rubricas`, `/employee/{id}/calculate`, `/employee/{id}/payslip-pdf`): ZERO;
#   · as rotas seguem existindo — nenhuma some, só perdem um `/payroll` do caminho.
# `payroll_events` e `payroll_exports` estão zeradas e `payroll_periods` tem 2 linhas; a
# folha viva é `hr_payslips` (822), servida por outro caminho.


@router.get(
    "/summary",
    summary="Resumo da folha salarial",
    description=(
        "Retorna totais consolidados da folha para a competência: "
        "proventos, descontos, INSS, IRRF e FGTS. "
        "Usa hr_payslips quando disponível, com fallback em employees.salario_base."
    ),
)
async def get_payroll_summary(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    mes: int = Query(None, ge=1, le=12, description="Mês (1-12). Padrão: mês atual"),
    ano: int = Query(None, ge=2020, le=2030, description="Ano. Padrão: ano atual"),
) -> Any:
    """Resumo consolidado da folha de pagamento."""
    from datetime import datetime

    from sqlalchemy import text as _text

    # [Veracidade] Sem mes/ano explicitos, usar a ULTIMA competencia REAL de hr_payslips
    # (mes corrente pode nao ter folha importada ainda -> caia no fallback estimado com
    # salario_base rotulado como liquido, o que gerava numero falso nos cards).
    if not mes or not ano:
        try:
            _last = (
                await db.execute(
                    _text(
                        "SELECT reference_month, reference_year FROM hr_payslips "
                        "ORDER BY reference_year DESC, reference_month DESC LIMIT 1"
                    )
                )
            ).first()
        except Exception:
            await db.rollback()
            _last = None
        if _last:
            mes = mes or int(_last[0])
            ano = ano or int(_last[1])
    mes = mes or datetime.now().month
    ano = ano or datetime.now().year

    # Tentar hr_payslips primeiro
    try:
        result = await db.execute(
            _text(
                # [Veracidade] colunas reais de hr_payslips (eram total_proventos/salario_liquido/inss/
                # competencia inexistentes -> caia no except -> fallback com 0s escondendo os 51 holerites reais)
                "SELECT "
                "COUNT(DISTINCT employee_id) as funcionarios, "
                "COALESCE(SUM(total_earnings), 0) as total_proventos, "
                "COALESCE(SUM(total_deductions), 0) as total_descontos, "
                "COALESCE(SUM(net_salary), 0) as total_liquido, "
                "COALESCE(SUM(inss_value), 0) as total_inss, "
                "COALESCE(SUM(irrf_value), 0) as total_irrf, "
                "COALESCE(SUM(fgts_value), 0) as total_fgts "
                "FROM hr_payslips "
                "WHERE reference_month = :mes AND reference_year = :ano"
            ),
            {"mes": mes, "ano": ano},
        )
        row = result.mappings().first()
        if row and float(row.get("total_proventos") or 0) > 0:
            return {
                "competencia": f"{mes:02d}/{ano}",
                "funcionarios": int(row.get("funcionarios") or 0),
                "total_proventos": float(row.get("total_proventos") or 0),
                "total_bruto": float(row.get("total_proventos") or 0),
                "total_descontos": float(row.get("total_descontos") or 0),
                "total_liquido": float(row.get("total_liquido") or 0),
                "total_inss": float(row.get("total_inss") or 0),
                "total_irrf": float(row.get("total_irrf") or 0),
                "total_fgts": float(row.get("total_fgts") or 0),
                "fonte": "hr_payslips",
            }
    except Exception:
        await db.rollback()

    # Fallback honesto: competencia sem folha importada -> NAO estimar liquido a partir
    # de salario_base (dado incompleto, NULLs, e nao e "folha"). Retorna zeros marcados.
    result2 = await db.execute(_text("SELECT COUNT(*) FROM employees WHERE status = 'ativo'"))
    _ativos = int(result2.scalar() or 0)
    return {
        "competencia": f"{mes:02d}/{ano}",
        "funcionarios": _ativos,
        "total_proventos": 0.0,
        "total_bruto": 0.0,
        "total_descontos": 0.0,
        "total_liquido": 0.0,
        "total_inss": 0.0,
        "total_irrf": 0.0,
        "total_fgts": 0.0,
        "fonte": "sem_folha_importada",
        "aviso": "Sem holerites em hr_payslips para esta competência — aguardando dado real.",
    }


@router.get(
    "/employee/{employee_id}/payslip-pdf",
    summary="Gerar Contracheque PDF",
    description="Gera e retorna contracheque em formato PDF para download.",
)
async def generate_payslip_pdf(
    employee_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    month: int = Query(..., ge=1, le=12, description="Mes de referencia"),
    year: int = Query(..., ge=2020, le=2030, description="Ano de referencia"),
) -> StreamingResponse:
    """Gera contracheque em PDF para um funcionario e competencia.

    Redireciona para o holerite OFICIAL (folha/holerite/{id}/{mes}/{ano}/pdf, padrão-ouro,
    engine CCT 2026). O PDF próprio desta rota nascia da engine legada, com valor errado
    (ver `calculate_employee_payroll`)."""
    from fastapi.responses import RedirectResponse

    return RedirectResponse(
        url=f"/api/v1/people-management/folha/holerite/{employee_id}/{month}/{year}/pdf", status_code=307
    )


@router.get(
    "/benefits",
    summary="Listar Benefícios/Rubricas",
    description="Lista rubricas e benefícios vinculados a funcionários com filtro por status.",
)
async def list_all_benefits(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    employee_id: str | None = Query(None, description="Filtrar por funcionário"),
    status: str = Query("active", description="Status: active, inactive"),
) -> Any:
    """Lista rubricas/benefícios cadastrados por funcionário."""
    from sqlalchemy import text

    sql = "SELECT b.*, e.nome as employee_name FROM employee_benefits b JOIN employees e ON b.employee_id = e.id WHERE b.status = :status"
    params: dict = {"status": status}
    if employee_id:
        sql += " AND b.employee_id = :emp_id"
        params["emp_id"] = employee_id
    sql += " ORDER BY e.nome, b.type"

    result = await db.execute(text(sql), params)
    rows = result.fetchall()

    return {
        "items": [
            {
                "id": str(r.id),
                "employee_id": str(r.employee_id),
                "employee_name": r.employee_name,
                "type": r.type,
                "provider": r.provider,
                "plan_name": r.plan_name,
                "employee_contribution": float(r.employee_contribution or 0),
                "company_contribution": float(r.company_contribution or 0),
                "start_date": r.start_date.isoformat() if r.start_date else None,
                "end_date": r.end_date.isoformat() if r.end_date else None,
                "status": r.status,
                "notes": r.notes,
            }
            for r in rows
        ],
        "total": len(rows),
    }


@router.post(
    "/benefits",
    summary="Cadastrar Benefício",
    status_code=201,
    description="Lista rubricas e benefícios vinculados a funcionários com filtro por status.",
)
async def create_benefit(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    employee_id: str = Query(..., description="ID do funcionário"),
    benefit_type: str = Query(
        ...,
        alias="type",
        description="Tipo: Emprestimo Consignado, Pensao Alimenticia, Vale Refeicao, Plano Saude, etc",
    ),
    employee_contribution: float = Query(0, description="Valor desconto do funcionário"),
    company_contribution: float = Query(0, description="Valor da empresa"),
    provider: str = Query("", description="Fornecedor/banco"),
    plan_name: str = Query("", description="Nome do plano/descrição"),
    notes: str = Query("", description="Observações"),
) -> Any:
    """Cadastra nova rubrica/benefício para um funcionário."""
    from sqlalchemy import text

    result = await db.execute(
        text(
            "INSERT INTO employee_benefits (employee_id, type, provider, plan_name, employee_contribution, company_contribution, notes, status) "
            "VALUES (:emp_id, :type, :provider, :plan, :emp_val, :co_val, :notes, 'active') RETURNING id"
        ),
        {
            "emp_id": employee_id,
            "type": benefit_type,
            "provider": provider or None,
            "plan": plan_name or None,
            "emp_val": employee_contribution,
            "co_val": company_contribution,
            "notes": notes or None,
        },
    )
    new_id = result.scalar()
    await db.commit()
    return {"id": str(new_id), "message": f"Rubrica '{benefit_type}' cadastrada para funcionário {employee_id}"}


@router.delete(
    "/benefits/{benefit_id}",
    summary="Desativar Benefício",
    description="Lista rubricas e benefícios vinculados a funcionários com filtro por status.",
)
async def delete_benefit(
    benefit_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Desativa uma rubrica/benefício."""
    from sqlalchemy import text

    await db.execute(
        text("UPDATE employee_benefits SET status = 'inactive', updated_at = now() WHERE id = :id"),
        {"id": benefit_id},
    )
    await db.commit()
    return {"message": "Rubrica desativada"}


@router.get(
    "/rubricas",
    summary="Listar Rubricas de Referência",
    description="Lista rubricas disponíveis na tabela de referência para cálculo de folha.",
)
async def list_rubricas(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Lista rubricas disponíveis (tabela de referência)."""
    from sqlalchemy import text

    result = await db.execute(text("SELECT * FROM rubricas_folha WHERE ativo ORDER BY codigo"))
    rows = result.fetchall()
    return {
        "items": [
            {
                "id": r.id,
                "codigo": r.codigo,
                "descricao": r.descricao,
                "tipo": r.tipo,
                "valor_fixo": float(r.valor_fixo) if r.valor_fixo else None,
                "percentual": float(r.percentual) if r.percentual else None,
                "incide_inss": r.incide_inss,
                "incide_irrf": r.incide_irrf,
                "incide_fgts": r.incide_fgts,
            }
            for r in rows
        ],
        "total": len(rows),
    }


