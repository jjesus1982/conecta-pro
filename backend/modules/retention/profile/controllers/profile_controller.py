"""
Controller de Perfil Operacional.

Endpoints REST para gestao de perfis operacionais e matches.
"""

import logging
from uuid import UUID  # [Retention] tipar profile_id -> /tipos-posto 500 (uuid cast) vira 422

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_db
from modules.retention.profile.schemas.profile_schemas import (
    BestFuncionariosResponse,
    BestMatchesResponse,
    CalculateMatchRequest,
    # Dashboard
    DashboardResponse,
    IdealProfileByType,
    OperationalProfileDetail,
    OperationalProfileHistory,
    # Perfil
    PostMatchDetail,
    # Match
    PostMatchResponse,
    PostTypeEnum,
    # Tipos de posto
    PostTypesResponse,
    ProfileDimensionEnum,
    ProfileFilter,
    ProfileListResponse,
    ProfileQuestionCreate,
    ProfileQuestionResponse,
    ProfileQuestionUpdate,
    ProgressResponse,
    # Questionario
    QuestionnaireResponse,
    SaveProgressRequest,
    # Respostas
    SubmitRespostasRequest,
)
from modules.retention.profile.services.profile_matcher import ProfileMatcher
from modules.retention.profile.services.profile_service import ProfileService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/retention/profile",
    tags=["Retention - Perfil Operacional"],
)


# ============================================================
# QUESTIONARIO
# ============================================================


@router.get(
    "/questionnaire",
    response_model=QuestionnaireResponse,
    summary="Obter questionario de perfil",
    description="Retorna o questionario completo com 20 perguntas para avaliacao do perfil operacional.",
)
async def get_questionnaire(
    versao: str = Query("1.0.0", description="Versao do questionario"),
    condominium_id: str | None = Query(None, description="ID do condominio para customizacoes"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> QuestionnaireResponse:
    """Retorna questionario de avaliacao de perfil."""
    service = ProfileService(db)
    return await service.get_questionario(versao, condominium_id)


@router.post(
    "/submit",
    response_model=OperationalProfileDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Submeter respostas do questionario",
    description="Processa as respostas do questionario e calcula o perfil operacional.",
)
async def submit_responses(
    data: SubmitRespostasRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> OperationalProfileDetail:
    """
    Processa respostas e calcula perfil operacional.

    Requer todas as 20 perguntas respondidas com valores de 1 a 4.
    """
    service = ProfileService(db)

    try:
        profile = await service.processar_respostas(data)
        return profile
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Erro ao processar respostas: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao processar respostas",
        )


@router.post(
    "/progress",
    response_model=ProgressResponse,
    summary="Salvar progresso do questionario",
    description="Salva o progresso parcial do questionario para continuar depois.",
)
async def save_progress(
    data: SaveProgressRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> ProgressResponse:
    """Salva progresso parcial do questionario."""
    service = ProfileService(db)
    return await service.save_progress(data)


@router.get(
    "/progress/{funcionario_id}",
    response_model=ProgressResponse,
    summary="Obter progresso salvo",
    description="Recupera o progresso salvo do questionario para continuar.",
)
async def get_progress(
    funcionario_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> ProgressResponse:
    """Recupera progresso salvo do questionario."""
    service = ProfileService(db)
    progress = await service.get_progress(funcionario_id)

    if not progress:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nenhum progresso salvo encontrado",
        )

    return progress


# ============================================================
# PERFIL DO FUNCIONARIO
# ============================================================


@router.get(
    "/funcionario/{funcionario_id}",
    response_model=OperationalProfileDetail,
    summary="Obter perfil do funcionario",
    description="Retorna o perfil operacional mais recente do funcionario com analise detalhada.",
)
async def get_funcionario_profile(
    funcionario_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> OperationalProfileDetail:
    """Retorna perfil mais recente do funcionario."""
    service = ProfileService(db)
    profile = await service.get_latest_profile(funcionario_id)

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Perfil nao encontrado para este funcionario",
        )

    return profile


@router.get(
    "/funcionario/{funcionario_id}/historico",
    response_model=OperationalProfileHistory,
    summary="Obter historico de perfis",
    description="Retorna historico de avaliacoes do funcionario com evolucao por dimensao.",
)
async def get_funcionario_history(
    funcionario_id: str,
    limit: int = Query(10, ge=1, le=50, description="Limite de resultados"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> OperationalProfileHistory:
    """Retorna historico de perfis do funcionario."""
    service = ProfileService(db)
    return await service.get_profile_history(funcionario_id, limit)


@router.get(
    "/{profile_id}",
    response_model=OperationalProfileDetail,
    summary="Obter perfil por ID",
    description="Retorna um perfil operacional especifico pelo ID.",
)
async def get_profile_by_id(
    profile_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> OperationalProfileDetail:
    """Retorna perfil por ID."""
    service = ProfileService(db)
    profile = await service.get_profile_by_id(profile_id)

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Perfil nao encontrado",
        )

    return profile


@router.get(
    "/",
    response_model=ProfileListResponse,
    summary="Listar perfis",
    description="Lista perfis operacionais com filtros e paginacao.",
)
async def list_profiles(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    funcionario_id: str | None = None,
    perfil_predominante: ProfileDimensionEnum | None = None,
    score_minimo: int | None = Query(None, ge=0, le=100),
    score_maximo: int | None = Query(None, ge=0, le=100),
    condominium_id: str | None = None,
    apenas_validos: bool = True,
    order_by: str = "created_at",
    order_desc: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> ProfileListResponse:
    """Lista perfis com filtros."""
    service = ProfileService(db)

    filters = ProfileFilter(
        funcionario_id=funcionario_id,
        perfil_predominante=perfil_predominante,
        score_minimo=score_minimo,
        score_maximo=score_maximo,
        condominium_id=condominium_id,
        apenas_validos=apenas_validos,
    )

    profiles, total = await service.list_profiles(filters, skip, limit, order_by, order_desc)

    pages = (total + limit - 1) // limit if limit > 0 else 0

    return ProfileListResponse(
        items=profiles,
        total=total,
        page=(skip // limit) + 1 if limit > 0 else 1,
        page_size=limit,
        pages=pages,
    )


# ============================================================
# MATCH FUNCIONARIO-POSTO
# ============================================================


@router.get(
    "/match/funcionario/{funcionario_id}/postos",
    response_model=BestMatchesResponse,
    summary="Melhores postos para funcionario",
    description="Retorna os postos com melhor compatibilidade para o funcionario.",
)
async def get_best_posts_for_funcionario(
    funcionario_id: str,
    limit: int = Query(10, ge=1, le=50),
    condominium_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> BestMatchesResponse:
    """Encontra melhores postos para o funcionario."""
    matcher = ProfileMatcher(db)

    try:
        return await matcher.encontrar_melhores_postos(funcionario_id, limit, condominium_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/match/posto/{posto_id}/funcionarios",
    response_model=BestFuncionariosResponse,
    summary="Melhores funcionarios para posto",
    description="Retorna os funcionarios com melhor compatibilidade para o posto.",
)
async def get_best_funcionarios_for_post(
    posto_id: str,
    posto_tipo: PostTypeEnum = Query(..., description="Tipo do posto"),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> BestFuncionariosResponse:
    """Encontra melhores funcionarios para o posto."""
    matcher = ProfileMatcher(db)

    try:
        return await matcher.encontrar_melhores_funcionarios(posto_id, posto_tipo.value, limit)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/match/{funcionario_id}/{posto_id}",
    response_model=PostMatchResponse,
    summary="Obter match especifico",
    description="Retorna o match entre um funcionario e um posto especificos.",
)
async def get_specific_match(
    funcionario_id: str,
    posto_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> PostMatchResponse:
    """Retorna match especifico."""
    matcher = ProfileMatcher(db)
    match = await matcher.get_match(funcionario_id, posto_id)

    if not match:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Match nao encontrado",
        )

    return match


@router.post(
    "/match/calculate",
    response_model=PostMatchDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Calcular match",
    description="Calcula a compatibilidade entre um funcionario e um posto.",
)
async def calculate_match(
    data: CalculateMatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> PostMatchDetail:
    """Calcula match entre funcionario e posto."""
    matcher = ProfileMatcher(db)

    try:
        return await matcher.calcular_match(
            funcionario_id=data.funcionario_id,
            posto_id=data.posto_id,
            posto_tipo=data.posto_tipo.value,
            condominium_id=data.condominium_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Erro ao calcular match: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao calcular match",
        )


@router.post(
    "/match/recalculate/{funcionario_id}",
    response_model=dict,
    summary="Recalcular matches do funcionario",
    description="Recalcula todos os matches de um funcionario apos nova avaliacao.",
)
async def recalculate_funcionario_matches(
    funcionario_id: str,
    condominium_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> dict:
    """Recalcula todos os matches do funcionario."""
    matcher = ProfileMatcher(db)

    try:
        count = await matcher.recalcular_matches(funcionario_id, condominium_id)
        return {
            "funcionario_id": funcionario_id,
            "matches_recalculados": count,
            "mensagem": f"{count} matches recalculados com sucesso",
        }
    except Exception as e:
        logger.error(f"Erro ao recalcular matches: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao recalcular matches",
        )


# ============================================================
# TIPOS DE POSTO
# ============================================================


@router.get(
    "/tipos-posto",
    response_model=PostTypesResponse,
    summary="Listar tipos de posto",
    description="Retorna todos os tipos de posto com seus perfis ideais.",
)
async def list_post_types(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> PostTypesResponse:
    """Lista tipos de posto com perfis ideais."""
    matcher = ProfileMatcher(db)
    return matcher.get_tipos_posto()


@router.get(
    "/tipos-posto/{tipo}",
    response_model=IdealProfileByType,
    summary="Obter perfil ideal por tipo",
    description="Retorna o perfil ideal para um tipo de posto especifico.",
)
async def get_ideal_profile_by_type(
    tipo: PostTypeEnum,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> IdealProfileByType:
    """Retorna perfil ideal para tipo de posto."""
    matcher = ProfileMatcher(db)
    tipos = matcher.get_tipos_posto()

    for t in tipos.tipos:
        if t.tipo == tipo:
            return t

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Tipo de posto nao encontrado: {tipo}",
    )


# ============================================================
# DASHBOARD
# ============================================================


@router.get(
    "/dashboard",
    response_model=DashboardResponse,
    summary="Dashboard de perfis",
    description="Retorna estatisticas e metricas do sistema de perfis operacionais.",
)
async def get_dashboard(
    condominium_id: str | None = Query(None, description="Filtrar por condominio"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> DashboardResponse:
    """Retorna dashboard de perfis operacionais."""
    service = ProfileService(db)
    return await service.get_dashboard(condominium_id)


# ============================================================
# ADMIN - GESTAO DE PERGUNTAS
# ============================================================


@router.post(
    "/admin/questions",
    response_model=ProfileQuestionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar pergunta (Admin)",
    description="Cria uma nova pergunta para o questionario.",
)
async def create_question(
    data: ProfileQuestionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> ProfileQuestionResponse:
    """Cria nova pergunta do questionario."""
    from modules.retention.profile.repositories.profile_repository import ProfileRepository

    repository = ProfileRepository(db)

    try:
        question = await repository.create_question(data)
        await db.commit()
        return ProfileQuestionResponse.model_validate(question)
    except Exception as e:
        logger.error(f"Erro ao criar pergunta: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao criar pergunta",
        )


@router.put(
    "/admin/questions/{question_id}",
    response_model=ProfileQuestionResponse,
    summary="Atualizar pergunta (Admin)",
    description="Atualiza uma pergunta existente.",
)
async def update_question(
    question_id: str,
    data: ProfileQuestionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> ProfileQuestionResponse:
    """Atualiza pergunta do questionario."""
    from modules.retention.profile.repositories.profile_repository import ProfileRepository

    repository = ProfileRepository(db)

    question = await repository.update_question(question_id, data)
    if not question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pergunta nao encontrada",
        )

    await db.commit()
    return ProfileQuestionResponse.model_validate(question)


@router.post(
    "/admin/questions/seed",
    response_model=dict,
    summary="Popular perguntas padrao (Admin)",
    description="Popula o banco com as perguntas padrao do questionario.",
)
async def seed_default_questions(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # pylint: disable=unused-argument
) -> dict:
    """Popula perguntas padrao."""
    from modules.retention.profile.repositories.profile_repository import ProfileRepository

    repository = ProfileRepository(db)

    count = await repository.seed_default_questions()
    await db.commit()

    return {
        "perguntas_criadas": count,
        "mensagem": f"{count} perguntas criadas com sucesso" if count > 0 else "Perguntas ja existem",
    }
