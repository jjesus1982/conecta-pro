"""ENSAIO E2E MULTI-CNPJ — sweep de oráculos de todas as etapas (E1–E8).

Valida, sobre DADOS REAIS (leitura), que a virada do Grupo Conecta Mais está
íntegra: cadastro, contratos, funcionários/docs por competência, Cora
(cobrança/pagamento/webhook/conciliação), fiscal por empresa, kits/certidões,
dashboard consolidado. Fecha num veredito GO / NO-GO.

Uso (no container): PYTHONPATH=/app python scripts/ensaio_multicnpj.py
Nada é alterado. Cada checagem imprime OK/FALHA + evidência.
"""

import os
import re

import psycopg2
import psycopg2.extras

_URL = re.sub(r"\+asyncpg|\+psycopg2?", "", os.getenv("DATABASE_URL", ""))
ELET = "35710481000103"
PATR = "66014833000110"

_resultados: list[tuple[str, bool, str]] = []


def check(etapa: str, ok: bool, evidencia: str):
    _resultados.append((etapa, ok, evidencia))
    print(f"[{'OK ' if ok else 'FALHA'}] {etapa}: {evidencia}")


def _q(cur, sql, *a):
    cur.execute(sql, a if a else None)  # sem vars => None (evita interpretar % do LIKE)
    return cur.fetchall()


def main():
    conn = psycopg2.connect(_URL)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # E1 — cadastro das 2 empresas ativas e completas
    rows = _q(cur, "SELECT slug, cnpj, inscricao_municipal, regime_tributario, anexo_simples, "
                   "certificado_a1_path FROM empresas WHERE status='ativa' ORDER BY is_principal DESC")
    ok = (len(rows) == 2 and all(r["cnpj"] and r["inscricao_municipal"] and r["certificado_a1_path"] for r in rows))
    check("E1 cadastro", ok, f"{len(rows)} empresas ativas, CNPJ/IM/cert preenchidos")

    # E2 — contratos migrados (7 Patrimonial + 3 Eletrônica) com aditivos
    rows = _q(cur, "SELECT e.slug, count(*) n FROM contracts c JOIN empresas e ON e.id=c.empresa_id "
                   "WHERE c.status='active' GROUP BY e.slug")
    d = {r["slug"]: r["n"] for r in rows}
    adit = _q(cur, "SELECT count(*) n FROM contract_addendums WHERE addendum_number LIKE 'TRANSF-%'")[0]["n"]
    check("E2 contratos", d.get("conecta_patrimonial") == 7 and d.get("conecta_eletronica") == 3 and adit >= 7,
          f"Patrimonial={d.get('conecta_patrimonial')} Eletrônica={d.get('conecta_eletronica')} aditivos={adit}")

    # E3 — funcionários vigentes na Patrimonial; nenhum órfão; flip COMPLETO
    tot = _q(cur, "SELECT count(*) n, count(empresa_id) c FROM employees")[0]
    pat = _q(cur, "SELECT count(*) n FROM employees emp JOIN empresas e ON e.id=emp.empresa_id "
                  "WHERE e.slug='conecta_patrimonial' AND LOWER(emp.status::text) IN ('ativo','afastado_inss','suspenso')")[0]["n"]
    # CORREÇÃO (não só não-nulo): o flip moveu toda a força CLT ATIVA p/ a Patrimonial —
    # não pode sobrar nenhum CLT vigente na Eletrônica. PJ vigente na Eletrônica é OK e
    # ESPERADO (regra Jordan: "na Eletrônica só os PJ"). Prova a REGRA, não a presença.
    # (Não-vigentes na Patrimonial são OK: demitido pós-flip é correto.)
    elet_clt_vig = _q(cur, "SELECT count(*) n FROM employees emp JOIN empresas e ON e.id=emp.empresa_id "
                           "WHERE e.slug='conecta_eletronica' AND LOWER(emp.status::text) IN ('ativo','afastado_inss','suspenso') "
                           "AND COALESCE(LOWER(emp.tipo_contrato),'') <> 'pj'")[0]["n"]
    check("E3 funcionários", tot["n"] == tot["c"] and pat >= 50 and elet_clt_vig == 0,
          f"{tot['c']}/{tot['n']} com empresa; {pat} vigentes Patrimonial; {elet_clt_vig} CLT vigentes órfãos na Eletrônica")

    # E4 — Cora: conta registrada + extrato conciliado + webhooks
    conta = _q(cur, "SELECT account_number FROM bank_accounts WHERE bank_code='403'")
    tx = _q(cur, "SELECT count(*) n, count(*) FILTER (WHERE reconciliation_status='conciliado') c "
                 "FROM bank_transactions bt JOIN bank_accounts ba ON ba.id=bt.bank_account_id WHERE ba.bank_code='403'")[0]
    # CORREÇÃO (não só presença): exige que a conciliação de FATO tenha ocorrido em ao menos
    # um lançamento (tx.c>=1) — antes só se contava a existência de 8 linhas no extrato.
    check("E4 Cora conta+extrato", bool(conta) and tx["n"] >= 8 and tx["c"] >= 1,
          f"conta {conta[0]['account_number'] if conta else '—'}; {tx['n']} lançamentos, {tx['c']} conciliados")

    # E5 — NFS-e VIVAS por empresa (emissor deixou de ser implícito; canceladas excluídas)
    rows = _q(cur, "SELECT e.slug, count(*) n, COALESCE(sum(valor_servicos),0) v FROM nfse_emitidas_nacional n "
                   "JOIN empresas e ON e.id=n.empresa_id WHERE COALESCE(n.cancelada,FALSE)=FALSE GROUP BY e.slug")
    dn = {r["slug"]: (r["n"], float(r["v"])) for r in rows}
    # >=1: Patrimonial tem NFS-e própria (a segmentação por emissor existe). Robusto a
    # cancelamentos (nota cancelada não conta) — a contagem exata vai na evidência.
    check("E5 NFS-e por empresa", "conecta_patrimonial" in dn and dn["conecta_patrimonial"][0] >= 1,
          f"Eletrônica={dn.get('conecta_eletronica')} Patrimonial={dn.get('conecta_patrimonial')} (vivas)")

    # E6 — certidões por CNPJ (2 conjuntos, sem mascarar o CNPJ2)
    rows = _q(cur, "SELECT cnpj, count(*) n FROM ged_certidoes GROUP BY cnpj")
    dc = {r["cnpj"]: r["n"] for r in rows}
    check("E6 certidões por CNPJ", ELET in dc and PATR in dc,
          f"Eletrônica={dc.get(ELET)} Patrimonial={dc.get(PATR)}")

    # E5b — checkpoint NSU por empresa
    rows = _q(cur, "SELECT count(distinct empresa_id) n FROM fiscal_nsu_checkpoint")
    check("E5 NSU por empresa", rows[0]["n"] >= 2, f"{rows[0]['n']} checkpoints de NSU")

    conn.close()

    # E4b — adapter Cora vivo (auth + saldo) e webhooks registrados
    try:
        import asyncio
        from modules.integrations.banking.adapters.cora import CoraAdapter

        async def _cora():
            a = CoraAdapter(); await a.authenticate()
            s = await a.get_balance()
            import httpx
            async with a._client() as cli:
                r = await cli.get("/endpoints/", headers=a._auth_headers())
                eps = r.json() if r.status_code == 200 else []
            return float(s.available), len(eps)
        saldo, eps = asyncio.run(_cora())
        check("E4 Cora API viva", saldo >= 0 and eps >= 1, f"saldo R${saldo:,.2f}; {eps} webhooks registrados")
    except Exception as e:  # noqa: BLE001
        check("E4 Cora API viva", False, f"erro: {e}")

    # E8 — branding por competência (F1 anti-reescrita)
    try:
        from modules.crm.services.pdf_branding import empresa_branding
        os.environ.setdefault("MULTICNPJ_FRONTEIRA_COMPETENCIA", "2026-07")
        jun = empresa_branding("conecta_patrimonial", "2026-06")["cnpj"]
        jul = empresa_branding("conecta_patrimonial", "2026-07")["cnpj"]
        check("E8 anti-reescrita", jun == "35.710.481/0001-03" and jul == "66.014.833/0001-10",
              f"junho={jun} julho={jul}")
    except Exception as e:  # noqa: BLE001
        check("E8 anti-reescrita", False, f"erro: {e}")

    # ── veredito ──
    print("\n" + "=" * 60)
    falhas = [r for r in _resultados if not r[1]]
    print(f"ENSAIO MULTI-CNPJ: {len(_resultados) - len(falhas)}/{len(_resultados)} oráculos OK")
    if falhas:
        print("VEREDITO: NO-GO — pendências:")
        for etapa, _ok, ev in falhas:
            print(f"  - {etapa}: {ev}")
        raise SystemExit(1)
    print("VEREDITO: GO ✅ — virada íntegra sobre dados reais")


if __name__ == "__main__":
    main()
