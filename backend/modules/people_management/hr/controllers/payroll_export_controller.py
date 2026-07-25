"""
Controller de Exportação de Folha — Domínio Sistemas + PDF Contracheque.

Endpoints para exportar folha no formato Domínio (TOTVS) e gerar
contracheques em PDF.
"""

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.people_management.hr.publishers import publish_holerite_gerado
from modules.people_management.hr.services.payroll_export_service import PayrollExportService
from modules.people_management.hr.services.payroll_service import PayrollService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payroll-export", tags=["DP - Exportação Folha"])


@router.get(
    "/dominio/{competencia}",
    summary="Exportar Folha para Domínio",
    description="Exporta folha de pagamento no formato texto para importação no Domínio Sistemas (TOTVS).",
)
async def exportar_dominio(
    competencia: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Exporta folha no formato texto para Domínio Sistemas (TOTVS).

    Args:
        competencia: Mês/ano no formato YYYY-MM (ex: 2026-03).
    """
    try:
        parts = competencia.split("-")
        year, month = int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        raise HTTPException(400, "Formato de competência inválido. Use YYYY-MM.")

    # EXPORT é LEITURA: jamais fechar a folha como efeito colateral de um GET (antes
    # chamava close_payroll aqui!). Usa o MESMO motor da tela de folha (calcular_folha_batch)
    # p/ o arquivo Domínio bater 1:1 com o que o DP vê — e status canônico 'ativo'
    # (o filtro antigo status == "Ativo" maiúsculo devolvia 0 funcionários).
    from sqlalchemy import text as _sqltext
    from starlette.concurrency import run_in_threadpool

    from core.database.session import SyncSessionLocal
    from modules.people_management.folha.services.calculo_service import calcular_folha_batch

    def _calc_batch() -> dict:
        _db = SyncSessionLocal()
        try:
            return calcular_folha_batch(_db, month, year)
        finally:
            _db.close()

    batch = await run_in_threadpool(_calc_batch)
    holerites = batch.get("holerites") or []

    # cpf/matrícula por funcionário (o motor devolve employee_id)
    rows = (
        await db.execute(_sqltext("SELECT CAST(id AS TEXT) AS id, cpf, matricula FROM employees WHERE status='ativo'"))
    ).mappings().all()
    _info = {r["id"]: r for r in rows}

    folha_data = []
    for h in holerites:
        emp_id = str(h.get("employee_id") or "")
        info = _info.get(emp_id, {})
        folha_data.append(
            {
                **h,
                # mapeia p/ as chaves do layout Domínio (export_dominio)
                "employee_name": h.get("employee_nome") or h.get("nome") or "",
                "salario_liquido": h.get("liquido", 0),
                "fgts_8_pct": h.get("fgts_empresa", 0),
                "cpf": info.get("cpf") or "",
                "matricula": info.get("matricula") or emp_id[:6],
            }
        )

    comp_fmt = f"{month:02d}/{year}"
    conteudo = PayrollExportService.export_dominio(folha_data, comp_fmt)

    return Response(
        content=conteudo,
        media_type="text/plain; charset=latin-1",
        headers={"Content-Disposition": f'attachment; filename="folha_{competencia}.txt"'},
    )


@router.get(
    "/contracheque/{employee_id}/{competencia}",
    summary="Gerar Contracheque PDF",
    description="Gera PDF do holerite de um funcionário para a competência e arquiva no GED.",
)
async def gerar_contracheque_pdf(
    employee_id: str,
    competencia: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Gera PDF do contracheque (holerite) de um funcionário.

    Args:
        employee_id: ID do funcionário.
        competencia: Mês/ano no formato YYYY-MM.
    """
    try:
        parts = competencia.split("-")
        year, month = int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        raise HTTPException(400, "Formato de competência inválido. Use YYYY-MM.")

    payroll_svc = PayrollService(db)
    try:
        calc = await payroll_svc.calculate_employee_payroll(employee_id, month, year)
    except ValueError as e:
        raise HTTPException(404, str(e))

    pdf_bytes = PayrollExportService.gerar_contracheque_pdf(calc)

    # Hook GED: arquivar contracheque automaticamente
    await _arquivar_contracheque_ged(
        db,
        employee_id,
        calc.get("employee_name", ""),
        competencia,
        year,
        month,
        pdf_bytes,
    )

    nome = calc.get("employee_name", "funcionario").replace(" ", "_")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="contracheque_{nome}_{competencia}.pdf"'},
    )


@router.post(
    "/contracheques-batch/{competencia}",
    summary="Gerar Contracheques em Lote",
    status_code=201,
    description="Gera holerites PDF em lote para todos os funcionários ativos e arquiva no GED.",
)
async def gerar_contracheques_batch(
    competencia: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Gera contracheques PDF em lote para todos os funcionários ativos.

    Retorna resumo da geração (quantidade, erros).
    """
    try:
        parts = competencia.split("-")
        year, month = int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        raise HTTPException(400, "Formato de competência inválido. Use YYYY-MM.")

    payroll_svc = PayrollService(db)
    from sqlalchemy import func, select

    from modules.operacional.models.employee import Employee

    # status é case-inconsistente no banco (dado real = 'ativo' minúsculo); comparar case-insensitive
    # senão a batch casa 0 funcionários e gera 0 contracheques (bug que mantinha esta rota órfã).
    result = await db.execute(select(Employee).where(func.lower(Employee.status) == "ativo"))
    employees = result.scalars().all()

    folha_data = []
    for emp in employees:
        try:
            calc = await payroll_svc.calculate_employee_payroll(str(emp.id), month, year)
            folha_data.append(calc)
        except Exception as exc:
            # defense-in-depth: se um cálculo falhar, faz rollback para não envenenar a transação
            # dos próximos (a causa-raiz do cascata — query solides_absences — foi corrigida no
            # payroll_service; isto evita regressão futura se outra query opcional falhar).
            logger.warning("Erro ao calcular folha do funcionário %s: %s", emp.id, exc)
            try:
                await db.rollback()
            except Exception:
                pass

    pdfs = PayrollExportService.gerar_contracheques_batch(folha_data)

    # Hook GED: arquivar todos os contracheques em batch
    arquivados = 0
    for emp_data in folha_data:
        eid = emp_data.get("employee_id", "")
        ename = emp_data.get("employee_name", "")
        pdf = pdfs.get(eid)
        if pdf:
            await _arquivar_contracheque_ged(
                db,
                eid,
                ename,
                competencia,
                year,
                month,
                pdf,
            )
            arquivados += 1

    # Publicar evento por funcionário com holerite gerado
    for emp_data in folha_data:
        asyncio.create_task(
            publish_holerite_gerado(
                funcionario_id=str(emp_data.get("employee_id", "")),
                funcionario_nome=str(emp_data.get("employee_name", "")),
                competencia=competencia,
            )
        )

    return {
        "competencia": competencia,
        "total_funcionarios": len(employees),
        "contracheques_gerados": len(pdfs),
        "arquivados_ged": arquivados,
        "status": "completed",
    }


async def _arquivar_contracheque_ged(
    db: AsyncSession,
    employee_id: str,
    employee_name: str,
    competencia: str,
    ano: int,
    mes: int,
    pdf_bytes: bytes,
) -> None:
    """Registra contracheque no GED e persiste o PDF fisicamente."""
    try:
        from pathlib import Path

        from sqlalchemy import text as sql_text

        # Persistir arquivo fisicamente
        upload_dir = Path(f"/app/uploads/ged/contracheques/{ano}/{mes:02d}")
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = upload_dir / f"{employee_id}.pdf"
        file_path.write_bytes(pdf_bytes)

        rel_path = f"ged/contracheques/{ano}/{mes:02d}/{employee_id}.pdf"
        await db.execute(
            sql_text(
                "INSERT INTO ged_contracheques "
                "(employee_id, employee_name, competencia, ano, mes, path, tamanho_bytes) "
                "VALUES (:eid, :ename, :comp, :ano, :mes, :path, :tam) "
                "ON CONFLICT (employee_id, competencia) DO UPDATE SET "
                "path = EXCLUDED.path, tamanho_bytes = EXCLUDED.tamanho_bytes, "
                "created_at = NOW()"
            ),
            {
                "eid": employee_id,
                "ename": employee_name,
                "comp": competencia,
                "ano": ano,
                "mes": mes,
                "path": rel_path,
                "tam": len(pdf_bytes),
            },
        )
        await db.commit()
        logger.info(
            "Contracheque arquivado no GED: %s %s (%d bytes em %s)",
            employee_name,
            competencia,
            len(pdf_bytes),
            rel_path,
        )
    except Exception as exc:
        logger.warning("Falha ao arquivar contracheque no GED (nao-bloqueante): %s", exc)
