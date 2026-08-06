# -*- coding: utf-8 -*-
"""Gera os documentos do MÊS (holerite, espelho de ponto, recibo de VT/VR) dos
funcionários CLT ativos da Patrimonial e cria cada um no fluxo de co-assinatura
(funcionário + empresa). É a versão IN-SYSTEM do que antes rodava por script no
terminal — chamado por `POST /redesign/action/gerar-docs-mes` (em thread, não trava
a API). Tudo SÍNCRONO + `garantir_solicitacao_assinatura_sync` (que já notifica o sino).

Idempotente: holerite usa payslip_id; espelho usa time_sheet_id; recibo usa uuid5
determinístico. Reexecutar não duplica.
"""
from __future__ import annotations

import hashlib
import logging
import os
import uuid

logger = logging.getLogger(__name__)

_NS = uuid.uuid5(uuid.NAMESPACE_URL, "coassinatura-patrimonial")

_ROSTER_SQL = """
    SELECT e.id::text, e.nome, e.cpf, e.pis, e.matricula, to_char(e.data_admissao,'YYYY-MM-DD')
    FROM employees e JOIN empresas em ON em.id = e.empresa_id
    WHERE em.slug = 'conecta_patrimonial' AND e.nome NOT ILIKE '%teste%'
      AND lower(coalesce(e.status,'')) IN ('ativo','afastado_inss','suspenso')
    ORDER BY e.nome
"""


def gerar_docs_mes(mes: int, ano: int, tipos: set[str]) -> dict:
    """Gera e cria no fluxo os documentos do mês. `tipos` ⊆ {holerite, espelho, recibo}."""
    from sqlalchemy import text

    from core.database.session import get_sync_db_dependency
    from modules.people_management.folha.services.calculo_service import calcular_folha_colaborador
    from modules.people_management.folha.services.holerite_pdf import montar_holerite_pdf
    from modules.people_management.folha.services.recibo_vt_vr_pdf import montar_recibo_vt_vr_pdf
    from modules.people_management.hr.services.espelho_ponto_pdf import montar_espelho_ponto_pdf
    from modules.people_management.hr.services.espelho_ponto_service import ler_espelho
    from modules.signatures.helpers.solicitar_assinatura_documento import (
        garantir_solicitacao_assinatura_sync,
    )

    comp = f"{ano:04d}-{mes:02d}"
    for d in ("holerites", "espelhos", "recibos_vtvr"):
        os.makedirs(f"/app/uploads/{d}", exist_ok=True)

    sdb = next(get_sync_db_dependency())
    roster = sdb.execute(text(_ROSTER_SQL)).fetchall()
    cont = {"roster": len(roster), "holerite": 0, "espelho": 0, "recibo": 0, "pulados": 0, "falhas": 0}

    def _req(**kw):
        garantir_solicitacao_assinatura_sync(**kw)

    for eid, nome, cpf, pis, matricula, adm in roster:
        func = {"cpf": cpf, "pis": pis, "matricula": matricula, "data_admissao": adm}

        if "holerite" in tipos:
            try:
                pid = sdb.execute(text(
                    "SELECT id::text FROM hr_payslips WHERE employee_id::text=:e AND reference_period=:c "
                    "AND upper(coalesce(status,''))='PUBLISHED' ORDER BY updated_at DESC LIMIT 1"),
                    {"e": eid, "c": comp}).scalar()
                if pid:
                    hol = calcular_folha_colaborador(sdb, eid, mes, ano)
                    if hol and "error" not in hol:
                        pdf = montar_holerite_pdf(hol, func)
                        path = f"/app/uploads/holerites/holerite_{pid}.pdf"
                        with open(path, "wb") as fh:
                            fh.write(pdf)
                        _req(document_type="payslip", document_id=pid,
                             title=f"Holerite {comp} — {nome}", document_path=path,
                             document_hash=hashlib.sha256(pdf).hexdigest(),
                             employee_id=eid, employee_name=nome, employee_document=cpf)
                        cont["holerite"] += 1
                    else:
                        cont["pulados"] += 1
                else:
                    cont["pulados"] += 1
            except Exception as exc:  # noqa: BLE001
                cont["falhas"] += 1
                logger.warning("gerar holerite %s: %s", nome, exc)

        if "espelho" in tipos:
            try:
                esp = ler_espelho(sdb, eid, mes, ano)
                if not esp:
                    try:
                        from modules.people_management.hr.services.espelho_service import calcular_espelho
                        calcular_espelho(sdb, eid, mes, ano)
                        sdb.commit()
                        esp = ler_espelho(sdb, eid, mes, ano)
                    except Exception:  # noqa: BLE001
                        esp = None
                if esp and esp.get("time_sheet_id"):
                    pdf = montar_espelho_ponto_pdf(esp)
                    path = f"/app/uploads/espelhos/espelho_{esp['time_sheet_id']}.pdf"
                    with open(path, "wb") as fh:
                        fh.write(pdf)
                    _req(document_type="espelho_ponto", document_id=str(esp["time_sheet_id"]),
                         title=f"Espelho de Ponto {comp} — {nome}", document_path=path,
                         document_hash=hashlib.sha256(pdf).hexdigest(),
                         employee_id=eid, employee_name=nome, employee_document=cpf)
                    cont["espelho"] += 1
                else:
                    cont["pulados"] += 1
            except Exception as exc:  # noqa: BLE001
                cont["falhas"] += 1
                logger.warning("gerar espelho %s: %s", nome, exc)

        if "recibo" in tipos:
            try:
                hol = calcular_folha_colaborador(sdb, eid, mes, ano)
                if hol and "error" not in hol:
                    pdf = montar_recibo_vt_vr_pdf(hol, func)
                    did = str(uuid.uuid5(_NS, f"vtvr:{eid}:{comp}"))
                    path = f"/app/uploads/recibos_vtvr/recibo_{did}.pdf"
                    with open(path, "wb") as fh:
                        fh.write(pdf)
                    _req(document_type="recibo_vt_vr", document_id=did,
                         title=f"Recibo VT/VR {comp} — {nome}", document_path=path,
                         document_hash=hashlib.sha256(pdf).hexdigest(),
                         employee_id=eid, employee_name=nome, employee_document=cpf)
                    cont["recibo"] += 1
                else:
                    cont["pulados"] += 1
            except Exception as exc:  # noqa: BLE001
                cont["falhas"] += 1
                logger.warning("gerar recibo %s: %s", nome, exc)

    logger.info("gerar_docs_mes %s tipos=%s => %s", comp, tipos, cont)
    return cont
