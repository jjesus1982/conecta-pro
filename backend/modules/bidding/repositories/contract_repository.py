"""
Repository de Contrato Publico - Licitacoes
===========================================
"""

import builtins
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from modules.bidding.models.measurement import Measurement, MeasurementStatus
from modules.bidding.models.public_contract import ContractStatus, PublicContract
from modules.bidding.schemas.contract import PublicContractCreate, PublicContractUpdate

logger = logging.getLogger(__name__)


class ContractRepository:
    """Repository para operacoes com contratos publicos."""

    def __init__(self, db: Session):
        self.db = db

    async def get_by_id(self, contract_id: UUID) -> PublicContract | None:
        """Busca contrato por ID."""
        result = await self.db.execute(
            select(PublicContract)
            .options(selectinload(PublicContract.medicoes))
            .where(PublicContract.id == contract_id, PublicContract.ativo)
        )
        return result.scalar_one_or_none()

    async def get_by_numero(self, numero: str, ano: int) -> PublicContract | None:
        """Busca contrato por numero e ano."""
        result = await self.db.execute(
            select(PublicContract).where(
                PublicContract.numero_contrato == numero, PublicContract.ano_contrato == ano, PublicContract.ativo
            )
        )
        return result.scalar_one_or_none()

    async def get_by_tender(self, tender_id: UUID) -> PublicContract | None:
        """Busca contrato por edital."""
        result = await self.db.execute(
            select(PublicContract).where(PublicContract.tender_id == tender_id, PublicContract.ativo)
        )
        return result.scalar_one_or_none()

    async def list(
        self, orgao_cnpj: str = None, status: str = None, vigente: bool = None, page: int = 1, size: int = 50
    ) -> tuple[list[PublicContract], int]:
        """Lista contratos com filtros."""
        query = select(PublicContract).options(selectinload(PublicContract.medicoes)).where(PublicContract.ativo)

        if orgao_cnpj:
            query = query.where(PublicContract.orgao_cnpj == orgao_cnpj)

        if status:
            query = query.where(PublicContract.status == status)

        if vigente is True:
            hoje = date.today()
            query = query.where(
                PublicContract.status == ContractStatus.ACTIVE.value,
                PublicContract.data_vigencia_inicio <= hoje,
                PublicContract.data_vigencia_fim >= hoje,
            )
        elif vigente is False:
            hoje = date.today()
            query = query.where(
                or_(
                    PublicContract.data_vigencia_fim < hoje,
                    PublicContract.status.in_(
                        [ContractStatus.COMPLETED.value, ContractStatus.TERMINATED.value, ContractStatus.EXPIRED.value]
                    ),
                )
            )

        # Total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        # Paginacao
        query = query.order_by(PublicContract.data_vigencia_fim.desc())
        offset = (page - 1) * size
        query = query.offset(offset).limit(size)

        result = await self.db.execute(query)
        items = list(result.scalars().all())

        return items, total

    async def create(self, data: PublicContractCreate, user_id: UUID = None) -> PublicContract:
        """Cria novo contrato."""
        contract = PublicContract(
            **data.model_dump(exclude_unset=True), saldo_contrato=data.valor_contrato, created_by=user_id
        )

        self.db.add(contract)
        await self.db.commit()
        await self.db.refresh(contract)
        logger.info(f"Contrato criado: {contract.numero_contrato}/{contract.ano_contrato}")
        return contract

    async def update(
        self, contract_id: UUID, data: PublicContractUpdate, user_id: UUID = None
    ) -> PublicContract | None:
        """Atualiza contrato existente."""
        contract = await self.get_by_id(contract_id)
        if not contract:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(contract, field, value)

        # Atualiza saldo
        contract.saldo_contrato = contract.valor_contrato - (contract.valor_executado or Decimal("0"))

        contract.updated_by = user_id
        contract.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(contract)
        logger.info(f"Contrato atualizado: {contract.numero_contrato}/{contract.ano_contrato}")
        return contract

    async def delete(self, contract_id: UUID) -> bool:
        """Remove contrato (soft delete)."""
        contract = await self.get_by_id(contract_id)
        if not contract:
            return False

        contract.ativo = False
        contract.updated_at = datetime.utcnow()
        await self.db.commit()
        logger.info(f"Contrato removido: {contract.numero_contrato}/{contract.ano_contrato}")
        return True

    async def add_addendum(
        self,
        contract_id: UUID,
        numero: str,
        tipo: str,
        objeto: str,
        valor: Decimal = None,
        prazo_dias: int = None,
        data_assinatura: date = None,
    ) -> PublicContract | None:
        """Adiciona aditivo ao contrato."""
        contract = await self.get_by_id(contract_id)
        if not contract:
            return None

        contract.adicionar_aditivo(
            tipo=tipo, numero=numero, objeto=objeto, valor=valor, prazo_dias=prazo_dias, data_assinatura=data_assinatura
        )

        await self.db.commit()
        await self.db.refresh(contract)
        logger.info(f"Aditivo adicionado: {numero} ao contrato {contract.numero_contrato}")
        return contract

    async def get_expiring(self, days: int = 90) -> builtins.list[PublicContract]:
        """Lista contratos vencendo nos proximos X dias."""
        limite = date.today() + timedelta(days=days)
        result = await self.db.execute(
            select(PublicContract)
            .options(selectinload(PublicContract.medicoes))  # evita MissingGreenlet no _to_response
            .where(
                PublicContract.ativo,
                PublicContract.status == ContractStatus.ACTIVE.value,
                PublicContract.data_vigencia_fim <= limite,
                PublicContract.data_vigencia_fim >= date.today(),
            )
            .order_by(PublicContract.data_vigencia_fim.asc())
        )
        return list(result.scalars().all())

    async def get_vigentes(self) -> builtins.list[PublicContract]:
        """Lista contratos vigentes."""
        hoje = date.today()
        result = await self.db.execute(
            select(PublicContract)
            .options(selectinload(PublicContract.medicoes))  # evita MissingGreenlet no _to_response
            .where(
                PublicContract.ativo,
                PublicContract.status == ContractStatus.ACTIVE.value,
                PublicContract.data_vigencia_inicio <= hoje,
                PublicContract.data_vigencia_fim >= hoje,
            )
            .order_by(PublicContract.data_vigencia_fim.asc())
        )
        return list(result.scalars().all())

    async def get_totals(self) -> dict:
        """Retorna totais dos contratos vigentes."""
        hoje = date.today()
        result = await self.db.execute(
            select(
                func.count(PublicContract.id).label("total"),
                func.sum(PublicContract.valor_contrato).label("valor_total"),
                func.sum(PublicContract.valor_executado).label("total_executado"),
                func.sum(PublicContract.valor_pago).label("total_pago"),
            ).where(
                PublicContract.ativo,
                PublicContract.status == ContractStatus.ACTIVE.value,
                PublicContract.data_vigencia_inicio <= hoje,
                PublicContract.data_vigencia_fim >= hoje,
            )
        )
        row = result.one()
        return {
            "total_contratos": row.total or 0,
            "valor_total": row.valor_total or Decimal("0"),
            "total_executado": row.total_executado or Decimal("0"),
            "total_pago": row.total_pago or Decimal("0"),
        }

    # Medicoes
    async def add_measurement(
        self,
        contract_id: UUID,
        numero: int,
        competencia: str,
        periodo_inicio: date,
        periodo_fim: date,
        valor_bruto: Decimal,
        user_id: UUID = None,
    ) -> Measurement:
        """Adiciona medicao ao contrato."""
        measurement = Measurement(
            contrato_id=contract_id,
            numero_medicao=numero,
            competencia=competencia,
            periodo_inicio=periodo_inicio,
            periodo_fim=periodo_fim,
            valor_bruto=valor_bruto,
            valor_liquido=valor_bruto,  # Sera atualizado com retencoes
            created_by=user_id,
        )

        self.db.add(measurement)
        await self.db.commit()
        await self.db.refresh(measurement)
        logger.info(f"Medicao {numero} adicionada ao contrato {contract_id}")
        return measurement

    async def get_measurements(self, contract_id: UUID) -> builtins.list[Measurement]:
        """Lista medicoes de um contrato."""
        result = await self.db.execute(
            select(Measurement)
            .where(Measurement.contrato_id == contract_id)
            .order_by(Measurement.numero_medicao.desc())
        )
        return list(result.scalars().all())

    async def get_measurement_by_id(self, measurement_id: UUID) -> Measurement | None:
        """Busca medicao por ID."""
        result = await self.db.execute(select(Measurement).where(Measurement.id == measurement_id))
        return result.scalar_one_or_none()

    async def approve_measurement(
        self, measurement_id: UUID, aprovador: str, cargo: str = None, observacoes: str = None
    ) -> Measurement | None:
        """Aprova uma medicao."""
        measurement = await self.get_measurement_by_id(measurement_id)
        if not measurement:
            return None

        measurement.status = MeasurementStatus.APPROVED.value
        measurement.data_aprovacao = date.today()
        measurement.aprovador_nome = aprovador
        measurement.aprovador_cargo = cargo
        measurement.observacoes_aprovador = observacoes

        # Atualiza contrato
        contract = await self.get_by_id(measurement.contrato_id)
        if contract:
            contract.valor_executado = (contract.valor_executado or Decimal("0")) + measurement.valor_liquido
            contract.saldo_contrato = contract.valor_contrato - contract.valor_executado

        await self.db.commit()
        await self.db.refresh(measurement)
        logger.info(f"Medicao {measurement.numero_medicao} aprovada")
        return measurement
