"""GEDEON — Arquiva os DANFSe (NFS-e) nos kits, por condomínio.

Puxa as notas emitidas do ADN (nfse_nacional_adn), gera o DANFSe (nfse_danfse_generator),
mapeia o tomador → condomínio do workspace e arquiva em [Condomínio]/[Mês]/.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
import unicodedata

from modules.gdrive.services.gdrive_service import gdrive_service
from modules.gedeon.services.kit_layout import _arquivo_ja_existe, pasta_kit_arquivo
from modules.gedeon.services.nfse_danfse_generator import gerar_danfse_pdf
from modules.gedeon.services.nfse_nacional_adn import distribuir, filtrar_vivas

logger = logging.getLogger(__name__)

# tomador (normalizado) → nome do condomínio no workspace
KNOWN = {
    "IDEAL FLORES": "IDEAL FLORES",
    "MICHELANGELO": "MICHELANGELO",
    "MIRANTE": "MIRANTE",
    "VILLA DOS PASSAROS": "VILLA PÁSSAROS",
    "VILLA DEI FIORI": "VILLA DEI FIORI",
    "LARANJEIRAS": "LARANJEIRAS",
    "PRIME ARENA": "PRIME ARENA",
    "GREEN HILLS": "GREEN HILLS",
    "PARISE": "PARISE VILLA",
    "GELAI": "PARQUE RESIDENCIAL GELAI",
    "SMART TORQUATO": "SMART TORQUATO",
    "VILLA DOS PARQUES": "VILLA DOS PARQUES",
}


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper()


def condominio_do_tomador(tomador: str) -> str:
    t = _norm(tomador)
    for chave, nome in KNOWN.items():
        if chave in t:
            return nome
    # genérico: tira prefixos comuns e limpa
    clean = re.sub(r"\b(CONDOMINIO|RESIDENCIAL|DO|EDIFICIO|EDIF|VILLAGE|DA CIDADE|CLUBE)\b", " ", t)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean.title() or (tomador or "Desconhecido")


def arquivar_danfse(competencia: str, mes_emissao: str = "2026-05", dry_run: bool = False) -> dict:
    """Arquiva o DANFSe de cada nota emitida no mês (mes_emissao=YYYY-MM) no kit do condomínio."""
    if not gdrive_service._service:
        gdrive_service.check_status()
    # Multi-CNPJ E6 (kit híbrido): notas das DUAS empresas do Grupo, cada feed
    # com seu certificado, aplicando a regra de validade (substituídas FORA —
    # antes o feed cru colocava DANFSe de nota morta no kit).
    notas_todas: list[dict] = []
    for slug in (None, "conecta_patrimonial"):  # None = CNPJ1/legado
        try:
            feed = distribuir(max_paginas=80, empresa_slug=slug)
            vivas, mortas = filtrar_vivas(feed.get("emitidas", []))
            notas_todas.extend(vivas)
            logger.info("DANFSe kits: %s -> %d vivas (%d substituídas fora)",
                        slug or "conecta_eletronica", len(vivas), mortas)
        except Exception as exc:  # noqa: BLE001
            logger.warning("DANFSe kits: feed %s falhou (%s) — segue com o outro",
                           slug or "conecta_eletronica", exc)
    notas = [n for n in notas_todas if mes_emissao in (n.get("dhProc", "") + n.get("competencia", ""))]
    rel = {
        "competencia": competencia,
        "mes_emissao": mes_emissao,
        "notas_no_mes": len(notas),
        "arquivados": 0,
        "por_condominio": {},
    }
    for n in notas:
        cond = condominio_do_tomador(n.get("tomador", ""))
        fn = f"Nota Fiscal NFS-{n.get('numero', '')}.pdf"
        rel["por_condominio"].setdefault(cond, 0)
        if dry_run:
            rel["arquivados"] += 1
            rel["por_condominio"][cond] += 1
            continue
        folder = pasta_kit_arquivo(cond, competencia, fn)
        if not folder or _arquivo_ja_existe(folder, fn):
            continue
        try:
            pdf = gerar_danfse_pdf(n["_xml"])
            path = os.path.join(tempfile.gettempdir(), fn)
            with open(path, "wb") as fh:
                fh.write(pdf)
            if gdrive_service.fazer_upload_arquivo(path, folder, fn):
                rel["arquivados"] += 1
                rel["por_condominio"][cond] += 1
        except Exception as exc:
            logger.warning("DANFSe NFS-%s: %s", n.get("numero"), exc)
    return rel
