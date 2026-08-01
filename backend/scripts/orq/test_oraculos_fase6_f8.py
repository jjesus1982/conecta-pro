"""SUITE-ORÁCULO da Fase 6 Fatia 8 (NFS-e no chat, escopado por empresa) —
prova formal, executável e MUTAÇÃO-TESTADA de que as paredes da tool
`gerar_relatorio_nfse_doc` (commit d69907f0) seguram, e de que a suite MORDE
se alguém regredir. Molde: `test_oraculos_fase6_f3.py` (standalone, sem
pytest, `sys.exit(!=0)` em falha crítica, mutação via monkeypatch).

Componente sob prova: `modules/ai/conversation/services/orquestrador/
tools_fiscal_doc.py` — `_gerar_relatorio_nfse_doc`, `_gate`, `_resolve_empresa`
(reuso 1:1 de tools_financeiro_doc). Fonte real: `nfse_emitidas_nacional`
(empresa_id, numero, competencia, tomador_nome, valor_servicos, iss_valor,
valor_liquido). Parede CENTRAL desta suite: a tool é POR EMPRESA e NUNCA
mistura os 2 CNPJ (Eletrônica × Patrimonial); só diretoria (belt fiscal) usa.

Os 4 oráculos:
  1. Números reais — resumo da tool (qtd de notas + valor dos serviços) ==
     `SELECT count(*), sum(valor_servicos) FROM nfse_emitidas_nacional WHERE
     empresa_id=<Eletrônica>` calculado independente. Nunca hardcoded.
  2. Escopado por empresa, NUNCA mistura CNPJ (parede central) — empresa=
     Patrimonial traz só as notas dela: qtd do resumo == count real filtrado
     por empresa_id da Patrimonial, e ESSA qtd é DIFERENTE do total geral
     (Eletrônica+Patrimonial somadas, sem filtro).
  3. Sem empresa → recusa — sem `empresa` a tool recusa (`status=recusado`,
     sem `arquivo_base64`); não assume nem consolida os 2 CNPJ.
  4. RBAC diretoria (fiscal) + read-only — a tool ∈ `tools_for_modules(
     {"fiscal"})`, ∉ `tools_for_modules({"crm"})`; `_gate(user sem fiscal)`
     levanta `PermissionError`; snapshot count(*) de `nfse_emitidas_nacional`
     antes/depois de rodar a tool: inalterado.

MUTAÇÃO-TESTE (prova que a suite morde):
  M1 — mistura CNPJ: monkeypatch de `_gerar_relatorio_nfse_doc` que roda a
       MESMA query sem o filtro `empresa_id` (traz as notas dos 2 CNPJ) →
       oráculo 2 deve FALHAR (a "qtd da Patrimonial" deixaria de bater com o
       count real filtrado por empresa_id dela).
Se M1 não derrubar o oráculo 2, o oráculo é fraco.

Bancada: container THROWAWAY (imagem conecta-pro-backend) anexado à rede
conecta-pro_conecta-pro-network, DATABASE_URL apontando pro Postgres real via
nome do container (conecta-pro-postgres) — NUNCA o backend vivo :8080.
READ-ONLY: só SELECT; nada cria/apaga. Nenhum monkeypatch desta suite escreve
no banco.

Receita (rodar da raiz do repo, no host):
  docker run --rm --network conecta-pro_conecta-pro-network \\
    -e DATABASE_URL='postgresql+asyncpg://postgres:<senha>@conecta-pro-postgres:5432/conecta_pro' \\
    -v backend/scripts/orq:/oracle:ro \\
    conecta-pro-backend:latest python /oracle/test_oraculos_fase6_f8.py
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

_ELETRONICA_ID = "619a3df1-8bce-49ce-b77a-04f80a0e8491"
_PATRIMONIAL_ID = "7d79ed12-d480-4906-b2e0-2b2c4d299bab"
_ELETRONICA_TERMO = "Eletronica"
_PATRIMONIAL_TERMO = "Patrimonial"


class FakeUser:
    """Objeto mínimo p/ exercitar `user_has_module`/`_gate` sem depender de
    sessão HTTP (mesmo padrão do molde f3)."""

    def __init__(self, role: str, permissions: list[str]) -> None:
        self.role = role
        self.permissions = permissions


# ───────────────────────── helpers de dado real (independentes da tool) ────

async def _count_e_soma(db, empresa_id: str | None) -> tuple[int, float]:
    """Conta/soma real em nfse_emitidas_nacional. empresa_id=None => total geral (2 CNPJ)."""
    if empresa_id is None:
        row = (await db.execute(text(
            "SELECT count(*) AS n, coalesce(sum(valor_servicos), 0)::float AS s "
            "FROM nfse_emitidas_nacional"
        ))).mappings().first()
    else:
        row = (await db.execute(text(
            "SELECT count(*) AS n, coalesce(sum(valor_servicos), 0)::float AS s "
            "FROM nfse_emitidas_nacional WHERE empresa_id = :eid"
        ), {"eid": empresa_id})).mappings().first()
    return row["n"], row["s"]


def _extrair_qtd_e_valor(resumo: str) -> tuple[int, str]:
    m = re.search(r"(\d+) notas, valor (R\$ -?[\d.]+,\d{2})", resumo)
    assert m, f"resumo não traz 'N notas, valor R$ ...': {resumo!r}"
    return int(m.group(1)), m.group(2)


# ───────────────────────── oráculos reutilizáveis (p/ mutação) ──────────────

async def _oraculo_1_numeros_reais(tfd, db, user) -> dict:
    r = await tfd._gerar_relatorio_nfse_doc(db, user, None, empresa=_ELETRONICA_TERMO)
    assert r.get("status") != "recusado", f"NFS-e recusou empresa real com notas: {r}"
    assert "arquivo_base64" in r, f"sem PDF no retorno: {r}"
    pdf = base64.b64decode(r["arquivo_base64"])
    assert pdf[:4] == b"%PDF", f"não é PDF real: {pdf[:20]!r}"

    n_real, s_real = await _count_e_soma(db, _ELETRONICA_ID)
    qtd, valor = _extrair_qtd_e_valor(r["resumo"])
    assert qtd == n_real, f"qtd no resumo ({qtd}) != count real filtrado ({n_real})"
    esperado = tfd._brl(s_real)
    assert valor == esperado, f"valor no resumo ({valor!r}) != soma real ({esperado!r})"
    return r


def _check_escopado_patrimonial(resultado: dict, n_patrimonial_real: int, n_total_real: int) -> None:
    qtd, _valor = _extrair_qtd_e_valor(resultado.get("resumo", ""))
    assert qtd == n_patrimonial_real, (
        f"qtd do resumo Patrimonial ({qtd}) != count real filtrado por empresa_id dela "
        f"({n_patrimonial_real}) — a tool não está escopando por CNPJ"
    )
    assert qtd != n_total_real, (
        f"qtd do resumo Patrimonial ({qtd}) == total geral dos 2 CNPJ ({n_total_real}) "
        "— MISTUROU CNPJ (filtro empresa_id não mordeu)"
    )


async def _oraculo_2_escopado_por_empresa(tfd, db, user) -> dict:
    r = await tfd._gerar_relatorio_nfse_doc(db, user, None, empresa=_PATRIMONIAL_TERMO)
    assert r.get("status") != "recusado", f"NFS-e recusou Patrimonial com notas reais: {r}"
    n_patrimonial_real, _ = await _count_e_soma(db, _PATRIMONIAL_ID)
    n_total_real, _ = await _count_e_soma(db, None)
    assert n_patrimonial_real != n_total_real, (
        "fixture inválida: Patrimonial tem o mesmo total geral (sem 2º CNPJ p/ provar mistura)"
    )
    _check_escopado_patrimonial(r, n_patrimonial_real, n_total_real)
    return r


async def _oraculo_3_sem_empresa_recusa(tfd, db, user) -> dict:
    r = await tfd._gerar_relatorio_nfse_doc(db, user, None)
    assert r.get("status") == "recusado", f"sem empresa deveria recusar (não assumir CNPJ): {r}"
    assert "arquivo_base64" not in r, f"recusa não deveria conter PDF: {r}"
    return r


def _oraculo_4_rbac(tfd, fiscal_user, non_fiscal_user) -> None:
    from modules.ai.conversation.services.orquestrador import tool_registry as tr
    fiscal_tools = {t.name for t in tr.tools_for_modules({"fiscal"})}
    crm_tools = {t.name for t in tr.tools_for_modules({"crm"})}
    nome = "gerar_relatorio_nfse_doc"
    assert nome in fiscal_tools, f"{nome} não aparece em tools_for_modules({{'fiscal'}})"
    assert nome not in crm_tools, f"{nome} vazou p/ tools_for_modules({{'crm'}})"
    tfd._gate(fiscal_user)  # não deve levantar
    levantou = False
    try:
        tfd._gate(non_fiscal_user)
    except PermissionError:
        levantou = True
    assert levantou, "_gate deveria levantar PermissionError p/ user sem módulo fiscal"


async def _snapshot_nfse(db) -> dict:
    row = (await db.execute(text(
        "SELECT count(*) AS n, coalesce(sum(valor_servicos), 0)::float AS soma "
        "FROM nfse_emitidas_nacional"
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


async def main() -> int:
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
                tools_fiscal_doc as tfd,  # noqa: F401 — import registra a ToolDef
            )

            fiscal_user = FakeUser("operator", ["module:fiscal"])
            non_fiscal_user = FakeUser("operator", ["module:crm"])

            # ── snapshot ANTES de tocar em qualquer tool (read-only, oráculo 4) ──
            antes = await _snapshot_nfse(db)

            # ════════════ ORÁCULO 4 — RBAC (não depende de dado real) ══════
            try:
                _oraculo_4_rbac(tfd, fiscal_user, non_fiscal_user)
                record(4, "RBAC diretoria (belt tools_for_modules + suspenders _gate) + read-only",
                       True, "fiscal vê a tool, crm não vê; _gate barra user sem fiscal")
            except Exception as exc:
                record(4, "RBAC diretoria + read-only", False, f"{type(exc).__name__}: {exc}")

            # ════════════ ORÁCULO 3 — sem empresa → recusa ═════════════════
            try:
                await _oraculo_3_sem_empresa_recusa(tfd, db, fiscal_user)
                record(3, "sem empresa → recusa (não assume nem consolida os 2 CNPJ)",
                       True, "status=recusado, sem arquivo_base64")
            except Exception as exc:
                record(3, "sem empresa → recusa", False, f"{type(exc).__name__}: {exc}")

            # ════════════ ORÁCULO 1 — números reais (Eletrônica) ═══════════
            resultado_1 = None
            try:
                resultado_1 = await _oraculo_1_numeros_reais(tfd, db, fiscal_user)
                record(1, "números reais (qtd + valor batem 1:1 com SELECT independente)",
                       True, f"Eletrônica: {resultado_1['resumo']}")
            except Exception as exc:
                record(1, "números reais", False, f"{type(exc).__name__}: {exc}")

            # ════════ ORÁCULO 2 — escopado por empresa, nunca mistura CNPJ (parede central) ═
            resultado_2 = None
            n_patrimonial_real = n_total_real = None
            try:
                n_patrimonial_real, _ = await _count_e_soma(db, _PATRIMONIAL_ID)
                n_total_real, _ = await _count_e_soma(db, None)
                resultado_2 = await _oraculo_2_escopado_por_empresa(tfd, db, fiscal_user)
                record(2, "escopado por empresa, NUNCA mistura CNPJ (parede central)",
                       True, f"Patrimonial: {n_patrimonial_real} notas "
                             f"(total geral 2 CNPJ = {n_total_real}, diferente)")
            except Exception as exc:
                record(2, "escopado por empresa, nunca mistura CNPJ", False, f"{type(exc).__name__}: {exc}")

            # ════════════ read-only: snapshot DEPOIS de tudo (fecha oráculo 4) ═
            try:
                depois = await _snapshot_nfse(db)
                assert antes == depois, f"nfse_emitidas_nacional mudou rodando a tool: antes={antes} depois={depois}"
            except Exception as exc:
                # se o oráculo 4 já tinha passado (RBAC), o read-only quebrando ainda derruba ele
                for i, (n, desc, ok, det) in enumerate(results):
                    if n == 4 and ok:
                        results[i] = (4, desc, False, f"{type(exc).__name__}: {exc}")
                        print(f"ORACULO 4 {desc} ... FAIL (read-only quebrou depois) — {exc}")

            # ══════════ MUTAÇÃO M1 — mistura CNPJ (deve derrubar oráculo 2) ══
            if resultado_2 is not None and n_patrimonial_real is not None:
                original = tfd._gerar_relatorio_nfse_doc

                async def _mut1_sem_filtro_empresa(db_, user_, scope_, *, empresa=None, competencia=None, **_kw):
                    tfd._gate(user_)
                    if not (empresa and str(empresa).strip()):
                        return tfd._recusa("sem empresa")
                    emp, recusa = await tfd._resolve_empresa(db_, str(empresa))
                    if recusa:
                        return recusa
                    # MUT: query IDÊNTICA, mas SEM `WHERE empresa_id = :eid` (mistura os 2 CNPJ)
                    rows = (await db_.execute(text(
                        "SELECT numero, competencia, tomador_nome, valor_servicos, iss_valor, cancelada "
                        "FROM nfse_emitidas_nacional ORDER BY competencia, data_emissao NULLS LAST, numero"
                    ))).mappings().all()
                    total_serv = sum(float(r["valor_servicos"] or 0) for r in rows)
                    total_iss = sum(float(r["iss_valor"] or 0) for r in rows)
                    return {
                        "arquivo_base64": base64.b64encode(b"%PDF-mut").decode(),
                        "nome": f"nfse_{emp.slug}.pdf",
                        "resumo": f"NFS-e Emitidas — escopado em {emp.razao_social} (CNPJ isolado): "
                                  f"{len(rows)} notas, valor {tfd._brl(total_serv)}, ISS {tfd._brl(total_iss)} "
                                  "— números reais (nfse_emitidas_nacional), doc INTERNO de gestão.",
                    }

                tfd._gerar_relatorio_nfse_doc = _mut1_sem_filtro_empresa
                try:
                    resultado_mut1 = await tfd._gerar_relatorio_nfse_doc(db, fiscal_user, None, empresa=_PATRIMONIAL_TERMO)
                finally:
                    tfd._gerar_relatorio_nfse_doc = original

                m1_ok, m1_det = await _expect_bite(lambda: _check_escopado_patrimonial(
                    resultado_mut1, n_patrimonial_real, n_total_real))
                record("MUTAÇÃO M1", "remove filtro empresa_id (mistura CNPJ) → oráculo 2", m1_ok, m1_det)
            else:
                record("MUTAÇÃO M1", "mistura CNPJ → oráculo 2", True, "PULADA (oráculo 2 falhou antes)")

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
    print(f"OK suite fase6-f8 ({n_pass}/{len(oraculos)} oráculos + {n_bite}/{len(mutacoes)} mutações) — GATE LIBERADO.")
    return 0


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    except Exception:
        traceback.print_exc()
        code = 2
    raise SystemExit(code)
