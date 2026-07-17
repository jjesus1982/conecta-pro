"""Regressão do release Ponto (2026-07-17) — convenção canônica de fuso.

A coluna gp_clock_punches.punch_timestamp é **UTC** (acervo do sync Tangerino +
presença ao vivo do Operacional). Os LEITORES convertem para America/Manaus
(UTC-4 fixo). Antes, o módulo Ponto lia cru → espelho +4h, batidas noturnas no
dia errado, banco de horas com débito fantasma.

Rodar dentro do container backend:
    python3 -m pytest tests/ponto_release/ -v
"""

import os
import uuid
from datetime import datetime, timedelta

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
        base_url=BASE, headers={"Authorization": f"Bearer {token}"}, timeout=60
    ) as c:
        yield c


def _db():
    from core.database.session import SyncSessionLocal

    return SyncSessionLocal()


def test_espelho_exibe_hora_local_manaus(client):
    """Batida 11:00 UTC do acervo tem que aparecer 07:00 (turno diurno real)."""
    from sqlalchemy import text

    s = _db()
    try:
        emp = s.execute(text(
            "SELECT employee_id::text FROM gp_clock_punches "
            "WHERE punch_type='entrada' AND extract(hour from punch_timestamp)=11 "
            "AND punch_timestamp >= '2026-07-01' LIMIT 1"
        )).scalar()
    finally:
        s.close()
    if not emp:
        pytest.skip("sem batidas 11h-UTC em julho")
    d = client.get(f"/api/v1/people-management/ponto/espelho/{emp}",
                   params={"month": 7, "year": 2026}).json()
    horas = {b["punch_timestamp"][11:13] for b in d.get("batidas", [])
             if b.get("punch_type") == "entrada"}
    assert "07" in horas or "06" in horas, (
        f"espelho não mostra entradas de manhã cedo (horas de entrada: {sorted(horas)}) — "
        "leitor voltou a ler punch_timestamp cru (UTC) como local"
    )
    assert "11" not in horas or "07" in horas, "entradas às 11h sem nenhuma às 07h — deslocado +4h"


def test_batida_propria_e2e_tempo_real(client):
    """Batida própria: grava UTC, exibe local, dashboard conta NA HORA. Limpa depois."""
    from sqlalchemy import text

    s = _db()
    try:
        emp = s.execute(text("SELECT id::text FROM employees WHERE status='ativo' LIMIT 1")).scalar()
        antes = client.get("/api/v1/people-management/ponto/dashboard").json()["presentes_hoje"]

        resp = client.post("/api/v1/people-management/ponto/batida",
                           json={"employee_id": emp, "punch_type": "entrada", "device_type": "web"})
        assert resp.status_code in (200, 201), resp.text
        pid = resp.json()["punch_id"]

        try:
            # armazenamento canônico UTC: linha no banco ≈ agora-UTC (não agora-local)
            row = s.execute(text(
                "SELECT punch_timestamp FROM gp_clock_punches WHERE punch_id=:p"), {"p": pid}
            ).scalar()
            delta_utc = abs((row - datetime.utcnow()).total_seconds())
            assert delta_utc < 120, (
                f"punch_timestamp {row} difere {delta_utc:.0f}s do UTC-agora — "
                "writer voltou a gravar hora local"
            )
            # exibição local: resposta da API ≈ agora-local (UTC-4)
            shown = datetime.fromisoformat(resp.json()["punch_timestamp"])
            delta_local = abs((shown - (datetime.utcnow() - timedelta(hours=4))).total_seconds())
            assert delta_local < 120, f"resposta exibe {shown}, não é hora local Manaus"
            # tempo real: dashboard conta o presente imediatamente
            depois = client.get("/api/v1/people-management/ponto/dashboard").json()["presentes_hoje"]
            assert depois >= max(antes, 1), (
                f"presentes_hoje não refletiu a batida na hora ({antes} → {depois})"
            )
        finally:
            s.execute(text("DELETE FROM gp_clock_punches WHERE punch_id=:p"), {"p": pid})
            s.commit()
    finally:
        s.close()


def test_inconsistencias_trazem_nome(client):
    d = client.get("/api/v1/people-management/ponto/relatorio/inconsistencias").json()
    items = d.get("inconsistencias") or d.get("items") or []
    if not items:
        pytest.skip("sem inconsistências no período")
    com_nome = [i for i in items if i.get("employee_nome")]
    assert len(com_nome) >= len(items) * 0.9, (
        "inconsistências sem employee_nome — a tela de Atrasos volta a mostrar '--'"
    )


def test_hr_employees_page_size_100(client):
    """A tela de justificativas usa page_size=100; o limite do endpoint é 100."""
    assert client.get("/api/v1/people-management/hr/employees",
                      params={"page_size": 100}).status_code == 200
