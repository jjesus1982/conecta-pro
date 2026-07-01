"""
Repository para operações de banco de dados com Post.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import logger
from modules.operacional.models.post import Post, PostStatus
from modules.operacional.schemas.post import PostCreate, PostFilter, PostStats, PostUpdate


class PostRepository:
    """Repository para operações CRUD de Post."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _generate_code(self) -> str:
        """Gera código único para o posto."""
        result = await self.db.execute(select(func.count(Post.id)))
        count = result.scalar() or 0
        return f"POST-{count + 1:04d}"

    async def _peric_cct_por_alocacao(self, post_id: str) -> float | None:
        """Deriva o adicional de periculosidade do posto a partir da CCT.

        O posto nao guarda cargo diretamente; o vinculo e:
            posts -> allocations (post_id) -> employees (employee_id)
            -> cct_cargos (employees.cct_cargo_id).

        Retorna o maior adicional_periculosidade_percentual entre os funcionarios
        ativos alocados no posto (fonte unica: cct_cargos). Retorna None se nao
        houver alocacao ativa com cargo CCT vinculado — nesse caso o chamador
        preserva o valor informado.
        """
        try:
            result = await self.db.execute(
                text(
                    "SELECT MAX(cc.adicional_periculosidade_percentual) "
                    "FROM allocations a "
                    "JOIN employees e ON e.id = a.employee_id "
                    "JOIN cct_cargos cc ON cc.id = e.cct_cargo_id "
                    "WHERE a.post_id = :pid AND a.status = 'active' "
                    "AND a.is_active = true"
                ),
                {"pid": post_id},
            )
            value = result.scalar()
            return float(value) if value is not None else None
        except Exception as exc:
            logger.debug(f"peric CCT por alocacao ({post_id}): {exc}")
            return None

    async def sincronizar_hazard_pay_cct(self, post_id: str) -> Post | None:
        """Recalcula hazard_pay_percent do posto a partir da CCT (cct_cargos).

        Puxa a periculosidade dos funcionarios alocados via
        employees.cct_cargo_id -> cct_cargos. Se houver periculosidade na CCT,
        o hazard_pay do posto passa a refleti-la (ex.: Vigia -> 30%), em vez de 0.
        """
        post = await self.get_by_id(post_id)
        if not post:
            return None
        peric = await self._peric_cct_por_alocacao(post_id)
        if peric is not None:
            post.hazard_pay_percent = peric
            await self.db.commit()
            await self.db.refresh(post)
            logger.info(f"Post {post.code}: hazard_pay sincronizado com CCT = {peric}%")
        return post

    async def create(self, data: PostCreate, created_by: str | None = None) -> Post:
        """
        Cria um novo posto.

        Args:
            data: Dados do posto
            created_by: ID do usuário criador

        Returns:
            Post criado
        """
        code = await self._generate_code()

        post = Post(
            id=str(uuid4()),
            code=code,
            name=data.name,
            description=data.description,
            post_type=data.post_type.value,
            status=PostStatus.ACTIVE.value,
            shift_type=data.shift_type.value,
            contract_id=data.contract_id,
            client_id=data.client_id,
            address=data.address,
            city=data.city,
            state=data.state,
            zip_code=data.zip_code,
            latitude=data.latitude,
            longitude=data.longitude,
            shift_start_time=data.shift_start_time,
            shift_end_time=data.shift_end_time,
            break_duration_minutes=data.break_duration_minutes,
            night_shift_bonus_percent=data.night_shift_bonus_percent,
            hazard_pay_percent=data.hazard_pay_percent,
            required_certifications=data.required_certifications,
            required_headcount=data.required_headcount,
            requires_experience_months=data.requires_experience_months,
            hourly_rate=data.hourly_rate,
            monthly_cost=data.monthly_cost,
            requires_armed=data.requires_armed,
            requires_vehicle=data.requires_vehicle,
            supervisor_name=data.supervisor_name,
            supervisor_phone=data.supervisor_phone,
            emergency_contact=data.emergency_contact,
            emergency_phone=data.emergency_phone,
            notes=data.notes,
            created_by=created_by,
        )

        self.db.add(post)
        await self.db.commit()
        await self.db.refresh(post)

        # Deriva periculosidade da CCT quando nao foi informada explicitamente.
        # (posto recem-criado normalmente ainda nao tem alocacao; nesse caso
        #  fica no valor informado e sera atualizado por sincronizar_hazard_pay_cct
        #  quando um funcionario for alocado).
        if not post.hazard_pay_percent:
            peric = await self._peric_cct_por_alocacao(post.id)
            if peric is not None and peric > 0:
                post.hazard_pay_percent = peric
                await self.db.commit()
                await self.db.refresh(post)

        logger.info(f"Post criado: {post.id} ({post.code})")
        return post

    async def get_by_id(self, post_id: str) -> Post | None:
        """
        Busca posto por ID.

        Args:
            post_id: ID do posto

        Returns:
            Post ou None
        """
        result = await self.db.execute(select(Post).where(Post.id == post_id, Post.is_active.is_(True)))
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> Post | None:
        """
        Busca posto por código.

        Args:
            code: Código do posto

        Returns:
            Post ou None
        """
        result = await self.db.execute(select(Post).where(Post.code == code, Post.is_active.is_(True)))
        return result.scalar_one_or_none()

    async def search_by_name(self, name: str, limit: int = 5) -> list[Post]:
        """
        Busca postos por nome usando ILIKE (fuzzy).

        Cada palavra do termo de busca deve estar presente no nome do posto.
        Ex: "prime arena" encontra "Condomínio Prime Arena".

        Args:
            name: Termo de busca (parcial)
            limit: Máximo de resultados

        Returns:
            Lista de postos encontrados
        """
        words = name.strip().split()
        if not words:
            return []

        query = select(Post).where(Post.is_active.is_(True))
        for word in words:
            if len(word) >= 2:
                query = query.where(Post.name.ilike(f"%{word}%"))

        query = query.order_by(Post.name).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def list(
        self,
        filters: PostFilter | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Post], int]:
        """
        Lista postos com filtros e paginação.

        Args:
            filters: Filtros de busca
            page: Página atual
            page_size: Itens por página

        Returns:
            Tupla (postos, total)
        """
        query = select(Post).where(Post.is_active.is_(True))

        if filters:
            query = self._apply_filters(query, filters)

        # Count total
        count_query = select(func.count(Post.id)).where(Post.is_active.is_(True))
        if filters:
            count_query = self._apply_filters(count_query, filters)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply pagination and ordering
        query = query.order_by(Post.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        posts = list(result.scalars().all())

        return posts, total

    def _apply_filters(self, query, filters: PostFilter):
        """Aplica filtros à query."""
        if filters.post_type:
            query = query.where(Post.post_type == filters.post_type.value)

        if filters.status:
            query = query.where(Post.status == filters.status.value)

        if filters.shift_type:
            query = query.where(Post.shift_type == filters.shift_type.value)

        if filters.contract_id:
            query = query.where(Post.contract_id == filters.contract_id)

        if filters.client_id:
            query = query.where(Post.client_id == filters.client_id)

        if filters.city:
            query = query.where(Post.city.ilike(f"%{filters.city}%"))

        if filters.state:
            query = query.where(Post.state == filters.state.upper())

        if filters.requires_armed is not None:
            query = query.where(Post.requires_armed == filters.requires_armed)

        if filters.requires_vehicle is not None:
            query = query.where(Post.requires_vehicle == filters.requires_vehicle)

        if filters.search:
            search_term = f"%{filters.search}%"
            query = query.where(
                or_(
                    Post.name.ilike(search_term),
                    Post.code.ilike(search_term),
                    Post.address.ilike(search_term),
                )
            )

        return query

    async def update(self, post_id: str, data: PostUpdate) -> Post | None:
        """
        Atualiza um posto.

        Args:
            post_id: ID do posto
            data: Dados para atualização

        Returns:
            Post atualizado ou None
        """
        post = await self.get_by_id(post_id)
        if not post:
            return None

        update_data = data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            if field in ("post_type", "status", "shift_type") and value:
                setattr(post, field, value.value)
            else:
                setattr(post, field, value)

        post.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(post)

        logger.info(f"Post atualizado: {post.id}")
        return post

    async def delete(self, post_id: str) -> bool:
        """
        Soft delete de posto.

        Args:
            post_id: ID do posto

        Returns:
            True se deletado
        """
        post = await self.get_by_id(post_id)
        if not post:
            return False

        post.is_active = False
        post.status = PostStatus.INACTIVE.value
        post.updated_at = datetime.utcnow()

        await self.db.commit()

        logger.info(f"Post deletado (soft): {post.id}")
        return True

    async def get_by_contract(self, contract_id: str) -> list[Post]:
        """
        Lista postos de um contrato.

        Args:
            contract_id: ID do contrato

        Returns:
            Lista de postos
        """
        result = await self.db.execute(
            select(Post).where(
                Post.contract_id == contract_id,
                Post.is_active.is_(True),
            )
        )
        return list(result.scalars().all())

    async def get_by_client(self, client_id: str) -> list[Post]:
        """
        Lista postos de um cliente.

        Args:
            client_id: ID do cliente

        Returns:
            Lista de postos
        """
        result = await self.db.execute(
            select(Post).where(
                Post.client_id == client_id,
                Post.is_active.is_(True),
            )
        )
        return list(result.scalars().all())

    async def get_stats(self) -> PostStats:
        """
        Obtém estatísticas de postos.

        Returns:
            Estatísticas
        """
        result = await self.db.execute(select(Post).where(Post.is_active.is_(True)))
        posts = list(result.scalars().all())

        if not posts:
            return PostStats(
                total=0,
                by_status={},
                by_type={},
                by_shift={},
                filled=0,
                with_vacancy=0,
                total_headcount=0,
                total_allocated=0,
                total_monthly_cost=0.0,
            )

        by_status: dict[str, int] = {}
        by_type: dict[str, int] = {}
        by_shift: dict[str, int] = {}
        filled = 0
        with_vacancy = 0
        total_headcount = 0
        total_allocated = 0
        total_monthly_cost = 0.0

        for post in posts:
            by_status[post.status] = by_status.get(post.status, 0) + 1
            by_type[post.post_type] = by_type.get(post.post_type, 0) + 1
            by_shift[post.shift_type] = by_shift.get(post.shift_type, 0) + 1

            total_headcount += post.required_headcount
            total_monthly_cost += post.monthly_cost

            if post.is_filled:
                filled += 1
            if post.vacancy_count > 0:
                with_vacancy += 1

            # Usar current_headcount em vez de contar allocations (lazy="noload")
            total_allocated += post.current_headcount

        return PostStats(
            total=len(posts),
            by_status=by_status,
            by_type=by_type,
            by_shift=by_shift,
            filled=filled,
            with_vacancy=with_vacancy,
            total_headcount=total_headcount,
            total_allocated=total_allocated,
            total_monthly_cost=total_monthly_cost,
        )
