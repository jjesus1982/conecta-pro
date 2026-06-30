"""
Pipeline Sync — liga o fluxo de PROPOSTA ao PIPELINE (opportunities/deals).

Toda proposta passa a ter uma Oportunidade (deal) ligada, que avança de estágio
no Kanban conforme o status da proposta. Idempotente e best-effort: NUNCA quebra
o fluxo da proposta (segue o mesmo padrão de _try_generate_commission).
"""

from __future__ import annotations

import logging
import re
from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Status da proposta -> estágio do deal (valores de OpportunityStage).
_STATUS_TO_STAGE: dict[str, str] = {
    "draft": "proposal",
    "pending_review": "proposal",
    "pending_approval": "proposal",
    "approved": "proposal",
    "sent": "negotiation",
    "viewed": "negotiation",
    "accepted": "closed_won",
    "rejected": "closed_lost",
    "expired": "closed_lost",
    "cancelled": "closed_lost",
}

# Probabilidade ponderada por estágio (alimenta o weighted_value/forecast do Kanban).
_STAGE_PROB: dict[str, int] = {
    "qualification": 20,
    "needs_analysis": 40,
    "proposal": 60,
    "negotiation": 80,
    "closed_won": 100,
    "closed_lost": 0,
}


# Status do LEAD -> estágio do deal. new/contacted não viram deal (ainda não qualificados).
_LEAD_STATUS_TO_STAGE: dict[str, str] = {
    "qualified": "qualification",
    "proposal": "proposal",
    "negotiation": "negotiation",
    "won": "closed_won",
    "lost": "closed_lost",
}
# Status que JUSTIFICAM criar um deal (lost só atualiza um deal existente, não cria do nada).
_LEAD_CREATE_STATUSES = {"qualified", "proposal", "negotiation", "won"}


def stage_for_proposal_status(status: str | None) -> str:
    return _STATUS_TO_STAGE.get((status or "").lower(), "proposal")


async def ensure_opportunity_for_lead(db: AsyncSession, lead) -> str | None:
    """Lead qualificado -> deal no pipeline. Idempotente (1 deal por lead_id) e best-effort.
    new/contacted não criam deal; lost só move um deal existente p/ Perdido."""
    try:
        from sqlalchemy import select

        from modules.crm.models.opportunity import Opportunity

        if getattr(lead, "is_active", True) is False:
            return None
        status = (getattr(lead, "status", "") or "").lower()
        stage = _LEAD_STATUS_TO_STAGE.get(status)
        if not stage:
            return None  # new/contacted -> ainda não é deal

        # Dedup: já existe deal ativo p/ este lead?
        existing = (
            (
                await db.execute(
                    select(Opportunity).where(Opportunity.lead_id == str(lead.id), Opportunity.is_active.is_(True))
                )
            )
            .scalars()
            .first()
        )
        if existing:
            existing.stage = stage
            existing.probability = _STAGE_PROB.get(stage, existing.probability)
            if stage in ("closed_won", "closed_lost") and not existing.actual_close_date:
                existing.actual_close_date = date.today()
            await db.commit()
            return str(existing.id)

        if status not in _LEAD_CREATE_STATUSES:
            return None  # lost sem deal prévio -> não cria

        nome = getattr(lead, "name", None) or "Lead"
        opp = Opportunity(
            id=str(uuid4()),
            title=str(nome)[:255],
            lead_id=str(lead.id),
            contact_name=str(nome)[:255],
            contact_email=(getattr(lead, "email", None) or f"sem-email-lead-{lead.id}@conectamais.pro")[:255],
            contact_phone=getattr(lead, "phone", None),
            company_name=getattr(lead, "company", None) or str(nome),
            stage=stage,
            priority="medium",
            value=float(getattr(lead, "expected_value", 0) or 0),
            probability=_STAGE_PROB.get(stage, 20),
            owner_id=getattr(lead, "assigned_to_id", None),
            is_active=True,
            notes=f"Gerada automaticamente do lead qualificado ({nome})",
        )
        if stage in ("closed_won", "closed_lost"):
            opp.actual_close_date = date.today()
        db.add(opp)
        await db.flush()
        await db.commit()
        logger.info("Pipeline: oportunidade %s criada do lead %s (stage=%s)", opp.id, lead.id, stage)
        return str(opp.id)
    except Exception as exc:  # noqa: BLE001 — pipeline nunca quebra o fluxo do lead
        logger.warning("Pipeline lead->deal falhou p/ lead %s: %s", getattr(lead, "id", "?"), exc)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None


async def sync_opportunity_for_proposal(db: AsyncSession, proposal) -> str | None:
    """Garante (idempotente) uma oportunidade ligada à proposta e ajusta o estágio conforme o
    status atual da proposta. Best-effort: qualquer falha só loga warning, não quebra a proposta."""
    try:
        from modules.crm.models.opportunity import Opportunity

        # Proposta inativa/excluída (soft-delete) não gera nem mantém deal.
        if getattr(proposal, "is_active", True) is False:
            return None

        stage = stage_for_proposal_status(getattr(proposal, "status", None))
        prob = _STAGE_PROB.get(stage, 60)
        valor = float(getattr(proposal, "total", 0) or 0)
        numero = getattr(proposal, "number", "") or ""

        opp_id = getattr(proposal, "opportunity_id", None)
        if opp_id:
            opp = await db.get(Opportunity, opp_id)
            if opp:
                opp.stage = stage
                opp.probability = prob
                if valor > 0:
                    opp.value = valor
                if stage in ("closed_won", "closed_lost") and not opp.actual_close_date:
                    opp.actual_close_date = date.today()
                await db.commit()
                return str(opp.id)
            # opportunity_id órfão -> recria abaixo

        opp = Opportunity(
            id=str(uuid4()),
            title=(getattr(proposal, "title", None) or f"Proposta {numero}")[:255],
            contact_name=(
                getattr(proposal, "client_company", None) or getattr(proposal, "client_name", None) or "Cliente"
            )[:255],
            contact_email=(getattr(proposal, "client_email", None) or f"sem-email-{numero or 'x'}@conectamais.pro")[
                :255
            ],
            company_name=getattr(proposal, "client_name", None),
            stage=stage,
            priority="medium",
            value=valor,
            probability=prob,
            owner_id=getattr(proposal, "created_by_id", None),
            is_active=True,
            notes=f"Gerada automaticamente da proposta {numero}",
        )
        if stage in ("closed_won", "closed_lost"):
            opp.actual_close_date = date.today()
        db.add(opp)
        await db.flush()
        proposal.opportunity_id = str(opp.id)
        await db.commit()
        logger.info("Pipeline: oportunidade %s ligada à proposta %s (stage=%s)", opp.id, numero, stage)
        return str(opp.id)
    except Exception as exc:  # noqa: BLE001 — pipeline nunca pode quebrar a proposta
        logger.warning("Pipeline sync falhou p/ proposta %s: %s", getattr(proposal, "number", "?"), exc)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None


async def ensure_contract_for_proposal(db: AsyncSession, proposal) -> str | None:
    """Proposta ACEITA (deal Ganho) -> cria contrato (DRAFT) ligado a deal+proposta+cliente.
    Acha o cliente por CNPJ; se não existir, cria um mínimo. Idempotente (1 contrato por proposta),
    best-effort: nunca quebra o aceite da proposta."""
    try:
        pid = str(getattr(proposal, "id", "") or "")
        if not pid:
            return None

        # Idempotência: já existe contrato p/ esta proposta?
        existing = (
            await db.execute(text("SELECT id FROM contracts WHERE proposal_id=:pid LIMIT 1"), {"pid": pid})
        ).first()
        if existing:
            return str(existing[0])

        # Resolve cliente por documento (CNPJ/CPF) na própria sessão da request.
        digits = re.sub(r"\D", "", getattr(proposal, "client_document", "") or "")
        client_id = None
        if digits:
            row = (
                await db.execute(
                    text(
                        "SELECT id FROM clients WHERE regexp_replace(coalesce(document_number,''),'\\D','','g')=:d AND ativo LIMIT 1"
                    ),
                    {"d": digits},
                )
            ).first()
            if row:
                client_id = str(row[0])
        if not client_id:
            # Cliente não cadastrado -> cria automaticamente a partir dos dados da proposta.
            if not digits:
                logger.info(
                    "Won->contrato: proposta %s sem CNPJ/CPF -> contrato não criado", getattr(proposal, "number", "?")
                )
                return None
            client_id = await _ensure_client_from_proposal(proposal, digits)
            if not client_id:
                logger.info("Won->contrato: falha ao criar cliente p/ proposta %s", getattr(proposal, "number", "?"))
                return None

        # Monta e cria o contrato (DRAFT) via repositório.
        from modules.crm.models.contract import ContractType
        from modules.crm.repositories.contract_repository import ContractRepository
        from modules.crm.schemas.contract import ContractCreate

        total = Decimal(str(float(getattr(proposal, "total", 0) or 0)))
        recorrente = (getattr(proposal, "billing_type", "") or "") == "recurring"
        nome = (getattr(proposal, "title", None) or f"Contrato {getattr(proposal, 'number', '')}")[:200]
        if len(nome) < 3:
            nome = f"Contrato {getattr(proposal, 'number', 'x')}"
        data = ContractCreate(
            client_id=client_id,
            opportunity_id=str(proposal.opportunity_id) if getattr(proposal, "opportunity_id", None) else None,
            proposal_id=pid,
            name=nome,
            contract_type=ContractType.RECURRING if recorrente else ContractType.ONE_TIME,
            monthly_value=total if recorrente else Decimal("0"),
            total_value=total,
            start_date=date.today(),
        )
        contract = await ContractRepository(db).create(data, created_by_id=getattr(proposal, "created_by_id", None))
        from modules.crm.services.timeline import log_activity

        await log_activity(
            db,
            "contract_created",
            f"Contrato {contract.contract_number} gerado",
            proposal_id=pid,
            opportunity_id=getattr(proposal, "opportunity_id", None),
            client_id=client_id,
        )
        logger.info(
            "Won->contrato: contrato %s criado da proposta %s",
            contract.contract_number,
            getattr(proposal, "number", "?"),
        )
        return str(contract.id)
    except Exception as exc:  # noqa: BLE001 — contrato nunca quebra o aceite da proposta
        logger.warning("Won->contrato falhou p/ proposta %s: %s", getattr(proposal, "number", "?"), exc)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None


async def ensure_contract_for_won_opportunity(db: AsyncSession, opportunity) -> str | None:
    """Deal que virou GANHO (pelo Kanban/close) -> cria contrato a partir da proposta vinculada.
    Reusa ensure_contract_for_proposal. Idempotente e best-effort."""
    try:
        if (getattr(opportunity, "stage", "") or "") != "closed_won":
            return None
        opp_id = str(getattr(opportunity, "id", "") or "")
        if not opp_id:
            return None
        from sqlalchemy import select

        from modules.crm.models.proposal import Proposal

        prop = (
            (
                await db.execute(
                    select(Proposal)
                    .where(Proposal.opportunity_id == opp_id, Proposal.is_active.is_(True))
                    .order_by(Proposal.created_at.desc())
                )
            )
            .scalars()
            .first()
        )
        if not prop:
            logger.info("Won->contrato: deal %s ganho sem proposta vinculada -> contrato não criado", opp_id)
            return None
        return await ensure_contract_for_proposal(db, prop)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Won->contrato (deal) falhou p/ %s: %s", getattr(opportunity, "id", "?"), exc)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None


async def _ensure_client_from_proposal(proposal, digits: str) -> str | None:
    """Acha (por documento) ou CRIA o cliente a partir da proposta. Sessão ISOLADA + valores planos +
    CAST (evita MissingGreenlet e o bug do ::enum). Retorna client_id ou None."""
    try:
        from core.database import async_session_factory

        nome = (getattr(proposal, "client_name", None) or "Cliente")[:255]
        email = getattr(proposal, "client_email", None)
        opp_id = getattr(proposal, "opportunity_id", None)
        async with async_session_factory() as s:
            row = (
                await s.execute(
                    text(
                        "SELECT id FROM clients WHERE regexp_replace(coalesce(document_number,''),'\\D','','g')=:d AND ativo LIMIT 1"
                    ),
                    {"d": digits},
                )
            ).first()
            if row:
                return str(row[0])
            lead_id = None
            if opp_id:
                lr = (
                    await s.execute(text("SELECT lead_id FROM opportunities WHERE id=:o"), {"o": str(opp_id)})
                ).first()
                if lr and lr[0]:
                    lead_id = str(lr[0])
            seq_row = (
                await s.execute(
                    text(
                        "SELECT COALESCE(MAX(CAST(split_part(code,'-',3) AS INTEGER)),0)+1 FROM clients WHERE code LIKE :p"
                    ),
                    {"p": f"CLI-{date.today().year}-%"},
                )
            ).first()
            seq = int(seq_row[0]) if seq_row and seq_row[0] else 1
            code = f"CLI-{date.today().year}-{seq:05d}"
            dtype = "cnpj" if len(digits) == 14 else ("cpf" if len(digits) == 11 else "other")
            ctype = "condominium" if "condom" in nome.lower() else ("pj" if len(digits) == 14 else "pf")
            mail = email or f"{code.lower()}@sememail.conectamais.pro"
            ins = (
                await s.execute(
                    text("""
                INSERT INTO clients (id,code,name,client_type,document_type,document_number,email,status,
                    guardian_enabled,plus_enabled,ativo,is_defaulter,is_vip,lead_id,crm_origin,created_at,updated_at)
                VALUES (gen_random_uuid(),:code,:name,CAST(:ctype AS client_type_enum),CAST(:dtype AS document_type_enum),
                    :doc,:email,CAST('active' AS client_status_enum),false,false,true,false,false,:lead_id,'proposta',now(),now())
                RETURNING id
                """),
                    {
                        "code": code,
                        "name": nome,
                        "ctype": ctype,
                        "dtype": dtype,
                        "doc": digits,
                        "email": mail,
                        "lead_id": lead_id,
                    },
                )
            ).first()
            await s.commit()
            logger.info("Won->contrato: cliente %s criado da proposta %s", code, getattr(proposal, "number", "?"))
            return str(ins[0])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Criar cliente da proposta falhou: %s", exc)
        return None
