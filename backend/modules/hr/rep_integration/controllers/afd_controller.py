"""Controller para gestão de arquivos AFD."""

import logging
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_db
from modules.hr.rep_integration.repositories import AFDRecordRepository
from modules.hr.rep_integration.schemas import (
    AFDExportRequest,
    AFDExportResponse,
    AFDImportRequest,
    AFDImportResponse,
    AFDRecordFilter,
    AFDRecordList,
    AFDRecordResponse,
    AFDValidationResult,
)
from modules.hr.rep_integration.services import AFDService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/afd", tags=["AFD Records"])


@router.get("/records", response_model=AFDRecordList)
async def list_afd_records(
    device_id: UUID | None = None,
    condominio_id: UUID | None = None,
    record_type: str | None = None,
    pis_number: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    is_exported: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> AFDRecordList:
    """Lista registros AFD."""
    repo = AFDRecordRepository(db)

    filters = AFDRecordFilter(
        device_id=device_id,
        condominio_id=condominio_id,
        record_type=record_type,
        pis_number=pis_number,
        date_from=date_from,
        date_to=date_to,
        is_exported=is_exported,
    )

    records, total = await repo.list_records(filters, page, page_size)

    return AFDRecordList(
        items=records,
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size,
    )


@router.get("/records/{record_id}", response_model=AFDRecordResponse)
async def get_afd_record(
    record_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> AFDRecordResponse:
    """Obtém registro AFD por ID."""
    repo = AFDRecordRepository(db)
    record = await repo.get_by_id(record_id)

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Registro não encontrado",
        )

    return record


@router.post("/export", response_model=AFDExportResponse)
async def export_afd(
    request: AFDExportRequest,
    company_cnpj: str = Query(..., min_length=14, max_length=14),
    company_cei: str = Query(..., min_length=12, max_length=12),
    company_name: str = Query(..., min_length=1, max_length=150),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> AFDExportResponse:
    """Exporta arquivo AFD para um período."""
    afd_service = AFDService(db)

    try:
        result = await afd_service.export_afd(
            request=request,
            company_cnpj=company_cnpj,
            company_cei=company_cei,
            company_name=company_name,
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/export/{device_id}/download")
async def download_afd(
    device_id: UUID,
    start_date: date,
    end_date: date,
    company_cnpj: str = Query(..., min_length=14, max_length=14),
    company_cei: str = Query(..., min_length=12, max_length=12),
    company_name: str = Query(..., min_length=1, max_length=150),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
):
    """Baixa arquivo AFD."""
    afd_service = AFDService(db)

    request = AFDExportRequest(
        device_id=device_id,
        start_date=start_date,
        end_date=end_date,
    )

    result = await afd_service.export_afd(
        request=request,
        company_cnpj=company_cnpj,
        company_cei=company_cei,
        company_name=company_name,
    )

    if not result.success or not result.file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nenhum registro para exportar",
        )

    return FileResponse(
        path=result.file_path,
        filename=result.file_name,
        media_type="text/plain",
    )


@router.post("/validate", response_model=AFDValidationResult)
async def validate_afd(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> AFDValidationResult:
    """Valida arquivo AFD."""
    content = await file.read()
    content_str = content.decode("utf-8")

    afd_service = AFDService(db)
    return await afd_service.validate_afd_file(content_str)


@router.post("/import", response_model=AFDImportResponse)
async def import_afd(
    device_id: UUID,
    file: UploadFile = File(...),
    validate_only: bool = Query(False),
    skip_duplicates: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> AFDImportResponse:
    """Importa arquivo AFD."""
    content = await file.read()
    content_str = content.decode("utf-8")

    request = AFDImportRequest(
        device_id=device_id,
        file_content=content_str,
        validate_only=validate_only,
        skip_duplicates=skip_duplicates,
    )

    afd_service = AFDService(db)
    return await afd_service.import_afd_file(request)


@router.get("/statistics")
async def get_afd_statistics(
    device_id: UUID | None = None,
    condominio_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> dict:
    """Retorna estatísticas de registros AFD."""
    afd_service = AFDService(db)
    return await afd_service.get_afd_statistics(device_id, condominio_id)


# ── frente 01 — REP-P (Portaria 671): gerar AFD desde o corte, baixar AFD e AEJ ──────────────
from fastapi.responses import Response  # noqa: E402

from modules.hr.rep_integration.services import rep_p  # noqa: E402


@router.post("/rep-p/gerar", summary="Gera linhas AFD (tipo 7) para toda batida >= corte sem linha")
async def rep_p_gerar(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> dict:
    """Idempotente. Devolve quantas gerou e quem ficou de fora (sem CPF / sem empregador)."""
    return await rep_p.gerar_afd_desde_corte(db)


@router.get("/rep-p/arquivo", summary="AFD do estabelecimento (CNPJ) no período")
async def rep_p_arquivo(
    cnpj: str = Query(..., description="CNPJ do empregador (só dígitos ou formatado)"),
    inicio: date = Query(...),
    fim: date = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
):
    try:
        nome, txt = await rep_p.montar_afd(db, cnpj, inicio, fim)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return Response(
        txt.encode("latin-1", "replace"),
        media_type="text/plain; charset=iso-8859-1",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


@router.get("/rep-p/aej", summary="AEJ (Anexo VI) do empregador na competência")
async def rep_p_aej(
    cnpj: str = Query(...),
    ano: int = Query(..., ge=2020),
    mes: int = Query(..., ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
):
    try:
        nome, txt, qt = await rep_p.montar_aej(db, cnpj, ano, mes)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return Response(
        txt.encode("latin-1", "replace"),
        media_type="text/plain; charset=iso-8859-1",
        headers={
            "Content-Disposition": f'attachment; filename="{nome}"',
            "X-AEJ-Contagem": ",".join(f"{k}={v}" for k, v in qt.items()),
        },
    )


@router.get("/rep-p/instrumento", summary="Instrumento legal do REP-P (INPI, atestado, termo)")
async def rep_p_instrumento(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> dict:
    """Vazio é a resposta honesta enquanto o dono não registrar — nunca um default."""
    inst = await rep_p.instrumento(db)
    return {
        "corte": rep_p.CORTE.isoformat(),
        "instrumentos": inst,
        "faltam": [t for t in ("INPI", "ATESTADO_TECNICO", "TERMO_RESPONSABILIDADE") if t not in inst],
    }


_TIPOS_INSTRUMENTO = {"INPI", "ATESTADO_TECNICO", "TERMO_RESPONSABILIDADE"}


@router.post("/rep-p/instrumento", summary="Registra o instrumento legal do REP-P")
async def rep_p_instrumento_gravar(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> dict:
    """Grava INPI, atestado técnico ou termo de responsabilidade — um por tipo.

    ⚠️ 18/09/2026. A tabela `rep_instrumento_legal` era SÓ LEITURA: o `rep_p` lia dela, o
    GET acima mostrava o que havia, o oráculo `test_oraculo_rep_p` cobrava os três — e não
    existia caminho nenhum para escrever. Quando o registro do programa no INPI saísse, o
    número não tinha onde entrar a não ser por SQL na mão, num campo que o AFD imprime.

    Não inventa nada: sem os campos obrigatórios do tipo, recusa. O que o dono não tem
    ainda continua faltando, e o vermelho do oráculo continua honesto até ele ter.
    """
    tipo = str(payload.get("tipo") or "").strip().upper()
    if tipo not in _TIPOS_INSTRUMENTO:
        raise HTTPException(status_code=400, detail=f"Tipo inválido: {tipo!r}. Válidos: {sorted(_TIPOS_INSTRUMENTO)}.")

    def _data(campo: str):
        v = (payload.get(campo) or "").strip()
        if not v:
            return None
        try:
            return date.fromisoformat(v)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"{campo}: use AAAA-MM-DD.") from exc

    numero = (payload.get("numero") or "").strip() or None
    emissor = (payload.get("emissor") or "").strip() or None
    emissao, validade = _data("data_emissao"), _data("validade")

    # O que cada tipo PRECISA é o que o oráculo cobra — a mesma lista, para não divergirem.
    if tipo == "INPI" and not (numero and emissao):
        raise HTTPException(status_code=400, detail="INPI exige número do registro e data de emissão.")
    if tipo == "ATESTADO_TECNICO" and not (emissor and emissao and validade):
        raise HTTPException(
            status_code=400,
            detail="Atestado técnico exige emissor, data de emissão e validade (art. 89 da Portaria 671).",
        )
    if tipo == "TERMO_RESPONSABILIDADE" and not emissao:
        raise HTTPException(status_code=400, detail="Termo de responsabilidade exige a data.")
    if validade and emissao and validade < emissao:
        raise HTTPException(status_code=400, detail="Validade anterior à emissão.")

    from sqlalchemy import text as _text  # noqa: PLC0415

    await db.execute(_text("DELETE FROM rep_instrumento_legal WHERE tipo = :t"), {"t": tipo})
    await db.execute(
        _text(
            "INSERT INTO rep_instrumento_legal (tipo, numero, emissor, data_emissao, validade, "
            "  arquivo_url, observacao) "
            "VALUES (:t, :n, :e, :de, :v, :url, :obs)"
        ),
        {
            "t": tipo,
            "n": numero,
            "e": emissor,
            "de": emissao,
            "v": validade,
            "url": (payload.get("arquivo_url") or "").strip() or None,
            "obs": (payload.get("observacao") or "").strip() or None,
        },
    )
    await db.commit()
    inst = await rep_p.instrumento(db)
    return {
        "ok": True,
        "tipo": tipo,
        "instrumentos": inst,
        "faltam": [t for t in sorted(_TIPOS_INSTRUMENTO) if t not in inst],
    }
