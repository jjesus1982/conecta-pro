"""Backfill do elo lead<->cliente: `leads.client_id` e `clients.lead_id`.

É o join da atribuição ("qual origem trouxe o cliente que mais paga"). Casa por:
  - telefone canônico (DDD + 8 últimos dígitos — `phone.match_key_br`);
  - e-mail;
  - documento (CNPJ/CPF): `leads` NÃO tem coluna de documento, então a ponte real é
    a proposta da oportunidade do lead (opportunities.lead_id -> proposals.client_document
    -> clients.document_number). Nunca por semelhança de nome (isso seria fabricar).

Grava SÓ em match ÚNICO nos dois sentidos (1 lead <-> 1 cliente). Ambíguo NÃO casa.
Idempotente: só preenche o que está NULL, re-rodar não muda nada.

Uso:  python3 scripts/backfill_lead_client_link.py [--dry-run|--selftest]
"""

import sys
from collections import defaultdict

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database.session import SyncSessionLocal  # noqa: E402
from modules.crm.services.phone import match_key_br  # noqa: E402

_SQL_DOC = """
SELECT DISTINCT o.lead_id, c.id
  FROM opportunities o
  JOIN proposals p ON p.opportunity_id = o.id
  JOIN clients   c ON regexp_replace(coalesce(c.document_number,''),'\\D','','g')
                    = regexp_replace(coalesce(p.client_document,''),'\\D','','g')
 WHERE o.lead_id IS NOT NULL AND c.ativo
   AND length(regexp_replace(coalesce(p.client_document,''),'\\D','','g')) >= 11
"""


def candidatos(db):
    """Gera (lead_id, client_id, motivo) — pares PLAUSÍVEIS, ainda sem gate de unicidade."""
    leads = db.execute(
        text("SELECT id, phone, lower(coalesce(email,'')) FROM leads WHERE coalesce(is_active,true)")
    ).all()
    clients = db.execute(
        text("SELECT id, phone, mobile, whatsapp, lower(coalesce(email,'')) FROM clients WHERE ativo")
    ).all()

    por_fone, por_email = defaultdict(set), defaultdict(set)
    for c in clients:
        for raw in (c[1], c[2], c[3]):
            k = match_key_br(raw)
            if k:
                por_fone[k].add(str(c[0]))
        if c[4]:
            por_email[c[4]].add(str(c[0]))

    for lead in leads:
        k = match_key_br(lead[1])
        for cid in por_fone.get(k, ()) if k else ():
            yield str(lead[0]), cid, "telefone"
        for cid in por_email.get(lead[2], ()) if lead[2] else ():
            yield str(lead[0]), cid, "email"

    for lid, cid in db.execute(text(_SQL_DOC)).all():
        yield str(lid), str(cid), "documento"


def unicos(pares):
    """Gate de unicidade (puro, testável). -> (casados, ambiguos).
    casados = [(lead_id, client_id, motivos)] só quando 1 lead <-> 1 cliente."""
    por_lead, por_cli, motivos = defaultdict(set), defaultdict(set), defaultdict(set)
    for lid, cid, mot in pares:
        por_lead[lid].add(cid)
        por_cli[cid].add(lid)
        motivos[(lid, cid)].add(mot)

    casados, ambiguos = [], []
    for lid, cids in sorted(por_lead.items()):
        if len(cids) != 1:
            ambiguos.append((lid, sorted(cids), f"lead casa com {len(cids)} clientes"))
            continue
        cid = next(iter(cids))
        if len(por_cli[cid]) != 1:
            ambiguos.append((lid, [cid], f"cliente casa com {len(por_cli[cid])} leads"))
            continue
        casados.append((lid, cid, "+".join(sorted(motivos[(lid, cid)]))))
    return casados, ambiguos


def _selftest():
    """Ambíguo NUNCA casa — a única regra que, se quebrar, corrompe dado."""
    c, a = unicos([("L1", "C1", "telefone"), ("L1", "C1", "email")])
    assert c == [("L1", "C1", "email+telefone")], c
    assert not a
    c, a = unicos([("L1", "C1", "telefone"), ("L1", "C2", "email")])  # lead -> 2 clientes
    assert c == [] and len(a) == 1, (c, a)
    c, a = unicos([("L1", "C1", "telefone"), ("L2", "C1", "telefone")])  # cliente <- 2 leads
    assert c == [] and len(a) == 2, (c, a)
    print("selftest OK")


def main(dry: bool) -> None:
    db = SyncSessionLocal()
    try:
        nomes = dict(db.execute(text("SELECT id::text, name FROM leads")).all())
        nomes.update(db.execute(text("SELECT id::text, name FROM clients")).all())
        casados, ambiguos = unicos(candidatos(db))

        total_leads = db.execute(text("SELECT count(*) FROM leads WHERE coalesce(is_active,true)")).scalar()
        gravados = 0
        for lid, cid, mot in casados:
            print(f"  CASA [{mot:<18}] {nomes.get(lid,'?')[:38]:<38} -> {nomes.get(cid,'?')[:40]}")
            if dry:
                continue
            r1 = db.execute(text("UPDATE leads SET client_id=:c WHERE id=:l AND client_id IS NULL"), {"c": cid, "l": lid})
            r2 = db.execute(text("UPDATE clients SET lead_id=:l WHERE id=:c AND lead_id IS NULL"), {"c": cid, "l": lid})
            gravados += max(r1.rowcount, r2.rowcount)
        if not dry:
            db.commit()

        for lid, cids, por in ambiguos:
            print(f"  AMBÍGUO (não casa): {nomes.get(lid,'?')[:38]:<38} — {por}: {[nomes.get(c,'?') for c in cids]}")

        sem_match = total_leads - len(casados) - len(ambiguos)
        print(
            f"\nleads ativos={total_leads} · casados={len(casados)} · ambíguos={len(ambiguos)} "
            f"· sem-match={sem_match} · linhas gravadas agora={gravados}{' (DRY-RUN)' if dry else ''}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        main("--dry-run" in sys.argv)
