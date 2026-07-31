"""SUITE-ORÁCULO da Fase 6 Fatia 5 (financeiro aging receber/pagar) —
prova formal, executável e MUTAÇÃO-TESTADA de que as paredes das 2 tools
(commit 7cb412f3) seguram, e de que a suite MORDE se alguém regredir.
Molde: `test_oraculos_fase6_f3.py` (standalone, sem pytest, `sys.exit(!=0)`
em falha crítica, mutação via monkeypatch de função real) — mesma forma,
CONSOLIDADA-render como DRE/balancete; só troca por aging receber/pagar.

Componente sob prova: `modules/ai/conversation/services/orquestrador/
tools_financeiro_doc.py` — `_gerar_aging_receber_doc`, `_gerar_aging_pagar_doc`,
`_gate`. Reuso real: `get_receivables_aging` (receivable_controller) +
`ReceivableService`, `get_payables_aging` (payable_controller) +
`PayableService`, `aging_pdf_bytes` (relatorio_financeiro_pdf).

Os 5 oráculos:
  1. Números só do serviço real — o `total_em_aberto`/`total_vencido` do
     `resumo` == os números de `get_receivables_aging(...)`/
     `get_payables_aging(...)` chamados independentemente (nunca hardcode).
     Dado real do banco: receivable_accounts está 100% quitado (sem título
     em aberto) → o lado receber não tem como exercitar "números batem"
     (a tool recusa, corretamente); o lado pagar tem títulos pendentes reais
     → oráculo roda de fato nele. Se um dia settings, roda nos dois.
  2. Rótulo consolidado honesto — o `resumo` de quem gerou PDF cita
     "grupo consolidado (todas as empresas)" e NÃO cita "ELETRONICA"/
     "PATRIMONIAL" como se fosse um CNPJ só; as 2 tools têm params_schema
     VAZIO (sem propriedade `empresa` — não aceitam filtro que não existe).
  3. RBAC — as 2 tools ∈ `tools_for_modules({"financeiro"})`, ∉
     `tools_for_modules({"crm"})`; `_gate(user_sem_financeiro)` levanta
     `PermissionError`.
  4. Fail-closed sem títulos — sem título em aberto (real, no lado receber)
     ou com `get_*_aging` monkeypatchado devolvendo faixas=[]/total=0 (no
     lado pagar, que tem títulos reais) → `{"status":"recusado"}` SEM
     `arquivo_base64` (nunca gera aging vazio como se fosse real).
  5. Read-only — snapshot de `receivable_accounts`+`payable_accounts`
     (count) antes/depois de rodar as 2 tools: inalterado.

MUTAÇÃO-TESTE (prova que a suite morde):
  M1 — número forjado: monkeypatch injeta um `total_em_aberto` fixo no
       resumo, diferente do serviço real → oráculo 1 deve FALHAR. Aplicada
       no lado que de fato teve oráculo 1 rodando com número real (pagar,
       no estado atual do banco — ver nota do oráculo 1).
Se a mutação certa não derrubar o oráculo certo, o oráculo é fraco.

Bancada: container THROWAWAY (imagem conecta-pro-backend) anexado à rede
conecta-pro_conecta-pro-network, DATABASE_URL apontando pro Postgres real via
nome do container (conecta-pro-postgres) — NUNCA o backend vivo :8080.
READ-ONLY: só SELECT; nada cria/apaga. Nenhum monkeypatch desta suite escreve
no banco (M1 e a simulação de faixas=[] só trocam o dict em memória); se algum
vier a escrever, reverter no `finally` (nenhum precisa aqui).
"""
from __future__ import annotations

import asyncio
import base64
import os
import re
import sys
import traceback
from datetime import date

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402


class FakeUser:
    """Objeto mínimo p/ exercitar `user_has_module`/`_gate` sem depender de
    sessão HTTP (mesmo padrão do molde f3)."""

    def __init__(self, role: str, permissions: list[str]) -> None:
        self.role = role
        self.permissions = permissions


# ───────────────────────── oráculos reutilizáveis (p/ mutação) ──────────────

_RE_BRL = r"(R\$ -?[\d.]+,\d{2})"


def _extrair_rotulo(resumo: str, rotulo: str) -> str:
    m = re.search(rf"{rotulo} {_RE_BRL}", resumo)
    assert m, f"resumo não traz o rótulo '{rotulo} R$ ...': {resumo!r}"
    return m.group(1)


def _sem_pdf(resultado: dict) -> dict:
    """Cópia do resultado sem o base64 do PDF, só p/ mensagens de erro legíveis."""
    return {k: (f"<{len(v)}B>" if k == "arquivo_base64" else v) for k, v in resultado.items()}


def _check_aging_numeros(tfd, resultado: dict, dados_real: dict) -> None:
    resumo = resultado.get("resumo", "")
    for rotulo, campo in (("em aberto", "total_em_aberto"), ("vencido", "total_vencido")):
        achado = _extrair_rotulo(resumo, rotulo)
        esperado = tfd._brl(dados_real[campo])
        assert achado == esperado, (
            f"{campo}: resumo diz '{rotulo} {achado}', serviço real diz {esperado!r} "
            "— número não pode vir de outro lugar"
        )


async def _oraculo_1_aging_receber(tfd, db, user) -> tuple[dict, dict] | None:
    """Roda a tool + a chamada independente ao serviço real. Se não houver
    título em aberto de verdade, a tool recusa (comportamento correto) e não
    há como cruzar números — devolve None (PULADO, não fabricado)."""
    r = await tfd._gerar_aging_receber_doc(db, user, None)
    from modules.financial.controllers.receivable_controller import get_receivables_aging
    from modules.financial.services.receivable_service import ReceivableService
    dados_real = await get_receivables_aging(condominio_id=None, service=ReceivableService(db), current_user=user)
    if r.get("status") == "recusado":
        return None  # sem título real em aberto — não dá pra provar "números batem" sem inventar
    assert "arquivo_base64" in r, f"sem PDF no retorno: {_sem_pdf(r)}"
    pdf = base64.b64decode(r["arquivo_base64"])
    assert pdf[:4] == b"%PDF", f"não é PDF real: {pdf[:20]!r}"
    return r, dados_real


async def _oraculo_1_aging_pagar(tfd, db, user) -> tuple[dict, dict] | None:
    r = await tfd._gerar_aging_pagar_doc(db, user, None)
    from modules.financial.controllers.payable_controller import get_payables_aging
    from modules.financial.services.payable_service import PayableService
    dados_real = await get_payables_aging(condominio_id=None, service=PayableService(db), current_user=user)
    if r.get("status") == "recusado":
        return None
    assert "arquivo_base64" in r, f"sem PDF no retorno: {_sem_pdf(r)}"
    pdf = base64.b64decode(r["arquivo_base64"])
    assert pdf[:4] == b"%PDF", f"não é PDF real: {pdf[:20]!r}"
    return r, dados_real


def _oraculo_2_rotulo_e_schema(tfd, resultados_ok: list[dict]) -> None:
    assert resultados_ok, "nenhuma das 2 tools gerou PDF real — não há resumo p/ checar rótulo"
    for r in resultados_ok:
        resumo = r.get("resumo", "")
        assert tfd._CONSOLIDADO in resumo, f"resumo não rotula grupo consolidado: {resumo!r}"
        alto = resumo.upper()
        for termo in ("ELETRONICA", "PATRIMONIAL"):
            assert termo not in alto, (
                f"resumo cita '{termo}' como se fosse CNPJ único (deveria ser só "
                f"'{tfd._CONSOLIDADO}'): {resumo!r}"
            )
    from modules.ai.conversation.services.orquestrador import tool_registry as tr
    by_name = {t.name: t for t in tr.tools_for_modules({"financeiro"})}
    for nome in ("gerar_aging_receber_doc", "gerar_aging_pagar_doc"):
        assert nome in by_name, f"{nome} não registrada em tools_for_modules({{'financeiro'}})"
        schema = by_name[nome].params_schema
        assert schema.get("properties") == {}, (
            f"{nome}: schema deveria ser vazio (aging não filtra por empresa — não existe a coluna), "
            f"achei properties={schema.get('properties')!r}"
        )
        assert "empresa" not in (schema.get("properties") or {}), (
            f"{nome}: schema não pode aceitar 'empresa' — aging é intrinsecamente consolidado"
        )


def _oraculo_3_rbac(tfd, fin_user, non_fin_user) -> None:
    from modules.ai.conversation.services.orquestrador import tool_registry as tr
    fin_tools = {t.name for t in tr.tools_for_modules({"financeiro"})}
    crm_tools = {t.name for t in tr.tools_for_modules({"crm"})}
    for nome in ("gerar_aging_receber_doc", "gerar_aging_pagar_doc"):
        assert nome in fin_tools, f"{nome} não aparece em tools_for_modules({{'financeiro'}})"
        assert nome not in crm_tools, f"{nome} vazou p/ tools_for_modules({{'crm'}})"
    tfd._gate(fin_user)  # não deve levantar
    levantou = False
    try:
        tfd._gate(non_fin_user)
    except PermissionError:
        levantou = True
    assert levantou, "_gate deveria levantar PermissionError p/ user sem módulo financeiro"


def _check_recusa_sem_titulos(resultado: dict, contexto: str) -> None:
    assert resultado.get("status") == "recusado", (
        f"{contexto}: deveria recusar sem título em aberto (não gerar aging vazio): {_sem_pdf(resultado)}"
    )
    assert "arquivo_base64" not in resultado, f"{contexto}: recusa não deveria conter PDF: {_sem_pdf(resultado)}"


async def _oraculo_4_fail_closed(tfd, db, user, receber_recusou_de_verdade: bool) -> dict:
    """Lado receber: no estado real do banco (sem título em aberto) já recusa
    de verdade — usa isso direto (não fabrica). Lado pagar: tem título real
    em aberto, então simula faixas=[]/total=0 via monkeypatch do serviço
    (só o dict devolvido, nenhuma escrita) e confirma que a tool recusa."""
    if receber_recusou_de_verdade:
        r_receber = await tfd._gerar_aging_receber_doc(db, user, None)
        _check_recusa_sem_titulos(r_receber, "aging receber (sem título real em aberto)")

    # A tool importa get_payables_aging DENTRO da função (import local), então o monkeypatch
    # tem de ser no módulo de origem (payable_controller), não em `tfd`.
    import modules.financial.controllers.payable_controller as payable_controller
    original_get_payables_aging = payable_controller.get_payables_aging

    async def _get_payables_aging_vazio(*, condominio_id=None, service=None, current_user=None):
        return {"aging_date": str(date.today()), "tipo": "contas_pagar",
                "faixas": [], "total_em_aberto": 0, "total_vencido": 0}

    payable_controller.get_payables_aging = _get_payables_aging_vazio
    try:
        r_pagar_vazio = await tfd._gerar_aging_pagar_doc(db, user, None)
    finally:
        payable_controller.get_payables_aging = original_get_payables_aging
    _check_recusa_sem_titulos(r_pagar_vazio, "aging pagar (get_payables_aging simulado vazio)")
    return r_pagar_vazio


async def _snapshot_titulos(db) -> dict:
    row = (await db.execute(text(
        "SELECT (SELECT count(*) FROM receivable_accounts) AS n_receber, "
        "(SELECT count(*) FROM payable_accounts) AS n_pagar"
    ))).mappings().first()
    return dict(row)


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


async def main() -> int:  # noqa: C901 (suite única e linear, como o molde f3)
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
                tools_financeiro_doc as tfd,  # noqa: F401 — import registra as 2 ToolDefs
            )

            fin_user = FakeUser("operator", ["module:financeiro"])
            non_fin_user = FakeUser("operator", ["module:crm"])

            # ── snapshot ANTES de tocar em qualquer tool (oráculo 5) ────────
            antes = await _snapshot_titulos(db)

            # ════════════ ORÁCULO 3 — RBAC (não depende de dado real) ══════
            try:
                _oraculo_3_rbac(tfd, fin_user, non_fin_user)
                record(3, "RBAC identidade real (belt tools_for_modules + suspenders _gate)",
                       True, "financeiro vê as 2 tools, crm não vê; _gate barra user sem financeiro")
            except Exception as exc:
                record(3, "RBAC identidade real", False, f"{type(exc).__name__}: {exc}")

            # ════════════ ORÁCULO 1 — números só dos serviços reais ════════
            resultado_receber = dados_receber_real = None
            resultado_pagar = dados_pagar_real = None
            aviso_1 = ""
            try:
                out_receber = await _oraculo_1_aging_receber(tfd, db, fin_user)
                out_pagar = await _oraculo_1_aging_pagar(tfd, db, fin_user)
                if out_receber is not None:
                    resultado_receber, dados_receber_real = out_receber
                    _check_aging_numeros(tfd, resultado_receber, dados_receber_real)
                else:
                    aviso_1 += "receber: sem título real em aberto no banco agora (recusou, correto) — PULADO, não fabricado. "
                if out_pagar is not None:
                    resultado_pagar, dados_pagar_real = out_pagar
                    _check_aging_numeros(tfd, resultado_pagar, dados_pagar_real)
                else:
                    aviso_1 += "pagar: sem título real em aberto no banco agora (recusou, correto) — PULADO, não fabricado."
                assert resultado_receber is not None or resultado_pagar is not None, (
                    "nenhum dos dois lados tem título real em aberto — oráculo 1 não roda em nenhum: "
                    f"{aviso_1}"
                )
                record(1, "números só dos serviços reais (aging receber/pagar == get_*_aging independente)",
                       True, aviso_1 or "receber e pagar: resumo bate 1:1 com get_receivables_aging/get_payables_aging")
            except Exception as exc:
                record(1, "números só dos serviços reais", False, f"{type(exc).__name__}: {exc}")

            # ════════════ ORÁCULO 2 — rótulo consolidado honesto + schema vazio ═
            try:
                resultados_ok = [r for r in (resultado_receber, resultado_pagar) if r is not None]
                _oraculo_2_rotulo_e_schema(tfd, resultados_ok)
                record(2, "rótulo consolidado honesto + schema sem 'empresa'",
                       True, f"cita '{tfd._CONSOLIDADO}', schema vazio nas 2 tools")
            except Exception as exc:
                record(2, "rótulo consolidado honesto + schema vazio", False, f"{type(exc).__name__}: {exc}")

            # ════════════ ORÁCULO 4 — fail-closed sem títulos ══════════════
            resultado_pagar_vazio = None
            try:
                resultado_pagar_vazio = await _oraculo_4_fail_closed(
                    tfd, db, fin_user, receber_recusou_de_verdade=(resultado_receber is None))
                record(4, "fail-closed sem títulos (receber real vazio + pagar simulado vazio)",
                       True, "as 2 tools recusam sem arquivo_base64 quando não há título em aberto")
            except Exception as exc:
                record(4, "fail-closed sem títulos", False, f"{type(exc).__name__}: {exc}")

            # ════════════ ORÁCULO 5 — read-only (títulos intactos) ═════════
            try:
                depois = await _snapshot_titulos(db)
                assert antes == depois, f"receivable/payable_accounts mudou rodando as tools: antes={antes} depois={depois}"
                record(5, "read-only (nenhuma tool grava em receivable/payable_accounts)",
                       True, f"count intacto: {depois}")
            except Exception as exc:
                record(5, "read-only", False, f"{type(exc).__name__}: {exc}")

            # ══════════ MUTAÇÃO M1 — número forjado (deve derrubar oráculo 1) ══
            # Aplica no lado que de fato rodou oráculo 1 com número real neste estado
            # do banco (preferência: receber, senão pagar — mesma lógica do molde f3).
            alvo, dados_reais_alvo, nome_tool = None, None, None
            if resultado_receber is not None:
                alvo, dados_reais_alvo, nome_tool = "_gerar_aging_receber_doc", dados_receber_real, "receber"
            elif resultado_pagar is not None:
                alvo, dados_reais_alvo, nome_tool = "_gerar_aging_pagar_doc", dados_pagar_real, "pagar"

            if alvo is not None:
                original = getattr(tfd, alvo)

                async def _mut1_em_aberto_forjado(db_, user_, scope_, **kw):
                    r = await original(db_, user_, scope_, **kw)
                    if r.get("status") == "recusado":
                        return r
                    r = dict(r)
                    # MUT: injeta "em aberto" fixo "vindo de fora", diferente do serviço real
                    r["resumo"] = re.sub(rf"em aberto {_RE_BRL}", "em aberto R$ 1,00", r["resumo"])
                    return r

                setattr(tfd, alvo, _mut1_em_aberto_forjado)
                try:
                    resultado_mut1 = await getattr(tfd, alvo)(db, fin_user, None)
                finally:
                    setattr(tfd, alvo, original)

                m1_ok, m1_det = await _expect_bite(lambda: _check_aging_numeros(
                    tfd, resultado_mut1, dados_reais_alvo))
                record("MUTAÇÃO M1", f"'em aberto' forjado no resumo do aging {nome_tool} → oráculo 1", m1_ok, m1_det)
            else:
                record("MUTAÇÃO M1", "'em aberto' forjado → oráculo 1", True,
                       "PULADA (oráculo 1 não rodou em nenhum lado — sem título real em aberto)")

        finally:
            await db.rollback()  # read-only: nada foi escrito por esta suite, mas garante nenhuma transação pendurada

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
    print(f"OK suite fase6-f5 ({n_pass}/{len(oraculos)} oráculos + {n_bite}/{len(mutacoes)} mutações) — GATE LIBERADO.")
    return 0


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    except Exception:
        traceback.print_exc()
        code = 2
    raise SystemExit(code)
