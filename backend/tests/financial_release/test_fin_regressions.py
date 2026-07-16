"""Regressão dos itens FIN-01..FIN-10 (release Financeiro, 2026-07-16).

Cada teste trava UM bug do relatório do CIC contra a API REAL em execução
(localhost:8080) e/ou o banco de produção — leitura apenas, exceto FIN-03/05
que criam um registro descartável e o removem no próprio teste.

Rodar dentro do container backend:
    python3 -m pytest tests/financial_release/ -v
"""

import asyncio
import os
import uuid

import httpx
import pytest

BASE = os.environ.get("CONECTA_API", "http://localhost:8080")
MATRIZ = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

# Tolerância do saldo-âncora: o Inter é live e muda entre requisições
# (observado 68.136 → 67.757). Assert por consistência, nunca ao centavo.
SALDO_TOLERANCIA = 5_000.0


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


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
        base_url=BASE, headers={"Authorization": f"Bearer {token}"}, timeout=30
    ) as c:
        yield c


def _db_scalar(sql: str, **params):
    from sqlalchemy import text

    from core.database.session import SyncSessionLocal

    session = SyncSessionLocal()
    try:
        return session.execute(text(sql), params).scalar()
    finally:
        session.close()


def _db_exec(sql: str, **params) -> None:
    from sqlalchemy import text

    from core.database.session import SyncSessionLocal

    session = SyncSessionLocal()
    try:
        session.execute(text(sql), params)
        session.commit()
    finally:
        session.close()


# ── FIN-01: lista de fluxo de caixa não pode voltar vazia sem condominio ──────


def test_fin01_cashflow_entries_aggregates_without_condominio(client):
    resp = client.get("/api/v1/financial/cashflow/entries", params={"limit": 5})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list) and len(data) > 0, (
        "lista vazia sem condominio_id — regressão do FIN-01 (deve agregar tudo, "
        "como o summary)"
    )
    amount = data[0]["expected_amount"]
    assert isinstance(amount, (int, float)), f"expected_amount veio {type(amount).__name__}"


# ── FIN-02 / raiz Decimal: stats devolvem número, com valor real ──────────────


@pytest.mark.parametrize("endpoint", ["payables", "receivables"])
def test_fin02_stats_total_value_is_positive_number(client, endpoint):
    resp = client.get(
        f"/api/v1/financial/{endpoint}/stats", params={"condominio_id": MATRIZ}
    )
    assert resp.status_code == 200
    total = resp.json()["total_value"]
    assert isinstance(total, (int, float)), (
        f"{endpoint} total_value serializou como {type(total).__name__} — raiz Decimal regrediu"
    )
    assert total > 0, f"{endpoint} total_value=0 — cards do DRE voltariam a zerar"


# ── FIN-03: fornecedor digitado persiste e aparece na lista ───────────────────


def test_fin03_supplier_name_persists_and_lists(client):
    marker = f"PYTEST FIN03 {uuid.uuid4().hex[:8]}"
    resp = client.post(
        "/api/v1/financial/payables",
        json={
            "description": marker,
            "supplier_name": "Fornecedor Pytest FIN03",
            "gross_value": 12.34,
            "due_date": "2026-08-01",
            "condominio_id": MATRIZ,
        },
    )
    try:
        assert resp.status_code in (200, 201), resp.text
        created = resp.json()
        assert created["supplier_name"] == "Fornecedor Pytest FIN03"

        listed = client.get(
            "/api/v1/financial/payables",
            params={"condominio_id": MATRIZ, "search": marker, "limit": 5},
        ).json()
        items = listed.get("data") or listed.get("items") or []
        match = [i for i in items if i["description"] == marker]
        assert match and match[0]["supplier_name"] == "Fornecedor Pytest FIN03", (
            "coluna Fornecedor não refletiu o nome digitado — regressão FIN-03"
        )
    finally:
        _db_exec("DELETE FROM payable_accounts WHERE description = :d", d=marker)


# ── FIN-04: projeção 30d coerente (duas pontas, partindo do saldo real) ───────


def test_fin04_projection_starts_from_real_balance(client):
    resp = client.get(
        "/api/v1/financial/cashflow/projection", params={"condominio_id": MATRIZ}
    )
    assert resp.status_code == 200
    projs = resp.json()
    projs = projs if isinstance(projs, list) else projs.get("items", [])
    if not projs:  # sem vencimentos no período — nada a validar além do 200
        pytest.skip("sem vencimentos na janela de projeção")

    saldo_real = float(
        _db_scalar(
            "SELECT COALESCE(SUM(current_balance),0) FROM bank_accounts "
            "WHERE condominio_id = :c AND ativo",
            c=MATRIZ,
        )
    )
    primeiro = projs[0]
    esperado = saldo_real + float(primeiro["balance"])
    assert abs(float(primeiro["cumulative_balance"]) - esperado) <= SALDO_TOLERANCIA, (
        f"cumulative_balance {primeiro['cumulative_balance']} não parte do saldo real "
        f"{saldo_real:.2f} — regressão FIN-04 (projeção voltou a partir de zero?)"
    )
    # As duas pontas existem no payload (receivables não pode ter sumido).
    assert "receivables" in primeiro and "payables" in primeiro


# ── FIN-05: valor <= 0 tem que ser rejeitado pelo backend ─────────────────────


@pytest.mark.parametrize("valor", [0, -10])
def test_fin05_rejects_non_positive_value(client, valor):
    resp = client.post(
        "/api/v1/financial/payables",
        json={
            "description": "PYTEST FIN05 valor invalido",
            "gross_value": valor,
            "due_date": "2026-08-01",
            "condominio_id": MATRIZ,
        },
    )
    assert resp.status_code == 422, (
        f"gross_value={valor} foi aceito (HTTP {resp.status_code}) — validação gt=0 regrediu"
    )


# ── FIN-06: grafia canônica 'paga' (nenhum 'pago' em receivable_accounts) ─────


def test_fin06_no_pago_status_left():
    count = _db_scalar("SELECT count(*) FROM receivable_accounts WHERE status = 'pago'")
    assert count == 0, (
        f"{count} conta(s) a receber com status 'pago' — writer não-canônico voltou "
        "(canônico é ReceivableStatus.PAGA='paga')"
    )


# ── FIN-09: descrição da tool MCP sem valor chumbado ──────────────────────────


def test_fin09_mcp_description_has_no_hardcoded_balance():
    content = open("/app/financial_mcp_server.py", encoding="utf-8").read()
    assert "R$36k" not in content, "'R$36k' hardcoded voltou ao financial_mcp_server.py"


# ── FIN-10: nenhum registro de teste QA sobrando em produção ──────────────────


@pytest.mark.parametrize("table", ["payable_accounts", "receivable_accounts"])
def test_fin10_no_qa_test_records(table):
    count = _db_scalar(
        f"SELECT count(*) FROM {table} WHERE description ILIKE '%TESTE QA%'"
    )
    assert count == 0, f"{count} registro(s) 'TESTE QA' em {table}"
