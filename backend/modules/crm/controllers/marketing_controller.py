"""
Marketing Controller — Campanhas, leads de marketing e conversão para CRM.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_async_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/marketing", tags=["Marketing"])


class CampaignCreate(BaseModel):
    name: str
    type: str = "organic"
    budget: float = 0
    description: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None


class MktLeadCreate(BaseModel):
    campaign_id: str | None = None
    name: str
    email: str | None = None
    phone: str | None = None
    whatsapp: str | None = None
    source: str | None = None


# === CAMPAIGNS ===


@router.get("/campaigns/")
async def listar_campanhas(current_user: CurrentActiveUser, db: AsyncSession = Depends(get_async_session)):
    result = await db.execute(
        text("""
        SELECT mc.*, (SELECT COUNT(*) FROM marketing_leads ml WHERE ml.campaign_id = mc.id) as total_leads,
               (SELECT COUNT(*) FROM marketing_leads ml WHERE ml.campaign_id = mc.id AND ml.status = 'converted') as converted
        FROM marketing_campaigns mc ORDER BY mc.created_at DESC
    """)
    )
    rows = result.fetchall()
    return {
        "items": [
            {
                "id": str(r.id),
                "name": r.name,
                "type": r.type,
                "status": r.status,
                "budget": float(r.budget) if r.budget else 0,
                "spent": float(r.spent) if r.spent else 0,
                "start_date": str(r.start_date) if r.start_date else None,
                "end_date": str(r.end_date) if r.end_date else None,
                "description": r.description,
                "total_leads": r.total_leads,
                "converted": r.converted,
                "roi": round((r.converted / max(r.total_leads, 1)) * 100, 1),
            }
            for r in rows
        ],
        "total": len(rows),
    }


@router.post("/campaigns/", status_code=201)
async def criar_campanha(
    data: CampaignCreate, current_user: CurrentActiveUser, db: AsyncSession = Depends(get_async_session)
):
    result = await db.execute(
        text("""
        INSERT INTO marketing_campaigns (name, type, budget, description, start_date, end_date, utm_source, utm_medium, utm_campaign)
        VALUES (:name, :type, :budget, :desc, :start, :end, :utm_s, :utm_m, :utm_c) RETURNING id
    """),
        {
            "name": data.name,
            "type": data.type,
            "budget": data.budget,
            "desc": data.description,
            "start": data.start_date,
            "end": data.end_date,
            "utm_s": data.utm_source,
            "utm_m": data.utm_medium,
            "utm_c": data.utm_campaign,
        },
    )
    await db.commit()
    return {"id": str(result.fetchone()[0]), "message": "Campanha criada"}


@router.put("/campaigns/{campaign_id}")
@router.patch("/campaigns/{campaign_id}")
async def atualizar_campanha(
    campaign_id: str,
    data: dict,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_async_session),
):
    """Atualiza campanha (parcial). Aceita {status} sozinho (botão Ativar) ou campos completos."""
    m = {
        "name": data.get("name"),
        "type": data.get("type"),
        "budget": data.get("budget"),
        "desc": data.get("description"),
        "start": data.get("start_date"),
        "end": data.get("end_date"),
        "utm_s": data.get("utm_source"),
        "utm_m": data.get("utm_medium"),
        "utm_c": data.get("utm_campaign"),
        "status": data.get("status"),
    }
    cols = {
        "name": "name",
        "type": "type",
        "budget": "budget",
        "desc": "description",
        "start": "start_date",
        "end": "end_date",
        "utm_s": "utm_source",
        "utm_m": "utm_medium",
        "utm_c": "utm_campaign",
        "status": "status",
    }
    sets = ", ".join(f"{cols[k]} = COALESCE(:{k}, {cols[k]})" for k in m)
    await db.execute(
        text(f"UPDATE marketing_campaigns SET {sets}, updated_at=NOW() WHERE id = :id"),
        {**m, "id": campaign_id},
    )
    await db.commit()
    return {"message": "Campanha atualizada", "id": campaign_id}


@router.delete("/campaigns/{campaign_id}", status_code=204)
async def excluir_campanha(
    campaign_id: str,
    current_user: CurrentActiveUser,  # noqa: ARG001
    db: AsyncSession = Depends(get_async_session),
):
    """Exclui uma campanha (ex.: campanhas de teste)."""
    await db.execute(text("DELETE FROM marketing_campaigns WHERE id = :id"), {"id": campaign_id})
    await db.commit()


# === MARKETING LEADS ===


@router.get("/leads/")
async def listar_mkt_leads(
    current_user: CurrentActiveUser,
    campaign_id: str | None = Query(None),
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_async_session),
):
    where_clauses = []
    if campaign_id:
        where_clauses.append(f"ml.campaign_id = '{campaign_id}'")
    if status:
        where_clauses.append(f"ml.status = '{status}'")
    where = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    result = await db.execute(
        text(f"""
        SELECT ml.*, mc.name as campaign_name
        FROM marketing_leads ml
        LEFT JOIN marketing_campaigns mc ON ml.campaign_id = mc.id
        {where}
        ORDER BY ml.created_at DESC
    """)
    )
    rows = result.fetchall()
    return {
        "items": [
            {
                "id": str(r.id),
                "name": r.name,
                "email": r.email,
                "phone": r.phone,
                "whatsapp": r.whatsapp,
                "source": r.source,
                "status": r.status,
                "campaign_name": r.campaign_name,
                "crm_lead_id": str(r.crm_lead_id) if r.crm_lead_id else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "total": len(rows),
    }


@router.post("/leads/", status_code=201)
async def criar_mkt_lead(
    data: MktLeadCreate, current_user: CurrentActiveUser, db: AsyncSession = Depends(get_async_session)
):
    result = await db.execute(
        text("""
        INSERT INTO marketing_leads (campaign_id, name, email, phone, whatsapp, source)
        VALUES (:cid, :name, :email, :phone, :whatsapp, :source) RETURNING id
    """),
        {
            "cid": data.campaign_id,
            "name": data.name,
            "email": data.email,
            "phone": data.phone,
            "whatsapp": data.whatsapp,
            "source": data.source,
        },
    )
    await db.commit()
    return {"id": str(result.fetchone()[0]), "message": "Lead marketing criado"}


@router.post("/leads/{lead_id}/convert", status_code=201)
async def converter_lead_para_crm(
    lead_id: str, current_user: CurrentActiveUser, db: AsyncSession = Depends(get_async_session)
):
    """Converte lead de marketing em lead CRM — fecha o ciclo campanha→CRM."""
    # Buscar lead marketing
    ml = await db.execute(text("SELECT * FROM marketing_leads WHERE id = :id"), {"id": lead_id})
    mkt_lead = ml.fetchone()
    if not mkt_lead:
        raise HTTPException(status_code=404, detail="Lead marketing nao encontrado")

    if mkt_lead.status == "converted":
        return {"message": "Lead ja convertido", "crm_lead_id": str(mkt_lead.crm_lead_id)}

    # Buscar campanha para source
    campaign_name = "marketing"
    if mkt_lead.campaign_id:
        camp = await db.execute(
            text("SELECT name FROM marketing_campaigns WHERE id = :id"), {"id": str(mkt_lead.campaign_id)}
        )
        cr = camp.fetchone()
        if cr:
            campaign_name = cr[0]

    # Criar lead no CRM
    crm_result = await db.execute(
        text("""
        INSERT INTO leads (id, name, email, phone, company, source, status, score, probability, expected_value, is_active, created_at, updated_at)
        VALUES (gen_random_uuid(), :name, :email, :phone, :name, :source, 'new', 50, 0.3, 0, true, NOW(), NOW()) RETURNING id
    """),
        {
            "name": mkt_lead.name,
            "email": mkt_lead.email or f"{mkt_lead.name.lower().replace(' ', '.')}@lead.conecta",
            "phone": mkt_lead.phone,
            "source": f"campanha_{campaign_name}",
        },
    )
    crm_lead_id = str(crm_result.fetchone()[0])

    # Atualizar marketing lead
    await db.execute(
        text("""
        UPDATE marketing_leads SET status = 'converted', crm_lead_id = :crm_id, updated_at = NOW()
        WHERE id = :id
    """),
        {"crm_id": crm_lead_id, "id": lead_id},
    )

    await db.commit()

    return {
        "message": "Lead convertido para CRM",
        "crm_lead_id": crm_lead_id,
        "campanha": campaign_name,
    }


@router.get("/leads/stats")
async def stats_mkt_leads(current_user: CurrentActiveUser, db: AsyncSession = Depends(get_async_session)):
    """Estatísticas de leads por campanha."""
    result = await db.execute(
        text("""
        SELECT
            mc.name as campanha,
            COUNT(ml.id) as total,
            COUNT(*) FILTER (WHERE ml.status = 'new') as novos,
            COUNT(*) FILTER (WHERE ml.status = 'contacted') as contactados,
            COUNT(*) FILTER (WHERE ml.status = 'qualified') as qualificados,
            COUNT(*) FILTER (WHERE ml.status = 'converted') as convertidos,
            COUNT(*) FILTER (WHERE ml.status = 'lost') as perdidos,
            ROUND(COUNT(*) FILTER (WHERE ml.status = 'converted')::numeric / NULLIF(COUNT(ml.id), 0) * 100, 1) as taxa_conversao
        FROM marketing_campaigns mc
        LEFT JOIN marketing_leads ml ON ml.campaign_id = mc.id
        GROUP BY mc.id, mc.name
        ORDER BY total DESC
    """)
    )
    rows = result.fetchall()
    return {
        "campanhas": [
            {
                "campanha": r[0],
                "total": r[1],
                "novos": r[2],
                "contactados": r[3],
                "qualificados": r[4],
                "convertidos": r[5],
                "perdidos": r[6],
                "taxa_conversao": float(r[7]) if r[7] else 0,
            }
            for r in rows
        ],
        "gerado_em": datetime.now().isoformat(),
    }


# === INTERLIGAÇÃO LICITAÇÕES → CRM ===


class LicitacaoConvertRequest(BaseModel):
    orgao: str
    objeto: str
    valor: float = 0
    numero_edital: str | None = None


@router.post("/licitacao/convert-to-crm", status_code=201)
async def converter_licitacao_para_crm(
    data: LicitacaoConvertRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_async_session),
):
    """Converte licitação vencida em lead CRM — fecha ciclo licitação→CRM."""
    crm_result = await db.execute(
        text("""
        INSERT INTO leads (id, name, email, phone, company, source, status, score, probability, expected_value, is_active, created_at, updated_at)
        VALUES (gen_random_uuid(), :name, :email, '', :company, 'licitacao', 'qualified', 70, 0.6, :value, true, NOW(), NOW()) RETURNING id
    """),
        {
            "name": data.orgao,
            "email": f"licitacao.{data.numero_edital or 'novo'}@lead.conecta",
            "company": data.orgao,
            "value": data.valor,
        },
    )
    crm_lead_id = str(crm_result.fetchone()[0])
    await db.commit()

    return {
        "message": "Licitação vencida convertida em lead CRM",
        "crm_lead_id": crm_lead_id,
        "orgao": data.orgao,
        "valor": data.valor,
    }


# === FUNIL REAL (dados reais: leads -> qualificados -> clientes -> MRR) ===

# Status de lead que contam como "qualificado ou além" no funil.
_QUALIFIED_PLUS = "('qualified','proposal','negotiation','won')"


@router.get("/funil")
async def funil_real(current_user: CurrentActiveUser, db: AsyncSession = Depends(get_async_session)):
    """Funil de vendas com dados REAIS: leads (por origem) -> qualificados -> clientes -> MRR."""
    # 1) Funil de leads (total / qualificados / ganhos)
    lead_row = (
        await db.execute(
            text(
                f"""
        SELECT
          count(*) AS leads_total,
          count(*) FILTER (WHERE status IN {_QUALIFIED_PLUS}
                           OR (qualificacao IS NOT NULL AND qualificacao::text <> '{{}}')) AS qualificados,
          count(*) FILTER (WHERE status = 'won') AS ganhos
        FROM leads WHERE is_active
        """
            )
        )
    ).fetchone()

    # 2) Clientes + MRR + quantos vieram de lead
    cli_row = (
        await db.execute(
            text(
                """
        SELECT
          count(*) FILTER (WHERE c.ativo) AS clientes_ativos,
          count(*) FILTER (WHERE c.ativo AND c.lead_id IS NOT NULL) AS clientes_de_lead,
          COALESCE(SUM(
            (SELECT SUM(cc.monthly_value) FROM client_contracts cc
             WHERE cc.client_id = c.id AND cc.status = 'active')
          ), 0) AS mrr_total
        FROM clients c
        """
            )
        )
    ).fetchone()

    # 3) Quebra por origem (leads por source + clientes/MRR atribuídos àquela origem)
    origem_rows = (
        await db.execute(
            text(
                f"""
        WITH leads_src AS (
          SELECT source,
                 count(*) AS leads,
                 count(*) FILTER (WHERE status IN {_QUALIFIED_PLUS}
                                  OR (qualificacao IS NOT NULL AND qualificacao::text <> '{{}}')) AS qualificados
          FROM leads WHERE is_active GROUP BY source
        ),
        cli_src AS (
          SELECT COALESCE(l.source, 'direto') AS source,
                 count(*) AS clientes,
                 COALESCE(SUM(
                   (SELECT SUM(cc.monthly_value) FROM client_contracts cc
                    WHERE cc.client_id = c.id AND cc.status = 'active')
                 ), 0) AS mrr
          FROM clients c LEFT JOIN leads l ON c.lead_id = l.id
          WHERE c.ativo GROUP BY COALESCE(l.source, 'direto')
        )
        SELECT COALESCE(ls.source, cs.source) AS origem,
               COALESCE(ls.leads, 0) AS leads,
               COALESCE(ls.qualificados, 0) AS qualificados,
               COALESCE(cs.clientes, 0) AS clientes,
               COALESCE(cs.mrr, 0) AS mrr
        FROM leads_src ls FULL OUTER JOIN cli_src cs ON ls.source = cs.source
        ORDER BY leads DESC, clientes DESC
        """
            )
        )
    ).fetchall()

    leads_total = lead_row.leads_total or 0
    qualificados = lead_row.qualificados or 0
    clientes_ativos = cli_row.clientes_ativos or 0
    clientes_de_lead = cli_row.clientes_de_lead or 0

    def _pct(num, den):
        return round((num / den) * 100, 1) if den else 0.0

    por_origem = []
    for r in origem_rows:
        por_origem.append(
            {
                "origem": r.origem,
                "leads": r.leads,
                "qualificados": r.qualificados,
                "clientes": r.clientes,
                "mrr": float(r.mrr or 0),
                "conversao": _pct(r.clientes, r.leads),
            }
        )

    return {
        "funil": [
            {"stage": "Leads", "value": leads_total},
            {"stage": "Qualificados", "value": qualificados},
            {"stage": "Convertidos (de lead)", "value": clientes_de_lead},
            {"stage": "Clientes ativos", "value": clientes_ativos},
        ],
        "por_origem": por_origem,
        "totais": {
            "leads": leads_total,
            "qualificados": qualificados,
            "clientes_ativos": clientes_ativos,
            "clientes_de_lead": clientes_de_lead,
            "mrr_total": float(cli_row.mrr_total or 0),
            "taxa_lead_qualificado": _pct(qualificados, leads_total),
            "taxa_lead_cliente": _pct(clientes_de_lead, leads_total),
        },
        "gerado_em": datetime.now().isoformat(),
    }


# === COPYWRITER AGENT (Conecta Marketing AI — F2) ===


class CopywriterRequest(BaseModel):
    formato: str
    briefing: str
    objetivo: str | None = None
    publico: str | None = None
    n_variacoes: int = 3


@router.get("/copywriter/formats")
async def listar_formatos_copywriter(current_user: CurrentActiveUser):
    """Lista os formatos de conteúdo que o agente copywriter sabe gerar."""
    from modules.crm.services.copywriter_agent import formatos_suportados

    return {"formatos": formatos_suportados()}


@router.post("/copywriter/generate")
async def gerar_conteudo_copywriter(
    data: CopywriterRequest,
    current_user: CurrentActiveUser,
):
    """
    Gera RASCUNHOS de conteúdo na voz da marca (human-in-the-loop — não publica).
    Retorna variações para revisão/aprovação humana.
    """
    from modules.crm.services.copywriter_agent import gerar_copy

    try:
        result = await gerar_copy(
            formato=data.formato,
            briefing=data.briefing,
            objetivo=data.objetivo,
            publico=data.publico,
            n_variacoes=data.n_variacoes,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("copywriter: erro ao gerar conteúdo")
        raise HTTPException(status_code=500, detail=f"Erro ao gerar conteúdo: {e}") from e

    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("erro", "Formato inválido"))
    return result


# === ESTRATEGISTA AGENT (Conecta Marketing AI — F2) ===


class EstrategistaRequest(BaseModel):
    objetivo: str
    periodo_dias: int = 30
    orcamento: str | None = None
    canais_preferidos: str | None = None


@router.post("/estrategista/plan")
async def gerar_plano_estrategista(
    data: EstrategistaRequest,
    current_user: CurrentActiveUser,
):
    """Gera um plano de campanha + calendário editorial a partir de um objetivo (rascunho)."""
    from modules.crm.services.estrategista_agent import gerar_plano

    try:
        return await gerar_plano(
            objetivo=data.objetivo,
            periodo_dias=data.periodo_dias,
            orcamento=data.orcamento,
            canais_preferidos=data.canais_preferidos,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("estrategista: erro ao gerar plano")
        raise HTTPException(status_code=500, detail=f"Erro ao gerar plano: {e}") from e


# === BIBLIOTECA DE CONTEÚDO (rascunhos aprovados — F2+) ===


class ContentSaveRequest(BaseModel):
    formato: str
    formato_label: str | None = None
    titulo: str | None = None
    conteudo: str
    observacao: str | None = None
    briefing: str | None = None
    objetivo: str | None = None
    publico: str | None = None
    modelo: str | None = None
    status: str = "aprovado"  # ao salvar da tela de revisão, já entra aprovado


class ContentStatusRequest(BaseModel):
    status: str


def _content_to_dict(c) -> dict:
    return {
        "id": str(c.id),
        "formato": c.formato,
        "formato_label": c.formato_label,
        "titulo": c.titulo,
        "conteudo": c.conteudo,
        "observacao": c.observacao,
        "briefing": c.briefing,
        "objetivo": c.objetivo,
        "publico": c.publico,
        "modelo": c.modelo,
        "status": c.status,
        "approved_at": c.approved_at.isoformat() if c.approved_at else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


@router.post("/content/", status_code=201)
async def salvar_conteudo(
    data: ContentSaveRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_async_session),
):
    """Salva uma peça na biblioteca (default: aprovada)."""
    from modules.crm.models.marketing_content import ContentStatus, MarketingContentDraft

    status = data.status if data.status in (s.value for s in ContentStatus) else ContentStatus.APROVADO.value
    item = MarketingContentDraft(
        formato=data.formato,
        formato_label=data.formato_label,
        titulo=data.titulo,
        conteudo=data.conteudo,
        observacao=data.observacao,
        briefing=data.briefing,
        objetivo=data.objetivo,
        publico=data.publico,
        modelo=data.modelo,
        status=status,
        created_by_id=getattr(current_user, "id", None),
        approved_at=datetime.utcnow() if status == ContentStatus.APROVADO.value else None,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return _content_to_dict(item)


@router.get("/content/")
async def listar_conteudo(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_async_session),
    status: str | None = Query(None),
    formato: str | None = Query(None),
):
    """Lista peças da biblioteca, filtrando por status e/ou formato."""
    from sqlalchemy import select

    from modules.crm.models.marketing_content import MarketingContentDraft

    stmt = select(MarketingContentDraft)
    if status:
        stmt = stmt.where(MarketingContentDraft.status == status)
    if formato:
        stmt = stmt.where(MarketingContentDraft.formato == formato)
    stmt = stmt.order_by(MarketingContentDraft.created_at.desc())
    rows = (await db.execute(stmt)).scalars().all()
    return {"items": [_content_to_dict(c) for c in rows], "total": len(rows)}


class ContentEditRequest(BaseModel):
    titulo: str | None = None
    conteudo: str | None = None
    observacao: str | None = None


@router.patch("/content/{content_id}")
async def editar_conteudo(
    content_id: str,
    data: ContentEditRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_async_session),
):
    """Edita o texto de uma peça da biblioteca (título/conteúdo/observação)."""
    from modules.crm.models.marketing_content import MarketingContentDraft

    item = await db.get(MarketingContentDraft, content_id)
    if not item:
        raise HTTPException(status_code=404, detail="Peça não encontrada")
    if data.titulo is not None:
        item.titulo = data.titulo
    if data.conteudo is not None:
        if not data.conteudo.strip():
            raise HTTPException(status_code=400, detail="Conteúdo não pode ficar vazio")
        item.conteudo = data.conteudo
    if data.observacao is not None:
        item.observacao = data.observacao
    await db.commit()
    await db.refresh(item)
    return _content_to_dict(item)


class ContentSendWhatsappRequest(BaseModel):
    numero: str


@router.post("/content/{content_id}/send-whatsapp")
async def enviar_conteudo_whatsapp(
    content_id: str,
    data: ContentSendWhatsappRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_async_session),
):
    """Envia uma peça da biblioteca para um número de WhatsApp (via Baileys).
    Human-in-the-loop: você escolhe o destino e dispara o envio (1 a 1)."""
    import re as _re

    from modules.crm.models.marketing_content import MarketingContentDraft

    item = await db.get(MarketingContentDraft, content_id)
    if not item:
        raise HTTPException(status_code=404, detail="Peça não encontrada")

    digits = _re.sub(r"\D", "", data.numero or "")
    if len(digits) < 10:
        raise HTTPException(status_code=400, detail="Número inválido (use DDI+DDD+número, ex: 5592...).")

    # Lazy import: evita acoplar o agent_service do José Luís no carregamento do módulo.
    from modules.integrations.connectors.whatsapp.agent_service import _enviar_whatsapp_direto

    ok = await _enviar_whatsapp_direto(digits, item.conteudo)
    if not ok:
        raise HTTPException(status_code=502, detail="Falha ao enviar pelo WhatsApp (Baileys). Tente novamente.")
    return {"ok": True, "enviado": True, "numero": digits, "content_id": content_id}


@router.patch("/content/{content_id}/status")
async def atualizar_status_conteudo(
    content_id: str,
    data: ContentStatusRequest,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_async_session),
):
    """Aprova/arquiva/volta a rascunho uma peça."""
    from modules.crm.models.marketing_content import ContentStatus, MarketingContentDraft

    if data.status not in (s.value for s in ContentStatus):
        raise HTTPException(status_code=400, detail="Status inválido")
    item = await db.get(MarketingContentDraft, content_id)
    if not item:
        raise HTTPException(status_code=404, detail="Peça não encontrada")
    item.status = data.status
    if data.status == ContentStatus.APROVADO.value and not item.approved_at:
        item.approved_at = datetime.utcnow()
    await db.commit()
    await db.refresh(item)
    return _content_to_dict(item)


@router.delete("/content/{content_id}", status_code=204)
async def excluir_conteudo(
    content_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_async_session),
):
    """Exclui uma peça da biblioteca."""
    from modules.crm.models.marketing_content import MarketingContentDraft

    item = await db.get(MarketingContentDraft, content_id)
    if item:
        await db.delete(item)
        await db.commit()
    return None
