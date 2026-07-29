"""SUITE-ORÁCULO da Fase 5.6b (análise read-only de contrato + consultor jurídico
que a usa) — prova formal, executável e MUTAÇÃO-TESTADA de que as invioláveis da
análise de contrato seguram, e de que a suite MORDE se alguém regredir. Molde:
`test_oraculos_5_6a_anomalia.py` (standalone, sem pytest, `sys.exit(!=0)` em falha,
mutação embutida via substituição da função real por uma mutante).

Componentes sob prova (BT1 commit cbe40aea, BT2 desta sessão):
  - `modules/ai/contract_analysis/services/analise_contrato.py::analisar(texto)` —
    análise PURA (regex+scoring), read-only, sem banco, sem LLM. Nunca fabrica:
    campo sem match no texto = vazio/None, nunca inventado.
  - `modules/juridico/contracts_controller.py::analise` — rota
    `GET /juridico/contratos/{id}/analise`: lê o texto real (obter_texto_contrato),
    roda `analisar`, gated por `get_current_active_user` (exige autenticação).

Os 3 oráculos:
  1. Read-only — rodar `analisar` + a rota do controller NÃO altera o contrato:
     a linha em `contracts` (todas as colunas) é idêntica ANTES e DEPOIS.
  2. Nunca-fabricar — texto SEM CNPJ/CPF ⇒ `partes.contractor_document` e
     `partes.contracted_document` vazios E nenhum CNPJ (padrão XX.XXX.XXX/XXXX-XX)
     ou CPF aparece em qualquer lugar do resultado. Não inventa documento.
  3. Gate — a rota exige usuário autenticado: `get_current_active_user` (o guard
     real que a rota declara) barra id inexistente e deixa passar usuário ativo.

MUTAÇÃO-TESTE (prova que a suite morde; molde 5.6a):
  M1 — `analisar` mutado p/ FABRICAR um CNPJ quando o texto não tem nenhum
       (preenche `partes.contractor_document` com um valor inventado) → oráculo 2
       (nunca-fabricar) deve FALHAR.
Se a mutação NÃO derrubar o oráculo 2, o oráculo é fraco.

Bancada: este arquivo roda DENTRO de um container THROWAWAY (imagem
conecta-pro-backend) anexado à rede `conecta-pro_conecta-pro-network`, com
`DATABASE_URL` apontando pro Postgres real via nome do container
(`conecta-pro-postgres`) — NUNCA o backend vivo/green:8080. Insere UM contrato
sentinela (marcador `__TESTE_5.6b__` no contract_number/name) só p/ o oráculo 1;
limpeza cirúrgica por id no finally — 0 remanescentes, NUNCA apaga contrato real.
Exit 0 só se os 3 oráculos PASS E a mutação MORDER.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import traceback
import uuid
from datetime import date

sys.path.insert(0, "/app")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker as sync_sessionmaker  # noqa: E402

MARK = "__TESTE_5.6b__"
CNPJ_RE = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")
CPF_RE = re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}")

# Texto COM dois CNPJs (contrato sentinela do oráculo 1 — read-only não depende disso).
TEXTO_COM_CNPJ = (
    "CONTRATO DE PRESTAÇÃO DE SERVIÇOS DE PORTARIA.\n"
    "CONTRATANTE: CONDOMINIO EXEMPLO, CNPJ 11.222.333/0001-44.\n"
    "CONTRATADO: CONECTAMAIS PATRIMONIAL LTDA, CNPJ 66.014.833/0001-10.\n"
    "CLÁUSULA 1 - DO OBJETO: prestação de serviços de agentes de portaria.\n"
    "CLÁUSULA 2 - DO VALOR: R$ 10.000,00 mensais.\n"
    "CLÁUSULA 3 - DA MULTA: multa de 50% em caso de rescisão antecipada.\n"
    "CLÁUSULA 4 - DA RENOVAÇÃO: renovação automática por iguais períodos.\n"
)

# Texto SEM qualquer CNPJ/CPF (oráculo 2 + mutação). Nenhum número no padrão de documento.
TEXTO_SEM_CNPJ = (
    "CONTRATO DE PRESTAÇÃO DE SERVIÇOS DE PORTARIA.\n"
    "As partes ajustam a prestação de serviços de agentes de portaria.\n"
    "CLÁUSULA PRIMEIRA - DO OBJETO: portaria e controle de acesso.\n"
    "CLÁUSULA SEGUNDA - DO PRAZO: doze meses, com renovação automática.\n"
    "CLÁUSULA TERCEIRA - DA MULTA: multa por rescisão antecipada.\n"
)


async def main() -> int:
    results: list[tuple[object, str, bool, str]] = []

    def record(n, desc: str, ok: bool, detail: str = "") -> None:
        results.append((n, desc, ok, detail))
        tag = "PASS" if ok else "FAIL"
        rot = f"ORACULO {n}" if isinstance(n, int) else str(n)
        print(f"{rot} {desc} ... {tag}{(' — ' + detail) if detail else ''}")

    eng = create_async_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    Session = async_sessionmaker(eng, expire_on_commit=False)
    # a rota `analise` usa internamente uma sessão SÍNCRONA (obter_texto_contrato);
    # engine sync separado só p/ exercitar o controller como em produção.
    sync_eng = create_engine(os.environ["DATABASE_URL"].replace("+asyncpg", ""), pool_pre_ping=True)
    SyncSession = sync_sessionmaker(sync_eng, expire_on_commit=False)

    contrato_sentinela: uuid.UUID | None = None

    async with Session() as db:
        try:
            from modules.ai.contract_analysis.services.analise_contrato import analisar
            from modules.juridico import contracts_controller as ctrl
            from core.auth import dependencies as authdep

            # identidade REAL p/ o gate (qualquer usuário ativo)
            user_ativo = (await db.execute(text(
                "SELECT id::text FROM users WHERE coalesce(is_active,true)=true LIMIT 1"))).scalar()
            assert user_ativo, "esperado >=1 usuário ativo real p/ o oráculo 3"
            user_row = (await db.execute(text(
                "SELECT id::text FROM users WHERE id::text = :i"), {"i": user_ativo})).scalar()

            client_id = (await db.execute(text(
                "SELECT id::text FROM clients LIMIT 1"))).scalar()
            assert client_id, "esperado >=1 client real (FK do contrato sentinela)"

            # ── contrato SENTINELA (só p/ o oráculo 1 read-only) ─────────
            contrato_sentinela = uuid.uuid4()
            await db.execute(text(
                "INSERT INTO contracts (id, contract_number, client_id, name, content, "
                " start_date, status) VALUES "
                "(:id, :num, :cli, :nome, :content, :sd, 'active')"),
                {"id": contrato_sentinela, "num": f"{MARK}-001", "cli": client_id,
                 "nome": f"{MARK} contrato sentinela", "content": TEXTO_COM_CNPJ,
                 "sd": date(2026, 1, 1)})
            await db.commit()

            # snapshot ANTES (linha inteira, via row_to_json — pega toda coluna)
            snap_antes = (await db.execute(text(
                "SELECT row_to_json(c) FROM contracts c WHERE id = :id"),
                {"id": contrato_sentinela})).scalar()

            # ════════════════ ORÁCULO 1 — READ-ONLY ════════════════════════
            try:
                # exercita a análise pura...
                res_pura = await analisar(TEXTO_COM_CNPJ)
                assert res_pura.get("clausulas"), "análise deveria achar cláusulas no texto sentinela"
                # ...e a ROTA (controller), que lê o texto real e roda a análise.
                class _U:  # usuário mínimo p/ satisfazer a assinatura da rota
                    id = user_ativo
                with SyncSession() as sdb:
                    res_rota = await ctrl.analise(
                        contrato_id=str(contrato_sentinela), db=sdb, current_user=_U())
                assert res_rota["id"] == str(contrato_sentinela)
                snap_depois = (await db.execute(text(
                    "SELECT row_to_json(c) FROM contracts c WHERE id = :id"),
                    {"id": contrato_sentinela})).scalar()
                assert snap_antes == snap_depois, "linha em contracts MUDOU (análise não é read-only)"
                record(1, "analisar + rota não alteram o contrato (linha contracts antes==depois)",
                       True, "0 diffs na linha após análise pura + rota")
            except Exception as exc:
                record(1, "read-only (contrato intocado)", False, f"{type(exc).__name__}: {exc}")

            # ════════════════ ORÁCULO 2 — NUNCA FABRICAR ═══════════════════
            try:
                await _oraculo_2_nunca_fabricar(analisar, TEXTO_SEM_CNPJ)
                record(2, "texto sem CNPJ → documentos vazios, nenhum CNPJ/CPF fabricado",
                       True, "partes.*_document vazios; 0 padrões de documento no resultado")
            except Exception as exc:
                record(2, "nunca fabricar (documento inventado sem match no texto)", False,
                       f"{type(exc).__name__}: {exc}")

            # ════════════════ ORÁCULO 3 — GATE (autenticação) ══════════════
            try:
                # a rota declara `get_current_active_user` como guard
                sig = __import__("inspect").signature(ctrl.analise)
                dep = sig.parameters["current_user"].default.dependency
                assert dep is authdep.get_current_active_user, "rota não usa o guard esperado"
                # guard real: id inexistente é barrado (404), usuário ativo passa
                barrado = False
                try:
                    await authdep.get_current_active_user(user_id=str(uuid.uuid4()), db=db)
                except HTTPException as exc:
                    barrado = exc.status_code in (401, 404)
                assert barrado, "usuário inexistente deveria ser barrado pelo guard"
                passou = await authdep.get_current_active_user(user_id=user_row, db=db)
                assert str(passou.id) == str(user_row), "usuário ativo deveria passar no guard"
                record(3, "rota exige autenticação (get_current_active_user barra id inexistente)",
                       True, "guard real barra id inexistente, deixa passar usuário ativo")
            except Exception as exc:
                record(3, "gate de autenticação da rota", False, f"{type(exc).__name__}: {exc}")

            # ════════════════ MUTAÇÃO M1 — a suite MORDE? ══════════════════
            async def _analisar_MUT_fabrica(texto: str) -> dict:
                an = await analisar(texto)  # real
                partes = an.setdefault("partes", {})
                if not partes.get("contractor_document"):
                    partes["contractor_document"] = "12.345.678/0001-99"  # FABRICADO
                return an

            m1_ok, m1_det = await _expect_bite(
                lambda: _oraculo_2_nunca_fabricar(_analisar_MUT_fabrica, TEXTO_SEM_CNPJ))
            record("MUTAÇÃO M1", "analisar fabrica CNPJ ausente → oráculo 2", m1_ok, m1_det)

        finally:
            await db.rollback()
            if contrato_sentinela is not None:
                await db.execute(text(
                    "DELETE FROM contracts WHERE id = :id"), {"id": contrato_sentinela})
            # rede de segurança: qualquer contrato com o marcador literal que tenha escapado
            await db.execute(text(
                "DELETE FROM contracts WHERE strpos(coalesce(contract_number,''), :m) > 0 "
                "OR strpos(coalesce(name,''), :m) > 0"), {"m": MARK})
            await db.commit()
            rem = int((await db.execute(text(
                "SELECT count(*) FROM contracts WHERE strpos(coalesce(contract_number,''), :m) > 0 "
                "OR strpos(coalesce(name,''), :m) > 0"), {"m": MARK})).scalar() or 0)
            if rem == 0:
                print("\nLIMPEZA OK — 0 contratos sentinela remanescentes")
            else:
                print(f"\nLIMPEZA FALHOU — remanescentes: {rem}")
            record("LIMPEZA", "0 remanescentes do que a suite criou", rem == 0, f"total={rem}")

    await eng.dispose()
    sync_eng.dispose()

    oraculos = [r for r in results if isinstance(r[0], int)]
    mutacoes = [r for r in results if isinstance(r[0], str) and r[0].startswith("MUTAÇÃO")]
    limpeza = [r for r in results if r[0] == "LIMPEZA"]
    n_pass = sum(1 for r in oraculos if r[2])
    n_bite = sum(1 for r in mutacoes if r[2])
    print("\n" + "═" * 68)
    print(f"RESUMO: {n_pass}/{len(oraculos)} oráculos PASS  |  "
          f"{n_bite}/{len(mutacoes)} mutações MORDERAM  |  "
          f"limpeza {'OK' if limpeza and limpeza[0][2] else 'FALHOU'}")
    falhas = [r for r in results if not r[2]]
    if falhas:
        print("FALHAS (findings — é o gate mordendo, NÃO ajustar o teste):")
        for n, desc, _ok, det in falhas:
            print(f"  ✗ {n} {desc} — {det}")
        print("═" * 68 + "\nGATE: BLOQUEADO.")
        return 1
    print("═" * 68)
    print(f"OK suite 5.6b ({n_pass}/{len(oraculos)} oráculos + {n_bite}/{len(mutacoes)} mutação) — GATE LIBERADO.")
    return 0


# ───────────────────────── oráculo reutilizável (p/ mutação) ────────────────

async def _oraculo_2_nunca_fabricar(analisar_fn, texto_sem_cnpj: str) -> None:
    """Nunca fabricar. Testado contra `analisar_fn` (real = analisar; mutado =
    fabrica CNPJ ausente → deve derrubar este oráculo)."""
    an = await analisar_fn(texto_sem_cnpj)
    partes = an.get("partes") or {}
    assert not partes.get("contractor_document"), (
        f"documento do contratante fabricado sem match no texto: {partes.get('contractor_document')!r}")
    assert not partes.get("contracted_document"), (
        f"documento do contratado fabricado sem match no texto: {partes.get('contracted_document')!r}")
    blob = json.dumps(an, default=str, ensure_ascii=False)
    assert not CNPJ_RE.search(blob), "CNPJ fabricado apareceu no resultado (texto não tinha nenhum)"
    assert not CPF_RE.search(blob), "CPF fabricado apareceu no resultado (texto não tinha nenhum)"


async def _expect_bite(coro_factory):
    """A mutação MORDE se o oráculo (async) FALHA sob ela."""
    try:
        await coro_factory()
    except AssertionError as exc:
        return True, f"mordeu ({type(exc).__name__}: {exc})"
    except Exception as exc:  # noqa: BLE001
        return True, f"mordeu ({type(exc).__name__}: {exc})"
    return False, "NÃO mordeu — oráculo passou sob mutação (oráculo FRACO!)"


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    except Exception:
        traceback.print_exc()
        code = 2
    raise SystemExit(code)
