"""Service para fluxo de aprovação de reembolsos."""

import logging
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from modules.reimbursement.models import (
    APPROVAL_LIMITS,
    ApprovalLevel,
    ReimbursementRequest,
    ReimbursementStatus,
)
from modules.reimbursement.repositories.reimbursement_repository import (
    ReimbursementRepository,
)

logger = logging.getLogger(__name__)


class ApprovalService:
    """Service para operações de aprovação de reembolsos."""

    def __init__(self, session: AsyncSession):
        """Inicializa o service."""
        self.session = session
        self.repo = ReimbursementRepository(session)

    async def list_pending_approvals(
        self,
        condominio_id: UUID,
        approval_level: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[ReimbursementRequest], int]:
        """Lista solicitações pendentes de aprovação."""
        return await self.repo.list_pending_approvals(
            condominio_id,
            approval_level,
            skip,
            limit,
        )

    async def start_analysis(
        self,
        request_id: UUID,
        user_id: UUID,
    ) -> ReimbursementRequest | None:
        """Inicia análise de uma solicitação."""
        request = await self.repo.get_request_by_id(request_id)
        if not request:
            return None

        if request.status != ReimbursementStatus.PENDENTE.value:
            raise ValueError("Apenas solicitações pendentes podem entrar em análise")

        request.status = ReimbursementStatus.EM_ANALISE.value
        request.internal_notes = (request.internal_notes or "") + f"\n[Em análise por {user_id}]"

        await self.session.commit()

        logger.info(f"Solicitação {request.code} em análise por {user_id}")
        return request

    async def approve_request(
        self,
        request_id: UUID,
        user_id: UUID,
        comments: str | None = None,
        approved_items: list[UUID] | None = None,
        rejected_items: dict[UUID, str] | None = None,
    ) -> ReimbursementRequest | None:
        """Aprova uma solicitação de reembolso."""
        request = await self.repo.get_request_by_id(request_id)
        if not request:
            return None

        if not request.can_approve:
            raise ValueError(f"Solicitação em status {request.status} não pode ser aprovada")

        # Processa aprovação/rejeição de itens individuais
        if approved_items or rejected_items:
            for item in request.items:
                if not item.is_active:
                    continue

                # chaves chegam como str (JSON) e item.id é UUID: comparar por texto, senão o item
                # rejeitado pelo aprovador era aprovado e pago (revisão 08/09/2026)
                _rej = {str(k): v for k, v in (rejected_items or {}).items()}
                _apr = {str(k) for k in (approved_items or [])}
                if str(item.id) in _rej:
                    item.reject(_rej[str(item.id)])
                elif approved_items:
                    if str(item.id) in _apr:
                        item.approve()
                else:
                    # Se não especificou itens, aprova todos
                    item.approve()
        else:
            # Aprova todos os itens
            for item in request.items:
                if item.is_active:
                    item.approve()

        # Verifica se pelo menos um item foi aprovado
        approved_items_count = len([i for i in request.items if i.is_active and i.is_approved])
        if approved_items_count == 0:
            raise ValueError("Pelo menos um item deve ser aprovado")

        request.approve(user_id, comments)
        await self.session.commit()

        logger.info(f"Solicitação {request.code} aprovada por {user_id}")
        return request

    async def reject_request(
        self,
        request_id: UUID,
        user_id: UUID,
        reason: str,
    ) -> ReimbursementRequest | None:
        """Rejeita uma solicitação de reembolso."""
        request = await self.repo.get_request_by_id(request_id)
        if not request:
            return None

        if not request.can_approve:
            raise ValueError(f"Solicitação em status {request.status} não pode ser rejeitada")

        request.reject(user_id, reason)
        await self.session.commit()

        logger.info(f"Solicitação {request.code} rejeitada por {user_id}: {reason}")
        return request

    async def return_to_draft(
        self,
        request_id: UUID,
        user_id: UUID,
        reason: str,
    ) -> ReimbursementRequest | None:
        """Devolve solicitação para rascunho."""
        request = await self.repo.get_request_by_id(request_id)
        if not request:
            return None

        request.return_to_draft(reason)
        await self.session.commit()

        logger.info(f"Solicitação {request.code} devolvida por {user_id}")
        return request

    async def approve_item(
        self,
        request_id: UUID,
        item_id: UUID,
        user_id: UUID,
        approved_amount: Decimal | None = None,
    ) -> bool:
        """Aprova um item específico."""
        request = await self.repo.get_request_by_id(request_id)
        if not request:
            return False

        if not request.can_approve:
            raise ValueError("Solicitação não está em aprovação")

        item = await self.repo.get_item_by_id(item_id)
        if not item or item.request_id != request_id:
            return False

        item.approve(approved_amount)
        await self.session.commit()

        logger.info(f"Item {item_id} aprovado na solicitação {request.code}")
        return True

    async def reject_item(
        self,
        request_id: UUID,
        item_id: UUID,
        user_id: UUID,
        reason: str,
    ) -> bool:
        """Rejeita um item específico."""
        request = await self.repo.get_request_by_id(request_id)
        if not request:
            return False

        if not request.can_approve:
            raise ValueError("Solicitação não está em aprovação")

        item = await self.repo.get_item_by_id(item_id)
        if not item or item.request_id != request_id:
            return False

        item.reject(reason)
        await self.session.commit()

        logger.info(f"Item {item_id} rejeitado na solicitação {request.code}")
        return True

    async def list_ready_for_payment(
        self,
        condominio_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[ReimbursementRequest], int]:
        """Lista solicitações aprovadas prontas para pagamento."""
        return await self.repo.list_ready_for_payment(condominio_id, skip, limit)

    async def process_payment(
        self,
        request_id: UUID,
        user_id: UUID,
        due_date: date | None = None,
        notes: str | None = None,
    ) -> ReimbursementRequest | None:
        """
        Processa pagamento de reembolso criando conta a pagar.

        Este método integra com o módulo financeiro para criar
        uma conta a pagar correspondente ao reembolso aprovado.
        """
        request = await self.repo.get_request_by_id(request_id)
        if not request:
            return None

        if not request.can_process:
            raise ValueError("Solicitação não está aprovada para processamento")

        # Define data de vencimento (padrão: 5 dias úteis)
        if not due_date:
            due_date = date.today() + timedelta(days=7)

        # Aqui seria feita a integração com o módulo financeiro
        # Para criar a conta a pagar
        # payable = await self._create_payable_account(request, due_date, user_id)

        # Não fingir: gravar um payable_account_id inventado e marcar "processado" fazia a tela
        # dizer que a conta a pagar nasceu quando nada nasceu (revisão 08/09/2026). Cria a conta
        # a pagar de verdade; se o serviço financeiro não aceitar, a falha sobe.
        payable = await self._create_payable_account(request, due_date, user_id)
        if payable is None or getattr(payable, "id", None) is None:
            raise ValueError("Não foi possível criar a conta a pagar do reembolso — processamento não concluído.")
        request.mark_as_processed(user_id, payable.id)

        if notes:
            request.internal_notes = (request.internal_notes or "") + f"\n[Processamento] {notes}"

        await self.session.commit()

        logger.info(f"Solicitação {request.code} processada - Conta a Pagar criada")
        return request

    async def _create_payable_account(
        self,
        request: ReimbursementRequest,
        due_date: date,
        user_id: UUID,
    ):
        """
        Cria conta a pagar a partir do reembolso.

        Este método seria implementado para integrar com o módulo financeiro.
        """
        # Integração REAL com o financeiro (revisão 08/09/2026): antes era um esboço comentado e
        # o processamento gravava um id inventado. Sem commit aqui — quem chama comita.
        from modules.financial.schemas.payable import PayableAccountCreate
        from modules.financial.services.payable_service import PayableService

        payable_data = PayableAccountCreate(
            condominio_id=request.condominio_id,
            description=f"Reembolso {request.code} - {request.title}",
            gross_value=str(request.approved_amount or request.total_amount),
            due_date=due_date,
            payable_type="avulsa",
            cost_center=getattr(request, "cost_center", None),
            notes=f"Reembolso de despesas: {request.description or ''}"[:500],
        )
        return await PayableService(self.session).account_repo.create(payable_data, user_id)

    def check_approval_permission(
        self,
        user_level: str,
        request_level: str,
    ) -> bool:
        """
        Verifica se usuário tem permissão para aprovar.

        Hierarquia de aprovação:
        - FINANCEIRO pode aprovar qualquer valor
        - DIRETOR pode aprovar até DIRETOR
        - GERENTE pode aprovar até GERENTE
        - SUPERVISOR pode aprovar até SUPERVISOR
        """
        level_order = {
            ApprovalLevel.SUPERVISOR.value: 1,
            ApprovalLevel.GERENTE.value: 2,
            ApprovalLevel.DIRETOR.value: 3,
            ApprovalLevel.FINANCEIRO.value: 4,
        }

        user_order = level_order.get(user_level, 0)
        request_order = level_order.get(request_level, 0)

        return user_order >= request_order

    def get_approval_level_for_amount(self, amount: Decimal) -> ApprovalLevel:
        """Retorna o nível de aprovação necessário para um valor."""
        if amount <= APPROVAL_LIMITS[ApprovalLevel.SUPERVISOR]:
            return ApprovalLevel.SUPERVISOR
        elif amount <= APPROVAL_LIMITS[ApprovalLevel.GERENTE]:
            return ApprovalLevel.GERENTE
        elif amount <= APPROVAL_LIMITS[ApprovalLevel.DIRETOR]:
            return ApprovalLevel.DIRETOR
        else:
            return ApprovalLevel.FINANCEIRO
