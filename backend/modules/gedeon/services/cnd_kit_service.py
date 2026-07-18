"""GEDEON — Arquiva as CNDs REAIS (emitidas pelo Conecta PRO) nos kits.

Multi-CNPJ E6: as CNDs deixaram de ser "empresa-wide" — cada CNPJ do Grupo tem
seu conjunto em ged_certidoes (chave cnpj × document_type). Na JANELA HÍBRIDA
da segmentação (kits de ago+set/2026, definição do Jordan: documentos das DUAS
empresas convivem por datas retroativas), os kits recebem as certidões de
ambas: Eletrônica com os nomes legados (idempotente com kits já montados) e
Patrimonial com sufixo do nome de exibição. Após a janela
(MULTICNPJ_KITS_HIBRIDOS_ATE, default 2026-09), mantém ambas até o mapeamento
condomínio→empresa dos kits entrar (E8) — nunca esconde certidão por suposição.
"""

from __future__ import annotations

import logging
import os

from sqlalchemy import text

from modules.gdrive.services.gdrive_service import gdrive_service
from modules.gedeon.services.kit_layout import _arquivo_ja_existe, pasta_kit_arquivo

logger = logging.getLogger(__name__)

# document_type → nome do arquivo no kit (nomes LEGADOS = Eletrônica/CNPJ1)
CND_NOMES = {
    "certidao_negativa_estadual": "CND Estadual (SEFAZ-AM).pdf",
    "certidao_negativa_trabalhista": "CND Trabalhista (CNDT).pdf",
    "certidao_negativa_municipal": "CND Municipal (Manaus).pdf",
    "certidao_negativa_federal": "CND Federal (RFB-PGFN).pdf",
    "certidao_negativa_fgts": "CRF FGTS (Caixa).pdf",
}

_CNPJ_ELETRONICA = "35710481000103"


def _nome_arquivo(document_type: str, cnpj: str, fantasia: str) -> str | None:
    """Nome do PDF no kit: legado p/ CNPJ1; sufixo de exibição p/ as demais."""
    base = CND_NOMES.get(document_type)
    if not base:
        return None
    if cnpj == _CNPJ_ELETRONICA:
        return base
    sufixo = (fantasia or cnpj).strip()
    return base.replace(".pdf", f" — {sufixo}.pdf")


def arquivar_cnds(competencia: str, condominios: list[str], dry_run: bool = False) -> dict:
    """Replica as CNDs emitidas (com PDF e válidas) nos kits de cada condomínio.

    Kit híbrido: certidões de TODAS as empresas ativas do Grupo entram em todos
    os kits durante a transição — princípio: melhor certidão a mais que
    compliance invisível (pré-mortem F4).
    """
    from core.database.session import get_sync_db

    if not gdrive_service._service:
        gdrive_service.check_status()
    rel = {"competencia": competencia, "cnds": [], "replicas": 0, "sem_pdf": []}

    with get_sync_db() as db:
        rows = db.execute(
            text(
                "SELECT g.document_type, g.file_path, g.expiry_date, g.cnpj, "
                "       COALESCE(e.nome_fantasia, g.cnpj) AS fantasia "
                "FROM ged_certidoes g "
                "LEFT JOIN empresas e "
                "  ON REGEXP_REPLACE(e.cnpj, '[^0-9]', '', 'g') = g.cnpj AND e.status = 'ativa' "
                "WHERE g.document_type = ANY(:dts) "
                "ORDER BY (g.cnpj = :cnpj1) DESC, g.document_type"
            ),
            {"dts": list(CND_NOMES.keys()), "cnpj1": _CNPJ_ELETRONICA},
        ).fetchall()

    for document_type, file_path, expiry, cnpj, fantasia in rows:
        fn = _nome_arquivo(document_type, cnpj or _CNPJ_ELETRONICA, fantasia)
        if not fn or not file_path or not os.path.exists(file_path):
            rel["sem_pdf"].append(f"{document_type} ({fantasia})")
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
