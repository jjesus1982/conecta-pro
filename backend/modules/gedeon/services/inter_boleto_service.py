"""GEDEON — Arquiva os BOLETOS (que o condomínio paga) do Banco Inter no kit.

Inter cobrança v3: lista cobranças (GET /cobranca/v3/cobrancas) → cada uma tem
seuNumero (NFS-X), pagador (condomínio), codigoSolicitacao. O PDF vem de
GET /cobranca/v3/cobrancas/{codigoSolicitacao}/pdf (base64).
Mapeia pagador → condomínio do workspace e arquiva "Boleto de Pagamento NFS-X.pdf".
"""

from __future__ import annotations

import base64
import logging
import os
import tempfile

from modules.gdrive.services.gdrive_service import gdrive_service
from modules.gedeon.services.kit_layout import _arquivo_ja_existe, pasta_kit_arquivo

logger = logging.getLogger(__name__)

# substring no nome do pagador (maiúsculo) → condomínio no workspace
PAGADOR_MAP: dict[str, str] = {
    "IDEAL FLORES": "IDEAL FLORES",
    "MICHELANGELO": "MICHELANGELO",
    "MIRANTE": "MIRANTE",
    "VILLA DOS PASSAROS": "VILLA PÁSSAROS",
    "VILLA DOS PÁSSAROS": "VILLA PÁSSAROS",
    "VILLA DEI FIORI": "VILLA DEI FIORI",
    "LARANJEIRAS": "LARANJEIRAS",
    "PRIME ARENA": "PRIME ARENA",
}


def _norm(s: str) -> str:
    import unicodedata

    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper()


def _condominio(pagador_nome: str) -> str | None:
    n = _norm(pagador_nome)
    for chave, cond in PAGADOR_MAP.items():
        if _norm(chave) in n:
            return cond
    return None


async def arquivar_boletos(
    competencia: str,
    adapter,
    emitido_em: str,
    data_inicial: str = "2026-05-15",
    data_final: str = "2026-06-30",
    dry_run: bool = False,
) -> dict:
    await adapter.authenticate()
    r = await adapter._request(
        "GET",
        "/cobranca/v3/cobrancas",
        params={
            "dataInicial": data_inicial,
            "dataFinal": data_final,
            "filtrarDataPor": "EMISSAO",
            "itensPorPagina": 100,
        },
    )
    cobs = r.get("cobrancas", []) if isinstance(r, dict) else []
    rel = {"competencia": competencia, "total_cobrancas": len(cobs), "arquivados": 0, "por_condominio": {}, "lista": []}
    if not dry_run and not gdrive_service._service:
        gdrive_service.check_status()

    for c in cobs:
        cb = c.get("cobranca", c)
        cond = _condominio(cb.get("pagador", {}).get("nome", ""))
        if not cond:
            continue
        seu = cb.get("seuNumero", "") or cb.get("codigoSolicitacao", "")[:8]
        fn = f"Boleto de Pagamento {seu}.pdf"
        rel["lista"].append(f"{cond}: {seu} R${cb.get('valorNominal')} ({cb.get('situacao')})")
        if dry_run:
            rel["arquivados"] += 1
            rel["por_condominio"].setdefault(cond, 0)
            rel["por_condominio"][cond] += 1
            continue
        folder = pasta_kit_arquivo(cond, competencia, fn)
        if not folder or _arquivo_ja_existe(folder, fn):
            continue
        try:
            pr = await adapter._request("GET", f"/cobranca/v3/cobrancas/{cb['codigoSolicitacao']}/pdf")
            b64 = pr.get("pdf") if isinstance(pr, dict) else None
            if not b64:
                continue
            path = os.path.join(tempfile.gettempdir(), fn)
            with open(path, "wb") as fh:
                fh.write(base64.b64decode(b64))
            if gdrive_service.fazer_upload_arquivo(path, folder, fn):
                rel["arquivados"] += 1
                rel["por_condominio"].setdefault(cond, 0)
                rel["por_condominio"][cond] += 1
        except Exception as exc:
            logger.warning("boleto %s: %s", seu, exc)
    return rel
