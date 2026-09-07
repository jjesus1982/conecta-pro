#!/usr/bin/env python3
"""Onde está o gerente: chegada/saída no posto com GPS — o fluxo que o dono pediu em 07/09/2026.

Telas vigiadas: "gerente-checkin", "gerente-checkout", "gerente-hoje" (Operacional › Postos & Presença).
Afirma, com um colaborador de TESTE (marcado ORACULO) e um posto real com coordenada:
  1. chegada a ~17 m do posto registra a visita e diz a distância;
  2. segunda chegada sem saída é recusada;
  3. saída fecha a visita: status realizada, duração ≥ 0 pelo relógio do banco;
  4. chegada a ~2 km é aceita mas marcada FORA do raio;
  5. as duas regras proativas do gerente detectam sem erro.
Não manda WhatsApp (payload._silencio, admin). Apaga tudo o que criou.

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_oraculo_gerente_checkin.py
"""
import asyncio
import sys
import uuid
from types import SimpleNamespace

sys.path.insert(0, "/app")
import main_production  # noqa: E402,F401

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import text  # noqa: E402

from core.database import async_session_factory  # noqa: E402
from modules.operacional.controllers.redesign_builders.operacional import (  # noqa: E402
    rd_action_gerente_checkin,
    rd_action_gerente_checkout,
)

MARCA = "ORACULO GERENTE"


async def main() -> None:
    admin = SimpleNamespace(id=uuid.uuid4(), name="Oráculo", email="oraculo@conectapro.com.br", role="admin")
    async with async_session_factory() as db:
        post = (await db.execute(text(
            "SELECT id::text, name, latitude, longitude FROM posts WHERE is_active AND latitude IS NOT NULL ORDER BY name LIMIT 1"))).first()
        assert post, "nenhum posto com coordenada"
        emp = str(uuid.uuid4())
        await db.execute(text(
            "INSERT INTO employees (id, nome, cargo, status, tipo_contrato, created_at, updated_at) "
            "VALUES (CAST(:i AS uuid), :n, 'Supervisor Operacional ORACULO', 'pj_ativo', 'pj', now(), now())"), {"i": emp, "n": MARCA})
        await db.commit()
        try:
            lat, lng = float(post[2]) + 0.00015, float(post[3])  # ~17 m ao norte
            r1 = await rd_action_gerente_checkin(current_user=admin, db=db,
                                                 payload={"post_id": post[0], "lat": lat, "lng": lng, "gerente_id": emp, "_silencio": True})
            assert r1["ok"] and "m do posto" in r1["message"] and "FORA" not in r1["message"], r1
            print(f"OK chegada: {r1['message']}")
            try:
                await rd_action_gerente_checkin(current_user=admin, db=db,
                                                payload={"post_id": post[0], "gerente_id": emp, "_silencio": True})
                raise AssertionError("segunda chegada sem saída deveria ser recusada")
            except HTTPException as exc:
                assert exc.status_code == 400 and "check-out" in exc.detail, exc.detail
            print("OK segunda chegada recusada")
            r2 = await rd_action_gerente_checkout(current_user=admin, db=db,
                                                  payload={"lat": lat, "lng": lng, "gerente_id": emp, "_silencio": True})
            assert r2["ok"], r2
            v = (await db.execute(text(
                "SELECT status, duracao_real_minutos, checkin_at, checkout_at FROM visitas "
                "WHERE responsavel_id::text = :e ORDER BY created_at DESC LIMIT 1"), {"e": emp})).first()
            assert v[0] == "realizada" and v[1] is not None and v[1] >= 0 and v[2] and v[3], v
            print(f"OK saída: status {v[0]}, {v[1]} min")
            r3 = await rd_action_gerente_checkin(current_user=admin, db=db,
                                                 payload={"post_id": post[0], "lat": float(post[2]) + 0.018, "lng": float(post[3]),
                                                          "gerente_id": emp, "_silencio": True})
            assert r3["ok"] and "FORA" in r3["message"], r3
            print(f"OK fora do raio marcado: {r3['message']}")
            await rd_action_gerente_checkout(current_user=admin, db=db, payload={"gerente_id": emp, "_silencio": True})
            from modules.notifications.proativo.regras import REGISTRY
            for nome in ("gerente_visita_aberta", "gerente_sem_checkin"):
                achados = await REGISTRY[nome].detectar(db)
                assert isinstance(achados, list)
            print("OK regras proativas do gerente detectam sem erro")
        finally:
            await db.execute(text("DELETE FROM visitas WHERE responsavel_id::text = :e"), {"e": emp})
            await db.execute(text("DELETE FROM employees WHERE id::text = :e"), {"e": emp})
            await db.commit()
            sobras = (await db.execute(text("SELECT count(*) FROM employees WHERE nome = :n"), {"n": MARCA})).scalar()
            print(f"LIMPEZA OK — {sobras} remanescente(s)"); assert sobras == 0
    print("TEST oraculo_gerente_checkin PASS")


if __name__ == "__main__":
    asyncio.run(main())
