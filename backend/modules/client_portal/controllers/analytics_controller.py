"""
Controller de Analytics do Portal do Cliente.

Endpoints protegidos por autenticacao do portal para visualizacao
de metricas historicas, conformidade e saude do relacionamento.
"""

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, extract, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from modules.client_portal.middleware.portal_auth import get_current_portal_client
from modules.client_portal.models.ticket import ClientTicket, TicketStatus
from modules.people_management.ged.models.document_kit import GedDocumentKit, KitStatus
from modules.people_management.ged.models.kit_document import DocumentType, KitDocument

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["Portal - Analytics"])

# Certidoes negativas que compoe o score de conformidade
CERTIDOES_TYPES = [
    (DocumentType.CND_FEDERAL, "CND Federal"),
    (DocumentType.CND_ESTADUAL, "CND Estadual"),
    (DocumentType.CND_MUNICIPAL, "CND Municipal"),
    (DocumentType.CRF_FGTS, "CRF FGTS"),
    (DocumentType.CNDT_TRABALHISTA, "CNDT Trabalhista"),
]


@router.get("/overview")
async def get_overview(
    client_id: str = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna visao geral consolidada de metricas do cliente.

    Inclui contadores de kits, chamados, documentos e calcula
    o health score baseado em conformidade e resolucao de chamados.
    """
    try:
        # --- Kits ---
        kits_result = await db.execute(
            select(
                func.count().label("total"),
                func.count(case((GedDocumentKit.status == KitStatus.APROVADO, 1))).label("aprovados"),
                func.count(
                    case(
                        (
                            GedDocumentKit.status.in_([KitStatus.EM_MONTAGEM, KitStatus.COMPLETO, KitStatus.ENVIADO]),
                            1,
                        )
                    )
                ).label("pendentes"),
                func.sum(GedDocumentKit.total_documents).label("docs_total"),
                func.sum(GedDocumentKit.documents_signed).label("docs_assinados"),
            ).where(GedDocumentKit.client_id == client_id)
        )
        kits_row = kits_result.one()
        kits_total = int(kits_row.total or 0)
        kits_aprovados = int(kits_row.aprovados or 0)
        kits_pendentes = int(kits_row.pendentes or 0)
        docs_total = int(kits_row.docs_total or 0)
        docs_assinados = int(kits_row.docs_assinados or 0)

        # --- Chamados ---
        now = datetime.now(tz=UTC)
        thirty_days_ago = now.replace(day=max(1, now.day - 30))

        tickets_result = await db.execute(
            select(
                func.count().label("total"),
                func.count(case((ClientTicket.status != TicketStatus.FECHADO, 1))).label("abertos"),
                func.count(
                    case(
                        (
                            (ClientTicket.status == TicketStatus.FECHADO) & (ClientTicket.closed_at >= thirty_days_ago),
                            1,
                        )
                    )
                ).label("resolvidos_30d"),
            ).where(ClientTicket.client_id == client_id)
        )
        tickets_row = tickets_result.one()
        chamados_abertos = int(tickets_row.abertos or 0)
        chamados_resolvidos_30d = int(tickets_row.resolvidos_30d or 0)

        # --- Tempo medio de resolucao (em horas) ---
        tempo_medio_result = await db.execute(
            select(
                func.avg(
                    extract(
                        "epoch",
                        ClientTicket.closed_at - ClientTicket.created_at,
                    )
                ).label("avg_seconds")
            ).where(
                ClientTicket.client_id == client_id,
                ClientTicket.status == TicketStatus.FECHADO,
                ClientTicket.closed_at.isnot(None),
            )
        )
        avg_seconds = tempo_medio_result.scalar()
        tempo_medio_horas = round((float(avg_seconds) / 3600), 1) if avg_seconds else 0.0

        # --- Conformidade para health score ---
        conformidade_pct = 0
        if kits_total > 0:
            conformidade_pct = round((kits_aprovados / kits_total) * 100)

        chamados_resolucao_pct = 0
        total_tickets_result = await db.execute(select(func.count()).where(ClientTicket.client_id == client_id))
        total_tickets = int(total_tickets_result.scalar() or 0)
        if total_tickets > 0:
            fechados_result = await db.execute(
                select(func.count()).where(
                    ClientTicket.client_id == client_id,
                    ClientTicket.status == TicketStatus.FECHADO,
                )
            )
            fechados = int(fechados_result.scalar() or 0)
            chamados_resolucao_pct = round((fechados / total_tickets) * 100)

        health_score = round(conformidade_pct * 0.6 + chamados_resolucao_pct * 0.4)

        # --- Proxima geracao de kit ---
        today = date.today()
        if today.month == 12:
            proxima_geracao = date(today.year + 1, 1, 1)
        else:
            proxima_geracao = date(today.year, today.month + 1, 1)

        return {
            "kits_total": kits_total,
            "kits_aprovados": kits_aprovados,
            "kits_pendentes": kits_pendentes,
            "chamados_abertos": chamados_abertos,
            "chamados_resolvidos_30d": chamados_resolvidos_30d,
            "tempo_medio_resolucao_horas": tempo_medio_horas,
            "documentos_total": docs_total,
            "documentos_baixados": docs_assinados,
            "health_score": min(100, max(0, health_score)),
            "proxima_geracao_kit": proxima_geracao.isoformat(),
        }

    except Exception as exc:
        logger.error("Erro ao calcular overview analytics: %s", exc)
        return {
            "kits_total": 0,
            "kits_aprovados": 0,
            "kits_pendentes": 0,
            "chamados_abertos": 0,
            "chamados_resolvidos_30d": 0,
            "tempo_medio_resolucao_horas": 0.0,
            "documentos_total": 0,
            "documentos_baixados": 0,
            "health_score": 0,
            "proxima_geracao_kit": date.today().isoformat(),
        }


@router.get("/kits-history")
async def get_kits_history(
    client_id: str = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db),
    months: int = Query(6, ge=1, le=24, description="Quantos meses de historico retornar"),
) -> Any:
    """Retorna historico mensal de kits documentais.

    Retorna os ultimos N meses de kits, util para graficos de barra.
    """
    try:
        result = await db.execute(
            select(
                GedDocumentKit.reference_month,
                GedDocumentKit.status,
                GedDocumentKit.total_documents,
                GedDocumentKit.completion_percentage,
            )
            .where(GedDocumentKit.client_id == client_id)
            .order_by(GedDocumentKit.reference_month.desc())
            .limit(months)
        )
        rows = result.all()

        history = []
        for row in reversed(rows):
            ref_month = row.reference_month
            month_str = f"{ref_month.year}-{ref_month.month:02d}"
            history.append(
                {
                    "month": month_str,
                    "status": row.status,
                    "documents": int(row.total_documents or 0),
                    "completion_pct": float(row.completion_percentage or 0),
                }
            )

        return history

    except Exception as exc:
        logger.error("Erro ao buscar historico de kits: %s", exc)
        return []


@router.get("/tickets-history")
async def get_tickets_history(
    client_id: str = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db),
    months: int = Query(6, ge=1, le=24, description="Quantos meses de historico retornar"),
) -> Any:
    """Retorna historico mensal de chamados.

    Agrupa chamados por mes com contadores de abertos, resolvidos
    e tempo medio de resolucao.
    """
    try:
        result = await db.execute(
            select(
                extract("year", ClientTicket.created_at).label("year"),
                extract("month", ClientTicket.created_at).label("month"),
                func.count().label("abertos"),
                func.count(case((ClientTicket.status == TicketStatus.FECHADO, 1))).label("resolvidos"),
                func.avg(
                    case(
                        (
                            ClientTicket.closed_at.isnot(None),
                            extract(
                                "epoch",
                                ClientTicket.closed_at - ClientTicket.created_at,
                            ),
                        )
                    )
                ).label("avg_seconds"),
            )
            .where(ClientTicket.client_id == client_id)
            .group_by(
                extract("year", ClientTicket.created_at),
                extract("month", ClientTicket.created_at),
            )
            .order_by(
                extract("year", ClientTicket.created_at).desc(),
                extract("month", ClientTicket.created_at).desc(),
            )
            .limit(months)
        )
        rows = result.all()

        history = []
        for row in reversed(rows):
            year = int(row.year)
            month = int(row.month)
            avg_h = round(float(row.avg_seconds) / 3600, 1) if row.avg_seconds else 0.0
            history.append(
                {
                    "month": f"{year}-{month:02d}",
                    "abertos": int(row.abertos or 0),
                    "resolvidos": int(row.resolvidos or 0),
                    "tempo_medio_h": avg_h,
                }
            )

        return history

    except Exception as exc:
        logger.error("Erro ao buscar historico de tickets: %s", exc)
        return []


@router.get("/conformidade")
async def get_conformidade(
    client_id: str = Depends(get_current_portal_client),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna status de conformidade documental do cliente.

    Verifica certidoes negativas nos kits mais recentes e calcula
    o compliance score geral.
    """
    try:
        # Buscar o kit mais recente aprovado ou enviado para extrair certidoes
        kit_result = await db.execute(
            select(GedDocumentKit.id)
            .where(
                GedDocumentKit.client_id == client_id,
                GedDocumentKit.status.in_(
                    [KitStatus.APROVADO, KitStatus.CONFERIDO, KitStatus.ENVIADO, KitStatus.COMPLETO]
                ),
            )
            .order_by(GedDocumentKit.reference_month.desc())
            .limit(1)
        )
        kit_id = kit_result.scalar_one_or_none()

        certidoes = []
        docs_em_dia = 0
        docs_pendentes = 0

        if kit_id:
            # Buscar documentos de certidoes no kit mais recente
            docs_result = await db.execute(
                select(
                    KitDocument.document_type,
                    KitDocument.document_name,
                    KitDocument.is_signed,
                    KitDocument.created_at,
                ).where(
                    KitDocument.kit_id == str(kit_id),
                    KitDocument.document_type.in_([dt.value for dt, _ in CERTIDOES_TYPES]),
                )
            )
            docs = docs_result.all()

            docs_por_tipo: dict[str, Any] = {doc.document_type: doc for doc in docs}

            # [Veracidade] validade REAL das certidoes vem de ged_certidoes.expiry_date — NAO simular.
            _map_ged = {
                DocumentType.CND_FEDERAL: "certidao_negativa_federal",
                DocumentType.CND_ESTADUAL: "certidao_negativa_estadual",
                DocumentType.CND_MUNICIPAL: "certidao_negativa_municipal",
                DocumentType.CRF_FGTS: "certidao_negativa_fgts",
                DocumentType.CNDT_TRABALHISTA: "certidao_negativa_trabalhista",
            }
            _cert_rows = (await db.execute(text("SELECT document_type, expiry_date FROM ged_certidoes"))).all()
            _validade_real = {r[0]: r[1] for r in _cert_rows}
            _hoje = date.today()

            for doc_type, display_name in CERTIDOES_TYPES:
                doc = docs_por_tipo.get(doc_type.value)
                expiry = _validade_real.get(_map_ged.get(doc_type))
                if expiry:
                    # validade REAL cadastrada
                    if expiry < _hoje:
                        status = "vencida"
                    elif expiry <= _hoje + timedelta(days=30):
                        status = "vencendo"
                    else:
                        status = "ok"
                    expires_at = expiry
                    if status == "ok":
                        docs_em_dia += 1
                    else:
                        docs_pendentes += 1
                elif doc:
                    # presente no kit, mas sem validade cadastrada — honesto, sem data inventada
                    status = "presente" if doc.is_signed else "pendente"
                    expires_at = None
                    if doc.is_signed:
                        docs_em_dia += 1
                    else:
                        docs_pendentes += 1
                else:
                    status = "vencida"
                    expires_at = None
                    docs_pendentes += 1

                certidoes.append(
                    {
                        "name": display_name,
                        "status": status,
                        "expires_at": expires_at.isoformat() if expires_at else None,
                    }
                )
        else:
            # Sem kit encontrado — todas as certidoes como pendentes
            for _, display_name in CERTIDOES_TYPES:
                certidoes.append(
                    {
                        "name": display_name,
                        "status": "vencida",
                        "expires_at": None,
                    }
                )
                docs_pendentes += 1

        total_certidoes = len(CERTIDOES_TYPES)
        compliance_score = round((docs_em_dia / total_certidoes) * 100) if total_certidoes > 0 else 0

        return {
            "certidoes": certidoes,
            "compliance_score": compliance_score,
            "documentos_em_dia": docs_em_dia,
            "documentos_pendentes": docs_pendentes,
        }

    except Exception as exc:
        logger.error("Erro ao calcular conformidade: %s", exc)
        return {
            "certidoes": [{"name": name, "status": "vencida", "expires_at": None} for _, name in CERTIDOES_TYPES],
            "compliance_score": 0,
            "documentos_em_dia": 0,
            "documentos_pendentes": len(CERTIDOES_TYPES),
        }
