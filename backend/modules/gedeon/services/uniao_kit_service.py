"""GEDEON — o kit é UM só: junta o que está no banco com o que está no Drive.

Medido em 19/08/2026, conferindo os kits de julho com a mesma régua dos dois lados:

    Ideal Flores    banco 74%   Drive 50%
      banco tem ponto, NFS-e e boleto que o Drive NÃO tem
      Drive tem 5 CNDs e o banco registrou 2

Não era número errado: eram duas COLEÇÕES diferentes. Os PDFs que o montador gera vivem em
`/app/uploads`, viram slot e nunca sobem ao Drive; os arquivos que os blocos do GEDEON põem
na pasta do condomínio nunca viram slot. O kit real sempre foi a união, e nenhuma das duas
telas mostrava isso — o Jordan conferia em dois lugares e via dois kits.

Mão dupla, e as duas direções são necessárias:
  A. slot com arquivo em disco  →  sobe para a pasta do condomínio (é o que o cliente recebe)
  B. arquivo na pasta           →  vira slot (é o que a completude e o painel enxergam)

Idempotente nas duas pontas: não sobe o que já está lá, não cria slot repetido.
"""

from __future__ import annotations

import logging
import os

from sqlalchemy import text

from modules.gdrive.services.gdrive_service import gdrive_service
from modules.gedeon.services.drive_kit_classifier import classify_filename
from modules.gedeon.services.kit_layout import (
    _arquivo_ja_existe,
    mes_kit_de_competencia,
    nome_pasta_condominio,
    pasta_kit_arquivo,
)

logger = logging.getLogger(__name__)

_RAIZ_UPLOADS = "/app/uploads"

_SQL_KITS = text(
    """
    SELECT k.id::text AS kit_id, g.name AS cond
      FROM ged_document_kits k
      JOIN ged_clients g ON g.id = k.client_id
     WHERE k.reference_month = CAST(:mes AS date)
     ORDER BY g.name
    """
)

_SQL_SLOTS = text(
    "SELECT document_type, document_name, file_path FROM ged_kit_documents "
    " WHERE kit_id = CAST(:kid AS uuid) AND coalesce(file_path,'') <> ''"
)

_SQL_TIPOS_DO_KIT = text(
    "SELECT document_type, coalesce(document_name,'') AS nome FROM ged_kit_documents  WHERE kit_id = CAST(:kid AS uuid)"
)

_SQL_INSERE_SLOT = text(
    "INSERT INTO ged_kit_documents (id, kit_id, document_type, document_name, file_path, "
    "  source_module, auto_generated, is_signed, created_at, updated_at) "
    "VALUES (gen_random_uuid(), CAST(:kid AS uuid), :dt, :dn, :fp, 'drive', true, false, NOW(), NOW())"
)


def _caminho_local(fp: str) -> str | None:
    """O slot guarda ora caminho absoluto, ora relativo a /app/uploads. Aceita os dois."""
    if not fp or fp.startswith("http"):
        return None
    p = fp if os.path.isabs(fp) else os.path.join(_RAIZ_UPLOADS, fp)
    return p if os.path.exists(p) else None


def _arquivos_do_kit_no_drive(cond: str, competencia: str) -> list[dict]:
    """Todos os arquivos das subpastas do kit daquele condomínio/mês."""
    svc = gdrive_service._service
    mes = mes_kit_de_competencia(competencia)
    raiz = (
        svc.files()
        .list(
            q=f"name='{nome_pasta_condominio(cond)}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
            fields="files(id)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
        .get("files", [])
    )
    if not raiz:
        return []
    pasta_mes = (
        svc.files()
        .list(
            q=f"name='{mes}' and '{raiz[0]['id']}' in parents and trashed=false",
            fields="files(id)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
        .get("files", [])
    )
    if not pasta_mes:
        return []
    out: list[dict] = []
    subs = (
        svc.files()
        .list(
            q=f"'{pasta_mes[0]['id']}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
            fields="files(id,name)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
        .get("files", [])
    )
    for sub in subs:
        arqs = (
            svc.files()
            .list(
                q=f"'{sub['id']}' in parents and trashed=false",
                fields="files(id,name,webViewLink,mimeType)",
                pageSize=300,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
            .get("files", [])
        )
        out += [a for a in arqs if not a["mimeType"].endswith("folder")]
    return out


def unir_kit_drive_banco(competencia: str, db, dry_run: bool = False) -> dict:
    """Junta as duas metades do kit, nas duas direções. Não faz commit — é do chamador."""
    from modules.gedeon.services.completude_slots import recalcular_competencia

    if not gdrive_service._service:
        gdrive_service.check_status()

    mes_ref = _mes_referencia(competencia)
    rel: dict = {
        "competencia": competencia,
        "mes_ref": mes_ref,
        "subiu_pro_drive": 0,
        "virou_slot": 0,
        "sem_classificacao": [],
        "por_kit": {},
        "falhas": 0,
    }
    cache: dict = {}

    for k in db.execute(_SQL_KITS, {"mes": mes_ref}).mappings().all():
        cond, kid = k["cond"], k["kit_id"]
        subiu = virou = 0
        try:
            # ── A. o que o banco tem e o Drive não ────────────────────────────
            for s in db.execute(_SQL_SLOTS, {"kid": kid}).mappings().all():
                local = _caminho_local(s["file_path"])
                if not local:
                    continue
                fn = s["document_name"] or os.path.basename(local)
                if not fn.lower().endswith(".pdf"):
                    fn += ".pdf"
                if dry_run:
                    subiu += 1
                    continue
                pasta = pasta_kit_arquivo(cond, competencia, fn, cache)
                if pasta and not _arquivo_ja_existe(pasta, fn):
                    if gdrive_service.fazer_upload_arquivo(local, pasta, fn):
                        subiu += 1

            # ── B. o que o Drive tem e o banco não ────────────────────────────
            ja_tem = {r["document_type"] for r in db.execute(_SQL_TIPOS_DO_KIT, {"kid": kid}).mappings()}
            nomes_no_kit = {r["nome"] for r in db.execute(_SQL_TIPOS_DO_KIT, {"kid": kid}).mappings()}
            for a in _arquivos_do_kit_no_drive(cond, competencia):
                slug, _escopo, _ = classify_filename(a["name"])
                if not slug:
                    rel["sem_classificacao"].append(a["name"][:60])
                    continue
                # Documento por condomínio: um por tipo basta. Por funcionário: um por nome.
                if slug in ja_tem and a["name"] in nomes_no_kit:
                    continue
                if slug in ja_tem and _escopo != "funcionario":
                    continue
                if dry_run:
                    virou += 1
                    continue
                db.execute(
                    _SQL_INSERE_SLOT,
                    {
                        "kid": kid,
                        "dt": slug,
                        "dn": a["name"],
                        "fp": a.get("webViewLink") or "",
                    },
                )
                ja_tem.add(slug)
                nomes_no_kit.add(a["name"])
                virou += 1
        except Exception as exc:  # noqa: BLE001 — um kit ruim não cala os outros seis
            rel["falhas"] += 1
            logger.warning("uniao do kit %s (%s): %s", cond, kid, exc)

        rel["subiu_pro_drive"] += subiu
        rel["virou_slot"] += virou
        if subiu or virou:
            rel["por_kit"][cond] = {"subiu": subiu, "virou_slot": virou}

    if not dry_run:
        recalcular_competencia(db, mes_ref)
    rel["sem_classificacao"] = sorted(set(rel["sem_classificacao"]))[:12]
    return rel


def _mes_referencia(competencia: str) -> str:
    """'07.2026' -> '2026-08-01'. O kit da competência X tem reference_month em X+1 —
    mesma convenção da pasta do Drive, que se chama pelo mês de ENTREGA."""
    m, a = int(competencia.split(".")[0]), int(competencia.split(".")[1])
    return f"{a + 1}-01-01" if m == 12 else f"{a}-{m + 1:02d}-01"
