"""
Client Service - Business Logic Layer
Sprint 30: Cadastro de Clientes/Condomínios
"""

import logging
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from modules.clients.models.client import Client
from modules.clients.models.client_contract import ClientContract
from modules.clients.models.condominium import Condominium
from modules.clients.models.integration_settings import IntegrationSettings
from modules.clients.models.unit import Unit
from modules.clients.repositories.client_repository import ClientRepository
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


class ClientService:
    """Service for managing clients and related entities."""

    def __init__(self, db: Session):
        self.db = db
        self.repository = ClientRepository(db)

    # =========================================================================
    # CLIENT METHODS
    # =========================================================================

    def create_client(self, data: ClientCreate, created_by: UUID | None = None) -> Client:
        """Create a new client with validation."""
        # Validate document — document_type pode vir como Enum ou str (Pydantic use_enum_values)
        _dtype = getattr(data.document_type, "value", data.document_type)
        if _dtype == "cnpj":
            if not Client.validate_cnpj(data.document_number):
                raise ValueError("CNPJ inválido")
        elif _dtype == "cpf":
            if not Client.validate_cpf(data.document_number):
                raise ValueError("CPF inválido")

        # Check for duplicate document
        existing = self.repository.get_client_by_document(data.document_number)
        if existing:
            raise ValueError("Já existe um cliente com este documento")

        client = self.repository.create_client(data, created_by)
        logger.info("Cliente criado: %s - %s", client.code, client.legal_name)
        return client

    def get_client(self, client_id: UUID) -> Client | None:
        """Get client by ID."""
        return self.repository.get_client(client_id)

    def get_client_by_code(self, code: str) -> Client | None:
        """Get client by code."""
        return self.repository.get_client_by_code(code)

    def get_client_full(self, client_id: UUID) -> Client | None:
        """Get client with all relations."""
        return self.repository.get_client_with_relations(client_id)

    def list_clients(
        self,
        filters: ClientFilter | None = None,
        skip: int = 0,
        limit: int = 100,
        order_by: str = "created_at",
        order_desc: bool = True,
    ) -> tuple[list[Client], int]:
        """List clients with filtering."""
        return self.repository.list_clients(filters, skip, limit, order_by, order_desc)

    def update_client(self, client_id: UUID, data: ClientUpdate, updated_by: UUID | None = None) -> Client | None:
        """Update a client."""
        client = self.repository.update_client(client_id, data, updated_by)
        if client:
            logger.info("Cliente atualizado: %s", client.code)
        return client

    def delete_client(self, client_id: UUID) -> bool:
        """Delete a client."""
        return self.repository.delete_client(client_id)

    def activate_client(self, client_id: UUID, updated_by: UUID | None = None) -> Client | None:
        """Activate a client."""
        client = self.repository.get_client(client_id)
        if not client:
            return None

        client.activate()
        client.updated_by = updated_by
        self.db.commit()
        self.db.refresh(client)
        logger.info("Cliente ativado: %s", client.code)
        return client

    def suspend_client(
        self, client_id: UUID, reason: str | None = None, updated_by: UUID | None = None
    ) -> Client | None:
        """Suspend a client."""
        client = self.repository.get_client(client_id)
        if not client:
            return None

        client.suspend(reason)
        client.updated_by = updated_by
        self.db.commit()
        self.db.refresh(client)
        logger.info("Cliente suspenso: %s - %s", client.code, reason)
        return client

    def block_client(self, client_id: UUID, reason: str | None = None, updated_by: UUID | None = None) -> Client | None:
        """Block a client."""
        client = self.repository.get_client(client_id)
        if not client:
            return None

        client.block(reason)
        client.updated_by = updated_by
        self.db.commit()
        self.db.refresh(client)
        logger.info("Cliente bloqueado: %s - %s", client.code, reason)
        return client

    def set_defaulter(self, client_id: UUID, debt_amount: Decimal, updated_by: UUID | None = None) -> Client | None:
        """Mark client as defaulter."""
        client = self.repository.get_client(client_id)
        if not client:
            return None

        client.set_defaulter(debt_amount)
        client.updated_by = updated_by
        self.db.commit()
        self.db.refresh(client)
        logger.info("Cliente marcado como inadimplente: %s - R$ %s", client.code, debt_amount)
        return client

    def clear_defaulter(self, client_id: UUID, updated_by: UUID | None = None) -> Client | None:
        """Remove defaulter status."""
        client = self.repository.get_client(client_id)
        if not client:
            return None

        client.clear_default()
        client.updated_by = updated_by
        self.db.commit()
        self.db.refresh(client)
        logger.info("Status de inadimplente removido: %s", client.code)
        return client

    def enable_plus(self, client_id: UUID, plus_client_id: str, updated_by: UUID | None = None) -> Client | None:
        """Enable Conecta Plus integration for client."""
        client = self.repository.get_client(client_id)
        if not client:
            return None

        client.enable_plus(plus_client_id)
        client.updated_by = updated_by
        self.db.commit()
        self.db.refresh(client)
        logger.info("Conecta Plus habilitado para cliente: %s", client.code)
        return client

    async def get_client_stats(self) -> dict:
        """Get client statistics."""
        return self.repository.get_client_stats()

    # =========================================================================
    # CONDOMINIUM METHODS
    # =========================================================================

    def create_condominium(self, data: CondominiumCreate, created_by: UUID | None = None) -> Condominium:
        """Create a new condominium."""
        condominium = self.repository.create_condominium(data, created_by)
        logger.info("Condomínio criado: %s - %s", condominium.code, condominium.name)
        return condominium

    def get_condominium(self, condominium_id: UUID) -> Condominium | None:
        """Get condominium by ID."""
        return self.repository.get_condominium(condominium_id)

    def get_condominium_full(self, condominium_id: UUID) -> Condominium | None:
        """Get condominium with units."""
        return self.repository.get_condominium_with_units(condominium_id)

    def list_condominiums(self, client_id: UUID, skip: int = 0, limit: int = 100) -> tuple[list[Condominium], int]:
        """List condominiums for a client."""
        return self.repository.list_condominiums_by_client(client_id, skip, limit)

    def update_condominium(
        self, condominium_id: UUID, data: CondominiumUpdate, updated_by: UUID | None = None
    ) -> Condominium | None:
        """Update a condominium."""
        return self.repository.update_condominium(condominium_id, data, updated_by)

    def delete_condominium(self, condominium_id: UUID) -> bool:
        """Delete a condominium."""
        return self.repository.delete_condominium(condominium_id)

    def activate_condominium(self, condominium_id: UUID, updated_by: UUID | None = None) -> Condominium | None:
        """Activate a condominium."""
        condominium = self.repository.get_condominium(condominium_id)
        if not condominium:
            return None

        condominium.activate()
        condominium.updated_by = updated_by
        self.db.commit()
        self.db.refresh(condominium)
        logger.info("Condomínio ativado: %s", condominium.code)
        return condominium

    def start_implantation(self, condominium_id: UUID, updated_by: UUID | None = None) -> Condominium | None:
        """Start condominium implantation."""
        condominium = self.repository.get_condominium(condominium_id)
        if not condominium:
            return None

        condominium.start_implantation()
        condominium.updated_by = updated_by
        self.db.commit()
        self.db.refresh(condominium)
        logger.info("Implantação iniciada: %s", condominium.code)
        return condominium

    def finish_implantation(self, condominium_id: UUID, updated_by: UUID | None = None) -> Condominium | None:
        """Finish condominium implantation."""
        condominium = self.repository.get_condominium(condominium_id)
        if not condominium:
            return None

        condominium.finish_implantation()
        condominium.updated_by = updated_by
        self.db.commit()
        self.db.refresh(condominium)
        logger.info("Implantação finalizada: %s", condominium.code)
        return condominium

    def update_syndic(
        self,
        condominium_id: UUID,
        name: str,
        phone: str | None = None,
        email: str | None = None,
        cpf: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        updated_by: UUID | None = None,
    ) -> Condominium | None:
        """Update condominium syndic."""
        condominium = self.repository.get_condominium(condominium_id)
        if not condominium:
            return None

        condominium.update_syndic(name, phone, email, cpf, start_date, end_date)
        condominium.updated_by = updated_by
        self.db.commit()
        self.db.refresh(condominium)
        logger.info("Síndico atualizado: %s - %s", condominium.code, name)
        return condominium

    def get_condominium_stats(self, client_id: UUID | None = None) -> dict:
        """Get condominium statistics."""
        return self.repository.get_condominium_stats(client_id)

    # =========================================================================
    # UNIT METHODS
    # =========================================================================

    def create_unit(self, data: UnitCreate, created_by: UUID | None = None) -> Unit:
        """Create a new unit."""
        unit = self.repository.create_unit(data, created_by)
        logger.info("Unidade criada: %s", unit.code)
        return unit

    def get_unit(self, unit_id: UUID) -> Unit | None:
        """Get unit by ID."""
        return self.repository.get_unit(unit_id)

    def list_units(self, condominium_id: UUID, skip: int = 0, limit: int = 100) -> tuple[list[Unit], int]:
        """List units for a condominium."""
        return self.repository.list_units_by_condominium(condominium_id, skip, limit)

    def update_unit(self, unit_id: UUID, data: UnitUpdate, updated_by: UUID | None = None) -> Unit | None:
        """Update a unit."""
        return self.repository.update_unit(unit_id, data, updated_by)

    def delete_unit(self, unit_id: UUID) -> bool:
        """Delete a unit."""
        return self.repository.delete_unit(unit_id)

    def set_unit_owner(
        self,
        unit_id: UUID,
        name: str,
        document: str | None = None,
        phone: str | None = None,
        email: str | None = None,
        updated_by: UUID | None = None,
    ) -> Unit | None:
        """Set unit owner."""
        unit = self.repository.get_unit(unit_id)
        if not unit:
            return None

        unit.set_owner(name, document, phone, email)
        unit.updated_by = updated_by
        self.db.commit()
        self.db.refresh(unit)
        logger.info("Proprietário definido: %s - %s", unit.code, name)
        return unit

    def set_unit_resident(
        self,
        unit_id: UUID,
        name: str,
        document: str | None = None,
        phone: str | None = None,
        email: str | None = None,
        is_tenant: bool = False,
        updated_by: UUID | None = None,
    ) -> Unit | None:
        """Set unit resident/tenant."""
        unit = self.repository.get_unit(unit_id)
        if not unit:
            return None

        unit.set_resident(name, document, phone, email, is_tenant=is_tenant)
        unit.updated_by = updated_by
        self.db.commit()
        self.db.refresh(unit)
        logger.info("Morador definido: %s - %s (inquilino=%s)", unit.code, name, is_tenant)
        return unit

    def clear_unit_resident(self, unit_id: UUID, updated_by: UUID | None = None) -> Unit | None:
        """Clear unit resident."""
        unit = self.repository.get_unit(unit_id)
        if not unit:
            return None

        unit.clear_resident()
        unit.updated_by = updated_by
        self.db.commit()
        self.db.refresh(unit)
        logger.info("Morador removido: %s", unit.code)
        return unit

    def get_unit_stats(self, condominium_id: UUID) -> dict:
        """Get unit statistics."""
        return self.repository.get_unit_stats(condominium_id)

    # =========================================================================
    # CLIENT CONTRACT METHODS
    # =========================================================================

    def create_contract(self, data: ClientContractCreate, created_by: UUID | None = None) -> ClientContract:
        """Create a new client contract."""
        contract = self.repository.create_client_contract(data, created_by)
        logger.info("Contrato de serviço criado: %s - %s", contract.id, contract.service_type)
        return contract

    def get_contract(self, contract_id: UUID) -> ClientContract | None:
        """Get client contract by ID."""
        return self.repository.get_client_contract(contract_id)

    def list_contracts(self, client_id: UUID, skip: int = 0, limit: int = 100) -> tuple[list[ClientContract], int]:
        """List contracts for a client."""
        return self.repository.list_contracts_by_client(client_id, skip, limit)

    def update_contract(
        self, contract_id: UUID, data: ClientContractUpdate, updated_by: UUID | None = None
    ) -> ClientContract | None:
        """Update a client contract."""
        return self.repository.update_client_contract(contract_id, data, updated_by)

    def activate_contract(self, contract_id: UUID, updated_by: UUID | None = None) -> ClientContract | None:
        """Activate a contract."""
        contract = self.repository.get_client_contract(contract_id)
        if not contract:
            return None

        contract.activate()
        contract.updated_by = updated_by
        self.db.commit()
        self.db.refresh(contract)
        logger.info("Contrato ativado: %s", contract.id)
        return contract

    def suspend_contract(
        self, contract_id: UUID, reason: str | None = None, updated_by: UUID | None = None
    ) -> ClientContract | None:
        """Suspend a contract."""
        contract = self.repository.get_client_contract(contract_id)
        if not contract:
            return None

        contract.suspend(reason)
        contract.updated_by = updated_by
        self.db.commit()
        self.db.refresh(contract)
        logger.info("Contrato suspenso: %s - %s", contract.id, reason)
        return contract

    def cancel_contract(
        self, contract_id: UUID, reason: str | None = None, updated_by: UUID | None = None
    ) -> ClientContract | None:
        """Cancel a contract."""
        contract = self.repository.get_client_contract(contract_id)
        if not contract:
            return None

        contract.cancel(reason)
        contract.updated_by = updated_by
        self.db.commit()
        self.db.refresh(contract)
        logger.info("Contrato cancelado: %s - %s", contract.id, reason)
        return contract

    # =========================================================================
    # INTEGRATION SETTINGS METHODS
    # =========================================================================

    def create_integration(
        self, data: IntegrationSettingsCreate, created_by: UUID | None = None
    ) -> IntegrationSettings:
        """Create integration settings."""
        integration = self.repository.create_integration_settings(data, created_by)
        logger.info("Integração criada: %s - %s", integration.id, integration.integration_type)
        return integration

    def get_integration(self, settings_id: UUID) -> IntegrationSettings | None:
        """Get integration settings by ID."""
        return self.repository.get_integration_settings(settings_id)

    def list_integrations(self, client_id: UUID) -> list[IntegrationSettings]:
        """List integrations for a client."""
        return self.repository.list_integration_settings_by_client(client_id)

    def update_integration(
        self, settings_id: UUID, data: IntegrationSettingsUpdate, updated_by: UUID | None = None
    ) -> IntegrationSettings | None:
        """Update integration settings."""
        return self.repository.update_integration_settings(settings_id, data, updated_by)

    def enable_integration(self, settings_id: UUID, updated_by: UUID | None = None) -> IntegrationSettings | None:
        """Enable an integration."""
        integration = self.repository.get_integration_settings(settings_id)
        if not integration:
            return None

        integration.enable()
        integration.updated_by = updated_by
        self.db.commit()
        self.db.refresh(integration)
        logger.info("Integração habilitada: %s", integration.id)
        return integration

    def disable_integration(self, settings_id: UUID, updated_by: UUID | None = None) -> IntegrationSettings | None:
        """Disable an integration."""
        integration = self.repository.get_integration_settings(settings_id)
        if not integration:
            return None

        integration.disable()
        integration.updated_by = updated_by
        self.db.commit()
        self.db.refresh(integration)
        logger.info("Integração desabilitada: %s", integration.id)
        return integration
