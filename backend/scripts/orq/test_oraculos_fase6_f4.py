"""SUITE-ORÁCULO da Fase 6 Fatia 4 (relatório de visita render) — prova formal,
executável e MUTAÇÃO-TESTADA de que as paredes da tool `gerar_relatorio_visita_doc`
(commit 2c6d2a77) seguram, e de que a suite MORDE se alguém regredir.
Molde: `test_oraculos_fase6_f2.py` (standalone, sem pytest, `sys.exit(!=0)` em
falha crítica, mutação via monkeypatch de função real, restauração com resíduo zero).

Componente sob prova: `modules/ai/conversation/services/orquestrador/
tools_operacional_doc.py` — `_gerar_relatorio_visita_doc`/`_resolve_visita`/`_gate`.
Reuso real: `VisitaService.obter_visita`/`obter_visita_por_numero`,
`visita_to_pdf_dict`, `build_visit_report_pdf`. Tabela real = `visitas`.

Os 3 oráculos:
  1. Render de real — `_gerar_relatorio_visita_doc` c/ visita_id de uma Visita
     REAL → PDF (`%PDF`); resolve pelo mesmo registro via visita_numero também.
     visita_id malformado/inexistente/vazio → `{"status":"recusado"}` sem
     `arquivo_base64`.
  2. NÃO grava no banco (parede central: operacional é READ-ONLY p/ agentes) —
     contagem de linhas de `visitas` + colunas estáveis (`numero`, `updated_at`)
     da visita alvo, lidas numa sessão NOVA antes/depois de rodar a tool: nada
     muda.
  3. RBAC identidade real — a tool ∈ `tools_for_modules({"operacional"})` e
     ∉ `tools_for_modules({"crm"})`; `_gate(user_sem_operacional)` levanta
     `PermissionError`.

MUTAÇÃO-TESTE (prova que a suite morde):
  M1 — visita persiste: handler monkeypatchado faz um UPDATE real (coluna
       mapeada `descricao_atendimento`) + `commit()` (simula uma regressão que
       grava) → oráculo 2 deve FALHAR. Restaurado por UPDATE explícito
       (descricao_atendimento + updated_at) logo em seguida — 0 resíduo,
       verificado por um snapshot final.
Se a mutação não derrubar o oráculo, o oráculo é fraco.

Bancada: container THROWAWAY (imagem conecta-pro-backend) anexado à rede
`conecta-pro_conecta-pro-network`, `DATABASE_URL` apontando pro Postgres real
via nome do container (`conecta-pro-postgres`) — NUNCA o backend vivo :8080.
Só SELECT p/ escolher a Visita (nenhuma criada/apagada). A ÚNICA escrita real
é a do M1 (proposital, pra provar a parede) — sempre revertida no próprio
teste, com verificação de resíduo zero.
Se não existir Visita real, oráculos 1/2 e a mutação M1 são PULADOS com aviso
claro (nunca inventa visita) — 3 não depende dela.
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
    """Objeto mínimo p/ exercitar `user_has_module`/`_gate` sem depender de
    sessão HTTP (mesmo padrão do molde f2)."""

    def __init__(self, role: str, permissions: list[str]) -> None:
        self.role = role
        self.permissions = permissions


_MUT_MARKER = "MUTATION-PROBE-F4T2-DO-NOT-KEEP"

_SNAPSHOT_SQL = text("SELECT numero, updated_at, descricao_atendimento FROM visitas WHERE id = :id")
_COUNTS_SQL = text("SELECT count(*) AS n_visitas FROM visitas")


async def _snapshot(session_factory, visita_id: str) -> dict:
    """Estado observável da visita-alvo + contagem global, numa sessão NOVA
    (nunca a mesma usada pelo handler sob teste — sem cache de identity map)."""
    async with session_factory() as s:
        row = (await s.execute(_SNAPSHOT_SQL, {"id": visita_id})).mappings().first()
        counts = (await s.execute(_COUNTS_SQL)).mappings().first()
    return {**dict(row), **dict(counts)}


def _assert_no_change(before: dict, after: dict) -> None:
    diffs = {k: (before[k], after[k]) for k in before if before[k] != after.get(k)}
    assert not diffs, f"visita/tabela mudaram (parede no-DB-write furada): {diffs}"


async def _oraculo_2_no_write(gerar_fn, db, user, session_factory, visita_id: str) -> None:
    antes = await _snapshot(session_factory, visita_id)
    r = await gerar_fn(db, user, None, visita_id=visita_id)
    assert r.get("status") != "recusado", f"recusou inesperadamente: {r}"
    depois = await _snapshot(session_factory, visita_id)
    _assert_no_change(antes, depois)


def _oraculo_4_rbac(tod_mod, op_user, non_op_user) -> None:
    from modules.ai.conversation.services.orquestrador import tool_registry as tr

    op_tools = {t.name for t in tr.tools_for_modules({"operacional"})}
    crm_tools = {t.name for t in tr.tools_for_modules({"crm"})}
    nome = "gerar_relatorio_visita_doc"
    assert nome in op_tools, f"{nome} não aparece em tools_for_modules({{'operacional'}})"
    assert nome not in crm_tools, f"{nome} vazou p/ tools_for_modules({{'crm'}})"
    tod_mod._gate(op_user)  # não deve levantar
    levantou = False
    try:
        tod_mod._gate(non_op_user)
    except PermissionError:
        levantou = True
    assert levantou, "_gate deveria levantar PermissionError p/ user sem módulo operacional"


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


async def main() -> int:  # noqa: C901 (suite única e linear, como o molde f2)
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
                tools_operacional_doc as tod,  # noqa: F401 — import registra a ToolDef
            )

            op_user = FakeUser("operator", ["module:operacional"])
            non_op_user = FakeUser("operator", ["module:crm"])

            # ── ORÁCULO 3 (RBAC) não depende de visita ──────────────────────
            try:
                _oraculo_4_rbac(tod, op_user, non_op_user)
                record(3, "RBAC identidade real (belt tools_for_modules + suspenders _gate)",
                       True, "operacional vê a tool, crm não vê; _gate barra user sem operacional")
            except Exception as exc:
                record(3, "RBAC identidade real", False, f"{type(exc).__name__}: {exc}")

            # ── Visita REAL p/ oráculos 1-2 (SELECT, nunca cria/apaga) ──────
            visita_row = (await db.execute(text(
                "SELECT id::text AS id, numero FROM visitas ORDER BY created_at LIMIT 1"
            ))).mappings().first()

            if visita_row is None:
                aviso = "NENHUMA visita real no banco — oráculos 1-2 e mutação M1 PULADOS."
                print(f"\nAVISO: {aviso}")
                for n in (1, 2):
                    record(n, "PULADO (sem visita real)", True, aviso)
                record("MUTAÇÃO M1", "visita persiste → oráculo 2", True, "PULADA (sem visita real)")
            else:
                visita_id = visita_row["id"]
                numero_real = visita_row["numero"]

                # ════════════ ORÁCULO 1 — RENDER DE REAL ════════════
                try:
                    r1 = await tod._gerar_relatorio_visita_doc(db, op_user, None, visita_id=visita_id)
                    assert r1.get("status") != "recusado", f"recusou visita real existente: {r1}"
                    pdf1 = base64.b64decode(r1["arquivo_base64"])
                    assert pdf1[:4] == b"%PDF", f"não é PDF real: {pdf1[:20]!r}"

                    r_por_numero = await tod._gerar_relatorio_visita_doc(
                        db, op_user, None, visita_numero=numero_real)
                    assert r_por_numero.get("status") != "recusado", (
                        f"recusou resolução por número real ({numero_real}): {r_por_numero}"
                    )
                    pdf_num = base64.b64decode(r_por_numero["arquivo_base64"])
                    assert pdf_num[:4] == b"%PDF", "resolução por número não é PDF real"

                    r_malformado = await tod._gerar_relatorio_visita_doc(
                        db, op_user, None, visita_id="not-a-uuid")
                    assert r_malformado.get("status") == "recusado", f"deveria recusar UUID malformado: {r_malformado}"
                    assert "arquivo_base64" not in r_malformado, "recusa não deveria conter PDF"

                    r_inexistente = await tod._gerar_relatorio_visita_doc(
                        db, op_user, None, visita_id=str(uuid.uuid4()))
                    assert r_inexistente.get("status") == "recusado", f"deveria recusar visita inexistente: {r_inexistente}"
                    assert "arquivo_base64" not in r_inexistente, "recusa não deveria conter PDF"

                    r_vazio = await tod._gerar_relatorio_visita_doc(db, op_user, None)
                    assert r_vazio.get("status") == "recusado", f"deveria recusar sem id/número: {r_vazio}"
                    assert "arquivo_base64" not in r_vazio, "recusa não deveria conter PDF"

                    record(1, "render de visita real (PDF por id e por número) + fail-closed",
                           True, f"{len(pdf1)}B %PDF (id) e {len(pdf_num)}B %PDF (número={numero_real}); "
                                 "malformado/inexistente/vazio recusados")
                except Exception as exc:
                    record(1, "render de visita real", False, f"{type(exc).__name__}: {exc}")

                # ════════════ ORÁCULO 2 — NÃO GRAVA NO BANCO ════════════
                try:
                    await _oraculo_2_no_write(tod._gerar_relatorio_visita_doc, db, op_user, Session, visita_id)
                    record(2, "visita NÃO grava no banco (contagem + numero/updated_at intactos)",
                           True, "count(visitas) e numero/updated_at da visita-alvo intactos")
                except Exception as exc:
                    record(2, "visita não grava no banco", False, f"{type(exc).__name__}: {exc}")

                # ════════ MUTAÇÃO M1 — persistência real (deve derrubar oráculo 2) ════
                original_gerar_visita = tod._gerar_relatorio_visita_doc
                antes_m1 = await _snapshot(Session, visita_id)
                residuo_ok = False
                depois_restaurado = None

                async def _mut1_persiste(db_, user_, scope_, *, visita_id=None, visita_numero=None, **_kw):
                    tod._gate(user_)
                    v = await tod._resolve_visita(db_, visita_id=visita_id, visita_numero=visita_numero)
                    if v is None:
                        return tod._recusa("não encontrada")
                    # MUTAÇÃO: regressão que grava de verdade (coluna mapeada real, não transiente)
                    v.descricao_atendimento = _MUT_MARKER
                    await db_.commit()
                    from modules.crm.services.doc_pdf import build_visit_report_pdf
                    from modules.campo.services.visita_service import visita_to_pdf_dict
                    pdf = build_visit_report_pdf(visita_to_pdf_dict(v))
                    return {"arquivo_base64": base64.b64encode(pdf).decode(),
                            "nome": "x.pdf", "resumo": f"Visita {numero_real} — mutada"}

                m1_ok, m1_det = False, "erro inesperado antes de avaliar a mutação"
                tod._gerar_relatorio_visita_doc = _mut1_persiste
                try:
                    try:
                        await tod._gerar_relatorio_visita_doc(db, op_user, None, visita_id=visita_id)
                    finally:
                        tod._gerar_relatorio_visita_doc = original_gerar_visita

                    depois_m1 = await _snapshot(Session, visita_id)
                    m1_ok, m1_det = await _expect_bite(lambda: _assert_no_change(antes_m1, depois_m1))
                except Exception as exc:  # noqa: BLE001 — nunca deixar a restauração de rodar
                    m1_det = f"ERRO inesperado rodando mutação M1: {type(exc).__name__}: {exc}"
                finally:
                    # ── RESTAURA + verifica resíduo ZERO, sempre, mesmo se a asserção acima falhar ──
                    async with Session() as srestore:
                        await srestore.execute(
                            text("UPDATE visitas SET descricao_atendimento = :d, updated_at = :u WHERE id = :id"),
                            {"d": antes_m1["descricao_atendimento"], "u": antes_m1["updated_at"], "id": visita_id},
                        )
                        await srestore.commit()
                    depois_restaurado = await _snapshot(Session, visita_id)
                    residuo_ok = depois_restaurado == antes_m1

                record("MUTAÇÃO M1", "visita persiste (UPDATE real + commit) → oráculo 2", m1_ok, m1_det)
                if not residuo_ok:
                    print("CRÍTICO: resíduo detectado no banco real após M1 — restauração NÃO bateu com o snapshot original!")
                record("RESÍDUO M1", "restauração pós-mutação bate 100% com o snapshot original", residuo_ok,
                       "descricao_atendimento/updated_at/contagem idênticos ao estado pré-teste" if residuo_ok
                       else f"antes={antes_m1} depois={depois_restaurado}")

        finally:
            await db.rollback()  # nenhuma transação pendurada (M1 já fez commit+restore próprios)

    await eng.dispose()

    # ══════════════ RESUMO ══════════════
    oraculos = [r for r in results if isinstance(r[0], int)]
    mutacoes = [r for r in results if isinstance(r[0], str) and r[0].startswith("MUTAÇÃO")]
    extras = [r for r in results if isinstance(r[0], str) and not r[0].startswith("MUTAÇÃO")]
    n_pass = sum(1 for r in oraculos if r[2])
    n_bite = sum(1 for r in mutacoes if r[2])
    print("\n" + "═" * 68)
    print(f"RESUMO: {n_pass}/{len(oraculos)} oráculos PASS  |  "
          f"{n_bite}/{len(mutacoes)} mutações MORDERAM")
    falhas = [r for r in results if not r[2]]
    if falhas:
        print("FALHAS (findings — é a parede quebrando ou resíduo no banco, NÃO ajustar o teste):")
        for n, desc, _ok, det in falhas:
            print(f"  ✗ {n} {desc} — {det}")
        print("═" * 68)
        print("GATE: BLOQUEADO.")
        return 1
    print("═" * 68)
    print(f"OK suite fase6-f4 ({n_pass}/{len(oraculos)} oráculos + {n_bite}/{len(mutacoes)} mutações"
          f"{' + ' + str(len(extras)) + ' resíduo' if extras else ''}) — GATE LIBERADO.")
    return 0


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    except Exception:
        traceback.print_exc()
        code = 2
    raise SystemExit(code)
