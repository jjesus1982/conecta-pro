"""GEDEON — Visão por funcionário: todos os documentos de uma pessoa de uma vez.

Útil pra conferência (a Pyetra abre 'Fulano' e vê contracheque + VT/VR + ponto + férias +
rescisão num lugar só). Junta os arquivos do kit no Drive (filtrados pelo nome) com os
recibos assinados do Sólides (manifesto) e os documentos do Onvio (onvio_documents).
"""

from __future__ import annotations

import json
import os

SOLIDES_SRC = "/app/uploads/solides_ged"


def listar_funcionarios(competencia: str, condominio: str) -> dict:
    """Nomes da folha do condomínio (p/ a UI montar o seletor de funcionário)."""
    from modules.gdrive.services.gdrive_service import gdrive_service
    from modules.gedeon.services.kit_ficha_service import _nomes_da_folha

    if not gdrive_service._service:
        gdrive_service.check_status()
    svc = gdrive_service._service
    nomes = sorted({n for n in (_nomes_da_folha(svc, condominio, competencia) if svc else []) if n.strip()})
    return {"competencia": competencia, "condominio": condominio, "funcionarios": nomes}


def visao_funcionario(competencia: str, funcionario: str, condominio: str | None = None) -> dict:
    """Agrega todos os docs de um funcionário no kit + Sólides + Onvio."""
    from core.database.session import get_sync_db
    from modules.gdrive.services.gdrive_service import gdrive_service
    from modules.gedeon.services.kit_completude_service import _ler_kit
    from modules.gedeon.services.kit_ficha_service import _norm, _pertence
    from modules.gedeon.services.kit_orchestrator import CONDOMINIOS_PADRAO

    if not gdrive_service._service:
        gdrive_service.check_status()
    svc = gdrive_service._service

    alvo = _norm(funcionario)
    conds = [condominio] if condominio else CONDOMINIOS_PADRAO
    docs_kit: list[dict] = []
    cond_achado = None
    if svc:
        for cond in conds:
            kit = _ler_kit(svc, cond, competencia)
            achou_aqui = False
            for sp in kit.get("subpastas", []):
                for a in sp.get("arquivos", []):
                    # casa o nome do arquivo (sem extensão) ao funcionário (subset de tokens)
                    base = _norm(a["name"].rsplit(".", 1)[0]).replace("_", " ")
                    if _pertence(funcionario, {base}) or alvo.split()[0] in base:
                        docs_kit.append({"subpasta": sp["nome"], "nome": a["name"], "link": a.get("link"), "condominio": cond})
                        achou_aqui = True
            if achou_aqui and not cond_achado:
                cond_achado = cond
            if condominio:  # se foi pedido um cond específico, não varre os outros
                break

    # Sólides (recibos assinados)
    solides = []
    mpath = f"{SOLIDES_SRC}/manifesto.json"
    if os.path.exists(mpath):
        try:
            for m in json.load(open(mpath)):
                if _pertence(funcionario, {_norm(m.get("funcionario", ""))}):
                    solides.append({"tipo": m.get("tipo"), "label": m.get("label"), "arquivo": m.get("arquivo"), "created": m.get("created")})
        except Exception:
            pass

    # Onvio (documentos do contador)
    onvio = []
    try:
        from sqlalchemy import text

        with get_sync_db() as db:
            for (na,) in db.execute(text("SELECT nome_arquivo FROM onvio_documents")).fetchall():
                base = _norm(na.rsplit(".", 1)[0]).replace("-", " ").replace("_", " ")
                if _pertence(funcionario, {base}) or alvo.split()[0] in base:
                    onvio.append({"nome_arquivo": na})
    except Exception:
        pass

    return {
        "competencia": competencia,
        "funcionario": funcionario,
        "condominio": cond_achado or condominio,
        "total_docs": len(docs_kit) + len(solides) + len(onvio),
        "kit": docs_kit,
        "solides_assinados": solides,
        "onvio": onvio[:30],
    }
