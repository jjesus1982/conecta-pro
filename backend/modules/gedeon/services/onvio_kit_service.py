"""
GEDEON — Arquiva os documentos do Onvio (Portte) no kit, formato flat.

Onvio (categoria) → nome do arquivo no kit (igual ao que a equipe entrega):
  folha_pagamento → "Folha de Pagamento.pdf"
  recibo_folha    → "Contracheques.pdf"

Cada doc do Onvio traz o condomínio no nome ("Folha 05.2026_Ideal Flores.pdf");
mapeamos pro nome do condomínio no workspace e arquivamos em [Condomínio]/[Mês]/.
Lê o binário do disco (caminho_local) e, se faltar, re-busca do Onvio.
"""

from __future__ import annotations

import logging
import os
import tempfile

from sqlalchemy import text

from modules.gdrive.services.gdrive_service import gdrive_service
from modules.gedeon.services.kit_layout import _arquivo_ja_existe, pasta_kit_arquivo

logger = logging.getLogger(__name__)

NOME_KIT: dict[str, str] = {
    "folha_pagamento": "Folha de Pagamento.pdf",
    "recibo_folha": "Contracheques.pdf",
}

# Guias da EMPRESA (Conecta Mais) — entram iguais em TODOS os kits (replicadas).
# Valor None = preserva o nome original do Onvio (já é descritivo e padrão do kit).
CATEGORIAS_EMPRESA: dict[str, str | None] = {
    "fgts_guia": None,
    "fgts_relatorio": None,
    "inss_guia": None,
    "dctfweb_declaracao": None,
    "dctfweb_recibo": None,
    "dctfweb_resumo_debitos": None,
}

# substring (no nome do arquivo Onvio, minúsculo) → nome do condomínio no workspace
CONDOMINIO_MAP: dict[str, str] = {
    "ideal flores": "IDEAL FLORES",
    "michelangelo": "MICHELANGELO",
    "mirante": "MIRANTE",
    "villa dei fiori": "VILLA DEI FIORI",
    "villa dos passaros": "VILLA PÁSSAROS",
    "villa dos pássaros": "VILLA PÁSSAROS",
    "laranjeiras": "LARANJEIRAS",
    "prime arena": "PRIME ARENA",
}


def _condominio_do_nome(nome_arquivo: str) -> str | None:
    n = nome_arquivo.lower()
    for chave, cond in CONDOMINIO_MAP.items():
        if chave in n:
            return cond
    return None


def _garantir_binario(onvio_client, caminho_local, onvio_folder_id, onvio_id) -> str | None:
    """Devolve um caminho local válido do PDF (disco ou re-baixado do Onvio)."""
    if caminho_local and os.path.exists(caminho_local):
        return caminho_local
    if onvio_client and onvio_folder_id and onvio_id:
        try:
            b = onvio_client.baixar_pdf(onvio_folder_id, onvio_id)
            tmp = os.path.join(tempfile.gettempdir(), f"onvio_{onvio_id}.pdf")
            with open(tmp, "wb") as fh:
                fh.write(b)
            return tmp
        except Exception as exc:
            logger.warning("re-fetch Onvio %s falhou: %s", onvio_id, exc)
    return None


def arquivar_onvio_flat(competencia: str, db, onvio_client=None, dry_run: bool = False) -> dict:
    """Arquiva folha + contracheque do Onvio (competência) no kit de cada condomínio."""
    cats = tuple(NOME_KIT.keys())
    rows = db.execute(
        text("""
        SELECT categoria, nome_arquivo, caminho_local, onvio_folder_id, onvio_id
        FROM onvio_documents
        WHERE mes_ref = :m AND categoria IN :cats
        ORDER BY nome_arquivo
    """).bindparams(__import__("sqlalchemy").bindparam("cats", expanding=True)),
        {"m": competencia, "cats": list(cats)},
    ).all()

    rel = {"competencia": competencia, "arquivados": 0, "pulados": [], "por_condominio": {}}
    feitos: set = set()  # (condominio, categoria) — 1 por condomínio/tipo (evita dupes "(1)")

    for categoria, nome, caminho, folder_id, oid in rows:
        cond = _condominio_do_nome(nome)
        if not cond:
            continue  # Laranjeiras/Prime Arena (Innovare) ou Geral — fora
        chave = (cond, categoria)
        if chave in feitos:
            continue
        fn = NOME_KIT[categoria]
        if dry_run:
            feitos.add(chave)
            rel["arquivados"] += 1
            rel["por_condominio"].setdefault(cond, []).append(fn)
            continue
        path = _garantir_binario(onvio_client, caminho, folder_id, oid)
        if not path:
            rel["pulados"].append(f"{cond}/{fn} (sem binário)")
            continue
        folder = pasta_kit_arquivo(cond, competencia, fn)
        if folder and not _arquivo_ja_existe(folder, fn):
            if gdrive_service.fazer_upload_arquivo(path, folder, fn):
                feitos.add(chave)
                rel["arquivados"] += 1
                rel["por_condominio"].setdefault(cond, []).append(fn)
        elif folder:
            feitos.add(chave)
    return rel


def arquivar_guias_empresa_flat(
    competencia: str, condominios: list[str], db, onvio_client=None, dry_run: bool = False
) -> dict:
    """Arquiva as guias da empresa (FGTS, INSS, DCTFWeb) replicadas em cada kit."""
    cats = tuple(CATEGORIAS_EMPRESA.keys())
    rows = db.execute(
        text("""
        SELECT categoria, nome_arquivo, caminho_local, onvio_folder_id, onvio_id
        FROM onvio_documents
        WHERE mes_ref = :m AND categoria IN :cats
        ORDER BY categoria, nome_arquivo
    """).bindparams(__import__("sqlalchemy").bindparam("cats", expanding=True)),
        {"m": competencia, "cats": list(cats)},
    ).all()

    rel = {"competencia": competencia, "guias": 0, "replicas": 0, "lista": []}
    vistos: set = set()
    for categoria, nome, caminho, folder_id, oid in rows:
        if categoria in vistos:  # 1 por tipo (evita duplicatas "(1)")
            continue
        vistos.add(categoria)
        fn = CATEGORIAS_EMPRESA[categoria] or nome
        rel["guias"] += 1
        rel["lista"].append(fn)
        if dry_run:
            continue
        path = _garantir_binario(onvio_client, caminho, folder_id, oid)
        if not path:
            continue
        for cond in condominios:
            folder = pasta_kit_arquivo(cond, competencia, fn)
            if folder and not _arquivo_ja_existe(folder, fn):
                if gdrive_service.fazer_upload_arquivo(path, folder, fn):
                    rel["replicas"] += 1
    return rel
