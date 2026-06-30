"""GEDEON — Arquiva as CNDs REAIS (emitidas pelo Conecta PRO) nos kits.

As CNDs são empresa-wide (iguais p/ todos os condomínios). Pega os PDFs emitidos
(ged_certidoes.file_path, válidos) e replica na subpasta "3. Impostos e Certidões"
de cada condomínio. Substitui a replicação antiga do kit de referência.
"""

from __future__ import annotations

import logging
import os

from sqlalchemy import text

from modules.gdrive.services.gdrive_service import gdrive_service
from modules.gedeon.services.kit_layout import _arquivo_ja_existe, pasta_kit_arquivo

logger = logging.getLogger(__name__)

# document_type → nome do arquivo no kit
CND_NOMES = {
    "certidao_negativa_estadual": "CND Estadual (SEFAZ-AM).pdf",
    "certidao_negativa_trabalhista": "CND Trabalhista (CNDT).pdf",
    "certidao_negativa_municipal": "CND Municipal (Manaus).pdf",
    "certidao_negativa_federal": "CND Federal (RFB-PGFN).pdf",
    "certidao_negativa_fgts": "CRF FGTS (Caixa).pdf",
}


def arquivar_cnds(competencia: str, condominios: list[str], dry_run: bool = False) -> dict:
    """Replica as CNDs emitidas (com PDF e válidas) nos kits de cada condomínio."""
    from core.database.session import get_sync_db

    if not gdrive_service._service:
        gdrive_service.check_status()
    rel = {"competencia": competencia, "cnds": [], "replicas": 0, "sem_pdf": []}

    with get_sync_db() as db:
        rows = db.execute(
            text(
                "SELECT document_type, file_path, expiry_date FROM ged_certidoes "
                "WHERE document_type = ANY(:dts) AND file_path IS NOT NULL"
            ),
            {"dts": list(CND_NOMES.keys())},
        ).fetchall()

    for document_type, file_path, expiry in rows:
        fn = CND_NOMES.get(document_type)
        if not fn or not file_path or not os.path.exists(file_path):
            rel["sem_pdf"].append(document_type)
            continue
        rel["cnds"].append(fn)
        if dry_run:
            continue
        for cond in condominios:
            folder = pasta_kit_arquivo(cond, competencia, fn)  # subpasta "3. Impostos e Certidões"
            if folder and not _arquivo_ja_existe(folder, fn):
                if gdrive_service.fazer_upload_arquivo(file_path, folder, fn):
                    rel["replicas"] += 1
    return rel
