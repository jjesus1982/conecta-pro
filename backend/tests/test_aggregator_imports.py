"""
Tests for the 9 aggregator module imports.

Validates that each aggregator module:
- Can be imported without errors
- Exports all names listed in __all__
- Every exported router is a FastAPI APIRouter instance
- __all__ matches the actual exported names
"""

import importlib

import pytest
from fastapi import APIRouter


class TestComercialAggregator:
    """Tests for modules.comercial aggregator."""

    EXPECTED_ALL = [
        "crm_lead_router",
        "crm_opportunity_router",
        "crm_proposal_router",
        "crm_contract_router",
        "crm_commission_router",
        "crm_dashboard_router",
        "client_router",
        "bidding_tender_router",
        "bidding_document_router",
        "bidding_proposal_router",
        "bidding_contract_router",
        "bidding_agent_router",
        "bidding_sync_router",
        "bidding_erp_router",
        "service_router",
    ]

    def test_import(self):
        mod = importlib.import_module("modules.comercial")
        assert mod is not None

    def test_all_matches_expected(self):
        mod = importlib.import_module("modules.comercial")
        assert sorted(mod.__all__) == sorted(self.EXPECTED_ALL)

    @pytest.mark.parametrize("name", EXPECTED_ALL)
    def test_router_is_api_router(self, name):
        mod = importlib.import_module("modules.comercial")
        obj = getattr(mod, name)
        assert isinstance(obj, APIRouter), f"{name} is {type(obj)}, expected APIRouter"

    def test_all_entries_exist_as_attributes(self):
        mod = importlib.import_module("modules.comercial")
        for name in mod.__all__:
            assert hasattr(mod, name), f"{name} in __all__ but not an attribute"


class TestOperacoesAggregator:
    """Tests for modules.operacoes aggregator."""

    EXPECTED_ALL = [
        "post_router",
        "scale_router",
        "scale_template_router",
        "shift_router",
        "allocation_router",
        "employee_router",
        "substitution_router",
        "time_bank_router",
        "reports_router",
        "kpi_trends_router",
        "occurrence_router",
        "diarist_router",
        "diarist_fiscal_router",
        "disciplinary_router",
        "inspection_round_router",
        "communication_router",
        "vacation_router",
        "operacional_ai_router",
        "operacional_ws_router",
        "ordem_servico_router",
        "visita_router",
        "checklist_router",
        "announcement_router",
        "notification_router",
        "operacional_dashboard_router",
        "banco_horas_alias",
        "ocorrencias_alias",
        "ferias_alias",
        "scale_templates_alias",
    ]

    def test_import(self):
        mod = importlib.import_module("modules.operacoes")
        assert mod is not None

    def test_all_matches_expected(self):
        mod = importlib.import_module("modules.operacoes")
        assert sorted(mod.__all__) == sorted(self.EXPECTED_ALL)

    @pytest.mark.parametrize("name", EXPECTED_ALL)
    def test_router_is_api_router(self, name):
        mod = importlib.import_module("modules.operacoes")
        obj = getattr(mod, name)
        assert isinstance(obj, APIRouter), f"{name} is {type(obj)}, expected APIRouter"

    def test_all_entries_exist_as_attributes(self):
        mod = importlib.import_module("modules.operacoes")
        for name in mod.__all__:
            assert hasattr(mod, name), f"{name} in __all__ but not an attribute"


class TestTecnicoAggregator:
    """Tests for modules.tecnico aggregator."""

    EXPECTED_ALL = [
        "equipment_router",
        "installation_router",
        "equipment_maintenance_router",
        "comodato_router",
        "document_kit_router",
    ]

    def test_import(self):
        mod = importlib.import_module("modules.tecnico")
        assert mod is not None

    def test_all_matches_expected(self):
        mod = importlib.import_module("modules.tecnico")
        assert sorted(mod.__all__) == sorted(self.EXPECTED_ALL)

    @pytest.mark.parametrize("name", EXPECTED_ALL)
    def test_router_is_api_router(self, name):
        mod = importlib.import_module("modules.tecnico")
        obj = getattr(mod, name)
        assert isinstance(obj, APIRouter), f"{name} is {type(obj)}, expected APIRouter"

    def test_all_entries_exist_as_attributes(self):
        mod = importlib.import_module("modules.tecnico")
        for name in mod.__all__:
            assert hasattr(mod, name), f"{name} in __all__ but not an attribute"


class TestPessoasAggregator:
    """Tests for modules.pessoas aggregator."""

    EXPECTED_ALL = [
        "recruitment_router",
        "onboarding_router",
        "profile_router",
        "climate_router",
        "turnover_router",
        "reimbursement_router",
        "ged_folder_router",
        "ged_document_router",
        "ged_version_router",
        "ged_share_router",
        "ged_tag_router",
        "ged_signature_router",
        "ged_stats_router",
    ]

    def test_import(self):
        mod = importlib.import_module("modules.pessoas")
        assert mod is not None

    def test_all_matches_expected(self):
        mod = importlib.import_module("modules.pessoas")
        assert sorted(mod.__all__) == sorted(self.EXPECTED_ALL)

    @pytest.mark.parametrize("name", EXPECTED_ALL)
    def test_router_is_api_router(self, name):
        mod = importlib.import_module("modules.pessoas")
        obj = getattr(mod, name)
        assert isinstance(obj, APIRouter), f"{name} is {type(obj)}, expected APIRouter"

    def test_all_entries_exist_as_attributes(self):
        mod = importlib.import_module("modules.pessoas")
        for name in mod.__all__:
            assert hasattr(mod, name), f"{name} in __all__ but not an attribute"


class TestFinanceiroAggregator:
    """Tests for modules.financeiro aggregator."""

    EXPECTED_ALL = [
        "accounting_router",
        "supplier_router",
        "payable_router",
        "customer_router",
        "receivable_category_router",
        "receivable_router",
        "billing_rule_router",
        "bank_account_router",
        "bank_transaction_router",
        "bank_reconciliation_router",
        "cashflow_router",
        "purchase_router",
        "inventory_router",
        "fiscal_router",
        "financial_ai_router",
        "relatorios_router",
    ]

    def test_import(self):
        mod = importlib.import_module("modules.financeiro")
        assert mod is not None

    def test_all_matches_expected(self):
        mod = importlib.import_module("modules.financeiro")
        assert sorted(mod.__all__) == sorted(self.EXPECTED_ALL)

    @pytest.mark.parametrize("name", EXPECTED_ALL)
    def test_router_is_api_router(self, name):
        mod = importlib.import_module("modules.financeiro")
        obj = getattr(mod, name)
        assert isinstance(obj, APIRouter), f"{name} is {type(obj)}, expected APIRouter"

    def test_all_entries_exist_as_attributes(self):
        mod = importlib.import_module("modules.financeiro")
        for name in mod.__all__:
            assert hasattr(mod, name), f"{name} in __all__ but not an attribute"


class TestFiscalContabilAggregator:
    """Tests for modules.fiscal_contabil aggregator."""

    EXPECTED_ALL = [
        "empresas_router",
        "migrador_router",
        "obrigacoes_router",
        "empresas_dashboard_router",
        "dominio_router",
        "bookkeeper_router",
        "statements_router",
        "nfse_multi_router",
        "government_integrations_router",
        "bidding_certificate_router",
    ]

    def test_import(self):
        mod = importlib.import_module("modules.fiscal_contabil")
        assert mod is not None

    def test_all_matches_expected(self):
        mod = importlib.import_module("modules.fiscal_contabil")
        assert sorted(mod.__all__) == sorted(self.EXPECTED_ALL)

    @pytest.mark.parametrize("name", EXPECTED_ALL)
    def test_router_is_api_router(self, name):
        mod = importlib.import_module("modules.fiscal_contabil")
        obj = getattr(mod, name)
        assert isinstance(obj, APIRouter), f"{name} is {type(obj)}, expected APIRouter"

    def test_all_entries_exist_as_attributes(self):
        mod = importlib.import_module("modules.fiscal_contabil")
        for name in mod.__all__:
            assert hasattr(mod, name), f"{name} in __all__ but not an attribute"


class TestInteligenciaAggregator:
    """Tests for modules.inteligencia aggregator."""

    EXPECTED_ALL = [
        "executive_dashboard_router",
        "analytics_router",
        "report_router",
        "monitoring_router",
    ]

    def test_import(self):
        mod = importlib.import_module("modules.inteligencia")
        assert mod is not None

    def test_all_matches_expected(self):
        mod = importlib.import_module("modules.inteligencia")
        assert sorted(mod.__all__) == sorted(self.EXPECTED_ALL)

    @pytest.mark.parametrize("name", EXPECTED_ALL)
    def test_router_is_api_router(self, name):
        mod = importlib.import_module("modules.inteligencia")
        obj = getattr(mod, name)
        assert isinstance(obj, APIRouter), f"{name} is {type(obj)}, expected APIRouter"

    def test_all_entries_exist_as_attributes(self):
        mod = importlib.import_module("modules.inteligencia")
        for name in mod.__all__:
            assert hasattr(mod, name), f"{name} in __all__ but not an attribute"


class TestGestaoAggregator:
    """Tests for modules.gestao aggregator."""

    EXPECTED_ALL = [
        "config_router",
        "audit_router",
        "notification_router",
        "notification_compliance_router",
        "intelligent_notification_router",
        "push_notification_router",
        "mobile_router",
        "workflow_router",
        "integration_router",
        "connector_router",
        "solides_router",
        "banking_router",
    ]

    def test_import(self):
        mod = importlib.import_module("modules.gestao")
        assert mod is not None

    def test_all_matches_expected(self):
        mod = importlib.import_module("modules.gestao")
        assert sorted(mod.__all__) == sorted(self.EXPECTED_ALL)

    @pytest.mark.parametrize("name", EXPECTED_ALL)
    def test_router_is_api_router(self, name):
        mod = importlib.import_module("modules.gestao")
        obj = getattr(mod, name)
        assert isinstance(obj, APIRouter), f"{name} is {type(obj)}, expected APIRouter"

    def test_all_entries_exist_as_attributes(self):
        mod = importlib.import_module("modules.gestao")
        for name in mod.__all__:
            assert hasattr(mod, name), f"{name} in __all__ but not an attribute"


# TestCadastrosAggregator removido — modulo cadastros deletado (scaffold vazio)
