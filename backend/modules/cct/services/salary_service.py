"""
Servico de Salarios — CCT 2026.

CRUD de auditorias salariais e interface com validador.
"""

import logging
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.cct.models.cct_tables import CCTSalaryAudit
from modules.cct.models.salary_table import (
    REAJUSTE_ACIMA_PISO,
    REAJUSTE_PISO,
    SALARIO_PISO,
    TABELA_SALARIAL_CCT_2026,
    CargoAdditional,
)
from modules.cct.validators.salary_validator import SalaryValidator

logger = logging.getLogger(__name__)


class SalaryService:
    """Servico de salarios CCT 2026."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.validator = SalaryValidator()

    def get_tabela_salarial(self) -> dict:
        """Retorna tabela salarial completa da CCT."""
        cargos = []
        for entry in TABELA_SALARIAL_CCT_2026:
            adicional_desc = ""
            if entry.adicional == CargoAdditional.INSALUBRIDADE_10:
                adicional_desc = "+10% insalubridade"
            elif entry.adicional == CargoAdditional.PERICULOSIDADE_30:
                adicional_desc = "+30% periculosidade"
            elif entry.adicional == CargoAdditional.ADICIONAL_10:
                adicional_desc = "+10%"

            cargos.append(
                {
                    "cargo": entry.cargo,
                    "piso": float(entry.piso),
                    "adicional": entry.adicional.value,
                    "adicional_descricao": adicional_desc,
                }
            )

        return {
            "total_cargos": len(cargos),
            "piso_geral": float(SALARIO_PISO),
            "reajuste_piso": float(REAJUSTE_PISO),
            "reajuste_acima_piso": float(REAJUSTE_ACIMA_PISO),
            "vigencia": "01/01/2026 a 31/12/2026",
            "cargos": cargos,
        }

    def validar_salario(self, cargo: str, salario_atual: float) -> dict:
        """Valida salario contra piso CCT."""
        return self.validator.validar_salario(cargo, salario_atual)

    def calcular_reajuste(self, salario_atual: float, cargo: str | None = None) -> dict:
        """Calcula reajuste salarial conforme CCT."""
        return self.validator.calcular_reajuste(salario_atual, cargo)

    async def registrar_auditoria(
        self,
        employee_id: str,
        cargo: str,
        salario_atual: float,
        auditado_por: str | None = None,
    ) -> CCTSalaryAudit:
        """Valida salario e persiste resultado como auditoria.

        Args:
            employee_id: ID do colaborador.
            cargo: Nome do cargo.
            salario_atual: Salario atual.
            auditado_por: Usuario que realizou a auditoria.

        Returns:
            Registro de auditoria criado.
        """
        resultado = self.validator.validar_salario(cargo, salario_atual)

        audit = CCTSalaryAudit(
            id=str(uuid4()),
            employee_id=employee_id,
            cargo_cct=resultado["cargo"],
            piso_cct=resultado["piso_cct"],
            salario_atual=salario_atual,
            conforme=resultado["conforme"],
            diferenca=resultado["diferenca"],
            adicional_tipo=resultado.get("adicional_tipo"),
            adicional_valor=resultado.get("adicional_valor"),
            observacoes=resultado.get("alerta"),
            auditado_por=auditado_por,
        )
        self.db.add(audit)
        await self.db.flush()
        await self.db.refresh(audit)
        logger.info(
            "Auditoria salarial CCT criada: employee=%s conforme=%s",
            employee_id,
            resultado["conforme"],
        )
        return audit

    async def listar_auditorias(
        self,
        employee_id: str | None = None,
        apenas_nao_conformes: bool = False,
    ) -> list[CCTSalaryAudit]:
        """Lista auditorias salariais.

        Args:
            employee_id: Filtro por colaborador.
            apenas_nao_conformes: Mostrar apenas nao conformes.

        Returns:
            Lista de auditorias.
        """
        query = select(CCTSalaryAudit).order_by(CCTSalaryAudit.created_at.desc())

        if employee_id:
            query = query.where(CCTSalaryAudit.employee_id == employee_id)
        if apenas_nao_conformes:
            query = query.where(CCTSalaryAudit.conforme.is_(False))

        from sqlalchemy.exc import SQLAlchemyError  # noqa: PLC0415

        try:
            result = await self.db.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as exc:
            await self.db.rollback()
            logger.warning("listar_auditorias: tabela ausente/erro — retornando vazio (%s)", exc)
            return []
