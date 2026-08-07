"""Elo lead -> cliente (Task 1).

A coluna leads.client_id JA existia no banco mas NAO estava mapeada no model:
setattr virava atributo Python solto, o PUT devolvia 200 e nada persistia.
Estes testes travam as duas pontas (model mapeia, schema aceita).
"""


def test_model_lead_mapeia_client_id():
    from modules.crm.models.lead import Lead
    cols = [c.name for c in Lead.__table__.columns]
    assert "client_id" in cols, "Lead.client_id nao mapeado -> nada persiste"


def test_leadupdate_aceita_client_id():
    from modules.crm.schemas.lead import LeadUpdate
    u = LeadUpdate(client_id="11111111-1111-1111-1111-111111111111")
    assert str(u.client_id).startswith("1111")


def test_update_inclui_client_id_no_dump():
    """O repositorio copia via model_dump(exclude_unset=True) — se o campo nao
    entrar no dump, o setattr nunca acontece."""
    from modules.crm.schemas.lead import LeadUpdate
    u = LeadUpdate(client_id="22222222-2222-2222-2222-222222222222")
    assert "client_id" in u.model_dump(exclude_unset=True)
