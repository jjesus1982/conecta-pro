"""
Controller do Kit Real — gera documentos conforme estrutura auditada do Google Drive.

Endpoints:
- POST /kit-real/{kit_id}/gerar — gera PDFs reais para 1 kit
- POST /kit-real/gerar-todos — gera PDFs para todos os kits do mes
- GET  /kit-real/{kit_id}/checklist — o que esta pronto e o que falta
"""

import hashlib
import io
import logging
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.crm.services import pdf_branding as B

logger = logging.getLogger(__name__)
router = APIRouter(tags=["GED - Kit Real"])


def _brand_build(doc, story, titulo: str | None = None):
    """doc.build com o cabeçalho/rodapé da marca Conecta Mais (logo completa + título azul + réguas)."""
    doc.build(
        story,
        onFirstPage=lambda cv, dc: B.header_footer(cv, dc, titulo=titulo),
        onLaterPages=lambda cv, dc: B.header_footer(cv, dc, titulo=titulo),
    )


async def _get_employees_for_client(db: AsyncSession, client_id: str) -> list[dict]:
    """Busca funcionarios alocados no cliente via posts+allocations."""
    rows = (
        (
            await db.execute(
                text(
                    "SELECT DISTINCT e.id, e.nome, e.cpf, e.cargo, e.salario_base, "
                    "e.data_admissao, e.matricula "
                    "FROM employees e "
                    "JOIN allocations a ON a.employee_id = e.id AND a.status = 'active' "
                    "JOIN posts p ON a.post_id = p.id AND p.client_id::text = :cid "
                    "WHERE e.is_active = true "
                    "ORDER BY e.nome"
                ),
                {"cid": client_id},
            )
        )
        .mappings()
        .all()
    )
    return [
        {
            "id": str(r["id"]),
            "nome": r["nome"],
            "cpf": r["cpf"],
            "cargo": r["cargo"],
            "salario_base": r["salario_base"],
            "data_admissao": r["data_admissao"].strftime("%d/%m/%Y") if r["data_admissao"] else "-",
            "matricula": r["matricula"],
        }
        for r in rows
    ]


async def _gerar_kit_real(db: AsyncSession, kit_id: str) -> dict:
    """Gera os 4 PDFs consolidados + NFS-e para 1 kit."""
    from modules.ged.services.kit_real_engine import (
        gerar_contracheques_consolidado,
        gerar_folha_pagamento,
        gerar_folhas_ponto,
        gerar_recibo_vt_va,
    )

    kit = (await db.execute(text("SELECT * FROM ged_document_kits WHERE id = :id"), {"id": kit_id})).mappings().first()
    if not kit:
        return {"erro": "Kit nao encontrado"}

    client_id = str(kit["client_id"])
    comp = kit["reference_month"] or date(2026, 3, 1)

    # Nome do cliente
    gc = (
        (await db.execute(text("SELECT name FROM ged_clients WHERE id::text = :cid"), {"cid": client_id}))
        .mappings()
        .first()
    )
    cliente_nome = gc["name"] if gc else "Cliente"

    employees = await _get_employees_for_client(db, client_id)
    if not employees:
        return {"kit_id": kit_id, "cliente": cliente_nome, "gerados": 0, "motivo": "Sem funcionarios alocados"}

    gerados = 0
    docs_gerados = []

    # 1. Folha de Pagamento
    path = gerar_folha_pagamento(employees, comp, cliente_nome)
    if path:
        await _upsert_doc(db, kit_id, "folha_pagamento", "Folha de Pagamento.pdf", path)
        gerados += 1
        docs_gerados.append("folha_pagamento")

    # 2. Contracheques consolidados
    path = gerar_contracheques_consolidado(employees, comp)
    if path:
        await _upsert_doc(db, kit_id, "contracheques_consolidado", "Contracheques.pdf", path)
        gerados += 1
        docs_gerados.append("contracheques_consolidado")

    # 3. Folhas de Ponto
    path = gerar_folhas_ponto(employees, comp, cliente_nome)
    if path:
        await _upsert_doc(db, kit_id, "folhas_ponto_consolidado", "Folhas_de_Ponto.pdf", path)
        gerados += 1
        docs_gerados.append("folhas_ponto_consolidado")

    # 4. Recibo VT+VA
    path = gerar_recibo_vt_va(employees, comp, cliente_nome)
    if path:
        await _upsert_doc(db, kit_id, "recibo_vt_va", "Recibo_VT_VA.pdf", path)
        gerados += 1
        docs_gerados.append("recibo_vt_va")

    # 5. NFS-e
    nfse_count = await _add_nfse_to_kit(db, kit_id, client_id, comp)
    gerados += nfse_count
    if nfse_count:
        docs_gerados.append(f"nfse x{nfse_count}")

    # 6. Certidoes (puxar do bidding_certificates — dados internos)
    cert_count = await _add_certidoes(db, kit_id, comp)
    gerados += cert_count
    if cert_count:
        docs_gerados.append(f"certidoes x{cert_count}")

    # 7. FGTS/DCTF/INSS/ISS (puxar do fiscal_obligations — dados internos)
    fiscal_count = await _add_fiscal_docs(db, kit_id, comp)
    gerados += fiscal_count
    if fiscal_count:
        docs_gerados.append(f"fiscal x{fiscal_count}")

    # 8. Comprovantes bancarios de salario (puxar do bank_transactions)
    bank_count = await _add_comprovantes_bancarios(db, kit_id, employees, comp)
    gerados += bank_count
    if bank_count:
        docs_gerados.append(f"comp_bancario x{bank_count}")

    # 9. Boleto NFS-e (puxar do receivable_accounts)
    try:
        boleto_count = await _add_boleto_nfse(db, kit_id, client_id, comp)
        gerados += boleto_count
        if boleto_count:
            docs_gerados.append(f"boleto_nfse x{boleto_count}")
    except Exception as exc:
        logger.warning("Erro gerando boleto_nfse: %s", exc)

    # 10. Comprovante VT (puxar do bank_transactions + employees)
    try:
        vt_count = await _add_comprovante_vt(db, kit_id, client_id, comp)
        gerados += vt_count
        if vt_count:
            docs_gerados.append("comprovante_vt")
    except Exception as exc:
        logger.warning("Erro gerando comprovante_vt: %s", exc, exc_info=True)

    await db.commit()

    # ATLAS: registra kit concluído para aprendizado contínuo (fire-and-forget)
    try:
        from modules.gedeon.agents.atlas import atlas as _atlas

        competencia_str = comp.strftime("%Y-%m") if hasattr(comp, "strftime") else str(comp)[:7]
        _atlas.registrar_kit_concluido(
            client_id=client_id,
            competencia=competencia_str,
            tipo_kit="maos_de_obra",
            score_final=100,
            docs_total=gerados,
            docs_auto=gerados,
            observacoes="",
            checklist_respostas={},
            movimentacoes=[],
            pendencias=[],
        )
    except Exception:
        pass

    return {
        "kit_id": kit_id,
        "cliente": cliente_nome,
        "funcionarios": len(employees),
        "gerados": gerados,
        "documentos": docs_gerados,
    }


async def _add_certidoes(db: AsyncSession, kit_id: str, comp: date) -> int:
    """Puxa certidoes validas do bidding_certificates e gera PDFs."""

    MAPA = {
        "FGTS": "cnd_caixa",
        "CND_FEDERAL": "cnd_receita",
        "CND_ESTADUAL": "cnd_sefaz",
        "CND_MUNICIPAL": "cnd_prefeitura",
        "CNDT": "cnd_trabalhista",
    }

    certs = (
        (
            await db.execute(
                text(
                    "SELECT tipo, nome, situacao, data_validade "
                    "FROM bidding_certificates "
                    "WHERE ativo = true AND data_validade::date >= :hoje AND tipo IN ('FGTS','CND_FEDERAL','CND_ESTADUAL','CND_MUNICIPAL','CNDT') "
                    "ORDER BY tipo"
                ),
                {"hoje": comp},
            )
        )
        .mappings()
        .all()
    )

    added = 0
    for c in certs:
        doc_type = MAPA.get(c["tipo"])
        if not doc_type:
            continue

        exists = (
            await db.execute(
                text("SELECT 1 FROM ged_kit_documents WHERE kit_id = :kid AND document_type = :dt"),
                {"kid": kit_id, "dt": doc_type},
            )
        ).first()
        if exists:
            continue

        # Gerar PDF simples da certidao
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm, mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        buf = io.BytesIO()
        # topMargin 42mm p/ não sobrepor o cabeçalho da marca (logo completa Conecta Mais)
        doc = SimpleDocTemplate(
            buf, pagesize=A4, topMargin=42 * mm, bottomMargin=2 * cm, leftMargin=2 * cm, rightMargin=2 * cm
        )
        st = getSampleStyleSheet()
        AZ = colors.HexColor("#0A2540")
        story: list[Any] = []
        story += [
            Paragraph(
                f'<b><font color="#0A2540" size="14">{c["nome"]}</font></b>', ParagraphStyle("t", alignment=TA_CENTER)
            ),
            Spacer(1, 0.4 * cm),
            Paragraph(
                f'<font size="9" color="grey">{B.EMPRESA["nome"]} — CNPJ {B.EMPRESA["cnpj"]}</font>',
                ParagraphStyle("s", alignment=TA_CENTER),
            ),
            Spacer(1, 0.5 * cm),
        ]
        data = [
            ["Tipo", c["tipo"]],
            ["Situacao", c["situacao"]],
            ["Validade", c["data_validade"].strftime("%d/%m/%Y") if c["data_validade"] else "-"],
            ["Status", "VALIDA" if c["situacao"] in ("REGULAR", "NEGATIVA", "VALIDO") else c["situacao"]],
        ]
        t = Table(data, colWidths=[5 * cm, 12 * cm])
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), AZ),
                    ("TEXTCOLOR", (0, 0), (0, -1), colors.white),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                    ("PADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(t)
        story.append(Spacer(1, 0.5 * cm))
        story.append(
            Paragraph(
                '<font size="8" color="grey">Documento extraido do sistema Conecta PRO. '
                "Consulte a autenticidade nos portais oficiais.</font>",
                st["Normal"],
            )
        )
        _brand_build(doc, story, titulo="CERTIDÃO")
        chk = hashlib.sha256(buf.getvalue()).hexdigest()[:12]
        fname = f"{doc_type}_{chk}.pdf"
        Path("/app/uploads/ged/kits").mkdir(parents=True, exist_ok=True)
        Path(f"/app/uploads/ged/kits/{fname}").write_bytes(buf.getvalue())
        fp = f"ged/kits/{fname}"

        await db.execute(
            text(
                "INSERT INTO ged_kit_documents (id, kit_id, document_type, document_name, file_path, "
                "source_module, auto_generated, is_signed, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :kid, :dt, :dn, :fp, 'fiscal', true, true, NOW(), NOW())"
            ),
            {"kid": kit_id, "dt": doc_type, "dn": f"{c['nome'][:50]}.pdf", "fp": fp},
        )
        added += 1

    return added


async def _add_fiscal_docs(db: AsyncSession, kit_id: str, comp: date) -> int:
    """Puxa FGTS, DCTF, INSS, ISS do fiscal_obligations e gera PDFs."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm, mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    # Competencia M-1 para FGTS/DCTF
    if comp.month == 1:
        m_ant, a_ant = 12, comp.year - 1
    else:
        m_ant, a_ant = comp.month - 1, comp.year

    MAPA = {
        "FGTS": "comprovante_fgts",
        "DCTFWEB": "dctf_declaracao",
        "EFD_REINF": "dctf_extrato",
        "INSS": "gfd_fgts",
        "ISS": "relatorio_gfd_fgts",
        "IRRF": "dctf_recibo",
    }

    obrigacoes = (
        (
            await db.execute(
                text(
                    "SELECT tipo, nome, status, valor_devido, data_vencimento "
                    "FROM fiscal_obligations "
                    "WHERE active = true AND competencia_mes = :m AND competencia_ano = :a "
                    "AND tipo IN ('FGTS','DCTFWEB','EFD_REINF','INSS','ISS','IRRF') "
                    "ORDER BY tipo"
                ),
                {"m": m_ant, "a": a_ant},
            )
        )
        .mappings()
        .all()
    )

    added = 0
    for o in obrigacoes:
        doc_type = MAPA.get(o["tipo"])
        if not doc_type:
            continue

        exists = (
            await db.execute(
                text("SELECT 1 FROM ged_kit_documents WHERE kit_id = :kid AND document_type = :dt"),
                {"kid": kit_id, "dt": doc_type},
            )
        ).first()
        if exists:
            continue

        AZ = colors.HexColor("#0A2540")
        buf = io.BytesIO()
        # topMargin 42mm p/ não sobrepor o cabeçalho da marca (logo completa Conecta Mais)
        doc = SimpleDocTemplate(
            buf, pagesize=A4, topMargin=42 * mm, bottomMargin=2 * cm, leftMargin=2 * cm, rightMargin=2 * cm
        )
        story: list[Any] = []
        story += [
            Paragraph(
                f'<b><font color="#0A2540" size="14">{o["nome"]}</font></b>', ParagraphStyle("t", alignment=TA_CENTER)
            ),
            Spacer(1, 0.3 * cm),
            Paragraph(
                f'<font size="9" color="grey">Competencia: {m_ant:02d}/{a_ant} | {B.EMPRESA["nome"]} — CNPJ {B.EMPRESA["cnpj"]}</font>',
                ParagraphStyle("s", alignment=TA_CENTER),
            ),
            Spacer(1, 0.5 * cm),
        ]
        valor = float(o["valor_devido"] or 0)
        data = [
            ["Obrigacao", o["nome"]],
            ["Tipo", o["tipo"]],
            ["Status", o["status"].upper()],
            ["Valor Devido", f"R$ {valor:,.2f}" if valor > 0 else "Sem valor (declaratorio)"],
            ["Vencimento", o["data_vencimento"].strftime("%d/%m/%Y") if o["data_vencimento"] else "-"],
        ]
        t = Table(data, colWidths=[5 * cm, 12 * cm])
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), AZ),
                    ("TEXTCOLOR", (0, 0), (0, -1), colors.white),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                    ("PADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(t)
        _brand_build(doc, story, titulo="OBRIGAÇÃO FISCAL")
        chk = hashlib.sha256(buf.getvalue()).hexdigest()[:12]
        fname = f"{doc_type}_{m_ant:02d}{a_ant}_{chk}.pdf"
        from pathlib import Path

        Path(f"/app/uploads/ged/kits/{fname}").write_bytes(buf.getvalue())

        await db.execute(
            text(
                "INSERT INTO ged_kit_documents (id, kit_id, document_type, document_name, file_path, "
                "source_module, auto_generated, is_signed, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :kid, :dt, :dn, :fp, 'fiscal', true, false, NOW(), NOW())"
            ),
            {"kid": kit_id, "dt": doc_type, "dn": f"{o['nome']} {m_ant:02d}/{a_ant}", "fp": f"ged/kits/{fname}"},
        )
        added += 1

    return added


async def _add_comprovantes_bancarios(db: AsyncSession, kit_id: str, employees: list[dict], comp: date) -> int:
    """Puxa comprovantes de pagamento de salario do bank_transactions."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm, mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    # Buscar transacoes do mes que parecem pagamento de salario
    txns = (
        (
            await db.execute(
                text(
                    "SELECT description, amount, transaction_date, document_number "
                    "FROM bank_transactions "
                    "WHERE transaction_type = 'credit' "
                    "AND EXTRACT(MONTH FROM transaction_date) = :m "
                    "AND EXTRACT(YEAR FROM transaction_date) = :a "
                    "AND (description ILIKE '%salario%' OR description ILIKE '%folha%' "
                    "     OR description ILIKE '%PIX ENVIADO%' OR description ILIKE '%PAGAMENTO%') "
                    "ORDER BY transaction_date DESC LIMIT 50"
                ),
                {"m": comp.month, "a": comp.year},
            )
        )
        .mappings()
        .all()
    )

    if not txns:
        return 0

    exists = (
        await db.execute(
            text("SELECT 1 FROM ged_kit_documents WHERE kit_id = :kid AND document_type = 'comprovante_salario'"),
            {"kid": kit_id},
        )
    ).first()
    if exists:
        return 0

    # Gerar PDF consolidado de comprovantes bancarios
    AZ = colors.HexColor("#0A2540")
    LJ = colors.HexColor("#FF6B35")
    buf = io.BytesIO()
    # topMargin 42mm p/ não sobrepor o cabeçalho da marca (logo completa Conecta Mais)
    doc = SimpleDocTemplate(
        buf, pagesize=A4, topMargin=42 * mm, bottomMargin=1.5 * cm, leftMargin=2 * cm, rightMargin=2 * cm
    )
    story: list[Any] = []
    story += [
        Paragraph(
            f'<b><font color="#0A2540" size="13">EXTRATO BANCARIO — PAGAMENTOS {comp.strftime("%m/%Y")}</font></b>',
            ParagraphStyle("t", alignment=TA_CENTER),
        ),
        Spacer(1, 0.3 * cm),
        Paragraph(
            f'<font size="9" color="grey">{B.EMPRESA["nome"]} — CNPJ {B.EMPRESA["cnpj"]}</font>',
            ParagraphStyle("s", alignment=TA_CENTER),
        ),
        Spacer(1, 0.5 * cm),
    ]

    rows = [["Data", "Descricao", "Valor", "Doc"]]
    total = 0.0
    for t_item in txns[:30]:
        val = float(t_item["amount"] or 0)
        total += val
        rows.append(
            [
                t_item["transaction_date"].strftime("%d/%m") if t_item["transaction_date"] else "-",
                (t_item["description"] or "-")[:45],
                f"R$ {val:,.2f}",
                (t_item["document_number"] or "-")[:15],
            ]
        )
    rows.append(["", "TOTAL", f"R$ {total:,.2f}", ""])

    t = Table(rows, colWidths=[2 * cm, 9 * cm, 3 * cm, 3 * cm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), AZ),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                ("ALIGN", (2, 0), (2, -1), "RIGHT"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F8FAFC")]),
                ("BACKGROUND", (0, -1), (-1, -1), LJ),
                ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("PADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(t)
    _brand_build(doc, story, titulo="EXTRATO BANCÁRIO")
    chk = hashlib.sha256(buf.getvalue()).hexdigest()[:12]
    fname = f"extrato_bancario_{comp.strftime('%Y%m')}_{chk}.pdf"

    Path(f"/app/uploads/ged/kits/{fname}").write_bytes(buf.getvalue())

    await db.execute(
        text(
            "INSERT INTO ged_kit_documents (id, kit_id, document_type, document_name, file_path, "
            "source_module, auto_generated, is_signed, created_at, updated_at) "
            "VALUES (gen_random_uuid(), :kid, 'comprovante_salario', :dn, :fp, 'banco', true, false, NOW(), NOW())"
        ),
        {"kid": kit_id, "dn": f"Extrato Bancario {comp.strftime('%m/%Y')}", "fp": f"ged/kits/{fname}"},
    )
    return 1


async def _add_boleto_nfse(db: AsyncSession, kit_id: str, client_id: str, comp: date) -> int:
    """Gera PDF de boleto a partir de receivable_accounts ou NFS-e."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm, mm
    from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    exists = (
        await db.execute(
            text("SELECT 1 FROM ged_kit_documents WHERE kit_id = :kid AND document_type = 'boleto_nfse'"),
            {"kid": kit_id},
        )
    ).first()
    if exists:
        return 0

    # Get NFS-e data for this client to generate boleto
    nfses = (
        (
            await db.execute(
                text(
                    "SELECT numero_nfse, valor_servicos, tomador_razao_social, data_competencia FROM nfses WHERE condominio_id::text = :cid AND active = true ORDER BY data_competencia DESC LIMIT 2"
                ),
                {"cid": client_id},
            )
        )
        .mappings()
        .all()
    )
    if not nfses:
        return 0

    gc = (
        (await db.execute(text("SELECT name FROM ged_clients WHERE id::text = :cid"), {"cid": client_id}))
        .mappings()
        .first()
    )
    cliente_nome = gc["name"] if gc else "Cliente"
    total_valor = sum(float(n["valor_servicos"]) for n in nfses)
    mes_ano = comp.strftime("%m/%Y")

    AZ2 = colors.HexColor("#1E3A5F")
    buf = io.BytesIO()
    # topMargin 42mm p/ não sobrepor o cabeçalho da marca (logo completa Conecta Mais)
    doc = SimpleDocTemplate(
        buf, pagesize=A4, topMargin=42 * mm, bottomMargin=1.5 * cm, leftMargin=2 * cm, rightMargin=2 * cm
    )
    story: list[Any] = []

    # Título limpo + valor total do boleto (o cabeçalho da marca é desenhado por B.header_footer)
    story.append(
        Paragraph(
            '<b><font color="#0A2540" size="14">BOLETO / COBRANÇA</font></b>'
            f'<br/><font color="#FF6B35" size="15">R$ {total_valor:,.2f}</font>',
            ParagraphStyle("boleto_titulo", spaceAfter=6),
        )
    )
    story.append(Spacer(1, 0.3 * cm))

    nfs_str = ", ".join(f"NF {n['numero_nfse']}" for n in nfses)
    dados = [
        ["BENEFICIARIO", f"{B.EMPRESA['nome']} — CNPJ {B.EMPRESA['cnpj']}"],
        ["PAGADOR", cliente_nome],
        ["REFERENCIA", f"Servicos prestados — {mes_ano} ({nfs_str})"],
        ["VENCIMENTO", f"15/{comp.strftime('%m/%Y')}"],
        ["VALOR", f"R$ {total_valor:,.2f}"],
        ["AG/CONTA", "0001 / 37099007-2 — Banco Inter"],
        ["PIX (CNPJ)", "35.710.481/0001-03"],
    ]
    t = Table(dados, colWidths=[4 * cm, 13 * cm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), AZ2),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.white),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(t)
    story.append(Spacer(1, 0.4 * cm))
    story.append(HRFlowable(width="100%", thickness=1, color=B.LARANJA))
    story.append(Spacer(1, 0.2 * cm))
    story.append(
        Paragraph(
            f'<font size="7" color="grey">{B.EMPRESA["nome"]} | CNPJ {B.EMPRESA["cnpj"]} | '
            f"{B.EMPRESA['fone']} | {B.EMPRESA['site']} | {mes_ano}</font>",
            ParagraphStyle("ft", alignment=TA_CENTER),
        )
    )

    _brand_build(doc, story, titulo="BOLETO NFS-e")
    chk = hashlib.sha256(buf.getvalue()).hexdigest()[:12]
    fname = f"boleto_nfse_{comp.strftime('%Y%m')}_{chk}.pdf"
    Path(f"/app/uploads/ged/kits/{fname}").write_bytes(buf.getvalue())
    fp = f"ged/kits/{fname}"

    await db.execute(
        text(
            "INSERT INTO ged_kit_documents (id, kit_id, document_type, document_name, file_path, source_module, auto_generated, is_signed, created_at, updated_at) VALUES (gen_random_uuid(), :kid, 'boleto_nfse', :dn, :fp, 'banco', true, false, NOW(), NOW())"
        ),
        {"kid": kit_id, "dn": f"Boleto NFS-e {mes_ano}", "fp": fp},
    )
    return 1


async def _add_comprovante_vt(db: AsyncSession, kit_id: str, client_id: str, comp: date) -> int:
    """Gera comprovante VT consolidado a partir dos funcionarios alocados."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm, mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    exists = (
        await db.execute(
            text(
                "SELECT 1 FROM ged_kit_documents WHERE kit_id = :kid AND document_type = 'comprovante_vt' AND file_path LIKE 'ged/kits/%'"
            ),
            {"kid": kit_id},
        )
    ).first()
    if exists:
        return 0

    employees = await _get_employees_for_client(db, client_id)
    if not employees:
        return 0

    gc = (
        (await db.execute(text("SELECT name FROM ged_clients WHERE id::text = :cid"), {"cid": client_id}))
        .mappings()
        .first()
    )
    cliente_nome = gc["name"] if gc else "Cliente"
    mes_ano = comp.strftime("%m/%Y")
    AZ = colors.HexColor("#0A2540")
    LJ = colors.HexColor("#FF6B35")
    CZ = colors.HexColor("#F8FAFC")

    buf = io.BytesIO()
    # topMargin 42mm p/ não sobrepor o cabeçalho da marca (logo completa Conecta Mais)
    doc = SimpleDocTemplate(
        buf, pagesize=A4, topMargin=42 * mm, bottomMargin=1.5 * cm, leftMargin=1.5 * cm, rightMargin=1.5 * cm
    )
    st = getSampleStyleSheet()
    story: list[Any] = []
    story.append(
        Paragraph(f'<b><font color="#0A2540" size="12">COMPROVANTE VALE TRANSPORTE — {mes_ano}</font></b>', st["Title"])
    )
    story.append(
        Paragraph(
            f'<font size="8" color="grey">{cliente_nome} | {B.EMPRESA["nome"]} — CNPJ {B.EMPRESA["cnpj"]}</font>',
            st["Normal"],
        )
    )
    story.append(Spacer(1, 0.4 * cm))

    rows = [["No", "Funcionario", "Cargo", "Salario", "VT Bruto (22d)", "Desc 6%", "VT Liquido", "Assin."]]
    tvt = td = tl = 0.0
    for i, e in enumerate(employees, 1):
        sal = float(e.get("salario_base") or 0)
        vt_bruto = round(sal * 0.06 * 22 / 30, 2)  # proporcional 22 dias uteis
        desc = round(sal * 0.06, 2)
        liq = round(max(vt_bruto - desc, 0), 2)
        tvt += vt_bruto
        td += desc
        tl += liq
        rows.append(
            [
                str(i),
                e.get("nome", "-")[:25],
                e.get("cargo", "-")[:15],
                f"R${sal:,.2f}",
                f"R${vt_bruto:,.2f}",
                f"R${desc:,.2f}",
                f"R${liq:,.2f}",
                "",
            ]
        )
    rows.append(["", "TOTAL", "", "", f"R${tvt:,.2f}", f"R${td:,.2f}", f"R${tl:,.2f}", ""])

    t = Table(rows, colWidths=[0.7 * cm, 4.5 * cm, 2.5 * cm, 2.2 * cm, 2.2 * cm, 2 * cm, 2.2 * cm, 2.2 * cm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), AZ),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("ALIGN", (3, 0), (6, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, CZ]),
                ("BACKGROUND", (0, -1), (-1, -1), LJ),
                ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("PADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(t)
    story.append(Spacer(1, 0.3 * cm))
    story.append(
        Paragraph(
            '<font size="7" color="grey">VT calculado: 6% salario x 22 dias uteis. Desconto: 6% salario base (CLT Art. 4o Lei 7.418/85)</font>',
            st["Normal"],
        )
    )

    _brand_build(doc, story, titulo="COMPROVANTE VT")
    chk = hashlib.sha256(buf.getvalue()).hexdigest()[:12]
    fname = f"comp_vt_{comp.strftime('%Y%m')}_{chk}.pdf"
    Path(f"/app/uploads/ged/kits/{fname}").write_bytes(buf.getvalue())
    fp = f"ged/kits/{fname}"

    await db.execute(
        text(
            "INSERT INTO ged_kit_documents (id, kit_id, document_type, document_name, file_path, source_module, auto_generated, is_signed, created_at, updated_at) VALUES (gen_random_uuid(), :kid, 'comprovante_vt', :dn, :fp, 'sistema', true, false, NOW(), NOW())"
        ),
        {"kid": kit_id, "dn": f"Comprovante VT {mes_ano}", "fp": fp},
    )
    return 1


async def _upsert_doc(db: AsyncSession, kit_id: str, doc_type: str, doc_name: str, file_path: str) -> None:
    """Insere ou atualiza documento no kit."""
    existing = (
        await db.execute(
            text("SELECT id FROM ged_kit_documents WHERE kit_id = :kid AND document_type = :dt"),
            {"kid": kit_id, "dt": doc_type},
        )
    ).first()
    if existing:
        await db.execute(
            text(
                "UPDATE ged_kit_documents SET file_path = :fp, document_name = :dn, updated_at = NOW() WHERE kit_id = :kid AND document_type = :dt"
            ),
            {"fp": file_path, "dn": doc_name, "kid": kit_id, "dt": doc_type},
        )
    else:
        await db.execute(
            text(
                "INSERT INTO ged_kit_documents (id, kit_id, document_type, document_name, file_path, "
                "source_module, auto_generated, is_signed, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :kid, :dt, :dn, :fp, 'sistema', true, false, NOW(), NOW())"
            ),
            {"kid": kit_id, "dt": doc_type, "dn": doc_name, "fp": file_path},
        )


async def _add_nfse_to_kit(db: AsyncSession, kit_id: str, client_id: str, comp: date) -> int:
    """Adiciona NFS-e do cliente (meses jan e fev) ao kit."""
    from modules.ged.controllers.kit_pdf_controller import _gerar_nfse_pdf, _save_pdf

    nfses = (
        (
            await db.execute(
                text(
                    "SELECT * FROM nfses WHERE condominio_id::text = :cid AND active = true ORDER BY data_competencia DESC"
                ),
                {"cid": client_id},
            )
        )
        .mappings()
        .all()
    )

    added = 0
    for n in nfses:
        sid = str(n["id"])
        exists = (
            await db.execute(
                text("SELECT 1 FROM ged_kit_documents WHERE kit_id = :kid AND source_record_id::text = :sid"),
                {"kid": kit_id, "sid": sid},
            )
        ).first()
        if exists:
            continue

        num = n["numero_nfse"] or str(n["numero_rps"])
        pdf_bytes = _gerar_nfse_pdf(
            numero=num,
            tomador=n["tomador_razao_social"],
            cnpj=n["tomador_cpf_cnpj"],
            valor=float(n["valor_servicos"]),
            iss=float(n["iss_valor"] or 0),
            descricao=n["descricao_servico"],
            competencia=n["data_competencia"].strftime("%m/%Y") if n["data_competencia"] else "02/2026",
        )
        path = _save_pdf(
            pdf_bytes, f"nfse_{num}_{n['data_competencia'].strftime('%Y%m') if n['data_competencia'] else '202602'}"
        )
        await db.execute(
            text(
                "INSERT INTO ged_kit_documents (id, kit_id, document_type, document_name, file_path, "
                "source_module, source_record_id, auto_generated, is_signed, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :kid, 'nfse', :dn, :fp, 'fiscal', :sid, true, false, NOW(), NOW())"
            ),
            {"kid": kit_id, "dn": f"NFS-e {num}", "fp": path, "sid": sid},
        )
        added += 1
    return added


# ── Endpoints ─────────────────────────────────────────────────────────────


@router.post("/kit-real/{kit_id}/gerar", status_code=201)
async def gerar_kit_real(
    kit_id: str,
    current_user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Gera todos os PDFs reais para um kit especifico."""
    return await _gerar_kit_real(db, kit_id)


@router.post("/kit-real/gerar-todos", status_code=201)
async def gerar_todos_kits_reais(
    mes: int = Query(3, ge=1, le=12),
    ano: int = Query(2026, ge=2020),
    current_user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Gera PDFs reais para TODOS os kits do mes."""
    kits = (
        (
            await db.execute(
                text("SELECT id FROM ged_document_kits WHERE reference_month = :rm"),
                {"rm": f"{ano}-{mes:02d}-01"},
            )
        )
        .mappings()
        .all()
    )

    resultados = []
    total_gerados = 0
    for k in kits:
        r = await _gerar_kit_real(db, str(k["id"]))
        total_gerados += r.get("gerados", 0)
        resultados.append(r)

    return {
        "competencia": f"{mes:02d}/{ano}",
        "kits_processados": len(kits),
        "total_pdfs_gerados": total_gerados,
        "kits": resultados,
    }


@router.get("/kit-real/{kit_id}/checklist")
async def checklist_kit_real(
    kit_id: str,
    current_user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Checklist do kit: prontos vs pendentes (baseado na anatomia real)."""
    kit = (await db.execute(text("SELECT * FROM ged_document_kits WHERE id = :id"), {"id": kit_id})).mappings().first()
    if not kit:
        raise HTTPException(404, "Kit nao encontrado")

    gc = (
        (await db.execute(text("SELECT name FROM ged_clients WHERE id::text = :cid"), {"cid": str(kit["client_id"])}))
        .mappings()
        .first()
    )

    docs = (
        (
            await db.execute(
                text("SELECT document_type, document_name, file_path FROM ged_kit_documents WHERE kit_id = :kid"),
                {"kid": kit_id},
            )
        )
        .mappings()
        .all()
    )
    tipos_ok = {d["document_type"] for d in docs if d["file_path"] and d["file_path"].startswith("ged/kits/")}

    TIPOS_SISTEMA = ["folha_pagamento", "contracheques_consolidado", "folhas_ponto_consolidado", "recibo_vt_va", "nfse"]
    TIPOS_UPLOAD = [
        "comprovante_fgts",
        "gfd_fgts",
        "relatorio_gfd_fgts",
        "dctf_declaracao",
        "dctf_recibo",
        "dctf_extrato",
        "boleto_nfse",
        "comprovante_salario",
        "comprovante_vt",
    ]
    TIPOS_CERTIDAO = ["cnd_caixa", "cnd_prefeitura", "cnd_receita", "cnd_sefaz", "cnd_trabalhista"]

    checklist = []
    for t in TIPOS_SISTEMA:
        checklist.append({"tipo": t, "categoria": "sistema", "status": "pronto" if t in tipos_ok else "pendente"})
    for t in TIPOS_CERTIDAO:
        checklist.append(
            {"tipo": t, "categoria": "certidao", "status": "pronto" if t in tipos_ok else "pendente_download"}
        )
    for t in TIPOS_UPLOAD:
        checklist.append(
            {"tipo": t, "categoria": "upload_manual", "status": "pronto" if t in tipos_ok else "pendente_upload"}
        )

    prontos = sum(1 for c in checklist if c["status"] == "pronto")
    return {
        "kit_id": kit_id,
        "cliente": gc["name"] if gc else "-",
        "total": len(checklist),
        "prontos": prontos,
        "pendentes": len(checklist) - prontos,
        "percentual": round(prontos / max(1, len(checklist)) * 100, 1),
        "checklist": checklist,
    }


# ── Montagem Guiada (listas suspensas) ─────────────────────────────────────


@router.get("/montar/condominios")
async def listar_condominios_kit(
    current_user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Lista 1: condominios que recebem kit mensal (7 mao de obra + 1 remota)."""
    rows = (
        (
            await db.execute(
                text(
                    "SELECT c.id, c.name, c.document_number, ct.id as contract_id, "
                    "ct.tipo_servico, ct.monthly_value, ct.retencao_iss, ct.retencao_inss, ct.retencao_csll, "
                    "(SELECT p.client_id FROM posts p WHERE p.client_id IS NOT NULL AND p.is_active = true "
                    " AND EXISTS (SELECT 1 FROM allocations a WHERE a.post_id = p.id AND a.status = 'active') "
                    " AND p.name ILIKE '%' || SPLIT_PART(c.name, ' ', 2) || '%' LIMIT 1) as ged_client_id "
                    "FROM contracts ct JOIN clients c ON ct.client_id = c.id "
                    "WHERE ct.is_active = true AND ct.kit_mensal = true "
                    "ORDER BY ct.monthly_value DESC"
                )
            )
        )
        .mappings()
        .all()
    )

    return {
        "total": len(rows),
        "condominios": [
            {
                "client_id": str(r["ged_client_id"] or r["id"]),
                "nome": r["name"],
                "cnpj": r["document_number"],
                "contract_id": str(r["contract_id"]),
                "tipo_servico": r["tipo_servico"],
                "valor_mensal": float(r["monthly_value"] or 0),
                "retencoes": {
                    "iss": r["retencao_iss"] or False,
                    "inss": r["retencao_inss"] or False,
                    "csll": r["retencao_csll"] or False,
                },
            }
            for r in rows
        ],
    }


@router.get("/montar/servicos/{client_id}")
async def listar_servicos_cliente(
    client_id: str,
    current_user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Lista 2: servicos do condominio baseado nas NFS-e reais emitidas."""
    client = (
        (await db.execute(text("SELECT name, document_number FROM clients WHERE id = :cid"), {"cid": client_id}))
        .mappings()
        .first()
    )
    if not client:
        raise HTTPException(404, "Cliente nao encontrado")

    import re

    cnpj = re.sub(r"\D", "", client["document_number"] or "")

    nfses = (
        (
            await db.execute(
                text(
                    "SELECT DISTINCT descricao_servico, codigo_servico, valor_servicos "
                    "FROM nfses WHERE tomador_cpf_cnpj = :cnpj AND active = true "
                    "ORDER BY valor_servicos DESC"
                ),
                {"cnpj": cnpj},
            )
        )
        .mappings()
        .all()
    )

    servicos = []
    seen = set()
    for n in nfses:
        desc = n["descricao_servico"]
        if desc in seen:
            continue
        seen.add(desc)
        tem_mao = any(w in desc.lower() for w in ["portaria", "limpeza", "servicos gerais", "jardinagem", "seguranca"])
        servicos.append(
            {
                "descricao": desc,
                "codigo": n["codigo_servico"],
                "valor_ultima_nf": float(n["valor_servicos"]),
                "tem_mao_de_obra": tem_mao,
            }
        )

    if not servicos:
        servicos.append(
            {"descricao": "Servicos de portaria", "codigo": "11.02", "valor_ultima_nf": 0, "tem_mao_de_obra": True}
        )

    return {"client_id": client_id, "cliente": client["name"], "servicos": servicos}


@router.get("/montar/funcionarios/{client_id}")
async def listar_funcionarios_kit(
    client_id: str,
    current_user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Lista funcionarios alocados no condominio para o kit."""
    employees = await _get_employees_for_client(db, client_id)

    # Buscar ged_client correspondente
    gc = (
        (await db.execute(text("SELECT id, name FROM ged_clients WHERE id::text = :cid"), {"cid": client_id}))
        .mappings()
        .first()
    )
    # Tentar pelo client_id nos posts
    if not gc:
        gc_alt = (
            (
                await db.execute(
                    text(
                        "SELECT g.id, g.name FROM ged_clients g "
                        "JOIN posts p ON p.client_id::text = g.id::text "
                        "JOIN clients c ON c.id = :cid "
                        "WHERE p.is_active = true LIMIT 1"
                    ),
                    {"cid": client_id},
                )
            )
            .mappings()
            .first()
        )
        gc = gc_alt

    return {
        "client_id": client_id,
        "cliente": gc["name"] if gc else "-",
        "total_funcionarios": len(employees),
        "funcionarios": [
            {
                "id": e["id"],
                "nome": e["nome"],
                "cargo": e["cargo"],
                "cpf": e["cpf"],
                "salario_base": float(e["salario_base"] or 0),
                "salario_liquido": round(float(e["salario_base"] or 0) * 0.85, 2),
            }
            for e in employees
        ],
    }


@router.post("/montar/kit", status_code=201)
async def montar_kit_guiado(
    client_id: str = Query(...),
    competencia: str = Query("2026-03-01"),
    current_user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Monta kit completo: gera PDFs + vincula NFS-e + retorna checklist."""
    from datetime import date as d

    d.fromisoformat(competencia)  # validate format

    # Verificar contrato com kit
    ct = (
        (
            await db.execute(
                text(
                    "SELECT kit_mensal, tipo_servico, retencao_iss, retencao_inss, retencao_csll FROM contracts WHERE client_id = :cid AND is_active = true AND kit_mensal = true LIMIT 1"
                ),
                {"cid": client_id},
            )
        )
        .mappings()
        .first()
    )
    if not ct:
        return {"erro": "Cliente nao recebe kit mensal", "sugestao": "Verificar contratos ativos"}

    # Buscar ou criar GED client
    gc = (
        (
            await db.execute(
                text(
                    "SELECT id FROM ged_clients WHERE id::text IN (SELECT p.client_id::text FROM posts p WHERE p.client_id IS NOT NULL) AND id::text = :cid"
                ),
                {"cid": client_id},
            )
        )
        .mappings()
        .first()
    )
    if not gc:
        # Tentar via posts linkados
        gc = (
            (
                await db.execute(
                    text(
                        "SELECT DISTINCT p.client_id as id FROM posts p WHERE p.client_id IS NOT NULL AND EXISTS (SELECT 1 FROM allocations a WHERE a.post_id = p.id AND a.status = 'active') AND p.client_id::text IN (SELECT g.id::text FROM ged_clients g) ORDER BY p.client_id LIMIT 1"
                    ),
                )
            )
            .mappings()
            .first()
        )

    ged_client_id = str(gc["id"]) if gc else client_id

    # Verificar/criar kit
    kit = (
        (
            await db.execute(
                text("SELECT id FROM ged_document_kits WHERE client_id::text = :cid AND reference_month = :rm LIMIT 1"),
                {"cid": ged_client_id, "rm": competencia},
            )
        )
        .mappings()
        .first()
    )

    if kit:
        kit_id = str(kit["id"])
    else:
        await db.execute(
            text(
                "INSERT INTO ged_document_kits (id, client_id, reference_month, status, total_employees, total_documents, completion_percentage, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :cid, :rm, 'em_montagem', 0, 0, 0, NOW(), NOW()) RETURNING id"
            ),
            {"cid": ged_client_id, "rm": competencia},
        )
        await db.commit()
        new_kit = (
            (
                await db.execute(
                    text("SELECT id FROM ged_document_kits WHERE client_id::text = :cid AND reference_month = :rm"),
                    {"cid": ged_client_id, "rm": competencia},
                )
            )
            .mappings()
            .first()
        )
        kit_id = str(new_kit["id"]) if new_kit else "?"

    # Gerar PDFs reais
    result = await _gerar_kit_real(db, kit_id)

    # Adicionar info de retencoes
    result["retencoes"] = {
        "iss": ct["retencao_iss"] or False,
        "inss": ct["retencao_inss"] or False,
        "csll": ct["retencao_csll"] or False,
    }
    result["tipo_servico"] = ct["tipo_servico"]

    return result
