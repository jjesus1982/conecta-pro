"""Service para o módulo de Empresas (Multi-CNPJ)."""

import logging
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.empresas.models.empresa import RegimeTributarioEnum
from modules.empresas.repositories.empresa_repository import EmpresaRepository
from modules.empresas.schemas.empresa_schemas import (
    EmpresaCreate,
    EmpresaListResponse,
    EmpresaResponse,
    EmpresaUpdate,
    LiminarCreate,
    LiminarResponse,
    LiminarUpdate,
    SimulacaoRegime,
    SugestaoEmpresaFaturamento,
)

logger = logging.getLogger(__name__)

_DEFAULT_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")


async def _resolve_condominio_id(db: AsyncSession, condominio_id: UUID) -> UUID:
    """
    Resolve o condominio_id real do banco de dados.

    Em sistemas single-tenant, o get_tenant_id() retorna um UUID padrão que não
    existe na tabela condominios. Nesse caso, buscamos o primeiro condominio real.
    """
    if condominio_id == _DEFAULT_TENANT_ID:
        result = await db.execute(text("SELECT id FROM condominios LIMIT 1"))
        row = result.fetchone()
        if row:
            return UUID(str(row[0]))
    return condominio_id


# Mapeamento tipo_servico → slug da empresa sugerida
_SERVICOS_PATRIMONIAL = {
    "vigilancia",
    "portaria_presencial",
    "portaria_24h",
    "portaria_12x36",
    "limpeza",
    "jardinagem",
    "facilities",
    "recepcao",
    "zeladoria",
}

_SERVICOS_ELETRONICA = {
    "portaria_remota",
    "monitoramento",
    "cftv",
    "alarmes",
    "controle_acesso",
    "automacao",
    "seguranca_eletronica",
}

# Tabela Simples Nacional Anexo III — alíquotas efetivas por faixa de receita bruta acumulada (12 meses)
# (Lei Complementar 123/2006 — Resolução CGSN 140/2018)
_SIMPLES_ANEXO_III = [
    (180_000.00, 0.06, 0.00),
    (360_000.00, 0.112, 9_360.00),
    (720_000.00, 0.135, 17_640.00),
    (1_800_000.00, 0.16, 35_640.00),
    (3_600_000.00, 0.21, 125_640.00),
    (4_800_000.00, 0.33, 648_000.00),
]


def _calcular_aliquota_simples_anexo_iii(faturamento_anual: float) -> float:
    """Calcula alíquota efetiva do Simples Nacional Anexo III."""
    for limite, nominal, deducao in _SIMPLES_ANEXO_III:
        if faturamento_anual <= limite:
            return (faturamento_anual * nominal - deducao) / faturamento_anual
    # Acima do limite → Lucro Presumido (desenquadrado)
    return 0.33


def _calcular_impostos(regime: str, faturamento_anual: float) -> float:
    """Calcula carga tributária estimada para o regime e faturamento dados."""
    if regime == RegimeTributarioEnum.SIMPLES_NACIONAL.value:
        aliq = _calcular_aliquota_simples_anexo_iii(faturamento_anual)
        return faturamento_anual * aliq
    elif regime == RegimeTributarioEnum.LUCRO_PRESUMIDO.value:
        # IRPJ 8% presunção × 15% + 10% adicional; CSLL 32% × 9%; PIS 0.65%; COFINS 3%; ISS 5%
        irpj = faturamento_anual * 0.08 * 0.15
        irpj_adicional = max(0, (faturamento_anual * 0.08 - 60_000) * 0.10)
        csll = faturamento_anual * 0.32 * 0.09
        pis = faturamento_anual * 0.0065
        cofins = faturamento_anual * 0.03
        iss = faturamento_anual * 0.05
        return irpj + irpj_adicional + csll + pis + cofins + iss
    elif regime == RegimeTributarioEnum.LUCRO_REAL.value:
        # IRPJ 15% + 10% adicional sobre lucro estimado; CSLL 9%; PIS 1.65%; COFINS 7.6%; ISS 5%
        lucro_estimado = faturamento_anual * 0.15  # margem estimada 15%
        irpj = lucro_estimado * 0.15
        irpj_adicional = max(0, (lucro_estimado - 60_000) * 0.10)
        csll = lucro_estimado * 0.09
        pis = faturamento_anual * 0.0165
        cofins = faturamento_anual * 0.076
        iss = faturamento_anual * 0.05
        return irpj + irpj_adicional + csll + pis + cofins + iss
    elif regime == RegimeTributarioEnum.MEI.value:
        return min(faturamento_anual * 0.05, 7_200.0)
    return faturamento_anual * 0.30


# ===================================================================
# SERVICE METHODS
# ===================================================================


async def criar_empresa(
    db: AsyncSession,
    dados: EmpresaCreate,
    condominio_id: UUID,
) -> EmpresaResponse:
    """Cria uma nova empresa para o tenant."""
    condominio_id = await _resolve_condominio_id(db, condominio_id)
    repo = EmpresaRepository(db)

    # Verifica duplicidade de CNPJ
    if dados.cnpj:
        existente = await repo.obter_empresa_por_cnpj(dados.cnpj, condominio_id)
        if existente:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Já existe uma empresa com o CNPJ {dados.cnpj}",
            )

    # Verifica duplicidade de slug
    existente_slug = await repo.obter_empresa_por_slug(dados.slug, condominio_id)
    if existente_slug:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Já existe uma empresa com o slug '{dados.slug}'",
        )

    payload = dados.model_dump(exclude_none=True)
    # Converter enums para string
    for campo in ("regime_tributario", "anexo_simples", "regime_futuro", "status"):
        if campo in payload and payload[campo] is not None:
            val = payload[campo]
            payload[campo] = val.value if hasattr(val, "value") else str(val)

    empresa = await repo.criar_empresa(payload, condominio_id)
    await db.commit()
    await db.refresh(empresa, attribute_names=["liminares"])
    return EmpresaResponse.model_validate(empresa)


async def listar_empresas(
    db: AsyncSession,
    condominio_id: UUID,
    status_filtro: str | None = None,
) -> list[EmpresaListResponse]:
    """Lista empresas do tenant."""
    condominio_id = await _resolve_condominio_id(db, condominio_id)
    repo = EmpresaRepository(db)
    empresas = await repo.listar_empresas(condominio_id, status=status_filtro)
    return [EmpresaListResponse.model_validate(e) for e in empresas]


async def obter_empresa(
    db: AsyncSession,
    empresa_id: UUID,
    condominio_id: UUID,
) -> EmpresaResponse:
    """Obtém empresa por ID."""
    condominio_id = await _resolve_condominio_id(db, condominio_id)
    repo = EmpresaRepository(db)
    empresa = await repo.obter_empresa(empresa_id, condominio_id)
    if not empresa:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Empresa não encontrada",
        )
    return EmpresaResponse.model_validate(empresa)


async def atualizar_empresa(
    db: AsyncSession,
    empresa_id: UUID,
    dados: EmpresaUpdate,
    condominio_id: UUID,
) -> EmpresaResponse:
    """Atualiza dados de uma empresa."""
    condominio_id = await _resolve_condominio_id(db, condominio_id)
    repo = EmpresaRepository(db)
    payload = dados.model_dump(exclude_none=True)
    # Converter enums para string
    for campo in ("regime_tributario", "anexo_simples", "regime_futuro", "status"):
        if campo in payload and payload[campo] is not None:
            val = payload[campo]
            payload[campo] = val.value if hasattr(val, "value") else str(val)

    empresa = await repo.atualizar_empresa(empresa_id, payload, condominio_id)
    if not empresa:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Empresa não encontrada",
        )
    await db.commit()
    await db.refresh(empresa, attribute_names=["liminares"])
    return EmpresaResponse.model_validate(empresa)


async def sugerir_empresa_para_servico(
    db: AsyncSession,
    tipo_servico: str,
    condominio_id: UUID,
) -> SugestaoEmpresaFaturamento:
    """Sugere a empresa mais adequada para um tipo de serviço."""
    condominio_id = await _resolve_condominio_id(db, condominio_id)
    repo = EmpresaRepository(db)

    if tipo_servico in _SERVICOS_PATRIMONIAL:
        slug_alvo = "conecta_patrimonial"
        motivo = (
            f"Serviço '{tipo_servico}' é operacional/humano — indicado para a empresa "
            "de segurança patrimonial (Simples Nacional Anexo III)."
        )
    elif tipo_servico in _SERVICOS_ELETRONICA:
        slug_alvo = "conecta_eletronica"
        motivo = (
            f"Serviço '{tipo_servico}' é tecnológico/eletrônico — indicado para a Conecta Mais Eletrônica (Lucro Real)."
        )
    else:
        # Serviço desconhecido: retorna empresa principal
        empresas = await repo.listar_empresas(condominio_id)
        principal = next((e for e in empresas if e.is_principal), None)
        if not principal:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Nenhuma empresa principal cadastrada",
            )
        return SugestaoEmpresaFaturamento(
            empresa_id=principal.id,
            slug=principal.slug,
            razao_social=principal.razao_social,
            motivo=f"Tipo de serviço '{tipo_servico}' não mapeado. Empresa principal sugerida.",
            carga_tributaria_estimada=0.30,
            economia_potencial=0.0,
        )

    empresa = await repo.obter_empresa_por_slug(slug_alvo, condominio_id)
    if not empresa:
        # Fallback: empresa principal
        empresas = await repo.listar_empresas(condominio_id)
        empresa = next((e for e in empresas if e.is_principal), None)
        if not empresa:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Empresa sugerida não encontrada",
            )

    # Estimativa de carga tributária com faturamento referência (R$ 1.200.000/ano)
    faturamento_ref = 1_200_000.0
    carga = _calcular_impostos(empresa.regime_tributario, faturamento_ref) / faturamento_ref
    # Economia potencial vs pior cenário (Lucro Real)
    carga_lr = _calcular_impostos(RegimeTributarioEnum.LUCRO_REAL.value, faturamento_ref) / faturamento_ref
    economia = max(0.0, (carga_lr - carga) * faturamento_ref)

    return SugestaoEmpresaFaturamento(
        empresa_id=empresa.id,
        slug=empresa.slug,
        razao_social=empresa.razao_social,
        motivo=motivo,
        carga_tributaria_estimada=round(carga, 4),
        economia_potencial=round(economia, 2),
    )


async def simular_mudanca_regime(
    db: AsyncSession,
    empresa_id: UUID,
    novo_regime: str,
    faturamento_anual: float,
    condominio_id: UUID,
) -> SimulacaoRegime:
    """Simula mudança de regime tributário calculando impostos e economia."""
    condominio_id = await _resolve_condominio_id(db, condominio_id)
    repo = EmpresaRepository(db)
    empresa = await repo.obter_empresa(empresa_id, condominio_id)
    if not empresa:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Empresa não encontrada",
        )

    impostos_atual = _calcular_impostos(empresa.regime_tributario, faturamento_anual)
    impostos_simulado = _calcular_impostos(novo_regime, faturamento_anual)
    economia = impostos_atual - impostos_simulado

    if economia > 0:
        recomendacao = (
            f"Recomendado migrar para {novo_regime.replace('_', ' ').title()}. "
            f"Economia estimada de R$ {economia:,.2f}/ano ({economia / faturamento_anual * 100:.1f}% do faturamento)."
        )
    elif economia < 0:
        recomendacao = (
            f"Não recomendado. O regime {novo_regime.replace('_', ' ').title()} seria "
            f"R$ {abs(economia):,.2f}/ano mais caro que o regime atual."
        )
    else:
        recomendacao = "Os regimes apresentam carga tributária equivalente para este faturamento."

    return SimulacaoRegime(
        empresa_id=empresa.id,
        regime_atual=empresa.regime_tributario,
        regime_simulado=novo_regime,
        faturamento_anual=faturamento_anual,
        impostos_regime_atual=round(impostos_atual, 2),
        impostos_regime_simulado=round(impostos_simulado, 2),
        economia_anual=round(economia, 2),
        recomendacao=recomendacao,
    )


async def cadastrar_liminar(
    db: AsyncSession,
    empresa_id: UUID,
    dados: LiminarCreate,
    condominio_id: UUID,
) -> LiminarResponse:
    """Cadastra uma nova liminar para a empresa."""
    condominio_id = await _resolve_condominio_id(db, condominio_id)
    repo = EmpresaRepository(db)
    # Valida que empresa pertence ao tenant
    empresa = await repo.obter_empresa(empresa_id, condominio_id)
    if not empresa:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Empresa não encontrada",
        )

    payload = dados.model_dump(exclude_none=True)
    for campo in ("tipo", "status"):
        if campo in payload and payload[campo] is not None:
            val = payload[campo]
            payload[campo] = val.value if hasattr(val, "value") else str(val)

    liminar = await repo.criar_liminar(empresa_id, payload)
    await db.commit()
    await db.refresh(liminar)
    return LiminarResponse.model_validate(liminar)


async def listar_liminares(
    db: AsyncSession,
    empresa_id: UUID,
    condominio_id: UUID,
) -> list[LiminarResponse]:
    """Lista liminares de uma empresa."""
    condominio_id = await _resolve_condominio_id(db, condominio_id)
    repo = EmpresaRepository(db)
    empresa = await repo.obter_empresa(empresa_id, condominio_id)
    if not empresa:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Empresa não encontrada",
        )
    liminares = await repo.listar_liminares(empresa_id)
    return [LiminarResponse.model_validate(lim) for lim in liminares]


async def atualizar_liminar(
    db: AsyncSession,
    empresa_id: UUID,
    liminar_id: UUID,
    dados: LiminarUpdate,
    condominio_id: UUID,
) -> LiminarResponse:
    """Atualiza dados de uma liminar."""
    condominio_id = await _resolve_condominio_id(db, condominio_id)
    repo = EmpresaRepository(db)
    # Valida que empresa pertence ao tenant
    empresa = await repo.obter_empresa(empresa_id, condominio_id)
    if not empresa:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Empresa não encontrada",
        )

    payload = dados.model_dump(exclude_none=True)
    for campo in ("tipo", "status"):
        if campo in payload and payload[campo] is not None:
            val = payload[campo]
            payload[campo] = val.value if hasattr(val, "value") else str(val)

    liminar = await repo.atualizar_liminar(liminar_id, payload)
    if not liminar:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Liminar não encontrada",
        )
    await db.commit()
    await db.refresh(liminar)
    return LiminarResponse.model_validate(liminar)


async def verificar_liminares_ativas(
    db: AsyncSession,
    empresa_id: UUID,
    condominio_id: UUID,
) -> list[LiminarResponse]:
    """Retorna liminares ativas (concedidas) de uma empresa."""
    condominio_id = await _resolve_condominio_id(db, condominio_id)
    repo = EmpresaRepository(db)
    empresa = await repo.obter_empresa(empresa_id, condominio_id)
    if not empresa:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Empresa não encontrada",
        )
    liminares = await repo.liminares_ativas(empresa_id)
    return [LiminarResponse.model_validate(lim) for lim in liminares]


async def aplicar_liminares_calculo(
    db: AsyncSession,
    empresa_id: UUID,
    calculo: dict[str, Any],
    condominio_id: UUID,
) -> dict[str, Any]:
    """Aplica efeitos das liminares ativas a um cálculo fiscal."""
    condominio_id = await _resolve_condominio_id(db, condominio_id)
    repo = EmpresaRepository(db)
    empresa = await repo.obter_empresa(empresa_id, condominio_id)
    if not empresa:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Empresa não encontrada",
        )

    liminares = await repo.liminares_ativas(empresa_id)
    resultado = dict(calculo)
    liminares_aplicadas = []

    for liminar in liminares:
        efeitos = liminar.efeitos or {}

        if "pis" in efeitos:
            resultado["pis"] = efeitos["pis"]
        if "cofins" in efeitos:
            resultado["cofins"] = efeitos["cofins"]
        if "inss_retido" in efeitos:
            resultado["inss_retido"] = efeitos["inss_retido"]
        if "aliquota_retencao" in efeitos:
            resultado["aliquota_retencao"] = efeitos["aliquota_retencao"]
        if "iss" in efeitos:
            resultado["iss"] = efeitos["iss"]

        liminares_aplicadas.append(
            {
                "id": str(liminar.id),
                "tipo": liminar.tipo,
                "descricao": liminar.descricao,
                "efeitos_aplicados": efeitos,
            }
        )

    resultado["liminares_aplicadas"] = liminares_aplicadas
    return resultado
