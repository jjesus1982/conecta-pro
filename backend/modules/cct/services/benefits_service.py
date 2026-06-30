"""
Servico de Beneficios — CCT 2026.

CRUD de configuracoes de beneficios e interface com validador.
"""

import logging
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.cct.models.benefits import (
    BENEFICIOS_OBRIGATORIOS_CCT,
)
from modules.cct.models.cct_tables import CCTBenefitConfig
from modules.cct.validators.benefits_validator import BenefitsValidator

logger = logging.getLogger(__name__)


class BenefitsService:
    """Servico de beneficios CCT 2026."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.validator = BenefitsValidator()

    def get_beneficios_cct(self) -> dict:
        """Retorna lista completa de beneficios da CCT."""
        beneficios = []
        obrigatorios = 0
        opcionais = 0

        for b in BENEFICIOS_OBRIGATORIOS_CCT:
            if b.obrigatorio:
                obrigatorios += 1
            else:
                opcionais += 1

            beneficios.append(
                {
                    "tipo": b.tipo.value,
                    "obrigatorio": b.obrigatorio,
                    "valor_total": float(b.valor_total) if b.valor_total else None,
                    "valor_empresa": float(b.valor_empresa) if b.valor_empresa else None,
                    "desconto_maximo_empregado": (
                        float(b.desconto_maximo_empregado) if b.desconto_maximo_empregado else None
                    ),
                    "desconto_percentual": (float(b.desconto_percentual) if b.desconto_percentual else None),
                    "observacao": b.observacao,
                }
            )

        return {
            "total_beneficios": len(beneficios),
            "obrigatorios": obrigatorios,
            "opcionais": opcionais,
            "beneficios": beneficios,
        }

    def validar_beneficios(
        self,
        employee_id: str,
        salario_base: float,
        beneficios_ativos: list[str],
        valor_vr_dia: float | None = None,
        desconto_vt_percentual: float | None = None,
    ) -> dict:
        """Valida beneficios de um colaborador contra CCT."""
        return self.validator.validar_beneficios(
            employee_id=employee_id,
            salario_base=salario_base,
            beneficios_ativos=beneficios_ativos,
            valor_vr_dia=valor_vr_dia,
            desconto_vt_percentual=desconto_vt_percentual,
        )

    def get_taxa_negocial(self, mes: int | None = None) -> dict:
        """Retorna informacoes da taxa negocial sindical."""
        return self.validator.verificar_taxa_negocial(mes)

    async def criar_config_beneficio(self, data: dict) -> CCTBenefitConfig:
        """Cria configuracao de beneficio por empresa.

        Args:
            data: Dados da configuracao.

        Returns:
            Configuracao criada.
        """
        config = CCTBenefitConfig(
            id=str(uuid4()),
            empresa_id=data.get("empresa_id"),
            tipo_beneficio=data["tipo_beneficio"],
            valor_empresa=data["valor_empresa"],
            desconto_empregado=data["desconto_empregado"],
            operadora=data.get("operadora"),
            vigencia_inicio=data.get("vigencia_inicio"),
            vigencia_fim=data.get("vigencia_fim"),
            observacoes=data.get("observacoes"),
        )
        self.db.add(config)
        await self.db.flush()
        await self.db.refresh(config)
        logger.info("Config beneficio CCT criada: tipo=%s", config.tipo_beneficio)
        return config

    async def listar_configs_beneficios(self, empresa_id: str | None = None) -> list[CCTBenefitConfig]:
        """Lista configuracoes de beneficios.

        Args:
            empresa_id: Filtro por empresa.

        Returns:
            Lista de configuracoes.
        """
        query = (
            select(CCTBenefitConfig).where(CCTBenefitConfig.ativo.is_(True)).order_by(CCTBenefitConfig.tipo_beneficio)
        )

        if empresa_id:
            query = query.where(CCTBenefitConfig.empresa_id == empresa_id)

        from sqlalchemy.exc import SQLAlchemyError  # noqa: PLC0415

        try:
            result = await self.db.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as exc:
            await self.db.rollback()
            logger.warning("listar_configs_beneficios: tabela ausente/erro — retornando vazio (%s)", exc)
            return []
