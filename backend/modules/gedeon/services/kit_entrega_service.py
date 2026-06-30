"""GEDEON — Preparação de entrega do kit ao condomínio.

NÃO envia nada ao cliente (decisão Jordan: entrega fica MANUAL por segurança). O que faz:
  - gera uma CAPA/ÍNDICE em PDF do kit (competência, condomínio, completude, selo ATLAS e a
    lista de todos os documentos por subpasta) e sobe no topo da pasta do kit no Drive;
  - registra o status de entrega (preparado / entregue) num marcador JSON no volume uploads,
    pra Pyetra/Jordan acompanharem o que já foi preparado e o que já foi entregue manualmente.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import datetime

ENTREGA_DIR = "/app/uploads/kit_entregas"
INDICE_NOME = "00 - Índice do Kit.pdf"


def _slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def _path_marker(competencia: str, condominio: str) -> str:
    os.makedirs(ENTREGA_DIR, exist_ok=True)
    return f"{ENTREGA_DIR}/{competencia}__{_slug(condominio)}.json"


def status_entrega(competencia: str, condominio: str) -> dict:
    p = _path_marker(competencia, condominio)
    if os.path.exists(p):
        try:
            return json.load(open(p))
        except Exception:
            pass
    return {"competencia": competencia, "condominio": condominio, "estado": "nao_preparado", "historico": []}


def _salvar_marker(competencia: str, condominio: str, data: dict) -> dict:
    json.dump(data, open(_path_marker(competencia, condominio), "w"), ensure_ascii=False, indent=2)
    return data


def _gerar_indice_pdf(competencia: str, condominio: str, kit: dict, atlas: dict | None) -> str:
    """Gera a capa/índice em PDF e devolve o caminho local."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    os.makedirs("/app/uploads/kit_indices", exist_ok=True)
    out = f"/app/uploads/kit_indices/indice_{competencia}_{_slug(condominio)}.pdf"
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(out, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm)
    el = []
    el.append(Paragraph("<b>Conecta Mais — Kit Documental Mensal</b>", styles["Title"]))
    el.append(Spacer(1, 0.3 * cm))
    el.append(Paragraph(f"<b>Condomínio:</b> {condominio}", styles["Normal"]))
    el.append(Paragraph(f"<b>Competência:</b> {competencia}  &nbsp;&nbsp; <b>Kit:</b> {kit.get('status','')}", styles["Normal"]))
    el.append(Paragraph(f"<b>Completude:</b> {kit.get('completion_percentage', 0)}%", styles["Normal"]))
    if atlas:
        selo = "✔ CONFERIDO (ATLAS)" if atlas.get("selo") == "conferido" else "⚠ REVISAR (ATLAS)"
        el.append(Paragraph(f"<b>Conferência:</b> {selo}", styles["Normal"]))
    el.append(Paragraph(f"<b>Gerado em:</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles["Normal"]))
    el.append(Spacer(1, 0.5 * cm))
    el.append(Paragraph("<b>Índice de documentos</b>", styles["Heading2"]))
    for sp in kit.get("subpastas", []):
        el.append(Spacer(1, 0.2 * cm))
        el.append(Paragraph(f"<b>{sp['nome']}</b> ({sp.get('docs', 0)} documentos)", styles["Heading3"]))
        arqs = sp.get("arquivos", [])
        if arqs:
            linhas = [[str(i + 1), a["name"]] for i, a in enumerate(arqs)]
            t = Table(linhas, colWidths=[1 * cm, 15 * cm])
            t.setStyle(
                TableStyle(
                    [
                        ("FONTSIZE", (0, 0), (-1, -1), 8),
                        ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                        ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ]
                )
            )
            el.append(t)
        else:
            el.append(Paragraph("<i>— vazio —</i>", styles["Normal"]))
    doc.build(el)
    return out


def preparar_entrega(competencia: str, condominio: str, conferir: bool = True) -> dict:
    """Gera a capa/índice do kit e sobe no Drive; registra o estado como 'preparado'.
    Não envia nada ao cliente (entrega é manual)."""
    from modules.gdrive.services.gdrive_service import gdrive_service
    from modules.gedeon.services import kit_cache
    from modules.gedeon.services.kit_layout import garantir_pasta_kit

    if not gdrive_service._service:
        gdrive_service.check_status()
    svc = gdrive_service._service
    if not svc:
        raise RuntimeError("Google Drive não conectado")

    kit = kit_cache.ler_kit(svc, condominio, competencia)
    atlas = None
    if conferir:
        try:
            from modules.gedeon.services.kit_atlas_service import conferir_kit

            atlas = conferir_kit(competencia, condominio)
        except Exception:
            atlas = None

    pdf_path = _gerar_indice_pdf(competencia, condominio, kit, atlas)
    base = garantir_pasta_kit(condominio, competencia)
    up = None
    if base:
        # remove índice antigo p/ não duplicar
        try:
            antigos = (
                svc.files()
                .list(
                    q=f"'{base}' in parents and name='{INDICE_NOME}' and trashed=false",
                    fields="files(id)",
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
                .get("files", [])
            )
            for f in antigos:
                svc.files().update(fileId=f["id"], body={"trashed": True}, supportsAllDrives=True).execute()
        except Exception:
            pass
        up = gdrive_service.fazer_upload_arquivo(pdf_path, base, INDICE_NOME)

    marker = status_entrega(competencia, condominio)
    marker.update(
        {
            "estado": "preparado",
            "completude": kit.get("completion_percentage", 0),
            "selo_atlas": (atlas or {}).get("selo"),
            "indice_link": (up or {}).get("webViewLink") if up else None,
            "drive_link": kit.get("drive_link"),
            "preparado_em": datetime.now().isoformat(timespec="seconds"),
        }
    )
    hist = marker.get("historico", [])
    hist.append({"acao": "preparado", "em": datetime.now().isoformat(timespec="seconds")})
    marker["historico"] = hist
    _salvar_marker(competencia, condominio, marker)
    return marker


def marcar_entregue(competencia: str, condominio: str, canal: str = "manual", obs: str = "", autor: str | None = None) -> dict:
    """Registra que o kit FOI entregue ao cliente (manualmente). canal: whatsapp|email|impresso|manual."""
    marker = status_entrega(competencia, condominio)
    marker["estado"] = "entregue"
    marker["entregue_em"] = datetime.now().isoformat(timespec="seconds")
    marker["canal"] = canal
    marker["obs"] = obs
    hist = marker.get("historico", [])
    hist.append(
        {"acao": "entregue", "canal": canal, "obs": obs, "autor": autor, "em": datetime.now().isoformat(timespec="seconds")}
    )
    marker["historico"] = hist
    return _salvar_marker(competencia, condominio, marker)
