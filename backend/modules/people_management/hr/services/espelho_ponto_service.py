"""Espelho de Ponto — leitor do motor (`time_sheets`) + integração de homologação.

READ-ONLY sobre o que o MOTOR calculou. NÃO recalcula horas, NÃO toca em batidas,
allocations ou posts. Responsável por:

1. `ler_espelho(...)`  → dict pronto para o gerador de PDF (campos do time_sheet +
   daily_summary + dados do empregado).
2. `painel_fechamento(...)` → status por funcionário do mês (calculado/anomalias/
   fechado/homologado) para o painel do DP.
3. `garantir_homologacao_espelho(...)` → cria a solicitação de assinatura
   (document_type='espelho_ponto', signer EMPLOYEE) para um espelho FECHADO.

O contrato do motor pode ainda não estar 100% pronto — tudo aqui é tolerante a
tabela vazia / colunas ausentes.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Status de time_sheet que contam como "mês FECHADO" (elegível para homologação).
STATUS_FECHADO = {"fechado", "aprovado", "revisado", "enviado_folha"}


def _hm(minutes) -> str:
    try:
        m = int(round(float(minutes or 0)))
    except (TypeError, ValueError):
        return "00:00"
    sinal = "-" if m < 0 else ""
    m = abs(m)
    return f"{sinal}{m // 60:02d}:{m % 60:02d}"


def ler_espelho(db: Session, employee_id: str, mes: int, ano: int) -> dict[str, Any] | None:
    """Lê o time_sheet do mês e devolve o dict do espelho, ou None se não existir."""
    row = db.execute(
        text(
            """
            SELECT id, employee_id, employee_name, employee_registration, employee_cpf,
                   employee_pis, position_name, department_name, condominium_name,
                   work_schedule_name, reference_month, reference_year, status,
                   hours_worked_minutes, hours_expected_minutes, hours_balance_minutes,
                   overtime_50_minutes, overtime_100_minutes, overtime_total_minutes,
                   night_hours_minutes, late_minutes, late_count,
                   absent_days, unjustified_absent_days, work_days_worked,
                   dsr_lost_days, dsr_entitled, anomaly_count, anomaly_resolved_count,
                   daily_summary, approved_by_employee, employee_approved_at
            FROM time_sheets
            WHERE CAST(employee_id AS TEXT) = :e
              AND reference_month = :m AND reference_year = :y
              AND COALESCE(is_deleted, false) = false
            ORDER BY updated_at DESC NULLS LAST
            LIMIT 1
            """
        ),
        {"e": str(employee_id), "m": int(mes), "y": int(ano)},
    ).mappings().first()

    # Dados do empregado (fonte da verdade em employees; completa o cabeçalho).
    emp = db.execute(
        text(
            "SELECT nome, matricula, cpf, pis, cargo, posto_atual_nome "
            "FROM employees WHERE CAST(id AS TEXT) = :e"
        ),
        {"e": str(employee_id)},
    ).mappings().first()

    if not row:
        # Sem espelho calculado — devolve None (o controller decide o 404/aguardando).
        return None

    d = dict(row)
    dias = d.get("daily_summary") or []
    if isinstance(dias, str):
        import json

        try:
            dias = json.loads(dias)
        except Exception:  # noqa: BLE001
            dias = []

    return {
        "time_sheet_id": str(d["id"]),
        "employee_id": str(d["employee_id"]),
        "employee_name": d.get("employee_name") or (emp or {}).get("nome") or "—",
        "employee_registration": d.get("employee_registration") or (emp or {}).get("matricula"),
        "employee_cpf": d.get("employee_cpf") or (emp or {}).get("cpf"),
        "employee_pis": d.get("employee_pis") or (emp or {}).get("pis"),
        "position_name": d.get("position_name") or (emp or {}).get("cargo"),
        "condominium_name": d.get("condominium_name") or (emp or {}).get("posto_atual_nome"),
        "work_schedule_name": d.get("work_schedule_name"),
        "mes": int(d["reference_month"]),
        "ano": int(d["reference_year"]),
        "status": d.get("status"),
        "fechado": (d.get("status") or "") in STATUS_FECHADO,
        # totais já formatados HH:MM (o gerador aceita ambos)
        "horas_trabalhadas": _hm(d.get("hours_worked_minutes")),
        "horas_previstas": _hm(d.get("hours_expected_minutes")),
        "saldo_banco": _hm(d.get("hours_balance_minutes")),
        "extras_50": _hm(d.get("overtime_50_minutes")),
        "extras_100": _hm(d.get("overtime_100_minutes")),
        "adicional_noturno": _hm(d.get("night_hours_minutes")),
        "atrasos": _hm(d.get("late_minutes")),
        "faltas_dias": int(d.get("absent_days") or 0),
        "dsr_dias": int(d.get("work_days_worked") or 0),
        "dsr_perdidos": int(d.get("dsr_lost_days") or 0),
        "anomaly_count": int(d.get("anomaly_count") or 0),
        "approved_by_employee": bool(d.get("approved_by_employee")),
        "employee_approved_at": d.get("employee_approved_at"),
        "dias": dias,
    }


def _status_homologacao(db: Session, time_sheet_id: str) -> dict[str, Any]:
    """Status da assinatura (homologação) do espelho, lido de sig_signature_requests."""
    try:
        r = db.execute(
            text(
                "SELECT status, signed_at FROM sig_signature_requests "
                "WHERE document_type = 'espelho_ponto' "
                "AND (CAST(document_id AS TEXT) = :d OR custom_fields->>'document_id_raw' = :d) "
                "AND signer_type = 'employee' "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"d": str(time_sheet_id)},
        ).mappings().first()
    except Exception as exc:  # noqa: BLE001
        logger.debug("status homologação indisponível: %s", exc)
        return {"solicitado": False, "assinado": False, "status": None}
    if not r:
        return {"solicitado": False, "assinado": False, "status": None}
    assinado = str(r.get("status") or "").lower() in ("signed", "completed") or bool(r.get("signed_at"))
    return {"solicitado": True, "assinado": assinado, "status": r.get("status")}


def painel_fechamento(db: Session, mes: int, ano: int) -> dict[str, Any]:
    """Agrega o status por funcionário para o painel do DP.

    Lê apenas time_sheets do mês (o que o motor calculou). Cada item traz:
    status calculado, anomalias, se está fechado e se já foi homologado (assinado).
    """
    rows = db.execute(
        text(
            """
            SELECT id, employee_id, employee_name, position_name, condominium_name,
                   status, hours_worked_minutes, overtime_total_minutes, night_hours_minutes,
                   absent_days, anomaly_count, anomaly_resolved_count,
                   approved_by_employee, employee_approved_at
            FROM time_sheets
            WHERE reference_month = :m AND reference_year = :y
              AND COALESCE(is_deleted, false) = false
            ORDER BY employee_name
            """
        ),
        {"m": int(mes), "y": int(ano)},
    ).mappings().all()

    itens: list[dict[str, Any]] = []
    tot = {"total": 0, "calculados": 0, "com_anomalia": 0, "fechados": 0, "homologados": 0}
    for r in rows:
        anomalias = int(r.get("anomaly_count") or 0) - int(r.get("anomaly_resolved_count") or 0)
        anomalias = max(anomalias, 0)
        fechado = (r.get("status") or "") in STATUS_FECHADO
        homo = _status_homologacao(db, str(r["id"])) if fechado else {"solicitado": False, "assinado": False}
        assinado = bool(r.get("approved_by_employee")) or homo.get("assinado", False)
        itens.append(
            {
                "time_sheet_id": str(r["id"]),
                "employee_id": str(r["employee_id"]),
                "employee_name": r.get("employee_name") or "—",
                "position_name": r.get("position_name"),
                "condominium_name": r.get("condominium_name"),
                "status": r.get("status"),
                "fechado": fechado,
                "horas_trabalhadas": _hm(r.get("hours_worked_minutes")),
                "extras": _hm(r.get("overtime_total_minutes")),
                "adicional_noturno": _hm(r.get("night_hours_minutes")),
                "faltas_dias": int(r.get("absent_days") or 0),
                "anomalias_abertas": anomalias,
                "homologacao_solicitada": homo.get("solicitado", False),
                "homologado": assinado,
                "employee_approved_at": (
                    r.get("employee_approved_at").isoformat()
                    if r.get("employee_approved_at") else None
                ),
            }
        )
        tot["total"] += 1
        tot["calculados"] += 1
        if anomalias > 0:
            tot["com_anomalia"] += 1
        if fechado:
            tot["fechados"] += 1
        if assinado:
            tot["homologados"] += 1

    return {
        "mes": int(mes),
        "ano": int(ano),
        "resumo": tot,
        "pode_fechar": tot["com_anomalia"] == 0 and tot["total"] > 0,
        "funcionarios": itens,
    }


def garantir_homologacao_espelho(
    db: Session,
    *,
    esp: dict[str, Any],
    pdf_bytes: bytes | None = None,
) -> dict[str, Any] | None:
    """Cria (idempotente) a solicitação de assinatura do espelho FECHADO → funcionário.

    Só cria se o mês estiver fechado. Nunca quebra o chamador.
    """
    if not esp or not esp.get("fechado"):
        return None
    try:
        from modules.signatures.helpers import (
            document_hash_sha256,
            garantir_solicitacao_assinatura_sync,
        )

        mes, ano = esp.get("mes"), esp.get("ano")
        return garantir_solicitacao_assinatura_sync(
            document_type="espelho_ponto",
            document_id=esp["time_sheet_id"],
            title=f"Espelho de Ponto {int(mes):02d}/{ano} — {esp.get('employee_name') or 'colaborador'}",
            document_hash=document_hash_sha256(pdf_bytes),
            employee_id=esp["employee_id"],
            employee_name=esp.get("employee_name"),
            employee_document=esp.get("employee_cpf"),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Homologação do espelho não criada (ts=%s): %s", esp.get("time_sheet_id"), exc)
        return None


def solicitar_homologacao_mes(db: Session, mes: int, ano: int) -> dict[str, Any]:
    """Para todos os funcionários com espelho FECHADO no mês, garante a solicitação
    de homologação (assinatura). Retorna quantos foram enviados. Idempotente.

    IMPORTANTE: primeiro coleta os espelhos + hash com a sessão SÍNCRONA (sem tocar
    no motor de assinatura), depois cria TODAS as solicitações num ÚNICO event loop
    (uma AsyncSession). Chamar o helper `_sync` (que faz asyncio.run) em laço quebra
    o pool asyncpg ("attached to a different loop") — por isso o batch usa a versão
    async diretamente, uma vez só.
    """
    import asyncio

    from modules.people_management.hr.services.espelho_ponto_pdf import montar_espelho_ponto_pdf

    rows = db.execute(
        text(
            "SELECT DISTINCT CAST(employee_id AS TEXT) AS eid FROM time_sheets "
            "WHERE reference_month = :m AND reference_year = :y "
            "AND COALESCE(is_deleted, false) = false"
        ),
        {"m": int(mes), "y": int(ano)},
    ).mappings().all()

    # Fase 1 (sync): coleta os espelhos FECHADOS + hash do PDF.
    payloads: list[dict[str, Any]] = []
    for r in rows:
        esp = ler_espelho(db, r["eid"], mes, ano)
        if not esp or not esp.get("fechado"):
            continue
        try:
            from modules.signatures.helpers import document_hash_sha256

            pdf = montar_espelho_ponto_pdf(esp)
            dhash = document_hash_sha256(pdf)
        except Exception:  # noqa: BLE001
            dhash = None
        payloads.append(
            {
                "document_id": esp["time_sheet_id"],
                "title": f"Espelho de Ponto {int(mes):02d}/{ano} — {esp.get('employee_name') or 'colaborador'}",
                "document_hash": dhash,
                "employee_id": esp["employee_id"],
                "employee_name": esp.get("employee_name"),
                "employee_document": esp.get("employee_cpf"),
            }
        )

    if not payloads:
        return {"mes": int(mes), "ano": int(ano), "espelhos_enviados": 0, "total_fechados": 0}

    # Fase 2 (async, um único loop, UMA sessão por item): cria/garante as solicitações.
    # Sessão isolada por item para que a falha de um espelho não aborte a transação
    # (e o cascateamento) dos demais.
    async def _criar_todas() -> int:
        from core.database import async_session_factory
        from modules.signatures.helpers import garantir_solicitacao_assinatura

        enviados = 0
        for p in payloads:
            try:
                async with async_session_factory() as session:
                    res = await garantir_solicitacao_assinatura(
                        session,
                        document_type="espelho_ponto",
                        document_id=p["document_id"],
                        title=p["title"],
                        document_hash=p["document_hash"],
                        employee_id=p["employee_id"],
                        employee_name=p["employee_name"],
                        employee_document=p["employee_document"],
                    )
                if res is not None:
                    enviados += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("Homologação não criada (ts=%s): %s", p.get("document_id"), exc)
        return enviados

    try:
        enviados = asyncio.run(_criar_todas())
    except RuntimeError:
        # Já há loop ativo neste contexto — não deveria em rota `def`, mas é tolerante.
        enviados = 0
    return {"mes": int(mes), "ano": int(ano), "espelhos_enviados": enviados, "total_fechados": len(payloads)}
