"""Eventos que EMPURRAM documentos para o kit (09/09/2026) — o kit é montado à medida que cada processo termina.

Regra do dono (09/09): "fiz o pagamento de 40% naquela data, o comprovante já vai pra pasta do kit; o mesmo vale
pros 60%, pro VT e VR; depois recebemos os documentos assinados, já vai pra pasta". E: "quando formos montar o kit
de setembro, já vai puxar os comprovantes e os recibos dos 40% que pagamos dia 20 ou 21 de agosto — já é uma regra".

Fontes de pagamento, nesta ordem:
  1. inter_payments (pago PELO sistema — folha PIX em lote, pagamento avulso): evento na hora (executar_lote/executar).
  2. bank_transactions (extrato sincronizado do Inter/Cora — pago fora do sistema): casado por CPF/nome do favorecido
     na janela da competência; entra na montagem diária (ged.kit_incremental_diario).
Classificação por data: dia 14–26 do mês M = adiantamento 40%; até dia 12 de M+1 = saldo 60%; descrição com VT/VR
= comprovante de VT/VR. O recibo do adiantamento é gerado pelo sistema com o valor REALMENTE pago (co-assinado).
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
KITS_STORAGE = Path("/app/uploads/kits")


def _norm(s: str | None) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper().strip()


def _dig(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


def _safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", _norm(s))[:40]


def classificar_pagamento(data_pg: date, ref: date, texto: str) -> tuple[str, str]:
    """→ (document_type, rótulo). ref = 1º dia da competência."""
    t = _norm(texto)
    if re.search(r"\bVT\b|VALE.?TRANSP", t):
        return "comprovante_vt", "VT"
    if re.search(r"\bVR\b|\bVA\b|VALE.?(REFEI|ALIMENT)", t):
        return "comprovante_vr", "VR"
    prox = (ref.replace(day=28) + timedelta(days=4)).replace(day=1)
    if data_pg >= prox:
        return "comprovante_pagamento", "Saldo 60% (folha)"
    if data_pg.month == ref.month and 14 <= data_pg.day <= 26:
        return "comprovante_pagamento", "Adiantamento 40%"
    return "comprovante_pagamento", "Folha"


def competencia_do_pagamento(data_pg: date, texto: str) -> date:
    """Pagamento até o dia 12 pertence ao mês ANTERIOR (saldo/VT do mês trabalhado); senão, ao próprio mês."""
    m = re.search(r"(\d{4})-(\d{2})", texto or "") or re.search(r"(\d{2})/(\d{4})", texto or "")
    if m:
        a, b = m.group(1), m.group(2)
        return date(int(a), int(b), 1) if len(a) == 4 else date(int(b), int(a), 1)
    if data_pg.day <= 12:
        return (data_pg.replace(day=1) - timedelta(days=1)).replace(day=1)
    return data_pg.replace(day=1)


async def pagamentos_do_funcionario(db: AsyncSession, cpf: str, nome: str, ref: date) -> list[dict]:
    """Pagamentos reais ao funcionário na janela [ref, ref+1 mês dia 12] — sistema (inter_payments) e extrato."""
    cpf_d = _dig(cpf)
    fim = (ref.replace(day=28) + timedelta(days=4)).replace(day=12)
    out: list[dict] = []
    rows = (
        await db.execute(
            text(
                "SELECT id::text, data_pagamento, valor, coalesce(observacoes,''), destinatario, coalesce(banco,'inter'), inter_payment_id "
                "FROM inter_payments WHERE status IN ('executado','confirmado') AND data_pagamento BETWEEN :ini AND :fim "
                "AND (regexp_replace(coalesce(destinatario->>'cpf_cnpj',''),'[^0-9]','','g') = :cpf "
                "     OR regexp_replace(coalesce(destinatario->>'chave',''),'[^0-9]','','g') = :cpf)"
            ),
            {"ini": ref, "fim": fim, "cpf": cpf_d},
        )
    ).fetchall()
    for r in rows:
        dest = r[4] if isinstance(r[4], dict) else {}
        out.append(
            {
                "origem": "sistema",
                "pagamento_id": r[0],
                "data": r[1],
                "valor": float(r[2]),
                "texto": f"{r[3]} {dest.get('descricao', '')} {dest.get('competencia', '')}",
                "banco": r[5],
                "ref_banco": r[6],
            }
        )
    if cpf_d or nome:
        rows = (
            await db.execute(
                text(
                    "SELECT id::text, transaction_date, amount, coalesce(description,''), coalesce(counterparty_name, contraparte_nome, ''), "
                    "coalesce(pix_end_to_end, external_id, ''), coalesce(memo,'') FROM bank_transactions "
                    "WHERE transaction_date BETWEEN :ini AND :fim AND amount < 0 AND coalesce(ativo,true) "
                    "AND (regexp_replace(coalesce(counterparty_document, contraparte_documento, ''),'[^0-9]','','g') = :cpf "
                    "     OR (:nome <> '' AND upper(coalesce(counterparty_name, contraparte_nome, '')) LIKE :nome))"
                ),
                {"ini": ref, "fim": fim, "cpf": cpf_d or "-", "nome": (_norm(nome) + "%") if nome else ""},
            )
        ).fetchall()
        for r in rows:
            out.append(
                {
                    "origem": "extrato",
                    "transacao_id": r[0],
                    "data": r[1],
                    "valor": abs(float(r[2])),
                    "texto": f"{r[3]} {r[6]}",
                    "favorecido": r[4],
                    "ref_banco": r[5],
                }
            )
    return out


async def ged_client_do_funcionario(db: AsyncSession, employee_id: str) -> str | None:
    """funcionário → alocação → posto → cliente CRM → cliente GED (CNPJ, nome ou nome fantasia)."""
    row = (
        await db.execute(
            text(
                "SELECT c.name, c.trading_name, c.document_number FROM allocations a JOIN posts p ON p.id = a.post_id "
                "JOIN clients c ON c.id = p.client_id WHERE a.employee_id = CAST(:e AS uuid) ORDER BY a.created_at DESC LIMIT 1"
            ),
            {"e": employee_id},
        )
    ).first()
    if not row:
        return None
    ged = (
        await db.execute(text("SELECT id::text, name, cnpj FROM ged_clients WHERE coalesce(is_active,true)"))
    ).fetchall()
    cnpj = _dig(row[2])
    for gid, _gname, gcnpj in ged:
        if cnpj and _dig(gcnpj) == cnpj:
            return gid
    for gid, gname, _ in ged:
        if _norm(gname) in (_norm(row[0]), _norm(row[1])):
            return gid
    return None


#: "Comprovante PIX Folha 08/2026" → "Comprovante de Pagamento de Salário". O rótulo interno diz o
#: MEIO (PIX) e o momento (folha/adiantamento); o cliente quer saber o QUE é.
_ROTULO_PARA_CLIENTE = (
    ("comprovante pix folha", "Comprovante de Pagamento de Salário"),
    ("comprovante pix saldo 60", "Comprovante de Pagamento de Salário (saldo 60%)"),
    ("comprovante pix adiantamento", "Comprovante de Pagamento de Adiantamento 40%"),
    ("comprovante pix", "Comprovante de Pagamento"),
)


def _nome_de_arquivo(nome_doc: str) -> str:
    """Nome legível para a pasta do condomínio, sem repetir a competência nem gritar em caixa alta."""
    n = re.sub(r"\s*\d{2}/\d{4}\s*$", "", (nome_doc or "").strip())
    baixo = n.lower()
    for chave, bonito in _ROTULO_PARA_CLIENTE:
        if baixo.startswith(chave):
            return bonito
    return n or "Documento"


async def registrar_comprovante(
    db: AsyncSession,
    *,
    kit_id: str,
    employee_id: str,
    document_type: str,
    nome_doc: str,
    pdf: bytes,
    ref: date,
    rotulo: str,
    nome_func: str,
    notes: str | None = None,
    is_signed: bool = True,
) -> str:
    """Cria/preenche a vaga do comprovante no kit e devolve o id do documento. Idempotente por (kit, funcionário, tipo, rótulo)."""
    from modules.people_management.ged.models.kit_document import KitDocument, SourceModule

    d = KITS_STORAGE / kit_id / employee_id
    d.mkdir(parents=True, exist_ok=True)
    # 10/09: o nome é o que o SÍNDICO lê. Antes saía
    # "COMPROVANTE_PIX_FOLHA_08_2026_08.2026_ANTONIO_CARLOS_VIEIRA.pdf" — competência duas vezes,
    # tudo em caixa alta, e nem o checklist do kit reconhecia ("comprovante de pagamento de sal").
    # O kit real do Villa Dei Fiori chama isso de "Comprovante de Pagamento de Salário_Fulano.pdf".
    fp = d / f"{_nome_de_arquivo(nome_doc)} — {nome_func.title()}.pdf"
    fp.write_bytes(pdf)
    row = (
        await db.execute(
            text(
                "SELECT id::text FROM ged_kit_documents WHERE kit_id = :k AND employee_id = CAST(:e AS uuid) AND document_type = :t "
                "AND (document_name ILIKE :r OR file_path IS NULL) ORDER BY file_path NULLS FIRST LIMIT 1"
            ),
            {"k": kit_id, "e": employee_id, "t": document_type, "r": f"%{rotulo}%"},
        )
    ).scalar()
    if row:
        await db.execute(
            text(
                "UPDATE ged_kit_documents SET file_path = :fp, file_size_bytes = :n, document_name = :dn, mime_type = 'application/pdf', "
                "notes = coalesce(:notes, notes), is_signed = :s, updated_at = now() WHERE id = :i"
            ),
            {"fp": str(fp), "n": len(pdf), "dn": nome_doc, "notes": notes, "s": is_signed, "i": row},
        )
        return row
    doc = KitDocument(
        kit_id=kit_id,
        employee_id=employee_id,
        document_type=document_type,
        document_name=nome_doc,
        file_path=str(fp),
        file_size_bytes=len(pdf),
        mime_type="application/pdf",
        source_module=SourceModule.FISCAL,
        auto_generated=True,
        is_signed=is_signed,
        notes=notes,
    )
    db.add(doc)
    await db.flush()
    return str(doc.id)


async def empurrar_para_drive(db: AsyncSession, kit_id: str, doc_id: str) -> dict:
    try:
        from modules.people_management.ged.services.google_drive_service import GoogleDriveService

        return await GoogleDriveService(db).sync_documento(kit_id, doc_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Drive ← documento %s do kit %s: %s", doc_id, kit_id, exc)
        return {"enviado": False, "motivo": str(exc)[:120]}


async def evento_pagamento_executado(db: AsyncSession, pagamento_id: str) -> dict:
    """Chamado logo depois de um pagamento sair pelo sistema (folha em lote ou avulso). Best-effort: nunca quebra o
    pagamento. Acha o funcionário pelo CPF do destinatário, a competência e o kit, gera o comprovante e empurra."""
    rel: dict = {"pagamento_id": pagamento_id, "kit": None, "documento": None}
    try:
        row = (
            await db.execute(
                text(
                    "SELECT data_pagamento, valor, coalesce(observacoes,''), destinatario, status FROM inter_payments WHERE id = :i"
                ),
                {"i": pagamento_id},
            )
        ).first()
        if not row or row[4] not in ("executado", "confirmado"):
            return {**rel, "motivo": "pagamento não efetivado"}
        dest = row[3] if isinstance(row[3], dict) else {}
        cpf = _dig(dest.get("cpf_cnpj") or dest.get("chave") or "")
        if len(cpf) != 11:
            return {**rel, "motivo": "destinatário não é CPF (não é funcionário)"}
        emp = (
            await db.execute(
                text(
                    "SELECT id::text, nome FROM employees WHERE regexp_replace(coalesce(cpf,''),'[^0-9]','','g') = :c LIMIT 1"
                ),
                {"c": cpf},
            )
        ).first()
        if not emp:
            return {**rel, "motivo": f"CPF {cpf[:3]}… não é de funcionário"}
        texto = f"{row[2]} {dest.get('descricao', '')} {dest.get('competencia', '')}"
        ref = competencia_do_pagamento(row[0], texto)
        tipo, rotulo = classificar_pagamento(row[0], ref, texto)
        ged_id = await ged_client_do_funcionario(db, emp[0])
        if not ged_id:
            return {**rel, "motivo": "funcionário sem cliente GED (alocação/posto)"}
        kit_id = (
            await db.execute(
                text("SELECT id::text FROM ged_document_kits WHERE client_id = :c AND reference_month = :m"),
                {"c": ged_id, "m": ref},
            )
        ).scalar()
        if not kit_id:
            from modules.people_management.ged.services.kit_builder_service import KitBuilderService

            res = await KitBuilderService(db).build_kit_for_client(ged_id, ref)
            kit_id = res["kit_id"]
        from modules.integrations.inter.payment_controller import comprovante_pdf_de_pagamento

        pdf = await comprovante_pdf_de_pagamento(db, pagamento_id)
        if not pdf:
            return {**rel, "kit": kit_id, "motivo": "comprovante não emitido (pagamento sem confirmação do banco)"}
        nome_doc = f"Comprovante PIX {rotulo} {ref:%m/%Y}"
        doc_id = await registrar_comprovante(
            db,
            kit_id=kit_id,
            employee_id=emp[0],
            document_type=tipo,
            nome_doc=nome_doc,
            pdf=pdf,
            ref=ref,
            rotulo=rotulo,
            nome_func=emp[1],
            notes=f"pagamento {pagamento_id} pelo sistema em {row[0]:%d/%m/%Y}",
        )
        await db.commit()
        rel.update(
            {
                "kit": kit_id,
                "documento": doc_id,
                "tipo": tipo,
                "rotulo": rotulo,
                "drive": await empurrar_para_drive(db, kit_id, doc_id),
            }
        )
        await db.commit()
        logger.info("kit ← comprovante de pagamento: %s", rel)
    except Exception as exc:  # noqa: BLE001
        logger.warning("evento_pagamento_executado %s: %s", pagamento_id, exc)
        rel["erro"] = str(exc)[:160]
    return rel


async def preencher_comprovantes_reais(db: AsyncSession, kit_id: str, ref: date, emp: dict[str, dict]) -> dict:
    """Montagem (diária/manual) de cliente REAL: para cada funcionário, casa os pagamentos (sistema + extrato) da
    janela e preenche comprovante do 40%, do 60%, do VT e do VR; gera o recibo do adiantamento com o valor pago."""
    from modules.gedeon.services.comprovante_generator import gerar_comprovante_pdf

    rel = {"comprovantes": 0, "recibos_adiantamento": 0, "sem_pagamento": []}
    pat = (await db.execute(text("SELECT cnpj, razao_social FROM empresas WHERE slug = 'conecta_patrimonial'"))).first()
    for e, info in emp.items():
        pags = await pagamentos_do_funcionario(db, info.get("cpf") or "", info.get("nome") or "", ref)
        if not pags:
            rel["sem_pagamento"].append(info.get("nome") or e)
            continue
        for p in pags:
            tipo, rotulo = classificar_pagamento(p["data"], ref, p["texto"])
            # 09/09/2026 (Jordan): "o comprovante de pagamento deve ser puxado via API do extrato do banco, não o
            # gerado pelo sistema". A linha do EXTRATO (bank_transactions, sincronizada do Inter/Cora) tem o
            # favorecido, o CPF e o endToEndId como o BANCO registrou — é ela que manda quando existe.
            if p["origem"] == "sistema" and not any(
                q["origem"] == "extrato" and q["data"] == p["data"] and abs(q["valor"] - p["valor"]) < 0.01
                for q in pags
            ):
                from modules.integrations.inter.payment_controller import comprovante_pdf_de_pagamento

                pdf = await comprovante_pdf_de_pagamento(db, p["pagamento_id"])
            elif p["origem"] == "sistema":
                continue  # a mesma transação vem do extrato logo abaixo, com o dado do banco
            else:
                pdf = gerar_comprovante_pdf(
                    favorecido=p.get("favorecido") or info.get("nome"),
                    cpf=info.get("cpf"),
                    valor=p["valor"],
                    data_pagamento=p["data"],
                    descricao=f"{rotulo} — extrato bancário {p.get('ref_banco') or ''}".strip(),
                    id_transacao=p.get("ref_banco"),
                    competencia=f"{ref:%m/%Y}",
                    tipo="PIX",
                    empresa_nome=pat[1] if pat else None,
                    empresa_cnpj=pat[0] if pat else None,
                )
            if not pdf:
                continue
            await registrar_comprovante(
                db,
                kit_id=kit_id,
                employee_id=e,
                document_type=tipo,
                nome_doc=f"Comprovante PIX {rotulo} {ref:%m/%Y}",
                pdf=pdf,
                ref=ref,
                rotulo=rotulo,
                nome_func=info.get("nome") or e,
                notes=f"{p['origem']}: {p.get('ref_banco') or ''}",
            )
            rel["comprovantes"] += 1
            if rotulo == "Adiantamento 40%":
                from modules.crm.services import pdf_branding as B  # noqa: N812
                from modules.crm.services.doc_pdf import build_recibo_pagamento_pdf

                rec = build_recibo_pagamento_pdf(
                    {
                        "valor": p["valor"],
                        "recebedor": info.get("nome"),
                        "documento": info.get("cpf"),
                        "referente": f"adiantamento salarial de 40% da competência {ref:%m/%Y}",
                        "forma_pagamento": "PIX",
                        "data": p["data"],
                        "numero": f"AD-{ref:%Y%m}-{info.get('matricula') or ''}",
                        "empresa": B.empresa_branding("conecta_patrimonial"),
                    }
                )
                await registrar_comprovante(
                    db,
                    kit_id=kit_id,
                    employee_id=e,
                    document_type="recibo_adiantamento",
                    nome_doc=f"Recibo de Adiantamento Salarial 40% {ref:%m/%Y}",
                    pdf=rec,
                    ref=ref,
                    rotulo="adiantamento",
                    nome_func=info.get("nome") or e,
                    is_signed=False,
                )
                rel["recibos_adiantamento"] += 1
    return rel
