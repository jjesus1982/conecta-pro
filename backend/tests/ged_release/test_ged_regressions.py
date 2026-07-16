"""Regressão do release GED/GEDEON (2026-07-16).

Cada teste trava um bug encontrado na lapidação do módulo, contra a API real
(localhost:8080) e o banco de produção — leitura apenas.

Rodar dentro do container backend:
    python3 -m pytest tests/ged_release/ -v
"""

import os

import httpx
import pytest

BASE = os.environ.get("CONECTA_API", "http://localhost:8080")


@pytest.fixture(scope="module")
def token() -> str:
    from sqlalchemy import text

    from core.auth.jwt import create_access_token
    from core.database.session import SyncSessionLocal

    session = SyncSessionLocal()
    try:
        uid = session.execute(
            text("SELECT id FROM users WHERE email='jjesus@conectamais.pro' LIMIT 1")
        ).scalar()
        return create_access_token(subject=str(uid))
    finally:
        session.close()


@pytest.fixture(scope="module")
def client(token) -> httpx.Client:
    with httpx.Client(
        base_url=BASE, headers={"Authorization": f"Bearer {token}"}, timeout=120
    ) as c:
        yield c


# ── Rotas engolidas por /{param} (500/422 → 200 com o conversor :uuid) ────────


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/ged/document-shares/owner",
        "/api/v1/ged/document-shares/recipient",
        "/api/v1/ged/document-signatures/signer",
        "/api/v1/ged/document-tags/most-used",
        "/api/v1/ged/folders/root",
        "/api/v1/ged/documents/expired",
    ],
)
def test_literal_routes_not_swallowed_by_uuid_param(client, path):
    resp = client.get(path)
    assert resp.status_code == 200, (
        f"{path} → {resp.status_code}: rota literal voltou a ser engolida por "
        "/{param} (conversor :uuid removido?)"
    )


def test_uuid_param_route_still_works(client):
    from sqlalchemy import text

    from core.database.session import SyncSessionLocal

    s = SyncSessionLocal()
    try:
        fid = s.execute(text("SELECT id FROM ged_folders LIMIT 1")).scalar()
    finally:
        s.close()
    if not fid:
        pytest.skip("sem folder para testar")
    assert client.get(f"/api/v1/ged/folders/{fid}").status_code == 200


# ── Panorama do consultor (funcionários reais + kits do espelho do Drive) ─────


def test_panorama_uses_formal_allocation_link(client):
    resp = client.get(
        "/api/v1/gedeon/consultor/panorama", params={"competencia": "2026-06"}
    )
    assert resp.status_code == 200
    d = resp.json()
    com_func = [c for c in d["condominios"] if c["funcionarios_alocados"] > 0]
    assert len(com_func) >= 5, (
        "quase nenhum condomínio com funcionários alocados — o elo formal "
        "posts.client_id regrediu para o match por nome (que não casa por acento)"
    )


def test_panorama_kits_reflect_drive_mirror(client):
    resp = client.get(
        "/api/v1/gedeon/consultor/panorama", params={"competencia": "2026-06"}
    )
    d = resp.json()
    assert d["kits_montados"] >= 5, (
        f"kits_montados={d['kits_montados']} para 2026-06 — o panorama deixou de "
        "olhar ged_document_kits (espelho do Drive) e voltou a dizer 'NÃO montado' "
        "com o Drive cheio"
    )


# ── Completude sem pastas-lixo (nome de arquivo não é condomínio) ─────────────


def test_completude_has_no_filename_kits(client):
    resp = client.get("/api/v1/gedeon/kits/completude")
    assert resp.status_code == 200
    d = resp.json()
    lixo = [
        k["condominio"]
        for k in d["kits"]
        if k["condominio"].lower().endswith((".pdf", ".xlsx", ".jpg", ".png"))
    ]
    assert not lixo, f"pastas-lixo voltaram ao painel de completude: {lixo}"
    assert d["total_kits"] <= 15, (
        f"total_kits={d['total_kits']} — acima do plausível (~11-12 condomínios); "
        "workspace poluído de novo?"
    )


def test_garantir_pasta_kit_refuses_filenames():
    from modules.gedeon.services.kit_layout import garantir_pasta_kit, nome_parece_arquivo

    assert nome_parece_arquivo("Comprovante de Pagamento de Salário_Fulano.pdf")
    assert nome_parece_arquivo("qualquer coisa.XLSX")
    assert not nome_parece_arquivo("CONDOMINIO IDEAL FLORES DA CIDADE")
    assert garantir_pasta_kit("Contracheques.pdf", "06.2026") is None, (
        "guard do choke point removido — pastas-lixo com nome de arquivo voltarão "
        "a nascer na raiz do workspace"
    )


# ── RiskMonitor/GEDEON financeiro (enum ABERTA não existe) ────────────────────


def test_gedeon_financial_context_has_no_error():
    import asyncio

    from core.database.session import async_session_factory
    from modules.financial.agents.gedeon_financial_orchestrator import (
        GedeonFinancialOrchestrator,
    )

    async def run():
        async with async_session_factory() as s:
            return await GedeonFinancialOrchestrator(s)._get_context()

    ctx = asyncio.get_event_loop().run_until_complete(run())
    assert not ctx.get("erro"), (
        f"contexto do RiskMonitor com erro: {ctx.get('erro')} — "
        "(ReceivableStatus.ABERTA não existe; usar notin_ de status fechados)"
    )
