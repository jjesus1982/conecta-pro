"""GEDEON — Pendências de assinatura por condomínio.

O robô do Sólides só baixa os documentos com status COMPLETED (assinados) — eles viram o
manifesto.json. Logo, quem está na FOLHA do condomínio mas NÃO tem o recibo de VT/VR
assinado no manifesto é uma PENDÊNCIA de assinatura (ex.: o funcionário ainda não assinou).
Serve à Pyetra/Jordan p/ cobrar a assinatura antes de fechar o kit.

Opcionalmente lê pendentes.json (docs em status != COMPLETED capturados pelo robô) p/
mostrar explicitamente "aguardando assinatura" — se o arquivo existir.
"""

from __future__ import annotations

import json
import os

SRC = "/app/uploads/solides_ged"


def _carregar_manifesto() -> list[dict]:
    p = f"{SRC}/manifesto.json"
    if os.path.exists(p):
        try:
            return json.load(open(p))
        except Exception:
            return []
    return []


def _carregar_pendentes() -> list[dict]:
    """Docs em status != COMPLETED (aguardando assinatura), se o robô os tiver capturado."""
    p = f"{SRC}/pendentes.json"
    if os.path.exists(p):
        try:
            return json.load(open(p))
        except Exception:
            return []
    return []


def pendencias_assinatura(competencia: str, condominio: str | None = None) -> dict:
    """Quem (folha do condomínio) ainda não tem o recibo de VT/VR assinado no Sólides."""
    from core.database.session import get_sync_db
    from modules.gdrive.services.gdrive_service import gdrive_service
    from modules.gedeon.services import kit_cache
    from modules.gedeon.services.kit_ficha_service import _norm, _pertence
    from modules.gedeon.services.kit_orchestrator import CONDOMINIOS_PADRAO

    if not gdrive_service._service:
        gdrive_service.check_status()
    svc = gdrive_service._service

    manifesto = _carregar_manifesto()
    pendentes_doc = _carregar_pendentes()
    # nomes (normalizados) que JÁ têm VT/VR assinado
    assinados_vavt = [_norm(m["funcionario"]) for m in manifesto if m.get("tipo") == "vale_vt_vr"]
    # nomes com QUALQUER doc assinado (informativo)
    assinados_qualquer = {_norm(m["funcionario"]) for m in manifesto}

    conds = [condominio] if condominio else CONDOMINIOS_PADRAO
    resultado = []
    total_pend = 0
    for cond in conds:
        folha = kit_cache.nomes_folha(svc, cond, competencia) if svc else []
        folha = [n for n in folha if n.strip()]
        pendentes, assinados = [], []
        for nome in folha:
            tem = any(_pertence(nome, {a}) for a in assinados_vavt)
            if tem:
                assinados.append(nome)
            else:
                # aguardando assinatura explícito?
                aguardando = any(_pertence(nome, {_norm(p["funcionario"])}) for p in pendentes_doc)
                pendentes.append({"funcionario": nome, "estado": "aguardando" if aguardando else "sem_recibo"})
        total_pend += len(pendentes)
        resultado.append(
            {
                "condominio": cond,
                "funcionarios_folha": len(folha),
                "assinados": len(assinados),
                "pendentes": pendentes,
                "total_pendentes": len(pendentes),
            }
        )
    return {
        "competencia": competencia,
        "tipo_doc": "vale_vt_vr",
        "total_pendentes": total_pend,
        "tem_dados_aguardando": bool(pendentes_doc),
        "manifesto_assinados": len(assinados_qualquer),
        "condominios": resultado,
    }
