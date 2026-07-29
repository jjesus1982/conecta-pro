"""Central de Contratos (Jurídico) — visão consolidada + motor de ALERTAS.

Lê a tabela real `contracts` (+ `clients` para o nome) e computa alertas de veracidade
a partir das DATAS REAIS: vencimento, renovação (janela de aviso), reajuste e assinatura.
Nada é fabricado — se o contrato vence em dez/2026, o alerta só acende quando a janela chega.
Inspirado no padrão "renewal watcher" (claude-for-legal, Apache-2.0), implementado nativo.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

# Janelas padrão (dias) — só usadas quando o contrato não define a sua própria
_JANELA_VENC = [30, 60, 90]
_REAJUSTE_AVISO_DIAS = 45


def _dias(d: date | None, hoje: date) -> int | None:
    return (d - hoje).days if d else None


def _alertas_do_contrato(c: dict, hoje: date) -> dict[str, Any]:
    """Computa os flags de alerta de UM contrato a partir das datas reais."""
    ativo = str(c.get("status") or "").lower() == "active"
    dpv = _dias(c.get("end_date"), hoje)
    aviso_renov = int(c.get("renewal_notification_days") or 30)
    # renovação: contrato ativo com auto-renovação e dentro da janela de aviso antes do fim
    renov = bool(
        ativo and c.get("auto_renewal") and dpv is not None and 0 <= dpv <= aviso_renov
    )
    # reajuste: habilitado e próxima data de reajuste dentro do aviso
    dpr = _dias(c.get("next_adjustment_date"), hoje)
    reaj = bool(c.get("adjustment_enabled") and dpr is not None and 0 <= dpr <= _REAJUSTE_AVISO_DIAS)
    # assinatura pendente: exige assinatura e não foi assinada
    assin_pend = bool(c.get("signature_required") and not c.get("signed_at"))
    # nível do alerta de vencimento
    venc_nivel = None
    if ativo and dpv is not None and dpv >= 0:
        if dpv <= 30:
            venc_nivel = "critico"
        elif dpv <= 60:
            venc_nivel = "atencao"
        elif dpv <= 90:
            venc_nivel = "proximo"
    vencido = bool(ativo and dpv is not None and dpv < 0)
    return {
        "dias_para_vencer": dpv,
        "vencido": vencido,
        "vencimento_nivel": venc_nivel,
        "renovacao_pendente": renov,
        "dias_para_reajuste": dpr,
        "reajuste_pendente": reaj,
        "assinatura_pendente": assin_pend,
        "tem_alerta": bool(venc_nivel or vencido or renov or reaj or assin_pend),
    }


def _fetch_contratos(db: Session) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT c.id, c.contract_number, c.name, c.status, c.contract_type,
                   c.monthly_value, c.total_value, c.start_date, c.end_date,
                   c.auto_renewal, c.renewal_period_months, c.renewal_notification_days,
                   c.adjustment_enabled, c.adjustment_index, c.next_adjustment_date,
                   c.signature_required, c.signed_at, c.tipo_servico, c.has_sla,
                   c.client_id, cl.name AS client_name
            FROM contracts c
            LEFT JOIN clients cl ON cl.id = c.client_id
            ORDER BY c.end_date NULLS LAST, c.created_at DESC
            """
        )
    ).mappings().all()
    return [dict(r) for r in rows]


def listar_contratos(db: Session) -> dict[str, Any]:
    """Lista consolidada de contratos com o status de alerta de cada um."""
    hoje = date.today()
    itens = []
    for c in _fetch_contratos(db):
        al = _alertas_do_contrato(c, hoje)
        itens.append(
            {
                "id": str(c["id"]),
                "numero": c.get("contract_number") or "—",
                "nome": c.get("name") or "—",
                "cliente": c.get("client_name") or "—",
                "status": c.get("status"),
                "tipo": c.get("contract_type"),
                "tipo_servico": c.get("tipo_servico"),
                "valor_mensal": float(c["monthly_value"]) if c.get("monthly_value") is not None else None,
                "valor_total": float(c["total_value"]) if c.get("total_value") is not None else None,
                "inicio": c["start_date"].isoformat() if c.get("start_date") else None,
                "fim": c["end_date"].isoformat() if c.get("end_date") else None,
                "auto_renovacao": bool(c.get("auto_renewal")),
                "tem_sla": bool(c.get("has_sla")),
                **al,
            }
        )
    return {"total": len(itens), "contratos": itens}


def dashboard_contratos(db: Session) -> dict[str, Any]:
    """Painel da Central de Contratos: totais reais + contadores de alerta."""
    hoje = date.today()
    contratos = _fetch_contratos(db)
    ativos = [c for c in contratos if str(c.get("status") or "").lower() == "active"]
    valor_mensal = sum(float(c["monthly_value"]) for c in ativos if c.get("monthly_value") is not None)
    valor_carteira = sum(float(c["total_value"]) for c in ativos if c.get("total_value") is not None)

    venc = {30: 0, 60: 0, 90: 0}
    vencidos = renov = reaj = assin = 0
    alertas: list[dict] = []
    for c in contratos:
        al = _alertas_do_contrato(c, hoje)
        dpv = al["dias_para_vencer"]
        if al["vencimento_nivel"]:
            for j in _JANELA_VENC:
                if dpv is not None and 0 <= dpv <= j:
                    venc[j] += 1
        if al["vencido"]:
            vencidos += 1
        if al["renovacao_pendente"]:
            renov += 1
        if al["reajuste_pendente"]:
            reaj += 1
        if al["assinatura_pendente"]:
            assin += 1
        if al["tem_alerta"]:
            motivos = []
            if al["vencido"]:
                motivos.append("VENCIDO")
            elif al["vencimento_nivel"]:
                motivos.append(f"vence em {dpv}d")
            if al["renovacao_pendente"]:
                motivos.append("renovação")
            if al["reajuste_pendente"]:
                motivos.append(f"reajuste em {al['dias_para_reajuste']}d")
            if al["assinatura_pendente"]:
                motivos.append("assinatura pendente")
            alertas.append(
                {
                    "id": str(c["id"]),
                    "numero": c.get("contract_number") or "—",
                    "cliente": c.get("client_name") or "—",
                    "motivos": motivos,
                    "prioridade": "critica" if (al["vencido"] or al["vencimento_nivel"] == "critico") else "media",
                }
            )
    return {
        "referencia": hoje.isoformat(),
        "total_contratos": len(contratos),
        "contratos_ativos": len(ativos),
        "contratos_rascunho": sum(1 for c in contratos if str(c.get("status") or "").lower() == "draft"),
        "valor_mensal_ativo": round(valor_mensal, 2),
        "valor_carteira_ativa": round(valor_carteira, 2),
        "vencendo_30d": venc[30],
        "vencendo_60d": venc[60],
        "vencendo_90d": venc[90],
        "vencidos": vencidos,
        "renovacoes_pendentes": renov,
        "reajustes_proximos": reaj,
        "assinaturas_pendentes": assin,
        "alertas": sorted(alertas, key=lambda a: 0 if a["prioridade"] == "critica" else 1),
    }


def obter_texto_contrato(db: Session, contrato_id: str) -> dict[str, Any] | None:
    """Busca só o texto real do contrato (`content`, fallback `description`) para a
    análise read-only (5.6b). Nunca fabrica: sem conteúdo em nenhum dos dois campos =
    texto vazio (a análise responde honestamente que não há o que analisar).
    """
    row = db.execute(
        text("SELECT id, contract_number, name, content, description FROM contracts WHERE id = :id"),
        {"id": contrato_id},
    ).mappings().first()
    if not row:
        return None
    return {
        "id": str(row["id"]),
        "numero": row.get("contract_number") or "—",
        "nome": row.get("name") or "—",
        "texto": (row.get("content") or row.get("description") or "").strip(),
    }


def obter_contrato(db: Session, contrato_id: str) -> dict[str, Any] | None:
    hoje = date.today()
    for c in _fetch_contratos(db):
        if str(c["id"]) == str(contrato_id):
            base = {k: (v.isoformat() if isinstance(v, date) else (float(v) if k in ("monthly_value", "total_value") and v is not None else v)) for k, v in c.items()}
            base["id"] = str(c["id"])
            base["client_id"] = str(c["client_id"]) if c.get("client_id") else None
            base["alertas"] = _alertas_do_contrato(c, hoje)
            return base
    return None
