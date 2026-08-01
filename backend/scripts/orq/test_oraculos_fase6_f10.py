"""SUITE-ORÁCULO da Fase 6 Fatia 10 (TRCT/aviso prévio self + DP) — LGPD.

Prova formal, executável e MUTAÇÃO-TESTADA de que as paredes das tools de TRCT
(commit c98ee365) seguram, e de que a suite MORDE se alguém regredir.
Molde: `test_oraculos_fase6_f6.py` (standalone, sem pytest, `sys.exit(!=0)` em
falha crítica, mutação via monkeypatch de função real).

Componente sob prova: `modules/ai/conversation/services/orquestrador/tools_rh_doc.py` —
`_meu_trct_doc`, `_gerar_trct_funcionario_doc`, `trct_pdf_de_termination`,
`_resolve_termination`, `_gate`, `_meu_aviso_previo_doc`. Model `TerminationProcess`
(people_management/hr/models/termination.py) tem `verbas_snapshot jsonb`.

DUAS PAREDES CRÍTICAS provadas aqui:
  - RENDER-PERSISTIDO: o TRCT SÓ renderiza do `verbas_snapshot` gravado na finalização —
    NUNCA recalcula (calculate_severance/clt_calculator). Sem snapshot → RECUSA.
  - LGPD: o colaborador NUNCA recebe o TRCT de outro. A identidade vem SÓ de
    `scope.employee_id`; o schema self NÃO tem `employee_id`; um `employee_id` injetado
    como argumento do LLM é IGNORADO (handler o engole no **_).

DADO (2026-08): NENHUMA termination real tem `verbas_snapshot` ainda (o código de
gravar não está bakado; a única `completed` real é legada, pré-snapshot). Então:
  - Oráculo de RENDER usa uma termination FAKE (SimpleNamespace com verbas_snapshot=
    dict plausível — mesmas chaves de `TerminationService.calculate_severance`/
    `montar_trct_pdf`) + um Employee FAKE. Chama `trct_pdf_de_termination` direto.
  - Oráculo de RECUSA usa a termination REAL legada (completed, verbas_snapshot=NULL) —
    fixture real, verificada por SELECT antes de asserir.

Fixtures reais (SELECT, nunca alterados):
  LEGACY_TERM_EMP = 109edac0-... (JÚLIO CÉSAR) — única termination completed real,
                    status='completed', verbas_snapshot=NULL (pré-snapshot).
  NO_TERM_EMP     = a78ea01e-... (Jordan) — empregado real SEM nenhuma termination.

Os 5 oráculos:
  1. render do snapshot — `trct_pdf_de_termination(fake_term_com_snapshot, fake_emp)` →
     bytes `%PDF`. Fonte é o snapshot fabricado (não há função de cálculo no caminho).
  2. sem snapshot → recusa, NUNCA recalc (parede central) —
     `trct_pdf_de_termination(fake_term_sem_snapshot, emp)` → None; `_meu_trct_doc`
     contra a termination legada REAL (sem snapshot) → recusado, sem arquivo_base64;
     grep no fonte: `tools_rh_doc.py` não importa/chama calculate_severance/clt_calculator.
  3. LGPD self — `_SCHEMA` da tool self de TRCT sem `employee_id`; `_meu_trct_doc`
     com `employee_id` injetado (de alguém SEM termination) é IGNORADO — o motivo da
     recusa continua o do SCOPE (legado sem snapshot), não vira "sem rescisão concluída"
     (o que ocorreria se o argumento tivesse sido honrado); sem scope.employee_id → recusa.
  4. RBAC DP — `gerar_trct_funcionario_doc` ∈ tools_for_modules({"dp"}), ∉ {"crm"};
     `meu_trct_doc` (self) ∉ tools_for_modules de módulo canônico; `_gate` barra sem dp.
  5. aviso prévio renderiza do REGISTRO (sem verbas) — `_meu_aviso_previo_doc` na
     termination legada real (sem verbas_snapshot) → PDF `%PDF` mesmo assim (não
     depende de verbas), provando que aviso prévio é caminho separado do TRCT.

MUTAÇÃO-TESTE (prova que a suite morde):
  M1 (render-persistido, crítica) — `trct_pdf_de_termination` monkeypatchado p/, quando
     não há snapshot, "recalcular" (fabrica um calc mínimo) e renderizar mesmo assim →
     oráculo 2 deve FALHAR (pega o fallback-recalc).
  M2 (LGPD) — `_meu_trct_doc` monkeypatchado p/ HONRAR um `employee_id` de argumento em
     vez do scope → oráculo 3 deve FALHAR (pega o vazamento de identidade).
Se a mutação certa não derrubar o oráculo certo, o oráculo é fraco.

Bancada: container THROWAWAY (imagem conecta-pro-backend) na rede
`conecta-pro_conecta-pro-network`, `DATABASE_URL` -> Postgres real (host `postgres`) —
NUNCA o backend vivo :8080. SÓ SELECT + render em memória (fakes). 0 escrita/resíduo.
"""
from __future__ import annotations

import asyncio
import base64
import inspect
import os
import sys
import traceback
from types import SimpleNamespace

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

# Fixtures do brief (existem no banco; verificadas por SELECT antes de asserir).
LEGACY_TERM_EMP = "109edac0-17a1-4cd4-8bf8-8b7062d905d0"  # JÚLIO CÉSAR — completed, sem snapshot
LEGACY_TERM_ID = "4c01077a-68c3-4efa-b53b-e06121041573"
NO_TERM_EMP = "a78ea01e-9919-4b10-afc7-7fc98bc03291"      # Jordan — sem termination nenhuma


class FakeUser:
    def __init__(self, role: str, permissions: list[str]) -> None:
        self.role = role
        self.permissions = permissions


class FakeScope:
    """Escopo self: a identidade REAL do colaborador logado (só `.employee_id`)."""

    def __init__(self, employee_id) -> None:
        self.employee_id = employee_id


def _fake_termination(*, snapshot: dict | None) -> SimpleNamespace:
    return SimpleNamespace(
        id="fake-term-0001",
        employee_id="fake-emp-0001",
        type="involuntary",
        reason="notice_type:indenizado",
        status="completed",
        last_working_day="2026-06-30",
        verbas_snapshot=snapshot,
    )


def _fake_employee() -> SimpleNamespace:
    return SimpleNamespace(
        id="fake-emp-0001",
        nome="FULANO DE TAL TESTE",
        cpf="12345678900",
        cargo="Agente de Portaria",
        matricula="F0001",
        data_admissao="2024-01-10",
    )


_SNAPSHOT_PLAUSIVEL = {
    "employee_name": "FULANO DE TAL TESTE",
    "termination_type": "involuntary",
    "last_working_day": "2026-06-30",
    "saldo_salario": 550.00,
    "aviso_previo_indenizado": 1700.00,
    "aviso_previo_dias": 33,
    "decimo_terceiro_proporcional": 850.00,
    "avos_decimo_terceiro": 6,
    "ferias_proporcionais": 850.00,
    "avos_ferias_proporcionais": 6,
    "terco_ferias_proporcionais": 283.33,
    "ferias_vencidas": 0.0,
    "terco_ferias_vencidas": 0.0,
    "multa_fgts_40": 680.00,
    "saldo_fgts_estimado": 850.00,
    "fgts_estimado": True,
    "total_proventos": 4233.33,
    "inss": 350.00,
    "irrf": 0.0,
    "total_descontos": 350.00,
    "total_liquido": 3883.33,
}

_COUNTS_SQL = text("SELECT count(*) AS n FROM termination_processes")


async def _snapshot_db(session_factory) -> dict:
    """count(termination_processes), numa sessão NOVA (sem cache do handler)."""
    async with session_factory() as s:
        n = (await s.execute(_COUNTS_SQL)).scalar()
    return {"n": n}


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


async def main() -> int:  # noqa: C901 (suite única e linear, como os moldes f2/f6)
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

            dp_user = FakeUser("operator", ["module:dp"])       # DP (belt)
            non_dp_user = FakeUser("operator", ["module:crm"])  # sem DP

            # ── Verifica as fixtures reais (SELECT). Sem elas, os oráculos de dado são inúteis. ──
            legacy = (await db.execute(text(
                "SELECT verbas_snapshot IS NOT NULL AS has_snap, status FROM termination_processes "
                "WHERE id::text=:i AND employee_id::text=:e"),
                {"i": LEGACY_TERM_ID, "e": LEGACY_TERM_EMP})).mappings().first()
            assert legacy is not None, f"fixture LEGACY_TERM ({LEGACY_TERM_ID}) não existe — brief desatualizado"
            assert legacy["status"] == "completed", f"fixture legada não está completed: {legacy}"
            assert legacy["has_snap"] is False, f"fixture legada TEM snapshot (não deveria): {legacy}"
            no_term = (await db.execute(text(
                "SELECT count(*) FROM termination_processes WHERE employee_id::text=:e"),
                {"e": NO_TERM_EMP})).scalar()
            assert no_term == 0, f"fixture NO_TERM_EMP tem {no_term} termination(s) (deveria ter 0)"
            print(f"FIXTURES: legacy_term={LEGACY_TERM_ID} emp={LEGACY_TERM_EMP} has_snap=False (completed); "
                  f"no_term_emp={NO_TERM_EMP} (0 terminations)")

            snap_antes = await _snapshot_db(Session)

            # ════════════ ORÁCULO 1 — render do snapshot (FAKE, dado que hoje nenhuma termination real tem) ════
            try:
                fake_term = _fake_termination(snapshot=_SNAPSHOT_PLAUSIVEL)
                fake_emp = _fake_employee()
                pdf1 = trd.trct_pdf_de_termination(fake_term, fake_emp)
                assert pdf1 is not None, "render retornou None com snapshot presente"
                assert pdf1[:4] == b"%PDF", f"não é PDF real (gerador branded): {pdf1[:20]!r}"
                assert len(pdf1) > 500, f"PDF suspeitosamente pequeno: {len(pdf1)}B"
                record(1, "render do snapshot PERSISTIDO (fake termination) → PDF branded",
                       True, f"{len(pdf1)}B %PDF a partir de verbas_snapshot fabricado (dict plausível)")
            except Exception as exc:
                record(1, "render do snapshot", False, f"{type(exc).__name__}: {exc}")

            # ════════════ ORÁCULO 2 — sem snapshot → recusa, NUNCA recalc (parede central) ════════════
            try:
                fake_term_sem = _fake_termination(snapshot=None)
                pdf_none = trd.trct_pdf_de_termination(fake_term_sem, _fake_employee())
                assert pdf_none is None, f"FABRICAÇÃO: renderizou sem snapshot: {pdf_none[:20] if pdf_none else pdf_none}"

                r_legacy = await trd._meu_trct_doc(db, dp_user, FakeScope(LEGACY_TERM_EMP))
                assert r_legacy.get("status") == "recusado", (
                    f"FABRICAÇÃO: gerou TRCT p/ termination legada sem snapshot: {r_legacy}"
                )
                assert "arquivo_base64" not in r_legacy, "recusa não deveria conter PDF"

                # Fonte da parede: o caminho de render NÃO importa/chama funções de cálculo
                # (ignora comentários — a docstring do módulo CITA os nomes só p/ dizer que
                # NÃO os chama; o que importa é ausência de código executável real).
                src_mod = "\n".join(
                    ln for ln in inspect.getsource(trd).splitlines()
                    if not ln.strip().startswith("#")
                )
                for proibido in ("calculate_severance", "clt_calculator", "TerminationService"):
                    assert proibido not in src_mod, (
                        f"tools_rh_doc.py referencia '{proibido}' fora de comentário — "
                        "caminho de render pode recalcular"
                    )
                record(2, "sem snapshot → recusa (fake+real), sem recalc no fonte (grep calculate_severance/clt_calculator)",
                       True, f"fake sem snapshot→None; legada real→recusado ({r_legacy.get('motivo')!r}); "
                             "grep limpo")
            except Exception as exc:
                record(2, "sem snapshot → recusa, nunca recalc", False, f"{type(exc).__name__}: {exc}")

            # ════════════ ORÁCULO 3 — LGPD: self só o próprio (schema + injeção ignorada) ════════════
            try:
                for tool in trd.RH_SELF_TOOLS:
                    if tool.name == "meu_trct_doc":
                        props = tool.params_schema.get("properties", {})
                        assert "employee_id" not in props, (
                            f"LGPD: schema de meu_trct_doc EXPÕE employee_id ao LLM: {props}"
                        )
                        break
                else:
                    raise AssertionError("meu_trct_doc não encontrada em RH_SELF_TOOLS")

                # Motivo-base do scope real (legado, sem snapshot):
                r_base = await trd._meu_trct_doc(db, dp_user, FakeScope(LEGACY_TERM_EMP))
                assert r_base.get("status") == "recusado"
                motivo_base = r_base.get("motivo")

                # Injeta employee_id de alguém SEM termination nenhuma — se fosse honrado,
                # o motivo mudaria p/ "não encontrei rescisão concluída" (outra recusa).
                r_inject = await trd._meu_trct_doc(
                    db, dp_user, FakeScope(LEGACY_TERM_EMP), employee_id=NO_TERM_EMP)
                assert r_inject.get("status") == "recusado"
                assert r_inject.get("motivo") == motivo_base, (
                    f"VAZAMENTO LGPD: employee_id injetado mudou o resultado "
                    f"({motivo_base!r} -> {r_inject.get('motivo')!r})"
                )

                # sem vínculo (scope sem employee_id) → recusa fail-closed:
                r_sem = await trd._meu_trct_doc(db, dp_user, FakeScope(None))
                assert r_sem.get("status") == "recusado", f"deveria recusar sem scope.employee_id: {r_sem}"
                r_scope_none = await trd._meu_trct_doc(db, dp_user, None)
                assert r_scope_none.get("status") == "recusado", f"deveria recusar scope None: {r_scope_none}"

                record(3, "LGPD self só o próprio (schema sem employee_id; injeção ignorada; sem vínculo→recusa)",
                       True, f"injetar {NO_TERM_EMP} manteve motivo do scope ({motivo_base!r})")
            except Exception as exc:
                record(3, "LGPD self só o próprio", False, f"{type(exc).__name__}: {exc}")

            # ════════════ ORÁCULO 4 — RBAC identidade real ════════════
            try:
                from modules.ai.conversation.services.orquestrador import tool_registry as tr
                from core.auth.module_scope import CANONICAL_MODULES

                dp_tools = {t.name for t in tr.tools_for_modules({"dp"})}
                crm_tools = {t.name for t in tr.tools_for_modules({"crm"})}
                all_canon_tools = {t.name for t in tr.tools_for_modules(set(CANONICAL_MODULES))}
                assert "gerar_trct_funcionario_doc" in dp_tools, "DP não vê gerar_trct_funcionario_doc"
                assert "gerar_trct_funcionario_doc" not in crm_tools, "TRCT DP vazou p/ crm"
                assert "meu_trct_doc" not in all_canon_tools, (
                    "self tool (meu_trct_doc) apareceu em tools_for_modules de módulo canônico "
                    "(deveria ser self-tier, fora do belt)"
                )
                trd._gate(dp_user)  # dp → não levanta
                levantou = False
                try:
                    trd._gate(non_dp_user)
                except PermissionError:
                    levantou = True
                assert levantou, "_gate deveria levantar PermissionError p/ user sem dp"
                # DP: colaborador inexistente → recusa
                r_inex = await trd._gerar_trct_funcionario_doc(
                    db, dp_user, None, funcionario="ZZQX_NAO_EXISTE_9999")
                assert r_inex.get("status") == "recusado", f"deveria recusar colaborador inexistente: {r_inex}"
                record(4, "RBAC (dp vê a tool, crm não; self-tier fora do belt; _gate barra; inexistente→recusa)",
                       True, "belt+_gate ok; inexistente recusado")
            except Exception as exc:
                record(4, "RBAC identidade real", False, f"{type(exc).__name__}: {exc}")

            # ════════════ ORÁCULO 5 — aviso prévio renderiza do REGISTRO (sem verbas) ════════════
            try:
                r_aviso = await trd._meu_aviso_previo_doc(db, dp_user, FakeScope(LEGACY_TERM_EMP))
                assert r_aviso.get("status") != "recusado", f"recusou aviso prévio do registro real: {r_aviso}"
                pdf5 = base64.b64decode(r_aviso["arquivo_base64"])
                assert pdf5[:4] == b"%PDF", f"não é PDF real: {pdf5[:20]!r}"
                record(5, "aviso prévio renderiza do registro (mesma termination SEM verbas_snapshot)",
                       True, f"{len(pdf5)}B %PDF sem depender de verbas — caminho separado do TRCT")
            except Exception as exc:
                record(5, "aviso prévio renderiza do registro", False, f"{type(exc).__name__}: {exc}")

            # ════════════ ORÁCULO 6 — read-only (nada gravou) ════════════
            try:
                snap_depois = await _snapshot_db(Session)
                assert snap_depois == snap_antes, f"parede read-only furada: {snap_antes} -> {snap_depois}"
                record(6, "read-only (count termination_processes intacto)",
                       True, f"count={snap_depois['n']} inalterado")
            except Exception as exc:
                record(6, "read-only", False, f"{type(exc).__name__}: {exc}")

            # ════════ MUTAÇÃO M1 — fallback recalc quando não há snapshot (deve derrubar oráculo 2) ════════
            # Regressão simulada: sem snapshot, "recalcula" (fabrica um calc mínimo) e renderiza mesmo assim.
            original_trct_render = trd.trct_pdf_de_termination

            def _mut1_recalc_fallback(term, emp):
                from modules.people_management.hr.services.trct_pdf import montar_trct_pdf
                snap = getattr(term, "verbas_snapshot", None)
                if not snap:
                    # BUG: em vez de None, fabrica um calc "recalculado" e renderiza mesmo assim.
                    snap = dict(_SNAPSHOT_PLAUSIVEL)  # stand-in de um recalc ao vivo
                return montar_trct_pdf(
                    snap, trd._func_identidade(emp),
                    meta={"termination_id": str(getattr(term, "id", "")), "assinaturas": []},
                )

            trd.trct_pdf_de_termination = _mut1_recalc_fallback
            try:
                pdf_mut1 = trd.trct_pdf_de_termination(_fake_termination(snapshot=None), _fake_employee())
                r_legacy_mut1 = await trd._meu_trct_doc(db, dp_user, FakeScope(LEGACY_TERM_EMP))
            finally:
                trd.trct_pdf_de_termination = original_trct_render

            def _oraculo2_check_under_mutation():
                assert pdf_mut1 is None, "esperava None sem snapshot (o oráculo 2 deveria pegar isto)"
                assert r_legacy_mut1.get("status") == "recusado", (
                    "esperava recusa da termination legada (o oráculo 2 deveria pegar isto)"
                )
                assert "arquivo_base64" not in r_legacy_mut1

            m1_ok, m1_det = await _expect_bite(_oraculo2_check_under_mutation)
            record("MUTAÇÃO M1", "fallback-recalc sem snapshot (render-persistido furado) → oráculo 2", m1_ok, m1_det)

            # ════════ MUTAÇÃO M2 — self honra employee_id de argumento (deve derrubar oráculo 3) ════════
            original_meu_trct = trd._meu_trct_doc

            async def _mut2_vaza(db_, user_, scope_, *, employee_id=None, **_kw):
                # BUG: identidade vem do ARGUMENTO (LLM) quando presente, não do scope — vazamento LGPD.
                emp_id = employee_id or (getattr(scope_, "employee_id", None) if scope_ else None)
                if not emp_id:
                    return trd._recusa("sem vínculo")
                term = await trd._resolve_termination(db_, emp_id)
                if term is None:
                    return trd._recusa("não encontrei rescisão concluída pra você; não há TRCT a mostrar.")
                emp = await trd._resolve_emp(db_, emp_id)
                pdf = trd.trct_pdf_de_termination(term, emp)
                if pdf is None:
                    return trd._recusa("essa rescisão não tem registro de verbas homologadas — não recalculo nem invento.")
                return {"arquivo_base64": base64.b64encode(pdf).decode()}

            trd._meu_trct_doc = _mut2_vaza
            try:
                r_leak = await trd._meu_trct_doc(
                    db, dp_user, FakeScope(LEGACY_TERM_EMP), employee_id=NO_TERM_EMP)
            finally:
                trd._meu_trct_doc = original_meu_trct

            def _oraculo3_check_under_mutation():
                # sob a mutação, o employee_id injetado (NO_TERM_EMP, sem nenhuma termination) É
                # honrado -> motivo vira "não encontrei rescisão concluída", diferente do motivo_base
                # do scope real (legado sem snapshot). O oráculo 3 exige que o motivo NÃO mude.
                assert r_leak.get("status") == "recusado"
                assert r_leak.get("motivo") == motivo_base_ref[0], (
                    f"VAZAMENTO LGPD: employee_id injetado mudou o resultado -> {r_leak.get('motivo')!r} "
                    f"(deveria continuar {motivo_base_ref[0]!r})"
                )

            # motivo_base foi calculado dentro do try do oráculo 3 (escopo local); recalcula aqui
            # de forma independente para a checagem da mutação não depender do oráculo 3 ter passado.
            r_base_ref = await trd._meu_trct_doc(db, dp_user, FakeScope(LEGACY_TERM_EMP))
            motivo_base_ref = [r_base_ref.get("motivo")]

            m2_ok, m2_det = await _expect_bite(_oraculo3_check_under_mutation)
            record("MUTAÇÃO M2", "self honra employee_id de argumento (vazamento LGPD) → oráculo 3", m2_ok, m2_det)

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
    print(f"OK suite fase6-f10 ({n_pass}/{len(oraculos)} oráculos + {n_bite}/{len(mutacoes)} mutações) — GATE LIBERADO.")
    return 0


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    except Exception:
        traceback.print_exc()
        code = 2
    raise SystemExit(code)
