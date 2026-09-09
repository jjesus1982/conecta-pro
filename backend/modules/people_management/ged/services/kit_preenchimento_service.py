"""Preenche as vagas do kit do banco com o que o SISTEMA já tem (09/09/2026, kit de teste Conecta Village).

Antes: cada collect_* do KitBuilderService criava a VAGA (KitDocument com file_path NULL) e esperava alguém
(Onvio, Pyetra) trazer o arquivo — o kit do banco era uma lista de vazios. Agora, na montagem, cada vaga tenta se
preencher sozinha, e quando não consegue diz POR QUÊ (relatório `faltas`): esse "por quê" é o que vira cobrança
para o responsável, não um silêncio.

Fontes (nunca fabricadas):
  contracheque   hr_payslips (employee, mês/ano) → gerar_pdf_holerite (mesmo PDF do portal/DP)
  VT/VR          motor da folha (calcular_folha_colaborador) → montar_recibo_vt_vr_pdf (um recibo cobre VT+VR;
                 a vaga VA separada não existe no kit real → apagada)
  CND            ged_certidoes da Conecta Patrimonial vigentes (decisão 07/09: certidões só Patrimonial)
  NFS-e          nfse_emitidas_nacional (tomador = cliente, competência do mês) → DANFSe; cliente de
                 HOMOLOGAÇÃO (todos os alocados is_homologacao) → DANFSe SIMULADA, sem valor fiscal
  boleto         cliente de homologação → PDF "BOLETO SIMULADO"; cliente real → arquivado pelo GEDEON (Inter),
                 esta página/serviço não fala com banco (regra da casa)
Arquivos em /app/uploads/kits/<kit_id>/ (mesmo volume de /app/uploads/ponto); o nome do arquivo carrega o nome do
funcionário — no Drive 12 'Contracheque_08.2026.pdf' viravam UM (dedup por nome), medido em 09/09.
"""
from __future__ import annotations

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
            "SELECT id::text, nome, cpf, pis, matricula, cargo, coalesce(is_homologacao,false), vt_modalidade "
            "FROM employees WHERE id::text = ANY(:ids)"),
            {"ids": emp_ids})).fetchall()
        emp = {r[0]: {"nome": r[1], "cpf": r[2], "pis": r[3], "matricula": r[4], "cargo": r[5], "homolog": r[6],
                      "vt_modalidade": r[7]} for r in rows}
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
                fd = {k: emp.get(e, {}).get(k) for k in ("cpf", "pis", "matricula", "vt_modalidade")}
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

    # ── escala: fora do kit (decisão do Jordan, 09/09/2026) ──

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

    # ── adiantamento 40% (dia 20) + comprovantes PIX (40% e 60%) — por funcionário ──
    await _adiantamento_e_comprovantes(db, kit, docs, emp, homolog, rel)

    # ── benefícios da empresa: VT (Sinetram) e VA (Sólides) — lista da Pyetra, 09/09/2026 ──
    await _beneficios_empresa(db, kit, homolog, {d.document_type for d in docs}, rel)

    # ── NFS-e, boleto e guias (nível do kit) ──
    crm_id = await _crm_client_id(db, client) if client else None
    tem = {d.document_type for d in docs}
    if DocumentType.NFS_SERVICO not in tem or DocumentType.BOLETO not in tem:
        await _nfse_e_boleto(db, kit, client, crm_id, homolog, tem, rel)
    await _guias(db, kit, emp, homolog, tem, rel)
    await db.flush()

    # ── assinaturas: pede (funcionário no portal; espelho/escala também a empresa na central) e sincroniza ──
    try:
        from modules.ged.services.kit_signature_service import sincronizar_assinaturas_kit, solicitar_assinaturas_kit

        rel["assinaturas"] = await solicitar_assinaturas_kit(db, kit_id)
        rel["assinaturas"]["sincronizadas"] = await sincronizar_assinaturas_kit(db, kit_id)
    except Exception as exc:  # noqa: BLE001
        rel["faltas"].append(f"assinaturas: {exc}")

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
        toma_end = ", ".join(x for x in (cli.get("address_street"), cli.get("address_number"), cli.get("address_neighborhood")) if x)
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
            iss = round(float(valor) * 0.0435, 2)  # alíquota efetiva da Patrimonial nas notas reais (nfse_emitidas_nacional)
            row = {"numero": "SIMULADA", "chave_acesso": "", "competencia": f"{ano:04d}-{mes:02d}", "data_emissao": date.today(),
                   "emit_cnpj": pat[0] if pat else "", "emit_nome": pat[1] if pat else "", "emit_im": pat[2] if pat else "",
                   "tomador_cnpj": cli["document_number"], "tomador_nome": cli["name"],
                   "descricao": f"SIMULAÇÃO — SEM VALOR FISCAL. {discr}", "valor_servicos": float(valor), "iss_valor": iss,
                   "inss_retido": 0, "valor_liquido": float(valor)}
        if row:
            try:
                if homolog:
                    # layout que a PREFEITURA entrega (DANFSe padrão nacional), não o nosso timbrado — pedido de 09/09
                    from modules.gedeon.services.kit_simulados_pdf import danfse_prefeitura_pdf

                    def _m(v):
                        return f"{float(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                    chave = f"1302603226{re.sub(r'\D', '', row['emit_cnpj'] or '')}00000000000{ano:04d}{mes:02d}00009999{int(row['valor_servicos'] * 100) % 100000:05d}"
                    pdf = danfse_prefeitura_pdf({
                        "numero": "SIMULADA", "chave": chave[:50], "competencia": f"{mes:02d}/{ano}", "emissao": date.today().strftime("%d/%m/%Y"),
                        "emit_nome": row["emit_nome"], "emit_cnpj": row["emit_cnpj"], "emit_im": row["emit_im"],
                        "toma_nome": row["tomador_nome"], "toma_cnpj": row["tomador_cnpj"], "toma_end": toma_end,
                        "servico": "Serviços de portaria, segurança e serviços gerais", "discr": row["descricao"],
                        "vserv": _m(row["valor_servicos"]), "vbc": _m(row["valor_servicos"]), "aliq": "4,35%", "viss": _m(row["iss_valor"]),
                        "vinss": _m(0), "vliq": _m(row["valor_liquido"]), "regime": "Simples Nacional (Anexo IV)"}, simulada=True)
                else:
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

            from modules.gedeon.services.kit_simulados_pdf import boleto_pix_pdf

            venc = (kit.reference_month.replace(day=28) + timedelta(days=4)).replace(day=10)  # dia 10 do mês seguinte
            pdf = boleto_pix_pdf(beneficiario={"nome": pat[1] if pat else "—", "cnpj": pat[0] if pat else "—"},
                                 pagador={"nome": cli["name"], "documento": cli["document_number"]}, valor=float(valor), vencimento=venc,
                                 descricao=discr, nosso_numero=f"{ano:04d}{mes:02d}{int(str(kit.id).replace('-', '')[:8], 16) % 10**8:08d}", simulado=True)
            db.add(KitDocument(kit_id=kid, employee_id=None, document_type=DocumentType.BOLETO,
                               document_name=f"Boleto SIMULADO {mes:02d}/{ano}", file_path=_gravar(kid, "faturamento", f"Boleto_SIMULADO_{mes:02d}.{ano}.pdf", pdf),
                               file_size_bytes=len(pdf), mime_type="application/pdf", source_module=SourceModule.FISCAL,
                               auto_generated=True, is_signed=False, notes="simulação de homologação — sem valor de cobrança"))
            rel["preenchidos"]["boleto"] = 1


async def _adiantamento_e_comprovantes(db, kit, docs, emp, homolog, rel) -> None:
    """Por funcionário: recibo do adiantamento de 40% (pago dia 20) e comprovantes PIX do 40% e do saldo de 60%
    (até o 5º dia útil do mês seguinte). Homologação: simulados. Cliente real: o comprovante vem do banco pelo GEDEON
    (Inter/Cora) — aqui só fica a vaga com o motivo."""
    from datetime import timedelta

    mes, ano = kit.reference_month.month, kit.reference_month.year
    kid = str(kit.id)
    tem = {(str(d.employee_id), d.document_type) for d in docs}
    dia20 = kit.reference_month.replace(day=20)
    prox = (kit.reference_month.replace(day=28) + timedelta(days=4)).replace(day=1)
    uteis = 0
    d5 = prox
    while True:  # 5º dia útil (sem feriados nacionais fixos além de 7/9)
        if d5.weekday() < 5 and not (d5.month == 9 and d5.day == 7):
            uteis += 1
            if uteis == 5:
                break
        d5 += timedelta(days=1)
    pat = (await db.execute(text("SELECT cnpj, razao_social FROM empresas WHERE slug = 'conecta_patrimonial'"))).first()
    emp_nome, emp_cnpj = (pat[1], pat[0]) if pat else ("CONECTAMAIS PATRIMONIAL LTDA", "66.014.833/0001-10")
    if not homolog:
        # cliente REAL (regra de 09/09): comprovante do 40% (dia 20/21), do 60% (5º dia útil), VT e VR entram assim
        # que o pagamento existe — pelo sistema (inter_payments) ou pelo extrato (bank_transactions); recibo do
        # adiantamento gerado com o valor pago. Quem ficou sem pagamento casado vira falta declarada.
        from modules.people_management.ged.services.kit_eventos import preencher_comprovantes_reais

        r = await preencher_comprovantes_reais(db, kid, kit.reference_month, emp)
        rel["preenchidos"]["comprovante_pagamento"] = r["comprovantes"]
        rel["preenchidos"]["recibo_adiantamento"] = r["recibos_adiantamento"]
        for nome in r["sem_pagamento"]:
            rel["faltas"].append(f"comprovantes {nome}: nenhum pagamento (sistema/extrato) casado por CPF/nome em {mes:02d}/{ano} até dia 12 do mês seguinte")
        return
    for e, info in emp.items():
        salario = float((await db.execute(text("SELECT coalesce(salario_base,0) FROM employees WHERE id = CAST(:e AS uuid)"), {"e": e})).scalar() or 0)
        adiant = round(salario * 0.40, 2)
        liquido = None
        try:
            from core.database.session import get_sync_db
            from modules.people_management.folha.services.calculo_service import calcular_folha_colaborador
            with get_sync_db() as s:
                r = calcular_folha_colaborador(s, e, mes, ano)
            liquido = float(r.get("liquido") or 0) if "error" not in r else None
        except Exception:  # noqa: BLE001
            liquido = None
        saldo = round((liquido if liquido is not None else salario) - adiant, 2)
        nome_s = _safe(info.get("nome") or e)
        if (e, DocumentType.RECIBO_ADIANTAMENTO) not in tem:
            from modules.crm.services.doc_pdf import build_recibo_pagamento_pdf

            pdf = build_recibo_pagamento_pdf({"valor": adiant, "recebedor": info.get("nome"), "documento": info.get("cpf"),
                                              "referente": f"adiantamento salarial de 40% da competência {mes:02d}/{ano} (SIMULADO — homologação)",
                                              "forma_pagamento": "PIX", "data": dia20, "numero": f"AD-{ano}{mes:02d}-{info.get('matricula') or ''}",
                                              "empresa": _empresa_branding("conecta_patrimonial")})
            db.add(KitDocument(kit_id=kid, employee_id=e, document_type=DocumentType.RECIBO_ADIANTAMENTO,
                               document_name=f"Recibo de Adiantamento Salarial 40% {mes:02d}/{ano}", file_path=_gravar(kid, e, f"Recibo_Adiantamento_Salarial_40pct_{mes:02d}.{ano}_{nome_s}.pdf", pdf),
                               file_size_bytes=len(pdf), mime_type="application/pdf", source_module=SourceModule.DP, auto_generated=True, is_signed=False,
                               notes="simulação de homologação"))
            rel["preenchidos"]["recibo_adiantamento"] = rel["preenchidos"].get("recibo_adiantamento", 0) + 1
        if (e, DocumentType.COMPROVANTE_PAGAMENTO) not in tem:
            from modules.gedeon.services.comprovante_generator import gerar_comprovante_pdf

            for rot, val, dt, seq in (("Adiantamento 40%", adiant, dia20, "40"), ("Saldo 60% (folha)", saldo, d5, "60")):
                pdf = gerar_comprovante_pdf(favorecido=info.get("nome"), cpf=info.get("cpf"), valor=val, data_pagamento=dt,
                                            descricao=f"{rot} — competência {mes:02d}/{ano} — SIMULADO (homologação)",
                                            id_transacao=f"SIM{ano}{mes:02d}{seq}{(info.get('matricula') or '')[-2:]}", competencia=f"{mes:02d}/{ano}",
                                            condominio="Conecta Village (TESTE)", tipo="PIX", empresa_nome=emp_nome, empresa_cnpj=emp_cnpj,
                                            banco_origem="Banco Cora SCD (403)")
                db.add(KitDocument(kit_id=kid, employee_id=e, document_type=DocumentType.COMPROVANTE_PAGAMENTO,
                                   document_name=f"Comprovante PIX {rot} {mes:02d}/{ano}",
                                   file_path=_gravar(kid, e, f"Comprovante_PIX_{seq}pct_{mes:02d}.{ano}_{nome_s}.pdf", pdf), file_size_bytes=len(pdf),
                                   mime_type="application/pdf", source_module=SourceModule.FISCAL, auto_generated=True, is_signed=True,
                                   notes="simulação de homologação — comprovante bancário não é assinado pelo funcionário"))
                rel["preenchidos"]["comprovante_pagamento"] = rel["preenchidos"].get("comprovante_pagamento", 0) + 1


def _empresa_branding(slug: str) -> dict:
    from modules.crm.services import pdf_branding as B  # noqa: N812

    return B.empresa_branding(slug)


async def _beneficios_empresa(db, kit, homolog, tem, rel) -> None:
    """Os 5 documentos que a Pyetra lista no bloco de benefícios: boleto e relatório do SINETRAM (VT), relatório do
    Sólides (VA) e o comprovante de pagamento de cada um. Em cliente REAL eles vêm do portal do Sinetram, do Sólides
    e do banco (GEDEON arquiva) — aqui fica a vaga com o motivo. Em homologação, versões simuladas."""
    mes, ano = kit.reference_month.month, kit.reference_month.year
    kid = str(kit.id)
    comp = f"{mes:02d}/{ano}"
    alvos = (
        (DocumentType.BOLETO_VT_SINETRAM, f"Boleto Vale-Transporte SINETRAM {comp}", "portal do SINETRAM (compra dos créditos)"),
        (DocumentType.COMPROVANTE_PAGTO_SINETRAM, f"Comprovante de pagamento SINETRAM {comp}", "banco (pagamento do boleto do SINETRAM)"),
        (DocumentType.RELATORIO_VT_SINETRAM, f"Relatório de pedido de VT SINETRAM {comp}", "portal do SINETRAM (pedido por colaborador, nº do cartão)"),
        (DocumentType.RELATORIO_VA_SOLIDES, f"Relatório de pedido de VA Sólides {comp}", "Sólides (pedido por colaborador, alimentação e mobilidade)"),
        (DocumentType.COMPROVANTE_PAGTO_SOLIDES, f"Comprovante de pagamento Sólides {comp}", "banco (pagamento do pedido do Sólides)"),
    )
    faltando = [(t, n, o) for t, n, o in alvos if t not in tem]
    if not faltando:
        return
    if not homolog:
        for t, n, origem in faltando:
            db.add(KitDocument(kit_id=kid, employee_id=None, document_type=t, document_name=n, file_path=None,
                               mime_type="application/pdf", source_module=SourceModule.FISCAL, auto_generated=True, is_signed=True))
            rel["faltas"].append(f"{n}: origem {origem}")
        return
    # homologação: simulados, com os mesmos números do recibo de VT/VR dos colaboradores do kit
    from datetime import timedelta

    from modules.gedeon.services.comprovante_generator import gerar_comprovante_pdf
    from modules.gedeon.services.kit_simulados_pdf import boleto_pix_pdf

    pat = (await db.execute(text("SELECT cnpj, razao_social FROM empresas WHERE slug = 'conecta_patrimonial'"))).first()
    empresa = {"nome": pat[1] if pat else "CONECTAMAIS PATRIMONIAL LTDA", "cnpj": pat[0] if pat else "66.014.833/0001-10"}
    tot_vt = float((await db.execute(text(
        "SELECT coalesce(sum(round(coalesce(e.salario_base,0) * 0.06, 2)), 0) FROM ged_kit_documents k "
        "JOIN employees e ON e.id = k.employee_id WHERE k.kit_id = :k AND k.document_type = 'comprovante_vt'"), {"k": kid})).scalar() or 0)
    tot_va = float((await db.execute(text(
        "SELECT coalesce(count(*) * 330.0, 0) FROM ged_kit_documents WHERE kit_id = :k AND document_type = 'comprovante_vr'"), {"k": kid})).scalar() or 0)
    venc = (kit.reference_month.replace(day=15))
    pago = venc + timedelta(days=1)
    for t, n, _origem in faltando:
        if t == DocumentType.BOLETO_VT_SINETRAM:
            pdf = boleto_pix_pdf(beneficiario={"nome": "SINETRAM — Sind. das Empresas de Transporte de Passageiros do AM", "cnpj": "04.603.197/0001-04"},
                                 pagador={"nome": empresa["nome"], "documento": empresa["cnpj"]}, valor=max(tot_vt, 1.0), vencimento=venc,
                                 descricao=f"Créditos de vale-transporte — competência {comp}", nosso_numero=f"{ano}{mes:02d}0001", banco_nome="Banco Bradesco",
                                 banco_codigo="237", simulado=True)
        elif t in (DocumentType.COMPROVANTE_PAGTO_SINETRAM, DocumentType.COMPROVANTE_PAGTO_SOLIDES):
            sinetram = t == DocumentType.COMPROVANTE_PAGTO_SINETRAM
            pdf = gerar_comprovante_pdf(
                favorecido="SINETRAM — Sind. Emp. Transporte de Passageiros do AM" if sinetram else "Sólides Tecnologia S.A. (benefícios)",
                cpf="04.603.197/0001-04" if sinetram else "10.461.302/0001-10",
                valor=max(tot_vt if sinetram else tot_va, 1.0), data_pagamento=pago,
                descricao=("Pagamento do boleto de vale-transporte (SINETRAM)" if sinetram else "Pagamento do pedido de vale-alimentação (Sólides)")
                          + f" — competência {comp} — SIMULADO (homologação)",
                id_transacao=f"SIM{ano}{mes:02d}{'VT' if sinetram else 'VA'}", competencia=comp, tipo="Boleto" if sinetram else "PIX",
                empresa_nome=empresa["nome"], empresa_cnpj=empresa["cnpj"], banco_origem="Banco Cora SCD (403)")
        else:
            pdf = await _relatorio_pedido_pdf(db, kid, empresa, comp, sinetram=(t == DocumentType.RELATORIO_VT_SINETRAM))
        db.add(KitDocument(kit_id=kid, employee_id=None, document_type=t, document_name=n + " (SIMULADO)",
                           file_path=_gravar(kid, "beneficios", f"{_safe(n)}.pdf", pdf), file_size_bytes=len(pdf),
                           mime_type="application/pdf", source_module=SourceModule.FISCAL, auto_generated=True, is_signed=True,
                           notes="simulação de homologação — documento do bloco de benefícios"))
        rel["preenchidos"]["beneficios_empresa"] = rel["preenchidos"].get("beneficios_empresa", 0) + 1


async def _relatorio_pedido_pdf(db, kid: str, empresa: dict, comp: str, sinetram: bool) -> bytes:
    """Relatório de pedido por colaborador (VT do SINETRAM / VA do Sólides), no formato dos reais."""
    import io as _io

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    from modules.crm.services import pdf_branding as B  # noqa: N812

    rows = (await db.execute(text(
        "SELECT e.nome, e.cpf, coalesce(e.salario_base,0) FROM ged_kit_documents k JOIN employees e ON e.id = k.employee_id "
        "WHERE k.kit_id = :k AND k.document_type = 'comprovante_vt' ORDER BY e.nome"), {"k": kid})).fetchall()
    st = B.styles()
    buf = _io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=40 * mm, bottomMargin=16 * mm, leftMargin=16 * mm, rightMargin=16 * mm)
    titulo = "RELATÓRIO DE PEDIDO — VALE-TRANSPORTE (SINETRAM)" if sinetram else "RELATÓRIO DE PEDIDO — VALE-ALIMENTAÇÃO (SÓLIDES)"
    cab = ["#", "Colaborador", "CPF", "Nº cartão", "Valor"] if sinetram else ["#", "Colaborador", "CPF", "Alimentação", "Mobilidade"]
    linhas = [cab]
    total = 0.0
    for i, (nome, cpf, sal) in enumerate(rows, start=1):
        vt = round(float(sal) * 0.06, 2)
        va = 330.00
        total += vt if sinetram else va
        linhas.append([str(i), (nome or "")[:34], cpf or "—", f"58.04.{i:08d}-1" if sinetram else B.brl(va), B.brl(vt) if sinetram else B.brl(vt)])
    linhas.append(["", "TOTAL", "", "", B.brl(total)])
    tb = Table(linhas, colWidths=[10 * mm, 62 * mm, 30 * mm, 36 * mm, 30 * mm], repeatRows=1)
    tb.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8),
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF5")), ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F7F9FB")])]))
    story = [Paragraph(f"<b>{titulo}</b>", st["corpo"]),
             Paragraph(f"Empresa: {empresa['nome']} — CNPJ {empresa['cnpj']} · Competência {comp} · {len(rows)} colaborador(es)", st["corpo"]),
             Paragraph("<font color='#B00020'><b>SIMULADO — homologação.</b> Em produção este relatório é o arquivo baixado do portal.</font>", st["corpo"]),
             Spacer(1, 5 * mm), tb]
    empresa_b = B.empresa_branding("conecta_patrimonial")
    hf = lambda cv, dc: B.header_footer(cv, dc, titulo="RELATÓRIO DE BENEFÍCIOS", empresa=empresa_b)  # noqa: E731
    doc.build(story, onFirstPage=hf, onLaterPages=hf)
    return buf.getvalue()


async def _guias(db, kit, emp, homolog, tem, rel) -> None:
    """Guias da competência: FGTS Digital, DARF DCTFWeb (INSS/CPP) e DAS (Patrimonial é Simples Nacional).
    Vencem dia 20 do mês seguinte; o kit real recebe as guias pelo GEDEON (Onvio) quando o contador emite."""
    from datetime import timedelta

    mes, ano = kit.reference_month.month, kit.reference_month.year
    kid = str(kit.id)
    venc = (kit.reference_month.replace(day=28) + timedelta(days=4)).replace(day=20)
    comp = f"{mes:02d}/{ano}"
    alvos = ((DocumentType.GRF_FGTS, f"Guia FGTS Digital {comp}"), (DocumentType.GPS_INSS, f"DARF DCTFWeb (INSS/CPP) {comp}"),
             (DocumentType.DAS_SIMPLES_NACIONAL, f"DAS Simples Nacional {comp}"))
    faltando = [(t, n) for t, n in alvos if t not in tem]
    if not faltando:
        return
    if not homolog:
        for t, n in faltando:
            db.add(KitDocument(kit_id=kid, employee_id=None, document_type=t, document_name=n, file_path=None, mime_type="application/pdf",
                               source_module=SourceModule.FISCAL, auto_generated=True, is_signed=True))
            rel["faltas"].append(f"{n}: vence {venc:%d/%m/%Y} — emitida pelo contador no Onvio, o GEDEON arquiva (bloco guias)")
            db.add(KitDocument(kit_id=kid, employee_id=None, document_type=t, document_name=f"Comprovante pagamento {n}", file_path=None,
                               mime_type="application/pdf", source_module=SourceModule.FISCAL, auto_generated=True, is_signed=True))
            rel["faltas"].append(f"Comprovante pagamento {n}: entra quando a guia for paga (inter_payments darf/gps/boleto ou extrato)")
        return
    from modules.gedeon.services.kit_simulados_pdf import guia_simulada_pdf

    pat = (await db.execute(text("SELECT cnpj, razao_social FROM empresas WHERE slug = 'conecta_patrimonial'"))).first()
    empresa = {"nome": pat[1] if pat else "CONECTAMAIS PATRIMONIAL LTDA", "cnpj": pat[0] if pat else "66.014.833/0001-10"}
    bruto = float((await db.execute(text(
        "SELECT coalesce(sum(coalesce(total_earnings, base_salary)),0) FROM hr_payslips WHERE reference_month=:m AND reference_year=:a "
        "AND employee_id::text = ANY(:ids)"), {"m": mes, "a": ano, "ids": list(emp)})).scalar() or 0)
    fat = float((await db.execute(text("SELECT coalesce(sum(monthly_value),0) FROM contracts c JOIN clients cl ON cl.id=c.client_id "
                                       "WHERE c.status='active' AND cl.trading_name ILIKE '%VILLAGE%'"))).scalar() or 0)
    dados = {
        DocumentType.GRF_FGTS: ("FGTS", round(bruto * 0.08, 2), [("Competência", comp), ("Trabalhadores", str(len(emp))), ("Base de cálculo (remuneração)", _brl_(bruto)),
                                                                 ("Alíquota", "8%")], "1" + "8" * 10 + "0"),
        DocumentType.GPS_INSS: ("DARF", round(bruto * 0.20 + bruto * 0.02, 2), [("Código da receita", "1141-02 — CP patronal (DCTFWeb)"), ("Período de apuração", comp),
                                                                             ("CPP 20% + RAT 2% sobre", _brl_(bruto))], "8" + "5" * 10 + "0"),
        DocumentType.DAS_SIMPLES_NACIONAL: ("DAS", round(fat * 0.0435 + fat * 0.0275, 2), [("Período de apuração", comp), ("Receita bruta do mês", _brl_(fat)),
                                                                                         ("Anexo IV (ISS 4,35% + IRPJ/CSLL/PIS/COFINS)", "6,10% efetivo")], "8" + "5" * 10 + "0"),
    }
    from modules.gedeon.services.comprovante_generator import gerar_comprovante_pdf

    for t, n in faltando:
        tipo, valor, linhas, base = dados[t]
        pdf = guia_simulada_pdf(tipo=tipo, empresa=empresa, competencia=comp, vencimento=venc, valor=valor, linhas=linhas, codigo_barras_base=base)
        db.add(KitDocument(kit_id=kid, employee_id=None, document_type=t, document_name=n + " (SIMULADA)",
                           file_path=_gravar(kid, "guias", f"{tipo}_{mes:02d}.{ano}_SIMULADA.pdf", pdf), file_size_bytes=len(pdf),
                           mime_type="application/pdf", source_module=SourceModule.FISCAL, auto_generated=True, is_signed=True,
                           notes="simulação de homologação — valores calculados sobre a folha de teste"))
        rel["preenchidos"]["guias"] = rel["preenchidos"].get("guias", 0) + 1
        # 09/09 (Jordan): a pasta Guias leva também o COMPROVANTE de pagamento de cada guia
        cp = gerar_comprovante_pdf(favorecido={"FGTS": "FGTS Digital — Caixa Econômica Federal", "DARF": "Receita Federal do Brasil (DARF)",
                                               "DAS": "Simples Nacional (DAS)"}[tipo], cpf=None, valor=valor, data_pagamento=venc,
                                   descricao=f"Pagamento da guia {tipo} {comp} — SIMULADO (homologação)", id_transacao=f"SIM{ano}{mes:02d}{tipo}",
                                   competencia=comp, tipo={"FGTS": "Boleto", "DARF": "DARF", "DAS": "DAS"}.get(tipo, "Boleto"),
                                   empresa_nome=empresa["nome"], empresa_cnpj=empresa["cnpj"], banco_origem="Banco Cora SCD (403)")
        db.add(KitDocument(kit_id=kid, employee_id=None, document_type=t, document_name=f"Comprovante pagamento {n} (SIMULADO)",
                           file_path=_gravar(kid, "guias", f"Comprovante_{tipo}_{mes:02d}.{ano}_SIMULADO.pdf", cp), file_size_bytes=len(cp),
                           mime_type="application/pdf", source_module=SourceModule.FISCAL, auto_generated=True, is_signed=True,
                           notes="simulação de homologação — comprovante de pagamento da guia"))


def _brl_(v: float) -> str:
    from modules.crm.services import pdf_branding as B  # noqa: N812

    return B.brl(v)
