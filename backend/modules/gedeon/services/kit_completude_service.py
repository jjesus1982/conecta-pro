"""GEDEON — completude REAL dos kits, lendo a estrutura do Google Drive.

Substitui o percentual fake do GED antigo (tabela ged_document_kits, nunca populada)
pela verdade: lê as 4 subpastas de cada condomínio no Drive, classifica os arquivos
contra um checklist do que o kit DEVE conter e calcula o % de montagem.
"""

from __future__ import annotations

import unicodedata

_FOLDER_MIME = "application/vnd.google-apps.folder"

# subpastas (mesma convenção do kit_layout.SUBPASTAS)
SUB_PESSOAL = "1. Folha e Pessoal"
SUB_VALE = "2. Vale Transporte e Alimentação"
SUB_IMPOSTOS = "3. Impostos e Certidões"
SUB_FATURAMENTO = "4. Faturamento"

# Checklist do kit: cada bloco vale 1 ponto (CND tem 5 itens → crédito proporcional).
# match = lista de termos (sem acento, minúsculo); o arquivo conta se contém QUALQUER um.
CHECKLIST = [
    {"key": "folha", "label": "Folha de Pagamento", "sub": SUB_PESSOAL, "match": ["folha de pagamento"], "esperado": 1},
    {
        "key": "contracheque",
        "label": "Contracheques",
        "sub": SUB_PESSOAL,
        "match": ["contracheque", "holerite"],
        "esperado": 1,
    },
    {
        "key": "salario",
        "label": "Comprovantes de salário",
        "sub": SUB_PESSOAL,
        "match": ["comprovante de pagamento de sal", "comprovante de sal", "comprovante salario"],
        "esperado": 1,
    },
    {
        "key": "ponto",
        "label": "Ponto assinado",
        "sub": SUB_PESSOAL,
        "match": ["ponto assinada", "ponto assinado", "folha de ponto"],
        "esperado": 1,
    },
    {
        "key": "vavt",
        "label": "Vale Transporte / Alimentação",
        "sub": SUB_VALE,
        "match": [],
        "esperado": 1,
    },  # qualquer arquivo na subpasta conta
    {
        "key": "guias",
        "label": "Guias (FGTS / DCTFWeb / INSS)",
        "sub": SUB_IMPOSTOS,
        "match": ["guia", "dctfweb", "gfd", "relatorio fgts", "fgts"],
        "esperado": 1,
    },
    {
        "key": "inss",
        "label": "Comprovante INSS",
        "sub": SUB_IMPOSTOS,
        "match": [
            "comprovante inss",
            "comprovante de pagamento inss",
            "inss comprovante",
            "comprovante de pagamento de inss",
        ],
        "esperado": 1,
    },
    {
        "key": "cnd",
        "label": "Certidões (CNDs)",
        "sub": SUB_IMPOSTOS,
        "match": ["cnd", "crf", "certidao"],
        "esperado": 5,
    },
    {
        "key": "nfse",
        "label": "Nota Fiscal (NFS-e)",
        "sub": SUB_FATURAMENTO,
        "match": ["nota fiscal", "nfs", "danfse"],
        "esperado": 1,
    },
    {"key": "boleto", "label": "Boleto", "sub": SUB_FATURAMENTO, "match": ["boleto"], "esperado": 1},
]
TOTAL_BLOCOS = len(CHECKLIST)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


def _status_de_pct(pct: int) -> str:
    if pct >= 100:
        return "completo"
    if pct > 0:
        return "em_montagem"
    return "pendente"


def _avaliar(arquivos_por_sub: dict[str, list[dict]]) -> dict:
    """Recebe {subpasta: [ {name, link} ]} e devolve checklist avaliado + pct."""
    itens = []
    score = 0.0
    for c in CHECKLIST:
        files = arquivos_por_sub.get(c["sub"], [])
        if c["match"]:
            achados = [f for f in files if any(t in _norm(f["name"]) for t in c["match"])]
        else:  # bloco "qualquer arquivo na subpasta" (VA/VT)
            achados = list(files)
        cnt = len(achados)
        esp = c["esperado"]
        credito = min(cnt, esp) / esp
        score += credito
        itens.append(
            {
                "key": c["key"],
                "label": c["label"],
                "subpasta": c["sub"],
                "presente": cnt > 0,
                "encontrados": cnt,
                "esperado": esp,
                "arquivos": [a["name"] for a in achados],
            }
        )
    pct = round(score / TOTAL_BLOCOS * 100)
    return {"pct": pct, "status": _status_de_pct(pct), "itens": itens}


def _ler_kit(svc, cond: str, competencia: str) -> dict:
    from modules.gedeon.services.kit_layout import SUBPASTAS, garantir_pasta_kit

    def _list(parent_id: str) -> list[dict]:
        if not parent_id:
            return []
        return (
            svc.files()
            .list(
                q=f"'{parent_id}' in parents and trashed=false",
                fields="files(id,name,mimeType,webViewLink)",
                pageSize=300,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
            .get("files", [])
        )

    base = garantir_pasta_kit(cond, competencia)
    link, arquivos_por_sub, subpastas, total = None, {}, [], 0
    if base:
        try:
            meta = svc.files().get(fileId=base, fields="webViewLink", supportsAllDrives=True).execute()
            link = meta.get("webViewLink")
        except Exception:
            pass
        folders = {f["name"]: f["id"] for f in _list(base) if f["mimeType"] == _FOLDER_MIME}
        for sp in SUBPASTAS:
            files = [
                {"id": x["id"], "name": x["name"], "link": x.get("webViewLink")}
                for x in _list(folders.get(sp, ""))
                if x["mimeType"] != _FOLDER_MIME
            ]
            arquivos_por_sub[sp] = files
            subpastas.append({"nome": sp, "docs": len(files), "arquivos": files})
            total += len(files)

    aval = _avaliar(arquivos_por_sub)
    return {
        "condominio": cond,
        "total": total,
        "drive_link": link,
        "completion_percentage": aval["pct"],
        "status": aval["status"],
        "checklist": aval["itens"],
        "subpastas": subpastas,
    }


def condominios_do_workspace(svc=None) -> list[str]:
    """Lista os condomínios REAIS direto das pastas do workspace do GEDEON (escala automática:
    inclui os que não estão nos 7 padrão). Exclui pastas meta (_AUDITORIA, _VA_VT, Folhas de Ponto).
    Fallback p/ CONDOMINIOS_PADRAO se o Drive falhar."""
    from modules.gedeon.services.kit_layout import ROOT_WORKSPACE_ID
    from modules.gedeon.services.kit_orchestrator import CONDOMINIOS_PADRAO

    if svc is None:
        from modules.gdrive.services.gdrive_service import gdrive_service

        if not gdrive_service._service:
            gdrive_service.check_status()
        svc = gdrive_service._service
    if not svc:
        return list(CONDOMINIOS_PADRAO)
    try:
        folders = (
            svc.files()
            .list(
                q=f"'{ROOT_WORKSPACE_ID}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
                fields="files(name)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
            .get("files", [])
        )
    except Exception:
        return list(CONDOMINIOS_PADRAO)
    nomes = sorted({f["name"] for f in folders if not f["name"].startswith("_") and f["name"].strip() != "Folhas de Ponto"})
    return nomes or list(CONDOMINIOS_PADRAO)


def completude_kits(competencia: str) -> dict:
    """Painel de completude REAL de TODOS os condomínios do workspace (lê o Drive)."""
    from modules.gdrive.services.gdrive_service import gdrive_service
    from modules.gedeon.services import kit_cache
    from modules.gedeon.services.kit_layout import mes_kit_de_competencia

    if not gdrive_service._service:
        gdrive_service.check_status()
    svc = gdrive_service._service
    if not svc:
        raise RuntimeError("Google Drive não conectado")

    conds = condominios_do_workspace(svc)  # escala: todos os condomínios reais do workspace
    kits = [kit_cache.ler_kit(svc, cond, competencia) for cond in conds]
    completos = sum(1 for k in kits if k["status"] == "completo")
    media = round(sum(k["completion_percentage"] for k in kits) / len(kits)) if kits else 0
    return {
        "competencia": competencia,
        "mes_kit": mes_kit_de_competencia(competencia),
        "total_kits": len(kits),
        "kits_completos": completos,
        "kits_pendentes": len(kits) - completos,
        "media_completude": media,
        "blocos_por_kit": TOTAL_BLOCOS,
        "kits": kits,
    }
