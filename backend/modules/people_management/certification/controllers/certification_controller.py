"""Endpoints da Certificacao Humana — a fila e a assinatura rastreavel (gate C)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser, require_roles
from core.database import get_db

# Perfil DP/Contabil: quem PODE certificar/rejeitar (a assinatura legal).
# manager = "Gerente de departamento" (DP/Contabil) e acima. Listar/ver fica aberto.
CERTIFIER_ROLES = ("super_admin", "admin", "manager")

from ..schemas.certification import (
    CertificationCertifyRequest,
    CertificationCreate,
    CertificationRejectRequest,
    CertificationResponse,
)
from ..services.certification_service import CertificationService

router = APIRouter(prefix="/certifications", tags=["DP - Certificacao Humana"])


def _to_response(cert) -> CertificationResponse:
    resp = CertificationResponse.model_validate(cert)
    resp.valida = CertificationService.is_valid(cert)
    return resp


@router.post("", response_model=CertificationResponse, status_code=201, include_in_schema=True)
@router.post("/", response_model=CertificationResponse, status_code=201, include_in_schema=False)
async def criar_certificacao(
    data: CertificationCreate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> CertificationResponse:
    """Cria uma certificacao PENDENTE (com hash do conteudo) para um calculo."""
    svc = CertificationService(db)
    cert = await svc.create_pending(data.model_dump())
    return _to_response(cert)


@router.get("", response_model=list[CertificationResponse], include_in_schema=True)
@router.get("/", response_model=list[CertificationResponse], include_in_schema=False)
async def listar_certificacoes(
    current_user: CurrentActiveUser,
    status: str | None = Query(None, description="pendente|certificado|rejeitado"),
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[CertificationResponse]:
    """Fila de certificacoes (default: todas; filtra por status)."""
    svc = CertificationService(db)
    return [_to_response(c) for c in await svc.list(status=status, limit=limit)]


@router.post(
    "/gerar-folha/{competencia}",
    dependencies=[Depends(require_roles(*CERTIFIER_ROLES))],
)
async def gerar_certificacoes_folha(
    competencia: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Gera a fila de certificacoes da folha de uma competencia (YYYY-MM) do golden set Dominio.

    Idempotente. Modo 1 do loop DP/Folha: DP/Contabil revisa e assina cada holerite.
    """
    svc = CertificationService(db)
    return await svc.gerar_da_folha(competencia)


@router.get("/{cert_id}", response_model=CertificationResponse)
async def obter_certificacao(
    cert_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> CertificationResponse:
    """O pacote de conferencia: calculado vs esperado (Dominio) vs divergencia."""
    svc = CertificationService(db)
    cert = await svc.get(cert_id)
    if not cert:
        raise HTTPException(status_code=404, detail="Certificacao nao encontrada")
    return _to_response(cert)


@router.patch(
    "/{cert_id}/certify",
    response_model=CertificationResponse,
    dependencies=[Depends(require_roles(*CERTIFIER_ROLES))],
)
async def certificar(
    cert_id: str,
    data: CertificationCertifyRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> CertificationResponse:
    """Assina (o trabalho humano de conferir vira fato rastreavel: quem, quando, hash)."""
    svc = CertificationService(db)
    cert = await svc.certify(cert_id, user_id=str(current_user.id), observacao=data.observacao)
    if not cert:
        raise HTTPException(status_code=404, detail="Certificacao nao encontrada")
    return _to_response(cert)


@router.patch(
    "/{cert_id}/reject",
    response_model=CertificationResponse,
    dependencies=[Depends(require_roles(*CERTIFIER_ROLES))],
)
async def rejeitar(
    cert_id: str,
    data: CertificationRejectRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> CertificationResponse:
    """Rejeita com motivo obrigatorio."""
    svc = CertificationService(db)
    cert = await svc.reject(cert_id, user_id=str(current_user.id), observacao=data.observacao)
    if not cert:
        raise HTTPException(status_code=404, detail="Certificacao nao encontrada")
    return _to_response(cert)
