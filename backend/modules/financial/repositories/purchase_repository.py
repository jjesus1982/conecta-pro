"""Repository para módulo de compras."""

import builtins
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from modules.financial.models.goods_receipt import GoodsReceipt, GoodsReceiptItem, ReceiptStatus
from modules.financial.models.product import Product, ProductStatus
from modules.financial.models.product_category import ProductCategory, ProductCategoryStatus
from modules.financial.models.purchase_approval import (
    ApprovalStatus,
    ApprovalType,
    PurchaseApproval,
)
from modules.financial.models.purchase_order import OrderStatus, PurchaseOrder, PurchaseOrderItem
from modules.financial.models.purchase_quotation import (
    PurchaseQuotation,
    PurchaseQuotationItem,
    QuotationStatus,
)
from modules.financial.models.purchase_requisition import (
    PurchaseRequisition,
    PurchaseRequisitionItem,
    RequisitionStatus,
)
from modules.financial.schemas.goods_receipt import (
    GoodsReceiptCreate,
    GoodsReceiptUpdate,
    ReceiptFilter,
    ReceiptStats,
)
from modules.financial.schemas.product import ProductCreate, ProductStats, ProductUpdate
from modules.financial.schemas.product_category import (
    ProductCategoryCreate,
    ProductCategoryStats,
    ProductCategoryUpdate,
)
from modules.financial.schemas.purchase_approval import (
    ApprovalFilter,
    ApprovalStats,
    PurchaseApprovalCreate,
    PurchaseApprovalUpdate,
)
from modules.financial.schemas.purchase_order import (
    OrderFilter,
    OrderStats,
    PurchaseOrderCreate,
    PurchaseOrderUpdate,
)
from modules.financial.schemas.purchase_quotation import (
    PurchaseQuotationCreate,
    PurchaseQuotationUpdate,
    QuotationStats,
)
from modules.financial.schemas.purchase_requisition import (
    PurchaseRequisitionCreate,
    PurchaseRequisitionUpdate,
    RequisitionFilter,
    RequisitionStats,
)


class ProductCategoryRepository:
    """Repository para categorias de produtos."""

    def __init__(self, session: AsyncSession):
        """Inicializa o repository."""
        self.session = session

    async def create(
        self,
        data: ProductCategoryCreate,
        user_id: UUID | None = None,
    ) -> ProductCategory:
        """Cria uma nova categoria."""
        category = ProductCategory(
            **data.model_dump(),
            created_by=user_id,
        )
        self.session.add(category)
        await self.session.flush()
        await self.session.refresh(category)
        return category

    async def get_by_id(self, category_id: UUID) -> ProductCategory | None:
        """Busca categoria por ID."""
        result = await self.session.execute(
            select(ProductCategory)
            .options(selectinload(ProductCategory.children))
            .where(
                and_(
                    ProductCategory.id == category_id,
                    ProductCategory.ativo.is_(True),
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_by_code(
        self,
        code: str,
        condominio_id: UUID,
    ) -> ProductCategory | None:
        """Busca categoria por código."""
        result = await self.session.execute(
            select(ProductCategory).where(
                and_(
                    ProductCategory.code == code,
                    ProductCategory.condominio_id == condominio_id,
                    ProductCategory.ativo.is_(True),
                )
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        condominio_id: UUID,
        parent_id: UUID | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ProductCategory]:
        """Lista categorias."""
        query = (
            select(ProductCategory)
            .options(selectinload(ProductCategory.children))
            .where(
                and_(
                    ProductCategory.condominio_id == condominio_id,
                    ProductCategory.ativo.is_(True),
                )
            )
        )

        if parent_id:
            query = query.where(ProductCategory.parent_id == parent_id)
        else:
            query = query.where(ProductCategory.parent_id.is_(None))

        query = query.order_by(ProductCategory.name).offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_tree(self, condominio_id: UUID) -> builtins.list[ProductCategory]:
        """Retorna árvore completa de categorias."""
        result = await self.session.execute(
            select(ProductCategory)
            .options(selectinload(ProductCategory.children))
            .where(
                and_(
                    ProductCategory.condominio_id == condominio_id,
                    ProductCategory.ativo.is_(True),
                    ProductCategory.parent_id.is_(None),
                )
            )
            .order_by(ProductCategory.name)
        )
        return list(result.scalars().all())

    async def update(
        self,
        category: ProductCategory,
        data: ProductCategoryUpdate,
    ) -> ProductCategory:
        """Atualiza categoria."""
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(category, field):
                setattr(category, field, value)
        category.updated_at = datetime.utcnow()
        await self.session.flush()
        await self.session.refresh(category)
        return category

    async def delete(self, category: ProductCategory) -> None:
        """Deleta categoria (soft delete)."""
        category.ativo = False
        category.status = ProductCategoryStatus.INATIVA.value
        category.updated_at = datetime.utcnow()
        await self.session.flush()

    async def get_stats(self, condominio_id: UUID) -> ProductCategoryStats:
        """Retorna estatísticas de categorias."""
        status_query = (
            select(
                ProductCategory.status,
                func.count(ProductCategory.id).label("count"),
            )
            .where(
                and_(
                    ProductCategory.condominio_id == condominio_id,
                    ProductCategory.ativo.is_(True),
                )
            )
            .group_by(ProductCategory.status)
        )
        status_result = await self.session.execute(status_query)
        status_data = {row.status: row.count for row in status_result}

        type_query = (
            select(
                ProductCategory.category_type,
                func.count(ProductCategory.id).label("count"),
            )
            .where(
                and_(
                    ProductCategory.condominio_id == condominio_id,
                    ProductCategory.ativo.is_(True),
                )
            )
            .group_by(ProductCategory.category_type)
        )
        type_result = await self.session.execute(type_query)
        type_data = {row.category_type: row.count for row in type_result}

        return ProductCategoryStats(
            total=sum(status_data.values()),
            by_status=status_data,
            by_type=type_data,
        )


class ProductRepository:
    """Repository para produtos."""

    def __init__(self, session: AsyncSession):
        """Inicializa o repository."""
        self.session = session

    async def create(
        self,
        data: ProductCreate,
        user_id: UUID | None = None,
    ) -> Product:
        """Cria um novo produto."""
        product_data = data.model_dump(exclude={"category_ids", "supplier_ids"})
        product = Product(**product_data, created_by=user_id)
        self.session.add(product)
        await self.session.flush()
        await self.session.refresh(product)
        return product

    async def get_by_id(self, product_id: UUID) -> Product | None:
        """Busca produto por ID."""
        result = await self.session.execute(
            select(Product).where(
                and_(
                    Product.id == product_id,
                    Product.ativo.is_(True),
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_by_code(
        self,
        code: str,
        condominio_id: UUID,
    ) -> Product | None:
        """Busca produto por código."""
        result = await self.session.execute(
            select(Product).where(
                and_(
                    Product.code == code,
                    Product.condominio_id == condominio_id,
                    Product.ativo.is_(True),
                )
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        condominio_id: UUID,
        search: str | None = None,
        category_id: UUID | None = None,
        status: list[ProductStatus] | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Product]:
        """Lista produtos com filtros."""
        query = select(Product).where(
            and_(
                Product.condominio_id == condominio_id,
                Product.ativo.is_(True),
            )
        )

        if search:
            search_term = f"%{search}%"
            query = query.where(
                or_(
                    Product.name.ilike(search_term),
                    Product.code.ilike(search_term),
                    Product.description.ilike(search_term),
                    Product.barcode.ilike(search_term),
                )
            )

        if category_id:
            query = query.where(Product.category_id == category_id)

        if status:
            query = query.where(Product.status.in_([s.value for s in status]))

        query = query.order_by(Product.name).offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count(
        self,
        condominio_id: UUID,
        search: str | None = None,
        category_id: UUID | None = None,
        status: builtins.list[ProductStatus] | None = None,
    ) -> int:
        """Conta produtos com filtros."""
        query = select(func.count(Product.id)).where(
            and_(
                Product.condominio_id == condominio_id,
                Product.ativo.is_(True),
            )
        )

        if search:
            search_term = f"%{search}%"
            query = query.where(
                or_(
                    Product.name.ilike(search_term),
                    Product.code.ilike(search_term),
                )
            )

        if category_id:
            query = query.where(Product.category_id == category_id)

        if status:
            query = query.where(Product.status.in_([s.value for s in status]))

        result = await self.session.execute(query)
        return result.scalar_one()

    async def update(self, product: Product, data: ProductUpdate) -> Product:
        """Atualiza produto."""
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(product, field):
                setattr(product, field, value)
        product.updated_at = datetime.utcnow()
        await self.session.flush()
        await self.session.refresh(product)
        return product

    async def delete(self, product: Product) -> None:
        """Deleta produto (soft delete)."""
        product.ativo = False
        product.status = ProductStatus.INATIVO.value
        product.updated_at = datetime.utcnow()
        await self.session.flush()

    async def update_price(
        self,
        product: Product,
        new_price: Decimal,
        source: str = "manual",
    ) -> Product:
        """Atualiza preço do produto."""
        product.update_price(new_price, source)
        await self.session.flush()
        await self.session.refresh(product)
        return product

    async def get_stats(self, condominio_id: UUID) -> ProductStats:
        """Retorna estatísticas de produtos."""
        status_query = (
            select(
                Product.status,
                func.count(Product.id).label("count"),
            )
            .where(
                and_(
                    Product.condominio_id == condominio_id,
                    Product.ativo.is_(True),
                )
            )
            .group_by(Product.status)
        )
        status_result = await self.session.execute(status_query)
        status_data = {row.status: row.count for row in status_result}

        type_query = (
            select(
                Product.product_type,
                func.count(Product.id).label("count"),
            )
            .where(
                and_(
                    Product.condominio_id == condominio_id,
                    Product.ativo.is_(True),
                )
            )
            .group_by(Product.product_type)
        )
        type_result = await self.session.execute(type_query)
        type_data = {row.product_type: row.count for row in type_result}

        low_stock_query = select(func.count(Product.id)).where(
            and_(
                Product.condominio_id == condominio_id,
                Product.ativo.is_(True),
                Product.current_stock <= Product.min_stock,
                Product.min_stock > 0,
            )
        )
        low_stock_result = await self.session.execute(low_stock_query)
        low_stock = low_stock_result.scalar_one()

        return ProductStats(
            total=sum(status_data.values()),
            by_status=status_data,
            by_type=type_data,
            low_stock=low_stock,
        )


class PurchaseRequisitionRepository:
    """Repository para requisições de compra."""

    def __init__(self, session: AsyncSession):
        """Inicializa o repository."""
        self.session = session

    async def create(
        self,
        data: PurchaseRequisitionCreate,
        user_id: UUID,
    ) -> PurchaseRequisition:
        """Cria uma nova requisição."""
        items_data = data.items
        req_data = data.model_dump(exclude={"items", "requester_id"})
        requisition = PurchaseRequisition(
            **req_data,
            requester_id=user_id,
            created_by=user_id,
        )
        self.session.add(requisition)
        await self.session.flush()

        for idx, item_data in enumerate(items_data, 1):
            item = PurchaseRequisitionItem(
                requisition_id=requisition.id,
                item_number=idx,
                **item_data.model_dump(),
            )
            self.session.add(item)

        await self.session.flush()
        await self.session.refresh(requisition)
        return requisition

    async def get_by_id(self, requisition_id: UUID) -> PurchaseRequisition | None:
        """Busca requisição por ID."""
        result = await self.session.execute(
            select(PurchaseRequisition)
            .options(selectinload(PurchaseRequisition.items))
            .where(
                and_(
                    PurchaseRequisition.id == requisition_id,
                    PurchaseRequisition.ativo.is_(True),
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_by_number(
        self,
        number: str,
        condominio_id: UUID,
    ) -> PurchaseRequisition | None:
        """Busca requisição por número."""
        result = await self.session.execute(
            select(PurchaseRequisition)
            .options(selectinload(PurchaseRequisition.items))
            .where(
                and_(
                    PurchaseRequisition.number == number,
                    PurchaseRequisition.condominio_id == condominio_id,
                    PurchaseRequisition.ativo.is_(True),
                )
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        condominio_id: UUID,
        filters: RequisitionFilter | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[PurchaseRequisition]:
        """Lista requisições com filtros."""
        query = (
            select(PurchaseRequisition)
            .options(selectinload(PurchaseRequisition.items))
            .where(
                and_(
                    PurchaseRequisition.condominio_id == condominio_id,
                    PurchaseRequisition.ativo.is_(True),
                )
            )
        )

        if filters:
            if filters.status:
                query = query.where(PurchaseRequisition.status.in_([s.value for s in filters.status]))
            if filters.priority:
                query = query.where(PurchaseRequisition.priority.in_([p.value for p in filters.priority]))
            if filters.requester_id:
                query = query.where(PurchaseRequisition.requester_id == filters.requester_id)
            if filters.department:
                query = query.where(PurchaseRequisition.department == filters.department)
            if filters.date_from:
                query = query.where(PurchaseRequisition.requisition_date >= filters.date_from)
            if filters.date_to:
                query = query.where(PurchaseRequisition.requisition_date <= filters.date_to)
            if filters.search:
                search_term = f"%{filters.search}%"
                query = query.where(
                    or_(
                        PurchaseRequisition.number.ilike(search_term),
                        PurchaseRequisition.description.ilike(search_term),
                    )
                )

        query = query.order_by(PurchaseRequisition.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count(
        self,
        condominio_id: UUID,
        filters: RequisitionFilter | None = None,
    ) -> int:
        """Conta requisições com filtros."""
        query = select(func.count(PurchaseRequisition.id)).where(
            and_(
                PurchaseRequisition.condominio_id == condominio_id,
                PurchaseRequisition.ativo.is_(True),
            )
        )

        if filters:
            if filters.status:
                query = query.where(PurchaseRequisition.status.in_([s.value for s in filters.status]))
            if filters.priority:
                query = query.where(PurchaseRequisition.priority.in_([p.value for p in filters.priority]))

        result = await self.session.execute(query)
        return result.scalar_one()

    async def update(
        self,
        requisition: PurchaseRequisition,
        data: PurchaseRequisitionUpdate,
    ) -> PurchaseRequisition:
        """Atualiza requisição."""
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(requisition, field):
                setattr(requisition, field, value)
        requisition.updated_at = datetime.utcnow()
        await self.session.flush()
        await self.session.refresh(requisition)
        return requisition

    async def delete(self, requisition: PurchaseRequisition) -> None:
        """Deleta requisição (soft delete)."""
        requisition.ativo = False
        requisition.updated_at = datetime.utcnow()
        await self.session.flush()

    async def get_stats(self, condominio_id: UUID) -> RequisitionStats:
        """Retorna estatísticas de requisições."""
        status_query = (
            select(
                PurchaseRequisition.status,
                func.count(PurchaseRequisition.id).label("count"),
            )
            .where(
                and_(
                    PurchaseRequisition.condominio_id == condominio_id,
                    PurchaseRequisition.ativo.is_(True),
                )
            )
            .group_by(PurchaseRequisition.status)
        )
        status_result = await self.session.execute(status_query)
        status_data = {row.status: row.count for row in status_result}

        priority_query = (
            select(
                PurchaseRequisition.priority,
                func.count(PurchaseRequisition.id).label("count"),
            )
            .where(
                and_(
                    PurchaseRequisition.condominio_id == condominio_id,
                    PurchaseRequisition.ativo.is_(True),
                )
            )
            .group_by(PurchaseRequisition.priority)
        )
        priority_result = await self.session.execute(priority_query)
        priority_data = {row.priority: row.count for row in priority_result}

        pending_approval = status_data.get(RequisitionStatus.PENDENTE_APROVACAO.value, 0)
        in_quotation = status_data.get(RequisitionStatus.EM_COTACAO.value, 0)

        total_query = select(func.sum(PurchaseRequisition.estimated_total)).where(
            and_(
                PurchaseRequisition.condominio_id == condominio_id,
                PurchaseRequisition.ativo.is_(True),
                PurchaseRequisition.status.in_(
                    [
                        RequisitionStatus.PENDENTE_APROVACAO.value,
                        RequisitionStatus.APROVADA.value,
                        RequisitionStatus.EM_COTACAO.value,
                    ]
                ),
            )
        )
        total_result = await self.session.execute(total_query)
        total_amount = total_result.scalar_one() or Decimal("0")

        return RequisitionStats(
            total=sum(status_data.values()),
            by_status=status_data,
            by_priority=priority_data,
            pending_approval=pending_approval,
            in_quotation=in_quotation,
            total_amount=total_amount,
        )


class PurchaseQuotationRepository:
    """Repository para cotações de compra."""

    def __init__(self, session: AsyncSession):
        """Inicializa o repository."""
        self.session = session

    async def create(
        self,
        data: PurchaseQuotationCreate,
        user_id: UUID | None = None,
    ) -> PurchaseQuotation:
        """Cria uma nova cotação."""
        items_data = data.items
        quot_data = data.model_dump(exclude={"items"})
        quotation = PurchaseQuotation(**quot_data, created_by=user_id)
        self.session.add(quotation)
        await self.session.flush()

        for idx, item_data in enumerate(items_data, 1):
            item = PurchaseQuotationItem(
                quotation_id=quotation.id,
                item_number=idx,
                **item_data.model_dump(),
            )
            self.session.add(item)

        await self.session.flush()
        await self.session.refresh(quotation)
        return quotation

    async def get_by_id(self, quotation_id: UUID) -> PurchaseQuotation | None:
        """Busca cotação por ID."""
        result = await self.session.execute(
            select(PurchaseQuotation)
            .options(selectinload(PurchaseQuotation.items))
            .where(
                and_(
                    PurchaseQuotation.id == quotation_id,
                    PurchaseQuotation.ativo.is_(True),
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_by_number(
        self,
        number: str,
        condominio_id: UUID,
    ) -> PurchaseQuotation | None:
        """Busca cotação por número."""
        result = await self.session.execute(
            select(PurchaseQuotation)
            .options(selectinload(PurchaseQuotation.items))
            .where(
                and_(
                    PurchaseQuotation.number == number,
                    PurchaseQuotation.condominio_id == condominio_id,
                    PurchaseQuotation.ativo.is_(True),
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_by_requisition(
        self,
        requisition_id: UUID,
    ) -> list[PurchaseQuotation]:
        """Lista cotações de uma requisição."""
        result = await self.session.execute(
            select(PurchaseQuotation)
            .options(selectinload(PurchaseQuotation.items))
            .where(
                and_(
                    PurchaseQuotation.requisition_id == requisition_id,
                    PurchaseQuotation.ativo.is_(True),
                )
            )
            .order_by(PurchaseQuotation.overall_score.desc())
        )
        return list(result.scalars().all())

    async def list(
        self,
        condominio_id: UUID,
        status: list[QuotationStatus] | None = None,
        supplier_id: UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[PurchaseQuotation]:
        """Lista cotações com filtros."""
        query = (
            select(PurchaseQuotation)
            .options(selectinload(PurchaseQuotation.items))
            .where(
                and_(
                    PurchaseQuotation.condominio_id == condominio_id,
                    PurchaseQuotation.ativo.is_(True),
                )
            )
        )

        if status:
            query = query.where(PurchaseQuotation.status.in_([s.value for s in status]))
        if supplier_id:
            query = query.where(PurchaseQuotation.supplier_id == supplier_id)
        if date_from:
            query = query.where(PurchaseQuotation.quotation_date >= date_from)
        if date_to:
            query = query.where(PurchaseQuotation.quotation_date <= date_to)

        query = query.order_by(PurchaseQuotation.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count(
        self,
        condominio_id: UUID,
        status: builtins.list[QuotationStatus] | None = None,
    ) -> int:
        """Conta cotações."""
        query = select(func.count(PurchaseQuotation.id)).where(
            and_(
                PurchaseQuotation.condominio_id == condominio_id,
                PurchaseQuotation.ativo.is_(True),
            )
        )

        if status:
            query = query.where(PurchaseQuotation.status.in_([s.value for s in status]))

        result = await self.session.execute(query)
        return result.scalar_one()

    async def update(
        self,
        quotation: PurchaseQuotation,
        data: PurchaseQuotationUpdate,
    ) -> PurchaseQuotation:
        """Atualiza cotação."""
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(quotation, field):
                setattr(quotation, field, value)
        quotation.updated_at = datetime.utcnow()
        await self.session.flush()
        await self.session.refresh(quotation)
        return quotation

    async def delete(self, quotation: PurchaseQuotation) -> None:
        """Deleta cotação (soft delete)."""
        quotation.ativo = False
        quotation.updated_at = datetime.utcnow()
        await self.session.flush()

    async def get_stats(self, condominio_id: UUID) -> QuotationStats:
        """Retorna estatísticas de cotações."""
        status_query = (
            select(
                PurchaseQuotation.status,
                func.count(PurchaseQuotation.id).label("count"),
            )
            .where(
                and_(
                    PurchaseQuotation.condominio_id == condominio_id,
                    PurchaseQuotation.ativo.is_(True),
                )
            )
            .group_by(PurchaseQuotation.status)
        )
        status_result = await self.session.execute(status_query)
        status_data = {row.status: row.count for row in status_result}

        avg_score_query = select(func.avg(PurchaseQuotation.overall_score)).where(
            and_(
                PurchaseQuotation.condominio_id == condominio_id,
                PurchaseQuotation.ativo.is_(True),
                PurchaseQuotation.overall_score.isnot(None),
            )
        )
        avg_result = await self.session.execute(avg_score_query)
        avg_score = avg_result.scalar_one()

        return QuotationStats(
            total=sum(status_data.values()),
            by_status=status_data,
            pending_analysis=status_data.get(QuotationStatus.RECEBIDA.value, 0),
            average_score=float(avg_score) if avg_score else None,
        )


class PurchaseOrderRepository:
    """Repository para ordens de compra."""

    def __init__(self, session: AsyncSession):
        """Inicializa o repository."""
        self.session = session

    async def create(
        self,
        data: PurchaseOrderCreate,
        user_id: UUID | None = None,
    ) -> PurchaseOrder:
        """Cria uma nova ordem de compra."""
        items_data = data.items
        order_data = data.model_dump(exclude={"items"})
        order = PurchaseOrder(**order_data, created_by=user_id)
        self.session.add(order)
        await self.session.flush()

        for idx, item_data in enumerate(items_data, 1):
            item = PurchaseOrderItem(
                order_id=order.id,
                item_number=idx,
                **item_data.model_dump(),
            )
            self.session.add(item)

        await self.session.flush()
        await self.session.refresh(order)
        return order

    async def get_by_id(self, order_id: UUID) -> PurchaseOrder | None:
        """Busca ordem por ID."""
        result = await self.session.execute(
            select(PurchaseOrder)
            .options(selectinload(PurchaseOrder.items))
            .where(
                and_(
                    PurchaseOrder.id == order_id,
                    PurchaseOrder.ativo.is_(True),
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_by_number(
        self,
        number: str,
        condominio_id: UUID,
    ) -> PurchaseOrder | None:
        """Busca ordem por número."""
        result = await self.session.execute(
            select(PurchaseOrder)
            .options(selectinload(PurchaseOrder.items))
            .where(
                and_(
                    PurchaseOrder.number == number,
                    PurchaseOrder.condominio_id == condominio_id,
                    PurchaseOrder.ativo.is_(True),
                )
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        condominio_id: UUID | None = None,
        filters: OrderFilter | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[PurchaseOrder]:
        """Lista ordens com filtros."""
        base_conditions = [PurchaseOrder.ativo.is_(True)]
        if condominio_id is not None:
            base_conditions.append(PurchaseOrder.condominio_id == condominio_id)
        query = select(PurchaseOrder).options(selectinload(PurchaseOrder.items)).where(and_(*base_conditions))

        if filters:
            if filters.status:
                query = query.where(PurchaseOrder.status.in_([s.value for s in filters.status]))
            if filters.priority:
                query = query.where(PurchaseOrder.priority.in_([p.value for p in filters.priority]))
            if filters.supplier_id:
                query = query.where(PurchaseOrder.supplier_id == filters.supplier_id)
            if filters.date_from:
                query = query.where(PurchaseOrder.order_date >= filters.date_from)
            if filters.date_to:
                query = query.where(PurchaseOrder.order_date <= filters.date_to)
            if filters.delivery_from:
                query = query.where(PurchaseOrder.expected_delivery_date >= filters.delivery_from)
            if filters.delivery_to:
                query = query.where(PurchaseOrder.expected_delivery_date <= filters.delivery_to)
            if filters.search:
                search_term = f"%{filters.search}%"
                query = query.where(PurchaseOrder.number.ilike(search_term))

        query = query.order_by(PurchaseOrder.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count(
        self,
        condominio_id: UUID | None = None,
        filters: OrderFilter | None = None,
    ) -> int:
        """Conta ordens com filtros."""
        base_conditions = [PurchaseOrder.ativo.is_(True)]
        if condominio_id is not None:
            base_conditions.append(PurchaseOrder.condominio_id == condominio_id)
        query = select(func.count(PurchaseOrder.id)).where(and_(*base_conditions))

        if filters:
            if filters.status:
                query = query.where(PurchaseOrder.status.in_([s.value for s in filters.status]))

        result = await self.session.execute(query)
        return result.scalar_one()

    async def update(
        self,
        order: PurchaseOrder,
        data: PurchaseOrderUpdate,
    ) -> PurchaseOrder:
        """Atualiza ordem."""
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(order, field):
                setattr(order, field, value)
        order.updated_at = datetime.utcnow()
        await self.session.flush()
        await self.session.refresh(order)
        return order

    async def delete(self, order: PurchaseOrder) -> None:
        """Deleta ordem (soft delete)."""
        order.ativo = False
        order.updated_at = datetime.utcnow()
        await self.session.flush()

    async def get_stats(self, condominio_id: UUID) -> OrderStats:  # pylint: disable=too-many-locals
        """Retorna estatísticas de ordens."""
        status_query = (
            select(
                PurchaseOrder.status,
                func.count(PurchaseOrder.id).label("count"),
            )
            .where(
                and_(
                    PurchaseOrder.condominio_id == condominio_id,
                    PurchaseOrder.ativo.is_(True),
                )
            )
            .group_by(PurchaseOrder.status)
        )
        status_result = await self.session.execute(status_query)
        status_data = {row.status: row.count for row in status_result}

        priority_query = (
            select(
                PurchaseOrder.priority,
                func.count(PurchaseOrder.id).label("count"),
            )
            .where(
                and_(
                    PurchaseOrder.condominio_id == condominio_id,
                    PurchaseOrder.ativo.is_(True),
                )
            )
            .group_by(PurchaseOrder.priority)
        )
        priority_result = await self.session.execute(priority_query)
        priority_data = {row.priority: row.count for row in priority_result}

        pending_approval = status_data.get(OrderStatus.PENDENTE_APROVACAO.value, 0)
        pending_delivery = sum(
            status_data.get(s.value, 0)
            for s in [
                OrderStatus.ENVIADA,
                OrderStatus.CONFIRMADA,
                OrderStatus.PARCIALMENTE_RECEBIDA,
            ]
        )

        total_query = select(func.sum(PurchaseOrder.total)).where(
            and_(
                PurchaseOrder.condominio_id == condominio_id,
                PurchaseOrder.ativo.is_(True),
            )
        )
        total_result = await self.session.execute(total_query)
        total_amount = total_result.scalar_one() or Decimal("0")

        pending_query = select(func.sum(PurchaseOrder.total - PurchaseOrder.paid_total)).where(
            and_(
                PurchaseOrder.condominio_id == condominio_id,
                PurchaseOrder.ativo.is_(True),
                PurchaseOrder.status.notin_([OrderStatus.CANCELADA.value, OrderStatus.REJEITADA.value]),
            )
        )
        pending_result = await self.session.execute(pending_query)
        pending_amount = pending_result.scalar_one() or Decimal("0")

        overdue_query = select(func.count(PurchaseOrder.id)).where(
            and_(
                PurchaseOrder.condominio_id == condominio_id,
                PurchaseOrder.ativo.is_(True),
                PurchaseOrder.expected_delivery_date < date.today(),
                PurchaseOrder.status.in_(
                    [
                        OrderStatus.ENVIADA.value,
                        OrderStatus.CONFIRMADA.value,
                    ]
                ),
            )
        )
        overdue_result = await self.session.execute(overdue_query)
        overdue = overdue_result.scalar_one()

        return OrderStats(
            total=sum(status_data.values()),
            by_status=status_data,
            by_priority=priority_data,
            pending_approval=pending_approval,
            pending_delivery=pending_delivery,
            overdue=overdue,
            total_amount=total_amount,
            total_pending=pending_amount,
        )


class GoodsReceiptRepository:
    """Repository para recebimentos de mercadorias."""

    def __init__(self, session: AsyncSession):
        """Inicializa o repository."""
        self.session = session

    async def create(
        self,
        data: GoodsReceiptCreate,
        user_id: UUID | None = None,
    ) -> GoodsReceipt:
        """Cria um novo recebimento."""
        items_data = data.items
        receipt_data = data.model_dump(exclude={"items"})
        receipt = GoodsReceipt(**receipt_data, created_by=user_id)
        self.session.add(receipt)
        await self.session.flush()

        for idx, item_data in enumerate(items_data, 1):
            item = GoodsReceiptItem(
                receipt_id=receipt.id,
                item_number=idx,
                **item_data.model_dump(),
            )
            self.session.add(item)

        await self.session.flush()
        await self.session.refresh(receipt)
        return receipt

    async def get_by_id(self, receipt_id: UUID) -> GoodsReceipt | None:
        """Busca recebimento por ID."""
        result = await self.session.execute(
            select(GoodsReceipt)
            .options(selectinload(GoodsReceipt.items))
            .where(
                and_(
                    GoodsReceipt.id == receipt_id,
                    GoodsReceipt.ativo.is_(True),
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_by_number(
        self,
        number: str,
        condominio_id: UUID,
    ) -> GoodsReceipt | None:
        """Busca recebimento por número."""
        result = await self.session.execute(
            select(GoodsReceipt)
            .options(selectinload(GoodsReceipt.items))
            .where(
                and_(
                    GoodsReceipt.number == number,
                    GoodsReceipt.condominio_id == condominio_id,
                    GoodsReceipt.ativo.is_(True),
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_by_order(self, order_id: UUID) -> list[GoodsReceipt]:
        """Lista recebimentos de uma ordem."""
        result = await self.session.execute(
            select(GoodsReceipt)
            .options(selectinload(GoodsReceipt.items))
            .where(
                and_(
                    GoodsReceipt.order_id == order_id,
                    GoodsReceipt.ativo.is_(True),
                )
            )
            .order_by(GoodsReceipt.receipt_date.desc())
        )
        return list(result.scalars().all())

    async def list(
        self,
        condominio_id: UUID,
        filters: ReceiptFilter | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[GoodsReceipt]:
        """Lista recebimentos com filtros."""
        query = (
            select(GoodsReceipt)
            .options(selectinload(GoodsReceipt.items))
            .where(
                and_(
                    GoodsReceipt.condominio_id == condominio_id,
                    GoodsReceipt.ativo.is_(True),
                )
            )
        )

        if filters:
            if filters.status:
                query = query.where(GoodsReceipt.status.in_([s.value for s in filters.status]))
            if filters.receipt_type:
                query = query.where(GoodsReceipt.receipt_type.in_([t.value for t in filters.receipt_type]))
            if filters.order_id:
                query = query.where(GoodsReceipt.order_id == filters.order_id)
            if filters.supplier_id:
                query = query.where(GoodsReceipt.supplier_id == filters.supplier_id)
            if filters.date_from:
                query = query.where(GoodsReceipt.receipt_date >= filters.date_from)
            if filters.date_to:
                query = query.where(GoodsReceipt.receipt_date <= filters.date_to)
            if filters.has_divergence is not None:
                query = query.where(GoodsReceipt.has_divergence == filters.has_divergence)
            if filters.search:
                search_term = f"%{filters.search}%"
                query = query.where(
                    or_(
                        GoodsReceipt.number.ilike(search_term),
                        GoodsReceipt.invoice_number.ilike(search_term),
                    )
                )

        query = query.order_by(GoodsReceipt.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count(
        self,
        condominio_id: UUID,
        filters: ReceiptFilter | None = None,
    ) -> int:
        """Conta recebimentos com filtros."""
        query = select(func.count(GoodsReceipt.id)).where(
            and_(
                GoodsReceipt.condominio_id == condominio_id,
                GoodsReceipt.ativo.is_(True),
            )
        )

        if filters:
            if filters.status:
                query = query.where(GoodsReceipt.status.in_([s.value for s in filters.status]))

        result = await self.session.execute(query)
        return result.scalar_one()

    async def update(
        self,
        receipt: GoodsReceipt,
        data: GoodsReceiptUpdate,
    ) -> GoodsReceipt:
        """Atualiza recebimento."""
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(receipt, field):
                setattr(receipt, field, value)
        receipt.updated_at = datetime.utcnow()
        await self.session.flush()
        await self.session.refresh(receipt)
        return receipt

    async def delete(self, receipt: GoodsReceipt) -> None:
        """Deleta recebimento (soft delete)."""
        receipt.ativo = False
        receipt.updated_at = datetime.utcnow()
        await self.session.flush()

    async def get_stats(self, condominio_id: UUID) -> ReceiptStats:
        """Retorna estatísticas de recebimentos."""
        status_query = (
            select(
                GoodsReceipt.status,
                func.count(GoodsReceipt.id).label("count"),
            )
            .where(
                and_(
                    GoodsReceipt.condominio_id == condominio_id,
                    GoodsReceipt.ativo.is_(True),
                )
            )
            .group_by(GoodsReceipt.status)
        )
        status_result = await self.session.execute(status_query)
        status_data = {row.status: row.count for row in status_result}

        type_query = (
            select(
                GoodsReceipt.receipt_type,
                func.count(GoodsReceipt.id).label("count"),
            )
            .where(
                and_(
                    GoodsReceipt.condominio_id == condominio_id,
                    GoodsReceipt.ativo.is_(True),
                )
            )
            .group_by(GoodsReceipt.receipt_type)
        )
        type_result = await self.session.execute(type_query)
        type_data = {row.receipt_type: row.count for row in type_result}

        pending_inspection = status_data.get(ReceiptStatus.EM_CONFERENCIA.value, 0)

        divergence_query = select(func.count(GoodsReceipt.id)).where(
            and_(
                GoodsReceipt.condominio_id == condominio_id,
                GoodsReceipt.ativo.is_(True),
                GoodsReceipt.has_divergence.is_(True),
            )
        )
        divergence_result = await self.session.execute(divergence_query)
        with_divergence = divergence_result.scalar_one()

        total_query = select(func.sum(GoodsReceipt.total_accepted)).where(
            and_(
                GoodsReceipt.condominio_id == condominio_id,
                GoodsReceipt.ativo.is_(True),
            )
        )
        total_result = await self.session.execute(total_query)
        total_received = total_result.scalar_one() or Decimal("0")

        return ReceiptStats(
            total=sum(status_data.values()),
            by_status=status_data,
            by_type=type_data,
            pending_inspection=pending_inspection,
            with_divergence=with_divergence,
            total_received_value=total_received,
        )


class PurchaseApprovalRepository:
    """Repository para aprovações de compra."""

    def __init__(self, session: AsyncSession):
        """Inicializa o repository."""
        self.session = session

    async def create(
        self,
        data: PurchaseApprovalCreate,
    ) -> PurchaseApproval:
        """Cria uma nova aprovação."""
        approval = PurchaseApproval(**data.model_dump())
        self.session.add(approval)
        await self.session.flush()
        await self.session.refresh(approval)
        return approval

    async def get_by_id(self, approval_id: UUID) -> PurchaseApproval | None:
        """Busca aprovação por ID."""
        result = await self.session.execute(
            select(PurchaseApproval).where(
                and_(
                    PurchaseApproval.id == approval_id,
                    PurchaseApproval.ativo.is_(True),
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_by_document(
        self,
        document_id: UUID,
        approval_type: ApprovalType,
    ) -> list[PurchaseApproval]:
        """Busca aprovações de um documento."""
        result = await self.session.execute(
            select(PurchaseApproval)
            .where(
                and_(
                    PurchaseApproval.document_id == document_id,
                    PurchaseApproval.approval_type == approval_type.value,
                    PurchaseApproval.ativo.is_(True),
                )
            )
            .order_by(PurchaseApproval.sequence)
        )
        return list(result.scalars().all())

    async def get_pending_for_approver(
        self,
        approver_id: UUID,
        condominio_id: UUID,
    ) -> list[PurchaseApproval]:
        """Busca aprovações pendentes para um aprovador."""
        result = await self.session.execute(
            select(PurchaseApproval)
            .where(
                and_(
                    PurchaseApproval.approver_id == approver_id,
                    PurchaseApproval.condominio_id == condominio_id,
                    PurchaseApproval.status == ApprovalStatus.PENDENTE.value,
                    PurchaseApproval.ativo.is_(True),
                )
            )
            .order_by(PurchaseApproval.requested_at)
        )
        return list(result.scalars().all())

    async def list(
        self,
        condominio_id: UUID,
        filters: ApprovalFilter | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[PurchaseApproval]:
        """Lista aprovações com filtros."""
        query = select(PurchaseApproval).where(
            and_(
                PurchaseApproval.condominio_id == condominio_id,
                PurchaseApproval.ativo.is_(True),
            )
        )

        if filters:
            if filters.status:
                query = query.where(PurchaseApproval.status.in_([s.value for s in filters.status]))
            if filters.approval_type:
                query = query.where(PurchaseApproval.approval_type.in_([t.value for t in filters.approval_type]))
            if filters.approval_level:
                query = query.where(
                    PurchaseApproval.approval_level.in_([level.value for level in filters.approval_level])
                )
            if filters.approver_id:
                query = query.where(PurchaseApproval.approver_id == filters.approver_id)
            if filters.document_id:
                query = query.where(PurchaseApproval.document_id == filters.document_id)
            if filters.is_overdue:
                query = query.where(
                    and_(
                        PurchaseApproval.deadline < datetime.utcnow(),
                        PurchaseApproval.status == ApprovalStatus.PENDENTE.value,
                    )
                )
            if filters.date_from:
                query = query.where(PurchaseApproval.requested_at >= filters.date_from)
            if filters.date_to:
                query = query.where(PurchaseApproval.requested_at <= filters.date_to)

        query = query.order_by(PurchaseApproval.requested_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count(
        self,
        condominio_id: UUID,
        filters: ApprovalFilter | None = None,
    ) -> int:
        """Conta aprovações com filtros."""
        query = select(func.count(PurchaseApproval.id)).where(
            and_(
                PurchaseApproval.condominio_id == condominio_id,
                PurchaseApproval.ativo.is_(True),
            )
        )

        if filters:
            if filters.status:
                query = query.where(PurchaseApproval.status.in_([s.value for s in filters.status]))

        result = await self.session.execute(query)
        return result.scalar_one()

    async def update(
        self,
        approval: PurchaseApproval,
        data: PurchaseApprovalUpdate,
    ) -> PurchaseApproval:
        """Atualiza aprovação."""
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(approval, field):
                setattr(approval, field, value)
        approval.updated_at = datetime.utcnow()
        await self.session.flush()
        await self.session.refresh(approval)
        return approval

    async def delete(self, approval: PurchaseApproval) -> None:
        """Deleta aprovação (soft delete)."""
        approval.ativo = False
        approval.updated_at = datetime.utcnow()
        await self.session.flush()

    async def get_stats(self, condominio_id: UUID) -> ApprovalStats:  # pylint: disable=too-many-locals
        """Retorna estatísticas de aprovações."""
        status_query = (
            select(
                PurchaseApproval.status,
                func.count(PurchaseApproval.id).label("count"),
            )
            .where(
                and_(
                    PurchaseApproval.condominio_id == condominio_id,
                    PurchaseApproval.ativo.is_(True),
                )
            )
            .group_by(PurchaseApproval.status)
        )
        status_result = await self.session.execute(status_query)
        status_data = {row.status: row.count for row in status_result}

        type_query = (
            select(
                PurchaseApproval.approval_type,
                func.count(PurchaseApproval.id).label("count"),
            )
            .where(
                and_(
                    PurchaseApproval.condominio_id == condominio_id,
                    PurchaseApproval.ativo.is_(True),
                )
            )
            .group_by(PurchaseApproval.approval_type)
        )
        type_result = await self.session.execute(type_query)
        type_data = {row.approval_type: row.count for row in type_result}

        level_query = (
            select(
                PurchaseApproval.approval_level,
                func.count(PurchaseApproval.id).label("count"),
            )
            .where(
                and_(
                    PurchaseApproval.condominio_id == condominio_id,
                    PurchaseApproval.ativo.is_(True),
                )
            )
            .group_by(PurchaseApproval.approval_level)
        )
        level_result = await self.session.execute(level_query)
        level_data = {row.approval_level: row.count for row in level_result}

        pending = status_data.get(ApprovalStatus.PENDENTE.value, 0)

        overdue_query = select(func.count(PurchaseApproval.id)).where(
            and_(
                PurchaseApproval.condominio_id == condominio_id,
                PurchaseApproval.ativo.is_(True),
                PurchaseApproval.status == ApprovalStatus.PENDENTE.value,
                PurchaseApproval.deadline < datetime.utcnow(),
            )
        )
        overdue_result = await self.session.execute(overdue_query)
        overdue = overdue_result.scalar_one()

        avg_time_query = select(func.avg(PurchaseApproval.response_time_hours)).where(
            and_(
                PurchaseApproval.condominio_id == condominio_id,
                PurchaseApproval.ativo.is_(True),
                PurchaseApproval.response_time_hours.isnot(None),
            )
        )
        avg_result = await self.session.execute(avg_time_query)
        avg_time = avg_result.scalar_one()

        approved_count = status_data.get(ApprovalStatus.APROVADO.value, 0)
        total_responded = sum(status_data.get(s.value, 0) for s in [ApprovalStatus.APROVADO, ApprovalStatus.REJEITADO])
        approval_rate = (approved_count / total_responded * 100) if total_responded > 0 else None

        return ApprovalStats(
            total=sum(status_data.values()),
            by_status=status_data,
            by_type=type_data,
            by_level=level_data,
            pending=pending,
            overdue=overdue,
            average_response_hours=float(avg_time) if avg_time else None,
            approval_rate=approval_rate,
        )
