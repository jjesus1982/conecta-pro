# -*- coding: utf-8 -*-
"""Gera os documentos do MÊS (holerite, espelho de ponto, recibo de VT/VR) e cria cada
um no fluxo de co-assinatura (funcionário + empresa). Duas entradas:

- `gerar_docs_mes(mes, ano, tipos)` — TODOS os CLT ativos da Patrimonial (botão manual
  em Empresas → "Gerar documentos do mês").
- `gerar_docs_funcionario(mes, ano, employee_id, tipos)` — UM funcionário (gatilho
  AUTOMÁTICO ao PUBLICAR o holerite dele em `publicar_payslip`).

Tudo SÍNCRONO + `garantir_solicitacao_assinatura_sync` (que já notifica o sino).
Idempotente: holerite usa payslip_id; espelho usa time_sheet_id; recibo usa uuid5.
"""
from __future__ import annotations

import hashlib
import logging
import os
import uuid

logger = logging.getLogger(__name__)

_NS = uuid.uuid5(uuid.NAMESPACE_URL, "coassinatura-patrimonial")

#: Fontes que o espelho CONTA como medição. Espelha `espelho_service.FONTES_MEDIDAS` — o que
#: sobra é grade de escala, e é justamente isso que queremos como referência no PDF.
_FONTES_MEDIDAS_SQL = "('mobile','contingencia','facial','biometria','app','relogio')"


def _grade_do_mes(sdb, eid: str, mes: int, ano: int) -> dict[str, str]:
    """`{'2026-08-08': '06:00 18:00'}` — os horários NÃO medidos do mês, por dia.

    🔴 28/09/2026. A folha de ponto passou a imprimir o mês inteiro («2» do Jordan) e o dia sem
    medição sai rotulado «Sem registro eletrônico», com o horário da escala ao lado como
    referência. Este é o alimentador desse `grade`.

    ⭐ Sem esta função o parâmetro existiria e ninguém o preencheria — o PDF imprimiria o
    calendário completo com «—» em todo dia não medido, e o cliente perderia a única pista de
    que houve cobertura. **Régua que ninguém alimenta é régua desligada**, e foi assim que 909
    fotos ficaram invisíveis nesta casa.

    Medido em agosto/2026: das 3.420 batidas do mês, 2.030 caem aqui (Tangerino com 65% em hora
    cheia, `web` com 4 horários distintos para 414 batidas). São a GRADE, não marcação — por
    isso o PDF as imprime com «ref.» e nunca as soma nas horas.

    Nunca levanta: folha de ponto não pode deixar de sair porque a referência falhou.
    """
    from sqlalchemy import text as _t

    try:
        rows = sdb.execute(
            _t(
                "SELECT punch_timestamp::date::text AS d, to_char(punch_timestamp,'HH24:MI') AS h "
                "  FROM gp_clock_punches "
                " WHERE employee_id::text = :e "
                "   AND date_trunc('month', punch_timestamp) = make_date(:a, :m, 1) "
                f"   AND lower(coalesce(device_type,'')) NOT IN {_FONTES_MEDIDAS_SQL} "
                " ORDER BY punch_timestamp"
            ),
            {"e": str(eid), "a": int(ano), "m": int(mes)},
        ).all()
    except Exception as exc:  # noqa: BLE001
        logger.warning("grade de referência do espelho %s %02d/%s: %s", eid, mes, ano, exc)
        return {}
    por_dia: dict[str, list[str]] = {}
    for d, h in rows:
        por_dia.setdefault(d, []).append(h)
    # No máximo 6 horários por dia: a folha tem SEIS colunas de período, e referência que
    # transborda a coluna viraria texto ilegível no documento que alguém assina.
    return {d: " ".join(hs[:6]) for d, hs in por_dia.items()}

_ROSTER_SQL = """
    SELECT e.id::text, e.nome, e.cpf, e.pis, e.matricula, to_char(e.data_admissao,'YYYY-MM-DD')
    FROM employees e JOIN empresas em ON em.id = e.empresa_id
    WHERE em.slug = 'conecta_patrimonial' AND e.nome NOT ILIKE '%teste%'
      AND lower(coalesce(e.status,'')) IN ('ativo','afastado_inss','suspenso')
    ORDER BY e.nome
"""

_EMP_SQL = """
    SELECT e.id::text, e.nome, e.cpf, e.pis, e.matricula, to_char(e.data_admissao,'YYYY-MM-DD')
    FROM employees e WHERE e.id::text = :eid
"""


def _garante_dirs() -> None:
    for d in ("holerites", "espelhos", "recibos_vtvr"):
        os.makedirs(f"/app/uploads/{d}", exist_ok=True)


def _processar_emp(sdb, eid, nome, cpf, pis, matricula, adm, mes, ano, tipos, comp, cont) -> None:
    from sqlalchemy import text

    from modules.people_management.folha.services.calculo_service import calcular_folha_colaborador
    from modules.people_management.folha.services.holerite_pdf import montar_holerite_pdf
    from modules.people_management.folha.services.recibo_vt_vr_pdf import montar_recibo_vt_vr_pdf
    from modules.people_management.hr.services.espelho_ponto_pdf import montar_espelho_ponto_pdf
    from modules.people_management.hr.services.espelho_ponto_service import ler_espelho
    from modules.signatures.helpers.solicitar_assinatura_documento import garantir_solicitacao_assinatura_sync

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
                    garantir_solicitacao_assinatura_sync(
                        document_type="payslip", document_id=pid, title=f"Holerite {comp} — {nome}",
                        document_path=path, document_hash=hashlib.sha256(pdf).hexdigest(),
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
                pdf = montar_espelho_ponto_pdf(esp, grade=_grade_do_mes(sdb, eid, mes, ano))
                path = f"/app/uploads/espelhos/espelho_{esp['time_sheet_id']}.pdf"
                with open(path, "wb") as fh:
                    fh.write(pdf)
                garantir_solicitacao_assinatura_sync(
                    document_type="espelho_ponto", document_id=str(esp["time_sheet_id"]),
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
                garantir_solicitacao_assinatura_sync(
                    document_type="recibo_vt_vr", document_id=did, title=f"Recibo VT/VR {comp} — {nome}",
                    document_path=path, document_hash=hashlib.sha256(pdf).hexdigest(),
                    employee_id=eid, employee_name=nome, employee_document=cpf)
                cont["recibo"] += 1
            else:
                cont["pulados"] += 1
        except Exception as exc:  # noqa: BLE001
            cont["falhas"] += 1
            logger.warning("gerar recibo %s: %s", nome, exc)


def gerar_docs_mes(mes: int, ano: int, tipos: set[str]) -> dict:
    """Gera e cria no fluxo os documentos do mês para TODOS os CLT ativos da Patrimonial."""
    from sqlalchemy import text

    from core.database.session import get_sync_db_dependency

    comp = f"{ano:04d}-{mes:02d}"
    _garante_dirs()
    sdb = next(get_sync_db_dependency())
    roster = sdb.execute(text(_ROSTER_SQL)).fetchall()
    cont = {"roster": len(roster), "holerite": 0, "espelho": 0, "recibo": 0, "pulados": 0, "falhas": 0}
    for eid, nome, cpf, pis, matricula, adm in roster:
        _processar_emp(sdb, eid, nome, cpf, pis, matricula, adm, mes, ano, tipos, comp, cont)
    logger.info("gerar_docs_mes %s tipos=%s => %s", comp, tipos, cont)
    return cont


def gerar_docs_funcionario(mes: int, ano: int, employee_id: str, tipos: set[str] | None = None) -> dict:
    """Gera os documentos do mês de UM funcionário (gatilho automático ao publicar o holerite)."""
    from sqlalchemy import text

    from core.database.session import get_sync_db_dependency

    tipos = tipos or {"holerite", "espelho", "recibo"}
    comp = f"{ano:04d}-{mes:02d}"
    _garante_dirs()
    sdb = next(get_sync_db_dependency())
    row = sdb.execute(text(_EMP_SQL), {"eid": str(employee_id)}).first()
    cont = {"holerite": 0, "espelho": 0, "recibo": 0, "pulados": 0, "falhas": 0}
    if not row:
        return cont
    eid, nome, cpf, pis, matricula, adm = row
    _processar_emp(sdb, eid, nome, cpf, pis, matricula, adm, mes, ano, tipos, comp, cont)
    logger.info("gerar_docs_funcionario %s emp=%s => %s", comp, employee_id, cont)
    return cont
