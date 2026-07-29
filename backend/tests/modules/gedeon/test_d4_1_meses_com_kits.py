"""Testes D4.1 — _meses_com_kits: auto-assemble não cria kits novos sozinho.

Princípio (D4.1): auto-assemble PREENCHE kits existentes, não cria novos.
Mês sem kits → SKIP com erro claro. Criar kits = decisão de negócio (§41.1).
"""

from __future__ import annotations

import os

import pytest
import requests
from sqlalchemy import text

from core.database.session import SyncSessionLocal


@pytest.fixture(scope="module")
def token():
    r = requests.post(  # noqa: S113
        "http://127.0.0.1:8080/api/v1/auth/login",
        data={"username": os.getenv("MCP_SERVICE_EMAIL", ""), "password": os.getenv("MCP_SERVICE_PASSWORD", "")},
        timeout=10,
    )
    assert r.status_code == 200, f"Login falhou: {r.text}"
    return r.json()["access_token"]


def test_meses_com_kits_retorna_apenas_existentes():
    """_meses_com_kits retorna SOMENTE meses que têm row em ged_document_kits."""
    db = SyncSessionLocal()
    try:
        rows = db.execute(text("SELECT DISTINCT reference_month FROM ged_document_kits ORDER BY 1 DESC")).fetchall()
        meses = [str(r[0]) for r in rows]

        # Confirmar que 02/2026 NÃO está (foi removido pelo D4.1 cleanup)
        assert "2026-02-01" not in meses, "02/2026 deve ter sido removido pelo D4.1 cleanup"
        # Confirmar que os meses existentes são os esperados
        assert "2026-04-01" in meses, "04/2026 deve existir"
        assert "2026-03-01" in meses, "03/2026 deve existir"
        # Confirmar que meses sem kits não aparecem
        assert "2026-01-01" not in meses, "01/2026 nunca teve kits"
    finally:
        db.close()


def test_executar_sem_mes_ref_nao_cria_kits_novos(token):
    """Sem mes_ref, executar() processa só meses com kits e NÃO cria novos."""
    import time

    # Registrar estado atual de meses com kits
    db = SyncSessionLocal()
    try:
        meses_antes = {
            str(r[0]) for r in db.execute(text("SELECT DISTINCT reference_month FROM ged_document_kits")).fetchall()
        }
    finally:
        db.close()

    # Disparar run sem mes_ref
    r = requests.post(  # noqa: S113
        "http://127.0.0.1:8080/api/v1/ged/coleta-automatica/run",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={},
        timeout=10,
    )
    assert r.status_code == 202, f"Expected 202, got {r.status_code}"

    # Aguardar execução
    time.sleep(15)

    # Verificar que nenhum mês NOVO foi criado
    db = SyncSessionLocal()
    try:
        meses_depois = {
            str(r[0]) for r in db.execute(text("SELECT DISTINCT reference_month FROM ged_document_kits")).fetchall()
        }
    finally:
        db.close()

    meses_novos = meses_depois - meses_antes
    assert not meses_novos, f"Meses novos criados indevidamente: {meses_novos}"


def test_executar_com_mes_ref_inexistente_retorna_erro(token):
    """Se mes_ref aponta para mês sem kits → status='error' + erro claro, sem kit criado."""
    import time

    # Disparar run com mês sem kits (01/2026)
    r = requests.post(  # noqa: S113
        "http://127.0.0.1:8080/api/v1/ged/coleta-automatica/run",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"mes_ref": "2026-01-01"},
        timeout=10,
    )
    assert r.status_code == 202, f"Expected 202 (aceita), got {r.status_code}"

    time.sleep(8)

    # Verificar que o log registrou erro
    r_hist = requests.get(  # noqa: S113
        "http://127.0.0.1:8080/api/v1/ged/coleta-automatica/history?limit=1",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    logs = r_hist.json()
    assert logs, "History deve ter pelo menos 1 log"
    last = logs[0]
    assert last["status"] == "error", f"Esperado status=error, got {last['status']}"
    assert last["kits_assembled"] == 0, "Não deve ter montado kits"
    erros = last.get("erros") or []
    assert any("não tem kits" in str(e).lower() for e in erros), f"Erro deve mencionar 'não tem kits': {erros}"

    # Confirmar que 01/2026 NÃO foi criado no banco
    db = SyncSessionLocal()
    try:
        count = db.execute(text("SELECT COUNT(*) FROM ged_document_kits WHERE reference_month='2026-01-01'")).scalar()
        assert count == 0, f"01/2026 não deveria ter kits, mas tem {count}"
    finally:
        db.close()
