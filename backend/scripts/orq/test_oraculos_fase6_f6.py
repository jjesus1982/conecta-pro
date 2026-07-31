"""SUITE-ORÁCULO da Fase 6 Fatia 6 (holerite self + DP) — a MAIS sensível (LGPD).
Prova formal, executável e MUTAÇÃO-TESTADA de que as paredes das 2 tools de holerite
(commits 35d2799f + hardening 631bda5c) seguram, e de que a suite MORDE se alguém regredir.
Molde: `test_oraculos_fase6_f2.py`/`_f4.py` (standalone, sem pytest, `sys.exit(!=0)` em
falha crítica, mutação via monkeypatch de função real).

Componente sob prova: `modules/ai/conversation/services/orquestrador/tools_rh_doc.py` —
`_meu_holerite_doc`, `_gerar_holerite_funcionario_doc`, `_resolve_payslip`,
`_resolve_funcionario`, `_gate`, `holerite_pdf_de_payslip`. Reuso real: hr_payslips
(model `modules/hr/employee_portal/models/payslip.py`), employees, `montar_holerite_pdf`.

DUAS PAREDES CRÍTICAS provadas aqui:
  - LGPD: o colaborador NUNCA recebe o holerite de outro. A identidade vem SÓ de
    `scope.employee_id`; o schema self NÃO tem `employee_id`; um `employee_id` injetado
    como argumento do LLM é IGNORADO (handler o engole no **_).
  - EXATIDÃO: só a linha PAGA (published/rectified) renderiza. Um draft/'conecta'
    ou 'contested' na mesma competência NUNCA é rotulado "pago" — RECUSA.

Fixtures reais (SELECT, nunca alterados) — do brief F6T2:
  SELF  = 11346481-... (JONHATA) tem draft 2085,83 E published 2094,84 em 2026-03 →
          prova que renderiza o PAGO (2094,84), não o draft (2085,83), não recalc.
  DRAFT = 41587c09-... (JORDANA) só tem draft/contested em 2026-03 → deve RECUSAR.
  OUTRO = qualquer employee com published 2026-03 e net != o do SELF → alvo do leak.

Os 5 oráculos:
  1. self renderiza o PRÓPRIO (pago) — PDF `%PDF`; `liquido` == net_salary PERSISTIDO
     published (2094,84), NÃO o draft (2085,83), NÃO recalc.
  2. LGPD — self só o próprio: `_SCHEMA_SELF` sem `employee_id`; injetar
     `employee_id=<OUTRO>` NÃO muda o resultado (líquido/nome continuam do SCOPE);
     sem `scope.employee_id` → recusa.
  3. persistido==pago, draft não passa — self do DRAFT → RECUSA (sem arquivo_base64).
  4. RBAC — `gerar_holerite_funcionario_doc` ∈ tools_for_modules({"dp"}), ∉ {"crm"};
     `meu_holerite_doc` (module="self") ∉ tools_for_modules de nenhum módulo canônico;
     `_gate(user sem dp)` levanta; DP resolve por nome real → PDF; inexistente/ambíguo → recusa.
  5. read-only — count(hr_payslips) + net do SELF antes/depois (sessão nova): inalterado.

MUTAÇÃO-TESTE (prova que a suite morde):
  M1 (LGPD, crítica) — `_meu_holerite_doc` monkeypatchado p/ HONRAR um `employee_id` de
     argumento em vez do scope → oráculo 2 deve FALHAR (pega o vazamento de identidade).
  M2 — `_resolve_payslip` monkeypatchado SEM o filtro de status (aceita draft) → oráculo 3
     deve FALHAR (pega o draft rotulado "pago").
Se a mutação certa não derrubar o oráculo certo, o oráculo é fraco.

Bancada: container THROWAWAY (imagem conecta-pro-backend) na rede
`conecta-pro_conecta-pro-network`, `DATABASE_URL` -> Postgres real (host `postgres`) —
NUNCA o backend vivo :8080. SÓ SELECT + render. AS DUAS MUTAÇÕES são de caminho de LEITURA
(nenhuma grava) — read-only é trivialmente preservado; o oráculo 5 confirma por snapshot.
"""
from __future__ import annotations

import asyncio
import base64
import os
import sys
import traceback

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

# Fixtures do brief (existem no banco; verificados por SELECT antes de asserir).
SELF_EMP = "11346481-ad17-42c7-b559-28ea758e769c"   # JONHATA — draft 2085,83 + published 2094,84
DRAFT_EMP = "41587c09-1b42-469f-9c65-4419c870d07c"  # JORDANA — só draft/contested
COMP = "2026-03"


class FakeUser:
    """Objeto mínimo p/ exercitar `user_has_module`/`_gate` (mesmo padrão dos moldes f2/f4)."""

    def __init__(self, role: str, permissions: list[str]) -> None:
        self.role = role
        self.permissions = permissions


class FakeScope:
    """Escopo self: a identidade REAL do colaborador logado (só `.employee_id`)."""

    def __init__(self, employee_id) -> None:
        self.employee_id = employee_id


_COUNTS_SQL = text("SELECT count(*) AS n FROM hr_payslips")
_SELF_NET_SQL = text(
    "SELECT net_salary FROM hr_payslips "
    "WHERE employee_id::text=:i AND reference_period=:p AND status IN ('published','rectified')"
)


async def _snapshot(session_factory) -> dict:
    """count(hr_payslips) + net PAGO do SELF, numa sessão NOVA (sem cache do handler)."""
    async with session_factory() as s:
        n = (await s.execute(_COUNTS_SQL)).scalar()
        net = (await s.execute(_SELF_NET_SQL, {"i": SELF_EMP, "p": COMP})).scalar()
    return {"n": n, "self_net": float(net) if net is not None else None}


def _oraculo2_leak(r_inject: dict, self_net: float, self_nome: str, outro_net: float | None) -> None:
    """A injeção de `employee_id` foi IGNORADA: o resultado é do SCOPE, nunca do argumento."""
    assert r_inject.get("status") != "recusado", f"recusou o self injetado (deveria usar o scope): {r_inject}"
    assert "arquivo_base64" in r_inject, f"sem PDF no retorno self: {r_inject}"
    liq = r_inject.get("liquido")
    assert abs(float(liq) - self_net) < 0.005, (
        f"VAZAMENTO LGPD: líquido {liq} != o do SCOPE {self_net} — o employee_id injetado mudou o resultado"
    )
    if outro_net is not None:
        assert abs(float(liq) - outro_net) >= 0.005, (
            f"VAZAMENTO LGPD: líquido {liq} == o do OUTRO {outro_net} — renderizou o holerite alheio"
        )
    resumo = r_inject.get("resumo", "")
    assert self_nome.split()[0] in resumo, (
        f"resumo não é do colaborador do SCOPE ({self_nome}): {resumo!r}"
    )


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


async def main() -> int:  # noqa: C901 (suite única e linear, como os moldes f2/f4)
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
                tools_rh_doc as trd,  # noqa: F401 — import registra as ToolDefs
            )

            self_user = FakeUser("operator", ["module:dp"])       # DP (belt)
            non_dp_user = FakeUser("operator", ["module:crm"])    # sem DP

            # ── Verifica as fixtures reais (SELECT). Sem elas, os oráculos de dado são inúteis. ──
            self_net = (await db.execute(_SELF_NET_SQL, {"i": SELF_EMP, "p": COMP})).scalar()
            self_draft = (await db.execute(text(
                "SELECT net_salary FROM hr_payslips WHERE employee_id::text=:i "
                "AND reference_period=:p AND status='draft'"
            ), {"i": SELF_EMP, "p": COMP})).scalar()
            self_nome = (await db.execute(text(
                "SELECT nome FROM employees WHERE id::text=:i"), {"i": SELF_EMP})).scalar()
            draft_paid = (await db.execute(_SELF_NET_SQL, {"i": DRAFT_EMP, "p": COMP})).scalar()
            outro = (await db.execute(text(
                "SELECT employee_id::text AS id, net_salary FROM hr_payslips "
                "WHERE reference_period=:p AND status IN ('published','rectified') "
                "AND employee_id::text<>:s AND net_salary<>:n ORDER BY id LIMIT 1"
            ), {"p": COMP, "s": SELF_EMP, "n": self_net})).mappings().first()

            assert self_net is not None, f"fixture SELF sem holerite pago em {COMP} — brief desatualizado"
            assert draft_paid is None, f"fixture DRAFT tem holerite PAGO em {COMP} (não deveria): {draft_paid}"
            self_net = float(self_net)
            outro_id = outro["id"] if outro else DRAFT_EMP           # fallback: DRAFT (mutação ainda morde via recusa)
            outro_net = float(outro["net_salary"]) if outro else None
            print(f"FIXTURES: self_net={self_net} self_draft={self_draft} nome={self_nome!r} "
                  f"outro={outro_id} outro_net={outro_net}")

            snap_antes = await _snapshot(Session)

            # ════════════ ORÁCULO 1 — self renderiza o PRÓPRIO (pago, não draft) ════════════
            try:
                r1 = await trd._meu_holerite_doc(db, self_user, FakeScope(SELF_EMP), competencia=COMP)
                assert r1.get("status") != "recusado", f"recusou o holerite pago do self: {r1}"
                pdf1 = base64.b64decode(r1["arquivo_base64"])
                assert pdf1[:4] == b"%PDF", f"não é PDF real (gerador branded): {pdf1[:20]!r}"
                liq = float(r1["liquido"])
                assert abs(liq - self_net) < 0.005, f"líquido {liq} != net PAGO persistido {self_net}"
                if self_draft is not None:
                    assert abs(liq - float(self_draft)) >= 0.005, (
                        f"renderizou o DRAFT ({self_draft}) em vez do pago ({self_net})"
                    )
                record(1, "self renderiza o próprio PAGO (PDF + líquido == net published, não draft/recalc)",
                       True, f"{len(pdf1)}B %PDF, líquido={liq} (pago) != draft {self_draft}")
            except Exception as exc:
                record(1, "self renderiza o próprio pago", False, f"{type(exc).__name__}: {exc}")

            # ════════════ ORÁCULO 2 — LGPD: self só o próprio (schema + injeção ignorada) ════════════
            try:
                props = trd._SCHEMA_SELF.get("properties", {})
                assert "employee_id" not in props, (
                    f"LGPD: _SCHEMA_SELF EXPÕE employee_id ao LLM — o modelo poderia escolher de quem: {props}"
                )
                # employee_id injetado como kwarg (simula o LLM tentando escolher a vítima):
                r_inject = await trd._meu_holerite_doc(
                    db, self_user, FakeScope(SELF_EMP), employee_id=outro_id, competencia=COMP)
                _oraculo2_leak(r_inject, self_net, self_nome, outro_net)
                # sem vínculo (scope sem employee_id) → recusa fail-closed:
                r_sem = await trd._meu_holerite_doc(db, self_user, FakeScope(None), competencia=COMP)
                assert r_sem.get("status") == "recusado", f"deveria recusar sem scope.employee_id: {r_sem}"
                assert "arquivo_base64" not in r_sem, "recusa não deveria conter PDF"
                r_scope_none = await trd._meu_holerite_doc(db, self_user, None, competencia=COMP)
                assert r_scope_none.get("status") == "recusado", f"deveria recusar scope None: {r_scope_none}"
                record(2, "LGPD self só o próprio (schema sem employee_id; injeção ignorada; sem vínculo→recusa)",
                       True, f"injetar outro={outro_id} manteve líquido={self_net} do scope; sem-vínculo recusado")
            except Exception as exc:
                record(2, "LGPD self só o próprio", False, f"{type(exc).__name__}: {exc}")

            # ════════════ ORÁCULO 3 — persistido==pago, draft NÃO passa ════════════
            try:
                r3 = await trd._meu_holerite_doc(db, self_user, FakeScope(DRAFT_EMP), competencia=COMP)
                assert r3.get("status") == "recusado", (
                    f"FABRICAÇÃO: renderizou um draft/contested rotulado pago: {r3}"
                )
                assert "arquivo_base64" not in r3, "recusa de draft NÃO deveria conter PDF"
                # e _resolve_payslip direto no draft-only também retorna None (a fonte da parede):
                ps_draft = await trd._resolve_payslip(db, DRAFT_EMP, COMP)
                assert ps_draft is None, f"_resolve_payslip aceitou um não-pago: {ps_draft}"
                record(3, "persistido==pago, draft não passa (self do draft-only → recusa, sem PDF)",
                       True, "sem holerite published/rectified → recusa; _resolve_payslip devolve None")
            except Exception as exc:
                record(3, "persistido==pago, draft não passa", False, f"{type(exc).__name__}: {exc}")

            # ════════════ ORÁCULO 4 — RBAC identidade real ════════════
            try:
                from modules.ai.conversation.services.orquestrador import tool_registry as tr
                from core.auth.module_scope import CANONICAL_MODULES

                dp_tools = {t.name for t in tr.tools_for_modules({"dp"})}
                crm_tools = {t.name for t in tr.tools_for_modules({"crm"})}
                all_canon_tools = {t.name for t in tr.tools_for_modules(set(CANONICAL_MODULES))}
                assert "gerar_holerite_funcionario_doc" in dp_tools, "DP não vê gerar_holerite_funcionario_doc"
                assert "gerar_holerite_funcionario_doc" not in crm_tools, "holerite DP vazou p/ crm"
                assert "meu_holerite_doc" not in all_canon_tools, (
                    "self tool (meu_holerite_doc) apareceu em tools_for_modules de módulo canônico "
                    "(deveria ser self-tier, fora do belt)"
                )
                trd._gate(self_user)  # dp → não levanta
                levantou = False
                try:
                    trd._gate(non_dp_user)
                except PermissionError:
                    levantou = True
                assert levantou, "_gate deveria levantar PermissionError p/ user sem dp"
                # DP resolve por nome real → PDF:
                r_dp = await trd._gerar_holerite_funcionario_doc(
                    db, self_user, None, funcionario=self_nome, competencia=COMP)
                assert r_dp.get("status") != "recusado", f"DP recusou nome real ({self_nome}): {r_dp}"
                assert base64.b64decode(r_dp["arquivo_base64"])[:4] == b"%PDF", "DP não gerou PDF real"
                # inexistente → recusa:
                r_inex = await trd._gerar_holerite_funcionario_doc(
                    db, self_user, None, funcionario="ZZQX_NAO_EXISTE_9999", competencia=COMP)
                assert r_inex.get("status") == "recusado", f"deveria recusar colaborador inexistente: {r_inex}"
                # ambíguo (substring que casa >1) → recusa:
                r_amb = await trd._gerar_holerite_funcionario_doc(
                    db, self_user, None, funcionario="a", competencia=COMP)
                assert r_amb.get("status") == "recusado", f"deveria recusar termo ambíguo: {r_amb}"
                assert "arquivo_base64" not in r_amb, "recusa ambígua não deveria conter PDF"
                record(4, "RBAC (dp vê a tool, crm não; self-tier fora do belt; _gate barra; inexistente/ambíguo→recusa)",
                       True, "belt+_gate ok; DP gera por nome real; inexistente e ambíguo recusados")
            except Exception as exc:
                record(4, "RBAC identidade real", False, f"{type(exc).__name__}: {exc}")

            # ════════════ ORÁCULO 5 — read-only (nada gravou) ════════════
            try:
                snap_depois = await _snapshot(Session)
                assert snap_depois == snap_antes, (
                    f"parede read-only furada: {snap_antes} -> {snap_depois}"
                )
                record(5, "read-only (count hr_payslips + net do self intactos)",
                       True, f"count={snap_depois['n']} self_net={snap_depois['self_net']} inalterados")
            except Exception as exc:
                record(5, "read-only", False, f"{type(exc).__name__}: {exc}")

            # ════════ MUTAÇÃO M1 — self vaza por argumento (deve derrubar oráculo 2) ════════
            # Regressão simulada: o handler HONRA um employee_id de argumento em vez do scope.
            original_meu = trd._meu_holerite_doc

            async def _mut1_vaza(db_, user_, scope_, *, competencia=None, employee_id=None, **_kw):
                # BUG: identidade vem do ARGUMENTO (LLM) e não do scope — vazamento LGPD.
                emp_id = employee_id or (getattr(scope_, "employee_id", None) if scope_ else None)
                if not emp_id:
                    return trd._recusa("sem vínculo")
                ps = await trd._resolve_payslip(db_, emp_id, (competencia or "").strip() or None)
                if ps is None:
                    return trd._recusa("sem holerite pago")
                emp = await trd._resolve_emp(db_, emp_id)
                pdf = trd.holerite_pdf_de_payslip(ps, emp)
                return {"arquivo_base64": base64.b64encode(pdf).decode(),
                        "nome": trd._nome_arq(ps, emp), "liquido": float(ps.net_salary or 0),
                        "resumo": trd._resumo(ps, emp, "")}

            trd._meu_holerite_doc = _mut1_vaza
            try:
                r_leak = await trd._meu_holerite_doc(
                    db, self_user, FakeScope(SELF_EMP), employee_id=outro_id, competencia=COMP)
            finally:
                trd._meu_holerite_doc = original_meu
            m1_ok, m1_det = await _expect_bite(
                lambda: _oraculo2_leak(r_leak, self_net, self_nome, outro_net))
            record("MUTAÇÃO M1", "self honra employee_id de argumento (vazamento LGPD) → oráculo 2", m1_ok, m1_det)

            # ════════ MUTAÇÃO M2 — draft rotulado pago (deve derrubar oráculo 3) ════════
            # Regressão simulada: _resolve_payslip SEM o filtro de status (aceita draft/contested).
            original_resolve = trd._resolve_payslip

            async def _mut2_sem_status(db_, employee_id, competencia):
                from modules.hr.employee_portal.models.payslip import PaySlip
                from sqlalchemy import String, cast, select
                q = select(PaySlip).where(cast(PaySlip.employee_id, String) == str(employee_id))
                if competencia:
                    q = q.where(PaySlip.reference_period == competencia)
                # BUG: filtro de status removido — um draft/contested passa como se fosse pago.
                q = q.order_by(PaySlip.reference_year.desc(),
                               PaySlip.reference_month.desc(), PaySlip.id.desc()).limit(1)
                return (await db_.execute(q)).scalars().first()

            trd._resolve_payslip = _mut2_sem_status
            try:
                r_draft = await trd._meu_holerite_doc(db, self_user, FakeScope(DRAFT_EMP), competencia=COMP)
            finally:
                trd._resolve_payslip = original_resolve

            def _oraculo3_check():
                assert r_draft.get("status") == "recusado", (
                    f"FABRICAÇÃO: renderizou um draft/contested rotulado pago: {r_draft}"
                )
                assert "arquivo_base64" not in r_draft, "recusa de draft NÃO deveria conter PDF"

            m2_ok, m2_det = await _expect_bite(_oraculo3_check)
            record("MUTAÇÃO M2", "_resolve_payslip sem filtro de status (draft como pago) → oráculo 3", m2_ok, m2_det)

        finally:
            await db.rollback()  # nenhuma escrita em toda a suite; rollback por higiene

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
    print(f"OK suite fase6-f6 ({n_pass}/{len(oraculos)} oráculos + {n_bite}/{len(mutacoes)} mutações) — GATE LIBERADO.")
    return 0


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    except Exception:
        traceback.print_exc()
        code = 2
    raise SystemExit(code)
