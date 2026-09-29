"""Reconcilia os kits de AGOSTO com o roster por condomínio. ENSAIO por padrão.

    python3 reconciliar_kit_agosto.py             # só relata, não escreve nada
    python3 reconciliar_kit_agosto.py --aplicar   # remove os vínculos indevidos
    python3 reconciliar_kit_agosto.py --aplicar --so "MIRANTE"   # um condomínio só

Confirmado pelo Jordan em 28/09/2026: kit individual por condomínio, competência agosto,
população de `roster_kit_agosto_por_condominio.py` (8 condomínios, 56 pessoas).

## O que ele faz e o que NÃO faz

**Faz:** tira do kit de um condomínio o vínculo de quem não trabalhou lá em agosto. É
`ged_kit_documents`, a tabela de VÍNCULO — o PDF no disco não é tocado, e o documento continua
existindo para a pessoa.

**Não faz:** não apaga arquivo, não cria documento, não pede assinatura. Cada uma dessas é um
ato distinto e cada uma merece a própria decisão.

⚠️ Guarda tudo em `ged_kit_documents_removidos_<data>` antes de remover, e confere por LEITURA
POSTERIOR — a linha «DELETE n» do driver não é prova. Já custou caro nesta casa acreditar nela.

⭐ Por que remover e não regerar em cima: o vínculo errado é o defeito que a Pyetra viu («salvei
o Kit do Mirante e veio informação do Fiori»). Regerar acrescenta o certo e **deixa o errado
lá** — foi assim que 1.952 vínculos indevidos se acumularam.
"""

import os
import re
import sys
import unicodedata
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database.session import get_sync_db  # noqa: E402

COMP = "2026-08-01"
CASA = "CONECTAMAIS ELETRONICA LTDA"
#: kits que NÃO são de condomínio de cliente — ficam fora da reconciliação, de propósito.
NAO_CLIENTE = ("CONECTA VILLAGE", "CONECTA MAIS", "CONECTAMAIS", "PATRIMONIAL", "VEGA MANAUS")
BACKUP = f"ged_kit_documents_removidos_{date.today():%Y%m%d}_recon"


def canon(nome: str) -> str:
    s = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode().upper()
    s = re.sub(r"\b(CONDOMINIO|RESIDENCIAL|COND|EDIFICIO|DO|DA|DE|DOS|DAS|CIDADE|VILLAGE)\b", " ", s)
    s = re.sub(r"[^A-Z0-9]+", " ", s).strip()
    return re.sub(r"\s+", " ", s)


def _roster(db) -> dict[str, set[str]]:
    """Delega ao roster — FONTE ÚNICA em `roster_kit_agosto_por_condominio.py`.

    A cópia local que existia aqui usava alocação + escala, e o Green Hills provou as duas
    erradas: a alocação do RILEM diz `data_inicio = 01/01/2026` num condomínio que abriu em
    01/09, e a escala perde quem bateu sem turno lançado. A regra mudou TRÊS vezes em um dia;
    duas cópias teriam divergido na primeira.
    """
    from roster_kit_agosto_por_condominio import roster_por_condominio

    por_cond, _ = roster_por_condominio(db)
    return {canon(c): eids for c, eids in por_cond.items()}


def main() -> None:
    aplicar = "--aplicar" in sys.argv
    so = None
    if "--so" in sys.argv:
        so = canon(sys.argv[sys.argv.index("--so") + 1])

    with get_sync_db() as db:
        roster = _roster(db)
        kits = db.execute(
            text(
                "SELECT g.id::text AS kid, coalesce(cd.name, cd2.nome, gc.name, '?') AS cond "
                "  FROM ged_document_kits g "
                "  LEFT JOIN condominiums cd ON cd.id=g.client_id "
                "  LEFT JOIN condominios  cd2 ON cd2.id=g.client_id "
                "  LEFT JOIN ged_clients  gc ON gc.id=g.client_id "
                " WHERE g.reference_month=:c"
            ),
            {"c": COMP},
        ).mappings().all()

        plano: list[tuple[str, str, str, str]] = []  # (cond, kid, eid, nome)
        pulados: list[str] = []
        for k in kits:
            nome_cond = k["cond"]
            if any(t in nome_cond.upper() for t in NAO_CLIENTE):
                pulados.append(nome_cond)
                continue
            ck = canon(nome_cond)
            if so and ck != so:
                continue
            esperados = roster.get(ck)
            if esperados is None:
                # Condomínio com kit e SEM roster: não adivinha. Falha ABERTO para o humano.
                print(f"⚠️ «{nome_cond}» tem kit e não casou com nenhum condomínio do roster — "
                      f"NADA foi tocado nele. Confira o nome antes de qualquer remoção.")
                continue
            no_kit = db.execute(
                text(
                    "SELECT DISTINCT k.employee_id::text AS eid, e.nome "
                    "  FROM ged_kit_documents k JOIN employees e ON e.id=k.employee_id "
                    " WHERE k.kit_id = :kid AND k.employee_id IS NOT NULL"
                ),
                {"kid": k["kid"]},
            ).mappings().all()
            sobra = [(r["eid"], r["nome"]) for r in no_kit if r["eid"] not in esperados]
            falta = esperados - {r["eid"] for r in no_kit}
            print(f"\n{nome_cond}")
            print(f"  no kit: {len(no_kit)} · roster: {len(esperados)} · "
                  f"a REMOVER: {len(sobra)} · a ACRESCENTAR: {len(falta)}")
            for eid, nome in sorted(sobra, key=lambda x: x[1]):
                print(f"    − {nome}")
                plano.append((nome_cond, k["kid"], eid, nome))
            for eid in falta:
                n = db.execute(text("SELECT nome FROM employees WHERE id::text=:e"), {"e": eid}).scalar()
                print(f"    + {n}  (documento precisa ser GERADO — não removo nada por isto)")

        print(f"\nkits fora da reconciliação (não são condomínio de cliente): {len(pulados)}")
        for p in sorted(set(pulados)):
            print(f"  · {p}")

        n_linhas = 0
        if plano:
            alvo = [(p[1], p[2]) for p in plano]
            n_linhas = db.execute(
                text(
                    "SELECT count(*) FROM ged_kit_documents "
                    " WHERE (kit_id::text, employee_id::text) IN "
                    "   (SELECT * FROM unnest(CAST(:k AS text[]), CAST(:e AS text[])))"
                ),
                {"k": [a[0] for a in alvo], "e": [a[1] for a in alvo]},
            ).scalar() or 0

        print(f"\n{'APLICANDO' if aplicar else 'ENSAIO'}: "
              f"{len(plano)} vínculo(s) pessoa×kit → {n_linhas} linha(s) de documento")
        if not aplicar:
            print("Nada foi escrito. Rode com --aplicar para efetivar.")
            return
        if not plano:
            print("Nada a fazer.")
            return

        alvo = [(p[1], p[2]) for p in plano]
        par = {"k": [a[0] for a in alvo], "e": [a[1] for a in alvo]}
        db.execute(
            text(
                f"CREATE TABLE IF NOT EXISTS {BACKUP} AS "  # noqa: S608 — nome de constante do módulo
                "SELECT *, now() AS removido_em FROM ged_kit_documents WHERE false"
            )
        )
        db.execute(
            text(
                f"INSERT INTO {BACKUP} "  # noqa: S608
                "SELECT *, now() FROM ged_kit_documents "
                " WHERE (kit_id::text, employee_id::text) IN "
                "  (SELECT * FROM unnest(CAST(:k AS text[]), CAST(:e AS text[])))"
            ),
            par,
        )
        guardadas = db.execute(text(f"SELECT count(*) FROM {BACKUP}")).scalar() or 0  # noqa: S608
        assert guardadas >= n_linhas, (
            f"o backup guardou {guardadas} e eu ia remover {n_linhas} — ABORTADO antes de "
            "apagar. Remoção sem cópia de volta não acontece nesta casa."
        )
        db.execute(
            text(
                "DELETE FROM ged_kit_documents "
                " WHERE (kit_id::text, employee_id::text) IN "
                "  (SELECT * FROM unnest(CAST(:k AS text[]), CAST(:e AS text[])))"
            ),
            par,
        )
        db.commit()

        # PROVA POR LEITURA POSTERIOR — «DELETE n» não é prova.
        sobrou = db.execute(
            text(
                "SELECT count(*) FROM ged_kit_documents "
                " WHERE (kit_id::text, employee_id::text) IN "
                "  (SELECT * FROM unnest(CAST(:k AS text[]), CAST(:e AS text[])))"
            ),
            par,
        ).scalar() or 0
        print(f"backup em {BACKUP}: {guardadas} linha(s)")
        print(f"conferido por leitura: restaram {sobrou} (tem de ser 0)")
        assert sobrou == 0, "a remoção não se confirmou na leitura posterior"


if __name__ == "__main__":
    main()
