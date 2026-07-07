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
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm, mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    from modules.crm.services import pdf_branding as B

    os.makedirs("/app/uploads/kit_indices", exist_ok=True)
    out = f"/app/uploads/kit_indices/indice_{competencia}_{_slug(condominio)}.pdf"
    st = B.styles()
    # topMargin 40mm p/ não sobrepor o cabeçalho da marca (logo completa Conecta Mais)
    doc = SimpleDocTemplate(out, pagesize=A4, topMargin=40 * mm, bottomMargin=16 * mm)
    el = []
    el.append(Paragraph("Kit Documental Mensal", st["capa_titulo"]))
    el.append(Spacer(1, 0.4 * cm))
    # ficha resumo do kit (competência, condomínio, completude, selo ATLAS) em caixa da marca
    ficha = [
        [Paragraph("<b>Condomínio</b>", st["cell"]), Paragraph(condominio, st["cell"])],
        [Paragraph("<b>Competência</b>", st["cell"]), Paragraph(str(competencia), st["cell"])],
        [Paragraph("<b>Kit</b>", st["cell"]), Paragraph(str(kit.get("status", "")), st["cell"])],
        [Paragraph("<b>Completude</b>", st["cell"]), Paragraph(f"{kit.get('completion_percentage', 0)}%", st["cell"])],
    ]
    if atlas:
        selo = "CONFERIDO (ATLAS)" if atlas.get("selo") == "conferido" else "REVISAR (ATLAS)"
        ficha.append([Paragraph("<b>Conferência</b>", st["cell"]), Paragraph(selo, st["cell"])])
    ficha.append(
        [Paragraph("<b>Gerado em</b>", st["cell"]), Paragraph(datetime.now().strftime("%d/%m/%Y %H:%M"), st["cell"])]
    )
    tf = Table(ficha, colWidths=[4 * cm, 13 * cm])
    tf.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), B.FUNDO_CLARO),
                ("BOX", (0, 0), (-1, -1), 0.6, B.AZUL_ESCURO),
                ("LINEBELOW", (0, 0), (-1, -2), 0.25, B.AZUL_MEDIO),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    el.append(tf)
    el.append(Spacer(1, 0.6 * cm))
    el.extend(B.secao("Índice de documentos", st))
    for sp in kit.get("subpastas", []):
        el.append(Spacer(1, 0.2 * cm))
        el.append(Paragraph(f"{sp['nome']} ({sp.get('docs', 0)} documentos)", st["h_sec"]))
        arqs = sp.get("arquivos", [])
        if arqs:
            linhas = [
                [Paragraph(str(i + 1), st["cellr"]), Paragraph(a["name"], st["cell"])] for i, a in enumerate(arqs)
            ]
            t = Table(linhas, colWidths=[1 * cm, 16 * cm])
            t.setStyle(
                TableStyle(
                    [
                        ("TEXTCOLOR", (0, 0), (0, -1), B.AZUL_MEDIO),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                        ("TOPPADDING", (0, 0), (-1, -1), 2),
                        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [None, B.FUNDO_CLARO]),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )
            el.append(t)
        else:
            el.append(Paragraph("<i>— vazio —</i>", st["small"]))
    doc.build(
        el,
        onFirstPage=lambda cv, dc: B.header_footer(cv, dc, titulo="KIT DOCUMENTAL"),
        onLaterPages=lambda cv, dc: B.header_footer(cv, dc, titulo="KIT DOCUMENTAL"),
    )
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


def marcar_entregue(
    competencia: str, condominio: str, canal: str = "manual", obs: str = "", autor: str | None = None
) -> dict:
    """Registra que o kit FOI entregue ao cliente (manualmente). canal: whatsapp|email|impresso|manual."""
    marker = status_entrega(competencia, condominio)
    marker["estado"] = "entregue"
    marker["entregue_em"] = datetime.now().isoformat(timespec="seconds")
    marker["canal"] = canal
    marker["obs"] = obs
    hist = marker.get("historico", [])
    hist.append(
        {
            "acao": "entregue",
            "canal": canal,
            "obs": obs,
            "autor": autor,
            "em": datetime.now().isoformat(timespec="seconds"),
        }
    )
    marker["historico"] = hist
    return _salvar_marker(competencia, condominio, marker)
