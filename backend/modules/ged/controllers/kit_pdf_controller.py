"""
Controller de geracao de PDFs reais, ZIP export e envio por email dos kits GED.

Endpoints:
- POST /kits/{kit_id}/generate-pdfs — gera PDFs reais para um kit
- POST /kits/generate-all-pdfs — gera PDFs para todos os kits do mes
- GET  /kits/{kit_id}/download-zip — baixa ZIP com todos os PDFs
- POST /kits/{kit_id}/send-email — envia kit por email
"""

import hashlib
import io
import logging
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["GED - Kit PDFs"])

UPLOAD_DIR = Path("/app/uploads/ged/kits")
MESES = [
    "",
    "Janeiro",
    "Fevereiro",
    "Marco",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
]


def _save_pdf(pdf_bytes: bytes, name: str) -> str:
    """Salva PDF no disco e retorna path relativo."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    chk = hashlib.sha256(pdf_bytes).hexdigest()[:12]
    fname = f"{name}_{chk}.pdf"
    (UPLOAD_DIR / fname).write_bytes(pdf_bytes)
    return f"ged/kits/{fname}"


def _gerar_contracheque(
    nome: str,
    cpf: str,
    cargo: str,
    salario: float,
    admissao: str,
    matricula: str,
    competencia: str,
) -> bytes:
    """Gera PDF de contracheque com ReportLab."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm, mm
    from reportlab.platypus import (
        HRFlowable,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    from modules.crm.services import pdf_branding as B

    AZ = colors.HexColor("#0A2540")
    AZ2 = colors.HexColor("#1E3A5F")
    LJ = colors.HexColor("#FF6B35")
    CZ = colors.HexColor("#F8FAFC")

    inss = round(salario * 0.09, 2)
    fgts = round(salario * 0.08, 2)
    vt = round(salario * 0.06, 2)
    liquido = round(salario - inss - vt, 2)

    buf = io.BytesIO()
    # topMargin 42mm p/ não sobrepor o cabeçalho da marca (logo completa Conecta Mais)
    doc = SimpleDocTemplate(
        buf, pagesize=A4, topMargin=42 * mm, bottomMargin=1.5 * cm, leftMargin=2 * cm, rightMargin=2 * cm
    )
    s: list[Any] = []

    # Título limpo do documento (cabeçalho da marca é desenhado por B.header_footer)
    s.append(
        Paragraph(
            '<b><font color="#0A2540" size="14">CONTRACHEQUE</font></b>'
            f'<br/><font color="grey" size="9">Competencia: {competencia}</font>',
            ParagraphStyle("cc_titulo", spaceAfter=6),
        )
    )
    s.append(Spacer(1, 0.3 * cm))

    info = Table(
        [
            ["FUNCIONARIO", nome],
            ["CPF", cpf or "-"],
            ["CARGO", cargo or "-"],
            ["ADMISSAO", admissao or "-"],
            ["MATRICULA", matricula or "-"],
        ],
        colWidths=[4 * cm, 13 * cm],
    )
    info.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), AZ2),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.white),
                ("BACKGROUND", (1, 0), (1, -1), CZ),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("PADDING", (0, 0), (-1, -1), 6),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ]
        )
    )
    s.append(info)
    s.append(Spacer(1, 0.4 * cm))

    s.append(Paragraph("<b>PROVENTOS</b>", ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=10, textColor=AZ)))
    s.append(Spacer(1, 0.2 * cm))
    prov = Table(
        [["Descricao", "Referencia", "Valor"], ["Salario Base", "30 dias", f"R$ {salario:,.2f}"]],
        colWidths=[8 * cm, 4 * cm, 5 * cm],
    )
    prov.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), AZ2),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (2, 0), (2, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    s.append(prov)
    s.append(Spacer(1, 0.3 * cm))

    s.append(
        Paragraph(
            "<b>DESCONTOS</b>", ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=10, textColor=colors.red)
        )
    )
    s.append(Spacer(1, 0.2 * cm))
    desc = Table(
        [
            ["Descricao", "Referencia", "Valor"],
            ["INSS", "9%", f"R$ {inss:,.2f}"],
            ["Vale Transporte", "6%", f"R$ {vt:,.2f}"],
        ],
        colWidths=[8 * cm, 4 * cm, 5 * cm],
    )
    desc.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#C0392B")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (2, 0), (2, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    s.append(desc)
    s.append(Spacer(1, 0.5 * cm))

    tot = Table(
        [
            ["TOTAL PROVENTOS", f"R$ {salario:,.2f}"],
            ["TOTAL DESCONTOS", f"R$ {inss + vt:,.2f}"],
            ["FGTS (EMPREGADOR)", f"R$ {fgts:,.2f}"],
            ["LIQUIDO A RECEBER", f"R$ {liquido:,.2f}"],
        ],
        colWidths=[12 * cm, 5 * cm],
    )
    tot.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ("BACKGROUND", (0, 3), (-1, 3), LJ),
                ("TEXTCOLOR", (0, 3), (-1, 3), colors.white),
                ("BACKGROUND", (0, 0), (-1, 0), CZ),
                ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#FFE5E5")),
                ("PADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    s.append(tot)
    s.append(Spacer(1, 1 * cm))
    s.append(HRFlowable(width="100%", thickness=1, color=B.LARANJA))
    s.append(Spacer(1, 0.2 * cm))
    s.append(
        Paragraph(
            f'<font size="7" color="grey">{B.EMPRESA["nome"]} | CNPJ {B.EMPRESA["cnpj"]} | '
            f"{B.EMPRESA['fone']} | {B.EMPRESA['site']} | "
            f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}</font>",
            ParagraphStyle("ft", alignment=TA_CENTER),
        )
    )

    doc.build(
        s,
        onFirstPage=lambda cv, dc: B.header_footer(cv, dc, titulo="CONTRACHEQUE"),
        onLaterPages=lambda cv, dc: B.header_footer(cv, dc, titulo="CONTRACHEQUE"),
    )
    return buf.getvalue()


def _gerar_nfse_pdf(
    numero: str,
    tomador: str,
    cnpj: str,
    valor: float,
    iss: float,
    descricao: str,
    competencia: str,
) -> bytes:
    """Gera PDF simples de NFS-e."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm, mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    from modules.crm.services import pdf_branding as B

    buf = io.BytesIO()
    # topMargin 42mm p/ não sobrepor o cabeçalho da marca (logo completa Conecta Mais)
    doc = SimpleDocTemplate(
        buf, pagesize=A4, topMargin=42 * mm, bottomMargin=2 * cm, leftMargin=2 * cm, rightMargin=2 * cm
    )
    AZ = colors.HexColor("#0A2540")

    s: list[Any] = []
    s.append(
        Paragraph(
            f'<b><font color="#0A2540" size="16">NFS-e No {numero}</font></b>', ParagraphStyle("t", alignment=TA_CENTER)
        )
    )
    s.append(Spacer(1, 0.3 * cm))
    s.append(
        Paragraph(
            f'<font size="9" color="grey">{B.EMPRESA["nome"]} — CNPJ {B.EMPRESA["cnpj"]}</font>',
            ParagraphStyle("sub", alignment=TA_CENTER),
        )
    )
    s.append(Spacer(1, 0.5 * cm))

    data = [
        ["Competencia", competencia],
        ["Tomador", tomador],
        ["CNPJ Tomador", cnpj],
        ["Servico", descricao],
        ["Valor Servicos", f"R$ {valor:,.2f}"],
        ["ISS (5%)", f"R$ {iss:,.2f}"],
        ["Valor Liquido", f"R$ {valor - iss:,.2f}"],
    ]
    t = Table(data, colWidths=[5 * cm, 12 * cm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), AZ),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.white),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ("PADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    s.append(t)
    doc.build(
        s,
        onFirstPage=lambda cv, dc: B.header_footer(cv, dc, titulo=f"NFS-e Nº {numero}"),
        onLaterPages=lambda cv, dc: B.header_footer(cv, dc, titulo=f"NFS-e Nº {numero}"),
    )
    return buf.getvalue()


# ── Endpoints ─────────────────────────────────────────────────────────────


@router.post("/kits/{kit_id}/generate-pdfs", status_code=201)
async def generate_kit_pdfs(
    kit_id: str,
    current_user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Gera PDFs reais para todos os documentos de um kit."""
    kit = (await db.execute(text("SELECT * FROM ged_document_kits WHERE id = :id"), {"id": kit_id})).mappings().first()
    if not kit:
        raise HTTPException(404, "Kit nao encontrado")

    comp = kit["reference_month"]
    comp_str = f"{comp.month:02d}/{comp.year}" if comp else "03/2026"

    docs = (
        (await db.execute(text("SELECT * FROM ged_kit_documents WHERE kit_id = :kid"), {"kid": kit_id}))
        .mappings()
        .all()
    )

    gerados = 0
    erros = 0

    for d in docs:
        dtype = (d["document_type"] or "").lower()
        existing_path = d["file_path"] or ""

        if existing_path.startswith("ged/kits/") and (UPLOAD_DIR / existing_path.replace("ged/kits/", "")).exists():
            continue

        try:
            pdf_bytes = None
            pdf_name = ""

            if "contracheque" in dtype:
                emp_id = d["employee_id"]
                if not emp_id:
                    continue
                emp = (
                    (
                        await db.execute(
                            text(
                                "SELECT nome, cpf, cargo, salario_base, data_admissao, matricula FROM employees WHERE id = :eid"
                            ),
                            {"eid": str(emp_id)},
                        )
                    )
                    .mappings()
                    .first()
                )
                if not emp:
                    continue
                pdf_bytes = _gerar_contracheque(
                    nome=emp["nome"] or "-",
                    cpf=emp["cpf"] or "-",
                    cargo=emp["cargo"] or "-",
                    salario=float(emp["salario_base"] or 0),
                    admissao=emp["data_admissao"].strftime("%d/%m/%Y") if emp["data_admissao"] else "-",
                    matricula=emp["matricula"] or "-",
                    competencia=comp_str,
                )
                safe_nome = (emp["nome"] or "func").replace(" ", "_")[:30]
                pdf_name = f"contracheque_{safe_nome}_{comp.strftime('%Y%m') if comp else '202603'}"

            if pdf_bytes:
                path = _save_pdf(pdf_bytes, pdf_name)
                await db.execute(
                    text("UPDATE ged_kit_documents SET file_path = :fp WHERE id = :did"),
                    {"fp": path, "did": str(d["id"])},
                )
                gerados += 1
            else:
                erros += 1
        except Exception as e:
            logger.error("Erro gerando PDF %s: %s", dtype, e)
            erros += 1

    await db.commit()
    return {"kit_id": kit_id, "gerados": gerados, "erros": erros, "total_docs": len(docs)}


@router.post("/kits/generate-all-pdfs", status_code=201)
async def generate_all_pdfs(
    reference_month: str = Query("2026-03-01"),
    current_user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Gera PDFs para todos os kits de um mes."""
    kits = (
        (
            await db.execute(
                text("SELECT id FROM ged_document_kits WHERE reference_month = :rm"),
                {"rm": reference_month},
            )
        )
        .mappings()
        .all()
    )

    total_gerados = 0
    detalhes = []
    for k in kits:
        kit_result = (
            (await db.execute(text("SELECT * FROM ged_document_kits WHERE id = :id"), {"id": str(k["id"])}))
            .mappings()
            .first()
        )
        if not kit_result:
            continue

        comp = kit_result["reference_month"]
        comp_str = f"{comp.month:02d}/{comp.year}" if comp else "03/2026"

        docs = (
            (await db.execute(text("SELECT * FROM ged_kit_documents WHERE kit_id = :kid"), {"kid": str(k["id"])}))
            .mappings()
            .all()
        )

        gerados = 0
        for d in docs:
            dtype = (d["document_type"] or "").lower()
            existing = d["file_path"] or ""
            if existing.startswith("ged/kits/") and (UPLOAD_DIR / existing.replace("ged/kits/", "")).exists():
                continue

            try:
                pdf_bytes = None
                pdf_name = ""
                if "contracheque" in dtype and d["employee_id"]:
                    emp = (
                        (
                            await db.execute(
                                text(
                                    "SELECT nome, cpf, cargo, salario_base, data_admissao, matricula FROM employees WHERE id = :eid"
                                ),
                                {"eid": str(d["employee_id"])},
                            )
                        )
                        .mappings()
                        .first()
                    )
                    if emp:
                        pdf_bytes = _gerar_contracheque(
                            nome=emp["nome"] or "-",
                            cpf=emp["cpf"] or "-",
                            cargo=emp["cargo"] or "-",
                            salario=float(emp["salario_base"] or 0),
                            admissao=emp["data_admissao"].strftime("%d/%m/%Y") if emp["data_admissao"] else "-",
                            matricula=emp["matricula"] or "-",
                            competencia=comp_str,
                        )
                        pdf_name = f"cc_{(emp['nome'] or 'f').replace(' ', '_')[:20]}_{comp.strftime('%Y%m') if comp else '202603'}"

                if pdf_bytes:
                    path = _save_pdf(pdf_bytes, pdf_name)
                    await db.execute(
                        text("UPDATE ged_kit_documents SET file_path = :fp WHERE id = :did"),
                        {"fp": path, "did": str(d["id"])},
                    )
                    gerados += 1
            except Exception:
                pass

        total_gerados += gerados
        detalhes.append({"kit_id": str(k["id"]), "gerados": gerados})

    await db.commit()
    return {"kits_processados": len(kits), "total_pdfs_gerados": total_gerados, "detalhes": detalhes}


@router.post("/kits/{kit_id}/add-nfse", status_code=201)
async def add_nfse_to_kit(
    kit_id: str,
    current_user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Adiciona NFS-e reais do cliente ao kit e gera PDFs."""
    kit = (await db.execute(text("SELECT * FROM ged_document_kits WHERE id = :id"), {"id": kit_id})).mappings().first()
    if not kit:
        raise HTTPException(404, "Kit nao encontrado")

    client_id = str(kit["client_id"])
    comp = kit["reference_month"]

    nfses = (
        (
            await db.execute(
                text(
                    "SELECT * FROM nfses WHERE condominio_id = :cid AND data_competencia BETWEEN :d1 AND :d2 AND active = true"
                ),
                {"cid": client_id, "d1": f"{comp.year}-{comp.month:02d}-01", "d2": f"{comp.year}-{comp.month:02d}-28"},
            )
        )
        .mappings()
        .all()
    )

    added = 0
    for n in nfses:
        exists = (
            await db.execute(
                text("SELECT 1 FROM ged_kit_documents WHERE kit_id = :kid AND source_record_id = :sid"),
                {"kid": kit_id, "sid": str(n["id"])},
            )
        ).first()
        if exists:
            continue

        pdf_bytes = _gerar_nfse_pdf(
            numero=n["numero_nfse"] or str(n["numero_rps"]),
            tomador=n["tomador_razao_social"],
            cnpj=n["tomador_cpf_cnpj"],
            valor=float(n["valor_servicos"]),
            iss=float(n["iss_valor"] or 0),
            descricao=n["descricao_servico"],
            competencia=f"{comp.month:02d}/{comp.year}",
        )
        path = _save_pdf(pdf_bytes, f"nfse_{n['numero_nfse'] or n['numero_rps']}_{comp.strftime('%Y%m')}")

        await db.execute(
            text(
                "INSERT INTO ged_kit_documents (id, kit_id, document_type, document_name, file_path, "
                "source_module, source_record_id, auto_generated, is_signed, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :kid, 'nfse', :name, :fp, 'fiscal', :sid, true, false, NOW(), NOW())"
            ),
            {
                "kid": kit_id,
                "name": f"NFS-e {n['numero_nfse'] or n['numero_rps']} - {n['tomador_razao_social'][:30]}",
                "fp": path,
                "sid": str(n["id"]),
            },
        )
        added += 1

    await db.commit()
    return {"kit_id": kit_id, "nfse_adicionadas": added, "nfse_encontradas": len(nfses)}


@router.get("/kits/{kit_id}/download-zip")
async def download_kit_zip(
    kit_id: str,
    current_user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Gera e retorna ZIP do kit com todos os PDFs."""
    kit = (await db.execute(text("SELECT * FROM ged_document_kits WHERE id = :id"), {"id": kit_id})).mappings().first()
    if not kit:
        raise HTTPException(404, "Kit nao encontrado")

    docs = (
        (await db.execute(text("SELECT * FROM ged_kit_documents WHERE kit_id = :kid"), {"kid": kit_id}))
        .mappings()
        .all()
    )

    # Build employee name lookup for per-employee docs
    emp_names: dict[str, str] = {}
    for d in docs:
        eid = d["employee_id"]
        if eid and str(eid) not in emp_names:
            emp_row = (
                (await db.execute(text("SELECT nome FROM employees WHERE id = :eid"), {"eid": str(eid)}))
                .mappings()
                .first()
            )
            if emp_row:
                emp_names[str(eid)] = emp_row["nome"]

    buf = io.BytesIO()
    included = 0
    seen_names: dict[str, int] = {}
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for d in docs:
            fp = d["file_path"] or ""
            if not fp:
                continue
            full = Path(f"/app/uploads/{fp}")
            if full.exists():
                base = (d["document_name"] or d["document_type"] or "doc").replace("/", "_").replace("\\", "_")

                # Add employee name for per-employee docs
                if d["employee_id"] and d["document_type"] in (
                    "contracheque",
                    "comprovante_va",
                    "comprovante_vt",
                    "comprovante_vr",
                    "folha_ponto",
                    "escala_mes",
                    "comp_salario",
                ):
                    emp_name = emp_names.get(str(d["employee_id"]), "")
                    if emp_name:
                        short = "_".join(emp_name.split()[:2])
                        base = f"{d['document_type']}_{short}"

                # Remove .pdf if already present, then add once
                if base.endswith(".pdf"):
                    base = base[:-4]
                arcname = f"{base[:60]}.pdf"

                # Deduplicate names
                if arcname in seen_names:
                    seen_names[arcname] += 1
                    name_no_ext = arcname[:-4]
                    arcname = f"{name_no_ext}_{seen_names[arcname]}.pdf"
                else:
                    seen_names[arcname] = 0

                zf.write(full, arcname)
                included += 1

        idx = f"KIT MENSAL — {kit['reference_month']}\nDocumentos: {included}\n"
        idx += "\n".join(d["document_name"] or d["document_type"] for d in docs)
        zf.writestr("INDICE.txt", idx)

    buf.seek(0)
    nome = f"kit_{kit['reference_month']}_{kit_id[:8]}.zip"
    return StreamingResponse(
        buf, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{nome}"'}
    )
