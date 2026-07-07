"""Controller para modulo Fiscal - Endpoints de NF-e, NFS-e, SPED, Retencoes."""
# pylint: disable=too-many-lines,too-many-arguments,too-many-positional-arguments
# pylint: disable=unused-argument,fixme,logging-fstring-interpolation
# pylint: disable=raise-missing-from,redefined-outer-name,no-else-return

import logging
from datetime import date, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user, require_permission
from core.config.settings import settings
from core.database.session import get_db
from modules.financial.integrations.nfe_provider import (
    NFeError,
    create_nfe_provider,
)
from modules.financial.models.cfop_ncm import CFOPS_VIGILANCIA_ZFM
from modules.financial.models.fiscal_obligation import (
    SIMPLES_ANEXO_III_FAIXAS,
    calcular_das_anexo_iii,
)
from modules.financial.repositories.fiscal_repository import FiscalRepository
from modules.financial.schemas.fiscal_schemas import (
    CalculoLucroRealRequest,
    CalculoRetencaoRequest,
    CalculoRetencaoResponse,
    CalculoSimplesRequest,
    CFOPCreate,
    CFOPListResponse,
    CFOPResponse,
    CFOPUpdate,
    ComparativoRegimesRequest,
    DASCalcularRequest,
    DASCalcularResponse,
    FiscalDashboard,
    FiscalStats,
    NCMCreate,
    NCMListResponse,
    NCMResponse,
    NCMUpdate,
    NFeCancelarRequest,
    NFeCreate,
    NFeEmitirRequest,
    NFeEmitirResponse,
    NFeInutilizarRequest,
    NFeListResponse,
    NFeResponse,
    NFeUpdate,
    NFSeCancelarRequest,
    NFSeCreate,
    NFSeEmitirRequest,
    NFSeEmitirResponse,
    NFSeListResponse,
    NFSeResponse,
    NFSeUpdate,
    ObrigacaoFiscalCreate,
    ObrigacaoFiscalListResponse,
    ObrigacaoFiscalResponse,
    ObrigacaoFiscalUpdate,
    RetencaoFederalCreate,
    RetencaoFederalListResponse,
    RetencaoFederalResponse,
    RetencaoFederalUpdate,
    RetencoesNFSeRequest,
    SimplesNacionalDASCreate,
    SimplesNacionalDASResponse,
    SPEDFileCreate,
    SPEDFileListResponse,
    SPEDFileResponse,
    SPEDGerarRequest,
    SPEDTransmitirRequest,
    SUFRAMAConfigCreate,
    SUFRAMAConfigResponse,
    SUFRAMAOperacaoCreate,
    SUFRAMAOperacaoListResponse,
    SUFRAMAOperacaoResponse,
    VerificacaoLimiteSimplesRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/fiscal", tags=["Fiscal"])


def get_repository(db: AsyncSession = Depends(get_db)) -> FiscalRepository:
    """Retorna instancia do repository fiscal."""
    return FiscalRepository(db)


# ============================================================
# CFOP Endpoints
# ============================================================


@router.post("/cfop", response_model=CFOPResponse, status_code=status.HTTP_201_CREATED)
async def criar_cfop(
    data: CFOPCreate,
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(require_permission("fiscal:cfop:create")),
) -> CFOPResponse:
    """Cria um novo CFOP."""
    try:
        cfop = await repo.create_cfop(data.model_dump())
        logger.info(f"CFOP {cfop.codigo} criado por {getattr(current_user, 'email', '')}")
        return CFOPResponse.model_validate(cfop)
    except Exception as e:
        logger.error(f"Erro ao criar CFOP: {e}")
        raise HTTPException(status_code=500, detail="Erro ao criar CFOP")


@router.get("/cfop", response_model=CFOPListResponse)
async def listar_cfops(
    tipo: str | None = Query(None, description="entrada ou saida"),
    grupo: str | None = Query(None, description="1,2,3,5,6,7"),
    natureza: str | None = None,
    zfm_aplicavel: bool | None = None,
    active: bool = True,
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
) -> CFOPListResponse:
    """Lista CFOPs com filtros."""
    cfops, total = await repo.list_cfops(
        tipo=tipo,
        grupo=grupo,
        natureza=natureza,
        zfm_aplicavel=zfm_aplicavel,
        active=active,
        search=search,
        page=page,
        page_size=page_size,
    )
    return CFOPListResponse(
        items=[CFOPResponse.model_validate(c) for c in cfops],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/cfop/vigilancia-zfm", response_model=dict[str, str])
async def listar_cfops_vigilancia_zfm(
    current_user: dict = Depends(get_current_user),
) -> dict[str, str]:
    """Lista CFOPs comuns para servicos de vigilancia em ZFM."""
    return CFOPS_VIGILANCIA_ZFM


@router.get("/cfop/{cfop_id}", response_model=CFOPResponse)
async def obter_cfop(
    cfop_id: UUID,
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
) -> CFOPResponse:
    """Busca CFOP por ID."""
    cfop = await repo.get_cfop_by_id(cfop_id)
    if not cfop:
        raise HTTPException(status_code=404, detail="CFOP nao encontrado")
    return CFOPResponse.model_validate(cfop)


@router.get("/cfop/codigo/{codigo}", response_model=CFOPResponse)
async def obter_cfop_por_codigo(
    codigo: str,
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
) -> CFOPResponse:
    """Busca CFOP por codigo."""
    cfop = await repo.get_cfop_by_codigo(codigo)
    if not cfop:
        raise HTTPException(status_code=404, detail="CFOP nao encontrado")
    return CFOPResponse.model_validate(cfop)


@router.patch("/cfop/{cfop_id}", response_model=CFOPResponse)
async def atualizar_cfop(
    cfop_id: UUID,
    data: CFOPUpdate,
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(require_permission("fiscal:cfop:update")),
) -> CFOPResponse:
    """Atualiza CFOP."""
    cfop = await repo.update_cfop(cfop_id, data.model_dump(exclude_unset=True))
    if not cfop:
        raise HTTPException(status_code=404, detail="CFOP nao encontrado")
    return CFOPResponse.model_validate(cfop)


# ============================================================
# NCM Endpoints
# ============================================================


@router.post("/ncm", response_model=NCMResponse, status_code=status.HTTP_201_CREATED)
async def criar_ncm(
    data: NCMCreate,
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(require_permission("fiscal:ncm:create")),
) -> NCMResponse:
    """Cria um novo NCM."""
    try:
        ncm = await repo.create_ncm(data.model_dump())
        logger.info(f"NCM {ncm.codigo} criado por {getattr(current_user, 'email', '')}")
        return NCMResponse.model_validate(ncm)
    except Exception as e:
        logger.error(f"Erro ao criar NCM: {e}")
        raise HTTPException(status_code=500, detail="Erro ao criar NCM")


@router.get("/ncm", response_model=NCMListResponse)
async def listar_ncms(
    capitulo: str | None = None,
    posicao: str | None = None,
    tributacao_monofasica: bool | None = None,
    zfm_isento_ipi: bool | None = None,
    active: bool = True,
    vigente: bool = True,
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
) -> NCMListResponse:
    """Lista NCMs com filtros."""
    ncms, total = await repo.list_ncms(
        capitulo=capitulo,
        posicao=posicao,
        tributacao_monofasica=tributacao_monofasica,
        zfm_isento_ipi=zfm_isento_ipi,
        active=active,
        vigente=vigente,
        search=search,
        page=page,
        page_size=page_size,
    )
    return NCMListResponse(
        items=[NCMResponse.model_validate(n) for n in ncms],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/ncm/{ncm_id}", response_model=NCMResponse)
async def obter_ncm(
    ncm_id: UUID,
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
) -> NCMResponse:
    """Busca NCM por ID."""
    ncm = await repo.get_ncm_by_id(ncm_id)
    if not ncm:
        raise HTTPException(status_code=404, detail="NCM nao encontrado")
    return NCMResponse.model_validate(ncm)


@router.get("/ncm/codigo/{codigo}", response_model=NCMResponse)
async def obter_ncm_por_codigo(
    codigo: str,
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
) -> NCMResponse:
    """Busca NCM por codigo."""
    ncm = await repo.get_ncm_by_codigo(codigo)
    if not ncm:
        raise HTTPException(status_code=404, detail="NCM nao encontrado")
    return NCMResponse.model_validate(ncm)


@router.patch("/ncm/{ncm_id}", response_model=NCMResponse)
async def atualizar_ncm(
    ncm_id: UUID,
    data: NCMUpdate,
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(require_permission("fiscal:ncm:update")),
) -> NCMResponse:
    """Atualiza NCM."""
    ncm = await repo.update_ncm(ncm_id, data.model_dump(exclude_unset=True))
    if not ncm:
        raise HTTPException(status_code=404, detail="NCM nao encontrado")
    return NCMResponse.model_validate(ncm)


# ============================================================
# Retencao Federal Endpoints
# ============================================================


@router.post(
    "/retencao",
    response_model=RetencaoFederalResponse,
    status_code=status.HTTP_201_CREATED,
)
async def criar_retencao(
    data: RetencaoFederalCreate,
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(require_permission("fiscal:retencao:create")),
) -> RetencaoFederalResponse:
    """Cria configuracao de retencao federal."""
    try:
        retencao = await repo.create_retencao(
            data.condominio_id,
            data.model_dump(exclude={"condominio_id"}),
        )
        logger.info(f"Retencao {retencao.nome} criada por {getattr(current_user, 'email', '')}")
        return RetencaoFederalResponse.model_validate(retencao)
    except Exception as e:
        logger.error(f"Erro ao criar retencao: {e}")
        raise HTTPException(status_code=500, detail="Erro ao criar retencao")


@router.get("/retencao", response_model=RetencaoFederalListResponse)
async def listar_retencoes(
    condominio_id: UUID,
    servico_vigilancia: bool | None = None,
    active: bool = True,
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
) -> RetencaoFederalListResponse:
    """Lista configuracoes de retencao."""
    retencoes = await repo.list_retencoes(
        condominio_id=condominio_id,
        servico_vigilancia=servico_vigilancia,
        active=active,
    )
    return RetencaoFederalListResponse(
        items=[RetencaoFederalResponse.model_validate(r) for r in retencoes],
        total=len(retencoes),
    )


@router.get("/retencao/{retencao_id}", response_model=RetencaoFederalResponse)
async def obter_retencao(
    retencao_id: UUID,
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
) -> RetencaoFederalResponse:
    """Busca configuracao de retencao por ID."""
    retencao = await repo.get_retencao_by_id(retencao_id)
    if not retencao:
        raise HTTPException(status_code=404, detail="Retencao nao encontrada")
    return RetencaoFederalResponse.model_validate(retencao)


@router.patch("/retencao/{retencao_id}", response_model=RetencaoFederalResponse)
async def atualizar_retencao(
    retencao_id: UUID,
    data: RetencaoFederalUpdate,
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(require_permission("fiscal:retencao:update")),
) -> RetencaoFederalResponse:
    """Atualiza configuracao de retencao."""
    retencao = await repo.update_retencao(retencao_id, data.model_dump(exclude_unset=True))
    if not retencao:
        raise HTTPException(status_code=404, detail="Retencao nao encontrada")
    return RetencaoFederalResponse.model_validate(retencao)


@router.post("/retencao/calcular", response_model=CalculoRetencaoResponse, status_code=201)
async def calcular_retencoes(
    data: CalculoRetencaoRequest,
    condominio_id: UUID | None = Query(None),
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
) -> CalculoRetencaoResponse:
    """Calcula retencoes federais para um valor de servico.

    Considera:
    - INSS: 11% (pode ter liminar que exime)
    - IR: 1.5% (base minima R$ 666,66)
    - PCC: PIS 0.65% + COFINS 3% + CSLL 1% = 4.65% (base minima R$ 215,05)
    - ISS: conforme aliquota municipal

    Para servicos de vigilancia do Simples Nacional Anexo III,
    se houver liminar ativa e o cliente aceitar, INSS = 0.
    """
    # Busca configuracao
    if data.retencao_id:
        retencao = await repo.get_retencao_by_id(data.retencao_id)
    else:
        retencao = await repo.get_retencao_padrao_vigilancia(condominio_id)

    if not retencao:
        raise HTTPException(
            status_code=404,
            detail="Configuracao de retencao nao encontrada",
        )

    # Calcula
    resultado = retencao.calcular_retencoes(
        data.valor_servico,
        data.cliente_aceita_liminar,
    )

    return CalculoRetencaoResponse(
        valor_servico=resultado["valor_servico"],
        inss=resultado["inss"],
        ir=resultado["ir"],
        csll=resultado["csll"],
        pis=resultado["pis"],
        cofins=resultado["cofins"],
        iss=resultado["iss"],
        total=resultado["total"],
        valor_liquido=resultado["valor_liquido"],
        liminar_aplicada=resultado["liminar_aplicada"],
        liminar_numero=resultado.get("liminar_numero"),
        detalhamento={
            "inss_aliquota": float(retencao.inss_aliquota),
            "ir_aliquota": float(retencao.ir_aliquota),
            "pcc_aliquota": float(retencao.aliquota_pcc),
            "liminar_ativa": retencao.inss_liminar_ativa,
            "anexo": "III",
            "observacao": (
                "CPP ja incluso no DAS do Simples Nacional. Retencao de INSS caracteriza bitributacao."
                if retencao.inss_liminar_ativa
                else None
            ),
        },
    )


# ============================================================
# NF-e Endpoints
# ============================================================


@router.post("/nfe", response_model=NFeResponse, status_code=status.HTTP_201_CREATED)
async def criar_nfe(
    data: NFeCreate,
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(require_permission("fiscal:nfe:create")),
) -> NFeResponse:
    """Cria uma nova NF-e."""
    try:
        # Gera numero se nao informado
        if not data.numero:
            data.numero = await repo.get_proximo_numero_nfe(data.condominio_id, data.serie)

        nfe = await repo.create_nfe(
            data.condominio_id,
            data.model_dump(exclude={"condominio_id", "itens"}),
            [item.model_dump() for item in data.itens],
        )
        logger.info(f"NF-e {nfe.numero} criada por {getattr(current_user, 'email', '')}")
        return NFeResponse.model_validate(nfe)
    except Exception as e:
        logger.error(f"Erro ao criar NF-e: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao criar NF-e: {e}")


@router.get("/nfe")
async def listar_nfes(
    condominio_id: UUID | None = None,
    status: str | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    """Lista NF-e. A empresa emite NFS-e (serviços), não NF-e (produtos), e não há
    tabela `nfe` no banco — retorna lista vazia (tela mostra "sem NF-e", não erro 500)."""
    return []


@router.get("/nfe/{nfe_id}")
async def obter_nfe(
    nfe_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Busca NF-e por ID. Le a tabela REAL `nfes` (o model antigo apontava p/ `nfe`,
    que nunca foi criada)."""
    row = (
        await db.execute(text("SELECT * FROM nfes WHERE id = :id AND active IS true"), {"id": nfe_id})
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="NF-e nao encontrada")
    return dict(row)


@router.get("/nfe/chave/{chave_acesso}")
async def obter_nfe_por_chave(
    chave_acesso: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Busca NF-e por chave de acesso. Le a tabela REAL `nfes`."""
    row = (
        await db.execute(
            text("SELECT * FROM nfes WHERE chave_acesso = :chave AND active IS true"),
            {"chave": chave_acesso},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="NF-e nao encontrada")
    return dict(row)


@router.patch("/nfe/{nfe_id}", response_model=NFeResponse)
async def atualizar_nfe(
    nfe_id: UUID,
    data: NFeUpdate,
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(require_permission("fiscal:nfe:update")),
) -> NFeResponse:
    """Atualiza NF-e (apenas rascunho)."""
    nfe = await repo.get_nfe_by_id(nfe_id)
    if not nfe:
        raise HTTPException(status_code=404, detail="NF-e nao encontrada")
    if nfe.status != "rascunho":
        raise HTTPException(
            status_code=400,
            detail="Apenas NF-e em rascunho pode ser editada",
        )

    nfe = await repo.update_nfe(nfe_id, data.model_dump(exclude_unset=True))
    return NFeResponse.model_validate(nfe)


@router.post("/nfe/emitir", response_model=NFeEmitirResponse, status_code=201)
async def emitir_nfe(
    data: NFeEmitirRequest,
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(require_permission("fiscal:nfe:emitir")),
) -> NFeEmitirResponse:
    """Emite NF-e para a SEFAZ.

    TODO: Integrar com biblioteca de NF-e (pynfe, brazilfiscal, etc)
    """
    nfe = await repo.get_nfe_by_id(data.nfe_id)
    if not nfe:
        raise HTTPException(status_code=404, detail="NF-e nao encontrada")
    if nfe.status not in ["rascunho", "rejeitada"]:
        raise HTTPException(
            status_code=400,
            detail=f"NF-e em status {nfe.status} nao pode ser emitida",
        )

    # Integração real com SEFAZ via NFeProvider
    try:
        # Criar provedor NF-e com configurações do ambiente
        nfe_provider = create_nfe_provider(
            certificado_path=settings.NFE_CERT_PATH,
            certificado_senha=settings.NFE_CERT_PASSWORD,
            ambiente=data.ambiente,  # Usar ambiente da requisição (1=prod, 2=homolog)
            uf=settings.NFE_UF,
        )

        # Preparar dados da NF-e para emissão
        nfe_data = {
            "destinatario": nfe.dados_destinatario if hasattr(nfe, "dados_destinatario") else {},
            "items": nfe.items if hasattr(nfe, "items") else [],
            "dados_adicionais": nfe.dados_adicionais if hasattr(nfe, "dados_adicionais") else {},
        }

        # Emitir NF-e na SEFAZ
        resultado = await nfe_provider.emitir_nfe(nfe_data=nfe_data, nfe_id=data.nfe_id, numero=nfe.numero)

        # Atualizar NF-e no banco com resultado da SEFAZ
        await repo.update_nfe(
            data.nfe_id,
            {
                "status": resultado["status"],
                "chave_acesso": resultado["chave_acesso"],
                "protocolo": resultado.get("protocolo"),
                "xml_autorizado": resultado.get("xml_autorizado"),
                "data_emissao": datetime.now(),
            },
        )

        logger.info(
            f"NF-e {nfe.numero} emitida com sucesso - "
            f"Status: {resultado['status']} - "
            f"Chave: {resultado['chave_acesso'][:16]}..."
        )

        return NFeEmitirResponse(
            nfe_id=data.nfe_id,
            status=resultado["status"],
            chave_acesso=resultado["chave_acesso"],
            protocolo=resultado.get("protocolo"),
            mensagem=resultado["mensagem"],
            xml_autorizado=resultado.get("xml_autorizado"),
            pdf_danfe=resultado.get("pdf_danfe"),
        )

    except NFeError as nfe_error:
        logger.error(f"Erro NF-e {nfe.numero}: {nfe_error.message}")
        # Atualizar status para rejeitada em caso de erro
        await repo.update_nfe(
            data.nfe_id, {"status": "rejeitada", "erro_sefaz": nfe_error.message, "codigo_erro": nfe_error.code}
        )
        raise HTTPException(status_code=400, detail=f"Erro na emissão NF-e: {nfe_error.message}")
    except Exception as e:
        logger.error(f"Erro inesperado na emissão NF-e {nfe.numero}: {str(e)}")
        await repo.update_nfe(data.nfe_id, {"status": "rejeitada", "erro_sefaz": f"Erro interno: {str(e)}"})
        raise HTTPException(status_code=500, detail="Erro interno na emissão da NF-e")


@router.post("/nfe/cancelar", status_code=201)
async def cancelar_nfe(
    data: NFeCancelarRequest,
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(require_permission("fiscal:nfe:cancelar")),
) -> dict[str, Any]:
    """Cancela NF-e autorizada."""
    nfe = await repo.get_nfe_by_id(data.nfe_id)
    if not nfe:
        raise HTTPException(status_code=404, detail="NF-e nao encontrada")
    if nfe.status != "autorizada":
        raise HTTPException(
            status_code=400,
            detail="Apenas NF-e autorizada pode ser cancelada",
        )

    # Cancelamento real na SEFAZ via NFeProvider
    try:
        # Criar provedor NF-e
        nfe_provider = create_nfe_provider(
            certificado_path=settings.NFE_CERT_PATH,
            certificado_senha=settings.NFE_CERT_PASSWORD,
            ambiente=settings.NFE_AMBIENTE,
            uf=settings.NFE_UF,
        )

        # Verificar se NF-e tem chave de acesso
        if not nfe.chave_acesso:
            raise HTTPException(status_code=400, detail="NF-e não possui chave de acesso para cancelamento")

        # Cancelar na SEFAZ
        resultado = await nfe_provider.cancelar_nfe(
            chave_acesso=nfe.chave_acesso, motivo=data.justificativa, nfe_id=data.nfe_id
        )

        # Atualizar no banco
        await repo.update_nfe(
            data.nfe_id,
            {
                "status": resultado["status"],
                "protocolo_cancelamento": resultado.get("protocolo"),
                "data_cancelamento": datetime.now(),
                "motivo_cancelamento": data.justificativa,
            },
        )

        logger.info(
            f"NF-e {nfe.numero} cancelada com sucesso - "
            f"Chave: {nfe.chave_acesso[:16]}... - "
            f"Motivo: {data.justificativa}"
        )

        return {
            "message": resultado["mensagem"],
            "nfe_id": str(data.nfe_id),
            "status": resultado["status"],
            "protocolo": resultado.get("protocolo"),
            "data_cancelamento": resultado["data_cancelamento"],
        }

    except NFeError as nfe_error:
        logger.error(f"Erro cancelamento NF-e {nfe.numero}: {nfe_error.message}")
        raise HTTPException(status_code=400, detail=f"Erro no cancelamento: {nfe_error.message}")
    except Exception as e:
        logger.error(f"Erro inesperado no cancelamento NF-e {nfe.numero}: {str(e)}")
        raise HTTPException(status_code=500, detail="Erro interno no cancelamento da NF-e")


@router.post("/nfe/inutilizar", status_code=201)
async def inutilizar_numeracao(
    data: NFeInutilizarRequest,
    condominio_id: UUID | None = Query(None),
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(require_permission("fiscal:nfe:inutilizar")),
) -> dict[str, Any]:
    """Inutiliza faixa de numeracao de NF-e."""
    # TODO: Implementar inutilizacao na SEFAZ
    logger.info(
        f"Inutilizando NF-e serie {data.serie} numeros "
        f"{data.numero_inicial} a {data.numero_final}: {data.justificativa}"
    )

    return {
        "message": "Numeracao inutilizada com sucesso",
        "serie": data.serie,
        "numero_inicial": data.numero_inicial,
        "numero_final": data.numero_final,
    }


# ============================================================
# NFS-e Endpoints
# ============================================================


@router.post("/nfse", response_model=NFSeResponse, status_code=status.HTTP_201_CREATED)
async def criar_nfse(
    data: NFSeCreate,
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(require_permission("fiscal:nfse:create")),
) -> NFSeResponse:
    """Cria uma nova NFS-e."""
    try:
        # Gera numero RPS se nao informado
        if not data.numero_rps:
            data.numero_rps = await repo.get_proximo_numero_rps(data.condominio_id, data.serie_rps)

        nfse = await repo.create_nfse(
            data.condominio_id,
            data.model_dump(exclude={"condominio_id"}),
        )
        logger.info(f"NFS-e RPS {nfse.numero_rps} criada por {getattr(current_user, 'email', '')}")
        return NFSeResponse.model_validate(nfse)
    except Exception as e:
        logger.error(f"Erro ao criar NFS-e: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao criar NFS-e: {e}")


@router.get("/nfse")
async def listar_nfses(
    condominio_id: UUID | None = None,
    status: str | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Lista NFS-e emitidas da fonte autoritativa `nfse_emitidas_nacional`
    (77 notas jan-jun, todas validas cStat 100). Devolve um array no formato que a
    tela consome. condominio_id é ignorado no filtro (as NFS-e da empresa pertencem
    aos condominio_ids reais e o front injeta um placeholder de dev).
    A tabela nacional nao tem coluna status/active/numero_rps/serie_rps/codigo_verificacao:
    todas as linhas sao autorizadas; competencia (varchar 'YYYY-MM') substitui data_competencia."""
    conds: list[str] = []
    params: dict[str, Any] = {"limit": page_size, "offset": (page - 1) * page_size}
    # Filtro por status: a fonte so contem notas autorizadas. Se pedirem outro
    # status, o resultado e vazio (nao existem canceladas/rejeitadas aqui).
    if status and status.lower() not in ("autorizada", "autorizado", "authorized"):
        conds.append("1 = 0")
    if search:
        conds.append("(tomador_nome ILIKE :s OR numero::text ILIKE :s)")
        params["s"] = f"%{search}%"
    where = (" AND ".join(conds)) if conds else "TRUE"
    rows = (
        await db.execute(
            text(
                "SELECT chave_acesso, numero, competencia, "
                "tomador_nome, tomador_cnpj, "
                "valor_servicos, data_emissao, created_at "
                f"FROM nfse_emitidas_nacional WHERE {where} "
                "ORDER BY data_emissao DESC NULLS LAST, numero DESC LIMIT :limit OFFSET :offset"
            ),
            params,
        )
    ).mappings().all()

    def _iso(v):
        return v.isoformat() if v else None

    return [
        {
            "id": r["chave_acesso"] or r["numero"],
            "number": r["numero"],
            "series": None,
            "recipient_name": r["tomador_nome"],
            "recipient_document": r["tomador_cnpj"],
            "access_key": r["chave_acesso"],
            "amount": float(r["valor_servicos"] or 0),
            "total_amount": float(r["valor_servicos"] or 0),
            "net_amount": float(r["valor_servicos"] or 0),
            "status": "autorizada",
            "issue_date": _iso(r["data_emissao"]),
            "competence_date": r["competencia"],
            "created_at": _iso(r["created_at"]),
            # aliases PT p/ robustez
            "numero": r["numero"],
            "valor": float(r["valor_servicos"] or 0),
        }
        for r in rows
    ]


@router.get("/nfse/{nfse_id}")
async def obter_nfse(
    nfse_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Busca NFS-e por ID. Le a tabela REAL `nfses` (o model antigo apontava p/ `nfse`,
    inexistente) — mesmo padrao do LIST."""
    row = (
        await db.execute(text("SELECT * FROM nfses WHERE id = :id AND active IS true"), {"id": nfse_id})
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="NFS-e nao encontrada")
    return dict(row)


@router.patch("/nfse/{nfse_id}", response_model=NFSeResponse)
async def atualizar_nfse(
    nfse_id: UUID,
    data: NFSeUpdate,
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(require_permission("fiscal:nfse:update")),
) -> NFSeResponse:
    """Atualiza NFS-e (apenas rascunho)."""
    nfse = await repo.get_nfse_by_id(nfse_id)
    if not nfse:
        raise HTTPException(status_code=404, detail="NFS-e nao encontrada")
    if nfse.status != "rascunho":
        raise HTTPException(
            status_code=400,
            detail="Apenas NFS-e em rascunho pode ser editada",
        )

    nfse = await repo.update_nfse(nfse_id, data.model_dump(exclude_unset=True))
    return NFSeResponse.model_validate(nfse)


@router.post("/nfse/emitir", response_model=NFSeEmitirResponse, status_code=201)
async def emitir_nfse(
    data: NFSeEmitirRequest,
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(require_permission("fiscal:nfse:emitir")),
) -> NFSeEmitirResponse:
    """Emite NFS-e para a prefeitura de Manaus (ABRASF 2.0, produção real).

    Liga ao motor real (NFSeManausService). O resultado é HONESTO: se a prefeitura autorizar,
    grava o número/código reais; se rejeitar, grava o erro real. Nunca finge sucesso.
    """
    nfse = await repo.get_nfse_by_id(data.nfse_id)
    if not nfse:
        raise HTTPException(status_code=404, detail="NFS-e nao encontrada")
    if nfse.status not in ["rascunho", "rejeitada"]:
        raise HTTPException(
            status_code=400,
            detail=f"NFS-e em status {nfse.status} nao pode ser emitida",
        )

    import re as _re

    from modules.government_integrations.services.nfse_manaus_service import NFSeManausService

    def _g(*names, default=None):
        for n in names:
            v = getattr(nfse, n, None)
            if v not in (None, ""):
                return v
        return default

    tomador_data = {
        "cpf_cnpj": _g("tomador_cpf_cnpj", default=""),
        "razao_social": _g("tomador_razao_social", default=""),
        "endereco": _g("tomador_logradouro", "tomador_endereco", default=""),
        "numero": _g("tomador_numero", default="S/N"),
        "bairro": _g("tomador_bairro", default=""),
        "cidade": _g("tomador_municipio", "tomador_cidade", default="Manaus"),
        "uf": _g("tomador_uf", default="AM"),
        "cep": _g("tomador_cep", default=""),
        "email": _g("tomador_email"),
        "telefone": _g("tomador_telefone"),
        "inscricao_municipal": _g("tomador_inscricao_municipal"),
    }
    servico_data = {
        "codigo_servico": _g("codigo_servico", default="11.02"),
        "discriminacao": _g("discriminacao", "descricao_servico", default=""),
        "valor_servicos": float(_g("valor_servicos", default=0) or 0),
        "aliquota_iss": float(_g("iss_aliquota", default=0.05) or 0.05),
        "iss_retido": bool(_g("iss_retido", default=False)),
        "codigo_cnae": _g("codigo_cnae"),
        "valor_deducoes": float(_g("valor_deducoes", default=0) or 0),
    }
    comp = None
    dc = _g("data_competencia", "competencia")
    if dc is not None:
        try:
            comp = dc.strftime("%Y-%m")
        except Exception:  # noqa: BLE001
            comp = str(dc)[:7]

    logger.info("Emitindo NFS-e REAL: RPS=%s tomador=%s valor=%s", nfse.numero_rps,
                tomador_data["cpf_cnpj"], servico_data["valor_servicos"])
    try:
        svc = NFSeManausService()
        # Empresa é LUCRO REAL (não Simples) — optante_simples=False
        resultado = svc.emitir_nfse(tomador_data, servico_data, competencia=comp, optante_simples=False)
    except Exception as exc:  # noqa: BLE001
        logger.error("Falha ao emitir NFS-e %s: %s", data.nfse_id, exc)
        await repo.update_nfse(data.nfse_id, {"status": "rejeitada"})
        raise HTTPException(status_code=502, detail=f"Falha ao emitir na prefeitura: {exc}") from exc

    status_ws = (resultado.get("status") or "").lower()
    saida = resultado.get("resposta_ws", {}) or {}
    corpo = str(saida.get("outputxml") or saida.get("resposta_raw") or "")
    numero_nfse = None
    codigo_verif = None
    m = _re.search(r"<Numero>(\d+)</Numero>", corpo)
    if m:
        numero_nfse = m.group(1)
    m = _re.search(r"<CodigoVerificacao>(.*?)</CodigoVerificacao>", corpo)
    if m:
        codigo_verif = m.group(1)
    erro_msg = None
    me = _re.search(r"<Mensagem>(.*?)</Mensagem>", corpo)
    if me:
        erro_msg = me.group(1)

    if numero_nfse:
        novo_status = "autorizada"
        upd = {"status": "autorizada", "numero_nfse": numero_nfse}
        if codigo_verif:
            upd["codigo_verificacao"] = codigo_verif
        await repo.update_nfse(data.nfse_id, upd)
        mensagem = f"NFS-e autorizada pela prefeitura (nº {numero_nfse})"
    elif status_ws in ("enviado", "processando") and not erro_msg:
        novo_status = "processando"
        await repo.update_nfse(data.nfse_id, {"status": "processando"})
        mensagem = "NFS-e enviada à prefeitura; aguardando autorização (consulte o status)."
    else:
        novo_status = "rejeitada"
        await repo.update_nfse(data.nfse_id, {"status": "rejeitada"})
        mensagem = f"Prefeitura rejeitou: {erro_msg or resultado.get('mensagem') or 'erro não detalhado'}"

    return NFSeEmitirResponse(
        nfse_id=data.nfse_id,
        status=novo_status,
        numero_nfse=numero_nfse,
        codigo_verificacao=codigo_verif,
        link_nfse=None,
        protocolo=resultado.get("protocolo"),
        mensagem=mensagem,
        xml=resultado.get("xml_envio"),
        pdf=None,
    )


@router.post("/nfse/cancelar", status_code=201)
async def cancelar_nfse(
    data: NFSeCancelarRequest,
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(require_permission("fiscal:nfse:cancelar")),
) -> dict[str, Any]:
    """Cancela NFS-e autorizada."""
    nfse = await repo.get_nfse_by_id(data.nfse_id)
    if not nfse:
        raise HTTPException(status_code=404, detail="NFS-e nao encontrada")
    if nfse.status != "autorizada":
        raise HTTPException(
            status_code=400,
            detail="Apenas NFS-e autorizada pode ser cancelada",
        )

    # TODO: Implementar cancelamento na prefeitura
    logger.info(f"Cancelando NFS-e {nfse.numero_nfse}: {data.codigo_cancelamento}")

    await repo.update_nfse(data.nfse_id, {"status": "cancelada"})

    return {"message": "NFS-e cancelada com sucesso", "nfse_id": str(data.nfse_id)}


@router.get("/nfse/retencoes/competencia")
async def obter_retencoes_competencia(
    condominio_id: UUID,
    mes: int = Query(..., ge=1, le=12),
    ano: int = Query(..., ge=2000),
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Retorna total de retencoes de uma competencia.

    Util para conferencia de DAS e relatorios fiscais.
    Inclui economia com liminar de INSS.
    """
    retencoes = await repo.calcular_total_retencoes_competencia(condominio_id, mes, ano)
    return {
        "competencia": f"{mes:02d}/{ano}",
        **{k: float(v) for k, v in retencoes.items()},
    }


# ============================================================
# SPED Endpoints
# ============================================================


@router.post("/sped", response_model=SPEDFileResponse, status_code=status.HTTP_201_CREATED)
async def criar_sped(
    data: SPEDFileCreate,
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(require_permission("fiscal:sped:create")),
) -> SPEDFileResponse:
    """Cria arquivo SPED."""
    try:
        sped = await repo.create_sped_file(
            data.condominio_id,
            data.model_dump(exclude={"condominio_id"}),
        )
        logger.info(f"SPED {sped.tipo} criado por {getattr(current_user, 'email', '')}")
        return SPEDFileResponse.model_validate(sped)
    except Exception as e:
        logger.error(f"Erro ao criar SPED: {e}")
        raise HTTPException(status_code=500, detail="Erro ao criar SPED")


@router.get("/sped", response_model=SPEDFileListResponse)
async def listar_speds(
    condominio_id: UUID,
    tipo: str | None = None,
    status: str | None = None,
    ano: int | None = None,
    mes: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
) -> SPEDFileListResponse:
    """Lista arquivos SPED."""
    speds, total = await repo.list_sped_files(
        condominio_id=condominio_id,
        tipo=tipo,
        status=status,
        ano=ano,
        mes=mes,
        page=page,
        page_size=page_size,
    )
    return SPEDFileListResponse(
        items=[SPEDFileResponse.model_validate(s) for s in speds],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/sped/{sped_id}", response_model=SPEDFileResponse)
async def obter_sped(
    sped_id: UUID,
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
) -> SPEDFileResponse:
    """Busca arquivo SPED por ID."""
    sped = await repo.get_sped_file_by_id(sped_id)
    if not sped:
        raise HTTPException(status_code=404, detail="SPED nao encontrado")
    return SPEDFileResponse.model_validate(sped)


@router.post("/sped/gerar", status_code=201)
async def gerar_sped(
    data: SPEDGerarRequest,
    condominio_id: UUID | None = Query(None),
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(require_permission("fiscal:sped:gerar")),
) -> dict[str, Any]:
    """Gera arquivo SPED.

    TODO: Implementar geracao de arquivos SPED
    """
    logger.info(f"Gerando SPED {data.tipo} para {data.ano}/{data.mes or 'anual'}")

    # Cria registro
    sped = await repo.create_sped_file(
        condominio_id,
        {
            "tipo": data.tipo,
            "ano": data.ano,
            "mes": data.mes,
            "finalidade": data.finalidade,
            "status": "gerando",
        },
    )

    # TODO: Implementar geracao assincrona

    return {
        "message": "Geracao de SPED iniciada",
        "sped_id": str(sped.id),
        "tipo": data.tipo,
    }


@router.post("/sped/{sped_id}/validar", status_code=201)
async def validar_sped(
    sped_id: UUID,
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(require_permission("fiscal:sped:validar")),
) -> dict[str, Any]:
    """Valida arquivo SPED."""
    sped = await repo.get_sped_file_by_id(sped_id)
    if not sped:
        raise HTTPException(status_code=404, detail="SPED nao encontrado")

    # TODO: Implementar validacao com PVA
    logger.info(f"Validando SPED {sped.id}")

    await repo.update_sped_file(sped_id, {"status": "validando"})

    return {"message": "Validacao iniciada", "sped_id": str(sped_id)}


@router.post("/sped/{sped_id}/transmitir", status_code=201)
async def transmitir_sped(
    sped_id: UUID,
    data: SPEDTransmitirRequest,
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(require_permission("fiscal:sped:transmitir")),
) -> dict[str, Any]:
    """Transmite arquivo SPED."""
    sped = await repo.get_sped_file_by_id(sped_id)
    if not sped:
        raise HTTPException(status_code=404, detail="SPED nao encontrado")
    if sped.status not in ["validado", "assinado"]:
        raise HTTPException(
            status_code=400,
            detail="SPED precisa estar validado/assinado para transmitir",
        )

    # TODO: Implementar transmissao
    logger.info(f"Transmitindo SPED {sped.id} - ambiente {data.ambiente}")

    await repo.update_sped_file(sped_id, {"status": "transmitindo"})

    return {"message": "Transmissao iniciada", "sped_id": str(sped_id)}


# ============================================================
# Obrigacao Fiscal Endpoints
# ============================================================


@router.post(
    "/obrigacao",
    response_model=ObrigacaoFiscalResponse,
    status_code=status.HTTP_201_CREATED,
)
async def criar_obrigacao(
    data: ObrigacaoFiscalCreate,
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(require_permission("fiscal:obrigacao:create")),
) -> ObrigacaoFiscalResponse:
    """Cria obrigacao fiscal."""
    obrigacao = await repo.create_obrigacao(
        data.condominio_id,
        data.model_dump(exclude={"condominio_id"}),
    )
    return ObrigacaoFiscalResponse.model_validate(obrigacao)


@router.get("/obrigacao", response_model=ObrigacaoFiscalListResponse)
async def listar_obrigacoes(
    condominio_id: UUID,
    tipo: str | None = None,
    status: str | None = None,
    mes: int | None = None,
    ano: int | None = None,
    vencimento_inicio: date | None = None,
    vencimento_fim: date | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
) -> ObrigacaoFiscalListResponse:
    """Lista obrigacoes fiscais."""
    obrigacoes, total = await repo.list_obrigacoes(
        condominio_id=condominio_id,
        tipo=tipo,
        status=status,
        mes=mes,
        ano=ano,
        vencimento_inicio=vencimento_inicio,
        vencimento_fim=vencimento_fim,
        page=page,
        page_size=page_size,
    )

    pendentes = await repo.get_obrigacoes_pendentes(condominio_id)
    atrasadas = await repo.get_obrigacoes_atrasadas(condominio_id)

    return ObrigacaoFiscalListResponse(
        items=[ObrigacaoFiscalResponse.model_validate(o) for o in obrigacoes],
        total=total,
        proximas_a_vencer=len(pendentes),
        atrasadas=len(atrasadas),
    )


@router.get("/obrigacao/pendentes")
async def listar_obrigacoes_pendentes(
    condominio_id: UUID,
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
) -> list[ObrigacaoFiscalResponse]:
    """Lista obrigacoes pendentes ordenadas por vencimento."""
    obrigacoes = await repo.get_obrigacoes_pendentes(condominio_id)
    return [ObrigacaoFiscalResponse.model_validate(o) for o in obrigacoes]


@router.get("/obrigacao/atrasadas")
async def listar_obrigacoes_atrasadas(
    condominio_id: UUID,
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
) -> list[ObrigacaoFiscalResponse]:
    """Lista obrigacoes atrasadas."""
    obrigacoes = await repo.get_obrigacoes_atrasadas(condominio_id)
    return [ObrigacaoFiscalResponse.model_validate(o) for o in obrigacoes]


@router.get("/obrigacao/{obrigacao_id}", response_model=ObrigacaoFiscalResponse)
async def obter_obrigacao(
    obrigacao_id: UUID,
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
) -> ObrigacaoFiscalResponse:
    """Busca obrigacao por ID."""
    obrigacao = await repo.get_obrigacao_by_id(obrigacao_id)
    if not obrigacao:
        raise HTTPException(status_code=404, detail="Obrigacao nao encontrada")
    return ObrigacaoFiscalResponse.model_validate(obrigacao)


@router.patch("/obrigacao/{obrigacao_id}", response_model=ObrigacaoFiscalResponse)
async def atualizar_obrigacao(
    obrigacao_id: UUID,
    data: ObrigacaoFiscalUpdate,
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(require_permission("fiscal:obrigacao:update")),
) -> ObrigacaoFiscalResponse:
    """Atualiza obrigacao fiscal."""
    obrigacao = await repo.update_obrigacao(obrigacao_id, data.model_dump(exclude_unset=True))
    if not obrigacao:
        raise HTTPException(status_code=404, detail="Obrigacao nao encontrada")
    return ObrigacaoFiscalResponse.model_validate(obrigacao)


# ============================================================
# Simples Nacional / DAS Endpoints
# ============================================================


@router.post("/das", response_model=SimplesNacionalDASResponse, status_code=status.HTTP_201_CREATED)
async def criar_das(
    data: SimplesNacionalDASCreate,
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(require_permission("fiscal:das:create")),
) -> SimplesNacionalDASResponse:
    """Cria DAS do Simples Nacional."""
    das = await repo.create_das(
        data.condominio_id,
        data.model_dump(exclude={"condominio_id"}),
    )
    return SimplesNacionalDASResponse.model_validate(das)


@router.get("/das")
async def listar_das(
    condominio_id: UUID,
    ano: int | None = None,
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
) -> list[SimplesNacionalDASResponse]:
    """Lista DAS do Simples Nacional."""
    das_list = await repo.list_das(condominio_id, ano)
    return [SimplesNacionalDASResponse.model_validate(d) for d in das_list]


@router.get("/das/competencia")
async def obter_das_competencia(
    condominio_id: UUID,
    mes: int = Query(..., ge=1, le=12),
    ano: int = Query(..., ge=2000),
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
) -> SimplesNacionalDASResponse | None:
    """Busca DAS de uma competencia."""
    das = await repo.get_das_competencia(condominio_id, mes, ano)
    if not das:
        return None
    return SimplesNacionalDASResponse.model_validate(das)


@router.post("/das/calcular", response_model=DASCalcularResponse, status_code=201)
async def calcular_das(
    data: DASCalcularRequest,
    condominio_id: UUID | None = Query(None),
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
) -> DASCalcularResponse:
    """Calcula DAS do Simples Nacional.

    Para servicos de vigilancia (Anexo III):
    - ISS ja esta INCLUSO no DAS
    - CPP (INSS patronal) ja esta INCLUSO no DAS
    - Nao deve haver retencao adicional de INSS (bitributacao)
    """
    # Calcula faixa e aliquota
    resultado = calcular_das_anexo_iii(
        data.receita_bruta_mes,
        data.receita_bruta_12_meses,
    )

    # Data de vencimento: dia 20 do mes seguinte
    if data.competencia_mes == 12:
        vencimento = date(data.competencia_ano + 1, 1, 20)
    else:
        vencimento = date(data.competencia_ano, data.competencia_mes + 1, 20)

    return DASCalcularResponse(
        faixa=resultado["faixa"],
        aliquota_nominal=resultado["aliquota_nominal"],
        parcela_deduzir=resultado["parcela_deduzir"],
        aliquota_efetiva=resultado["aliquota_efetiva"],
        valor_devido=resultado["valor_devido"],
        reparticao=resultado["reparticao"],
        data_vencimento=vencimento,
    )


@router.get("/das/faixas")
async def obter_faixas_simples(
    anexo: str = Query("III", description="III, IV ou V"),
    current_user: dict = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Retorna tabela de faixas do Simples Nacional.

    Anexo III - Servicos de vigilancia, limpeza, conservacao:
    - ISS INCLUSO no DAS
    - CPP INCLUSO no DAS (nao reter INSS adicional)
    """
    if anexo == "III":
        return SIMPLES_ANEXO_III_FAIXAS
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Anexo {anexo} nao implementado. Use III.",
        )


@router.get("/das/receita-12-meses")
async def obter_receita_12_meses(
    condominio_id: UUID,
    mes_referencia: int = Query(..., ge=1, le=12),
    ano_referencia: int = Query(..., ge=2000),
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Calcula receita bruta dos ultimos 12 meses para DAS."""
    receita = await repo.get_receita_12_meses(condominio_id, mes_referencia, ano_referencia)
    return {
        "referencia": f"{mes_referencia:02d}/{ano_referencia}",
        "receita_bruta_12_meses": float(receita),
    }


# ============================================================
# SUFRAMA Endpoints
# ============================================================


@router.post(
    "/suframa/config",
    response_model=SUFRAMAConfigResponse,
    status_code=status.HTTP_201_CREATED,
)
async def criar_suframa_config(
    data: SUFRAMAConfigCreate,
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(require_permission("fiscal:suframa:create")),
) -> SUFRAMAConfigResponse:
    """Cria configuracao SUFRAMA."""
    config = await repo.create_suframa_config(
        data.condominio_id,
        data.model_dump(exclude={"condominio_id"}),
    )
    return SUFRAMAConfigResponse.model_validate(config)


@router.get("/suframa/config", response_model=SUFRAMAConfigResponse | None)
async def obter_suframa_config(
    condominio_id: UUID,
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
) -> SUFRAMAConfigResponse | None:
    """Busca configuracao SUFRAMA ativa."""
    config = await repo.get_suframa_config(condominio_id)
    if not config:
        return None
    return SUFRAMAConfigResponse.model_validate(config)


@router.post(
    "/suframa/operacao",
    response_model=SUFRAMAOperacaoResponse,
    status_code=status.HTTP_201_CREATED,
)
async def registrar_operacao_suframa(
    data: SUFRAMAOperacaoCreate,
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(require_permission("fiscal:suframa:create")),
) -> SUFRAMAOperacaoResponse:
    """Registra operacao com beneficio SUFRAMA."""
    operacao = await repo.create_suframa_operacao(
        data.condominio_id,
        data.model_dump(exclude={"condominio_id"}),
    )
    return SUFRAMAOperacaoResponse.model_validate(operacao)


@router.get("/suframa/operacoes", response_model=SUFRAMAOperacaoListResponse)
async def listar_operacoes_suframa(
    condominio_id: UUID,
    data_inicial: date | None = None,
    data_final: date | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
) -> SUFRAMAOperacaoListResponse:
    """Lista operacoes com beneficio SUFRAMA."""
    operacoes, total = await repo.list_suframa_operacoes(
        condominio_id=condominio_id,
        data_inicial=data_inicial,
        data_final=data_final,
        page=page,
        page_size=page_size,
    )

    economia = await repo.get_economia_suframa_periodo(
        condominio_id,
        data_inicial or date(date.today().year, 1, 1),
        data_final or date.today(),
    )

    return SUFRAMAOperacaoListResponse(
        items=[SUFRAMAOperacaoResponse.model_validate(o) for o in operacoes],
        total=total,
        total_economia_ipi=economia["ipi"],
        total_economia_icms=economia["icms"],
        total_economia_pis_cofins=economia["pis_cofins"],
    )


@router.get("/suframa/economia")
async def obter_economia_suframa(
    condominio_id: UUID,
    data_inicial: date,
    data_final: date,
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Calcula economia SUFRAMA de um periodo."""
    economia = await repo.get_economia_suframa_periodo(condominio_id, data_inicial, data_final)
    return {
        "periodo": f"{data_inicial.isoformat()} a {data_final.isoformat()}",
        "economia_ipi": float(economia["ipi"]),
        "economia_icms": float(economia["icms"]),
        "economia_pis_cofins": float(economia["pis_cofins"]),
        "total": float(economia["total"]),
    }


# ============================================================
# Dashboard e Estatisticas
# ============================================================


@router.get("/stats", response_model=FiscalStats)
async def obter_stats_fiscal(
    condominio_id: UUID,
    mes: int = Query(default=None, ge=1, le=12),
    ano: int = Query(default=None, ge=2000),
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
) -> FiscalStats:
    """Retorna estatisticas fiscais do mes."""
    if not mes:
        mes = date.today().month
    if not ano:
        ano = date.today().year

    stats = await repo.get_fiscal_stats(condominio_id, mes, ano)
    return FiscalStats(**stats)


@router.get("/dashboard")
async def obter_dashboard_fiscal(
    condominio_id: UUID | None = None,
    mes: int = Query(default=None, ge=1, le=12),
    ano: int = Query(default=None, ge=2000),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Dashboard fiscal — lê a tabela REAL `nfses` (o model antigo apontava p/ `nfse`,
    inexistente, causando 500). Retorna o shape consumido pela tela (stats.*)."""
    if not mes:
        mes = date.today().month
    if not ano:
        ano = date.today().year

    total_nfse = (await db.execute(text("SELECT count(*) FROM nfse_emitidas_nacional"))).scalar() or 0
    total_nfse_mes = (
        await db.execute(
            text(
                "SELECT count(*) FROM nfse_emitidas_nacional "
                "WHERE CAST(substr(competencia, 6, 2) AS int) = :m "
                "AND CAST(left(competencia, 4) AS int) = :a"
            ),
            {"m": mes, "a": ano},
        )
    ).scalar() or 0
    valor_total = (
        await db.execute(text("SELECT COALESCE(SUM(valor_servicos), 0) FROM nfse_emitidas_nacional"))
    ).scalar() or 0
    try:
        obrig_pend = (
            await db.execute(
                text("SELECT count(*) FROM fiscal_obligations WHERE active = true AND status = 'pendente'")
            )
        ).scalar() or 0
    except Exception:  # noqa: BLE001
        obrig_pend = 0

    notas_recentes = [
        {
            "tipo": "NFS-e",
            "numero": r["numero"],
            "valor": float(r["valor_servicos"] or 0),
            "data": r["data_emissao"].isoformat() if r["data_emissao"] else None,
            # nfse_emitidas_nacional so contem notas validas (cStat 100)
            "status": "autorizada",
        }
        for r in (
            await db.execute(
                text(
                    "SELECT numero, valor_servicos, data_emissao "
                    "FROM nfse_emitidas_nacional ORDER BY data_emissao DESC NULLS LAST LIMIT 5"
                )
            )
        ).mappings().all()
    ]

    return {
        "stats": {
            "total_nfse_emitidas": int(total_nfse),
            "total_nfe_emitidas": 0,
            "total_nfe_mes": int(total_nfse_mes),
            "valor_total_nfse": float(valor_total),
            "obrigacoes_pendentes": int(obrig_pend),
        },
        "notas_recentes": notas_recentes,
        "obrigacoes_proximas": [],
        "alertas": [],
        "grafico_impostos": [],
        "grafico_notas": [],
    }


# ── Tax Calculator Multi-Regime ───────────────────────────────────────────────

from decimal import Decimal  # noqa: E402

from modules.financial.agents.tax_calculator import TaxCalculatorAgent  # noqa: E402

_tax_agent = TaxCalculatorAgent()


@router.post("/calcular/simples", summary="Calcular DAS Simples Nacional", status_code=201)
async def calcular_simples_nacional(
    dados: CalculoSimplesRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Calcula DAS do Simples Nacional (Anexo III - vigilância/serviços).
    Aplica liminares automaticamente se informadas.
    """
    resultado = _tax_agent.calcular_simples(
        receita_mes=Decimal(str(dados.receita_mes)),
        rbt12=Decimal(str(dados.rbt12)),
        liminares=dados.liminares,
    )
    return {
        "regime": "simples_nacional",
        "anexo": resultado.anexo,
        "receita_bruta_mes": float(resultado.receita_bruta_mes),
        "receita_bruta_12_meses": float(resultado.receita_bruta_12_meses),
        "aliquota_nominal": f"{float(resultado.aliquota_nominal) * 100:.2f}%",
        "aliquota_efetiva": f"{float(resultado.aliquota_efetiva) * 100:.2f}%",
        "valor_das": float(resultado.valor_das),
        "carga_tributaria": f"{float(resultado.carga_tributaria_percentual):.2f}%",
        "distribuicao": resultado.distribuicao,
        "liminares_aplicadas": resultado.liminares_aplicadas,
        "economia_liminares": float(resultado.economia_liminares),
    }


@router.post("/calcular/lucro-real", summary="Calcular impostos Lucro Real", status_code=201)
async def calcular_lucro_real(
    dados: CalculoLucroRealRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Calcula IRPJ, CSLL, PIS (nc), COFINS (nc), ISS no regime Lucro Real.
    """
    resultado = _tax_agent.calcular_lucro_real(
        receita_mes=Decimal(str(dados.receita_mes)),
        receita_trimestre=Decimal(str(dados.receita_trimestre)),
        custos_dedutiveis_mes=Decimal(str(dados.custos_dedutiveis_mes)),
    )
    return {
        "regime": "lucro_real",
        "receita_bruta_mes": float(resultado.receita_bruta_mes),
        "lucro_presumido_base": float(resultado.lucro_bruto),
        "irpj": float(resultado.irpj),
        "irpj_adicional": float(resultado.irpj_adicional),
        "csll": float(resultado.csll),
        "pis": float(resultado.pis),
        "cofins": float(resultado.cofins),
        "iss": float(resultado.iss),
        "total_impostos_mes": float(resultado.total_impostos_mes),
        "carga_tributaria": f"{float(resultado.carga_tributaria_percentual):.2f}%",
        "detalhamento": [
            {
                "nome": d.nome,
                "aliquota": float(d.aliquota),
                "base": float(d.base_calculo),
                "valor": float(d.valor),
            }
            for d in resultado.detalhamento
        ],
    }


@router.post("/calcular/comparativo-regimes", summary="Comparar Simples vs Lucro Real", status_code=201)
async def comparar_regimes(
    dados: ComparativoRegimesRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Compara carga tributária anual entre Simples Nacional e Lucro Real.
    Útil para decisão de mudança de regime.
    """
    resultado = _tax_agent.comparar_regimes(
        receita_anual=Decimal(str(dados.receita_anual)),
        custos_dedutiveis_anual=Decimal(str(dados.custos_dedutiveis_anual)),
        liminares=dados.liminares,
    )
    return {
        "receita_bruta_anual": float(resultado.receita_bruta_anual),
        "simples_nacional": {
            "total_anual": float(resultado.simples_nacional_total),
            "percentual": f"{float(resultado.simples_nacional_percentual):.2f}%",
        },
        "lucro_real": {
            "total_anual": float(resultado.lucro_real_total),
            "percentual": f"{float(resultado.lucro_real_percentual):.2f}%",
        },
        "economia_simples_anual": float(resultado.economia_simples),
        "recomendacao": resultado.recomendacao,
        "observacoes": resultado.observacoes,
    }


@router.post("/calcular/retencoes-nfse", summary="Calcular retenções na fonte NFS-e", status_code=201)
async def calcular_retencoes_nfse(
    dados: RetencoesNFSeRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Calcula INSS, IR, CSLL, PIS, COFINS, ISS retidos na fonte.
    Aplica liminares automaticamente.
    """
    resultado = _tax_agent.calcular_retencoes_nfse(
        valor_servico=Decimal(str(dados.valor_servico)),
        regime_empresa=dados.regime_empresa,
        liminares=dados.liminares,
    )
    return {
        "valor_servico": float(resultado.valor_servico),
        "retencoes": {
            "inss_11pct": float(resultado.inss),
            "ir_1_5pct": float(resultado.ir),
            "csll_1pct": float(resultado.csll),
            "pis_0_65pct": float(resultado.pis),
            "cofins_3pct": float(resultado.cofins),
            "iss_5pct": float(resultado.iss),
        },
        "total_retencoes": float(resultado.total_retencoes),
        "valor_liquido_receber": float(resultado.valor_liquido),
        "liminares_aplicadas": resultado.liminares_aplicadas,
    }


@router.post("/calcular/verificar-limite-simples", summary="Verificar limite do Simples Nacional", status_code=201)
async def verificar_limite_simples(
    dados: VerificacaoLimiteSimplesRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Verifica se empresa está próxima ou além do limite do Simples Nacional.
    """
    return _tax_agent.verificar_limite_simples(
        rbt12=Decimal(str(dados.rbt12)),
    )
