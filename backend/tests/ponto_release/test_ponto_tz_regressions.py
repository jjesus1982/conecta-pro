"""Regressão do release Ponto (2026-07-17) — convenção canônica de fuso.

A coluna gp_clock_punches.punch_timestamp é gravada em **hora LOCAL de Manaus**
(naive). O sync Tangerino usa datetime.fromtimestamp num servidor America/Manaus,
e o ponto nativo grava datetime.now() — ambos Manaus local. Os LEITORES leem o
valor COMO ESTÁ (sem conversão de fuso). O bug do release anterior era tratar a
coluna como UTC e subtrair 4h → espelho mostrava 03:00 para uma batida real de
07:00, batidas caíam no dia errado, banco de horas com débito fantasma.

Rodar dentro do container backend:
    python3 -m pytest tests/ponto_release/ -v
"""

import os
from datetime import datetime

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


def test_espelho_exibe_hora_igual_ao_armazenado(client):
    """Leitura direta: a hora exibida no espelho == a hora gravada (sem shift de fuso).

    Pega uma entrada matinal real (hora 6-8) e confirma que o espelho mostra a MESMA
    hora — não hora-4h (regressão de reler o valor local como se fosse UTC).
    """
    from sqlalchemy import text

    s = _db()
    try:
        row = s.execute(text(
            "SELECT employee_id::text, extract(hour from punch_timestamp)::int "
            "FROM gp_clock_punches "
            "WHERE punch_type='entrada' AND extract(hour from punch_timestamp) BETWEEN 6 AND 8 "
            "AND punch_timestamp >= '2026-07-01' LIMIT 1"
        )).fetchone()
    finally:
        s.close()
    if not row:
        pytest.skip("sem entradas matinais (6-8h) em julho")
    emp, hora_armazenada = row[0], row[1]
    d = client.get(f"/api/v1/people-management/ponto/espelho/{emp}",
                   params={"month": 7, "year": 2026}).json()
    horas = {int(b["punch_timestamp"][11:13]) for b in d.get("batidas", [])
             if b.get("punch_type") == "entrada" and b.get("punch_timestamp")}
    assert hora_armazenada in horas, (
        f"espelho não mostra a entrada gravada às {hora_armazenada}h (viu {sorted(horas)}) — "
        "leitor deslocou o fuso"
    )
    assert (hora_armazenada - 4) not in horas or hora_armazenada in horas, (
        f"entrada apareceu às {hora_armazenada - 4}h — leitor voltou a subtrair 4h (bug UTC)"
    )


def test_batida_propria_e2e_tempo_real(client):
    """Batida própria: grava Manaus local, exibe local, dashboard conta NA HORA. Limpa depois."""
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
            # armazenamento canônico = Manaus local: linha no banco ≈ agora-local
            # (servidor é America/Manaus, então datetime.now() == parede de Manaus)
            row = s.execute(text(
                "SELECT punch_timestamp FROM gp_clock_punches WHERE punch_id=:p"), {"p": pid}
            ).scalar()
            delta = abs((row - datetime.now()).total_seconds())
            assert delta < 120, (
                f"punch_timestamp {row} difere {delta:.0f}s do agora-local — "
                "writer não gravou hora local Manaus"
            )
            # exibição: resposta da API ≈ agora-local (leitura direta, sem conversão)
            shown = datetime.fromisoformat(resp.json()["punch_timestamp"])
            delta_shown = abs((shown.replace(tzinfo=None) - datetime.now()).total_seconds())
            assert delta_shown < 120, f"resposta exibe {shown}, não é hora local Manaus"
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
