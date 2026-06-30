"""GEDEON — registra os resultados da emissão de CND (robô) em ged_certidoes.
Roda no CONTAINER. Lê /app/uploads/cnd_results.jsonl (1 JSON por portal) + os PDFs,
e faz UPSERT por document_type (validade real, situação, caminho do PDF, alerta)."""

import datetime
import json
import os

from sqlalchemy import text

from core.database.session import get_sync_db

MAP = {
    "sefaz_am": ("certidao_negativa_estadual", "CND Estadual (SEFAZ-AM)", "SEFAZ-AM"),
    "cndt": ("certidao_negativa_trabalhista", "CNDT — Débitos Trabalhistas", "TST"),
    "prefeitura": ("certidao_negativa_municipal", "CND Municipal (Manaus)", "Prefeitura de Manaus"),
    "federal": ("certidao_negativa_federal", "CND Federal (RFB/PGFN)", "Receita Federal"),
    "caixa": ("certidao_negativa_fgts", "CRF — FGTS", "Caixa Econômica Federal"),
}


def _date(s):
    try:
        return datetime.datetime.strptime((s or "").strip(), "%d/%m/%Y").date()
    except Exception:
        return None


def main():
    path = "/app/uploads/cnd_results.jsonl"
    results = []
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if line:
                try:
                    results.append(json.loads(line))
                except Exception:
                    pass
    if not results:
        print("nenhum resultado p/ registrar")
        return

    with get_sync_db() as db:
        for r in results:
            info = MAP.get(r.get("portal"))
            if not info:
                continue
            dt, name, body = info
            if not r.get("ok"):
                print("pulado (não ok):", r.get("portal"), r.get("mensagem"))
                continue
            validade = _date(r.get("validade"))
            situacao = r.get("situacao")
            pdf = (r.get("pdf") or "").replace("/opt/conecta-pro/uploads", "/app/uploads")
            notes = json.dumps(
                {
                    "situacao": situacao,
                    "regular": r.get("regular"),
                    "numero": r.get("numero"),
                    "fonte": "emissão automática (Conecta PRO)",
                    "emitido_em": datetime.datetime.now().isoformat(),
                },
                ensure_ascii=False,
            )
            alerta = r.get("regular") is not True  # alerta se não-regular
            row = db.execute(
                text("SELECT id FROM ged_certidoes WHERE document_type=:dt LIMIT 1"), {"dt": dt}
            ).fetchone()
            if row:
                db.execute(
                    text(
                        "UPDATE ged_certidoes SET expiry_date=:v, issue_date=:i, file_path=:f, "
                        "notes=:n, issuing_body=:b, alerta_ativo=:a, updated_at=now() WHERE id=:id"
                    ),
                    {
                        "v": validade,
                        "i": datetime.date.today(),
                        "f": pdf,
                        "n": notes,
                        "b": body,
                        "a": alerta,
                        "id": row[0],
                    },
                )
            else:
                db.execute(
                    text(
                        "INSERT INTO ged_certidoes (id,name,document_type,issuing_body,issue_date,"
                        "expiry_date,file_path,notes,alerta_ativo,created_at,updated_at) VALUES "
                        "(gen_random_uuid(),:nm,:dt,:b,:i,:v,:f,:n,:a,now(),now())"
                    ),
                    {
                        "nm": name,
                        "dt": dt,
                        "b": body,
                        "i": datetime.date.today(),
                        "v": validade,
                        "f": pdf,
                        "n": notes,
                        "a": alerta,
                    },
                )
            print(f"registrado {dt}: {situacao} val={validade}")
        db.commit()

    # replica as CNDs reais nos kits do mês corrente (subpasta Impostos e Certidões)
    try:
        from modules.gedeon.services.cnd_kit_service import arquivar_cnds
        from modules.gedeon.services.kit_orchestrator import CONDOMINIOS_PADRAO

        h = datetime.date.today()
        m, a = (h.month - 1, h.year) if h.month > 1 else (12, h.year - 1)
        comp = f"{m:02d}.{a}"
        r = arquivar_cnds(comp, CONDOMINIOS_PADRAO, dry_run=False)
        print(f"kit {comp}: {r['replicas']} réplicas de CND")
    except Exception as exc:
        print("replicação no kit falhou (não crítico):", exc)


if __name__ == "__main__":
    main()
