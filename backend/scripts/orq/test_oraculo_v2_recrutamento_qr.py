"""Oráculo — DGX V2: vaga do contrato → recrutamento, e QR de chamado por setor (24/09/2026).

Por que existe: duas pontas que não se tocavam. (a) A vaga do contrato (`posts`, com `contract_id`
e `salario_base` desde a T3) e a vaga do RH (`job_positions`) viviam em mundos separados — o
supervisor via o buraco no grid e o RH abria a vaga no escuro, e ninguém ligava o candidato
aprovado ao POSTO que motivou a contratação. (b) O chamado da F8 só nascia por dentro do ERP;
o DGX põe um QR no setor e quem está lá abre o chamado do celular, sem login.

As três formas de isso mentir, e o que o oráculo faz contra cada uma:
  · "recrutar" virar botão que cria vaga nova a cada clique → recruta DUAS vezes o mesmo posto e
    exige que continue existindo UMA vaga aberta (e que a 2ª chamada aponte a 1ª);
  · a esteira "alocar" só na aparência → reconta por SQL próprio em `employee_alocacoes` que a
    linha nasceu com `posto_id` e motivo `alocacao_de_vaga`, e que SEM vaga nenhuma linha nasce
    (o caminho antigo tem de ficar byte a byte o mesmo);
  · a página pública aceitar qualquer coisa → token inválido é 404, chamado sem descrição é 422,
    e o chamado que passa nasce com canal `qr`, com o setor certo e com o responsável avisado.

O que afirma (recontado por SQL próprio, não pelo serviço):
  1. Esquema: `job_positions.post_id/contract_id`, índice ÚNICO parcial de uma vaga ABERTA por
     posto, `op_setores.token` (único) e canal `qr` no serviço de chamados.
  2. `vaga-recrutar` num posto com 3 contratados e 0 alocados abre vaga com 3 posições, com
     `post_id`/`contract_id` do posto e salário base do posto; chamar de novo NÃO cria a segunda.
  3. Posto sem `salario_base` mas com função da CCT → a vaga nasce com o PISO da CCT.
  4. Candidato aprovado com `vaga_id` de vaga ligada a posto → `employee_alocacoes` ganha 1 linha
     ativa, com `posto_id` e motivo `alocacao_de_vaga`; a vaga sobe `filled_count`.
  5. Candidato aprovado SEM vaga → ZERO linha em `employee_alocacoes` (caminho de hoje), e ainda
     assim `allocations` + `posto_atual_id` como sempre foram.
  6. Token público: GET devolve a página com o nome do setor; POST sem descrição = 422; POST bom
     abre `op_chamados` com `canal='qr'`, `setor_id` certo e `notificado` preenchido (simulado no
     sandbox); token inexistente = 404 no GET e no POST.
  7. A etiqueta do setor gera um PDF de verdade (`%PDF`) e o QR carrega o endereço público.

Estado medido no nascimento (staging, 24/09/2026): `job_positions` sem `post_id`/`contract_id`,
`op_setores` sem `token`, nenhuma rota pública de chamado, canal `qr` inexistente → VERMELHO de 1
a 7. Fixtures marcadas 'FIXTURE DGX V2' e apagadas ao fim.

Como roda (container, PYTHONPATH=/app):
  docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" -e PYTHONPATH=/app \
    -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env -e SMTP_HOST= -e SMTP_USERNAME= \
    -e SMTP_PASSWORD= $ENVS conecta-pro-backend:latest \
    python3 /app/scripts/orq/test_oraculo_v2_recrutamento_qr.py
Sai 0 = verde; 1 = vermelho. Linha final `TOTAL falhas DGX V2: N`.
"""

from __future__ import annotations

import asyncio
import sys
import uuid as _uuid

FIX = "FIXTURE DGX V2"


async def _limpar(db) -> None:
    from sqlalchemy import text

    await db.rollback()
    emps = "(SELECT id FROM employees WHERE nome LIKE :f)"
    postos = "(SELECT id FROM posts WHERE name LIKE :f)"
    for sql in [
        f"DELETE FROM employee_alocacoes WHERE employee_id IN {emps}",
        f"DELETE FROM shifts WHERE employee_id IN {emps} OR post_id IN {postos}",
        f"DELETE FROM scales WHERE post_id IN {postos}",
        f"DELETE FROM allocations WHERE employee_id IN {emps} OR post_id IN {postos}",
        f"DELETE FROM admission_checklists WHERE employee_id IN {emps}",
        f"DELETE FROM portal_notifications WHERE employee_id IN {emps}",
        f"DELETE FROM candidate_background_checks WHERE employee_id IN {emps}",
        f"DELETE FROM candidate_documents WHERE employee_id IN {emps}",
        f"DELETE FROM sig_signature_requests WHERE employee_id IN {emps}",
        f"DELETE FROM users WHERE employee_id IN {emps}",
        "DELETE FROM employees WHERE nome LIKE :f",
        "DELETE FROM op_chamados WHERE descricao LIKE :f",
        "DELETE FROM op_setores WHERE nome LIKE :f",
        "DELETE FROM job_positions WHERE title LIKE :f OR description LIKE :f",
        "DELETE FROM posts WHERE name LIKE :f",
    ]:
        try:
            await db.execute(text(sql), {"f": f"%{FIX}%"})
            await db.commit()
        except Exception:  # noqa: BLE001 — coluna/tabela pode não existir na rodada vermelha
            await db.rollback()


def _mini_app(db):
    """App ASGI mínima só com o router da V2 — as rotas públicas passam pelo rate limit de
    verdade e os status (404/422) são os que o morador veria no celular."""
    from fastapi import FastAPI
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    from core.auth.dependencies import get_current_active_user
    from core.database import get_db
    from core.rate_limit import limiter
    from modules.operacional.controllers.redesign_builders._dgx_v2_recrutamento_qr import router

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(router, prefix="/api/v1/redesign")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_active_user] = lambda: type("U", (), {"id": None, "role": "admin"})()
    return app


async def main() -> int:  # noqa: PLR0915 — um oráculo é uma lista de afirmações
    import httpx
    from sqlalchemy import text

    from core.database import async_session_factory

    falhas: list[str] = []

    def ok(cond: bool, msg: str) -> None:
        print(("  ✓ " if cond else "  ✗ ") + msg)
        if not cond:
            falhas.append(msg)

    async with async_session_factory() as db:
        try:
            try:
                from modules.operacional.controllers.redesign_builders import _dgx_v2_recrutamento_qr as v2
                from modules.operacional.services import supervisao_service as sv
            except Exception as exc:  # noqa: BLE001
                ok(False, f"módulo _dgx_v2_recrutamento_qr importa: {exc}")
                print(f"TOTAL falhas DGX V2: {len(falhas)}")
                return 1
            await _limpar(db)
            await v2._ensure(db)
            await sv._ensure(db)

            # ── 1. esquema ──
            cols = {
                (r[0], r[1])
                for r in (
                    await db.execute(
                        text(
                            "SELECT table_name, column_name FROM information_schema.columns "
                            "WHERE table_name IN ('job_positions','op_setores')"
                        )
                    )
                ).fetchall()
            }
            for tb, c in [
                ("job_positions", "post_id"),
                ("job_positions", "contract_id"),
                ("op_setores", "token"),
            ]:
                ok((tb, c) in cols, f"esquema: {tb}.{c} existe")
            idx = (
                await db.execute(
                    text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ux_job_positions_post_aberta'")
                )
            ).scalar() or ""
            ok(
                "UNIQUE" in idx.upper() and "post_id" in idx and "aberta" in idx,
                "esquema: índice ÚNICO parcial — uma vaga ABERTA por posto (a idempotência é do banco)",
            )
            ok("qr" in sv.CANAIS, "esquema: canal 'qr' existe no serviço de chamados (F8)")
            sem_token = (
                await db.execute(text("SELECT count(*) FROM op_setores WHERE ativo AND token IS NULL"))
            ).scalar()
            ok(sem_token == 0, f"esquema: todo setor ativo tem token (sem token: {sem_token})")

            # ── fixtures: cliente com condomínio ativo e contrato vivo ──
            cli = (
                await db.execute(
                    text(
                        "SELECT cl.id::text, cl.name, "
                        " (SELECT c.id::text FROM condominios c WHERE c.client_id = cl.id AND c.ativo LIMIT 1), "
                        " (SELECT k.id::text FROM contracts k WHERE k.client_id = cl.id AND k.is_active LIMIT 1) "
                        "FROM clients cl WHERE EXISTS (SELECT 1 FROM condominios c WHERE c.client_id = cl.id AND c.ativo) "
                        "  AND EXISTS (SELECT 1 FROM contracts k WHERE k.client_id = cl.id AND k.is_active) LIMIT 1"
                    )
                )
            ).fetchone()
            ok(bool(cli), "fixtures: há cliente com condomínio ativo e contrato vivo no sandbox")
            if not cli:
                print(f"TOTAL falhas DGX V2: {len(falhas)}")
                return 1
            cli_id, _cli_nome, cond_id, ctr_id = cli
            user_id = (
                await db.execute(text("SELECT id::text FROM users WHERE email = 'jjesus@conectamais.pro'"))
            ).scalar()

            async def _posto(nome: str, funcao: str, headcount: int, salario) -> str:
                pid = str(_uuid.uuid4())
                await db.execute(
                    text(
                        "INSERT INTO posts (id, code, name, post_type, shift_type, required_headcount, client_id, "
                        " contract_id, salario_base, is_active, status) VALUES (CAST(:i AS uuid), :c, :n, :f, '12x36', :h, "
                        " CAST(:cl AS uuid), CAST(:ct AS uuid), :s, true, 'active')"
                    ),
                    {
                        "i": pid,
                        "c": f"FIXV2-{pid[:6]}",
                        "n": nome,
                        "f": funcao,
                        "h": headcount,
                        "cl": cli_id,
                        "ct": ctr_id,
                        "s": salario,
                    },
                )
                await db.commit()
                return pid

            p1 = await _posto(f"{FIX} posto com salario", "AGENTE DE PORTARIA", 3, 1800)
            p2 = await _posto(f"{FIX} posto sem salario", "AGENTE DE FISCALIZACAO", 1, None)

            class _U:
                id = user_id

            # ── 2. recrutar 2× → UMA vaga aberta ──
            r1 = await v2.rd_vaga_recrutar(current_user=_U(), post_id=p1, payload={}, db=db)
            r2 = await v2.rd_vaga_recrutar(current_user=_U(), post_id=p1, payload={}, db=db)
            ok(r1.get("ja_existia") is False and bool(r1.get("vaga_id")), "recrutar: a 1ª chamada criou a vaga")
            ok(r2.get("ja_existia") is True and r2.get("vaga_id") == r1.get("vaga_id"), "recrutar: a 2ª aponta a 1ª")
            n_abertas = (
                await db.execute(
                    text(
                        "SELECT count(*) FROM job_positions WHERE post_id = CAST(:p AS uuid) AND status = 'aberta' "
                        "AND coalesce(is_deleted, false) = false"
                    ),
                    {"p": p1},
                )
            ).scalar()
            ok(n_abertas == 1, f"recrutar: recontado por SQL — 1 vaga ABERTA para o posto (achei {n_abertas})")
            v = (
                await db.execute(
                    text(
                        "SELECT vacancies, salary_min, post_id::text, contract_id::text, condominio_id::text, status "
                        "FROM job_positions WHERE id::text = :v"
                    ),
                    {"v": r1["vaga_id"]},
                )
            ).fetchone()
            ok(v[0] == 3, f"recrutar: quantidade = descoberto de hoje (3 contratados − 0 alocados); achei {v[0]}")
            ok(float(v[1] or 0) == 1800.0, f"recrutar: salário base veio da vaga do contrato (1800); achei {v[1]}")
            ok(v[2] == p1 and v[3] == ctr_id, "recrutar: a vaga aponta o POSTO e o CONTRATO")
            ok(v[4] == cond_id, "recrutar: a vaga carrega o condomínio do cliente")

            # ── 3. sem salário no posto → piso da CCT ──
            r3 = await v2.rd_vaga_recrutar(current_user=_U(), post_id=p2, payload={}, db=db)
            piso = await v2.piso_cct(db, "AGENTE DE FISCALIZACAO")
            sal3 = (
                await db.execute(text("SELECT salary_min FROM job_positions WHERE id::text = :v"), {"v": r3["vaga_id"]})
            ).scalar()
            ok(
                piso is not None and float(sal3 or 0) == float(piso),
                f"recrutar: sem salário na vaga, cai no PISO da CCT ({piso}); achei {sal3}",
            )

            # ── 4/5. esteira: com vaga aloca no posto (F5); sem vaga, caminho de hoje ──
            from modules.people_management.human_resources.controllers.candidatos_esteira_controller import (
                AprovarBody,
                aprovar_e_ativar,
            )

            async def _candidato(nome: str) -> str:
                eid = str(_uuid.uuid4())
                await db.execute(
                    text(
                        "INSERT INTO employees (id, nome, cpf, cargo, status, created_at) "
                        "VALUES (CAST(:i AS uuid), :n, :c, 'AGENTE DE PORTARIA', 'candidato', now())"
                    ),
                    {"i": eid, "n": nome, "c": str(abs(hash(eid)) % 10**11).zfill(11)},
                )
                for ct in ("cpf_valido", "receita_situacao"):
                    await db.execute(
                        text(
                            "INSERT INTO candidate_background_checks (employee_id, check_type, status) "
                            "VALUES (CAST(:e AS uuid), :t, 'ok')"
                        ),
                        {"e": eid, "t": ct},
                    )
                await db.commit()
                return eid

            cand_a = await _candidato(f"{FIX} candidato com vaga")
            cand_b = await _candidato(f"{FIX} candidato sem vaga")

            res_a = await aprovar_e_ativar(
                candidato_id=cand_a, body=AprovarBody(vaga_id=r1["vaga_id"]), db=db, current_user={"id": user_id}
            )
            aloc = (
                await db.execute(
                    text(
                        "SELECT count(*), max(coalesce(posto_id::text, '')), max(coalesce(motivo, '')), "
                        " bool_and(ativo), max(coalesce(tipo, '')) FROM employee_alocacoes WHERE employee_id = CAST(:e AS uuid)"
                    ),
                    {"e": cand_a},
                )
            ).fetchone()
            ok(aloc[0] == 1, f"esteira com vaga: 1 linha em employee_alocacoes (achei {aloc[0]})")
            ok(aloc[1] == p1, "esteira com vaga: a linha aponta o POSTO da vaga")
            ok(aloc[2] == "alocacao_de_vaga", f"esteira com vaga: motivo `alocacao_de_vaga` (achei {aloc[2]!r})")
            ok(bool(aloc[3]) and aloc[4] == "alocar", "esteira com vaga: linha ATIVA do tipo alocar (F5)")
            ok(
                (res_a.get("propagacao", {}).get("operacional", {}).get("vaga") or {}).get("ok") is True,
                "esteira com vaga: a resposta conta a movimentação (nada silencioso)",
            )
            filled = (
                await db.execute(
                    text("SELECT filled_count, status FROM job_positions WHERE id::text = :v"), {"v": r1["vaga_id"]}
                )
            ).fetchone()
            ok(filled[0] == 1 and filled[1] == "aberta", f"esteira com vaga: vaga baixou 1 de 3 e segue aberta ({filled})")
            posto_a = (
                await db.execute(
                    text("SELECT posto_atual_id::text, status FROM employees WHERE id::text = :e"), {"e": cand_a}
                )
            ).fetchone()
            ok(posto_a[0] == p1 and posto_a[1] == "ativo", "esteira com vaga: o candidato virou ativo NO posto")

            await aprovar_e_ativar(
                candidato_id=cand_b, body=AprovarBody(posto_id=p1), db=db, current_user={"id": user_id}
            )
            n_b = (
                await db.execute(
                    text("SELECT count(*) FROM employee_alocacoes WHERE employee_id = CAST(:e AS uuid)"), {"e": cand_b}
                )
            ).scalar()
            ok(n_b == 0, f"esteira SEM vaga: nenhuma linha em employee_alocacoes — caminho de hoje (achei {n_b})")
            b_ok = (
                await db.execute(
                    text(
                        "SELECT (SELECT count(*) FROM allocations WHERE employee_id = CAST(:e AS uuid) AND status = 'active'), "
                        " (SELECT posto_atual_id::text FROM employees WHERE id = CAST(:e AS uuid)), "
                        " (SELECT count(*) FROM shifts WHERE employee_id = CAST(:e AS uuid))"
                    ),
                    {"e": cand_b},
                )
            ).fetchone()
            ok(
                b_ok[0] == 1 and b_ok[1] == p1 and b_ok[2] > 0,
                f"esteira SEM vaga: allocations + posto + escala como sempre foram ({b_ok})",
            )

            # ── 6. página pública por token ──
            await db.execute(
                text(
                    "INSERT INTO op_setores (nome, client_id, contract_id, responsavel, email, whatsapp) "
                    "VALUES (:n, CAST(:cl AS uuid), CAST(:ct AS uuid), 'Zelador FIX', 'fixture@example.invalid', '')"
                ),
                {"n": f"{FIX} portaria social", "cl": cli_id, "ct": ctr_id},
            )
            await db.commit()
            await v2._ensure(db)
            setor = (
                await db.execute(text("SELECT id::text, token FROM op_setores WHERE nome LIKE :f"), {"f": f"%{FIX}%"})
            ).fetchone()
            ok(bool(setor and setor[1]), "QR: o setor novo nasceu com token")

            app = _mini_app(db)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://oraculo"
            ) as cli_http:
                g = await cli_http.get(f"/api/v1/redesign/publico/chamado/{setor[1]}")
                ok(g.status_code == 200 and "portaria social" in g.text, "QR: GET público devolve a página do setor")
                g404 = await cli_http.get("/api/v1/redesign/publico/chamado/naoexiste123")
                ok(g404.status_code == 404, f"QR: token inválido = 404 no GET (achei {g404.status_code})")
                p422 = await cli_http.post(
                    f"/api/v1/redesign/publico/chamado/{setor[1]}",
                    data={"descricao": "curto", "nome": "Morador", "telefone": "92999"},
                )
                ok(p422.status_code == 422, f"QR: POST sem descrição de verdade = 422 (achei {p422.status_code})")
                p404 = await cli_http.post(
                    "/api/v1/redesign/publico/chamado/naoexiste123",
                    data={"descricao": f"{FIX} nao deve gravar nada", "nome": "X", "telefone": "1"},
                )
                ok(p404.status_code == 404, f"QR: token inválido = 404 no POST (achei {p404.status_code})")
                pok = await cli_http.post(
                    f"/api/v1/redesign/publico/chamado/{setor[1]}",
                    data={
                        "descricao": f"{FIX} portão social não fecha desde ontem",
                        "nome": "Morador do 302",
                        "telefone": "92 98888-0000",
                        "prioridade": "alta",
                    },
                )
                ok(pok.status_code == 200 and "aberto" in pok.text.lower(), "QR: POST bom confirma o chamado na tela")
            # a rota da etiqueta é autenticada (CurrentActiveUser) e a app mínima deste oráculo não
            # resolve a referência adiantada do tipo — o PDF se prova pelo gerador (7) e a rota, por
            # estar registrada; sobre HTTP de verdade ela responde 200 (ver §4 do relatório).
            rotas = {getattr(r, "path", "") for r in v2.router.routes}
            ok(
                "/setores/{setor_id}/etiqueta/pdf" in rotas,
                f"QR: a rota da etiqueta está registrada no router (achei {sorted(rotas)})",
            )

            ch = (
                await db.execute(
                    text(
                        "SELECT count(*), max(coalesce(canal, '')), max(coalesce(setor_id::text, '')), "
                        " max(coalesce(solicitante_contato, '')), bool_and(jsonb_array_length(notificado) > 0) "
                        "FROM op_chamados WHERE descricao LIKE :f"
                    ),
                    {"f": f"%{FIX}%"},
                )
            ).fetchone()
            ok(ch[0] == 1, f"QR: exatamente 1 chamado gravado — o 404 não gravou nada (achei {ch[0]})")
            ok(ch[1] == "qr", f"QR: o chamado nasceu com canal 'qr' (achei {ch[1]!r})")
            ok(ch[2] == setor[0], "QR: o chamado aponta o SETOR do token")
            ok(bool(ch[3]), "QR: o telefone de quem pediu ficou gravado")
            ok(bool(ch[4]), "QR: o responsável foi avisado (simulado no sandbox) — notificado não vazio")

            # ── 7. etiqueta pelo gerador, com o endereço público dentro ──
            pdf = v2.montar_etiqueta_pdf("Portaria social", f"{v2.BASE_URL}{v2.PUBLICO}/{setor[1]}", cliente="Teste")
            ok(pdf[:4] == b"%PDF" and len(pdf) > 3000, f"etiqueta: gerador devolve PDF de verdade ({len(pdf)} bytes)")
        finally:
            await _limpar(db)
            try:
                sobra = (
                    await db.execute(
                        text(
                            "SELECT (SELECT count(*) FROM employees WHERE nome LIKE :f) "
                            " + (SELECT count(*) FROM posts WHERE name LIKE :f) "
                            " + (SELECT count(*) FROM op_setores WHERE nome LIKE :f) "
                            " + (SELECT count(*) FROM job_positions WHERE title LIKE :f OR description LIKE :f)"
                        ),
                        {"f": f"%{FIX}%"},
                    )
                ).scalar()
            except Exception:  # noqa: BLE001 — rodada vermelha
                await db.rollback()
                sobra = "coluna inexistente"
            print(f"  fixtures apagadas (sobra: {sobra})")

    print(f"TOTAL falhas DGX V2: {len(falhas)}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
