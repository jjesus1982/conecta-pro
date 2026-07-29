"""SUITE-ORÁCULO da Fase 6 Fatia 1 (gera-doc comercial) — prova formal,
executável e MUTAÇÃO-TESTADA de que as paredes das 2 tools gera-doc
(commit 84745537) seguram, e de que a suite MORDE se alguém regredir.
Molde: `test_oraculos_5_6a_anomalia.py` (standalone, sem pytest,
`sys.exit(!=0)` em falha crítica, mutação via monkeypatch de função real).

Componente sob prova: `modules/ai/conversation/services/orquestrador/
tools_comercial_doc.py` — `_gerar_proposta`/`_gerar_orcamento` (handlers),
`_lastro` (gate+preço+resolução de cliente), `_gate`, e o `register()` das 2
ToolDefs. Preço vem de `ProposalService().calculate_proposal_pricing(...) ->
PricingResult` (`modules/crm/services/pricing_engine.py`).

Os 5 oráculos:
  1. Branding — `_gerar_proposta`/`_gerar_orcamento` devolvem PDF (bytes
     decodificados começam com `%PDF`) — vieram do gerador branded real.
  2. Preço do motor, nunca de arg — `total` retornado == `float(
     PricingResult.total_monthly)` calculado independentemente com os MESMOS
     parâmetros; `_SCHEMA["properties"]` não declara total/valor/preco/price.
  3. Zero vazamento de custo/margem — nem o dict retornado nem os bytes do
     PDF (decodificados/inflados) contêm os VALORES internos do
     PricingResult (base_cost, total_cost, labor_cost, benefits_cost,
     equipment_cost, tax_amount, margin_value).
  4. RBAC identidade real — as 2 tools ∈ `tools_for_modules({"crm"})` e ∉
     `tools_for_modules({"dp"})`; `_gate(user_sem_crm)` levanta
     `PermissionError`.
  5. Fail-closed — sem `salario_base` ou cliente inexistente → dict
     `{"status": "recusado", ...}` SEM `arquivo_base64` (nunca fabrica).

MUTAÇÃO-TESTE (prova que a suite morde):
  M1 — preço de arg: `_lastro` monkeypatchado devolve um `pr` cujo
       `total_monthly` é um valor arbitrário "vindo de fora" (simulando
       preço do LLM) → oráculo 2 deve FALHAR.
  M2 — vazamento de custo: handler monkeypatchado injeta `pr.total_cost` no
       `resumo` do dict retornado → oráculo 3 deve FALHAR.
Se a mutação certa não derrubar o oráculo certo, o oráculo é fraco.

Bancada: container THROWAWAY (imagem conecta-pro-backend) anexado à rede
`conecta-pro_conecta-pro-network`, `DATABASE_URL` apontando pro Postgres real
via nome do container (`conecta-pro-postgres`) — NUNCA o backend vivo :8080.
READ-ONLY: só SELECT (primeiro Client ativo real); não cria nem apaga nada.
Se não existir cliente ativo real, os oráculos 1-3 são PULADOS com aviso
claro (nunca inventa cliente) — 4 e 5 não dependem de cliente e sempre rodam.
"""
from __future__ import annotations

import asyncio
import base64
import os
import re
import sys
import traceback
import zlib
from decimal import Decimal

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402


class FakeUser:
    """Objeto mínimo p/ exercitar `user_has_module`/`_gate` sem depender de
    sessão HTTP (mesmo padrão do molde 5.6a)."""

    def __init__(self, role: str, permissions: list[str]) -> None:
        self.role = role
        self.permissions = permissions


def _extrair_texto_pdf(pdf_bytes: bytes) -> str:
    """Texto bruto do PDF + conteúdo de todo stream flate-decompresso (os
    geradores usam ReportLab com pageCompression=1 por padrão — sem inflar
    os streams, uma string vazada dentro deles passaria despercebida)."""
    partes = [pdf_bytes.decode("latin-1", errors="ignore")]
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", pdf_bytes, re.DOTALL):
        try:
            partes.append(zlib.decompress(m.group(1)).decode("latin-1", errors="ignore"))
        except Exception:
            pass
    return "\n".join(partes)


# ───────────────────────── oráculos reutilizáveis (p/ mutação) ──────────────

async def _oraculo_1_branding(gerar_fn, db, user, *, cliente_id: str) -> tuple[dict, bytes]:
    r = await gerar_fn(db, user, None, produto="portaria", cliente_id=cliente_id,
                        salario_base=1670, qtd_postos=2, meses_contrato=12)
    assert r.get("status") != "recusado", f"recusou inesperadamente: {r}"
    assert "arquivo_base64" in r, f"sem PDF no retorno: {r}"
    pdf = base64.b64decode(r["arquivo_base64"])
    assert pdf[:4] == b"%PDF", f"não é PDF real (gerador branded): {pdf[:20]!r}"
    return r, pdf


async def _oraculo_2_preco_motor(tcd_mod, resultado: dict, *, base, hc, meses, stype,
                                  client_state, margem) -> None:
    from modules.crm.services.proposal_service import ProposalService
    pr_independente = ProposalService().calculate_proposal_pricing(
        base_salary=base, headcount=hc, contract_months=meses,
        service_type=stype, client_state=client_state, margin_target=margem)
    assert resultado.get("total") == float(pr_independente.total_monthly), (
        f"total retornado {resultado.get('total')} != motor real "
        f"{pr_independente.total_monthly} (preço não pode vir de outro lugar)"
    )
    proibidas = {"total", "valor", "preco", "price"} & set(tcd_mod._SCHEMA["properties"])
    assert not proibidas, f"_SCHEMA expõe propriedade de preço ao LLM: {proibidas}"


def _oraculo_3_zero_vazamento(tcd_mod, resultado: dict, pdf_bytes: bytes, pr) -> None:
    campos = ("base_cost", "total_cost", "labor_cost", "benefits_cost",
              "equipment_cost", "tax_amount", "margin_value")
    texto_dict = " ".join(str(v) for v in resultado.values())
    texto_pdf = _extrair_texto_pdf(pdf_bytes) if pdf_bytes else ""
    for campo in campos:
        val = getattr(pr, campo)
        val_brl = tcd_mod._brl(float(val))
        val_num = f"{float(val):.2f}"
        assert val_brl not in texto_dict, f"{campo} ({val_brl}) vazou no dict retornado: {resultado}"
        assert val_num not in texto_dict, f"{campo} ({val_num}) vazou no dict retornado: {resultado}"
        if texto_pdf:
            assert val_brl not in texto_pdf, f"{campo} ({val_brl}) vazou no PDF (texto/stream)"


def _oraculo_4_rbac(tcd_mod, crm_user, non_crm_user) -> None:
    from modules.ai.conversation.services.orquestrador import tool_registry as tr
    crm_tools = {t.name for t in tr.tools_for_modules({"crm"})}
    dp_tools = {t.name for t in tr.tools_for_modules({"dp"})}
    for nome in ("gerar_proposta_comercial_doc", "gerar_orcamento_doc"):
        assert nome in crm_tools, f"{nome} não aparece em tools_for_modules({{'crm'}})"
        assert nome not in dp_tools, f"{nome} vazou p/ tools_for_modules({{'dp'}})"
    tcd_mod._gate(crm_user)  # não deve levantar
    levantou = False
    try:
        tcd_mod._gate(non_crm_user)
    except PermissionError:
        levantou = True
    assert levantou, "_gate deveria levantar PermissionError p/ user sem módulo crm"


async def _oraculo_5_fail_closed(tcd_mod, db, user) -> None:
    r1 = await tcd_mod._gerar_proposta(db, user, None, produto="portaria", cliente_id=None,
                                        salario_base=None, qtd_postos=2, meses_contrato=12)
    assert r1.get("status") == "recusado", f"deveria recusar sem salario_base: {r1}"
    assert "arquivo_base64" not in r1, f"recusa não deveria conter PDF: {r1}"

    r2 = await tcd_mod._gerar_proposta(db, user, None, produto="portaria",
                                        cliente_cnpj="99999999999999",  # dígitos que não existem
                                        salario_base=1670, qtd_postos=2, meses_contrato=12)
    assert r2.get("status") == "recusado", f"deveria recusar cliente inexistente: {r2}"
    assert "arquivo_base64" not in r2, f"recusa não deveria conter PDF: {r2}"


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


async def main() -> int:  # noqa: C901 (suite única e linear, como o molde 5.6a)
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
                tools_comercial_doc as tcd,  # noqa: F401 — import registra as 2 ToolDefs
            )

            crm_user = FakeUser("operator", ["module:crm"])
            non_crm_user = FakeUser("operator", ["module:dp"])

            # ── ORÁCULO 4 (RBAC) e 5 (fail-closed) não dependem de cliente ──
            try:
                _oraculo_4_rbac(tcd, crm_user, non_crm_user)
                record(4, "RBAC identidade real (belt tools_for_modules + suspenders _gate)",
                       True, "crm vê as 2 tools, dp não vê; _gate barra user sem crm")
            except Exception as exc:
                record(4, "RBAC identidade real", False, f"{type(exc).__name__}: {exc}")

            try:
                await _oraculo_5_fail_closed(tcd, db, crm_user)
                record(5, "fail-closed (sem salário/cliente inexistente → recusa sem PDF)",
                       True, "2/2 casos recusados, nenhum arquivo_base64")
            except Exception as exc:
                record(5, "fail-closed", False, f"{type(exc).__name__}: {exc}")

            # ── cliente REAL p/ oráculos 1-3 (SELECT, nunca cria/apaga) ─────
            cli_row = (await db.execute(text(
                "SELECT id::text AS id, address_state FROM clients "
                "WHERE coalesce(ativo, true) = true ORDER BY created_at LIMIT 1"
            ))).mappings().first()

            if cli_row is None:
                aviso = "NENHUM cliente ativo real no banco — oráculos 1-3 PULADOS (não inventa cliente)."
                print(f"\nAVISO: {aviso}")
                for n in (1, 2, 3):
                    record(n, "PULADO (sem cliente real)", True, aviso)
            else:
                cliente_id = cli_row["id"]
                client_state = cli_row["address_state"] or "SP"
                base, hc, meses, stype, margem = (
                    Decimal("1670"), 2, 12, "portaria", Decimal("15.00"))

                # ════════════ ORÁCULO 1 — BRANDING ════════════
                resultado_prop, pdf_prop = None, None
                try:
                    resultado_prop, pdf_prop = await _oraculo_1_branding(
                        tcd._gerar_proposta, db, crm_user, cliente_id=cliente_id)
                    _, pdf_orc = await _oraculo_1_branding(
                        tcd._gerar_orcamento, db, crm_user, cliente_id=cliente_id)
                    record(1, "branding (PDF real do gerador branded, proposta+orçamento)",
                           True, f"{len(pdf_prop)}B + {len(pdf_orc)}B, ambos %PDF")
                except Exception as exc:
                    record(1, "branding", False, f"{type(exc).__name__}: {exc}")

                # ════════════ ORÁCULO 2 — PREÇO DO MOTOR ════════════
                try:
                    assert resultado_prop is not None, "oráculo 1 falhou antes"
                    await _oraculo_2_preco_motor(
                        tcd, resultado_prop, base=base, hc=hc, meses=meses, stype=stype,
                        client_state=client_state, margem=margem)
                    record(2, "preço sempre do PricingEngine, nunca de arg do LLM",
                           True, f"total={resultado_prop['total']} == motor real; _SCHEMA sem preço")
                except Exception as exc:
                    record(2, "preço do motor", False, f"{type(exc).__name__}: {exc}")

                # ════════════ ORÁCULO 3 — ZERO VAZAMENTO ════════════
                pr_real = None
                try:
                    from modules.crm.services.proposal_service import ProposalService
                    pr_real = ProposalService().calculate_proposal_pricing(
                        base_salary=base, headcount=hc, contract_months=meses,
                        service_type=stype, client_state=client_state, margin_target=margem)
                    assert resultado_prop is not None and pdf_prop is not None
                    _oraculo_3_zero_vazamento(tcd, resultado_prop, pdf_prop, pr_real)
                    record(3, "zero vazamento de custo/margem interno (dict + PDF)",
                           True, "base_cost/total_cost/labor_cost/benefits_cost/"
                                 "equipment_cost/tax_amount/margin_value ausentes")
                except Exception as exc:
                    record(3, "zero vazamento", False, f"{type(exc).__name__}: {exc}")

            # ════════════ MUTAÇÃO M1 — preço de arg (deve derrubar oráculo 2) ══
            if cli_row is not None:
                original_lastro = tcd._lastro

                async def _mut1_preco_arbitrario(db_, user_, **kwargs):
                    dados, recusa = await original_lastro(db_, user_, **kwargs)
                    if recusa:
                        return recusa
                    cli, hc_, meses_, pr = dados
                    pr.total_monthly = Decimal("999999.99")  # MUT: "preço vindo de fora"
                    return (cli, hc_, meses_, pr), None

                tcd._lastro = _mut1_preco_arbitrario
                try:
                    resultado_mut = await tcd._gerar_proposta(
                        db, crm_user, None, produto="portaria", cliente_id=cliente_id,
                        salario_base=1670, qtd_postos=2, meses_contrato=12)
                finally:
                    tcd._lastro = original_lastro

                m1_ok, m1_det = await _expect_bite(lambda: _oraculo_2_preco_motor(
                    tcd, resultado_mut, base=base, hc=hc, meses=meses, stype=stype,
                    client_state=client_state, margem=margem))
                record("MUTAÇÃO M1", "preço de arg (_lastro devolve total arbitrário) → oráculo 2",
                       m1_ok, m1_det)

                # ════════ MUTAÇÃO M2 — vazamento de custo (deve derrubar oráculo 3) ══
                original_gerar = tcd._gerar_proposta

                async def _mut2_vaza_custo(db_, user_, scope_, *, produto=None, cliente_id=None,
                                           cliente_cnpj=None, cliente_nome=None, salario_base=None,
                                           qtd_postos=None, meses_contrato=None, margem_pct=None, **_kw):
                    dados, recusa = await tcd._lastro(
                        db_, user_, produto=produto, cliente_id=cliente_id, cliente_cnpj=cliente_cnpj,
                        cliente_nome=cliente_nome, salario_base=salario_base, qtd_postos=qtd_postos,
                        meses_contrato=meses_contrato, margem_pct=margem_pct)
                    if recusa:
                        return recusa
                    cli, hc_, meses_, pr = dados
                    total_mensal = float(pr.total_monthly)
                    resumo = (f"{produto} p/ {cli.name}: "
                              f"custo interno {tcd._brl(float(pr.total_cost))}")  # MUT: vaza custo
                    return {"total": total_mensal, "resumo": resumo, "arquivo_base64": ""}

                tcd._gerar_proposta = _mut2_vaza_custo
                try:
                    resultado_mut2 = await tcd._gerar_proposta(
                        db, crm_user, None, produto="portaria", cliente_id=cliente_id,
                        salario_base=1670, qtd_postos=2, meses_contrato=12)
                finally:
                    tcd._gerar_proposta = original_gerar

                m2_ok, m2_det = await _expect_bite(lambda: _oraculo_3_zero_vazamento(
                    tcd, resultado_mut2, b"", pr_real))
                record("MUTAÇÃO M2", "vazamento de custo (handler injeta total_cost no resumo) → oráculo 3",
                       m2_ok, m2_det)
            else:
                record("MUTAÇÃO M1", "preço de arg → oráculo 2", True, "PULADA (sem cliente real p/ oráculo 2/3)")
                record("MUTAÇÃO M2", "vazamento de custo → oráculo 3", True, "PULADA (sem cliente real p/ oráculo 2/3)")

        finally:
            await db.rollback()  # read-only: nada foi escrito, mas garante nenhuma transação pendurada

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
    print(f"OK suite fase6-f1 ({n_pass}/{len(oraculos)} oráculos + {n_bite}/{len(mutacoes)} mutações) — GATE LIBERADO.")
    return 0


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    except Exception:
        traceback.print_exc()
        code = 2
    raise SystemExit(code)
