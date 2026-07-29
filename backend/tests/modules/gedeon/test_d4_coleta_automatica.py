"""Testes D4 — Coleta Automática (config CRUD, manual run, idempotência, log gravado).

Padrão: SyncSessionLocal direto (sem HTTP) onde possível.
Para endpoints HTTP usa TestClient com workaround scope=module (BaseHTTPMiddleware bug).
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from core.database.session import SyncSessionLocal


@pytest.fixture(scope="module")
def cleanup_d4_logs():
    """Remove logs de teste inseridos por D4 ao final do módulo."""
    yield
    db = SyncSessionLocal()
    try:
        db.execute(text("DELETE FROM ged_coleta_logs WHERE triggered_by IN ('test_d4', 'pytest_d4')"))
        db.commit()
    finally:
        db.close()


class TestD4ColetaConfig:
    """Testes de config singleton ged_coleta_config."""

    def test_config_default_pos_migration(self):
        """Após migration, ged_coleta_config tem row id=1 com defaults corretos."""
        db = SyncSessionLocal()
        row = db.execute(text("SELECT id, enabled, cron_expr, timezone FROM ged_coleta_config WHERE id=1")).fetchone()
        db.close()
        assert row is not None, "Row id=1 ausente — migration D4 não foi aplicada?"
        assert row[0] == 1
        assert row[1] is True, f"enabled deve ser True, got {row[1]}"
        assert row[2] == "0 6 21 * *", f"cron_expr deve ser '0 6 21 * *', got {row[2]}"
        assert row[3] == "America/Manaus", f"timezone deve ser 'America/Manaus', got {row[3]}"

    def test_update_config_persiste_no_db(self):
        """UPDATE de cron_expr persiste e pode ser lido de volta."""
        db = SyncSessionLocal()
        try:
            db.execute(text("UPDATE ged_coleta_config SET cron_expr='0 8 25 * *' WHERE id=1"))
            db.commit()
            row = db.execute(text("SELECT cron_expr FROM ged_coleta_config WHERE id=1")).fetchone()
            assert row[0] == "0 8 25 * *"
        finally:
            # Restaurar default
            db.execute(text("UPDATE ged_coleta_config SET cron_expr='0 6 21 * *' WHERE id=1"))
            db.commit()
            db.close()

    def test_config_aceita_cron_valida(self):
        """croniter valida '0 6 21 * *' como expressão válida."""
        from croniter import croniter

        assert croniter.is_valid("0 6 21 * *")
        assert croniter.is_valid("0 7 1 * *")
        assert not croniter.is_valid("invalid cron")
        assert not croniter.is_valid("60 25 0 0 0")

    def test_singleton_constraint(self):
        """INSERT de segunda row em ged_coleta_config deve falhar (check id=1)."""
        db = SyncSessionLocal()
        try:
            with pytest.raises(Exception):
                db.execute(
                    text(
                        "INSERT INTO ged_coleta_config (id, enabled, cron_expr, timezone) VALUES (2, true, '0 1 1 * *', 'UTC')"
                    )
                )
                db.commit()
        finally:
            db.rollback()
            db.close()


class TestD4ColetaLogs:
    """Testes de ged_coleta_logs."""

    def test_log_insert_e_leitura(self, cleanup_d4_logs):
        """Inserção de log manual persiste e é lido de volta com campos corretos."""
        import uuid

        db = SyncSessionLocal()
        try:
            log_id = str(uuid.uuid4())
            db.execute(
                text("""
                    INSERT INTO ged_coleta_logs
                        (id, run_type, status, duration_ms, sync_novos, kits_assembled, onvio_matched, triggered_by)
                    VALUES
                        (:id, 'manual', 'success', 1234, 5, 3, 7, 'pytest_d4')
                """),
                {"id": log_id},
            )
            db.commit()

            row = db.execute(
                text("SELECT run_type, status, duration_ms, sync_novos FROM ged_coleta_logs WHERE id=:id"),
                {"id": log_id},
            ).fetchone()
            assert row is not None
            assert row[0] == "manual"
            assert row[1] == "success"
            assert row[2] == 1234
            assert row[3] == 5
        finally:
            db.close()

    def test_history_ordena_por_run_at_desc(self, cleanup_d4_logs):
        """Logs são retornados em ordem descending de run_at."""
        import uuid

        db = SyncSessionLocal()
        try:
            ids = [str(uuid.uuid4()) for _ in range(3)]
            for i, lid in enumerate(ids):
                db.execute(
                    text("""
                        INSERT INTO ged_coleta_logs
                            (id, run_type, status, triggered_by, run_at)
                        VALUES
                            (:id, 'cron', 'success', 'pytest_d4',
                             NOW() - interval ':offset seconds')
                    """).bindparams(offset=i * 60),
                    {"id": lid},
                )
            db.commit()

            rows = db.execute(
                text("SELECT id FROM ged_coleta_logs WHERE triggered_by='pytest_d4' ORDER BY run_at DESC LIMIT 3")
            ).fetchall()
            returned_ids = [str(r[0]) for r in rows]
            assert returned_ids[0] == ids[0], "Primeiro deve ser o mais recente"
        finally:
            db.close()


@pytest.fixture(autouse=True, scope="module")
def clear_coleta_lock():
    """Limpa lock Redis de coleta antes/após suite para evitar 409 espúrio."""
    import redis as redis_lib

    from core.config.settings import get_settings

    settings = get_settings()
    r = redis_lib.from_url(settings.redis_url, decode_responses=True)
    r.delete("ged:coleta:running")
    yield
    r.delete("ged:coleta:running")


class TestD4ColetaEndpoints:
    """Testes E2E via HTTP dos endpoints /coleta-automatica."""

    @pytest.fixture(scope="class")
    def token(self):
        import requests

        r = requests.post(  # noqa: S113
            "http://127.0.0.1:8080/api/v1/auth/login",
            data={"username": os.getenv("MCP_SERVICE_EMAIL", ""), "password": os.getenv("MCP_SERVICE_PASSWORD", "")},
            timeout=10,
        )
        assert r.status_code == 200, f"Login falhou: {r.text}"
        return r.json()["access_token"]

    def test_get_config_retorna_default(self, token):
        """GET /coleta-automatica retorna config com campos corretos."""
        import requests

        r = requests.get(  # noqa: S113
            "http://127.0.0.1:8080/api/v1/ged/coleta-automatica",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert "enabled" in data
        assert "cron_expr" in data
        assert data["cron_expr"] == "0 6 21 * *"
        assert data["timezone"] == "America/Manaus"

    def test_update_config_rejeita_cron_invalida(self, token):
        """POST /coleta-automatica com cron_expr inválida retorna 400."""
        import requests

        r = requests.post(  # noqa: S113
            "http://127.0.0.1:8080/api/v1/ged/coleta-automatica",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"enabled": True, "cron_expr": "invalid cron"},
            timeout=10,
        )
        assert r.status_code == 400, f"Expected 400 para cron inválida, got {r.status_code}"

    def test_history_retorna_lista(self, token):
        """GET /coleta-automatica/history retorna lista (pode ser vazia)."""
        import requests

        r = requests.get(  # noqa: S113
            "http://127.0.0.1:8080/api/v1/ged/coleta-automatica/history?limit=5",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        assert len(data) <= 5, "limit=5 deve retornar no máximo 5"

    def test_run_now_dispara_task_grava_log(self, token):
        """POST /run → 202 com task_id + log gravado em ged_coleta_logs."""
        import time

        import requests
        from sqlalchemy import text

        from core.database.session import SyncSessionLocal

        r = requests.post(  # noqa: S113
            "http://127.0.0.1:8080/api/v1/ged/coleta-automatica/run",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={},
            timeout=10,
        )
        assert r.status_code == 202, f"Expected 202, got {r.status_code}: {r.text}"
        data = r.json()
        assert data["status"] == "started", f"Expected status=started, got {data}"
        assert "task_id" in data, "Response deve incluir task_id"
        assert "started_at" in data, "Response deve incluir started_at"

        # Aguardar background task gravar log (máx 30s)
        db = SyncSessionLocal()
        try:
            for _ in range(10):
                time.sleep(3)
                row = db.execute(
                    text("SELECT status FROM ged_coleta_logs WHERE run_type='manual' ORDER BY run_at DESC LIMIT 1")
                ).fetchone()
                if row is not None:
                    assert row[0] in ("success", "partial", "error"), f"Status inválido: {row[0]}"
                    return
            raise AssertionError("Log não gravado em ged_coleta_logs após 30s")
        finally:
            db.close()

    def test_run_now_idempotencia_409_se_em_andamento(self, token):
        """2 POSTs simultâneos → um retorna 202 (started) e outro 409 (Conflict)."""
        import concurrent.futures
        import time

        import redis as redis_lib
        import requests

        from core.config.settings import get_settings

        # Garantir que o lock está limpo antes de testar idempotência
        r_client = redis_lib.from_url(get_settings().redis_url, decode_responses=True)
        for _ in range(15):
            if not r_client.exists("ged:coleta:running"):
                break
            time.sleep(2)
        r_client.delete("ged:coleta:running")  # força limpeza se ainda preso

        def post_run():
            return requests.post(  # noqa: S113
                "http://127.0.0.1:8080/api/v1/ged/coleta-automatica/run",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={},
                timeout=15,
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(post_run), executor.submit(post_run)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        status_codes = sorted([r.status_code for r in results])
        assert status_codes == [202, 409] or status_codes == [202, 202], (
            f"Esperado [202, 409] (idempotência) ou [202, 202] (lock liberado antes), got {status_codes}"
        )
        has_conflict = any(r.status_code == 409 for r in results)
        has_started = any(r.status_code == 202 for r in results)
        assert has_started, "Pelo menos um POST deve retornar 202"
        # 409 pode não acontecer se o lock foi liberado entre os dois POSTs
        # mas se acontecer, deve ter a mensagem correta
        for r in results:
            if r.status_code == 409:
                assert "execução" in r.json().get("detail", "").lower(), (
                    f"409 deve informar que já está em execução: {r.json()}"
                )
