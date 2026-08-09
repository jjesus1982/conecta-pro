"""
Repository para operações de banco de dados com Lead.
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import logger
from modules.crm.models.lead import Lead, LeadStatus
from modules.crm.schemas.lead import LeadCreate, LeadFilter, LeadStats, LeadUpdate
from modules.crm.services.lead_service import lead_service
from modules.crm.services.phone import match_key_br


class LeadRepository:
    """Repository para operações CRUD de Lead."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def find_duplicate(
        self, phone: str | None = None, email: str | None = None
    ) -> Lead | None:
        """Lead existente do MESMO contato — ponto único de dedup do CRM.

        Regra (decisão do Jordan, 2026-08-07): mesmo telefone = mesmo lead.
        Casa por `match_key_br` (DDD + 8 últimos dígitos), que tolera nono dígito e
        variação de DDI — o mesmo helper já usado por `pipeline_sync`.

        O SQL apenas PRÉ-FILTRA pelos 8 últimos dígitos; quem decide é o
        `match_key_br` em Python. Assim a regra de pareamento tem UMA fonte só, em
        vez de viver duplicada entre Python e SQL.

        Devolve None quando AMBÍGUO (2+ candidatos): nunca escolher entre dois leads
        — mesma semântica de `pipeline_sync._lead_id_for_proposal`.

        Só considera lead ativo: lead desativado não deve capturar contato novo.
        Telefone curto demais (< 10 dígitos) → `match_key_br` devolve None e caímos
        no e-mail, se houver. Nunca adivinhar.
        """
        chave = match_key_br(phone)
        if chave:
            sufixo = chave[-8:]
            res = await self.db.execute(
                select(Lead).where(
                    Lead.is_active.is_(True),
                    func.right(func.regexp_replace(Lead.phone, r"\D", "", "g"), 8) == sufixo,
                )
            )
            # Confirma com a regra canônica (o sufixo sozinho ignora o DDD).
            candidatos = [lead for lead in res.scalars().all() if match_key_br(lead.phone) == chave]
            if len(candidatos) == 1:
                return candidatos[0]
            if len(candidatos) > 1:
                logger.warning(
                    f"Dedup ambíguo p/ telefone …{sufixo}: {len(candidatos)} leads ativos. "
                    "Não escolho — criando lead novo."
                )
            return None

        if email:
            alvo = email.strip().lower()
            res = await self.db.execute(
                select(Lead).where(Lead.is_active.is_(True), func.lower(Lead.email) == alvo)
            )
            candidatos = res.scalars().all()
            return candidatos[0] if len(candidatos) == 1 else None

        return None

    async def create_or_get(self, data: LeadCreate, *, dedup: bool = True) -> tuple[Lead, bool]:
        """PONTO ÚNICO de criação de lead. Devolve `(lead, criado)`.

        Com `dedup=True` (padrão) e já existindo lead ATIVO do mesmo contato
        (ver `find_duplicate`), devolve o EXISTENTE em vez de duplicar.

        No lead reencontrado preenche APENAS campos vazios — nunca sobrescreve o
        que já tem valor. `source` é preservado de propósito: a origem é a do
        PRIMEIRO contato, e reescrevê-la apagaria a atribuição de marketing
        (quem já falou com a gente antes não "vira" lead de campanha nova).

        `dedup=False` existe para o chamador que precisa mesmo de registro novo;
        use com motivo declarado, não por conveniência.
        """
        if dedup:
            existente = await self.find_duplicate(phone=data.phone, email=data.email)
            if existente:
                if self._preencher_vazios(existente, data):
                    existente.score, existente.probability = lead_service.calculate_score(existente)
                    await self.db.commit()
                    await self.db.refresh(existente)
                logger.info(
                    f"Lead reaproveitado: {existente.id} — origem preservada "
                    f"({existente.source}), não duplicado"
                )
                return existente, False
        return await self.create(data), True

    @staticmethod
    def _preencher_vazios(lead: Lead, data: LeadCreate) -> bool:
        """Completa só o que está vazio no lead existente. Devolve True se mudou algo.

        NUNCA toca em `source` nem sobrescreve campo já preenchido.
        """
        mudou = False
        for campo in (
            "email", "phone", "company", "position", "company_size",
            "industry", "notes", "expected_value", "assigned_to_id",
        ):
            novo = getattr(data, campo, None)
            if novo and not getattr(lead, campo, None):
                setattr(lead, campo, novo)
                mudou = True
        return mudou

    async def create(self, data: LeadCreate) -> Lead:
        """
        Cria um novo lead.

        Args:
            data: Dados do lead

        Returns:
            Lead criado
        """
        lead = Lead(
            id=str(uuid4()),
            name=data.name,
            email=data.email,
            phone=data.phone,
            company=data.company,
            position=data.position,
            company_size=data.company_size,
            industry=data.industry,
            source=data.source.value,
            status=LeadStatus.NEW.value,
            expected_value=data.expected_value,
            notes=data.notes,
            assigned_to_id=data.assigned_to_id,
        )

        # Calcular score inicial
        score, probability = lead_service.calculate_score(lead)
        lead.score = score
        lead.probability = probability

        self.db.add(lead)
        await self.db.commit()
        await self.db.refresh(lead)

        logger.info(f"Lead criado: {lead.id} ({lead.email})")
        return lead

    async def get_by_id(self, lead_id: str) -> Lead | None:
        """
        Busca lead por ID.

        Args:
            lead_id: ID do lead

        Returns:
            Lead ou None
        """
        result = await self.db.execute(select(Lead).where(Lead.id == lead_id, Lead.is_active.is_(True)))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Lead | None:
        """
        Busca lead por email.

        Args:
            email: Email do lead

        Returns:
            Lead ou None
        """
        result = await self.db.execute(select(Lead).where(Lead.email == email, Lead.is_active.is_(True)))
        return result.scalar_one_or_none()

    async def list(
        self,
        filters: LeadFilter | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Lead], int]:
        """
        Lista leads com filtros e paginação.

        Args:
            filters: Filtros de busca
            page: Página atual
            page_size: Itens por página

        Returns:
            Tupla (leads, total)
        """
        query = select(Lead).where(Lead.is_active.is_(True))

        if filters:
            query = self._apply_filters(query, filters)

        # Count total
        count_query = select(func.count(Lead.id)).where(Lead.is_active.is_(True))
        if filters:
            count_query = self._apply_filters(count_query, filters)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply pagination and ordering
        query = query.order_by(Lead.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        leads = list(result.scalars().all())

        return leads, total

    def _apply_filters(self, query, filters: LeadFilter):
        """Aplica filtros à query."""
        if filters.status:
            query = query.where(Lead.status == filters.status.value)

        if filters.source:
            query = query.where(Lead.source == filters.source.value)

        if filters.assigned_to_id:
            query = query.where(Lead.assigned_to_id == filters.assigned_to_id)

        if filters.min_score is not None:
            query = query.where(Lead.score >= filters.min_score)

        if filters.max_score is not None:
            query = query.where(Lead.score <= filters.max_score)

        if filters.is_hot is not None:
            if filters.is_hot:
                query = query.where(Lead.score >= 70)
            else:
                query = query.where(Lead.score < 70)

        if filters.company:
            query = query.where(Lead.company.ilike(f"%{filters.company}%"))

        if filters.search:
            search_term = f"%{filters.search}%"
            query = query.where(
                or_(
                    Lead.name.ilike(search_term),
                    Lead.email.ilike(search_term),
                    Lead.company.ilike(search_term),
                )
            )

        return query

    async def update(self, lead_id: str, data: LeadUpdate) -> Lead | None:
        """
        Atualiza um lead.

        Args:
            lead_id: ID do lead
            data: Dados para atualização

        Returns:
            Lead atualizado ou None
        """
        lead = await self.get_by_id(lead_id)
        if not lead:
            return None

        # Atualizar apenas campos fornecidos
        update_data = data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            if field == "status" and value or field == "source" and value:
                setattr(lead, field, value.value)
            else:
                setattr(lead, field, value)

        # Recalcular score se dados relevantes mudaram
        score_fields = {"company", "company_size", "industry", "status"}
        if score_fields & set(update_data.keys()):
            score, probability = lead_service.calculate_score(lead)
            lead.score = score
            lead.probability = probability

        lead.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(lead)

        logger.info(f"Lead atualizado: {lead.id}")
        return lead

    async def update_score(self, lead_id: str) -> Lead | None:
        """
        Recalcula e atualiza o score do lead.

        Args:
            lead_id: ID do lead

        Returns:
            Lead com score atualizado ou None
        """
        lead = await self.get_by_id(lead_id)
        if not lead:
            return None

        score, probability = lead_service.calculate_score(lead)
        lead.score = score
        lead.probability = probability
        lead.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(lead)

        return lead

    async def update_status(
        self,
        lead_id: str,
        status: LeadStatus,
        notes: str | None = None,
    ) -> Lead | None:
        """
        Atualiza status do lead.

        Args:
            lead_id: ID do lead
            status: Novo status
            notes: Observações

        Returns:
            Lead atualizado ou None
        """
        lead = await self.get_by_id(lead_id)
        if not lead:
            return None

        lead.status = status.value
        lead.last_contact_at = datetime.utcnow()

        if notes:
            existing_notes = lead.notes or ""
            timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
            lead.notes = f"{existing_notes}\n[{timestamp}] Status: {status.value} - {notes}".strip()

        # Recalcular score com novo status
        score, probability = lead_service.calculate_score(lead)
        lead.score = score
        lead.probability = probability

        # Sugerir próximo contato
        lead.next_contact_at = lead_service.get_next_contact_date(lead)

        await self.db.commit()
        await self.db.refresh(lead)

        logger.info(f"Lead {lead.id} status alterado para {status.value}")
        return lead

    async def delete(self, lead_id: str) -> bool:
        """
        Soft delete de lead.

        Args:
            lead_id: ID do lead

        Returns:
            True se deletado
        """
        lead = await self.get_by_id(lead_id)
        if not lead:
            return False

        lead.is_active = False
        lead.updated_at = datetime.utcnow()

        await self.db.commit()

        logger.info(f"Lead deletado (soft): {lead.id}")
        return True

    async def get_stats(
        self,
        assigned_to_id: str | None = None,
    ) -> LeadStats:
        """
        Obtém estatísticas de leads.

        Args:
            assigned_to_id: Filtrar por responsável

        Returns:
            Estatísticas
        """
        base_query = select(Lead).where(Lead.is_active.is_(True))

        if assigned_to_id:
            base_query = base_query.where(Lead.assigned_to_id == assigned_to_id)

        result = await self.db.execute(base_query)
        leads = list(result.scalars().all())

        if not leads:
            return LeadStats(
                total=0,
                by_status={},
                by_source={},
                hot_leads=0,
                avg_score=0.0,
                total_expected_value=0.0,
                total_weighted_value=0.0,
            )

        # Calcular estatísticas
        by_status: dict[str, int] = {}
        by_source: dict[str, int] = {}
        hot_leads = 0
        total_score = 0
        total_expected = 0.0
        total_weighted = 0.0

        for lead in leads:
            by_status[lead.status] = by_status.get(lead.status, 0) + 1
            by_source[lead.source] = by_source.get(lead.source, 0) + 1
            total_score += lead.score
            total_expected += lead.expected_value
            total_weighted += lead.weighted_value

            if lead.is_hot:
                hot_leads += 1

        return LeadStats(
            total=len(leads),
            by_status=by_status,
            by_source=by_source,
            hot_leads=hot_leads,
            avg_score=total_score / len(leads),
            total_expected_value=total_expected,
            total_weighted_value=total_weighted,
        )
