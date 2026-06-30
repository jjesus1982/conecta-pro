"""
Client Repository - Data Access Layer
Sprint 30: Cadastro de Clientes/Condomínios
"""

import logging
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import desc, func
from sqlalchemy.orm import Session, joinedload

from modules.clients.models.client import Client
from modules.clients.models.client_contract import ClientContract
from modules.clients.models.condominium import Condominium, CondominiumStatus
from modules.clients.models.integration_settings import IntegrationSettings
from modules.clients.models.unit import Unit, UnitStatus
from modules.clients.schemas.client_schemas import (
    ClientContractCreate,
    ClientContractUpdate,
    ClientCreate,
    ClientFilter,
    ClientUpdate,
    CondominiumCreate,
    CondominiumUpdate,
    IntegrationSettingsCreate,
    IntegrationSettingsUpdate,
    UnitCreate,
    UnitUpdate,
)

logger = logging.getLogger(__name__)


class ClientRepository:
    """Repository for Client and related entities."""

    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # CLIENT METHODS
    # =========================================================================

    def create_client(self, data: ClientCreate, created_by: UUID | None = None) -> Client:
        """Create a new client."""
        # Generate code
        sequence = self._get_next_client_sequence()
        code = Client.generate_code(sequence)

        client = Client(code=code, created_by=created_by, **data.model_dump(exclude_none=True))
        # status é NOT NULL (enum) e o ClientCreate não o define -> default 'active' ao cadastrar.
        if not getattr(client, "status", None):
            client.status = "active"
        self.db.add(client)
        self.db.commit()
        self.db.refresh(client)
        logger.info("Client created: %s", client.code)
        return client

    def get_client(self, client_id: UUID) -> Client | None:
        """Get client by ID."""
        return self.db.query(Client).filter(Client.id == client_id).first()

    def get_client_by_code(self, code: str) -> Client | None:
        """Get client by code."""
        return self.db.query(Client).filter(Client.code == code).first()

    def get_client_by_document(self, document: str) -> Client | None:
        """Get client by document number."""
        return self.db.query(Client).filter(Client.document_number == document).first()

    def get_client_with_relations(self, client_id: UUID) -> Client | None:
        """Get client with all relations loaded."""
        return (
            self.db.query(Client)
            .options(
                joinedload(Client.condominiums), joinedload(Client.contracts), joinedload(Client.integration_settings)
            )
            .filter(Client.id == client_id)
            .first()
        )

    def list_clients(  # pylint: disable=too-many-branches
        self,
        filters: ClientFilter | None = None,
        skip: int = 0,
        limit: int = 100,
        order_by: str = "created_at",
        order_desc: bool = True,
    ) -> tuple[list, int]:
        """List clients with filtering and pagination using raw SQL."""
        from sqlalchemy import text

        where_clauses = ["1=1"]
        params: dict = {}

        if filters:
            ftype = filters.client_type if hasattr(filters, "client_type") else None
            if ftype:
                where_clauses.append("client_type = :ftype")
                params["ftype"] = ftype.value if hasattr(ftype, "value") else ftype
            if filters.status:
                where_clauses.append("status = :fstatus")
                params["fstatus"] = filters.status.value if hasattr(filters.status, "value") else filters.status
            if filters.segment:
                where_clauses.append("segment = :fsegment")
                params["fsegment"] = filters.segment.value if hasattr(filters.segment, "value") else filters.segment
            if getattr(filters, "is_defaulter", None) is not None:
                where_clauses.append("is_defaulter = :fdefaulter")
                params["fdefaulter"] = filters.is_defaulter
            if getattr(filters, "is_vip", None) is not None:
                where_clauses.append("is_vip = :fvip")
                params["fvip"] = filters.is_vip
            if getattr(filters, "plus_enabled", None) is not None:
                where_clauses.append("plus_enabled = :fplus")
                params["fplus"] = filters.plus_enabled
            if getattr(filters, "city", None):
                where_clauses.append("address_city ILIKE :fcity")
                params["fcity"] = f"%{filters.city}%"
            if getattr(filters, "state", None):
                where_clauses.append("address_state = :fstate")
                params["fstate"] = filters.state
            if getattr(filters, "search", None):
                where_clauses.append(
                    "(name ILIKE :fsearch OR trading_name ILIKE :fsearch "
                    "OR document_number ILIKE :fsearch OR code ILIKE :fsearch OR email ILIKE :fsearch)"
                )
                params["fsearch"] = f"%{filters.search}%"

        where = " AND ".join(where_clauses)

        # Count
        count_sql = text(f"SELECT count(*) FROM clients WHERE {where}")  # noqa: S608
        total = self.db.execute(count_sql, params).scalar() or 0

        # Ordering + pagination via raw SQL
        valid_order = order_by if order_by in ("created_at", "name", "code", "status") else "created_at"
        direction = "DESC" if order_desc else "ASC"
        params["pskip"] = skip
        params["plimit"] = limit

        data_sql = text(  # noqa: S608
            f"SELECT id, code, name, trading_name, client_type, document_type, "
            f"document_number, email, phone, address_city, address_state, "
            f"status, segment, plus_enabled, guardian_enabled, "
            f"is_defaulter, is_vip, created_at, updated_at "
            f"FROM clients WHERE {where} "
            f"ORDER BY {valid_order} {direction} OFFSET :pskip LIMIT :plimit"
        )
        rows = self.db.execute(data_sql, params).fetchall()

        # Convert rows to dicts that match ClientListResponse
        clients = []
        for r in rows:
            clients.append(
                {
                    "id": str(r[0]),
                    "code": r[1],
                    "name": r[2],
                    "trading_name": r[3],
                    "type": r[4],
                    "document_type": r[5],
                    "document_number": r[6],
                    "email": r[7],
                    "phone": r[8],
                    "address_city": r[9],
                    "address_state": r[10],
                    "status": r[11],
                    "segment": r[12],
                    "plus_enabled": r[13],
                    "guardian_enabled": r[14],
                    "is_defaulter": r[15],
                    "is_vip": r[16],
                    "created_at": r[17].isoformat() if r[17] else None,
                    "updated_at": r[18].isoformat() if r[18] else None,
                }
            )
        return clients, total

    def update_client(self, client_id: UUID, data: ClientUpdate, updated_by: UUID | None = None) -> Client | None:
        """Update a client."""
        client = self.get_client(client_id)
        if not client:
            return None

        update_data = data.model_dump(exclude_none=True)
        for field, value in update_data.items():
            setattr(client, field, value)

        client.updated_by = updated_by
        client.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(client)
        logger.info("Client updated: %s", client.code)
        return client

    def delete_client(self, client_id: UUID) -> bool:
        """Delete a client."""
        client = self.get_client(client_id)
        if not client:
            return False

        self.db.delete(client)
        self.db.commit()
        logger.info("Client deleted: %s", client.code)
        return True

    def get_client_stats(self) -> dict:
        """Get client statistics using only columns that exist in the database."""
        from sqlalchemy import text

        # Use raw SQL to avoid ORM column mapping issues (migrations pending)
        total = self.db.execute(text("SELECT count(*) FROM clients")).scalar() or 0
        active = self.db.execute(text("SELECT count(*) FROM clients WHERE ativo = true")).scalar() or 0
        inactive = self.db.execute(text("SELECT count(*) FROM clients WHERE ativo = false")).scalar() or 0

        by_status = {
            (row[0] or "none"): row[1]
            for row in self.db.execute(text("SELECT status, count(*) FROM clients GROUP BY status"))
        }
        by_segment = {
            (row[0] or "none"): row[1]
            for row in self.db.execute(
                text("SELECT segment, count(*) FROM clients WHERE segment IS NOT NULL GROUP BY segment")
            )
        }
        total_revenue = self.db.execute(
            text("SELECT COALESCE(sum(total_revenue), 0) FROM clients")
        ).scalar() or Decimal("0")

        return {
            "total_clients": total,
            "active_clients": active,
            "inactive_clients": inactive,
            "defaulter_clients": 0,
            "vip_clients": 0,
            "by_type": {},
            "by_status": by_status,
            "by_segment": by_segment,
            "total_revenue": total_revenue,
            "average_contracts_per_client": 0.0,
        }

    def _get_next_client_sequence(self) -> int:
        """Get next client sequence number."""
        year = datetime.now().year
        pattern = f"CLI-{year}-%"
        max_code = self.db.query(func.max(Client.code)).filter(Client.code.like(pattern)).scalar()
        if max_code:
            try:
                return int(max_code.split("-")[-1]) + 1
            except (ValueError, IndexError):
                pass
        return 1

    # =========================================================================
    # CONDOMINIUM METHODS
    # =========================================================================

    def create_condominium(self, data: CondominiumCreate, created_by: UUID | None = None) -> Condominium:
        """Create a new condominium."""
        client = self.get_client(data.client_id)
        if not client:
            raise ValueError("Client not found")

        sequence = self._get_next_condominium_sequence(client.code)
        code = Condominium.generate_code(client.code, sequence)

        condominium = Condominium(code=code, created_by=created_by, **data.model_dump(exclude_none=True))
        self.db.add(condominium)
        self.db.commit()
        self.db.refresh(condominium)
        logger.info("Condominium created: %s", condominium.code)
        return condominium

    def get_condominium(self, condominium_id: UUID) -> Condominium | None:
        """Get condominium by ID."""
        return self.db.query(Condominium).filter(Condominium.id == condominium_id).first()

    def get_condominium_with_units(self, condominium_id: UUID) -> Condominium | None:
        """Get condominium with units loaded."""
        return (
            self.db.query(Condominium)
            .options(joinedload(Condominium.units))
            .filter(Condominium.id == condominium_id)
            .first()
        )

    def list_condominiums_by_client(
        self, client_id: UUID, skip: int = 0, limit: int = 100
    ) -> tuple[list[Condominium], int]:
        """List condominiums for a client."""
        query = self.db.query(Condominium).filter(Condominium.client_id == client_id)
        total = query.count()
        condominiums = query.order_by(desc(Condominium.created_at)).offset(skip).limit(limit).all()
        return condominiums, total

    def update_condominium(
        self, condominium_id: UUID, data: CondominiumUpdate, updated_by: UUID | None = None
    ) -> Condominium | None:
        """Update a condominium."""
        condominium = self.get_condominium(condominium_id)
        if not condominium:
            return None

        update_data = data.model_dump(exclude_none=True)
        for field, value in update_data.items():
            setattr(condominium, field, value)

        condominium.updated_by = updated_by
        condominium.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(condominium)
        logger.info("Condominium updated: %s", condominium.code)
        return condominium

    def delete_condominium(self, condominium_id: UUID) -> bool:
        """Delete a condominium."""
        condominium = self.get_condominium(condominium_id)
        if not condominium:
            return False

        self.db.delete(condominium)
        self.db.commit()
        logger.info("Condominium deleted: %s", condominium.code)
        return True

    def get_condominium_stats(self, client_id: UUID | None = None) -> dict:
        """Get condominium statistics."""
        query = self.db.query(Condominium)
        if client_id:
            query = query.filter(Condominium.client_id == client_id)

        total = query.count()
        active = query.filter(Condominium.status == CondominiumStatus.ATIVO).count()
        total_units = query.with_entities(func.sum(Condominium.total_units)).scalar() or 0

        by_type = dict(
            query.with_entities(Condominium.type, func.count(Condominium.id)).group_by(Condominium.type).all()
        )
        by_status = dict(
            query.with_entities(Condominium.status, func.count(Condominium.id)).group_by(Condominium.status).all()
        )

        return {
            "total_condominiums": total,
            "active_condominiums": active,
            "total_units": total_units,
            "by_type": {k.value if k else "none": v for k, v in by_type.items()},
            "by_status": {k.value if k else "none": v for k, v in by_status.items()},
        }

    def _get_next_condominium_sequence(self, client_code: str) -> int:
        """Get next condominium sequence for client."""
        pattern = f"{client_code}-COND-%"
        max_code = self.db.query(func.max(Condominium.code)).filter(Condominium.code.like(pattern)).scalar()
        if max_code:
            try:
                return int(max_code.split("-")[-1]) + 1
            except (ValueError, IndexError):
                pass
        return 1

    # =========================================================================
    # UNIT METHODS
    # =========================================================================

    def create_unit(self, data: UnitCreate, created_by: UUID | None = None) -> Unit:
        """Create a new unit."""
        condominium = self.get_condominium(data.condominium_id)
        if not condominium:
            raise ValueError("Condominium not found")

        code = Unit.generate_code(condominium.code, data.block, data.number)

        unit = Unit(code=code, created_by=created_by, **data.model_dump(exclude_none=True))
        self.db.add(unit)
        self.db.commit()
        self.db.refresh(unit)

        # Update condominium unit count
        condominium.update_unit_count(condominium.total_units + 1)
        self.db.commit()

        logger.info("Unit created: %s", unit.code)
        return unit

    def get_unit(self, unit_id: UUID) -> Unit | None:
        """Get unit by ID."""
        return self.db.query(Unit).filter(Unit.id == unit_id).first()

    def list_units_by_condominium(
        self, condominium_id: UUID, skip: int = 0, limit: int = 100
    ) -> tuple[list[Unit], int]:
        """List units for a condominium."""
        query = self.db.query(Unit).filter(Unit.condominium_id == condominium_id)
        total = query.count()
        units = query.order_by(Unit.block, Unit.number).offset(skip).limit(limit).all()
        return units, total

    def update_unit(self, unit_id: UUID, data: UnitUpdate, updated_by: UUID | None = None) -> Unit | None:
        """Update a unit."""
        unit = self.get_unit(unit_id)
        if not unit:
            return None

        update_data = data.model_dump(exclude_none=True)
        for field, value in update_data.items():
            setattr(unit, field, value)

        unit.updated_by = updated_by
        unit.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(unit)
        logger.info("Unit updated: %s", unit.code)
        return unit

    def delete_unit(self, unit_id: UUID) -> bool:
        """Delete a unit."""
        unit = self.get_unit(unit_id)
        if not unit:
            return False

        condominium = unit.condominium
        self.db.delete(unit)
        self.db.commit()

        # Update condominium unit count
        if condominium:
            condominium.update_unit_count(max(0, condominium.total_units - 1))
            self.db.commit()

        logger.info("Unit deleted: %s", unit.code)
        return True

    def get_unit_stats(self, condominium_id: UUID) -> dict:
        """Get unit statistics for a condominium."""
        query = self.db.query(Unit).filter(Unit.condominium_id == condominium_id)

        total = query.count()
        occupied = query.filter(Unit.status.in_([UnitStatus.OCUPADA, UnitStatus.ALUGADA])).count()
        available = query.filter(Unit.status == UnitStatus.DISPONIVEL).count()
        defaulters = query.filter(Unit.is_defaulter.is_(True)).count()

        occupancy_rate = (occupied / total * 100) if total > 0 else 0.0

        total_fees = query.with_entities(func.sum(Unit.monthly_fee)).scalar() or Decimal("0")

        by_type = dict(query.with_entities(Unit.type, func.count(Unit.id)).group_by(Unit.type).all())
        by_status = dict(query.with_entities(Unit.status, func.count(Unit.id)).group_by(Unit.status).all())

        return {
            "total_units": total,
            "occupied_units": occupied,
            "available_units": available,
            "defaulter_units": defaulters,
            "occupancy_rate": occupancy_rate,
            "by_type": {k.value if k else "none": v for k, v in by_type.items()},
            "by_status": {k.value if k else "none": v for k, v in by_status.items()},
            "total_monthly_fees": total_fees,
        }

    # =========================================================================
    # CLIENT CONTRACT METHODS
    # =========================================================================

    def create_client_contract(self, data: ClientContractCreate, created_by: UUID | None = None) -> ClientContract:
        """Create a new client contract."""
        contract = ClientContract(created_by=created_by, **data.model_dump(exclude_none=True))
        contract.calculate_value()
        self.db.add(contract)
        self.db.commit()
        self.db.refresh(contract)
        logger.info("Client contract created: %s", contract.id)
        return contract

    def get_client_contract(self, contract_id: UUID) -> ClientContract | None:
        """Get client contract by ID."""
        return self.db.query(ClientContract).filter(ClientContract.id == contract_id).first()

    def list_contracts_by_client(
        self, client_id: UUID, skip: int = 0, limit: int = 100
    ) -> tuple[list[ClientContract], int]:
        """List contracts for a client."""
        query = self.db.query(ClientContract).filter(ClientContract.client_id == client_id)
        total = query.count()
        contracts = query.order_by(desc(ClientContract.created_at)).offset(skip).limit(limit).all()
        return contracts, total

    def update_client_contract(
        self, contract_id: UUID, data: ClientContractUpdate, updated_by: UUID | None = None
    ) -> ClientContract | None:
        """Update a client contract."""
        contract = self.get_client_contract(contract_id)
        if not contract:
            return None

        update_data = data.model_dump(exclude_none=True)
        for field, value in update_data.items():
            setattr(contract, field, value)

        contract.calculate_value()
        contract.updated_by = updated_by
        contract.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(contract)
        logger.info("Client contract updated: %s", contract.id)
        return contract

    # =========================================================================
    # INTEGRATION SETTINGS METHODS
    # =========================================================================

    def create_integration_settings(
        self, data: IntegrationSettingsCreate, created_by: UUID | None = None
    ) -> IntegrationSettings:
        """Create new integration settings."""
        settings = IntegrationSettings(created_by=created_by, **data.model_dump(exclude_none=True))
        self.db.add(settings)
        self.db.commit()
        self.db.refresh(settings)
        logger.info("Integration settings created: %s", settings.id)
        return settings

    def get_integration_settings(self, settings_id: UUID) -> IntegrationSettings | None:
        """Get integration settings by ID."""
        return self.db.query(IntegrationSettings).filter(IntegrationSettings.id == settings_id).first()

    def list_integration_settings_by_client(self, client_id: UUID) -> list[IntegrationSettings]:
        """List integration settings for a client."""
        return self.db.query(IntegrationSettings).filter(IntegrationSettings.client_id == client_id).all()

    def update_integration_settings(
        self, settings_id: UUID, data: IntegrationSettingsUpdate, updated_by: UUID | None = None
    ) -> IntegrationSettings | None:
        """Update integration settings."""
        settings = self.get_integration_settings(settings_id)
        if not settings:
            return None

        update_data = data.model_dump(exclude_none=True)
        for field, value in update_data.items():
            setattr(settings, field, value)

        settings.updated_by = updated_by
        settings.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(settings)
        logger.info("Integration settings updated: %s", settings.id)
        return settings
