"""
Service de Perfil Operacional.

Logica de negocio para processamento de questionarios e gestao de perfis.
"""

import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from modules.retention.profile.models.profile_models import (
    QUESTIONARIO_PERFIL,
    OperationalProfile,
)
from modules.retention.profile.repositories.profile_repository import ProfileRepository
from modules.retention.profile.schemas.profile_schemas import (
    DashboardResponse,
    DashboardStats,
    DimensionScore,
    OperationalProfileDetail,
    OperationalProfileHistory,
    OperationalProfileResponse,
    PostMatchResponse,
    ProfileDimensionEnum,
    ProfileDistribution,
    ProfileFilter,
    ProfileQuestionResponse,
    ProgressResponse,
    QuestionnaireResponse,
    SaveProgressRequest,
    SubmitRespostasRequest,
)

logger = logging.getLogger(__name__)


# Descricoes das dimensoes
DIMENSAO_DESCRICOES = {
    "vigilancia": "Capacidade de observacao, atencao aos detalhes e foco prolongado",
    "comunicacao": "Habilidades interpessoais, empatia e clareza na comunicacao",
    "resiliencia": "Capacidade de lidar com pressao, estresse e recuperacao emocional",
    "lideranca": "Iniciativa, capacidade de motivar outros e tomar decisoes",
}

# Descricoes dos niveis
NIVEL_DESCRICOES = {
    "baixo": "Nivel inicial - area com potencial de desenvolvimento",
    "medio": "Nivel adequado - atende requisitos basicos",
    "alto": "Nivel destacado - supera a maioria dos requisitos",
    "excelente": "Nivel excepcional - referencia na area",
}

# Tipos de posto recomendados por dimensao forte
TIPOS_POSTO_POR_DIMENSAO = {
    "vigilancia": ["cftv", "ronda", "controle_acesso", "porteiro"],
    "comunicacao": ["portaria", "recepcao"],
    "resiliencia": ["evento", "controle_acesso", "supervisor"],
    "lideranca": ["supervisor", "evento"],
}


class ProfileService:
    """Service para operacoes de perfil operacional."""

    def __init__(self, session: AsyncSession):
        """Inicializa o service."""
        self.session = session
        self.repository = ProfileRepository(session)

    # ============================================================
    # Questionario
    # ============================================================

    async def get_questionario(
        self,
        versao: str = "1.0.0",
        condominium_id: str | None = None,
    ) -> QuestionnaireResponse:
        """
        Retorna questionario completo para avaliacao.

        Args:
            versao: Versao do questionario
            condominium_id: ID do condominio para customizacoes

        Returns:
            Questionario com perguntas ativas
        """
        # Tenta buscar perguntas do banco
        perguntas = await self.repository.get_questions(versao, condominium_id)

        # Se nao houver, usa as default e popula o banco
        if not perguntas:
            await self.repository.seed_default_questions()
            await self.session.commit()
            perguntas = await self.repository.get_questions(versao, condominium_id)

            # Se ainda nao houver, cria respostas a partir do QUESTIONARIO_PERFIL
            if not perguntas:
                perguntas_response = [
                    ProfileQuestionResponse(
                        id=f"default-{q['id']}",
                        codigo=q["id"],
                        texto=q["texto"],
                        dimensao=ProfileDimensionEnum(q["dimensao"]),
                        ordem=q["ordem"],
                        peso=1.0,
                        ativo=True,
                        versao=versao,
                        condominium_id=None,
                        created_at=datetime.utcnow(),
                        updated_at=None,
                    )
                    for q in QUESTIONARIO_PERFIL
                ]

                return QuestionnaireResponse(
                    perguntas=perguntas_response,
                    total_perguntas=len(perguntas_response),
                    versao=versao,
                    dimensoes=["vigilancia", "comunicacao", "resiliencia", "lideranca"],
                )

        perguntas_response = [ProfileQuestionResponse.model_validate(p) for p in perguntas]

        return QuestionnaireResponse(
            perguntas=perguntas_response,
            total_perguntas=len(perguntas_response),
            versao=versao,
            dimensoes=["vigilancia", "comunicacao", "resiliencia", "lideranca"],
        )

    async def save_progress(self, data: SaveProgressRequest) -> ProgressResponse:
        """
        Salva progresso parcial do questionario.

        Args:
            data: Dados de progresso

        Returns:
            Status do progresso
        """
        await self.repository.save_progress(
            funcionario_id=data.funcionario_id,
            respostas_parciais=data.respostas_parciais,
            ultima_pergunta=data.ultima_pergunta,
            condominium_id=data.condominium_id,
        )
        await self.session.commit()

        return ProgressResponse(
            funcionario_id=data.funcionario_id,
            respostas_salvas=data.respostas_parciais,
            ultima_pergunta=data.ultima_pergunta,
            total_perguntas=20,
            percentual_completo=(data.ultima_pergunta / 20) * 100,
            em_andamento=True,
        )

    async def get_progress(self, funcionario_id: str) -> ProgressResponse | None:
        """
        Busca progresso salvo do funcionario.

        Args:
            funcionario_id: UUID do funcionario

        Returns:
            Progresso ou None
        """
        profile = await self.repository.get_progress(funcionario_id)
        if not profile:
            return None

        return ProgressResponse(
            funcionario_id=funcionario_id,
            respostas_salvas=profile.progresso_respostas or {},
            ultima_pergunta=profile.ultima_pergunta_respondida or 0,
            total_perguntas=20,
            percentual_completo=((profile.ultima_pergunta_respondida or 0) / 20) * 100,
            em_andamento=True,
        )

    # ============================================================
    # Processamento de Respostas
    # ============================================================

    async def processar_respostas(self, data: SubmitRespostasRequest) -> OperationalProfileDetail:
        """
        Processa respostas do questionario e calcula perfil.

        Args:
            data: Respostas submetidas

        Returns:
            Perfil calculado com analise

        Raises:
            ValueError: Se respostas invalidas
        """
        # Valida respostas
        self._validar_respostas(data.respostas)

        # Calcula scores por dimensao
        scores = self._calcular_scores(data.respostas)

        # Cria perfil no banco
        profile = await self.repository.create_profile(
            funcionario_id=data.funcionario_id,
            scores=scores,
            respostas=data.respostas,
            tempo_resposta=data.tempo_resposta_segundos,
            condominium_id=data.condominium_id,
        )

        # Remove progresso se existir
        await self.repository.delete_progress(data.funcionario_id)

        await self.session.commit()

        logger.info(
            f"Perfil processado para funcionario {data.funcionario_id}",
            extra={
                "profile_id": profile.id,
                "scores": scores,
                "perfil_predominante": profile.perfil_predominante,
            },
        )

        # Retorna analise detalhada
        return await self._build_profile_detail(profile)

    def _validar_respostas(self, respostas: dict[str, int]) -> None:
        """
        Valida respostas do questionario.

        Args:
            respostas: Dict {pergunta_id: valor}

        Raises:
            ValueError: Se respostas invalidas
        """
        perguntas_esperadas = {q["id"] for q in QUESTIONARIO_PERFIL}

        # Verifica se tem todas as perguntas
        respostas_ids = set(respostas.keys())

        faltando = perguntas_esperadas - respostas_ids
        if faltando:
            raise ValueError(f"Perguntas faltando: {', '.join(sorted(faltando))}")

        # Valida valores
        for pergunta_id, valor in respostas.items():
            if valor < 1 or valor > 4:
                raise ValueError(f"Valor invalido para {pergunta_id}: {valor}. Deve estar entre 1 e 4")

    def _calcular_scores(self, respostas: dict[str, int]) -> dict[str, int]:
        """
        Calcula scores por dimensao.

        Formula: media das respostas * 25 (resulta em 0-100)

        Args:
            respostas: Dict {pergunta_id: valor}

        Returns:
            Dict {dimensao: score}
        """
        # Agrupa respostas por dimensao
        dimensoes: dict[str, list[int]] = {
            "vigilancia": [],
            "comunicacao": [],
            "resiliencia": [],
            "lideranca": [],
        }

        for pergunta in QUESTIONARIO_PERFIL:
            pergunta_id = pergunta["id"]
            dimensao = pergunta["dimensao"]
            if pergunta_id in respostas:
                dimensoes[dimensao].append(respostas[pergunta_id])

        # Calcula score por dimensao
        scores = {}
        for dimensao, valores in dimensoes.items():
            if valores:
                media = sum(valores) / len(valores)
                # Converte escala 1-4 para 0-100
                # media 1.0 -> score 25, media 4.0 -> score 100
                score = int(media * 25)
                scores[dimensao] = min(100, max(0, score))
            else:
                scores[dimensao] = 0

        return scores

    # ============================================================
    # Busca e Listagem
    # ============================================================

    async def get_profile_by_id(self, profile_id: str) -> OperationalProfileDetail | None:
        """
        Busca perfil por ID com analise detalhada.

        Args:
            profile_id: UUID do perfil

        Returns:
            Perfil detalhado ou None
        """
        profile = await self.repository.get_profile_by_id(profile_id)
        if not profile:
            return None
        return await self._build_profile_detail(profile)

    async def get_latest_profile(self, funcionario_id: str) -> OperationalProfileDetail | None:
        """
        Busca perfil mais recente do funcionario.

        Args:
            funcionario_id: UUID do funcionario

        Returns:
            Perfil detalhado ou None
        """
        profile = await self.repository.get_latest_profile(funcionario_id)
        if not profile:
            return None
        return await self._build_profile_detail(profile)

    async def get_profile_history(
        self,
        funcionario_id: str,
        limit: int = 10,
    ) -> OperationalProfileHistory:
        """
        Busca historico de perfis do funcionario.

        Args:
            funcionario_id: UUID do funcionario
            limit: Limite de resultados

        Returns:
            Historico com evolucao
        """
        profiles = await self.repository.get_profile_history(funcionario_id, limit)

        profiles_response = [
            OperationalProfileResponse(
                id=p.id,
                funcionario_id=p.funcionario_id,
                data_avaliacao=p.data_avaliacao,
                vigilancia=p.vigilancia,
                comunicacao=p.comunicacao,
                resiliencia=p.resiliencia,
                lideranca=p.lideranca,
                perfil_predominante=ProfileDimensionEnum(p.perfil_predominante),
                versao_questionario=p.versao_questionario,
                tempo_resposta_segundos=p.tempo_resposta_segundos,
                is_valid=p.is_valid,
                invalidation_reason=p.invalidation_reason,
                condominium_id=p.condominium_id,
                created_at=p.created_at,
                updated_at=p.updated_at,
                score_medio=p.score_medio,
                dimensao_mais_fraca=p.dimensao_mais_fraca,
            )
            for p in profiles
        ]

        # Calcula evolucao por dimensao
        evolucao = {
            "vigilancia": [],
            "comunicacao": [],
            "resiliencia": [],
            "lideranca": [],
        }

        for p in reversed(profiles):  # Do mais antigo para mais recente
            data_str = p.data_avaliacao.isoformat()
            evolucao["vigilancia"].append({"data": data_str, "score": p.vigilancia})
            evolucao["comunicacao"].append({"data": data_str, "score": p.comunicacao})
            evolucao["resiliencia"].append({"data": data_str, "score": p.resiliencia})
            evolucao["lideranca"].append({"data": data_str, "score": p.lideranca})

        return OperationalProfileHistory(
            profiles=profiles_response,
            total=len(profiles),
            evolucao=evolucao,
        )

    async def list_profiles(
        self,
        filters: ProfileFilter | None = None,
        skip: int = 0,
        limit: int = 20,
        order_by: str = "created_at",
        order_desc: bool = True,
    ) -> tuple[list[OperationalProfileResponse], int]:
        """
        Lista perfis com filtros.

        Args:
            filters: Filtros opcionais
            skip: Offset
            limit: Limite
            order_by: Campo para ordenacao
            order_desc: Ordem descendente

        Returns:
            Tuple (lista, total)
        """
        profiles, total = await self.repository.list_profiles(filters, skip, limit, order_by, order_desc)

        profiles_response = [
            OperationalProfileResponse(
                id=p.id,
                funcionario_id=p.funcionario_id,
                data_avaliacao=p.data_avaliacao,
                vigilancia=p.vigilancia,
                comunicacao=p.comunicacao,
                resiliencia=p.resiliencia,
                lideranca=p.lideranca,
                perfil_predominante=ProfileDimensionEnum(p.perfil_predominante),
                versao_questionario=p.versao_questionario,
                tempo_resposta_segundos=p.tempo_resposta_segundos,
                is_valid=p.is_valid,
                invalidation_reason=p.invalidation_reason,
                condominium_id=p.condominium_id,
                created_at=p.created_at,
                updated_at=p.updated_at,
                score_medio=p.score_medio,
                dimensao_mais_fraca=p.dimensao_mais_fraca,
            )
            for p in profiles
        ]

        return profiles_response, total

    # ============================================================
    # Dashboard
    # ============================================================

    async def get_dashboard(self, condominium_id: str | None = None) -> DashboardResponse:
        """
        Retorna dados do dashboard de perfis.

        Args:
            condominium_id: Filtrar por condominio

        Returns:
            Dados do dashboard
        """
        # Estatisticas gerais
        stats_raw = await self.repository.get_stats(condominium_id)

        # Distribuicao de scores
        distribuicao_scores = [
            ProfileDistribution(
                dimensao=ProfileDimensionEnum.VIGILANCIA,
                media=round(stats_raw.get("media_vigilancia", 0), 1),
                minimo=0,
                maximo=100,
                desvio_padrao=round(stats_raw.get("desvio_vigilancia", 0), 1),
                total_avaliados=stats_raw.get("total_avaliacoes", 0),
            ),
            ProfileDistribution(
                dimensao=ProfileDimensionEnum.COMUNICACAO,
                media=round(stats_raw.get("media_comunicacao", 0), 1),
                minimo=0,
                maximo=100,
                desvio_padrao=round(stats_raw.get("desvio_comunicacao", 0), 1),
                total_avaliados=stats_raw.get("total_avaliacoes", 0),
            ),
            ProfileDistribution(
                dimensao=ProfileDimensionEnum.RESILIENCIA,
                media=round(stats_raw.get("media_resiliencia", 0), 1),
                minimo=0,
                maximo=100,
                desvio_padrao=round(stats_raw.get("desvio_resiliencia", 0), 1),
                total_avaliados=stats_raw.get("total_avaliacoes", 0),
            ),
            ProfileDistribution(
                dimensao=ProfileDimensionEnum.LIDERANCA,
                media=round(stats_raw.get("media_lideranca", 0), 1),
                minimo=0,
                maximo=100,
                desvio_padrao=round(stats_raw.get("desvio_lideranca", 0), 1),
                total_avaliados=stats_raw.get("total_avaliacoes", 0),
            ),
        ]

        # Evolucao mensal
        evolucao = await self.repository.get_evolucao_mensal(12, condominium_id)

        # Top matches (placeholder - seria integrado com ProfileMatcher)
        top_matches: list[PostMatchResponse] = []

        stats = DashboardStats(
            total_avaliacoes=stats_raw.get("total_avaliacoes", 0),
            avaliacoes_mes=stats_raw.get("avaliacoes_mes", 0),
            avaliacoes_semana=stats_raw.get("avaliacoes_semana", 0),
            media_score_geral=round(stats_raw.get("media_geral", 0), 1),
            distribuicao_perfis=stats_raw.get("distribuicao_perfis", {}),
            distribuicao_scores=distribuicao_scores,
            top_matches=top_matches,
            funcionarios_sem_perfil=0,  # Seria calculado com lista de funcionarios
            evolucao_mensal=evolucao,
        )

        # Alertas e recomendacoes
        alertas = []
        recomendacoes = []

        if stats.total_avaliacoes == 0:
            alertas.append("Nenhuma avaliacao de perfil realizada ainda")
            recomendacoes.append("Inicie o processo de avaliacao com os funcionarios")
        elif stats.avaliacoes_mes < stats.total_avaliacoes * 0.1:
            alertas.append("Poucas avaliacoes realizadas este mes")
            recomendacoes.append("Considere reavaliar funcionarios sem avaliacao recente")

        # Verifica dimensoes com media baixa
        for dist in distribuicao_scores:
            if dist.media < 50:
                alertas.append(f"Media de {dist.dimensao.value} abaixo de 50: {dist.media:.1f}")
                recomendacoes.append(f"Considere treinamentos para desenvolver {dist.dimensao.value}")

        return DashboardResponse(
            stats=stats,
            alertas=alertas,
            recomendacoes=recomendacoes,
            ultima_atualizacao=datetime.utcnow(),
        )

    # ============================================================
    # Helpers
    # ============================================================

    async def _build_profile_detail(self, profile: OperationalProfile) -> OperationalProfileDetail:
        """
        Constroi resposta detalhada do perfil com analise.

        Args:
            profile: Modelo do perfil

        Returns:
            Perfil com analise completa
        """

        def get_nivel(score: int) -> str:
            if score >= 85:
                return "excelente"
            elif score >= 70:
                return "alto"
            elif score >= 50:
                return "medio"
            else:
                return "baixo"

        # Scores detalhados por dimensao
        scores_detalhados = [
            DimensionScore(
                dimensao=ProfileDimensionEnum.VIGILANCIA,
                score=profile.vigilancia,
                nivel=get_nivel(profile.vigilancia),
                descricao=DIMENSAO_DESCRICOES["vigilancia"],
            ),
            DimensionScore(
                dimensao=ProfileDimensionEnum.COMUNICACAO,
                score=profile.comunicacao,
                nivel=get_nivel(profile.comunicacao),
                descricao=DIMENSAO_DESCRICOES["comunicacao"],
            ),
            DimensionScore(
                dimensao=ProfileDimensionEnum.RESILIENCIA,
                score=profile.resiliencia,
                nivel=get_nivel(profile.resiliencia),
                descricao=DIMENSAO_DESCRICOES["resiliencia"],
            ),
            DimensionScore(
                dimensao=ProfileDimensionEnum.LIDERANCA,
                score=profile.lideranca,
                nivel=get_nivel(profile.lideranca),
                descricao=DIMENSAO_DESCRICOES["lideranca"],
            ),
        ]

        # Dados para grafico radar
        radar_chart_data = {
            "vigilancia": profile.vigilancia,
            "comunicacao": profile.comunicacao,
            "resiliencia": profile.resiliencia,
            "lideranca": profile.lideranca,
        }

        # Pontos fortes (scores >= 70)
        pontos_fortes = []
        for ds in scores_detalhados:
            if ds.score >= 70:
                pontos_fortes.append(f"{ds.dimensao.value.capitalize()}: {ds.descricao}")

        # Pontos a desenvolver (scores < 50)
        pontos_desenvolvimento = []
        for ds in scores_detalhados:
            if ds.score < 50:
                pontos_desenvolvimento.append(f"{ds.dimensao.value.capitalize()}: {ds.descricao}")

        # Recomendacoes baseadas no perfil
        recomendacoes = self._gerar_recomendacoes(profile)

        # Tipos de posto recomendados
        tipos_recomendados = self._identificar_tipos_posto(profile)

        return OperationalProfileDetail(
            id=profile.id,
            funcionario_id=profile.funcionario_id,
            data_avaliacao=profile.data_avaliacao,
            vigilancia=profile.vigilancia,
            comunicacao=profile.comunicacao,
            resiliencia=profile.resiliencia,
            lideranca=profile.lideranca,
            perfil_predominante=ProfileDimensionEnum(profile.perfil_predominante),
            versao_questionario=profile.versao_questionario,
            tempo_resposta_segundos=profile.tempo_resposta_segundos,
            is_valid=profile.is_valid,
            invalidation_reason=profile.invalidation_reason,
            condominium_id=profile.condominium_id,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
            score_medio=profile.score_medio,
            dimensao_mais_fraca=profile.dimensao_mais_fraca,
            scores_detalhados=scores_detalhados,
            radar_chart_data=radar_chart_data,
            recomendacoes=recomendacoes,
            pontos_fortes=pontos_fortes,
            pontos_desenvolvimento=pontos_desenvolvimento,
            tipos_posto_recomendados=tipos_recomendados,
        )

    def _gerar_recomendacoes(self, profile: OperationalProfile) -> list[str]:
        """Gera recomendacoes baseadas no perfil."""
        recomendacoes = []
        scores = profile.scores

        # Recomendacoes por dimensao fraca
        for dimensao, score in scores.items():
            if score < 50:
                if dimensao == "vigilancia":
                    recomendacoes.append("Treinamento em tecnicas de observacao e atencao concentrada")
                elif dimensao == "comunicacao":
                    recomendacoes.append("Desenvolvimento de habilidades interpessoais e comunicacao assertiva")
                elif dimensao == "resiliencia":
                    recomendacoes.append("Treinamento em gestao de estresse e inteligencia emocional")
                elif dimensao == "lideranca":
                    recomendacoes.append("Programa de desenvolvimento de lideranca e tomada de decisao")

        # Recomendacao geral baseada no perfil predominante
        predominante = profile.perfil_predominante
        if predominante == "vigilancia":
            recomendacoes.append("Considerar alocacao em postos de monitoramento ou CFTV")
        elif predominante == "comunicacao":
            recomendacoes.append("Considerar alocacao em portaria ou recepcao")
        elif predominante == "resiliencia":
            recomendacoes.append("Considerar alocacao em eventos ou situacoes de alta pressao")
        elif predominante == "lideranca":
            recomendacoes.append("Avaliar potencial para cargo de supervisao")

        return recomendacoes

    def _identificar_tipos_posto(self, profile: OperationalProfile) -> list[str]:
        """Identifica tipos de posto mais adequados ao perfil."""
        tipos_recomendados = []

        # Ordena dimensoes por score
        scores = profile.scores
        dimensoes_ordenadas = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        # Adiciona tipos baseado nas dimensoes mais fortes
        for dimensao, score in dimensoes_ordenadas[:2]:  # Top 2 dimensoes
            if score >= 60:  # Apenas se score razoavel
                tipos = TIPOS_POSTO_POR_DIMENSAO.get(dimensao, [])
                for tipo in tipos:
                    if tipo not in tipos_recomendados:
                        tipos_recomendados.append(tipo)

        return tipos_recomendados[:5]  # Limita a 5 tipos
