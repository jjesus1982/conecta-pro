"""
Controller Fiscal para Diaristas.

Fornece endpoints para:
- Cálculo de retenções
- Geração de RPA
- Consulta de documentos
- Relatórios fiscais
"""

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.operacional.diaristas.models.documento_fiscal import (
    StatusDocumentoFiscal,
    TipoDocumentoFiscal,
)
from modules.operacional.diaristas.services.fiscal_service import (
    get_fiscal_service,
)

router = APIRouter()


# =============================================================================
# SCHEMAS
# =============================================================================


class CalculoRetencoesRequest(BaseModel):
    """Request para calcular retenções."""

    valor_bruto: Decimal = Field(..., gt=0, description="Valor bruto do serviço")
    dependentes: int = Field(0, ge=0, description="Número de dependentes (IRRF)")
    aliquota_iss: Decimal | None = Field(None, ge=0, le=5, description="Alíquota ISS (%)")


class RetencaoResponse(BaseModel):
    """Response de uma retenção."""

    base_calculo: float
    aliquota: float
    valor: float


class RetencoesResponse(BaseModel):
    """Response completo de retenções."""

    valor_bruto: float
    inss: RetencaoResponse
    irrf: dict[str, Any]
    iss: RetencaoResponse
    total_retencoes: float
    valor_liquido: float


class GerarRPARequest(BaseModel):
    """Request para gerar RPA."""

    diarist_id: UUID
    payment_id: UUID | None = None
    valor_bruto: Decimal | None = Field(None, gt=0)
    competencia: str | None = Field(None, pattern=r"^\d{4}-\d{2}$")
    descricao_servico: str = Field("Prestação de serviços de limpeza e conservação", max_length=500)
    codigo_servico: str = Field("7.10", max_length=20)
    dependentes: int = Field(0, ge=0)
    aliquota_iss: Decimal | None = Field(None)
    tomador_cnpj: str | None = Field(None, max_length=18)
    tomador_razao_social: str | None = Field(None, max_length=200)


class DocumentoFiscalResponse(BaseModel):
    """Response de documento fiscal."""

    id: str
    numero: str
    tipo: str
    status: str
    competencia: str
    data_emissao: str
    valor_bruto: float
    valor_inss: float
    valor_iss: float
    valor_irrf: float
    valor_liquido: float
    prestador_nome: str
    prestador_cpf: str


class RelatorioRetencoesResponse(BaseModel):
    """Response de relatório de retenções."""

    periodo: dict[str, str]
    totais: dict[str, float]
    documentos: int


# =============================================================================
# ENDPOINTS - CÁLCULOS
# =============================================================================


@router.post(
    "/calcular-retencoes",
    response_model=RetencoesResponse,
    summary="Calcular retenções",
    description="Calcula todas as retenções fiscais (INSS, ISS, IRRF, status_code=201)",
)
async def calcular_retencoes(
    request: CalculoRetencoesRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
):
    """
    Calcula todas as retenções fiscais para um valor.

    Retenções calculadas:
    - **INSS**: 11% sobre o valor até o teto (autônomo)
    - **ISS**: 2% a 5% sobre o valor (varia por município)
    - **IRRF**: Tabela progressiva após dedução do INSS

    O cálculo segue a legislação brasileira vigente.
    """
    service = get_fiscal_service(db)

    try:
        resultado = await service.calcular_todas_retencoes(
            valor_bruto=request.valor_bruto,
            dependentes=request.dependentes,
            aliquota_iss=request.aliquota_iss,
        )

        return {
            "valor_bruto": float(resultado["valor_bruto"]),
            "inss": {
                "base_calculo": float(resultado["inss"]["base_calculo"]),
                "aliquota": float(resultado["inss"]["aliquota"]),
                "valor": float(resultado["inss"]["valor"]),
            },
            "irrf": {
                "base_calculo": float(resultado["irrf"]["base_calculo"]),
                "aliquota": float(resultado["irrf"]["aliquota"]),
                "valor": float(resultado["irrf"]["valor"]),
                "deducao_tabela": float(resultado["irrf"]["deducao_tabela"]),
                "dependentes": resultado["irrf"]["dependentes"],
            },
            "iss": {
                "base_calculo": float(resultado["iss"]["base_calculo"]),
                "aliquota": float(resultado["iss"]["aliquota"]),
                "valor": float(resultado["iss"]["valor"]),
            },
            "total_retencoes": float(resultado["total_retencoes"]),
            "valor_liquido": float(resultado["valor_liquido"]),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao calcular retenções: {str(e)}"
        )


@router.get(
    "/simular/{valor_bruto}", summary="Simular retenções", description="Simulação rápida de retenções para um valor"
)
async def simular_retencoes(
    valor_bruto: Decimal,
    current_user: CurrentActiveUser,
    dependentes: int = Query(0, ge=0),
    aliquota_iss: Decimal | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Simulação rápida de retenções."""
    service = get_fiscal_service(db)

    resultado = await service.calcular_todas_retencoes(
        valor_bruto=valor_bruto,
        dependentes=dependentes,
        aliquota_iss=aliquota_iss,
    )

    return {
        "valor_bruto": f"R$ {float(resultado['valor_bruto']):.2f}",
        "retencoes": {
            "INSS": f"R$ {float(resultado['inss']['valor']):.2f}",
            "ISS": f"R$ {float(resultado['iss']['valor']):.2f}",
            "IRRF": f"R$ {float(resultado['irrf']['valor']):.2f}",
        },
        "total_retencoes": f"R$ {float(resultado['total_retencoes']):.2f}",
        "valor_liquido": f"R$ {float(resultado['valor_liquido']):.2f}",
    }


# =============================================================================
# ENDPOINTS - DOCUMENTOS
# =============================================================================


@router.post(
    "/rpa",
    response_model=DocumentoFiscalResponse,
    summary="Gerar RPA",
    description="Gera Recibo de Pagamento Autônomo",
    status_code=201,
)
async def gerar_rpa(
    request: GerarRPARequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
):
    """
    Gera RPA (Recibo de Pagamento Autônomo) para um diarista.

    O RPA é obrigatório para pagamentos a profissionais autônomos
    e deve conter as retenções de INSS, ISS e IRRF quando aplicáveis.
    """
    service = get_fiscal_service(db)

    try:
        documento = await service.gerar_rpa(
            diarist_id=request.diarist_id,
            payment_id=request.payment_id,
            valor_bruto=request.valor_bruto,
            competencia=request.competencia,
            descricao_servico=request.descricao_servico,
            codigo_servico=request.codigo_servico,
            dependentes=request.dependentes,
            aliquota_iss=request.aliquota_iss,
            tomador_cnpj=request.tomador_cnpj,
            tomador_razao_social=request.tomador_razao_social,
        )

        return {
            "id": str(documento.id),
            "numero": documento.numero,
            "tipo": documento.tipo.value,
            "status": documento.status.value,
            "competencia": documento.competencia,
            "data_emissao": documento.data_emissao.isoformat(),
            "valor_bruto": float(documento.valor_bruto),
            "valor_inss": float(documento.valor_inss),
            "valor_iss": float(documento.valor_iss),
            "valor_irrf": float(documento.valor_irrf),
            "valor_liquido": float(documento.valor_liquido),
            "prestador_nome": documento.prestador_nome,
            "prestador_cpf": documento.prestador_cpf,
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao gerar RPA: {str(e)}")


@router.get(
    "/documentos",
    response_model=list[DocumentoFiscalResponse],
    summary="Listar documentos",
    description="Lista documentos fiscais com filtros",
)
async def listar_documentos(
    current_user: CurrentActiveUser,
    diarist_id: UUID | None = Query(None),
    tipo: TipoDocumentoFiscal | None = Query(None),
    competencia: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    status_filter: StatusDocumentoFiscal | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Lista documentos fiscais."""
    service = get_fiscal_service(db)

    try:
        documentos = await service.listar_documentos(
            diarist_id=diarist_id,
            tipo=tipo,
            competencia=competencia,
            status=status_filter,
            limit=limit,
        )

        return [
            {
                "id": str(doc.id),
                "numero": doc.numero,
                "tipo": doc.tipo.value,
                "status": doc.status.value,
                "competencia": doc.competencia,
                "data_emissao": doc.data_emissao.isoformat(),
                "valor_bruto": float(doc.valor_bruto),
                "valor_inss": float(doc.valor_inss),
                "valor_iss": float(doc.valor_iss),
                "valor_irrf": float(doc.valor_irrf),
                "valor_liquido": float(doc.valor_liquido),
                "prestador_nome": doc.prestador_nome,
                "prestador_cpf": doc.prestador_cpf,
            }
            for doc in documentos
        ]

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao listar documentos: {str(e)}"
        )


@router.get(
    "/documentos/{documento_id}", summary="Obter documento", description="Retorna detalhes de um documento fiscal"
)
async def get_documento(
    documento_id: UUID,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
):
    """Retorna detalhes de um documento fiscal."""
    from modules.operacional.diaristas.models.documento_fiscal import DocumentoFiscal

    result = await db.execute(select(DocumentoFiscal).where(DocumentoFiscal.id == documento_id))
    documento = result.scalar_one_or_none()

    if not documento:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Documento não encontrado")

    return {
        "id": str(documento.id),
        "numero": documento.numero,
        "tipo": documento.tipo.value,
        "status": documento.status.value,
        "competencia": documento.competencia,
        "data_emissao": documento.data_emissao.isoformat(),
        "data_pagamento": documento.data_pagamento.isoformat() if documento.data_pagamento else None,
        "valores": {
            "bruto": float(documento.valor_bruto),
            "inss": float(documento.valor_inss),
            "iss": float(documento.valor_iss),
            "irrf": float(documento.valor_irrf),
            "outras_retencoes": float(documento.valor_outras_retencoes),
            "liquido": float(documento.valor_liquido),
        },
        "prestador": {
            "cpf": documento.prestador_cpf,
            "nome": documento.prestador_nome,
            "endereco": documento.prestador_endereco,
            "municipio": documento.prestador_municipio,
            "uf": documento.prestador_uf,
            "pis": documento.prestador_pis,
        },
        "tomador": {
            "cnpj": documento.tomador_cnpj,
            "razao_social": documento.tomador_razao_social,
            "endereco": documento.tomador_endereco,
        },
        "servico": {
            "descricao": documento.descricao_servico,
            "codigo": documento.codigo_servico,
            "cnae": documento.cnae,
        },
        "calculos": {
            "inss": {
                "base_calculo": float(documento.base_calculo_inss) if documento.base_calculo_inss else None,
                "aliquota": float(documento.aliquota_inss) if documento.aliquota_inss else None,
            },
            "iss": {
                "base_calculo": float(documento.base_calculo_iss) if documento.base_calculo_iss else None,
                "aliquota": float(documento.aliquota_iss) if documento.aliquota_iss else None,
            },
            "irrf": {
                "base_calculo": float(documento.base_calculo_irrf) if documento.base_calculo_irrf else None,
                "aliquota": float(documento.aliquota_irrf) if documento.aliquota_irrf else None,
            },
        },
        "pdf_url": documento.pdf_url,
        "observacoes": documento.observacoes,
    }


# =============================================================================
# ENDPOINTS - RELATÓRIOS
# =============================================================================


@router.get(
    "/relatorio/retencoes",
    response_model=RelatorioRetencoesResponse,
    summary="Relatório de retenções",
    description="Gera relatório de retenções por período",
)
async def relatorio_retencoes(
    current_user: CurrentActiveUser,
    data_inicio: date = Query(..., description="Data inicial"),
    data_fim: date = Query(..., description="Data final"),
    diarist_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Gera relatório de retenções por período.

    Útil para:
    - Conciliação fiscal
    - Declarações de imposto
    - Controle de obrigações acessórias
    """
    if data_fim < data_inicio:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Data fim deve ser maior ou igual a data início"
        )

    service = get_fiscal_service(db)

    try:
        relatorio = await service.relatorio_retencoes_periodo(
            data_inicio=data_inicio,
            data_fim=data_fim,
            diarist_id=diarist_id,
        )
        return relatorio

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao gerar relatório: {str(e)}"
        )


@router.get(
    "/relatorio/diarista/{diarist_id}",
    summary="Relatório do diarista",
    description="Relatório fiscal consolidado de um diarista",
)
async def relatorio_diarista(
    diarist_id: UUID,
    current_user: CurrentActiveUser,
    ano: int = Query(..., ge=2020, le=2030),
    db: AsyncSession = Depends(get_db),
):
    """Relatório fiscal consolidado de um diarista para um ano."""
    from modules.operacional.diaristas.models.documento_fiscal import DocumentoFiscal

    # Buscar todos os documentos do ano
    result = await db.execute(
        select(DocumentoFiscal)
        .where(
            DocumentoFiscal.diarist_id == diarist_id,
            DocumentoFiscal.is_active,
            DocumentoFiscal.competencia.like(f"{ano}-%"),
        )
        .order_by(DocumentoFiscal.competencia)
    )
    documentos = list(result.scalars().all())

    # Agrupar por mês
    por_mes = {}
    totais = {
        "bruto": Decimal("0"),
        "inss": Decimal("0"),
        "iss": Decimal("0"),
        "irrf": Decimal("0"),
        "liquido": Decimal("0"),
    }

    for doc in documentos:
        mes = doc.competencia
        if mes not in por_mes:
            por_mes[mes] = {
                "documentos": 0,
                "bruto": Decimal("0"),
                "inss": Decimal("0"),
                "iss": Decimal("0"),
                "irrf": Decimal("0"),
                "liquido": Decimal("0"),
            }

        por_mes[mes]["documentos"] += 1
        por_mes[mes]["bruto"] += doc.valor_bruto
        por_mes[mes]["inss"] += doc.valor_inss
        por_mes[mes]["iss"] += doc.valor_iss
        por_mes[mes]["irrf"] += doc.valor_irrf
        por_mes[mes]["liquido"] += doc.valor_liquido

        totais["bruto"] += doc.valor_bruto
        totais["inss"] += doc.valor_inss
        totais["iss"] += doc.valor_iss
        totais["irrf"] += doc.valor_irrf
        totais["liquido"] += doc.valor_liquido

    return {
        "diarist_id": str(diarist_id),
        "ano": ano,
        "por_mes": {
            mes: {
                "documentos": dados["documentos"],
                "bruto": float(dados["bruto"]),
                "inss": float(dados["inss"]),
                "iss": float(dados["iss"]),
                "irrf": float(dados["irrf"]),
                "liquido": float(dados["liquido"]),
            }
            for mes, dados in por_mes.items()
        },
        "totais": {
            "bruto": float(totais["bruto"]),
            "inss": float(totais["inss"]),
            "iss": float(totais["iss"]),
            "irrf": float(totais["irrf"]),
            "total_retencoes": float(totais["inss"] + totais["iss"] + totais["irrf"]),
            "liquido": float(totais["liquido"]),
        },
        "documentos_total": len(documentos),
    }


# =============================================================================
# ENDPOINTS - TABELAS
# =============================================================================


@router.get("/tabelas/inss", summary="Tabela INSS", description="Retorna tabela INSS vigente (do banco)")
async def get_tabela_inss(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
):
    """Retorna tabela INSS vigente para contribuintes individuais (fonte: tabela_inss no banco)."""
    service = get_fiscal_service(db)
    tabela = await service._get_tabela_inss()  # 422 honesto se não houver vigência cadastrada

    return {
        "vigencia_inicio": tabela["vigencia_inicio"],
        "vigencia_fim": tabela["vigencia_fim"],
        "tipo_contribuinte": "Contribuinte Individual (Autônomo)",
        "aliquota": float(tabela["aliquota_autonomo"]),
        "teto": float(tabela["teto"]),
        "faixas": tabela["faixas"],
        "fonte": "banco de dados (tabela_inss)",
        "observacao": "Alíquota sobre valor até o teto para contribuinte individual",
    }


@router.get("/tabelas/irrf", summary="Tabela IRRF", description="Retorna tabela IRRF vigente (do banco)")
async def get_tabela_irrf(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
):
    """Retorna tabela IRRF vigente (fonte: tabela_irrf no banco)."""
    service = get_fiscal_service(db)
    tabela = await service._get_tabela_irrf()  # 422 honesto se não houver vigência cadastrada

    return {
        "vigencia_inicio": tabela["vigencia_inicio"],
        "vigencia_fim": tabela["vigencia_fim"],
        "faixas": tabela["faixas"],
        "deducao_por_dependente": float(tabela["deducao_dependente"]),
        "fonte": "banco de dados (tabela_irrf)",
    }


@router.get("/codigos-servico", summary="Códigos de serviço", description="Lista códigos de serviço (LC 116/2003)")
async def listar_codigos_servico(current_user: CurrentActiveUser):
    """Lista códigos de serviço relevantes para diaristas."""
    return {
        "codigos": [
            {
                "codigo": "7.10",
                "descricao": "Limpeza, manutenção e conservação de imóveis",
                "padrao": True,
            },
            {
                "codigo": "7.02",
                "descricao": "Limpeza e dragagem de rios, portos, canais, etc",
                "padrao": False,
            },
            {
                "codigo": "7.04",
                "descricao": "Coleta e tratamento de resíduos",
                "padrao": False,
            },
            {
                "codigo": "7.09",
                "descricao": "Varrição, coleta, remoção, etc de resíduos",
                "padrao": False,
            },
            {
                "codigo": "7.11",
                "descricao": "Decoração e jardinagem",
                "padrao": False,
            },
        ],
        "referencia": "Lei Complementar 116/2003",
    }
