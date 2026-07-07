"""
Testes de cobertura — CRM Marketing & Vendas.

Cobre:
  - MarketingController (campanhas, leads mkt, conversão mkt→CRM, stats, licitação→CRM)
  - ClientController (listar, resumo, detalhe)
  - ContactController (contatos CRUD, atividades CRUD, visão 360°)
  - LeadScoringEngine (score, probabilidade, ação recomendada, próximo contato)
  - PipelineService (pipeline ponderado, win rate, velocidade, forecast, health)
  - DashboardService (KPIs, funil, trends, conversion rates, performance)
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _uid() -> str:
    return str(uuid.uuid4())


def _mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    return db


def _row(**kw):
    """Cria um mock Row com acesso por atributo e por índice."""
    m = MagicMock()
    for k, v in kw.items():
        setattr(m, k, v)
    vals = list(kw.values())
    m.__getitem__ = lambda self, i: vals[i]
    return m


def _make_lead_mock(**overrides):
    """Lead mock compatível com scoring engine (campos como string, não MagicMock)."""
    defaults = {
        "id": _uid(),
        "name": "Lead Teste",
        "email": "teste@empresa.com",
        "phone": None,
        "company": None,
        "position": None,
        "company_size": None,
        "industry": None,
        "source": "other",
        "notes": None,
        "last_contact_at": None,
        "created_at": datetime.now(),
        "status": "new",
        "score": 50,
        "probability": 0.3,
        "expected_value": 0,
        "is_active": True,
        "assigned_to_id": None,
        "updated_at": datetime.now(),
    }
    defaults.update(overrides)
    m = MagicMock()
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


def _make_opp_mock(**overrides):
    """Opportunity mock compatível com PipelineService e DashboardService."""
    defaults = {
        "id": _uid(),
        "title": "Opp Teste",
        "stage": "proposal",
        "value": Decimal("50000"),
        "probability": 0.5,
        "is_active": True,
        "is_won": False,
        "is_lost": False,
        "is_open": True,
        "is_overdue": False,
        "weighted_value": 25000.0,
        "days_in_pipeline": 30,
        "created_at": datetime.now() - timedelta(days=30),
        "updated_at": datetime.now(),
        "expected_close_date": date.today() + timedelta(days=30),
        "actual_close_date": None,
        "loss_reason": None,
        "competitor": None,
        "owner_id": _uid(),
    }
    defaults.update(overrides)
    m = MagicMock()
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


# ===========================================================================
# 1. LEAD SCORING ENGINE
# ===========================================================================


class TestLeadScoringEngine:
    """Testes do motor de scoring de leads."""

    @pytest.fixture
    def engine(self):
        from modules.crm.services.lead_service import LeadScoringEngine

        return LeadScoringEngine()

    def test_calculate_score_complete_lead(self, engine):
        lead = _make_lead_mock(
            phone="92999999999",
            company="Empresa Teste LTDA",
            position="Gerente",
            company_size="large",
            industry="security",
            source="referral",
            notes="Interessado em vigilância",
            last_contact_at=datetime.now() - timedelta(hours=12),
            created_at=datetime.now() - timedelta(days=2),
            status="qualified",
        )
        score, prob = engine.calculate_score(lead)
        assert 0 <= score <= 100
        assert 0 <= prob <= 100

    def test_calculate_score_minimal_lead(self, engine):
        lead = _make_lead_mock()
        score, prob = engine.calculate_score(lead)
        assert 0 <= score <= 100
        assert score < 70

    def test_calculate_probability_qualified(self, engine):
        prob = engine._calculate_probability(80, "qualified")
        assert 0 <= prob <= 100

    def test_calculate_probability_won(self, engine):
        prob = engine._calculate_probability(90, "won")
        assert prob >= 80

    def test_calculate_probability_lost(self, engine):
        prob = engine._calculate_probability(50, "lost")
        assert prob == 0

    def test_score_source_referral(self, engine):
        lead = _make_lead_mock(source="referral")
        assert engine._score_source(lead) == 100

    def test_score_source_cold_call(self, engine):
        lead = _make_lead_mock(source="cold_call")
        assert engine._score_source(lead) == 40

    def test_score_company_size_enterprise(self, engine):
        lead = _make_lead_mock(company_size="enterprise")
        assert engine._score_company_size(lead) == 100

    def test_score_company_size_none(self, engine):
        lead = _make_lead_mock(company_size=None)
        assert engine._score_company_size(lead) == 50

    def test_score_industry_security(self, engine):
        lead = _make_lead_mock(industry="seguranca patrimonial")
        assert engine._score_industry(lead) == 90

    def test_score_industry_unknown(self, engine):
        lead = _make_lead_mock(industry="tecnologia")
        assert engine._score_industry(lead) == 50

    def test_score_engagement_negotiation(self, engine):
        lead = _make_lead_mock(status="negotiation")
        assert engine._score_engagement(lead) == 95

    def test_score_response_time_recent_contact(self, engine):
        lead = _make_lead_mock(last_contact_at=datetime.now() - timedelta(hours=6))
        assert engine._score_response_time(lead) == 100

    def test_score_response_time_old_contact(self, engine):
        lead = _make_lead_mock(last_contact_at=datetime.now() - timedelta(days=45))
        assert engine._score_response_time(lead) == 10

    def test_score_response_time_no_contact_new(self, engine):
        lead = _make_lead_mock(last_contact_at=None, created_at=datetime.now())
        assert engine._score_response_time(lead) == 100

    def test_score_completeness(self, engine):
        lead_full = _make_lead_mock(
            name="A",
            email="a@a.com",
            phone="123",
            company="X",
            position="Y",
            company_size="Z",
            industry="W",
            notes="N",
        )
        lead_min = _make_lead_mock(name="A", email="a@a.com")
        assert engine._score_completeness(lead_full) > engine._score_completeness(lead_min)


class TestLeadService:
    """Testes do serviço de leads."""

    @pytest.fixture
    def service(self):
        from modules.crm.services.lead_service import LeadService

        return LeadService()

    def test_get_recommended_action_hot_new(self, service):
        lead = _make_lead_mock(score=85, status="new")
        action = service.get_recommended_action(lead)
        assert "imediato" in action.lower() or "quente" in action.lower()

    def test_get_recommended_action_hot_qualified(self, service):
        lead = _make_lead_mock(score=85, status="qualified")
        action = service.get_recommended_action(lead)
        assert "proposta" in action.lower()

    def test_get_recommended_action_medium_no_contact(self, service):
        lead = _make_lead_mock(score=55, status="new", last_contact_at=None)
        action = service.get_recommended_action(lead)
        assert "contato" in action.lower()

    def test_get_recommended_action_medium_follow_up(self, service):
        lead = _make_lead_mock(
            score=55,
            status="contacted",
            last_contact_at=datetime.now() - timedelta(days=10),
        )
        action = service.get_recommended_action(lead)
        assert "follow" in action.lower()

    def test_get_recommended_action_cold_no_company(self, service):
        lead = _make_lead_mock(score=20, status="contacted", company=None)
        action = service.get_recommended_action(lead)
        assert "qualificar" in action.lower()

    def test_get_recommended_action_cold_with_company(self, service):
        lead = _make_lead_mock(score=20, status="contacted", company="Empresa X")
        action = service.get_recommended_action(lead)
        assert "nutrir" in action.lower()

    def test_get_recommended_action_won(self, service):
        lead = _make_lead_mock(score=90, status="won")
        action = service.get_recommended_action(lead)
        assert "onboarding" in action.lower()

    def test_get_recommended_action_lost(self, service):
        lead = _make_lead_mock(score=50, status="lost")
        action = service.get_recommended_action(lead)
        assert "arquivar" in action.lower() or "reengajamento" in action.lower()

    def test_get_next_contact_date_hot(self, service):
        lead = _make_lead_mock(score=80, status="new")
        next_date = service.get_next_contact_date(lead)
        assert next_date is not None
        assert (next_date - datetime.now()).days < 2

    def test_get_next_contact_date_warm(self, service):
        lead = _make_lead_mock(score=55, status="contacted")
        next_date = service.get_next_contact_date(lead)
        assert next_date is not None
        assert 2 <= (next_date - datetime.now()).days <= 4

    def test_get_next_contact_date_cold(self, service):
        lead = _make_lead_mock(score=25, status="new")
        next_date = service.get_next_contact_date(lead)
        assert next_date is not None
        assert (next_date - datetime.now()).days >= 6

    def test_get_next_contact_date_won(self, service):
        lead = _make_lead_mock(score=90, status="won")
        assert service.get_next_contact_date(lead) is None

    def test_get_next_contact_date_lost(self, service):
        lead = _make_lead_mock(score=50, status="lost")
        assert service.get_next_contact_date(lead) is None

    def test_calculate_score_delegates(self, service):
        lead = _make_lead_mock(source="referral", status="qualified")
        score, prob = service.calculate_score(lead)
        assert isinstance(score, int)
        assert isinstance(prob, float)


# ===========================================================================
# 2. PIPELINE SERVICE
# ===========================================================================


class TestPipelineService:
    """Testes do serviço de pipeline de vendas."""

    @pytest.fixture
    def service(self):
        from modules.crm.services.pipeline_service import PipelineService

        return PipelineService()

    def test_calculate_weighted_pipeline(self, service):
        opps = [
            _make_opp_mock(is_open=True, weighted_value=50000.0),
            _make_opp_mock(is_open=True, weighted_value=40000.0),
            _make_opp_mock(is_open=False, weighted_value=30000.0),
        ]
        assert service.calculate_weighted_pipeline(opps) == 90000.0

    def test_calculate_weighted_pipeline_empty(self, service):
        assert service.calculate_weighted_pipeline([]) == 0

    def test_calculate_win_rate(self, service):
        opps = [
            _make_opp_mock(is_won=True, is_lost=False, actual_close_date=date.today(), updated_at=datetime.now()),
            _make_opp_mock(is_won=True, is_lost=False, actual_close_date=date.today(), updated_at=datetime.now()),
            _make_opp_mock(is_won=False, is_lost=True, actual_close_date=date.today(), updated_at=datetime.now()),
        ]
        rate = service.calculate_win_rate(opps)
        assert abs(rate - 66.67) < 1

    def test_calculate_win_rate_no_closed(self, service):
        assert service.calculate_win_rate([_make_opp_mock(actual_close_date=None)]) == 0

    def test_calculate_win_rate_empty(self, service):
        assert service.calculate_win_rate([]) == 0

    def test_calculate_avg_deal_size(self, service):
        opps = [
            _make_opp_mock(is_won=True, value=Decimal("100000")),
            _make_opp_mock(is_won=True, value=Decimal("60000")),
        ]
        assert service.calculate_avg_deal_size(opps) == 80000.0

    def test_calculate_avg_deal_size_no_won(self, service):
        assert service.calculate_avg_deal_size([_make_opp_mock()]) == 0

    def test_calculate_avg_sales_cycle(self, service):
        opps = [
            _make_opp_mock(is_won=True, actual_close_date=date.today(), days_in_pipeline=45),
            _make_opp_mock(is_won=True, actual_close_date=date.today(), days_in_pipeline=30),
        ]
        assert service.calculate_avg_sales_cycle(opps) == 37.5

    def test_calculate_avg_sales_cycle_no_closed(self, service):
        assert service.calculate_avg_sales_cycle([_make_opp_mock(actual_close_date=None)]) == 0

    def test_calculate_sales_velocity(self, service):
        opps = [
            _make_opp_mock(is_open=True, is_won=False, is_lost=False),
            _make_opp_mock(
                is_won=True,
                is_lost=False,
                actual_close_date=date.today(),
                updated_at=datetime.now(),
                value=80000.0,
                days_in_pipeline=30,
            ),
            _make_opp_mock(is_won=False, is_lost=True, actual_close_date=date.today(), updated_at=datetime.now()),
        ]
        velocity = service.calculate_sales_velocity(opps)
        assert isinstance(velocity, (int, float))

    def test_calculate_sales_velocity_no_cycle(self, service):
        assert service.calculate_sales_velocity([_make_opp_mock(actual_close_date=None)]) == 0

    def test_get_overdue_opportunities(self, service):
        opps = [
            _make_opp_mock(is_overdue=True),
            _make_opp_mock(is_overdue=False),
        ]
        assert len(service.get_overdue_opportunities(opps)) == 1

    def test_get_stagnant_opportunities(self, service):
        opps = [
            _make_opp_mock(is_open=True, updated_at=datetime.now() - timedelta(days=45)),
            _make_opp_mock(is_open=True, updated_at=datetime.now()),
        ]
        assert len(service.get_stagnant_opportunities(opps, days_threshold=30)) == 1

    def test_get_health_score_empty(self, service):
        h = service.get_health_score([])
        assert h["score"] == 0
        assert h["status"] == "empty"

    def test_get_health_score_healthy(self, service):
        opps = [_make_opp_mock(is_open=True, is_overdue=False, stage="proposal", updated_at=datetime.now())]
        h = service.get_health_score(opps)
        assert h["score"] > 0

    def test_forecast_revenue(self, service):
        next_month = date.today() + timedelta(days=35)
        opps = [
            _make_opp_mock(
                is_open=True,
                value=Decimal("100000"),
                weighted_value=80000.0,
                probability=0.8,
                expected_close_date=next_month,
            ),
        ]
        forecasts = service.forecast_revenue(opps, months_ahead=3)
        assert len(forecasts) == 3

    def test_calculate_loss_analysis(self, service):
        opps = [
            _make_opp_mock(is_lost=True, loss_reason="price", competitor="Alpha Seg", value=50000.0),
            _make_opp_mock(is_lost=True, loss_reason="timing", competitor=None, value=30000.0),
        ]
        a = service.calculate_loss_analysis(opps)
        assert a["total_lost"] == 2
        assert "price" in a["by_reason"]

    def test_calculate_loss_analysis_no_losses(self, service):
        a = service.calculate_loss_analysis([_make_opp_mock(is_lost=False)])
        assert a["total_lost"] == 0

    def test_get_stage_conversion_rates(self, service):
        from modules.crm.models.opportunity import OpportunityStage

        opps = [
            _make_opp_mock(stage=OpportunityStage.QUALIFICATION.value, is_won=False, is_lost=False),
            _make_opp_mock(stage=OpportunityStage.PROPOSAL.value, is_won=False, is_lost=False),
            _make_opp_mock(stage=OpportunityStage.CLOSED_WON.value, is_won=True, is_lost=False),
        ]
        rates = service.get_stage_conversion_rates(opps)
        assert isinstance(rates, dict)


# ===========================================================================
# 3. DASHBOARD SERVICE
# ===========================================================================


class TestDashboardService:
    """Testes do serviço de dashboard CRM."""

    @pytest.fixture
    def service(self):
        from modules.crm.services.dashboard_service import DashboardService

        return DashboardService()

    def _lead(self, **kw):
        defaults = {
            "status": "new",
            "source": "website",
            "score": 50,
            "is_active": True,
            "assigned_to_id": _uid(),
            "created_at": datetime.now() - timedelta(days=5),
            "updated_at": datetime.now(),
        }
        defaults.update(kw)
        m = MagicMock()
        for k, v in defaults.items():
            setattr(m, k, v)
        return m

    def _opp(self, **kw):
        defaults = {
            "stage": "proposal",
            "value": Decimal("50000"),
            "probability": 0.5,
            "weighted_value": 25000.0,
            "days_in_pipeline": 30,
            "is_active": True,
            "is_won": False,
            "is_lost": False,
            "owner_id": _uid(),
            "created_at": datetime.now() - timedelta(days=10),
            "updated_at": datetime.now(),
        }
        defaults.update(kw)
        m = MagicMock()
        for k, v in defaults.items():
            setattr(m, k, v)
        return m

    def _proposal(self, **kw):
        defaults = {
            "status": "sent",
            "total": Decimal("45000"),
            "is_active": True,
            "created_at": datetime.now() - timedelta(days=3),
        }
        defaults.update(kw)
        m = MagicMock()
        for k, v in defaults.items():
            setattr(m, k, v)
        return m

    def _commission(self, **kw):
        defaults = {
            "status": "pending",
            "final_commission": Decimal("2500"),
            "is_active": True,
            "seller_id": _uid(),
            "created_at": datetime.now() - timedelta(days=2),
        }
        defaults.update(kw)
        m = MagicMock()
        for k, v in defaults.items():
            setattr(m, k, v)
        return m

    def test_calculate_kpis(self, service):
        kpis = service.calculate_kpis(
            leads=[self._lead(), self._lead(status="qualified")],
            opportunities=[self._opp()],
            proposals=[self._proposal()],
            commissions=[self._commission()],
        )
        assert kpis.leads_total == 2
        assert kpis.opportunities_total == 1

    def test_calculate_kpis_empty(self, service):
        kpis = service.calculate_kpis(leads=[], opportunities=[], proposals=[], commissions=[])
        assert kpis.leads_total == 0

    def test_generate_funnel_chart(self, service):
        from modules.crm.models.opportunity import OpportunityStage

        opps = [
            self._opp(stage=OpportunityStage.QUALIFICATION.value),
            self._opp(stage=OpportunityStage.PROPOSAL.value),
        ]
        chart = service.generate_funnel_chart(opps)
        assert chart.chart_type == "funnel"

    def test_generate_funnel_chart_empty(self, service):
        chart = service.generate_funnel_chart([])
        assert chart.chart_type == "funnel"

    def test_generate_trends(self, service):
        leads = [self._lead(created_at=datetime.now() - timedelta(days=i * 30)) for i in range(6)]
        trends = service.generate_trends(
            data=leads,
            date_field="created_at",
            value_field="count",
            period="month",
            periods_count=6,
        )
        assert isinstance(trends, list)

    def test_generate_trends_empty(self, service):
        trends = service.generate_trends(
            data=[],
            date_field="created_at",
            value_field="count",
            period="month",
            periods_count=6,
        )
        assert isinstance(trends, list)

    def test_generate_pie_chart_by_status(self, service):
        leads = [self._lead(status="new"), self._lead(status="qualified")]
        chart = service.generate_pie_chart_by_status(items=leads, status_field="status", title="Leads")
        assert chart.chart_type == "pie"

    def test_calculate_conversion_rates(self, service):
        from modules.crm.models.opportunity import OpportunityStage

        opps = [
            self._opp(stage=OpportunityStage.QUALIFICATION.value, is_won=False, is_lost=False),
            self._opp(stage=OpportunityStage.CLOSED_WON.value, is_won=True, is_lost=False),
        ]
        rates = service.calculate_conversion_rates(opps)
        assert isinstance(rates, dict)

    def test_calculate_conversion_rates_empty(self, service):
        assert isinstance(service.calculate_conversion_rates([]), dict)

    def test_calculate_seller_performance(self, service):
        sid = _uid()
        perf = service.calculate_seller_performance(
            seller_id=sid,
            leads=[self._lead(assigned_to_id=sid)],
            opportunities=[self._opp(owner_id=sid, stage="closed_won", is_won=True)],
            commissions=[self._commission(seller_id=sid)],
        )
        assert perf.seller_id == sid

    def test_get_top_performers(self, service):
        s1, s2 = _uid(), _uid()
        top = service.get_top_performers(
            leads=[self._lead(assigned_to_id=s1)],
            opportunities=[self._opp(owner_id=s1, stage="closed_won", is_won=True)],
            commissions=[self._commission(seller_id=s1)],
            sellers={s1: None, s2: None},
            limit=5,
        )
        assert isinstance(top, list)


# ===========================================================================
# 5. MARKETING CONTROLLER — Schemas
# ===========================================================================


class TestMarketingSchemas:
    """Testes dos schemas Pydantic do marketing controller."""

    def test_campaign_create_defaults(self):
        from modules.crm.controllers.marketing_controller import CampaignCreate

        c = CampaignCreate(name="Campanha Teste")
        assert c.type == "organic"
        assert c.budget == 0

    def test_campaign_create_full(self):
        from modules.crm.controllers.marketing_controller import CampaignCreate

        c = CampaignCreate(
            name="Google Ads Q1",
            type="google_ads",
            budget=5000.0,
            utm_source="google",
            utm_medium="cpc",
            utm_campaign="q1-2026",
        )
        assert c.budget == 5000.0

    def test_mkt_lead_create_minimal(self):
        from modules.crm.controllers.marketing_controller import MktLeadCreate

        assert MktLeadCreate(name="João").campaign_id is None

    def test_mkt_lead_create_full(self):
        from modules.crm.controllers.marketing_controller import MktLeadCreate

        ml = MktLeadCreate(
            campaign_id=_uid(),
            name="Maria",
            email="m@t.com",
            phone="92999887766",
            source="instagram",
        )
        assert ml.email == "m@t.com"

    def test_licitacao_convert_request(self):
        from modules.crm.controllers.marketing_controller import LicitacaoConvertRequest

        req = LicitacaoConvertRequest(
            orgao="Prefeitura",
            objeto="Vigilância",
            valor=500000.0,
            numero_edital="PE-001/2026",
        )
        assert req.valor == 500000.0


# ===========================================================================
# 6. CONTACT CONTROLLER — Schemas
# ===========================================================================


class TestContactSchemas:
    def test_contact_create(self):
        from modules.crm.controllers.contact_controller import ContactCreate

        c = ContactCreate(client_id=_uid(), name="Carlos", role="Síndico", is_primary=True)
        assert c.is_primary is True

    def test_activity_create(self):
        from modules.crm.controllers.contact_controller import ActivityCreate

        assert ActivityCreate(client_id=_uid(), type="visit", subject="Visita").type == "visit"

    def test_activity_create_defaults(self):
        from modules.crm.controllers.contact_controller import ActivityCreate

        assert ActivityCreate(client_id=_uid(), subject="Nota").type == "note"


# ===========================================================================
# 7. LEAD SCHEMAS
# ===========================================================================


class TestLeadSchemas:
    def test_lead_create_valid(self):
        from modules.crm.schemas.lead import LeadCreate

        assert LeadCreate(name="Lead", email="l@t.com", phone="11999998888").name == "Lead"

    def test_lead_create_minimal(self):
        from modules.crm.schemas.lead import LeadCreate

        assert LeadCreate(name="Min", email="m@t.com").name == "Min"

    def test_lead_filter_defaults(self):
        from modules.crm.schemas.lead import LeadFilter

        f = LeadFilter()
        assert f.status is None and f.source is None

    def test_lead_status_update(self):
        from modules.crm.models.lead import LeadStatus
        from modules.crm.schemas.lead import LeadStatusUpdate

        u = LeadStatusUpdate(status=LeadStatus.QUALIFIED, notes="OK")
        assert u.status == LeadStatus.QUALIFIED

    def test_lead_update_partial(self):
        from modules.crm.schemas.lead import LeadUpdate

        u = LeadUpdate(company="Nova")
        assert u.company == "Nova" and u.name is None


# ===========================================================================
# 8. LEAD MODEL
# ===========================================================================


class TestLeadModel:
    def test_lead_status_enum(self):
        from modules.crm.models.lead import LeadStatus

        assert LeadStatus.NEW == "new"
        assert len(LeadStatus) == 7

    def test_lead_source_enum(self):
        from modules.crm.models.lead import LeadSource

        assert LeadSource.WEBSITE == "website"
        assert len(LeadSource) == 8

    def test_lead_properties(self):
        from modules.crm.models.lead import Lead

        lead = Lead(
            name="Test",
            email="t@t.com",
            score=75,
            probability=0.6,
            expected_value=100000,
            status="qualified",
        )
        assert lead.is_hot is True
        assert lead.is_qualified is True
        assert lead.weighted_value == 600.0  # 100000 * (0.6 / 100)

    def test_lead_not_hot(self):
        from modules.crm.models.lead import Lead

        assert Lead(name="C", email="c@c.com", score=30, status="new").is_hot is False

    def test_lead_not_qualified(self):
        from modules.crm.models.lead import Lead

        assert Lead(name="N", email="n@n.com", score=50, status="new").is_qualified is False


# ===========================================================================
# 9. MARKETING CONTROLLER — Lógica (mock DB)
# ===========================================================================


class TestMarketingControllerLogic:
    @pytest.mark.asyncio
    async def test_listar_campanhas_empty(self):
        from modules.crm.controllers.marketing_controller import listar_campanhas

        db = _mock_db()
        result_mock = MagicMock()
        result_mock.fetchall.return_value = []
        db.execute.return_value = result_mock
        result = await listar_campanhas(db=db)
        assert result["items"] == [] and result["total"] == 0

    @pytest.mark.asyncio
    async def test_criar_campanha(self):
        from modules.crm.controllers.marketing_controller import CampaignCreate, criar_campanha

        db = _mock_db()
        cid = _uid()
        row = MagicMock()
        row.__getitem__ = lambda s, i: cid
        rm = MagicMock()
        rm.fetchone.return_value = row
        db.execute.return_value = rm
        result = await criar_campanha(data=CampaignCreate(name="Nova", type="fb", budget=3000), db=db)
        assert result["id"] == cid
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_atualizar_campanha(self):
        from modules.crm.controllers.marketing_controller import CampaignCreate, atualizar_campanha

        db = _mock_db()
        cid = _uid()
        result = await atualizar_campanha(campaign_id=cid, data=CampaignCreate(name="Atualizada"), db=db)
        assert result["id"] == cid

    @pytest.mark.asyncio
    async def test_criar_mkt_lead(self):
        from modules.crm.controllers.marketing_controller import MktLeadCreate, criar_mkt_lead

        db = _mock_db()
        lid = _uid()
        row = MagicMock()
        row.__getitem__ = lambda s, i: lid
        rm = MagicMock()
        rm.fetchone.return_value = row
        db.execute.return_value = rm
        result = await criar_mkt_lead(data=MktLeadCreate(name="Lead FB", source="fb"), db=db)
        assert result["id"] == lid

    @pytest.mark.asyncio
    async def test_stats_mkt_leads(self):
        from modules.crm.controllers.marketing_controller import stats_mkt_leads

        db = _mock_db()
        rm = MagicMock()
        rm.fetchall.return_value = [("Google Ads", 50, 20, 15, 10, 3, 2, Decimal("6.0"))]
        db.execute.return_value = rm
        result = await stats_mkt_leads(db=db)
        assert result["campanhas"][0]["total"] == 50

    @pytest.mark.asyncio
    async def test_converter_lead_not_found(self):
        from fastapi import HTTPException

        from modules.crm.controllers.marketing_controller import converter_lead_para_crm

        db = _mock_db()
        rm = MagicMock()
        rm.fetchone.return_value = None
        db.execute.return_value = rm
        with pytest.raises(HTTPException) as exc:
            await converter_lead_para_crm(lead_id=_uid(), db=db)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_converter_lead_already_converted(self):
        from modules.crm.controllers.marketing_controller import converter_lead_para_crm

        db = _mock_db()
        crm_id = _uid()
        mkt_lead = _row(
            id=_uid(),
            name="JC",
            email="jc@t.com",
            phone=None,
            whatsapp=None,
            source="google",
            status="converted",
            campaign_id=None,
            crm_lead_id=crm_id,
        )
        rm = MagicMock()
        rm.fetchone.return_value = mkt_lead
        db.execute.return_value = rm
        result = await converter_lead_para_crm(lead_id=_uid(), db=db)
        assert "ja convertido" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_converter_licitacao_para_crm(self):
        from modules.crm.controllers.marketing_controller import LicitacaoConvertRequest, converter_licitacao_para_crm

        db = _mock_db()
        cid = _uid()
        row = MagicMock()
        row.__getitem__ = lambda s, i: cid
        rm = MagicMock()
        rm.fetchone.return_value = row
        db.execute.return_value = rm
        data = LicitacaoConvertRequest(orgao="SEMSA", objeto="Vig", valor=800000, numero_edital="PE-042")
        result = await converter_licitacao_para_crm(data=data, db=db)
        assert result["crm_lead_id"] == cid
        db.commit.assert_awaited_once()


# ===========================================================================
# 10. CLIENT CONTROLLER — Lógica (mock DB)
# ===========================================================================


class TestClientControllerLogic:
    @pytest.mark.asyncio
    async def test_listar_clientes_empty(self):
        from modules.crm.controllers.client_controller import listar_clientes

        db = _mock_db()
        rm = MagicMock()
        rm.fetchall.return_value = []
        db.execute.return_value = rm
        result = await listar_clientes(db=db)
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_resumo_clientes(self):
        from modules.crm.controllers.client_controller import resumo_clientes

        db = _mock_db()
        vals = [13, 2, 1, 3, 5, Decimal("272086.96"), 4]
        row = MagicMock()
        row.__getitem__ = lambda s, i: vals[i]
        rm = MagicMock()
        rm.fetchone.return_value = row
        db.execute.return_value = rm
        result = await resumo_clientes(db=db)
        assert result["clientes_ativos"] == 13
        assert result["mrr_total"] == 272086.96

    @pytest.mark.asyncio
    async def test_detalhe_cliente_not_found(self):
        from fastapi import HTTPException

        from modules.crm.controllers.client_controller import detalhe_cliente

        db = _mock_db()
        rm = MagicMock()
        rm.fetchone.return_value = None
        db.execute.return_value = rm
        with pytest.raises(HTTPException) as exc:
            await detalhe_cliente(client_id=uuid.uuid4(), db=db)
        assert exc.value.status_code == 404


# ===========================================================================
# 11. CONTACT CONTROLLER — Lógica (mock DB)
# ===========================================================================


class TestContactControllerLogic:
    @pytest.mark.asyncio
    async def test_listar_contatos_empty(self):
        from modules.crm.controllers.contact_controller import listar_contatos

        db = _mock_db()
        rm = MagicMock()
        rm.fetchall.return_value = []
        db.execute.return_value = rm
        result = await listar_contatos(db=db)
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_criar_contato(self):
        from modules.crm.controllers.contact_controller import ContactCreate, criar_contato

        db = _mock_db()
        cid = _uid()
        row = MagicMock()
        row.__getitem__ = lambda s, i: cid
        rm = MagicMock()
        rm.fetchone.return_value = row
        db.execute.return_value = rm
        data = ContactCreate(client_id=_uid(), name="João", role="Síndico", is_primary=True)
        result = await criar_contato(data=data, db=db)
        assert result["id"] == cid

    @pytest.mark.asyncio
    async def test_deletar_contato(self):
        from modules.crm.controllers.contact_controller import deletar_contato

        db = _mock_db()
        result = await deletar_contato(contact_id=uuid.uuid4(), db=db)
        assert "removido" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_atividades_recentes_empty(self):
        from modules.crm.controllers.contact_controller import atividades_recentes

        db = _mock_db()
        rm = MagicMock()
        rm.fetchall.return_value = []
        db.execute.return_value = rm
        assert (await atividades_recentes(db=db))["items"] == []

    @pytest.mark.asyncio
    async def test_criar_atividade(self):
        from modules.crm.controllers.contact_controller import ActivityCreate, criar_atividade

        db = _mock_db()
        aid = _uid()
        row = MagicMock()
        row.__getitem__ = lambda s, i: aid
        rm = MagicMock()
        rm.fetchone.return_value = row
        db.execute.return_value = rm
        data = ActivityCreate(client_id=_uid(), type="call", subject="Ligação")
        result = await criar_atividade(data=data, db=db)
        assert result["id"] == aid

    @pytest.mark.asyncio
    async def test_visao_360_not_found(self):
        from fastapi import HTTPException

        from modules.crm.controllers.contact_controller import visao_360_cliente

        db = _mock_db()
        rm = MagicMock()
        rm.fetchone.return_value = None
        db.execute.return_value = rm
        with pytest.raises(HTTPException) as exc:
            await visao_360_cliente(client_id=uuid.uuid4(), db=db)
        assert exc.value.status_code == 404
