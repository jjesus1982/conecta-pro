"""DP Payslips Controller — Gestão de contracheques pelo Departamento Pessoal.

Endpoints (prefixo /dp/payslips):
  GET    /                  — listar contracheques (filtros: employee_id, mes, ano, status)
  POST   /                  — criar contracheque manualmente
  GET    /{id}              — detalhe
  GET    /{id}/pdf          — download PDF do holerite (application/pdf)
  PATCH  /{id}/publicar     — publicar (torna visível no portal)
  PATCH  /{id}/rascunho     — reverter para rascunho
  DELETE /{id}              — soft delete
  POST   /importar-lote     — importar vários contracheques de uma vez
"""

import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dp/payslips", tags=["DP - Contracheques"])
payroll_router = APIRouter(prefix="/dp/payroll", tags=["DP - Pagamento Folha PIX"])


# ─────────────────────────── SCHEMAS ──────────────────────────────


class ItemHolerite(BaseModel):
    descricao: str
    valor: float
    tipo: str = "provento"  # provento | desconto


class PayslipCreateBody(BaseModel):
    employee_id: str
    mes: int = Field(..., ge=1, le=12)
    ano: int = Field(..., ge=2020, le=2030)
    salario_bruto: float = Field(..., ge=0)
    salario_liquido: float = Field(..., ge=0)
    proventos: list[ItemHolerite] = Field(default_factory=list)
    descontos: list[ItemHolerite] = Field(default_factory=list)
    observacoes: str | None = None


class PayslipLoteItem(PayslipCreateBody):
    pass


# ─────────────────────────── ENDPOINTS ────────────────────────────


@router.get("/")
async def listar_payslips(
    current_user: CurrentActiveUser,
    employee_id: str | None = Query(None),
    mes: int | None = Query(None, ge=1, le=12),
    ano: int | None = Query(None, ge=2020, le=2030),
    mes_referencia: str | None = Query(None, description="Filtro AAAA-MM, ex: 2026-03"),
    payslip_status: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    limit: int | None = Query(None, ge=1, le=100, description="Alias para page_size"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Lista contracheques com filtros. Acessível apenas pelo DP/admin."""
    try:
        from modules.hr.employee_portal.models.payslip import PaySlip

        # limit é alias de page_size
        effective_page_size = limit if limit is not None else page_size

        # mes_referencia=AAAA-MM extrai mes e ano
        if mes_referencia and not mes and not ano:
            try:
                _ano_str, _mes_str = mes_referencia.split("-")
                ano = int(_ano_str)
                mes = int(_mes_str)
            except (ValueError, AttributeError):
                pass

        stmt = select(PaySlip)
        if employee_id:
            stmt = stmt.where(PaySlip.employee_id == uuid.UUID(employee_id))
        if mes:
            stmt = stmt.where(PaySlip.reference_month == mes)
        if ano:
            stmt = stmt.where(PaySlip.reference_year == ano)
        if payslip_status:
            stmt = stmt.where(PaySlip.status == payslip_status)

        stmt = stmt.order_by(PaySlip.reference_year.desc(), PaySlip.reference_month.desc())
        stmt = stmt.offset((page - 1) * effective_page_size).limit(effective_page_size)

        result = await db.execute(stmt)
        payslips = result.scalars().all()

        return {
            "payslips": [_serialize_payslip(p) for p in payslips],
            "page": page,
            "page_size": effective_page_size,
            "total": len(payslips),
        }
    except Exception as exc:
        logger.warning("Erro ao listar payslips: %s", exc)
        return {"payslips": [], "page": page, "page_size": page_size, "total": 0}


@router.post("/", status_code=status.HTTP_201_CREATED)
async def criar_payslip(
    body: PayslipCreateBody, current_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)
) -> Any:
    """Cria contracheque manualmente. Status inicial: DRAFT."""
    try:
        payslip = _build_payslip(body)
        db.add(payslip)
        await db.commit()
        await db.refresh(payslip)
        return _serialize_payslip(payslip)
    except Exception as exc:
        await db.rollback()
        logger.error("Erro ao criar payslip: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao criar contracheque: {exc}",
        ) from exc


@router.get("/{payslip_id}")
async def detalhe_payslip(
    payslip_id: uuid.UUID, current_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)
) -> Any:
    """Retorna detalhe de um contracheque."""
    payslip = await _get_or_404(db, payslip_id)
    return _serialize_payslip(payslip)


@router.get("/{payslip_id}/pdf", summary="Download PDF do Holerite")
async def download_pdf_holerite(
    payslip_id: uuid.UUID,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Gera e retorna o PDF do holerite/contracheque.

    Registra o download no campo download_count do contracheque.
    """
    from modules.people_management.employee_portal.services.payslip_pdf_service import (
        gerar_pdf_holerite,
    )

    try:
        pdf_bytes = await gerar_pdf_holerite(db, payslip_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Erro ao gerar PDF holerite %s: %s", payslip_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao gerar PDF: {exc}",
        ) from exc

    # Registra download
    try:
        from sqlalchemy import select as sa_select

        from modules.hr.employee_portal.models.payslip import PaySlip

        result = await db.execute(sa_select(PaySlip).where(PaySlip.id == payslip_id))
        payslip = result.scalar_one_or_none()
        if payslip:
            payslip.record_download()
            payslip.updated_at = datetime.utcnow()
            await db.commit()
    except Exception as reg_exc:
        logger.debug("Falha ao registrar download: %s", reg_exc)

    filename = f"holerite_{payslip_id!s:.8}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
            "Cache-Control": "no-store",
        },
    )


@router.patch("/{payslip_id}/publicar")
async def publicar_payslip(
    payslip_id: uuid.UUID, current_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)
) -> Any:
    """Publica contracheque — torna visível no portal do funcionário."""
    payslip = await _get_or_404(db, payslip_id)
    try:
        from modules.hr.employee_portal.models.payslip import PaySlipStatus

        payslip.status = PaySlipStatus.PUBLISHED
        payslip.published_at = datetime.utcnow()
        payslip.updated_at = datetime.utcnow()
        await db.commit()

        # Dispara auto-notificação para o funcionário
        try:
            from modules.people_management.employee_portal.services.auto_notification_service import (
                AutoNotificationService,
            )

            await AutoNotificationService(db).notify_payslip_published(
                employee_id=str(payslip.employee_id),
                mes=payslip.reference_month,
                ano=payslip.reference_year,
            )
        except Exception as notif_err:
            logger.warning("Auto-notificação payslip falhou: %s", notif_err)

        return {"message": "Contracheque publicado com sucesso.", "payslip_id": str(payslip_id)}
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.patch("/{payslip_id}/rascunho")
async def reverter_rascunho(
    payslip_id: uuid.UUID, current_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)
) -> Any:
    """Reverte contracheque para rascunho."""
    payslip = await _get_or_404(db, payslip_id)
    try:
        from modules.hr.employee_portal.models.payslip import PaySlipStatus

        payslip.status = PaySlipStatus.DRAFT
        payslip.updated_at = datetime.utcnow()
        await db.commit()
        return {"message": "Contracheque revertido para rascunho.", "payslip_id": str(payslip_id)}
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.delete("/{payslip_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deletar_payslip(
    payslip_id: uuid.UUID, current_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)
) -> None:
    """Soft delete de contracheque (marca como CANCELLED — o model não tem is_active)."""
    payslip = await _get_or_404(db, payslip_id)
    try:
        from modules.hr.employee_portal.models.payslip import PaySlipStatus

        payslip.status = PaySlipStatus.CANCELLED.value
        payslip.updated_at = datetime.utcnow()
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post("/importar-lote", status_code=status.HTTP_201_CREATED)
async def importar_lote(
    items: list[PayslipLoteItem], current_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)
) -> Any:
    """Importa múltiplos contracheques de uma vez. Máximo 100 por lote."""
    if len(items) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Máximo de 100 contracheques por lote.",
        )
    criados = 0
    erros = []
    for item in items:
        try:
            p = _build_payslip(item)
            db.add(p)
            criados += 1
        except Exception as exc:
            erros.append({"employee_id": item.employee_id, "erro": str(exc)})

    await db.commit()
    return {"criados": criados, "erros": erros}


# ─────────────────────────── HELPERS ──────────────────────────────

# Sentinela usado pelas folhas manuais (mesmo valor das folhas já existentes no
# banco); manual não está atrelado a um condomínio específico.
_DEFAULT_CONDOMINIO_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _build_payslip(body: "PayslipCreateBody") -> Any:
    """Constrói um PaySlip a partir do body, mapeando para as colunas REAIS de hr_payslips.

    O model NÃO possui competence_month/competence_year/notes/is_active/items nem
    setter para gross_salary. Usamos os campos reais: reference_year/reference_month/
    reference_period, base_salary/total_earnings/total_deductions/net_salary e
    earnings/deductions JSONB. Preenche colunas NOT NULL (payslip_code, condominio_id,
    reference_period).
    """
    from modules.hr.employee_portal.models.payslip import PaySlip, PaySlipStatus, PaySlipType

    emp_uuid = uuid.UUID(body.employee_id)
    reference_period = f"{body.ano:04d}-{body.mes:02d}"
    total_deductions = float(sum(d.valor for d in body.descontos))
    total_earnings = float(body.salario_bruto)

    # earnings/deductions como JSONB no formato esperado ({code, description, value}).
    earnings_json = [
        {"code": None, "description": p.descricao, "value": float(p.valor)} for p in body.proventos
    ]
    deductions_json = [
        {"code": None, "description": d.descricao, "value": float(d.valor)} for d in body.descontos
    ]

    payslip = PaySlip(
        id=uuid.uuid4(),
        condominio_id=_DEFAULT_CONDOMINIO_ID,
        employee_id=emp_uuid,
        payslip_code=f"MANUAL-{reference_period}-{str(emp_uuid)[:8]}",
        payslip_type=PaySlipType.MONTHLY.value,
        status=PaySlipStatus.DRAFT.value,
        reference_year=body.ano,
        reference_month=body.mes,
        reference_period=reference_period,
        base_salary=total_earnings,
        total_earnings=total_earnings,
        total_deductions=total_deductions,
        net_salary=float(body.salario_liquido),
        earnings=earnings_json,
        deductions=deductions_json,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    return payslip


async def _get_or_404(db: AsyncSession, payslip_id: uuid.UUID):
    try:
        from modules.hr.employee_portal.models.payslip import PaySlip

        result = await db.execute(select(PaySlip).where(PaySlip.id == payslip_id))
        payslip = result.scalar_one_or_none()
    except Exception:
        payslip = None

    if not payslip:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contracheque não encontrado.")
    return payslip


# Códigos de LINHA DE TOTAL nas rubricas do Domínio/Portte (não são itens individuais).
_TOTAL_ROW_CODES = {"0099", "99", "9999", "0999"}


def _is_total_row(rubrica: dict) -> bool:
    """True se a rubrica é uma linha de TOTAL (não itemizável).

    Evita a dupla contagem de 'Proventos Totais' (0099) e 'Total Descontos' (9999)
    no detalhamento. Casa por código normalizado e, como defesa, por descrição.
    """
    code = str(rubrica.get("code") or "").strip().lstrip("0") or "0"
    code_raw = str(rubrica.get("code") or "").strip()
    if code_raw in _TOTAL_ROW_CODES or code in {c.lstrip("0") or "0" for c in _TOTAL_ROW_CODES}:
        return True
    desc = str(rubrica.get("description") or rubrica.get("descricao") or "").upper()
    return "PROVENTOS TOTAIS" in desc or "TOTAL DESCONTOS" in desc or desc.strip() in {
        "TOTAIS",
        "TOTAL",
    }


def _serialize_payslip(p: Any) -> dict:
    # Mapeia campos do model hr_payslips (reference_month/year, total_earnings, earnings JSONB)
    earnings_raw = p.earnings if p.earnings else []
    deductions_raw = p.deductions if p.deductions else []
    items = []
    if isinstance(earnings_raw, list):
        items += [
            {
                "descricao": e.get("description", e.get("descricao", "")),
                "valor": float(e.get("value", e.get("valor", 0))),
                "tipo": "provento",
            }
            for e in earnings_raw
            if isinstance(e, dict) and not _is_total_row(e)
        ]
    if isinstance(deductions_raw, list):
        items += [
            {
                "descricao": d.get("description", d.get("descricao", "")),
                "valor": float(d.get("value", d.get("valor", 0))),
                "tipo": "desconto",
            }
            for d in deductions_raw
            if isinstance(d, dict) and not _is_total_row(d)
        ]
    _bruto = float(p.total_earnings or 0)
    _liquido = float(p.net_salary or 0)
    _descontos = float(p.total_deductions or 0)
    _inss = float(p.inss_value or 0)
    _fgts = float(p.fgts_value or 0)
    _irrf = float(p.irrf_value or 0)
    _mes_ref = getattr(p, "reference_period", None) or f"{p.reference_year:04d}-{p.reference_month:02d}"
    return {
        "id": str(p.id),
        "employee_id": str(p.employee_id),
        "mes": p.reference_month,
        "ano": p.reference_year,
        "mes_referencia": _mes_ref,
        # campos PT-BR (compatibilidade)
        "salario_bruto": _bruto,
        "salario_liquido": _liquido,
        "descontos": _descontos,
        # campos EN (exigidos pelo prompt)
        "gross_salary": _bruto,
        "net_salary": _liquido,
        "total_deductions": _descontos,
        "inss": _inss,
        "fgts": _fgts,
        "irrf": _irrf,
        "status": str(p.status) if p.status else "draft",
        "tipo": str(p.payslip_type) if p.payslip_type else "monthly",
        "observacoes": getattr(p, "notes", None),
        "items": items,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "published_at": p.published_at.isoformat() if p.published_at else None,
    }


# ─────────────────────── UPLOAD PDF FOLHA ─────────────────────────


@router.post(
    "/folha/upload",
    summary="Upload PDF Extrato Mensal Domínio/Portte — importa rubricas",
    description=(
        "Recebe PDF do Extrato Mensal Portte Contabil/Domínio Sistemas. "
        "Extrai rubricas por funcionário e popula hr_payslip_items. "
        "NÃO modifica totais de hr_payslips (fonte: Domínio importado pelo T2). "
        "Preenche bases fiscais (INSS/FGTS/IRRF) somente se ainda NULL."
    ),
)
async def upload_folha_pdf(
    current_user: CurrentActiveUser,
    mes: int = Query(..., ge=1, le=12, description="Mês de competência"),
    ano: int = Query(..., ge=2020, le=2030, description="Ano de competência"),
    arquivo: UploadFile = File(..., description="PDF Extrato Mensal Domínio"),
    db: AsyncSession = Depends(get_db),
):
    """
    Fluxo:
    1. Salva PDF em /uploads/folhas/AAAA-MM/
    2. Extrai funcionários e rubricas via FolhaPDFParser
    3. Para cada funcionário, localiza hr_payslip por CPF + competência
    4. Insere rubricas em hr_payslip_items (substitui anteriores)
    5. Preenche bases fiscais se NULL (não conflita com T2)
    """
    import os

    import psycopg2

    from modules.people_management.services.folha_pdf_parser import (
        FolhaPDFParser,
        importar_rubricas,
    )

    if not arquivo.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Arquivo deve ser PDF")

    pasta = f"/app/uploads/folhas/{ano:04d}-{mes:02d}"
    os.makedirs(pasta, exist_ok=True)
    pdf_path = f"{pasta}/extrato_{ano:04d}_{mes:02d}.pdf"
    with open(pdf_path, "wb") as f:
        f.write(await arquivo.read())

    parser = FolhaPDFParser(pdf_path)
    funcs = parser.parse()
    if not funcs:
        raise HTTPException(422, "Não foi possível extrair dados do PDF")

    validacao = parser.validar_totais()
    # DATABASE_URL usa +asyncpg — converter para psycopg2
    raw_url = os.getenv("DATABASE_URL", "").replace("+asyncpg", "")
    conn = psycopg2.connect(raw_url)
    try:
        resultado = importar_rubricas(parser, mes, ano, conn)
    finally:
        conn.close()

    return {
        "arquivo": pdf_path,
        "funcionarios": len(funcs),
        "validacao": validacao,
        "rubricas": resultado,
    }


# ─────────────────── FOLHA PIX — PAGAMENTO VIA BANCO INTER ────────────────────


@router.get(
    "/folha/pagar-via-pix/{mes}/{ano}/preview",
    summary="Preview pagamento folha via PIX — sem pagar",
)
async def preview_pagamento_folha(
    mes: int,
    ano: int,
    _user: CurrentActiveUser = None,
):
    """
    Simula pagamento da folha sem executar nenhum PIX.
    Mostra funcionários, valores e quem não tem chave PIX cadastrada.
    """
    from modules.people_management.services.folha_payment_service import (
        processar_folha_completa,
    )

    return await processar_folha_completa(mes, ano, apenas_preview=True)


@router.post(
    "/folha/pagar-via-pix/{mes}/{ano}",
    summary="Pagar folha completa via PIX Inter — 51 funcionários",
)
async def pagar_folha_via_pix(
    mes: int,
    ano: int,
    _user: CurrentActiveUser = None,
):
    """
    Processa pagamento de salários via PIX para todos os funcionários
    com chave PIX cadastrada e holerite publicado no período.
    ATENÇÃO: envia PIX reais pelo Banco Inter (mTLS OAuth2).
    """
    from modules.people_management.services.folha_payment_service import (
        processar_folha_completa,
    )

    return await processar_folha_completa(mes, ano, apenas_preview=False)


@router.get(
    "/folha/pagar-via-pix/{mes}/{ano}/status",
    summary="Status dos pagamentos PIX da folha",
)
async def status_pagamento_folha(
    mes: int,
    ano: int,
    _user: CurrentActiveUser = None,
):
    """Retorna status detalhado dos pagamentos PIX da folha do período."""
    from modules.people_management.services.folha_payment_service import (
        status_pagamentos_folha,
    )

    return status_pagamentos_folha(mes, ano)


class PayBatchRequest(BaseModel):
    mes_referencia: str = Field(
        ...,
        description="Mês de referência no formato AAAA-MM (ex: 2026-03)",
        pattern=r"^\d{4}-\d{2}$",
    )
    modo: str = Field(
        "simulacao",
        description="simulacao (preview sem tocar banco) | execucao (registra como pendente_pagamento — SEM PIX real)",
    )


@payroll_router.post(
    "/pay-batch",
    summary="Agendamento lote folha — pendente_pagamento",
    description=(
        "Monta payload PIX por funcionário e registra como pendente_pagamento "
        "para aprovação manual. NUNCA envia PIX real. "
        "modo=simulacao: preview sem alterar banco. "
        "modo=execucao: insere em payroll_payments com status=pendente_pagamento."
    ),
)
async def pagar_folha_lote(
    body: PayBatchRequest,
    _user: CurrentActiveUser = None,  # noqa: B008
):
    """
    POST /api/v1/people-management/dp/payroll/pay-batch
    Body: {"mes_referencia": "2026-03", "modo": "simulacao|execucao"}

    IMPORTANTE: NÃO executa PIX real.
    - simulacao: preview sem alterar banco de dados
    - execucao: registra como 'pendente_pagamento' para aprovação manual
    """
    try:
        ano_str, mes_str = body.mes_referencia.split("-")
        mes = int(mes_str)
        ano = int(ano_str)
    except (ValueError, AttributeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"mes_referencia inválido: '{body.mes_referencia}'. Use formato AAAA-MM.",
        ) from exc

    if not (1 <= mes <= 12):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Mês inválido: {mes}. Deve ser entre 1 e 12.",
        )

    if body.modo.lower() == "execucao":
        # Registra como pendente_pagamento — NÃO envia PIX real
        from modules.people_management.services.folha_payment_service import (
            registrar_lote_pendente,
        )

        resultado = registrar_lote_pendente(mes, ano)
    else:
        # Simulação — apenas preview sem tocar banco
        from modules.people_management.services.folha_payment_service import (
            processar_folha_completa,
        )

        resultado = await processar_folha_completa(mes, ano, apenas_preview=True)

    return {**resultado, "mes_referencia": body.mes_referencia, "modo": body.modo}


@router.put(
    "/folha/funcionario/{employee_id}/pix-key",
    summary="Cadastrar/atualizar chave PIX do funcionário",
)
async def cadastrar_pix_key(
    employee_id: str,
    pix_key: str,
    pix_key_type: str = "CPF",
    db: AsyncSession = Depends(get_db),
    _user: CurrentActiveUser = None,
):
    """
    Cadastra chave PIX do funcionário para pagamento de salário.
    tipo: CPF | TELEFONE | EMAIL | ALEATORIA
    """
    from sqlalchemy import text

    result = await db.execute(
        text(
            """
            UPDATE employees SET
                pix_key = :pix_key,
                pix_key_type = :pix_key_type,
                updated_at = NOW()
            WHERE id = :emp_id
            RETURNING id::text, nome, pix_key, pix_key_type
            """
        ),
        {"pix_key": pix_key, "pix_key_type": pix_key_type, "emp_id": employee_id},
    )
    row = result.fetchone()
    await db.commit()
    if not row:
        raise HTTPException(status_code=404, detail="Funcionário não encontrado")
    return {
        "id": row[0],
        "nome": row[1],
        "pix_key": row[2],
        "pix_key_type": row[3],
    }
