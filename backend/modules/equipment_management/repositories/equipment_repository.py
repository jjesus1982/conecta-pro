"""Repository para Equipment."""

import logging
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.equipment_management.models.equipment import (
    Equipment,
    EquipmentStatus,
)
from modules.equipment_management.schemas.equipment import (
    EquipmentCreate,
    EquipmentFilter,
    EquipmentStats,
    EquipmentUpdate,
)

logger = logging.getLogger(__name__)


class EquipmentRepository:
    """Repository para operações de Equipment."""

    def __init__(self, session: AsyncSession):
        """Inicializa o repository."""
        self.session = session

    async def create(self, data: EquipmentCreate) -> Equipment:
        """Cria um novo equipamento."""
        equipment = Equipment(
            equipment_code=(getattr(data, "equipment_code", None) or f"EQ-{uuid4().hex[:10].upper()}"),
            equipment_type=data.equipment_type,
            category=data.category,
            brand=data.brand,
            model=data.model,
            name=data.name,
            serial_number=data.serial_number,
            part_number=data.part_number,
            description=data.description,
            supplier_id=data.supplier_id,
            supplier_name=data.supplier_name,
            purchase_date=data.purchase_date,
            purchase_value=data.purchase_value,
            invoice_number=data.invoice_number,
            warranty_months=data.warranty_months,
            warranty_start=data.warranty_start,
            warranty_end=data.warranty_end,
            ip_address=data.ip_address,
            mac_address=data.mac_address,
            port=data.port,
            technical_config=data.technical_config,
            maintenance_interval_days=data.maintenance_interval_days,
            depreciation_rate=data.depreciation_rate,
            useful_life_months=data.useful_life_months,
            images=data.images,
            tags=data.tags,
            notes=data.notes,
            metadata_extra=data.metadata_extra,
        )
        self.session.add(equipment)
        await self.session.flush()
        await self.session.refresh(equipment)
        logger.info(f"Equipamento criado: {equipment.equipment_code}")
        return equipment

    async def get_by_id(self, equipment_id: str | UUID) -> Equipment | None:
        """Busca equipamento por ID."""
        if isinstance(equipment_id, str):
            equipment_id = UUID(equipment_id)
        result = await self.session.execute(
            select(Equipment).where(and_(Equipment.id == equipment_id, Equipment.is_active.is_(True)))
        )
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> Equipment | None:
        """Busca equipamento por código."""
        result = await self.session.execute(
            select(Equipment).where(and_(Equipment.equipment_code == code, Equipment.is_active.is_(True)))
        )
        return result.scalar_one_or_none()

    async def get_by_serial_number(self, serial: str) -> Equipment | None:
        """Busca equipamento por número de série."""
        result = await self.session.execute(
            select(Equipment).where(and_(Equipment.serial_number == serial, Equipment.is_active.is_(True)))
        )
        return result.scalar_one_or_none()

    async def update(self, equipment_id: str | UUID, data: EquipmentUpdate) -> Equipment | None:
        """Atualiza um equipamento."""
        equipment = await self.get_by_id(equipment_id)
        if not equipment:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(equipment, field, value)

        equipment.updated_at = datetime.utcnow()
        await self.session.flush()
        await self.session.refresh(equipment)
        logger.info(f"Equipamento atualizado: {equipment.equipment_code}")
        return equipment

    async def delete(self, equipment_id: str | UUID) -> bool:
        """Soft delete de equipamento."""
        equipment = await self.get_by_id(equipment_id)
        if not equipment:
            return False

        equipment.is_active = False
        equipment.updated_at = datetime.utcnow()
        await self.session.flush()
        logger.info(f"Equipamento desativado: {equipment.equipment_code}")
        return True

    async def list_with_filters(  # pylint: disable=too-many-branches
        self,
        filters: EquipmentFilter | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Equipment], int]:
        """Lista equipamentos com filtros e paginação."""
        query = select(Equipment).where(Equipment.is_active.is_(True))

        if filters:
            conditions = []

            if filters.search:
                search_term = f"%{filters.search}%"
                conditions.append(
                    or_(
                        Equipment.equipment_code.ilike(search_term),
                        Equipment.name.ilike(search_term),
                        Equipment.brand.ilike(search_term),
                        Equipment.model.ilike(search_term),
                        Equipment.serial_number.ilike(search_term),
                    )
                )

            if filters.equipment_type:
                conditions.append(Equipment.equipment_type == filters.equipment_type)

            if filters.category:
                conditions.append(Equipment.category == filters.category)

            if filters.status:
                conditions.append(Equipment.status == filters.status)

            if filters.brand:
                conditions.append(Equipment.brand.ilike(f"%{filters.brand}%"))

            if filters.client_id:
                conditions.append(Equipment.client_id == filters.client_id)

            if filters.contract_id:
                conditions.append(Equipment.contract_id == filters.contract_id)

            if filters.location_type:
                conditions.append(Equipment.location_type == filters.location_type)

            if filters.is_online is not None:
                conditions.append(Equipment.is_online == filters.is_online)

            if filters.is_in_warranty is not None:
                now = datetime.utcnow()
                if filters.is_in_warranty:
                    conditions.append(Equipment.warranty_end > now)
                else:
                    conditions.append(
                        or_(
                            Equipment.warranty_end <= now,
                            Equipment.warranty_end.is_(None),
                        )
                    )

            if filters.needs_maintenance is not None:
                now = datetime.utcnow()
                if filters.needs_maintenance:
                    conditions.append(Equipment.next_maintenance_at <= now)
                else:
                    conditions.append(
                        or_(
                            Equipment.next_maintenance_at > now,
                            Equipment.next_maintenance_at.is_(None),
                        )
                    )

            if conditions:
                query = query.where(and_(*conditions))

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        # Pagination
        offset = (page - 1) * page_size
        query = query.order_by(Equipment.created_at.desc())
        query = query.offset(offset).limit(page_size)

        result = await self.session.execute(query)
        items = list(result.scalars().all())

        return items, total

    async def get_by_client(self, client_id: str) -> list[Equipment]:
        """Lista equipamentos de um cliente."""
        result = await self.session.execute(
            select(Equipment)
            .where(
                and_(
                    Equipment.client_id == client_id,
                    Equipment.is_active.is_(True),
                )
            )
            .order_by(Equipment.name)
        )
        return list(result.scalars().all())

    async def get_by_contract(self, contract_id: str) -> list[Equipment]:
        """Lista equipamentos de um contrato."""
        result = await self.session.execute(
            select(Equipment)
            .where(
                and_(
                    Equipment.contract_id == contract_id,
                    Equipment.is_active.is_(True),
                )
            )
            .order_by(Equipment.name)
        )
        return list(result.scalars().all())

    async def get_in_stock(self) -> list[Equipment]:
        """Lista equipamentos em estoque."""
        result = await self.session.execute(
            select(Equipment)
            .where(
                and_(
                    Equipment.status == EquipmentStatus.ESTOQUE,
                    Equipment.is_active.is_(True),
                )
            )
            .order_by(Equipment.name)
        )
        return list(result.scalars().all())

    async def get_needing_maintenance(self) -> list[Equipment]:
        """Lista equipamentos que precisam de manutenção."""
        now = datetime.utcnow()
        result = await self.session.execute(
            select(Equipment)
            .where(
                and_(
                    Equipment.next_maintenance_at <= now,
                    Equipment.is_active.is_(True),
                    Equipment.status == EquipmentStatus.INSTALADO,
                )
            )
            .order_by(Equipment.next_maintenance_at)
        )
        return list(result.scalars().all())

    async def get_offline(self) -> list[Equipment]:
        """Lista equipamentos offline."""
        result = await self.session.execute(
            select(Equipment)
            .where(
                and_(
                    Equipment.is_online.is_(False),
                    Equipment.status == EquipmentStatus.INSTALADO,
                    Equipment.is_active.is_(True),
                )
            )
            .order_by(Equipment.last_offline_at)
        )
        return list(result.scalars().all())

    async def get_expiring_warranty(self, days: int = 30) -> list[Equipment]:
        """Lista equipamentos com garantia expirando."""
        now = datetime.utcnow()
        limit_date = now + timedelta(days=days)
        result = await self.session.execute(
            select(Equipment)
            .where(
                and_(
                    Equipment.warranty_end > now,
                    Equipment.warranty_end <= limit_date,
                    Equipment.is_active.is_(True),
                )
            )
            .order_by(Equipment.warranty_end)
        )
        return list(result.scalars().all())

    async def get_stats(  # pylint: disable=too-many-branches,E1137
        self, client_id: str | None = None
    ) -> EquipmentStats:
        """Calcula estatísticas de equipamentos."""
        base_query = select(Equipment).where(Equipment.is_active.is_(True))
        if client_id:
            base_query = base_query.where(Equipment.client_id == client_id)

        result = await self.session.execute(base_query)
        equipments = list(result.scalars().all())

        stats = EquipmentStats(
            total=len(equipments),
            by_status={},
            by_type={},
            by_category={},
        )

        now = datetime.utcnow()
        total_value = 0.0

        for eq in equipments:
            # Por status
            status_key = eq.status.value if eq.status else "unknown"
            stats.by_status[status_key] = stats.by_status.get(status_key, 0) + 1

            # Por tipo
            type_key = eq.equipment_type.value if eq.equipment_type else "unknown"
            stats.by_type[type_key] = stats.by_type.get(type_key, 0) + 1

            # Por categoria
            cat_key = eq.category.value if eq.category else "unknown"
            stats.by_category[cat_key] = stats.by_category.get(cat_key, 0) + 1

            # Contadores
            if eq.status == EquipmentStatus.ESTOQUE:
                stats.in_stock += 1
            elif eq.status == EquipmentStatus.INSTALADO:
                stats.installed += 1
            elif eq.status == EquipmentStatus.MANUTENCAO:
                stats.in_maintenance += 1
            elif eq.status == EquipmentStatus.DEFEITO:
                stats.defective += 1

            if eq.is_online:
                stats.online += 1
            else:
                stats.offline += 1

            if eq.warranty_end and eq.warranty_end > now:
                stats.in_warranty += 1

            if eq.next_maintenance_at and eq.next_maintenance_at <= now:
                stats.needs_maintenance += 1

            if eq.purchase_value:
                total_value += eq.purchase_value

        stats.total_value = total_value

        # Calcular idade média
        if equipments:
            ages = []
            for eq in equipments:
                if eq.purchase_date:
                    age = (now - eq.purchase_date).days / 30
                    ages.append(age)
            if ages:
                stats.avg_age_months = sum(ages) / len(ages)

        return stats

    async def install(
        self,
        equipment_id: str | UUID,
        client_id: str,
        client_name: str,
        contract_id: str | None = None,
        installation_id: str | None = None,
        location: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> Equipment | None:
        """Registra instalação de equipamento."""
        equipment = await self.get_by_id(equipment_id)
        if not equipment:
            return None

        equipment.install(
            client_id=client_id,
            client_name=client_name,
            contract_id=contract_id,
            installation_id=installation_id,
            location=location,
            latitude=latitude,
            longitude=longitude,
        )
        await self.session.flush()
        await self.session.refresh(equipment)
        logger.info(f"Equipamento instalado: {equipment.equipment_code}")
        return equipment

    async def uninstall(self, equipment_id: str | UUID) -> Equipment | None:
        """Desinstala equipamento."""
        equipment = await self.get_by_id(equipment_id)
        if not equipment:
            return None

        equipment.uninstall()
        await self.session.flush()
        await self.session.refresh(equipment)
        logger.info(f"Equipamento desinstalado: {equipment.equipment_code}")
        return equipment

    async def update_online_status(self, equipment_id: str | UUID, is_online: bool) -> Equipment | None:
        """Atualiza status online/offline."""
        equipment = await self.get_by_id(equipment_id)
        if not equipment:
            return None

        if is_online:
            equipment.set_online()
        else:
            equipment.set_offline()

        await self.session.flush()
        await self.session.refresh(equipment)
        return equipment

    async def bulk_update_online_status(self, equipment_ids: list[str], is_online: bool) -> int:
        """Atualiza status online/offline em massa."""
        count = 0
        for eq_id in equipment_ids:
            equipment = await self.update_online_status(eq_id, is_online)
            if equipment:
                count += 1
        return count
