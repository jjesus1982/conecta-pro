"""
GEDEON — Comprovantes de pagamento GERAIS via Inter (impostos/guias da empresa).

"Tudo o que o Jordan paga sai pelo Inter" → o Inter é a fonte de TODOS os
comprovantes. Aqui tratamos os pagamentos da EMPRESA (federais), que entram
iguais no kit de cada condomínio (como nos kits de referência).

Casamento por FAVORECIDO (não por valor — Jordan paga PARCELADO, então o valor
do pagamento ≠ total da guia). Mapeamento confirmado pelo Jordan:
  - "CEF MATRIZ"      → FGTS (maior valor) / FGTS Consignado (demais)
  - "DARF NUMERADO"   → INSS
  - "RECEITA FEDERAL" → Parcelamento de Impostos (entrada + parcelas em andamento)

Determinístico; sem efeito externo além do upload no Drive do próprio Jordan.
"""

from __future__ import annotations

import logging
import os
import tempfile

from modules.gdrive.services.gdrive_service import gdrive_service
from modules.gedeon.services.comprovante_generator import gerar_comprovante_pdf
from modules.gedeon.services.kit_layout import (
    _arquivo_ja_existe,
    mes_kit_de_competencia,
    pasta_kit_arquivo,
)

logger = logging.getLogger(__name__)


def _favorecido(t: dict) -> str:
    det = t.get("detalhes", {}) or {}
    return (str(t.get("descricao", "")) + " " + str(det.get("nomeRecebedor", ""))).upper()


def _valor(t: dict) -> float:
    try:
        return float(t.get("valor", 0))
    except Exception:
        return 0.0


def _fmt(v: float) -> str:
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def classificar_pagamentos_empresa(txs: list[dict]) -> list[dict]:
    """Devolve [{rotulo, nome_arquivo, tx}] dos pagamentos federais da empresa."""
    debitos = [t for t in txs if t.get("tipoOperacao") == "D"]
    itens: list[dict] = []

    # FGTS (CEF Matriz): maior = FGTS, demais = FGTS Consignado
    cef = sorted([t for t in debitos if "CEF MATRIZ" in _favorecido(t)], key=_valor, reverse=True)
    for i, t in enumerate(cef):
        rot = "FGTS" if i == 0 else "FGTS Consignado"
        itens.append({"rotulo": rot, "nome": f"Comprovante de Pagamento de {rot}.pdf", "tx": t})

    # INSS (DARF Numerado)
    for t in [t for t in debitos if "DARF NUMERADO" in _favorecido(t) or "DARF" in _favorecido(t)]:
        itens.append({"rotulo": "INSS", "nome": "Comprovante de Pagamento de INSS.pdf", "tx": t})

    # Parcelamento de Impostos (Receita Federal): entrada + parcelas
    rf = sorted([t for t in debitos if "RECEITA FEDERAL" in _favorecido(t)], key=_valor, reverse=True)
    for t in rf:
        v = _valor(t)
        data = str(t.get("dataTransacao", "")).replace("-", ".")
        itens.append(
            {
                "rotulo": "Parcelamento de Impostos",
                "nome": f"Comprovante de Pagamento de Parcelamento de Impostos - R$ {_fmt(v)} - {data}.pdf",
                "tx": t,
            }
        )
    return itens


def gerar_comprovantes_va_vt(competencia: str, txs: list[dict], emitido_em: str, dry_run: bool = False) -> dict:
    """Gera comprovantes de VA (Sólides) e VT (Sinetran) do Inter.
    Atribuição por condomínio exige o Relatório de Pedido de VA do Sólides (pendente)
    → por ora vão pra '_VA_VT (a atribuir)' nomeados por valor+data."""
    from modules.gedeon.services.kit_layout import ROOT_WORKSPACE_ID, _garantir_pasta

    if not gdrive_service._service:
        gdrive_service.check_status()
    debitos = [t for t in txs if t.get("tipoOperacao") == "D"]
    grupos = [
        ("Vale Alimentação (Sólides)", lambda t: "SOLIDES" in _favorecido(t)),
        ("Vale Transporte (Sinetran)", lambda t: "SIND DAS EMP" in _favorecido(t) or "SINETRAN" in _favorecido(t)),
    ]
    rel = {"competencia": competencia, "gerados": 0, "lista": []}
    cache: dict = {}
    holding = None if dry_run else _garantir_pasta(cache, "_VA_VT (a atribuir por condomínio)", ROOT_WORKSPACE_ID)
    mes_kit = mes_kit_de_competencia(competencia)
    sub = None if dry_run else _garantir_pasta(cache, mes_kit, holding)
    for rotulo, cond in grupos:
        for t in [t for t in debitos if cond(t)]:
            det = t.get("detalhes", {}) or {}
            v = _valor(t)
            data = str(t.get("dataTransacao", "")).replace("-", ".")
            fn = f"Comprovante de Pagamento {rotulo} - R$ {_fmt(v)} - {data}.pdf"
            rel["lista"].append(f"{rotulo}: R$ {_fmt(v)} em {t.get('dataTransacao')}")
            if dry_run:
                rel["gerados"] += 1
                continue
            pdf = gerar_comprovante_pdf(
                favorecido=det.get("nomeRecebedor") or rotulo,
                cpf=det.get("cpfCnpjRecebedor"),
                valor=v,
                data_pagamento=t.get("dataTransacao"),
                descricao=rotulo,
                id_transacao=det.get("endToEndId") or t.get("idTransacao"),
                competencia=competencia,
                condominio="(a atribuir)",
                emitido_em=emitido_em,
            )
            path = os.path.join(tempfile.gettempdir(), fn)
            with open(path, "wb") as fh:
                fh.write(pdf)
            if sub and not _arquivo_ja_existe(sub, fn):
                if gdrive_service.fazer_upload_arquivo(path, sub, fn):
                    rel["gerados"] += 1
    return rel


def gerar_comprovantes_empresa(
    competencia: str,
    condominios: list[str],
    txs: list[dict],
    emitido_em: str,
    dry_run: bool = False,
    apenas: list[str] | None = None,
) -> dict:
    """Gera os comprovantes federais e REPLICA em cada condomínio (iguais p/ todos).

    `apenas` filtra por rótulo (ex.: ['INSS'] — decisão do Jordan: no KIT do cliente
    vai SÓ o comprovante de INSS; FGTS/parcelamento ficam fora). None = todos.
    """
    if not gdrive_service._service:
        gdrive_service.check_status()
    itens = classificar_pagamentos_empresa(txs)
    if apenas:
        itens = [it for it in itens if it["rotulo"] in apenas]
    rel = {"competencia": competencia, "comprovantes": len(itens), "replicas": 0, "lista": []}

    for it in itens:
        t = it["tx"]
        det = t.get("detalhes", {}) or {}
        rel["lista"].append(f"{it['rotulo']}: R$ {_fmt(_valor(t))} em {t.get('dataTransacao')}")
        if dry_run:
            continue
        pdf = gerar_comprovante_pdf(
            favorecido=det.get("nomeRecebedor") or it["rotulo"],
            cpf=det.get("cpfCnpjRecebedor"),
            valor=t.get("valor"),
            data_pagamento=t.get("dataTransacao"),
            descricao=it["rotulo"],
            id_transacao=det.get("endToEndId") or t.get("idTransacao"),
            competencia=competencia,
            condominio="Conecta Mais (empresa)",
            emitido_em=emitido_em,
        )
        path = os.path.join(tempfile.gettempdir(), it["nome"])
        with open(path, "wb") as fh:
            fh.write(pdf)
        for cond in condominios:
            folder = pasta_kit_arquivo(cond, competencia, it["nome"])
            if folder and not _arquivo_ja_existe(folder, it["nome"]):
                if gdrive_service.fazer_upload_arquivo(path, folder, it["nome"]):
                    rel["replicas"] += 1
    return rel
