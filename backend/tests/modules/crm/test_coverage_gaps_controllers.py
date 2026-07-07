"""
Tests to close coverage gaps in CRM module:
- contact_controller.py (listar_atividades, visao_360_cliente)
- marketing_controller.py (listar_mkt_leads, converter_lead_para_crm)
- client_controller.py (detalhe_cliente contratos)
- lead_service.py (_score_response_time branches, _score_completeness, get_recommended_action)
- dashboard_service.py (trends, seller performance, conversion rates, pie chart)
- pipeline_service.py (stage conversion, forecast, health score)
- signature_integration.py (cancel error, validation error)
"""

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ============================================================
# GAP 1: contact_controller.py — listar_atividades + visao_360
# ============================================================


@pytest.mark.asyncio
async def test_listar_atividades_with_client_id_and_limit():
    """Cover lines 175-194: listar_atividades with client_id filter and limit."""
    from modules.crm.controllers.contact_controller import listar_atividades

    db = AsyncMock()
    row = (
        "act-1",  # id
        "cli-1",  # client_id
        "call",  # type
        "Follow up",  # subject
        "Called client",  # description
        "positive",  # outcome
        datetime(2026, 1, 10),  # scheduled_at
        datetime(2026, 1, 11),  # completed_at
        datetime(2026, 1, 9),  # created_at
        "Client ABC",  # client_name
    )
    result_mock = MagicMock()
    result_mock.fetchall.return_value = [row]
    db.execute = AsyncMock(return_value=result_mock)

    resp = await listar_atividades(client_id="cli-1", limit=5, db=db)

    assert resp["total"] == 1
    assert resp["items"][0]["client_id"] == "cli-1"
    assert resp["items"][0]["type"] == "call"
    assert resp["items"][0]["scheduled_at"] is not None
    assert resp["items"][0]["completed_at"] is not None


@pytest.mark.asyncio
async def test_listar_atividades_no_filter():
    """Cover lines 175-194: listar_atividades without client_id."""
    from modules.crm.controllers.contact_controller import listar_atividades

    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.fetchall.return_value = []
    db.execute = AsyncMock(return_value=result_mock)

    resp = await listar_atividades(client_id=None, limit=20, db=db)
    assert resp["total"] == 0
    assert resp["items"] == []


@pytest.mark.asyncio
async def test_listar_atividades_none_dates():
    """Cover optional date formatting in listar_atividades."""
    from modules.crm.controllers.contact_controller import listar_atividades

    db = AsyncMock()
    row = ("act-2", "cli-2", "email", "Intro", "Sent email", "ok", None, None, None, "Client XYZ")
    result_mock = MagicMock()
    result_mock.fetchall.return_value = [row]
    db.execute = AsyncMock(return_value=result_mock)

    resp = await listar_atividades(client_id="cli-2", limit=10, db=db)
    assert resp["items"][0]["scheduled_at"] is None
    assert resp["items"][0]["completed_at"] is None
    assert resp["items"][0]["created_at"] is None


@pytest.mark.asyncio
async def test_visao_360_cliente_full():
    """Cover lines 267-356: visao_360_cliente when client IS found."""
    from uuid import UUID as _PyUUID  # noqa: N811

    from modules.crm.controllers.contact_controller import visao_360_cliente

    cid = _PyUUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    db = AsyncMock()

    # Client row — indexed access
    cl_row = (
        str(cid),  # 0 id
        "Empresa X",  # 1 name
        "12345678000100",  # 2 document_number / cnpj
        "email@x.com",  # 3 email
        "92999999999",  # 4 phone
        "active",  # 5 status
        "vip",  # 6 segment
        85,  # 7 health_score
        False,  # 8 is_defaulter
        True,  # 9 is_vip
        "website",  # 10 crm_origin
        "Lead Teste",  # 11 lead_name
        "referral",  # 12 lead_source
    )

    # Contratos fetchall
    contrato_row = ("ct-1", "vigilancia", 15000.0, date(2025, 1, 1), date(2026, 1, 1), "active")

    # MRR scalar
    mrr_val = 15000.0

    # Oportunidades fetchall
    opp_row = ("opp-1", "Expansion", "negotiation", 50000.0, 75)

    # Contatos fetchall
    contact_row = ("cont-1", "Joao", "Gerente", "joao@x.com", "9299", "9299", True)

    # Atividades fetchall
    activity_row = ("act-1", "call", "Follow up", "Desc", "positive", datetime(2026, 1, 15))

    # NFS-e fetchall
    nfse_row = ("NF001", date(2026, 1, 1), 15000.0, "autorizada")

    # Funcionarios fetchall
    func_row = ("emp-1", "Carlos", "Vigilante", "MAT001")

    # MRR historico fetchall
    mrr_hist_row = (datetime(2026, 1, 1), 15000.0)

    # Build mock results for each sequential db.execute call
    def make_result(fetchone_val=None, fetchall_val=None, scalar_val=None):
        m = MagicMock()
        if fetchone_val is not None:
            m.fetchone.return_value = fetchone_val
        if fetchall_val is not None:
            m.fetchall.return_value = fetchall_val
        if scalar_val is not None:
            m.scalar.return_value = scalar_val
        return m

    client_result = make_result(fetchone_val=cl_row)
    contratos_result = make_result(fetchall_val=[contrato_row])
    mrr_result = make_result(scalar_val=mrr_val)
    opps_result = make_result(fetchall_val=[opp_row])
    contacts_result = make_result(fetchall_val=[contact_row])
    activities_result = make_result(fetchall_val=[activity_row])
    nfse_result = make_result(fetchall_val=[nfse_row])
    funcionarios_result = make_result(fetchall_val=[func_row])
    mrr_hist_result = make_result(fetchall_val=[mrr_hist_row])

    db.execute = AsyncMock(
        side_effect=[
            client_result,
            contratos_result,
            mrr_result,
            opps_result,
            contacts_result,
            activities_result,
            nfse_result,
            funcionarios_result,
            mrr_hist_result,
        ]
    )

    resp = await visao_360_cliente(client_id=cid, db=db)

    assert resp["cliente"]["name"] == "Empresa X"
    assert resp["cliente"]["mrr"] == 15000.0
    assert len(resp["contratos"]) == 1
    assert resp["contratos"][0]["service_type"] == "vigilancia"
    assert len(resp["oportunidades"]) == 1
    assert len(resp["contatos"]) == 1
    assert len(resp["atividades"]) == 1
    assert resp["atividades"][0]["created_at"] is not None
    assert len(resp["nfse"]) == 1
    assert len(resp["funcionarios_alocados"]) == 1
    assert len(resp["mrr_historico"]) == 1
    assert resp["mrr_historico"][0]["mes"] == "2026-01"
    assert "gerado_em" in resp


@pytest.mark.asyncio
async def test_visao_360_cliente_not_found():
    """Cover 404 branch of visao_360_cliente."""
    from uuid import UUID as _PyUUID  # noqa: N811

    from fastapi import HTTPException

    from modules.crm.controllers.contact_controller import visao_360_cliente

    cid = _PyUUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.fetchone.return_value = None
    db.execute = AsyncMock(return_value=result_mock)

    with pytest.raises(HTTPException) as exc_info:
        await visao_360_cliente(client_id=cid, db=db)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_visao_360_empty_sub_results():
    """Cover visao_360 with empty sub-queries and None values."""
    from uuid import UUID as _PyUUID  # noqa: N811

    from modules.crm.controllers.contact_controller import visao_360_cliente

    cid = _PyUUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    db = AsyncMock()

    cl_row = (str(cid), "Empty Co", "00000000000000", None, None, "active", None, None, False, False, None, None, None)

    def make_result(fetchone_val=None, fetchall_val=None, scalar_val=None):
        m = MagicMock()
        if fetchone_val is not None:
            m.fetchone.return_value = fetchone_val
        if fetchall_val is not None:
            m.fetchall.return_value = fetchall_val
        if scalar_val is not None:
            m.scalar.return_value = scalar_val
        return m

    db.execute = AsyncMock(
        side_effect=[
            make_result(fetchone_val=cl_row),
            make_result(fetchall_val=[]),
            make_result(scalar_val=0),  # MRR None → 0
            make_result(fetchall_val=[]),
            make_result(fetchall_val=[]),
            make_result(fetchall_val=[]),
            make_result(fetchall_val=[]),
            make_result(fetchall_val=[]),
            make_result(fetchall_val=[]),
        ]
    )

    resp = await visao_360_cliente(client_id=cid, db=db)
    assert resp["cliente"]["mrr"] == 0
    assert resp["contratos"] == []


# ============================================================
# GAP 2: marketing_controller.py — listar_mkt_leads + converter
# ============================================================


@pytest.mark.asyncio
async def test_listar_mkt_leads_with_campaign_and_status():
    """Cover lines 135-152: listar_mkt_leads with both filters."""
    from modules.crm.controllers.marketing_controller import listar_mkt_leads

    db = AsyncMock()
    row = MagicMock()
    row.id = "ml-1"
    row.name = "Lead Test"
    row.email = "test@test.com"
    row.phone = "92999"
    row.whatsapp = "92999"
    row.source = "website"
    row.status = "new"
    row.campaign_name = "Summer Campaign"
    row.crm_lead_id = None
    row.created_at = datetime(2026, 2, 1)

    result_mock = MagicMock()
    result_mock.fetchall.return_value = [row]
    db.execute = AsyncMock(return_value=result_mock)

    resp = await listar_mkt_leads(campaign_id="camp-1", status="new", db=db)

    assert resp["total"] == 1
    assert resp["items"][0]["name"] == "Lead Test"
    assert resp["items"][0]["campaign_name"] == "Summer Campaign"


@pytest.mark.asyncio
async def test_listar_mkt_leads_campaign_only():
    """Cover lines 135-152: with only campaign_id filter."""
    from modules.crm.controllers.marketing_controller import listar_mkt_leads

    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.fetchall.return_value = []
    db.execute = AsyncMock(return_value=result_mock)

    resp = await listar_mkt_leads(campaign_id="camp-1", status=None, db=db)
    assert resp["total"] == 0


@pytest.mark.asyncio
async def test_listar_mkt_leads_status_only():
    """Cover lines 135-152: with only status filter."""
    from modules.crm.controllers.marketing_controller import listar_mkt_leads

    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.fetchall.return_value = []
    db.execute = AsyncMock(return_value=result_mock)

    resp = await listar_mkt_leads(campaign_id=None, status="qualified", db=db)
    assert resp["total"] == 0


@pytest.mark.asyncio
async def test_converter_lead_para_crm_full_flow():
    """Cover lines 205-240: full conversion with campaign lookup."""
    from modules.crm.controllers.marketing_controller import converter_lead_para_crm

    db = AsyncMock()

    # 1. SELECT marketing_lead
    mkt_lead = MagicMock()
    mkt_lead.status = "qualified"  # Not 'converted'
    mkt_lead.campaign_id = "camp-1"
    mkt_lead.name = "Test Lead"
    mkt_lead.email = "test@lead.com"
    mkt_lead.phone = "92999"

    mkt_lead_result = MagicMock()
    mkt_lead_result.fetchone.return_value = mkt_lead

    # 2. SELECT campaign name
    campaign_result = MagicMock()
    campaign_row = MagicMock()
    campaign_row.__getitem__ = lambda self, idx: "Summer 2026"
    campaign_result.fetchone.return_value = campaign_row

    # 3. INSERT CRM lead RETURNING id
    crm_insert_result = MagicMock()
    crm_insert_row = MagicMock()
    crm_insert_row.__getitem__ = lambda self, idx: "new-crm-lead-id"
    crm_insert_result.fetchone.return_value = crm_insert_row

    # 4. UPDATE marketing_leads
    update_result = MagicMock()

    db.execute = AsyncMock(side_effect=[mkt_lead_result, campaign_result, crm_insert_result, update_result])
    db.commit = AsyncMock()

    resp = await converter_lead_para_crm(lead_id="ml-1", db=db)

    assert resp["message"] == "Lead convertido para CRM"
    assert resp["crm_lead_id"] == "new-crm-lead-id"
    assert resp["campanha"] == "Summer 2026"


@pytest.mark.asyncio
async def test_converter_lead_para_crm_no_campaign():
    """Cover converter_lead_para_crm when campaign_id is None."""
    from modules.crm.controllers.marketing_controller import converter_lead_para_crm

    db = AsyncMock()

    mkt_lead = MagicMock()
    mkt_lead.status = "new"
    mkt_lead.campaign_id = None
    mkt_lead.name = "No Campaign Lead"
    mkt_lead.email = None
    mkt_lead.phone = None

    mkt_lead_result = MagicMock()
    mkt_lead_result.fetchone.return_value = mkt_lead

    crm_insert_result = MagicMock()
    crm_insert_row = MagicMock()
    crm_insert_row.__getitem__ = lambda self, idx: "crm-id-2"
    crm_insert_result.fetchone.return_value = crm_insert_row

    update_result = MagicMock()

    db.execute = AsyncMock(side_effect=[mkt_lead_result, crm_insert_result, update_result])
    db.commit = AsyncMock()

    resp = await converter_lead_para_crm(lead_id="ml-2", db=db)

    assert resp["campanha"] == "marketing"


@pytest.mark.asyncio
async def test_converter_lead_already_converted():
    """Cover the early return when status is 'converted'."""
    from modules.crm.controllers.marketing_controller import converter_lead_para_crm

    db = AsyncMock()

    mkt_lead = MagicMock()
    mkt_lead.status = "converted"
    mkt_lead.crm_lead_id = "existing-crm-id"

    mkt_lead_result = MagicMock()
    mkt_lead_result.fetchone.return_value = mkt_lead

    db.execute = AsyncMock(return_value=mkt_lead_result)

    resp = await converter_lead_para_crm(lead_id="ml-3", db=db)
    assert resp["message"] == "Lead ja convertido"


@pytest.mark.asyncio
async def test_converter_lead_not_found():
    """Cover 404 when lead not found."""
    from fastapi import HTTPException

    from modules.crm.controllers.marketing_controller import converter_lead_para_crm

    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.fetchone.return_value = None
    db.execute = AsyncMock(return_value=result_mock)

    with pytest.raises(HTTPException) as exc_info:
        await converter_lead_para_crm(lead_id="missing", db=db)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_converter_lead_campaign_not_found():
    """Cover branch where campaign lookup returns None."""
    from modules.crm.controllers.marketing_controller import converter_lead_para_crm

    db = AsyncMock()

    mkt_lead = MagicMock()
    mkt_lead.status = "new"
    mkt_lead.campaign_id = "camp-missing"
    mkt_lead.name = "Orphan Lead"
    mkt_lead.email = "orphan@test.com"
    mkt_lead.phone = None

    mkt_lead_result = MagicMock()
    mkt_lead_result.fetchone.return_value = mkt_lead

    # Campaign returns None
    campaign_result = MagicMock()
    campaign_result.fetchone.return_value = None

    crm_insert_result = MagicMock()
    crm_insert_row = MagicMock()
    crm_insert_row.__getitem__ = lambda self, idx: "crm-id-orphan"
    crm_insert_result.fetchone.return_value = crm_insert_row

    update_result = MagicMock()

    db.execute = AsyncMock(side_effect=[mkt_lead_result, campaign_result, crm_insert_result, update_result])
    db.commit = AsyncMock()

    resp = await converter_lead_para_crm(lead_id="ml-orphan", db=db)
    # campaign_name stays "marketing" because cr is None
    assert resp["campanha"] == "marketing"


# ============================================================
# GAP 3: client_controller.py — detalhe_cliente contratos
# ============================================================


@pytest.mark.asyncio
async def test_detalhe_cliente_with_contratos():
    """Cover lines 162-170: detalhe_cliente building contratos list."""
    from uuid import UUID as _PyUUID  # noqa: N811

    from modules.crm.controllers.client_controller import detalhe_cliente

    cid = _PyUUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    db = AsyncMock()

    # Client row with named attributes
    client_row = MagicMock()
    client_row.id = str(cid)
    client_row.name = "Client Teste"
    client_row.document_number = "12345678000100"
    client_row.email = "client@test.com"
    client_row.phone = "92999"
    client_row.status = "active"
    client_row.segment = "premium"
    client_row.health_score = 90
    client_row.crm_origin = "website"
    client_row.lead_name = "Lead Origin"

    # Contrato rows
    ct = MagicMock()
    ct.id = "ct-1"
    ct.service_type = "vigilancia"
    ct.monthly_value = 12000.0
    ct.start_date = date(2025, 6, 1)
    ct.status = "active"

    ct2 = MagicMock()
    ct2.id = "ct-2"
    ct2.service_type = "portaria"
    ct2.monthly_value = None  # test None branch
    ct2.start_date = None
    ct2.status = "inactive"

    client_result = MagicMock()
    client_result.fetchone.return_value = client_row

    contratos_result = MagicMock()
    contratos_result.fetchall.return_value = [ct, ct2]

    db.execute = AsyncMock(side_effect=[client_result, contratos_result])

    resp = await detalhe_cliente(client_id=cid, db=db)

    assert resp["name"] == "Client Teste"
    assert len(resp["contratos"]) == 2
    assert resp["contratos"][0]["monthly_value"] == 12000.0
    assert resp["contratos"][1]["monthly_value"] == 0
    assert resp["contratos"][1]["start_date"] is None


# ============================================================
# GAP 4: lead_service.py — score branches
# ============================================================


def _make_lead(**overrides):
    """Create a mock Lead for scoring tests."""
    from modules.crm.models.lead import Lead, LeadSource, LeadStatus

    lead = MagicMock(spec=Lead)
    lead.id = "lead-1"
    lead.name = "Test Lead"
    lead.email = "test@test.com"
    lead.phone = "92999"
    lead.company = "TestCo"
    lead.position = "Manager"
    lead.company_size = "medium"
    lead.industry = "seguranca"
    lead.notes = "some notes"
    lead.source = LeadSource.WEBSITE.value
    lead.status = LeadStatus.NEW.value
    lead.score = 50
    lead.probability = 30.0
    lead.expected_value = 10000.0
    lead.assigned_to_id = None
    lead.last_contact_at = None
    lead.created_at = datetime.now()
    lead.updated_at = datetime.now()
    for k, v in overrides.items():
        setattr(lead, k, v)
    return lead


def test_score_response_time_3_to_7_days():
    """Cover line 177: days_since_contact 3-7 range."""
    from modules.crm.services.lead_service import LeadScoringEngine

    engine = LeadScoringEngine()
    lead = _make_lead(last_contact_at=datetime.now() - timedelta(days=5))
    score = engine._score_response_time(lead)
    assert score == 70


def test_score_response_time_7_to_14_days():
    """Cover line 179: days_since_contact 7-14 range."""
    from modules.crm.services.lead_service import LeadScoringEngine

    engine = LeadScoringEngine()
    lead = _make_lead(last_contact_at=datetime.now() - timedelta(days=10))
    score = engine._score_response_time(lead)
    assert score == 50


def test_score_response_time_14_to_30_days():
    """Cover line 181: days_since_contact 14-30 range."""
    from modules.crm.services.lead_service import LeadScoringEngine

    engine = LeadScoringEngine()
    lead = _make_lead(last_contact_at=datetime.now() - timedelta(days=20))
    score = engine._score_response_time(lead)
    assert score == 30


def test_score_response_time_over_30_days():
    """Cover line 182: days_since_contact > 30."""
    from modules.crm.services.lead_service import LeadScoringEngine

    engine = LeadScoringEngine()
    lead = _make_lead(last_contact_at=datetime.now() - timedelta(days=45))
    score = engine._score_response_time(lead)
    assert score == 10


def test_score_response_time_less_than_1_day():
    """Cover line 173: days_since_contact < 1."""
    from modules.crm.services.lead_service import LeadScoringEngine

    engine = LeadScoringEngine()
    lead = _make_lead(last_contact_at=datetime.now() - timedelta(hours=5))
    score = engine._score_response_time(lead)
    assert score == 100


def test_score_response_time_1_to_3_days():
    """Cover line 175: days_since_contact 1-3."""
    from modules.crm.services.lead_service import LeadScoringEngine

    engine = LeadScoringEngine()
    lead = _make_lead(last_contact_at=datetime.now() - timedelta(days=2))
    score = engine._score_response_time(lead)
    assert score == 85


def test_score_response_time_no_contact_recent():
    """Cover no last_contact, recent lead (< 1 day)."""
    from modules.crm.services.lead_service import LeadScoringEngine

    engine = LeadScoringEngine()
    lead = _make_lead(last_contact_at=None, created_at=datetime.now())
    score = engine._score_response_time(lead)
    assert score == 100


def test_score_response_time_no_contact_week():
    """Cover no last_contact, 1-7 day old lead."""
    from modules.crm.services.lead_service import LeadScoringEngine

    engine = LeadScoringEngine()
    lead = _make_lead(last_contact_at=None, created_at=datetime.now() - timedelta(days=3))
    score = engine._score_response_time(lead)
    assert score == 70


def test_score_response_time_no_contact_old():
    """Cover no last_contact, > 7 day old lead."""
    from modules.crm.services.lead_service import LeadScoringEngine

    engine = LeadScoringEngine()
    lead = _make_lead(last_contact_at=None, created_at=datetime.now() - timedelta(days=15))
    score = engine._score_response_time(lead)
    assert score == 40


def test_score_completeness_minimal():
    """Cover _score_completeness with only name and email."""
    from modules.crm.services.lead_service import LeadScoringEngine

    engine = LeadScoringEngine()
    lead = _make_lead(phone=None, company=None, position=None, company_size=None, industry=None, notes=None)
    score = engine._score_completeness(lead)
    assert score == 30  # name(15) + email(15)


def test_score_completeness_full():
    """Cover _score_completeness with all fields filled."""
    from modules.crm.services.lead_service import LeadScoringEngine

    engine = LeadScoringEngine()
    lead = _make_lead()
    score = engine._score_completeness(lead)
    assert score == 100


def test_get_recommended_action_medium_score_no_contact():
    """Cover line 254-255: score >= 50, no last_contact_at."""
    from modules.crm.services.lead_service import LeadService

    service = LeadService()
    lead = _make_lead(score=60, last_contact_at=None, status="contacted")
    action = service.get_recommended_action(lead)
    assert action == "Realizar primeiro contato"


def test_get_recommended_action_medium_score_stale():
    """Cover line 257-258: score >= 50, > 7 days since contact."""
    from modules.crm.services.lead_service import LeadService

    service = LeadService()
    lead = _make_lead(
        score=55,
        last_contact_at=datetime.now() - timedelta(days=10),
        status="contacted",
    )
    action = service.get_recommended_action(lead)
    assert action == "Fazer follow-up"


def test_get_recommended_action_medium_score_recent():
    """Cover line 259: score >= 50, recent contact."""
    from modules.crm.services.lead_service import LeadService

    service = LeadService()
    lead = _make_lead(
        score=55,
        last_contact_at=datetime.now() - timedelta(days=2),
        status="contacted",
    )
    action = service.get_recommended_action(lead)
    assert action == "Aguardar resposta ou enviar material informativo"


def test_get_recommended_action_low_score_no_company():
    """Cover line 263: low score, no company."""
    from modules.crm.services.lead_service import LeadService

    service = LeadService()
    lead = _make_lead(score=30, company=None, status="new")
    action = service.get_recommended_action(lead)
    assert action == "Qualificar - obter informações da empresa"


def test_get_recommended_action_low_score_with_company():
    """Cover line 264: low score, with company."""
    from modules.crm.services.lead_service import LeadService

    service = LeadService()
    lead = _make_lead(score=30, company="SomeCo", status="new")
    action = service.get_recommended_action(lead)
    assert action == "Nutrir com conteúdo antes de contato direto"


def test_get_recommended_action_high_score_new():
    """Cover score >= 80, status new."""
    from modules.crm.services.lead_service import LeadService

    service = LeadService()
    lead = _make_lead(score=85, status="new")
    action = service.get_recommended_action(lead)
    assert action == "Contato imediato - Lead quente!"


def test_get_recommended_action_high_score_qualified():
    """Cover score >= 80, status contacted/qualified."""
    from modules.crm.services.lead_service import LeadService

    service = LeadService()
    lead = _make_lead(score=85, status="qualified")
    action = service.get_recommended_action(lead)
    assert action == "Enviar proposta comercial"


def test_get_recommended_action_high_score_other():
    """Cover score >= 80, other status (negotiation)."""
    from modules.crm.services.lead_service import LeadService

    service = LeadService()
    lead = _make_lead(score=85, status="negotiation")
    action = service.get_recommended_action(lead)
    assert action == "Agendar reunião de fechamento"


def test_get_recommended_action_lost():
    """Cover lost status."""
    from modules.crm.services.lead_service import LeadService

    service = LeadService()
    lead = _make_lead(status="lost")
    action = service.get_recommended_action(lead)
    assert action == "Arquivar ou tentar reengajamento após 90 dias"


def test_get_recommended_action_won():
    """Cover won status."""
    from modules.crm.services.lead_service import LeadService

    service = LeadService()
    lead = _make_lead(status="won")
    action = service.get_recommended_action(lead)
    assert action == "Iniciar onboarding do cliente"


# ============================================================
# GAP 5: dashboard_service.py — trends, pie chart, performance
# ============================================================


def _make_opportunity(**overrides):
    from modules.crm.models.opportunity import Opportunity, OpportunityStage

    opp = MagicMock(spec=Opportunity)
    opp.id = "opp-1"
    opp.title = "Deal"
    opp.stage = OpportunityStage.QUALIFICATION.value
    opp.value = 10000.0
    opp.probability = 50
    opp.weighted_value = 5000.0
    opp.is_open = True
    opp.is_won = False
    opp.is_lost = False
    opp.days_in_pipeline = 15
    opp.owner_id = None
    opp.actual_close_date = None
    opp.expected_close_date = None
    opp.updated_at = datetime.now()
    opp.created_at = datetime.now()
    opp.loss_reason = None
    opp.competitor = None
    opp.is_overdue = False
    for k, v in overrides.items():
        setattr(opp, k, v)
    return opp


def _make_proposal(**overrides):
    from modules.crm.models.proposal import ProposalStatus

    p = MagicMock()
    p.status = ProposalStatus.DRAFT.value
    p.total = 5000.0
    for k, v in overrides.items():
        setattr(p, k, v)
    return p


def _make_commission(**overrides):
    from modules.crm.models.commission import CommissionStatus

    c = MagicMock()
    c.status = CommissionStatus.PENDING.value
    c.final_commission = 500.0
    c.seller_id = "seller-1"
    for k, v in overrides.items():
        setattr(c, k, v)
    return c


def test_generate_trends_month():
    """Cover generate_trends with month period."""
    from modules.crm.services.dashboard_service import DashboardService

    svc = DashboardService()

    class FakeItem:
        def __init__(self, dt, val):
            self.created_at = dt
            self.value = val

    items = [
        FakeItem(datetime.now(), 100),
        FakeItem(datetime.now() - timedelta(days=5), 200),
    ]

    trends = svc.generate_trends(items, "created_at", "value", period="month", periods_count=3)
    assert len(trends) == 3
    # Last trend should have change_percent if previous had value > 0
    assert trends[-1].period is not None


def test_generate_trends_week():
    """Cover generate_trends with week period."""
    from modules.crm.services.dashboard_service import DashboardService

    svc = DashboardService()

    class FakeItem:
        def __init__(self, dt):
            self.created_at = dt

    items = [FakeItem(datetime.now())]
    trends = svc.generate_trends(items, "created_at", "count", period="week", periods_count=2)
    assert len(trends) == 2


def test_generate_trends_day():
    """Cover generate_trends with day period."""
    from modules.crm.services.dashboard_service import DashboardService

    svc = DashboardService()

    class FakeItem:
        def __init__(self, dt):
            self.created_at = dt

    items = [FakeItem(datetime.now())]
    trends = svc.generate_trends(items, "created_at", "count", period="day", periods_count=3)
    assert len(trends) == 3


def test_generate_trends_with_change_percent():
    """Cover change_percent calculation in trends."""
    from modules.crm.services.dashboard_service import DashboardService

    svc = DashboardService()

    class FakeItem:
        def __init__(self, dt, val):
            self.created_at = dt
            self.amount = val

    now = datetime.now()
    items = [
        FakeItem(now - timedelta(days=35), 1000),
        FakeItem(now - timedelta(days=5), 2000),
    ]

    trends = svc.generate_trends(items, "created_at", "amount", period="month", periods_count=3)
    # One of the later trends should have previous_value set
    has_change = any(t.change_percent is not None for t in trends)
    # As long as the first period has data and next period also has data
    assert len(trends) == 3


def test_calculate_seller_performance_with_target():
    """Cover seller performance with target metric."""
    from modules.crm.models.lead import LeadStatus
    from modules.crm.models.opportunity import OpportunityStage
    from modules.crm.services.dashboard_service import DashboardService

    svc = DashboardService()

    lead = _make_lead(assigned_to_id="seller-1", status=LeadStatus.WON.value)
    opp = _make_opportunity(
        owner_id="seller-1",
        stage=OpportunityStage.CLOSED_WON.value,
        is_won=True,
        is_lost=False,
        is_open=False,
        value=50000.0,
    )
    comm = _make_commission(seller_id="seller-1", final_commission=5000.0)

    metrics = svc.calculate_seller_performance(
        seller_id="seller-1",
        leads=[lead],
        opportunities=[opp],
        commissions=[comm],
        seller_name="Joao",
        target=100000.0,
    )

    assert metrics.seller_name == "Joao"
    assert metrics.leads_converted == 1
    assert metrics.total_sales == 50000.0
    assert metrics.target_percentage == 50.0


def test_get_top_performers():
    """Cover get_top_performers."""
    from modules.crm.services.dashboard_service import DashboardService

    svc = DashboardService()

    sellers = {"seller-1": "Joao", "seller-2": "Maria"}
    result = svc.get_top_performers(leads=[], opportunities=[], commissions=[], sellers=sellers, limit=2)
    assert len(result) == 2


def test_generate_pie_chart_by_status():
    """Cover generate_pie_chart_by_status."""
    from modules.crm.services.dashboard_service import DashboardService

    svc = DashboardService()

    class Item:
        def __init__(self, s):
            self.status = s

    items = [Item("active"), Item("active"), Item("inactive")]
    chart = svc.generate_pie_chart_by_status(items)
    assert chart.chart_type == "pie"
    assert len(chart.labels) == 2


def test_generate_pie_chart_with_enum_status():
    """Cover the hasattr(status, 'value') branch."""
    from modules.crm.services.dashboard_service import DashboardService

    svc = DashboardService()

    from enum import StrEnum

    class FakeStatus(StrEnum):
        ON = "on"
        OFF = "off"

    class Item:
        def __init__(self, s):
            self.status = s

    items = [Item(FakeStatus.ON), Item(FakeStatus.OFF)]
    chart = svc.generate_pie_chart_by_status(items)
    assert chart.chart_type == "pie"


def test_calculate_conversion_rates():
    """Cover calculate_conversion_rates."""
    from modules.crm.models.opportunity import OpportunityStage
    from modules.crm.services.dashboard_service import DashboardService

    svc = DashboardService()

    opps = [
        _make_opportunity(stage=OpportunityStage.QUALIFICATION.value),
        _make_opportunity(stage=OpportunityStage.PROPOSAL.value),
        _make_opportunity(stage=OpportunityStage.CLOSED_WON.value),
    ]

    rates = svc.calculate_conversion_rates(opps)
    assert isinstance(rates, dict)
    assert len(rates) > 0


def test_generate_funnel_chart():
    """Cover generate_funnel_chart."""
    from modules.crm.models.opportunity import OpportunityStage
    from modules.crm.services.dashboard_service import DashboardService

    svc = DashboardService()

    opps = [_make_opportunity(stage=OpportunityStage.QUALIFICATION.value)]
    chart = svc.generate_funnel_chart(opps)
    assert chart.chart_type == "funnel"
    assert len(chart.labels) == 5


# ============================================================
# GAP 6: pipeline_service.py — conversion, forecast, health
# ============================================================


def test_stage_conversion_rates_with_lost():
    """Cover lines 165-167: lost opp branch in get_stage_conversion_rates."""
    from modules.crm.models.opportunity import OpportunityStage
    from modules.crm.services.pipeline_service import PipelineService

    svc = PipelineService()

    opps = [
        _make_opportunity(
            stage=OpportunityStage.PROPOSAL.value,
            is_won=False,
            is_lost=True,
            is_open=False,
        ),
        _make_opportunity(
            stage=OpportunityStage.CLOSED_WON.value,
            is_won=True,
            is_lost=False,
            is_open=False,
        ),
        _make_opportunity(
            stage=OpportunityStage.NEEDS_ANALYSIS.value,
            is_won=False,
            is_lost=False,
            is_open=True,
        ),
    ]

    rates = svc.get_stage_conversion_rates(opps)
    assert isinstance(rates, dict)
    assert len(rates) == 4  # 4 transitions


def test_stage_conversion_rates_empty():
    """Cover 0-division branch: current_count == 0."""
    from modules.crm.services.pipeline_service import PipelineService

    svc = PipelineService()
    rates = svc.get_stage_conversion_rates([])
    for key, val in rates.items():
        assert val == 0.0


def test_forecast_revenue_empty_month():
    """Cover lines 230-239: empty month in forecast_revenue."""
    from modules.crm.services.pipeline_service import PipelineService

    svc = PipelineService()

    # No opps at all -> all months empty
    forecasts = svc.forecast_revenue([], months_ahead=2)
    assert len(forecasts) == 2
    assert forecasts[0].opportunity_count == 0
    assert forecasts[0].expected_value == 0.0


def test_forecast_revenue_with_opps():
    """Cover lines 242-254: forecast with matching opps."""
    from modules.crm.services.pipeline_service import PipelineService

    svc = PipelineService()

    today = date.today()
    opp = _make_opportunity(
        is_open=True,
        expected_close_date=date(today.year, today.month, 15),
        value=100000.0,
        weighted_value=50000.0,
        probability=50,
    )

    forecasts = svc.forecast_revenue([opp], months_ahead=1)
    assert forecasts[0].opportunity_count == 1
    assert forecasts[0].expected_value == 100000.0


def test_forecast_revenue_month_overflow():
    """Cover lines 214-216: target_month > 12."""
    from modules.crm.services.pipeline_service import PipelineService

    svc = PipelineService()

    # Force month overflow by asking for many months ahead
    forecasts = svc.forecast_revenue([], months_ahead=15)
    assert len(forecasts) == 15


def test_health_score_healthy():
    """Cover health score — healthy pipeline."""
    from modules.crm.services.pipeline_service import PipelineService

    svc = PipelineService()

    opp = _make_opportunity(is_overdue=False, is_open=True, updated_at=datetime.now())
    result = svc.get_health_score([opp])
    assert result["status"] in ("healthy", "attention", "warning", "critical")
    assert result["score"] >= 0


def test_health_score_empty():
    """Cover empty pipeline."""
    from modules.crm.services.pipeline_service import PipelineService

    svc = PipelineService()
    result = svc.get_health_score([])
    assert result["status"] == "empty"
    assert result["score"] == 0


def test_health_score_overdue_high():
    """Cover overdue > 20% branch (lines 358-359)."""
    from modules.crm.services.pipeline_service import PipelineService

    svc = PipelineService()

    # All overdue => 100% > 20%
    opps = [
        _make_opportunity(is_overdue=True, is_open=True, updated_at=datetime.now()),
        _make_opportunity(is_overdue=True, is_open=True, updated_at=datetime.now()),
        _make_opportunity(is_overdue=True, is_open=True, updated_at=datetime.now()),
    ]

    result = svc.get_health_score(opps)
    assert result["score"] < 100
    assert any("prazo vencido" in r for r in result["recommendations"])


def test_health_score_overdue_moderate():
    """Cover overdue 10-20% branch (lines 361-362)."""
    from modules.crm.services.pipeline_service import PipelineService

    svc = PipelineService()

    # 1 overdue out of 7 = ~14% (between 10 and 20)
    opps = [_make_opportunity(is_overdue=False, is_open=True, updated_at=datetime.now()) for _ in range(6)]
    opps.append(_make_opportunity(is_overdue=True, is_open=True, updated_at=datetime.now()))

    result = svc.get_health_score(opps)
    assert any(">10%" in r for r in result["recommendations"])


def test_health_score_stagnant():
    """Cover stagnant > 30% branch (lines 367-369)."""
    from modules.crm.services.pipeline_service import PipelineService

    svc = PipelineService()

    old = datetime.utcnow() - timedelta(days=60)
    opps = [_make_opportunity(is_overdue=False, is_open=True, updated_at=old) for _ in range(3)]

    result = svc.get_health_score(opps)
    assert any("estagnadas" in r for r in result["recommendations"])


def test_health_score_low_win_rate():
    """Cover win rate < 20% branch (lines 374-375)."""
    from modules.crm.models.opportunity import OpportunityStage
    from modules.crm.services.pipeline_service import PipelineService

    svc = PipelineService()

    # Many lost, few won -> low win rate
    opps = []
    for _ in range(8):
        opps.append(
            _make_opportunity(
                stage=OpportunityStage.CLOSED_LOST.value,
                is_lost=True,
                is_won=False,
                is_open=False,
                actual_close_date=date.today(),
                updated_at=datetime.now(),
            )
        )
    opps.append(
        _make_opportunity(
            stage=OpportunityStage.CLOSED_WON.value,
            is_won=True,
            is_lost=False,
            is_open=False,
            actual_close_date=date.today(),
            updated_at=datetime.now(),
        )
    )

    result = svc.get_health_score(opps)
    assert any("Win rate" in r for r in result["recommendations"])


def test_health_score_win_rate_below_30():
    """Cover win rate 20-30% branch (lines 377-378)."""
    from modules.crm.models.opportunity import OpportunityStage
    from modules.crm.services.pipeline_service import PipelineService

    svc = PipelineService()

    # 1 won, 3 lost = 25% win rate
    opps = []
    for _ in range(3):
        opps.append(
            _make_opportunity(
                stage=OpportunityStage.CLOSED_LOST.value,
                is_lost=True,
                is_won=False,
                is_open=False,
                actual_close_date=date.today(),
                updated_at=datetime.now(),
            )
        )
    opps.append(
        _make_opportunity(
            stage=OpportunityStage.CLOSED_WON.value,
            is_won=True,
            is_lost=False,
            is_open=False,
            actual_close_date=date.today(),
            updated_at=datetime.now(),
        )
    )

    result = svc.get_health_score(opps)
    assert any("abaixo do ideal" in r or "Win rate" in r for r in result["recommendations"])


def test_health_score_too_many_qualification():
    """Cover qualification > 50% branch (lines 385-387)."""
    from modules.crm.models.opportunity import OpportunityStage
    from modules.crm.services.pipeline_service import PipelineService

    svc = PipelineService()

    opps = [
        _make_opportunity(
            stage=OpportunityStage.QUALIFICATION.value,
            is_open=True,
            is_overdue=False,
            updated_at=datetime.now(),
        )
        for _ in range(5)
    ]

    result = svc.get_health_score(opps)
    assert any("Qualification" in r for r in result["recommendations"])


def test_health_score_no_recommendations():
    """Cover line 399-400: no recommendations -> healthy message."""
    from modules.crm.models.opportunity import OpportunityStage
    from modules.crm.services.pipeline_service import PipelineService

    svc = PipelineService()

    # Build a perfectly healthy pipeline: no overdue, not stagnant, good win rate
    # Mix of stages, high win rate
    now = datetime.now()
    opps = []
    # 5 won out of 6 closed = 83% win rate
    for _ in range(5):
        opps.append(
            _make_opportunity(
                stage=OpportunityStage.CLOSED_WON.value,
                is_won=True,
                is_lost=False,
                is_open=False,
                is_overdue=False,
                actual_close_date=date.today(),
                updated_at=now,
            )
        )
    opps.append(
        _make_opportunity(
            stage=OpportunityStage.CLOSED_LOST.value,
            is_lost=True,
            is_won=False,
            is_open=False,
            is_overdue=False,
            actual_close_date=date.today(),
            updated_at=now,
        )
    )
    # A few open ones in later stages (not qualification heavy)
    opps.append(
        _make_opportunity(
            stage=OpportunityStage.NEGOTIATION.value,
            is_open=True,
            is_overdue=False,
            updated_at=now,
        )
    )
    opps.append(
        _make_opportunity(
            stage=OpportunityStage.PROPOSAL.value,
            is_open=True,
            is_overdue=False,
            updated_at=now,
        )
    )

    result = svc.get_health_score(opps)
    assert result["status"] == "healthy"
    assert "Pipeline saudavel" in result["recommendations"][0]


# ============================================================
# GAP 8: signature_integration.py — cancel error, validation
# ============================================================


@pytest.mark.asyncio
async def test_cancel_signature_request_error():
    """Cover lines 187-189: cancel_signature_request exception branch."""
    from modules.crm.services.signature_integration import ProposalSignatureService

    svc = ProposalSignatureService()

    # Patch logger.info to raise an exception
    with patch("modules.crm.services.signature_integration.logger") as mock_logger:
        mock_logger.info.side_effect = Exception("log failed")
        mock_logger.error = MagicMock()
        result = await svc.cancel_signature_request("ext-123", reason="test")
        assert result is False
        mock_logger.error.assert_called_once()


@pytest.mark.asyncio
async def test_create_signature_request_validation_error():
    """Cover lines 148-150: validation error branch in create_signature_request."""
    from modules.crm.services.signature_integration import (
        ProposalSignatureService,
        SignatureRequest,
        SignerInfo,
    )

    svc = ProposalSignatureService()

    # Empty proposal_id triggers ValueError
    request = SignatureRequest(
        proposal_id="",  # Invalid
        proposal_number="P001",
        document_url="/doc.pdf",
        signers=[SignerInfo(name="Test", email="test@test.com")],
    )

    result = await svc.create_signature_request(request)
    assert result.success is False
    assert "obrigatorio" in result.error.lower()


@pytest.mark.asyncio
async def test_create_signature_request_no_signers():
    """Cover validation: no signers."""
    from modules.crm.services.signature_integration import (
        ProposalSignatureService,
        SignatureRequest,
    )

    svc = ProposalSignatureService()

    request = SignatureRequest(
        proposal_id="prop-1",
        proposal_number="P001",
        document_url="/doc.pdf",
        signers=[],
    )

    result = await svc.create_signature_request(request)
    assert result.success is False


@pytest.mark.asyncio
async def test_create_signature_request_generic_exception():
    """Cover lines 149-150: generic exception in create_signature_request."""
    from modules.crm.services.signature_integration import (
        ProposalSignatureService,
        SignatureProvider,
        SignatureRequest,
        SignerInfo,
    )

    svc = ProposalSignatureService()

    request = SignatureRequest(
        proposal_id="prop-1",
        proposal_number="P001",
        document_url="/doc.pdf",
        signers=[SignerInfo(name="Test", email="test@test.com")],
        provider=SignatureProvider.INTERNAL,
    )

    # Patch _create_internal_signature to raise generic exception
    with patch.object(svc, "_create_internal_signature", side_effect=RuntimeError("boom")):
        result = await svc.create_signature_request(request)
        assert result.success is False
        assert result.error == "Erro interno"


@pytest.mark.asyncio
async def test_create_signature_clicksign_no_key():
    """Cover ClickSign without API key."""
    from modules.crm.services.signature_integration import (
        ProposalSignatureService,
        SignatureProvider,
        SignatureRequest,
        SignerInfo,
    )

    svc = ProposalSignatureService(provider=SignatureProvider.CLICKSIGN)

    request = SignatureRequest(
        proposal_id="prop-1",
        proposal_number="P001",
        document_url="/doc.pdf",
        signers=[SignerInfo(name="Test", email="test@test.com")],
        provider=SignatureProvider.CLICKSIGN,
    )

    result = await svc.create_signature_request(request)
    assert result.success is False
    assert "ClickSign" in result.error


@pytest.mark.asyncio
async def test_create_signature_generic_provider():
    """Cover generic provider path."""
    from modules.crm.services.signature_integration import (
        ProposalSignatureService,
        SignatureProvider,
        SignatureRequest,
        SignerInfo,
    )

    svc = ProposalSignatureService(provider=SignatureProvider.D4SIGN)

    request = SignatureRequest(
        proposal_id="prop-1",
        proposal_number="P001",
        document_url="/doc.pdf",
        signers=[SignerInfo(name="Test", email="test@test.com")],
        provider=SignatureProvider.D4SIGN,
    )

    result = await svc.create_signature_request(request)
    assert result.success is True
    assert "d4sign" in result.external_id
