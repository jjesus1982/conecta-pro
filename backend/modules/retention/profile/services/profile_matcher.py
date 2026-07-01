"""
Service de Match de Perfil com Posto.

Calcula compatibilidade entre perfil operacional e requisitos do posto.
"""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from modules.retention.profile.models.profile_models import (
    PERFIL_IDEAL_POR_TIPO,
    OperationalProfile,
)
from modules.retention.profile.repositories.profile_repository import ProfileRepository
from modules.retention.profile.schemas.profile_schemas import (
    BestFuncionariosResponse,
    BestMatchesResponse,
    IdealProfileByType,
    MatchNivelEnum,
    PostMatchDetail,
    PostMatchResponse,
    PostTypeEnum,
    PostTypesResponse,
)

logger = logging.getLogger(__name__)


# Descricoes dos tipos de posto
TIPO_POSTO_DESCRICOES = {
    "cftv": "Monitoramento por cameras - exige atencao constante e observacao de detalhes",
    "portaria": "Controle de acesso - exige comunicacao clara e bom relacionamento interpessoal",
    "recepcao": "Atendimento ao publico - exige excelente comunicacao e cordialidade",
    "ronda": "Patrulhamento de areas - exige observacao aguada e resistencia fisica",
    "evento": "Seguranca de eventos - exige resiliencia sob pressao e adaptabilidade",
    "supervisor": "Gestao de equipe - exige lideranca e capacidade de tomada de decisao",
    "controle_acesso": "Controle de acesso - exige triagem cuidadosa, observacao e postura preventiva",
    "porteiro": "Portaria e controle de acesso - exige comunicacao, observacao e presenca constante",
}

# Requisitos principais por tipo
REQUISITOS_PRINCIPAIS = {
    "cftv": [
        "Alta capacidade de concentracao",
        "Atencao aos detalhes visuais",
        "Resistencia a monotonia",
    ],
    "portaria": [
        "Boa comunicacao verbal",
        "Cordialidade no atendimento",
        "Organizacao e controle",
    ],
    "recepcao": [
        "Excelente comunicacao",
        "Empatia e paciencia",
        "Apresentacao pessoal",
    ],
    "ronda": [
        "Boa condicao fisica",
        "Observacao do ambiente",
        "Proatividade",
    ],
    "evento": [
        "Resiliencia sob pressao",
        "Adaptabilidade rapida",
        "Trabalho em equipe",
    ],
    "supervisor": [
        "Lideranca de equipe",
        "Tomada de decisao",
        "Comunicacao efetiva",
    ],
    "controle_acesso": [
        "Controle emocional",
        "Triagem criteriosa",
        "Discernimento",
    ],
    "porteiro": [
        "Observacao constante",
        "Postura preventiva",
        "Cumprimento de procedimentos",
    ],
}


class ProfileMatcher:
    """Service para calculo de match entre perfil e posto."""

    def __init__(self, session: AsyncSession):
        """Inicializa o service."""
        self.session = session
        self.repository = ProfileRepository(session)

    # ============================================================
    # Calculo de Match
    # ============================================================

    async def calcular_match(
        self,
        funcionario_id: str,
        posto_id: str,
        posto_tipo: str,
        condominium_id: str | None = None,
    ) -> PostMatchDetail:
        """
        Calcula match entre funcionario e posto.

        Formula: 100 - (soma das diferencas absolutas / 4)

        Args:
            funcionario_id: UUID do funcionario
            posto_id: UUID do posto
            posto_tipo: Tipo do posto
            condominium_id: UUID do condominio

        Returns:
            Match calculado com analise

        Raises:
            ValueError: Se funcionario nao tem perfil ou tipo invalido
        """
        # Busca perfil do funcionario
        profile = await self.repository.get_latest_profile(funcionario_id)
        if not profile:
            raise ValueError(f"Funcionario {funcionario_id} nao possui perfil operacional avaliado")

        # Valida tipo de posto
        posto_tipo_lower = posto_tipo.lower()
        if posto_tipo_lower not in PERFIL_IDEAL_POR_TIPO:
            raise ValueError(
                f"Tipo de posto invalido: {posto_tipo}. Tipos validos: {', '.join(PERFIL_IDEAL_POR_TIPO.keys())}"
            )

        # Calcula score
        score = self._calcular_score_match(profile, posto_tipo_lower)

        # Analisa fatores
        fatores_positivos, fatores_negativos = self._analisar_fatores(profile, posto_tipo_lower)

        # Scores detalhados
        scores_detalhados = self._calcular_scores_detalhados(profile, posto_tipo_lower)

        # Gap analysis
        gap_analysis = self._calcular_gap(profile, posto_tipo_lower)

        # Sugestoes
        sugestoes = self._gerar_sugestoes_desenvolvimento(profile, posto_tipo_lower)

        # Probabilidade de sucesso (baseada no score e fatores)
        prob_sucesso = self._calcular_probabilidade_sucesso(score, len(fatores_positivos), len(fatores_negativos))

        # Salva/atualiza match no banco
        match = await self.repository.create_match(
            funcionario_id=funcionario_id,
            posto_id=posto_id,
            posto_tipo=posto_tipo_lower,
            score_match=score,
            profile_id=profile.id,
            fatores_positivos=fatores_positivos,
            fatores_negativos=fatores_negativos,
            scores_detalhados=scores_detalhados,
            condominium_id=condominium_id,
        )

        await self.session.commit()

        logger.info(
            f"Match calculado: funcionario {funcionario_id} -> posto {posto_id}",
            extra={
                "score": score,
                "nivel": match.nivel_match,
                "recomendado": match.recomendado,
            },
        )

        return PostMatchDetail(
            id=match.id,
            funcionario_id=match.funcionario_id,
            posto_id=match.posto_id,
            posto_tipo=PostTypeEnum(match.posto_tipo),
            profile_id=match.profile_id,
            score_match=match.score_match,
            fatores_positivos=match.fatores_positivos,
            fatores_negativos=match.fatores_negativos,
            scores_detalhados=match.scores_detalhados,
            recomendado=match.recomendado,
            nivel_match=MatchNivelEnum(match.nivel_match),
            calculado_em=match.calculado_em,
            valido_ate=match.valido_ate,
            condominium_id=match.condominium_id,
            created_at=match.created_at,
            analise_dimensoes=self._build_analise_dimensoes(profile, posto_tipo_lower),
            gap_analysis=gap_analysis,
            sugestoes_desenvolvimento=sugestoes,
            probabilidade_sucesso=prob_sucesso,
        )

    def _calcular_score_match(self, profile: OperationalProfile, posto_tipo: str) -> float:
        """
        Calcula score de compatibilidade.

        Formula: 100 - (soma das diferencas absolutas / 4)

        Args:
            profile: Perfil do funcionario
            posto_tipo: Tipo do posto

        Returns:
            Score de 0 a 100
        """
        perfil_ideal = PERFIL_IDEAL_POR_TIPO[posto_tipo]
        perfil_funcionario = profile.scores

        soma_diferencas = 0
        for dimensao, valor_ideal in perfil_ideal.items():
            valor_funcionario = perfil_funcionario.get(dimensao, 0)
            diferenca = abs(valor_ideal - valor_funcionario)
            soma_diferencas += diferenca

        # Formula: 100 - (soma / 4)
        # Maximo de diferenca por dimensao = 100
        # Soma maxima = 400, media = 100
        # Score minimo = 0, maximo = 100
        score = 100 - (soma_diferencas / 4)
        return max(0, min(100, round(score, 2)))

    def _analisar_fatores(self, profile: OperationalProfile, posto_tipo: str) -> tuple[list[str], list[str]]:
        """
        Analisa fatores positivos e negativos do match.

        Args:
            profile: Perfil do funcionario
            posto_tipo: Tipo do posto

        Returns:
            Tuple (fatores_positivos, fatores_negativos)
        """
        perfil_ideal = PERFIL_IDEAL_POR_TIPO[posto_tipo]
        perfil_funcionario = profile.scores

        fatores_positivos = []
        fatores_negativos = []

        dimensao_nomes = {
            "vigilancia": "Vigilancia e Observacao",
            "comunicacao": "Comunicacao Interpessoal",
            "resiliencia": "Resiliencia e Controle Emocional",
            "lideranca": "Lideranca e Iniciativa",
        }

        for dimensao, valor_ideal in perfil_ideal.items():
            valor_funcionario = perfil_funcionario.get(dimensao, 0)
            nome_dimensao = dimensao_nomes.get(dimensao, dimensao.capitalize())

            diferenca = valor_funcionario - valor_ideal

            if diferenca >= 10:
                # Funcionario supera o ideal em 10+ pontos
                fatores_positivos.append(f"{nome_dimensao}: score {valor_funcionario} supera o ideal ({valor_ideal})")
            elif diferenca >= -5:
                # Funcionario dentro da margem aceitavel (-5 a +10)
                if valor_ideal >= 70:  # Dimensao importante para o posto
                    fatores_positivos.append(
                        f"{nome_dimensao}: score {valor_funcionario} atende ao requisito ({valor_ideal})"
                    )
            elif diferenca >= -20:
                # Diferenca moderada (-20 a -5)
                if valor_ideal >= 70:  # Dimensao importante
                    fatores_negativos.append(
                        f"{nome_dimensao}: score {valor_funcionario} abaixo do ideal ({valor_ideal}) - desenvolvimento recomendado"
                    )
            else:
                # Diferenca significativa (> 20 pontos abaixo)
                fatores_negativos.append(
                    f"{nome_dimensao}: gap significativo (score {valor_funcionario} vs ideal {valor_ideal})"
                )

        # Adiciona fator do perfil predominante se compativel
        predominante = profile.perfil_predominante
        dimensoes_importantes = [d for d, v in perfil_ideal.items() if v >= 80]
        if predominante in dimensoes_importantes:
            fatores_positivos.insert(0, f"Perfil predominante ({predominante}) alinhado com requisitos do posto")

        return fatores_positivos, fatores_negativos

    def _calcular_scores_detalhados(self, profile: OperationalProfile, posto_tipo: str) -> dict[str, Any]:
        """
        Calcula scores detalhados por dimensao.

        Args:
            profile: Perfil do funcionario
            posto_tipo: Tipo do posto

        Returns:
            Dict com detalhes por dimensao
        """
        perfil_ideal = PERFIL_IDEAL_POR_TIPO[posto_tipo]
        perfil_funcionario = profile.scores

        detalhes = {}
        for dimensao in ["vigilancia", "comunicacao", "resiliencia", "lideranca"]:
            valor_ideal = perfil_ideal.get(dimensao, 50)
            valor_funcionario = perfil_funcionario.get(dimensao, 0)
            diferenca = valor_funcionario - valor_ideal

            # Score da dimensao (0-100 baseado na proximidade)
            score_dimensao = max(0, 100 - abs(diferenca))

            detalhes[dimensao] = {
                "score_funcionario": valor_funcionario,
                "score_ideal": valor_ideal,
                "diferenca": diferenca,
                "score_match": score_dimensao,
                "status": self._get_status_dimensao(diferenca, valor_ideal),
            }

        return detalhes

    def _get_status_dimensao(self, diferenca: int, valor_ideal: int) -> str:
        """Determina status da dimensao no match."""
        if diferenca >= 10:
            return "excelente"
        elif diferenca >= -5:
            return "adequado"
        elif diferenca >= -20:
            return "desenvolver"
        else:
            return "critico"

    def _calcular_gap(self, profile: OperationalProfile, posto_tipo: str) -> dict[str, int]:
        """
        Calcula gap entre perfil e ideal.

        Args:
            profile: Perfil do funcionario
            posto_tipo: Tipo do posto

        Returns:
            Dict {dimensao: diferenca}
        """
        perfil_ideal = PERFIL_IDEAL_POR_TIPO[posto_tipo]
        perfil_funcionario = profile.scores

        return {
            dimensao: perfil_funcionario.get(dimensao, 0) - valor_ideal
            for dimensao, valor_ideal in perfil_ideal.items()
        }

    def _gerar_sugestoes_desenvolvimento(self, profile: OperationalProfile, posto_tipo: str) -> list[str]:
        """
        Gera sugestoes de desenvolvimento para melhorar o match.

        Args:
            profile: Perfil do funcionario
            posto_tipo: Tipo do posto

        Returns:
            Lista de sugestoes
        """
        perfil_ideal = PERFIL_IDEAL_POR_TIPO[posto_tipo]
        perfil_funcionario = profile.scores

        sugestoes = []

        # Sugestoes por gap
        gaps = []
        for dimensao, valor_ideal in perfil_ideal.items():
            valor_funcionario = perfil_funcionario.get(dimensao, 0)
            gap = valor_ideal - valor_funcionario
            if gap > 10:  # Gap significativo
                gaps.append((dimensao, gap))

        # Ordena por gap (maior primeiro)
        gaps.sort(key=lambda x: x[1], reverse=True)

        sugestoes_por_dimensao = {
            "vigilancia": [
                "Exercicios de atencao focada e mindfulness",
                "Treinamento em tecnicas de observacao",
                "Pratica com simuladores de monitoramento",
            ],
            "comunicacao": [
                "Curso de comunicacao assertiva",
                "Treinamento em atendimento ao cliente",
                "Pratica de escuta ativa",
            ],
            "resiliencia": [
                "Treinamento em gestao de estresse",
                "Tecnicas de inteligencia emocional",
                "Simulacoes de situacoes de pressao",
            ],
            "lideranca": [
                "Programa de desenvolvimento de lideranca",
                "Mentoria com supervisores experientes",
                "Treinamento em tomada de decisao",
            ],
        }

        for dimensao, gap in gaps[:2]:  # Top 2 gaps
            sugestoes_dimensao = sugestoes_por_dimensao.get(dimensao, [])
            if sugestoes_dimensao:
                sugestoes.append(f"{dimensao.capitalize()} (gap de {gap} pontos): {sugestoes_dimensao[0]}")

        if not sugestoes:
            sugestoes.append("Perfil bem alinhado com requisitos do posto - manter desenvolvimento continuo")

        return sugestoes

    def _calcular_probabilidade_sucesso(self, score: float, n_positivos: int, n_negativos: int) -> float:
        """
        Calcula probabilidade estimada de sucesso no posto.

        Args:
            score: Score de match
            n_positivos: Numero de fatores positivos
            n_negativos: Numero de fatores negativos

        Returns:
            Probabilidade de 0 a 100
        """
        # Base no score
        prob = score

        # Ajuste por fatores
        prob += n_positivos * 2
        prob -= n_negativos * 3

        return max(0, min(100, round(prob, 1)))

    def _build_analise_dimensoes(self, profile: OperationalProfile, posto_tipo: str) -> list[dict[str, Any]]:
        """
        Constroi analise detalhada por dimensao.

        Args:
            profile: Perfil do funcionario
            posto_tipo: Tipo do posto

        Returns:
            Lista de analises por dimensao
        """
        perfil_ideal = PERFIL_IDEAL_POR_TIPO[posto_tipo]
        perfil_funcionario = profile.scores

        analises = []
        for dimensao in ["vigilancia", "comunicacao", "resiliencia", "lideranca"]:
            valor_ideal = perfil_ideal.get(dimensao, 50)
            valor_funcionario = perfil_funcionario.get(dimensao, 0)
            diferenca = valor_funcionario - valor_ideal

            importancia = "alta" if valor_ideal >= 80 else "media" if valor_ideal >= 60 else "baixa"

            analises.append(
                {
                    "dimensao": dimensao,
                    "score_funcionario": valor_funcionario,
                    "score_ideal": valor_ideal,
                    "diferenca": diferenca,
                    "importancia_para_posto": importancia,
                    "avaliacao": self._get_status_dimensao(diferenca, valor_ideal),
                }
            )

        return analises

    # ============================================================
    # Busca de Melhores Matches
    # ============================================================

    async def encontrar_melhores_postos(
        self,
        funcionario_id: str,
        limit: int = 10,
        condominium_id: str | None = None,
    ) -> BestMatchesResponse:
        """
        Encontra melhores postos para um funcionario.

        Calcula match com todos os tipos de posto e retorna os melhores.

        Args:
            funcionario_id: UUID do funcionario
            limit: Limite de resultados
            condominium_id: UUID do condominio

        Returns:
            Melhores matches ordenados por score
        """
        # Busca perfil
        profile = await self.repository.get_latest_profile(funcionario_id)
        if not profile:
            raise ValueError(f"Funcionario {funcionario_id} nao possui perfil operacional")

        # Calcula match para cada tipo de posto
        matches_calculados = []
        for posto_tipo in PERFIL_IDEAL_POR_TIPO.keys():
            score = self._calcular_score_match(profile, posto_tipo)
            fatores_positivos, fatores_negativos = self._analisar_fatores(profile, posto_tipo)

            nivel = "excelente" if score >= 85 else "alto" if score >= 70 else "medio" if score >= 50 else "baixo"
            recomendado = score >= 70

            matches_calculados.append(
                {
                    "posto_tipo": posto_tipo,
                    "score": score,
                    "nivel": nivel,
                    "recomendado": recomendado,
                    "fatores_positivos": fatores_positivos,
                    "fatores_negativos": fatores_negativos,
                }
            )

        # Ordena por score
        matches_calculados.sort(key=lambda x: x["score"], reverse=True)

        # Busca matches salvos do repositorio
        matches_salvos = await self.repository.get_matches_by_funcionario(funcionario_id, limit)

        # Converte para response
        matches_response = []
        for m in matches_salvos[:limit]:
            matches_response.append(
                PostMatchResponse(
                    id=m.id,
                    funcionario_id=m.funcionario_id,
                    posto_id=m.posto_id,
                    posto_tipo=PostTypeEnum(m.posto_tipo),
                    profile_id=m.profile_id,
                    score_match=m.score_match,
                    fatores_positivos=m.fatores_positivos,
                    fatores_negativos=m.fatores_negativos,
                    scores_detalhados=m.scores_detalhados,
                    recomendado=m.recomendado,
                    nivel_match=MatchNivelEnum(m.nivel_match),
                    calculado_em=m.calculado_em,
                    valido_ate=m.valido_ate,
                    condominium_id=m.condominium_id,
                    created_at=m.created_at,
                )
            )

        # Identifica melhor e pior tipo
        melhor_tipo = PostTypeEnum(matches_calculados[0]["posto_tipo"]) if matches_calculados else None
        pior_tipo = PostTypeEnum(matches_calculados[-1]["posto_tipo"]) if matches_calculados else None

        return BestMatchesResponse(
            funcionario_id=funcionario_id,
            matches=matches_response,
            total=len(matches_response),
            melhor_tipo_posto=melhor_tipo,
            pior_tipo_posto=pior_tipo,
        )

    async def encontrar_melhores_funcionarios(
        self,
        posto_id: str,
        posto_tipo: str,
        limit: int = 10,
    ) -> BestFuncionariosResponse:
        """
        Encontra melhores funcionarios para um posto.

        Args:
            posto_id: UUID do posto
            posto_tipo: Tipo do posto
            limit: Limite de resultados

        Returns:
            Melhores funcionarios ordenados por match
        """
        posto_tipo_lower = posto_tipo.lower()
        if posto_tipo_lower not in PERFIL_IDEAL_POR_TIPO:
            raise ValueError(f"Tipo de posto invalido: {posto_tipo}")

        # Busca matches existentes
        matches = await self.repository.get_matches_by_posto(posto_id, limit)

        matches_response = []
        total_score = 0

        for m in matches:
            matches_response.append(
                PostMatchResponse(
                    id=m.id,
                    funcionario_id=m.funcionario_id,
                    posto_id=m.posto_id,
                    posto_tipo=PostTypeEnum(m.posto_tipo),
                    profile_id=m.profile_id,
                    score_match=m.score_match,
                    fatores_positivos=m.fatores_positivos,
                    fatores_negativos=m.fatores_negativos,
                    scores_detalhados=m.scores_detalhados,
                    recomendado=m.recomendado,
                    nivel_match=MatchNivelEnum(m.nivel_match),
                    calculado_em=m.calculado_em,
                    valido_ate=m.valido_ate,
                    condominium_id=m.condominium_id,
                    created_at=m.created_at,
                )
            )
            total_score += m.score_match

        media_match = total_score / len(matches) if matches else 0

        return BestFuncionariosResponse(
            posto_id=posto_id,
            posto_tipo=PostTypeEnum(posto_tipo_lower),
            matches=matches_response,
            total=len(matches_response),
            media_match=round(media_match, 2),
        )

    async def get_match(self, funcionario_id: str, posto_id: str) -> PostMatchResponse | None:
        """
        Busca match especifico entre funcionario e posto.

        Args:
            funcionario_id: UUID do funcionario
            posto_id: UUID do posto

        Returns:
            Match ou None
        """
        match = await self.repository.get_match(funcionario_id, posto_id)
        if not match:
            return None

        return PostMatchResponse(
            id=match.id,
            funcionario_id=match.funcionario_id,
            posto_id=match.posto_id,
            posto_tipo=PostTypeEnum(match.posto_tipo),
            profile_id=match.profile_id,
            score_match=match.score_match,
            fatores_positivos=match.fatores_positivos,
            fatores_negativos=match.fatores_negativos,
            scores_detalhados=match.scores_detalhados,
            recomendado=match.recomendado,
            nivel_match=MatchNivelEnum(match.nivel_match),
            calculado_em=match.calculado_em,
            valido_ate=match.valido_ate,
            condominium_id=match.condominium_id,
            created_at=match.created_at,
        )

    # ============================================================
    # Tipos de Posto
    # ============================================================

    def get_tipos_posto(self) -> PostTypesResponse:
        """
        Retorna todos os tipos de posto com perfis ideais.

        Returns:
            Lista de tipos com descricoes
        """
        tipos = []
        for tipo, perfil in PERFIL_IDEAL_POR_TIPO.items():
            tipos.append(
                IdealProfileByType(
                    tipo=PostTypeEnum(tipo),
                    perfil_ideal=perfil,
                    descricao=TIPO_POSTO_DESCRICOES.get(tipo, ""),
                    requisitos_principais=REQUISITOS_PRINCIPAIS.get(tipo, []),
                )
            )

        return PostTypesResponse(
            tipos=tipos,
            total=len(tipos),
        )

    async def recalcular_matches(self, funcionario_id: str, condominium_id: str | None = None) -> int:
        """
        Recalcula todos os matches de um funcionario.

        Util apos nova avaliacao de perfil.

        Args:
            funcionario_id: UUID do funcionario
            condominium_id: UUID do condominio

        Returns:
            Numero de matches recalculados
        """
        # Busca perfil atualizado
        profile = await self.repository.get_latest_profile(funcionario_id)
        if not profile:
            return 0

        # Busca matches existentes
        matches = await self.repository.get_matches_by_funcionario(funcionario_id, limit=100)

        count = 0
        for match in matches:
            # Recalcula score
            score = self._calcular_score_match(profile, match.posto_tipo)
            fatores_pos, fatores_neg = self._analisar_fatores(profile, match.posto_tipo)

            # Atualiza match
            await self.repository.create_match(
                funcionario_id=funcionario_id,
                posto_id=match.posto_id,
                posto_tipo=match.posto_tipo,
                score_match=score,
                profile_id=profile.id,
                fatores_positivos=fatores_pos,
                fatores_negativos=fatores_neg,
                scores_detalhados=self._calcular_scores_detalhados(profile, match.posto_tipo),
                condominium_id=condominium_id,
            )
            count += 1

        await self.session.commit()

        logger.info(
            f"Recalculados {count} matches para funcionario {funcionario_id}",
            extra={"profile_id": profile.id},
        )

        return count
