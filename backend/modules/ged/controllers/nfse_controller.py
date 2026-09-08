"""
Controller de NFS-e e Dashboard Financeiro.

Endpoints para consulta de notas fiscais de servico emitidas,
emissao via ABRASF 2.04 (Prefeitura de Manaus) e metricas de faturamento.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["NFS-e"])


# ── Schemas de emissão ───────────────────────────────────────────────────────


class EmitirNFSeRequest(BaseModel):
    """Payload para emissão de NFS-e.

    Aceita nfse_id (carrega dados do banco) OU dados completos.
    """

    nfse_id: str | None = None

    # Tomador (obrigatório quando nfse_id não informado)
    tomador_cpf_cnpj: str | None = None
    tomador_razao_social: str | None = None
    tomador_endereco: str | None = None
    tomador_numero: str | None = None
    tomador_bairro: str | None = None
    tomador_cidade: str | None = None
    tomador_uf: str | None = None
    tomador_cep: str | None = None
    tomador_email: str | None = None
    tomador_telefone: str | None = None

    # Serviço (obrigatório quando nfse_id não informado)
    codigo_servico: str | None = None
    discriminacao: str | None = None
    valor_servicos: float | None = None
    valor_deducoes: float = 0.0
    valor_pis: float = 0.0
    valor_cofins: float = 0.0
    valor_inss: float = 0.0
    valor_ir: float = 0.0
    valor_csll: float = 0.0
    aliquota_iss: float = 0.05
    iss_retido: bool = False

    # Competência (YYYY-MM-DD ou YYYY-MM)
    competencia: str | None = None
    natureza_operacao: str = "1"
    optante_simples: bool = True


class EmitirNFSeResponse(BaseModel):
    numero_nfse: str | None
    codigo_verificacao: str | None
    status: str
    protocolo: str | None = None
    mensagem: str | None = None
    xml: str | None = None


# ── Endpoint de emissão ───────────────────────────────────────────────────────


@router.get("/nfse")
async def list_nfse(
    competencia: str | None = Query(None, description="YYYY-MM (ex: 2026-01)"),
    cliente: str | None = Query(None, description="Filtro por razao social (parcial)"),
    status: str | None = Query(None, description="autorizada, cancelada, etc."),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Lista NFS-e emitidas com filtros.

    FONTE REAL: nfse_emitidas_nacional (portal nacional gov.br, todos os meses de 2026,
    só cStat 100 = autorizadas). Não existe coluna 'active'/'status' (toda linha é válida),
    nem 'numero_rps'/'iss_retido'/'discriminacao'. 'competencia' é VARCHAR 'YYYY-MM'.
    Mesma fonte usada por /nfse/dashboard logo abaixo (que estava correto).
    """
    conditions: list[str] = []
    params: dict[str, Any] = {"limit": limit, "offset": offset}

    if competencia:
        conditions.append("competencia = :competencia")
        params["competencia"] = competencia
    if cliente:
        conditions.append("tomador_nome ILIKE :cliente")
        params["cliente"] = f"%{cliente}%"
    # NOTA: nfse_emitidas_nacional não tem coluna 'status' — todas as linhas são
    # autorizadas (cStat 100). O filtro 'status' é ignorado (mantido na assinatura
    # por compatibilidade de API). Só cancelaria se houvesse uma tabela de canceladas.

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""

    # COUNT(*) real da query com os MESMOS filtros (independente do limit/offset da
    # página). Antes retornava len(rows), que mentia sobre o total quando o LIMIT
    # truncava (ex.: 77 notas no banco, mas total=50). Params de paginação removidos
    # do COUNT para não colidir com a query sem LIMIT.
    count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}
    count_result = await db.execute(
        text(f"SELECT count(*) FROM nfse_emitidas_nacional{where}"),
        count_params,
    )
    total = int(count_result.scalar() or 0)

    result = await db.execute(
        text(
            f"SELECT chave_acesso, numero, competencia, data_emissao, "
            f"tomador_nome, tomador_cnpj, descricao, valor_servicos, "
            f"iss_aliquota, iss_valor "
            f"FROM nfse_emitidas_nacional{where} "
            f"ORDER BY competencia DESC, data_emissao DESC "
            f"LIMIT :limit OFFSET :offset"
        ),
        params,
    )
    rows = result.mappings().all()

    return {
        "total": total,
        "items": [
            {
                "id": r["chave_acesso"],
                "numero_nfse": r["numero"],
                "numero_rps": None,
                "status": "autorizada",
                "data_emissao": r["data_emissao"].isoformat() if r["data_emissao"] else None,
                # competencia é VARCHAR 'YYYY-MM' na fonte nacional (não é date)
                "data_competencia": r["competencia"],
                "tomador_razao_social": r["tomador_nome"],
                "tomador_cpf_cnpj": r["tomador_cnpj"],
                "descricao_servico": r["descricao"],
                "valor_servicos": float(r["valor_servicos"] or 0),
                "iss_aliquota": float(r["iss_aliquota"] or 0),
                "iss_valor": float(r["iss_valor"]) if r["iss_valor"] else 0,
                "iss_retido": False,
                "discriminacao": r["descricao"],
            }
            for r in rows
        ],
    }


@router.get("/nfse/dashboard")
async def nfse_dashboard(
    current_user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Dashboard de faturamento com metricas consolidadas."""
    # FONTE REAL: nfse_emitidas_nacional (portal nacional gov.br, só cStat 100, todos meses 2026)
    # Faturamento por competencia
    por_mes = await db.execute(
        text("""
        SELECT
            competencia as competencia,
            count(*) as nfse_emitidas,
            sum(valor_servicos) as faturamento_bruto,
            sum(iss_valor) as iss_total,
            sum(valor_servicos) - COALESCE(sum(iss_valor), 0) as faturamento_liquido
        FROM nfse_emitidas_nacional
        GROUP BY competencia
        ORDER BY competencia DESC
        LIMIT 12
    """)
    )
    meses = por_mes.mappings().all()

    # Faturamento por cliente (acumulado)
    por_cliente = await db.execute(
        text("""
        SELECT
            tomador_nome as cliente,
            tomador_cnpj as cnpj,
            count(*) as nfse_emitidas,
            sum(valor_servicos) as total_bruto,
            sum(iss_valor) as total_iss
        FROM nfse_emitidas_nacional
        GROUP BY tomador_nome, tomador_cnpj
        ORDER BY sum(valor_servicos) DESC
    """)
    )
    clientes = por_cliente.mappings().all()

    # Faturamento por tipo de servico
    por_servico = await db.execute(
        text("""
        SELECT
            descricao as servico,
            count(*) as quantidade,
            sum(valor_servicos) as total
        FROM nfse_emitidas_nacional
        GROUP BY descricao
        ORDER BY sum(valor_servicos) DESC
    """)
    )
    servicos = por_servico.mappings().all()

    # Totais gerais
    totais = await db.execute(
        text("""
        SELECT
            count(*) as total_nfse,
            count(DISTINCT tomador_cnpj) as total_clientes,
            sum(valor_servicos) as faturamento_total,
            sum(iss_valor) as iss_total,
            avg(valor_servicos) as ticket_medio
        FROM nfse_emitidas_nacional
    """)
    )
    t = totais.mappings().first()

    return {
        "totais": {
            "nfse_emitidas": t["total_nfse"] if t else 0,
            "clientes_ativos": t["total_clientes"] if t else 0,
            "faturamento_bruto": round(float(t["faturamento_total"]), 2) if t and t["faturamento_total"] else 0,
            "iss_total": round(float(t["iss_total"]), 2) if t and t["iss_total"] else 0,
            "ticket_medio": round(float(t["ticket_medio"]), 2) if t and t["ticket_medio"] else 0,
        },
        "por_mes": [
            {
                "competencia": m["competencia"],
                "nfse_emitidas": m["nfse_emitidas"],
                "faturamento_bruto": round(float(m["faturamento_bruto"]), 2),
                "iss_total": round(float(m["iss_total"]), 2) if m["iss_total"] else 0,
                "faturamento_liquido": round(float(m["faturamento_liquido"]), 2) if m["faturamento_liquido"] else 0,
            }
            for m in meses
        ],
        "por_cliente": [
            {
                "cliente": c["cliente"],
                "cnpj": c["cnpj"],
                "nfse_emitidas": c["nfse_emitidas"],
                "total_bruto": round(float(c["total_bruto"]), 2),
                "total_iss": round(float(c["total_iss"]), 2) if c["total_iss"] else 0,
            }
            for c in clientes
        ],
        "por_servico": [
            {
                "servico": s["servico"],
                "quantidade": s["quantidade"],
                "total": round(float(s["total"]), 2),
            }
            for s in servicos
        ],
    }


@router.get("/contracts")
async def list_contracts(
    status_filter: str | None = Query(None, alias="status", description="ativo, cancelado, etc."),
    current_user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Lista contratos com dados do cliente e retencoes fiscais."""
    conditions = ["ct.is_active = true", "ct.status <> 'draft'"]  # rascunho não é MRR (somava R$ 23.900 a mais)
    params: dict[str, Any] = {}
    if status_filter:
        conditions.append("ct.status = :status")
        params["status"] = status_filter
    where = " AND ".join(conditions)
    result = await db.execute(
        text(f"""
        SELECT ct.id, ct.contract_number, ct.name as servico, ct.description,
            ct.monthly_value, ct.total_value, ct.start_date, ct.end_date,
            ct.status, ct.contract_type, ct.auto_renewal,
            ct.renewal_period_months, ct.renewal_notification_days,
            ct.adjustment_enabled, ct.adjustment_index,
            ct.sla_config,
            c.id as client_id, c.name as client_name,
            c.document_number as client_cnpj, c.email as client_email,
            c.address_city, c.address_state
        FROM contracts ct
        JOIN clients c ON ct.client_id = c.id
        WHERE {where}
        ORDER BY ct.monthly_value DESC
        """),
        params,
    )
    rows = result.mappings().all()
    total_mrr = sum(float(r["monthly_value"]) for r in rows)
    return {
        "total": len(rows),
        "mrr_total": round(total_mrr, 2),
        "items": [
            {
                "id": str(r["id"]),
                "contract_number": r["contract_number"],
                "servico": r["servico"],
                "description": r["description"],
                "monthly_value": float(r["monthly_value"]),
                "total_value": float(r["total_value"]) if r["total_value"] else 0,
                "start_date": r["start_date"].isoformat() if r["start_date"] else None,
                "end_date": r["end_date"].isoformat() if r["end_date"] else None,
                "status": r["status"],
                "contract_type": r["contract_type"],
                "auto_renewal": r["auto_renewal"],
                "renewal_period_months": r["renewal_period_months"],
                "adjustment_enabled": r["adjustment_enabled"],
                "adjustment_index": r["adjustment_index"],
                "sla_config": r["sla_config"] or {},
                "client": {
                    "id": str(r["client_id"]),
                    "name": r["client_name"],
                    "cnpj": r["client_cnpj"],
                    "email": r["client_email"],
                    "city": r["address_city"],
                    "state": r["address_state"],
                },
            }
            for r in rows
        ],
    }


@router.post("/contracts/{contract_id}/renew", status_code=201)
async def renew_contract(
    contract_id: str,
    reajuste_percent: float = Query(0.0, description="Percentual de reajuste"),
    meses: int = Query(12, description="Meses de renovacao"),
    current_user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Renova contrato criando novo periodo com reajuste opcional."""
    import uuid
    from datetime import date as date_cls
    from datetime import timedelta

    result = await db.execute(text("SELECT * FROM contracts WHERE id = :id AND is_active = true"), {"id": contract_id})
    contract = result.mappings().first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contrato nao encontrado")
    old_value = float(contract["monthly_value"])
    new_value = round(old_value * (1 + reajuste_percent / 100), 2)
    old_end = contract["end_date"]
    new_start = old_end + timedelta(days=1) if old_end else date_cls.today()
    new_end = date_cls(
        new_start.year + (new_start.month + meses - 1) // 12, (new_start.month + meses - 1) % 12 + 1, 1
    ) - timedelta(days=1)
    num_parts = contract["contract_number"].rsplit("-", 1)
    new_num = f"{num_parts[0]}-R{num_parts[1]}" if len(num_parts) > 1 else f"{contract['contract_number']}-R1"
    new_id = str(uuid.uuid4())
    await db.execute(
        text("""
        INSERT INTO contracts (id, contract_number, client_id, contract_type, status, name, description,
            monthly_value, total_value, setup_fee, start_date, end_date,
            grace_period_days, notice_period_days, auto_renewal, renewal_period_months,
            renewal_notification_days, adjustment_enabled, has_sla, signature_required,
            sla_config, is_active, created_at)
        VALUES (:id, :num, :cid, :type, 'active', :name, :desc, :mv, :tv, 0, :sd, :ed,  -- 'ativo' sumia do MRR (filtra 'active'), 08/09/2026
            0, 30, true, :months, 30, true, false, true, :sla, true, NOW())
    """),
        {
            "id": new_id,
            "num": new_num,
            "cid": str(contract["client_id"]),
            "type": contract["contract_type"],
            "name": contract["name"],
            "desc": contract["description"],
            "mv": new_value,
            "tv": round(new_value * meses, 2),
            "sd": new_start.isoformat(),
            "ed": new_end.isoformat(),
            "months": meses,
            "sla": contract["sla_config"],
        },
    )
    await db.execute(
        text("UPDATE contracts SET status='encerrado', is_active=false, updated_at=NOW() WHERE id=:id"),
        {"id": contract_id},
    )
    await db.commit()
    return {
        "message": "Contrato renovado com sucesso",
        "old_contract": {
            "id": contract_id,
            "number": contract["contract_number"],
            "value": old_value,
            "status": "encerrado",
        },
        "new_contract": {
            "id": new_id,
            "number": new_num,
            "monthly_value": new_value,
            "total_value": round(new_value * meses, 2),
            "start_date": new_start.isoformat(),
            "end_date": new_end.isoformat(),
            "reajuste_percent": reajuste_percent,
        },
    }


@router.get("/bi/dashboard")
async def bi_dashboard(
    current_user: CurrentActiveUser = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Dashboard Business Intelligence com KPIs executivos e indicadores."""
    kpis_result = await db.execute(
        text("""
        SELECT code AS codigo, name AS nome, category, unit, current_value, previous_value,
               target_value, variance_percentage, trend, history
        FROM executive_kpis
        WHERE ativo = true
        ORDER BY display_order
    """)
    )
    kpis = kpis_result.mappings().all()

    obrig_result = await db.execute(
        text("""
        SELECT tipo, nome, status, competencia_mes, competencia_ano,
               data_vencimento, valor_devido
        FROM fiscal_obligations
        WHERE active = true AND status = 'pendente'
        ORDER BY data_vencimento
    """)
    )
    obrigacoes = obrig_result.mappings().all()

    cumpridas = (
        await db.execute(text("SELECT count(*) FROM fiscal_obligations WHERE active = true AND status = 'cumprida'"))
    ).scalar() or 0

    return {
        "kpis": [
            {
                "codigo": k["codigo"],
                "nome": k["nome"],
                "categoria": k["category"],
                "unidade": k["unit"],
                "valor_atual": float(k["current_value"]) if k["current_value"] else 0,
                "valor_anterior": float(k["previous_value"]) if k["previous_value"] else 0,
                "meta": float(k["target_value"]) if k["target_value"] else 0,
                "variacao_pct": float(k["variance_percentage"]) if k["variance_percentage"] else 0,
                "tendencia": k["trend"],
                "historico": k["history"],
            }
            for k in kpis
        ],
        "fiscal": {
            "obrigacoes_cumpridas": cumpridas,
            "obrigacoes_pendentes": len(obrigacoes),
            "proximas": [
                {
                    "tipo": o["tipo"],
                    "nome": o["nome"],
                    "competencia": f"{o['competencia_mes']:02d}/{o['competencia_ano']}",
                    "vencimento": o["data_vencimento"].isoformat() if o["data_vencimento"] else None,
                    "valor": float(o["valor_devido"]) if o["valor_devido"] else 0,
                }
                for o in obrigacoes
            ],
        },
    }
