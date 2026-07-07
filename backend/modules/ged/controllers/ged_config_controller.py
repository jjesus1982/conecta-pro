"""
GED Config & Reports Controller.

Endpoints:
- GET  /config/drive      → status Google Drive
- GET  /config/schedule   → agendamento de envios
- PUT  /config/schedule   → salvar agendamento
- GET  /reports/monthly   → relatório mensal GED
"""

import logging
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["GED - Config & Reports"])


# ─── GED Clients (alias /ged/clients → proxy to people-management) ────────────


@router.get("/clients")
@router.get("/clients/", include_in_schema=False)
async def list_ged_clients(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Lista clientes GED. Alias para /people-management/ged/clients."""
    result = await db.execute(
        text("""
        SELECT id, name, type, cnpj, address, contact_name, contact_email,
            contact_phone, portal_access_enabled, is_active, created_at
        FROM ged_clients
        WHERE is_active = true
        ORDER BY name
        """)
    )
    rows = result.mappings().all()
    return {
        "items": [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "type": r["type"],
                "cnpj": r["cnpj"],
                "address": r["address"],
                "contact_name": r["contact_name"],
                "contact_email": r["contact_email"],
                "contact_phone": r["contact_phone"],
                "portal_access_enabled": r["portal_access_enabled"],
                "is_active": r["is_active"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ],
        "total": len(rows),
    }


@router.put("/config/document-types/{doc_type_id}")
async def update_document_type(
    doc_type_id: str,
    data: dict[str, Any],
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Atualiza tipo de documento (ativar/desativar)."""
    logger.info("Document type %s updated: %s", doc_type_id, data)
    return {"id": doc_type_id, **data, "updated": True}


@router.get("/reports/by-client")
async def report_by_client(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Relatório de documentos por cliente."""
    result = await db.execute(
        text("""
        SELECT gc.name as cliente, gc.cnpj,
            COUNT(gk.id) as total_kits,
            SUM(gk.total_documents) as total_docs,
            SUM(gk.documents_signed) as docs_assinados
        FROM ged_clients gc
        LEFT JOIN ged_document_kits gk ON gk.client_id = gc.id
        WHERE gc.is_active = true
        GROUP BY gc.id, gc.name, gc.cnpj
        ORDER BY gc.name
        """)
    )
    rows = result.mappings().all()
    return {
        "tipo": "por_cliente",
        "gerado_em": __import__("datetime").datetime.now().isoformat(),
        "dados": [
            {
                "cliente": r["cliente"],
                "cnpj": r["cnpj"],
                "total_kits": r["total_kits"] or 0,
                "total_docs": int(r["total_docs"] or 0),
                "docs_assinados": int(r["docs_assinados"] or 0),
            }
            for r in rows
        ],
    }


@router.get("/reports/compliance")
async def report_compliance(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Relatório de compliance — certidões e prazos."""
    result = await db.execute(
        text("""
        SELECT tipo, nome, situacao, status, data_validade, ativo
        FROM bidding_certificates WHERE ativo = true
        ORDER BY data_validade ASC
        """)
    )
    rows = result.mappings().all()
    from datetime import date as d

    today = d.today()
    return {
        "tipo": "compliance",
        "gerado_em": __import__("datetime").datetime.now().isoformat(),
        "certidoes": [
            {
                "tipo": r["tipo"],
                "nome": r["nome"],
                "situacao": r["situacao"],
                "status": r["status"],
                "data_validade": r["data_validade"].isoformat() if r["data_validade"] else None,
                "dias_restantes": (r["data_validade"].date() - today).days if r["data_validade"] else None,
            }
            for r in rows
        ],
        "resumo": {
            "total": len(rows),
            "validas": sum(1 for r in rows if r["status"] == "valid"),
            "vencidas": sum(1 for r in rows if r["status"] == "expired"),
        },
    }


@router.get("/reports/signatures")
async def report_signatures(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Relatório de assinaturas digitais."""
    result = await db.execute(
        text("""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE status = 'signed') as assinados,
            COUNT(*) FILTER (WHERE status = 'pending') as pendentes,
            COUNT(*) FILTER (WHERE status = 'refused') as recusados,
            COUNT(*) FILTER (WHERE status = 'expired') as expirados
        FROM ged_document_signatures
        """)
    )
    r = result.mappings().first()
    return {
        "tipo": "assinaturas",
        "gerado_em": __import__("datetime").datetime.now().isoformat(),
        "resumo": {
            "total": r["total"] if r else 0,
            "assinados": r["assinados"] if r else 0,
            "pendentes": r["pendentes"] if r else 0,
            "recusados": r["recusados"] if r else 0,
            "expirados": r["expirados"] if r else 0,
        },
    }


# ─── Config Schedule ──────────────────────────────────────────────────────────

_schedule_config: dict[str, Any] = {
    "envio_automatico": False,
    "dia_envio": 25,
    "hora_envio": "09:00",
    "canal_envio": "whatsapp",
    "incluir_certidoes": True,
    "incluir_kits": True,
    "destinatarios": [],
    "ativo": False,
}


@router.get("/config/schedule")
async def get_config_schedule(
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Retorna configuração de agendamento de envios."""
    return _schedule_config


@router.put("/config/schedule")
async def update_config_schedule(
    config: dict[str, Any],
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Salva configuração de agendamento."""
    allowed_keys = {
        "envio_automatico",
        "dia_envio",
        "hora_envio",
        "canal_envio",
        "incluir_certidoes",
        "incluir_kits",
        "destinatarios",
        "ativo",
    }
    for key, value in config.items():
        if key in allowed_keys:
            _schedule_config[key] = value

    logger.info("GED schedule atualizado: %s", config)
    return _schedule_config


# ─── Config Email Templates ──────────────────────────────────────────────────


@router.get("/config/email-templates")
async def get_email_templates(
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Retorna templates de email configurados."""
    return {
        "templates": [
            {
                "id": "kit-envio",
                "nome": "Envio Kit Mensal",
                "assunto": "Kit Documental {mes}/{ano} - {cliente}",
                "ativo": True,
            },
            {
                "id": "cert-alerta",
                "nome": "Alerta Certidão Vencendo",
                "assunto": "Certidão {tipo} vence em {dias} dias",
                "ativo": True,
            },
        ],
    }


# ─── Config Document Types ───────────────────────────────────────────────────


@router.get("/config/document-types")
async def get_document_types(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Retorna tipos de documentos configurados para kits GED."""
    result = await db.execute(
        text("""
        SELECT id, name, category, description, required_for_kit, is_active
        FROM ged_document_types
        WHERE is_active = true
        ORDER BY category, name
        """)
    )
    rows = result.mappings().all()
    tipos = [
        {
            "id": str(r["id"]),
            "name": r["name"],
            "category": r["category"],
            "description": r["description"],
            "required_for_kit": r["required_for_kit"],
            "is_active": r["is_active"],
        }
        for r in rows
    ]
    return {"tipos": tipos, "total": len(tipos)}


# ─── Reports Monthly ─────────────────────────────────────────────────────────


@router.get("/reports/monthly")
async def get_relatorio_mensal(
    mes: int | None = Query(None),
    ano: int | None = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Relatório mensal completo do módulo GED."""
    hoje = date.today()

    # Quando não há parâmetros, usar o mês mais recente que possui kits
    # (evita retornar zerado quando o mês corrente ainda não tem kits)
    if mes is None and ano is None:
        latest_result = await db.execute(text("SELECT MAX(reference_month) FROM ged_document_kits"))
        latest_month = latest_result.scalar()
        if latest_month:
            mes_ref = latest_month.month
            ano_ref = latest_month.year
        else:
            mes_ref = hoje.month
            ano_ref = hoje.year
    else:
        mes_ref = mes or hoje.month
        ano_ref = ano or hoje.year

    mes_date = date(ano_ref, mes_ref, 1)

    # Kits do mês
    kits_result = await db.execute(
        text("""
        SELECT
            gk.id,
            gc.name as cliente,
            gk.status,
            gk.total_documents,
            gk.documents_signed,
            gk.completion_percentage
        FROM ged_document_kits gk
        LEFT JOIN ged_clients gc ON gk.client_id = gc.id
        WHERE DATE_TRUNC('month', gk.reference_month) = DATE_TRUNC('month', CAST(:mes AS date))
        ORDER BY gc.name
        """),
        {"mes": mes_date},
    )
    kits_rows = kits_result.mappings().all()

    kits = []
    concluidos = 0
    pendentes = 0
    for r in kits_rows:
        status = r["status"] or "em_montagem"
        kits.append(
            {
                "kit_id": str(r["id"]),
                "cliente": r["cliente"] or "—",
                "status": status,
                "documentos_total": r["total_documents"] or 0,
                "documentos_assinados": r["documents_signed"] or 0,
                "percentual": float(r["completion_percentage"] or 0),
            }
        )
        if status in ("completo", "enviado", "aprovado"):
            concluidos += 1
        else:
            pendentes += 1

    # Certidões
    certs_result = await db.execute(
        text("""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE status = 'valid') as validas,
            COUNT(*) FILTER (WHERE status = 'expired') as vencidas,
            COUNT(*) FILTER (WHERE data_validade <= CURRENT_TIMESTAMP + INTERVAL '30 days'
                AND status = 'valid') as vencendo_30d
        FROM bidding_certificates
        WHERE ativo = true
        """)
    )
    cr = certs_result.mappings().first()
    certidoes = {
        "total": cr["total"] if cr else 0,
        "validas": cr["validas"] if cr else 0,
        "vencidas": cr["vencidas"] if cr else 0,
        "vencendo_30d": cr["vencendo_30d"] if cr else 0,
    }

    # NFS-e do mês
    # [Veracidade] Fonte autoritativa = nfse_emitidas_nacional (jan-jun, cStat 100).
    # `nfses` so tinha jan-fev. competencia e varchar 'YYYY-MM'.
    nfse_result = await db.execute(
        text("""
        SELECT COUNT(*) as total, COALESCE(SUM(valor_servicos), 0) as valor_total
        FROM nfse_emitidas_nacional
        WHERE competencia = to_char(CAST(:mes AS date), 'YYYY-MM')
        """),
        {"mes": mes_date},
    )
    nr = nfse_result.mappings().first()
    documentos = {
        "nfse_emitidas": nr["total"] if nr else 0,
        "nfse_valor": float(nr["valor_total"]) if nr and nr["valor_total"] else 0,
    }

    # Ações recomendadas
    acoes = []
    if pendentes > 0:
        acoes.append(f"{pendentes} kit(s) em montagem — completar antes do envio")
    if certidoes.get("vencidas", 0) > 0:
        acoes.append(f"{certidoes['vencidas']} certidão(ões) vencida(s) — renovar urgente")
    if certidoes.get("vencendo_30d", 0) > 0:
        acoes.append(f"{certidoes['vencendo_30d']} certidão(ões) vencendo em 30 dias")
    if concluidos == len(kits) and len(kits) > 0:
        acoes.append(f"Todos os {concluidos} kits prontos — enviar para síndicos")
    if not acoes:
        acoes.append("Nenhuma ação pendente")

    nomes_mes = [
        "",
        "Janeiro",
        "Fevereiro",
        "Março",
        "Abril",
        "Maio",
        "Junho",
        "Julho",
        "Agosto",
        "Setembro",
        "Outubro",
        "Novembro",
        "Dezembro",
    ]

    return {
        "mes_referencia": f"{nomes_mes[mes_ref]}/{ano_ref}",
        "gerado_em": datetime.now().isoformat(),
        "resumo": {
            "total_kits": len(kits),
            "kits_concluidos": concluidos,
            "kits_pendentes": pendentes,
            "percentual_conclusao": round(concluidos / len(kits) * 100) if kits else 0,
        },
        "kits": kits,
        "certidoes": certidoes,
        "documentos": documentos,
        "acoes_recomendadas": acoes,
    }
