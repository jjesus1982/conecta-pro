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
from modules.gedeon.services.kit_layout import item_ja_na_pasta, pasta_kit_arquivo
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


def arquivar_danfse(competencia: str, mes_emissao: str = "2026-05", dry_run: bool = False,
                    gerar_se_faltar: bool = False) -> dict:
    """Confere, no kit de cada condomínio, se a NFS-e do mês está anexada — e NÃO gera nada.

    Regra do dono (07/09/2026): o kit leva o PDF ORIGINAL da nota (o DANFSe do portal), não
    um render do sistema. O SEFIN nacional não entrega a DANFSe por API (501 — medido em
    07/09/2026), então quem anexa é a Pyetra; o montador só diz o que FALTA. O casamento é
    por número da NFS-e ou da DPS em qualquer nome de arquivo ("NFS-e 7.pdf", "Nota Fiscal
    NFS-26.pdf"…) — o antigo comparava nome exato e subia uma cópia gerada ao lado da
    original. `gerar_se_faltar=True` volta ao render antigo, só se alguém pedir de propósito.
    """
    import re as _re

    if not gdrive_service._service:
        gdrive_service.check_status()
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
    # Casa pela COMPETÊNCIA da nota (dCompet, 'YYYY-MM'); sem dCompet, pelo mês de emissão.
    notas = [n for n in notas_todas
             if str(n.get("competencia") or n.get("dhProc") or "")[:7] == mes_emissao[:7]]
    rel = {"competencia": competencia, "mes_emissao": mes_emissao, "notas_no_mes": len(notas),
           "presentes": 0, "faltando": [], "arquivados": 0, "por_condominio": {}}
    for n in notas:
        cond = condominio_do_tomador(n.get("tomador", ""))
        numero = str(n.get("numero", "")).strip()
        ndps = (_re.search(r"<nDPS>(\d+)</nDPS>", n.get("_xml", "") or "") or [None, ""])[1]
        rel["por_condominio"].setdefault(cond, 0)
        rel["por_condominio"][cond] += 1
        if dry_run and not gdrive_service._service:
            continue
        fn = f"Nota Fiscal NFS-{numero}.pdf"
        folder = pasta_kit_arquivo(cond, competencia, fn)
        if not folder:
            rel["faltando"].append(f"{cond}: NFS-e {numero} (sem pasta do kit)")
            continue
        chaves = [f"NFS-{numero}", f"NFS-E {numero}", f"NFSE {numero}", f"NOTA {numero}"]
        if ndps:
            chaves += [f"NFS-{ndps}", f"NFS-E {ndps}", f"DPS {ndps}"]
        ja = item_ja_na_pasta(folder, chaves)
        if ja:
            rel["presentes"] += 1
            continue
        if not gerar_se_faltar or dry_run:
            rel["faltando"].append(f"{cond}: NFS-e {numero} — anexar o PDF original do portal")
            continue
        try:
            pdf = gerar_danfse_pdf(n["_xml"])
            path = os.path.join(tempfile.gettempdir(), fn)
            with open(path, "wb") as fh:
                fh.write(pdf)
            if gdrive_service.fazer_upload_arquivo(path, folder, fn):
                rel["arquivados"] += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("DANFSe NFS-%s: %s", numero, exc)
    return rel
