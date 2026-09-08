"""
Controller (endpoints) para Dashboard CRM.
"""


from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.crm.models.commission import Commission
from modules.crm.models.lead import Lead
from modules.crm.models.opportunity import Opportunity
from modules.crm.models.proposal import Proposal

router = APIRouter(prefix="/dashboard", tags=["CRM - Dashboard"])


async def _get_all_leads(db: AsyncSession) -> list[Lead]:
    """Busca todos os leads ativos."""
    result = await db.execute(select(Lead).where(Lead.is_active.is_(True)))
    return list(result.scalars().all())


async def _get_all_opportunities(db: AsyncSession) -> list[Opportunity]:
    """Busca todas as opportunities ativas."""
    result = await db.execute(select(Opportunity).where(Opportunity.is_active.is_(True)))
    return list(result.scalars().all())


async def _get_all_proposals(db: AsyncSession) -> list[Proposal]:
    """Busca todas as propostas ativas."""
    result = await db.execute(select(Proposal).where(Proposal.is_active.is_(True)))
    return list(result.scalars().all())


async def _get_all_commissions(db: AsyncSession) -> list[Commission]:
    """Busca todas as comissões ativas."""
    result = await db.execute(select(Commission).where(Commission.is_active.is_(True)))
    return list(result.scalars().all())


