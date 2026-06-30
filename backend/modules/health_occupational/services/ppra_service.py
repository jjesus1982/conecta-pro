"""
Service PPRA/PGR (NR-9) - Programa de Prevencao de Riscos Ambientais
====================================================================

Logica de negocio para mapeamento de riscos ocupacionais.
"""

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from modules.health_occupational.models.ppra import (
    ControlMeasure,
    OccupationalRisk,
    RiskLevel,
    RiskMapping,
)
from modules.health_occupational.schemas.ppra import (
    ControlMeasureRequest,
    ControlMeasureUpdateRequest,
    OccupationalRiskRequest,
    RiskMappingRequest,
    RiskMappingUpdateRequest,
)

logger = logging.getLogger(__name__)


# Mapeamento de EPIs recomendados por categoria de risco
EPI_RECOMMENDATIONS = {
    "ruido": ["protetor_auricular", "abafador"],
    "poeiras": ["mascara_pff2", "respirador"],
    "produtos_quimicos": ["luvas_nitrila", "oculos", "avental"],
    "quedas": ["cinturao_seguranca", "trava_quedas", "capacete"],
    "eletricidade": ["luvas_isolantes", "calcado_seguranca"],
    "temperaturas_extremas": ["luvas_termicas", "avental_termico"],
    "radiacao": ["oculos_protecao", "avental_chumbo"],
}


class PPRAService:
    """Service para gerenciamento de riscos ocupacionais (PPRA/PGR - NR-9)."""

    def __init__(self, db: Session | None = None):
        self.db = db

    # ==========================================================================
    # Risk Mapping Operations
    # ==========================================================================

    def create_mapping(
        self,
        request: RiskMappingRequest,
        created_by: UUID | None = None,
    ) -> RiskMapping:
        """
        Cria mapeamento de riscos para um setor.

        Args:
            request: Dados do mapeamento.
            created_by: UUID do usuario que criou.

        Returns:
            RiskMapping: Mapeamento criado.
        """
        mapping = RiskMapping(
            setor=request.setor,
            descricao_setor=request.descricao_setor,
            localizacao=request.localizacao,
            # funcao (singular, NOT NULL na tabela) precisa ser populada — antes ficava NULL e o
            # INSERT violava a constraint. Usa a 1ª função da lista (ou 'geral' se vazia).
            funcao=(request.funcoes[0] if request.funcoes else "geral"),
            funcoes=request.funcoes,
            numero_trabalhadores=request.numero_trabalhadores,
            avaliador=request.avaliador,
            cargo_avaliador=request.cargo_avaliador,
            data_proxima_revisao=request.data_proxima_revisao,
            created_by=created_by,
        )

        self.db.add(mapping)
        self.db.flush()  # Para obter o ID

        # Adicionar riscos
        for risk_data in request.riscos:
            risk = self._create_risk(mapping.id, risk_data)
            mapping.riscos.append(risk)

        # Calcular nivel de risco geral
        mapping.nivel_risco_geral = self._calculate_general_risk_level(mapping.riscos)

        self.db.commit()
        self.db.refresh(mapping)

        logger.info(
            "Mapeamento criado: setor=%s, riscos=%d, nivel=%s",
            request.setor,
            len(request.riscos),
            mapping.nivel_risco_geral,
        )

        return mapping

    def _create_risk(self, mapping_id: UUID, data: OccupationalRiskRequest) -> OccupationalRisk:
        """Cria risco ocupacional."""
        risk = OccupationalRisk(
            mapeamento_id=mapping_id,
            categoria=data.categoria,
            agente=data.agente,
            descricao=data.descricao,
            fonte_geradora=data.fonte_geradora,
            meio_propagacao=data.meio_propagacao,
            funcoes_expostas=data.funcoes_expostas,
            numero_expostos=data.numero_expostos,
            tempo_exposicao=data.tempo_exposicao,
            probabilidade=data.probabilidade,
            severidade=data.severidade,
            valor_medido=data.valor_medido,
            unidade_medida=data.unidade_medida,
            limite_tolerancia=data.limite_tolerancia,
            medidas_existentes=data.medidas_existentes,
            epis_recomendados=data.epis_recomendados or self._get_recommended_epis(data.agente),
            exames_requeridos=data.exames_requeridos,
            prioridade=data.prioridade,
        )

        # Calcular nivel de risco
        risk.nivel_risco = risk.calcular_nivel_risco()

        self.db.add(risk)
        return risk

    def _calculate_general_risk_level(self, risks: list[OccupationalRisk]) -> str:
        """Calcula nivel de risco geral baseado nos riscos individuais."""
        if not risks:
            return RiskLevel.TRIVIAL.value

        level_order = {
            RiskLevel.TRIVIAL.value: 1,
            RiskLevel.TOLERAVEL.value: 2,
            RiskLevel.MODERADO.value: 3,
            RiskLevel.SUBSTANCIAL.value: 4,
            RiskLevel.INTOLERAVEL.value: 5,
        }

        max_level = max(level_order.get(r.nivel_risco, 3) for r in risks)

        for level, order in level_order.items():
            if order == max_level:
                return level

        return RiskLevel.MODERADO.value

    def _get_recommended_epis(self, agente: str) -> list[str]:
        """Retorna EPIs recomendados para um agente de risco."""
        return EPI_RECOMMENDATIONS.get(agente.lower(), [])

    def get_mapping(self, mapping_id: UUID) -> RiskMapping | None:
        """Busca mapeamento por ID."""
        return self.db.query(RiskMapping).filter(RiskMapping.id == mapping_id).first()

    def update_mapping(
        self,
        mapping_id: UUID,
        request: RiskMappingUpdateRequest,
    ) -> RiskMapping | None:
        """Atualiza mapeamento de riscos."""
        mapping = self.get_mapping(mapping_id)
        if not mapping:
            return None

        update_data = request.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(mapping, field, value)

        # Incrementar versao
        mapping.versao += 1

        self.db.commit()
        self.db.refresh(mapping)
        return mapping

    def list_mappings(
        self,
        setor: str | None = None,
        ativo: bool | None = True,
        page: int = 1,
        size: int = 20,
    ) -> dict[str, Any]:
        """Lista mapeamentos de risco."""
        if not self.db:
            return {"items": [], "total": 0, "page": page, "size": size}

        from sqlalchemy import text

        try:
            where = "WHERE 1=1"
            params: dict = {"limit": size, "offset": (page - 1) * size}

            if setor:
                where += " AND setor ILIKE :setor"
                params["setor"] = f"%{setor}%"
            if ativo is not None:
                where += " AND status = :status"
                params["status"] = "ativo" if ativo else "inativo"

            total = self.db.execute(text(f"SELECT count(*) FROM health_risk_mappings {where}"), params).scalar() or 0

            rows = self.db.execute(
                text(
                    f"SELECT id, setor, funcao, agente_risco, tipo_risco, intensidade, fonte_geradora, medidas_controle, epi_recomendado, status, created_at FROM health_risk_mappings {where} ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
                ),
                params,
            ).fetchall()

            items = [
                {
                    "id": str(r.id),
                    "setor": r.setor,
                    "funcao": r.funcao,
                    "agente_risco": r.agente_risco,
                    "tipo_risco": r.tipo_risco,
                    "intensidade": r.intensidade,
                    "fonte_geradora": r.fonte_geradora,
                    "medidas_controle": r.medidas_controle,
                    "epi_recomendado": r.epi_recomendado,
                    "status": r.status,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]

            return {"items": items, "total": total, "page": page, "size": size}
        except Exception as e:
            logger.error("Erro ao listar mapeamentos: %s", e)
            return {"items": [], "total": 0, "page": page, "size": size}

    def get_sector_risks(self, setor: str) -> list[OccupationalRisk]:
        """Retorna riscos de um setor."""
        mapping = (
            self.db.query(RiskMapping)
            .filter(
                RiskMapping.setor == setor,
                RiskMapping.ativo,
            )
            .order_by(RiskMapping.data_avaliacao.desc())
            .first()
        )

        if not mapping:
            return []

        return mapping.riscos

    def get_function_risks(self, funcao: str) -> list[OccupationalRisk]:
        """Retorna riscos associados a uma funcao."""
        risks = self.db.query(OccupationalRisk).filter(OccupationalRisk.funcoes_expostas.contains([funcao])).all()

        return risks

    def calculate_sector_risk(self, setor: str) -> str:
        """Calcula nivel de risco de um setor."""
        risks = self.get_sector_risks(setor)
        return self._calculate_general_risk_level(risks)

    def get_recommended_epis(self, funcao: str) -> list[str]:
        """Retorna EPIs recomendados para uma funcao."""
        risks = self.get_function_risks(funcao)
        epis = set()

        for risk in risks:
            epis.update(risk.epis_recomendados or [])

        return list(epis)

    # ==========================================================================
    # Control Measure Operations
    # ==========================================================================

    def add_control_measure(self, request: ControlMeasureRequest) -> ControlMeasure:
        """Adiciona medida de controle."""
        measure = ControlMeasure(
            mapeamento_id=request.mapeamento_id,
            tipo=request.tipo,
            descricao=request.descricao,
            riscos_controlados=[str(r) for r in request.riscos_controlados],
            responsavel=request.responsavel,
            data_prevista=request.data_prevista,
            custo_estimado=request.custo_estimado,
        )

        self.db.add(measure)
        self.db.commit()
        self.db.refresh(measure)

        logger.info(
            "Medida de controle adicionada: tipo=%s, mapeamento=%s",
            request.tipo,
            request.mapeamento_id,
        )

        return measure

    def update_control_measure(
        self,
        measure_id: UUID,
        request: ControlMeasureUpdateRequest,
    ) -> ControlMeasure | None:
        """Atualiza medida de controle."""
        measure = self.db.query(ControlMeasure).filter(ControlMeasure.id == measure_id).first()

        if not measure:
            return None

        update_data = request.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(measure, field, value)

        self.db.commit()
        self.db.refresh(measure)
        return measure

    def list_control_measures(
        self,
        mapeamento_id: UUID,
        status: str | None = None,
    ) -> list[ControlMeasure]:
        """Lista medidas de controle de um mapeamento."""
        query = self.db.query(ControlMeasure).filter(ControlMeasure.mapeamento_id == mapeamento_id)

        if status:
            query = query.filter(ControlMeasure.status == status)

        return query.all()

    # ==========================================================================
    # Risk Categories Info
    # ==========================================================================

    def get_risk_categories(self) -> dict[str, Any]:
        """Retorna informacoes sobre categorias de risco."""
        return {
            "categorias": [
                {
                    "id": "fisico",
                    "nome": "Riscos Fisicos",
                    "exemplos": ["ruido", "vibracoes", "temperaturas_extremas", "radiacao"],
                    "cor_mapa": "verde",
                },
                {
                    "id": "quimico",
                    "nome": "Riscos Quimicos",
                    "exemplos": ["poeiras", "fumos", "gases", "vapores", "produtos_quimicos"],
                    "cor_mapa": "vermelho",
                },
                {
                    "id": "biologico",
                    "nome": "Riscos Biologicos",
                    "exemplos": ["virus", "bacterias", "fungos", "parasitas"],
                    "cor_mapa": "marrom",
                },
                {
                    "id": "ergonomico",
                    "nome": "Riscos Ergonomicos",
                    "exemplos": ["postura_inadequada", "movimentos_repetitivos", "esforco_fisico"],
                    "cor_mapa": "amarelo",
                },
                {
                    "id": "acidente",
                    "nome": "Riscos de Acidentes",
                    "exemplos": ["maquinas", "eletricidade", "quedas", "incendio"],
                    "cor_mapa": "azul",
                },
            ],
            "niveis_risco": [
                RiskLevel.TRIVIAL.value,
                RiskLevel.TOLERAVEL.value,
                RiskLevel.MODERADO.value,
                RiskLevel.SUBSTANCIAL.value,
                RiskLevel.INTOLERAVEL.value,
            ],
        }

    # ==========================================================================
    # Statistics
    # ==========================================================================

    def get_statistics(self) -> dict[str, Any]:
        """Retorna estatisticas do PPRA."""
        if not self.db:
            return {
                "total_mapeamentos_ativos": 0,
                "total_riscos_identificados": 0,
                "riscos_alto_nivel": 0,
                "medidas_pendentes": 0,
            }

        from sqlalchemy import text

        try:
            total_mappings = (
                self.db.execute(text("SELECT count(*) FROM health_risk_mappings WHERE status = 'ativo'")).scalar() or 0
            )

            total_risks = self.db.execute(text("SELECT count(*) FROM health_risk_mappings")).scalar() or 0

            high_risks = (
                self.db.execute(
                    text(
                        "SELECT count(*) FROM health_risk_mappings WHERE intensidade IN ('alta', 'critica', 'muito_alta')"
                    )
                ).scalar()
                or 0
            )

            return {
                "total_mapeamentos_ativos": total_mappings,
                "total_riscos_identificados": total_risks,
                "riscos_alto_nivel": high_risks,
                "medidas_pendentes": 0,
            }
        except Exception as e:
            logger.error("Erro ao consultar estatisticas PPRA: %s", e)
            return {
                "total_mapeamentos_ativos": 0,
                "total_riscos_identificados": 0,
                "riscos_alto_nivel": 0,
                "medidas_pendentes": 0,
            }
