"""Hub Jurídico — painel CONSOLIDADO do escritório jurídico.

Agrega, com dado REAL do banco, os indicadores dos vários "balcões" do módulo:
  - Contratos (`contracts`): ativos, vencendo, valor mensal/carteira, alertas.
    Reusa a REGRA de alertas de `contracts_service._alertas_do_contrato`
    (função pura, sem I/O) sobre linhas lidas de forma assíncrona.
  - Consultas IA (`juridico_consultas`) — contagem por área.
  - Pareceres (`juridico_pareceres`) — contagem por status.
  - Análises (`juridico_analises`) — contagem total.
  - Prazos (`juridico_prazos` + automáticos) — abertos/atrasados via prazos_service.
  - Certidões (`ged_certidoes`) — válidas / vencidas.

Nada é fabricado: tabela vazia → 0 honesto.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from . import contracts_service, prazos_service


async def _card_contratos(db: AsyncSession) -> dict[str, Any]:
    """Cards de contratos — lê `contracts` (async) e reusa a regra de alertas."""
    hoje = date.today()
    rows = (
        await db.execute(
            text(
                """
                SELECT c.id, c.contract_number, c.status, c.monthly_value, c.total_value,
                       c.end_date, c.auto_renewal, c.renewal_notification_days,
                       c.adjustment_enabled, c.next_adjustment_date,
                       c.signature_required, c.signed_at
                FROM contracts c
                """
            )
        )
    ).mappings().all()
    contratos = [dict(r) for r in rows]
    ativos = [c for c in contratos if str(c.get("status") or "").lower() == "active"]
    valor_mensal = sum(float(c["monthly_value"]) for c in ativos if c.get("monthly_value") is not None)
    valor_carteira = sum(float(c["total_value"]) for c in ativos if c.get("total_value") is not None)

    vencendo_30 = vencidos = renov = reaj = assin = com_alerta = 0
    for c in contratos:
        al = contracts_service._alertas_do_contrato(c, hoje)  # regra pura, sem I/O
        dpv = al["dias_para_vencer"]
        if al["vencimento_nivel"] and dpv is not None and 0 <= dpv <= 30:
            vencendo_30 += 1
        if al["vencido"]:
            vencidos += 1
        if al["renovacao_pendente"]:
            renov += 1
        if al["reajuste_pendente"]:
            reaj += 1
        if al["assinatura_pendente"]:
            assin += 1
        if al["tem_alerta"]:
            com_alerta += 1

    return {
        "total": len(contratos),
        "ativos": len(ativos),
        "valor_mensal_ativo": round(valor_mensal, 2),
        "valor_carteira_ativa": round(valor_carteira, 2),
        "vencendo_30d": vencendo_30,
        "vencidos": vencidos,
        "renovacoes_pendentes": renov,
        "reajustes_proximos": reaj,
        "assinaturas_pendentes": assin,
        "com_alerta": com_alerta,
    }


async def _contagem_por(db: AsyncSession, tabela: str, coluna: str) -> dict[str, int]:
    rows = (
        await db.execute(
            text(f"SELECT COALESCE({coluna}, '(sem)') AS chave, COUNT(*) AS n FROM {tabela} GROUP BY 1")
        )
    ).mappings().all()
    return {str(r["chave"]): int(r["n"]) for r in rows}


async def _scalar(db: AsyncSession, sql: str) -> int:
    return int((await db.execute(text(sql))).scalar() or 0)


async def _card_consultas(db: AsyncSession) -> dict[str, Any]:
    por_area = await _contagem_por(db, "juridico_consultas", "area")
    return {
        "total": sum(por_area.values()),
        "por_area": por_area,
        "escalonadas": await _scalar(
            db, "SELECT COUNT(*) FROM juridico_consultas WHERE escalonar IS TRUE"
        ),
    }


async def _card_pareceres(db: AsyncSession) -> dict[str, Any]:
    por_status = await _contagem_por(db, "juridico_pareceres", "status")
    return {"total": sum(por_status.values()), "por_status": por_status}


async def _card_analises(db: AsyncSession) -> dict[str, Any]:
    total = await _scalar(db, "SELECT COUNT(*) FROM juridico_analises")
    criticas = await _scalar(
        db, "SELECT COUNT(*) FROM juridico_analises WHERE COALESCE(clausulas_criticas, 0) > 0"
    )
    return {"total": total, "com_clausulas_criticas": criticas}


async def _card_prazos(db: AsyncSession) -> dict[str, Any]:
    dados = await prazos_service.listar_prazos(db, incluir_automaticos=True)
    r = dados["resumo"]
    return {
        "total": dados["total"],
        "abertos": r["abertos"],
        "atrasados": r["atrasados"],
        "cumpridos": r["cumpridos"],
    }


async def _card_certidoes(db: AsyncSession) -> dict[str, Any]:
    hoje = date.today().isoformat()
    total = await _scalar(db, "SELECT COUNT(*) FROM ged_certidoes")
    vencidas = await _scalar(
        db, f"SELECT COUNT(*) FROM ged_certidoes WHERE expiry_date IS NOT NULL AND expiry_date < DATE '{hoje}'"
    )
    validas = await _scalar(
        db, f"SELECT COUNT(*) FROM ged_certidoes WHERE expiry_date IS NULL OR expiry_date >= DATE '{hoje}'"
    )
    return {"total": total, "validas": validas, "vencidas": vencidas}


async def hub_dashboard(db: AsyncSession) -> dict[str, Any]:
    """Painel consolidado do módulo Jurídico — todos os cards com dado real."""
    contratos = await _card_contratos(db)
    consultas = await _card_consultas(db)
    pareceres = await _card_pareceres(db)
    analises = await _card_analises(db)
    prazos = await _card_prazos(db)
    certidoes = await _card_certidoes(db)

    # painel de "pendências" — o que exige ação do jurídico agora
    pendencias = (
        contratos["com_alerta"]
        + prazos["atrasados"]
        + certidoes["vencidas"]
        + consultas["escalonadas"]
    )

    return {
        "referencia": date.today().isoformat(),
        "pendencias_totais": pendencias,
        "cards": {
            "contratos": contratos,
            "consultas_ia": consultas,
            "pareceres": pareceres,
            "analises": analises,
            "prazos": prazos,
            "certidoes": certidoes,
        },
    }
