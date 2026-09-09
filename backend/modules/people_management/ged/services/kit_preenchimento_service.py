"""Preenche as vagas do kit do banco com o que o SISTEMA já tem (09/09/2026, kit de teste Conecta Village).

Antes: cada collect_* do KitBuilderService criava a VAGA (KitDocument com file_path NULL) e esperava alguém
(Onvio, Pyetra) trazer o arquivo — o kit do banco era uma lista de vazios. Agora, na montagem, cada vaga tenta se
preencher sozinha, e quando não consegue diz POR QUÊ (relatório `faltas`): esse "por quê" é o que vira cobrança
para o responsável, não um silêncio.

Fontes (nunca fabricadas):
  contracheque   hr_payslips (employee, mês/ano) → gerar_pdf_holerite (mesmo PDF do portal/DP)
  VT/VR          motor da folha (calcular_folha_colaborador) → montar_recibo_vt_vr_pdf (um recibo cobre VT+VR;
                 a vaga VA separada não existe no kit real → apagada)
  escala         shifts do funcionário no mês → montar_escala_pdf
  CND            ged_certidoes da Conecta Patrimonial vigentes (decisão 07/09: certidões só Patrimonial)
  NFS-e          nfse_emitidas_nacional (tomador = cliente, competência do mês) → DANFSe; cliente de
                 HOMOLOGAÇÃO (todos os alocados is_homologacao) → DANFSe SIMULADA, sem valor fiscal
  boleto         cliente de homologação → PDF "BOLETO SIMULADO"; cliente real → arquivado pelo GEDEON (Inter),
                 esta página/serviço não fala com banco (regra da casa)
Arquivos em /app/uploads/kits/<kit_id>/ (mesmo volume de /app/uploads/ponto); o nome do arquivo carrega o nome do
funcionário — no Drive 12 'Contracheque_08.2026.pdf' viravam UM (dedup por nome), medido em 09/09.
"""
from __future__ import annotations

import io
import logging
import re
import unicodedata
from datetime import date
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.people_management.ged.models.client import GedClient
from modules.people_management.ged.models.document_kit import GedDocumentKit
from modules.people_management.ged.models.kit_document import DocumentType, KitDocument, SourceModule

logger = logging.getLogger(__name__)
KITS_STORAGE = Path("/app/uploads/kits")

_CND_MAP = {
    DocumentType.CND_FEDERAL: "certidao_negativa_federal",
    DocumentType.CND_ESTADUAL: "certidao_negativa_estadual",
    DocumentType.CND_MUNICIPAL: "certidao_negativa_municipal",
    DocumentType.CRF_FGTS: "certidao_negativa_fgts",
    DocumentType.CNDT_TRABALHISTA: "certidao_negativa_trabalhista",
}


def _norm(s: str | None) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper().strip()


def _safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", _norm(s))[:40]


def _gravar(kit_id: str, sub: str, nome: str, pdf: bytes) -> str:
    d = KITS_STORAGE / kit_id / sub
    d.mkdir(parents=True, exist_ok=True)
    fp = d / nome
    fp.write_bytes(pdf)
    return str(fp)


async def _crm_client_id(db: AsyncSession, ged_client: GedClient) -> str | None:
    """ged_clients não aponta para clients: casa por CNPJ, senão por nome (name/trading_name)."""
    if ged_client.cnpj:
        cid = (await db.execute(text("SELECT id FROM clients WHERE regexp_replace(document_number,'[^0-9]','','g') = :c"),
                                {"c": re.sub(r"\D", "", ged_client.cnpj)})).scalar()
        if cid:
            return str(cid)
    alvo = _norm(ged_client.name)
    rows = (await db.execute(text("SELECT id, name, trading_name FROM clients"))).fetchall()
    for cid, nome, fant in rows:
        if alvo in (_norm(nome), _norm(fant)):
            return str(cid)
    return None


async def preencher_vagas(db: AsyncSession, kit_id: str) -> dict:
    kit = (await db.execute(select(GedDocumentKit).where(GedDocumentKit.id == kit_id))).scalar_one_or_none()
    if not kit:
        raise ValueError(f"kit {kit_id} não encontrado")
    client = (await db.execute(select(GedClient).where(GedClient.id == kit.client_id))).scalar_one_or_none()
    ref: date = kit.reference_month
    mes, ano = ref.month, ref.year
    docs = (await db.execute(select(KitDocument).where(KitDocument.kit_id == kit_id))).scalars().all()
    rel: dict = {"kit_id": kit_id, "preenchidos": {}, "faltas": [], "apagados": 0}

    def conta(tipo: str) -> None:
        rel["preenchidos"][tipo] = rel["preenchidos"].get(tipo, 0) + 1

    emp_ids = sorted({str(d.employee_id) for d in docs if d.employee_id})
    emp: dict[str, dict] = {}
    if emp_ids:
        rows = (await db.execute(text(
            "SELECT id::text, nome, cpf, pis, matricula, cargo, coalesce(is_homologacao,false) FROM employees WHERE id::text = ANY(:ids)"),
            {"ids": emp_ids})).fetchall()
        emp = {r[0]: {"nome": r[1], "cpf": r[2], "pis": r[3], "matricula": r[4], "cargo": r[5], "homolog": r[6]} for r in rows}
    homolog = bool(emp) and all(e["homolog"] for e in emp.values())
    rel["homologacao"] = homolog

    # ── contracheque ──
    for d in docs:
        if d.document_type != DocumentType.CONTRACHEQUE or d.file_path:
            continue
        pid = (await db.execute(text(
            "SELECT id FROM hr_payslips WHERE employee_id = :e AND reference_month = :m AND reference_year = :a "
            "ORDER BY created_at DESC LIMIT 1"), {"e": str(d.employee_id), "m": mes, "a": ano})).scalar()
        if not pid:
            rel["faltas"].append(f"contracheque {emp.get(str(d.employee_id), {}).get('nome', d.employee_id)}: "
                                 f"sem holerite {mes:02d}/{ano} em hr_payslips (folha não calculada/importada)")
            continue
        try:
            from modules.people_management.employee_portal.services.payslip_pdf_service import gerar_pdf_holerite
            pdf = await gerar_pdf_holerite(db, pid)
            d.file_path = _gravar(kit_id, str(d.employee_id), f"Contracheque_{mes:02d}.{ano}_{_safe(emp.get(str(d.employee_id), {}).get('nome') or str(d.employee_id))}.pdf", pdf)
            d.file_size_bytes = len(pdf)
            d.mime_type = "application/pdf"
            d.source_record_id = pid
            conta("contracheque")
        except Exception as exc:  # noqa: BLE001
            rel["faltas"].append(f"contracheque {d.employee_id}: erro ao gerar PDF — {exc}")

    # ── VT/VR (um recibo cobre os dois; VA não existe no kit real) ──
    from core.database.session import get_sync_db
    recibos: dict[str, tuple[str, int]] = {}
    for d in docs:
        if d.document_type == DocumentType.COMPROVANTE_VA and not d.file_path and d.auto_generated:
            await db.delete(d)
            rel["apagados"] += 1
            continue
        if d.document_type not in (DocumentType.COMPROVANTE_VT, DocumentType.COMPROVANTE_VR) or d.file_path:
            continue
        e = str(d.employee_id)
        if e not in recibos:
            try:
                from modules.people_management.folha.services.calculo_service import calcular_folha_colaborador
                from modules.people_management.folha.services.recibo_vt_vr_pdf import montar_recibo_vt_vr_pdf
                with get_sync_db() as s:
                    r = calcular_folha_colaborador(s, e, mes, ano)
                    posto = s.execute(text("SELECT p.name FROM allocations a JOIN posts p ON p.id=a.post_id "
                                           "WHERE a.employee_id = CAST(:e AS uuid) ORDER BY a.created_at DESC LIMIT 1"), {"e": e}).scalar()
                if "error" in r:
                    rel["faltas"].append(f"VT/VR {emp.get(e, {}).get('nome', e)}: motor da folha — {r['error']}")
                    recibos[e] = ("", 0)
                    continue
                fd = {k: emp.get(e, {}).get(k) for k in ("cpf", "pis", "matricula")}
                fd["posto"] = posto or "—"
                pdf = montar_recibo_vt_vr_pdf(r, fd, vt_concedido=None)
                recibos[e] = (_gravar(kit_id, e, f"Recibo_VT_VR_{mes:02d}.{ano}_{_safe(emp.get(e, {}).get('nome') or e)}.pdf", pdf), len(pdf))
            except Exception as exc:  # noqa: BLE001
                rel["faltas"].append(f"VT/VR {e}: erro ao gerar recibo — {exc}")
                recibos[e] = ("", 0)
        fp, n = recibos[e]
        if fp:
            d.file_path, d.file_size_bytes, d.mime_type = fp, n, "application/pdf"
            conta("vt_vr")

    # ── escala ──
    for d in docs:
        if d.document_type != DocumentType.ESCALA_MES or d.file_path:
            continue
        e = str(d.employee_id)
        rows = (await db.execute(text(
            "SELECT s.shift_date, s.planned_start_time, s.planned_end_time, s.is_off_day, s.is_night_shift, s.planned_hours, p.name "
            "FROM shifts s JOIN scales sc ON sc.id = s.scale_id JOIN posts p ON p.id = sc.post_id "
            "WHERE s.employee_id = CAST(:e AS uuid) AND sc.month = :m AND sc.year = :a AND coalesce(s.is_active,true) "
            "ORDER BY s.shift_date"), {"e": e, "m": mes, "a": ano})).fetchall()
        if not rows:
            rel["faltas"].append(f"escala {emp.get(e, {}).get('nome', e)}: sem turnos em {mes:02d}/{ano} (escala não gerada)")
            continue
        try:
            from modules.operacional.services.escala_pdf import montar_escala_pdf
            turnos = [{"data": r[0], "inicio": r[1], "fim": r[2], "folga": bool(r[3]), "noturno": bool(r[4]), "horas": r[5]} for r in rows]
            fdad = dict(emp.get(e, {}))
            fdad.setdefault("nome", str(e))
            pdf = montar_escala_pdf(fdad, rows[0][6], mes, ano, turnos)
            d.file_path = _gravar(kit_id, e, f"Escala_{mes:02d}.{ano}_{_safe(emp.get(e, {}).get('nome') or e)}.pdf", pdf)
            d.file_size_bytes, d.mime_type = len(pdf), "application/pdf"
            conta("escala")
        except Exception as exc:  # noqa: BLE001
            rel["faltas"].append(f"escala {e}: erro ao gerar PDF — {exc}")

    # ── CNDs (Patrimonial, vigentes) ──
    cnpj_pat = (await db.execute(text("SELECT cnpj FROM empresas WHERE slug = 'conecta_patrimonial'"))).scalar() or ""
    cnpj_pat = re.sub(r"\D", "", cnpj_pat)
    for d in docs:
        tipo = _CND_MAP.get(d.document_type)
        if not tipo or d.file_path:
            continue
        row = (await db.execute(text(
            "SELECT file_path, expiry_date FROM ged_certidoes WHERE regexp_replace(coalesce(cnpj,''),'[^0-9]','','g') = :c "
            "AND document_type = :t AND file_path IS NOT NULL AND (expiry_date IS NULL OR expiry_date >= CURRENT_DATE) "
            "ORDER BY expiry_date DESC NULLS LAST LIMIT 1"), {"c": cnpj_pat, "t": tipo})).first()
        if not row or not Path(row[0]).exists():
            rel["faltas"].append(f"{d.document_name}: sem certidão VIGENTE da Patrimonial em ged_certidoes (robô de CND / renovar)")
            continue
        d.file_path = row[0]
        d.mime_type = "application/pdf"
        d.notes = f"validade {row[1]:%d/%m/%Y}" if row[1] else None
        conta("cnd")

    # ── NFS-e e boleto (nível do kit) ──
    crm_id = await _crm_client_id(db, client) if client else None
    tem = {d.document_type for d in docs}
    if DocumentType.NFS_SERVICO not in tem or DocumentType.BOLETO not in tem:
        await _nfse_e_boleto(db, kit, client, crm_id, homolog, tem, rel)

    await db.flush()
    n_total = (await db.execute(text("SELECT count(*), count(file_path) FROM ged_kit_documents WHERE kit_id = :k"), {"k": kit_id})).first()
    rel["total"], rel["presentes"] = int(n_total[0]), int(n_total[1])
    return rel


async def _nfse_e_boleto(db, kit, client, crm_id, homolog, tem, rel) -> None:
    mes, ano = kit.reference_month.month, kit.reference_month.year
    kid = str(kit.id)
    if not crm_id:
        rel["faltas"].append(f"NFS-e/boleto: cliente GED '{getattr(client, 'name', '?')}' não casa com nenhum cliente do CRM (CNPJ ou nome)")
        return
    cli = (await db.execute(text(
        "SELECT name, document_number, address_street, address_number, address_neighborhood, address_city, address_state, email "
        "FROM clients WHERE id = CAST(:c AS uuid)"), {"c": crm_id})).mappings().first()
    valor = (await db.execute(text(
        "SELECT monthly_value FROM contracts WHERE client_id = CAST(:c AS uuid) AND status = 'active' ORDER BY monthly_value DESC LIMIT 1"),
        {"c": crm_id})).scalar()
    pat = (await db.execute(text(
        "SELECT cnpj, razao_social, inscricao_municipal FROM empresas WHERE slug = 'conecta_patrimonial'"))).first()
    discr = f"Prestação de serviços de portaria/segurança e serviços gerais — competência {mes:02d}/{ano}"

    if DocumentType.NFS_SERVICO not in tem:
        row = None
        if not homolog:
            row = (await db.execute(text(
                "SELECT n.*, e.cnpj AS emit_cnpj, e.razao_social AS emit_nome, e.inscricao_municipal AS emit_im "
                "FROM nfse_emitidas_nacional n LEFT JOIN empresas e ON e.id = n.empresa_id "
                "WHERE regexp_replace(n.tomador_cnpj,'[^0-9]','','g') = :c AND n.competencia = :comp "
                "AND coalesce(n.cancelada,false) = false ORDER BY n.data_emissao DESC LIMIT 1"),
                {"c": re.sub(r"\D", "", cli["document_number"] or ""), "comp": f"{ano:04d}-{mes:02d}"})).mappings().first()
            if not row:
                rel["faltas"].append(f"NFS-e {mes:02d}/{ano}: nenhuma nota emitida para {cli['name']} em nfse_emitidas_nacional (faturar primeiro)")
        elif not valor:
            rel["faltas"].append("NFS-e simulada: contrato ativo sem valor mensal")
        else:
            iss = round(float(valor) * 0.05, 2)
            row = {"numero": "SIMULADA", "chave_acesso": "", "competencia": f"{ano:04d}-{mes:02d}", "data_emissao": date.today(),
                   "emit_cnpj": pat[0] if pat else "", "emit_nome": pat[1] if pat else "", "emit_im": pat[2] if pat else "",
                   "tomador_cnpj": cli["document_number"], "tomador_nome": cli["name"],
                   "descricao": f"SIMULAÇÃO — SEM VALOR FISCAL. {discr}", "valor_servicos": float(valor), "iss_valor": iss,
                   "inss_retido": 0, "valor_liquido": float(valor)}
        if row:
            try:
                from modules.gedeon.services.nfse_danfse_generator import gerar_danfse_de_emitida
                pdf = gerar_danfse_de_emitida(dict(row))
                nome = f"NFSe_{'SIMULADA' if homolog else row.get('numero')}_{mes:02d}.{ano}.pdf"
                db.add(KitDocument(kit_id=kid, employee_id=None, document_type=DocumentType.NFS_SERVICO,
                                   document_name=f"NFS-e {'SIMULADA ' if homolog else ''}{mes:02d}/{ano}",
                                   file_path=_gravar(kid, "faturamento", nome, pdf), file_size_bytes=len(pdf),
                                   mime_type="application/pdf", source_module=SourceModule.FISCAL, auto_generated=True,
                                   is_signed=not homolog, notes="simulação de homologação — sem valor fiscal" if homolog else None))
                rel["preenchidos"]["nfse"] = 1
            except Exception as exc:  # noqa: BLE001
                rel["faltas"].append(f"NFS-e: erro ao gerar DANFSe — {exc}")

    if DocumentType.BOLETO not in tem:
        if not homolog:
            rel["faltas"].append("boleto: cliente real — o boleto do Inter é arquivado pelo GEDEON (kit do Drive); este serviço não fala com banco")
        elif not valor:
            rel["faltas"].append("boleto simulado: contrato ativo sem valor mensal")
        else:
            from datetime import timedelta
            venc = (kit.reference_month.replace(day=28) + timedelta(days=4)).replace(day=10)  # dia 10 do mês seguinte
            pdf = _boleto_simulado_pdf(cli, float(valor), venc, discr, pat)
            db.add(KitDocument(kit_id=kid, employee_id=None, document_type=DocumentType.BOLETO,
                               document_name=f"Boleto SIMULADO {mes:02d}/{ano}", file_path=_gravar(kid, "faturamento", f"Boleto_SIMULADO_{mes:02d}.{ano}.pdf", pdf),
                               file_size_bytes=len(pdf), mime_type="application/pdf", source_module=SourceModule.FISCAL,
                               auto_generated=True, is_signed=False, notes="simulação de homologação — sem valor de cobrança"))
            rel["preenchidos"]["boleto"] = 1


def _boleto_simulado_pdf(cli, valor: float, venc: date, discr: str, pat) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    from modules.crm.services import pdf_branding as B  # noqa: N812

    st = B.styles()
    p = st["corpo"]
    empresa = B.empresa_branding("conecta_patrimonial")
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=40 * mm, bottomMargin=16 * mm, leftMargin=16 * mm, rightMargin=16 * mm)
    W = A4[0] - 32 * mm
    linhas = [
        ["Beneficiário", f"{pat[1] if pat else '—'} — CNPJ {pat[0] if pat else '—'}"],
        ["Pagador", f"{cli['name']} — CNPJ {cli['document_number'] or '—'}"],
        ["Vencimento", venc.strftime("%d/%m/%Y")],
        ["Valor do documento", B.brl(valor)],
        ["Instruções", discr],
        ["Linha digitável", "00000.00000 00000.000000 00000.000000 0 00000000000000 (SIMULADA)"],
    ]
    tb = Table(linhas, colWidths=[W * 0.25, W * 0.75])
    tb.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 9),
                            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#E8EEF5")),
                            ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story = [Paragraph("<b>BOLETO SIMULADO — AMBIENTE DE HOMOLOGAÇÃO</b>", p),
             Paragraph("Este documento NÃO é uma cobrança. Foi gerado pelo Conecta PRO para validar o kit documental de um "
                       "cliente de teste; não possui código de barras válido nem registro bancário.", p),
             Spacer(1, 6 * mm), tb]
    hf = lambda cv, dc: B.header_footer(cv, dc, titulo="BOLETO (SIMULAÇÃO)", empresa=empresa)  # noqa: E731
    doc.build(story, onFirstPage=hf, onLaterPages=hf)
    return buf.getvalue()
