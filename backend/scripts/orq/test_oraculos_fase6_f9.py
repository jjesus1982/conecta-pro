"""SUITE-ORÁCULO da Fase 6 Fatia 9 (comprovante de pagamento no chat) — money-adjacent.
Prova formal, executável e MUTAÇÃO-TESTADA de que as paredes da tool
`gerar_comprovante_pagamento_doc` (commit 6ddf4b49) seguram, e de que a suite MORDE
se alguém regredir. Molde: `test_oraculos_fase6_f3.py`/`_f6.py` (standalone, sem
pytest, `sys.exit(!=0)` em falha crítica, mutação via monkeypatch de função real).

Componente sob prova: `modules/ai/conversation/services/orquestrador/
tools_financeiro_doc.py` — `_gerar_comprovante_pagamento_doc`, `_resolve_pagamento`,
`_gate`. Reuso real: `_pagamento_efetivado` (deny-list) + `comprovante_pdf_de_pagamento`
(`modules/integrations/inter/payment_controller.py`).

DUAS PAREDES CRÍTICAS provadas aqui:
  - GUARDA EFETIVADO: um comprovante NUNCA é produzido para um pagamento que não saiu
    (status preparado/aprovado/cancelado/erro, ou id inexistente). Fonte única da
    verdade = `_pagamento_efetivado` (deny-list `_STATUS_NAO_EFETIVADO`); o status
    real de efetivado no banco é **'confirmado'** (não 'executado').
  - READ-ONLY: a tool é pura leitura de `inter_payments` — NUNCA move, cria, aprova
    ou altera um pagamento (nem via categorização como o fluxo de caixa da F3; aqui
    não há nenhum UPDATE idempotente reusado — é leitura pura).

Fixtures reais (SELECT, resolvidas na própria suite, nunca hardcoded IDs):
  EFETIVADO     = 1 linha real com status='confirmado' AND inter_payment_id IS NOT NULL.
  NÃO-EFETIVADO = 1 linha real com status IN ('preparado','aprovado').
  INEXISTENTE   = uuid4() aleatório (não existe na tabela).

Os 4 oráculos:
  1. Efetivado → PDF — `_gerar_comprovante_pagamento_doc(..., pagamento_id=EFETIVADO)`
     devolve `arquivo_base64` que decoda `%PDF` real (gerador branded).
  2. Guarda efetivado — NÃO-efetivado (preparado/aprovado) → `{"status":"recusado"}`
     sem `arquivo_base64`; id inexistente → recusa também. NUNCA gera comprovante de
     pagamento não-realizado. Confirma a fonte (`_pagamento_efetivado`) direto.
  3. RBAC diretoria — a tool ∈ `tools_for_modules({"financeiro"})`, ∉ `{"crm"}`;
     `_gate(user sem financeiro)` levanta `PermissionError`.
  4. Read-only (parede money) — snapshot de `inter_payments` (count total + status/
     valor/inter_payment_id/observacoes da linha EFETIVADA, lido em SESSÃO NOVA)
     antes/depois de rodar a tool (efetivado + não-efetivado + inexistente):
     inalterado. A tool não move/altera/cria pagamento.

MUTAÇÃO-TESTE (prova que a suite morde):
  M1 (guarda furada) — `_pagamento_efetivado` (no módulo `payment_controller`, fonte
     única usada tanto pelo gate em `tools_financeiro_doc` quanto internamente por
     `comprovante_pdf_de_pagamento`) monkeypatchada p/ sempre retornar True → aceita
     um pagamento NÃO-efetivado → oráculo 2 deve FALHAR (geraria PDF de pagamento
     que não saiu).
  M2 (efeito colateral) — `_gerar_comprovante_pagamento_doc` monkeypatchada p/ fazer
     um UPDATE real em `inter_payments` (seta `observacoes`) + commit ANTES de
     delegar pro original → oráculo 4 deve FALHAR (read-only violado). Revertido
     explicitamente logo em seguida (UPDATE de volta ao valor original + commit),
     com 0 resíduo verificado por snapshot novo.
Se a mutação certa não derrubar o oráculo certo, o oráculo é fraco.

Bancada: container THROWAWAY (imagem conecta-pro-backend) na rede
`conecta-pro_conecta-pro-network`, `DATABASE_URL` -> Postgres real (host `postgres`) —
NUNCA o backend vivo :8080. Oráculos 1/2/3 e a M1 são só SELECT + render. A M2
GRAVA de propósito (para provar que o oráculo 4 pega) e REVERTE no mesmo teste,
verificado por snapshot — nenhum resíduo fica no banco ao final da suite.
"""
from __future__ import annotations

import asyncio
import base64
import os
import sys
import traceback
import uuid

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402


class FakeUser:
    """Objeto mínimo p/ exercitar `user_has_module`/`_gate` (mesmo padrão dos moldes f3/f6)."""

    def __init__(self, role: str, permissions: list[str]) -> None:
        self.role = role
        self.permissions = permissions


_COUNT_SQL = text("SELECT count(*) AS n FROM inter_payments")
_ROW_SQL = text(
    "SELECT status, valor, inter_payment_id, observacoes FROM inter_payments WHERE id=:id"
)


async def _snapshot(session_factory, target_id: str) -> dict:
    """count(inter_payments) + a linha-alvo (status/valor/inter_payment_id/observacoes),
    numa sessão NOVA (sem cache do handler)."""
    async with session_factory() as s:
        n = (await s.execute(_COUNT_SQL)).scalar()
        row = (await s.execute(_ROW_SQL, {"id": target_id})).mappings().first()
    return {"n": n, "row": dict(row) if row else None}


def _sem_pdf(resultado: dict) -> dict:
    """Cópia do resultado sem o base64 do PDF, só p/ mensagens de erro legíveis."""
    return {k: (f"<{len(v)}B base64>" if k == "arquivo_base64" else v) for k, v in resultado.items()}


async def _expect_bite(coro_factory):
    """A mutação MORDE se o oráculo (async ou sync) FALHA sob ela."""
    try:
        r = coro_factory()
        if asyncio.iscoroutine(r):
            await r
    except AssertionError as exc:
        return True, f"mordeu ({type(exc).__name__}: {exc})"
    except Exception as exc:  # noqa: BLE001 — qualquer exceção sob mutação também conta
        return True, f"mordeu ({type(exc).__name__}: {exc})"
    return False, "NÃO mordeu — oráculo passou sob mutação (oráculo FRACO!)"


async def main() -> int:  # noqa: C901 (suite única e linear, como os moldes f3/f6)
    results: list[tuple[object, str, bool, str]] = []

    def record(n, desc: str, ok: bool, detail: str = "") -> None:
        results.append((n, desc, ok, detail))
        tag = "PASS" if ok else "FAIL"
        rot = f"ORACULO {n}" if isinstance(n, int) else str(n)
        print(f"{rot} {desc} ... {tag}{(' — ' + detail) if detail else ''}")

    eng = create_async_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    Session = async_sessionmaker(eng, expire_on_commit=False)

    async with Session() as db:
        try:
            from modules.ai.conversation.services.orquestrador import (
                tools_financeiro_doc as tfd,  # noqa: F401 — import registra a ToolDef
            )
            import modules.integrations.inter.payment_controller as pc

            fin_user = FakeUser("operator", ["module:financeiro"])
            non_fin_user = FakeUser("operator", ["module:crm"])

            # ── Fixtures REAIS via SQL (nunca hardcode de id) ────────────────
            efetivado = (await db.execute(text(
                "SELECT id, observacoes FROM inter_payments "
                "WHERE status='confirmado' AND inter_payment_id IS NOT NULL "
                "ORDER BY id LIMIT 1"))).mappings().first()
            assert efetivado, "sem pagamento EFETIVADO (status='confirmado') real — brief desatualizado"
            EFET_ID = str(efetivado["id"])
            EFET_OBS_ORIG = efetivado["observacoes"]

            nao_efet = (await db.execute(text(
                "SELECT id FROM inter_payments WHERE status IN ('preparado','aprovado') "
                "ORDER BY id LIMIT 1"))).mappings().first()
            assert nao_efet, "sem pagamento NÃO-efetivado (preparado/aprovado) real — brief desatualizado"
            NAO_EFET_ID = str(nao_efet["id"])

            INEXISTENTE_ID = str(uuid.uuid4())

            print(f"FIXTURES: efetivado={EFET_ID} nao_efetivado={NAO_EFET_ID} "
                  f"inexistente={INEXISTENTE_ID}")

            snap_antes = await _snapshot(Session, EFET_ID)

            # ════════════ ORÁCULO 1 — efetivado → PDF ════════════
            try:
                r1 = await tfd._gerar_comprovante_pagamento_doc(
                    db, fin_user, None, pagamento_id=EFET_ID)
                assert r1.get("status") != "recusado", f"recusou pagamento EFETIVADO real: {r1}"
                pdf1 = base64.b64decode(r1["arquivo_base64"])
                assert pdf1[:4] == b"%PDF", f"não é PDF real (gerador branded): {pdf1[:20]!r}"
                record(1, "efetivado renderiza o comprovante (PDF real, branded)",
                       True, f"{len(pdf1)}B %PDF, id={EFET_ID}")
            except Exception as exc:
                record(1, "efetivado renderiza o comprovante", False, f"{type(exc).__name__}: {exc}")

            # ════════════ ORÁCULO 2 — guarda efetivado (nunca fabrica) ════════════
            try:
                r2a = await tfd._gerar_comprovante_pagamento_doc(
                    db, fin_user, None, pagamento_id=NAO_EFET_ID)
                assert r2a.get("status") == "recusado", (
                    f"FABRICAÇÃO: gerou comprovante de pagamento NÃO-efetivado: {_sem_pdf(r2a)}"
                )
                assert "arquivo_base64" not in r2a, "recusa de não-efetivado não deveria conter PDF"

                r2b = await tfd._gerar_comprovante_pagamento_doc(
                    db, fin_user, None, pagamento_id=INEXISTENTE_ID)
                assert r2b.get("status") == "recusado", f"deveria recusar id inexistente: {_sem_pdf(r2b)}"
                assert "arquivo_base64" not in r2b, "recusa de id inexistente não deveria conter PDF"

                # a fonte da parede também recusa direto (belt-and-suspenders):
                row_nao = (await db.execute(text(
                    "SELECT status, inter_payment_id FROM inter_payments WHERE id=:id"),
                    {"id": NAO_EFET_ID})).mappings().first()
                assert pc._pagamento_efetivado(row_nao) is False, (
                    f"_pagamento_efetivado aceitou uma linha não-efetivada: {dict(row_nao)}"
                )
                record(2, "guarda efetivado (não-efetivado/inexistente → recusa, sem PDF)",
                       True, f"não-efetivado {NAO_EFET_ID} e inexistente {INEXISTENTE_ID} recusados")
            except Exception as exc:
                record(2, "guarda efetivado", False, f"{type(exc).__name__}: {exc}")

            # ════════════ ORÁCULO 3 — RBAC diretoria ════════════
            try:
                from modules.ai.conversation.services.orquestrador import tool_registry as tr

                fin_tools = {t.name for t in tr.tools_for_modules({"financeiro"})}
                crm_tools = {t.name for t in tr.tools_for_modules({"crm"})}
                assert "gerar_comprovante_pagamento_doc" in fin_tools, (
                    "financeiro não vê gerar_comprovante_pagamento_doc"
                )
                assert "gerar_comprovante_pagamento_doc" not in crm_tools, (
                    "comprovante de pagamento vazou p/ crm"
                )
                tfd._gate(fin_user)  # financeiro → não levanta
                levantou = False
                try:
                    tfd._gate(non_fin_user)
                except PermissionError:
                    levantou = True
                assert levantou, "_gate deveria levantar PermissionError p/ user sem financeiro"
                record(3, "RBAC diretoria (financeiro vê a tool, crm não; _gate barra)",
                       True, "belt+_gate ok")
            except Exception as exc:
                record(3, "RBAC diretoria", False, f"{type(exc).__name__}: {exc}")

            # ════════════ ORÁCULO 4 — read-only (parede money) ════════════
            try:
                snap_depois = await _snapshot(Session, EFET_ID)
                assert snap_depois == snap_antes, (
                    f"parede read-only furada: {snap_antes} -> {snap_depois}"
                )
                record(4, "read-only (count inter_payments + linha efetivada intactos)",
                       True, f"count={snap_depois['n']} linha={snap_depois['row']} inalterados")
            except Exception as exc:
                record(4, "read-only", False, f"{type(exc).__name__}: {exc}")

            # ════════ MUTAÇÃO M1 — guarda furada (deve derrubar oráculo 2) ════════
            # Regressão simulada: a fonte única da verdade (_pagamento_efetivado) sempre
            # aceita — tanto o gate em tools_financeiro_doc quanto o interno de
            # comprovante_pdf_de_pagamento leem essa mesma função do módulo.
            original_efetivado = pc._pagamento_efetivado
            pc._pagamento_efetivado = lambda row: True
            try:
                r_m1 = await tfd._gerar_comprovante_pagamento_doc(
                    db, fin_user, None, pagamento_id=NAO_EFET_ID)
            finally:
                pc._pagamento_efetivado = original_efetivado

            def _oraculo2_check_mut():
                assert r_m1.get("status") == "recusado", (
                    f"FABRICAÇÃO: gerou comprovante de pagamento NÃO-efetivado: {_sem_pdf(r_m1)}"
                )
                assert "arquivo_base64" not in r_m1, "recusa não deveria conter PDF"

            m1_ok, m1_det = await _expect_bite(_oraculo2_check_mut)
            record("MUTAÇÃO M1", "_pagamento_efetivado sempre True (guarda furada) → oráculo 2",
                   m1_ok, m1_det)

            # ════════ MUTAÇÃO M2 — efeito colateral (deve derrubar oráculo 4) ════════
            # Regressão simulada: o handler grava em inter_payments antes de delegar —
            # viola read-only. GRAVA de propósito e REVERTE explicitamente em seguida.
            original_gerar = tfd._gerar_comprovante_pagamento_doc

            async def _mut2_grava(db_, user_, scope_, *, pagamento_id=None,
                                  beneficiario=None, data=None, **kw):
                await db_.execute(text(
                    "UPDATE inter_payments SET observacoes=:o WHERE id=:id"),
                    {"o": "MUTACAO_M9T2_NAO_DEVERIA_PERSISTIR", "id": pagamento_id})
                await db_.commit()
                return await original_gerar(
                    db_, user_, scope_, pagamento_id=pagamento_id,
                    beneficiario=beneficiario, data=data, **kw)

            tfd._gerar_comprovante_pagamento_doc = _mut2_grava
            try:
                await tfd._gerar_comprovante_pagamento_doc(db, fin_user, None, pagamento_id=EFET_ID)
            finally:
                tfd._gerar_comprovante_pagamento_doc = original_gerar

            async def _oraculo4_check_mut():
                snap_sob_mutacao = await _snapshot(Session, EFET_ID)
                assert snap_sob_mutacao == snap_antes, (
                    f"parede read-only furada: {snap_antes} -> {snap_sob_mutacao}"
                )

            m2_ok, m2_det = await _expect_bite(_oraculo4_check_mut)
            record("MUTAÇÃO M2", "UPDATE real em inter_payments (efeito colateral) → oráculo 4",
                   m2_ok, m2_det)

            # ── REVERT explícito da M2: 0 resíduo, verificado por snapshot novo ──
            await db.execute(text(
                "UPDATE inter_payments SET observacoes=:o WHERE id=:id"),
                {"o": EFET_OBS_ORIG, "id": EFET_ID})
            await db.commit()
            snap_revertido = await _snapshot(Session, EFET_ID)
            residuo_ok = snap_revertido == snap_antes
            record("REVERT M2", "reverte a gravação da M2 (0 resíduo, snapshot novo)",
                   residuo_ok, f"antes={snap_antes} revertido={snap_revertido}")

        finally:
            await db.rollback()  # higiene: nenhuma transação pendurada (M2 já commitou/reverteu)

    await eng.dispose()

    # ══════════════ RESUMO ══════════════
    oraculos = [r for r in results if isinstance(r[0], int)]
    mutacoes = [r for r in results if isinstance(r[0], str) and r[0].startswith("MUTAÇÃO")]
    n_pass = sum(1 for r in oraculos if r[2])
    n_bite = sum(1 for r in mutacoes if r[2])
    print("\n" + "═" * 68)
    print(f"RESUMO: {n_pass}/{len(oraculos)} oráculos PASS  |  "
          f"{n_bite}/{len(mutacoes)} mutações MORDERAM")
    falhas = [r for r in results if not r[2]]
    if falhas:
        print("FALHAS (findings — é a parede quebrando, NÃO ajustar o teste):")
        for n, desc, _ok, det in falhas:
            print(f"  ✗ {n} {desc} — {det}")
        print("═" * 68)
        print("GATE: BLOQUEADO.")
        return 1
    print("═" * 68)
    print(f"OK suite fase6-f9 ({n_pass}/{len(oraculos)} oráculos + {n_bite}/{len(mutacoes)} mutações, "
          "0 resíduo) — GATE LIBERADO.")
    return 0


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    except Exception:
        traceback.print_exc()
        code = 2
    raise SystemExit(code)
