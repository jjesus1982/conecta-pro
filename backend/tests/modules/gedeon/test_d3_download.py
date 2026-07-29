"""Testes D3 — download endpoint ged_kit_documents (§40).

Usa TestClient (HTTP real) + SyncSessionLocal (DB state).

Cobrem:
  - Download de doc com file_path real retorna PDF binário (status=200, %PDF)
  - Download de placeholder (file_path NULL) retorna 404 limpo
  - Path traversal bloqueado (400)
  - BUG 7 regressão: sem auth retorna 401

Padrão de auth: override em get_current_user (retorna user_id real)
→ get_current_active_user faz lookup no DB e retorna o User real.
Igual ao padrão de test_kit_controller.py.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from core.database.session import SyncSessionLocal

DOWNLOAD_BASE = "/api/v1/people-management/ged/documents"

# Jordan Jesus — user real no DB (ad9abb59-55fb-444e-a04f-0e1f22541de3)
ADMIN_USER_ID = "ad9abb59-55fb-444e-a04f-0e1f22541de3"


@pytest.fixture(scope="module")
def app_production():
    from main_production import app

    return app


@pytest.fixture  # scope=function — necessário: BaseHTTPMiddleware tem bug de event loop com scope=module
def client(app_production):
    """TestClient sem auth — para testes de 401."""
    return TestClient(app_production)


@pytest.fixture  # scope=function — necessário: evita "Future attached to a different loop"
def client_auth(app_production):
    """TestClient com auth override via get_current_active_user (sync override)."""
    from core.auth.dependencies import get_current_active_user

    class _FakeUser:
        id = ADMIN_USER_ID
        email = "jjesus@conectamais.pro"
        is_active = True
        full_name = "Jordan Jesus"

    def _override():
        return _FakeUser()

    app_production.dependency_overrides[get_current_active_user] = _override
    yield TestClient(app_production)
    app_production.dependency_overrides.clear()


_TEST_REAL_DOC_ID = "ffff0001-0001-0000-0000-000000000001"
_REAL_PDF_PATH = (
    "/app/uploads/ged/historico/52958919-0a15-4e4f-806d-be3c75e5951b/2025-01/40756c97_Folha de Pagamento.pdf"
)


@pytest.fixture(scope="module")
def real_doc_id() -> str:
    """Kit_doc temporário apontando pro PDF histórico real em disco.

    Após D3.1 os paths Onvio foram zerados (PDFs nunca baixados).
    Usa PDF do histórico GED que existe independente do sync Onvio.
    """
    db = SyncSessionLocal()
    try:
        db.execute(
            text("""
                INSERT INTO ged_kit_documents
                  (id, kit_id, document_type, document_name, file_path,
                   source_module, is_signed, auto_generated, created_at, updated_at)
                VALUES (
                  :id,
                  (SELECT id FROM ged_document_kits LIMIT 1),
                  'outro', 'test_d3_real_pdf', :fp,
                  'test', false, false, NOW(), NOW()
                )
                ON CONFLICT (id) DO UPDATE SET file_path = :fp
            """),
            {"id": _TEST_REAL_DOC_ID, "fp": _REAL_PDF_PATH},
        )
        db.commit()
    finally:
        db.close()
    yield _TEST_REAL_DOC_ID
    db2 = SyncSessionLocal()
    db2.execute(text("DELETE FROM ged_kit_documents WHERE id = :id"), {"id": _TEST_REAL_DOC_ID})
    db2.commit()
    db2.close()


@pytest.fixture(scope="module")
def placeholder_doc_id() -> str:
    """ID de kit_doc com file_path NULL (placeholder)."""
    db = SyncSessionLocal()
    row = db.execute(text("SELECT id FROM ged_kit_documents WHERE file_path IS NULL LIMIT 1")).fetchone()
    db.close()
    assert row, "Nenhum kit_doc placeholder — DB inesperado"
    return str(row[0])


class TestD3DownloadHTTP:
    """Testes HTTP para o endpoint de download (§40)."""

    def test_download_doc_com_file_path_retorna_pdf(self, client_auth, real_doc_id):
        """Download de doc com file_path válido retorna PDF binário."""
        resp = client_auth.get(f"{DOWNLOAD_BASE}/{real_doc_id}/download")

        assert resp.status_code == 200, (
            f"Esperado 200 para doc com file_path real, obtido {resp.status_code}. Body: {resp.text[:200]}"
        )
        assert "application/pdf" in resp.headers.get("content-type", ""), (
            f"Esperado content-type application/pdf, obtido {resp.headers.get('content-type')}"
        )
        assert resp.content[:4] == b"%PDF", (
            f"Corpo não começa com %PDF — não é PDF válido. Início: {resp.content[:8]!r}"
        )

    def test_download_doc_placeholder_404(self, placeholder_doc_id):
        """Download de placeholder (file_path=NULL) retorna 404 limpo.

        Usa requests contra servidor vivo (porta 8080) para evitar bug do
        Starlette BaseHTTPMiddleware com asyncio no TestClient.
        """
        import requests as req

        # Token real via API de login
        login = req.post(
            "http://localhost:8080/api/v1/auth/login",
            data={"username": os.getenv("MCP_SERVICE_EMAIL", ""), "password": os.getenv("MCP_SERVICE_PASSWORD", "")},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )
        assert login.status_code == 200, f"Login falhou: {login.text}"
        token = login.json()["access_token"]

        resp = req.get(
            f"http://localhost:8080{DOWNLOAD_BASE}/{placeholder_doc_id}/download",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        assert resp.status_code == 404, f"Esperado 404 para placeholder, obtido {resp.status_code}"
        body = resp.json()
        assert "detail" in body, "Resposta de erro deve ter campo 'detail'"

    def test_download_path_traversal_bloqueado(self):
        """Tentativa de path traversal (../../etc/passwd) bloqueada com 400.

        Usa requests contra servidor vivo (porta 8080) para evitar bug do
        Starlette BaseHTTPMiddleware com asyncio no TestClient.
        """
        import requests as req

        traversal_id = "cccccccc-dddd-eeee-ffff-000000000001"

        db = SyncSessionLocal()
        try:
            db.execute(
                text("""
                    INSERT INTO ged_kit_documents
                      (id, kit_id, document_type, document_name, file_path,
                       source_module, is_signed, auto_generated, created_at, updated_at)
                    VALUES (
                      :id,
                      (SELECT id FROM ged_document_kits LIMIT 1),
                      'outro', 'test traversal', '../../etc/passwd',
                      'manual', false, false, NOW(), NOW()
                    )
                    ON CONFLICT (id) DO NOTHING
                """),
                {"id": traversal_id},
            )
            db.commit()
        finally:
            db.close()

        try:
            login = req.post(
                "http://localhost:8080/api/v1/auth/login",
                data={"username": os.getenv("MCP_SERVICE_EMAIL", ""), "password": os.getenv("MCP_SERVICE_PASSWORD", "")},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10,
            )
            assert login.status_code == 200, f"Login falhou: {login.text}"
            token = login.json()["access_token"]

            resp = req.get(
                f"http://localhost:8080{DOWNLOAD_BASE}/{traversal_id}/download",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            assert resp.status_code == 400, (
                f"Esperado 400 para path traversal, obtido {resp.status_code}. "
                "INV-3 deve bloquear paths fora de /app/uploads/"
            )
        finally:
            db2 = SyncSessionLocal()
            db2.execute(text("DELETE FROM ged_kit_documents WHERE id = :id"), {"id": traversal_id})
            db2.commit()
            db2.close()

    def test_download_sem_auth_401(self, client, real_doc_id):
        """BUG 7 regressão — download sem auth retorna 401."""
        resp = client.get(f"{DOWNLOAD_BASE}/{real_doc_id}/download")

        assert resp.status_code == 401, (
            f"BUG 7 REGRESSÃO — endpoint retornou {resp.status_code} sem auth. Download de kit_doc exige token válido."
        )


class TestD3DownloadDBState:
    """Testes de estado do banco — validam pré-condições de D3."""

    def test_folha_pagamento_03_2026_placeholder(self):
        """Pós-D3.1: 7 folha_pagamento de 03/2026 devem ser placeholder (file_path=NULL).

        D3.1 zerou os file_paths Onvio porque os PDFs reais nunca foram baixados
        (Cenário B — INV-5). Estado honesto: NULL até próximo sync.
        """
        db = SyncSessionLocal()
        result = db.execute(
            text("""
                SELECT COUNT(*) FROM ged_kit_documents kd
                JOIN ged_document_kits dk ON dk.id = kd.kit_id
                WHERE kd.document_type = 'folha_pagamento'
                  AND kd.file_path IS NULL
                  AND dk.reference_month = '2026-03-01'
            """)
        ).scalar()
        db.close()
        assert result == 7, (
            f"Esperado 7 folha_pagamento placeholder (NULL) para 03/2026, obtido {result}. "
            "D3.1 deveria ter zerado os 7 file_paths Onvio falsos."
        )

    def test_path_onvio_sem_formato_desconhecido(self):
        """Não deve haver paths com formato desconhecido em ged_kit_documents."""
        db = SyncSessionLocal()
        result = db.execute(
            text("""
                SELECT COUNT(*) FROM ged_kit_documents
                WHERE file_path IS NOT NULL
                  AND file_path NOT LIKE '/app/%'
                  AND file_path NOT LIKE 'documents/%'
                  AND file_path NOT LIKE 'http%'
            """)
        ).scalar()
        db.close()
        assert result == 0, f"Esperado 0 paths com formato desconhecido, obtido {result}."
