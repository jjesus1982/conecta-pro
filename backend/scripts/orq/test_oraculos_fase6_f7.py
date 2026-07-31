"""SUITE-ORÁCULO da Fase 6 Fatia 7 (espelho de ponto self + DP) — LGPD.
Prova formal, executável e MUTAÇÃO-TESTADA de que as paredes das 2 tools de espelho de
ponto (commit 5d05c1fe) seguram, e de que a suite MORDE se alguém regredir.
Molde: `test_oraculos_fase6_f6.py` (holerite — standalone, sem pytest, `sys.exit(!=0)` em
falha crítica, mutação via monkeypatch de função real). Estruturalmente IGUAL, troca
holerite→espelho.

Componente sob prova: `modules/ai/conversation/services/orquestrador/tools_rh_doc.py` —
`_meu_espelho_ponto_doc`, `_gerar_espelho_ponto_funcionario_doc`, `_espelho_render`,
`_SCHEMA_ESPELHO_SELF`, `_gate`, `_resolve_funcionario`. Reuso real: `ler_espelho`/
`montar_espelho_ponto_pdf` (people_management/hr/services) — read-only sobre `time_sheets`.

DUAS PAREDES CRÍTICAS provadas aqui:
  - LGPD: o colaborador NUNCA recebe o espelho de outro. A identidade vem SÓ de
    `scope.employee_id`; o schema self NÃO tem `employee_id` nem `funcionario`; um
    `employee_id` injetado como argumento do LLM é IGNORADO (handler o engole no **_).
  - ANTI-FABRICAÇÃO: sem `time_sheet` no período → RECUSA. Nunca inventa dias/batidas,
    nunca grava (não chama `garantir_homologacao_espelho`).

Fixtures reais (SELECT, nunca alterados) — do brief F7T2:
  SELF  = 2430761d-172e-44b8-a817-edfea166e321 (ADAILSON SERRA ALVES, matrícula 85) tem
          time_sheet em 07/2026 (status 'calculado', hours_worked_minutes=4981 -> 83:01).
  OUTRO = 6bf7804a-4976-44d2-aa3e-5bf1f25c3530 (ERIKA CRISTINA MAQUINE PEREIRA, matrícula
          137) tem time_sheet em 07/2026 com horas diferentes (4605 -> 76:45) -> alvo do leak.
  SEM_DADO = mes=1 ano=2019 — período sem nenhum time_sheet (confirmado por SELECT) -> recusa.

Os 4 oráculos:
  1. self renderiza o PRÓPRIO — PDF `%PDF`; resumo/horas == o time_sheet REAL do scope
     (83:01), não o de ninguém mais.
  2. LGPD — self só o próprio: `_SCHEMA_ESPELHO_SELF` sem `employee_id`/`funcionario`;
     injetar `employee_id=<OUTRO>` NÃO muda o resultado (continua o do SCOPE, nunca 76:45
     do outro); sem `scope.employee_id` → recusa; scope None → recusa.
  3. RBAC — `gerar_espelho_ponto_funcionario_doc` ∈ tools_for_modules({"dp"}), ∉ {"crm"};
     `meu_espelho_ponto_doc` (module="self") ∉ tools_for_modules de nenhum módulo canônico;
     `_gate(user sem dp)` levanta; DP resolve por nome real → PDF; inexistente/ambíguo →
     recusa.
  4. anti-fabricação + read-only — período sem time_sheet → RECUSA (sem arquivo_base64,
     "não invento batidas"); snapshot count(time_sheets) + count(sig_signature_requests) +
     hours_worked_minutes do SELF antes/depois: inalterados (nenhuma escrita;
     garantir_homologacao_espelho NÃO é chamado).

MUTAÇÃO-TESTE (prova que a suite morde):
  M1 (LGPD, crítica) — `_meu_espelho_ponto_doc` monkeypatchado p/ HONRAR um `employee_id`
     de argumento em vez do scope → oráculo 2 deve FALHAR (pega o vazamento de identidade).
Se a mutação certa não derrubar o oráculo certo, o oráculo é fraco.

Bancada: container THROWAWAY (imagem conecta-pro-backend) na rede
`conecta-pro_conecta-pro-network`, `DATABASE_URL` -> Postgres real (host `postgres`) —
NUNCA o backend vivo :8080. SÓ SELECT + render. A mutação é de caminho de LEITURA (nenhuma
grava) — read-only é trivialmente preservado; o oráculo 4 confirma por snapshot.
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
SELF_EMP = "2430761d-172e-44b8-a817-edfea166e321"   # ADAILSON SERRA ALVES, matrícula 85
OUTRO_EMP = "6bf7804a-4976-44d2-aa3e-5bf1f25c3530"  # ERIKA CRISTINA MAQUINE PEREIRA, matrícula 137
MES, ANO = 7, 2026
SEM_DADO = (1, 2019)  # período sem nenhum time_sheet


class FakeUser:
    """Objeto mínimo p/ exercitar `user_has_module`/`_gate` (mesmo padrão dos moldes f2/f4/f6)."""

    def __init__(self, role: str, permissions: list[str]) -> None:
        self.role = role
        self.permissions = permissions


class FakeScope:
    """Escopo self: a identidade REAL do colaborador logado (só `.employee_id`)."""

    def __init__(self, employee_id) -> None:
        self.employee_id = employee_id


def _hm(minutes) -> str:
    m = int(minutes)
    return f"{m // 60:02d}:{m % 60:02d}"


_COUNTS_SQL = text(
    "SELECT (SELECT count(*) FROM time_sheets) AS n_ts, "
    "(SELECT count(*) FROM sig_signature_requests) AS n_sig"
)
_SELF_MINUTES_SQL = text(
    "SELECT hours_worked_minutes FROM time_sheets WHERE employee_id::text=:i "
    "AND reference_month=:m AND reference_year=:y AND COALESCE(is_deleted,false)=false"
)


async def _snapshot(session_factory) -> dict:
    """count(time_sheets) + count(sig_signature_requests) + minutos do SELF, sessão NOVA."""
    async with session_factory() as s:
        row = (await s.execute(_COUNTS_SQL)).mappings().first()
        mins = (await s.execute(_SELF_MINUTES_SQL, {"i": SELF_EMP, "m": MES, "y": ANO})).scalar()
    return {"n_ts": row["n_ts"], "n_sig": row["n_sig"], "self_minutes": mins}


def _oraculo2_leak(r_inject: dict, self_horas: str, self_nome: str, outro_horas: str) -> None:
    """A injeção de `employee_id` foi IGNORADA: o resultado é do SCOPE, nunca do argumento."""
    assert r_inject.get("status") != "recusado", f"recusou o self injetado (deveria usar o scope): {r_inject}"
    assert "arquivo_base64" in r_inject, f"sem PDF no retorno self: {r_inject}"
    resumo = r_inject.get("resumo", "")
    assert self_nome.split()[0] in resumo, f"resumo não é do colaborador do SCOPE ({self_nome}): {resumo!r}"
    assert self_horas in resumo, (
        f"VAZAMENTO LGPD: horas {self_horas} do SCOPE não aparecem no resumo: {resumo!r}"
    )
    if outro_horas != self_horas:
        assert outro_horas not in resumo, (
            f"VAZAMENTO LGPD: horas do OUTRO ({outro_horas}) aparecem no resumo — renderizou o espelho alheio: {resumo!r}"
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


async def main() -> int:  # noqa: C901 (suite única e linear, como os moldes f2/f4/f6)
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
            self_min = (await db.execute(_SELF_MINUTES_SQL, {"i": SELF_EMP, "m": MES, "y": ANO})).scalar()
            outro_min = (await db.execute(text(
                "SELECT hours_worked_minutes FROM time_sheets WHERE employee_id::text=:i "
                "AND reference_month=:m AND reference_year=:y AND COALESCE(is_deleted,false)=false"
            ), {"i": OUTRO_EMP, "m": MES, "y": ANO})).scalar()
            self_nome = (await db.execute(text(
                "SELECT nome FROM employees WHERE id::text=:i"), {"i": SELF_EMP})).scalar()
            sem_dado_count = (await db.execute(text(
                "SELECT count(*) FROM time_sheets WHERE reference_month=:m AND reference_year=:y "
                "AND COALESCE(is_deleted,false)=false"
            ), {"m": SEM_DADO[0], "y": SEM_DADO[1]})).scalar()

            assert self_min is not None, f"fixture SELF sem time_sheet em {MES:02d}/{ANO} — brief desatualizado"
            assert outro_min is not None, f"fixture OUTRO sem time_sheet em {MES:02d}/{ANO} — brief desatualizado"
            assert sem_dado_count == 0, f"SEM_DADO ({SEM_DADO}) tem {sem_dado_count} time_sheet(s) — escolha outro período"
            self_horas, outro_horas = _hm(self_min), _hm(outro_min)
            assert self_horas != outro_horas, "fixtures SELF/OUTRO com as mesmas horas — leak ficaria mascarado"
            print(f"FIXTURES: self={SELF_EMP} ({self_nome!r}) horas={self_horas} | "
                  f"outro={OUTRO_EMP} horas={outro_horas} | sem_dado={SEM_DADO}")

            snap_antes = await _snapshot(Session)

            # ════════════ ORÁCULO 1 — self renderiza o PRÓPRIO ════════════
            try:
                r1 = await trd._meu_espelho_ponto_doc(db, self_user, FakeScope(SELF_EMP), mes=MES, ano=ANO)
                assert r1.get("status") != "recusado", f"recusou o espelho real do self: {r1}"
                pdf1 = base64.b64decode(r1["arquivo_base64"])
                assert pdf1[:4] == b"%PDF", f"não é PDF real (gerador branded): {pdf1[:20]!r}"
                resumo1 = r1.get("resumo", "")
                assert self_horas in resumo1, f"resumo não traz as horas reais do self ({self_horas}): {resumo1!r}"
                assert self_nome.split()[0] in resumo1, f"resumo não é do self ({self_nome}): {resumo1!r}"
                record(1, "self renderiza o próprio espelho (PDF + horas == time_sheet real do scope)",
                       True, f"{len(pdf1)}B %PDF, horas={self_horas}")
            except Exception as exc:
                record(1, "self renderiza o próprio", False, f"{type(exc).__name__}: {exc}")

            # ════════════ ORÁCULO 2 — LGPD: self só o próprio (schema + injeção ignorada) ════════════
            try:
                props = trd._SCHEMA_ESPELHO_SELF.get("properties", {})
                assert "employee_id" not in props, (
                    f"LGPD: _SCHEMA_ESPELHO_SELF EXPÕE employee_id ao LLM — o modelo poderia escolher de quem: {props}"
                )
                assert "funcionario" not in props, (
                    f"LGPD: _SCHEMA_ESPELHO_SELF EXPÕE funcionario ao LLM — o modelo poderia escolher de quem: {props}"
                )
                # employee_id injetado como kwarg (simula o LLM tentando escolher a vítima):
                r_inject = await trd._meu_espelho_ponto_doc(
                    db, self_user, FakeScope(SELF_EMP), employee_id=OUTRO_EMP, mes=MES, ano=ANO)
                _oraculo2_leak(r_inject, self_horas, self_nome, outro_horas)
                # sem vínculo (scope sem employee_id) → recusa fail-closed:
                r_sem = await trd._meu_espelho_ponto_doc(db, self_user, FakeScope(None), mes=MES, ano=ANO)
                assert r_sem.get("status") == "recusado", f"deveria recusar sem scope.employee_id: {r_sem}"
                assert "arquivo_base64" not in r_sem, "recusa não deveria conter PDF"
                r_scope_none = await trd._meu_espelho_ponto_doc(db, self_user, None, mes=MES, ano=ANO)
                assert r_scope_none.get("status") == "recusado", f"deveria recusar scope None: {r_scope_none}"
                record(2, "LGPD self só o próprio (schema sem employee_id/funcionario; injeção ignorada; sem vínculo→recusa)",
                       True, f"injetar outro={OUTRO_EMP} manteve horas={self_horas} do scope; sem-vínculo recusado")
            except Exception as exc:
                record(2, "LGPD self só o próprio", False, f"{type(exc).__name__}: {exc}")

            # ════════════ ORÁCULO 3 — RBAC identidade real ════════════
            try:
                from modules.ai.conversation.services.orquestrador import tool_registry as tr
                from core.auth.module_scope import CANONICAL_MODULES

                dp_tools = {t.name for t in tr.tools_for_modules({"dp"})}
                crm_tools = {t.name for t in tr.tools_for_modules({"crm"})}
                all_canon_tools = {t.name for t in tr.tools_for_modules(set(CANONICAL_MODULES))}
                assert "gerar_espelho_ponto_funcionario_doc" in dp_tools, "DP não vê gerar_espelho_ponto_funcionario_doc"
                assert "gerar_espelho_ponto_funcionario_doc" not in crm_tools, "espelho DP vazou p/ crm"
                assert "meu_espelho_ponto_doc" not in all_canon_tools, (
                    "self tool (meu_espelho_ponto_doc) apareceu em tools_for_modules de módulo canônico "
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
                r_dp = await trd._gerar_espelho_ponto_funcionario_doc(
                    db, self_user, None, funcionario=self_nome, mes=MES, ano=ANO)
                assert r_dp.get("status") != "recusado", f"DP recusou nome real ({self_nome}): {r_dp}"
                assert base64.b64decode(r_dp["arquivo_base64"])[:4] == b"%PDF", "DP não gerou PDF real"
                # inexistente → recusa:
                r_inex = await trd._gerar_espelho_ponto_funcionario_doc(
                    db, self_user, None, funcionario="ZZQX_NAO_EXISTE_9999", mes=MES, ano=ANO)
                assert r_inex.get("status") == "recusado", f"deveria recusar colaborador inexistente: {r_inex}"
                # ambíguo (substring que casa >1) → recusa:
                r_amb = await trd._gerar_espelho_ponto_funcionario_doc(
                    db, self_user, None, funcionario="a", mes=MES, ano=ANO)
                assert r_amb.get("status") == "recusado", f"deveria recusar termo ambíguo: {r_amb}"
                assert "arquivo_base64" not in r_amb, "recusa ambígua não deveria conter PDF"
                record(3, "RBAC (dp vê a tool, crm não; self-tier fora do belt; _gate barra; inexistente/ambíguo→recusa)",
                       True, "belt+_gate ok; DP gera por nome real; inexistente e ambíguo recusados")
            except Exception as exc:
                record(3, "RBAC identidade real", False, f"{type(exc).__name__}: {exc}")

            # ════════════ ORÁCULO 4 — anti-fabricação + read-only ════════════
            try:
                sem_mes, sem_ano = SEM_DADO
                r4 = await trd._meu_espelho_ponto_doc(db, self_user, FakeScope(SELF_EMP), mes=sem_mes, ano=sem_ano)
                assert r4.get("status") == "recusado", (
                    f"FABRICAÇÃO: gerou espelho sem time_sheet no período {sem_mes:02d}/{sem_ano}: {r4}"
                )
                assert "arquivo_base64" not in r4, "recusa por falta de dado NÃO deveria conter PDF"
                # e _espelho_render direto no período vazio também retorna None (a fonte da parede):
                res_none = await asyncio.to_thread(trd._espelho_render, SELF_EMP, sem_mes, sem_ano)
                assert res_none is None, f"_espelho_render aceitou período sem time_sheet: {res_none}"
                snap_depois = await _snapshot(Session)
                assert snap_depois == snap_antes, (
                    f"parede read-only furada (nenhuma escrita esperada, garantir_homologacao NÃO chamado): "
                    f"{snap_antes} -> {snap_depois}"
                )
                record(4, "anti-fabricação (sem time_sheet→recusa, sem PDF) + read-only (time_sheets/sig_requests/minutos intactos)",
                       True, f"{sem_mes:02d}/{sem_ano} sem dado → recusa; snapshot={snap_depois} inalterado")
            except Exception as exc:
                record(4, "anti-fabricação + read-only", False, f"{type(exc).__name__}: {exc}")

            # ════════ MUTAÇÃO M1 — self vaza por argumento (deve derrubar oráculo 2) ════════
            # Regressão simulada: o handler HONRA um employee_id de argumento em vez do scope.
            original_meu = trd._meu_espelho_ponto_doc

            async def _mut1_vaza(db_, user_, scope_, *, mes=None, ano=None, employee_id=None, **_kw):
                # BUG: identidade vem do ARGUMENTO (LLM) e não do scope — vazamento LGPD.
                emp_id = employee_id or (getattr(scope_, "employee_id", None) if scope_ else None)
                if not emp_id:
                    return trd._recusa("sem vínculo")
                m, a = trd._norm_mes_ano(mes, ano)
                res = await asyncio.to_thread(trd._espelho_render, str(emp_id), m, a)
                if res is None:
                    return trd._recusa("sem registro de ponto")
                esp, pdf = res
                return trd._resposta_espelho(esp, pdf, "")

            trd._meu_espelho_ponto_doc = _mut1_vaza
            try:
                r_leak = await trd._meu_espelho_ponto_doc(
                    db, self_user, FakeScope(SELF_EMP), employee_id=OUTRO_EMP, mes=MES, ano=ANO)
            finally:
                trd._meu_espelho_ponto_doc = original_meu
            m1_ok, m1_det = await _expect_bite(
                lambda: _oraculo2_leak(r_leak, self_horas, self_nome, outro_horas))
            record("MUTAÇÃO M1", "self honra employee_id de argumento (vazamento LGPD) → oráculo 2", m1_ok, m1_det)

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
    print(f"OK suite fase6-f7 ({n_pass}/{len(oraculos)} oráculos + {n_bite}/{len(mutacoes)} mutações) — GATE LIBERADO.")
    return 0


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    except Exception:
        traceback.print_exc()
        code = 2
    raise SystemExit(code)
