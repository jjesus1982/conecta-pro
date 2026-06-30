"""
GEDEON — Montador Onvio → Workspace limpo do Google Drive.

Pega os documentos que a Portte Contábil publica no Onvio (folha, contracheque,
recibo VT/VA, FGTS, DCTFWeb, contrato, ficha…), classifica cada um no tipo de
kit (slug) e arquiva na subpasta certa do workspace organizado, por condomínio.

Fonte: tabela onvio_documents (arquivos em disco via caminho_local).
Destino: workspace limpo (ROOT) → "AAAA-MM — Mês" → [Condomínio | 00 Empresa Matriz] → "NN - Categoria".

Idempotente: se um arquivo de mesmo nome já existe na subpasta, não reenvia.
Determinístico e sem efeito externo além do upload no Drive do próprio Jordan.
"""

from __future__ import annotations

import logging

from modules.gdrive.services.gdrive_service import gdrive_service
from modules.gedeon.services.drive_kit_classifier import classify_filename
from modules.gedeon.services.kit_structure import categoria_de

logger = logging.getLogger(__name__)

# Workspace LIMPO criado do zero (raiz "GEDEON — Kits Documentais (Conecta Mais)")
ROOT_WORKSPACE_ID = "1oigpHoCvFT-M2tm96FDvE0LvowciNLKJ"

# Pasta para documentos da empresa toda (sem condomínio): DCTFWeb, FGTS guia, CNDs…
PASTA_EMPRESA = "00 - Empresa Matriz (compartilhado)"

_MESES_PT = {
    "01": "Janeiro",
    "02": "Fevereiro",
    "03": "Março",
    "04": "Abril",
    "05": "Maio",
    "06": "Junho",
    "07": "Julho",
    "08": "Agosto",
    "09": "Setembro",
    "10": "Outubro",
    "11": "Novembro",
    "12": "Dezembro",
}

# categoria do Onvio -> slug do kit (espelha CategoriaToTipoDocumento do kit_builder)
_CATEGORIA_PARA_SLUG: dict[str, str] = {
    "folha_pagamento": "folha_pagamento",
    "recibo_folha": "contracheque",
    "folha_ponto": "folhas_ponto",
    "fgts_guia": "gfd_fgts_mensal",
    "fgts_relatorio": "relatorio_gfd_fgts",
    "fgts_consignado_relatorio": "relatorio_gfd_fgts",
    "dctfweb_declaracao": "dctfweb_declaracao",
    "dctfweb_recibo": "dctfweb_recibo",
    "dctfweb_extrato": "dctfweb_extrato",
    "dctfweb_resumo_creditos": "dctfweb_extrato",
    "dctfweb_resumo_debitos": "dctfweb_extrato",
    "dctfweb_creditos": "dctfweb_extrato",
    "dctfweb_debitos": "dctfweb_extrato",
    "dctfweb_situacao": "dctfweb_extrato",
    "contrato_trabalho": "contrato_trabalho",
    "ficha_registro": "ficha_empregado",
    "rescisao": "rescisao_contrato",
    "aso": "aso",
    "aviso_previo": "aviso_previo_ferias",
    "ferias": "recibo_ferias",
    "declaracao_vt": "comp_vt_individual",
    "guia_issqn": "inss_mensal",  # tributário municipal — agrupa no tributário
}


def nome_pasta_mes(mes_ref: str) -> str:
    """'03.2026' -> '2026-03 — Março'."""
    try:
        mes, ano = mes_ref.split(".")
        return f"{ano}-{mes} — {_MESES_PT.get(mes, mes)}"
    except Exception:
        return mes_ref


def resolver_slug(categoria: str | None, nome_arquivo: str) -> tuple[str | None, str]:
    """Tipo do kit: 1º pela categoria do Onvio; senão pelo nome do arquivo."""
    cat = (categoria or "").strip().lower()
    if cat in _CATEGORIA_PARA_SLUG:
        return _CATEGORIA_PARA_SLUG[cat], f"categoria={cat}"
    slug, _escopo, motivo = classify_filename(nome_arquivo)
    if slug:
        return slug, f"nome→{motivo}"
    return None, f"sem match (cat={cat or '?'})"


def _garantir_pasta(cache: dict, nome: str, parent_id: str) -> str | None:
    """Cria/encontra pasta (com cache local p/ evitar chamadas repetidas)."""
    key = (parent_id, nome)
    if key in cache:
        return cache[key]
    fid = gdrive_service._criar_pasta(nome, parent_id)
    cache[key] = fid
    return fid


def _arquivo_ja_existe(folder_id: str, nome: str) -> bool:
    svc = gdrive_service._service
    if not svc:
        return False
    safe = nome.replace("'", "\\'")
    q = f"name='{safe}' and '{folder_id}' in parents and trashed=false"
    try:
        r = svc.files().list(q=q, fields="files(id)").execute()
        return bool(r.get("files"))
    except Exception:
        return False


def montar_mes(mes_ref: str, docs: list[dict], dry_run: bool = False) -> dict:
    """
    docs: lista de {nome_arquivo, categoria, caminho_local, condominio_nome|None}.
    Retorna relatório com o que foi (ou seria) arquivado.
    """
    if not gdrive_service._service:
        gdrive_service.check_status()
    if not gdrive_service._service:
        return {"erro": "Google Drive não conectado", "mes_ref": mes_ref}

    cache: dict = {}
    mes_label = nome_pasta_mes(mes_ref)
    mes_folder = None if dry_run else _garantir_pasta(cache, mes_label, ROOT_WORKSPACE_ID)

    rel = {
        "mes_ref": mes_ref,
        "mes_label": mes_label,
        "dry_run": dry_run,
        "total": len(docs),
        "arquivados": 0,
        "ja_existiam": 0,
        "sem_classificacao": 0,
        "arquivo_ausente": 0,
        "por_condominio": {},
        "por_subpasta": {},
        "nao_classificados": [],
    }

    for d in docs:
        nome = d["nome_arquivo"]
        caminho = d.get("caminho_local") or ""
        cond = d.get("condominio_nome") or PASTA_EMPRESA
        slug, motivo = resolver_slug(d.get("categoria"), nome)
        if not slug:
            rel["sem_classificacao"] += 1
            rel["nao_classificados"].append(f"{nome}  [{motivo}]")
            continue
        subpasta = categoria_de(slug)
        rel["por_condominio"].setdefault(cond, 0)
        rel["por_subpasta"].setdefault(subpasta, 0)

        if dry_run:
            rel["arquivados"] += 1
            rel["por_condominio"][cond] += 1
            rel["por_subpasta"][subpasta] += 1
            continue

        cond_folder = _garantir_pasta(cache, cond, mes_folder)
        sub_folder = _garantir_pasta(cache, subpasta, cond_folder) if cond_folder else None
        if not sub_folder:
            rel["arquivo_ausente"] += 1
            continue
        if _arquivo_ja_existe(sub_folder, nome):
            rel["ja_existiam"] += 1
            continue
        up = gdrive_service.fazer_upload_arquivo(caminho, sub_folder, nome)
        if up:
            rel["arquivados"] += 1
            rel["por_condominio"][cond] += 1
            rel["por_subpasta"][subpasta] += 1
        else:
            rel["arquivo_ausente"] += 1

    return rel
