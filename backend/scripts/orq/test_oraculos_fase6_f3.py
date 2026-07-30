"""SUITE-ORÁCULO da Fase 6 Fatia 3 (gera-doc financeiro: DRE/balancete/fluxo) —
prova formal, executável e MUTAÇÃO-TESTADA de que as paredes das 3 tools
(commit 8156b4ca) seguram, e de que a suite MORDE se alguém regredir.
Molde: `test_oraculos_fase6_f1.py`/`_f2.py` (standalone, sem pytest,
`sys.exit(!=0)` em falha crítica, mutação via monkeypatch de função real).

Componente sob prova: `modules/ai/conversation/services/orquestrador/
tools_financeiro_doc.py` — `_gerar_dre_doc`, `_gerar_balancete_doc`,
`_gerar_fluxo_caixa_doc`, `_resolve_empresa`, `_gate`. Reuso real: `get_dre`,
`balancete_real`, `FluxoCaixaService.dfc_mensal`, `_*_pdf_bytes`
(`relatorios_controller`).

Os 6 oráculos:
  1. Números só dos serviços reais — o `resumo` do balancete (débito/crédito/
     diferença) == os números de `balancete_real(...)` chamado independente;
     o lucro líquido do resumo do DRE == o valor do grupo `lucro_liquido` de
     `get_dre(...)` chamado independente. Mesma fonte, nunca hardcode.
  2. DRE recusa projeção pura — ano antigo sem lançamento real no razão (só
     estimativa por contratos ativos, `meses_com_folha_lancada == 0`) →
     `{"status": "recusado"}` SEM `arquivo_base64`.
  3. Rótulo consolidado honesto — DRE e balancete citam "grupo consolidado
     (todas as empresas)" e NÃO citam "ELETRONICA"/"PATRIMONIAL" como se
     fossem de um CNPJ só.
  4. Fluxo POR-CNPJ sem default — sem `empresa` → recusa (sem PDF), mensagem
     fala de CNPJ/não assume default; com `empresa` real → resolve e gera;
     `empresa` inexistente → recusa.
  5. RBAC — as 3 tools ∈ `tools_for_modules({"financeiro"})` e ∉
     `tools_for_modules({"crm"})`; `_gate(user_sem_financeiro)` levanta
     `PermissionError`.
  6. Read-only — snapshot de `accounting_entries` (count/soma/updated_at
     máximo) antes/depois de rodar as 3 tools: inalterado.

MUTAÇÃO-TESTE (prova que a suite morde):
  M1 — número forjado: `_gerar_balancete_doc` monkeypatchado devolve um
       resumo com débito fixo diferente do serviço real → oráculo 1 deve
       FALHAR.
  M2 — fluxo cai num CNPJ default: `_gerar_fluxo_caixa_doc` monkeypatchado
       assume uma empresa default quando `empresa` vem ausente (em vez de
       recusar) → oráculo 4 deve FALHAR.
Se a mutação certa não derrubar o oráculo certo, o oráculo é fraco.

Bancada: container THROWAWAY (imagem conecta-pro-backend) anexado à rede
conecta-pro_conecta-pro-network, DATABASE_URL apontando pro Postgres real via
nome do container (conecta-pro-postgres) — NUNCA o backend vivo :8080.
READ-ONLY: só SELECT (oráculos 1/2/3/4/6 usam ano=2026 real p/ dado com
lançamento, e ano=2020 — sem accounting_entries — p/ a recusa de projeção
pura); nada cria/apaga. Nenhum monkeypatch desta suite escreve no banco; se
algum vier a escrever, reverter no `finally` (nenhum precisa aqui).
"""
from __future__ import annotations

import asyncio
import base64
import os
import re
import sys
import traceback

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

_ANO_REAL = 2026  # tem accounting_entries reais lançados
_ANO_SEM_FOLHA = 2020  # sem nenhum accounting_entries; só estimativa por contrato -> DRE recusa
_EMPRESA_REAL = "Eletrônica"  # nome_fantasia real (Conecta Mais Eletrônica), tem bank_transactions 2026


class FakeUser:
    """Objeto mínimo p/ exercitar `user_has_module`/`_gate` sem depender de
    sessão HTTP (mesmo padrão dos moldes f1/f2)."""

    def __init__(self, role: str, permissions: list[str]) -> None:
        self.role = role
        self.permissions = permissions


# ───────────────────────── oráculos reutilizáveis (p/ mutação) ──────────────

async def _oraculo_1_balancete(tfd, db, user, ano: int) -> tuple[dict, dict]:
    r = await tfd._gerar_balancete_doc(db, user, None, ano=ano)
    assert r.get("status") != "recusado", f"balancete recusou ano com lançamento real: {r}"
    assert "arquivo_base64" in r, f"sem PDF no retorno: {r}"
    pdf = base64.b64decode(r["arquivo_base64"])
    assert pdf[:4] == b"%PDF", f"não é PDF real: {pdf[:20]!r}"
    from modules.financial.controllers.relatorios_controller import balancete_real
    dados_real = await balancete_real(ano=ano, mes=None, db=db, _user=user)
    return r, dados_real


_RE_BRL = r"(R\$ -?[\d.]+,\d{2})"


def _extrair_rotulo(resumo: str, rotulo: str) -> str:
    m = re.search(rf"{rotulo} {_RE_BRL}", resumo)
    assert m, f"resumo não traz o rótulo '{rotulo} R$ ...': {resumo!r}"
    return m.group(1)


def _check_balancete_numeros(tfd, resultado: dict, dados_real: dict) -> None:
    resumo = resultado.get("resumo", "")
    # extrai por RÓTULO (não por substring solta): débito == crédito quando o balancete
    # fecha, então um "in resumo" ingênuo não pegaria um valor forjado só no rótulo errado.
    for rotulo, campo in (("débito", "total_debito"), ("crédito", "total_credito"),
                          ("diferença", "diferenca")):
        achado = _extrair_rotulo(resumo, rotulo)
        esperado = tfd._brl(dados_real[campo])
        assert achado == esperado, (
            f"{campo}: resumo diz '{rotulo} {achado}', balancete_real diz {esperado!r} "
            "— número não pode vir de outro lugar"
        )


async def _oraculo_1_dre(tfd, db, user, ano: int) -> tuple[dict, dict]:
    r = await tfd._gerar_dre_doc(db, user, None, ano=ano)
    assert r.get("status") != "recusado", f"DRE recusou ano com lançamento real: {r}"
    assert "arquivo_base64" in r, f"sem PDF no retorno: {r}"
    pdf = base64.b64decode(r["arquivo_base64"])
    assert pdf[:4] == b"%PDF", f"não é PDF real: {pdf[:20]!r}"
    from modules.financial.controllers.relatorios_controller import get_dre
    dados_real = await get_dre(ano=ano, mes_inicio=1, mes_fim=12, comparativo=False,
                                condominio_id=None, db=db, _current_user=user)
    return r, dados_real


def _check_dre_numeros(tfd, resultado: dict, dados_real: dict) -> None:
    grupos = dados_real.get("grupos", [])
    ll = next((float(g.get("valor") or 0) for g in grupos
               if g.get("grupo") in ("lucro_liquido", "resultado_liquido")), None)
    resumo = resultado.get("resumo", "")
    assert ll is not None, f"get_dre real não devolveu grupo lucro_liquido: {dados_real}"
    achado = _extrair_rotulo(resumo, "lucro líquido")
    esperado = tfd._brl(ll)
    assert achado == esperado, (
        f"lucro líquido: resumo diz '{achado}', get_dre real diz {esperado!r} "
        "— número não pode vir de outro lugar"
    )


async def _oraculo_2_dre_recusa_projecao(tfd, db, user, ano: int) -> None:
    r = await tfd._gerar_dre_doc(db, user, None, ano=ano)
    assert r.get("status") == "recusado", f"DRE deveria recusar ano só-projeção ({ano}): {r}"
    assert "arquivo_base64" not in r, f"recusa não deveria conter PDF: {r}"


def _oraculo_3_rotulo_consolidado(tfd, resultado_dre: dict, resultado_balancete: dict) -> None:
    for nome, r in (("DRE", resultado_dre), ("balancete", resultado_balancete)):
        resumo = r.get("resumo", "")
        assert tfd._CONSOLIDADO in resumo, f"{nome}: resumo não rotula grupo consolidado: {resumo!r}"
        alto = resumo.upper()
        for termo in ("ELETRONICA", "PATRIMONIAL"):
            assert termo not in alto, (
                f"{nome}: resumo cita '{termo}' como se fosse CNPJ único (deveria ser só "
                f"'{tfd._CONSOLIDADO}'): {resumo!r}"
            )


def _sem_pdf(resultado: dict) -> dict:
    """Cópia do resultado sem o base64 do PDF, só p/ mensagens de erro legíveis."""
    return {k: (f"<{len(v)}B>" if k == "arquivo_base64" else v) for k, v in resultado.items()}


def _check_fluxo_sem_empresa_recusa(resultado: dict) -> None:
    assert resultado.get("status") == "recusado", (
        f"fluxo sem empresa deveria recusar (não assumir CNPJ default): {_sem_pdf(resultado)}"
    )
    assert "arquivo_base64" not in resultado, f"recusa não deveria conter PDF: {_sem_pdf(resultado)}"
    motivo = (resultado.get("motivo") or "").upper()
    assert "CNPJ" in motivo or "EMPRESA" in motivo, (
        f"recusa deveria explicar que fluxo é por CNPJ/pedir a empresa: {_sem_pdf(resultado)}"
    )


async def _oraculo_4_fluxo_por_cnpj(tfd, db, user, ano: int, empresa_real: str) -> dict:
    r_sem_empresa = await tfd._gerar_fluxo_caixa_doc(db, user, None, ano=ano)
    _check_fluxo_sem_empresa_recusa(r_sem_empresa)

    r_ok = await tfd._gerar_fluxo_caixa_doc(db, user, None, ano=ano, empresa=empresa_real)
    assert r_ok.get("status") != "recusado", f"fluxo recusou empresa real com movimento: {r_ok}"
    assert "arquivo_base64" in r_ok, f"sem PDF no retorno: {r_ok}"
    pdf = base64.b64decode(r_ok["arquivo_base64"])
    assert pdf[:4] == b"%PDF", f"não é PDF real: {pdf[:20]!r}"
    assert "CNPJ isolado" in r_ok.get("resumo", ""), f"resumo não rotula CNPJ isolado: {r_ok.get('resumo')}"

    r_bad = await tfd._gerar_fluxo_caixa_doc(db, user, None, ano=ano, empresa="xyz empresa inexistente 12345")
    assert r_bad.get("status") == "recusado", f"fluxo deveria recusar empresa inexistente: {r_bad}"
    assert "arquivo_base64" not in r_bad, f"recusa não deveria conter PDF: {r_bad}"
    return r_sem_empresa


def _oraculo_5_rbac(tfd, fin_user, non_fin_user) -> None:
    from modules.ai.conversation.services.orquestrador import tool_registry as tr
    fin_tools = {t.name for t in tr.tools_for_modules({"financeiro"})}
    crm_tools = {t.name for t in tr.tools_for_modules({"crm"})}
    for nome in ("gerar_dre_doc", "gerar_balancete_doc", "gerar_fluxo_caixa_doc"):
        assert nome in fin_tools, f"{nome} não aparece em tools_for_modules({{'financeiro'}})"
        assert nome not in crm_tools, f"{nome} vazou p/ tools_for_modules({{'crm'}})"
    tfd._gate(fin_user)  # não deve levantar
    levantou = False
    try:
        tfd._gate(non_fin_user)
    except PermissionError:
        levantou = True
    assert levantou, "_gate deveria levantar PermissionError p/ user sem módulo financeiro"


async def _snapshot_razao(db) -> dict:
    row = (await db.execute(text(
        "SELECT count(*) AS n, coalesce(sum(valor), 0)::float AS soma, "
        "max(updated_at) AS ultimo FROM accounting_entries"
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


async def main() -> int:  # noqa: C901 (suite única e linear, como os moldes f1/f2)
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
                tools_financeiro_doc as tfd,  # noqa: F401 — import registra as 3 ToolDefs
            )

            fin_user = FakeUser("operator", ["module:financeiro"])
            non_fin_user = FakeUser("operator", ["module:crm"])

            # ── snapshot ANTES de tocar em qualquer tool (oráculo 6) ────────
            antes = await _snapshot_razao(db)

            # ════════════ ORÁCULO 5 — RBAC (não depende de dado real) ══════
            try:
                _oraculo_5_rbac(tfd, fin_user, non_fin_user)
                record(5, "RBAC identidade real (belt tools_for_modules + suspenders _gate)",
                       True, "financeiro vê as 3 tools, crm não vê; _gate barra user sem financeiro")
            except Exception as exc:
                record(5, "RBAC identidade real", False, f"{type(exc).__name__}: {exc}")

            # ════════════ ORÁCULO 2 — DRE recusa projeção pura ═════════════
            try:
                await _oraculo_2_dre_recusa_projecao(tfd, db, fin_user, _ANO_SEM_FOLHA)
                record(2, "DRE recusa projeção pura (ano sem lançamento real no razão)",
                       True, f"ano {_ANO_SEM_FOLHA}: recusado sem PDF")
            except Exception as exc:
                record(2, "DRE recusa projeção pura", False, f"{type(exc).__name__}: {exc}")

            # ════════════ ORÁCULO 1 — números só dos serviços reais ════════
            resultado_dre = resultado_balancete = None
            try:
                resultado_dre, dados_dre_real = await _oraculo_1_dre(tfd, db, fin_user, _ANO_REAL)
                _check_dre_numeros(tfd, resultado_dre, dados_dre_real)
                resultado_balancete, dados_bal_real = await _oraculo_1_balancete(tfd, db, fin_user, _ANO_REAL)
                _check_balancete_numeros(tfd, resultado_balancete, dados_bal_real)
                record(1, "números só dos serviços reais (DRE lucro líquido + balancete débito/crédito)",
                       True, f"ano {_ANO_REAL}: resumo bate 1:1 com get_dre/balancete_real")
            except Exception as exc:
                record(1, "números só dos serviços reais", False, f"{type(exc).__name__}: {exc}")

            # ════════════ ORÁCULO 3 — rótulo consolidado honesto ═══════════
            try:
                assert resultado_dre is not None and resultado_balancete is not None, "oráculo 1 falhou antes"
                _oraculo_3_rotulo_consolidado(tfd, resultado_dre, resultado_balancete)
                record(3, "rótulo consolidado honesto (nunca um CNPJ único)",
                       True, f"DRE e balancete citam '{tfd._CONSOLIDADO}'")
            except Exception as exc:
                record(3, "rótulo consolidado honesto", False, f"{type(exc).__name__}: {exc}")

            # ════════════ ORÁCULO 4 — fluxo POR-CNPJ, sem default ══════════
            resultado_fluxo_sem_empresa = None
            try:
                resultado_fluxo_sem_empresa = await _oraculo_4_fluxo_por_cnpj(
                    tfd, db, fin_user, _ANO_REAL, _EMPRESA_REAL)
                record(4, "fluxo por CNPJ (sem empresa recusa, empresa real gera, inexistente recusa)",
                       True, f"empresa='{_EMPRESA_REAL}' resolvida via cadastro real")
            except Exception as exc:
                record(4, "fluxo por CNPJ sem default", False, f"{type(exc).__name__}: {exc}")

            # ════════════ ORÁCULO 6 — read-only (accounting_entries intacto) ═
            try:
                depois = await _snapshot_razao(db)
                assert antes == depois, f"accounting_entries mudou rodando as tools: antes={antes} depois={depois}"
                record(6, "read-only (nenhuma tool grava em accounting_entries)",
                       True, f"count/soma/updated_at intactos: {depois}")
            except Exception as exc:
                record(6, "read-only", False, f"{type(exc).__name__}: {exc}")

            # ══════════ MUTAÇÃO M1 — número forjado (deve derrubar oráculo 1) ══
            if resultado_balancete is not None:
                original_balancete = tfd._gerar_balancete_doc

                async def _mut1_debito_forjado(db_, user_, scope_, *, mes=None, ano=None, **_kw):
                    r = await original_balancete(db_, user_, scope_, mes=mes, ano=ano)
                    if r.get("status") == "recusado":
                        return r
                    r = dict(r)
                    # MUT: injeta débito fixo "vindo de fora", diferente do serviço real
                    r["resumo"] = re.sub(rf"débito {_RE_BRL}", "débito R$ 1,00", r["resumo"])
                    return r

                tfd._gerar_balancete_doc = _mut1_debito_forjado
                try:
                    resultado_mut1 = await tfd._gerar_balancete_doc(db, fin_user, None, ano=_ANO_REAL)
                finally:
                    tfd._gerar_balancete_doc = original_balancete

                m1_ok, m1_det = await _expect_bite(lambda: _check_balancete_numeros(
                    tfd, resultado_mut1, dados_bal_real))
                record("MUTAÇÃO M1", "débito forjado no resumo do balancete → oráculo 1", m1_ok, m1_det)
            else:
                record("MUTAÇÃO M1", "débito forjado → oráculo 1", True, "PULADA (oráculo 1 falhou antes)")

            # ═══════ MUTAÇÃO M2 — fluxo cai em CNPJ default (deve derrubar oráculo 4) ══
            if resultado_fluxo_sem_empresa is not None:
                original_fluxo = tfd._gerar_fluxo_caixa_doc

                async def _mut2_default_cnpj(db_, user_, scope_, *, empresa=None, ano=None, mes=None, **_kw):
                    if not (empresa and str(empresa).strip()):
                        empresa = _EMPRESA_REAL  # MUT: assume CNPJ default em vez de recusar
                    return await original_fluxo(db_, user_, scope_, empresa=empresa, ano=ano, mes=mes)

                tfd._gerar_fluxo_caixa_doc = _mut2_default_cnpj
                try:
                    resultado_mut2 = await tfd._gerar_fluxo_caixa_doc(db, fin_user, None, ano=_ANO_REAL)
                finally:
                    tfd._gerar_fluxo_caixa_doc = original_fluxo

                m2_ok, m2_det = await _expect_bite(lambda: _check_fluxo_sem_empresa_recusa(resultado_mut2))
                record("MUTAÇÃO M2", "fluxo sem empresa cai num CNPJ default → oráculo 4", m2_ok, m2_det)
            else:
                record("MUTAÇÃO M2", "fluxo cai em CNPJ default → oráculo 4", True, "PULADA (oráculo 4 falhou antes)")

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
    print(f"OK suite fase6-f3 ({n_pass}/{len(oraculos)} oráculos + {n_bite}/{len(mutacoes)} mutações) — GATE LIBERADO.")
    return 0


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    except Exception:
        traceback.print_exc()
        code = 2
    raise SystemExit(code)
