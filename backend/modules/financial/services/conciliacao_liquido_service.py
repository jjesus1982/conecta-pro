"""Conciliação por LÍQUIDO — casa créditos do banco (Inter 077 / Cora 403) com as NFS-e
emitidas pelo valor que REALMENTE cai na conta.

O que cai no banco NÃO é o valor de face da nota (bruto): sai ISS e retenções. O líquido
da nota (`valor_liquido`) é o alvo; quando o tomador retém INSS, o que cai é `valor_liquido
- inss_retido`. Casamos por esses alvos (±R$0,50) numa janela de data larga (pagamento entra
semanas depois da emissão). Só o match EXATO (C1) é elegível para persistir; identidade+valor
aproximado vira SUGESTÃO para revisão humana (nunca baixa sozinho).

persistir=False → só relatório (read-only). persistir=True → marca o crédito bancário
reconciliation_status='conciliado' + nota de auditoria vinculando à NFS-e. É bookkeeping:
NÃO move dinheiro e NÃO altera contas a receber.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta

from sqlalchemy import text

_JANELA_ANTES = 5     # dias antes da emissão
_JANELA_DEPOIS = 95   # dias depois (lag de pagamento)
_TOL_EXATO = 0.50     # R$ para considerar match exato (C1)
_TOL_FUZZY_PCT = 0.15 # faixa p/ SUGESTÃO quando a identidade do pagador bate

# CNPJ-aware: nota da Eletrônica (CNPJ1) é paga no Inter (077); nota da Patrimonial (CNPJ2)
# é paga no Cora (403). NÃO cruzar bancos. (Itaú PF fora — não é conta da empresa.)
_ELETRONICA = "619a3df1-8bce-49ce-b77a-04f80a0e8491"
_PATRIMONIAL = "7d79ed12-d480-4906-b2e0-2b2c4d299bab"
_BANCO_DA_EMPRESA = {_ELETRONICA: "077", _PATRIMONIAL: "403"}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9]", "", s)


def _pix_nome(desc: str) -> str:
    m = re.search(r"PIX RECEBIDO.*?-\s*([A-Za-z].*)$", desc or "")
    return _norm(m.group(1)) if m else ""


def _d(x):
    return x.date() if hasattr(x, "hour") else x


async def casar_notas_banco(db, inicio: str, fim: str, persistir: bool = False) -> dict:
    """Casa NFS-e (líquido) × créditos do banco no período [inicio, fim] (YYYY-MM-DD ou date)."""
    di = inicio if isinstance(inicio, date) else date.fromisoformat(str(inicio))
    df = fim if isinstance(fim, date) else date.fromisoformat(str(fim))
    notas = (await db.execute(text(
        "SELECT chave_acesso, tomador_nome, tomador_cnpj, valor_liquido, coalesce(inss_retido,0), data_emissao, "
        "coalesce(empresa_id::text,'') FROM nfse_emitidas_nacional "
        "WHERE data_emissao BETWEEN :a AND :b AND coalesce(valor_liquido,0)>0 "
        "ORDER BY valor_liquido DESC"), {"a": di, "b": df})).fetchall()
    creds = (await db.execute(text(
        "SELECT bt.id, bt.transaction_date, bt.amount, coalesce(bt.description,''), coalesce(bt.reconciliation_status,''), ba.bank_code "
        "FROM bank_transactions bt JOIN bank_accounts ba ON ba.id=bt.bank_account_id "
        "WHERE ba.bank_code IN ('077','403') AND bt.transaction_type IN ('credit','credito') "
        "AND bt.transaction_date BETWEEN :a AND :b"), {"a": di, "b": df})).fetchall()
    C = [{"id": str(c[0]), "date": _d(c[1]), "amt": float(c[2]), "desc": c[3],
          "nome": _norm(c[3]), "st": c[4], "bank": c[5], "used": False} for c in creds]

    casados, sugestoes, notas_sem = [], [], []
    tot_liq = 0.0
    for chave, tnome, tcnpj, vliq, inss, dt, empresa_id in notas:
        vliq = float(vliq); inss = float(inss); tot_liq += vliq
        dt = _d(dt); tnorm = _norm(tnome)
        alvos = [vliq] + ([round(vliq - inss, 2)] if inss > 0 else [])
        banco_ok = _BANCO_DA_EMPRESA.get(empresa_id, "077")  # Eletrônica→Inter, Patrimonial→Cora

        def _na_janela(c, _bk=banco_ok):
            return (c["bank"] == _bk and c["date"] is not None
                    and dt - timedelta(days=_JANELA_ANTES) <= c["date"] <= dt + timedelta(days=_JANELA_DEPOIS))

        # C1 — exato (±R$0,50) em qualquer alvo + janela: alta confiança → persiste
        best = None
        for c in C:
            if c["used"] or not _na_janela(c):
                continue
            diff = min(abs(c["amt"] - a) for a in alvos)
            if diff <= _TOL_EXATO and (best is None or diff < best[1]):
                best = (c, diff)
        if best:
            best[0]["used"] = True
            casados.append({"chave": chave, "cliente": tnome, "liquido": round(vliq, 2), "inss": round(inss, 2),
                            "credito_id": best[0]["id"], "credito_valor": best[0]["amt"],
                            "credito_data": str(best[0]["date"]), "diff": round(best[1], 2),
                            "banco": "Cora" if best[0]["bank"] == "403" else "Inter"})
            continue

        # Fuzzy — identidade do pagador (nome do PIX) bate + valor aproximado → SUGESTÃO (não persiste)
        sug = None
        for c in C:
            if c["used"] or not _na_janela(c):
                continue
            pn = _pix_nome(c["desc"])
            ident = (len(tnorm) >= 12 and tnorm[:12] in c["nome"]) or (len(pn) >= 12 and pn[:12] in tnorm)
            if not ident:
                continue
            diff = min(abs(c["amt"] - a) for a in alvos)
            if diff <= vliq * _TOL_FUZZY_PCT and (sug is None or diff < sug[1]):
                sug = (c, diff)
        if sug:
            sugestoes.append({"chave": chave, "cliente": tnome, "liquido": round(vliq, 2),
                              "credito_valor": sug[0]["amt"], "credito_data": str(sug[0]["date"]), "diff": round(sug[1], 2)})
        else:
            notas_sem.append({"chave": chave, "cliente": tnome, "liquido": round(vliq, 2), "emissao": str(dt)})

    aplicados = 0
    if persistir and casados:
        for m in casados:
            r = await db.execute(text(
                "UPDATE bank_transactions SET reconciliation_status='conciliado', reconciled_at=now(), "
                "reconciliation_note = coalesce(reconciliation_note,'') || :nota "
                "WHERE id::text = :cid AND coalesce(reconciliation_status,'') <> 'conciliado'"),
                {"nota": f" | conciliado por liquido c/ NFS-e {m['chave'] or '-'} ({m['cliente']}) R$ {m['liquido']:.2f}",
                 "cid": m["credito_id"]})
            aplicados += r.rowcount or 0
        await db.commit()

    val_cas = sum(m["liquido"] for m in casados)
    return {
        "casados": casados, "sugestoes": sugestoes, "notas_sem": notas_sem,
        "n_notas": len(notas), "n_casados": len(casados), "n_sugestoes": len(sugestoes), "n_sem": len(notas_sem),
        "liquido_total": round(tot_liq, 2), "liquido_casado": round(val_cas, 2),
        "pct_casado": round(val_cas / tot_liq * 100, 1) if tot_liq > 0 else 0.0,
        "aplicados": aplicados,
    }
