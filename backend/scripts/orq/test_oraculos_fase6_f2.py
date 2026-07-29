"""SUITE-ORÁCULO da Fase 6 Fatia 2 (contrato render + relatório comercial) —
prova formal, executável e MUTAÇÃO-TESTADA de que as paredes das 2 tools
(commit 6750206f) seguram, e de que a suite MORDE se alguém regredir.
Molde: `test_oraculos_fase6_f1.py` (standalone, sem pytest, `sys.exit(!=0)`
em falha crítica, mutação via monkeypatch de função/módulo real).

Componente sob prova: `modules/ai/conversation/services/orquestrador/
tools_comercial_doc.py` — `_gerar_contrato_doc`/`_resolve_contrato` e
`_gerar_relatorio_comercial_doc`. Reuso real: `ContractRepository`,
`build_contract_pdf`, `orchestration.relatorio_comercial_ctx`,
`build_commercial_report_pdf`.

Os 4 oráculos:
  1. Contrato render de real — `_gerar_contrato_doc` c/ contrato_id de um
     Contract REAL ativo → PDF (`%PDF`) e `resumo` cita o `contract_number`
     real. contrato_id malformado/inexistente → `{"status":"recusado"}` sem
     `arquivo_base64`.
  2. Contrato NÃO grava no banco (parede central) — contagem de linhas de
     `contracts`/`clients` e os valores (`description`, `updated_at`, ...)
     do Contract alvo, lidos numa sessão NOVA antes/depois de rodar
     `_gerar_contrato_doc` (que faz o enrich client_name/document, atributo
     transiente): nada muda.
  3. Relatório = interno, dado real, rotulado não-cliente — PDF não-vazio;
     o `resumo` embute os MESMOS números de `await relatorio_comercial_ctx(db)`
     chamado independente (prova reuso do helper real, não hardcode) e traz
     marcador "CONFIDENCIAL".
  4. RBAC identidade real — as 2 tools ∈ `tools_for_modules({"crm"})` e ∉
     `tools_for_modules({"dp"})`; `_gate(user_sem_crm)` levanta
     `PermissionError`.

MUTAÇÃO-TESTE (prova que a suite morde):
  M1 — contrato persiste: handler monkeypatchado faz um UPDATE real (coluna
       mapeada `description`) + `commit()` depois do enrich (simula uma
       regressão que grava) → oráculo 2 deve FALHAR. Restaurado por UPDATE
       explícito (description + updated_at) logo em seguida — 0 resíduo,
       verificado por um snapshot final.
  M2 — relatório hardcoded: `orchestration.relatorio_comercial_ctx`
       monkeypatchado devolve números fixos diferentes dos reais → oráculo 3
       deve FALHAR (prova que o oráculo casa contra o helper real).
Se a mutação certa não derrubar o oráculo certo, o oráculo é fraco.

Bancada: container THROWAWAY (imagem conecta-pro-backend) anexado à rede
`conecta-pro_conecta-pro-network`, `DATABASE_URL` apontando pro Postgres real
via nome do container (`conecta-pro-postgres`) — NUNCA o backend vivo :8080.
Só SELECT p/ escolher o Contract (nenhum criado/apagado). A ÚNICA escrita
real é a do M1 (proposital, pra provar a parede) — sempre revertida no
próprio teste, com verificação de resíduo zero.
Se não existir Contract ativo real, oráculos 1/2 e a mutação M1 são
PULADOS com aviso claro (nunca inventa contrato) — 3 e 4 não dependem dele.
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
    sessão HTTP (mesmo padrão do molde f1)."""

    def __init__(self, role: str, permissions: list[str]) -> None:
        self.role = role
        self.permissions = permissions


_MUT_MARKER = "MUTATION-PROBE-F2T2-DO-NOT-KEEP"

_SNAPSHOT_SQL = text(
    "SELECT description, updated_at, name, monthly_value, total_value, contract_number "
    "FROM contracts WHERE id = :id"
)
_COUNTS_SQL = text(
    "SELECT (SELECT count(*) FROM contracts) AS n_contracts, "
    "(SELECT count(*) FROM clients) AS n_clients"
)


async def _snapshot(session_factory, contrato_id: str) -> dict:
    """Estado observável do contrato-alvo + contagens globais, numa sessão NOVA
    (nunca a mesma usada pelo handler sob teste — sem cache de identity map)."""
    async with session_factory() as s:
        row = (await s.execute(_SNAPSHOT_SQL, {"id": contrato_id})).mappings().first()
        counts = (await s.execute(_COUNTS_SQL)).mappings().first()
    return {**dict(row), **dict(counts)}


def _assert_no_change(before: dict, after: dict) -> None:
    diffs = {k: (before[k], after[k]) for k in before if before[k] != after.get(k)}
    assert not diffs, f"contrato/tabelas mudaram (parede no-DB-write furada): {diffs}"


async def _oraculo_2_no_write(gerar_fn, db, user, session_factory, contrato_id: str) -> None:
    antes = await _snapshot(session_factory, contrato_id)
    r = await gerar_fn(db, user, None, contrato_id=contrato_id)
    assert r.get("status") != "recusado", f"recusou inesperadamente: {r}"
    depois = await _snapshot(session_factory, contrato_id)
    _assert_no_change(antes, depois)


def _oraculo_3_relatorio_ctx(tcd_mod, resultado: dict, ctx_real: dict) -> None:
    assert resultado.get("status") != "recusado", f"recusou inesperadamente: {resultado}"
    assert "arquivo_base64" in resultado, f"sem PDF no retorno: {resultado}"
    pdf = base64.b64decode(resultado["arquivo_base64"])
    assert pdf[:4] == b"%PDF" and len(pdf) > 100, "não é PDF real (gerador branded)"
    resumo = resultado.get("resumo", "")
    assert "CONFIDENCIAL" in resumo, f"resumo sem rótulo de confidencial/interno: {resumo}"
    for chave in ("mrr", "pipeline_aberto"):
        marcador = tcd_mod._brl(float(ctx_real[chave]))
        assert marcador in resumo, (
            f"resumo não bate com relatorio_comercial_ctx real p/ {chave} "
            f"({marcador!r} ausente) — indício de número hardcoded: {resumo}"
        )
    assert str(ctx_real["clientes"]) in resumo, (
        f"resumo não bate com contagem real de clientes ({ctx_real['clientes']}): {resumo}"
    )


def _oraculo_4_rbac(tcd_mod, crm_user, non_crm_user) -> None:
    from modules.ai.conversation.services.orquestrador import tool_registry as tr

    crm_tools = {t.name for t in tr.tools_for_modules({"crm"})}
    dp_tools = {t.name for t in tr.tools_for_modules({"dp"})}
    for nome in ("gerar_contrato_doc", "gerar_relatorio_comercial_doc"):
        assert nome in crm_tools, f"{nome} não aparece em tools_for_modules({{'crm'}})"
        assert nome not in dp_tools, f"{nome} vazou p/ tools_for_modules({{'dp'}})"
    tcd_mod._gate(crm_user)  # não deve levantar
    levantou = False
    try:
        tcd_mod._gate(non_crm_user)
    except PermissionError:
        levantou = True
    assert levantou, "_gate deveria levantar PermissionError p/ user sem módulo crm"


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


async def main() -> int:  # noqa: C901 (suite única e linear, como o molde f1)
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
                tools_comercial_doc as tcd,  # noqa: F401 — import registra as ToolDefs
            )
            from modules.crm.services import orchestration

            crm_user = FakeUser("operator", ["module:crm"])
            non_crm_user = FakeUser("operator", ["module:dp"])

            # ── ORÁCULO 4 (RBAC) não depende de contrato ────────────────────
            try:
                _oraculo_4_rbac(tcd, crm_user, non_crm_user)
                record(4, "RBAC identidade real (belt tools_for_modules + suspenders _gate)",
                       True, "crm vê as 2 tools, dp não vê; _gate barra user sem crm")
            except Exception as exc:
                record(4, "RBAC identidade real", False, f"{type(exc).__name__}: {exc}")

            # ── ORÁCULO 3 (relatório) não depende de contrato ───────────────
            ctx_real = None
            try:
                ctx_real = await orchestration.relatorio_comercial_ctx(db)
                r_rel = await tcd._gerar_relatorio_comercial_doc(db, crm_user, None)
                _oraculo_3_relatorio_ctx(tcd, r_rel, ctx_real)
                record(3, "relatório interno = dado real do helper (rotulado CONFIDENCIAL)",
                       True, f"mrr={tcd._brl(float(ctx_real['mrr']))} clientes={ctx_real['clientes']} "
                             f"pipeline={tcd._brl(float(ctx_real['pipeline_aberto']))}")
            except Exception as exc:
                record(3, "relatório interno = dado real", False, f"{type(exc).__name__}: {exc}")

            # ── Contract REAL ativo p/ oráculos 1-2 (SELECT, nunca cria/apaga) ──
            contrato_row = (await db.execute(text(
                "SELECT id::text AS id, contract_number FROM contracts "
                "WHERE is_active = true ORDER BY created_at LIMIT 1"
            ))).mappings().first()

            if contrato_row is None:
                aviso = "NENHUM contrato ativo real no banco — oráculos 1-2 e mutação M1 PULADOS."
                print(f"\nAVISO: {aviso}")
                for n in (1, 2):
                    record(n, "PULADO (sem contrato real)", True, aviso)
                record("MUTAÇÃO M1", "contrato persiste → oráculo 2", True, "PULADA (sem contrato real)")
            else:
                contrato_id = contrato_row["id"]
                numero_real = contrato_row["contract_number"]

                # ════════════ ORÁCULO 1 — RENDER DE REAL ════════════
                try:
                    r1 = await tcd._gerar_contrato_doc(db, crm_user, None, contrato_id=contrato_id)
                    assert r1.get("status") != "recusado", f"recusou contrato real existente: {r1}"
                    pdf1 = base64.b64decode(r1["arquivo_base64"])
                    assert pdf1[:4] == b"%PDF", f"não é PDF real: {pdf1[:20]!r}"
                    assert numero_real in r1.get("resumo", ""), (
                        f"resumo não cita o contract_number real ({numero_real}): {r1.get('resumo')}"
                    )

                    r_malformado = await tcd._gerar_contrato_doc(db, crm_user, None, contrato_id="not-a-uuid")
                    assert r_malformado.get("status") == "recusado", f"deveria recusar UUID malformado: {r_malformado}"
                    assert "arquivo_base64" not in r_malformado, "recusa não deveria conter PDF"

                    r_inexistente = await tcd._gerar_contrato_doc(
                        db, crm_user, None, contrato_id=str(uuid.uuid4()))
                    assert r_inexistente.get("status") == "recusado", f"deveria recusar contrato inexistente: {r_inexistente}"
                    assert "arquivo_base64" not in r_inexistente, "recusa não deveria conter PDF"

                    record(1, "render de contrato real (PDF + resumo com contract_number) + fail-closed",
                           True, f"{len(pdf1)}B %PDF, resumo cita {numero_real}; malformado/inexistente recusados")
                except Exception as exc:
                    record(1, "render de contrato real", False, f"{type(exc).__name__}: {exc}")

                # ════════════ ORÁCULO 2 — NÃO GRAVA NO BANCO ════════════
                try:
                    await _oraculo_2_no_write(tcd._gerar_contrato_doc, db, crm_user, Session, contrato_id)
                    record(2, "contrato NÃO grava no banco (contagens + colunas intactas)",
                           True, "contracts/clients count e description/updated_at do contrato intactos")
                except Exception as exc:
                    record(2, "contrato não grava no banco", False, f"{type(exc).__name__}: {exc}")

                # ════════ MUTAÇÃO M1 — persistência real (deve derrubar oráculo 2) ════
                original_gerar_contrato = tcd._gerar_contrato_doc
                antes_m1 = await _snapshot(Session, contrato_id)
                residuo_ok = False

                async def _mut1_persiste(db_, user_, scope_, *, contrato_id=None, contrato_numero=None, **_kw):
                    tcd._gate(user_)
                    c = await tcd._resolve_contrato(db_, contrato_id=contrato_id, contrato_numero=contrato_numero)
                    if c is None:
                        return tcd._recusa("não encontrado")
                    from sqlalchemy import select as _select

                    from modules.clients.models import Client
                    cli = (await db_.execute(_select(Client).where(Client.id == c.client_id))).scalars().first()
                    if cli is not None:
                        c.client_name = cli.name
                        c.client_document = cli.document_number
                    # MUTAÇÃO: regressão que grava de verdade (coluna mapeada real, não transiente)
                    c.description = _MUT_MARKER
                    await db_.commit()
                    from modules.crm.services.contract_pdf import build_contract_pdf
                    pdf = build_contract_pdf(c)
                    return {"arquivo_base64": base64.b64encode(pdf).decode(),
                            "nome": "x.pdf", "resumo": f"Contrato {numero_real} — mutado"}

                m1_ok, m1_det = False, "erro inesperado antes de avaliar a mutação"
                tcd._gerar_contrato_doc = _mut1_persiste
                try:
                    try:
                        await tcd._gerar_contrato_doc(db, crm_user, None, contrato_id=contrato_id)
                    finally:
                        tcd._gerar_contrato_doc = original_gerar_contrato

                    depois_m1 = await _snapshot(Session, contrato_id)
                    m1_ok, m1_det = await _expect_bite(lambda: _assert_no_change(antes_m1, depois_m1))
                except Exception as exc:  # noqa: BLE001 — nunca deixar a restauração de rodar
                    m1_det = f"ERRO inesperado rodando mutação M1: {type(exc).__name__}: {exc}"
                finally:
                    # ── RESTAURA + verifica resíduo ZERO, sempre, mesmo se a asserção acima falhar ──
                    async with Session() as srestore:
                        await srestore.execute(
                            text("UPDATE contracts SET description = :d, updated_at = :u WHERE id = :id"),
                            {"d": antes_m1["description"], "u": antes_m1["updated_at"], "id": contrato_id},
                        )
                        await srestore.commit()
                    depois_restaurado = await _snapshot(Session, contrato_id)
                    residuo_ok = depois_restaurado == antes_m1

                record("MUTAÇÃO M1", "contrato persiste (UPDATE real + commit) → oráculo 2", m1_ok, m1_det)
                if not residuo_ok:
                    print("CRÍTICO: resíduo detectado no banco real após M1 — restauração NÃO bateu com o snapshot original!")
                record("RESÍDUO M1", "restauração pós-mutação bate 100% com o snapshot original", residuo_ok,
                       "description/updated_at/contagens idênticos ao estado pré-teste" if residuo_ok
                       else f"antes={antes_m1} depois={depois_restaurado}")

            # ════════ MUTAÇÃO M2 — relatório hardcoded (deve derrubar oráculo 3) ════
            if ctx_real is not None:
                original_ctx_fn = orchestration.relatorio_comercial_ctx

                async def _mut2_ctx_fixo(db_):
                    return {
                        "mrr": 123456.78, "clientes": 777, "pipeline_aberto": 99999.99,
                        "ganho_mes": 0.0, "por_estagio": [], "top_deals": [],
                    }

                orchestration.relatorio_comercial_ctx = _mut2_ctx_fixo
                try:
                    r_mut2 = await tcd._gerar_relatorio_comercial_doc(db, crm_user, None)
                finally:
                    orchestration.relatorio_comercial_ctx = original_ctx_fn

                m2_ok, m2_det = await _expect_bite(
                    lambda: _oraculo_3_relatorio_ctx(tcd, r_mut2, ctx_real))
                record("MUTAÇÃO M2", "relatório com ctx hardcoded (números fixos) → oráculo 3", m2_ok, m2_det)
            else:
                record("MUTAÇÃO M2", "relatório com ctx hardcoded → oráculo 3", True, "PULADA (oráculo 3 falhou antes)")

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
    print(f"OK suite fase6-f2 ({n_pass}/{len(oraculos)} oráculos + {n_bite}/{len(mutacoes)} mutações"
          f"{' + ' + str(len(extras)) + ' resíduo' if extras else ''}) — GATE LIBERADO.")
    return 0


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    except Exception:
        traceback.print_exc()
        code = 2
    raise SystemExit(code)
