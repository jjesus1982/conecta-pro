"""As 3 portas manuais do DP, batidas pelo HTTP com o payload EXATO que o formulário monta.

Mesmo raciocínio do `test_dp_http_aprovar.py`: o builder pode emitir uma tela perfeita
apontando para uma rota que responde 405 (método errado) ou 422 (campo faltando) — e nenhum
teste de função percebe, porque o defeito mora entre a tela e a rota. Aqui o payload é
construído A PARTIR do próprio builder, não escrito à mão: se alguém mudar um `key` da tela
sem mudar a rota, este teste cai.

Foi assim que apareceram os dois defeitos da porta de justificativa: a rota é PUT (a tela
mandava POST → 405) e o schema exige `reviewer_id` (a tela não mandava → 422).
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import timedelta

sys.path.insert(0, "/app")

import httpx  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

MARCA = f"BANCADA_PORTA_{uuid.uuid4().hex[:8]}"
BASE = "http://127.0.0.1:8080"
SERVICO = "01f4c6a0-743d-4702-8a1c-562ea57cfbe1"  # mcp-service@conectamais.pro


class _U:
    id = SERVICO
    email = "mcp-service@conectamais.pro"
    role = "admin"
    perfil = "all"
    modulos = ["dp"]


def _payload(tela: dict, valores: dict) -> dict:
    """Monta o body como o ModuleView monta: {...fixed, ...campos preenchidos}."""
    corpo = dict((tela.get("submit") or tela).get("fixed") or tela.get("fixed") or {})
    for f in tela.get("fields", []):
        if f["key"] in valores:
            corpo[f["key"]] = valores[f["key"]]
    return corpo


async def main() -> None:
    from core.auth.jwt import create_access_token
    from modules.operacional.controllers.redesign_builders import departamento_pessoal as dp

    H = {"Authorization": f"Bearer {create_access_token(SERVICO, expires_delta=timedelta(minutes=10))}"}
    eng = create_async_engine(os.environ["DATABASE_URL"])
    S = async_sessionmaker(eng, expire_on_commit=False)
    eid = jid = None
    try:
        async with S() as db:
            eid = (await db.execute(text(
                "INSERT INTO employees (id, nome, cpf, status, data_admissao, salario_base, "
                " created_at, updated_at) VALUES (gen_random_uuid(), :n, :c, 'ativo', "
                " DATE '2025-01-01', 1670, now(), now()) RETURNING id::text"),
                {"n": MARCA, "c": str(uuid.uuid4().int)[:11]})).scalar()
            jid = str(uuid.uuid4())
            await db.execute(text(
                # `id` é serial (integer), não uuid — quem identifica é justification_id
                "INSERT INTO gp_justifications (justification_id, employee_id, "
                " justification_type, reason, category, status, created_at, updated_at) "
                "VALUES (:j, :e, 'falta', :r, 'falta', 'pendente', now(), now())"),
                {"j": jid, "e": eid, "r": MARCA})
            await db.commit()

        async with httpx.AsyncClient(timeout=60) as cli:
            # ── porta 1: registrar licença ─────────────────────────────────
            t = dp._tela_registrar_licenca([])
            body = _payload(t, {"employee_id": eid, "leave_type": "licenca",
                                "start_date": "2099-05-01", "end_date": "2099-05-10",
                                "notes": f"{MARCA} motivo"})
            r = await cli.post(f"{BASE}{t['submit']['endpoint']}", json=body, headers=H)
            assert r.status_code in (200, 201), \
                f"porta licença: {r.status_code} {r.text[:300]}"
            async with S() as db:
                mot = (await db.execute(text(
                    "SELECT motivo FROM sst_afastamentos WHERE CAST(employee_id AS TEXT)=:e"),
                    {"e": eid})).scalar()
            assert mot and MARCA in mot, f"o motivo digitado se perdeu: {mot!r}"
            print(f"PORTA-1 licença → {r.status_code}, motivo preservado PASS")

            # ── porta 2: agendar/renovar ASO ───────────────────────────────
            t = dp._tela_renovar_aso([])
            body = _payload(t, {"employee_id": eid, "tipo": "periodico",
                                "data_agendamento": "2099-05-20", "clinica": MARCA})
            r = await cli.post(f"{BASE}{t['submit']['endpoint']}", json=body, headers=H)
            assert r.status_code in (200, 201), f"porta ASO: {r.status_code} {r.text[:300]}"
            print(f"PORTA-2 ASO → {r.status_code} PASS")

            # ── porta 3: revisar justificativa (a que estava quebrada) ─────
            async with S() as db:
                t = await dp._tela_revisar_justificativa(db, _U())
            linha = next((x for x in t["rows"]
                          if any(jid in str(a.get("endpoint", "")) for a in x["actions"])), None)
            assert linha, "a justificativa da bancada não apareceu na tela"
            acao = linha["actions"][0]

            assert acao["method"] == "PUT", f"método {acao['method']} → a rota é PUT (405)"
            assert acao["fixed"].get("reviewer_id"), "reviewer_id vazio → 422"
            assert not any(f.get("type") == "hidden" for f in acao["fields"]), \
                "campo hidden voltaria como input de texto editável"

            body = _payload(acao, {"notes": f"{MARCA} ok"})
            r = await cli.request(acao["method"], f"{BASE}{acao['endpoint']}",
                                  json=body, headers=H)
            assert r.status_code == 200, f"porta justificativa: {r.status_code} {r.text[:300]}"
            async with S() as db:
                st = (await db.execute(text(
                    "SELECT status FROM gp_justifications WHERE justification_id::text=:j"),
                    {"j": jid})).scalar()
            assert str(st).lower() not in ("pendente", "pending"), f"não decidiu: {st!r}"
            print(f"PORTA-3 justificativa → {r.status_code}, pendente → {st!r} PASS")

            print("\nAS 3 PORTAS MANUAIS ABREM PELO HTTP — método, campos e efeito no banco")
    finally:
        # limpeza pelo PREFIXO, não pela MARCA desta execução: uma rodada que morre no meio
        # deixa funcionário de bancada para trás, e o resíduo de ontem tem outra marca.
        async with S() as db:
            alvo = ("SELECT id FROM employees WHERE nome LIKE 'BANCADA_PORTA_%'")
            for tb in ("sst_afastamentos", "gp_justifications", "gp_asos"):
                await db.execute(text(
                    f"DELETE FROM {tb} WHERE CAST(employee_id AS TEXT) IN "
                    f"(SELECT CAST(id AS TEXT) FROM ({alvo}) q)"))
            await db.execute(text("DELETE FROM employees WHERE nome LIKE 'BANCADA_PORTA_%'"))
            await db.commit()
            rem = (await db.execute(text(
                "SELECT count(*) FROM employees WHERE nome LIKE 'BANCADA_PORTA_%'"))).scalar()
            assert rem == 0, f"resíduo: {rem}"
            print("LIMPEZA OK — 0 resíduo (varre o prefixo, não só esta rodada)")
        await eng.dispose()


asyncio.run(main())
